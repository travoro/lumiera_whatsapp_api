"""Twilio WhatsApp client for messaging."""
from typing import Optional, List, Dict, Any
import json
import requests
from requests.auth import HTTPBasicAuth
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from src.config import settings
from src.utils.logger import log
from src.services.retry import retry_on_network_error


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

    @retry_on_network_error(max_attempts=3)
    def send_message(
        self,
        to: str,
        body: str,
        media_url: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Send WhatsApp message to user with automatic retries on network errors."""
        try:
            # Ensure 'to' number is in WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            # Ensure 'from' number is in WhatsApp format
            from_number = self.whatsapp_number
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            message_params = {
                "from_": from_number,
                "to": to,
                "body": body,
            }

            if media_url:
                message_params["media_url"] = media_url
                log.info(f"📎 Adding {len(media_url)} media URLs to message")
                for idx, url in enumerate(media_url):
                    log.info(f"   Media {idx+1}: {url[:80]}")

            message = self.client.messages.create(**message_params)

            log.info(f"Message sent to {to}, SID: {message.sid}")
            return message.sid
        except Exception as e:
            log.error(f"Error sending message: {e}")
            return None

    @retry_on_network_error(max_attempts=3)
    def send_message_with_content(
        self,
        to: str,
        content_sid: str,
        content_variables: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Send WhatsApp message using a Content Template.

        Args:
            to: Recipient phone number
            content_sid: Content Template SID
            content_variables: Optional variables for template substitution

        Returns:
            Message SID if successful, None otherwise
        """
        try:
            # Ensure 'to' number is in WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            # Ensure 'from' number is in WhatsApp format
            from_number = self.whatsapp_number
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            message_params = {
                "from_": from_number,
                "to": to,
                "content_sid": content_sid,
            }

            if content_variables:
                import json
                message_params["content_variables"] = json.dumps(content_variables)

            log.info(f"📤 Sending message with content_sid: {content_sid}")
            log.info(f"   to: {to}")
            log.info(f"   from: {from_number}")

            message = self.client.messages.create(**message_params)

            log.info(f"✅ Content message sent to {to}, SID: {message.sid}")
            log.info(f"📊 Message status: {message.status}")
            return message.sid
        except Exception as e:
            log.error(f"❌ Error sending content message: {e}")
            log.error(f"Error type: {type(e).__name__}")
            log.error(f"Error details: {str(e)}")
            return None

    @retry_on_network_error(max_attempts=3)
    def send_interactive_list_direct_api(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Send WhatsApp interactive list using direct Twilio REST API.

        The Python SDK doesn't support the 'interactive' parameter yet,
        so we call the Twilio API directly using requests.

        Args:
            to: Recipient phone number
            body: Message body text
            button_text: Text for the list button (e.g., "View options")
            sections: List of sections with rows (WhatsApp format)

        Returns:
            Message SID if successful, None otherwise
        """
        try:
            # Ensure 'to' number is in WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            # Ensure 'from' number is in WhatsApp format
            from_number = self.whatsapp_number
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            # Build the API URL
            url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"

            # Build the interactive structure
            interactive_payload = {
                "type": "list",
                "body": {
                    "text": body
                },
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }

            log.info(f"🚀 Sending interactive list via direct API to {to}")
            log.info(f"📝 Body text ({len(body)} chars): {body[:100]}...")
            log.info(f"📋 Sections: {len(sections)} sections")
            if sections:
                log.info(f"📋 Section 0: {len(sections[0].get('rows', []))} items")
                for idx, row in enumerate(sections[0].get('rows', [])):
                    log.info(f"   - Item {idx+1}: id={row.get('id')}, title={row.get('title')}, desc={row.get('description')}")

            log.info(f"🔧 Interactive payload structure:")
            log.info(f"--- START INTERACTIVE ---")
            log.info(json.dumps(interactive_payload, indent=2))
            log.info(f"--- END INTERACTIVE ---")

            # Send POST request to Twilio API with FORM DATA (not JSON)
            # The interactive parameter must be a JSON string in form data
            response = requests.post(
                url,
                data={
                    "To": to,
                    "From": from_number,
                    "Body": body,  # Fallback text
                    "Interactive": json.dumps(interactive_payload)  # JSON string in form data
                },
                auth=HTTPBasicAuth(
                    settings.twilio_account_sid,
                    settings.twilio_auth_token
                )
            )

            log.info(f"📊 Response status code: {response.status_code}")

            if response.status_code in [200, 201]:
                response_data = response.json()
                message_sid = response_data.get("sid")
                log.info(f"✅ Interactive list sent to {to}, SID: {message_sid}")
                log.info(f"📊 Message status: {response_data.get('status')}")
                log.info(f"📊 Message direction: {response_data.get('direction')}")
                log.info(f"🔗 Check details: https://console.twilio.com/us1/monitor/logs/sms/{message_sid}")
                return message_sid
            else:
                log.error(f"❌ Failed to send interactive list")
                log.error(f"Status code: {response.status_code}")
                log.error(f"Response: {response.text}")
                return None

        except Exception as e:
            log.error(f"❌ Error sending interactive list via direct API: {e}")
            log.error(f"Error type: {type(e).__name__}")
            log.error(f"Error details: {str(e)}")
            return None

    @retry_on_network_error(max_attempts=3)
    def send_interactive_list(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Send WhatsApp interactive list message using Twilio's Programmable Messaging API.

        Args:
            to: Recipient phone number
            body: Message body text
            button_text: Text for the list button (e.g., "View options")
            sections: List of sections with rows (WhatsApp format)

        Returns:
            Message SID if successful, None otherwise
        """
        try:
            # Ensure 'to' number is in WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            # Ensure 'from' number is in WhatsApp format
            from_number = self.whatsapp_number
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            # Build interactive message payload (correct format!)
            interactive_payload = {
                "type": "list",
                "body": {
                    "text": body
                },
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }

            log.info(f"🚀 Attempting to send interactive list to {to}")
            log.info(f"📝 Body text ({len(body)} chars):")
            log.info(f"--- START BODY ---")
            log.info(body)
            log.info(f"--- END BODY ---")
            log.info(f"📋 Sections: {len(sections)} sections")
            if sections:
                log.info(f"📋 Section 0: {len(sections[0].get('rows', []))} items")
                for idx, row in enumerate(sections[0].get('rows', [])):
                    log.info(f"   - Item {idx+1}: id={row.get('id')}, title={row.get('title')}, desc={row.get('description')}")

            log.info(f"🔧 FULL Interactive payload:")
            log.info(f"--- START INTERACTIVE ---")
            log.info(json.dumps(interactive_payload, indent=2))
            log.info(f"--- END INTERACTIVE ---")

            log.info(f"📤 Twilio API call parameters:")
            log.info(f"   from_: {from_number}")
            log.info(f"   to: {to}")
            log.info(f"   interactive: {interactive_payload['type']}")

            # Send message with interactive parameter (CORRECT!)
            message = self.client.messages.create(
                from_=from_number,
                to=to,
                interactive=interactive_payload
            )

            log.info(f"✅ Interactive list sent to {to}, SID: {message.sid}")
            log.info(f"📊 Message status: {message.status}")
            log.info(f"📊 Message direction: {message.direction}")
            log.info(f"📊 Message price: {message.price}")
            log.info(f"📊 Message error_code: {message.error_code}")
            log.info(f"📊 Message error_message: {message.error_message}")
            log.info(f"🔗 Check full details: https://console.twilio.com/us1/monitor/logs/sms/{message.sid}")

            # Fetch the message again to see if status changed
            try:
                fetched = self.client.messages(message.sid).fetch()
                log.info(f"📊 Fetched status: {fetched.status}")
                if fetched.error_code:
                    log.error(f"⚠️ Twilio error code: {fetched.error_code}")
                if fetched.error_message:
                    log.error(f"⚠️ Twilio error message: {fetched.error_message}")
            except Exception as fetch_error:
                log.warning(f"Could not fetch message details: {fetch_error}")

            return message.sid
        except Exception as e:
            log.error(f"❌ Error sending interactive list: {e}")
            log.error(f"Error type: {type(e).__name__}")
            log.error(f"Error details: {str(e)}")
            log.warning("Interactive lists may not be supported on your Twilio account tier")
            return None

    @retry_on_network_error(max_attempts=3)
    def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: List[Dict[str, str]],
    ) -> Optional[str]:
        """Send WhatsApp interactive button message (up to 3 buttons).

        Args:
            to: Recipient phone number
            body: Message body text
            buttons: List of buttons with 'id' and 'title' keys

        Returns:
            Message SID if successful, None otherwise
        """
        try:
            # Ensure 'to' number is in WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            # Ensure 'from' number is in WhatsApp format
            from_number = self.whatsapp_number
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            # Build persistent action for interactive buttons
            persistent_action = [
                json.dumps({
                    "type": "button",
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn["id"],
                                "title": btn["title"]
                            }
                        }
                        for btn in buttons[:3]  # Max 3 buttons
                    ]
                })
            ]

            # Send message with persistent action (interactive buttons)
            message = self.client.messages.create(
                from_=from_number,
                to=to,
                body=body,
                persistent_action=persistent_action
            )

            log.info(f"Interactive buttons sent to {to}, SID: {message.sid}")
            return message.sid
        except Exception as e:
            log.error(f"Error sending interactive buttons: {e}")
            log.warning("Interactive buttons may not be supported on your Twilio account tier")
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
