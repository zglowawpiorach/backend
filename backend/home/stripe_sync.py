"""
Stripe synchronization service for Product model.

Handles creating, updating, and deactivating Stripe products and prices,
as well as creating checkout sessions.
"""

import logging
from typing import Optional, List
from datetime import datetime
from django.conf import settings
import stripe

logger = logging.getLogger(__name__)


# Shipping cost in grosze (20 PLN = 2000 grosze)
SHIPPING_COST_GROSZE = 2000
SHIPPING_CURRENCY = "pln"


class StripeSync:
    """
    Service class for synchronizing Product model with Stripe.

    All methods are static for stateless operation.
    Reads STRIPE_SECRET_KEY from Django settings.
    """

    @staticmethod
    def _get_stripe_api_key() -> str:
        """Get Stripe API key from settings."""
        api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
        if not api_key:
            raise ValueError("STRIPE_SECRET_KEY is not configured in Django settings")
        return api_key

    @staticmethod
    def _build_absolute_url(relative_url: str) -> str:
        """
        Build absolute URL from relative path using PUBLIC_URL setting.

        Args:
            relative_url: Relative URL like '/media/images/image.jpg'

        Returns:
            Full URL like 'https://example.com/media/images/image.jpg'
        """
        if not relative_url:
            return None

        base_url = getattr(settings, 'PUBLIC_URL', '')
        if not base_url:
            logger.warning("PUBLIC_URL not configured, using relative URL for images")
            return relative_url

        # Remove trailing slash from base_url if present
        base_url = base_url.rstrip('/')

        # Ensure relative_url starts with /
        if not relative_url.startswith('/'):
            relative_url = '/' + relative_url

        return f"{base_url}{relative_url}"

    @staticmethod
    def _price_to_grosze(price_value) -> int:
        """
        Convert Decimal price to grosze (integer cents).

        Args:
            price_value: Decimal price value in PLN

        Returns:
            Integer price in grosze (1 PLN = 100 grosze)
        """
        return int(float(price_value) * 100)

    @staticmethod
    def create_or_update_product(product) -> dict:
        """
        Create or update a Stripe Product and Price for the given Product.

        If stripe_product_id is empty, creates a new Stripe Product and Price.
        If stripe_product_id exists, updates the Stripe Product.
        If price changed, archives old Price and creates a new one.

        Args:
            product: Product instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            product_name = product.tytul if product.tytul else product.name
            product_description = product.opis if product.opis else None

            # Build metadata for Stripe product
            metadata = {
                'wagtail_id': str(product.pk),
                'slug': product.slug,
            }

            # Check if this is a new product or update
            is_new = not bool(product.stripe_product_id)

            if is_new:
                # Create new Stripe Product
                # Build absolute URL for product image
                # Note: product.primary_image already returns the wagtailimages.Image object
                product_images: List[str] = []
                if product.primary_image:
                    image_url = product.primary_image.file.url
                    product_images.append(StripeSync._build_absolute_url(image_url))

                stripe_product = stripe.Product.create(
                    name=product_name,
                    description=product_description,
                    active=product.status == 'active',
                    metadata=metadata,
                    images=product_images,
                )

                product.stripe_product_id = stripe_product.id
                logger.info(f"Created Stripe product {stripe_product.id} for Wagtail product {product.pk}")

                # Create new Stripe Price
                price_grosze = StripeSync._price_to_grosze(product.price)
                stripe_price = stripe.Price.create(
                    product=stripe_product.id,
                    unit_amount=price_grosze,
                    currency=SHIPPING_CURRENCY,
                )

                product.stripe_price_id = stripe_price.id
                logger.info(f"Created Stripe price {stripe_price.id} for product {product.pk}")

            else:
                # Update existing Stripe Product
                stripe.Product.modify(
                    product.stripe_product_id,
                    name=product_name,
                    description=product_description,
                    active=product.status == 'active',
                    metadata=metadata,
                )
                logger.info(f"Updated Stripe product {product.stripe_product_id}")

                # Check if price changed - compare with current Stripe price
                current_price_grosze = StripeSync._price_to_grosze(product.price)

                try:
                    current_stripe_price = stripe.Price.retrieve(product.stripe_price_id)
                    price_changed = current_stripe_price.unit_amount != current_price_grosze

                    if price_changed:
                        # Archive old price
                        stripe.Price.modify(
                            product.stripe_price_id,
                            active=False,
                        )
                        logger.info(f"Archived old Stripe price {product.stripe_price_id}")

                        # Create new price
                        new_stripe_price = stripe.Price.create(
                            product=product.stripe_product_id,
                            unit_amount=current_price_grosze,
                            currency=SHIPPING_CURRENCY,
                        )

                        product.stripe_price_id = new_stripe_price.id
                        logger.info(f"Created new Stripe price {new_stripe_price.id} for product {product.pk}")

                except stripe.error.InvalidRequestError as e:
                    logger.warning(f"Could not retrieve current Stripe price: {e}")
                    # Create new price anyway
                    new_stripe_price = stripe.Price.create(
                        product=product.stripe_product_id,
                        unit_amount=current_price_grosze,
                        currency=SHIPPING_CURRENCY,
                    )
                    product.stripe_price_id = new_stripe_price.id
                    logger.info(f"Created replacement Stripe price {new_stripe_price.id}")

            # Save the updated IDs to the product
            # Skip signal to prevent infinite loop
            product._skip_stripe_sync = True
            product.save(update_fields=['stripe_product_id', 'stripe_price_id'])

            return {'success': True}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe sync error for product {product.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe sync error for product {product.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def deactivate_product(product) -> dict:
        """
        Deactivate a Stripe Product (set active=False).

        Args:
            product: Product instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        if not product.stripe_product_id:
            logger.warning(f"Cannot deactivate product {product.pk}: no stripe_product_id")
            return {'success': False, 'error': 'No stripe_product_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            stripe.Product.modify(
                product.stripe_product_id,
                active=False,
            )

            logger.info(f"Deactivated Stripe product {product.stripe_product_id}")
            return {'success': True}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe deactivation error for product {product.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe deactivation error for product {product.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def mark_as_sold(product) -> dict:
        """
        Mark a product as sold by updating status and sold_at,
        and deactivating the Stripe Product.

        Args:
            product: Product instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        try:
            from django.utils import timezone

            # Update product status and sold_at
            product.status = 'sold'
            product.sold_at = timezone.now()
            product.active = False  # Also update legacy field
            product.save(update_fields=['status', 'sold_at', 'active'])

            # Deactivate Stripe product
            if product.stripe_product_id:
                result = StripeSync.deactivate_product(product)
                if not result['success']:
                    logger.warning(f"Product marked as sold but Stripe deactivation failed: {result.get('error')}")

            logger.info(f"Marked product {product.pk} as sold")
            return {'success': True}

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Error marking product {product.pk} as sold: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def create_checkout_session(
        product,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None
    ) -> dict:
        """
        Create a Stripe Checkout Session for a single product purchase.

        Args:
            product: Product instance (must be ACTIVE)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
            customer_email: Optional customer email for pre-filling

        Returns:
            Dict with 'success' (bool), 'checkout_url' (str), and optional 'error' message
        """
        if not product.is_buyable:
            return {'success': False, 'error': 'Product is not buyable'}

        if not product.stripe_price_id:
            return {'success': False, 'error': 'Product has no stripe_price_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            # Ensure success_url has the CHECKOUT_SESSION_ID placeholder
            if '{CHECKOUT_SESSION_ID}' not in success_url:
                if '?' in success_url:
                    success_url = f"{success_url}&session_id={{CHECKOUT_SESSION_ID}}"
                else:
                    success_url = f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}"

            # Build line items
            line_items = [
                {
                    'price': product.stripe_price_id,
                    'quantity': 1,
                }
            ]

            # Build session params
            session_params = {
                'mode': 'payment',
                'line_items': line_items,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': {
                    'product_id': str(product.pk),
                },
            }

            # Add shipping
            session_params['shipping_options'] = [
                {
                    'shipping_rate_data': {
                        'type': 'fixed_amount',
                        'fixed_amount': {
                            'amount': SHIPPING_COST_GROSZE,
                            'currency': SHIPPING_CURRENCY,
                        },
                        'display_name': 'Przesyłka kurierska',
                        'delivery_estimate': {
                            'minimum': {'unit': 'business_day', 'value': 3},
                            'maximum': {'unit': 'business_day', 'value': 7},
                        },
                    },
                }
            ]

            # Add customer email if provided
            if customer_email:
                session_params['customer_email'] = customer_email
                session_params['payment_intent_data'] = {
                    'receipt_email': customer_email,
                }

            # Create the checkout session
            session = stripe.checkout.Session.create(**session_params)

            logger.info(f"Created checkout session {session.id} for product {product.pk}")
            return {
                'success': True,
                'checkout_url': session.url,
                'session_id': session.id,
            }

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Checkout session error for product {product.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Checkout session error for product {product.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def create_basket_checkout_session(
        products: List,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None
    ) -> dict:
        """
        Create a Stripe Checkout Session for multiple products (basket).

        Each product is unique (quantity always 1), but basket can contain
        multiple different products.

        Args:
            products: List of Product instances (all must be ACTIVE and buyable)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
            customer_email: Optional customer email for pre-filling

        Returns:
            Dict with 'success' (bool), 'checkout_url' (str), 'session_id' (str),
            and optional 'error' message
        """
        if not products:
            return {'success': False, 'error': 'Basket is empty'}

        # Validate all products
        for product in products:
            if not product.is_buyable:
                return {'success': False, 'error': f'Product {product.pk} is not buyable'}
            if not product.stripe_price_id:
                return {'success': False, 'error': f'Product {product.pk} has no stripe_price_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            # Ensure success_url has the CHECKOUT_SESSION_ID placeholder
            if '{CHECKOUT_SESSION_ID}' not in success_url:
                if '?' in success_url:
                    success_url = f"{success_url}&session_id={{CHECKOUT_SESSION_ID}}"
                else:
                    success_url = f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}"

            # Build line items - one per product (quantity always 1)
            line_items = [
                {
                    'price': product.stripe_price_id,
                    'quantity': 1,
                }
                for product in products
            ]

            # Build session params
            session_params = {
                'mode': 'payment',
                'line_items': line_items,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': {
                    'product_ids': ','.join(str(p.pk) for p in products),
                },
            }

            # Add shipping (only once, not per product)
            session_params['shipping_options'] = [
                {
                    'shipping_rate_data': {
                        'type': 'fixed_amount',
                        'fixed_amount': {
                            'amount': SHIPPING_COST_GROSZE,
                            'currency': SHIPPING_CURRENCY,
                        },
                        'display_name': 'Przesyłka kurierska',
                        'delivery_estimate': {
                            'minimum': {'unit': 'business_day', 'value': 3},
                            'maximum': {'unit': 'business_day', 'value': 7},
                        },
                    },
                }
            ]

            # Add customer email if provided
            if customer_email:
                session_params['customer_email'] = customer_email
                session_params['payment_intent_data'] = {
                    'receipt_email': customer_email,
                }

            # Create the checkout session
            session = stripe.checkout.Session.create(**session_params)

            product_ids = ','.join(str(p.pk) for p in products)
            logger.info(f"Created checkout session {session.id} for basket [{product_ids}]")
            return {
                'success': True,
                'checkout_url': session.url,
                'session_id': session.id,
            }

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            product_ids = ','.join(str(p.pk) for p in products)
            logger.error(f"Checkout session error for basket [{product_ids}]: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            product_ids = ','.join(str(p.pk) for p in products)
            logger.error(f"Checkout session error for basket [{product_ids}]: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def cancel_checkout_session(session_id: str) -> dict:
        """
        Cancel a Stripe Checkout Session.

        Args:
            session_id: The Stripe checkout session ID to cancel

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            session = stripe.checkout.Session.expire(session_id)

            logger.info(f"Cancelled checkout session {session_id}")
            return {
                'success': True,
                'session_id': session.id,
            }

        except stripe.error.InvalidRequestError as e:
            # Session might already be expired or completed
            error_msg = f"Invalid session: {str(e)}"
            logger.warning(f"Failed to cancel session {session_id}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Error cancelling session {session_id}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Error cancelling session {session_id}: {error_msg}")
            return {'success': False, 'error': error_msg}
