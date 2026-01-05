"""Intent classification service for hybrid approach."""
from typing import Optional, Dict, Any
from langchain_anthropic import ChatAnthropic
from src.config import settings
from src.utils.logger import log

INTENTS = {
    "greeting": {
        "keywords": ["hello", "hi", "bonjour", "salut", "hola", "hey", "buenos dias", "bom dia"],
        "requires_tools": False
    },
    "list_projects": {
        "keywords": ["projects", "chantiers", "list", "show", "projets", "voir", "mostrar"],
        "tools": ["list_projects_tool"],
        "requires_confirmation": False
    },
    "list_tasks": {
        "keywords": ["tasks", "tâches", "todo", "tareas", "tarefas"],
        "tools": ["list_tasks_tool"],
        "requires_confirmation": False
    },
    "escalate": {  # EASY ESCALATION - NO CONFIRMATION
        "keywords": ["human", "person", "admin", "help", "stuck", "parler", "humano", "pessoa", "ayuda"],
        "tools": ["escalate_to_human_tool"],
        "requires_confirmation": False  # No confirmation needed!
    },
    "report_incident": {
        "keywords": ["incident", "problem", "issue", "problema", "signaler", "reportar"],
        "tools": ["report_incident_tool"],
        "requires_confirmation": False
    },
    "general": {
        "keywords": [],
        "tools": "all",  # All tools available
        "requires_confirmation": False
    }
}


class IntentClassifier:
    """Fast intent classification using Claude Haiku for hybrid approach."""

    def __init__(self):
        """Initialize intent classifier with Claude Haiku for speed."""
        self.haiku = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            api_key=settings.anthropic_api_key,
            temperature=0.1,
            max_tokens=50
        )
        log.info("Intent classifier initialized with Claude Haiku")

    async def classify(self, message: str, user_id: str = None) -> Dict[str, Any]:
        """Classify intent quickly with Claude Haiku.

        Args:
            message: User message to classify
            user_id: Optional user ID for logging

        Returns:
            Dict with intent name and metadata
        """
        try:
            prompt = f"""Classify this message into ONE intent:
- greeting (hello, hi, bonjour, salut, etc.)
- list_projects (user wants to see their projects/chantiers)
- list_tasks (user wants to see tasks/tâches)
- report_incident (user wants to report a problem/incident)
- escalate (user wants to speak with human/admin/help)
- general (anything else - questions, updates, etc.)

Message: {message}

Return ONLY the intent name, nothing else."""

            response = await self.haiku.ainvoke([{"role": "user", "content": prompt}])
            intent = response.content.strip().lower()

            # Validate intent
            if intent not in INTENTS:
                log.warning(f"Unknown intent '{intent}' returned, defaulting to 'general'")
                intent = "general"

            # Get intent metadata
            intent_metadata = INTENTS[intent]

            result = {
                "intent": intent,
                "requires_tools": intent_metadata.get("requires_tools", True),
                "tools": intent_metadata.get("tools", []),
                "requires_confirmation": intent_metadata.get("requires_confirmation", False)
            }

            log.info(f"Classified intent: {intent} for message: '{message[:50]}...' (user: {user_id})")

            # Save classification for analytics (async, don't wait)
            try:
                from src.integrations.supabase import supabase_client
                if user_id:
                    supabase_client.client.table('intent_classifications').insert({
                        'subcontractor_id': user_id,
                        'message_text': message[:500],  # Limit length
                        'classified_intent': intent,
                        'confidence': 0.9  # Haiku is generally reliable
                    }).execute()
            except Exception as e:
                log.warning(f"Failed to save intent classification: {e}")

            return result

        except Exception as e:
            log.error(f"Error classifying intent: {e}")
            # Default to general on error
            return {
                "intent": "general",
                "requires_tools": True,
                "tools": "all",
                "requires_confirmation": False
            }

    def get_intent_info(self, intent: str) -> Dict[str, Any]:
        """Get metadata for a specific intent.

        Args:
            intent: Intent name

        Returns:
            Intent metadata dict
        """
        return INTENTS.get(intent, INTENTS["general"])


# Global instance
intent_classifier = IntentClassifier()
