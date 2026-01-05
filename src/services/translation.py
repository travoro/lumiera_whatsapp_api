"""Translation service using Claude for high-quality contextual translation."""
from typing import Optional
from anthropic import Anthropic
from langsmith import traceable
from src.config import settings
from src.utils.logger import log
from src.services.retry import retry_on_api_error, retry_on_rate_limit


class TranslationService:
    """Handle translation between user languages and French."""

    def __init__(self):
        """Initialize translation service with Anthropic client."""
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.default_language = settings.default_language
        log.info("Translation service initialized")

    @traceable(
        name="translation_detect_language",
        run_type="llm",
        metadata={"service": "translation", "operation": "detect_language", "model": "claude-3-5-haiku-20241022"}
    )
    @retry_on_api_error(max_attempts=3)
    async def detect_language(self, text: str) -> str:
        """Detect the language of input text with automatic retries."""
        try:
            prompt = f"""Detect the language of the following text and respond with ONLY the ISO 639-1 language code (e.g., 'en', 'fr', 'es', 'ar', 'pt', 'de', 'it').

Text: {text}

Language code:"""

            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Using Haiku for fast detection
                max_tokens=10,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )

            language_code = message.content[0].text.strip().lower()

            # Validate it's a supported language
            if language_code in settings.supported_languages_list:
                return language_code
            return self.default_language
        except Exception as e:
            log.error(f"Error detecting language: {e}")
            return self.default_language

    @traceable(
        name="translate_to_french",
        run_type="llm",
        metadata={"service": "translation", "operation": "to_french", "model": "claude-3-5-haiku-20241022"}
    )
    @retry_on_api_error(max_attempts=3)
    async def translate_to_french(
        self,
        text: str,
        source_language: Optional[str] = None,
    ) -> str:
        """Translate text from source language to French with automatic retries."""
        # If already in French, return as-is
        if source_language == "fr":
            return text

        try:
            prompt = f"""Translate the following text to French. Maintain the tone and context. Respond with ONLY the translated text, nothing else.

Text to translate: {text}

French translation:"""

            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )

            return message.content[0].text.strip()
        except Exception as e:
            log.error(f"Error translating to French: {e}")
            return text  # Return original if translation fails

    @traceable(
        name="translate_from_french",
        run_type="llm",
        metadata={"service": "translation", "operation": "from_french", "model": "claude-3-5-haiku-20241022"}
    )
    @retry_on_api_error(max_attempts=3)
    async def translate_from_french(
        self,
        text: str,
        target_language: str,
    ) -> str:
        """Translate text from French to target language with automatic retries."""
        # If target is French, return as-is
        if target_language == "fr":
            return text

        try:
            language_names = {
                # Western European
                "en": "English",
                "es": "Spanish",
                "pt": "Portuguese",
                "de": "German",
                "it": "Italian",
                # Eastern European
                "ro": "Romanian",
                "pl": "Polish",
                "cs": "Czech",
                "sk": "Slovak",
                "hu": "Hungarian",
                "bg": "Bulgarian",
                "sr": "Serbian",
                "hr": "Croatian",
                "sl": "Slovenian",
                "uk": "Ukrainian",
                "ru": "Russian",
                "lt": "Lithuanian",
                "lv": "Latvian",
                "et": "Estonian",
                "sq": "Albanian",
                "mk": "Macedonian",
                "bs": "Bosnian",
                # Middle Eastern
                "ar": "Arabic",
            }

            target_lang_name = language_names.get(target_language, target_language)

            prompt = f"""Translate the following text from French to {target_lang_name}. Maintain the tone and context. Respond with ONLY the translated text, nothing else.

Text to translate: {text}

{target_lang_name} translation:"""

            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )

            return message.content[0].text.strip()
        except Exception as e:
            log.error(f"Error translating from French: {e}")
            return text  # Return original if translation fails

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Translate text between any two languages via French."""
        if source_language == target_language:
            return text

        # If neither is French, translate via French
        if source_language != "fr" and target_language != "fr":
            # First translate to French
            french_text = await self.translate_to_french(text, source_language)
            # Then translate to target language
            return await self.translate_from_french(french_text, target_language)
        elif source_language == "fr":
            return await self.translate_from_french(text, target_language)
        else:
            return await self.translate_to_french(text, source_language)


# Global instance
translation_service = TranslationService()
