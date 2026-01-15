"""Specialized LangChain tools for progress update agent."""
from langchain.tools import tool
from typing import Optional
from src.services.progress_update.state import progress_update_state
from src.services.project_context import project_context_service
from src.integrations.planradar import planradar_client
from src.integrations.supabase import supabase_client
from src.actions.tasks import list_tasks
from src.utils.logger import log


@tool
async def get_active_task_context_tool(user_id: str) -> str:
    """Check if user has an active project and task in context.

    This should be called FIRST before asking user to select project/task.
    Returns the active task info if available, or indicates what's missing.

    Args:
        user_id: User ID

    Returns:
        Context information about active project/task or what's needed
    """
    try:
        # Check for active task (1 hour expiration)
        active_task_id = await project_context_service.get_active_task(user_id)

        if active_task_id:
            # User has active task - get details
            task = await supabase_client.get_task(active_task_id)
            if task:
                project_id = task.get("project_id")
                task_title = task.get("title", "Unknown Task")

                # Get project to find PlanRadar project ID
                project = await supabase_client.get_project(project_id, user_id=user_id)
                if project:
                    planradar_project_id = project.get("planradar_project_id")
                    project_name = project.get("name", "Unknown Project")

                    return f"✅ ACTIVE CONTEXT FOUND:\nTask: {task_title}\nProject: {project_name}\nTask ID: {active_task_id}\nPlanRadar Project ID: {planradar_project_id}\n\nUSE start_progress_update_session_tool with these IDs immediately!"

        # Check for active project (7 hour expiration)
        active_project_id = await project_context_service.get_active_project(user_id)

        if active_project_id:
            # User has active project but no active task - LIST TASKS
            project = await supabase_client.get_project(active_project_id, user_id=user_id)
            if project:
                project_name = project.get("name", "Unknown Project")
                planradar_project_id = project.get("planradar_project_id")

                # Get tasks for this project
                tasks_result = await list_tasks(
                    user_id=user_id,
                    project_id=active_project_id
                )

                if tasks_result.get("success"):
                    tasks = tasks_result.get("tasks", [])

                    if tasks:
                        # Format task list - SIMPLE format for user display
                        task_list_display = "\n".join([
                            f"{idx}. {task.get('title', 'No title')}"
                            for idx, task in enumerate(tasks[:10], 1)  # Limit to 10
                        ])

                        # Also provide task IDs for agent to use when user selects
                        task_id_mapping = "\n".join([
                            f"Number {idx} = ID {task.get('id')}"
                            for idx, task in enumerate(tasks[:10], 1)
                        ])

                        return f"""⚠️ Active project: {project_name}
But NO active task selected.

Show the user this list (SIMPLE FORMAT, no IDs visible):
{task_list_display}

Task ID mapping (for your use only, don't show to user):
{task_id_mapping}

ASK the user: "Quelle tâche souhaitez-vous mettre à jour ?"
When they select by number or name, use the ID mapping above with start_progress_update_session_tool (task_id, project_id={planradar_project_id})"""
                    else:
                        return f"⚠️ Active project: {project_name}\nBut NO tasks found for this project. Ask user if they want to select a different project."
                else:
                    return f"⚠️ Active project: {project_name}\nError retrieving tasks: {tasks_result.get('message', 'Unknown error')}. Ask user to provide task name or number."

        # No active context
        return "❌ No active project or task context. Ask user to select a project first, then a task."

    except Exception as e:
        log.error(f"Error in get_active_task_context_tool: {e}")
        return f"❌ TECHNICAL ERROR: {str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate using escalate_to_human_tool."


@tool
async def get_progress_update_context_tool(user_id: str) -> str:
    """Get current progress update session context.

    Returns information about:
    - Current task being updated
    - Actions already completed
    - What's remaining

    Args:
        user_id: User ID

    Returns:
        Context information as formatted string
    """
    try:
        session = await progress_update_state.get_session(user_id)

        if not session:
            return "Aucune session de mise à jour active. Demandez à l'utilisateur pour quelle tâche il souhaite mettre à jour la progression."

        # Get task details
        task = await supabase_client.get_task(session["task_id"])
        if not task:
            return "Erreur : Tâche non trouvée."

        output = f"📋 Session de mise à jour active :\n"
        output += f"Tâche : {task.get('title', 'Unknown')}\n"
        output += f"Projet ID : {session['project_id']}\n\n"
        output += f"Actions déjà effectuées :\n"
        output += f"- Photos ajoutées : {session['images_uploaded']}\n"
        output += f"- Commentaires ajoutés : {session['comments_added']}\n"
        output += f"- Statut changé : {'Oui' if session['status_changed'] else 'Non'}\n\n"

        # Suggest next actions
        remaining = []
        if session['images_uploaded'] == 0:
            remaining.append("📸 Ajouter une photo")
        if session['comments_added'] == 0:
            remaining.append("💬 Laisser un commentaire")
        if not session['status_changed']:
            remaining.append("✅ Marquer comme terminé")

        if remaining:
            output += f"Actions possibles :\n" + "\n".join(f"- {a}" for a in remaining)
        else:
            output += "✅ Toutes les actions ont été complétées !"

        return output

    except Exception as e:
        log.error(f"Error in get_progress_update_context_tool: {e}")
        return f"❌ TECHNICAL ERROR: {str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate using escalate_to_human_tool."


