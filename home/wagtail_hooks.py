import logging
import re

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail import hooks
from wagtail.admin.action_menu import ActionMenuItem
from wagtail.admin.ui.tables import Column
from django.urls import path, reverse
from django.http import JsonResponse, HttpResponseRedirect
from django.views import View
from django.contrib import messages
from django.contrib.auth.decorators import permission_required, login_required
from django.utils.decorators import method_decorator
from django.db import models as db_models
from django.shortcuts import get_object_or_404
from django.utils.html import format_html, strip_tags
from django.utils.safestring import mark_safe

from .models import (
    Product, Event, Reservation, Coupon, PickupPoint, InPostPoint,
    FurgonetkaConfig, FurgonetkaService, BrevoConfig, Transaction, TransactionStatus
)

logger = logging.getLogger(__name__)


def _strip_html(text: str, max_length: int = None) -> str:
    """
    Strip HTML tags and clean up whitespace from text.

    Args:
        text: HTML text to strip
        max_length: Optional maximum length (will truncate with ...)

    Returns:
        Plain text with HTML tags removed and whitespace normalized
    """
    if not text:
        return ""

    # Strip HTML tags
    plain = strip_tags(text)

    # Normalize whitespace (remove extra spaces, newlines)
    plain = re.sub(r'\s+', ' ', plain).strip()

    # Truncate if needed
    if max_length and len(plain) > max_length:
        plain = plain[:max_length].rstrip() + "..."

    return plain


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


class TransactionViewSet(SnippetViewSet):
    model = Transaction
    icon = 'credit-card'
    menu_label = 'Transakcje'
    menu_name = 'transactions'
    menu_order = 205
    add_to_admin_menu = True
    list_display = ['id', 'customer_email', 'get_products_display', 'total_amount', 'status', 'created_at', 'mark_sent_action']
    list_filter = ['status', 'created_at']
    search_fields = ['customer_email', 'stripe_session_id', 'customer_name']
    readonly_fields = ['stripe_session_id', 'customer_email', 'customer_name', 'products', 'shipping_method', 'shipping_address', 'total_amount', 'created_at']

    panels = [
        MultiFieldPanel([
            FieldPanel('stripe_session_id', read_only=True),
            FieldPanel('customer_email', read_only=True),
            FieldPanel('customer_name', read_only=True),
            FieldPanel('total_amount', read_only=True),
        ], heading="Klient"),
        MultiFieldPanel([
            FieldPanel('shipping_method', read_only=True),
            FieldPanel('shipping_address', read_only=True),
        ], heading="Dostawa"),
        MultiFieldPanel([
            FieldPanel('products', read_only=True),
        ], heading="Produkty"),
        MultiFieldPanel([
            FieldPanel('status'),
            FieldPanel('tracking_number'),
            FieldPanel('carrier'),
        ], heading="Status i śledzenie"),
    ]

    def get_admin_urls(self):
        urls = super().get_admin_urls()
        urls += [
            path(
                f'{self.model._meta.model_name}/<int:pk>/mark-sent/',
                self.mark_sent_view,
                name=f'{self.model._meta.model_name}_mark_sent'
            ),
        ]
        return urls

    @method_decorator(login_required)
    def mark_sent_view(self, request, pk):
        """Mark transaction as sent and send email."""
        transaction = get_object_or_404(Transaction, pk=pk)

        if transaction.status == TransactionStatus.SENT:
            messages.warning(request, "Transakcja jest już oznaczona jako wysłana.")
        else:
            # Update status
            transaction.status = TransactionStatus.SENT
            transaction.save(update_fields=['status'])

            # Send email via Brevo
            try:
                from home.services import BrevoService
                brevo = BrevoService()

                # Build items list for email template
                items = []
                for product in transaction.products.all():
                    # Get first product image
                    image_url = ""
                    first_image = product.images.first()
                    if first_image and first_image.image:
                        image_url = first_image.image.file.url

                    items.append({
                        "name": product.name or product.tytul or f"Product #{product.id}",
                        "category": product.get_przeznaczenie_ogolne_display() if hasattr(product, 'przeznaczenie_ogolne') else "",
                        "description": _strip_html(product.description or product.opis or "", max_length=100),
                        "quantity": 1,
                        "price": f"{float(product.cena):.2f}" if product.cena else "0.00",
                        "image": image_url,
                    })

                # Carrier display name
                carrier_names = {
                    "inpost": "InPost Paczkomat",
                    "inpostkurier": "InPost Kurier",
                    "dpd": "Kurier DPD",
                    "ups": "Kurier UPS",
                    "gls": "Kurier GLS",
                    "fedex": "Kurier FedEx",
                    "dhl": "Kurier DHL",
                    "poczta": "Poczta Polska",
                    "orlen": "Orlen Paczka",
                }
                carrier_display = carrier_names.get(transaction.carrier, transaction.carrier or "Kurier")

                # Build tracking URL
                tracking_urls = {
                    "inpost": f"https://inpost.pl/sledzenie-przesylek?number={transaction.tracking_number}",
                    "inpostkurier": f"https://inpost.pl/sledzenie-przesylek?number={transaction.tracking_number}",
                    "dpd": f"https://tracktrace.dpd.com.pl/parcelDetails?p1={transaction.tracking_number}",
                    "ups": f"https://www.ups.com/track?tracknum={transaction.tracking_number}",
                    "gls": f"https://gls-group.eu/PL/pl/sledzenie-paczek?match={transaction.tracking_number}",
                    "fedex": f"https://www.fedex.com/fedextrack/?trknbr={transaction.tracking_number}",
                    "dhl": f"https://www.dhl.com/pl-pl/home/tracking/tracking-parcel.html?submit=1&tracking-id={transaction.tracking_number}",
                    "poczta": f"https://emonitoring.poczta-polska.pl/?numer={transaction.tracking_number}",
                    "orlen": f"https://orlenpaczka.pl/sledzenie/{transaction.tracking_number}",
                }
                tracking_url = tracking_urls.get(transaction.carrier, "")

                # Log before sending
                email_params = {
                    "email": transaction.customer_email,
                    "order_id": str(transaction.id),
                    "products": items,
                    "total_amount": float(transaction.total_amount),
                    "customer_name": transaction.customer_name,
                    "shipping_method": transaction.shipping_method,
                    "shipping_address": transaction.shipping_address,
                    "tracking_number": transaction.tracking_number,
                    "tracking_url": tracking_url,
                    "carrier": carrier_display,
                }
                logger.info(
                    f"[Brevo] Sending order email from admin panel: "
                    f"email={transaction.customer_email}, order={transaction.id}, "
                    f"tracking={transaction.tracking_number}"
                )
                logger.debug(f"[Brevo] Order email params: {email_params}")

                # Send the email using template
                result = brevo.send_order_email(**email_params)

                logger.debug(f"[Brevo] Order email result: {result}")

                messages.success(request, f"Transakcja #{transaction.id} oznaczona jako wysłana. Email wysłany do {transaction.customer_email}")
            except Exception as e:
                messages.error(request, f"Błąd wysyłania emaila: {e}")

        # Redirect back to list view
        return HttpResponseRedirect(reverse('admin_snippets_home_transaction:list'))


register_snippet(ProductViewSet)
register_snippet(EventViewSet)
register_snippet(ReservationViewSet)
register_snippet(CouponViewSet)
register_snippet(PickupPointViewSet)
register_snippet(FurgonetkaConfigViewSet)
register_snippet(FurgonetkaServiceViewSet)
register_snippet(BrevoConfigViewSet)
register_snippet(TransactionViewSet)


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
