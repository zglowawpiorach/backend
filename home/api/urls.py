"""
URL configuration for the products API.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from home.api.views import (
    ProductViewSet,
    create_checkout,
    check_availability,
    reserve_basket,
    cancel_checkout,
    cleanup_expired_reservations,
    validate_coupon,
    search_inpost_points,
    get_inpost_point
)
from home.api.furgonetka_views import (
    orders,
    order_tracking_number,
    order_payments
)

# Create router for ViewSet
router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')

app_name = 'products_api'

urlpatterns = [
    path('', include(router.urls)),
    path('checkout/', create_checkout, name='checkout'),
    path('check-availability/', check_availability, name='check_availability'),
    path('reserve-basket/', reserve_basket, name='reserve_basket'),
    path('cancel-checkout/', cancel_checkout, name='cancel_checkout'),
    path('cleanup-expired-reservations/', cleanup_expired_reservations, name='cleanup_expired_reservations'),
    path('validate-coupon/', validate_coupon, name='validate_coupon'),

    # InPost Paczkomat search
    path('inpost-points/', search_inpost_points, name='search_inpost_points'),
    path('inpost-points/<str:name>/', get_inpost_point, name='get_inpost_point'),

    # Furgonetka integration endpoints (called BY Furgonetka)
    path('orders', orders, name='furgonetka_orders'),
    path('orders/<str:source_order_id>/tracking_number', order_tracking_number, name='furgonetka_tracking'),
    path('orders/<str:source_order_id>/payments', order_payments, name='furgonetka_payments'),
]
