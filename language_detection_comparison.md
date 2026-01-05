# Language Detection Options for Audio Transcription

## Current Issue
- **langdetect** misidentifies "Hola, ¿qué tal?" as Catalan instead of Spanish
- Struggles with short phrases
- No confidence scores

## Recommended Solution: Hybrid Approach

### Option 1: lingua-py (Best for accuracy)
```python
from lingua import Language, LanguageDetectorBuilder

detector = LanguageDetectorBuilder.from_languages(
    Language.SPANISH, Language.FRENCH, Language.ENGLISH,
    Language.PORTUGUESE, Language.ARABIC, Language.GERMAN,
    Language.ITALIAN, Language.ROMANIAN, Language.POLISH,
    Language.CATALAN
).with_minimum_relative_distance(0.9).build()

result = detector.detect_language_with_confidence("Hola, ¿qué tal?")
# Returns: (Language.SPANISH, 0.95)
```

**Pros:**
- More accurate for short text
- Returns confidence scores
- Distinguishes Spanish from Catalan better
- Pure Python, no C dependencies

**Cons:**
- Slower than langdetect (but still fast enough)
- Slightly larger library

### Option 2: fasttext (Best for speed)
```python
import fasttext

model = fasttext.load_model('lid.176.bin')
result = model.predict("Hola, ¿qué tal?", k=2)
# Returns: (('__label__es', '__label__ca'), (0.95, 0.03))
```

**Pros:**
- Very fast
- Excellent accuracy
- Returns top-k predictions with probabilities
- Trained on massive dataset

**Cons:**
- Requires downloading model file (~900KB compressed)
- C++ dependency

### Option 3: Hybrid Approach (Recommended)
Combine keyword matching for common greetings with lingua-py for everything else:

```python
GREETING_KEYWORDS = {
    'es': ['hola', 'buenos días', 'buenas tardes', 'buenas noches', 'qué tal'],
    'fr': ['bonjour', 'bonsoir', 'salut', 'ça va'],
    'en': ['hello', 'hi', 'hey', 'good morning', 'good evening'],
    'ro': ['bună', 'bună dimineața', 'bună seara', 'salut'],
    'pt': ['olá', 'oi', 'bom dia', 'boa tarde', 'boa noite'],
    'de': ['hallo', 'guten morgen', 'guten tag', 'guten abend'],
    'it': ['ciao', 'buongiorno', 'buonasera', 'salve'],
    'ar': ['مرحبا', 'السلام عليكم', 'صباح الخير', 'مساء الخير'],
    'pl': ['cześć', 'dzień dobry', 'dobry wieczór']
}

def detect_language_robust(text: str, min_confidence: float = 0.85):
    """Detect language with keyword fallback."""
    text_lower = text.lower()

    # For very short text, check keywords first
    if len(text) < 30:
        for lang, keywords in GREETING_KEYWORDS.items():
            if any(keyword in text_lower for keyword in keywords):
                return lang, 1.0

    # Use lingua-py for longer text or non-matching short text
    result = detector.detect_language_with_confidence(text)
    if result and result[1] >= min_confidence:
        return iso_code_map[result[0]], result[1]

    return None, 0.0
```

**Benefits:**
- Fast keyword matching for common greetings (instant)
- Accurate detection for longer text
- Clear "Hola" → Spanish mapping
- Confidence scores to avoid false positives

## Installation

```bash
# Option 1: lingua-py
pip install lingua-language-detector

# Option 2: fasttext
pip install fasttext

# For Arabic support in keyword matching
pip install arabic-reshaper python-bidi
```

## My Recommendation

**Use Hybrid Approach with lingua-py:**
1. Fast keyword matching for greetings like "Hola" → Spanish
2. lingua-py for everything else (more accurate than langdetect)
3. Confidence threshold to avoid false positives
4. Falls back to profile language if confidence too low

This solves:
- "Hola, ¿qué tal?" → Correctly detected as Spanish via keyword
- Longer phrases → Accurately detected by lingua-py
- Short ambiguous text → Falls back to profile if confidence low
