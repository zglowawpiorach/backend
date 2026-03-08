"""Coupon models for promotional discounts."""

from django.db import models
from django.core.exceptions import ValidationError
from wagtail.admin.panels import FieldPanel, MultiFieldPanel


class CouponStatus(models.TextChoices):
    """Coupon status choices"""
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class Coupon(models.Model):
    """
    Promotional coupon that syncs with Stripe.

    Creates both a Stripe Coupon (discount rules) and PromotionCode
    (customer-facing code like "SUMMER20").
    """
    DISCOUNT_TYPE_CHOICES = [
        ('percent', 'Percentage'),
        ('fixed', 'Fixed amount'),
    ]

    # Customer-facing code
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="Kod promocyjny",
        help_text="Kod który wpisuje klient, np. SUMMER20"
    )

    # Discount type and value
    discount_type = models.CharField(
        max_length=10,
        choices=DISCOUNT_TYPE_CHOICES,
        verbose_name="Typ zniżki"
    )
    percent_off = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Zniżka procentowa",
        help_text="Np. 20 dla 20% zniżki"
    )
    amount_off = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Zniżka kwotowa (PLN)",
        help_text="Np. 20 dla 20 PLN zniżki"
    )

    # Optional limits
    max_redemptions = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Maksymalna liczba użyć",
        help_text="Puste = bez limitu"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Data wygaśnięcia"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=CouponStatus.choices,
        default=CouponStatus.ACTIVE,
        db_index=True,
        verbose_name="Status"
    )
    times_redeemed = models.PositiveIntegerField(
        default=0,
        verbose_name="Liczba użyć",
        help_text="Synchronizowane ze Stripe"
    )

    # Stripe IDs
    stripe_coupon_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Stripe Coupon ID"
    )
    stripe_promotion_code_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Stripe Promotion Code ID"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Flag to prevent sync loops
    _skip_stripe_sync = False
    _old_status = None

    panels = [
        MultiFieldPanel([
            FieldPanel('code'),
            FieldPanel('status'),
            FieldPanel('times_redeemed', read_only=True),
        ], heading="Podstawowe informacje"),
        MultiFieldPanel([
            FieldPanel('discount_type'),
            FieldPanel('percent_off'),
            FieldPanel('amount_off'),
        ], heading="Zniżka"),
        MultiFieldPanel([
            FieldPanel('max_redemptions'),
            FieldPanel('expires_at'),
        ], heading="Limity (opcjonalne)"),
        MultiFieldPanel([
            FieldPanel('stripe_coupon_id', read_only=True),
            FieldPanel('stripe_promotion_code_id', read_only=True),
        ], heading="Integracja Stripe"),
    ]

    def clean(self):
        """Validate that exactly one discount value is set."""
        errors = {}

        if not self.code or not self.code.strip():
            errors['code'] = 'Kod jest wymagany'

        # Normalize code to uppercase
        if self.code:
            self.code = self.code.upper().strip()

        # Validate discount
        if self.discount_type == 'percent':
            if not self.percent_off or self.percent_off <= 0 or self.percent_off > 100:
                errors['percent_off'] = 'Procent musi być między 1 a 100'
            if self.amount_off:
                errors['amount_off'] = 'Dla zniżki procentowej nie podawaj kwoty'
        elif self.discount_type == 'fixed':
            if not self.amount_off or self.amount_off <= 0:
                errors['amount_off'] = 'Kwota musi być większa od 0'
            if self.percent_off:
                errors['percent_off'] = 'Dla zniżki kwotowej nie podawaj procentu'
        else:
            errors['discount_type'] = 'Wybierz typ zniżki'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Normalize code to uppercase
        if self.code:
            self.code = self.code.upper().strip()
        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        """Check if coupon can be used right now."""
        from django.utils import timezone

        if self.status != CouponStatus.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_redemptions and self.times_redeemed >= self.max_redemptions:
            return False
        return True

    def discount_display(self) -> str:
        """Return formatted discount string for admin display."""
        if self.discount_type == 'percent':
            return f"{self.percent_off}%"
        return f"{self.amount_off:.2f} PLN"
    discount_display.short_description = 'Zniżka'

    def is_valid_display(self) -> str:
        """Return 'Tak' or 'Nie' for admin display."""
        return "Tak" if self.is_valid else "Nie"
    is_valid_display.short_description = 'Ważny'

    def __str__(self):
        return self.code

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Kupon promocyjny"
        verbose_name_plural = "Kupony promocyjne"
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status']),
        ]
