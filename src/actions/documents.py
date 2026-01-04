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
        documents = await planradar_client.get_documents(
            project_id=project_id,
            folder_id=folder_id,
        )

        if not documents:
            return {
                "success": True,
                "message": "Aucun document trouvé.",
                "data": []
            }

        # Format documents for display
        formatted_docs = []
        for doc in documents:
            formatted_docs.append({
                "id": doc.get("id"),
                "name": doc.get("name"),
                "type": doc.get("type"),
                "url": doc.get("url"),
                "size": doc.get("size"),
                "created_at": doc.get("created_at"),
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
