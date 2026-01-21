"""Specialized agent for progress update multi-step flows."""

from typing import Any, Dict, Optional

# isort: off
from langchain.agents import AgentExecutor, create_tool_calling_agent  # type: ignore[attr-defined]
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic

# isort: on

from src.agent.tools import escalate_to_human_tool
from src.config import settings
from src.services.progress_update.tools import (
    add_progress_comment_tool,
    add_progress_image_tool,
    exit_progress_update_session_tool,
    get_active_task_context_tool,
    get_progress_update_context_tool,
    mark_task_complete_tool,
    start_progress_update_session_tool,
)
from src.utils.logger import log

PROGRESS_UPDATE_PROMPT = """Tu es un assistant spécialisé pour guider les utilisateurs dans la mise à jour de leurs tâches.

OBJECTIF : Accompagner l'utilisateur étape par étape pour mettre à jour la progression d'une tâche avec :
1. 📸 Photos (via upload)
2. 💬 Commentaires (texte ou transcription vocale)
3. ✅ Changement de statut (marquer comme terminé)

CONTEXTE UTILISATEUR :
- User ID : {user_id}
- Nom : {user_name}
- Langue : {language}

RÈGLES IMPORTANTES :

1. **Contexte de projet/tâche** :
   - TOUJOURS appeler get_active_task_context_tool EN PREMIER pour vérifier si l'utilisateur a déjà un projet/tâche actif
   - Si active_task_id existe : Utilise start_progress_update_session_tool IMMÉDIATEMENT avec les IDs retournés
   - Si seulement active_project_id existe : Demande quelle tâche l'utilisateur souhaite mettre à jour
   - Si aucun contexte : Demande d'abord le projet, puis la tâche
   - NE JAMAIS demander de sélectionner un projet/tâche si le contexte existe déjà!

2. **Actions multiples** :
   - L'utilisateur peut effectuer plusieurs actions (photo + commentaire + compléter)
   - Après chaque action, suggère les actions restantes
   - Sois intelligent : si l'utilisateur ajoute 3 photos et un commentaire, propose "Voulez-vous marquer cette tâche comme terminée ?"

3. **Messages vocaux** :
   - Les messages vocaux sont déjà transcrits par le système
   - Utilise le texte transcrit comme commentaire
   - Confirme toujours : "Commentaire ajouté : '[texte transcrit]'"

4. **Images** :
   - Quand l'utilisateur envoie une image, elle est déjà uploadée en storage
   - Tu reçois l'URL publique
   - Utilise add_progress_image_tool avec cette URL

5. **État de la session** :
   - Utilise get_progress_update_context_tool pour voir ce qui a déjà été fait
   - Adapte tes suggestions en fonction
   - Si tout est fait (image + commentaire + complété), félicite et termine

6. **Confirmation avant completion** :
   - Si l'utilisateur dit en texte libre "termine" ou "c'est fini", demande confirmation : "Voulez-vous marquer cette tâche comme terminée ?"
   - MAIS si tu vois "[UTILISATEUR A CLIQUÉ: ✅ Marquer terminé]" ou similaire dans le message, c'est DÉJÀ une confirmation explicite
   - Dans ce cas, appelle mark_task_complete_tool DIRECTEMENT sans redemander de confirmation
   - Ne dis JAMAIS "Je dois d'abord confirmer" quand l'utilisateur a déjà cliqué sur un bouton d'action

7. **Fluidité** :
   - Sois naturel et conversationnel
   - Pas de menus rigides - adapte-toi au contexte
   - Si l'utilisateur dit "ajoute cette photo et marque comme terminé", fais les deux

8. **Messages clairs** :
   - Utilise des emojis pour clarifier
   - Confirme chaque action effectuée
   - Résume à la fin
   - ⚠️ IMPORTANT: N'utilise JAMAIS de markdown (**, *, _, etc.) dans tes réponses - écris en texte simple uniquement

9. **CRITIQUE - Limites WhatsApp pour listes interactives**:
   ⚠️ TOUTES les options que tu proposes doivent faire MAX 20 caractères (incluant espaces et emojis)
   - WhatsApp tronque automatiquement au-delà de 24 caractères
   - Pour éviter des textes coupés comme "Changer de tâche (même p...", utilise des formulations courtes
   - Exemples CORRECTS (≤20 chars):
     ✅ "Oui, c'est ça" (13)
     ✅ "Autre tâche" (11)
     ✅ "Autre projet" (12)
     ✅ "Marquer terminé" (15)
     ✅ "Ajouter photo" (13)
     ✅ "Non merci" (9)
   - Exemples INCORRECTS (>20 chars - SERONT TRONQUÉS):
     ❌ "Changer de tâche (même projet)" (31 chars)
     ❌ "Mettre à jour cette tâche" (27 chars)
     ❌ "Oui je veux continuer" (22 chars)
   - Sois bref et direct dans TOUTES tes options de liste!

**IMPORTANT - Format des listes de tâches** :
   - Quand tu présentes des tâches à l'utilisateur, utilise un format SIMPLE avec des nombres :
   1. Tâche A
   2. Tâche B
   3. Tâche C
   - PAS de tirets, PAS de [ID: xxx], juste le numéro et le titre
   - Exemple correct :
     Tâches disponibles :
     1. Installer l'électricité
     2. Réparer la fuite
     3. Peindre le mur

10. **Gestion des erreurs** :
   - Si tu rencontres une erreur technique (tool qui échoue), dis : "Désolé, je rencontre un problème technique. 😔"
   - Propose IMMÉDIATEMENT : "Souhaitez-vous parler avec quelqu'un de l'équipe ?"
   - Utilise escalate_to_human_tool avec reason="Erreur technique lors de la mise à jour de progression"

⚠️⚠️⚠️ RÈGLES CRITIQUES - LIMITES DE MA RESPONSABILITÉ ⚠️⚠️⚠️

**CE QUE JE PEUX FAIRE (Ma responsabilité)** :
✅ Ajouter des photos pour la tâche ACTIVE en cours
✅ Ajouter des commentaires pour la tâche ACTIVE en cours
✅ Marquer la tâche ACTIVE en cours comme terminée
✅ Répondre à des questions sur la tâche ACTIVE en cours
✅ Aider avec des problèmes techniques (erreurs)

**CE QUE JE NE PEUX PAS FAIRE (Hors de ma responsabilité)** :
❌ Changer de tâche ou de projet
❌ Lister les projets disponibles
❌ Lister les tâches disponibles
❌ Voir les documents ou plans
❌ Créer un rapport d'incident
❌ Répondre à des questions générales sur le système
❌ Gérer des demandes concernant une tâche DIFFÉRENTE

**DÉTECTION CRITIQUE - Quand SORTIR de ma session** :

Si l'utilisateur demande QUELQUE CHOSE QUE JE NE PEUX PAS FAIRE :
→ NE PAS essayer de le faire moi-même
→ APPELER IMMÉDIATEMENT exit_progress_update_session_tool
→ ⚠️ IMPORTANT: Ne génère AUCUN message après avoir appelé ce tool! Le tool s'occupe de tout.

Exemples de détection :
- "je souhaite mettre a jour une autre tache" → Hors scope (autre tâche)
  → Appeler exit_progress_update_session_tool(user_id="{user_id}", reason="user_wants_different_task")
  → ⚠️ STOP - ne dis rien d'autre après!
- "voir mes projets" → Hors scope (lister projets)
  → Appeler exit_progress_update_session_tool(user_id="{user_id}", reason="user_wants_list_projects")
  → ⚠️ STOP - ne dis rien d'autre après!
- "autre projet" → Hors scope (changer projet)
  → Appeler exit_progress_update_session_tool(user_id="{user_id}", reason="user_wants_different_project")
  → ⚠️ STOP - ne dis rien d'autre après!
- "bonjour" → Hors scope (nouvelle conversation)
  → Appeler exit_progress_update_session_tool(user_id="{user_id}", reason="user_greeting_new_session")
  → ⚠️ STOP - ne dis rien d'autre après!
- "voir les documents" → Hors scope (documents)
  → Appeler exit_progress_update_session_tool(user_id="{user_id}", reason="user_wants_documents")
  → ⚠️ STOP - ne dis rien d'autre après!
- "il y a un problème avec..." → Hors scope (nouveau incident)
  → Appeler exit_progress_update_session_tool(user_id="{user_id}", reason="user_reporting_new_incident")
  → ⚠️ STOP - ne dis rien d'autre après!

Ce tool va :
1. Fermer ma session proprement avec une transition FSM validée
2. Transmettre la demande au LLM principal (SILENCIEUSEMENT - tu ne dis rien!)
3. Le LLM principal a TOUS les outils nécessaires (list_projects, list_tasks, documents, etc.)

OUTILS DISPONIBLES :
- get_active_task_context_tool : Vérifier le contexte actif (projet/tâche) - UTILISE CECI EN PREMIER!
- get_progress_update_context_tool : Voir l'état de la session de mise à jour
- start_progress_update_session_tool : Démarrer une session pour une tâche
- add_progress_image_tool : Ajouter une photo
- add_progress_comment_tool : Ajouter un commentaire
- mark_task_complete_tool : Marquer comme terminé
- escalate_to_human_tool : Escalader vers un humain en cas d'erreur ou si l'utilisateur demande
- exit_progress_update_session_tool : SORTIR de ma session quand demande hors de ma responsabilité

Historique de conversation :
{chat_history}

Message actuel :
{input}

{agent_scratchpad}
"""


