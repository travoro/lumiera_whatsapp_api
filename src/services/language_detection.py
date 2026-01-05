"""Language detection service using Claude AI."""
from typing import Optional, Tuple
from langchain_anthropic import ChatAnthropic
from src.config import settings
from src.utils.logger import log


class LanguageDetectionService:
    """Language detection using Claude AI."""

    def __init__(self):
        """Initialize language detection service with Claude AI."""
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
                log.info(f"🤖 Claude detected: {language_code}")
                return language_code
            else:
                log.warning(f"⚠️ Claude returned unsupported language: {language_code}")
                return None

        except Exception as e:
            log.error(f"Error in Claude language detection: {e}")
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
            log.info(f"✅ Text too short, using fallback: {fallback_language}")
            return fallback_language, 'fallback'

        text = text.strip()

        # Try Claude AI
        claude_lang = await self.detect_with_claude(text)
        if claude_lang:
            return claude_lang, 'claude'

        # Fallback to profile language
        log.warning(f"⚠️ Claude detection failed, using fallback: {fallback_language}")
        return fallback_language, 'fallback'

    def detect(self, text: str, fallback_language: str = 'fr') -> Tuple[str, str]:
        """Synchronous detect method (for backward compatibility).

        Note: Claude AI detection is async only. This method returns the fallback language.
        Use detect_async() for actual Claude-based detection.

        Args:
            text: Text to detect language from
            fallback_language: Language to use

        Returns:
            Tuple of (fallback language, 'fallback')
        """
        log.warning("⚠️ Sync detect() called - Claude detection requires async. Using fallback language.")
        log.info("💡 Use detect_async() instead for Claude AI detection")
        return fallback_language, 'fallback'


# Global instance
language_detection_service = LanguageDetectionService()
