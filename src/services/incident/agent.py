"""Specialized agent for incident reporting multi-step flows."""

from typing import Any, Dict, Optional

# isort: off
from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore[attr-defined]
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic

# isort: on

from src.agent.tools import escalate_to_human_tool
from src.config import settings
from src.services.incident.tools import (
    add_incident_comment_tool,
    add_incident_image_tool,
    exit_incident_session_tool,
    finalize_incident_tool,
    get_active_project_for_incident_tool,
    start_incident_session_tool,
)
from src.utils.logger import log

INCIDENT_REPORT_PROMPT = """Tu es un assistant spécialisé pour aider les utilisateurs à signaler des incidents/problèmes.

OBJECTIF : Accompagner l'utilisateur étape par étape pour signaler un incident avec :
1. 📸 Photos (une ou plusieurs)
2. 💬 Commentaires/descriptions (texte ou transcription vocale)
3. ✅ Finalisation du rapport

CONTEXTE UTILISATEUR :
- User ID : {user_id}
- Nom : {user_name}
- Langue : {language}

RÈGLES IMPORTANTES :

1. **Contexte de projet** :
   - TOUJOURS appeler get_active_project_for_incident_tool EN PREMIER pour vérifier si l'utilisateur a un projet actif (7h)
   - Si active_project existe : Utilise start_incident_session_tool IMMÉDIATEMENT avec le project_id retourné
   - Si aucun contexte : Tu ne peux pas gérer cette situation - utilise exit_incident_session_tool pour laisser le LLM principal gérer
   - NE JAMAIS demander de sélectionner un projet si le contexte existe déjà!

2. **Collecte flexible de données** :
   - L'utilisateur peut envoyer plusieurs photos et commentaires dans n'importe quel ordre
   - Accepte TOUT : photo seule, commentaire seul, ou les deux
   - Après chaque action, encourage l'utilisateur : "Ajoutez plus de détails ou dites 'terminé'"
   - Sois patient et accueillant - ne presse jamais l'utilisateur

3. **Messages vocaux** :
   - Les messages vocaux sont déjà transcrits par le système
   - Utilise le texte transcrit comme commentaire
   - Confirme toujours : "Commentaire ajouté : '[texte transcrit]'"

4. **Images** :
   - Quand l'utilisateur envoie une image, elle est déjà uploadée en storage
   - Tu reçois l'URL publique
   - Utilise add_incident_image_tool avec cette URL
   - L'utilisateur peut envoyer plusieurs images (pas de limite)

5. **Détection de finalisation** :
   - Cherche ces mots/expressions : "terminé", "fini", "c'est tout", "ça suffit", "voilà"
   - Quand détecté, appelle finalize_incident_tool
   - Affiche un résumé (nombre de photos, nombre de commentaires)
   - Remercie l'utilisateur

6. **Descriptions du problème** :
   - Encourage l'utilisateur à décrire ce qui ne va pas
   - Exemples de questions utiles :
     * "Que s'est-il passé ?"
     * "Depuis quand avez-vous remarqué ce problème ?"
     * "Y a-t-il des risques de sécurité ?"
   - Mais reste flexible - accepte toute description

7. **Messages clairs** :
   - Utilise des emojis pour clarifier
   - Confirme chaque action effectuée
   - Résume à la fin
   - ⚠️ IMPORTANT: N'utilise JAMAIS de markdown (**, *, _, etc.) dans tes réponses - écris en texte simple uniquement

8. **CRITIQUE - Limites WhatsApp pour listes interactives**:
   ⚠️ TOUTES les options que tu proposes doivent faire MAX 20 caractères (incluant espaces et emojis)
   - WhatsApp tronque automatiquement au-delà de 24 caractères
   - Exemples CORRECTS (≤20 chars):
     ✅ "Oui, terminé" (12)
     ✅ "Ajouter photo" (13)
     ✅ "Ajouter détails" (15)
     ✅ "Annuler" (7)
   - Exemples INCORRECTS (>20 chars - SERONT TRONQUÉS):
     ❌ "Ajouter plus de photos" (22 chars)
     ❌ "Oui je veux continuer" (22 chars)

9. **Gestion des erreurs** :
   - Si tu rencontres une erreur technique (tool qui échoue), dis : "Désolé, je rencontre un problème technique. 😔"
   - Propose IMMÉDIATEMENT : "Souhaitez-vous parler avec quelqu'un de l'équipe ?"
   - Utilise escalate_to_human_tool avec reason="Erreur technique lors du signalement d'incident"

⚠️⚠️⚠️ RÈGLES CRITIQUES - LIMITES DE MA RESPONSABILITÉ ⚠️⚠️⚠️

**CE QUE JE PEUX FAIRE (Ma responsabilité)** :
✅ Ajouter des photos pour l'incident EN COURS
✅ Ajouter des commentaires/descriptions pour l'incident EN COURS
✅ Finaliser le rapport d'incident EN COURS
✅ Répondre à des questions sur l'incident EN COURS
✅ Aider avec des problèmes techniques (erreurs)

**CE QUE JE NE PEUX PAS FAIRE (Hors de ma responsabilité)** :
❌ Changer de projet
❌ Lister les projets disponibles
❌ Lister les tâches/lots
❌ Voir les documents ou plans
❌ Mettre à jour la progression d'une tâche/lot
❌ Répondre à des questions générales sur le système
❌ Gérer des demandes concernant un AUTRE incident

**DÉTECTION CRITIQUE - Quand SORTIR de ma session** :

Si l'utilisateur demande QUELQUE CHOSE QUE JE NE PEUX PAS FAIRE :
→ NE PAS essayer de le faire moi-même
→ APPELER IMMÉDIATEMENT exit_incident_session_tool
→ ⚠️ IMPORTANT: Ne génère AUCUN message après avoir appelé ce tool! Le tool s'occupe de tout.

Exemples de détection :
- "autre projet" / "changer de projet" → Hors scope (changer projet)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_wants_different_project")
  → ⚠️ STOP - ne dis rien d'autre après!
- "voir mes projets" / "liste des projets" → Hors scope (lister projets)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_wants_list_projects")
  → ⚠️ STOP - ne dis rien d'autre après!
- "mettre à jour" / "ajouter progression" → Hors scope (progress update)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_wants_progress_update")
  → ⚠️ STOP - ne dis rien d'autre après!
- "voir mes tâches" / "liste des lots" → Hors scope (lister tâches)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_wants_list_tasks")
  → ⚠️ STOP - ne dis rien d'autre après!
- "bonjour" / "salut" → Hors scope (nouvelle conversation)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_greeting_new_session")
  → ⚠️ STOP - ne dis rien d'autre après!
- "voir les documents" → Hors scope (documents)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_wants_documents")
  → ⚠️ STOP - ne dis rien d'autre après!
- "annuler" / "abandonner" → Hors scope (annulation)
  → Appeler exit_incident_session_tool(user_id="{user_id}", reason="user_cancelled")
  → ⚠️ STOP - ne dis rien d'autre après!

Ce tool va :
1. Fermer ma session proprement avec une transition FSM validée
2. Transmettre la demande au LLM principal (SILENCIEUSEMENT - tu ne dis rien!)
3. Le LLM principal a TOUS les outils nécessaires (list_projects, list_tasks, documents, etc.)

OUTILS DISPONIBLES :
- get_active_project_for_incident_tool : Vérifier le contexte projet actif (7h) - UTILISE CECI EN PREMIER!
- start_incident_session_tool : Démarrer une session de signalement d'incident
- add_incident_image_tool : Ajouter une photo
- add_incident_comment_tool : Ajouter un commentaire/description
- finalize_incident_tool : Finaliser le rapport et terminer la session
- escalate_to_human_tool : Escalader vers un humain en cas d'erreur ou si l'utilisateur demande
- exit_incident_session_tool : SORTIR de ma session quand demande hors de ma responsabilité

Historique de conversation :
{chat_history}

Message actuel :
{input}

{agent_scratchpad}
"""


