"""
Stripe synchronization service for Product model.

Handles creating, updating, and deactivating Stripe products and prices,
as well as creating checkout sessions.
"""

import logging
import re
from typing import Optional, List
from datetime import datetime
from django.conf import settings
from django.utils.html import strip_tags
import stripe

# Configure Stripe to use certifi's CA bundle for TLS connections
# This fixes issues where the bundled certificate path is invalid
try:
    import certifi
    stripe.default_ca_bundle_path = certifi.where()
except ImportError:
    pass  # certifi not installed, use Stripe's default

logger = logging.getLogger(__name__)


# Shipping cost in grosze (20 PLN = 2000 grosze)
SHIPPING_COST_GROSZE = 2000
SHIPPING_CURRENCY = "pln"


def _strip_html(text: str) -> str:
    """
    Strip HTML tags and clean up whitespace from text.

    Args:
        text: HTML text to strip

    Returns:
        Plain text with HTML tags removed and whitespace normalized
    """
    if not text:
        return ""

    # Strip HTML tags
    plain = strip_tags(text)

    # Normalize whitespace (remove extra spaces, newlines)
    plain = re.sub(r'\s+', ' ', plain).strip()

    return plain


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
    def _get_discount_amount(product) -> Optional[int]:
        """
        Calculate discount amount in grosze if product has a valid discount price.

        Args:
            product: Product instance

        Returns:
            Discount amount in grosze, or None if no valid discount
        """
        if not product.cena:
            return None

        base_price_grosze = StripeSync._price_to_grosze(product.price)
        discount_price_grosze = StripeSync._price_to_grosze(product.cena)

        # Only return discount if cena is lower than price
        if discount_price_grosze < base_price_grosze:
            return base_price_grosze - discount_price_grosze

        return None

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
            # Strip HTML from description for Stripe (plain text only)
            product_description = _strip_html(product.opis) if product.opis else None

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
        customer_email: Optional[str] = None,
        furgonetka_service_id: Optional[str] = None,
        furgonetka_locker_id: Optional[str] = None,
    ) -> dict:
        """
        Create a Stripe Checkout Session for a single product purchase.

        Args:
            product: Product instance (must be ACTIVE)
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
            customer_email: Optional customer email for pre-filling
            furgonetka_service_id: Furgonetka shipping service ID (e.g., 'inpost', 'dpd')
            furgonetka_locker_id: InPost locker ID if shipping to paczkomat

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
            # If product has a discount price (cena), use price_data to show the discounted price
            # Otherwise, use the existing Stripe Price
            discount_amount = StripeSync._get_discount_amount(product)
            if discount_amount:
                # Use price_data with the discounted price
                final_price_grosze = StripeSync._price_to_grosze(product.cena)
                line_items = [
                    {
                        'price_data': {
                            'currency': SHIPPING_CURRENCY,
                            'product': product.stripe_product_id,
                            'unit_amount': final_price_grosze,
                        },
                        'quantity': 1,
                    }
                ]
                logger.info(f"Using discounted price {final_price_grosze} grosze for product {product.pk} (discount: {discount_amount} grosze)")
            else:
                # Use existing Stripe Price
                line_items = [
                    {
                        'price': product.stripe_price_id,
                        'quantity': 1,
                    }
                ]

            # Build session params
            logger.info(f"[Stripe] Creating single product session with furgonetka_service_id={furgonetka_service_id}, furgonetka_locker_id={furgonetka_locker_id}")
            session_params = {
                'mode': 'payment',
                'line_items': line_items,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': {
                    'product_id': str(product.pk),
                    'furgonetka_service_id': furgonetka_service_id or '',
                    'furgonetka_locker_id': furgonetka_locker_id or '',
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

            # Always enable payment_intent_data for receipt_email
            # If customer_email is provided, use it; otherwise Stripe will use collected email
            session_params['payment_intent_data'] = {
                'receipt_email': customer_email,  # Can be None - Stripe will use collected email
            }

            # Pre-fill customer email if provided
            if customer_email:
                session_params['customer_email'] = customer_email

            # Create the checkout session
            logger.info(f"[Stripe] ========== SENDING TO STRIPE (single product) ==========")
            logger.info(f"[Stripe] Full session_params: {session_params}")
            logger.info(f"[Stripe] =============================================================")

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
        customer_email: Optional[str] = None,
        coupon = None,
        furgonetka_service_id: Optional[str] = None,
        furgonetka_locker_id: Optional[str] = None,
        invoice_creation: bool = False,
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
            coupon: Optional Coupon instance to apply discount
            furgonetka_service_id: Furgonetka shipping service ID (e.g., 'inpost', 'dpd')
            furgonetka_locker_id: InPost locker ID if shipping to paczkomat
            invoice_creation: If True, enable invoice creation, tax ID collection,
                              and business name collection

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
            # Use price_data for products with discount prices, otherwise use Stripe Price
            line_items = []
            for product in products:
                discount = StripeSync._get_discount_amount(product)
                if discount:
                    # Use price_data with the discounted price
                    final_price_grosze = StripeSync._price_to_grosze(product.cena)
                    line_items.append({
                        'price_data': {
                            'currency': SHIPPING_CURRENCY,
                            'product': product.stripe_product_id,
                            'unit_amount': final_price_grosze,
                        },
                        'quantity': 1,
                    })
                    logger.info(f"Using discounted price {final_price_grosze} grosze for product {product.pk} in basket")
                else:
                    # Use existing Stripe Price
                    line_items.append({
                        'price': product.stripe_price_id,
                        'quantity': 1,
                    })

            # Build session params
            logger.info(f"[Stripe] Creating basket session with furgonetka_service_id={furgonetka_service_id}, furgonetka_locker_id={furgonetka_locker_id}, invoice_creation={invoice_creation}")
            session_params = {
                'mode': 'payment',
                'line_items': line_items,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'allow_promotion_codes': True,
                'metadata': {
                    'product_ids': ','.join(str(p.pk) for p in products),
                    'furgonetka_service_id': furgonetka_service_id or '',
                    'furgonetka_locker_id': furgonetka_locker_id or '',
                },
                'billing_address_collection': 'required',
                'shipping_address_collection': {'allowed_countries': ['PL']},
            }

            # Add invoice-related options if requested
            if invoice_creation:
                session_params['invoice_creation'] = {'enabled': True}
                session_params['tax_id_collection'] = {'enabled': True}
                session_params['customer_update'] = {
                    'name': 'auto',
                    'address': 'auto',
                }
                logger.info("[Stripe] Invoice creation enabled with tax ID and name collection")

            # Apply coupon if provided and valid
            if coupon and coupon.is_valid and coupon.stripe_promotion_code_id:
                session_params['discounts'] = [{
                    'promotion_code': coupon.stripe_promotion_code_id
                }]
                logger.info(f"Applied coupon {coupon.code} to checkout session")

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

            # Collect phone number (required for shipping)
            session_params['phone_number_collection'] = {'enabled': True}

            # Always enable payment_intent_data for receipt_email
            # If customer_email is provided, use it; otherwise Stripe will use collected email
            session_params['payment_intent_data'] = {
                'receipt_email': customer_email,  # Can be None - Stripe will use collected email
            }

            # Pre-fill customer email if provided
            if customer_email:
                session_params['customer_email'] = customer_email

            # Create the checkout session
            logger.info(f"[Stripe] ========== SENDING TO STRIPE ==========")
            logger.info(f"[Stripe] Full session_params: {session_params}")
            logger.info(f"[Stripe] =======================================")

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

    @staticmethod
    def create_or_update_coupon(coupon) -> dict:
        """
        Create or update a Stripe Coupon and PromotionCode for the given Coupon.

        If stripe_coupon_id is empty, creates new Stripe Coupon and PromotionCode.
        If stripe_coupon_id exists, updates the Stripe Coupon.

        Args:
            coupon: Coupon instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            is_new = not bool(coupon.stripe_coupon_id)

            # Build coupon params
            coupon_params = {
                'metadata': {
                    'wagtail_id': str(coupon.pk),
                    'code': coupon.code,
                },
            }

            # Set discount
            if coupon.discount_type == 'percent':
                coupon_params['percent_off'] = coupon.percent_off
            else:
                # Convert PLN to grosze (multiply by 100)
                amount_grosze = int(float(coupon.amount_off) * 100)
                coupon_params['amount_off'] = amount_grosze
                coupon_params['currency'] = SHIPPING_CURRENCY

            # Set optional limits
            if coupon.max_redemptions:
                coupon_params['max_redemptions'] = coupon.max_redemptions

            if coupon.expires_at:
                coupon_params['redeem_by'] = int(coupon.expires_at.timestamp())

            if is_new:
                # Create Stripe Coupon
                stripe_coupon = stripe.Coupon.create(**coupon_params)
                coupon.stripe_coupon_id = stripe_coupon.id
                logger.info(f"Created Stripe coupon {stripe_coupon.id} for Coupon {coupon.pk}")

                # Create PromotionCode with the customer-facing code
                promo_params = {
                    'coupon': stripe_coupon.id,
                    'code': coupon.code,
                    'active': coupon.status == 'active',
                    'metadata': {
                        'wagtail_id': str(coupon.pk),
                    },
                }
                stripe_promo = stripe.PromotionCode.create(**promo_params)
                coupon.stripe_promotion_code_id = stripe_promo.id
                logger.info(f"Created Stripe promotion code {stripe_promo.id} for Coupon {coupon.pk}")

            else:
                # Update existing Stripe Coupon
                # Note: Stripe Coupons have limited updatable fields
                stripe.Coupon.modify(
                    coupon.stripe_coupon_id,
                    metadata=coupon_params['metadata'],
                )
                logger.info(f"Updated Stripe coupon {coupon.stripe_coupon_id}")

                # Update PromotionCode active status
                if coupon.stripe_promotion_code_id:
                    stripe.PromotionCode.modify(
                        coupon.stripe_promotion_code_id,
                        active=coupon.status == 'active',
                    )

            # Save the updated IDs
            coupon._skip_stripe_sync = True
            coupon.save(update_fields=['stripe_coupon_id', 'stripe_promotion_code_id'])

            return {'success': True}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def deactivate_coupon(coupon) -> dict:
        """
        Deactivate a coupon by setting its PromotionCode to inactive.

        Args:
            coupon: Coupon instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        if not coupon.stripe_promotion_code_id:
            logger.warning(f"Cannot deactivate Coupon {coupon.pk}: no stripe_promotion_code_id")
            return {'success': False, 'error': 'No stripe_promotion_code_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            stripe.PromotionCode.modify(
                coupon.stripe_promotion_code_id,
                active=False,
            )

            logger.info(f"Deactivated Stripe promotion code {coupon.stripe_promotion_code_id}")
            return {'success': True}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe coupon deactivation error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe coupon deactivation error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def sync_coupon_redemptions(coupon) -> dict:
        """
        Sync times_redeemed from Stripe Coupon.

        Args:
            coupon: Coupon instance

        Returns:
            Dict with 'success' (bool), 'times_redeemed', and optional 'error'
        """
        if not coupon.stripe_coupon_id:
            return {'success': False, 'error': 'No stripe_coupon_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            stripe_coupon = stripe.Coupon.retrieve(coupon.stripe_coupon_id)
            times_redeemed = stripe_coupon.times_redeemed or 0

            # Update local model
            coupon._skip_stripe_sync = True
            coupon.times_redeemed = times_redeemed
            coupon.save(update_fields=['times_redeemed'])

            logger.info(f"Synced times_redeemed={times_redeemed} for Coupon {coupon.pk}")
            return {'success': True, 'times_redeemed': times_redeemed}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
