"""
Django management command to clean up expired reservations.

This command should be run periodically (e.g., every 5 minutes) via cron
or a background process to release products from reservations that have
expired but haven't been cancelled by Stripe webhooks.

Run: python manage.py cleanup_expired_reservations
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from home.models import Reservation


class Command(BaseCommand):
    help = 'Cancel expired reservations and release products back to active status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cancelled without actually cancelling',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()

        # Find pending/active reservations that have expired
        expired_reservations = Reservation.objects.filter(
            status__in=['pending', 'active'],
            expires_at__lt=now
        )

        count = expired_reservations.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No expired reservations found'))
            return

        if dry_run:
            self.stdout.write(f'Dry run: would cancel {count} expired reservation(s):')
            for reservation in expired_reservations:
                self.stdout.write(f'  - Session {reservation.stripe_session_id} expired at {reservation.expires_at}')
            return

        # Cancel each expired reservation using the service
        cancelled = 0
        for reservation in expired_reservations:
            from home.reservation import ReservationService
            result = ReservationService.cancel_reservation(reservation.stripe_session_id)
            if result['success']:
                cancelled += 1
                product_ids = result.get('product_ids', [])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Cancelled reservation {reservation.stripe_session_id}, '
                        f'released products: {product_ids}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'Failed to cancel reservation {reservation.stripe_session_id}: '
                        f'{result.get("error")}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Cleanup complete: cancelled {cancelled}/{count} expired reservation(s)'
            )
        )
