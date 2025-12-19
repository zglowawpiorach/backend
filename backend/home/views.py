from django.http import JsonResponse
from wagtail.images.models import Image
from .models import Product, Event


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


def products_api(request):
    """
    API endpoint to get active products.
    Usage: /api/products/
    Returns list of active products with their details.
    """
    # Get only active products
    products = Product.objects.filter(active=True).prefetch_related('images')

    # Build response with product data
    product_list = []
    for product in products:
        # Get all product images
        images = []
        for product_image in product.images.all():
            images.append({
                'url': request.build_absolute_uri(product_image.image.file.url),
                'width': product_image.image.width,
                'height': product_image.image.height,
            })

        product_list.append({
            'id': product.id,
            'slug': product.slug,
            'name': product.name,
            'tytul': product.tytul,
            'description': product.description,
            'opis': product.opis,
            'price': float(product.price),
            'cena': float(product.cena) if product.cena else None,
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
            'images': images,
            'created_at': event.created_at.isoformat(),
            'updated_at': event.updated_at.isoformat(),
        })

    return JsonResponse({
        'count': len(event_list),
        'events': event_list
    })
