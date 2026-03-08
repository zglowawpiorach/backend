"""
Product API views.
"""

from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from home.models import Product, ProductStatus
from home.api.serializers import ProductSerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for Product model.

    - Lookup by slug (not id)
    - Default: only ACTIVE products
    - Query param ?status=sold returns sold products
    - Query param ?status=all returns all products
    """
    serializer_class = ProductSerializer
    lookup_field = 'slug'
    permission_classes = [AllowAny]

    def get_queryset(self):
        """
        Filter queryset based on status query parameter.

        Returns:
            - ACTIVE products by default
            - SOLD products if ?status=sold
            - All products if ?status=all
        """
        queryset = Product.objects.prefetch_related('images__image')
        status_filter = self.request.query_params.get('status', 'active')

        if status_filter == 'sold':
            return queryset.filter(status=ProductStatus.SOLD)
        elif status_filter == 'all':
            return queryset.all()
        else:  # default to active
            return queryset.filter(status=ProductStatus.ACTIVE)
