"""Task-related intent handlers.

These handlers execute directly without calling the main agent,
providing fast responses for task operations.

IMPORTANT: All handlers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""
from typing import Dict, Any, List
from src.actions import tasks as task_actions
from src.utils.whatsapp_formatter import get_translation
from src.utils.handler_helpers import get_projects_with_context, format_project_list
from src.utils.response_helpers import build_no_projects_response, get_selected_project
from src.utils.logger import log


def _compact_projects(projects: List[Dict]) -> List[Dict]:
    """Extract only essential fields from projects for metadata storage."""
    return [
        {
            "id": p.get("id"),
            "nom": p.get("nom"),
            "planradar_project_id": p.get("planradar_project_id")
        }
        for p in projects
    ]


def _compact_tasks(tasks: List[Dict]) -> List[Dict]:
    """Extract only essential fields from tasks for metadata storage."""
    return [
        {
            "id": t.get("id"),
            "title": t.get("title"),
            "status": t.get("status"),
            "progress": t.get("progress")
        }
        for t in tasks
    ]


async def handle_list_tasks(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    message_text: str = "",
    last_tool_outputs: list = None,
    session_id: str = None,
    **kwargs
) -> Dict[str, Any]:
    """Handle list tasks intent with context-aware project selection.

    Args:
        message_text: User's message text for extracting project name if mentioned
        last_tool_outputs: Tool outputs from previous bot message (for resolving numeric selections)
        session_id: Session ID for context

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

        # Scenario 2: Resolve numeric selection from last tool_outputs
        mentioned_project_id = None
        if message_text and message_text.strip().isdigit() and last_tool_outputs:
            selection_index = int(message_text.strip()) - 1  # Convert to 0-based index
            # Find projects in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get('tool') == 'list_projects_tool':
                    output_projects = tool_output.get('output', [])
                    if 0 <= selection_index < len(output_projects):
                        mentioned_project_id = output_projects[selection_index].get('id')
                        project_name = output_projects[selection_index].get('nom')
                        log.info(f"🔢 Resolved numeric selection {message_text} → {project_name} (ID: {mentioned_project_id})")
                        break

        # Scenario 3: Extract project name from message if mentioned
        # User might say "taches pour Champigny" or just "champigny"
        if not mentioned_project_id and message_text and not current_project_id:
            message_lower = message_text.lower()
            for project in projects:
                project_name = project.get('nom', '').lower()
                if project_name and project_name in message_lower:
                    mentioned_project_id = project.get('id')
                    log.info(f"📍 Extracted project from message: {project.get('nom')}")
                    break

        # Use mentioned project if found, otherwise use active context
        selected_project_id = mentioned_project_id or current_project_id
        tool_outputs = []

        # Scenario 4: Has selected project (from message or context)
        if selected_project_id:
            # Use header for showing tasks
            message = get_translation("fr", "list_tasks_header")
            # Get selected project or fallback
            project, project_name, project_id = get_selected_project(projects, selected_project_id)

            # Set active project in database when user makes a selection
            if mentioned_project_id:  # User explicitly selected this project
                from src.services.project_context import project_context_service
                await project_context_service.set_active_project(user_id, project_id, project_name)
                log.info(f"✅ Set active project: {project_name} (ID: {project_id})")

            message += get_translation("fr", "list_tasks_project_context").format(project_name=project_name)

            # Store the selected project in tool_outputs for context
            tool_outputs.append({
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": _compact_projects([project])  # Only essential fields
            })

            # Get tasks for this project using actions layer
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += get_translation("fr", "list_tasks_no_tasks")
            else:
                tasks = task_result["data"]
                # Store tasks in tool_outputs
                tool_outputs.append({
                    "tool": "list_tasks_tool",
                    "input": {"user_id": user_id, "project_id": project_id},
                    "output": _compact_tasks(tasks)  # Only essential fields
                })

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

        # Scenario 5: Has projects but no selection (ask which project)
        else:
            # Use header for asking which project
            message = get_translation("fr", "list_tasks_select_header")

            # Use helper to format project list
            message += format_project_list(projects, language, max_items=5)

            # Add prompt to select project using centralized translation
            message += get_translation("fr", "list_tasks_select_project")

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append({
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": _compact_projects(projects[:5])  # Only essential fields
            })

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs
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
    message_text: str = "",
    last_tool_outputs: list = None,
    session_id: str = None,
    **kwargs
) -> Dict[str, Any]:
    """Handle update progress intent with context-aware project and task selection.

    Args:
        message_text: User's message text for extracting project name if mentioned
        last_tool_outputs: Tool outputs from previous bot message (for resolving numeric selections)
        session_id: Session ID for context

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

        # Scenario 2: Resolve numeric selection from last tool_outputs
        mentioned_project_id = None
        if message_text and message_text.strip().isdigit() and last_tool_outputs:
            selection_index = int(message_text.strip()) - 1  # Convert to 0-based index
            # Find projects in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get('tool') == 'list_projects_tool':
                    output_projects = tool_output.get('output', [])
                    if 0 <= selection_index < len(output_projects):
                        mentioned_project_id = output_projects[selection_index].get('id')
                        project_name = output_projects[selection_index].get('nom')
                        log.info(f"🔢 Resolved numeric selection {message_text} → {project_name} (ID: {mentioned_project_id})")
                        break

        # Scenario 3: Extract project name from message if mentioned
        mentioned_project_id_from_text = None
        if not mentioned_project_id and message_text and not current_project_id:
            message_lower = message_text.lower()
            for project in projects:
                project_name = project.get('nom', '').lower()
                if project_name and project_name in message_lower:
                    mentioned_project_id_from_text = project.get('id')
                    log.info(f"📍 Extracted project from message: {project.get('nom')}")
                    break

        # Use mentioned project if found, otherwise use active context
        selected_project_id = mentioned_project_id or mentioned_project_id_from_text or current_project_id
        tool_outputs = []

        # Use centralized translations
        message = get_translation("fr", "update_progress_header")

        # Scenario 4: Has selected project (from message or context)
        if selected_project_id:
            # Get selected project or fallback
            project, project_name, project_id = get_selected_project(projects, selected_project_id)

            # Set active project in database when user makes a selection
            if mentioned_project_id or mentioned_project_id_from_text:  # User explicitly selected this project
                from src.services.project_context import project_context_service
                await project_context_service.set_active_project(user_id, project_id, project_name)
                log.info(f"✅ Set active project: {project_name} (ID: {project_id})")

            message += get_translation("fr", "update_progress_project_context").format(project_name=project_name)

            # Store the selected project in tool_outputs for context
            tool_outputs.append({
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": _compact_projects([project])  # Only essential fields
            })

            # Get tasks for this project using actions layer
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += get_translation("fr", "update_progress_no_tasks")
            else:
                tasks = task_result["data"]
                # Store tasks in tool_outputs
                tool_outputs.append({
                    "tool": "list_tasks_tool",
                    "input": {"user_id": user_id, "project_id": project_id},
                    "output": _compact_tasks(tasks)  # Only essential fields
                })

                message += get_translation("fr", "update_progress_tasks_header")
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    progress = task.get('progress', 0)
                    message += f"{i}. {task['title']} ({progress}%)\n"

            message += get_translation("fr", "update_progress_footer")

        # Scenario 5: Has projects but no selection (ask which project)
        else:
            # Use helper to format project list
            message += format_project_list(projects, language, max_items=5)

            message += get_translation("fr", "update_progress_footer")

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append({
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": _compact_projects(projects[:5])  # Only essential fields
            })

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs
        }

    except Exception as e:
        log.error(f"Error in fast path update_progress: {e}")
        # Return None to trigger fallback to full agent
        return None
