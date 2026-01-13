"""Task action handlers."""
from typing import Dict, Any, Optional, List
from src.integrations.planradar import planradar_client
from src.integrations.supabase import supabase_client
from src.utils.logger import log


async def list_tasks(user_id: str, project_id: str, status: Optional[str] = None) -> Dict[str, Any]:
    """List tasks for a specific project."""
    try:
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
        tasks = await planradar_client.list_tasks(planradar_project_id, status)

        if not tasks:
            return {
                "success": True,
                "message": "Aucune tâche trouvée pour ce projet.",
                "data": []
            }

        # Format tasks for display
        formatted_tasks = []
        for task in tasks:
            formatted_tasks.append({
                "id": task.get("id"),
                "title": task.get("title"),
                "status": task.get("status"),
                "priority": task.get("priority"),
                "due_date": task.get("due_date"),
            })

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


async def get_task_description(user_id: str, task_id: str) -> Dict[str, Any]:
    """Get detailed description of a task."""
    try:
        description = await planradar_client.get_task_description(task_id)

        if not description:
            return {
                "success": False,
                "message": "Description de tâche non trouvée."
            }

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
            "data": {"description": description}
        }

    except Exception as e:
        log.error(f"Error in get_task_description: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération de la description.",
            "error": str(e)
        }


async def get_task_plans(user_id: str, task_id: str) -> Dict[str, Any]:
    """Get plans/blueprints for a task."""
    try:
        plans = await planradar_client.get_task_plans(task_id)

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


async def get_task_images(user_id: str, task_id: str) -> Dict[str, Any]:
    """Get images attached to a task."""
    try:
        images = await planradar_client.get_task_images(task_id)

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_task_images",
            parameters={"task_id": task_id},
            result={"count": len(images)}
        )

        return {
            "success": True,
            "message": f"{len(images)} image(s) trouvée(s).",
            "data": images
        }

    except Exception as e:
        log.error(f"Error in get_task_images: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des images.",
            "error": str(e)
        }


async def add_task_comment(user_id: str, task_id: str, comment_text: str) -> Dict[str, Any]:
    """Add a comment to a task."""
    try:
        success = await planradar_client.add_task_comment(task_id, comment_text)

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


async def get_task_comments(user_id: str, task_id: str) -> Dict[str, Any]:
    """Get all comments for a task."""
    try:
        comments = await planradar_client.get_task_comments(task_id)

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
    status: str,
    progress_note: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update task progress with status, notes, and images."""
    try:
        success = await planradar_client.update_task_progress(
            task_id=task_id,
            status=status,
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
                "status": status,
                "has_note": bool(progress_note),
                "image_count": len(image_urls) if image_urls else 0,
            },
            result={"success": True}
        )

        return {
            "success": True,
            "message": "Progression de la tâche mise à jour avec succès."
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
