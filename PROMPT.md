# Claude Code Prompt: Stripe Integration for Z Głową w Chmurach

## Project Context

You are implementing a Stripe payment integration for **Z Głową w Chmurach** — a one-of-a-kind jewelry e-commerce store. The backend is **Django + Wagtail CMS**, the frontend is **Next.js** (separate app). Each product is unique (quantity: 1). Once purchased, the product moves to a "sold archive" gallery visible on the frontend but no longer buyable.

## Tech Stack

- **Backend:** Python 3.11+, Django 5.x, Wagtail 6.x, Django REST Framework
- **Frontend:** Next.js (TypeScript, Tailwind CSS) — separate repository/service
- **Payments:** Stripe (Checkout Sessions, hosted payment page)
- **Auth:** django-allauth (optional customer accounts linked to Stripe via `stripe_customer_id`)
- **Database:** PostgreSQL
- **Cache:** Redis
- **Deployment:** Docker / Coolify on OVH VPS

## Implementation Requirements

### 1. Product Model (`products/models.py`)

Create a Wagtail Snippet model `Product` with:

```python
class ProductStatus(models.TextChoices):
    ACTIVE = "active", "Active"        # visible in shop, buyable
    INACTIVE = "inactive", "Inactive"  # hidden by client (e.g. sold on-site)
    SOLD = "sold", "Sold"              # purchased online, moved to archive
```

Fields:
- `name` — CharField(max_length=255)
- `slug` — SlugField(unique=True)
- `description` — TextField(blank=True)
- `price` — DecimalField(max_digits=10, decimal_places=2) — price in PLN
- `status` — CharField with ProductStatus choices, default ACTIVE
- `image` — ForeignKey to `wagtailimages.Image` (nullable)
- `stripe_product_id` — CharField(max_length=255, blank=True) — auto-managed
- `stripe_price_id` — CharField(max_length=255, blank=True) — auto-managed
- `sold_at` — DateTimeField(null=True, blank=True) — timestamp when purchased
- `created_at` — DateTimeField(auto_now_add=True)
- `updated_at` — DateTimeField(auto_now=True)

Wagtail panels:
- Main panel: name, slug, description, price, status, image
- Stripe panel (read-only): stripe_product_id, stripe_price_id, sold_at

Properties:
- `is_buyable` → returns True only if status == ACTIVE

### 2. Stripe Sync Service (`products/stripe_sync.py`)

Create a `StripeSync` class with static methods. Use `stripe` Python SDK. Read `STRIPE_SECRET_KEY` from Django settings.

#### `create_or_update_product(product)`
- If `stripe_product_id` is empty: create Stripe Product + Stripe Price (unit_amount in grosze, currency "pln"), save IDs to model
- If `stripe_product_id` exists: update Stripe Product metadata/name/description/active status
- If price changed: archive old Stripe Price (set inactive), create new Price, update `stripe_price_id`
- Stripe Product metadata must include: `wagtail_id`, `slug`

#### `deactivate_product(product)`
- Set Stripe Product `active: false`

#### `mark_as_sold(product)`
- Set product `status = "sold"`, `sold_at = now()`
- Save with `update_fields`
- Set Stripe Product `active: false`

#### `create_checkout_session(product, success_url, cancel_url, customer_email=None)`
- Create Stripe Checkout Session in mode "payment"
- Line items: product's `stripe_price_id`, quantity 1
- Shipping: fixed amount 2000 (20 PLN in grosze), display name "Przesyłka kurierska", delivery estimate 3-7 business days
- `success_url` — include `{CHECKOUT_SESSION_ID}` placeholder
- `cancel_url` — straight URL back to shop
- Metadata: `product_id` (string of Django PK)
- If `customer_email` provided: set on session and on `payment_intent_data.receipt_email`

### 3. Django Signals (`products/signals.py`)

#### `pre_save` on Product
- Track `_old_status` by loading the existing instance from DB

#### `post_save` on Product
- Skip if `instance._skip_stripe_sync` is True (prevents webhook → signal infinite loop)
- If status changed to "inactive": call `StripeSync.deactivate_product()`
- If status is "active" (new product or reactivated): call `StripeSync.create_or_update_product()`
- Wrap in try/except, log errors — never crash the save

Register signals in `products/apps.py` → `ready()`.

### 4. REST API Endpoints (`products/api/`)

#### Serializers (`serializers.py`)

**ProductSerializer** — ModelSerializer:
- Fields: id, name, slug, description, price, status, image_url, sold_at, created_at
- `image_url` — SerializerMethodField returning Wagtail rendition URL (fill-800x800) or None

**CheckoutRequestSerializer** — Serializer:
- `product_id` — IntegerField (required)
- `success_url` — URLField (required)
- `cancel_url` — URLField (required)
- `customer_email` — EmailField (optional)

#### Views (`views.py`)

**ProductViewSet** — ReadOnlyModelViewSet:
- Lookup by `slug`
- Query param `?status=sold` returns sold products (for archive page)
- Default queryset: only ACTIVE products
- Also support `?status=all` to return everything (useful for admin/debug)

**create_checkout** — @api_view(["POST"]):
- Validate with CheckoutRequestSerializer
- Get product by PK, must be ACTIVE — return 404 if not found or not active
- Call `StripeSync.create_checkout_session()`
- Return `{"checkout_url": session.url}`

#### URLs (`urls.py`)
- Router: `products/` → ProductViewSet (basename "products")
- Path: `checkout/` → create_checkout

### 5. Stripe Webhook Handler (`products/api/webhooks.py`)

Path: `POST /api/webhooks/stripe/`

- Exempt from CSRF
- Verify signature using `STRIPE_WEBHOOK_SECRET`
- Handle `checkout.session.completed`:
  - Extract `product_id` from session metadata
  - Load Product from DB
  - Set `_skip_stripe_sync = True` on instance (prevent signal loop)
  - Call `StripeSync.mark_as_sold(product)`
  - Log success
- Return 200 for all valid events (even unhandled ones)
- Return 400 for invalid signature

### 6. Management Command (`products/management/commands/sync_stripe_products.py`)

Command: `python manage.py sync_stripe_products`

- Iterate all ACTIVE products
- Call `StripeSync.create_or_update_product()` for each
- Print success/failure per product
- Useful for initial setup and debugging

### 7. URL Configuration

In `config/urls.py`, add:
```python
path("api/v1/", include("products.api.urls")),
path("api/webhooks/stripe/", stripe_webhook, name="stripe-webhook"),
```

### 8. Settings (`config/settings.py`)

Ensure these are configured (using `python-decouple`):
```python
STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')
```

Add to INSTALLED_APPS:
- `rest_framework`
- `corsheaders`
- `products`

Configure CORS for Next.js frontend origin.

### 9. Dependencies

Add to `requirements.txt`:
```
stripe>=8.0.0
djangorestframework>=3.15.0
django-cors-headers>=4.3.0
```
