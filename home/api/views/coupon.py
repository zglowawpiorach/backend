"""
Coupon API views.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils import timezone

from home.models import Coupon, CouponStatus


@api_view(['GET'])
@permission_classes([AllowAny])
def validate_coupon(request):
    """
    Validate a coupon code.

    GET /api/v1/validate-coupon/?code=SUMMER20

    Returns:
        - 200: Coupon is valid with discount details
        - 400: Invalid or expired coupon
        - 404: Coupon not found
    """
    code = request.query_params.get('code', '').upper().strip()

    if not code:
        return Response(
            {'valid': False, 'error': 'Kod jest wymagany'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return Response(
            {'valid': False, 'error': 'Nie znaleziono kodu'},
            status=status.HTTP_404_NOT_FOUND
        )

    if not coupon.is_valid:
        # Determine why it's invalid
        if coupon.status != CouponStatus.ACTIVE:
            error = 'Ten kupon jest nieaktywny'
        elif coupon.expires_at and coupon.expires_at < timezone.now():
            error = 'Ten kupon wygasł'
        elif coupon.max_redemptions and coupon.times_redeemed >= coupon.max_redemptions:
            error = 'Ten kupon osiągnął limit użyć'
        else:
            error = 'Ten kupon jest nieprawidłowy'

        return Response({'valid': False, 'error': error}, status=status.HTTP_400_BAD_REQUEST)

    # Return valid coupon details
    response_data = {
        'valid': True,
        'code': coupon.code,
        'discount_type': coupon.discount_type,
        'message': '',
    }

    if coupon.discount_type == 'percent':
        response_data['percent_off'] = coupon.percent_off
        response_data['message'] = f'{coupon.percent_off}% zniżki zastosowane'
    else:
        response_data['amount_off'] = coupon.amount_off
        response_data['amount_off_pln'] = coupon.amount_off
        response_data['message'] = f'{coupon.amount_off:.2f} PLN zniżki zastosowane'

    return Response(response_data, status=status.HTTP_200_OK)
