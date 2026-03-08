"""
Brevo (Sendinblue) email service integration.

Brevo API documentation: https://developers.brevo.com/

This service handles:
1. Order confirmation emails (Thank you for purchase)
2. Package sent emails (with tracking)

Configuration is stored in database via BrevoConfig model (Wagtail admin).
Templates are managed in Brevo dashboard for full customization.
"""

import logging
import requests
from typing import Optional, List

from home.models import BrevoConfig

logger = logging.getLogger(__name__)


class BrevoService:
    """
    Brevo email service for sending transactional emails.

    Uses database configuration (BrevoConfig model) for API credentials.
    All email content is rendered via Brevo templates for easy customization.

    Usage:
        brevo = BrevoService()
        brevo.send_order_email(
            email="customer@example.com",
            order_id="123",
            products=[...],
            total_amount=150.00,
            customer_name="Jan",
        )
    """

    BASE_URL = "https://api.brevo.com/v3"

    def __init__(self):
        config = BrevoConfig.get_solo()
        self.api_key = config.api_key
        self.sender_email = config.sender_email
        self.sender_name = config.sender_name
        self.order_template_id = config.thank_you_template_id
        self.shipping_template_id = config.shipping_template_id
        self.newsletter_list_id = config.newsletter_list_id

    def _headers(self) -> dict:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": self.api_key,
        }

    def is_configured(self) -> bool:
        """Check if Brevo is properly configured with API key and sender."""
        return bool(self.api_key and self.sender_email)

    def send_template_email(
        self,
        to_email: str,
        template_id: int,
        params: dict,
        to_name: Optional[str] = None,
    ) -> dict:
        """
        Send a transactional email using a Brevo template.

        Args:
            to_email: Recipient email address
            template_id: Brevo template ID
            params: Template parameters (available in template as {{ params.key }})
            to_name: Recipient name (optional)

        Returns:
            dict with 'success' boolean and 'message_id' or 'error'
        """
        if not self.is_configured():
            logger.error("[Brevo] Not configured - missing API key or sender email")
            return {"success": False, "error": "Brevo not configured"}

        payload = {
            "sender": {
                "email": self.sender_email,
                "name": self.sender_name,
            },
            "to": [{"email": to_email, "name": to_name or ""}],
            "templateId": template_id,
            "params": params,
        }

        logger.info(f"[Brevo] Sending email to {to_email} (template={template_id})")
        logger.debug(f"[Brevo] Email payload: {payload}")

        try:
            response = requests.post(
                f"{self.BASE_URL}/smtp/email",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )

            if response.status_code >= 400:
                logger.error(f"[Brevo] API error {response.status_code}: {response.text}")

            response.raise_for_status()
            data = response.json()
            message_id = data.get("messageId")
            logger.info(f"[Brevo] Email sent to {to_email}: messageId={message_id}")
            return {"success": True, "message_id": message_id}

        except requests.exceptions.RequestException as e:
            logger.error(f"[Brevo] Failed to send email to {to_email}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"[Brevo] Response: {e.response.text}")
            return {"success": False, "error": str(e)}

    def send_order_email(
        self,
        email: str,
        order_id: str,
        products: List[dict],
        total_amount: float,
        customer_name: Optional[str] = None,
        shipping_method: Optional[str] = None,
        shipping_address: Optional[str] = None,
        tracking_number: Optional[str] = None,
        tracking_url: Optional[str] = None,
        carrier: Optional[str] = None,
    ) -> dict:
        """
        Send order confirmation or shipping notification email.

        Uses shipping_template_id if tracking info provided, otherwise order_template_id.

        Args:
            email: Customer email
            order_id: Order reference (transaction ID)
            products: List of products, each with: name, quantity, price, (optional: image, description)
            total_amount: Total order amount in PLN
            customer_name: Customer first name
            shipping_method: Shipping method name (e.g., "InPost Paczkomat")
            shipping_address: Full shipping address string
            tracking_number: Tracking number (triggers shipping email)
            tracking_url: Tracking URL
            carrier: Carrier display name

        Returns:
            dict with 'success' boolean
        """
        # Determine which template to use
        is_shipping = bool(tracking_number)
        template_id = self.shipping_template_id if is_shipping else self.order_template_id

        if not template_id:
            logger.error(f"[Brevo] Missing template ID for {'shipping' if is_shipping else 'order'} email")
            return {"success": False, "error": "Template not configured"}

        # Build template parameters
        params = {
            "customer_name": customer_name or "Kliencie",
            "customer_email": email,
            "order_id": order_id,
            "items": products,
            "total_amount": f"{total_amount:.2f}",
            "shipping_method": shipping_method or "",
            "shipping_address": shipping_address or "",
            "tracking_number": tracking_number or "",
            "tracking_url": tracking_url or "",
            "carrier": carrier or "",
            "is_shipping": is_shipping,
        }

        logger.info(f"[Brevo] Sending {'shipping' if is_shipping else 'order'} email to {email} for order {order_id}")
        logger.debug(f"[Brevo] Order email params: {params}")

        return self.send_template_email(
            to_email=email,
            to_name=customer_name,
            template_id=template_id,
            params=params,
        )

    def send_tracking_email(
        self,
        email: str,
        order_id: str,
        tracking_number: str,
        carrier: str,
        customer_name: Optional[str] = None,
        tracking_url: Optional[str] = None,
    ) -> dict:
        """
        Send shipping notification email with tracking info.

        Simplified method for sending just tracking information
        (e.g., from Furgonetka webhook).

        Args:
            email: Customer email
            order_id: Order reference
            tracking_number: Tracking number
            carrier: Carrier name
            customer_name: Customer first name
            tracking_url: Tracking URL (optional)

        Returns:
            dict with 'success' boolean
        """
        if not self.shipping_template_id:
            logger.error("[Brevo] Missing shipping template ID")
            return {"success": False, "error": "Shipping template not configured"}

        params = {
            "customer_name": customer_name or "Kliencie",
            "customer_email": email,
            "order_id": order_id,
            "items": [],  # Empty for tracking-only emails
            "total_amount": "0.00",
            "shipping_method": "",
            "shipping_address": "",
            "tracking_number": tracking_number,
            "tracking_url": tracking_url or "",
            "carrier": carrier,
            "is_shipping": True,
        }

        logger.info(f"[Brevo] Sending tracking email to {email} for order {order_id}")
        logger.debug(f"[Brevo] Tracking email params: {params}")

        return self.send_template_email(
            to_email=email,
            to_name=customer_name,
            template_id=self.shipping_template_id,
            params=params,
        )

    def subscribe_to_newsletter(self, email: str, name: Optional[str] = None) -> dict:
        """
        Subscribe a contact to the Brevo newsletter list.

        Uses Brevo Contacts API to create or update a contact and add them
        to the configured newsletter list.

        Args:
            email: Subscriber email address
            name: Subscriber name (optional, will be split into first/last name)

        Returns:
            dict with 'success' boolean and 'contact_id' or 'error'
        """
        if not self.newsletter_list_id:
            logger.error("[Brevo] Newsletter list ID not configured")
            return {"success": False, "error": "Newsletter list not configured"}

        if not self.is_configured():
            logger.error("[Brevo] Not configured - missing API key")
            return {"success": False, "error": "Brevo not configured"}

        # Split name into first and last name if provided
        first_name = ""
        last_name = ""
        if name:
            parts = name.strip().split(maxsplit=1)
            if len(parts) >= 1:
                first_name = parts[0]
            if len(parts) >= 2:
                last_name = parts[1]

        payload = {
            "email": email,
            "listIds": [self.newsletter_list_id],
            "updateEnabled": True,  # Update if already exists
            "attributes": {},
        }

        # Add name attributes if provided
        if first_name:
            payload["attributes"]["FIRSTNAME"] = first_name
        if last_name:
            payload["attributes"]["LASTNAME"] = last_name

        logger.info(f"[Brevo] Subscribing {email} to newsletter list {self.newsletter_list_id}")
        logger.debug(f"[Brevo] Newsletter subscription payload: {payload}")

        try:
            response = requests.post(
                f"{self.BASE_URL}/contacts",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )

            if response.status_code >= 400:
                logger.error(f"[Brevo] Newsletter subscription error {response.status_code}: {response.text}")

            response.raise_for_status()
            data = response.json()
            contact_id = data.get("id")
            logger.info(f"[Brevo] Successfully subscribed {email} to newsletter: contact_id={contact_id}")
            return {"success": True, "contact_id": contact_id}

        except requests.exceptions.RequestException as e:
            logger.error(f"[Brevo] Failed to subscribe {email}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"[Brevo] Response: {e.response.text}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[Brevo] Unexpected error subscribing {email}: {e}")
            return {"success": False, "error": str(e)}


# =============================================================================
# JSON EXAMPLE FOR BREVO TEMPLATE TESTING
# =============================================================================
#
# Copy this JSON to Brevo template editor to test rendering:
#
# ORDER CONFIRMATION EMAIL:
# {
#   "customer_name": "Jan",
#   "customer_email": "jan.kowalski@example.com",
#   "order_id": "PIOR-2024-001",
#   "items": [
#     {
#       "name": "Kolczyki Sowa - Srebrne",
#       "quantity": 1,
#       "price": "89.00",
#       "image": "https://zglowawpiorach.pl/media/products/owl-earrings.jpg",
#       "description": "Piękne kolczyki w kształcie sowy"
#     },
#     {
#       "name": "Naszyjnik Pawi",
#       "quantity": 2,
#       "price": "149.00",
#       "image": "https://zglowawpiorach.pl/media/products/peacock-necklace.jpg",
#       "description": "Elegancki naszyjnik z piersiami pawa"
#     }
#   ],
#   "total_amount": "387.00",
#   "shipping_method": "InPost Paczkomat",
#   "shipping_address": "Paczkomat WRO123, ul. Legnicka 58, 54-203 Wrocław",
#   "tracking_number": "",
#   "tracking_url": "",
#   "carrier": "",
#   "is_shipping": false
# }
#
# SHIPPING NOTIFICATION EMAIL:
# {
#   "customer_name": "Anna",
#   "customer_email": "anna.nowak@example.com",
#   "order_id": "PIOR-2024-002",
#   "items": [
#     {
#       "name": "Bransoletka Lawendowa",
#       "quantity": 1,
#       "price": "75.00",
#       "image": "https://zglowawpiorach.pl/media/products/lavender-bracelet.jpg",
#       "description": "Delikatna bransoletka w odcieniu lawendy"
#     }
#   ],
#   "total_amount": "75.00",
#   "shipping_method": "InPost Paczkomat",
#   "shipping_address": "Paczkomat WAW456, ul. Marszałkowska 100, 00-001 Warszawa",
#   "tracking_number": "1234567890123456789012",
#   "tracking_url": "https://inpost.pl/sledzenie/1234567890123456789012",
#   "carrier": "InPost",
#   "is_shipping": true
# }
#
# TRACKING ONLY EMAIL (minimal - from Furgonetka webhook):
# {
#   "customer_name": "Piotr",
#   "customer_email": "piotr.kowalski@example.com",
#   "order_id": "PIOR-2024-003",
#   "items": [],
#   "total_amount": "0.00",
#   "shipping_method": "",
#   "shipping_address": "",
#   "tracking_number": "9876543210987654321098",
#   "tracking_url": "https://inpost.pl/sledzenie/9876543210987654321098",
#   "carrier": "InPost",
#   "is_shipping": true
# }
#
# =============================================================================
# BREVO TEMPLATE SYNTAX EXAMPLES
# =============================================================================
#
# In your Brevo template, use these variables:
#
# Customer:
#   {{ params.customer_name }}      - Customer first name
#   {{ params.customer_email }}     - Customer email
#
# Order:
#   {{ params.order_id }}           - Order reference number
#   {{ params.total_amount }}       - Total amount in PLN (e.g., "150.00")
#
# Items (loop):
#   {{ params.items }}              - Array of products
#   {% for item in params.items %}
#     {{ item.name }}               - Product name
#     {{ item.quantity }}           - Quantity
#     {{ item.price }}              - Unit price
#     {{ item.image }}              - Product image URL
#     {{ item.description }}        - Product description
#   {% endfor %}
#
# Shipping:
#   {{ params.shipping_method }}    - Shipping method name
#   {{ params.shipping_address }}   - Full address
#
# Tracking (for shipping emails):
#   {{ params.tracking_number }}    - Tracking number
#   {{ params.tracking_url }}       - Tracking URL
#   {{ params.carrier }}            - Carrier name
#   {{ params.is_shipping }}        - Boolean: true for shipping email
#
# Conditional example:
#   {% if params.is_shipping %}
#     Twoja przesyłka jest w drodze!
#     Numer śledzenia: {{ params.tracking_number }}
#   {% else %}
#     Dziękujemy za zamówienie!
#   {% endif %}
#
