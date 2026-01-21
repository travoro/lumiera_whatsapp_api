"""Common helper functions for direct handlers.

IMPORTANT: All helpers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""

from typing import Any, Dict, List, Optional, Tuple

from src.integrations.supabase import supabase_client
from src.utils.logger import log
from src.utils.whatsapp_formatter import get_translation


async def get_projects_with_context(
    user_id: str, language: str
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """Get user's projects with active project context.

    This is a common pattern used across multiple handlers to:
    1. Fetch all projects for the user
    2. Check for active project context (7-hour window)
    3. Return formatted response based on scenario

    Args:
        user_id: Subcontractor ID
        language: User's language code

    Returns:
        Tuple of (projects, current_project_id, message_if_no_projects)
        - projects: List of project dicts
        - current_project_id: Active project ID if within 7-hour window, else None
        - message_if_no_projects: Translated "no projects" message if applicable, else None

    Example:
        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, "fr")
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

        # Check for active project context (7-hour window)
        from src.services.project_context import project_context_service

        current_project_id = await project_context_service.get_active_project(user_id)
        if current_project_id:
            log.debug(
                f"✅ Active project context found for user {user_id}: {current_project_id[:8]}..."
            )

        return (projects, current_project_id, None)

    except Exception as e:
        log.error(f"Error in get_projects_with_context for user {user_id}: {e}")
        # Return empty results on error (ALWAYS French)
        no_projects_msg = get_translation("fr", "no_projects")
        return ([], None, no_projects_msg)


def format_project_list(
    projects: List[Dict[str, Any]],
    language: str,
    max_items: int = 5,
    header_key: str = "project_list",
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
