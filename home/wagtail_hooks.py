from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail import hooks
from django.urls import path
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import permission_required
from django.utils.decorators import method_decorator
from django.db import models as db_models

from .models import (
    Product, Event, Reservation, Coupon, PickupPoint, InPostPoint,
    FurgonetkaConfig, FurgonetkaService, BrevoConfig
)


class ProductViewSet(SnippetViewSet):
    model = Product
    icon = "tag"
    menu_label = "Products"
    menu_order = 200
    add_to_admin_menu = True
    list_display = ["nr_w_katalogu_zdjec", "tytul", "price", "active", "featured", "created_at"]
    list_filter = ["active", "created_at"]
    search_fields = ["tytul", "description", "nr_w_katalogu_zdjec"]


class EventViewSet(SnippetViewSet):
    model = Event
    icon = "date"
    menu_label = "Events"
    menu_order = 201
    add_to_admin_menu = True
    list_display = ["title", "location", "start_date", "end_date", "active"]
    list_filter = ["active", "start_date"]
    search_fields = ["title", "location", "description"]


class ReservationViewSet(SnippetViewSet):
    model = Reservation
    icon = "lock"
    menu_label = "Reservations"
    menu_order = 202
    add_to_admin_menu = True
    list_display = ["stripe_session_id", "status", "reserved_at", "expires_at", "customer_email"]
    list_filter = ["status", "reserved_at", "expires_at"]
    search_fields = ["stripe_session_id", "customer_email"]


class CouponViewSet(SnippetViewSet):
    model = Coupon
    icon = 'tag'
    menu_label = 'Kupony'
    menu_name = 'coupons'
    menu_order = 203
    add_to_admin_menu = True
    list_display = ['code', 'status', 'discount_display', 'times_redeemed', 'expires_at', 'is_valid_display']
    list_filter = ['status', 'discount_type']
    search_fields = ['code']


class PickupPointViewSet(SnippetViewSet):
    model = PickupPoint
    icon = 'site'
    menu_label = 'Punkty odbioru'
    menu_name = 'pickup_points'
    menu_order = 204
    add_to_admin_menu = True
    list_display = ['name', 'street', 'city', 'postcode', 'is_default', 'active']
    list_filter = ['active', 'is_default']
    search_fields = ['name', 'street', 'city']


class FurgonetkaConfigViewSet(SnippetViewSet):
    model = FurgonetkaConfig
    icon = 'cog'
    menu_label = 'Furgonetka'
    menu_name = 'furgonetka_config'
    menu_order = 300
    add_to_admin_menu = True
    list_display = ['__str__', 'sandbox', 'sender_name', 'sender_city']


class FurgonetkaServiceViewSet(SnippetViewSet):
    model = FurgonetkaService
    icon = 'truck'
    menu_label = 'Usługi Furgonetka'
    menu_name = 'furgonetka_services'
    menu_order = 301
    add_to_admin_menu = True
    list_display = ['name', 'service_id', 'active']
    list_filter = ['active']
    search_fields = ['name', 'service_id']


class BrevoConfigViewSet(SnippetViewSet):
    model = BrevoConfig
    icon = 'mail'
    menu_label = 'Brevo (Email)'
    menu_name = 'brevo_config'
    menu_order = 302
    add_to_admin_menu = True
    list_display = ['__str__', 'sender_email', 'sender_name']


register_snippet(ProductViewSet)
register_snippet(EventViewSet)
register_snippet(ReservationViewSet)
register_snippet(CouponViewSet)
register_snippet(PickupPointViewSet)
register_snippet(FurgonetkaConfigViewSet)
register_snippet(FurgonetkaServiceViewSet)
register_snippet(BrevoConfigViewSet)


@hooks.register('construct_main_menu')
def hide_menu_items(request, menu_items):
    menu_items[:] = [item for item in menu_items if item.name not in ['explorer', 'documents', 'snippets']]


@hooks.register('register_admin_urls')
def register_inpost_search_url():
    """Register URL for InPost search autocomplete."""
    return [
        path(
            'inpost-search/',
            InPostSearchView.as_view(),
            name='inpost_search'
        ),
    ]


class InPostSearchView(View):
    """API endpoint for searching InPost points in admin."""

    @method_decorator(permission_required('home.view_pickuppoint', raise_exception=True))
    def get(self, request):
        q = request.GET.get('q', '').strip()
        if len(q) < 2:
            return JsonResponse([], safe=False)

        points = InPostPoint.objects.filter(
            active=True
        ).filter(
            db_models.Q(name__icontains=q) |
            db_models.Q(city__icontains=q) |
            db_models.Q(street__icontains=q)
        )[:20]

        results = [
            {
                'name': p.name,
                'street': p.street,
                'building_number': p.building_number,
                'postcode': p.postcode,
                'city': p.city,
                'full_address': p.full_address,
            }
            for p in points
        ]
        return JsonResponse(results, safe=False)
