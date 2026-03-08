"""
Newsletter API views.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt

from home.services import BrevoService
from home.api.serializers import NewsletterSubscribeSerializer

logger = logging.getLogger(__name__)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@csrf_exempt
def subscribe_to_newsletter(request):
    """
    Subscribe a contact to the Brevo newsletter list.

    GET /api/v1/newsletter/subscribe/?email=customer@example.com&name=Jan%20Kowalski
    POST /api/v1/newsletter/subscribe/

    Supports both query parameters (for email links) and request body (for API calls).

    Query params (GET) or Request body (POST):
    - email: Customer email address (required)
    - name: Customer name (optional)

    Response:
    {
        "success": true,
        "contact_id": "123456"
    }

    or on error:
    {
        "success": false,
        "error": "Newsletter list not configured"
    }
    """
    # Accept data from query params (GET) or request body (POST)
    if request.method == 'GET':
        data = {
            'email': request.query_params.get('email'),
            'name': request.query_params.get('name'),
        }
    else:
        data = request.data

    serializer = NewsletterSubscribeSerializer(data=data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data.get('email')
    name = serializer.validated_data.get('name')

    logger.info(f"[Newsletter] Subscribe request: email={email}, name={name}")

    brevo = BrevoService()
    result = brevo.subscribe_to_newsletter(email=email, name=name)

    logger.debug(f"[Newsletter] Brevo response: {result}")

    if result["success"]:
        return Response(
            {"success": True, "contact_id": result.get("contact_id")},
            status=status.HTTP_201_CREATED
        )
    else:
        return Response(
            {"success": False, "error": result.get("error")},
            status=status.HTTP_400_BAD_REQUEST
        )
