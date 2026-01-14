"""Language detection service using LLM."""
from typing import Optional, Tuple
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from src.config import settings
from src.utils.logger import log


class LanguageDetectionService:
    """Language detection using LLM."""

    def __init__(self):
        """Initialize language detection service with selected LLM provider."""
        if settings.llm_provider == "openai":
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=settings.openai_api_key,
                temperature=0,
                max_tokens=10
            )
            log.info("Language detection service initialized with OpenAI")
        else:
            self.llm = ChatAnthropic(
                model="claude-3-5-haiku-20241022",
                api_key=settings.anthropic_api_key,
                temperature=0,
                max_tokens=10
            )
            log.info("Language detection service initialized with Claude AI")

    async def detect_with_claude(self, text: str) -> Optional[str]:
        """Detect language using Claude AI (most accurate method).

        Args:
            text: Text to detect language from

        Returns:
            ISO 639-1 language code or None if detection fails
        """
        try:
            prompt = f"""Detect the language of the following text and respond with ONLY the ISO 639-1 language code (e.g., 'en', 'fr', 'es', 'ro', 'pt', 'de', 'it', 'ar').

Text: {text}

Language code:"""

            # Use LangChain ChatAnthropic for automatic cost tracking
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            language_code = response.content.strip().lower()

            # Validate it's a supported language
            if language_code in settings.supported_languages_list:
                log.info(f"🤖 Claude AI detected language: {language_code}")
                return language_code
            else:
                log.warning(
                    f"⚠️ Claude returned unsupported language code: '{language_code}' "
                    f"(supported: {', '.join(settings.supported_languages_list)})"
                )
                return None

        except Exception as e:
            log.error(f"❌ Claude language detection error: {str(e)}")
            return None

    async def detect_async(self, text: str, fallback_language: str = 'fr') -> Tuple[str, str]:
        """Detect language using Claude AI.

        Strategy:
        1. Try Claude AI (accurate for all languages including Romanian)
        2. If Claude fails: Use fallback language

        Args:
            text: Text to detect language from
            fallback_language: Language to use if detection fails

        Returns:
            Tuple of (detected language, detection method)
            Method can be: 'claude' or 'fallback'
        """
        if not text or len(text.strip()) < 2:
            log.info(f"⏩ Text too short for detection ({len(text)} chars) → Using fallback: {fallback_language}")
            return fallback_language, 'fallback'

        text = text.strip()
        text_preview = text[:30] + "..." if len(text) > 30 else text

        # Try Claude AI
        log.info(f"🔍 Claude AI analyzing: '{text_preview}'")
        claude_lang = await self.detect_with_claude(text)
        if claude_lang:
            log.info(f"✅ Detection successful: {claude_lang} (method: claude)")
            return claude_lang, 'claude'

        # Fallback to profile language
        log.warning(
            f"⚠️ Claude detection failed for '{text_preview}' → Using fallback: {fallback_language}"
        )
        return fallback_language, 'fallback'

    def detect(self, text: str, fallback_language: str = 'fr') -> Tuple[str, str]:
        """Deprecated: Use detect_async() instead.

        This method is deprecated because Claude AI detection requires async operations.
        Calling this method will raise a NotImplementedError to prevent silent fallback behavior.

        Args:
            text: Text to detect language from
            fallback_language: Language to use

        Returns:
            Never returns - raises NotImplementedError

        Raises:
            NotImplementedError: Always raised to enforce use of detect_async()
        """
        log.error("❌ Sync detect() called - This method is deprecated!")
        log.error("💡 Use 'await language_detection_service.detect_async()' instead")
        raise NotImplementedError(
            "Synchronous detect() is deprecated. "
            "Claude AI language detection requires async operations. "
            "Use 'await detect_async()' instead."
        )


# Global instance
language_detection_service = LanguageDetectionService()
