"""LLM-based context classifier for active sessions.

Determines if user messages continue active specialized sessions
or represent intent changes that should exit the session.
"""

import json
import re
from typing import Any, Dict, Optional

from langchain_anthropic import ChatAnthropic
from langsmith import traceable

from src.config import settings
from src.utils.logger import log


class ContextClassifier:
    """LLM-based classifier to determine message context relative to active session."""

    def __init__(self):
        """Initialize context classifier with Haiku for speed and cost efficiency."""
        self.llm = ChatAnthropic(
            model="claude-haiku-4-20250514",  # Fast, cheap, smart enough
            api_key=settings.anthropic_api_key,
            temperature=0.1,  # Low temperature for consistent classification
            max_tokens=500,  # Small output needed
        )
        log.info("✅ Context Classifier initialized (Haiku)")

    @traceable(name="Context Classification (Haiku 4)")
    async def classify_message_context(
        self,
        message: str,
        session_type: str,
        session_state: str,
        last_bot_message: str,
        expecting_response: bool,
        session_metadata: Optional[Dict[str, Any]] = None,
        user_language: str = "fr",
    ) -> Dict[str, Any]:
        """
        Use LLM to classify if message is in-context or represents intent change.

        Args:
            message: User's message text
            session_type: Type of active session (e.g., "progress_update")
            session_state: Current FSM state (e.g., "awaiting_action")
            last_bot_message: Last message sent by bot
            expecting_response: Whether bot is waiting for user response
            session_metadata: Optional additional session context
            user_language: User's language code

        Returns:
            Dict with:
                - context: "IN_CONTEXT" | "OUT_OF_CONTEXT"
                - confidence: 0.0-1.0
                - reasoning: Explanation of classification
                - intent_change_type: Type of intent change if OUT_OF_CONTEXT
                - issue_mentioned: Whether issue/problem was mentioned
                - issue_severity: "low" | "medium" | "high" (if issue mentioned)
                - issue_description: Brief description of issue (if mentioned)
                - suggest_user_choice: Whether to ask user how to handle issue
                - suggest_incident_report: Whether to suggest creating incident (deprecated)
                - suggest_task_switch: Whether to suggest task/project switch
        """
        prompt = self._build_classification_prompt(
            message=message,
            session_type=session_type,
            session_state=session_state,
            last_bot_message=last_bot_message,
            expecting_response=expecting_response,
            session_metadata=session_metadata,
            user_language=user_language,
        )

        try:
            # Call LLM
            response = await self.llm.ainvoke(prompt)

            # Parse JSON response
            content = response.content
            if isinstance(content, list):
                content = content[0]["text"] if content else "{}"

            # Extract JSON from response (might be wrapped in markdown)
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group(0))
            else:
                log.warning("⚠️ Could not parse LLM response as JSON, using fallback")
                result = {
                    "context": "IN_CONTEXT",
                    "confidence": 0.5,
                    "reasoning": "Could not parse LLM response",
                    "intent_change_type": None,
                    "issue_mentioned": False,
                    "issue_severity": None,
                    "issue_description": None,
                    "suggest_user_choice": False,
                    "suggest_incident_report": False,
                    "suggest_task_switch": False,
                }

            log.info(
                f"🤖 Context Classification: {result.get('context')} "
                f"({result.get('confidence', 0):.0%})"
            )
            log.info(f"   Reasoning: {result.get('reasoning', 'N/A')}")

            if result.get("intent_change_type"):
                log.info(f"   Intent change detected: {result['intent_change_type']}")
            if result.get("issue_mentioned"):
                severity = result.get("issue_severity", "unknown")
                description = result.get("issue_description", "N/A")
                log.info(f"   ⚠️ Issue mentioned: {description} (severity: {severity})")
            if result.get("suggest_user_choice"):
                log.info("   💡 Suggesting user choice for issue handling")
            if result.get("suggest_incident_report"):
                log.info("   📋 Suggesting incident report (deprecated)")
            if result.get("suggest_task_switch"):
                log.info("   🔄 Suggesting task/project switch")

            return result

        except Exception as e:
            log.error(f"Error in context classification: {e}")
            # Fallback: assume IN_CONTEXT to avoid disrupting flow
            return {
                "context": "IN_CONTEXT",
                "confidence": 0.5,
                "reasoning": f"Error during classification: {str(e)}",
                "intent_change_type": None,
                "issue_mentioned": False,
                "issue_severity": None,
                "issue_description": None,
                "suggest_user_choice": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }

    def _build_classification_prompt(
        self,
        message: str,
        session_type: str,
        session_state: str,
        last_bot_message: str,
        expecting_response: bool,
        session_metadata: Optional[Dict[str, Any]],
        user_language: str,
    ) -> str:
        """Build the classification prompt based on session type."""

        # Base context
        prompt = f"""Tu es un classificateur de contexte conversationnel pour un assistant WhatsApp.

**TÂCHE**: Déterminer si le message de l'utilisateur continue la session active ou représente un changement d'intention.

**CONTEXTE DE LA SESSION ACTIVE**:
- Type de session: {session_type}
- État actuel: {session_state}
- Dernier message du bot: "{last_bot_message}"
- Bot attend une réponse: {"Oui" if expecting_response else "Non"}
- Langue de l'utilisateur: {user_language}

**MESSAGE DE L'UTILISATEUR**:
"{message}"

"""

        # Session-specific guidance
        if session_type == "progress_update":
            prompt += """
**CONTEXTE SPÉCIFIQUE - Mise à jour de progression**:
L'utilisateur est en train de mettre à jour la progression d'une tâche (photos, commentaires, statut).

**SIGNAUX IN_CONTEXT (message continue la session)**:
- Réponses courtes: "oui", "non", "ok", "d'accord", "voici"
- Réponses numériques: "1", "2", "3" (sélection d'options)
- Actions de progression: mentions de photos, commentaires, complétion
- Confirmations ou clarifications sur la tâche actuelle
- Ajout d'informations complémentaires

**SIGNAUX OUT_OF_CONTEXT (changement d'intention)**:
- Navigation: "changer de tâche/projet", "voir mes projets", "liste des tâches"
- Nouvelles actions: "signaler un problème", "voir les documents", "créer un rapport"
- Questions générales: "quels sont mes chantiers?", "comment faire X?"
- Salutations nouvelles: "bonjour", "salut" (redémarrage)
- Demandes d'aide: "j'ai besoin d'aide", "parler avec quelqu'un"

**DÉTECTION SPÉCIALE - Problèmes/Incidents avec ÉVALUATION DE GRAVITÉ**:
Si l'utilisateur mentionne un problème, une anomalie, un incident, une panne, quelque chose qui ne fonctionne pas:

1. Mettre issue_mentioned = true
2. Évaluer la gravité (issue_severity):
   - **high**: Dangers pour la sécurité (électrique, structure, fuite d'eau importante, chute possible),
               travail complètement bloqué, risques pour les personnes
   - **medium**: Problèmes de qualité, matériaux/outils manquants, retards,
                 fonctionnalités qui ne marchent pas correctement
   - **low**: Détails cosmétiques, observations mineures, petites imperfections,
              suggestions d'amélioration
3. Extraire issue_description: description courte du problème (5-10 mots max)
   - Exemples: "fuite d'eau", "mur fissuré", "peinture imparfaite", "vis manquantes"
4. Mettre suggest_user_choice = true (on demande à l'utilisateur comment procéder)
5. NE PAS mettre suggest_incident_report = true (c'est deprecated, on utilise suggest_user_choice)

Exemples avec gravité:
- "il y a une fuite d'eau" → high, "fuite d'eau", suggest_user_choice=true
- "attention danger électrique" → high, "danger électrique", suggest_user_choice=true
- "le mur est fissuré" → high, "mur fissuré", suggest_user_choice=true
- "il manque des vis" → medium, "vis manquantes", suggest_user_choice=true
- "la peinture n'est pas belle" → low, "peinture imparfaite", suggest_user_choice=true
- "je ne comprends pas" → PAS UN INCIDENT, issue_mentioned=false

**DÉTECTION SPÉCIALE - Changement de tâche/projet**:
Si l'utilisateur veut explicitement changer de tâche ou projet:
- intent_change_type = "change_task" ou "change_project"
- suggest_task_switch = true
"""

        elif session_type == "incident_report":
            prompt += """
**CONTEXTE SPÉCIFIQUE - Signalement d'incident**:
L'utilisateur est en train de créer un rapport d'incident (photos, description, localisation).

**SIGNAUX IN_CONTEXT**:
- Envoi de photos/vidéos
- Descriptions du problème
- Informations de localisation
- Réponses aux questions du bot sur l'incident

**SIGNAUX OUT_OF_CONTEXT**:
- Veut voir autre chose: "voir mes tâches", "liste des projets"
- Veut faire autre chose: "mettre à jour ma progression"
- Annulation: "annuler", "retour", "laisse tomber"
"""

        # Common special cases
        prompt += """

**CAS PARTICULIERS & NUANCES**:

1. **Acronymes français**:
   - "RAS" = Rien À Signaler → Tout va bien → IN_CONTEXT, issue_mentioned = false
   - "TBD", "A voir", "On verra" → IN_CONTEXT

2. **Demandes d'aide ambiguës**:
   - "Aide" quand le bot vient de poser une question → IN_CONTEXT (clarification)
   - "Aide" sans question récente → OUT_OF_CONTEXT, intent_change_type="escalate"
   - "J'ai besoin d'aide" (phrase complète) → OUT_OF_CONTEXT, intent_change_type="escalate"

3. **Salutations en cours de session**:
   - "Bonjour", "Salut", "Hello" → OUT_OF_CONTEXT (redémarrage)
   - Sauf si c'est la première interaction → IN_CONTEXT

4. **Messages très courts** ("ok", "bien", "..."):
   - Si le bot attend une réponse → IN_CONTEXT (confiance moyenne 0.65-0.75)
   - Contexte doit guider la décision

5. **Expressions de difficulté**:
   - "C'est compliqué", "Je ne comprends pas", "Comment ça?" → IN_CONTEXT
   - L'utilisateur a besoin de clarification, pas de sortir
   - Sauf si suivi de "je veux parler à quelqu'un" → OUT_OF_CONTEXT

6. **Expressions de finalité**:
   - "Merci", "C'est bon", "Parfait" → IN_CONTEXT (conclusion positive)
   - Mais si suivi de nouvelle demande: "Merci. Maintenant je veux..." → OUT_OF_CONTEXT

**FORMAT DE RÉPONSE** (JSON uniquement, pas de texte avant ou après):
{{
    "context": "IN_CONTEXT" | "OUT_OF_CONTEXT",
    "confidence": 0.0-1.0,
    "reasoning": "Explication claire de ta décision en 1-2 phrases",
    "intent_change_type": null | "change_task" | "change_project" | "report_incident" | "view_documents" | "escalate" | "general",
    "issue_mentioned": true | false,
    "issue_severity": null | "low" | "medium" | "high",
    "issue_description": null | "courte description du problème",
    "suggest_user_choice": true | false,
    "suggest_incident_report": false,
    "suggest_task_switch": true | false
}}

**RÈGLES**:
1. Si le message est une réponse directe à la question du bot → IN_CONTEXT (haute confiance)
2. Si le message contient des mots de navigation claire → OUT_OF_CONTEXT (haute confiance)
3. Si ambiguë (ex: "ok" seul) → IN_CONTEXT mais confiance moyenne (0.6)
4. Confiance haute = 0.85-1.0, moyenne = 0.6-0.84, faible = 0.0-0.59
5. Toujours remplir intent_change_type si context = OUT_OF_CONTEXT
6. Si problème détecté: remplir issue_severity, issue_description, suggest_user_choice = true
7. Être intelligent: "j'ai fini mais il y a une fuite" = OUT_OF_CONTEXT + issue (high severity) + suggest_user_choice

Réponds UNIQUEMENT avec le JSON, rien d'autre.
"""

        return prompt


# Global instance
context_classifier = ContextClassifier()
