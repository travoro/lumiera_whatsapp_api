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
        "keywords": [
            # English
            "human", "person", "admin", "team", "contact", "speak", "talk", "help", "stuck",
            # French
            "humain", "personne", "administrateur", "équipe", "equipe", "contacter", "parler", "aide", "bloqué",
            # Spanish
            "humano", "persona", "administrador", "equipo", "contactar", "hablar", "ayuda", "atascado",
            # Portuguese
            "humano", "pessoa", "administrador", "equipe", "equipa", "contatar", "falar", "ajuda", "preso",
            # German
            "mensch", "person", "administrator", "team", "kontakt", "sprechen", "hilfe", "fest",
            # Italian
            "umano", "persona", "amministratore", "squadra", "contattare", "parlare", "aiuto", "bloccato",
            # Romanian
            "om", "persoană", "administrator", "echipă", "echipa", "contacta", "vorbi", "ajutor", "blocat",
            # Polish
            "człowiek", "osoba", "administrator", "zespół", "kontakt", "rozmawiać", "pomoc", "utknął",
            # Arabic (transliterated)
            "insan", "shakhṣ", "mudīr", "farīq", "ittiṣāl", "takallum", "musāʿada"
        ],
        "tools": ["escalate_to_human_tool"],
        "requires_confirmation": False  # No confirmation needed!
    },
    "report_incident": {
        "keywords": ["incident", "problem", "issue", "problema", "signaler", "reportar"],
        "tools": ["report_incident_tool"],
        "requires_confirmation": False
    },
    "update_progress": {
        "keywords": ["update", "progress", "progression", "mettre à jour", "actualizar", "atualizar", "avancement", "progreso", "progresso"],
        "tools": ["update_task_progress_tool"],
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
        """Classify intent quickly with Claude Haiku and confidence score.

        Args:
            message: User message to classify
            user_id: Optional user ID for logging

        Returns:
            Dict with intent name, confidence score (0-1), and metadata
        """
        try:
            # First, check for exact keyword matches (highest confidence)
            message_lower = message.lower().strip()
            confidence = 0.0

            # Exact keyword matching for high confidence
            for intent_name, intent_config in INTENTS.items():
                keywords = intent_config.get("keywords", [])
                for keyword in keywords:
                    if keyword in message_lower:
                        # Exact match = high confidence
                        if message_lower == keyword or message_lower.startswith(keyword + " ") or message_lower.endswith(" " + keyword):
                            confidence = 0.98
                            log.info(f"🎯 Exact keyword match: '{keyword}' → {intent_name} (confidence: {confidence})")
                            intent = intent_name
                            break
                        # Partial match = medium-high confidence
                        elif len(message_lower.split()) <= 3:
                            confidence = 0.90
                            log.info(f"🎯 Strong keyword match: '{keyword}' → {intent_name} (confidence: {confidence})")
                            intent = intent_name
                            break
                if confidence >= 0.90:
                    break

            # If no strong keyword match, use Claude Haiku for classification
            if confidence < 0.90:
                prompt = f"""Classify this message into ONE intent with confidence:
- greeting (hello, hi, bonjour, salut, etc.)
- list_projects (user wants to see their projects/chantiers)
- list_tasks (user wants to see tasks/tâches)
- report_incident (user wants to report a problem/incident)
- update_progress (user wants to update task progress/progression)
- escalate (user wants to speak with human/admin/help)
- general (anything else - questions, clarifications, etc.)

Message: {message}

Return ONLY the intent name and confidence (0-100) in format: intent:confidence
Example: greeting:95"""

                response = await self.haiku.ainvoke([{"role": "user", "content": prompt}])
                response_text = response.content.strip().lower()

                # Parse response
                if ":" in response_text:
                    parts = response_text.split(":")
                    intent = parts[0].strip()
                    try:
                        confidence = float(parts[1].strip()) / 100.0
                    except:
                        confidence = 0.75  # Default medium confidence
                else:
                    intent = response_text
                    confidence = 0.75  # Default if no confidence provided

                log.info(f"🤖 Haiku classification: {intent} (confidence: {confidence})")

            # Validate intent
            if intent not in INTENTS:
                log.warning(f"Unknown intent '{intent}' returned, defaulting to 'general'")
                intent = "general"
                confidence = 0.5  # Low confidence for fallback

            # Get intent metadata
            intent_metadata = INTENTS[intent]

            result = {
                "intent": intent,
                "confidence": confidence,
                "requires_tools": intent_metadata.get("requires_tools", True),
                "tools": intent_metadata.get("tools", []),
                "requires_confirmation": intent_metadata.get("requires_confirmation", False)
            }

            log.info(f"Classified intent: {intent} for message: '{message[:50]}...' (user: {user_id})")

            # Save classification for analytics (async, don't wait)
            try:
                from src.integrations.supabase import supabase_client
                if user_id:
                    await supabase_client.log_intent_classification({
                        'subcontractor_id': user_id,
                        'message_text': message[:500],  # Limit length
                        'classified_intent': intent,
                        'confidence': confidence  # Use actual confidence score
                    })
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
