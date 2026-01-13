"""Task-related intent handlers.

These handlers execute directly without calling the main agent,
providing fast responses for task operations.

IMPORTANT: All handlers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""
from typing import Dict, Any
from src.actions import tasks as task_actions
from src.utils.whatsapp_formatter import get_translation
from src.utils.handler_helpers import get_projects_with_context, format_project_list
from src.utils.response_helpers import build_no_projects_response, get_selected_project
from src.utils.logger import log


async def handle_list_tasks(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Dict[str, Any]:
    """Handle list tasks intent with context-aware project selection.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling list tasks for {user_id}")

    try:
        # Use helper to get projects and context
        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return build_no_projects_response(language)

        # Scenario 2: Has current project in context
        if current_project_id:
            # Use header for showing tasks
            message = get_translation("fr", "list_tasks_header")
            # Get selected project or fallback
            project, project_name, project_id = get_selected_project(projects, current_project_id)

            message += get_translation("fr", "list_tasks_project_context").format(project_name=project_name)

            # Get tasks for this project using actions layer
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += get_translation("fr", "list_tasks_no_tasks")
            else:
                tasks = task_result["data"]
                message += get_translation("fr", "list_tasks_tasks_header")
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    status = task.get('status', 'pending')
                    progress = task.get('progress', 0)

                    # Status emoji
                    status_emoji = "⏳" if status == "pending" else "✅" if status == "completed" else "🔄"

                    message += f"{i}. {status_emoji} {task['title']}"
                    if progress > 0:
                        message += f" ({progress}%)"
                    message += "\n"

            message += get_translation("fr", "list_tasks_footer")

        # Scenario 3: Has projects but no current project in context
        else:
            # Use header for asking which project
            message = get_translation("fr", "list_tasks_select_header")

            # Use helper to format project list
            message += format_project_list(projects, language, max_items=5)

            # Add prompt to select project using centralized translation
            message += get_translation("fr", "list_tasks_select_project")

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

    except Exception as e:
        log.error(f"Error in fast path list_tasks: {e}")
        # Return None to trigger fallback to full agent
        return None


async def handle_update_progress(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Dict[str, Any]:
    """Handle update progress intent with context-aware project and task selection.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling update progress for {user_id}")

    try:
        # Use helper to get projects and context
        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return build_no_projects_response(language)

        # Use centralized translations
        message = get_translation("fr", "update_progress_header")

        # Scenario 2: Has current project in context
        if current_project_id:
            # Get selected project or fallback
            project, project_name, project_id = get_selected_project(projects, current_project_id)

            message += get_translation("fr", "update_progress_project_context").format(project_name=project_name)

            # Get tasks for this project using actions layer
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += get_translation("fr", "update_progress_no_tasks")
            else:
                tasks = task_result["data"]
                message += get_translation("fr", "update_progress_tasks_header")
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    progress = task.get('progress', 0)
                    message += f"{i}. {task['title']} ({progress}%)\n"

            message += get_translation("fr", "update_progress_footer")

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list
            message += format_project_list(projects, language, max_items=5)

            message += get_translation("fr", "update_progress_footer")

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

    except Exception as e:
        log.error(f"Error in fast path update_progress: {e}")
        # Return None to trigger fallback to full agent
        return None
