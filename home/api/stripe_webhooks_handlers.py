"""
Stripe webhook handlers.

Individual handler functions for each Stripe webhook event type.
All handlers are stateless - they don't create local database records,
instead they sync data between Stripe and external services (Furgonetka).
"""

import logging
from typing import Any

import stripe
from django.conf import settings

from home.furgonetka import FurgonetkaService
from home.models import Product, Coupon
from home.stripe_sync import StripeSync
from home.reservation import ReservationService

logger = logging.getLogger(__name__)


def handle_checkout_completed(session: dict) -> None:
    """
    Handle checkout.session.completed event.

    1. Complete reservation (if exists)
    2. Mark products as sold
    3. Create Furgonetka shipping package
    4. Store package ID in Stripe metadata

    Args:
        session: Stripe checkout session object (dict)
    """
    session_id = session.get("id")
    payment_intent_id = session.get("payment_intent")
    metadata = session.get("metadata", {})

    # Prevent duplicate package creation (check Stripe metadata)
    if metadata.get("furgonetka_package_id"):
        logger.info(f"[Webhook] Package already exists for session {session_id}, skipping Furgonetka")
    else:
        # Create Furgonetka package
        try:
            furgonetka = FurgonetkaService()
            package = furgonetka.create_package_from_stripe_session(session)
            package_id = package.get("id") or package.get("package_id", "")

            # Store package_id back in Stripe PaymentIntent metadata
            if payment_intent_id and package_id:
                stripe.PaymentIntent.modify(
                    payment_intent_id,
                    metadata={"furgonetka_package_id": package_id},
                )
                logger.info(f"[Furgonetka] Package {package_id} created for session {session_id}")

        except Exception as e:
            # Log error but don't raise - Stripe requires 200 response
            # Consider adding alerting here (Sentry, Slack, email)
            logger.error(f"[Furgonetka] Failed for session {session_id}: {e}")

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

    # Mark all products as sold
    for product_id in product_ids:
        try:
            product = Product.objects.get(pk=product_id)

            # Set skip flag to prevent signal loop
            product._skip_stripe_sync = True

            # Mark product as sold
            result = StripeSync.mark_as_sold(product)

            if result["success"]:
                logger.info(f"[Webhook] Product {product_id} marked as sold")
            else:
                logger.error(
                    f"[Webhook] Failed to mark product {product_id} as sold: "
                    f"{result.get('error')}"
                )

        except Product.DoesNotExist:
            logger.error(f"[Webhook] Product {product_id} not found")
        except Exception as e:
            logger.exception(f"[Webhook] Error marking product {product_id} as sold: {e}")


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
