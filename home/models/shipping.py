"""Shipping and pickup point models."""

from django.db import models, transaction
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from home.widgets import InPostSearchWidget


class PickupPoint(models.Model):
    """
    Pickup location for Furgonetka shipments.

    Defines where packages will be dropped off by the sender.
    The 'point' field must contain a valid paczkomat code (e.g. 'ADA01N')
    so that Furgonetka creates a sender-dropoff shipment instead of
    dispatching a courier to pick up from the address.
    """
    name = models.CharField(
        max_length=100,
        verbose_name="Nazwa",
        help_text="Np. 'Dom', 'Biuro', 'Paczkomat przy sklepie'"
    )
    street = models.CharField(
        max_length=255,
        verbose_name="Ulica i numer",
        help_text="Np. 'Mickiewicza 15'"
    )
    postcode = models.CharField(
        max_length=10,
        verbose_name="Kod pocztowy",
        help_text="Np. '00-001'"
    )
    city = models.CharField(
        max_length=100,
        verbose_name="Miasto"
    )
    point = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Kod punktu (opcjonalnie)",
        help_text=(
            "Kod paczkomatu/punktu np. 'ADA01N' dla InPost. "
            "Wymagany — bez kodu Furgonetka tworzy przesyłkę z odbiorem kuriera pod adres."
        )
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Domyślny punkt nadania"
    )
    active = models.BooleanField(
        default=True,
        verbose_name="Aktywny"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        MultiFieldPanel([
            FieldPanel('name'),
            FieldPanel('active'),
            FieldPanel('is_default'),
        ], heading="Podstawowe"),
        MultiFieldPanel([
            FieldPanel('point', widget=InPostSearchWidget()),
            FieldPanel('street'),
            FieldPanel('postcode'),
            FieldPanel('city'),
        ], heading="Adres"),
    ]

    @transaction.atomic
    def save(self, *args, **kwargs):
        # Ensure only one default pickup point
        if self.is_default:
            PickupPoint.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls):
        """Get the default pickup point or None."""
        return cls.objects.filter(active=True, is_default=True).first()

    @classmethod
    def get_first_active(cls):
        """Get first active pickup point or None."""
        return cls.objects.filter(active=True).first()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.street})"

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = "Punkt nadania"
        verbose_name_plural = "Punkty nadania"


class InPostPoint(models.Model):
    """
    InPost Paczkomat location synced from inpost.pl/points-pl.json

    Used for customer delivery address selection.
    """
    # Core identification
    name = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Kod paczkomatu",
        help_text="Np. 'ADA01N'"
    )

    # Location details
    street = models.CharField(
        max_length=255,
        verbose_name="Ulica"
    )
    building_number = models.CharField(
        max_length=20,
        verbose_name="Numer budynku"
    )
    postcode = models.CharField(
        max_length=10,
        verbose_name="Kod pocztowy"
    )
    city = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Miasto"
    )

    # Geographic coordinates
    latitude = models.FloatField(verbose_name="Szerokość geograficzna")
    longitude = models.FloatField(verbose_name="Długość geograficzna")

    # Additional info
    location_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Opis lokalizacji"
    )
    opening_hours = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Godziny otwarcia"
    )

    # Status
    active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Aktywny"
    )

    # Metadata
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.city}, {self.street}"

    @property
    def full_address(self) -> str:
        """Return formatted address string."""
        return f"{self.street} {self.building_number}, {self.postcode} {self.city}"

    class Meta:
        ordering = ['city', 'name']
        verbose_name = "Paczkomat InPost"
        verbose_name_plural = "Paczkomaty InPost"
        indexes = [
            models.Index(fields=['city']),
            models.Index(fields=['active']),
            models.Index(fields=['name']),
        ]
