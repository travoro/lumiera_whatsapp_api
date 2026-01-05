"""Twilio Content API client for creating interactive message templates."""
from typing import Optional, List, Dict, Any
import hashlib
import json
from twilio.rest import Client
from src.config import settings
from src.utils.logger import log
from src.services.retry import retry_on_network_error


class TwilioContentClient:
    """Client for managing Twilio Content API templates."""

    def __init__(self):
        """Initialize Twilio Content API client."""
        self.client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token
        )
        log.info("Twilio Content API client initialized")

    def _generate_template_name(self, items: List[Dict[str, Any]]) -> str:
        """Generate a unique template name based on list items.

        Args:
            items: List of items for the list picker

        Returns:
            Unique template name
        """
        # Create a hash of the items to generate unique but consistent name
        items_str = json.dumps(items, sort_keys=True)
        hash_suffix = hashlib.md5(items_str.encode()).hexdigest()[:8]
        return f"list_picker_{hash_suffix}"

    @retry_on_network_error(max_attempts=3)
    def create_list_picker_template(
        self,
        body_text: str,
        button_text: str,
        items: List[Dict[str, str]],
        variables: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Create a list-picker content template dynamically.

        Args:
            body_text: Main message text (can include {{1}}, {{2}} for variables)
            button_text: Text for the list button
            items: List of dicts with 'id', 'item', and optional 'description'
            variables: Optional default values for template variables

        Returns:
            Content SID if successful, None otherwise
        """
        try:
            # Generate unique friendly name
            friendly_name = self._generate_template_name(items)

            # Check if template already exists by searching
            existing_templates = self.client.content.v1.contents.list(limit=100)
            for template in existing_templates:
                if template.friendly_name == friendly_name:
                    log.info(f"♻️ Reusing existing template: {friendly_name} (SID: {template.sid})")
                    return template.sid

            # Prepare items in correct format
            formatted_items = []
            for item_data in items[:10]:  # WhatsApp limit: 10 items
                formatted_item = {
                    "id": item_data.get("id", ""),
                    "item": item_data.get("item", item_data.get("title", ""))[:24],  # Max 24 chars
                }
                if "description" in item_data and item_data["description"]:
                    formatted_item["description"] = item_data["description"][:72]  # Max 72 chars
                formatted_items.append(formatted_item)

            # Build template structure
            template_types = {
                "twilio/list-picker": {
                    "body": body_text,
                    "button": button_text[:20],  # Max 20 chars for button
                    "items": formatted_items
                }
            }

            # Add text fallback for non-WhatsApp channels
            template_types["twilio/text"] = {
                "body": body_text
            }

            log.info(f"🏗️ Creating new list-picker template: {friendly_name}")
            log.info(f"📝 Body: {body_text[:100]}...")
            log.info(f"📋 Items count: {len(formatted_items)}")

            # Create content template
            content = self.client.content.v1.contents.create(
                friendly_name=friendly_name,
                language="fr",  # French as primary language
                variables=variables or {},
                types=template_types
            )

            log.info(f"✅ Created template SID: {content.sid}")
            return content.sid

        except Exception as e:
            log.error(f"❌ Error creating list-picker template: {e}")
            log.error(f"Error type: {type(e).__name__}")
            log.error(f"Error details: {str(e)}")
            return None

    @retry_on_network_error(max_attempts=3)
    def delete_template(self, content_sid: str) -> bool:
        """Delete a content template.

        Args:
            content_sid: The Content SID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.content.v1.contents(content_sid).delete()
            log.info(f"🗑️ Deleted template: {content_sid}")
            return True
        except Exception as e:
            log.error(f"❌ Error deleting template {content_sid}: {e}")
            return False


# Global instance
twilio_content_client = TwilioContentClient()
