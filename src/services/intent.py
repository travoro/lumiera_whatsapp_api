"""Intent classification service for hybrid approach."""

import json
import re
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langsmith import traceable

from src.config import settings
from src.utils.logger import log

INTENTS = {
    "greeting": {
        "keywords": [
            # English
            "hello",
            "hi",
            "hey",
            # French
            "bonjour",
            "salut",
            # Spanish
            "hola",
            "buenos dias",
            # Portuguese
            "bom dia",
            # Arabic (transliterated and common phrases)
            "allahu akbar",
            "salam",
            "as-salamu alaykum",
            "assalamu alaikum",
            "marhaba",
            "ahlan",
            "sabah al-khayr",
            "sabah al khair",
            "masa al-khayr",
            "masa al khair",
        ],
        "requires_tools": False,
    },
    "list_projects": {
        "keywords": [
            "projects",
            "chantiers",
            "list",
            "show",
            "projets",
            "voir",
            "mostrar",
        ],
        "tools": ["list_projects_tool"],
        "requires_confirmation": False,
    },
    "list_tasks": {
        "keywords": ["tasks", "tâches", "todo", "tareas", "tarefas"],
        "tools": ["list_tasks_tool"],
        "requires_confirmation": False,
    },
    "view_documents": {
        "keywords": [
            # English
            "documents",
            "plans",
            "plan",
            "files",
            "blueprints",
            "drawings",
            # French
            "documents",
            "plan",
            "plans",
            "fichiers",
            "schémas",
            "dessins",
            "voir plan",
            "voir les plans",
            # Spanish
            "documentos",
            "planos",
            "archivos",
            "ver plan",
            # Portuguese
            "documentos",
            "planos",
            "arquivos",
            "ver plano",
        ],
        "tools": ["get_documents_tool"],
        "requires_confirmation": False,
    },
    "escalate": {  # EASY ESCALATION - NO CONFIRMATION
        "keywords": [
            # English
            "human",
            "person",
            "admin",
            "team",
            "contact",
            "speak",
            "talk",
            "help",
            "stuck",
            # French
            "humain",
            "personne",
            "administrateur",
            "équipe",
            "equipe",
            "contacter",
            "parler",
            "aide",
            "bloqué",
            # Spanish
            "humano",
            "persona",
            "administrador",
            "equipo",
            "contactar",
            "hablar",
            "ayuda",
            "atascado",
            # Portuguese
            "humano",
            "pessoa",
            "administrador",
            "equipe",
            "equipa",
            "contatar",
            "falar",
            "ajuda",
            "preso",
            # German
            "mensch",
            "person",
            "administrator",
            "team",
            "kontakt",
            "sprechen",
            "hilfe",
            "fest",
            # Italian
            "umano",
            "persona",
            "amministratore",
            "squadra",
            "contattare",
            "parlare",
            "aiuto",
            "bloccato",
            # Romanian
            "om",
            "persoană",
            "administrator",
            "echipă",
            "echipa",
            "contacta",
            "vorbi",
            "ajutor",
            "blocat",
            # Polish
            "człowiek",
            "osoba",
            "administrator",
            "zespół",
            "kontakt",
            "rozmawiać",
            "pomoc",
            "utknął",
            # Arabic (transliterated)
            "insan",
            "shakhṣ",
            "mudīr",
            "farīq",
            "ittiṣāl",
            "takallum",
            "musāʿada",
        ],
        "tools": ["escalate_to_human_tool"],
        "requires_confirmation": False,  # No confirmation needed!
    },
    "report_incident": {
        "keywords": [
            "incident",
            "problem",
            "issue",
            "problema",
            "signaler",
            "reportar",
        ],
        "tools": ["report_incident_tool"],
        "requires_confirmation": False,
    },
    "update_progress": {
        "keywords": [
            "update",
            "progress",
            "progression",
            "mettre à jour",
            "actualizar",
            "atualizar",
            "avancement",
            "progreso",
            "progresso",
        ],
        "tools": ["update_task_progress_tool"],
        "requires_confirmation": False,
    },
    "task_details": {
        "keywords": [
            # English
            "details",
            "detail",
            "info",
            "information",
            "describe",
            "show",
            "view",
            "see",
            # French
            "détails",
            "détail",
            "description",
            "voir",
            "montrer",
            "afficher",
            "infos",
            "informations",
            # Spanish
            "detalles",
            "detalle",
            "descripción",
            "información",
            "ver",
            "mostrar",
            # Portuguese
            "detalhes",
            "descrição",
            "informação",
            "ver",
            "mostrar",
        ],
        "tools": ["get_task_description_tool", "get_task_images_tool"],
        "requires_confirmation": False,
    },
    "general": {
        "keywords": [],
        "tools": "all",  # All tools available
        "requires_confirmation": False,
    },
}


