"""Input validation and sanitization service."""
import re
from typing import Dict, Any
from src.utils.logger import log

# Suspicious patterns that might indicate prompt injection or malicious input
SUSPICIOUS_PATTERNS = [
    r"ignore.*previous.*instructions?",
    r"system.*prompt",
    r"you are now",
    r"jailbreak",
    r"<script",
    r"javascript:",
    r"onerror\s*=",
    r"eval\s*\(",
    r"exec\s*\(",
    r"<iframe",
    r"onclick\s*=",
    r"onload\s*=",
]

# Configuration
MAX_MESSAGE_LENGTH = 5000
MIN_MESSAGE_LENGTH = 1


async def validate_input(message: str, user_id: str) -> Dict[str, Any]:
    """Validate and sanitize user input.

    Args:
        message: User message to validate
        user_id: User ID for logging

    Returns:
        Dict with validation result:
        - is_valid: bool
        - reason: str (if invalid)
        - message: str (error message if invalid)
        - sanitized: str (sanitized message if valid)
    """
    # Empty check
    if not message or not message.strip():
        return {
            "is_valid": False,
            "reason": "empty_message",
            "message": "Message cannot be empty"
        }

    # Length check - minimum
    if len(message.strip()) < MIN_MESSAGE_LENGTH:
        return {
            "is_valid": False,
            "reason": "message_too_short",
            "message": "Message is too short"
        }

    # Length check - maximum
    if len(message) > MAX_MESSAGE_LENGTH:
        log.warning(f"Message too long from user {user_id}: {len(message)} characters")
        return {
            "is_valid": False,
            "reason": "message_too_long",
            "message": f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"
        }

    # Injection detection
    message_lower = message.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            log.warning(f"Suspicious pattern detected for user {user_id}: pattern='{pattern}', message='{message[:100]}'")
            return {
                "is_valid": False,
                "reason": "suspicious_pattern",
                "message": "Your message contains suspicious content. Please rephrase your message."
            }

    # Sanitize - basic cleanup
    sanitized = message.strip()

    # Remove excessive whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized)

    log.info(f"Input validated successfully for user {user_id}: {len(sanitized)} chars")

    return {
        "is_valid": True,
        "sanitized": sanitized
    }


def is_safe_for_sql(value: str) -> bool:
    """Check if a value is safe to use in SQL queries.

    Note: This is a secondary check. All queries should use parameterized
    queries, but this provides an additional safety layer.

    Args:
        value: Value to check

    Returns:
        True if safe, False otherwise
    """
    if not value:
        return False

    # Check for SQL injection patterns
    sql_patterns = [
        r";\s*drop\s+table",
        r";\s*delete\s+from",
        r";\s*update\s+",
        r"union\s+select",
        r"--",
        r"/\*",
        r"\*/",
        r"xp_cmdshell",
        r"exec\s*\(",
    ]

    value_lower = value.lower()
    for pattern in sql_patterns:
        if re.search(pattern, value_lower):
            log.error(f"SQL injection pattern detected: {pattern} in value: {value[:100]}")
            return False

    return True


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal attacks.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"

    # Remove path components
    filename = filename.split('/')[-1]
    filename = filename.split('\\')[-1]

    # Remove dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '', filename)

    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')

    return filename or "unnamed"
