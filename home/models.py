import logging
from django.db import models
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django import forms
from django.utils.text import slugify
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, InlinePanel
from home.widgets import InPostSearchWidget
from wagtail.fields import RichTextField
from wagtail.models import Page, Orderable
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modelcluster.forms import ClusterForm

logger = logging.getLogger(__name__)


class ProductStatus(models.TextChoices):
    """Product status choices for Stripe integration"""
    ACTIVE = "active", "Active"        # visible in shop, buyable
    INACTIVE = "inactive", "Inactive"  # hidden by client (e.g. sold on-site)
    SOLD = "sold", "Sold"              # purchased online, moved to archive
    RESERVED = "reserved", "Reserved"  # reserved by a customer during checkout


class ProductAdminForm(ClusterForm):
    """Custom form for Product admin with proper multiselect handling"""

    dla_kogo = forms.MultipleChoiceField(
        choices=[],  # Will be set in __init__
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Dla kogo"
    )

    kolor_pior = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Kolor piór w przewadze"
    )

    gatunek_ptakow = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Pióra zgubiły (gatunek)"
    )

    rodzaj_zapiecia = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Rodzaj zapięcia"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set choices from model
        self.fields['dla_kogo'].choices = Product.DLA_KOGO_CHOICES
        self.fields['kolor_pior'].choices = Product.KOLOR_PIOR_CHOICES
        self.fields['gatunek_ptakow'].choices = Product.GATUNEK_PTAKOW_CHOICES
        self.fields['rodzaj_zapiecia'].choices = Product.RODZAJ_ZAPIECIA_CHOICES

        # Set initial values from instance
        if self.instance and self.instance.pk:
            if self.instance.dla_kogo:
                self.fields['dla_kogo'].initial = self.instance.dla_kogo
            if self.instance.kolor_pior:
                self.fields['kolor_pior'].initial = self.instance.kolor_pior
            if self.instance.gatunek_ptakow:
                self.fields['gatunek_ptakow'].initial = self.instance.gatunek_ptakow
            if self.instance.rodzaj_zapiecia:
                self.fields['rodzaj_zapiecia'].initial = self.instance.rodzaj_zapiecia

    def save(self, commit=True):
        # Let parent ClusterForm handle the save
        instance = super().save(commit=commit)

        # Update JSONField values after save
        instance.dla_kogo = self.cleaned_data.get('dla_kogo', [])
        instance.kolor_pior = self.cleaned_data.get('kolor_pior', [])
        instance.gatunek_ptakow = self.cleaned_data.get('gatunek_ptakow', [])
        instance.rodzaj_zapiecia = self.cleaned_data.get('rodzaj_zapiecia', [])

        # Save again to update the JSON fields
        if commit:
            instance.save(update_fields=['dla_kogo', 'kolor_pior', 'gatunek_ptakow', 'rodzaj_zapiecia'])

            # Clean up any empty images after save
            instance.images.filter(image__isnull=True).delete()

        return instance


class ProductImage(Orderable):
    """Product image with ordering support"""
    product = ParentalKey('Product', on_delete=models.CASCADE, related_name='images')
    image = models.ForeignKey(
        'wagtailimages.Image',
        on_delete=models.CASCADE,
        related_name='+',
        null=True,
        blank=True
    )

    panels = [
        FieldPanel('image'),
    ]

    def __str__(self):
        return f"{self.product.name} - Image {self.sort_order}"

    class Meta:
        verbose_name = "Zdjęcie produktu"
        verbose_name_plural = "Zdjęcia produktu"


