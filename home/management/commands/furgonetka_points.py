"""
Management command to search Furgonetka points (paczkomats, etc.).

Usage:
    python manage.py furgonetka_points --service=inpost --postcode=00-001
    python manage.py furgonetka_points --service=inpost --city=Warszawa
    python manage.py furgonetka_points --service=inpost --limit=5
"""

from django.core.management.base import BaseCommand
from home.services import FurgonetkaService


class Command(BaseCommand):
    help = "Search Furgonetka delivery points (paczkomats, service points)"

    def add_arguments(self, parser):
        parser.add_argument("--service", default="inpost", help="Service: inpost, dpd, dhl, poczta")
        parser.add_argument("--postcode", help="Postcode to search near")
        parser.add_argument("--city", help="City to search in")
        parser.add_argument("--point-id", help="Specific point ID to look up")
        parser.add_argument("--limit", type=int, default=10, help="Max results")

    def handle(self, *args, **options):
        svc = FurgonetkaService()

        self.stdout.write(f"Searching {options['service']} points...")

        points = svc.search_points(
            service=options["service"],
            postcode=options.get("postcode"),
            city=options.get("city"),
            point_id=options.get("point_id"),
            limit=options["limit"],
        )

        self.stdout.write(f"Found {len(points)} points:\n")

        for p in points:
            code = p.get("code", "N/A")
            name = p.get("name", "N/A")
            addr = p.get("address", {})
            street = addr.get("street", "")
            city = addr.get("city", "")
            postcode = addr.get("postcode", "")

            self.stdout.write(f"  {code}: {name}")
            self.stdout.write(f"    {street}, {postcode} {city}")
            self.stdout.write(f"    Type: {p.get('type')}, Active: {p.get('active')}")
            self.stdout.write("")
