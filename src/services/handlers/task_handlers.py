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
from src.utils.metadata_helpers import compact_projects, compact_tasks
from src.utils.fuzzy_matcher import fuzzy_match_project
from src.utils.logger import log


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
            log.debug(f"🔢 Attempting to resolve numeric selection: '{message_text}' (index: {selection_index})")
            log.debug(f"📦 Available tool_outputs: {[t.get('tool') for t in last_tool_outputs]}")

            # Find projects in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get('tool') == 'list_projects_tool':
                    output_projects = tool_output.get('output', [])
                    log.debug(f"📋 Found list_projects_tool with {len(output_projects)} projects")

                    if 0 <= selection_index < len(output_projects):
                        mentioned_project_id = output_projects[selection_index].get('id')
                        project_name = output_projects[selection_index].get('nom')
                        log.info(f"✅ Resolved numeric selection '{message_text}' → {project_name} (ID: {mentioned_project_id})")
                        break
                    else:
                        log.warning(f"⚠️ Selection index {selection_index} out of range (0-{len(output_projects)-1})")

            if not mentioned_project_id:
                log.warning(f"⚠️ Could not resolve numeric selection '{message_text}' - no list_projects_tool found in tool_outputs")

        # Scenario 3: Extract project name from message if mentioned (exact match)
        # User might say "taches pour Champigny" or just "champigny"
        if not mentioned_project_id and message_text and not current_project_id:
            log.debug(f"🔎 Scenario 3: Trying exact match for '{message_text}'")
            message_lower = message_text.lower()
            for project in projects:
                project_name = project.get('nom', '').lower()
                if project_name and project_name in message_lower:
                    mentioned_project_id = project.get('id')
                    log.info(f"✅ Exact match: Extracted project '{project.get('nom')}' from message")
                    break

            if not mentioned_project_id:
                log.debug(f"❌ Exact match failed for '{message_text}'")

        # Scenario 3b: Try fuzzy matching if exact match failed
        if not mentioned_project_id and message_text and not current_project_id:
            log.debug(f"🔎 Scenario 3b: Trying fuzzy match for '{message_text}'")
            fuzzy_result = fuzzy_match_project(message_text, projects, threshold=0.80)

            if fuzzy_result:
                mentioned_project_id = fuzzy_result['project_id']
                log.info(f"✅ Fuzzy match: '{message_text}' → '{fuzzy_result['project_name']}' (confidence: {fuzzy_result['confidence']:.2%})")
            else:
                log.debug(f"❌ Fuzzy match failed for '{message_text}'")

        # Use mentioned project if found, otherwise use active context
        selected_project_id = mentioned_project_id or current_project_id

        # Log parameter resolution result
        if selected_project_id:
            resolution_method = "mentioned" if mentioned_project_id else "active_context"
            log.info(f"✅ Parameter resolution successful: project_id={selected_project_id[:8]}... (method: {resolution_method})")
        else:
            log.warning(f"⚠️ Parameter resolution FAILED: No project context available")
            log.debug(f"   - mentioned_project_id: {mentioned_project_id}")
            log.debug(f"   - current_project_id: {current_project_id}")
            log.debug(f"   - message_text: '{message_text}'")
            log.debug(f"   - available_projects: {len(projects)}")

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
                "output": compact_projects([project])  # Only essential fields
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
                    "output": compact_tasks(tasks)  # Only essential fields
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

            return {
                "message": message,
                "escalation": False,
                "tools_called": [],
                "fast_path": True,
                "tool_outputs": tool_outputs
            }

        # Scenario 5: Parameters unclear - Route to full AI agent
        else:
            log.warning(f"🤖 FAST PATH FALLBACK → Routing to full AI agent")
            log.info(f"   Reason: Could not determine which project user wants")
            log.info(f"   User message: '{message_text}'")
            log.info(f"   Available projects: {[p.get('nom') for p in projects[:5]]}")
            log.info(f"   AI agent will use conversation history to understand user intent")

            # Return None to signal that full AI agent should handle this
            return None

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
            log.debug(f"🔢 Attempting to resolve numeric selection: '{message_text}' (index: {selection_index})")
            log.debug(f"📦 Available tool_outputs: {[t.get('tool') for t in last_tool_outputs]}")

            # Find projects in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get('tool') == 'list_projects_tool':
                    output_projects = tool_output.get('output', [])
                    log.debug(f"📋 Found list_projects_tool with {len(output_projects)} projects")

                    if 0 <= selection_index < len(output_projects):
                        mentioned_project_id = output_projects[selection_index].get('id')
                        project_name = output_projects[selection_index].get('nom')
                        log.info(f"✅ Resolved numeric selection '{message_text}' → {project_name} (ID: {mentioned_project_id})")
                        break
                    else:
                        log.warning(f"⚠️ Selection index {selection_index} out of range (0-{len(output_projects)-1})")

            if not mentioned_project_id:
                log.warning(f"⚠️ Could not resolve numeric selection '{message_text}' - no list_projects_tool found in tool_outputs")

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
                "output": compact_projects([project])  # Only essential fields
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
                    "output": compact_tasks(tasks)  # Only essential fields
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
                "output": compact_projects(projects[:5])  # Only essential fields
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
