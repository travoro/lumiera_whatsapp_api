"""Dynamic Template Service for WhatsApp Interactive Content.

This service creates templates on-the-fly, uses them, and deletes them automatically
to avoid piling up templates in Twilio. Supports all WhatsApp interactive content types
with full emoji support.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from src.config import settings
from src.integrations.supabase import supabase_client
from src.services.retry import retry_on_network_error
from src.utils.logger import log


class DynamicTemplateService:
    """Service for creating, using, and deleting WhatsApp templates on-the-fly."""

    def __init__(self):
        """Initialize dynamic template service."""
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self.stats = {
            "created": 0,
            "sent": 0,
            "deleted": 0,
            "failed_deletions": 0,
            "total_time_ms": 0,
        }
        log.info("Dynamic template service initialized")

    # ============================================================================
    # CORE TEMPLATE LIFECYCLE METHODS
    # ============================================================================

    @retry_on_network_error(max_attempts=3)
    def create_dynamic_template(
        self, content_type: str, content_data: Dict[str, Any], language: str = "en"
    ) -> Optional[str]:
        """Base method for creating any template type.

        Args:
            content_type: Type of content (twilio/list-picker, twilio/quick-reply, etc.)
            content_data: Content configuration for the template
            language: Language code (default: en)

        Returns:
            Content SID if successful, None otherwise
        """
        try:
            friendly_name = (
                f"dynamic_{content_type.split('/')[-1]}_{int(time.time() * 1000)}"
            )

            create_start = time.time()

            # Use direct HTTP API (Twilio SDK has issues with Content API in v9.9.0)
            response = requests.post(
                "https://content.twilio.com/v1/Content",
                auth=HTTPBasicAuth(
                    settings.twilio_account_sid, settings.twilio_auth_token
                ),
                json={
                    "friendly_name": friendly_name,
                    "language": language,
                    "types": {content_type: content_data},
                },
                timeout=10,
            )

            create_time = (time.time() - create_start) * 1000

            if response.status_code != 201:
                raise Exception(f"Create failed: {response.text}")

            content_sid = response.json()["sid"]
            self.stats["created"] += 1

            log.info(
                f"✅ Created {content_type} template: {content_sid} ({create_time:.0f}ms)"
            )

            # Log to database
            self.log_template_created(
                content_sid, content_type, friendly_name, language
            )

            return content_sid

        except Exception as e:
            log.error(f"❌ Error creating {content_type} template: {e}")
            return None

    @retry_on_network_error(max_attempts=3)
    def send_with_template(
        self,
        to_number: str,
        content_sid: str,
        content_variables: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Send message using a template.

        Args:
            to_number: Recipient WhatsApp number
            content_sid: Template Content SID
            content_variables: Variables to fill in template

        Returns:
            Message SID if successful, None otherwise
        """
        try:
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            send_start = time.time()
            message = self.client.messages.create(
                from_=f"whatsapp:{settings.twilio_whatsapp_number}",
                to=to_number,
                content_sid=content_sid,
                content_variables=content_variables or {},
            )
            send_time = (time.time() - send_start) * 1000

            message_sid = message.sid
            self.stats["sent"] += 1

            log.info(f"✅ Sent message: {message_sid} ({send_time:.0f}ms)")

            return message_sid

        except Exception as e:
            log.error(f"❌ Error sending message with template {content_sid}: {e}")
            return None

    @retry_on_network_error(max_attempts=3)
    def delete_template(self, content_sid: str) -> bool:
        """Delete template from Twilio.

        Args:
            content_sid: The Content SID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            delete_start = time.time()

            # Use direct HTTP API for consistency
            response = requests.delete(
                f"https://content.twilio.com/v1/Content/{content_sid}",
                auth=HTTPBasicAuth(
                    settings.twilio_account_sid, settings.twilio_auth_token
                ),
                timeout=10,
            )
            delete_time = (time.time() - delete_start) * 1000

            if response.status_code == 204:
                self.stats["deleted"] += 1
                log.info(f"✅ Deleted template: {content_sid} ({delete_time:.0f}ms)")
                self.log_template_deleted(content_sid, success=True)
                return True
            elif response.status_code == 404:
                # Template already deleted
                log.info(f"ℹ️ Template {content_sid} already deleted")
                self.log_template_deleted(content_sid, success=True)
                return True
            else:
                raise Exception(
                    f"Delete failed: {response.status_code} - {response.text}"
                )

        except Exception as e:
            log.error(f"❌ Error deleting template {content_sid}: {e}")
            self.stats["failed_deletions"] += 1
            self.log_template_deleted(content_sid, success=False, error=str(e))
            return False

    def cleanup_template(self, content_sid: str) -> bool:
        """Delete template and verify in database.

        Args:
            content_sid: The Content SID to delete

        Returns:
            True if successful, False otherwise
        """
        success = self.delete_template(content_sid)

        if success:
            # Verify deletion
            if self.verify_template_deleted(content_sid):
                log.info(f"✅ Template {content_sid} verified deleted")
                return True
            else:
                log.warning(
                    f"⚠️ Template {content_sid} deleted but still exists in Twilio"
                )
                return False

        return False

    def get_template_usage_stats(self, content_sid: str) -> Dict[str, Any]:
        """Track template usage before deletion.

        Args:
            content_sid: The Content SID

        Returns:
            Usage statistics dict
        """
        try:
            # Get template info from database
            result = (
                supabase_client.client.table("templates")
                .select("*")
                .eq("twilio_content_sid", content_sid)
                .execute()
            )

            if result.data:
                template_data = result.data[0]
                created_at = datetime.fromisoformat(
                    template_data["created_at"].replace("Z", "+00:00")
                )

                return {
                    "content_sid": content_sid,
                    "created_at": created_at,
                    "age_seconds": (
                        datetime.now(created_at.tzinfo) - created_at
                    ).total_seconds(),
                    "template_type": template_data.get("template_type", "unknown"),
                    "template_name": template_data.get("template_name", "unknown"),
                    "is_active": template_data.get("is_active", False),
                }

            return {"content_sid": content_sid, "found": False}

        except Exception as e:
            log.error(f"❌ Error getting template stats for {content_sid}: {e}")
            return {"content_sid": content_sid, "error": str(e)}

    # ============================================================================
    # LIST PICKER METHODS (twilio/list-picker)
    # ============================================================================

    def validate_list_items(
        self, items: List[Dict[str, str]]
    ) -> Tuple[bool, Optional[str]]:
        """Validate list items.

        Args:
            items: List items to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not items or len(items) > 10:
            return False, f"Items must be 1-10, got {len(items)}"

        for i, item in enumerate(items):
            # Check required fields
            if "item" not in item or "id" not in item:
                return False, f"Item {i} missing 'item' or 'id' field"

            # Check item text length (max 24 chars)
            if len(item["item"]) > 24:
                return (
                    False,
                    f"Item {i} text '{item['item']}' exceeds 24 chars (length: {len(item['item'])})",
                )

            # Check description length if present (max 72 chars recommended)
            if "description" in item and len(item["description"]) > 72:
                return (
                    False,
                    f"Item {i} description exceeds 72 chars (length: {len(item['description'])})",
                )

        return True, None

    def create_list_picker(
        self,
        body_text: str,
        button_text: str,
        items: List[Dict[str, str]],
        language: str = "en",
    ) -> Optional[str]:
        """Create list picker with up to 10 items + emojis.

        Args:
            body_text: Message body text (can include emojis)
            button_text: Button text (max 20 chars, can include emojis)
            items: List items (max 10), each with:
                   - item: Display text (max 24 chars, can include emojis)
                   - id: Unique identifier
                   - description: Optional description (max 72 chars)
            language: Language code

        Returns:
            Content SID if successful, None otherwise
        """
        # Validate items
        is_valid, error = self.validate_list_items(items)
        if not is_valid:
            log.error(f"❌ Invalid list items: {error}")
            return None

        # Truncate button text if needed
        button_text = self.truncate_with_emoji(button_text, 20)

        content_data = {
            "body": body_text,
            "button": button_text,
            "items": items[:10],  # Max 10 items
        }

        return self.create_dynamic_template(
            "twilio/list-picker", content_data, language
        )

    def send_list_picker(
        self,
        to_number: str,
        body_text: str,
        button_text: str,
        items: List[Dict[str, str]],
        cleanup: bool = True,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Full workflow: create → send → delete list picker.

        Args:
            to_number: Recipient WhatsApp number
            body_text: Message body
            button_text: Button text
            items: List items
            cleanup: Delete template after sending (default: True)
            language: Language code

        Returns:
            Result dict with success status and IDs
        """
        workflow_start = time.time()

        # Create template
        content_sid = self.create_list_picker(body_text, button_text, items, language)
        if not content_sid:
            return {"success": False, "error": "Failed to create template"}

        # Send message
        message_sid = self.send_with_template(to_number, content_sid)
        if not message_sid:
            # Failed to send, cleanup template
            self.delete_template(content_sid)
            return {"success": False, "error": "Failed to send message"}

        # Cleanup if requested
        if cleanup:
            self.schedule_deletion(content_sid, delay_seconds=2)

        total_time = (time.time() - workflow_start) * 1000
        self.stats["total_time_ms"] += total_time

        return {
            "success": True,
            "content_sid": content_sid,
            "message_sid": message_sid,
            "total_ms": total_time,
        }

    # ============================================================================
    # QUICK REPLY METHODS (twilio/quick-reply)
    # ============================================================================

    def validate_quick_reply_buttons(
        self, buttons: List[Dict[str, str]]
    ) -> Tuple[bool, Optional[str]]:
        """Validate quick reply buttons.

        Args:
            buttons: Quick reply buttons to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not buttons or len(buttons) > 3:
            return False, f"Buttons must be 1-3, got {len(buttons)}"

        for i, button in enumerate(buttons):
            if "text" not in button or "id" not in button:
                return False, f"Button {i} missing 'text' or 'id' field"

            if len(button["text"]) > 20:
                return (
                    False,
                    f"Button {i} text '{button['text']}' exceeds 20 chars (length: {len(button['text'])})",
                )

        return True, None

    def create_quick_reply(
        self, body_text: str, buttons: List[Dict[str, str]], language: str = "en"
    ) -> Optional[str]:
        """Create quick reply with up to 3 buttons + emojis.

        Args:
            body_text: Message body text (can include emojis)
            buttons: Quick reply buttons (max 3), each with:
                     - text: Button text (max 20 chars, can include emojis)
                     - id: Unique identifier
            language: Language code

        Returns:
            Content SID if successful, None otherwise
        """
        # Validate buttons
        is_valid, error = self.validate_quick_reply_buttons(buttons)
        if not is_valid:
            log.error(f"❌ Invalid quick reply buttons: {error}")
            return None

        # Truncate button texts if needed
        formatted_buttons = []
        for button in buttons[:3]:
            formatted_buttons.append(
                {
                    "text": self.truncate_with_emoji(button["text"], 20),
                    "id": button["id"],
                }
            )

        content_data = {"body": body_text, "actions": formatted_buttons}

        return self.create_dynamic_template(
            "twilio/quick-reply", content_data, language
        )

    def send_quick_reply(
        self,
        to_number: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        cleanup: bool = True,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Full workflow: create → send → delete quick reply.

        Args:
            to_number: Recipient WhatsApp number
            body_text: Message body
            buttons: Quick reply buttons
            cleanup: Delete template after sending (default: True)
            language: Language code

        Returns:
            Result dict with success status and IDs
        """
        workflow_start = time.time()

        content_sid = self.create_quick_reply(body_text, buttons, language)
        if not content_sid:
            return {"success": False, "error": "Failed to create template"}

        message_sid = self.send_with_template(to_number, content_sid)
        if not message_sid:
            self.delete_template(content_sid)
            return {"success": False, "error": "Failed to send message"}

        if cleanup:
            self.schedule_deletion(content_sid, delay_seconds=2)

        total_time = (time.time() - workflow_start) * 1000

        return {
            "success": True,
            "content_sid": content_sid,
            "message_sid": message_sid,
            "total_ms": total_time,
        }

    # ============================================================================
    # CALL-TO-ACTION METHODS (twilio/call-to-action)
    # ============================================================================

    def validate_cta_buttons(
        self, buttons: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        """Validate CTA buttons.

        Args:
            buttons: CTA buttons to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not buttons or len(buttons) > 2:
            return False, f"CTA buttons must be 1-2, got {len(buttons)}"

        for i, button in enumerate(buttons):
            if "text" not in button or "type" not in button:
                return False, f"Button {i} missing 'text' or 'type' field"

            button_type = button["type"]
            if button_type not in ["PHONE_NUMBER", "URL"]:
                return (
                    False,
                    f"Button {i} invalid type '{button_type}', must be PHONE_NUMBER or URL",
                )

            if button_type == "PHONE_NUMBER" and "phone_number" not in button:
                return (
                    False,
                    f"Button {i} type PHONE_NUMBER missing 'phone_number' field",
                )

            if button_type == "URL" and "url" not in button:
                return False, f"Button {i} type URL missing 'url' field"

        return True, None

    def create_call_to_action(
        self, body_text: str, buttons: List[Dict[str, Any]], language: str = "en"
    ) -> Optional[str]:
        """Create call-to-action with phone/URL buttons + emojis.

        Args:
            body_text: Message body text (can include emojis)
            buttons: CTA buttons (max 2), each with:
                     - text: Button text (can include emojis)
                     - type: 'PHONE_NUMBER' or 'URL'
                     - phone_number: Phone number (if type is PHONE_NUMBER)
                     - url: URL (if type is URL)
            language: Language code

        Returns:
            Content SID if successful, None otherwise
        """
        # Validate buttons
        is_valid, error = self.validate_cta_buttons(buttons)
        if not is_valid:
            log.error(f"❌ Invalid CTA buttons: {error}")
            return None

        content_data = {"body": body_text, "actions": buttons[:2]}

        return self.create_dynamic_template(
            "twilio/call-to-action", content_data, language
        )

    def send_call_to_action(
        self,
        to_number: str,
        body_text: str,
        buttons: List[Dict[str, Any]],
        cleanup: bool = True,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Full workflow: create → send → delete call-to-action.

        Args:
            to_number: Recipient WhatsApp number
            body_text: Message body
            buttons: CTA buttons
            cleanup: Delete template after sending (default: True)
            language: Language code

        Returns:
            Result dict with success status and IDs
        """
        workflow_start = time.time()

        content_sid = self.create_call_to_action(body_text, buttons, language)
        if not content_sid:
            return {"success": False, "error": "Failed to create template"}

        message_sid = self.send_with_template(to_number, content_sid)
        if not message_sid:
            self.delete_template(content_sid)
            return {"success": False, "error": "Failed to send message"}

        if cleanup:
            self.schedule_deletion(content_sid, delay_seconds=2)

        total_time = (time.time() - workflow_start) * 1000

        return {
            "success": True,
            "content_sid": content_sid,
            "message_sid": message_sid,
            "total_ms": total_time,
        }

    # ============================================================================
    # MEDIA METHODS (twilio/media)
    # ============================================================================

    def create_media_template(
        self, body_text: str, media_url: str, language: str = "en"
    ) -> Optional[str]:
        """Create media template with image/video/document + emojis.

        Args:
            body_text: Message body text (can include emojis)
            media_url: URL to media file
            language: Language code

        Returns:
            Content SID if successful, None otherwise
        """
        content_data = {"body": body_text, "media": [media_url]}

        return self.create_dynamic_template("twilio/media", content_data, language)

    def send_media_message(
        self,
        to_number: str,
        body_text: str,
        media_url: str,
        cleanup: bool = True,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Full workflow: create → send → delete media message.

        Args:
            to_number: Recipient WhatsApp number
            body_text: Message body
            media_url: URL to media file
            cleanup: Delete template after sending (default: True)
            language: Language code

        Returns:
            Result dict with success status and IDs
        """
        workflow_start = time.time()

        content_sid = self.create_media_template(body_text, media_url, language)
        if not content_sid:
            return {"success": False, "error": "Failed to create template"}

        message_sid = self.send_with_template(to_number, content_sid)
        if not message_sid:
            self.delete_template(content_sid)
            return {"success": False, "error": "Failed to send message"}

        if cleanup:
            self.schedule_deletion(content_sid, delay_seconds=2)

        total_time = (time.time() - workflow_start) * 1000

        return {
            "success": True,
            "content_sid": content_sid,
            "message_sid": message_sid,
            "total_ms": total_time,
        }

    # ============================================================================
    # CARD METHODS (twilio/card)
    # ============================================================================

    def create_card(
        self,
        body_text: str,
        media_url: Optional[str] = None,
        buttons: Optional[List[Dict[str, Any]]] = None,
        language: str = "en",
    ) -> Optional[str]:
        """Create rich card with media + buttons + emojis.

        Args:
            body_text: Card body text (can include emojis)
            media_url: Optional media URL
            buttons: Optional buttons (max 3)
            language: Language code

        Returns:
            Content SID if successful, None otherwise
        """
        content_data = {"body": body_text}

        if media_url:
            content_data["media"] = [media_url]

        if buttons:
            content_data["actions"] = buttons[:3]

        return self.create_dynamic_template("twilio/card", content_data, language)

    def send_card(
        self,
        to_number: str,
        body_text: str,
        media_url: Optional[str] = None,
        buttons: Optional[List[Dict[str, Any]]] = None,
        cleanup: bool = True,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Full workflow: create → send → delete card.

        Args:
            to_number: Recipient WhatsApp number
            body_text: Card body text
            media_url: Optional media URL
            buttons: Optional buttons
            cleanup: Delete template after sending (default: True)
            language: Language code

        Returns:
            Result dict with success status and IDs
        """
        workflow_start = time.time()

        content_sid = self.create_card(body_text, media_url, buttons, language)
        if not content_sid:
            return {"success": False, "error": "Failed to create template"}

        message_sid = self.send_with_template(to_number, content_sid)
        if not message_sid:
            self.delete_template(content_sid)
            return {"success": False, "error": "Failed to send message"}

        if cleanup:
            self.schedule_deletion(content_sid, delay_seconds=2)

        total_time = (time.time() - workflow_start) * 1000

        return {
            "success": True,
            "content_sid": content_sid,
            "message_sid": message_sid,
            "total_ms": total_time,
        }

    # ============================================================================
    # CAROUSEL METHODS (twilio/carousel)
    # ============================================================================

    def create_carousel(
        self, cards: List[Dict[str, str]], body: str = "", language: str = "en"
    ) -> Optional[str]:
        """Create carousel with up to 10 image cards.

        Args:
            cards: List of cards (max 10), each with:
                   - media_url: URL to image (required)
                   - title: Card title (optional)
                   - body: Card body text (optional)
            body: Intro message text above carousel
            language: Language code

        Returns:
            Content SID if successful, None otherwise
        """
        # Validate cards
        if not cards or len(cards) > 10:
            log.error(
                f"❌ Invalid card count: {len(cards) if cards else 0} (must be 1-10)"
            )
            return None

        # Format cards for Twilio carousel
        formatted_cards = []
        for i, card in enumerate(cards[:10]):
            if not card.get("media_url"):
                log.error(f"❌ Card {i} missing required media_url")
                continue

            card_data = {"media": card.get("media_url")}

            # Optional: Add title/body if provided
            if card.get("title"):
                card_data["title"] = card.get("title")[
                    :160
                ]  # Max 160 chars combined with body
            if card.get("body"):
                card_data["body"] = card.get("body")[:160]

            formatted_cards.append(card_data)

        if not formatted_cards:
            log.error(f"❌ No valid cards after validation")
            return None

        content_data = {"body": body or "Photos", "cards": formatted_cards}

        return self.create_dynamic_template("twilio/carousel", content_data, language)

    def send_carousel(
        self,
        to_number: str,
        cards: List[Dict[str, str]],
        body: str = "",
        cleanup: bool = True,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Full workflow: create → send → delete carousel.

        Args:
            to_number: Recipient WhatsApp number
            cards: List of image cards
            body: Intro message text above carousel
            cleanup: Delete template after sending (default: True)
            language: Language code

        Returns:
            Result dict with success status and IDs
        """
        workflow_start = time.time()

        content_sid = self.create_carousel(cards, body, language)
        if not content_sid:
            return {"success": False, "error": "Failed to create carousel template"}

        message_sid = self.send_with_template(to_number, content_sid)
        if not message_sid:
            self.delete_template(content_sid)
            return {"success": False, "error": "Failed to send carousel"}

        if cleanup:
            self.schedule_deletion(content_sid, delay_seconds=2)

        total_time = (time.time() - workflow_start) * 1000

        return {
            "success": True,
            "content_sid": content_sid,
            "message_sid": message_sid,
            "total_ms": total_time,
        }

    # ============================================================================
    # DATABASE INTEGRATION METHODS
    # ============================================================================

    def log_template_created(
        self,
        content_sid: str,
        template_type: str,
        friendly_name: str,
        language: str = "en",
    ) -> bool:
        """Log template creation to database.

        Args:
            content_sid: Template Content SID
            template_type: Type of template
            friendly_name: Template friendly name
            language: Language code

        Returns:
            True if successful, False otherwise
        """
        try:
            supabase_client.client.table("templates").insert(
                {
                    "template_name": friendly_name,
                    "language": language,
                    "twilio_content_sid": content_sid,
                    "template_type": template_type,
                    "description": f"Dynamic {template_type} template",
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ).execute()

            return True

        except Exception as e:
            log.error(f"❌ Error logging template creation: {e}")
            return False

    def log_template_deleted(
        self, content_sid: str, success: bool, error: Optional[str] = None
    ) -> bool:
        """Log template deletion to database.

        Args:
            content_sid: Template Content SID
            success: Whether deletion was successful
            error: Error message if deletion failed

        Returns:
            True if successful, False otherwise
        """
        try:
            if success:
                # Mark as inactive instead of deleting
                supabase_client.client.table("templates").update(
                    {
                        "is_active": False,
                        "updated_at": datetime.utcnow().isoformat(),
                        "description": f"Deleted at {datetime.utcnow().isoformat()}",
                    }
                ).eq("twilio_content_sid", content_sid).execute()
            else:
                # Log error in description
                error_msg = f"Deletion failed: {error}" if error else "Deletion failed"
                supabase_client.client.table("templates").update(
                    {
                        "description": error_msg,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("twilio_content_sid", content_sid).execute()

            return True

        except Exception as e:
            log.error(f"❌ Error logging template deletion: {e}")
            return False

    def get_pending_deletions(self) -> List[Dict[str, Any]]:
        """Get templates that failed to delete.

        Returns:
            List of templates pending deletion
        """
        try:
            # Get templates where description contains "Deletion failed"
            result = (
                supabase_client.client.table("templates")
                .select("*")
                .like("description", "%Deletion failed%")
                .eq("is_active", True)
                .execute()
            )

            return result.data if result.data else []

        except Exception as e:
            log.error(f"❌ Error getting pending deletions: {e}")
            return []

    def retry_failed_deletions(self) -> Dict[str, int]:
        """Cleanup orphaned templates that failed to delete.

        Returns:
            Dict with retry statistics
        """
        pending = self.get_pending_deletions()

        stats = {"total": len(pending), "success": 0, "failed": 0}

        for template in pending:
            content_sid = template["twilio_content_sid"]
            if self.delete_template(content_sid):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        log.info(
            f"🔄 Retried {stats['total']} failed deletions: {stats['success']} success, {stats['failed']} failed"
        )

        return stats

    def verify_template_deleted(self, content_sid: str) -> bool:
        """Check if template still exists in Twilio.

        Args:
            content_sid: Template Content SID

        Returns:
            True if deleted (not found), False if still exists
        """
        try:
            self.client.content.v1.contents(content_sid).fetch()
            # If fetch succeeds, template still exists
            return False

        except TwilioRestException as e:
            if e.status == 404:
                # Template not found = deleted
                return True
            log.error(f"❌ Error verifying template deletion: {e}")
            return False

        except Exception as e:
            log.error(f"❌ Error verifying template deletion: {e}")
            return False

    # ============================================================================
    # CLEANUP & MAINTENANCE METHODS
    # ============================================================================

    def schedule_deletion(self, content_sid: str, delay_seconds: int = 5) -> None:
        """Schedule template for deletion after a delay.

        Args:
            content_sid: Template Content SID
            delay_seconds: Delay before deletion (default: 5)
        """
        import threading

        def delayed_delete():
            time.sleep(delay_seconds)
            self.delete_template(content_sid)

        thread = threading.Thread(target=delayed_delete, daemon=True)
        thread.start()

        log.info(f"⏱️ Scheduled deletion for {content_sid} in {delay_seconds}s")

    def batch_delete_templates(self, content_sids: List[str]) -> Dict[str, int]:
        """Delete multiple templates at once.

        Args:
            content_sids: List of Content SIDs to delete

        Returns:
            Dict with deletion statistics
        """
        stats = {"total": len(content_sids), "success": 0, "failed": 0}

        for content_sid in content_sids:
            if self.delete_template(content_sid):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        log.info(
            f"🗑️ Batch deleted {stats['total']} templates: {stats['success']} success, {stats['failed']} failed"
        )

        return stats

    def cleanup_orphaned_templates(self) -> Dict[str, int]:
        """Find and delete templates not in database.

        Returns:
            Dict with cleanup statistics
        """
        stats = {"found": 0, "deleted": 0, "failed": 0}

        try:
            # Get all templates from Twilio
            twilio_templates = self.client.content.v1.contents.list(limit=1000)

            # Get all templates from database
            db_result = (
                supabase_client.client.table("templates")
                .select("twilio_content_sid")
                .execute()
            )
            db_sids = {t["twilio_content_sid"] for t in (db_result.data or [])}

            # Find orphaned templates (in Twilio but not in DB)
            for template in twilio_templates:
                if template.sid not in db_sids and template.friendly_name.startswith(
                    "dynamic_"
                ):
                    stats["found"] += 1
                    if self.delete_template(template.sid):
                        stats["deleted"] += 1
                    else:
                        stats["failed"] += 1

            log.info(
                f"🧹 Cleaned up orphaned templates: {stats['deleted']}/{stats['found']} deleted"
            )

            return stats

        except Exception as e:
            log.error(f"❌ Error cleaning up orphaned templates: {e}")
            return stats

    def get_template_age(self, content_sid: str) -> Optional[float]:
        """Check template creation time.

        Args:
            content_sid: Template Content SID

        Returns:
            Age in seconds, None if not found
        """
        try:
            result = (
                supabase_client.client.table("templates")
                .select("created_at")
                .eq("twilio_content_sid", content_sid)
                .execute()
            )

            if result.data:
                created_at = datetime.fromisoformat(
                    result.data[0]["created_at"].replace("Z", "+00:00")
                )
                age = (datetime.now(created_at.tzinfo) - created_at).total_seconds()
                return age

            return None

        except Exception as e:
            log.error(f"❌ Error getting template age: {e}")
            return None

    def delete_expired_templates(self, max_age_hours: int = 24) -> Dict[str, int]:
        """Delete templates older than specified hours.

        Args:
            max_age_hours: Maximum age in hours (default: 24)

        Returns:
            Dict with deletion statistics
        """
        stats = {"found": 0, "deleted": 0, "failed": 0}

        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)

            result = (
                supabase_client.client.table("templates")
                .select("*")
                .eq("is_active", True)
                .lt("created_at", cutoff_time.isoformat())
                .execute()
            )

            expired_templates = result.data or []
            stats["found"] = len(expired_templates)

            for template in expired_templates:
                content_sid = template["twilio_content_sid"]
                if self.delete_template(content_sid):
                    stats["deleted"] += 1
                else:
                    stats["failed"] += 1

            log.info(
                f"⏰ Deleted expired templates (>{max_age_hours}h): {stats['deleted']}/{stats['found']}"
            )

            return stats

        except Exception as e:
            log.error(f"❌ Error deleting expired templates: {e}")
            return stats

    # ============================================================================
    # EMOJI & FORMATTING METHODS
    # ============================================================================

    def add_emoji_to_items(
        self, items: List[Dict[str, str]], emojis: List[str], position: str = "end"
    ) -> List[Dict[str, str]]:
        """Add emojis to list items.

        Args:
            items: List items
            emojis: List of emojis (one per item)
            position: Emoji position ('start', 'end', 'middle')

        Returns:
            Items with emojis added
        """
        result = []

        for i, item in enumerate(items):
            emoji = emojis[i] if i < len(emojis) else ""
            text = item["item"]

            if position == "start":
                new_text = f"{emoji} {text}".strip()
            elif position == "middle":
                words = text.split()
                if len(words) > 1:
                    new_text = f"{words[0]} {emoji} {' '.join(words[1:])}".strip()
                else:
                    new_text = f"{text} {emoji}".strip()
            else:  # end
                new_text = f"{text} {emoji}".strip()

            # Ensure it doesn't exceed 24 chars
            new_text = self.truncate_with_emoji(new_text, 24)

            result.append({**item, "item": new_text})

        return result

    def validate_emoji_length(self, text: str, max_length: int) -> bool:
        """Ensure text with emojis doesn't exceed char limit.

        Args:
            text: Text to validate
            max_length: Maximum allowed length

        Returns:
            True if valid, False otherwise
        """
        return len(text) <= max_length

    def format_text_with_emoji(
        self, text: str, emoji: str, position: str = "end"
    ) -> str:
        """Format text with emoji at specified position.

        Args:
            text: Text to format
            emoji: Emoji to add
            position: Position ('start', 'end', 'middle')

        Returns:
            Formatted text
        """
        if position == "start":
            return f"{emoji} {text}".strip()
        elif position == "middle":
            words = text.split()
            if len(words) > 1:
                return f"{words[0]} {emoji} {' '.join(words[1:])}".strip()
            return f"{text} {emoji}".strip()
        else:  # end
            return f"{text} {emoji}".strip()

    def truncate_with_emoji(self, text: str, max_length: int) -> str:
        """Safely truncate text preserving emojis.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text

        # Simple truncation - emojis are counted as characters
        return text[:max_length].strip()

    # ============================================================================
    # ANALYTICS & MONITORING METHODS
    # ============================================================================

    def track_template_send(
        self, content_sid: str, message_sid: str, to_number: str
    ) -> bool:
        """Log template usage metrics (updates template's updated_at).

        Args:
            content_sid: Template Content SID
            message_sid: Message SID
            to_number: Recipient number

        Returns:
            True if successful, False otherwise
        """
        try:
            # Update template's updated_at to track last usage
            supabase_client.client.table("templates").update(
                {
                    "updated_at": datetime.utcnow().isoformat(),
                    "description": f"Last sent: {datetime.utcnow().isoformat()} to {to_number}",
                }
            ).eq("twilio_content_sid", content_sid).execute()

            return True

        except Exception as e:
            log.error(f"❌ Error tracking template send: {e}")
            return False

    def get_template_stats(self) -> Dict[str, Any]:
        """Get create/send/delete statistics.

        Returns:
            Statistics dict
        """
        return {
            **self.stats,
            "average_time_ms": self.stats["total_time_ms"] / max(self.stats["sent"], 1),
        }

    def calculate_average_lifecycle(self) -> Optional[float]:
        """Calculate average time from create to update (last usage).

        Returns:
            Average lifecycle in seconds, None if no data
        """
        try:
            result = (
                supabase_client.client.table("templates")
                .select("created_at, updated_at")
                .eq("is_active", False)
                .execute()
            )

            if not result.data:
                return None

            total_lifecycle = 0
            count = 0

            for template in result.data:
                if template["created_at"] and template["updated_at"]:
                    created = datetime.fromisoformat(
                        template["created_at"].replace("Z", "+00:00")
                    )
                    updated = datetime.fromisoformat(
                        template["updated_at"].replace("Z", "+00:00")
                    )
                    lifecycle = (updated - created).total_seconds()
                    total_lifecycle += lifecycle
                    count += 1

            if count == 0:
                return None

            return total_lifecycle / count

        except Exception as e:
            log.error(f"❌ Error calculating average lifecycle: {e}")
            return None

    def monitor_template_pile_up(self, threshold: int = 50) -> Dict[str, Any]:
        """Alert if too many templates exist.

        Args:
            threshold: Maximum allowed active templates

        Returns:
            Monitoring result dict
        """
        try:
            result = (
                supabase_client.client.table("templates")
                .select("twilio_content_sid")
                .eq("is_active", True)
                .execute()
            )

            active_count = len(result.data) if result.data else 0

            alert = active_count > threshold

            if alert:
                log.warning(
                    f"⚠️ Template pile-up detected: {active_count} active templates (threshold: {threshold})"
                )

            return {
                "active_count": active_count,
                "threshold": threshold,
                "alert": alert,
                "message": f"{active_count} active templates"
                + (" - THRESHOLD EXCEEDED!" if alert else ""),
            }

        except Exception as e:
            log.error(f"❌ Error monitoring template pile-up: {e}")
            return {"error": str(e)}

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    def generate_unique_template_name(self, content_type: str) -> str:
        """Generate unique template name.

        Args:
            content_type: Type of content

        Returns:
            Unique template name
        """
        timestamp = int(time.time() * 1000)
        return f"dynamic_{content_type}_{timestamp}"

    def estimate_template_cost(self, operations: Dict[str, int]) -> Dict[str, float]:
        """Estimate API call costs.

        Args:
            operations: Dict with operation counts (create, send, delete)

        Returns:
            Cost estimate dict
        """
        # Twilio pricing (approximate)
        costs = {
            "create": 0.00,  # Content API is free
            "send": 0.005,  # WhatsApp message cost
            "delete": 0.00,  # Content API is free
        }

        total = sum(
            operations.get(op, 0) * costs.get(op, 0)
            for op in ["create", "send", "delete"]
        )

        return {
            "operations": operations,
            "cost_per_operation": costs,
            "total_cost_usd": total,
        }

    def validate_session_window(self, to_number: str) -> bool:
        """Ensure 24h session window is active.

        Args:
            to_number: Recipient WhatsApp number

        Returns:
            True if session is active, False otherwise
        """
        # TODO: Implement session window validation
        # This would check the last incoming message from the user
        # and verify it's within 24 hours
        return True


# Global instance
dynamic_template_service = DynamicTemplateService()
