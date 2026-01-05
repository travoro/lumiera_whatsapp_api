"""Robust language detection service combining Claude AI and ML detection."""
from typing import Optional, Tuple
from lingua import Language, LanguageDetectorBuilder
from anthropic import Anthropic
from langsmith import traceable
from src.config import settings
from src.utils.logger import log


class LanguageDetectionService:
    """Hybrid language detection using Claude AI, keywords, and lingua-py."""

    # Common greetings and phrases for fast keyword matching (fallback only)
    GREETING_KEYWORDS = {
        'es': ['hola', 'buenos días', 'buenas tardes', 'buenas noches', 'qué tal', 'cómo estás'],
        'fr': ['bonjour', 'bonsoir', 'salut', 'ça va', 'comment allez-vous'],
        'en': ['hello', 'hi', 'hey', 'good morning', 'good evening', 'how are you'],
        'ro': ['bună', 'bună dimineața', 'bună seara', 'bună ziua', 'salut', 'ce mai faci'],
        'pt': ['olá', 'oi', 'bom dia', 'boa tarde', 'boa noite', 'tudo bem'],
        'de': ['hallo', 'guten morgen', 'guten tag', 'guten abend', 'wie geht'],
        'it': ['ciao', 'buongiorno', 'buonasera', 'salve', 'come stai'],
        'ar': ['مرحبا', 'مرحبًا', 'السلام عليكم', 'صباح الخير', 'مساء الخير', 'أهلا'],
        'pl': ['cześć', 'dzień dobry', 'dobry wieczór', 'witaj', 'jak się masz'],
        'ca': ['bon dia', 'bona tarda', 'bona nit', 'què tal', 'com estàs']
    }

    # Map lingua Language enum to ISO 639-1 codes
    LINGUA_TO_ISO = {
        Language.SPANISH: 'es',
        Language.FRENCH: 'fr',
        Language.ENGLISH: 'en',
        Language.ROMANIAN: 'ro',
        Language.PORTUGUESE: 'pt',
        Language.GERMAN: 'de',
        Language.ITALIAN: 'it',
        Language.ARABIC: 'ar',
        Language.POLISH: 'pl',
        Language.CATALAN: 'ca'
    }

    def __init__(self, min_confidence: float = 0.85):
        """Initialize language detection service.

        Args:
            min_confidence: Minimum confidence score for lingua detection (0.0 to 1.0)
        """
        self.min_confidence = min_confidence
        self.client = Anthropic(api_key=settings.anthropic_api_key)

        # Build lingua detector with all supported languages
        self.detector = LanguageDetectorBuilder.from_languages(
            Language.SPANISH,
            Language.FRENCH,
            Language.ENGLISH,
            Language.ROMANIAN,
            Language.PORTUGUESE,
            Language.GERMAN,
            Language.ITALIAN,
            Language.ARABIC,
            Language.POLISH,
            Language.CATALAN
        ).with_minimum_relative_distance(0.9).build()

        log.info("Language detection service initialized with Claude AI + lingua-py")

    @traceable(
        name="language_detection",
        run_type="llm",
        metadata={"service": "language_detection", "model": "claude-3-5-haiku-20241022"}
    )
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

            message = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Fast and accurate
                max_tokens=10,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )

            language_code = message.content[0].text.strip().lower()

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

    def detect_from_keywords(self, text: str) -> Optional[str]:
        """Fast keyword-based detection for common greetings (FALLBACK ONLY).

        Args:
            text: Text to check for keywords

        Returns:
            ISO 639-1 language code if keyword found, None otherwise
        """
        text_lower = text.lower().strip()

        # Check each language's keywords
        for lang, keywords in self.GREETING_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    log.info(f"🎯 Keyword match: '{keyword}' → {lang}")
                    return lang

        return None

    def detect_with_lingua(self, text: str) -> Tuple[Optional[str], float]:
        """Detect language using lingua-py ML model.

        Args:
            text: Text to detect language from

        Returns:
            Tuple of (ISO language code, confidence score)
            Returns (None, 0.0) if detection fails or confidence too low
        """
        try:
            detected_language = self.detector.detect_language_of(text)

            if detected_language:
                # Get confidence score
                confidence_values = self.detector.compute_language_confidence_values(text)

                # Find confidence for detected language
                confidence = 0.0
                for lang_conf in confidence_values:
                    if lang_conf.language == detected_language:
                        confidence = lang_conf.value
                        break

                iso_code = self.LINGUA_TO_ISO.get(detected_language)

                if iso_code and confidence >= self.min_confidence:
                    log.info(f"🔍 lingua-py detection: {iso_code} (confidence: {confidence:.2%})")
                    return iso_code, confidence
                elif iso_code:
                    log.warning(
                        f"⚠️ lingua-py detected {iso_code} but confidence too low: {confidence:.2%} "
                        f"(threshold: {self.min_confidence:.2%})"
                    )
                    return None, confidence

            return None, 0.0

        except Exception as e:
            log.error(f"Error in lingua-py detection: {e}")
            return None, 0.0

    async def detect_async(self, text: str, fallback_language: str = 'fr') -> Tuple[str, str]:
        """Detect language using hybrid approach with Claude AI (async).

        Strategy:
        1. Try Claude AI first (most accurate, especially for Romanian)
        2. If Claude fails: Try lingua-py ML detection
        3. If lingua fails: Try keyword matching (last resort)
        4. If all fail: Use fallback language

        Args:
            text: Text to detect language from
            fallback_language: Language to use if detection fails

        Returns:
            Tuple of (detected language, detection method)
            Method can be: 'claude', 'lingua', 'keyword', 'fallback'
        """
        if not text or len(text.strip()) < 2:
            log.info(f"✅ Text too short, using fallback: {fallback_language}")
            return fallback_language, 'fallback'

        text = text.strip()

        # 1. Try Claude AI first (best for all languages including Romanian)
        claude_lang = await self.detect_with_claude(text)
        if claude_lang:
            return claude_lang, 'claude'

        # 2. Try lingua-py as fallback
        lingua_lang, confidence = self.detect_with_lingua(text)
        if lingua_lang:
            return lingua_lang, 'lingua'

        # 3. Try keyword matching as last resort (for very short greetings)
        if len(text) < 30:
            keyword_lang = self.detect_from_keywords(text)
            if keyword_lang:
                return keyword_lang, 'keyword'

        # 4. Fallback to profile language
        log.info(
            f"⚠️ No confident detection, using fallback: {fallback_language}"
        )
        return fallback_language, 'fallback'

    def detect(self, text: str, fallback_language: str = 'fr') -> Tuple[str, str]:
        """Detect language using hybrid approach (sync wrapper).

        This is a synchronous wrapper for backward compatibility.
        New code should use detect_async() instead.

        Strategy:
        1. For short text (< 30 chars): Try keyword matching first
        2. If no keyword match or longer text: Use lingua-py
        3. If lingua confidence too low: Use fallback language

        Args:
            text: Text to detect language from
            fallback_language: Language to use if detection fails

        Returns:
            Tuple of (detected language, detection method)
            Method can be: 'keyword', 'lingua', 'fallback'
        """
        if not text or len(text.strip()) < 2:
            log.info(f"✅ Text too short, using fallback: {fallback_language}")
            return fallback_language, 'fallback'

        text = text.strip()

        # Try lingua-py first
        lingua_lang, confidence = self.detect_with_lingua(text)
        if lingua_lang:
            return lingua_lang, 'lingua'

        # Try keyword matching as fallback
        if len(text) < 30:
            keyword_lang = self.detect_from_keywords(text)
            if keyword_lang:
                return keyword_lang, 'keyword'

        # Fallback to profile language
        log.info(
            f"⚠️ No confident detection, using fallback: {fallback_language}"
        )
        return fallback_language, 'fallback'


# Global instance
language_detection_service = LanguageDetectionService(min_confidence=0.85)
