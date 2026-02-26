# Frontend Basket & Checkout Integration Guide

## Overview

This guide explains how to integrate the frontend basket with the backend checkout and reservation system.

## Architecture

```
┌─────────────┐     reserve-basket      ┌──────────────┐
│   Frontend  │ ──────────────────────> │   Backend    │
│  (Basket)   │                          │  (Django)    │
└─────────────┘                          └──────────────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │    Stripe    │
                                        │   Checkout   │
                                        └──────────────┘
                                               │
                    ┌──────────────────────────┴──────────────────────────┐
                    ▼                                                         ▼
            ┌───────────────┐                                       ┌───────────────┐
            │  Webhook:     │                                       │  Webhook:     │
            │  completed    │                                       │  expired      │
            │  (mark sold)  │                                       │  (release)    │
            └───────────────┘                                       └───────────────┘
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/products/` | GET | Get available products (excludes reserved/sold) |
| `/api/v1/check-availability/` | POST | Check if products can be purchased |
| `/api/v1/reserve-basket/` | POST | Create reservation + Stripe checkout |
| `/api/v1/cancel-checkout/` | POST | Cancel reservation and release products |

## Integration Steps

### 1. Fetch Products

```typescript
// Fetch only active, buyable products
const response = await fetch('https://api.zglowawpiorach.pl/api/v1/products/');
const data = await response.json();

// data.results contains products that are available for purchase
// Products with status='reserved' or status='sold' are filtered out
```

### 2. Build Basket State

```typescript
interface BasketItem {
  id: number;
  name: string;
  tytul: string;  // Polish title
  price: number;
  cena: number;  // Promotional price (if set)
  image_url: string;
  slug: string;
}

interface BasketState {
  items: BasketItem[];
  // Store session_id after reservation for cancellation option
  sessionId: string | null;
  expiresAt: string | null;
}
```

### 3. Check Availability Before Checkout

Before redirecting to checkout, verify all items are still available:

```typescript
async function checkAvailability(productIds: number[]) {
  const response = await fetch('/api/v1/check-availability/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_ids: productIds })
  });

  const { available, unavailable } = await response.json();

  if (unavailable.length > 0) {
    // Show user which items are no longer available
    unavailable.forEach(item => {
      console.error(`Product ${item.id}: ${item.message}`);
    });
    return false;
  }

  return true;
}
```

### 4. Reserve Basket & Create Checkout

This is the main checkout flow. It atomically:
1. Creates a Stripe Checkout Session
2. Reserves all products for 30 minutes

```typescript
async function initiateCheckout(basket: BasketItem[]) {
  // 1. Build URLs with session_id placeholder
  const baseUrl = window.location.origin;
  const successUrl = `${baseUrl}/success?session_id={CHECKOUT_SESSION_ID}`;
  const cancelUrl = `${baseUrl}/shop`;

  // 2. Call reserve-basket endpoint
  const response = await fetch('/api/v1/reserve-basket/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      product_ids: basket.map(item => item.id),
      success_url: successUrl,
      cancel_url: cancelUrl,
      // Optional: pre-fill customer email
      // customer_email: user?.email
    })
  });

  const result = await response.json();

  if (!result.success) {
    // Handle unavailable products
    if (result.unavailable_products) {
      result.unavailable_products.forEach(item => {
        console.error(`Product ${item.id}: ${item.message}`);
        // Remove from basket or show error
      });
    }
    return { success: false };
  }

  // 3. Store session info for potential cancellation
  basketState.sessionId = result.session_id;
  basketState.expiresAt = result.expires_at;

  // 4. Redirect to Stripe checkout
  window.location.href = result.checkout_url;

  return { success: true };
}
```

### 5. Handle Success Page

After payment, Stripe redirects to your success URL with the session ID:

```typescript
// On /success page
const urlParams = new URLSearchParams(window.location.search);
const sessionId = urlParams.get('session_id');

if (sessionId) {
  // Verify payment status (optional, for security)
  // You could create an endpoint to verify session status
  showThankYouMessage();
  clearBasket();
}
```

### 6. Cancel Checkout (Optional)

If user wants to cancel their order before paying:

```typescript
async function cancelCheckout(sessionId: string) {
  const response = await fetch('/api/v1/cancel-checkout/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId })
  });

  const result = await response.json();

  if (result.success) {
    // Products released back to inventory
    clearBasket();
  }
}
```

