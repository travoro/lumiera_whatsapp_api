"""Direct intent handlers for high-confidence classifications.

These handlers execute directly without calling the main agent,
providing fast responses for simple, unambiguous requests.

The handlers are organized into three modules:
- basic_handlers: greeting, escalation (no project context needed)
- project_handlers: list_projects, list_documents, report_incident
- task_handlers: list_tasks, update_progress
"""
from typing import Dict, Any, Optional
from src.services.handlers.basic_handlers import handle_greeting, handle_escalation
from src.services.handlers.project_handlers import (
    handle_list_projects,
    handle_list_documents,
    handle_report_incident
)
from src.services.handlers.task_handlers import handle_list_tasks, handle_task_details
from src.utils.logger import log


# Intent handler mapping
INTENT_HANDLERS = {
    "greeting": handle_greeting,
    "list_projects": handle_list_projects,
    "list_tasks": handle_list_tasks,
    "task_details": handle_task_details,
    "list_documents": handle_list_documents,
    "view_documents": handle_list_documents,  # Same handler as list_documents
    "escalate": handle_escalation,
    "report_incident": handle_report_incident,
    # NOTE: update_progress removed from fast path - now handled by specialized agent in message.py
    # Add more handlers as needed
}


async def execute_direct_handler(
    intent: str,
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """Execute direct handler for given intent.

    Args:
        intent: Intent name
        user_id: User ID
        phone_number: User phone number
        user_name: User name
        language: User language
        **kwargs: Additional parameters

    Returns:
        Dict with message, escalation, tools_called if successful
        None if handler fails (triggers fallback to full agent)
    """
    handler = INTENT_HANDLERS.get(intent)

    if not handler:
        log.warning(f"No direct handler for intent: {intent}")
        return None

    try:
        result = await handler(
            user_id=user_id,
            phone_number=phone_number,
            user_name=user_name,
            language=language,
            **kwargs
        )

        if result:
            log.info(f"✅ Fast path successful for intent: {intent}")
        else:
            log.warning(f"⚠️ Fast path handler returned None for intent: {intent}")

        return result

    except Exception as e:
        log.error(f"❌ Fast path failed for intent {intent}: {e}")
        return None


# Export all handlers and utilities
__all__ = [
    "INTENT_HANDLERS",
    "execute_direct_handler",
    "handle_greeting",
    "handle_escalation",
    "handle_list_projects",
    "handle_list_documents",
    "handle_report_incident",
    "handle_list_tasks",
    "handle_task_details",
]