class IncidentAgent:
    """Specialized agent for incident reporting."""

    def __init__(self):
        """Initialize incident reporting agent."""
        self.llm = ChatAnthropic(
            model="claude-opus-4-5-20251101",  # Use Opus 4.5
            api_key=settings.anthropic_api_key,
            temperature=0.3,  # Slightly creative for natural conversation
        )

        # Create tools list
        self.tools = [
            get_active_project_for_incident_tool,
            start_incident_session_tool,
            add_incident_image_tool,
            add_incident_comment_tool,
            finalize_incident_tool,
            escalate_to_human_tool,
            exit_incident_session_tool,
        ]

        # Create prompt
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", INCIDENT_REPORT_PROMPT),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=10,
            handle_parsing_errors=True,
            return_intermediate_steps=True,  # CRITICAL: Need this to analyze tool calls!
        )

        log.info("✅ Incident Agent initialized")

    async def process(
        self,
        user_id: str,
        user_name: str,
        language: str,
        message: str,
        chat_history: list = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process incident report request.

        Args:
            user_id: User ID
            user_name: User name
            language: User language
            message: User message
            chat_history: Recent conversation history
            media_url: Optional media URL (image uploaded by user)
            media_type: Optional media type

        Returns:
            Response dict with message and metadata
        """
        try:
            log.info(
                f"🤖 Incident Agent starting\n"
                f"   User: {user_name} ({user_id[:8]}...)\n"
                f"   Message: {message[:100]}{'...' if len(message) > 100 else ''}\n"
                f"   Language: {language}\n"
                f"   Media: {media_type or 'none'}"
            )

            # Enhance message with media context
            enhanced_message = message
            if media_url and "image" in (media_type or ""):
                enhanced_message = f"{message}\n\n[SYSTEM: L'utilisateur a envoyé une image. URL: {media_url}]"
                log.info("   📸 Enhanced message with image URL")

            # Run agent
            log.info("   ⚙️ Invoking agent executor...")
            result = await self.agent_executor.ainvoke(
                {
                    "input": enhanced_message,
                    "user_id": user_id,
                    "user_name": user_name,
                    "language": language,
                    "chat_history": chat_history or [],
                }
            )

            log.info(f"🤖 Agent result output type: {type(result['output'])}")
            log.info(
                f"🤖 Agent result output: {result['output'][:200] if isinstance(result['output'], str) else str(result['output'])[:200]}"
            )

            # Extract message text from result
            # Opus 4.5 sometimes returns structured output [{"text": "..."}] instead of plain string
            output = result["output"]
            if (
                isinstance(output, list)
                and len(output) > 0
                and isinstance(output[0], dict)
                and "text" in output[0]
            ):
                message_text = output[0]["text"]
                log.info(
                    f"📝 Extracted text from structured output: {message_text[:100]}"
                )
            elif isinstance(output, str):
                message_text = output
            else:
                log.warning(f"⚠️ Unexpected output format: {type(output)}")
                message_text = str(output)

            response = {
                "success": True,
                "message": message_text,
                "agent_used": "incident",
                "response_type": "text",  # Default to plain text
            }

            # Analyze intermediate_steps to determine response type
            intermediate_steps = result.get("intermediate_steps", [])
            log.info(f"🔍 Analyzing {len(intermediate_steps)} intermediate steps")

            # CRITICAL: Check for exit tool FIRST in a separate pass
            for action, observation in intermediate_steps:
                if not hasattr(action, "tool"):
                    continue

                tool_name = action.tool

                # Case 0: Exit session called (CRITICAL - check first!)
                if tool_name == "exit_incident_session_tool":
                    log.info("🚪 Agent called exit_incident_session_tool")
                    log.info("   → Session exited, triggering reroute to main LLM")
                    return {
                        "success": False,  # Signals fallback needed
                        "reroute_reason": "out_of_scope",
                        "original_message": message,
                        "session_exited": True,
                        "agent_used": "incident",
                    }

            # Now process other tools
            for action, observation in intermediate_steps:
                if not hasattr(action, "tool"):
                    continue

                tool_name = action.tool

                # Skip exit tool - already handled above
                if tool_name == "exit_incident_session_tool":
                    continue

                # Case 1: Escalation called
                if tool_name == "escalate_to_human_tool":
                    response["escalation"] = True
                    response["response_type"] = "escalation"
                    log.info(
                        "🔧 Agent called escalate_to_human_tool → Setting escalation flag"
                    )
                    break

                # Case 2: Session started
                elif tool_name == "start_incident_session_tool":
                    if "Session de signalement d'incident démarrée" in observation:
                        response["response_type"] = "session_started"
                        log.info("✅ Incident session started")

                # Case 3: Incident finalized
                elif tool_name == "finalize_incident_tool":
                    if "Incident signalé avec succès" in observation:
                        response["response_type"] = "incident_completed"
                        log.info("✅ Incident report finalized")

            log.info(
                f"✅ Returning response with response_type: {response.get('response_type')}"
            )

            return response

        except Exception as e:
            log.error(f"Error in incident agent: {e}")
            import traceback

            log.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "message": "❌ Erreur lors du signalement. Veuillez réessayer.",
                "error": str(e),
            }


# Global instance
incident_agent = IncidentAgent()
