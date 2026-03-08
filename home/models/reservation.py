"""Reservation models for checkout flow."""

from django.db import models


class ReservationStatus(models.TextChoices):
    """Reservation status choices"""
    PENDING = "pending", "Pending"         # Checkout created, waiting for payment
    COMPLETED = "completed", "Completed"   # Payment successful
    EXPIRED = "expired", "Expired"         # Timer expired
    CANCELLED = "cancelled", "Cancelled"   # User cancelled


class Reservation(models.Model):
    """
    Product reservation with expiration.

    When a customer creates a checkout session, products are reserved
    for a limited time to prevent race conditions. The reservation
    expires if payment is not completed within the timeout period.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),      # Checkout created, waiting for payment
        ('completed', 'Completed'),  # Payment successful
        ('expired', 'Expired'),      # Timer expired
        ('cancelled', 'Cancelled'),  # User cancelled
    ]

    stripe_session_id = models.CharField(max_length=255, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ReservationStatus.PENDING,
        db_index=True
    )
    reserved_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    customer_email = models.EmailField(blank=True, null=True)

    class Meta:
        verbose_name = "Rezerwacja"
        verbose_name_plural = "Rezerwacje"
        ordering = ['-reserved_at']
        indexes = [
            models.Index(fields=['expires_at']),
            models.Index(fields=['status']),
            models.Index(fields=['-reserved_at']),
        ]

    def __str__(self):
        return f"Reservation {self.id} - {self.status}"


class ReservedProduct(models.Model):
    """
    Through model connecting Reservations to Products.

    Tracks which products are included in each reservation.
    """
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='reserved_products'
    )
    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zarezerwowany produkt"
        verbose_name_plural = "Zarezerwowane produkty"
        unique_together = [['reservation', 'product']]
        ordering = ['reservation', 'added_at']

    def __str__(self):
        return f"{self.reservation.stripe_session_id} - {self.product.name}"
