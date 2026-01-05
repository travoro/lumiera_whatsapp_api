"""WhatsApp message formatter with interactive message support."""
from typing import Dict, List, Optional, Any
from src.integrations.twilio import twilio_client
from src.services.template_manager import template_manager
from src.utils.logger import log


def send_whatsapp_message_smart(
    to: str,
    text: str,
    interactive_data: Optional[Dict[str, Any]] = None,
    user_name: str = "",
    language: str = "fr",
) -> Optional[str]:
    """Send WhatsApp message with automatic fallback from interactive to text.

    Args:
        to: Recipient phone number
        text: Message text content (FULL text including list for fallback)
        interactive_data: Optional dict with interactive message data:
            - type: "list" or "buttons"
            - For list: button_text, body_text, sections
            - For buttons: buttons list
        user_name: User's name for personalization
        language: User's language code (e.g., "fr", "en", "es")

    Returns:
        Message SID if successful
    """
    # Interactive messages - ENABLED via Content Template!
    # Using dynamically created templates per language
    ENABLE_INTERACTIVE = True

    # Try interactive message first if data provided and enabled
    if ENABLE_INTERACTIVE and interactive_data:
        msg_type = interactive_data.get("type")

        if msg_type == "list":
            sections = interactive_data.get("sections", [])

            if sections and len(sections) > 0:
                # Extract items from sections
                items = []
                for section in sections:
                    rows = section.get("rows", [])
                    for row in rows:
                        items.append({
                            "id": row.get("id", ""),
                            "title": row.get("title", ""),
                            "description": row.get("description", "")
                        })

                # Limit to 6 items (template supports 6)
                items = items[:6]

                log.info(f"📋 Sending interactive list using content template with {len(items)} items")

                # Build content variables for template
                # Variable 1: user name
                # Variables 2-4, 5-7, 8-10, 11-13, 14-16, 17-19: items (title, id, description)
                content_variables = {
                    "1": user_name or "there"
                }

                # Add items to variables
                for idx, item in enumerate(items):
                    var_base = (idx * 3) + 2  # 2, 5, 8, 11, 14, 17

                    # Get title and clean it (remove emojis and special chars)
                    title = item.get("title") or f"Option {idx+1}"
                    title_clean = title.replace("*", "").strip()
                    # Remove emojis
                    import re
                    title_clean = re.sub(r'[^\w\s-]', '', title_clean).strip()

                    # Generate meaningful ID from title
                    item_id = item.get("id") or f"action_{title_clean.lower().replace(' ', '_')[:30]}"

                    # Generate description from title if not provided (no emojis)
                    description = item.get("description")
                    if not description or description.strip() == "":
                        description = f"Select to {title_clean.lower()}"

                    content_variables[str(var_base)] = title_clean[:24]
                    content_variables[str(var_base + 1)] = item_id[:200]
                    content_variables[str(var_base + 2)] = description[:72]

                log.info(f"📝 Content variables: {content_variables}")

                # Get template from database for this language
                content_sid = template_manager.get_template_from_database("greeting_menu", language)

                if not content_sid:
                    log.error(f"❌ Template not found in database for language: {language}")
                    # Fallback to text
                    log.info("📱 Sending as regular text message")
                    sid = twilio_client.send_message(to=to, body=text)
                    return sid

                log.info(f"📋 Using template for language '{language}': {content_sid}")

                # Send using content template
                sid = twilio_client.send_message_with_content(
                    to=to,
                    content_sid=content_sid,
                    content_variables=content_variables
                )

                if sid:
                    log.info(f"✅ Sent interactive list via template to {to}, SID: {sid}")
                    return sid
                else:
                    log.error(f"❌ Content template send FAILED, falling back to text")

        elif msg_type == "buttons":
            # Buttons not yet implemented
            log.warning("⚠️ Interactive buttons not yet implemented, sending as text")

    # Fallback to regular text message
    log.info("📱 Sending as regular text message")
    sid = twilio_client.send_message(to=to, body=text)
    return sid


def format_menu_as_interactive_list(
    intro_text: str,
    options: List[Dict[str, str]],
    button_text: str = "Choose an option",
    section_title: str = "Options"
) -> Dict[str, Any]:
    """Format a menu into WhatsApp interactive list format.

    Args:
        intro_text: Introduction message
        options: List of dicts with 'id', 'title', and optional 'description'
        button_text: Text for the list button
        section_title: Title for the section

    Returns:
        Dict with formatted interactive list data
    """
    # Build rows from options
    rows = []
    for opt in options[:10]:  # WhatsApp limit: 10 items
        row = {
            "id": opt.get("id", f"opt_{len(rows)}"),
            "title": opt.get("title", "Option")[:24],  # Max 24 chars
        }
        if "description" in opt and opt["description"]:
            row["description"] = opt["description"][:72]  # Max 72 chars
        rows.append(row)

    return {
        "type": "list",
        "button_text": button_text,
        "sections": [
            {
                "title": section_title[:24],  # Max 24 chars
                "rows": rows
            }
        ]
    }


def format_menu_as_interactive_buttons(
    intro_text: str,
    buttons: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Format a menu into WhatsApp interactive buttons format (max 3).

    Args:
        intro_text: Introduction message
        buttons: List of dicts with 'id' and 'title'

    Returns:
        Dict with formatted interactive buttons data
    """
    return {
        "type": "buttons",
        "buttons": [
            {
                "id": btn.get("id", f"btn_{i}"),
                "title": btn.get("title", "Option")[:20]  # Max 20 chars
            }
            for i, btn in enumerate(buttons[:3])  # Max 3 buttons
        ]
    }


def format_text_with_numbered_list(
    intro_text: str,
    items: List[str],
    emoji: str = "•"
) -> str:
    """Format a text message with a numbered list.

    Args:
        intro_text: Introduction message
        items: List of items to display
        emoji: Emoji to use as bullet (default: •)

    Returns:
        Formatted text message
    """
    text = f"{intro_text}\n\n"
    for i, item in enumerate(items, 1):
        text += f"{i}. {emoji} {item}\n"
    return text.strip()
