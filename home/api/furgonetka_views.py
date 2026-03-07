"""
Furgonetka integration API endpoints.

These endpoints are called BY Furgonetka (not by our frontend).
Furgonetka uses them to:
1. Add orders (POST /orders) - when customer uses Furgonetka checkout
2. Fetch orders (GET /orders) - sync orders from our shop
3. Update tracking (POST /orders/{id}/tracking_number) - after package is shipped

Since we're stateless (no Order model), we:
- Store tracking numbers in Stripe PaymentIntent metadata
- Fetch order data from Stripe when Furgonetka requests it
"""

import logging
from datetime import datetime
from typing import Any, Optional, List

import stripe
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from home.models import Product
from home.brevo import BrevoService

logger = logging.getLogger(__name__)


def _verify_furgonetka_auth(request) -> bool:
    """
    Verify that the request comes from Furgonetka.

    Furgonetka sends Authorization header with the API token we configured.
    """
    auth_header = request.headers.get("Authorization", "")
    expected_token = getattr(settings, "FURGONETKA_API_TOKEN", "")

    if not expected_token:
        logger.warning("FURGONETKA_API_TOKEN not configured")
        return False

    # Furgonetka sends: "Authorization: token <value>"
    token = auth_header.replace("token ", "").replace("Token ", "").strip()
    return token == expected_token


