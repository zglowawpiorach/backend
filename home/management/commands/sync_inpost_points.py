"""
Django management command to sync InPost Paczkomat locations.

Fetches data from https://inpost.pl/sites/default/files/points-pl.json
and updates the InPostPoint model.

Usage:
    python manage.py sync_inpost_points
"""

import logging
import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from home.models import InPostPoint

logger = logging.getLogger(__name__)

INPOST_POINTS_URL = "https://inpost.pl/sites/default/files/points-pl.json"


class Command(BaseCommand):
    help = 'Sync InPost Paczkomat locations from inpost.pl'

    def add_arguments(self, parser):
        parser.add_argument(
            '--url',
            type=str,
            default=INPOST_POINTS_URL,
            help='Custom URL to fetch points from'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without making changes'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Batch size for database operations'
        )

    def handle(self, *args, **options):
        url = options['url']
        dry_run = options['dry_run']
        batch_size = options['batch_size']

        self.stdout.write(f"Fetching InPost points from: {url}")

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch data: {e}"))
            return
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Failed to parse JSON: {e}"))
            return

        # Data is a dict with 'items' key
        if isinstance(data, dict):
            items = data.get('items', [])
            total = data.get('total', len(items))
            self.stdout.write(f"Feed reports {total} total points, got {len(items)} items")
        elif isinstance(data, list):
            items = data
            self.stdout.write(f"Found {len(items)} points in feed")
        else:
            self.stdout.write(self.style.ERROR(f"Unexpected data format: {type(data)}"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))
            self._show_sample(items[:5])
            return

        # Process in transaction
        with transaction.atomic():
            # Get existing point names
            existing_names = set(InPostPoint.objects.values_list('name', flat=True))
            new_count = 0
            updated_count = 0

            points_to_create = []
            points_to_update = []

            for item in items:
                # Map JSON fields (short names) to model fields
                # n = name, c = city, e = street, b = building number
                # o = postcode, l = location {a: lat, o: lon}
                # h = hours, d = description, s = status (1 = active)
                name = item.get('n', '')
                if not name:
                    continue

                location = item.get('l', {})
                latitude = location.get('a', 0)
                longitude = location.get('o', 0)

                point_data = {
                    'street': item.get('e', ''),
                    'building_number': item.get('b', ''),
                    'postcode': item.get('o', ''),
                    'city': item.get('c', ''),
                    'latitude': float(latitude) if latitude else 0.0,
                    'longitude': float(longitude) if longitude else 0.0,
                    'location_description': item.get('d', ''),
                    'opening_hours': item.get('h', ''),
                    'active': item.get('s', 0) == 1,
                }

                if name in existing_names:
                    points_to_update.append((name, point_data))
                else:
                    points_to_create.append(InPostPoint(name=name, **point_data))

                # Batch create
                if len(points_to_create) >= batch_size:
                    InPostPoint.objects.bulk_create(points_to_create)
                    new_count += len(points_to_create)
                    points_to_create = []

                # Batch update
                if len(points_to_update) >= batch_size:
                    for n, pd in points_to_update:
                        InPostPoint.objects.filter(name=n).update(**pd)
                    updated_count += len(points_to_update)
                    points_to_update = []

            # Final batch
            if points_to_create:
                InPostPoint.objects.bulk_create(points_to_create)
                new_count += len(points_to_create)

            for n, pd in points_to_update:
                InPostPoint.objects.filter(name=n).update(**pd)
            updated_count += len(points_to_update)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sync complete: {new_count} new, {updated_count} updated"
            )
        )

    def _show_sample(self, items):
        """Show sample of data that would be imported."""
        self.stdout.write("\nSample data:")
        for item in items:
            name = item.get('n', '')
            city = item.get('c', '')
            street = item.get('e', '')
            building = item.get('b', '')
            self.stdout.write(f"  {name}: {city}, {street} {building}")
