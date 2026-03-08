"""
Stripe webhook handlers.

Individual handler functions for each Stripe webhook event type.
Creates Transaction records for order tracking in admin.
"""

import logging
import re
from typing import Any, List

import stripe
from django.conf import settings
from django.utils.html import strip_tags

from home.services import FurgonetkaService, StripeSync, ReservationService, BrevoService
from home.models import Product, Coupon, Transaction

logger = logging.getLogger(__name__)


def _strip_html(text: str, max_length: int = 100) -> str:
    """
    Strip HTML tags and clean up whitespace from text.

    Args:
        text: HTML text to strip
        max_length: Maximum length of returned text (default 100)

    Returns:
        Plain text with HTML tags removed, whitespace normalized, and truncated
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


def _extract_customer_details(session: dict) -> dict:
    """
    Extract customer details from Stripe checkout session.

    Returns dict with: email, name, shipping_address
    """
    customer_details = session.get("customer_details", {}) or {}
    shipping_details = session.get("shipping_details", {}) or {}

    # Prefer shipping name over customer name (gift purchases)
    shipping_name = shipping_details.get("name", "")
    customer_name = customer_details.get("name", "")
    name = shipping_name or customer_name or ""

    # Get email
    email = customer_details.get("email", "")

    # Get shipping address
    shipping_address = {}
    if shipping_details.get("address"):
        addr = shipping_details["address"]
        parts = [addr.get("line1", "")]
        if addr.get("line2"):
            parts.append(addr["line2"])
        parts.append(f"{addr.get('postal_code', '')} {addr.get('city', '')}")
        shipping_address = ", ".join(parts)

    return {
        "email": email,
        "name": name,
        "shipping_address": shipping_address,
    }


def _get_shipping_method(metadata: dict) -> str:
    """Get shipping method display name from metadata."""
    service_id = metadata.get("furgonetka_service_id", "")
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
    return carrier_names.get(service_id, service_id or "Dostawa")


def handle_checkout_completed(session: dict) -> None:
    """
    Handle checkout.session.completed event.

    1. Complete reservation (if exists)
    2. Mark products as sold
    3. Create Transaction record for admin tracking
    4. Create Furgonetka shipping package

    Args:
        session: Stripe checkout session object (dict)
    """
    session_id = session.get("id")
    payment_intent_id = session.get("payment_intent")
    metadata = session.get("metadata", {})

    # Extract customer details
    customer = _extract_customer_details(session)
    customer_email = customer["email"]
    customer_name = customer["name"]
    shipping_address = customer["shipping_address"]
    shipping_method = _get_shipping_method(metadata)

    # Get product IDs from reservation or metadata
    product_ids = []

    # First, try to complete the reservation if it exists
    reservation_result = ReservationService.complete_reservation(session_id)

    if reservation_result["success"]:
        # Reservation found and completed - get product IDs from it
        product_ids = reservation_result.get("product_ids", [])
        logger.info(f"[Webhook] Completed reservation for session {session_id}")
    elif "not found" not in reservation_result.get("error", ""):
        # Log unexpected errors but don't fail the webhook
        logger.warning(
            f"[Webhook] Reservation completion failed for session {session_id}: "
            f"{reservation_result.get('error')}"
        )

    # If no reservation, fall back to metadata (for single product checkout)
    product_ids_str = metadata.get("product_ids")
    product_id_str = metadata.get("product_id")

    if not product_ids and product_id_str:
        product_ids = [int(product_id_str)]
    elif not product_ids and product_ids_str:
        product_ids = [int(pid) for pid in product_ids_str.split(",")]

    if not product_ids:
        logger.error(f"[Webhook] Checkout session {session_id} has no product IDs")
        return

    # Get product objects and calculate total
    products = []
    total_amount = 0
    for product_id in product_ids:
        try:
            product = Product.objects.get(pk=product_id)
            products.append(product)
            total_amount += float(product.cena) if product.cena else 0
        except Product.DoesNotExist:
            logger.error(f"[Webhook] Product {product_id} not found")

    if not products:
        logger.error(f"[Webhook] No valid products found for session {session_id}")
        return

    # Mark all products as sold
    for product in products:
        try:
            # Set skip flag to prevent signal loop
            product._skip_stripe_sync = True

            # Mark product as sold
            result = StripeSync.mark_as_sold(product)

            if result["success"]:
                logger.info(f"[Webhook] Product {product.id} marked as sold")
            else:
                logger.error(
                    f"[Webhook] Failed to mark product {product.id} as sold: "
                    f"{result.get('error')}"
                )

        except Exception as e:
            logger.exception(f"[Webhook] Error marking product {product.id} as sold: {e}")

    # Create Transaction record
    transaction, created = Transaction.objects.get_or_create(
        stripe_session_id=session_id,
        defaults={
            "customer_email": customer_email,
            "customer_name": customer_name,
            "shipping_method": shipping_method,
            "shipping_address": shipping_address,
            "total_amount": total_amount,
            "carrier": metadata.get("furgonetka_service_id", ""),
        }
    )

    if created:
        # Add products to transaction
        transaction.products.set(products)
        logger.info(f"[Webhook] Created transaction #{transaction.id} for session {session_id}")
    else:
        logger.info(f"[Webhook] Transaction already exists for session {session_id}")

    # Create Furgonetka package
    package_id = None
    tracking_number = None

    # Prevent duplicate package creation (check Stripe metadata)
    if metadata.get("furgonetka_package_id"):
        logger.info(f"[Webhook] Package already exists for session {session_id}, skipping Furgonetka")
        package_id = metadata.get("furgonetka_package_id")
    else:
        try:
            furgonetka = FurgonetkaService()
            package = furgonetka.create_package_from_stripe_session(session)
            package_id = package.get("id") or package.get("package_id", "")
            tracking_number = package.get("tracking_number") or package.get("number", "") or package_id

            # Store package_id back in Stripe PaymentIntent metadata
            if payment_intent_id and package_id:
                stripe.PaymentIntent.modify(
                    payment_intent_id,
                    metadata={"furgonetka_package_id": package_id},
                )
                logger.info(f"[Furgonetka] Package {package_id} created for session {session_id}")

            # Update transaction with tracking info
            if tracking_number:
                transaction.tracking_number = tracking_number
                transaction.save(update_fields=["tracking_number"])

        except Exception as e:
            # Log error but don't raise - Stripe requires 200 response
            logger.error(f"[Furgonetka] Failed for session {session_id}: {e}")

    # Send order confirmation email via Brevo
    if customer_email:
        try:
            brevo = BrevoService()

            # Build items list for email template
            items = []
            for product in products:
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

            logger.info(
                f"[Brevo] Sending order confirmation email: "
                f"email={customer_email}, order={transaction.id}, "
                f"products={len(items)}, total={total_amount}"
            )

            email_result = brevo.send_order_email(
                email=customer_email,
                order_id=str(transaction.id),
                products=items,
                total_amount=total_amount,
                customer_name=customer_name,
                shipping_method=shipping_method,
                shipping_address=shipping_address,
            )

            if email_result.get("success"):
                logger.info(f"[Brevo] Order confirmation email sent to {customer_email}")
                logger.debug(f"[Brevo] Order email result: {email_result}")
            else:
                logger.error(
                    f"[Brevo] Failed to send order confirmation email: "
                    f"{email_result.get('error')}"
                )

        except Exception as e:
            # Log error but don't fail the webhook
            logger.error(f"[Brevo] Exception sending order email to {customer_email}: {e}")


def handle_checkout_expired(session_id: str) -> None:
    """
    Handle checkout.session.expired event.

    Cancels any pending reservation for the expired session.

    Args:
        session_id: Stripe checkout session ID
    """
    logger.info(f"[Webhook] Checkout session {session_id} expired, cancelling reservation")

    cancel_result = ReservationService.cancel_reservation(session_id)
    if cancel_result["success"]:
        logger.info(f"[Webhook] Cancelled reservation for expired session {session_id}")
    elif "not found" not in cancel_result.get("error", ""):
        logger.warning(
            f"[Webhook] Failed to cancel reservation for expired session {session_id}: "
            f"{cancel_result.get('error')}"
        )


def handle_coupon_updated(stripe_coupon: dict) -> None:
    """
    Handle coupon.updated event.

    Syncs times_redeemed from Stripe to local Coupon model.

    Args:
        stripe_coupon: Stripe coupon object (dict)
    """
    wagtail_id = stripe_coupon.get("metadata", {}).get("wagtail_id")

    if not wagtail_id:
        return

    try:
        coupon = Coupon.objects.get(pk=int(wagtail_id))
        result = StripeSync.sync_coupon_redemptions(coupon)
        if result["success"]:
            logger.info(f"[Webhook] Synced coupon {wagtail_id} redemptions from Stripe")
    except Coupon.DoesNotExist:
        logger.warning(f"[Webhook] Coupon {wagtail_id} not found for webhook sync")


def handle_promotion_code_updated(stripe_promo: dict) -> None:
    """
    Handle promotion_code.updated event.

    Syncs active status from Stripe to local Coupon model.

    Args:
        stripe_promo: Stripe promotion code object (dict)
    """
    wagtail_id = stripe_promo.get("metadata", {}).get("wagtail_id")

    if not wagtail_id:
        return

    try:
        coupon = Coupon.objects.get(pk=int(wagtail_id))
        new_status = "active" if stripe_promo.get("active") else "inactive"

        if coupon.status != new_status:
            coupon._skip_stripe_sync = True
            coupon.status = new_status
            coupon.save(update_fields=["status"])
            logger.info(f"[Webhook] Updated coupon {wagtail_id} status from Stripe webhook")
    except Coupon.DoesNotExist:
        logger.warning(f"[Webhook] Coupon {wagtail_id} not found for webhook sync")
