"""Task action handlers."""
from typing import Dict, Any, Optional, List
from src.integrations.planradar import planradar_client
from src.integrations.supabase import supabase_client
from src.services.project_context import project_context_service
from src.utils.logger import log


async def list_tasks(user_id: str, project_id: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    """List tasks for a specific project.

    If project_id is not provided, uses the active project context from the user's profile.
    If no active project is found, prompts the user to select a project.
    """
    try:
        # If no project_id provided, try to get from active project context
        if not project_id:
            project_id = await project_context_service.get_active_project(user_id)
            if not project_id:
                return {
                    "success": False,
                    "message": "Sur quel projet travaillez-vous actuellement ? Veuillez sélectionner un projet.",
                    "requires_project_selection": True,
                    "data": []
                }

        # Get project details to retrieve PlanRadar project ID
        project = await supabase_client.get_project(project_id, user_id=user_id)

        if not project:
            return {
                "success": False,
                "message": "Projet non trouvé.",
                "data": []
            }

        planradar_project_id = project.get("planradar_project_id")

        if not planradar_project_id:
            return {
                "success": False,
                "message": "Ce projet n'est pas lié à PlanRadar.",
                "data": []
            }

        # Fetch tasks from PlanRadar using the PlanRadar project ID
        try:
            tasks = await planradar_client.list_tasks(planradar_project_id, status)
        except Exception as api_error:
            # Handle rate limit errors specifically
            if "rate limit" in str(api_error).lower():
                return {
                    "success": False,
                    "message": "⏱️ L'API PlanRadar est temporairement surchargée. Veuillez réessayer dans quelques instants.",
                    "data": [],
                    "rate_limited": True
                }
            else:
                raise  # Re-raise other exceptions

        if not tasks:
            project_name = project.get("nom", "ce projet")
            return {
                "success": True,
                "message": f"Le projet '{project_name}' n'a actuellement aucune tâche active. "
                          f"Il n'y a pas encore de tâches assignées ou toutes les tâches ont été complétées.",
                "data": []
            }

        # Format tasks for display
        # PlanRadar uses JSON:API format with attributes nested
        formatted_tasks = []
        for task in tasks:
            attributes = task.get("attributes", {})
            uuid_val = attributes.get("uuid")
            short_id_val = task.get("id")

            # DEBUG: Log what we're getting from PlanRadar
            log.info(f"   📊 Task from PlanRadar: short_id={short_id_val}, uuid={uuid_val}, has_uuid={uuid_val is not None}")

            formatted_tasks.append({
                "id": uuid_val,  # Use UUID as primary ID (latest API standard)
                "short_id": short_id_val,  # Keep short ID for backward compatibility
                "title": attributes.get("subject", "Sans titre"),
                "status": attributes.get("status-id", "unknown"),
                "priority": attributes.get("priority", "normal"),
                "due_date": attributes.get("due-date"),
                "progress": attributes.get("progress", 0),
                "sequential_id": attributes.get("sequential-id"),
                "project_id": attributes.get("project-id") or planradar_project_id,  # Store project_id for API calls
            })

        # Update active project context (set or touch activity)
        project_name = project.get("nom")
        await project_context_service.set_active_project(
            user_id=user_id,
            project_id=project_id,
            project_name=project_name
        )

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="list_tasks",
            parameters={"project_id": project_id, "status": status},
            result={"count": len(formatted_tasks)}
        )

        return {
            "success": True,
            "message": f"{len(formatted_tasks)} tâche(s) trouvée(s).",
            "data": formatted_tasks
        }

    except Exception as e:
        log.error(f"Error in list_tasks: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des tâches.",
            "error": str(e)
        }