class ProgressUpdateAgent:
    """Specialized agent for progress updates."""

    def __init__(self):
        """Initialize progress update agent."""
        self.llm = ChatAnthropic(
            model="claude-opus-4-5-20251101",  # Use Opus 4.5 (Sonnet 3.5 not working)
            api_key=settings.anthropic_api_key,
            temperature=0.3,  # Slightly creative for natural conversation
        )

        # Create tools list
        self.tools = [
            get_active_task_context_tool,
            get_progress_update_context_tool,
            start_progress_update_session_tool,
            add_progress_image_tool,
            add_progress_comment_tool,
            mark_task_complete_tool,
            escalate_to_human_tool,
            exit_progress_update_session_tool,
        ]

        # Create prompt
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", PROGRESS_UPDATE_PROMPT),
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

        log.info("✅ Progress Update Agent initialized")

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
        """Process progress update request.

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
                f"🤖 Progress Update Agent starting\n"
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
                "agent_used": "progress_update",
                "response_type": "text",  # Default to plain text
            }

            # Analyze intermediate_steps to determine response type
            intermediate_steps = result.get("intermediate_steps", [])
            log.info(f"🔍 Analyzing {len(intermediate_steps)} intermediate steps")

            # CRITICAL: Check for exit tool FIRST in a separate pass
            # This prevents early breaks from other tools from blocking exit detection
            for action, observation in intermediate_steps:
                if not hasattr(action, "tool"):
                    continue

                tool_name = action.tool

                # Case 0: Exit session called (CRITICAL - check first!)
                if tool_name == "exit_progress_update_session_tool":
                    log.info("🚪 Agent called exit_progress_update_session_tool")
                    log.info("   → Session exited, triggering reroute to main LLM")
                    return {
                        "success": False,  # Signals fallback needed
                        "reroute_reason": "out_of_scope",
                        "original_message": message,
                        "session_exited": True,
                        "agent_used": "progress_update",
                    }

            # Now process other tools
            for action, observation in intermediate_steps:
                if not hasattr(action, "tool"):
                    continue

                tool_name = action.tool

                # Skip exit tool - already handled above
                if tool_name == "exit_progress_update_session_tool":
                    continue

                # Case 1: Escalation called
                if tool_name == "escalate_to_human_tool":
                    response["escalation"] = True
                    response["response_type"] = "escalation"
                    log.info(
                        "🔧 Agent called escalate_to_human_tool → Setting escalation flag"
                    )
                    break

                # Case 2: Task confirmation or task list
                elif tool_name == "get_active_task_context_tool":
                    log.info("🔍 Checking get_active_task_context_tool observation")
                    log.info(
                        f"   Has 'Show the user this list': {'Show the user this list' in observation}"
                    )
                    log.info(
                        f"   Has 'CONFIRMATION NEEDED': {'CONFIRMATION NEEDED' in observation}"
                    )
                    log.info(f"   Has 'Number': {'Number' in observation}")
                    log.info(f"   Observation preview: {observation[:200]}")

                    # Check if this is a CONFIRMATION (Yes/No options)
                    if "CONFIRMATION NEEDED" in observation:
                        # This is a confirmation, not a task list
                        # Extract task_id and project_id from observation for routing
                        import re

                        task_id_match = re.search(
                            r"Task ID: ([a-zA-Z0-9-]+)", observation
                        )
                        project_id_match = re.search(
                            r"PlanRadar Project ID: ([a-zA-Z0-9-]+)", observation
                        )
                        task_title_match = re.search(r"Task: (.+)", observation)

                        confirmation_data = {}
                        if task_id_match:
                            confirmation_data["task_id"] = task_id_match.group(1)
                        if project_id_match:
                            confirmation_data["project_id"] = project_id_match.group(1)
                        if task_title_match:
                            confirmation_data["task_title"] = task_title_match.group(
                                1
                            ).strip()

                        # Add tool_outputs so message history search can find this
                        response["tool_outputs"] = [
                            {
                                "tool": "get_active_task_context_tool",
                                "output": {"confirmation": confirmation_data},
                            }
                        ]
                        response["response_type"] = "interactive_list"
                        response["list_type"] = "option"  # Use "option" not "tasks"
                        log.info(
                            "✅ Detected confirmation → response_type=interactive_list, list_type=option"
                        )
                        log.info(f"   Confirmation data: {confirmation_data}")
                        break

                    # Check if observation contains task list with IDs
                    elif (
                        "Show the user this list" in observation
                        and "Number" in observation
                    ):
                        # Extract task list from observation
                        import re

                        # Extract user-facing task list (simple format)
                        user_list_match = re.search(
                            r"Show the user this list.*?:\n((?:\d+\..+\n?)+)",
                            observation,
                            re.DOTALL,
                        )

                        # Extract ID mapping
                        id_mapping_match = re.search(
                            r"Task ID mapping.*?:\n((?:Number \d+.*\n?)+)",
                            observation,
                            re.DOTALL,
                        )

                        if user_list_match and id_mapping_match:
                            user_list = user_list_match.group(1).strip()
                            id_mapping = id_mapping_match.group(1).strip()

                            log.info(f"📋 Extracted user list: {user_list[:100]}")
                            log.info(f"🔗 Extracted ID mapping: {id_mapping[:100]}")

                            # Parse ID mapping: "Number 1 = ID abc-123"
                            id_pattern = r"Number (\d+) = ID ([a-f0-9-]+)"
                            id_matches = re.findall(id_pattern, id_mapping)

                            # Parse user list: "1. Task title"
                            task_pattern = r"(\d+)\.\s+(.+?)(?:\n|$)"
                            task_matches = re.findall(task_pattern, user_list)

                            log.info(
                                f"🔢 ID matches: {len(id_matches)}, Task matches: {len(task_matches)}"
                            )

                            if id_matches and task_matches:
                                # Build task data
                                tasks_data = []
                                id_map = dict(id_matches)  # {number: id}

                                for num, title in task_matches:
                                    task_id = id_map.get(num)
                                    if task_id:
                                        tasks_data.append(
                                            {"id": task_id, "title": title.strip()}
                                        )

                                if tasks_data:
                                    response["tool_outputs"] = [
                                        {
                                            "tool": "get_active_task_context_tool",
                                            "output": {"tasks": tasks_data},
                                        }
                                    ]
                                    response["list_type"] = "tasks"
                                    response["response_type"] = "interactive_list"
                                    log.info(
                                        f"📋 Extracted {len(tasks_data)} tasks for interactive list"
                                    )
                                    break

                    # Case 3: No tasks available, but agent provided numbered options
                    elif (
                        "NO tasks found" in observation
                        or "aucune tâche disponible" in observation.lower()
                    ):
                        response["response_type"] = "no_tasks_available"
                        log.info("⚠️ No tasks available in project")

                # Case 4: Session started - could show action menu
                elif tool_name == "start_progress_update_session_tool":
                    if "Session de mise à jour démarrée" in observation:
                        response["response_type"] = "session_started"
                        log.info("✅ Progress update session started")

            log.info(
                f"✅ Returning response with response_type: {response.get('response_type')}"
            )
            if response.get("list_type"):
                log.info(f"   list_type: {response.get('list_type')}")
            if response.get("tool_outputs"):
                log.info(f"   tool_outputs: {len(response.get('tool_outputs'))} items")

            return response

        except Exception as e:
            log.error(f"Error in progress update agent: {e}")
            import traceback

            log.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "message": "❌ Erreur lors de la mise à jour. Veuillez réessayer.",
                "error": str(e),
            }


# Global instance
progress_update_agent = ProgressUpdateAgent()
