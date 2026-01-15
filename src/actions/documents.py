"""Document access action handlers."""
from typing import Dict, Any, Optional
from src.integrations.planradar import planradar_client
from src.integrations.supabase import supabase_client
from src.utils.logger import log


async def get_documents(
    user_id: str,
    project_id: str,
    folder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Get documents for a project.

    Args:
        user_id: User ID requesting documents
        project_id: Project ID to get documents from
        folder_id: Optional folder ID to filter documents

    Returns:
        Result dictionary with success status and documents list
    """
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

        # Fetch documents from PlanRadar using PlanRadar project ID
        # Use get_project_documents() which retrieves plans via components workflow
        try:
            documents = await planradar_client.get_project_documents(
                project_id=planradar_project_id
            )
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

        if not documents:
            return {
                "success": True,
                "message": "Aucun document trouvé.",
                "data": []
            }

        # Format documents for display
        # get_project_documents() returns plans with component info
        formatted_docs = []
        for doc in documents:
            formatted_docs.append({
                "id": doc.get("id"),
                "name": doc.get("name"),  # Plan name (e.g., "La_plateforme.pdf")
                "type": doc.get("content_type", "application/pdf"),  # MIME type
                "url": doc.get("url"),  # original-url from PlanRadar
                "size": doc.get("file_size"),  # File size in bytes
                "component_name": doc.get("component_name"),  # Room/area name (e.g., "Principal")
                "thumbnail_url": doc.get("thumbnail_url"),  # Optional thumbnail
            })

        # Log action
        await supabase_client.save_action_log(
            user_id=user_id,
            action_name="get_documents",
            parameters={
                "project_id": project_id,
                "folder_id": folder_id,
            },
            result={"count": len(formatted_docs)}
        )

        return {
            "success": True,
            "message": f"{len(formatted_docs)} document(s) trouvé(s).",
            "data": formatted_docs
        }

    except Exception as e:
        log.error(f"Error in get_documents: {e}")
        return {
            "success": False,
            "message": "Erreur lors de la récupération des documents.",
            "error": str(e)
        }
