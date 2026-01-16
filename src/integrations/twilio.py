"""Twilio WhatsApp client for messaging."""
from typing import Optional, List, Dict, Any
import json
import requests
import tempfile
import os
from pathlib import Path
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

    def download_and_upload_media(
        self,
        media_url: str,
        content_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """Download media from external URL and save with proper filename.

        This is needed when external URLs (like PlanRadar S3) are protected
        and Twilio can't fetch them directly (error 63019).

        Args:
            media_url: The URL of the media to download
            content_type: Optional content type (e.g., 'application/pdf')
            filename: Optional desired filename (e.g., 'La_plateforme.pdf')

        Returns:
            Local file path if successful, None otherwise
        """
        temp_file_path = None
        try:
            log.info(f"📥 Downloading media from external URL...")
            log.info(f"   URL: {media_url[:100]}...")
            if filename:
                log.info(f"   Target filename: {filename}")

            # Download the file
            response = requests.get(media_url, timeout=30)
            response.raise_for_status()

            file_size = len(response.content)
            log.info(f"   ✅ Downloaded {file_size} bytes ({file_size/1024/1024:.2f} MB)")

            # Determine file extension from content type or URL
            extension = ".bin"  # Default
            if content_type:
                if "pdf" in content_type.lower():
                    extension = ".pdf"
                elif "png" in content_type.lower():
                    extension = ".png"
                elif "jpeg" in content_type.lower() or "jpg" in content_type.lower():
                    extension = ".jpg"
            else:
                # Try to extract from URL
                url_path = media_url.split('?')[0]  # Remove query params
                if url_path.endswith('.pdf'):
                    extension = '.pdf'
                elif url_path.endswith('.png'):
                    extension = '.png'
                elif url_path.endswith('.jpg') or url_path.endswith('.jpeg'):
                    extension = '.jpg'

            log.info(f"   📄 File extension: {extension}")

            # Use provided filename or generate temp name
            if filename:
                # Save with a simplified filename to avoid URL encoding issues
                import re
                import hashlib

                # Create a hash of the original filename for uniqueness
                name_hash = hashlib.md5(filename.encode()).hexdigest()[:8]

                # Extract just the base name without path, and limit length
                base_name = os.path.basename(filename)
                # Keep only alphanumeric, hyphens, and underscores
                clean_name = re.sub(r'[^\w\-]', '_', base_name)
                # Remove multiple consecutive underscores
                clean_name = re.sub(r'_+', '_', clean_name)
                # Remove leading/trailing underscores
                clean_name = clean_name.strip('_')
                # Limit length to 50 chars (excluding extension)
                if len(clean_name) > 50:
                    clean_name = clean_name[:50]

                # Create final filename: cleanname_hash.ext
                safe_filename = f"{clean_name}_{name_hash}{extension}"

                temp_file_path = os.path.join(tempfile.gettempdir(), safe_filename)
                log.info(f"   🏷️ Sanitized filename: {filename} → {safe_filename}")
            else:
                # Save to temporary file with auto-generated name
                with tempfile.NamedTemporaryFile(mode='wb', suffix=extension, delete=False) as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
                    log.info(f"   💾 Saved to temporary file: {temp_file_path}")
                    return temp_file_path

            # Write content to the named file
            with open(temp_file_path, 'wb') as f:
                f.write(response.content)

            log.info(f"   💾 Saved to: {temp_file_path}")
            log.info(f"   ✅ File ready with correct filename")

            return temp_file_path

        except Exception as e:
            log.error(f"   ❌ Error downloading/uploading media: {e}")
            # Clean up temp file if it was created
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    log.info(f"   🗑️ Cleaned up temp file after error")
                except Exception as cleanup_error:
                    log.warning(f"   ⚠️ Could not clean up temp file: {cleanup_error}")
            return None

    def send_message_with_local_media(
        self,
        to: str,
        body: str,
        local_file_path: str,
        server_url: str,
    ) -> Optional[str]:
        """Send WhatsApp message with a local file attachment via temporary hosting.

        Args:
            to: Recipient phone number
            body: Message body text
            local_file_path: Path to local file to send
            server_url: Base URL of this server (e.g., https://api.example.com)

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

            log.info(f"📤 Sending message with local file via temporary hosting")
            log.info(f"   To: {to}")
            log.info(f"   File: {local_file_path}")
            log.info(f"   Size: {os.path.getsize(local_file_path)} bytes")

            # Register the file for temporary hosting
            from src.handlers.media import register_temp_file
            temp_url_path = register_temp_file(local_file_path)

            # Build full URL
            media_url = f"{server_url}{temp_url_path}"
            log.info(f"   📡 Temporary URL: {media_url}")

            # Send message with media URL
            message = self.client.messages.create(
                from_=from_number,
                to=to,
                body=body,
                media_url=[media_url]
            )

            log.info(f"   ✅ Message sent with temp hosted file, SID: {message.sid}")
            return message.sid

        except Exception as e:
            log.error(f"   ❌ Error sending message with local media: {e}")
            import traceback
            log.error(f"   Traceback: {traceback.format_exc()}")
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
