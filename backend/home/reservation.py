"""
Product reservation service for preventing race conditions.

Handles reserving products during checkout, releasing reservations
via Stripe webhooks when payment is completed or checkout expires.
"""

import logging
from typing import List, Optional, Dict
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from home.models import Product, ProductStatus, Reservation, ReservationStatus, ReservedProduct

logger = logging.getLogger(__name__)

# Default reservation timeout in minutes (should match Stripe checkout expiration)
DEFAULT_RESERVATION_MINUTES = 30  # Stripe default is 30 minutes for checkout sessions


class ReservationService:
    """
    Service class for managing product reservations.

    All methods are static for stateless operation.
    Uses database transactions to ensure atomicity and prevent race conditions.

    Relies on Stripe webhooks for reservation lifecycle:
    - Products reserved when checkout session is created
    - checkout.session.completed -> marks products as sold
    - checkout.session.expired -> releases products back to active
    """

    @staticmethod
    def reserve_products(
        products: List[Product],
        stripe_session_id: str,
        timeout_minutes: int = DEFAULT_RESERVATION_MINUTES,
        customer_email: Optional[str] = None
    ) -> Dict:
        """
        Reserve products when checkout session is created.

        Uses select_for_update() to prevent race conditions when multiple
        users try to buy the same product simultaneously.

        Args:
            products: List of Product instances to reserve
            stripe_session_id: Stripe checkout session ID
            timeout_minutes: Minutes until reservation expires (default: 30, should match Stripe)
            customer_email: Optional customer email

        Returns:
            Dict with:
                - success (bool): Whether reservation was created
                - reservation (Reservation): Created reservation instance
                - unavailable_products (list): Products that couldn't be reserved
                - error (str): Error message if failed
        """
        unavailable_products = []

        try:
            with transaction.atomic():
                # Lock products for update to prevent race conditions
                product_ids = [p.pk for p in products]
                locked_products = list(
                    Product.objects
                    .select_for_update()
                    .filter(pk__in=product_ids)
                )

                # Create a dict for easy lookup
                product_map = {p.pk: p for p in locked_products}

                # Check all products are still buyable
                for product in products:
                    locked_product = product_map.get(product.pk)
                    if not locked_product:
                        unavailable_products.append({
                            'id': product.pk,
                            'name': product.name,
                            'reason': 'not_found',
                            'message': 'Produkt nie został znaleziony'
                        })
                        continue

                    if locked_product.status != ProductStatus.ACTIVE:
                        status_reasons = {
                            ProductStatus.RESERVED: 'Produkt jest zarezerwowany przez innego klienta',
                            ProductStatus.SOLD: 'Produkt został już sprzedany',
                            ProductStatus.INACTIVE: 'Produkt jest nieaktywny',
                        }
                        unavailable_products.append({
                            'id': product.pk,
                            'name': product.name,
                            'reason': locked_product.status,
                            'message': status_reasons.get(
                                locked_product.status,
                                'Produkt jest niedostępny'
                            )
                        })

                if unavailable_products:
                    # Rollback transaction - no reservation created
                    return {
                        'success': False,
                        'unavailable_products': unavailable_products,
                        'error': 'Some products are not available'
                    }

                # All products available - create reservation
                expires_at = timezone.now() + timedelta(minutes=timeout_minutes)

                reservation = Reservation.objects.create(
                    stripe_session_id=stripe_session_id,
                    status=ReservationStatus.PENDING,
                    expires_at=expires_at,
                    customer_email=customer_email
                )

                # Create ReservedProduct relations and update product status
                reserved_products = []
                for product in locked_products:
                    ReservedProduct.objects.create(
                        reservation=reservation,
                        product=product
                    )
                    reserved_products.append(product)

                # Update product status to RESERVED
                Product.objects.filter(pk__in=product_ids).update(
                    status=ProductStatus.RESERVED
                )

                product_ids_str = ','.join(str(p.pk) for p in reserved_products)
                logger.info(
                    f"Created reservation {reservation.id} for session "
                    f"{stripe_session_id}, products [{product_ids_str}], "
                    f"expires at {expires_at}"
                )

                return {
                    'success': True,
                    'reservation': reservation,
                    'expires_at': expires_at
                }

        except Exception as e:
            error_msg = f"Error creating reservation: {str(e)}"
            logger.exception(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    @staticmethod
    def complete_reservation(stripe_session_id: str) -> Dict:
        """
        Mark reservation as completed after successful payment.

        Called by checkout.session.completed webhook.
        Products will be marked as SOLD by the webhook handler.

        Args:
            stripe_session_id: Stripe checkout session ID

        Returns:
            Dict with 'success' (bool), 'reservation', and 'product_ids'
        """
        try:
            with transaction.atomic():
                reservation = Reservation.objects.select_for_update().get(
                    stripe_session_id=stripe_session_id
                )

                if reservation.status != ReservationStatus.PENDING:
                    logger.warning(
                        f"Reservation {reservation.id} is not pending "
                        f"(status: {reservation.status}), cannot complete"
                    )
                    return {
                        'success': False,
                        'error': f'Reservation is not pending (status: {reservation.status})'
                    }

                reservation.status = ReservationStatus.COMPLETED
                reservation.completed_at = timezone.now()
                reservation.save(update_fields=['status', 'completed_at'])

                logger.info(
                    f"Completed reservation {reservation.id} "
                    f"for session {stripe_session_id}"
                )

                # Get reserved products for marking as sold
                reserved_products = list(
                    reservation.reserved_products.select_related('product').all()
                )
                product_ids = [rp.product.pk for rp in reserved_products]

                return {
                    'success': True,
                    'reservation': reservation,
                    'product_ids': product_ids
                }

        except Reservation.DoesNotExist:
            logger.error(f"Reservation for session {stripe_session_id} not found")
            return {
                'success': False,
                'error': 'Reservation not found'
            }
        except Exception as e:
            error_msg = f"Error completing reservation: {str(e)}"
            logger.exception(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    @staticmethod
    def cancel_reservation(stripe_session_id: str) -> Dict:
        """
        Cancel reservation and release products back to ACTIVE status.

        Called by checkout.session.expired webhook when checkout expires
        without payment.

        Args:
            stripe_session_id: Stripe checkout session ID

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        try:
            with transaction.atomic():
                reservation = Reservation.objects.select_for_update().get(
                    stripe_session_id=stripe_session_id
                )

                if reservation.status != ReservationStatus.PENDING:
                    logger.warning(
                        f"Reservation {reservation.id} is not pending "
                        f"(status: {reservation.status}), cannot cancel"
                    )
                    return {
                        'success': False,
                        'error': f'Reservation is not pending (status: {reservation.status})'
                    }

                # Get product IDs before deleting reservation
                product_ids = list(
                    reservation.reserved_products.values_list('product_id', flat=True)
                )

                # Update reservation status to EXPIRED (for expired checkouts)
                reservation.status = ReservationStatus.EXPIRED
                reservation.save(update_fields=['status'])

                # Release products back to ACTIVE
                Product.objects.filter(pk__in=product_ids).update(
                    status=ProductStatus.ACTIVE
                )

                product_ids_str = ','.join(str(pid) for pid in product_ids)
                logger.info(
                    f"Cancelled reservation {reservation.id} for session "
                    f"{stripe_session_id}, released products [{product_ids_str}]"
                )

                return {
                    'success': True,
                    'reservation': reservation,
                    'released_product_ids': product_ids
                }

        except Reservation.DoesNotExist:
            logger.error(f"Reservation for session {stripe_session_id} not found")
            return {
                'success': False,
                'error': 'Reservation not found'
            }
        except Exception as e:
            error_msg = f"Error cancelling reservation: {str(e)}"
            logger.exception(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    @staticmethod
    def check_product_availability(product_ids: List[int]) -> Dict:
        """
        Check if products are available for reservation.

        Args:
            product_ids: List of product IDs to check

        Returns:
            Dict with 'available' (list) and 'unavailable' (list of dicts)
        """
        try:
            products = Product.objects.filter(pk__in=product_ids)

            available = []
            unavailable = []

            for product_id in product_ids:
                try:
                    product = products.get(pk=product_id)

                    if product.status == ProductStatus.ACTIVE:
                        available.append(product_id)
                    else:
                        status_reasons = {
                            ProductStatus.RESERVED: 'reserved',
                            ProductStatus.SOLD: 'sold',
                            ProductStatus.INACTIVE: 'inactive',
                        }
                        unavailable.append({
                            'id': product_id,
                            'reason': status_reasons.get(
                                product.status,
                                'unavailable'
                            ),
                            'message': {
                                'reserved': 'Produkt jest zarezerwowany przez innego klienta',
                                'sold': 'Produkt został już sprzedany',
                                'inactive': 'Produkt jest niedostępny',
                            }.get(status_reasons.get(product.status, 'unavailable'),
                                  'Produkt jest niedostępny')
                        })
                except Product.DoesNotExist:
                    unavailable.append({
                        'id': product_id,
                        'reason': 'not_found',
                        'message': 'Produkt nie został znaleziony'
                    })

            return {
                'available': available,
                'unavailable': unavailable
            }

        except Exception as e:
            error_msg = f"Error checking product availability: {str(e)}"
            logger.exception(error_msg)
            return {
                'available': [],
                'unavailable': [
                    {'id': pid, 'reason': 'error', 'message': 'Błąd sprawdzania dostępności'}
                    for pid in product_ids
                ],
                'error': error_msg
            }
