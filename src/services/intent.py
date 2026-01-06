"""Intent classification service for hybrid approach."""
from typing import Optional, Dict, Any
import re
from langchain_anthropic import ChatAnthropic
from src.config import settings
from src.utils.logger import log

INTENTS = {
    "greeting": {
        "keywords": [
            # English
            "hello", "hi", "hey",
            # French
            "bonjour", "salut",
            # Spanish
            "hola", "buenos dias",
            # Portuguese
            "bom dia",
            # Arabic (transliterated and common phrases)
            "allahu akbar", "salam", "as-salamu alaykum", "assalamu alaikum",
            "marhaba", "ahlan", "sabah al-khayr", "sabah al khair",
            "masa al-khayr", "masa al khair"
        ],
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

    def _contains_numbered_list(self, text: str) -> bool:
        """Check if text contains a numbered list (1. 2. 3. etc).

        Args:
            text: Text to check for numbered list

        Returns:
            True if text contains numbered list pattern
        """
        if not text:
            return False
        # Match patterns like "1.", "2)", "1 -", "1:", etc.
        # Look for at least 2 numbered items
        pattern = r'(?:^|\n)\s*[1-6][\.\)\:\-]\s+'
        matches = re.findall(pattern, text, re.MULTILINE)
        return len(matches) >= 2

    def _map_menu_option_to_intent(self, option: int, menu_text: str) -> str:
        """Map menu option number to intent based on menu content.

        Args:
            option: Selected option number (1-6)
            menu_text: The menu text that was shown to user

        Returns:
            Intent name corresponding to the option
        """
        # Standard greeting menu mapping (matches agent.py:76-84)
        # 1. 🏗️ Voir mes chantiers actifs
        # 2. 📋 Consulter mes tâches
        # 3. 🚨 Signaler un incident
        # 4. ✅ Mettre à jour ma progression
        # 5. 🗣️ Parler avec l'équipe
        GREETING_MENU_MAP = {
            1: "list_projects",
            2: "list_tasks",
            3: "report_incident",
            4: "update_progress",
            5: "escalate"
        }

        menu_lower = menu_text.lower() if menu_text else ""

        # Check if it's the standard greeting menu
        # Look for key phrases that identify it as the main menu
        is_greeting_menu = (
            ("chantier" in menu_lower or "projet" in menu_lower) and
            ("tâche" in menu_lower or "task" in menu_lower) and
            ("incident" in menu_lower or "problem" in menu_lower)
        )

        if is_greeting_menu:
            intent = GREETING_MENU_MAP.get(option, "general")
            log.info(f"🎯 Mapped greeting menu option {option} → {intent}")
            return intent

        # Project selection menu - numbers map to project indices
        # In this case, return "general" and let the agent handle it with context
        if "projet" in menu_lower or "chantier" in menu_lower:
            log.info(f"📋 Project list menu detected - option {option} (routing to agent with context)")
            return "general"

        # Task selection menu
        if "tâche" in menu_lower or "task" in menu_lower:
            log.info(f"📋 Task list menu detected - option {option} (routing to agent with context)")
            return "general"

        # Default: route to general intent (agent will use conversation context)
        log.info(f"❓ Unknown menu type - option {option} (routing to agent)")
        return "general"

    async def classify(self, message: str, user_id: str = None, last_bot_message: str = None) -> Dict[str, Any]:
        """Classify intent quickly with Claude Haiku and confidence score.

        Args:
            message: User message to classify
            user_id: Optional user ID for logging
            last_bot_message: Optional last message sent by bot (for menu context)

        Returns:
            Dict with intent name, confidence score (0-1), and metadata
        """
        try:
            message_lower = message.lower().strip()
            confidence = 0.0

            # PRIORITY 1: Check for numeric menu selection (highest priority)
            # If user sends a single digit and the last bot message contained a menu,
            # map the number directly to the corresponding intent
            if message.strip().isdigit() and last_bot_message:
                option_number = int(message.strip())
                # Check if last message was a numbered menu
                if self._contains_numbered_list(last_bot_message):
                    intent = self._map_menu_option_to_intent(option_number, last_bot_message)
                    log.info(f"🔢 Numeric menu selection detected: '{message}' from menu → {intent}")

                    # Get intent metadata
                    intent_metadata = INTENTS.get(intent, INTENTS["general"])

                    return {
                        "intent": intent,
                        "confidence": 0.95,  # High confidence for direct menu selection
                        "requires_tools": intent_metadata.get("requires_tools", True),
                        "tools": intent_metadata.get("tools", []),
                        "requires_confirmation": intent_metadata.get("requires_confirmation", False),
                        "menu_selection": True  # Flag to indicate this was a menu selection
                    }

            # PRIORITY 2: Check for exact keyword matches (high confidence)
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
