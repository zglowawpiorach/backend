"""Brevo (Sendinblue) email configuration models."""

from django.db import models


class BrevoConfig(models.Model):
    """
    Brevo (Sendinblue) email configuration (singleton model).

    Stores API key and email template settings.
    Only one instance should exist - use get_solo() to retrieve.
    """
    api_key = models.CharField(
        max_length=255,
        verbose_name="API Key"
    )
    sender_email = models.EmailField(
        verbose_name="Email nadawcy"
    )
    sender_name = models.CharField(
        max_length=255,
        verbose_name="Nazwa nadawcy"
    )
    thank_you_template_id = models.IntegerField(
        verbose_name="ID szablonu 'Dziękujemy'",
        help_text="ID szablonu email po zakupie"
    )
    shipping_template_id = models.IntegerField(
        verbose_name="ID szablonu 'Wysyłka'",
        help_text="ID szablonu email przy wysyłce"
    )
    newsletter_list_id = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="ID listy newsletter",
        help_text="ID listy kontaktów w Brevo dla subskrybentów newslettera"
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
        return "Konfiguracja Brevo"

    class Meta:
        verbose_name = "Konfiguracja Brevo"
        verbose_name_plural = "Konfiguracja Brevo"