async def get_task_description(user_id: str, task_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Get detailed description of a task."""
    log.info(f"📝 get_task_description action: user_id={user_id[:8]}..., task_id={task_id}, project_id={project_id[:8] if project_id else 'None'}...")
    try:
        # Get project_id from active context if not provided
        if not project_id:
            log.info(f"   🔍 Fetching active project from context")
            project_id = await project_context_service.get_active_project(user_id)
            if not project_id:
                log.warning(f"   ⚠️ No active project found")
                return {
                    "success": False,
                    "message": "Contexte du projet non trouvé. Veuillez d'abord sélectionner un projet."
                }
            log.info(f"   ✅ Active project: {project_id[:8]}...")

        # Get PlanRadar project ID from database
        log.info(f"   🔍 Fetching PlanRadar project ID from DB")
        project = await supabase_client.get_project(project_id, user_id=user_id)
        if not project:
            log.warning(f"   ⚠️ Project not found in DB")
            return {
                "success": False,
                "message": "Projet non trouvé."
            }

        planradar_project_id = project.get("planradar_project_id")
        if not planradar_project_id:
            log.warning(f"   ⚠️ Project not linked to PlanRadar")
            return {
                "success": False,
                "message": "Ce projet n'est pas lié à PlanRadar."
            }
        log.info(f"   ✅ PlanRadar project ID: {planradar_project_id[:8]}...")

        # Get full task details to include title
        log.info(f"   🌐 Calling PlanRadar API for task details")
        task = await planradar_client.get_task(task_id, planradar_project_id)

        if not task:
            return {
                "success": False,
                "message": "Tâche non trouvée."
            }

        # Handle PlanRadar's JSON:API format - title and description are in attributes
        attributes = task.get("attributes", {})
        title = attributes.get("subject") or task.get("title", "")

        # Description can be in multiple places:
        # 1. Standard description field
        # 2. Custom fields in typed-values (PlanRadar custom fields)
        description = task.get("description") or attributes.get("description")

        # If no standard description, check typed-values for description-like fields
        if not description:
            typed_values = attributes.get("typed-values", {})
            if typed_values and isinstance(typed_values, dict):
                # Look for the first non-empty text value (likely description)
                for field_id, field_value in typed_values.items():
                    if field_value and isinstance(field_value, str) and len(field_value) > 10:
                        description = field_value
                        log.info(f"   📝 Found description in typed-values field: {field_id}")
                        break

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_task_description",
            parameters={"task_id": task_id},
            result={"has_description": bool(description)}
        )

        return {
            "success": True,
            "message": "Description de la tâche récupérée.",
            "data": {
                "description": description,
                "title": title
            }
        }

    except Exception as e:
        log.error(f"Error in get_task_description: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération de la description.",
            "error": str(e)
        }


async def get_task_plans(user_id: str, task_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Get plans/blueprints for a task."""
    try:
        # Get project_id from active context if not provided
        if not project_id:
            project_id = await project_context_service.get_active_project(user_id)
            if not project_id:
                return {"success": False, "message": "Contexte du projet non trouvé."}

        project = await supabase_client.get_project(project_id, user_id=user_id)
        if not project:
            return {"success": False, "message": "Projet non trouvé."}

        planradar_project_id = project.get("planradar_project_id")
        if not planradar_project_id:
            return {"success": False, "message": "Ce projet n'est pas lié à PlanRadar."}

        plans = await planradar_client.get_task_plans(task_id, planradar_project_id)

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_task_plans",
            parameters={"task_id": task_id},
            result={"count": len(plans)}
        )

        return {
            "success": True,
            "message": f"{len(plans)} plan(s) trouvé(s).",
            "data": plans
        }

    except Exception as e:
        log.error(f"Error in get_task_plans: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des plans.",
            "error": str(e)
        }


async def get_task_images(user_id: str, task_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Get all attachments (images, documents, etc.) attached to a task.

    Args:
        user_id: The user ID
        task_id: The task UUID (primary identifier, latest API standard)
        project_id: Optional project ID (fetched from context if not provided)

    Returns:
        Dict with success status and list of all attachments (images, PDFs, documents, etc.)
    """
    log.info(f"📎 get_task_images action: user_id={user_id[:8]}..., task_id={task_id[:8]}..., project_id={project_id[:8] if project_id else 'None'}...")
    try:
        # Get project_id from active context if not provided
        if not project_id:
            log.info(f"   🔍 Fetching active project from context")
            project_id = await project_context_service.get_active_project(user_id)
            if not project_id:
                log.warning(f"   ⚠️ No active project found")
                return {"success": False, "message": "Contexte du projet non trouvé."}
            log.info(f"   ✅ Active project: {project_id[:8]}...")

        log.info(f"   🔍 Fetching PlanRadar project ID from DB")
        project = await supabase_client.get_project(project_id, user_id=user_id)
        if not project:
            log.warning(f"   ⚠️ Project not found in DB")
            return {"success": False, "message": "Projet non trouvé."}

        planradar_project_id = project.get("planradar_project_id")
        if not planradar_project_id:
            log.warning(f"   ⚠️ Project not linked to PlanRadar")
            return {"success": False, "message": "Ce projet n'est pas lié à PlanRadar."}
        log.info(f"   ✅ PlanRadar project ID: {planradar_project_id[:8]}...")

        log.info(f"   🌐 Calling PlanRadar API for task attachments")
        # task_id is now UUID, pass it directly to get_task_images (now returns all attachments)
        attachments = await planradar_client.get_task_images(task_id, planradar_project_id, task_uuid=task_id)

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_task_images",
            parameters={"task_id": task_id},
            result={"count": len(attachments)}
        )

        return {
            "success": True,
            "message": f"{len(attachments)} pièce(s) jointe(s) trouvée(s).",
            "data": attachments
        }

    except Exception as e:
        log.error(f"Error in get_task_images: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des images.",
            "error": str(e)
        }


async def add_task_comment(user_id: str, task_id: str, comment_text: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Add a comment to a task."""
    try:
        # Get project_id from active context if not provided
        if not project_id:
            project_id = await project_context_service.get_active_project(user_id)
            if not project_id:
                return {"success": False, "message": "Contexte du projet non trouvé."}

        project = await supabase_client.get_project(project_id, user_id=user_id)
        if not project:
            return {"success": False, "message": "Projet non trouvé."}

        planradar_project_id = project.get("planradar_project_id")
        if not planradar_project_id:
            return {"success": False, "message": "Ce projet n'est pas lié à PlanRadar."}

        success = await planradar_client.add_task_comment(task_id, planradar_project_id, comment_text)

        if not success:
            return {
                "success": False,
                "message": "Erreur lors de l'ajout du commentaire."
            }

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="add_task_comment",
            parameters={"task_id": task_id, "comment_length": len(comment_text)},
            result={"success": True}
        )

        return {
            "success": True,
            "message": "Commentaire ajouté avec succès."
        }

    except Exception as e:
        log.error(f"Error in add_task_comment: {e}")
        return {
            "success": False,
            "message": "Erreur lors de l'ajout du commentaire.",
            "error": str(e)
        }