class IntentClassifier:
    """Fast intent classification using LLM for hybrid approach."""

    def __init__(self):
        """Initialize intent classifier with selected LLM provider."""
        if settings.llm_provider == "openai":
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",  # Fast and cheap for classification
                api_key=settings.openai_api_key,
                temperature=0.1,
                max_tokens=100,
            )
            log.info("Intent classifier initialized with OpenAI (gpt-4o-mini)")
        else:
            self.llm = ChatAnthropic(
                model="claude-3-5-haiku-20241022",
                api_key=settings.anthropic_api_key,
                temperature=0.1,
                max_tokens=100,
            )
            log.info("Intent classifier initialized with Claude Haiku")
        # Keep backward compatibility
        self.haiku = self.llm

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
        pattern = r"(?:^|\n)\s*[1-9][\.\)\:\-]\s+|(?:^|\n)\s*10[\.\)\:\-]\s+"
        matches = re.findall(pattern, text, re.MULTILINE)
        return len(matches) >= 1

    @traceable(
        name="Intent Classification (Haiku)",
        metadata={
            "model": "claude-3-5-haiku-20241022",
            "purpose": "classify_user_intent",
        },
    )
    async def classify(
        self,
        message: str,
        user_id: str = None,
        last_bot_message: str = None,
        conversation_history: list = None,
        # FSM context for session continuation (context preservation)
        active_session_id: str = None,
        fsm_state: str = None,
        expecting_response: bool = False,
        should_continue_session: bool = False,
        # Media context (critical for photo/video messages)
        has_media: bool = False,
        media_type: str = None,
        num_media: int = 0,
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

            # PRIORITY 1: Check for exact keyword matches (high confidence)
            # Exact keyword matching for high confidence
            for intent_name, intent_config in INTENTS.items():
                keywords = intent_config.get("keywords", [])
                for keyword in keywords:  # type: ignore[attr-defined]
                    if keyword in message_lower:
                        # Exact match = high confidence
                        if (
                            message_lower == keyword
                            or message_lower.startswith(keyword + " ")
                            or message_lower.endswith(" " + keyword)
                        ):
                            confidence = 0.98
                            log.info(
                                f"🎯 Exact keyword match: '{keyword}' → {intent_name} (confidence: {confidence})"
                            )
                            intent = intent_name
                            break
                        # Partial match = medium-high confidence
                        elif len(message_lower.split()) <= 3:
                            confidence = 0.90
                            log.info(
                                f"🎯 Strong keyword match: '{keyword}' → {intent_name} (confidence: {confidence})"
                            )
                            intent = intent_name
                            break
                if confidence >= 0.90:
                    break

            # PRIORITY 2: Use Claude Haiku for classification (handles both menu selections and general messages)
            if confidence < 0.90:
                # Build conversation context if available
                context_section = ""
                if conversation_history and len(conversation_history) > 0:
                    context_section = "\n\nHistorique récent de conversation :\n"
                    for msg in conversation_history:
                        direction = msg.get("direction", "")
                        content = msg.get("content", "")[:200]  # Limit to 200 chars
                        if direction == "inbound":
                            context_section += f"User: {content}\n"
                        elif direction == "outbound":
                            context_section += f"Bot: {content}\n"
                    context_section += "\n"

                # Check if last bot message was a numbered menu
                is_menu_response = (
                    message.strip().isdigit()
                    and last_bot_message
                    and self._contains_numbered_list(last_bot_message)
                )
                menu_hint = ""
                if is_menu_response:
                    menu_hint = f"\n⚠️ IMPORTANT : L'utilisateur répond à un menu numéroté avec '{message}'. Analyse l'historique pour comprendre ce que ce numéro représente.\n"

                # Media context hint (critical for photo/video messages)
                media_hint = ""
                media_reminder = ""  # For reinforcement near message
                if has_media:
                    media_types = {
                        "image": "photo/image",
                        "video": "vidéo",
                        "audio": "message vocal/audio",
                    }
                    media_display = media_types.get(media_type, "média")
                    media_hint = f"""
📎 MEDIA ATTACHÉ : L'utilisateur a envoyé {num_media} {media_display}

RÈGLES CRITIQUES POUR MESSAGES AVEC MÉDIA :
1. Si session active (update_progress) + photo/vidéo → update_progress:95
   (L'utilisateur envoie une photo pour la tâche en cours)

2. Si message vide/court ("...", "voilà", "") + photo → utiliser l'historique :
   - Si bot vient de demander une photo → update_progress:95
   - Si dernière action était mise à jour tâche → update_progress:90
   - Si pas de contexte clair → general:70

3. Si photo + texte descriptif ("le mur", "voici le problème") :
   - Session active → update_progress:95 (photo pour tâche en cours)
   - Pas de session → report_incident:85 (nouveau problème avec preuve)

4. IMPORTANT : Ne JAMAIS classifier "escalate" quand il y a une photo,
   sauf si le texte dit explicitement "aide", "parler à quelqu'un", etc.

5. Photo = ACTION de l'utilisateur, pas demande d'aide!
"""
                    # Add reminder near the message for better locality
                    media_reminder = f"\n📎 Médias joints : {num_media} {media_display}"

                # FSM context hint (critical for context preservation)
                fsm_hint = ""
                if should_continue_session and expecting_response:
                    fsm_hint = f"""
⚠️⚠️⚠️ CONTEXTE DE SESSION ACTIVE CRITIQUE ⚠️⚠️⚠️

L'utilisateur est EN TRAIN de mettre à jour une tâche (état FSM: {fsm_state})
Le bot vient de lui présenter des options et ATTEND UNE RÉPONSE.
Ce message est TRÈS PROBABLEMENT une réponse à ces options, PAS un nouveau intent!

RÈGLES PRIORITAIRES (À APPLIQUER EN PREMIER) :
1. Si le message peut être interprété comme un commentaire/description (texte descriptif,
   observation, mention de problème, description d'état), c'est "update_progress" pour
   CONTINUER la session active, PAS "report_incident" pour créer un nouvel incident.

2. EXEMPLES dans ce contexte de session active :
   - "le mur est encore fisurré" → update_progress:95 (commentaire sur la tâche en cours)
   - "il y a un problème avec la peinture" → update_progress:95 (commentaire, pas incident)
   - "c'est fait" / "terminé" → update_progress:90 (veut probablement marquer comme terminé)
   - "voilà" / "ok" → update_progress:85 (confirmation vague, continuer session)

3. Classifier comme NOUVEAU intent seulement si l'utilisateur dit EXPLICITEMENT :
   - "Annuler" / "Stop" / "Non merci" / "Laisse tomber" / "Abandonner"
   - "Je veux faire autre chose" / "Change de sujet"
   - Demande CLAIRE et EXPLICITE d'une action différente ("Montre-moi les documents" / "Liste mes projets")

4. IMPORTANT : Dans le DOUTE, TOUJOURS privilégier "update_progress" (continuer la session)
   plutôt que de commencer un nouveau flow. Il est préférable de continuer la session existante
   que de l'abandonner par erreur.

5. Confiance recommandée : update_progress:95 (haute confiance car session active)
"""

                prompt = f"""Classifie ce message dans UN seul intent avec confiance :
- greeting (hello, hi, bonjour, salut, etc.)
- list_projects (l'utilisateur veut voir ses projets/chantiers)
- list_tasks (l'utilisateur veut voir les tâches pour un projet)
- view_documents (l'utilisateur veut voir les documents/plans d'un projet)
- task_details (l'utilisateur veut voir les détails/description/photos d'une tâche spécifique)
- report_incident (l'utilisateur veut signaler un problème/incident)
- update_progress (l'utilisateur veut mettre à jour la progression d'une tâche)
- escalate (l'utilisateur veut parler à un humain/admin/aide)
- general (tout le reste - questions, clarifications, demandes complexes)
{media_hint}{fsm_hint}{menu_hint}
RÈGLES DE CONTEXTE IMPORTANTES :
- Si historique montre LISTE DE PROJETS (🏗️, "projet", "chantier") ET utilisateur sélectionne numéro → list_tasks:95
- Si historique montre LISTE DE TÂCHES (📝, "tâche") ET utilisateur sélectionne numéro → task_details:90
- Si utilisateur demande explicitement "plan", "plans", "documents" d'un projet → view_documents:90
- Si le bot a demandé "quel projet/chantier" et l'utilisateur répond avec nom → list_tasks:90
- Si bot pose question sur incident/progression et utilisateur répond → même intent (85-90)
- Quand utilisateur répond clairement à question du bot → confiance HAUTE (85-95) pour fast path

⚠️ CAS AMBIGUS - Classifier comme "general" pour clarification :
- Si utilisateur dit "autre tâche" / "différente tâche" / "changer de tâche" SANS préciser laquelle
  → L'utilisateur veut une tâche différente mais n'a pas précisé même/autre projet
  → Classifier "general" pour que le LLM puisse poser des questions de clarification
  → Exemples : "je souhaite modifier une autre tache" → general:90
  → Exemples : "je veux travailler sur une autre tâche" → general:85

⚠️ RÈGLE CRITIQUE POUR update_progress :
- NE JAMAIS classifier comme "update_progress" si la requête est VAGUE ou sans contexte de tâche claire
- Exemples VAGUES à classifier comme "general" :
  → "Mettre à jour les tâches" → general:85 (pas de tâche spécifique mentionnée)
  → "Je veux faire une mise à jour" → general:85 (vague, aucune tâche)
  → "Mise à jour de progression" → general:85 (pas de contexte)
- Classifier "update_progress" SEULEMENT si :
  → Session active (should_continue_session=True) ET message compatible avec ajout photo/commentaire
  → OU utilisateur mentionne explicitement une tâche spécifique (ex: "mettre à jour tâche X")
  → OU contexte indique clairement quelle tâche (dans l'historique récent)
- Sinon → Toujours "general" pour laisser le LLM principal clarifier quelle tâche/projet
{context_section}
Message actuel : {message}{media_reminder}

Retourne UNIQUEMENT un JSON valide sans texte supplémentaire. Format :
{{"intent": "nom_intent", "confidence": 95}}

Exemple : {{"intent": "greeting", "confidence": 95}}"""

                response = await self.haiku.ainvoke(
                    [{"role": "user", "content": prompt}]
                )
                response_text = response.content.strip()

                # Log raw response for debugging
                log.debug(f"🤖 Haiku raw response: {response_text}")

                # Parse JSON response
                try:
                    # Try to extract JSON if there's extra text (sometimes LLMs add explanation)
                    # Find first { and last } to extract JSON object
                    start_idx = response_text.find("{")
                    end_idx = response_text.rfind("}")

                    if start_idx != -1 and end_idx != -1:
                        json_str = response_text[start_idx : end_idx + 1]
                        parsed = json.loads(json_str)
                        intent = parsed.get("intent", "general").lower()
                        confidence = float(parsed.get("confidence", 75)) / 100.0
                        log.info(
                            f"✅ JSON parsed successfully: intent={intent}, confidence={confidence}"
                        )
                    else:
                        raise ValueError("No JSON object found in response")

                except Exception as e:
                    log.warning(f"⚠️ JSON parsing failed: {e}")
                    log.warning(
                        f"📝 Raw response (first 200 chars): {response_text[:200]}"
                    )
                    # Fallback to old format if JSON parsing fails
                    response_lower = response_text.lower()
                    if ":" in response_lower:
                        parts = response_lower.split(":")
                        intent = parts[0].strip()
                        try:
                            # Extract just the number (handles "95" or "95%" or "95 explanation")
                            conf_text = (
                                parts[1].strip().split()[0]
                                if parts[1].strip()
                                else "75"
                            )
                            conf_text = conf_text.replace("%", "")
                            confidence = float(conf_text) / 100.0
                        except BaseException:
                            confidence = 0.75
                    else:
                        intent = response_lower
                        confidence = 0.75

                log_prefix = "🔢" if is_menu_response else "🤖"
                log.info(
                    f"{log_prefix} Haiku classification: {intent} (confidence: {confidence})"
                )

            # Validate intent
            if intent not in INTENTS:
                log.warning(
                    f"Unknown intent '{intent}' returned, defaulting to 'general'"
                )
                intent = "general"
                confidence = 0.5  # Low confidence for fallback

            # Get intent metadata
            intent_metadata = INTENTS[intent]

            result = {
                "intent": intent,
                "confidence": confidence,
                "requires_tools": intent_metadata.get("requires_tools", True),
                "tools": intent_metadata.get("tools", []),
                "requires_confirmation": intent_metadata.get(
                    "requires_confirmation", False
                ),
            }

            log.info(
                f"Classified intent: {intent} for message: '{message[:50]}...' (user: {user_id})"
            )

            # Save classification for analytics (async, don't wait)
            try:
                from src.integrations.supabase import supabase_client

                if user_id:
                    await supabase_client.log_intent_classification(
                        {
                            "subcontractor_id": user_id,
                            "message_text": message[:500],  # Limit length
                            "classified_intent": intent,
                            "confidence": confidence,  # Use actual confidence score
                        }
                    )
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
                "requires_confirmation": False,
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
