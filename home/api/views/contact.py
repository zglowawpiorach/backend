"""
Contact form API views.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt

from home.services import BrevoService
from home.api.serializers import ContactFormSerializer

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def submit_contact_form(request):
    """
    Submit contact form and send emails via Brevo.

    POST /api/v1/contact/

    Request body:
    {
        "name": "Jan Kowalski",
        "email": "jan.kowalski@example.com",
        "message": "Treść wiadomości..."
    }

    Sends two emails:
    1. Notification to business owner with the user's message
    2. Thank you auto-reply to the user who filled the form

    Response:
    {
        "success": true
    }

    or on error:
    {
        "success": false,
        "error": "Contact template not configured"
    }
    """
    serializer = ContactFormSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    name = serializer.validated_data.get('name')
    email = serializer.validated_data.get('email')
    message = serializer.validated_data.get('message')

    logger.info(f"[Contact] Form submission: name={name}, email={email}")

    brevo = BrevoService()
    result = brevo.send_contact_emails(
        user_email=email,
        user_name=name,
        message=message,
    )

    logger.debug(f"[Contact] Brevo response: {result}")

    if result["success"]:
        return Response({"success": True}, status=status.HTTP_200_OK)
    else:
        return Response(
            {"success": False, "error": result.get("error")},
            status=status.HTTP_400_BAD_REQUEST
        )
