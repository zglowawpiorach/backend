# Repository Guidelines

## Project Overview

Piorka is a Django 6 + Wagtail 7 e-commerce backend for a handmade jewelry store. It provides a product catalog, event pages, Stripe-powered checkout with basket reservations, coupon/promo codes, and integrations with Brevo (email), Furgonetka/InPost (shipping), and Stripe (payments). The API is consumed by a separate frontend via `/api/v1/`.

## Architecture & Data Flow

```
Frontend → /api/v1/ (DRF) → Services → Models (PostgreSQL)
                                  ↓
                            External APIs (Stripe, Brevo, Furgonetka, InPost)

Stripe Webhooks → /api/webhooks/stripe/ → Handlers → Models + Brevo emails
```

- **CMS**: Wagtail pages (HomePage) + Snippets (Product, Event, Coupon, config singletons)
- **API**: DRF `ReadOnlyModelViewSet` for products; `@api_view` function views for checkout/reservations/coupons/shipping/newsletter/contact
- **Services**: Business logic lives in `home/services/` — no base class, either instance-based (Brevo, Furgonetka) or static-method-based (StripeSync, ReservationService)
- **Signals**: `home/signals.py` — `pre_save`/`post_save` on Product and Coupon trigger Stripe sync via `StripeSync`
- **Reservations**: 30-minute holds using `select_for_update` + `transaction.atomic`; cleaned up via cron or Stripe webhook expiry

## Key Directories

| Directory | Purpose |
|---|---|
| `home/models/` | Domain models (Product, Reservation, Coupon, Transaction, Event, shipping, configs) |
| `home/api/` | DRF views, serializers, URL routing, webhook handlers |
| `home/services/` | External integrations and business logic (Stripe, Brevo, Furgonetka, reservations) |
| `home/management/commands/` | Cron-friendly management commands (cleanup, sync) |
| `home/templates/` | Wagtail admin overrides and page templates |
| `core/settings/` | Split Django settings (base → dev/production) |
| `docs/plans/` | Feature design and implementation plans |

## Development Commands

```bash
# Dependency management
poetry install

# Run dev server
poetry run python manage.py runserver

# Database migrations
poetry run python manage.py makemigrations
poetry run python manage.py migrate

# Management commands
poetry run python manage.py sync_stripe_products
poetry run python manage.py sync_inpost_points
poetry run python manage.py furgonetka_points
poetry run python manage.py cleanup_expired_reservations
poetry run python manage.py create_random_products

# Docker services (Postgres + Stripe CLI)
docker compose up -d

# Tests
poetry run python manage.py test
# Note: also a manual integration test at project root: test_reservation.py (uses requests, not Django test runner)

# Linting
poetry run black .
poetry run pylint home/
```

## Code Conventions & Common Patterns

### Models
- Use Wagtail `ClusterableModel` for models with inline children (Product, Event)
- Use `Orderable` + `ParentalKey` for image galleries (`ProductImage`, `EventImage`)
- Config singletons use `django-solo` pattern (`BrevoConfig`, `FurgonetkaConfig`)
- Field names mix Polish (domain-specific like `dlugosc`, `kategoria`) and English (`created_at`, `status`)
- Enums defined as `IntegerChoices` or `TextChoices` inside model classes (`ProductStatus`, `CouponStatus`)

### API
- Public endpoints use `AllowAny` permissions — no user auth on API
- Furgonetka endpoints use shared-secret token auth via custom `_verify_furgonetka_auth()`
- Serializers: use plain `serializers.Serializer` (not `ModelSerializer`) for request/response validation
- Error responses: `JsonResponse({"error": "message"}, status=4xx)` or DRF standard errors

### Services
- No shared base class — each service is independent
- Instance-based services (`BrevoService`, `FurgonetkaService`) load config from singleton models in `__init__`
- Static-method services (`StripeSync`, `ReservationService`) are stateless
- External API calls use `requests` lib with `raise_for_status()` + `try/except RequestException`
- Stripe uses the official `stripe` Python SDK
- Logging: per-module `logger = logging.getLogger(__name__)` with `[ServiceName]` prefixes

