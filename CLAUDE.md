# CLAUDE.md - Piorka E-Commerce Platform

## Project Overview

E-commerce platform for a Polish artist selling handmade jewelry crafted from bird feathers. The platform combines a product catalog with artist portfolio functionality.

### Architecture

The project is a **monorepo** with planned structure:
- **Backend** (`/backend`) - Django 5.2 + Wagtail 7.2 CMS with REST API
- **Frontend Shop** (`/frontend`) - React 19 + TypeScript + Vite + Tailwind CSS
- **Frontend Artist Page** - Planned, not yet implemented

## Tech Stack

### Backend
- **Framework**: Django 5.2.8
- **CMS**: Wagtail 7.2.1
- **Database**: PostgreSQL
- **Server**: Gunicorn
- **Package Manager**: Poetry

### Frontend
- **Framework**: React 19
- **Language**: TypeScript 5.9
- **Build Tool**: Vite 7
- **Styling**: Tailwind CSS 4

## Quick Commands

### Backend
```bash
cd backend
poetry install                    # Install dependencies
poetry run python manage.py runserver  # Run dev server (port 8000)
poetry run python manage.py migrate    # Run migrations
poetry run python manage.py createsuperuser  # Create admin user
```

### Frontend
```bash
cd frontend
npm install     # Install dependencies
npm run dev     # Run dev server (port 5173)
npm run build   # Production build
npm run lint    # ESLint
```

## Database Models

### Product (`home/models.py`)
Main product model for jewelry items:

| Field | Type | Description |
|-------|------|-------------|
| `name` / `tytul` | CharField | English / Polish name |
| `slug` | SlugField | Auto-generated URL slug |
| `description` / `opis` | TextField | English / Polish description |
| `price` / `cena` | DecimalField | Base price / promotional price |
| `active` | BooleanField | Available in store |
| `featured` | BooleanField | Show on homepage |
| `stripe_product_id` | CharField | Stripe product ID |
| `stripe_price_id` | CharField | Stripe price ID |

**Product Attributes** (jewelry-specific):
- `przeznaczenie_ogolne` - Type: earrings, necklace, bracelet, hair accessory
- `dla_kogo` - Target: women, men, unisex (JSONField multi-select)
- `dlugosc_kategoria` / `dlugosc_w_cm` - Length category and exact measurement
- `kolor_pior` - Feather colors (JSONField multi-select)
- `gatunek_ptakow` - Bird species (JSONField multi-select)
- `kolor_elementow_metalowych` - Metal element color
- `rodzaj_zapiecia` - Fastening type (JSONField multi-select)

### ProductImage (`home/models.py`)
Ordered image gallery for products using Wagtail's image system.

### Event (`home/models.py`)
Artist's local shop appearances and exhibitions:
- `title`, `description`, `location`
- `start_date`, `end_date`
- `active` - Is event active
- Related `EventImage` gallery

## API Endpoints

All endpoints return JSON and are located at `/api/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/products/` | GET | All active products with images |
| `/api/events/` | GET | All active events with images |
| `/api/images/?tag=x,y` | GET | Images filtered by tags |

## URL Structure

```
/admin/           # Wagtail CMS admin
/django-admin/    # Django admin
/api/products/    # Products API
/api/events/      # Events API
/api/images/      # Images API
```

## Integrations

### Stripe (Partially Implemented)
- Product model has `stripe_product_id` and `stripe_price_id` fields
- No webhook handlers or checkout flow implemented yet
- **TODO**: Payment processing, webhooks, checkout sessions

### InPost (Not Implemented)
- Polish parcel locker shipping service
- **TODO**: Shipping method integration, parcel tracking

## Environment Variables

### Database (PostgreSQL)
```
POSTGRES_DB=wagtail
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### Django
```
DJANGO_SETTINGS_MODULE=core.settings.dev  # or core.settings.production
SECRET_KEY=your-secret-key
```

### CORS (configured in settings)
- Dev frontend: `http://localhost:5173`

## Project Conventions

### Languages
- **Polish (pl)** - Primary language for product content
- **English (en)** - Secondary language support
- Field naming uses Polish for domain-specific attributes

### Code Style
- Backend: Black formatter, Pylint
- Frontend: ESLint with TypeScript rules

### Model Patterns
- `ClusterableModel` for models with related orderable items (images)
- `ParentalKey` for foreign keys in orderable inline models
- JSONField for multi-select attributes
- Automatic slug generation from name field

### Admin Interface
- Products and Events registered as Wagtail Snippets
- Custom ViewSets with filtering and search
- Hidden menu items: explorer, documents, snippets

## Docker

### Backend
```dockerfile
# Port 8000, Python 3.13, non-root user
docker build -t piorka-backend ./backend
docker run -p 8000:8000 piorka-backend
```

### Frontend
```dockerfile
# Port 80, Nginx Alpine, gzip compression
docker build -t piorka-frontend ./frontend
docker run -p 80:80 piorka-frontend
```

## File Structure

```
piorka/
├── backend/
│   ├── core/                 # Django project settings
│   │   ├── settings/
│   │   │   ├── base.py      # Shared settings
│   │   │   ├── dev.py       # Development
│   │   │   └── production.py
│   │   ├── urls.py          # URL routing
│   │   └── wsgi.py
│   ├── home/                 # Main app
│   │   ├── models.py        # Product, Event, Image models
│   │   ├── views.py         # API views
│   │   ├── wagtail_hooks.py # Admin customization
│   │   └── migrations/
│   ├── search/              # Wagtail search app
│   ├── manage.py
│   ├── pyproject.toml       # Poetry dependencies
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main React component
│   │   └── main.tsx         # Entry point
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
└── README.md
```

## Current Status

### Completed
- Product and Event models with full attribute schema
- Wagtail CMS admin interface
- REST API endpoints for products, events, images
- Docker containerization
- Frontend scaffold (React + TypeScript + Tailwind)

### In Progress / TODO
- [ ] Stripe payment integration (webhooks, checkout, payment links)
- [ ] InPost shipping integration
- [ ] Order management system (no Order model yet)
- [ ] Customer accounts / authentication
- [ ] Frontend shop UI (product catalog, cart, checkout)
- [ ] Frontend artist portfolio page
- [ ] Email notifications
