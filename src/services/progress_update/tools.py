"""Specialized LangChain tools for progress update agent."""

from typing import Optional

from langchain.tools import tool

from src.actions.tasks import list_tasks
from src.integrations.planradar import planradar_client
from src.integrations.supabase import supabase_client
from src.services.progress_update.state import progress_update_state
from src.services.project_context import project_context_service
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
            # User has active task - get project_id from user context
            user = supabase_client.get_user(user_id)
            if not user:
                return "❌ No user context found. Please try again."

            # Get active project ID from user context
            active_project_id = user.get("active_project_id")
            if not active_project_id:
                return "❌ No active project context. Please select a project first."

            # Get project details to find PlanRadar project ID
            project = await supabase_client.get_project(
                active_project_id, user_id=user_id
            )
            if not project:
                return "❌ Project not found. Please select a project first."

            planradar_project_id = project.get("planradar_project_id")
            project_name = project.get("name", "Unknown Project")

            # Now get task details from PlanRadar using the project ID
            from src.integrations.planradar import planradar_client

            task = await planradar_client.get_task(active_task_id, planradar_project_id)
            if task:
                # get_task already returns the "data" object, not full response
                attributes = task.get("attributes", {})
                task_title = attributes.get("subject") or task.get(
                    "title", "Unknown Task"
                )

                return f"""✅ ACTIVE TASK FOUND (CONFIRMATION NEEDED):
Task: {task_title}
Project: {project_name}
Task ID: {active_task_id}
PlanRadar Project ID: {planradar_project_id}

AGENT INSTRUCTIONS - This is a CONFIRMATION, not a task list!
Say: "Je comprends, vous souhaitez mettre à jour la tâche {task_title} pour le projet {project_name} ?

1. Oui, c'est ça
2. Non, autre tâche"

IMPORTANT: This should be formatted as list_type="option" (not "tasks")!
IMPORTANT: Keep option 2 text SHORT (max 24 chars for WhatsApp limit)!
- If user says 1 or "oui": USE start_progress_update_session_tool with task_id={active_task_id}, project_id={planradar_project_id}
- If user says 2 or "non": Ask user if they want to change task in same project OR change project entirely
  * If user says "changer de projet" or "autre projet": Call list_projects_tool to show all projects
  * If user says "changer de tâche" or "autre tâche": Call get_active_task_context_tool to show task list
- NEVER say "session", "prête", "active", "contexte" - too technical!"""

        # Check for active project (7 hour expiration)
        active_project_id = await project_context_service.get_active_project(user_id)

        if active_project_id:
            # User has active project but no active task - LIST TASKS
            project = await supabase_client.get_project(
                active_project_id, user_id=user_id
            )
            if project:
                project_name = project.get("name", "Unknown Project")
                planradar_project_id = project.get("planradar_project_id")

                # Get tasks for this project
                tasks_result = await list_tasks(
                    user_id=user_id, project_id=active_project_id
                )

                log.info(
                    f"📋 list_tasks result: success={tasks_result.get('success')}, data_length={len(tasks_result.get('data', []))}"
                )

                if tasks_result.get("success"):
                    tasks = tasks_result.get(
                        "data", []
                    )  # list_tasks returns "data", not "tasks"
                    log.info(f"📊 Extracted tasks: {len(tasks)} tasks found")

                    if tasks:
                        # SPECIAL CASE: If only ONE task, ask for confirmation instead of showing list
                        if len(tasks) == 1:
                            tasks[0].get("title", "No title")
                            tasks[0].get("id")

                            log.info(
                                "📌 Only 1 task found - showing confirmation instead of list"
                            )
                            return f"""✅ ACTIVE TASK FOUND (CONFIRMATION NEEDED):
Task: {task_title}
Project: {project_name}
Task ID: {task_id}
PlanRadar Project ID: {planradar_project_id}

AGENT INSTRUCTIONS - This is a CONFIRMATION, not a task list!
Say: "Je comprends, vous souhaitez mettre à jour la tâche {task_title} pour le projet {project_name} ?

1. Oui, c'est ça
2. Non, autre tâche"

IMPORTANT: This should be formatted as list_type="option" (not "tasks")!
IMPORTANT: Keep option 2 text SHORT (max 24 chars for WhatsApp limit)!
- If user says 1 or "oui": USE start_progress_update_session_tool with task_id={task_id}, project_id={planradar_project_id}
- If user says 2 or "non": Ask user if they want to change task in same project OR change project entirely
  * If user says "changer de projet" or "autre projet": Call list_projects_tool to show all projects
  * If user says "changer de tâche" or "autre tâche": Call get_active_task_context_tool to show task list
- NEVER say "session", "prête", "active", "contexte" - too technical!"""

                        # MULTIPLE TASKS: Show list for selection
                        log.info("✅ Building task list for user display")
                        # Format task list - SIMPLE format for user display
                        task_list_display = "\n".join(
                            [
                                f"{idx}. {task.get('title', 'No title')}"
                                for idx, task in enumerate(tasks[:10], 1)  # Limit to 10
                            ]
                        )

                        # Also provide task IDs for agent to use when user selects
                        task_id_mapping = "\n".join(
                            [
                                f"Number {idx} = ID {task.get('id')}"
                                for idx, task in enumerate(tasks[:10], 1)
                            ]
                        )

                        result_text = f"""✅ Active project: {project_name}

Show the user this list (SIMPLE FORMAT, no IDs visible):
{task_list_display}

Task ID mapping (for your use only, don't show to user):
{task_id_mapping}

AGENT INSTRUCTIONS:
1. Say: "Pour quelle tâche du projet {project_name} ?"
2. Show the task list above (just numbers and titles, no formatting)
3. When user selects by number, use start_progress_update_session_tool with the task_id from mapping above and project_id={planradar_project_id}
4. Be simple and friendly - no technical terms"""

                        log.info(f"🎯 Tool returning task list with {len(tasks)} tasks")
                        log.info(f"📝 First task: {tasks[0].get('title', 'No title')}")
                        return result_text
                    else:
                        return f"⚠️ Active project: {project_name}\nBut NO tasks found for this project. Ask user if they want to select a different project."
                else:
                    return f"⚠️ Active project: {project_name}\nError retrieving tasks: {
                        tasks_result.get(
                            'message', 'Unknown error')}. Ask user to provide task name or number."

        # No active context
        return "❌ No active project or task context. Ask user to select a project first, then a task."

    except Exception as e:
        log.error(f"Error in get_active_task_context_tool: {e}")
        return f"❌ TECHNICAL ERROR: {
            str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate using escalate_to_human_tool."


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

        # Get task details from PlanRadar
        from src.integrations.planradar import planradar_client

        task = await planradar_client.get_task(
            session["task_id"], session["project_id"]
        )

        task_title = "Unknown"
        if task:
            # get_task already returns the "data" object, not full response
            attributes = task.get("attributes", {})
            task_title = attributes.get("subject") or task.get("title", "Unknown")

        output = "📋 Session de mise à jour active :\n"
        output += f"Tâche : {task_title}\n"
        output += f"Projet ID : {session['project_id']}\n\n"
        output += "Actions déjà effectuées :\n"
        output += f"- Photos ajoutées : {session['images_uploaded']}\n"
        output += f"- Commentaires ajoutés : {session['comments_added']}\n"
        output += (
            f"- Statut changé : {'Oui' if session['status_changed'] else 'Non'}\n\n"
        )

        # Suggest next actions
        remaining = []
        if session["images_uploaded"] == 0:
            remaining.append("📸 Ajouter une photo")
        if session["comments_added"] == 0:
            remaining.append("💬 Laisser un commentaire")
        if not session["status_changed"]:
            remaining.append("✅ Marquer comme terminé")

        if remaining:
            output += "Actions possibles :\n" + "\n".join(f"- {a}" for a in remaining)
        else:
            output += "✅ Toutes les actions ont été complétées !"

        return output

    except Exception as e:
        log.error(f"Error in get_progress_update_context_tool: {e}")
        return f"❌ TECHNICAL ERROR: {
            str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate using escalate_to_human_tool."


