"""
REST API views for products and Stripe checkout.
"""

import logging
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from home.models import Product, ProductStatus
from home.api.serializers import (
    ProductSerializer,
    CheckoutRequestSerializer,
    CheckAvailabilityRequestSerializer,
    ReserveBasketRequestSerializer
)
from home.stripe_sync import StripeSync
from home.reservation import ReservationService

logger = logging.getLogger(__name__)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for Product model.

    - Lookup by slug (not id)
    - Default: only ACTIVE products
    - Query param ?status=sold returns sold products
    - Query param ?status=all returns all products
    """
    serializer_class = ProductSerializer
    lookup_field = 'slug'
    permission_classes = [AllowAny]

    def get_queryset(self):
        """
        Filter queryset based on status query parameter.

        Returns:
            - ACTIVE products by default
            - SOLD products if ?status=sold
            - All products if ?status=all
        """
        queryset = Product.objects.prefetch_related('images__image')
        status_filter = self.request.query_params.get('status', 'active')

        if status_filter == 'sold':
            return queryset.filter(status=ProductStatus.SOLD)
        elif status_filter == 'all':
            return queryset.all()
        else:  # default to active
            return queryset.filter(status=ProductStatus.ACTIVE)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_checkout(request):
    """
    Create a Stripe Checkout Session for a product.

    POST /api/v1/checkout/

    Request body:
    {
        "product_id": 123,
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/shop",
        "customer_email": "customer@example.com"  // optional
    }

    Response:
    {
        "checkout_url": "https://checkout.stripe.com/...",
        "session_id": "cs_..."
    }

    Errors:
    - 400: Invalid request data
    - 404: Product not found or not buyable
    """
    serializer = CheckoutRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'error': 'Invalid request', 'details': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_id = serializer.validated_data['product_id']
    success_url = serializer.validated_data['success_url']
    cancel_url = serializer.validated_data['cancel_url']
    customer_email = serializer.validated_data.get('customer_email')

    # Get product
    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check if product is buyable
    if not product.is_buyable:
        return Response(
            {'error': 'Product is not available for purchase'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Create checkout session
    result = StripeSync.create_checkout_session(
        product=product,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
    )

    if result['success']:
        return Response({
            'checkout_url': result['checkout_url'],
            'session_id': result.get('session_id'),
        }, status=status.HTTP_200_OK)
    else:
        logger.error(f"Checkout creation failed: {result.get('error')}")
        return Response(
            {'error': 'Failed to create checkout session', 'details': result.get('error')},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def check_availability(request):
    """
    Check if products are available for adding to basket.

    POST /api/v1/check-availability/

    Request body:
    {
        "product_ids": [1, 5, 9]
    }

    Response:
    {
        "available": [1, 5],
        "unavailable": [
            {"id": 9, "reason": "reserved", "message": "Produkt jest zarezerwowany przez innego klienta"}
        ]
    }

    The 'reason' field can be:
    - 'reserved': Product is reserved by another customer
    - 'sold': Product has been sold
    - 'inactive': Product is inactive
    - 'not_found': Product doesn't exist
    """
    serializer = CheckAvailabilityRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'error': 'Invalid request', 'details': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_ids = serializer.validated_data['product_ids']

    # Check availability using reservation service
    result = ReservationService.check_product_availability(product_ids)

    return Response(result, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def reserve_basket(request):
    """
    Create checkout session AND reserve products atomically.

    This replaces the regular checkout endpoint when using a basket.
    Products are reserved for 10 minutes while customer completes payment.

    POST /api/v1/reserve-basket/

    Request body:
    {
        "product_ids": [1, 5, 9],
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/shop",
        "customer_email": "optional@example.com"
    }

    Response (success):
    {
        "success": true,
        "checkout_url": "https://checkout.stripe.com/...",
        "session_id": "cs_...",
        "expires_at": "2026-02-17T12:30:00Z"
    }

    Response (some products unavailable):
    {
        "success": false,
        "unavailable_products": [
            {"id": 9, "reason": "reserved", "message": "Produkt jest zarezerwowany..."}
        ]
    }

    Errors:
    - 400: Invalid request data
    - 500: Server error
    """
    serializer = ReserveBasketRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'error': 'Invalid request', 'details': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_ids = serializer.validated_data['product_ids']
    success_url = serializer.validated_data['success_url']
    cancel_url = serializer.validated_data['cancel_url']
    customer_email = serializer.validated_data.get('customer_email')

    # Validate product IDs exist
    products = list(Product.objects.filter(pk__in=product_ids))

    if len(products) != len(product_ids):
        found_ids = {p.pk for p in products}
        missing_ids = set(product_ids) - found_ids
        unavailable = [
            {'id': pid, 'reason': 'not_found', 'message': 'Produkt nie został znaleziony'}
            for pid in missing_ids
        ]
        return Response({
            'success': False,
            'unavailable_products': unavailable
        }, status=status.HTTP_200_OK)

    # First, create Stripe checkout session (lightweight operation)
    stripe_result = StripeSync.create_basket_checkout_session(
        products=products,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email
    )

    if not stripe_result['success']:
        logger.error(f"Stripe checkout creation failed: {stripe_result.get('error')}")
        return Response(
            {'success': False, 'error': 'Failed to create checkout session'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    stripe_session_id = stripe_result['session_id']

    # Now reserve products with the session ID
    reservation_result = ReservationService.reserve_products(
        products=products,
        stripe_session_id=stripe_session_id,
        customer_email=customer_email
    )

    if not reservation_result['success']:
        # Cancel the Stripe session since reservation failed
        # Note: We can't actually cancel Stripe sessions, but they'll expire
        logger.warning(
            f"Stripe session {stripe_session_id} created but reservation failed: "
            f"{reservation_result.get('error')}"
        )

        unavailable = reservation_result.get('unavailable_products', [])
        return Response({
            'success': False,
            'unavailable_products': unavailable
        }, status=status.HTTP_200_OK)

    # Success - return checkout URL
    from django.utils.timezone import localtime
    expires_at = reservation_result['expires_at']

    return Response({
        'success': True,
        'checkout_url': stripe_result['checkout_url'],
        'session_id': stripe_session_id,
        'expires_at': localtime(expires_at).isoformat()
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def cancel_checkout(request):
    """
    Cancel a checkout session and release reserved products.

    POST /api/v1/cancel-checkout/

    Request body:
    {
        "session_id": "cs_test_..."
    }

    Response (success):
    {
        "success": true,
        "message": "Checkout session cancelled and products released"
    }

    Response (session not found):
    {
        "success": false,
        "error": "Reservation not found"
    }
    """
    from home.stripe_sync import StripeSync
    from home.reservation import ReservationService

    session_id = request.data.get('session_id')

    if not session_id:
        return Response(
            {'success': False, 'error': 'session_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # First cancel the Stripe checkout session
    stripe_result = StripeSync.cancel_checkout_session(session_id)

    # Then cancel our internal reservation (this works even if Stripe session is already expired)
    reservation_result = ReservationService.cancel_reservation(session_id)

    if not reservation_result['success']:
        return Response({
            'success': False,
            'error': reservation_result.get('error', 'Failed to cancel reservation')
        }, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'success': True,
        'message': 'Checkout session cancelled and products released'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def cleanup_expired_reservations(request):
    """
    Clean up expired reservations.

    This endpoint is meant to be called periodically (e.g., every 5 minutes)
    by a cron job or background process to release products from reservations
    that have expired but haven't been cancelled by Stripe webhooks.

    POST /api/v1/cleanup-expired-reservations/

    Response:
    {
        "success": true,
        "cancelled": 5,
        "message": "Cancelled 5 expired reservation(s)"
    }
    """
    from django.utils import timezone
    from home.models import Reservation

    now = timezone.now()

    # Find pending/active reservations that have expired
    expired_reservations = Reservation.objects.filter(
        status__in=['pending', 'active'],
        expires_at__lt=now
    )

    count = expired_reservations.count()

    if count == 0:
        return Response({
            'success': True,
            'cancelled': 0,
            'message': 'No expired reservations found'
        }, status=status.HTTP_200_OK)

    # Cancel each expired reservation using the service
    cancelled = 0
    for reservation in expired_reservations:
        result = ReservationService.cancel_reservation(reservation.stripe_session_id)
        if result['success']:
            cancelled += 1

    return Response({
        'success': True,
        'cancelled': cancelled,
        'message': f'Cancelled {cancelled}/{count} expired reservation(s)'
    }, status=status.HTTP_200_OK)
