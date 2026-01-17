"""Translation service using LLM for high-quality contextual translation."""

from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from src.config import settings
from src.services.retry import retry_on_api_error
from src.utils.logger import log


class TranslationService:
    """Handle translation between user languages and French."""

    def __init__(self):
        """Initialize translation service with selected LLM provider."""
        if settings.llm_provider == "openai":
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",  # Cheaper, faster for translation
                api_key=settings.openai_api_key,
                temperature=0,
                max_tokens=1000,
            )
            log.info("Translation service initialized with OpenAI (gpt-4o-mini)")
        else:
            self.llm = ChatAnthropic(
                model="claude-3-5-haiku-20241022",
                api_key=settings.anthropic_api_key,
                temperature=0,
                max_tokens=1000,
            )
            log.info("Translation service initialized with ChatAnthropic")
        self.default_language = settings.default_language

    @retry_on_api_error(max_attempts=3)
    async def detect_language(self, text: str) -> str:
        """Detect the language of input text with automatic retries."""
        try:
            prompt = """Detect the language of the following text and respond with ONLY the ISO 639-1 language code (e.g., 'en', 'fr', 'es', 'ar', 'pt', 'de', 'it').

Text: {text}

Language code:"""

            # Use LangChain ChatAnthropic for automatic cost tracking
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            language_code = response.content.strip().lower()

            # Validate it's a supported language
            if language_code in settings.supported_languages_list:
                return language_code
            return self.default_language
        except Exception as e:
            log.error(f"Error detecting language: {e}")
            return self.default_language

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
            prompt = """Translate the following text to French. Maintain the tone and context. Respond with ONLY the translated text, nothing else.

Text to translate: {text}

French translation:"""

            # Use LangChain ChatAnthropic for automatic cost tracking
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content.strip()
        except Exception as e:
            log.error(f"Error translating to French: {e}")
            return text  # Return original if translation fails

    @retry_on_api_error(max_attempts=3)
    async def translate_from_french(
        self,
        text: str,
        target_language: str,
    ) -> str:
        """Translate text from French to target language with automatic retries."""
        # If target is French, return as-is (skip translation)
        if target_language == "fr":
            log.debug("Skipping translation - target language is already French")
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

            language_names.get(target_language, target_language)

            prompt = """Translate the following text from French to {target_lang_name}. Maintain the tone and context. Respond with ONLY the translated text, nothing else.

Text to translate: {text}

{target_lang_name} translation:"""

            # Use LangChain ChatAnthropic for automatic cost tracking
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content.strip()
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
