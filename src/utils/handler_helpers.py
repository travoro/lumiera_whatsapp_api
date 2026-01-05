"""Common helper functions for direct handlers."""
from typing import Tuple, List, Dict, Any, Optional
from src.integrations.supabase import supabase_client
from src.services.user_context import user_context_service
from src.utils.whatsapp_formatter import get_translation
from src.utils.logger import log


async def get_projects_with_context(
    user_id: str,
    language: str
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """Get user's projects and current project context.
    
    This is a common pattern used across multiple handlers to:
    1. Check for current_project in user context
    2. Fetch all projects for the user  
    3. Return formatted response based on scenario
    
    Args:
        user_id: Subcontractor ID
        language: User's language code
        
    Returns:
        Tuple of (projects, current_project_id, message_if_no_projects)
        - projects: List of project dicts
        - current_project_id: Current project ID from context or None
        - message_if_no_projects: Translated "no projects" message if applicable, else None
        
    Example:
        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, "fr")
        if no_projects_msg:
            return {"message": no_projects_msg, ...}
    """
    try:
        # Check for current project in context
        current_project_id = await user_context_service.get_context(user_id, 'current_project')
        
        # Get user's projects
        projects = await supabase_client.list_projects(user_id)
        
        # If no projects, return error message
        if not projects:
            no_projects_msg = get_translation(language, "no_projects")
            return ([], None, no_projects_msg)
            
        return (projects, current_project_id, None)
        
    except Exception as e:
        log.error(f"Error in get_projects_with_context for user {user_id}: {e}")
        # Return empty results on error
        no_projects_msg = get_translation(language, "no_projects")
        return ([], None, no_projects_msg)


def format_project_list(
    projects: List[Dict[str, Any]],
    language: str,
    max_items: int = 5,
    header_key: str = "project_list"
) -> str:
    """Format a list of projects as numbered text.
    
    Args:
        projects: List of project dicts with 'name' field
        language: User's language code
        max_items: Maximum number of projects to show
        header_key: Translation key for header (e.g. "project_list")
        
    Returns:
        Formatted string with numbered project list
    """
    # Get header from translations if available
    prompts = {
        "fr": "Chantiers disponibles :\n",
        "en": "Available sites:\n",
        "es": "Obras disponibles:\n",
        "pt": "Obras disponíveis:\n",
        "de": "Verfügbare Baustellen:\n",
        "it": "Cantieri disponibili:\n",
        "ro": "Șantiere disponibile:\n",
        "pl": "Dostępne place budowy:\n",
        "ar": "مواقع البناء المتاحة:\n"
    }
    
    header = prompts.get(language, prompts["en"])
    message = header
    
    for i, project in enumerate(projects[:max_items], 1):
        message += f"{i}. {project['name']}\n"
        
    return message
