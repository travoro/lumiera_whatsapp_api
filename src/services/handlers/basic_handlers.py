"""Basic intent handlers that don't require project context.

These handlers execute directly without calling the main agent,
providing fast responses for simple, unambiguous requests.
"""

from typing import Any, Dict

from src.services.escalation import escalation_service
from src.utils.logger import log
from src.utils.whatsapp_formatter import get_translation


async def handle_greeting(
    user_id: str, user_name: str, language: str, phone_number: str = None, **kwargs
) -> Dict[str, Any]:
    """Handle greeting intent directly.

    IMPORTANT: Always returns French text. Translation to user language
    happens in the pipeline (message.py:272-278).

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling greeting for {user_name}")

    # Format name for greeting (with comma if provided)
    name_part = f", {user_name}" if user_name else ""

    # ALWAYS return French - translation to user language happens in pipeline
    greeting_template = get_translation("fr", "greeting")
    message = (
        greeting_template.format(name=name_part)
        if greeting_template
        else f"Bonjour{name_part}!"
    )

    return {
        "message": message,
        "escalation": False,
        "tools_called": [],
        "fast_path": True,
    }


async def handle_escalation(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    reason: str = "User requested to speak with team",
    **kwargs,
) -> Dict[str, Any]:
    """Handle escalation intent directly.

    IMPORTANT: Always returns French text. Translation to user language
    happens in the pipeline (message.py:272-278).

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Escalating for {user_id}")

    try:
        escalation_id = await escalation_service.create_escalation(
            user_id=user_id,
            user_phone=phone_number,
            user_language=language,
            reason=reason,
            context={"escalation_type": "direct_intent", "fast_path": True},
        )

        if escalation_id:
            # ALWAYS return French - translation to user language happens in pipeline
            return {
                "message": get_translation("fr", "escalation_success"),
                "escalation": True,
                "tools_called": ["escalate_to_human_tool"],
                "fast_path": True,
            }
        else:
            # Escalation failed, return None to trigger full agent
            return None

    except Exception as e:
        log.error(f"Error in fast path escalation: {e}")
        return None
