"""
Django management command to create random products for testing.

Usage:
    python manage.py create_random_products [--count N]

Default creates 20 products.
"""

import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from home.models import Product


class Command(BaseCommand):
    help = 'Create random products for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of products to create (default: 20)',
        )

    def handle(self, *args, **options):
        count = options['count']

        # Product name templates (Polish jewelry names)
        name_templates = [
            "Kolczyki {color} {bird}",
            "Naszyjnik {color} {bird}",
            "Bransoletka {color} {bird}",
            "Wisiorek {color} {bird}",
            "Zausznica {color} {bird}",
            "Kolczyki asymetryczne {color} {bird}",
            "Komplet {color} {bird}",
            "Spinka do włosów {color} {bird}",
        ]

        colors_pl = {
            'bezowy': 'beżowe',
            'bialy': 'białe',
            'brazowy': 'brązowe',
            'zielony': 'zielone',
            'czerwony': 'czerwone',
            'czarny': 'czarne',
            'granatowy': 'granatowe',
            'niebieski': 'niebieskie',
            'rozowy': 'różowe',
            'szary': 'szare',
            'turkusowy': 'turkusowe',
            'zolty': 'żółte',
            'wielokolorowe': 'wielokolorowe',
        }

        birds_pl = {
            'bazant': 'z bażanta',
            'emu': 'z emu',
            'indyk': 'z indyka',
            'kura_kogut': 'z kury',
            'papuga': 'z papugi',
            'paw': 'z pawia',
            'perlica': 'z perlicy',
        }

        created_count = 0

        for i in range(count):
            # Random selections
            color_key = random.choice(list(colors_pl.keys()))
            bird_key = random.choice(list(birds_pl.keys()))
            template = random.choice(name_templates)

            # Generate Polish name
            tytul = template.format(color=colors_pl[color_key], bird=birds_pl[bird_key])

            # Generate English name (simpler)
            name = f"Feather Jewelry {i+1} - {color_key.title()} {bird_key.title()}"

            # Random price between 50 and 500 PLN
            price = Decimal(random.randint(50, 500))

            # 30% chance of promotional price
            cena = None
            if random.random() < 0.3:
                cena = price * Decimal('0.8')  # 20% off
                cena = cena.quantize(Decimal('0.01'))

            # Random przeznaczenie
            przeznaczenie = random.choice([c[0] for c in Product.PRZEZNACZENIE_CHOICES])

            # Random dla_kogo (1-2 choices)
            dla_kogo = random.sample(
                [c[0] for c in Product.DLA_KOGO_CHOICES],
                k=random.randint(1, 2)
            )

            # Random length
            dlugosc_kategoria = random.choice([c[0] for c in Product.DLUGOSC_KATEGORIA_CHOICES] + [''])
            dlugosc_w_cm = None
            if dlugosc_kategoria:
                lengths = {'krotkie': (5, 10), 'srednie': (10, 15), 'dlugie': (15, 20), 'bardzo_dlugie': (20, 25)}
                min_len, max_len = lengths.get(dlugosc_kategoria, (5, 15))
                dlugosc_w_cm = Decimal(random.uniform(min_len, max_len)).quantize(Decimal('0.01'))

            # Random colors (1-3)
            kolor_pior = random.sample(
                [c[0] for c in Product.KOLOR_PIOR_CHOICES],
                k=random.randint(1, 3)
            )

            # Random bird species (1-2)
            gatunek_ptakow = random.sample(
                [c[0] for c in Product.GATUNEK_PTAKOW_CHOICES],
                k=random.randint(1, 2)
            )

            # Random metal color
            kolor_metalu = random.choice([c[0] for c in Product.KOLOR_METALOWYCH_CHOICES] + [''])

            # Random zapiecia (1-2)
            rodzaj_zapiecia = random.sample(
                [c[0] for c in Product.RODZAJ_ZAPIECIA_CHOICES],
                k=random.randint(1, 2)
            )

            # Create product
            product = Product(
                name=name,
                tytul=tytul,
                price=price,
                cena=cena,
                active=True,
                featured=random.random() < 0.2,  # 20% featured
                przeznaczenie_ogolne=przeznaczenie,
                dla_kogo=dla_kogo,
                dlugosc_kategoria=dlugosc_kategoria,
                dlugosc_w_cm=dlugosc_w_cm,
                kolor_pior=kolor_pior,
                gatunek_ptakow=gatunek_ptakow,
                kolor_elementow_metalowych=kolor_metalu,
                rodzaj_zapiecia=rodzaj_zapiecia,
            )

            # Skip Stripe sync for test products
            product._skip_stripe_sync = True

            try:
                product.save()
                created_count += 1
                self.stdout.write(f"Created: {tytul} ({price} PLN)")
            except Exception as e:
                self.stderr.write(f"Error creating product: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully created {created_count} products")
        )