## Reservation Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                     Product Status Flow                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   active ──reserve───> reserved (30 min)                        │
│      │                      │                                   │
│      │                      ├─payment completed──> sold          │
│      │                      │                                   │
│      │                      └─expired/cancelled──> active        │
│      │                                                          │
│      └─────────────────────> sold (after webhook)              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Webhook Events (Backend Only)

The backend handles these Stripe webhook events automatically:

- `checkout.session.completed` → Marks products as sold
- `checkout.session.expired` → Releases products back to active

## Cron Job Setup

A cleanup script runs every 5 minutes to handle edge cases:

```bash
# Add to crontab with: crontab -e
*/5 * * * * /path/to/backend/cleanup_reservations.sh
```

## Complete Example

```typescript
// basket.ts - Complete basket management
import { reactive } from 'vue';

interface BasketItem {
  id: number;
  name: string;
  tytul: string;
  price: number;
  cena: number | null;
  image_url: string;
  slug: string;
}

const basketState = reactive<{
  items: BasketItem[];
  sessionId: string | null;
  expiresAt: string | null;
}>({
  items: [],
  sessionId: null,
  expiresAt: null
});

// Add product to basket
export function addToBasket(product: BasketItem) {
  // Check if already in basket (each product is unique)
  if (!basketState.items.find(item => item.id === product.id)) {
    basketState.items.push(product);
    saveToLocalStorage();
  }
}

// Remove from basket
export function removeFromBasket(productId: number) {
  basketState.items = basketState.items.filter(item => item.id !== productId);
  saveToLocalStorage();
}

// Check if all items are still available
export async function checkBasketAvailability(): Promise<boolean> {
  if (basketState.items.length === 0) return false;

  const response = await fetch('/api/v1/check-availability/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      product_ids: basketState.items.map(item => item.id)
    })
  });

  const { unavailable } = await response.json();

  if (unavailable && unavailable.length > 0) {
    // Remove unavailable items from basket
    unavailable.forEach(item => {
      removeFromBasket(item.id);
    });
    return false;
  }

  return true;
}

// Initiate checkout
export async function checkout(): Promise<{ success: boolean; error?: string }> {
  if (basketState.items.length === 0) {
    return { success: false, error: 'Basket is empty' };
  }

  // Check availability first
  const available = await checkBasketAvailability();
  if (!available) {
    return { success: false, error: 'Some items are no longer available' };
  }

  const baseUrl = window.location.origin;
  const response = await fetch('/api/v1/reserve-basket/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      product_ids: basketState.items.map(item => item.id),
      success_url: `${baseUrl}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${baseUrl}/shop`
    })
  });

  const result = await response.json();

  if (!result.success) {
    return { success: false, error: 'Failed to create checkout' };
  }

  // Store session info
  basketState.sessionId = result.session_id;
  basketState.expiresAt = result.expires_at;

  // Redirect to Stripe
  window.location.href = result.checkout_url;

  return { success: true };
}

// Cancel active reservation
export async function cancelReservation(): Promise<void> {
  if (basketState.sessionId) {
    await fetch('/api/v1/cancel-checkout/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: basketState.sessionId })
    });
  }

  basketState.sessionId = null;
  basketState.expiresAt = null;
}

// Calculate total
export function basketTotal(): number {
  return basketState.items.reduce((sum, item) => {
    return sum + (item.cena ?? item.price);
  }, 0);
}

// Local storage helpers
function saveToLocalStorage() {
  localStorage.setItem('basket', JSON.stringify(basketState.items));
}

export function loadFromLocalStorage() {
  const saved = localStorage.getItem('basket');
  if (saved) {
    basketState.items = JSON.parse(saved);
  }
}

export { basketState };
```

## Environment Variables

```env
# Backend
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Frontend (for Stripe.js if needed)
VITE_STRIPE_PUBLIC_KEY=pk_test_...
```

## Testing Checklist

- [ ] Add product to basket
- [ ] Check availability returns available
- [ ] Reserve basket creates checkout session
- [ ] Redirect to Stripe works
- [ ] Product becomes reserved (not visible in products list)
- [ ] Cancel checkout releases product
- [ ] Product becomes available again
- [ ] Expired reservation releases product (after 30 min or via cleanup)