async def get_task_comments(user_id: str, task_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
    """Get all comments for a task."""
    try:
        # Get project_id from active context if not provided
        if not project_id:
            project_id = await project_context_service.get_active_project(user_id)
            if not project_id:
                return {"success": False, "message": "Contexte du projet non trouvé."}

        project = await supabase_client.get_project(project_id, user_id=user_id)
        if not project:
            return {"success": False, "message": "Projet non trouvé."}

        planradar_project_id = project.get("planradar_project_id")
        if not planradar_project_id:
            return {"success": False, "message": "Ce projet n'est pas lié à PlanRadar."}

        comments = await planradar_client.get_task_comments(task_id, planradar_project_id)

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_task_comments",
            parameters={"task_id": task_id},
            result={"count": len(comments)}
        )

        return {
            "success": True,
            "message": f"{len(comments)} commentaire(s) trouvé(s).",
            "data": comments
        }

    except Exception as e:
        log.error(f"Error in get_task_comments: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des commentaires.",
            "error": str(e)
        }


async def update_task_progress(
    user_id: str,
    task_id: str,
    status_id: int,  # 1=Open, 2=In-Progress, 3=Resolved, 4=Feedback, 5=Closed, 6=Rejected
    progress: Optional[int] = None,  # 0-100 percentage
    progress_note: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update task progress with status, progress percentage, notes, and images.

    Args:
        user_id: User ID
        task_id: Task ID (PlanRadar UUID)
        status_id: Status ID (1=Open, 2=In-Progress, 3=Resolved, 4=Feedback, 5=Closed, 6=Rejected)
        progress: Optional progress percentage (0-100)
        progress_note: Optional progress note
        image_urls: Optional list of image URLs

    Returns:
        Result dict with success status and message
    """
    try:
        # Get task to find project_id
        task = await supabase_client.get_task(task_id)
        if not task:
            return {
                "success": False,
                "message": "Tâche non trouvée."
            }

        project_id = task.get("project_id")
        if not project_id:
            return {
                "success": False,
                "message": "Projet non trouvé pour cette tâche."
            }

        # Get project to find planradar_project_id
        project = await supabase_client.get_project(project_id, user_id=user_id)
        if not project:
            return {
                "success": False,
                "message": "Projet non trouvé."
            }

        planradar_project_id = project.get("planradar_project_id")
        if not planradar_project_id:
            return {
                "success": False,
                "message": "Ce projet n'est pas lié à PlanRadar."
            }

        # Update via PlanRadar with correct parameters
        success = await planradar_client.update_task_progress(
            task_id=task_id,
            project_id=planradar_project_id,
            status_id=status_id,
            progress=progress,
            progress_note=progress_note,
            image_urls=image_urls,
        )

        if not success:
            return {
                "success": False,
                "message": "Erreur lors de la mise à jour de la progression."
            }

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="update_task_progress",
            parameters={
                "task_id": task_id,
                "status_id": status_id,
                "progress": progress,
                "has_note": bool(progress_note),
                "image_count": len(image_urls) if image_urls else 0,
            },
            result={"success": True}
        )

        # Status name mapping for user-friendly message
        status_names = {
            1: "Ouvert",
            2: "En cours",
            3: "Résolu",
            4: "Feedback",
            5: "Fermé",
            6: "Rejeté"
        }
        status_name = status_names.get(status_id, "Inconnu")

        message = f"Progression de la tâche mise à jour : {status_name}"
        if progress is not None:
            message += f" ({progress}%)"

        return {
            "success": True,
            "message": message
        }

    except Exception as e:
        log.error(f"Error in update_task_progress: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la mise à jour de la progression.",
            "error": str(e)
        }


async def mark_task_complete(user_id: str, task_id: str) -> Dict[str, Any]:
    """Mark a task as complete."""
    try:
        success = await planradar_client.mark_task_complete(task_id)

        if not success:
            return {
                "success": False,
                "message": "Erreur lors du marquage de la tâche comme terminée."
            }

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="mark_task_complete",
            parameters={"task_id": task_id},
            result={"success": True}
        )

        return {
            "success": True,
            "message": "Tâche marquée comme terminée avec succès."
        }

    except Exception as e:
        log.error(f"Error in mark_task_complete: {e}")
        return {
            "success": False,
            "message": "Erreur lors du marquage de la tâche.",
            "error": str(e)
        }
