"""Specialized LangChain tools for incident reporting agent."""

from typing import Optional

from langchain.tools import tool

from src.integrations.supabase import supabase_client
from src.services.incident.state import incident_state
from src.services.incident.storage import incident_storage
from src.services.project_context import project_context_service
from src.utils.logger import log


@tool
async def get_active_project_for_incident_tool(user_id: str) -> str:
    """Check if user has an active project context (7-hour window).

    This should be called FIRST before asking user to select a project.
    Returns the active project info if available, or indicates no active project.

    Args:
        user_id: User ID

    Returns:
        Active project information or message indicating no active project
    """
    try:
        # Check for active project (7-hour expiration)
        active_project_id = await project_context_service.get_active_project(user_id)

        if active_project_id:
            # User has active project - get details
            project = await supabase_client.get_project(
                active_project_id, user_id=user_id
            )
            if project:
                project_name = project.get("nom", "Unknown Project")
                planradar_project_id = project.get("planradar_project_id")

                return f"""✅ ACTIVE PROJECT FOUND:
Project: {project_name}
Project ID: {active_project_id}
PlanRadar Project ID: {planradar_project_id}

AGENT INSTRUCTIONS:
Use start_incident_session_tool with project_id={active_project_id} to begin incident reporting.
Then ask user: "Décrivez le problème ou envoyez une photo."
"""

        # No active project context
        return """❌ NO ACTIVE PROJECT CONTEXT

AGENT INSTRUCTIONS:
Ask user: "Pour quel projet souhaitez-vous signaler un incident ?"
If user provides project name, you'll need to use exit_incident_session_tool
and let the main LLM handle project selection (you don't have list_projects_tool).
"""

    except Exception as e:
        log.error(f"Error in get_active_project_for_incident_tool: {e}")
        return f"""❌ TECHNICAL ERROR: {str(e)}

Tell the user: 'Désolé, je rencontre un problème technique. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate using escalate_to_human_tool."""


@tool
async def start_incident_session_tool(
    user_id: str, project_id: Optional[str] = None
) -> str:
    """Start a new incident reporting session.

    CRITICAL: Only call this tool when you have a valid project_id from
    get_active_project_for_incident_tool output. DO NOT call this tool
    if project_id is None or missing.

    Args:
        user_id: User ID (required)
        project_id: Project ID from get_active_project_for_incident_tool (REQUIRED)

    Returns:
        Success message or error message
    """
    try:
        # Validation: Ensure we have valid project_id
        if not project_id:
            log.error(
                f"❌ start_incident_session_tool called without project_id for user {user_id}"
            )
            return """❌ Impossible de démarrer la session: project_id manquant.

Utilise d'abord get_active_project_for_incident_tool pour obtenir l'ID du projet."""

        # Create incident record first
        incident_id = await incident_storage.create_incident(
            user_id=user_id, project_id=project_id
        )

        if not incident_id:
            return "❌ Impossible de créer l'incident. Veuillez réessayer."

        # Create session
        session_id = await incident_state.create_session(
            user_id=user_id, project_id=project_id, incident_id=incident_id
        )

        if session_id:
            log.info(
                f"✅ Started incident session {session_id} for user {user_id} "
                f"(incident: {incident_id})"
            )
            return """✅ Session de signalement d'incident démarrée !

Décrivez le problème ou envoyez une photo.
Vous pouvez ajouter plusieurs photos et commentaires.
Dites "terminé" quand vous avez fini."""
        else:
            return "❌ Impossible de démarrer la session. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error starting incident session: {e}")
        return f"""❌ TECHNICAL ERROR: {str(e)}

Tell the user: 'Désolé, je rencontre un problème technique pour démarrer la session. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."""


