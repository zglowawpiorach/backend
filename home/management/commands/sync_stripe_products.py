"""
Django management command to sync all active products to Stripe.

Usage:
    python manage.py sync_stripe_products
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from home.models import Product, ProductStatus
from home.stripe_sync import StripeSync


class Command(BaseCommand):
    help = 'Sync all active products to Stripe'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            dest='force',
            help='Force sync all products (not just active ones)',
        )

    def handle(self, *args, **options):
        """Execute the sync command."""
        # Check if Stripe is configured
        if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
            self.stdout.write(self.style.ERROR('STRIPE_SECRET_KEY is not configured'))
            return

        force = options.get('force', False)

        if force:
            products = Product.objects.all()
            self.stdout.write(f"Syncing ALL products to Stripe...")
        else:
            products = Product.objects.filter(status=ProductStatus.ACTIVE)
            self.stdout.write(f"Syncing active products to Stripe...")

        success_count = 0
        error_count = 0

        for product in products:
            product_name = product.tytul if product.tytul else product.name
            self.stdout.write(f"  Processing: {product_name} (#{product.pk})... ", ending='')

            result = StripeSync.create_or_update_product(product)

            if result['success']:
                self.stdout.write(self.style.SUCCESS('OK'))
                success_count += 1
            else:
                self.stdout.write(self.style.ERROR(f"FAILED: {result.get('error')}"))
                error_count += 1

        # Summary
        total = success_count + error_count
        self.stdout.write(f"\nSynced {success_count}/{total} products successfully")

        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"{error_count} products failed to sync"))
