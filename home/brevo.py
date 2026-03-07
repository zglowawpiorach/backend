"""
Brevo (Sendinblue) email service integration.

Brevo API documentation: https://developers.brevo.com/

This service handles:
1. Order confirmation emails
2. Shipping tracking emails
3. Marketing emails (optional)
"""

import logging
import requests
from django.conf import settings
from typing import Optional, List

logger = logging.getLogger(__name__)


class BrevoService:
    """
    Brevo email service for sending transactional emails.

    Usage:
        brevo = BrevoService()
        brevo.send_tracking_email(
            email="customer@example.com",
            tracking_number="1234567890123",
            carrier="inpost",
            order_id="cs_abc123"
        )
    """

    BASE_URL = "https://api.brevo.com/v3"

    def __init__(self):
        self.api_key = getattr(settings, "BREVO_API_KEY", "")
        self.sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "noreply@example.com")
        self.sender_name = getattr(settings, "BREVO_SENDER_NAME", "Z Głową w Piórach")

    def _headers(self) -> dict:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": self.api_key,
        }

    def is_configured(self) -> bool:
        """Check if Brevo is properly configured."""
        return bool(self.api_key)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None,
        template_id: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """
        Send a transactional email via Brevo.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content (if not using template)
            to_name: Recipient name (optional)
            template_id: Brevo template ID (optional, uses template instead of html_content)
            params: Template parameters (optional)

        Returns:
            dict with 'success' boolean and 'message_id' or 'error'
        """
        if not self.is_configured():
            logger.warning("Brevo not configured - email not sent")
            return {"success": False, "error": "Brevo not configured"}

        payload = {
            "sender": {
                "email": self.sender_email,
                "name": self.sender_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name or "",
                }
            ],
            "subject": subject,
        }

        if template_id:
            payload["templateId"] = template_id
            if params:
                payload["params"] = params
        else:
            payload["htmlContent"] = html_content

        try:
            response = requests.post(
                f"{self.BASE_URL}/smtp/email",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"[Brevo] Email sent to {to_email}: {data.get('messageId')}")
            return {"success": True, "message_id": data.get("messageId")}

        except requests.exceptions.RequestException as e:
            logger.error(f"[Brevo] Failed to send email to {to_email}: {e}")
            return {"success": False, "error": str(e)}

    def send_tracking_email(
        self,
        email: str,
        tracking_number: str,
        carrier: str = "inpost",
        order_id: Optional[str] = None,
        customer_name: Optional[str] = None,
    ) -> dict:
        """
        Send shipping tracking email.

        Args:
            email: Customer email
            tracking_number: Package tracking number
            carrier: Shipping carrier (inpost, dpd, ups, etc.)
            order_id: Order reference (Stripe session ID)
            customer_name: Customer name for personalization

        Returns:
            dict with 'success' boolean
        """
        # Carrier display names
        carrier_names = {
            "inpost": "InPost Paczkomat",
            "inpostkurier": "InPost Kurier",
            "dpd": "DPD",
            "ups": "UPS",
            "gls": "GLS",
            "fedex": "FedEx",
            "dhl": "DHL",
            "poczta": "Poczta Polska",
            "orlen": "Orlen Paczka",
        }

        carrier_display = carrier_names.get(carrier, carrier.upper())

        # Tracking URLs
        tracking_urls = {
            "inpost": f"https://inpost.pl/sledzenie-przesylek?number={tracking_number}",
            "inpostkurier": f"https://inpost.pl/sledzenie-przesylek?number={tracking_number}",
            "dpd": f"https://tracktrace.dpd.com.pl/parcelDetails?p1={tracking_number}",
            "ups": f"https://www.ups.com/track?tracknum={tracking_number}",
            "gls": f"https://gls-group.eu/PL/pl/sledzenie-paczek?match={tracking_number}",
            "fedex": f"https://www.fedex.com/fedextrack/?trknbr={tracking_number}",
            "dhl": f"https://www.dhl.com/pl-pl/home/tracking/tracking-parcel.html?submit=1&tracking-id={tracking_number}",
            "poczta": f"https://emonitoring.poczta-polska.pl/?numer={tracking_number}",
            "orlen": f"https://orlenpaczka.pl/sledzenie/{tracking_number}",
        }

        tracking_url = tracking_urls.get(carrier, "")

        # Use template if configured, otherwise send HTML directly
        template_id = getattr(settings, "BREVO_SHIPPING_TEMPLATE_ID", None)

        if template_id:
            # Use Brevo template
            return self.send_email(
                to_email=email,
                to_name=customer_name,
                subject=f"Twoja przesyłka jest w drodze - {carrier_display}",
                template_id=template_id,
                params={
                    "tracking_number": tracking_number,
                    "carrier": carrier_display,
                    "tracking_url": tracking_url,
                    "order_id": order_id or "",
                    "customer_name": customer_name or "",
                },
            )
        else:
            # Send HTML directly
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Twoja przesyłka jest w drodze!</h2>
                <p>Cześć{f" {customer_name}" if customer_name else ""},</p>
                <p>Twoje zamówienie {f"({order_id})" if order_id else ""} zostało wysłane.</p>
                <p><strong>Przewoźnik:</strong> {carrier_display}</p>
                <p><strong>Numer przesyłki:</strong> {tracking_number}</p>
                {f'<p><a href="{tracking_url}" style="background-color: #4F46E5; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Śledź przesyłkę</a></p>' if tracking_url else ''}
                <p>Dziękujemy za zakupy!</p>
                <p>Pozdrawiamy,<br>Z Głową w Piórach</p>
            </body>
            </html>
            """

            return self.send_email(
                to_email=email,
                to_name=customer_name,
                subject=f"Twoja przesyłka jest w drodze - {carrier_display}",
                html_content=html_content,
            )

    def send_order_confirmation_email(
        self,
        email: str,
        order_id: str,
        total_amount: float,
        products: List[dict],
        customer_name: Optional[str] = None,
        shipping_address: Optional[dict] = None,
    ) -> dict:
        """
        Send order confirmation email.

        Args:
            email: Customer email
            order_id: Order reference (Stripe session ID)
            total_amount: Total order amount in PLN
            products: List of products with name, price, quantity
            customer_name: Customer name
            shipping_address: Shipping address dict

        Returns:
            dict with 'success' boolean
        """
        template_id = getattr(settings, "BREVO_THANK_YOU_TEMPLATE_ID", None)

        if template_id:
            return self.send_email(
                to_email=email,
                to_name=customer_name,
                subject="Potwierdzenie zamówienia",
                template_id=template_id,
                params={
                    "order_id": order_id,
                    "total_amount": f"{total_amount:.2f} PLN",
                    "products": products,
                    "customer_name": customer_name or "",
                    "shipping_address": shipping_address or {},
                },
            )
        else:
            # Build product list HTML
            products_html = ""
            for p in products:
                products_html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{p.get('name', '')}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{p.get('quantity', 1)}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{p.get('price', 0):.2f} PLN</td>
                </tr>
                """

            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Dziękujemy za zamówienie!</h2>
                <p>Cześć{f" {customer_name}" if customer_name else ""},</p>
                <p>Twoje zamówienie zostało przyjęte. Numer zamówienia: <strong>{order_id}</strong></p>

                <h3>Zamówione produkty:</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background-color: #f5f5f5;">
                        <th style="padding: 8px; text-align: left;">Produkt</th>
                        <th style="padding: 8px; text-align: left;">Ilość</th>
                        <th style="padding: 8px; text-align: left;">Cena</th>
                    </tr>
                    {products_html}
                    <tr>
                        <td colspan="2" style="padding: 8px; text-align: right;"><strong>Suma:</strong></td>
                        <td style="padding: 8px;"><strong>{total_amount:.2f} PLN</strong></td>
                    </tr>
                </table>

                <p>Otrzymasz kolejny email z numerem przesyłki, gdy zamówienie zostanie wysłane.</p>
                <p>Pozdrawiamy,<br>Z Głową w Piórach</p>
            </body>
            </html>
            """

            return self.send_email(
                to_email=email,
                to_name=customer_name,
                subject=f"Potwierdzenie zamówienia {order_id}",
                html_content=html_content,
            )
