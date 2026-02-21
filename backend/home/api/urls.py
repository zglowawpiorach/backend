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
    cleanup_expired_reservations
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
]