class Product(ClusterableModel):
    # Choices for fields
    PRZEZNACZENIE_CHOICES = [
        ('kolczyki_para', 'Do ucha - kolczyki (para)'),
        ('kolczyki_asymetria', 'Do ucha - kolczyki (asymetria)'),
        ('kolczyki_single', 'Do ucha - kolczyki (single)'),
        ('kolczyki_komplet', 'Do ucha - kolczyki (komplet z wisiorkiem)'),
        ('zausznice', 'Zausznice'),
        ('na_szyje', 'Na szyję'),
        ('na_reke', 'Na rękę'),
        ('do_wlosow', 'Do włosów'),
        ('inne', 'Inne'),
    ]

    DLA_KOGO_CHOICES = [
        ('dla_niej', 'Dla niej'),
        ('dla_niego', 'Dla niego'),
        ('unisex', 'Unisex'),
    ]

    DLUGOSC_KATEGORIA_CHOICES = [
        ('krotkie', 'Krótkie (do 10cm)'),
        ('srednie', 'Średnie (10-15cm)'),
        ('dlugie', 'Długie (15-20cm)'),
        ('bardzo_dlugie', 'Bardzo długie (20cm+)'),
    ]

    KOLOR_PIOR_CHOICES = [
        ('bezowy', 'Beżowy'),
        ('bialy', 'Biały'),
        ('brazowy', 'Brązowy'),
        ('zielony', 'Zielony'),
        ('czerwony', 'Czerwony'),
        ('czarny', 'Czarny'),
        ('granatowy', 'Granatowy'),
        ('niebieski', 'Niebieski'),
        ('rozowy', 'Różowy'),
        ('szary', 'Szary'),
        ('turkusowy', 'Turkusowy'),
        ('wzor', 'Wzór'),
        ('zolty', 'Żółty'),
        ('wielokolorowe', 'Wielokolorowe'),
    ]

    GATUNEK_PTAKOW_CHOICES = [
        ('bazant', 'Bażant'),
        ('emu', 'Emu'),
        ('indyk', 'Indyk'),
        ('kura_kogut', 'Kura lub kogut'),
        ('papuga', 'Papuga'),
        ('paw', 'Paw'),
        ('perlica', 'Perlica'),
        ('inny', 'Inny'),
    ]

    KOLOR_METALOWYCH_CHOICES = [
        ('zloty', 'Złoty'),
        ('srebrny', 'Srebrny'),
        ('mieszany', 'Mieszany'),
        ('inny', 'Inny'),
    ]

    RODZAJ_ZAPIECIA_CHOICES = [
        ('bigiel_otwarty', 'Bigiel otwarty'),
        ('bigiel_zamkniety', 'Bigiel zamknięty'),
        ('sztyft', 'Sztyft'),
        ('kolko', 'Kółko'),
        ('klips', 'Klips'),
        ('zausznik', 'Zausznik'),
        ('inny', 'Inny'),
        ('nie_dotyczy', 'Nie dotyczy'),
    ]

    # Basic fields
    name = models.CharField(max_length=255, verbose_name="Nazwa (ang.)")
    tytul = models.CharField(max_length=255, blank=True, verbose_name="Nazwa (pl.)")

    slug = models.SlugField(unique=True, blank=True, max_length=255, help_text="Automatycznie generowane z nazwy")
    
    description = RichTextField(blank=True, verbose_name="Opis (ang.)", default=" ")
    opis = RichTextField(blank=True, verbose_name="Opis (pl.)", default=" ")

    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena podstawowa")
    cena = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Cena promocyjna")
    
    stripe_price_id = models.CharField(max_length=255, blank=True, help_text="Automatycznie generowane przez Stripe")
    stripe_product_id = models.CharField(max_length=255, blank=True, help_text="Automatycznie generowane przez Stripe")

    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.ACTIVE,
        db_index=True,
        verbose_name="Status"
    )
    sold_at = models.DateTimeField(null=True, blank=True, verbose_name="Data sprzedaży")

    # Legacy field - kept for backwards compatibility, mapped to status
    active = models.BooleanField(default=True, db_index=True, verbose_name="Czy dostepny w sklepie")

    featured = models.BooleanField(default=False, db_index=True, verbose_name="Wyróżnij na stronie głównej")

    # New fields
    nr_w_katalogu_zdjec = models.CharField(max_length=255, blank=True, default='', verbose_name="Nr w katalogu zdjęć")
    przeznaczenie_ogolne = models.CharField(max_length=255, choices=PRZEZNACZENIE_CHOICES, blank=True, default='', verbose_name="Przeznaczenie ogólne")
    dla_kogo = models.JSONField(default=list, blank=True, null=False, verbose_name="Dla kogo")
    dlugosc_kategoria = models.CharField(max_length=255, choices=DLUGOSC_KATEGORIA_CHOICES, blank=True, default='', verbose_name="Długość kategoria")
    dlugosc_w_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Długość w cm")
    kolor_pior = models.JSONField(default=list, blank=True, null=False, verbose_name="Kolor piór w przewadze")
    gatunek_ptakow = models.JSONField(default=list, blank=True, null=False, verbose_name="Pióra zgubiły (gatunek)")
    kolor_elementow_metalowych = models.CharField(max_length=255, choices=KOLOR_METALOWYCH_CHOICES, blank=True, default='', verbose_name="Kolor elementów metalowych")
    rodzaj_zapiecia = models.JSONField(default=list, blank=True, null=False, verbose_name="Rodzaj zapięcia")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    base_form_class = ProductAdminForm

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Flag to prevent Stripe sync from triggering signals in webhook handlers
        self._skip_stripe_sync = False
        # Track old status for signal handlers
        self._old_status = None

    panels = [
        MultiFieldPanel([
            FieldPanel('slug'),
            FieldPanel('status'),
            FieldPanel('sold_at', read_only=True),
            FieldPanel('active'),
            FieldPanel('featured'),
        ], heading="Basic Info"),
        MultiFieldPanel([
            FieldPanel('tytul'),
            FieldPanel('name'),
            FieldPanel('nr_w_katalogu_zdjec'),
            FieldPanel('opis'),
            FieldPanel('description'),
        ], heading="Opisy"),
        MultiFieldPanel([
            FieldPanel('price'),
            FieldPanel('cena'),
        ], heading="Ceny"),
        InlinePanel('images', label="Zdjęcia", help_text="Pierwsze zdjęcie będzie wyświetlane jako główne w sklepie"),
        MultiFieldPanel([
            FieldPanel('przeznaczenie_ogolne'),
            FieldPanel('dla_kogo'),
        ], heading="Przeznaczenie"),
        MultiFieldPanel([
            FieldPanel('dlugosc_w_cm'),
            FieldPanel('dlugosc_kategoria'),
        ], heading="Wymiary"),
        MultiFieldPanel([
            FieldPanel('kolor_pior'),
            FieldPanel('gatunek_ptakow'),
        ], heading="Pióra"),
        MultiFieldPanel([
            FieldPanel('kolor_elementow_metalowych'),
            FieldPanel('rodzaj_zapiecia'),
        ], heading="Elementy metalowe i zapięcia"),
        MultiFieldPanel([
            FieldPanel('stripe_product_id', read_only=True),
            FieldPanel('stripe_price_id', read_only=True),
            FieldPanel('sold_at', read_only=True),
        ], heading="Stripe Integration"),
    ]

    def clean(self):
        """Validate model fields before saving"""
        errors = {}

        # Validate required fields
        if not self.name or not self.name.strip():
            errors['name'] = 'Nazwa (ang.) jest wymagana'

        if not self.price or self.price <= 0:
            errors['price'] = 'Cena podstawowa musi być większa niż 0'

        # Validate JSONField fields are lists
        if self.dla_kogo is not None and not isinstance(self.dla_kogo, list):
            errors['dla_kogo'] = 'Nieprawidłowy format danych'

        if self.kolor_pior is not None and not isinstance(self.kolor_pior, list):
            errors['kolor_pior'] = 'Nieprawidłowy format danych'

        if self.gatunek_ptakow is not None and not isinstance(self.gatunek_ptakow, list):
            errors['gatunek_ptakow'] = 'Nieprawidłowy format danych'

        if self.rodzaj_zapiecia is not None and not isinstance(self.rodzaj_zapiecia, list):
            errors['rodzaj_zapiecia'] = 'Nieprawidłowy format danych'

        # Validate choice fields have valid values
        if self.przeznaczenie_ogolne and self.przeznaczenie_ogolne not in dict(self.PRZEZNACZENIE_CHOICES):
            errors['przeznaczenie_ogolne'] = 'Nieprawidłowa wartość'

        if self.dlugosc_kategoria and self.dlugosc_kategoria not in dict(self.DLUGOSC_KATEGORIA_CHOICES):
            errors['dlugosc_kategoria'] = 'Nieprawidłowa wartość'

        if self.kolor_elementow_metalowych and self.kolor_elementow_metalowych not in dict(self.KOLOR_METALOWYCH_CHOICES):
            errors['kolor_elementow_metalowych'] = 'Nieprawidłowa wartość'

        # Validate multiselect choices
        for choice in self.dla_kogo or []:
            if choice not in dict(self.DLA_KOGO_CHOICES):
                errors['dla_kogo'] = f'Nieprawidłowa wartość: {choice}'
                break

        for choice in self.kolor_pior or []:
            if choice not in dict(self.KOLOR_PIOR_CHOICES):
                errors['kolor_pior'] = f'Nieprawidłowa wartość: {choice}'
                break

        for choice in self.gatunek_ptakow or []:
            if choice not in dict(self.GATUNEK_PTAKOW_CHOICES):
                errors['gatunek_ptakow'] = f'Nieprawidłowa wartość: {choice}'
                break

        for choice in self.rodzaj_zapiecia or []:
            if choice not in dict(self.RODZAJ_ZAPIECIA_CHOICES):
                errors['rodzaj_zapiecia'] = f'Nieprawidłowa wartość: {choice}'
                break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Auto-generate slug from name
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            # Exclude current instance if updating
            queryset = Product.objects.filter(slug=slug)
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)

            while queryset.exists():
                slug = f"{base_slug}-{counter}"
                queryset = Product.objects.filter(slug=slug)
                if self.pk:
                    queryset = queryset.exclude(pk=self.pk)
                counter += 1
            self.slug = slug

        # Ensure JSONField fields are never NULL, always use empty list
        if self.dla_kogo is None:
            self.dla_kogo = []
        if self.kolor_pior is None:
            self.kolor_pior = []
        if self.gatunek_ptakow is None:
            self.gatunek_ptakow = []
        if self.rodzaj_zapiecia is None:
            self.rodzaj_zapiecia = []

        super().save(*args, **kwargs)

        # Invalidate product filters cache when product changes
        cache.delete('product_filters')

    def delete(self, *args, **kwargs):
        # Invalidate product filters cache when product is deleted
        cache.delete('product_filters')
        super().delete(*args, **kwargs)

    @property
    def primary_image(self):
        """Returns the first image (main product image)"""
        first_image = self.images.first()
        return first_image.image if first_image else None

    @property
    def is_buyable(self):
        """
        Returns True only if status is ACTIVE.
        This is the main check for whether a product can be purchased.
        """
        return self.status == ProductStatus.ACTIVE

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['active', '-created_at']),
            models.Index(fields=['featured', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

class EventImage(Orderable):
    """Event image with ordering support"""
    event = ParentalKey('Event', on_delete=models.CASCADE, related_name='images')
    image = models.ForeignKey(
        'wagtailimages.Image',
        on_delete=models.CASCADE,
        related_name='+'
    )

    panels = [
        FieldPanel('image'),
    ]

    def __str__(self):
        return f"{self.event.title} - Image {self.sort_order}"

    class Meta:
        verbose_name = "Zdjęcie eventu"
        verbose_name_plural = "Zdjęcia eventu"


class Event(ClusterableModel):
    """Event model for artist's local shop appearances"""
    title = models.CharField(max_length=255, verbose_name="Tytuł")
    description = models.TextField(blank=True, verbose_name="Opis")
    location = models.CharField(max_length=500, verbose_name="Lokalizacja")
    start_date = models.DateTimeField(verbose_name="Data rozpoczęcia")
    end_date = models.DateTimeField(verbose_name="Data zakończenia")
    external_url = models.URLField(blank=True, verbose_name="Link do zewnętrznej strony wydarzenia")

    active = models.BooleanField(default=True, db_index=True, verbose_name="Aktywny")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel('title'),
        FieldPanel('description'),
        FieldPanel('location'),
        FieldPanel('start_date'),
        FieldPanel('end_date'),
        FieldPanel('external_url'),
        FieldPanel('active'),
        InlinePanel('images', label="Zdjęcia", min_num=0),
    ]

    @property
    def primary_image(self):
        """Returns the first image (main event image)"""
        first_image = self.images.first()
        return first_image.image if first_image else None

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Event"
        verbose_name_plural = "Eventy"
        indexes = [
            models.Index(fields=['-start_date']),
            models.Index(fields=['active', '-start_date']),
        ]


class HomePage(Page):
    pass


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
        Product,
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


class PickupPoint(models.Model):
    """
    Pickup location for Furgonetka shipments.

    Defines where packages will be collected by the courier.
    Can be a home/business address or a parcel locker point.
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
        help_text="Kod paczkomatu/punktu np. 'ADA01N' dla InPost"
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Domyślny punkt odbioru"
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

    def save(self, *args, **kwargs):
        # Ensure only one default pickup point
        if self.is_default:
            PickupPoint.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls):
        """Get the default pickup point or None."""
        try:
            return cls.objects.filter(active=True, is_default=True).first()
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_first_active(cls):
        """Get first active pickup point or None."""
        return cls.objects.filter(active=True).first()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.street})"

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = "Punkt odbioru"
        verbose_name_plural = "Punkty odbioru"


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
