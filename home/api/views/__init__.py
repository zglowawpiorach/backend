"""
API Views Module.

This module organizes all API views into logical groups:
- product: Product listing and filtering
- checkout: Stripe checkout, reservations, basket management
- coupon: Coupon validation
- newsletter: Newsletter subscription
- inpost: InPost Paczkomat location search
"""

from home.api.views.product import ProductViewSet
from home.api.views.checkout import (
    create_checkout,
    check_availability,
    reserve_basket,
    cancel_checkout,
    cleanup_expired_reservations,
)
from home.api.views.coupon import validate_coupon
from home.api.views.newsletter import subscribe_to_newsletter
from home.api.views.inpost import (
    search_inpost_points,
    get_inpost_point,
)

__all__ = [
    # Product
    'ProductViewSet',
    # Checkout
    'create_checkout',
    'check_availability',
    'reserve_basket',
    'cancel_checkout',
    'cleanup_expired_reservations',
    # Coupon
    'validate_coupon',
    # Newsletter
    'subscribe_to_newsletter',
    # InPost
    'search_inpost_points',
    'get_inpost_point',
]