@tool
async def add_incident_comment_tool(user_id: str, comment_text: str) -> str:
    """Add a comment/description to the incident being reported.

    Args:
        user_id: User ID
        comment_text: Comment text (can be from voice transcription or text message)

    Returns:
        Success or error message
    """
    try:
        session = await incident_state.get_session(user_id)

        if not session:
            return "❌ Aucune session active. Impossible d'ajouter le commentaire."

        incident_id = session.get("incident_id")
        if not incident_id:
            return "❌ Aucun incident trouvé. Veuillez réessayer."

        # Add comment to incident
        success = await incident_storage.add_comment_to_incident(
            incident_id=incident_id, comment=comment_text
        )

        if success:
            # Record action in session
            await incident_state.add_action(user_id, "comment")

            comments_added = session.get("comments_added", 0) + 1
            images_added = session.get("images_uploaded", 0)

            return f"""✅ Commentaire ajouté : '{comment_text}'

📊 Progression:
- Commentaires: {comments_added}
- Photos: {images_added}

Vous pouvez ajouter plus de détails ou dire "terminé" quand vous avez fini."""
        else:
            return "❌ Erreur lors de l'ajout du commentaire. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error adding incident comment: {e}")
        return f"""❌ TECHNICAL ERROR: {str(e)}

Tell the user: 'Désolé, je rencontre un problème technique lors de l'ajout du commentaire. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."""


@tool
async def add_incident_image_tool(user_id: str, image_url: str) -> str:
    """Add an image to the incident being reported.

    Args:
        user_id: User ID
        image_url: Public URL of the image to attach

    Returns:
        Success or error message
    """
    try:
        session = await incident_state.get_session(user_id)

        if not session:
            return "❌ Aucune session active. Impossible d'ajouter l'image."

        incident_id = session.get("incident_id")
        if not incident_id:
            return "❌ Aucun incident trouvé. Veuillez réessayer."

        # Add image to incident
        success = await incident_storage.add_image_to_incident(
            incident_id=incident_id, image_url=image_url
        )

        if success:
            # Record action in session
            await incident_state.add_action(user_id, "image")

            images_added = session.get("images_uploaded", 0) + 1
            comments_added = session.get("comments_added", 0)

            return f"""✅ Photo ajoutée avec succès !

📊 Progression:
- Photos: {images_added}
- Commentaires: {comments_added}

Ajoutez un commentaire pour décrire le problème, ou dites "terminé"."""
        else:
            return "❌ Erreur lors de l'ajout de la photo. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error adding incident image: {e}")
        return f"""❌ TECHNICAL ERROR: {str(e)}

Tell the user: 'Désolé, je rencontre un problème technique lors de l'ajout de la photo. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."""


@tool
async def finalize_incident_tool(user_id: str) -> str:
    """Finalize the incident report and end the session.

    Call this when user indicates they're done (e.g., "terminé", "fini", "c'est tout").

    Args:
        user_id: User ID

    Returns:
        Success message with summary or error message
    """
    try:
        session = await incident_state.get_session(user_id)

        if not session:
            return "❌ Aucune session active. Impossible de finaliser l'incident."

        incident_id = session.get("incident_id")
        if not incident_id:
            return "❌ Aucun incident trouvé. Veuillez réessayer."

        # Get incident details for summary
        incident = await incident_storage.get_incident(incident_id)
        if not incident:
            return "❌ Impossible de récupérer les détails de l'incident."

        # Finalize incident (updates timestamp)
        success = await incident_storage.finalize_incident(incident_id)

        if success:
            # Record action and clear session
            await incident_state.add_action(user_id, "finalize")

            # Build summary
            image_count = incident.get("image_count", 0)
            comments_added = incident.get("comments_added", 0)

            summary = "✅ Incident signalé avec succès !\n\n"
            summary += "📊 Résumé :\n"
            summary += f"- Photos ajoutées : {image_count}\n"
            summary += f"- Commentaires ajoutés : {comments_added}\n\n"
            summary += "L'équipe a été informée et reviendra vers vous. Merci ! 🙏"

            # Clear session
            await incident_state.clear_session(user_id, reason="completed")

            return summary
        else:
            return "❌ Erreur lors de la finalisation. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error finalizing incident: {e}")
        return f"""❌ TECHNICAL ERROR: {str(e)}

Tell the user: 'Désolé, je rencontre un problème technique pour finaliser l'incident. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."""


