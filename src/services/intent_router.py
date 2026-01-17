"""Intent router for dispatching user actions to appropriate handlers.

This module acts as the single point of routing for all user intents,
preventing direct handler-to-handler calls and maintaining proper layering.
"""

from typing import Any, Dict, Optional

from src.utils.logger import log


class IntentRouter:
    """Routes user intents to appropriate handlers with proper orchestration."""

    def __init__(self):
        """Initialize router with lazy-loaded handlers."""
        self._handlers = {}
        log.info("Intent router initialized")

    def _get_handler(self, intent: str):
        """Lazy load handler to avoid circular imports."""
        if intent in self._handlers:
            return self._handlers[intent]

        # Lazy import handlers
        from src.services.handlers import (  # handle_update_progress removed - now handled by specialized agent
            handle_escalation,
            handle_greeting,
            handle_list_documents,
            handle_list_projects,
            handle_list_tasks,
            handle_report_incident,
            handle_task_details,
        )

        handler_mapping = {
            "view_tasks": handle_list_tasks,
            "list_tasks": handle_list_tasks,
            "task_details": handle_task_details,
            "view_documents": handle_list_documents,
            "list_documents": handle_list_documents,
            "report_incident": handle_report_incident,
            # "update_progress": handle_update_progress,  # Removed - use specialized agent
            "greeting": handle_greeting,
            "escalate": handle_escalation,
            "talk_team": handle_escalation,
            "view_sites": handle_list_projects,
            "list_projects": handle_list_projects,
        }

        handler = handler_mapping.get(intent)
        if handler:
            self._handlers[intent] = handler
        return handler

    async def route_intent(
        self,
        intent: str,
        user_id: str,
        phone_number: str,
        user_name: str,
        language: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Route intent to appropriate handler.

        Args:
            intent: The user's intent/action
            user_id: User ID
            phone_number: User phone number
            user_name: User name
            language: User language
            **kwargs: Additional parameters for handler

        Returns:
            Handler response dict or None if no handler found
        """
        handler = self._get_handler(intent)

        if not handler:
            log.warning(f"No handler found for intent: {intent}")
            return None

        try:
            log.info(f"Routing intent '{intent}' to handler")
            result = await handler(
                user_id=user_id,
                phone_number=phone_number,
                user_name=user_name,
                language=language,
                **kwargs,
            )

            if result:
                log.info(f"✅ Intent '{intent}' handled successfully")
            else:
                log.warning(f"⚠️ Handler returned None for intent: {intent}")

            return result

        except Exception as e:
            log.error(f"❌ Error routing intent '{intent}': {e}")
            return None


# Global router instance
intent_router = IntentRouter()
