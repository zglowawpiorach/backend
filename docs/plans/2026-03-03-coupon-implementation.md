# Coupon Model Implementation Plan

> **For the implementing engineer:** Follow each step exactly. Run commands in order. Commit after each task.

## Overview

Add a Coupon model for promotional codes that sync with Stripe automatically.

**Reference:** See `docs/plans/2026-03-03-coupon-design.md` for full design.

## Files Modified

| File | Purpose |
|------|---------|
| `home/models.py` | Add Coupon model |
| `home/stripe_sync.py` | Add coupon sync methods |
| `home/signals.py` | Add coupon signal handlers |
| `home/wagtail_hooks.py` | Register Coupon snippet |
| `home/api/views.py` | Add validate-coupon endpoint |
| `home/api/urls.py` | Add coupon API route |
| `home/api/webhooks.py` | Add coupon webhook handlers |

---

## Task 1: Add Coupon Model

### Step 1.1: Add CouponStatus and Coupon to models.py

Add to `home/models.py` after the `Reservation` model (around line 557):

```python
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
    amount_off = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Zniżka kwotowa (w groszach)",
        help_text="Np. 2000 dla 20 PLN zniżki"
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
```

### Step 1.2: Run migrations

```bash
cd /Users/seba/piorka && poetry run python manage.py makemigrations home
poetry run python manage.py migrate
```

Expected: Migration created and applied successfully.

### Step 1.3: Commit

