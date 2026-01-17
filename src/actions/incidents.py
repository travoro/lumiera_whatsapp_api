"""Incident reporting action handlers."""

from typing import Any, Dict, List, Optional

from src.integrations.planradar import planradar_client
from src.integrations.supabase import supabase_client
from src.utils.logger import log


async def submit_incident_report(
    user_id: str,
    project_id: str,
    title: str,
    description: str,
    image_urls: List[str],
    location: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Submit a new incident report.

    Args:
        user_id: User ID submitting the report
        project_id: Project ID where incident occurred
        title: Incident title
        description: Incident description (text or transcribed audio)
        image_urls: List of image URLs (at least one required)
        location: Optional location data

    Returns:
        Result dictionary with success status and incident ID
    """
    try:
        # Validate that at least one image is provided
        if not image_urls or len(image_urls) == 0:
            return {
                "success": False,
                "message": "Au moins une image est requise pour signaler un incident.",
            }

        # Validate that description is provided
        if not description or len(description.strip()) == 0:
            return {
                "success": False,
                "message": "Une description est requise pour signaler un incident.",
            }

        # Get project details to retrieve PlanRadar project ID
        project = await supabase_client.get_project(project_id, user_id=user_id)

        if not project:
            return {"success": False, "message": "Projet non trouvé."}

        planradar_project_id = project.get("planradar_project_id")

        if not planradar_project_id:
            return {"success": False, "message": "Ce projet n'est pas lié à PlanRadar."}

        # Submit incident to PlanRadar using PlanRadar project ID
        incident_id = await planradar_client.submit_incident_report(
            project_id=planradar_project_id,
            title=title,
            description=description,
            image_urls=image_urls,
            location=location,
        )

        if not incident_id:
            return {
                "success": False,
                "message": "Erreur lors de la soumission du rapport d'incident.",
            }

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="submit_incident_report",
            parameters={
                "project_id": project_id,
                "title": title,
                "image_count": len(image_urls),
                "has_location": bool(location),
            },
            result={"incident_id": incident_id},
        )

        return {
            "success": True,
            "message": "Rapport d'incident soumis avec succès.",
            "data": {"incident_id": incident_id},
        }

    except Exception as e:
        log.error(f"Error in submit_incident_report: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la soumission du rapport d'incident.",
            "error": str(e),
        }


async def update_incident_report(
    user_id: str,
    incident_id: str,
    project_id: str,
    additional_text: Optional[str] = None,
    additional_images: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update an existing incident report with additional information.

    Args:
        user_id: User ID updating the report
        incident_id: ID of the incident to update
        project_id: Project ID where the incident exists
        additional_text: Additional text/notes to add
        additional_images: Additional images to attach

    Returns:
        Result dictionary with success status
    """
    try:
        # Validate that at least something is being added
        if not additional_text and not additional_images:
            return {
                "success": False,
                "message": "Veuillez fournir du texte ou des images supplémentaires.",
            }

        # Update incident in PlanRadar
        success = await planradar_client.update_incident_report(
            task_id=incident_id,
            project_id=project_id,
            additional_text=additional_text,
            additional_images=additional_images,
        )

        if not success:
            return {
                "success": False,
                "message": "Erreur lors de la mise à jour du rapport d'incident.",
            }

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="update_incident_report",
            parameters={
                "incident_id": incident_id,
                "has_text": bool(additional_text),
                "image_count": len(additional_images) if additional_images else 0,
            },
            result={"success": True},
        )

        return {
            "success": True,
            "message": "Rapport d'incident mis à jour avec succès.",
        }

    except Exception as e:
        log.error(f"Error in update_incident_report: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la mise à jour du rapport d'incident.",
            "error": str(e),
        }
