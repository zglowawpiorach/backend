from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail import hooks

from .models import Product, Event, Reservation, Coupon


class ProductViewSet(SnippetViewSet):
    model = Product
    icon = "tag"
    menu_label = "Products"
    menu_order = 200
    add_to_admin_menu = True
    list_display = ["nr_w_katalogu_zdjec", "tytul",  "price", "active", "featured", "created_at"]
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

    def discount_display(self, obj):
        if obj.discount_type == 'percent':
            return f"{obj.percent_off}%"
        return f"{obj.amount_off / 100:.2f} PLN"
    discount_display.short_description = 'Zniżka'

    def is_valid_display(self, obj):
        return "Tak" if obj.is_valid else "Nie"
    is_valid_display.short_description = 'Ważny'


register_snippet(ProductViewSet)
register_snippet(EventViewSet)
register_snippet(ReservationViewSet)
register_snippet(CouponViewSet)


@hooks.register('construct_main_menu')
def hide_menu_items(request, menu_items):
    menu_items[:] = [item for item in menu_items if item.name not in ['explorer', 'documents', 'snippets']]
