#!/usr/bin/env python
"""
Test script for product reservation flow.

Run with: poetry run python test_reservation.py
"""

import requests
import json

# API base URL
API_BASE = "http://localhost:8000/api/v1"

# Test product IDs
PRODUCT_IDS = [1]

# URLs for redirect
SUCCESS_URL = "http://localhost:5173/success?session_id={CHECKOUT_SESSION_ID}"
CANCEL_URL = "http://localhost:5173/shop"


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_check_availability():
    """Test the check-availability endpoint"""
    print_section("1. Check Availability")

    response = requests.post(
        f"{API_BASE}/check-availability/",
        json={"product_ids": PRODUCT_IDS},
        timeout=10
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json()


def test_get_products():
    """Get all products to see current state"""
    print_section("Current Products")

    response = requests.get(
        f"{API_BASE}/products/",
        timeout=10
    )

    print(f"Status: {response.status_code}")
    data = response.json()

    if 'results' in data:
        for item in data['results'][:5]:
            print(f"  ID {item.get('id')}: {item.get('name')} - Status: {item.get('status')}")
    else:
        print(f"Response: {json.dumps(data, indent=2)[:500]}...")


def test_reserve_basket():
    """Test the reserve-basket endpoint"""
    print_section("2. Reserve Basket & Create Checkout")

    payload = {
        "product_ids": PRODUCT_IDS,
        "success_url": SUCCESS_URL,
        "cancel_url": CANCEL_URL,
    }

    response = requests.post(
        f"{API_BASE}/reserve-basket/",
        json=payload,
        timeout=10
    )

    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response:")
    if data.get('success'):
        print(f"  ✓ Success!")
        print(f"  Checkout URL: {data.get('checkout_url')}")
        print(f"  Session ID: {data.get('session_id')}")
        print(f"  Expires at: {data.get('expires_at')}")
    else:
        print(f"  ✗ Failed!")
        print(f"  Error: {data.get('error')}")
        print(f"  Unavailable: {data.get('unavailable_products')}")

    return data


def main():
    print_section("Product Reservation Test")
    print(f"API Base: {API_BASE}")
    print(f"Product IDs: {PRODUCT_IDS}")

    # Check current state
    test_get_products()

    # Test availability
    availability = test_check_availability()

    if availability.get('unavailable'):
        print("\n⚠️  Some products are unavailable, skipping reserve test")
        return

    # Ask if user wants to proceed
    print_section("Confirm")
    response = input("\nDo you want to create a reservation? (y/n): ").strip().lower()
    if response != 'y':
        print("Skipped.")
        return

    # Reserve basket
    result = test_reserve_basket()

    # Check status after reservation
    if result.get('success'):
        print("\n⚠️  Products should now be RESERVED")
        print("   Visit the checkout URL to complete the purchase")
        print("   Or wait 30 min for the reservation to expire")

    test_get_products()


if __name__ == "__main__":
    main()