### Error Handling
- Services: `try/except` around external calls, `logger.error`/`logger.exception`, re-raise or return error
- API views: catch service exceptions, return `JsonResponse` with error message
- Webhooks: signature verification first, then event routing with per-handler try/except

### Naming
- Model files: one model per file in `home/models/` (except `__init__.py` re-exports all)
- API views: one file per domain in `home/api/views/` (`product.py`, `checkout.py`, `coupon.py`, etc.)
- Templates: `home/templates/home/` for pages, `home/templates/wagtailadmin/` for admin overrides

## Important Files

| File | Purpose |
|---|---|
| `manage.py` | CLI entrypoint, loads `.env` via python-dotenv |
| `core/settings/base.py` | All settings: apps, middleware, DB, Stripe, REST, logging |
| `core/settings/dev.py` | Dev overrides: `DEBUG=True`, console email, verbose logging |
| `core/settings/production.py` | Prod: `ManifestStaticFilesStorage`, reduced logging, `local.py` override |
| `core/urls.py` | Root URL config — mounts `/api/v1/` and `/api/webhooks/stripe/` |
| `home/models/product.py` | Core Product model with status, images, Stripe sync |
| `home/models/transaction.py` | Transaction model (M2M to Product, customer/shipping data) |
| `home/models/reservation.py` | Reservation + ReservedProduct (basket holds) |
| `home/services/stripe.py` | Stripe checkout sessions, product/price/coupon sync |
| `home/services/reservation.py` | Atomic reserve/complete/cancel with 30-min expiry |
| `home/api/stripe_webhooks_handlers.py` | Webhook event handlers (checkout completed/expired, coupon events) |
| `home/signals.py` | Auto-sync Product/Coupon changes to Stripe |
| `home/wagtail_hooks.py` | Wagtail admin: snippet registrations, menu items, custom URLs |
| `openapi.yml` | OpenAPI 3.0 spec for the API |
| `docker-compose.yml` | Postgres 16 + Stripe CLI for local development |

## Runtime/Tooling Preferences

- **Python**: >=3.13
- **Package manager**: Poetry (no pip/setuptools)
- **Django**: 6.x + Wagtail 7.x
- **Database**: PostgreSQL (psycopg2-binary in dev, psycopg2 in prod)
- **Dev server**: `manage.py runserver` (no gunicorn in dev)
- **Env vars**: `.env` file loaded via python-dotenv in `manage.py`
- **Linting**: black (formatter), pylint (linter) — in dev dependencies
- **No Makefile/justfile** — use `poetry run` commands directly

### Key Environment Variables

```
DJANGO_SETTINGS_MODULE=core.settings.dev
SECRET_KEY=...
DATABASE_URL=...
STRIPE_SECRET_KEY=...
STRIPE_PUBLIC_KEY=...
STRIPE_WEBHOOK_SECRET=...
FURGONETKA_API_TOKEN=...
SENTRY_DSN=...
PUBLIC_URL=...
ALLOWED_HOSTS=...
CORS_ALLOWED_ORIGINS=...
```

## Testing & QA

- **Framework**: Django test runner + `WagtailPageTestCase` for page tests
- **Test files**: `home/tests.py` (basic Wagtail page tests), `test_reservation.py` at root (manual integration test using `requests`)
- **Coverage**: No coverage tooling configured — tests are minimal
- **API contract**: Documented in `openapi.yml` (OpenAPI 3.0.3)
- **Webhook testing**: Stripe CLI in Docker forwards events to local server (`docker compose up stripe-cli`)
- **Manual testing**: `test_reservation.py` hits live endpoints with `requests` library
- **Cron job**: `cleanup_reservations.sh` runs `cleanup_expired_reservations` via Poetry
