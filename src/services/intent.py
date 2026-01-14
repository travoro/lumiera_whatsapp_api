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
            max_tokens=100  # Increased for menu context understanding
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
        # Look for at least 1 numbered item (supporting 1-10 for dynamic menus)
        pattern = r'(?:^|\n)\s*[1-9][\.\)\:\-]\s+|(?:^|\n)\s*10[\.\)\:\-]\s+'
        matches = re.findall(pattern, text, re.MULTILINE)
        return len(matches) >= 1

    async def _classify_menu_selection(self, option: int, menu_text: str) -> str:
        """Use Haiku to intelligently classify menu selection based on context.

        Instead of hardcoded mappings, we let Haiku understand the menu content
        and determine what the user wants to do based on their selection.

        Args:
            option: Selected option number (1-9)
            menu_text: The full menu text shown to user

        Returns:
            Intent name based on Haiku's understanding of the menu
        """
        # Truncate menu text if too long (keep first 500 chars for context)
        menu_preview = menu_text[:500] if len(menu_text) > 500 else menu_text

        prompt = f"""Le bot a montré ce menu à l'utilisateur :

{menu_preview}

L'utilisateur a répondu avec : {option}

En fonction du contenu du menu et de la sélection de l'option {option} par l'utilisateur, classifie ce que l'utilisateur veut faire :

- greeting: L'utilisateur veut revoir le menu principal
- list_projects: L'utilisateur veut voir ses projets/chantiers
- list_tasks: L'utilisateur veut voir les tâches (OU sélectionne un PROJET d'une liste de projets pour voir ses tâches)
- report_incident: L'utilisateur veut signaler un problème/incident
- update_progress: L'utilisateur veut mettre à jour la progression d'une tâche
- escalate: L'utilisateur veut parler à un humain/équipe
- general: Sélection d'une TÂCHE spécifique d'une liste de tâches (nécessite le contexte complet de l'agent)

Retourne SEULEMENT le nom de l'intent et la confiance (0-100) au format : intent:confidence
Exemple : escalate:95

RÈGLES CRITIQUES :
1. Si le menu montre une LISTE DE PROJETS (contient "projet" ou "chantier" ou "🏗️") ET l'utilisateur sélectionne un numéro → Retourne : list_tasks
   Exemple : "1. 🏗️ Champigny" + utilisateur dit "1" → list_tasks (utilisateur veut les tâches pour Champigny)
2. Si le menu montre une LISTE DE TÂCHES (contient "tâche" ou "📝") ET l'utilisateur sélectionne un numéro → Retourne : general
   Exemple : "1. 📝 Installation" + utilisateur dit "1" → general (nécessite contexte complet)
3. Si le menu est le MENU PRINCIPAL (plusieurs options d'action) → Basé sur l'option spécifique sélectionnée"""

        try:
            response = await self.haiku.ainvoke([{"role": "user", "content": prompt}])
            response_text = response.content.strip().lower()

            # Parse response
            if ":" in response_text:
                parts = response_text.split(":")
                intent = parts[0].strip()
                try:
                    confidence = float(parts[1].strip()) / 100.0
                except:
                    confidence = 0.90  # High confidence for menu selection
            else:
                intent = response_text.strip()
                confidence = 0.90

            log.info(f"🤖 Haiku classified menu option {option} → {intent} (confidence: {confidence})")
            return intent

        except Exception as e:
            log.error(f"Error in Haiku menu classification: {e}")
            # Fallback: return general so agent can handle it
            return "general"

    async def classify(
        self,
        message: str,
        user_id: str = None,
        last_bot_message: str = None,
        conversation_history: list = None
    ) -> Dict[str, Any]:
        """Classify intent quickly with Claude Haiku and confidence score.

        Args:
            message: User message to classify
            user_id: Optional user ID for logging
            last_bot_message: Optional last message sent by bot (for menu context)
            conversation_history: Optional list of recent messages (last 3) for context

        Returns:
            Dict with intent name, confidence score (0-1), and metadata
        """
        try:
            message_lower = message.lower().strip()
            confidence = 0.0

            # PRIORITY 1: Check for numeric menu selection (highest priority)
            # If user sends a single digit and the last bot message contained a menu,
            # use Haiku to intelligently understand what the selection means
            if message.strip().isdigit() and last_bot_message:
                option_number = int(message.strip())
                # Check if last message was a numbered menu
                if self._contains_numbered_list(last_bot_message):
                    log.info(f"🔢 Numeric menu selection detected: '{message}' - asking Haiku to classify with context")

                    # Use Haiku to understand the menu and classify the intent
                    intent = await self._classify_menu_selection(option_number, last_bot_message)

                    # Get intent metadata
                    intent_metadata = INTENTS.get(intent, INTENTS["general"])

                    return {
                        "intent": intent,
                        "confidence": 0.95,  # Very high confidence for menu selection with context
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
                # Build conversation context if available
                context_section = ""
                if conversation_history and len(conversation_history) > 0:
                    context_section = "\n\nRecent conversation history:\n"
                    for msg in conversation_history:
                        direction = msg.get('direction', '')
                        content = msg.get('content', '')[:100]  # Limit to 100 chars
                        if direction == 'inbound':
                            context_section += f"User: {content}\n"
                        elif direction == 'outbound':
                            context_section += f"Bot: {content}\n"
                    context_section += "\n"

                prompt = f"""Classify this message into ONE intent with confidence:
- greeting (hello, hi, bonjour, salut, etc.)
- list_projects (user wants to see their projects/chantiers)
- list_tasks (user wants to see tasks/tâches for a project)
- report_incident (user wants to report a problem/incident)
- update_progress (user wants to update task progress/progression)
- escalate (user wants to speak with human/admin/help)
- general (anything else - questions, clarifications, complex requests)

IMPORTANT CONTEXT RULES:
- If bot asked "which project/chantier for tasks" and user answers with project name → list_tasks:90 (user still wants tasks)
- If bot is showing task list and user is selecting a specific task → general:85 (needs full context)
- If bot asked question about incident/progress and user answering → keep same intent as conversation topic with high confidence (85-90)
- For simple project name after bot asked about tasks → list_tasks:90 (fast path can handle it)
- When user is clearly answering a bot question, return HIGHER confidence (85-95) to enable fast path
{context_section}
Current message: {message}

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