def _get_order_from_stripe(session_id: str) -> Optional[dict]:
    """
    Fetch order data from Stripe checkout session.

    Returns order data in Furgonetka format.
    """
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["payment_intent", "line_items"]
        )
    except stripe.error.StripeError as e:
        logger.error(f"Failed to fetch Stripe session {session_id}: {e}")
        return None

    # Extract data from Stripe session
    metadata = session.get("metadata", {})
    customer = session.get("customer_details", {})
    collected = session.get("collected_information", {})
    shipping = collected.get("shipping_details", {})
    address = shipping.get("address", {})

    payment_intent = session.get("payment_intent", {})
    pi_metadata = payment_intent.get("metadata", {}) if isinstance(payment_intent, dict) else {}

    # Get products from metadata
    product_ids_str = metadata.get("product_ids", "")
    product_id_str = metadata.get("product_id", "")

    products = []
    total_weight = 0

    if product_ids_str:
        product_ids = [int(pid) for pid in product_ids_str.split(",")]
    elif product_id_str:
        product_ids = [int(product_id_str)]
    else:
        product_ids = []

    for pid in product_ids:
        try:
            product = Product.objects.get(pk=pid)
            product_data = {
                "sourceProductId": pid,
                "name": product.name or product.tytul,
                "priceGross": float(product.price),
                "priceNet": float(product.price) / 1.23,  # Assuming 23% VAT
                "vat": 23,
                "taxRate": 23,
                "weight": 0.1,  # Default weight
                "quantity": 1,
                "sku": product.slug,
            }
            products.append(product_data)
            total_weight += 0.1
        except Product.DoesNotExist:
            logger.warning(f"Product {pid} not found for order {session_id}")

    # Build shipping address
    shipping_address = {
        "name": shipping.get("name", "").split()[0] if shipping.get("name") else "",
        "surname": " ".join(shipping.get("name", "").split()[1:]) if shipping.get("name") else "",
        "street": address.get("line1", ""),
        "city": address.get("city", ""),
        "postcode": address.get("postal_code", ""),
        "countryCode": address.get("country", "PL"),
        "phone": customer.get("phone", ""),
        "email": customer.get("email", ""),
    }

    # Build order response
    order = {
        "sourceOrderId": session_id,
        "sourceClientId": customer.get("email", ""),
        "datetimeOrder": datetime.fromtimestamp(session.get("created", 0)).isoformat(),
        "sourceDatetimeChange": datetime.fromtimestamp(session.get("created", 0)).isoformat(),
        "service": metadata.get("furgonetka_service_id", "inpost"),
        "serviceDescription": metadata.get("furgonetka_service_id", "inpost"),
        "status": "paid" if session.get("payment_status") == "paid" else "pending",
        "totalPrice": float(session.get("amount_total", 0)) / 100,
        "shippingCost": 0,  # We don't charge separate shipping
        "shippingMethodId": 1,
        "shippingTaxRate": 23,
        "totalPaid": float(session.get("amount_total", 0)) / 100,
        "codAmount": 0,  # No COD
        "totalWeight": total_weight,
        "point": metadata.get("furgonetka_locker_id", ""),
        "comment": "",
        "shippingAddress": shipping_address,
        "invoiceAddress": shipping_address,  # Same as shipping for now
        "products": products,
        "paymentDatetime": datetime.fromtimestamp(session.get("created", 0)).isoformat(),
        "trackingNumber": pi_metadata.get("tracking_number", ""),
        "furgonetkaPackageId": pi_metadata.get("furgonetka_package_id", ""),
    }

    return order


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def orders(request):
    """
    Handle orders endpoint for Furgonetka integration.

    GET /api/furgonetka/orders
        - Furgonetka fetches orders from our shop
        - Query params: datetime, limit

    POST /api/furgonetka/orders
        - Furgonetka adds an order (when customer uses their checkout)
        - We store minimal order data for tracking
    """
    # Verify auth
    if not _verify_furgonetka_auth(request):
        return Response(
            {"error": "Unauthorized"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if request.method == "GET":
        return _get_orders(request)
    else:
        return _create_order(request)


def _get_orders(request):
    """
    Fetch orders for Furgonetka from Stripe API.

    Query params:
        - datetime: ISO datetime, return orders newer than this
        - limit: max orders to return (default 100)
    """
    datetime_param = request.query_params.get("datetime")
    limit = min(int(request.query_params.get("limit", 100)), 100)

    orders = []

    try:
        # Build Stripe API params
        stripe_params = {
            "limit": limit,
            "status": "complete",  # Only completed checkouts
        }

        # Convert datetime param to timestamp for Stripe
        if datetime_param:
            try:
                dt = datetime.fromisoformat(datetime_param.replace("Z", "+00:00"))
                stripe_params["created"] = {"gt": int(dt.timestamp())}
            except (ValueError, TypeError):
                pass

        # Fetch completed checkout sessions from Stripe
        sessions = stripe.checkout.Session.list(**stripe_params)

        for session in sessions.auto_paging_iter():
            order = _convert_stripe_session_to_order(session)
            if order:
                orders.append(order)

            if len(orders) >= limit:
                break

    except stripe.error.StripeError as e:
        logger.error(f"Failed to fetch orders from Stripe: {e}")
        # Return empty list on error, not 500 (Furgonetka expects valid response)
        return Response([], status=status.HTTP_200_OK)

    return Response(orders, status=status.HTTP_200_OK)


def _convert_stripe_session_to_order(session: dict) -> Optional[dict]:
    """
    Convert a Stripe checkout session to Furgonetka order format.
    """
    # Skip incomplete sessions
    if session.get("status") != "complete":
        return None

    # Skip unpaid sessions (unless it's a valid pending payment)
    payment_status = session.get("payment_status")
    if payment_status not in ("paid", "unpaid"):
        return None

    # Extract data from Stripe session
    metadata = session.get("metadata", {})

    # Skip orders without Furgonetka shipping details
    # (orders from before Furgonetka integration)
    furgonetka_service_id = metadata.get("furgonetka_service_id", "")
    if not furgonetka_service_id:
        logger.debug(f"Skipping session {session.id} - no Furgonetka service ID")
        return None

    # Extract data from Stripe session
    metadata = session.get("metadata", {})
    customer = session.get("customer_details", {}) or {}
    collected = session.get("collected_information", {}) or {}
    shipping = collected.get("shipping_details", {}) or {}
    address = shipping.get("address", {}) or {}

    # Get shipping cost
    shipping_cost = session.get("shipping_cost", {}) or {}
    shipping_amount = shipping_cost.get("amount_total", 0) / 100 if shipping_cost else 0

    # Build shipping address
    shipping_address = {
        "company": customer.get("business_name", ""),
        "name": shipping.get("name", "").split()[0] if shipping.get("name") else "",
        "surname": " ".join(shipping.get("name", "").split()[1:]) if shipping.get("name") else "",
        "street": address.get("line1", ""),
        "city": address.get("city", ""),
        "postcode": address.get("postal_code", ""),
        "countryCode": address.get("country", "PL"),
        "phone": customer.get("phone", ""),
        "email": customer.get("email", ""),
    }

    # Build products from metadata
    products = []
    total_weight = 0

    product_ids_str = metadata.get("product_ids", "")
    product_id_str = metadata.get("product_id", "")

    if product_ids_str:
        product_ids = [int(pid) for pid in product_ids_str.split(",") if pid]
    elif product_id_str:
        product_ids = [int(product_id_str)]
    else:
        product_ids = []

    for pid in product_ids:
        try:
            product = Product.objects.get(pk=pid)
            product_data = {
                "sourceProductId": pid,
                "name": product.name or product.tytul or f"Product {pid}",
                "priceGross": float(product.price) if product.price else 0,
                "priceNet": float(product.price) / 1.23 if product.price else 0,
                "vat": 23,
                "taxRate": 23,
                "weight": 0.1,  # Default weight
                "quantity": 1,
                "sku": product.slug or str(pid),
            }
            products.append(product_data)
            total_weight += 0.1
        except Product.DoesNotExist:
            logger.warning(f"Product {pid} not found for session {session.id}")
            # Include placeholder product
            products.append({
                "sourceProductId": pid,
                "name": f"Product {pid}",
                "priceGross": 0,
                "priceNet": 0,
                "vat": 23,
                "taxRate": 23,
                "weight": 0.1,
                "quantity": 1,
            })
            total_weight += 0.1

    # Determine order status
    status_map = {
        "paid": "paid",
        "unpaid": "pending",
    }
    order_status = status_map.get(payment_status, "pending")

    # Get tracking number from PaymentIntent if available
    tracking_number = ""
    payment_intent_id = session.get("payment_intent")
    if payment_intent_id:
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_id)
            tracking_number = pi.get("metadata", {}).get("tracking_number", "")
        except stripe.error.StripeError:
            pass

    # Build order response
    order = {
        "sourceOrderId": session.id,
        "sourceClientId": customer.get("email", ""),
        "datetimeOrder": datetime.fromtimestamp(session.get("created", 0)).isoformat(),
        "sourceDatetimeChange": datetime.fromtimestamp(session.get("created", 0)).isoformat(),
        "service": metadata.get("furgonetka_service_id", "") or "inpost",
        "serviceDescription": metadata.get("furgonetka_service_id", "") or "InPost",
        "status": order_status,
        "totalPrice": float(session.get("amount_total", 0)) / 100,
        "shippingCost": shipping_amount,
        "shippingMethodId": 1,
        "shippingTaxRate": 23,
        "totalPaid": float(session.get("amount_total", 0)) / 100 if payment_status == "paid" else 0,
        "codAmount": 0,  # No COD - all payments via Stripe
        "totalWeight": total_weight,
        "point": metadata.get("furgonetka_locker_id", ""),
        "comment": "",
        "shippingAddress": shipping_address,
        "invoiceAddress": shipping_address,  # Same as shipping for now
        "products": products,
        "paymentDatetime": datetime.fromtimestamp(session.get("created", 0)).isoformat(),
        "trackingNumber": tracking_number,
    }

    return order


def _create_order(request):
    """
    Create order from Furgonetka checkout.

    This is called when customer completes checkout through Furgonetka's interface.
    Since we're stateless, we acknowledge the order but don't store it locally.
    """
    data = request.data

    cart_id = data.get("cartId")
    service = data.get("service")
    shipping_address = data.get("shippingAddress", {})
    products_data = data.get("products", [])

    logger.info(
        f"[Furgonetka] Order received: cart={cart_id}, service={service}, "
        f"products={len(products_data)}"
    )

    # Generate a source order ID
    source_order_id = f"furgonetka_{cart_id}_{timezone.now().timestamp()}"

    # Build response with order details
    response = {
        "sourceOrderId": source_order_id,
        "sourceClientId": shipping_address.get("email", ""),
        "datetimeOrder": timezone.now().isoformat(),
        "sourceDatetimeChange": timezone.now().isoformat(),
        "service": service,
        "serviceDescription": service,
        "status": "pending",
        "totalPrice": sum(
            p.get("priceGross", 0) * p.get("quantity", 1)
            for p in products_data
        ),
        "shippingCost": 0,
        "shippingMethodId": 1,
        "shippingTaxRate": 23,
        "totalPaid": 0,
        "codAmount": data.get("codAmount", 0),
        "totalWeight": sum(p.get("weight", 0) for p in products_data),
        "point": data.get("point", ""),
        "comment": data.get("comment", ""),
        "shippingAddress": shipping_address,
        "invoiceAddress": data.get("invoiceAddress", shipping_address),
        "products": products_data,
    }

    return Response(response, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def order_tracking_number(request, source_order_id: str):
    """
    Update tracking number for an order.

    POST /api/furgonetka/orders/{source_order_id}/tracking_number

    Called by Furgonetka after package is shipped.
    We store the tracking number and trigger email via Brevo.

    Request body:
    {
        "trackingNumber": "1234567890123"
    }
    """
    # Verify auth
    if not _verify_furgonetka_auth(request):
        return Response(
            {"error": "Unauthorized"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    tracking_number = request.data.get("trackingNumber")

    if not tracking_number:
        return Response(
            {"error": "trackingNumber is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    logger.info(
        f"[Furgonetka] Tracking number received for order {source_order_id}: "
        f"{tracking_number}"
    )

    # If source_order_id is a Stripe session ID, update PaymentIntent metadata
    carrier = request.data.get("carrier", "inpost")  # Optional carrier info

    if source_order_id.startswith("cs_"):
        try:
            session = stripe.checkout.Session.retrieve(source_order_id)
            payment_intent_id = session.get("payment_intent")
            metadata = session.get("metadata", {})

            # Get carrier from session metadata if not provided
            if not carrier or carrier == "inpost":
                carrier = metadata.get("furgonetka_service_id", "inpost")

            if payment_intent_id:
                # Update PaymentIntent metadata with tracking number
                stripe.PaymentIntent.modify(
                    payment_intent_id,
                    metadata={"tracking_number": tracking_number}
                )
                logger.info(
                    f"[Furgonetka] Updated tracking {tracking_number} "
                    f"for payment intent {payment_intent_id}"
                )

            # Send tracking email via Brevo
            customer_details = session.get("customer_details", {})
            customer_email = customer_details.get("email", "")
            customer_name = customer_details.get("name", "")

            if customer_email:
                brevo = BrevoService()
                email_result = brevo.send_tracking_email(
                    email=customer_email,
                    tracking_number=tracking_number,
                    carrier=carrier,
                    order_id=source_order_id,
                    customer_name=customer_name,
                )

                if email_result.get("success"):
                    logger.info(f"[Brevo] Tracking email sent to {customer_email}")
                else:
                    logger.error(
                        f"[Brevo] Failed to send tracking email: "
                        f"{email_result.get('error')}"
                    )

        except stripe.error.StripeError as e:
            logger.error(f"Failed to update tracking in Stripe: {e}")
            # Still return success - we logged the tracking number

    # Store tracking number in cache/logs for Brevo integration
    # When Brevo is integrated, we'll send the email here

    return Response(
        {
            "success": True,
            "sourceOrderId": source_order_id,
            "trackingNumber": tracking_number,
        },
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def order_payments(request, source_order_id: str):
    """
    Add payment information for an order.

    POST /api/furgonetka/orders/{source_order_id}/payments

    Called by Furgonetka to update payment status.

    Request body:
    {
        "paymentStatus": "completed",
        "paidAmount": 200.99
    }
    """
    # Verify auth
    if not _verify_furgonetka_auth(request):
        return Response(
            {"error": "Unauthorized"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    payment_status = request.data.get("paymentStatus")
    paid_amount = request.data.get("paidAmount")

    logger.info(
        f"[Furgonetka] Payment update for order {source_order_id}: "
        f"status={payment_status}, amount={paid_amount}"
    )

    # For stateless approach, just acknowledge the payment
    # When we integrate with Brevo, we can send confirmation emails here

    return Response(
        {
            "success": True,
            "sourceOrderId": source_order_id,
            "paymentStatus": payment_status,
            "paidAmount": paid_amount,
        },
        status=status.HTTP_200_OK
    )
