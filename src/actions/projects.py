"""Project (Chantier) action handlers."""
from typing import Dict, Any, List
from src.integrations.supabase import supabase_client
from src.utils.whatsapp_formatter import get_plural_translation
from src.utils.logger import log


async def list_projects(user_id: str) -> Dict[str, Any]:
    """List all active projects for the user."""
    try:
        projects = await supabase_client.list_projects(user_id)

        if not projects:
            return {
                "success": True,
                "message": "Aucun projet actif trouvé.",
                "data": []
            }

        # Format projects for display
        formatted_projects = []
        for project in projects:
            formatted_projects.append({
                "id": project.get("id"),
                "nom": project.get("nom"),
                "location": project.get("location"),
                "status": project.get("status"),
                "planradar_project_id": project.get("planradar_project_id"),
            })

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="list_projects",
            parameters={},
            result={"count": len(formatted_projects)}
        )

        return {
            "success": True,
            "message": get_plural_translation("fr", "projects_found", len(formatted_projects)),
            "data": formatted_projects
        }

    except Exception as e:
        log.error(f"Error in list_projects: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des projets.",
            "error": str(e)
        }


async def get_project_details(user_id: str, project_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific project."""
    try:
        # Pass user_id for authorization check
        project = await supabase_client.get_project(project_id, user_id=user_id)

        if not project:
            return {
                "success": False,
                "message": "Projet non trouvé."
            }

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_project_details",
            parameters={"project_id": project_id},
            result={"project": project.get("nom")}
        )

        return {
            "success": True,
            "message": "Détails du projet récupérés.",
            "data": project
        }

    except Exception as e:
        log.error(f"Error in get_project_details: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des détails du projet.",
            "error": str(e)
        }
