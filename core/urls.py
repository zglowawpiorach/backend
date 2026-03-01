from django.conf import settings
from django.urls import include, path
from django.contrib import admin

from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls

from search import views as search_views
from home import views as home_views
from home.api.webhooks import stripe_webhook

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("search/", search_views.search, name="search"),
    path("api/images/", home_views.images_api, name="images_api"),
    path("api/products/", home_views.products_api, name="products_api"),
    path("api/events/", home_views.events_api, name="events_api"),
    path("api/product-filters/", home_views.product_filters_api, name="product_filters_api"),
    # Stripe checkout endpoint
    path("api/checkout/create/", home_views.create_checkout_session, name="checkout_create"),
    # New REST API v1 endpoints with Stripe integration
    path("api/v1/", include("home.api.urls")),
    # Stripe webhook endpoint
    path("api/webhooks/stripe/", stripe_webhook, name="stripe-webhook"),
]


if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    # Serve static and media files from development server
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns = urlpatterns + [
    # For anything not caught by a more specific rule above, hand over to
    # Wagtail's page serving mechanism. This should be the last pattern in
    # the list:
    path("", include(wagtail_urls)),
    # Alternatively, if you want Wagtail pages to be served from a subpath
    # of your site, rather than the site root:
    #    path("pages/", include(wagtail_urls)),
]
