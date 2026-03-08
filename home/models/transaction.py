"""Transaction model for tracking orders."""

from django.db import models
from django.core.exceptions import ValidationError


class TransactionStatus(models.TextChoices):
    """Transaction status choices"""
    SOLD = "sold", "Sprzedane"
    SENT = "sent", "Wysłane"


class Transaction(models.Model):
    """
    Transaction record for completed orders.

    Stores minimal data: products sold and customer email.
    Status can be changed from 'sold' to 'sent' which triggers email.
    """
    # Stripe reference
    stripe_session_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name="Stripe Session ID"
    )

    # Customer info (minimal - no sensitive data)
    customer_email = models.EmailField(
        verbose_name="Email klienta"
    )
    customer_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Imię klienta"
    )

    # Products sold
    products = models.ManyToManyField(
        'Product',
        related_name='transactions',
        verbose_name="Produkty"
    )

    # Shipping details
    shipping_method = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Metoda dostawy",
        help_text="Np. 'InPost Paczkomat', 'Kurier DPD'"
    )
    shipping_address = models.TextField(
        blank=True,
        verbose_name="Adres dostawy",
        help_text="Adres lub punkt odbioru"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.SOLD,
        db_index=True,
        verbose_name="Status"
    )

    # Tracking (filled when sent)
    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Numer śledzenia",
        help_text="Wypełnij przy zmianie statusu na 'Wysłane'"
    )

    # Carrier info
    carrier = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Przewoźnik",
        help_text="Np. 'inpost', 'dpd'"
    )

    # Total amount (for display)
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Kwota (PLN)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Transakcja"
        verbose_name_plural = "Transakcje"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['customer_email']),
        ]

    def __str__(self):
        return f"#{self.id} - {self.customer_email} ({self.get_status_display()})"

    @property
    def is_sent(self) -> bool:
        return self.status == TransactionStatus.SENT

    def get_products_display(self) -> str:
        """Return comma-separated product names."""
        return ", ".join(
            p.name or p.tytul or f"#{p.id}"
            for p in self.products.all()
        )
    get_products_display.short_description = "Produkty"

    def mark_sent_action(self) -> str:
        """Return HTML for mark as sent button or status indicator."""
        from django.urls import reverse
        from django.utils.html import format_html

        if self.status == TransactionStatus.SOLD:
            url = reverse(f'admin_snippets_home_{self._meta.model_name}_mark_sent', args=[self.pk])
            return format_html(
                '<a href="{}" class="button button-small button-primary" '
                'onclick="return confirm(\'Czy na pewno oznaczyć jako wysłane i wysłać email do klienta?\')">'
                'Oznacz jako wysłane'
                '</a>',
                url
            )
        elif self.status == TransactionStatus.SENT:
            return format_html('<span class="status-tag status-tag-success">Wysłano</span>')
        return ""
    mark_sent_action.short_description = "Akcja"
