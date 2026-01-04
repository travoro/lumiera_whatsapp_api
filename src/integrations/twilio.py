"""Twilio WhatsApp client for messaging."""
from typing import Optional, List
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from src.config import settings
from src.utils.logger import log


class TwilioClient:
    """Client for sending and receiving WhatsApp messages via Twilio."""

    def __init__(self):
        """Initialize Twilio client."""
        self.client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token
        )
        self.whatsapp_number = settings.twilio_whatsapp_number
        self.validator = RequestValidator(settings.twilio_auth_token)
        log.info("Twilio client initialized")

    def send_message(
        self,
        to: str,
        body: str,
        media_url: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Send WhatsApp message to user."""
        try:
            # Ensure 'to' number is in WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            message_params = {
                "from_": self.whatsapp_number,
                "to": to,
                "body": body,
            }

            if media_url:
                message_params["media_url"] = media_url

            message = self.client.messages.create(**message_params)

            log.info(f"Message sent to {to}, SID: {message.sid}")
            return message.sid
        except Exception as e:
            log.error(f"Error sending message: {e}")
            return None

    def validate_webhook(
        self,
        url: str,
        params: dict,
        signature: str,
    ) -> bool:
        """Validate that webhook request is from Twilio."""
        if not settings.verify_webhook_signature:
            return True

        return self.validator.validate(url, params, signature)


# Global instance
twilio_client = TwilioClient()
