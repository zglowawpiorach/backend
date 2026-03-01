"""
Stripe webhook handler.

Processes webhook events from Stripe, specifically checkout.session.completed
to mark products as sold when payment is successful.
"""

import logging
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

import stripe

from home.models import Product
from home.stripe_sync import StripeSync
from home.reservation import ReservationService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    """
    Handle Stripe webhook events.

    Path: POST /api/webhooks/stripe/

    Processes checkout.session.completed events to mark products as sold.

    Returns:
        - 200: Event processed successfully (or unsupported event)
        - 400: Invalid signature or request format

    The webhook verifies the Stripe signature using STRIPE_WEBHOOK_SECRET
    and marks the associated product as sold.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    if not sig_header:
        logger.error("Stripe webhook received without signature")
        return JsonResponse({'error': 'No signature'}, status=400)

    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return JsonResponse({'error': 'Webhook not configured'}, status=500)

    try:
        # Verify signature and construct event
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )

        logger.info(f"Received Stripe webhook: {event.type}")

        # Handle checkout.session.completed event
        if event.type == 'checkout.session.completed':
            session = event.data.object
            metadata = session.metadata

            # Check if this is a basket checkout (multiple products)
            product_ids_str = metadata.get('product_ids')
            product_id_str = metadata.get('product_id')

            try:
                product_ids = []

                # First, try to complete the reservation if it exists
                reservation_result = ReservationService.complete_reservation(session.id)

                if reservation_result['success']:
                    # Reservation found and completed - get product IDs from it
                    product_ids = reservation_result.get('product_ids', [])
                    logger.info(f"Completed reservation for session {session.id}")
                elif 'not found' not in reservation_result.get('error', ''):
                    # Log unexpected errors but don't fail the webhook
                    logger.warning(
                        f"Reservation completion failed for session {session.id}: "
                        f"{reservation_result.get('error')}"
                    )

                # If no reservation, fall back to metadata (for single product checkout)
                if not product_ids and product_id_str:
                    product_ids = [int(product_id_str)]
                elif not product_ids and product_ids_str:
                    product_ids = [int(pid) for pid in product_ids_str.split(',')]

                if not product_ids:
                    logger.error(f"Checkout session {session.id} has no product IDs")
                    return JsonResponse(
                        {'error': 'No product IDs in metadata or reservation'},
                        status=400
                    )

                # Mark all products as sold
                for product_id in product_ids:
                    try:
                        product = Product.objects.get(pk=product_id)

                        # Set skip flag to prevent signal loop
                        product._skip_stripe_sync = True

                        # Mark product as sold
                        result = StripeSync.mark_as_sold(product)

                        if result['success']:
                            logger.info(f"Product {product_id} marked as sold via webhook")
                        else:
                            logger.error(
                                f"Failed to mark product {product_id} as sold: "
                                f"{result.get('error')}"
                            )

                    except Product.DoesNotExist:
                        logger.error(f"Product {product_id} not found in webhook handler")
                    except Exception as e:
                        logger.exception(
                            f"Error marking product {product_id} as sold: {str(e)}"
                        )

            except ValueError:
                logger.error(f"Invalid product_id in metadata")
                return JsonResponse({'error': 'Invalid product_id'}, status=400)
            except Exception as e:
                logger.exception(f"Error processing checkout.session.completed: {str(e)}")
                return JsonResponse({'error': 'Processing error'}, status=500)

        elif event.type == 'checkout.session.expired':
            # Handle expired checkout sessions - cancel reservation
            session_id = event.data.object.id
            logger.info(f"Checkout session {session_id} expired, cancelling reservation")

            cancel_result = ReservationService.cancel_reservation(session_id)
            if cancel_result['success']:
                logger.info(f"Cancelled reservation for expired session {session_id}")
            elif 'not found' not in cancel_result.get('error', ''):
                logger.warning(
                    f"Failed to cancel reservation for expired session {session_id}: "
                    f"{cancel_result.get('error')}"
                )

        else:
            # Log unsupported event types but return 200
            logger.debug(f"Unhandled Stripe event type: {event.type}")

        return JsonResponse({'status': 'success'}, status=200)

    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid webhook payload: {str(e)}")
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid webhook signature: {str(e)}")
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception as e:
        # Unexpected error
        logger.exception(f"Unexpected webhook error: {str(e)}")
        return JsonResponse({'error': 'Unexpected error'}, status=500)