@tool
async def add_progress_image_tool(user_id: str, image_url: str) -> str:
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
            additional_images=[image_url],
        )

        if success:
            # Record action
            await progress_update_state.add_action(user_id, "image")

            return "✅ Photo ajoutée avec succès à la tâche !\n\nActions restantes disponibles :\n- 💬 Laisser un commentaire\n- ✅ Marquer comme terminé"
        else:
            return "❌ Erreur lors de l'ajout de la photo. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error adding progress image: {e}")
        return f"❌ TECHNICAL ERROR: {
            str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique lors de l'ajout de la photo. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."


@tool
async def add_progress_comment_tool(user_id: str, comment_text: str) -> str:
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
            comment_text=comment_text,
        )

        if success:
            # Record action
            await progress_update_state.add_action(user_id, "comment")

            return f"✅ Commentaire ajouté : '{comment_text}'\n\nActions restantes disponibles :\n- 📸 Ajouter une photo\n- ✅ Marquer comme terminé"
        else:
            return "❌ Erreur lors de l'ajout du commentaire. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error adding progress comment: {e}")
        return f"❌ TECHNICAL ERROR: {
            str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique lors de l'ajout du commentaire. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."


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
            task_id=session["task_id"], project_id=session["project_id"]
        )

        if success:
            # Record action
            await progress_update_state.add_action(user_id, "complete")

            # Get summary
            updated_session = await progress_update_state.get_session(user_id)
            summary = "✅ Tâche marquée comme terminée !\n\n"
            summary += "📊 Résumé :\n"
            summary += f"- Photos ajoutées : {updated_session['images_uploaded']}\n"
            summary += f"- Commentaires ajoutés : {updated_session['comments_added']}\n"
            summary += "- Statut : Terminé\n\n"
            summary += "Excellent travail ! 🎉"

            # Clear session
            await progress_update_state.clear_session(user_id)

            return summary
        else:
            return "❌ Erreur lors du changement de statut. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error marking task complete: {e}")
        return f"❌ TECHNICAL ERROR: {
            str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique pour marquer la tâche comme terminée. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."


