"""
Models package for the Piorka e-commerce platform.

Organized into separate modules for better maintainability:
- product.py: Product, ProductImage, ProductStatus, ProductAdminForm
- event.py: Event, EventImage
- page.py: HomePage
- reservation.py: Reservation, ReservedProduct  ReservationStatus
- coupon.py: Coupon, CouponStatus
- shipping.py: PickupPoint, InPostPoint
- furgonetka.py: FurgonetkaConfig, FurgonetkaService
- brevo.py: BrevoConfig
- transaction.py: Transaction, TransactionStatus
"""

from .product import Product, ProductImage, ProductStatus, ProductAdminForm
from .event import Event, EventImage
from .page import HomePage
from .reservation import Reservation, ReservedProduct, ReservationStatus
from .coupon import Coupon, CouponStatus
from .shipping import PickupPoint, InPostPoint
from .furgonetka import FurgonetkaConfig, FurgonetkaService
from .brevo import BrevoConfig
from .transaction import Transaction, TransactionStatus

__all__ = [
    'Product',
    'ProductImage',
    'ProductStatus',
    'ProductAdminForm',
    'Event',
    'EventImage',
    'HomePage',
    'Reservation',
    'ReservedProduct',
    'ReservationStatus',
    'Coupon',
    'CouponStatus',
    'PickupPoint',
    'InPostPoint',
    'FurgonetkaConfig',
    'FurgonetkaService',
    'BrevoConfig',
    'Transaction',
    'TransactionStatus',
]
