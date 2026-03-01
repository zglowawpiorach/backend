"""
REST API serializers for Product model and checkout requests.
"""

import logging
from django.utils import timezone
from rest_framework import serializers
from wagtail.images.models import Image
from home.models import Product, ProductStatus, ReservationStatus

logger = logging.getLogger(__name__)


class ProductSerializer(serializers.ModelSerializer):
    """
    Serializer for Product model.

    Includes image URL as a rendition URL for frontend consumption.
    Includes reservation info for displaying reserved status with countdown.
    """
    image_url = serializers.SerializerMethodField()
    is_buyable = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)
    is_reserved = serializers.SerializerMethodField()
    reserved_until = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'tytul',
            'slug',
            'description',
            'opis',
            'price',
            'cena',
            'status',
            'sold_at',
            'image_url',
            'is_buyable',
            'is_reserved',
            'reserved_until',
            'featured',
            'nr_w_katalogu_zdjec',
            'przeznaczenie_ogolne',
            'dla_kogo',
            'dlugosc_kategoria',
            'dlugosc_w_cm',
            'kolor_pior',
            'gatunek_ptakow',
            'kolor_elementow_metalowych',
            'rodzaj_zapiecia',
            'created_at',
            'updated_at',
        ]

    def get_image_url(self, obj):
        """
        Get the product's primary image URL as a rendition.

        Returns fill-800x800 rendition URL or None if no image.
        """
        primary_image = obj.primary_image
        if primary_image:
            try:
                # Get or create a rendition for consistent sizing
                rendition = primary_image.get_rendition('fill-800x800')
                return rendition.url
            except Exception as e:
                logger.warning(f"Could not create rendition for product {obj.pk}: {e}")
                # Fallback to original file URL
                return primary_image.file.url if primary_image.file else None
        return None

    def get_is_reserved(self, obj):
        """
        Check if product has an active (non-expired) reservation.

        Returns True only if:
        - Product status is RESERVED
        - There's a pending reservation
        - Reservation hasn't expired yet

        Frontend should treat product as available if this returns False,
        even if status is 'reserved' (stale reservation).
        """
        if obj.status != ProductStatus.RESERVED:
            return False

        now = timezone.now()

        # Check for active pending reservation that hasn't expired
        active_reservation = obj.reservations.filter(
            reservation__status=ReservationStatus.PENDING,
            reservation__expires_at__gt=now
        ).select_related('reservation').first()

        return active_reservation is not None

    def get_reserved_until(self, obj):
        """
        Get expiration time of active reservation.

        Returns ISO datetime string if product is actively reserved,
        None otherwise.

        Frontend can use this to:
        1. Display countdown timer
        2. Ignore reserved status if time is in the past
        """
        if obj.status != ProductStatus.RESERVED:
            return None

        now = timezone.now()

        # Get the active pending reservation
        active_reservation = obj.reservations.filter(
            reservation__status=ReservationStatus.PENDING,
            reservation__expires_at__gt=now
        ).select_related('reservation').first()

        if active_reservation:
            return active_reservation.reservation.expires_at.isoformat()

        return None


class CheckoutRequestSerializer(serializers.Serializer):
    """
    Serializer for checkout session creation requests.

    Validates required fields for creating a Stripe checkout session.
    """
    product_id = serializers.IntegerField(required=True)
    success_url = serializers.URLField(required=True)
    cancel_url = serializers.URLField(required=True)
    customer_email = serializers.EmailField(required=False, allow_null=True)


class CheckoutResponseSerializer(serializers.Serializer):
    """
    Serializer for checkout session response.
    """
    checkout_url = serializers.URLField()
    session_id = serializers.CharField()


class CheckAvailabilityRequestSerializer(serializers.Serializer):
    """
    Serializer for product availability check requests.
    """
    product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=False
    )


class ReserveBasketRequestSerializer(serializers.Serializer):
    """
    Serializer for basket reservation requests.
    """
    product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=False,
        help_text="List of product IDs to reserve"
    )
    success_url = serializers.URLField(required=True)
    cancel_url = serializers.URLField(required=True)
    customer_email = serializers.EmailField(required=False, allow_null=True)


class UnavailableProductSerializer(serializers.Serializer):
    """Serializer for unavailable product details."""
    id = serializers.IntegerField()
    reason = serializers.CharField()
    message = serializers.CharField()


class CheckAvailabilityResponseSerializer(serializers.Serializer):
    """Serializer for availability check response."""
    available = serializers.ListField(child=serializers.IntegerField())
    unavailable = UnavailableProductSerializer(many=True)


class ReserveBasketResponseSerializer(serializers.Serializer):
    """Serializer for basket reservation response."""
    success = serializers.BooleanField()
    checkout_url = serializers.URLField(required=False, allow_null=True)
    session_id = serializers.CharField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    unavailable_products = UnavailableProductSerializer(many=True, required=False)
    error = serializers.CharField(required=False, allow_null=True)
