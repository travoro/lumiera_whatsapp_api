"""Helper functions for building consistent response structures.

IMPORTANT: All helpers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""
from typing import Dict, Any, List, Optional
from src.utils.whatsapp_formatter import get_translation


def build_no_projects_response(language: str) -> Dict[str, Any]:
    """Build standard 'no projects' response.

    Args:
        language: User's language code

    Returns:
        Standard response dict
    """
    return {
        "message": get_translation("fr", "no_projects"),
        "escalation": False,
        "tools_called": [],
        "fast_path": True
    }


def build_fast_path_response(
    message: str,
    tools_called: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Build standard fast path response.

    Args:
        message: Response message text
        tools_called: List of tools that were called (default: empty list)

    Returns:
        Standard fast path response dict
    """
    return {
        "message": message,
        "escalation": False,
        "tools_called": tools_called or [],
        "fast_path": True
    }


def build_error_response(
    language: str,
    error_key: str = "error_generic"
) -> Dict[str, Any]:
    """Build standard error response.

    Args:
        language: User's language code
        error_key: Translation key for error message

    Returns:
        Standard error response dict
    """
    return {
        "message": get_translation("fr", error_key),
        "escalation": False,
        "tools_called": [],
        "fast_path": True,
        "error": True
    }


def get_selected_project(
    projects: List[Dict[str, Any]],
    current_project_id: Optional[str]
) -> tuple[Optional[Dict[str, Any]], str, str]:
    """Get the selected project or fallback to first project.

    Args:
        projects: List of project dicts
        current_project_id: Current project ID from context

    Returns:
        Tuple of (project_dict, project_name, project_id)
    """
    if not projects:
        return None, "", ""

    if current_project_id:
        # Find the current project
        current_project = next(
            (p for p in projects if str(p.get('id')) == current_project_id),
            None
        )
    else:
        current_project = None

    # Use current project or fallback to first
    project = current_project if current_project else projects[0]
    return project, project['name'], project['id']
