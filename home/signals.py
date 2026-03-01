"""
Django signals for automatic Stripe synchronization.

Handles pre_save and post_save signals on Product model to keep
Stripe products in sync with Wagtail products.
"""

import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Product, ProductStatus
from .stripe_sync import StripeSync

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Product)
def track_product_status_change(sender, instance, **kwargs):
    """
    Track the old status of a product before save.

    This allows us to detect status changes in post_save.
    """
    if instance.pk:
        try:
            old_instance = Product.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Product.DoesNotExist:
            # New product, no old status
            instance._old_status = None


@receiver(post_save, sender=Product)
def sync_product_to_stripe(sender, instance, created, **kwargs):
    """
    Sync product to Stripe after save.

    - Skips if _skip_stripe_sync is True (prevents webhook -> signal loop)
    - If status changed to "inactive": deactivate Stripe product
    - If status is "active": create or update Stripe product
    - Logs errors but never crashes the save
    """
    # Skip if explicitly requested (e.g., from webhook handler)
    if hasattr(instance, '_skip_stripe_sync') and instance._skip_stripe_sync:
        logger.debug(f"Skipping Stripe sync for product {instance.pk}")
        return

    # Skip if Stripe is not configured
    from django.conf import settings
    if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
        logger.debug("Stripe not configured, skipping sync")
        return

    try:
        current_status = instance.status
        old_status = instance._old_status

        # If status changed to inactive
        if current_status == ProductStatus.INACTIVE and old_status != ProductStatus.INACTIVE:
            logger.info(f"Product {instance.pk} deactivated, syncing to Stripe")
            result = StripeSync.deactivate_product(instance)
            if not result['success']:
                logger.error(f"Failed to deactivate Stripe product: {result.get('error')}")
            return

        # If status is active (new product or reactivated)
        if current_status == ProductStatus.ACTIVE:
            if created or old_status != ProductStatus.ACTIVE:
                logger.info(f"Product {instance.pk} activated/created, syncing to Stripe")
            else:
                logger.debug(f"Product {instance.pk} updated, syncing to Stripe")

            result = StripeSync.create_or_update_product(instance)
            if not result['success']:
                logger.error(f"Failed to sync Stripe product: {result.get('error')}")

    except Exception as e:
        # Never crash the save operation due to Stripe sync issues
        logger.exception(f"Unexpected error in Stripe sync signal for product {instance.pk}: {str(e)}")