@tool
async def exit_incident_session_tool(user_id: str, reason: str) -> str:
    """Exit incident session when user request is OUT OF YOUR SCOPE.

    ⚠️ CRITICAL: After calling this tool, DO NOT generate any message to the user!
    The tool handles the transition silently and hands off to the main LLM.
    Your job ends when you call this tool.

    WHEN TO USE THIS TOOL:
    Call this tool IMMEDIATELY when the user asks for something you CANNOT handle:

    ❌ OUT OF SCOPE (use this tool):
    - Change to another project ("autre projet", "changer de projet")
    - List projects/tasks/lots ("voir mes projets", "liste des tâches", "liste des lots")
    - View documents/plans ("voir les documents", "voir le plan")
    - Update progress on tasks ("mettre à jour", "ajouter progression")
    - General questions ("comment ça marche?", "qui es-tu?")
    - New greetings ("bonjour", "salut", "hello") - indicates session restart
    - Escalate to human ("parler à quelqu'un", "aide", "contacter l'équipe")
    - Cancel incident ("annuler", "abandonner")

    ✅ IN SCOPE (DO NOT use this tool):
    - Add photo to CURRENT incident
    - Add comment/description to CURRENT incident
    - Questions about CURRENT incident
    - Finalize CURRENT incident

    This tool will:
    1. Trigger FSM transition (COLLECTING_DATA → ABANDONED)
    2. Clear your session cleanly from database
    3. Hand off to main LLM which has ALL tools (list_projects, list_tasks, etc.)

    Args:
        user_id: User ID
        reason: Short description why exiting (e.g., "user_wants_different_project",
                "user_greeting", "user_wants_documents", "user_cancelled")

    Returns:
        Exit signal that triggers reroute to main LLM
    """
    try:
        log.info(
            f"🚪 Incident Agent exiting session - Reason: {reason}",
            user_id=user_id,
        )

        # Get current session for FSM transition
        session = await incident_state.get_session(user_id)

        if session:
            # Trigger FSM transition: current_state → ABANDONED
            from src.fsm.core import FSMContext, FSMEngine, SessionState, StateManager

            # Build FSM context from session
            current_state_str = session.get("fsm_state", "idle")
            try:
                current_state = SessionState(current_state_str)
            except ValueError:
                log.warning(
                    f"Invalid FSM state '{current_state_str}', defaulting to IDLE"
                )
                current_state = SessionState.IDLE

            context = FSMContext(
                user_id=user_id,
                current_state=current_state,
                session_id=session.get("id"),
                task_id=None,  # Incidents don't have task_id
            )

            # Execute validated FSM transition
            fsm_engine = FSMEngine(StateManager())
            result = await fsm_engine.transition(
                context=context,
                to_state=SessionState.ABANDONED,
                trigger="cancel",  # Use valid trigger from TRANSITION_RULES
                closure_reason=reason,
            )

            if result.success:
                log.info(
                    f"✅ FSM transition successful: {result.from_state.value} → {result.to_state.value}"
                )
            else:
                log.warning(
                    f"⚠️ FSM transition failed: {result.error} - clearing session anyway"
                )

        # Clear session from database (even if FSM transition failed)
        await incident_state.clear_session(user_id, reason=reason)

        log.info(
            f"✅ Incident session cleared for user {user_id[:8]}... - handing off to main LLM"
        )

        # Return special signal that agent framework will detect
        return "EXIT_SESSION_REROUTE_TO_MAIN_LLM"

    except Exception as e:
        log.error(f"Error exiting incident session: {e}")
        # Even on error, try to clear session
        try:
            await incident_state.clear_session(user_id, reason=f"error_{reason}")
        except Exception:
            pass
        return "EXIT_SESSION_REROUTE_TO_MAIN_LLM"  # Still signal exit