@tool
async def add_progress_image_tool(
    user_id: str,
    image_url: str
) -> str:
    """Add an image to the task being updated.

    Args:
        user_id: User ID
        image_url: Public URL of the image to attach

    Returns:
        Success or error message
    """
    try:
        session = await progress_update_state.get_session(user_id)

        if not session:
            return "❌ Aucune session active. Impossible d'ajouter l'image."

        # Use PlanRadar's update_incident_report to add image
        success = await planradar_client.update_incident_report(
            task_id=session["task_id"],
            project_id=session["project_id"],
            additional_images=[image_url]
        )

        if success:
            # Record action
            await progress_update_state.add_action(user_id, "image")

            return f"✅ Photo ajoutée avec succès à la tâche !\n\nActions restantes disponibles :\n- 💬 Laisser un commentaire\n- ✅ Marquer comme terminé"
        else:
            return "❌ Erreur lors de l'ajout de la photo. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error adding progress image: {e}")
        return f"❌ TECHNICAL ERROR: {str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique lors de l'ajout de la photo. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."


@tool
async def add_progress_comment_tool(
    user_id: str,
    comment_text: str
) -> str:
    """Add a comment to the task being updated.

    Args:
        user_id: User ID
        comment_text: Comment text (can be from voice transcription)

    Returns:
        Success or error message
    """
    try:
        session = await progress_update_state.get_session(user_id)

        if not session:
            return "❌ Aucune session active. Impossible d'ajouter le commentaire."

        success = await planradar_client.add_task_comment(
            task_id=session["task_id"],
            project_id=session["project_id"],
            comment_text=comment_text
        )

        if success:
            # Record action
            await progress_update_state.add_action(user_id, "comment")

            return f"✅ Commentaire ajouté : '{comment_text}'\n\nActions restantes disponibles :\n- 📸 Ajouter une photo\n- ✅ Marquer comme terminé"
        else:
            return "❌ Erreur lors de l'ajout du commentaire. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error adding progress comment: {e}")
        return f"❌ TECHNICAL ERROR: {str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique lors de l'ajout du commentaire. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."


@tool
async def mark_task_complete_tool(user_id: str) -> str:
    """Mark the task as complete (Resolved status).

    Args:
        user_id: User ID

    Returns:
        Success message with summary or error message
    """
    try:
        session = await progress_update_state.get_session(user_id)

        if not session:
            return "❌ Aucune session active. Impossible de marquer la tâche comme terminée."

        success = await planradar_client.mark_task_complete(
            task_id=session["task_id"],
            project_id=session["project_id"]
        )

        if success:
            # Record action
            await progress_update_state.add_action(user_id, "complete")

            # Get summary
            updated_session = await progress_update_state.get_session(user_id)
            summary = f"✅ Tâche marquée comme terminée !\n\n"
            summary += f"📊 Résumé :\n"
            summary += f"- Photos ajoutées : {updated_session['images_uploaded']}\n"
            summary += f"- Commentaires ajoutés : {updated_session['comments_added']}\n"
            summary += f"- Statut : Terminé\n\n"
            summary += "Excellent travail ! 🎉"

            # Clear session
            await progress_update_state.clear_session(user_id)

            return summary
        else:
            return "❌ Erreur lors du changement de statut. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error marking task complete: {e}")
        return f"❌ TECHNICAL ERROR: {str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique pour marquer la tâche comme terminée. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."


@tool
async def start_progress_update_session_tool(
    user_id: str,
    task_id: str,
    project_id: str
) -> str:
    """Start a new progress update session for a specific task.

    Args:
        user_id: User ID
        task_id: Task ID to update
        project_id: PlanRadar project ID

    Returns:
        Success message with action menu or error message
    """
    try:
        # Create session
        session_id = await progress_update_state.create_session(
            user_id=user_id,
            task_id=task_id,
            project_id=project_id
        )

        if session_id:
            # Get task details
            task = await supabase_client.get_task(task_id)
            task_title = task.get("title", "Unknown Task") if task else "Unknown Task"

            return f"✅ Session de mise à jour démarrée pour : {task_title}\n\nQue souhaitez-vous faire ?\n1. 📸 Ajouter une photo\n2. 💬 Laisser un commentaire\n3. ✅ Marquer comme terminé"
        else:
            return "❌ Impossible de démarrer la session. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error starting progress update session: {e}")
        return f"❌ TECHNICAL ERROR: {str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique pour démarrer la session. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."
