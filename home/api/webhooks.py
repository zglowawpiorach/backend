"""
Stripe webhook handler.

Verifies signatures and routes events to appropriate handler functions.
See stripe_webhooks_handlers.py for individual handler implementations.
"""

import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

import stripe

from home.api.stripe_webhooks_handlers import (
    handle_checkout_completed,
    handle_checkout_expired,
    handle_coupon_updated,
    handle_promotion_code_updated,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    """
    Handle Stripe webhook events.

    Path: POST /api/webhooks/stripe/

    Verifies signature and routes to appropriate handler based on event type.

    Returns:
        - 200: Event processed successfully (or unsupported event)
        - 400: Invalid signature or request format
        - 500: Webhook not configured
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    if not sig_header:
        logger.error("Stripe webhook received without signature")
        return JsonResponse({"error": "No signature"}, status=400)

    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return JsonResponse({"error": "Webhook not configured"}, status=500)

    try:
        # Verify signature and construct event
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

        logger.info(f"Received Stripe webhook: {event.type}")

        # Route to appropriate handler
        if event.type == "checkout.session.completed":
            handle_checkout_completed(event.data.object)

        elif event.type == "checkout.session.expired":
            handle_checkout_expired(event.data.object.id)

        elif event.type == "coupon.updated":
            handle_coupon_updated(event.data.object)

        elif event.type == "promotion_code.updated":
            handle_promotion_code_updated(event.data.object)

        else:
            # Log unsupported event types but return 200
            logger.debug(f"Unhandled Stripe event type: {event.type}")

        return JsonResponse({"status": "success"}, status=200)

    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid webhook payload: {e}")
        return JsonResponse({"error": "Invalid payload"}, status=400)

    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid webhook signature: {e}")
        return JsonResponse({"error": "Invalid signature"}, status=400)

    except Exception as e:
        # Unexpected error
        logger.exception(f"Unexpected webhook error: {e}")
        return JsonResponse({"error": "Unexpected error"}, status=500)
