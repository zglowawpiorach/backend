# Coupon Model Design

Date: 2026-03-03
Status: Approved

## Overview

Add a Coupon model for promotional codes that customers can enter at checkout. Coupons sync with Stripe automatically (similar to Product sync pattern).

## Requirements

- Support both percentage and fixed amount discounts
- Admin-defined codes (e.g., "SUMMER20")
- Optional limits: max redemptions, expiration date
- Apply to entire order
- Automatic Stripe sync on create/update/deactivate

## Model

```python
class CouponStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"

class Coupon(models.Model):
    # Customer-facing code
    code = models.CharField(max_length=50, unique=True, db_index=True)

    # Discount type and value
    discount_type = models.CharField(choices=[
        ('percent', 'Percentage'),
        ('fixed', 'Fixed amount'),
    ])
    percent_off = models.PositiveIntegerField(null=True, blank=True)
    amount_off = models.PositiveIntegerField(null=True, blank=True)  # in grosze

    # Optional limits
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Status tracking
    status = models.CharField(choices=CouponStatus.choices, default=CouponStatus.ACTIVE)
    times_redeemed = models.PositiveIntegerField(default=0)

    # Stripe IDs
    stripe_coupon_id = models.CharField(max_length=255, blank=True)
    stripe_promotion_code_id = models.CharField(max_length=255, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_valid(self) -> bool:
        """Check if coupon can be used right now."""
        if self.status != CouponStatus.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_redemptions and self.times_redeemed >= self.max_redemptions:
            return False
        return True
```

## Stripe Sync

### StripeSync Methods (stripe_sync.py)

```python
@staticmethod
def create_or_update_coupon(coupon) -> dict:
    """
    Create or update Stripe Coupon + PromotionCode.
    - Creates Stripe Coupon with discount rules
    - Creates Stripe PromotionCode with customer-facing code
    - Updates stripe_coupon_id and stripe_promotion_code_id on model
    """

@staticmethod
def deactivate_coupon(coupon) -> dict:
    """
    Deactivate in Stripe by setting PromotionCode.active=False.
    """
```

### Signal Handlers (signals.py)

```python
@receiver(pre_save, sender=Coupon)
def track_coupon_status_change(sender, instance, **kwargs):
    # Track old status for detecting changes

@receiver(post_save, sender=Coupon)
def sync_coupon_to_stripe(sender, instance, created, **kwargs):
    """
    - Skip if _skip_stripe_sync is True
    - If status changed to INACTIVE: deactivate in Stripe
    - If status is ACTIVE: create or update in Stripe
    """
```

## Admin Interface

Registered as Wagtail Snippet with panels:

- Basic Info: code, status, times_redeemed (read-only)
- Discount: discount_type, percent_off, amount_off
- Limits: max_redemptions, expires_at
- Stripe Integration: stripe_coupon_id, stripe_promotion_code_id (read-only)

## Checkout Integration

### API Endpoint

```
POST /api/v1/validate-coupon/
Request:  { "code": "SUMMER20" }
Response: { "valid": true, "discount_type": "percent", "percent_off": 20, "message": "20% off applied" }
Error:    { "valid": false, "error": "Coupon expired" }
```

### Checkout Session Update

```python
# In create_basket_checkout_session
if coupon and coupon.is_valid:
    session_params['discounts'] = [{
        'promotion_code': coupon.stripe_promotion_code_id
    }]
```

## Webhook Handling

Sync `times_redeemed` from Stripe:

- `coupon.updated` - sync times_redeemed if changed
- `promotion_code.updated` - sync active status

## Implementation Order

1. Add Coupon model to models.py
2. Add StripeSync methods for coupons
3. Add signal handlers for coupon sync
4. Register Coupon as Wagtail Snippet
5. Add validate-coupon API endpoint
6. Update checkout session to accept coupon
7. Add webhook handlers for coupon events
8. Run migrations

## Files to Modify

- `home/models.py` - Add Coupon model
- `home/stripe_sync.py` - Add coupon sync methods
- `home/signals.py` - Add coupon signal handlers
- `home/wagtail_hooks.py` - Register Coupon snippet
- `home/api/views.py` - Add validate-coupon endpoint
- `home/api/urls.py` - Add coupon API route
- `home/api/webhooks.py` - Add coupon webhook handlers
