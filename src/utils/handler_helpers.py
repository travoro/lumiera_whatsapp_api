"""Common helper functions for direct handlers.

IMPORTANT: All helpers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""
from typing import Tuple, List, Dict, Any, Optional
from src.integrations.supabase import supabase_client
from src.utils.whatsapp_formatter import get_translation
from src.utils.logger import log


async def get_projects_with_context(
    user_id: str,
    language: str
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """Get user's projects.

    This is a common pattern used across multiple handlers to:
    1. Fetch all projects for the user
    2. Return formatted response based on scenario

    Args:
        user_id: Subcontractor ID
        language: User's language code

    Returns:
        Tuple of (projects, None, message_if_no_projects)
        - projects: List of project dicts
        - None: Placeholder for backwards compatibility (previously current_project_id)
        - message_if_no_projects: Translated "no projects" message if applicable, else None

    Example:
        projects, _, no_projects_msg = await get_projects_with_context(user_id, "fr")
        if no_projects_msg:
            return {"message": no_projects_msg, ...}
    """
    try:
        # Get user's projects
        projects = await supabase_client.list_projects(user_id)

        # If no projects, return error message (ALWAYS French)
        if not projects:
            no_projects_msg = get_translation("fr", "no_projects")
            return ([], None, no_projects_msg)

        return (projects, None, None)

    except Exception as e:
        log.error(f"Error in get_projects_with_context for user {user_id}: {e}")
        # Return empty results on error (ALWAYS French)
        no_projects_msg = get_translation("fr", "no_projects")
        return ([], None, no_projects_msg)


def format_project_list(
    projects: List[Dict[str, Any]],
    language: str,
    max_items: int = 5,
    header_key: str = "project_list"
) -> str:
    """Format a list of projects as numbered text.

    IMPORTANT: Always returns French text. Translation to user language
    happens in the pipeline.

    Args:
        projects: List of project dicts with 'nom' field
        language: User's language code (kept for compatibility, always uses "fr")
        max_items: Maximum number of projects to show
        header_key: Translation key for header (e.g. "project_list")

    Returns:
        Formatted string with numbered project list (ALWAYS in French)
    """
    # Get header from centralized translations (ALWAYS French)
    header = get_translation("fr", "available_projects_header")
    message = header

    for i, project in enumerate(projects[:max_items], 1):
        message += f"{i}. {project['nom']}\n"

    return message