```bash
git add home/models.py home/migrations/
git commit -m "$(cat <<'EOF'
feat: add Coupon model for promotional codes

- Support percentage and fixed amount discounts
- Optional limits: max_redemptions, expires_at
- Stripe sync via stripe_coupon_id, stripe_promotion_code_id
- is_valid property for checkout validation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Stripe Sync Methods for Coupons

### Step 2.1: Add coupon sync methods to stripe_sync.py

Add these methods to the `StripeSync` class in `home/stripe_sync.py`, after the `cancel_checkout_session` method (around line 535):

```python
    @staticmethod
    def create_or_update_coupon(coupon) -> dict:
        """
        Create or update a Stripe Coupon and PromotionCode for the given Coupon.

        If stripe_coupon_id is empty, creates new Stripe Coupon and PromotionCode.
        If stripe_coupon_id exists, updates the Stripe Coupon.

        Args:
            coupon: Coupon instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            is_new = not bool(coupon.stripe_coupon_id)

            # Build coupon params
            coupon_params = {
                'metadata': {
                    'wagtail_id': str(coupon.pk),
                    'code': coupon.code,
                },
            }

            # Set discount
            if coupon.discount_type == 'percent':
                coupon_params['percent_off'] = coupon.percent_off
            else:
                coupon_params['amount_off'] = coupon.amount_off
                coupon_params['currency'] = SHIPPING_CURRENCY

            # Set optional limits
            if coupon.max_redemptions:
                coupon_params['max_redemptions'] = coupon.max_redemptions

            if coupon.expires_at:
                coupon_params['redeem_by'] = int(coupon.expires_at.timestamp())

            if is_new:
                # Create Stripe Coupon
                stripe_coupon = stripe.Coupon.create(**coupon_params)
                coupon.stripe_coupon_id = stripe_coupon.id
                logger.info(f"Created Stripe coupon {stripe_coupon.id} for Coupon {coupon.pk}")

                # Create PromotionCode with the customer-facing code
                promo_params = {
                    'coupon': stripe_coupon.id,
                    'code': coupon.code,
                    'active': coupon.status == 'active',
                    'metadata': {
                        'wagtail_id': str(coupon.pk),
                    },
                }
                stripe_promo = stripe.PromotionCode.create(**promo_params)
                coupon.stripe_promotion_code_id = stripe_promo.id
                logger.info(f"Created Stripe promotion code {stripe_promo.id} for Coupon {coupon.pk}")

            else:
                # Update existing Stripe Coupon
                # Note: Stripe Coupons have limited updatable fields
                stripe.Coupon.modify(
                    coupon.stripe_coupon_id,
                    metadata=coupon_params['metadata'],
                )
                logger.info(f"Updated Stripe coupon {coupon.stripe_coupon_id}")

                # Update PromotionCode active status
                if coupon.stripe_promotion_code_id:
                    stripe.PromotionCode.modify(
                        coupon.stripe_promotion_code_id,
                        active=coupon.status == 'active',
                    )

            # Save the updated IDs
            coupon._skip_stripe_sync = True
            coupon.save(update_fields=['stripe_coupon_id', 'stripe_promotion_code_id'])

            return {'success': True}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def deactivate_coupon(coupon) -> dict:
        """
        Deactivate a coupon by setting its PromotionCode to inactive.

        Args:
            coupon: Coupon instance

        Returns:
            Dict with 'success' (bool) and optional 'error' message
        """
        if not coupon.stripe_promotion_code_id:
            logger.warning(f"Cannot deactivate Coupon {coupon.pk}: no stripe_promotion_code_id")
            return {'success': False, 'error': 'No stripe_promotion_code_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            stripe.PromotionCode.modify(
                coupon.stripe_promotion_code_id,
                active=False,
            )

            logger.info(f"Deactivated Stripe promotion code {coupon.stripe_promotion_code_id}")
            return {'success': True}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe coupon deactivation error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe coupon deactivation error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}

    @staticmethod
    def sync_coupon_redemptions(coupon) -> dict:
        """
        Sync times_redeemed from Stripe Coupon.

        Args:
            coupon: Coupon instance

        Returns:
            Dict with 'success' (bool), 'times_redeemed', and optional 'error'
        """
        if not coupon.stripe_coupon_id:
            return {'success': False, 'error': 'No stripe_coupon_id'}

        try:
            api_key = StripeSync._get_stripe_api_key()
            stripe.api_key = api_key

            stripe_coupon = stripe.Coupon.retrieve(coupon.stripe_coupon_id)
            times_redeemed = stripe_coupon.times_redeemed or 0

            # Update local model
            coupon._skip_stripe_sync = True
            coupon.times_redeemed = times_redeemed
            coupon.save(update_fields=['times_redeemed'])

            logger.info(f"Synced times_redeemed={times_redeemed} for Coupon {coupon.pk}")
            return {'success': True, 'times_redeemed': times_redeemed}

        except stripe.error.StripeError as e:
            error_msg = f"Stripe API error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Stripe coupon sync error for Coupon {coupon.pk}: {error_msg}")
            return {'success': False, 'error': error_msg}
```

### Step 2.2: Commit

```bash
git add home/stripe_sync.py
git commit -m "$(cat <<'EOF'
feat: add Stripe sync methods for Coupon model

- create_or_update_coupon: creates Coupon + PromotionCode
- deactivate_coupon: sets PromotionCode.active=False
- sync_coupon_redemptions: syncs times_redeemed from Stripe

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Signal Handlers for Coupon Sync

### Step 3.1: Add coupon signals to signals.py

Add to `home/signals.py` after the existing product signals:

```python
@receiver(pre_save, sender=Coupon)
def track_coupon_status_change(sender, instance, **kwargs):
    """
    Track the old status of a coupon before save.
    """
    if instance.pk:
        try:
            old_instance = Coupon.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Coupon.DoesNotExist:
            instance._old_status = None


@receiver(post_save, sender=Coupon)
def sync_coupon_to_stripe(sender, instance, created, **kwargs):
    """
    Sync coupon to Stripe after save.

    - Skips if _skip_stripe_sync is True
    - If status changed to inactive: deactivate in Stripe
    - If status is active: create or update in Stripe
    """
    from .models import Coupon, CouponStatus

    # Skip if explicitly requested
    if hasattr(instance, '_skip_stripe_sync') and instance._skip_stripe_sync:
        logger.debug(f"Skipping Stripe sync for coupon {instance.pk}")
        return

    # Skip if Stripe is not configured
    from django.conf import settings
    if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
        logger.debug("Stripe not configured, skipping coupon sync")
        return

    try:
        current_status = instance.status
        old_status = instance._old_status

        # If status changed to inactive
        if current_status == CouponStatus.INACTIVE and old_status != CouponStatus.INACTIVE:
            logger.info(f"Coupon {instance.pk} deactivated, syncing to Stripe")
            result = StripeSync.deactivate_coupon(instance)
            if not result['success']:
                logger.error(f"Failed to deactivate Stripe coupon: {result.get('error')}")
            return

        # If status is active
        if current_status == CouponStatus.ACTIVE:
            if created or old_status != CouponStatus.ACTIVE:
                logger.info(f"Coupon {instance.pk} activated/created, syncing to Stripe")
            else:
                logger.debug(f"Coupon {instance.pk} updated, syncing to Stripe")

            result = StripeSync.create_or_update_coupon(instance)
            if not result['success']:
                logger.error(f"Failed to sync Stripe coupon: {result.get('error')}")

    except Exception as e:
        logger.exception(f"Unexpected error in Stripe sync signal for coupon {instance.pk}: {str(e)}")
```

### Step 3.2: Update imports in signals.py

Update the imports at the top of `home/signals.py`:

```python
from .models import Product, ProductStatus, Coupon, CouponStatus
```

### Step 3.3: Commit

```bash
git add home/signals.py
git commit -m "$(cat <<'EOF'
feat: add signal handlers for automatic Coupon sync

- track_coupon_status_change: tracks old status before save
- sync_coupon_to_stripe: creates/updates/deactivates in Stripe

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Register Coupon as Wagtail Snippet

### Step 4.1: Register Coupon in wagtail_hooks.py

Add to `home/wagtail_hooks.py` after the existing registrations:

```python
from .models import Product, Event, Coupon

# ... existing registrations ...

@hooks.register('register_snippet')
class CouponViewSet(SnippetViewSet):
    model = Coupon
    icon = 'tag'
    menu_label = 'Kupony'
    menu_name = 'coupons'
    list_display = ['code', 'status', 'discount_display', 'times_redeemed', 'expires_at', 'is_valid_display']
    list_filter = ['status', 'discount_type']
    search_fields = ['code']

    def discount_display(self, obj):
        if obj.discount_type == 'percent':
            return f"{obj.percent_off}%"
        return f"{obj.amount_off / 100:.2f} PLN"
    discount_display.short_description = 'Zniżka'

    def is_valid_display(self, obj):
        return "Tak" if obj.is_valid else "Nie"
    is_valid_display.short_description = 'Ważny'
```

### Step 4.2: Check existing imports in wagtail_hooks.py

Read the file first to see what's already imported:

```bash
head -30 home/wagtail_hooks.py
```

Make sure `SnippetViewSet` is imported from `wagtail.admin.ui.tables` or the appropriate location based on Wagtail version.

### Step 4.3: Commit

```bash
git add home/wagtail_hooks.py
git commit -m "$(cat <<'EOF'
feat: register Coupon as Wagtail Snippet

- List view with code, status, discount, times_redeemed
- Filter by status and discount_type
- Search by code

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Validate Coupon API Endpoint

### Step 5.1: Add validate_coupon view to api/views.py

Add to `home/api/views.py`:

```python
@require_http_methods(["GET"])
def validate_coupon(request):
    """
    Validate a coupon code.

    Path: GET /api/v1/validate-coupon/?code=SUMMER20

    Returns:
        - 200: Coupon is valid with discount details
        - 400: Invalid or expired coupon
        - 404: Coupon not found
    """
    code = request.GET.get('code', '').upper().strip()

    if not code:
        return JsonResponse({'valid': False, 'error': 'Kod jest wymagany'}, status=400)

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return JsonResponse({'valid': False, 'error': 'Nie znaleziono kodu'}, status=404)

    if not coupon.is_valid:
        # Determine why it's invalid
        if coupon.status != 'active':
            error = 'Ten kupon jest nieaktywny'
        elif coupon.expires_at and coupon.expires_at < timezone.now():
            error = 'Ten kupon wygasł'
        elif coupon.max_redemptions and coupon.times_redeemed >= coupon.max_redemptions:
            error = 'Ten kupon osiągnął limit użyć'
        else:
            error = 'Ten kupon jest nieprawidłowy'

        return JsonResponse({'valid': False, 'error': error}, status=400)

    # Return valid coupon details
    response_data = {
        'valid': True,
        'code': coupon.code,
        'discount_type': coupon.discount_type,
        'message': '',
    }

    if coupon.discount_type == 'percent':
        response_data['percent_off'] = coupon.percent_off
        response_data['message'] = f'{coupon.percent_off}% zniżki zastosowane'
    else:
        response_data['amount_off'] = coupon.amount_off
        response_data['amount_off_pln'] = coupon.amount_off / 100
        response_data['message'] = f'{coupon.amount_off / 100:.2f} PLN zniżki zastosowane'

    return JsonResponse(response_data)
```

### Step 5.2: Update imports in api/views.py

Add `Coupon` and `timezone` to imports:

```python
from django.utils import timezone
from home.models import Product, Event, Coupon
```

### Step 5.3: Add URL route in api/urls.py

Add to `home/api/urls.py`:

```python
path('validate-coupon/', views.validate_coupon, name='validate_coupon'),
```

### Step 5.4: Commit

```bash
git add home/api/views.py home/api/urls.py
git commit -m "$(cat <<'EOF'
feat: add validate-coupon API endpoint

- GET /api/v1/validate-coupon/?code=SUMMER20
- Returns discount details or error message
- Validates status, expiration, and usage limits

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update Checkout to Accept Coupon

### Step 6.1: Update create_basket_checkout_session signature

Modify `create_basket_checkout_session` in `home/stripe_sync.py` to accept an optional coupon parameter:

```python
@staticmethod
def create_basket_checkout_session(
    products: List,
    success_url: str,
    cancel_url: str,
    customer_email: Optional[str] = None,
    coupon = None  # Add this parameter
) -> dict:
```

### Step 6.2: Add coupon to session params

Inside `create_basket_checkout_session`, after the `session_params` definition, add:

```python
            # Apply coupon if provided and valid
            if coupon and coupon.is_valid and coupon.stripe_promotion_code_id:
                session_params['discounts'] = [{
                    'promotion_code': coupon.stripe_promotion_code_id
                }]
                logger.info(f"Applied coupon {coupon.code} to checkout session")
```

### Step 6.3: Update the view that calls create_basket_checkout_session

Find and update the view that creates checkout sessions (likely in `home/api/views.py`) to accept and pass the coupon:

```python
# In the checkout creation view, get coupon from request
coupon_code = request.data.get('coupon_code')
coupon = None
if coupon_code:
    try:
        coupon = Coupon.objects.get(code=coupon_code.upper())
        if not coupon.is_valid:
            coupon = None  # Ignore invalid coupons
    except Coupon.DoesNotExist:
        pass  # Ignore non-existent coupons

# Pass coupon to checkout session creation
result = StripeSync.create_basket_checkout_session(
    products=products,
    success_url=success_url,
    cancel_url=cancel_url,
    customer_email=customer_email,
    coupon=coupon,  # Add this
)
```

### Step 6.4: Commit

```bash
git add home/stripe_sync.py home/api/views.py
git commit -m "$(cat <<'EOF'
feat: apply coupon to checkout session

- create_basket_checkout_session accepts optional coupon
- Applies Stripe promotion_code if coupon is valid
- Checkout view passes coupon from request

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add Webhook Handlers for Coupon Events

### Step 7.1: Add coupon webhook handlers to webhooks.py

Add to `home/api/webhooks.py` in the event handling section:

```python
        elif event.type == 'coupon.updated':
            # Sync times_redeemed from Stripe
            stripe_coupon = event.data.object
            wagtail_id = stripe_coupon.metadata.get('wagtail_id')

            if wagtail_id:
                try:
                    coupon = Coupon.objects.get(pk=int(wagtail_id))
                    result = StripeSync.sync_coupon_redemptions(coupon)
                    if result['success']:
                        logger.info(f"Synced coupon {wagtail_id} redemptions from Stripe")
                except Coupon.DoesNotExist:
                    logger.warning(f"Coupon {wagtail_id} not found for webhook sync")

        elif event.type == 'promotion_code.updated':
            # Sync active status from Stripe
            stripe_promo = event.data.object
            wagtail_id = stripe_promo.metadata.get('wagtail_id')

            if wagtail_id:
                try:
                    coupon = Coupon.objects.get(pk=int(wagtail_id))
                    new_status = 'active' if stripe_promo.active else 'inactive'

                    if coupon.status != new_status:
                        coupon._skip_stripe_sync = True
                        coupon.status = new_status
                        coupon.save(update_fields=['status'])
                        logger.info(f"Updated coupon {wagtail_id} status from Stripe webhook")
                except Coupon.DoesNotExist:
                    logger.warning(f"Coupon {wagtail_id} not found for webhook sync")
```

### Step 7.2: Add Coupon import to webhooks.py

```python
from home.models import Product, Coupon
```

### Step 7.3: Commit

```bash
git add home/api/webhooks.py
git commit -m "$(cat <<'EOF'
feat: add webhook handlers for coupon sync

- coupon.updated: syncs times_redeemed from Stripe
- promotion_code.updated: syncs active status

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Final Testing

### Step 8.1: Run the development server

```bash
cd /Users/seba/piorka && poetry run python manage.py runserver
```

### Step 8.2: Test coupon creation

1. Go to `/admin/`
2. Navigate to Snippets > Kupony
3. Create a new coupon:
   - Code: TEST20
   - Discount type: Percentage
   - Percent off: 20
   - Status: Active
4. Save and verify it appears in Stripe dashboard

### Step 8.3: Test coupon validation

```bash
curl "http://localhost:8000/api/v1/validate-coupon/?code=TEST20"
```

Expected: `{"valid": true, "code": "TEST20", "discount_type": "percent", "percent_off": 20, ...}`

### Step 8.4: Test invalid coupon

```bash
curl "http://localhost:8000/api/v1/validate-coupon/?code=INVALID"
```

Expected: `{"valid": false, "error": "Nie znaleziono kodu"}`

---

## Summary

| Task | Description | Commits |
|------|-------------|---------|
| 1 | Add Coupon model | 1 |
| 2 | Add Stripe sync methods | 1 |
| 3 | Add signal handlers | 1 |
| 4 | Register Wagtail Snippet | 1 |
| 5 | Add validate-coupon API | 1 |
| 6 | Update checkout with coupon | 1 |
| 7 | Add webhook handlers | 1 |
| 8 | Testing | - |

**Total: 7 commits**
