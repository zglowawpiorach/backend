"""Furgonetka integration configuration models."""

from django.db import models


class FurgonetkaConfig(models.Model):
    """
    Furgonetka API configuration (singleton model).

    Stores API credentials and sender details for package creation.
    Only one instance should exist - use get_solo() to retrieve.
    """
    # API Configuration
    sandbox = models.BooleanField(
        default=True,
        verbose_name="Tryb sandbox",
        help_text="Używaj środowiska testowego"
    )
    client_id = models.CharField(
        max_length=255,
        verbose_name="Client ID"
    )
    client_secret = models.CharField(
        max_length=255,
        verbose_name="Client Secret"
    )
    username = models.CharField(
        max_length=255,
        verbose_name="Email / Username"
    )
    password = models.CharField(
        max_length=255,
        verbose_name="Hasło"
    )

    # Sender details (nadawca)
    sender_name = models.CharField(
        max_length=255,
        verbose_name="Nazwa nadawcy"
    )
    sender_email = models.EmailField(
        verbose_name="Email nadawcy"
    )
    sender_phone = models.CharField(
        max_length=20,
        verbose_name="Telefon nadawcy"
    )
    sender_street = models.CharField(
        max_length=255,
        verbose_name="Ulica nadawcy"
    )
    sender_city = models.CharField(
        max_length=100,
        verbose_name="Miasto nadawcy"
    )
    sender_postcode = models.CharField(
        max_length=10,
        verbose_name="Kod pocztowy nadawcy"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        """Get or create the singleton instance."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent deletion of singleton
        pass

    def __str__(self):
        return "Konfiguracja Furgonetka"

    class Meta:
        verbose_name = "Konfiguracja Furgonetka"
        verbose_name_plural = "Konfiguracja Furgonetka"


class FurgonetkaService(models.Model):
    """
    Furgonetka service ID mapping.

    Maps service names (e.g., 'inpost', 'dpd') to Furgonetka service IDs.
    """
    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nazwa usługi",
        help_text="Np. 'inpost', 'dpd', 'poczta'"
    )
    service_id = models.CharField(
        max_length=20,
        verbose_name="Service ID",
        help_text="ID usługi z Furgonetka (np. '11361412')"
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Opis"
    )
    active = models.BooleanField(
        default=True,
        verbose_name="Aktywna"
    )

    def __str__(self):
        return f"{self.name} ({self.service_id})"

    class Meta:
        ordering = ['name']
        verbose_name = "Usługa Furgonetka"
        verbose_name_plural = "Usługi Furgonetka"