@tool
async def start_progress_update_session_tool(
    user_id: str, task_id: Optional[str] = None, project_id: Optional[str] = None
) -> str:
    """Start a new progress update session for a specific task.

    CRITICAL: Only call this tool when you have BOTH task_id AND project_id from get_active_task_context_tool output.
    DO NOT call this tool if task_id or project_id is None, empty, or missing.
    If you don't have these IDs, you MUST ask the user to select a task first using get_active_task_context_tool.

    Args:
        user_id: User ID (required)
        task_id: Task ID from get_active_task_context_tool (REQUIRED - do not pass None)
        project_id: PlanRadar project ID from get_active_task_context_tool (REQUIRED - do not pass None)

    Returns:
        Success message with action menu or error message
    """
    try:
        # Validation: Ensure we have valid IDs
        if not task_id or not project_id:
            # Determine which parameters are missing for specific error message
            missing_params = []
            if not task_id:
                missing_params.append("task_id")
            if not project_id:
                missing_params.append("project_id")

            log.error(
                f"❌ start_progress_update_session_tool called with missing IDs: task_id={task_id}, project_id={project_id}"
            )

            # Return error that works for both agent guidance and potential user visibility
            return f"""❌ Impossible de démarrer la session: {' et '.join(missing_params)} manquant(s).

Utilise d'abord get_active_task_context_tool pour obtenir les IDs nécessaires, puis rappelle cet outil avec les valeurs correctes.

Si aucun contexte actif n'est trouvé, demande à l'utilisateur quelle tâche il souhaite mettre à jour."""
        # Create session
        session_id = await progress_update_state.create_session(
            user_id=user_id, task_id=task_id, project_id=project_id
        )

        if session_id:
            # Get task details from PlanRadar
            from src.integrations.planradar import planradar_client

            task = await planradar_client.get_task(task_id, project_id)

            task_title = "Unknown Task"
            if task:
                # get_task already returns the "data" object, not full response
                attributes = task.get("attributes", {})
                task_title = attributes.get("subject") or task.get(
                    "title", "Unknown Task"
                )

            return f"✅ Session de mise à jour démarrée pour : {task_title}\n\nQue souhaitez-vous faire ?\n1. 📸 Ajouter une photo\n2. 💬 Laisser un commentaire\n3. ✅ Marquer comme terminé"
        else:
            return "❌ Impossible de démarrer la session. Veuillez réessayer."

    except Exception as e:
        log.error(f"Error starting progress update session: {e}")
        return f"❌ TECHNICAL ERROR: {
            str(e)}\n\nTell the user: 'Désolé, je rencontre un problème technique pour démarrer la session. Souhaitez-vous parler avec quelqu'un de l'équipe ?' and offer to escalate."
