"""Smart response parser that detects and structures agent responses."""
from typing import Optional, Tuple, List, Dict, Any
import re
from src.utils.logger import log


def detect_numbered_list(text: str, language: str = "fr") -> Optional[List[Dict[str, Any]]]:
    """Detect numbered lists in text and extract structured items.

    Looks for patterns like:
    1. Title - Description
    1. 🏗️ Title - Description

    Args:
        text: Text to analyze
        language: Language code to append to IDs (e.g., "fr", "en")

    Returns:
        List of items with id, title, description or None if no list found
    """
    # Defensive: ensure text is a string
    if not isinstance(text, str):
        log.warning(f"detect_numbered_list received non-string: {type(text)}")
        return None

    lines = text.split('\n')
    items = []
    current_section = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match numbered items: "1. ...", "1) ...", "1 - ..."
        match = re.match(r'^(\d+)[\.\)]\s+(.+)$', line)
        if match:
            current_section.append(line)
        elif current_section and not match:
            # End of numbered section
            break

    # Must have at least 1 item to be considered a menu (easier for users to click)
    if len(current_section) < 1:
        return None

    # Parse items
    for line in current_section:
        match = re.match(r'^(\d+)[\.\)]\s+(.+)$', line)
        if not match:
            continue

        number = match.group(1)
        content = match.group(2).strip()

        # Remove leading emoji if present
        emoji_match = re.match(r'^([^\w\s]+)\s+(.+)$', content)
        if emoji_match:
            emoji = emoji_match.group(1)
            content = emoji_match.group(2)
        else:
            emoji = ""

        # Split into title and description
        if ' - ' in content or ' – ' in content:
            # Use both regular and em dash
            parts = re.split(r'\s+[-–]\s+', content, 1)
            title = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else None
        else:
            title = content
            description = None

        # Add emoji back to title if it was present
        if emoji:
            title = f"{emoji} {title}"

        items.append({
            "id": f"option_{number}_{language}",  # Include language suffix to prevent language detection
            "title": title[:24],  # WhatsApp limit
            "description": description[:72] if description else None  # WhatsApp limit
        })

    return items if items else None


def extract_intro_and_list(text: str, language: str = "fr") -> Tuple[str, Optional[List[Dict[str, Any]]], str]:
    """Extract intro text, list items, and outro text from response.

    Args:
        text: Full response text
        language: Language code to append to IDs (e.g., "fr", "en")

    Returns:
        Tuple of (intro_text, list_items or None, outro_text)
    """
    # Defensive: ensure text is a string
    if not isinstance(text, str):
        log.warning(f"extract_intro_and_list received non-string: {type(text)}")
        return str(text) if text else "", None, ""

    lines = text.split('\n')
    intro_lines = []
    list_lines = []
    outro_lines = []

    in_list = False
    list_ended = False

    for line in lines:
        stripped = line.strip()

        # Check if this is a numbered item
        is_numbered = bool(re.match(r'^\d+[\.\)]\s+', stripped))

        if is_numbered and not list_ended:
            in_list = True
            list_lines.append(line)
        elif in_list and not stripped:
            # Empty line might be in the list
            list_lines.append(line)
        elif in_list and stripped and not is_numbered:
            # Non-numbered line after list started - list has ended
            list_ended = True
            outro_lines.append(line)
        elif not in_list:
            intro_lines.append(line)
        else:
            outro_lines.append(line)

    intro_text = '\n'.join(intro_lines).strip()
    outro_text = '\n'.join(outro_lines).strip()

    # Parse list items
    list_text = '\n'.join(list_lines).strip()
    items = detect_numbered_list(list_text, language) if list_text else None

    return intro_text, items, outro_text


def should_use_interactive_message(text: str) -> bool:
    """Determine if response should use interactive message.

    Args:
        text: Response text

    Returns:
        True if should use interactive, False otherwise
    """
    items = detect_numbered_list(text)
    if not items:
        return False

    # Use interactive if we have 1-10 items (WhatsApp limits, easier for users to click)
    num_items = len(items)
    return 1 <= num_items <= 10


def format_for_interactive(text: str, language: str = "fr") -> Tuple[str, Optional[Dict[str, Any]]]:
    """Format response for interactive WhatsApp message.

    Args:
        text: Agent response text
        language: Language code to append to IDs (e.g., "fr", "en")

    Returns:
        Tuple of (message_text, interactive_data or None)
        Note: message_text ALWAYS contains the full original text for fallback
    """
    if not should_use_interactive_message(text):
        return text, None

    intro, items, outro = extract_intro_and_list(text, language)

    if not items:
        return text, None

    # IMPORTANT: Keep the original text as fallback!
    # If interactive messaging fails, the full text with list will still be sent

    # For interactive body, use intro + outro (without the list items)
    body_parts = []
    if intro:
        body_parts.append(intro)
    if outro:
        body_parts.append(outro)

    interactive_body = '\n\n'.join(body_parts).strip()

    # Create interactive list data with the body text
    interactive_data = {
        "type": "list",
        "button_text": "Choisir une option",
        "body_text": interactive_body,  # Text shown above the list button
        "sections": [
            {
                "title": "Options",
                "rows": items
            }
        ]
    }

    log.info(f"📋 Formatted interactive message with {len(items)} items")
    log.info(f"📝 Original text length: {len(text)} chars")
    log.info(f"📝 Interactive body length: {len(interactive_body)} chars")
    log.info(f"📋 Items extracted: {[item['title'] for item in items]}")
    log.info(f"✅ Returning ORIGINAL TEXT as fallback")

    # Return ORIGINAL TEXT as fallback (with the numbered list intact)
    return text, interactive_data


def format_for_buttons(text: str, buttons: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
    """Format response with button options (max 3).

    Args:
        text: Message text
        buttons: List of button dicts with 'id' and 'title'

    Returns:
        Tuple of (message_text, interactive_data)
    """
    interactive_data = {
        "type": "buttons",
        "buttons": [
            {
                "id": btn.get("id", f"btn_{i}"),
                "title": btn.get("title", "Option")[:20]
            }
            for i, btn in enumerate(buttons[:3])  # Max 3
        ]
    }

    return text, interactive_data
