"""
InPost Paczkomat API views.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import models

from home.models import InPostPoint


@api_view(['GET'])
@permission_classes([AllowAny])
def search_inpost_points(request):
    """
    Search InPost Paczkomat locations.

    GET /api/v1/inpost-points/?q=warszawa
    GET /api/v1/inpost-points/?postcode=00-001
    GET /api/v1/inpost-points/?city=Warszawa

    Returns:
        List of matching InPost points with:
        - name: Point code (e.g., "ADA01N")
        - full_address: Formatted address
        - city: City name
        - postcode: Postal code
        - latitude/longitude: GPS coordinates
    """
    queryset = InPostPoint.objects.filter(active=True)

    # Search by query (searches name, city, street)
    q = request.query_params.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            models.Q(name__icontains=q) |
            models.Q(city__icontains=q) |
            models.Q(street__icontains=q)
        )

    # Filter by city
    city = request.query_params.get('city', '').strip()
    if city:
        queryset = queryset.filter(city__icontains=city)

    # Filter by postcode prefix
    postcode = request.query_params.get('postcode', '').strip()
    if postcode:
        queryset = queryset.filter(postcode__startswith=postcode)

    # Limit results
    queryset = queryset[:50]

    results = [
        {
            'name': point.name,
            'street': point.street,
            'building_number': point.building_number,
            'postcode': point.postcode,
            'city': point.city,
            'full_address': point.full_address,
            'latitude': point.latitude,
            'longitude': point.longitude,
            'location_description': point.location_description,
            'opening_hours': point.opening_hours,
        }
        for point in queryset
    ]

    return Response(results, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_inpost_point(request, name):
    """
    Get single InPost Paczkomat by name/code.

    GET /api/v1/inpost-points/ADA01N/

    Returns:
        Single point details or 404 if not found.
    """
    try:
        point = InPostPoint.objects.get(name=name, active=True)
    except InPostPoint.DoesNotExist:
        return Response(
            {'error': 'Paczkomat nie znaleziony'},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response({
        'name': point.name,
        'street': point.street,
        'building_number': point.building_number,
        'postcode': point.postcode,
        'city': point.city,
        'full_address': point.full_address,
        'latitude': point.latitude,
        'longitude': point.longitude,
        'location_description': point.location_description,
        'opening_hours': point.opening_hours,
    }, status=status.HTTP_200_OK)
