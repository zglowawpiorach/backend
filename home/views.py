import logging
from django.http import JsonResponse
from django.core.cache import cache
from django.utils import timezone
from wagtail.images.models import Image
from .models import Product, Event, ProductStatus, ReservationStatus
from .decorators import api_error_handler

logger = logging.getLogger(__name__)


@api_error_handler
def images_api(request):
    """
    API endpoint to get images filtered by tags.
    Usage: /api/images/?tag=one,two,three
    Returns list of image URLs matching any of the provided tags.
    """
    # Get tag parameter from query string
    tag_param = request.GET.get('tag', '')

    # Start with all images
    images = Image.objects.all()

    # Filter by tags if provided
    if tag_param:
        tags = [tag.strip() for tag in tag_param.split(',')]
        # Filter images that have any of the specified tags
        for tag in tags:
            images = images.filter(tags__name__iexact=tag)

    # Build response with image data
    image_list = []
    for img in images:
        image_list.append({
            'id': img.id,
            'title': img.title,
            'url': request.build_absolute_uri(img.file.url),
            'width': img.width,
            'height': img.height,
            'tags': [tag.name for tag in img.tags.all()],
        })

    return JsonResponse({
        'count': len(image_list),
        'images': image_list
    })


@api_error_handler
def products_api(request):
    """
    API endpoint to get active products.
    Usage: /api/products/
    Returns list of active products with their details.
    Query params:
      - status: 'active' (default), 'sold', 'all'
    """
    # Get status filter from query string
    status_filter = request.GET.get('status', 'active')

    # Build queryset based on status filter
    if status_filter == 'sold':
        products = Product.objects.filter(status=ProductStatus.SOLD)
    elif status_filter == 'all':
        products = Product.objects.all()
    else:
        # Default: active products (includes RESERVED status for frontend to handle)
        products = Product.objects.filter(active=True)

    products = products.prefetch_related('images')

    now = timezone.now()

    # Build response with product data
    product_list = []
    for product in products:
        # Get all product images
        images = []
        for product_image in product.images.all():
            if product_image.image:
                images.append({
                    'url': request.build_absolute_uri(product_image.image.file.url),
                    'width': product_image.image.width,
                    'height': product_image.image.height,
                })

        # Check for active reservation
        is_reserved = False
        reserved_until = None

        if product.status == ProductStatus.RESERVED:
            # Check for active pending reservation that hasn't expired
            active_reservation = product.reservations.filter(
                reservation__status=ReservationStatus.PENDING,
                reservation__expires_at__gt=now
            ).select_related('reservation').first()

            if active_reservation:
                is_reserved = True
                reserved_until = active_reservation.reservation.expires_at.isoformat()

        product_list.append({
            'id': product.id,
            'slug': product.slug,
            'name': product.name,
            'tytul': product.tytul,
            'description': product.description,
            'opis': product.opis,
            'price': float(product.price),
            'cena': float(product.cena) if product.cena else None,
            'status': product.status,
            'is_reserved': is_reserved,
            'reserved_until': reserved_until,
            'featured': product.featured,
            'nr_w_katalogu_zdjec': product.nr_w_katalogu_zdjec,
            'przeznaczenie_ogolne': product.przeznaczenie_ogolne,
            'dla_kogo': product.dla_kogo,
            'dlugosc_kategoria': product.dlugosc_kategoria,
            'dlugosc_w_cm': float(product.dlugosc_w_cm) if product.dlugosc_w_cm else None,
            'kolor_pior': product.kolor_pior,
            'gatunek_ptakow': product.gatunek_ptakow,
            'kolor_elementow_metalowych': product.kolor_elementow_metalowych,
            'rodzaj_zapiecia': product.rodzaj_zapiecia,
            'images': images,
            'created_at': product.created_at.isoformat(),
            'updated_at': product.updated_at.isoformat(),
        })

    return JsonResponse({
        'count': len(product_list),
        'products': product_list
    })


@api_error_handler
def events_api(request):
    """
    API endpoint to get active events.
    Usage: /api/events/
    Returns list of active events with their details.
    """
    # Get only active events
    events = Event.objects.filter(active=True).prefetch_related('images')

    # Build response with event data
    event_list = []
    for event in events:
        # Get all event images
        images = []
        for event_image in event.images.all():
            if event_image.image:
                images.append({
                    'url': request.build_absolute_uri(event_image.image.file.url),
                    'width': event_image.image.width,
                    'height': event_image.image.height,
                })

        event_list.append({
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'location': event.location,
            'start_date': event.start_date.isoformat(),
            'end_date': event.end_date.isoformat(),
            'external_url': event.external_url,
            'images': images,
            'created_at': event.created_at.isoformat(),
            'updated_at': event.updated_at.isoformat(),
        })

    return JsonResponse({
        'count': len(event_list),
        'events': event_list
    })


@api_error_handler
def product_filters_api(request):
    """
    API endpoint to get all possible filter values for products.
    Returns unique values for all filterable fields from active products.
    Cached for 24 hours.
    Usage: /api/product-filters/
    """
    cache_key = 'product_filters'

    # Try to get from cache first
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return JsonResponse(cached_data)

    # Build filters from active products
    products = Product.objects.filter(active=True)

    # Single choice fields - use distinct()
    przeznaczenie = list(products.exclude(przeznaczenie_ogolne='')
                                          .values_list('przeznaczenie_ogolne', flat=True)
                                          .distinct()
                                          .order_by('przeznaczenie_ogolne'))

    dlugosc_kat = list(products.exclude(dlugosc_kategoria='')
                                      .values_list('dlugosc_kategoria', flat=True)
                                      .distinct()
                                      .order_by('dlugosc_kategoria'))

    kolor_metalowych = list(products.exclude(kolor_elementow_metalowych='')
                                            .values_list('kolor_elementow_metalowych', flat=True)
                                            .distinct()
                                            .order_by('kolor_elementow_metalowych'))

    # JSONField multi-select - extract unique values
    dla_kogo_set = set()
    kolor_pior_set = set()
    gatunek_set = set()
    zapięcia_set = set()

    for product in products.iterator():
        for val in (product.dla_kogo or []):
            dla_kogo_set.add(val)
        for val in (product.kolor_pior or []):
            kolor_pior_set.add(val)
        for val in (product.gatunek_ptakow or []):
            gatunek_set.add(val)
        for val in (product.rodzaj_zapiecia or []):
            zapięcia_set.add(val)

    response_data = {
        'przeznaczenie_ogolne': przeznaczenie,
        'dla_kogo': sorted(dla_kogo_set),
        'dlugosc_kategoria': dlugosc_kat,
        'kolor_pior': sorted(kolor_pior_set),
        'gatunek_ptakow': sorted(gatunek_set),
        'kolor_elementow_metalowych': kolor_metalowych,
        'rodzaj_zapiecia': sorted(zapięcia_set),
    }

    # Cache for 24 hours
    cache.set(cache_key, response_data, 86400)

    return JsonResponse(response_data)
