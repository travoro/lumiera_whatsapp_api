"""Template manager for creating dynamic WhatsApp list-picker templates."""

from typing import Any, Dict, List, Optional

from twilio.rest import Client

from src.config import settings
from src.integrations.supabase import supabase_client
from src.utils.logger import log


class TemplateManager:
    """Manages dynamic creation and caching of WhatsApp list-picker templates."""

    def __init__(self):
        """Initialize template manager."""
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        # Cache for template SIDs: {language: {template_name: sid}}
        self.template_cache: Dict[str, Dict[str, str]] = {}
        log.info("Template manager initialized")

    def create_list_picker_template(
        self,
        template_name: str,
        language: str,
        greeting_text: str,
        button_text: str,
        items: List[Dict[str, str]],
    ) -> Optional[str]:
        """Create a list-picker template for a specific language.

        Args:
            template_name: Unique name for the template (e.g., "main_menu")
            language: Language code (e.g., "en", "fr", "es")
            greeting_text: Greeting text with {{1}} placeholder for name
            button_text: Button text (e.g., "Choose an option")
            items: List of items with 'title' and 'description'

        Returns:
            Content SID if successful, None otherwise
        """
        try:
            # Check cache first
            cache_key = f"{template_name}_{language}"
            if (
                language in self.template_cache
                and template_name in self.template_cache[language]
            ):
                cached_sid = self.template_cache[language][template_name]
                log.info(f"Using cached template: {cache_key} (SID: {cached_sid})")
                return cached_sid

            # Prepare template structure for list-picker
            friendly_name = f"{template_name}_{language}"

            # Build list items (max 10)
            template_items = []
            for idx, item in enumerate(items[:10]):
                template_items.append(
                    {
                        "item": f"{{{{{idx*3 + 2}}}}}",  # {{2}}, {{5}}, {{8}}, etc.
                        "id": f"{{{{{idx*3 + 3}}}}}",  # {{3}}, {{6}}, {{9}}, etc.
                        "description": f"{{{{{idx*3 + 4}}}}}",  # {{4}}, {{7}}, {{10}}, etc.
                    }
                )

            # Create template via Content API
            content_types = {
                "twilio/list-picker": {
                    "body": greeting_text,  # Must have {{1}} for name
                    "button": button_text,
                    "items": template_items,
                }
            }

            log.info(f"Creating list-picker template: {friendly_name}")
            log.info(f"Greeting: {greeting_text}")
            log.info(f"Button: {button_text}")
            log.info(f"Items: {len(template_items)}")

            # Create the content template
            content = self.client.content.v1.contents.create(
                friendly_name=friendly_name, language=language, types=content_types
            )

            content_sid = content.sid
            log.info(f"✅ Created template {friendly_name}: {content_sid}")

            # Cache the SID
            if language not in self.template_cache:
                self.template_cache[language] = {}
            self.template_cache[language][template_name] = content_sid

            return content_sid

        except Exception as e:
            log.error(f"❌ Error creating template {template_name}_{language}: {e}")
            log.error(f"Error type: {type(e).__name__}")
            return None

    def get_or_create_main_menu_template(self, language: str) -> Optional[str]:
        """Get or create the main menu template for a language.

        Args:
            language: Language code (e.g., "en", "fr", "es")

        Returns:
            Content SID if successful, None otherwise
        """
        # Define greeting texts for different languages
        greetings = {
            "fr": "Bonjour {{1}} ! Comment puis-je vous aider ?",
            "en": "Hello {{1}}! How can I help you?",
            "es": "Hola {{1}}! ¿Cómo puedo ayudarte?",
            "pt": "Olá {{1}}! Como posso ajudá-lo?",
            "de": "Hallo {{1}}! Wie kann ich Ihnen helfen?",
            "it": "Ciao {{1}}! Come posso aiutarti?",
            "ro": "Bună {{1}}! Cum te pot ajuta?",
            "pl": "Cześć {{1}}! Jak mogę Ci pomóc?",
            "ar": "مرحبا {{1}}! كيف يمكنني مساعدتك؟",
        }

        button_texts = {
            "fr": "Choisir une option",
            "en": "Choose an option",
            "es": "Elegir una opción",
            "pt": "Escolher uma opção",
            "de": "Option wählen",
            "it": "Scegli un'opzione",
            "ro": "Alege o opțiune",
            "pl": "Wybierz opcję",
            "ar": "اختر خيار",
        }

        # Use English as fallback
        greeting = greetings.get(language, greetings["en"])
        button_text = button_texts.get(language, button_texts["en"])

        # Define 6 menu items (structure only - content filled at send time)
        items = [
            {"title": "Item 1", "description": "Description 1"},
            {"title": "Item 2", "description": "Description 2"},
            {"title": "Item 3", "description": "Description 3"},
            {"title": "Item 4", "description": "Description 4"},
            {"title": "Item 5", "description": "Description 5"},
            {"title": "Item 6", "description": "Description 6"},
        ]

        return self.create_list_picker_template(
            template_name="main_menu",
            language=language,
            greeting_text=greeting,
            button_text=button_text,
            items=items,
        )

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

            # Remove from cache
            for lang in self.template_cache:
                self.template_cache[lang] = {
                    k: v
                    for k, v in self.template_cache[lang].items()
                    if v != content_sid
                }

            return True
        except Exception as e:
            log.error(f"❌ Error deleting template {content_sid}: {e}")
            return False

    def get_template_from_database(
        self, template_name: str, language: str = "all"
    ) -> Optional[str]:
        """Fetch template SID from database.

        Args:
            template_name: Template name (e.g., "greeting_menu")
            language: Language code (e.g., "fr", "en", "es") or "all" for universal template

        Returns:
            Content SID if found, None otherwise
        """
        try:
            # Check cache first
            cache_key = f"{template_name}_{language}"
            if (
                language in self.template_cache
                and template_name in self.template_cache[language]
            ):
                cached_sid = self.template_cache[language][template_name]
                log.info(
                    f"Using cached template from memory: {cache_key} (SID: {cached_sid})"
                )
                return cached_sid

            # Query database - try specific language first, then fallback to "all"
            # Note: Using direct client access here because this method is called synchronously during initialization
            result = (
                supabase_client.client.table("templates")
                .select("twilio_content_sid")
                .eq("template_name", template_name)
                .eq("language", language)
                .eq("is_active", True)
                .single()
                .execute()
            )

            if not result.data and language != "all":
                # Fallback to universal template
                log.info(
                    f"Language-specific template not found, trying universal template"
                )
                result = (
                    supabase_client.client.table("templates")
                    .select("twilio_content_sid")
                    .eq("template_name", template_name)
                    .eq("language", "all")
                    .eq("is_active", True)
                    .single()
                    .execute()
                )

            if result.data:
                content_sid = result.data["twilio_content_sid"]
                log.info(
                    f"Retrieved template from database: {cache_key} (SID: {content_sid})"
                )

                # Cache it
                if language not in self.template_cache:
                    self.template_cache[language] = {}
                self.template_cache[language][template_name] = content_sid

                return content_sid
            else:
                log.warning(
                    f"Template not found in database: {template_name}_{language}"
                )
                return None

        except Exception as e:
            log.error(f"❌ Error fetching template from database: {e}")
            return None


# Global instance
template_manager = TemplateManager()
