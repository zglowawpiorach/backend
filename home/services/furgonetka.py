"""
Furgonetka shipping service integration.

Furgonetka API documentation: https://furgonetka.pl/api

This service handles:
1. Authentication with OAuth2
2. Searching for delivery points (paczkomats, service points)
3. Creating shipping packages
"""

import base64
import logging
import requests
from django.core.cache import cache

from home.models import PickupPoint, FurgonetkaConfig, FurgonetkaService as FurgonetkaServiceModel

logger = logging.getLogger(__name__)


class FurgonetkaService:
    """Furgonetka API integration service."""

    SANDBOX_URL = "https://api.sandbox.furgonetka.pl"
    PRODUCTION_URL = "https://api.furgonetka.pl"

    def __init__(self):
        # Load configuration from database
        self.config = FurgonetkaConfig.get_solo()

        use_sandbox = self.config.sandbox
        self.BASE_URL = self.SANDBOX_URL if use_sandbox else self.PRODUCTION_URL
        logger.info(f"[Furgonetka] Initialized with BASE_URL={self.BASE_URL}, sandbox={use_sandbox}")

    def _get_token(self) -> str:
        token = cache.get("furgonetka_token")
        if token:
            return token

        refresh = cache.get("furgonetka_refresh")
        if refresh:
            return self._refresh(refresh)

        return self._login()

    def _basic_auth(self) -> str:
        raw = f"{self.config.client_id}:{self.config.client_secret}"
        return base64.b64encode(raw.encode()).decode()

    def _login(self) -> str:
        url = f"{self.BASE_URL}/oauth/token"
        logger.info(f"[Furgonetka] Login request to: {url}")
        r = requests.post(
            url,
            headers={"Authorization": f"Basic {self._basic_auth()}"},
            data={
                "grant_type": "password",
                "scope": "api",
                "username": self.config.username,
                "password": self.config.password,
            },
        )
        r.raise_for_status()
        data = r.json()
        cache.set("furgonetka_token", data["access_token"], 29 * 86400)
        cache.set("furgonetka_refresh", data["refresh_token"], 88 * 86400)
        return data["access_token"]

    def _refresh(self, refresh_token: str) -> str:
        r = requests.post(
            f"{self.BASE_URL}/oauth/token",
            headers={"Authorization": f"Basic {self._basic_auth()}"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        r.raise_for_status()
        data = r.json()
        cache.set("furgonetka_token", data["access_token"], 29 * 86400)
        cache.set("furgonetka_refresh", data["refresh_token"], 88 * 86400)
        return data["access_token"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def get_services(self) -> list:
        """Pobierz dostępne metody wysyłki — wywołaj raz żeby zobaczyć service_id."""
        r = requests.get(f"{self.BASE_URL}/account/services", headers=self._headers(), json={})
        r.raise_for_status()
        return r.json()

    def search_points(
        self,
        service: str = "inpost",
        postcode: str = None,
        city: str = None,
        point_id: str = None,
        limit: int = 20,
    ) -> list:
        """
        Search for delivery points (paczkomats, service points, etc.).

        Args:
            service: Service name - "inpost", "dpd", "dhl", "poczta", etc.
            postcode: Postcode to search near
            city: City to search in
            point_id: Specific point ID to look up
            limit: Max results (1-2000, default 100)

        Returns:
            List of point objects with code, name, address, etc.
        """
        payload = {
            "location": {},
            "filters": {
                "services": [service],
                "limit": limit,
            },
        }

        if point_id:
            payload["filters"]["point_id"] = point_id
        elif postcode:
            payload["location"]["address"] = {
                "postcode": postcode,
                "country_code": "PL",
            }
        elif city:
            payload["location"]["address"] = {
                "city": city,
                "country_code": "PL",
            }
        else:
            # Default to Warsaw center if no location specified
            payload["location"]["coordinates"] = {
                "latitude": 52.2297,
                "longitude": 21.0122,
            }

        logger.info(f"[Furgonetka] Searching points with payload: {payload}")

        r = requests.post(
            f"{self.BASE_URL}/points/map",
            headers=self._headers(),
            json=payload,
        )

        logger.info(f"[Furgonetka] Points search response: {r.status_code}")
        r.raise_for_status()
        data = r.json()
        return data.get("points", [])

    def create_package_from_stripe_session(self, session: dict) -> dict:
        """
        Główna metoda. Przyjmuje surowy Stripe checkout.session
        i tworzy przesyłkę w Furgonetce. Nie dotyka bazy danych.
        Zwraca pełny response z Furgonetki (zawiera package_id).
        """
        # — Wyciągnij dane z Stripe session —
        collected = session.get("collected_information", {})
        shipping = collected.get("shipping_details", {})
        address = shipping.get("address", {})
        customer = session.get("customer_details", {})

        # Receiver name from shipping details (recipient, not buyer)
        receiver_name = shipping.get("name", "")
        receiver_email = customer.get("email", "")
        receiver_phone = customer.get("phone") or ""  # wymaga phone_number_collection!
        receiver_street = address.get("line1", "")
        receiver_city = address.get("city", "")
        receiver_postcode = address.get("postal_code", "")

        # — Wybrana metoda wysyłki (zapisana w Stripe metadata podczas checkout) —
        metadata = session.get("metadata", {})
        service_name = metadata.get("furgonetka_service_id", "inpost")  # nazwa usługi lub ID
        locker_id = metadata.get("furgonetka_locker_id")  # opcjonalne dla paczkomatów

        # — Count products for parcel size calculation —
        product_ids_str = metadata.get("product_ids", "")
        product_count = len([p for p in product_ids_str.split(",") if p.strip()]) if product_ids_str else 1
        if product_count < 1:
            product_count = 1

        # Calculate parcel dimensions based on product count
        # Each product = 0.5kg
        # Small (1-2):  38x59x8   cm
        # Medium (3-10): 38x59x19  cm
        # Large (11+):   38x59x41  cm
        parcel_width = 38
        parcel_depth = 59

        if product_count <= 2:
            parcel_height = 8   # Small
            parcel_label = "Small"
        elif product_count <= 10:
            parcel_height = 19  # Medium
            parcel_label = "Medium"
        else:
            parcel_height = 41  # Large
            parcel_label = "Large"

        parcel_weight = product_count * 0.5

        logger.info(f"[Furgonetka] Parcel: {parcel_label} ({product_count} products, {parcel_weight}kg, {parcel_width}x{parcel_depth}x{parcel_height}cm)")

        # Resolve service name to ID from database
        if service_name.isdigit():
            service_id = int(service_name)
        else:
            # Look up service by name in database
            try:
                service_obj = FurgonetkaServiceModel.objects.get(name__iexact=service_name, active=True)
                service_id = int(service_obj.service_id)
            except FurgonetkaServiceModel.DoesNotExist:
                raise ValueError(
                    f"Nie znaleziono usługi '{service_name}'. "
                    f"Dodaj FurgonetkaService w adminie."
                )

        # — Pobierz domyślny punkt odbioru —
        pickup_point = PickupPoint.get_default() or PickupPoint.get_first_active()
        if not pickup_point:
            raise ValueError("Brak skonfigurowanego punktu odbioru. Dodaj PickupPoint w adminie.")

        # User reference number max 36 chars - use last 36 chars of session ID
        session_id = session["id"]
        user_ref = session_id[-36:] if len(session_id) > 36 else session_id

        payload = {
            "service_id": service_id,
            "type": "package",
            "user_reference_number": user_ref,
            "sender": {
                "name": self.config.sender_name,
                "email": self.config.sender_email,
                "phone": self.config.sender_phone,
                "street": self.config.sender_street,
                "city": self.config.sender_city,
                "postcode": self.config.sender_postcode,
            },
            "pickup": {
                "name": self.config.sender_name,  # wymagane
                "email": self.config.sender_email,  # wymagane
                "phone": self.config.sender_phone,
                "street": pickup_point.street,
                "city": pickup_point.city,
                "postcode": pickup_point.postcode,
            },
            "receiver": {
                "name": receiver_name,
                "email": receiver_email,
                "phone": receiver_phone,
                "street": receiver_street,
                "city": receiver_city,
                "postcode": receiver_postcode,
                "country_code": "PL",
            },
            "parcels": [{
                "weight": parcel_weight,
                "width": parcel_width,
                "depth": parcel_depth,
                "height": parcel_height,
            }],
        }

        if locker_id:
            # Only add point for paczkomat delivery
            # Note: Sandbox and production have different point codes
            # Sandbox points may need to be validated separately
            payload["receiver"]["point"] = locker_id
            logger.info(f"[Furgonetka] Adding locker/point: {locker_id}")

        # Add pickup point if configured
        if pickup_point.point:
            payload["pickup"]["point"] = pickup_point.point

        logger.info(f"[Furgonetka] Creating package with payload: {payload}")
        logger.info(f"[Furgonetka] POST to: {self.BASE_URL}/packages")

        r = requests.post(f"{self.BASE_URL}/packages", headers=self._headers(), json=payload)

        logger.info(f"[Furgonetka] Response status: {r.status_code}")
        logger.info(f"[Furgonetka] Response body: {r.text[:500] if r.text else 'empty'}")

        r.raise_for_status()
        return r.json()
