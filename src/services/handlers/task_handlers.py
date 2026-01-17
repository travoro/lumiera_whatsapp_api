"""Task-related intent handlers.

These handlers execute directly without calling the main agent,
providing fast responses for task operations.

IMPORTANT: All handlers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""

from typing import Any, Dict

from src.actions import tasks as task_actions
from src.services.project_context import project_context_service
from src.utils.fuzzy_matcher import fuzzy_match_project
from src.utils.handler_helpers import format_project_list, get_projects_with_context
from src.utils.logger import log
from src.utils.metadata_helpers import compact_projects, compact_tasks
from src.utils.response_helpers import build_no_projects_response, get_selected_project
from src.utils.whatsapp_formatter import get_translation


async def handle_list_tasks(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    message_text: str = "",
    last_tool_outputs: list = None,
    session_id: str = None,
    **kwargs,
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
        projects, current_project_id, no_projects_msg = await get_projects_with_context(
            user_id, language
        )

        # Scenario 1: No projects available
        if no_projects_msg:
            return build_no_projects_response(language)

        # Scenario 2: Resolve numeric selection from last tool_outputs
        mentioned_project_id = None
        if message_text and message_text.strip().isdigit() and last_tool_outputs:
            selection_index = int(message_text.strip()) - 1  # Convert to 0-based index
            log.debug(
                f"🔢 Attempting to resolve numeric selection: '{message_text}' (index: {selection_index})"
            )
            log.debug(
                f"📦 Available tool_outputs: {[t.get('tool') for t in last_tool_outputs]}"
            )

            # Find projects in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get("tool") == "list_projects_tool":
                    output_projects = tool_output.get("output", [])
                    log.debug(
                        f"📋 Found list_projects_tool with {len(output_projects)} projects"
                    )

                    if 0 <= selection_index < len(output_projects):
                        mentioned_project_id = output_projects[selection_index].get(
                            "id"
                        )
                        project_name = output_projects[selection_index].get("nom")
                        log.info(
                            f"✅ Resolved numeric selection '{message_text}' → {project_name} (ID: {mentioned_project_id})"
                        )
                        break
                    else:
                        log.warning(
                            f"⚠️ Selection index {selection_index} out of range (0-{len(output_projects) - 1})"
                        )

            if not mentioned_project_id:
                log.warning(
                    f"⚠️ Could not resolve numeric selection '{message_text}' - no list_projects_tool found in tool_outputs"
                )

        # Scenario 3: Extract project name from message if mentioned (exact match)
        # User might say "taches pour Champigny" or just "champigny"
        if not mentioned_project_id and message_text and not current_project_id:
            log.debug(f"🔎 Scenario 3: Trying exact match for '{message_text}'")
            message_lower = message_text.lower()
            for project in projects:
                project_name = project.get("nom", "").lower()
                if project_name and project_name in message_lower:
                    mentioned_project_id = project.get("id")
                    log.info(
                        f"✅ Exact match: Extracted project '{project.get('nom')}' from message"
                    )
                    break

            if not mentioned_project_id:
                log.debug(f"❌ Exact match failed for '{message_text}'")

        # Scenario 3b: Try fuzzy matching if exact match failed
        if not mentioned_project_id and message_text and not current_project_id:
            log.debug(f"🔎 Scenario 3b: Trying fuzzy match for '{message_text}'")
            fuzzy_result = fuzzy_match_project(message_text, projects, threshold=0.80)

            if fuzzy_result:
                mentioned_project_id = fuzzy_result["project_id"]
                log.info(
                    f"✅ Fuzzy match: '{message_text}' → '{
                        fuzzy_result['project_name']}' (confidence: {
                        fuzzy_result['confidence']:.2%})"
                )
            else:
                log.debug(f"❌ Fuzzy match failed for '{message_text}'")

        # Use mentioned project if found, otherwise use active context
        selected_project_id = mentioned_project_id or current_project_id

        # Scenario 3c: Single project available - Auto-select it
        if not selected_project_id and len(projects) == 1:
            selected_project_id = projects[0].get("id")
            project_name = projects[0].get("nom")
            log.info(
                f"✅ Auto-selected single available project: {project_name} (ID: {selected_project_id[:8]}...)"
            )

        # Scenario 3d: Multiple projects available - Show project picker
        if not selected_project_id and len(projects) > 1:
            log.info(
                f"📋 Multiple projects available ({len(projects)}) - Showing project picker"
            )
            message = get_translation("fr", "list_projects_header")

            tool_outputs = []
            tool_outputs.append(
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects(projects),
                }
            )

            for i, project in enumerate(projects, 1):
                message += f"{i}. 🏗️ {project.get('nom')}\n"

            message += "\n" + get_translation("fr", "list_projects_footer")

            return {
                "message": message,
                "escalation": False,
                "tools_called": [],
                "fast_path": True,
                "tool_outputs": tool_outputs,
                "list_type": "projects",
            }

        # Log parameter resolution result
        if selected_project_id:
            resolution_method = (
                "mentioned"
                if mentioned_project_id
                else "active_context" if current_project_id else "auto_selected"
            )
            log.info(
                f"✅ Parameter resolution successful: project_id={selected_project_id[:8]}... (method: {resolution_method})"
            )

        tool_outputs = []

        # Scenario 4: Has selected project (from message or context or auto-select)
        if selected_project_id:
            # Use header for showing tasks
            message = get_translation("fr", "list_tasks_header")
            # Get selected project or fallback
            project, project_name, project_id = get_selected_project(
                projects, selected_project_id
            )

            # Set active project in database when user makes a selection
            if mentioned_project_id:  # User explicitly selected this project
                from src.services.project_context import project_context_service

                await project_context_service.set_active_project(
                    user_id, project_id, project_name
                )
                log.info(f"✅ Set active project: {project_name} (ID: {project_id})")

            message += get_translation("fr", "list_tasks_project_context").format(
                project_name=project_name
            )

            # Store the selected project in tool_outputs for context
            tool_outputs.append(
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects([project]),  # Only essential fields
                }
            )

            # Get structured data from actions layer
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"]:
                # Use the specific error message (e.g., rate limit, API error)
                message += task_result.get(
                    "message", get_translation("fr", "list_tasks_no_tasks")
                )
            elif not task_result["data"]:
                # Success but no tasks found
                message += get_translation("fr", "list_tasks_no_tasks")
            else:
                tasks = task_result["data"]
                # Store tasks in tool_outputs
                tool_outputs.append(
                    {
                        "tool": "list_tasks_tool",
                        "input": {"user_id": user_id, "project_id": project_id},
                        "output": compact_tasks(tasks),  # Only essential fields
                    }
                )

                message += get_translation("fr", "list_tasks_tasks_header")
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    status = task.get("status", "pending")
                    progress = task.get("progress", 0)

                    # Status emoji
                    status_emoji = (
                        "⏳"
                        if status == "pending"
                        else "✅" if status == "completed" else "🔄"
                    )

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
                "tool_outputs": tool_outputs,
                "list_type": "tasks",  # Metadata for robust interactive list handling
            }

        # Scenario 5: Parameters unclear - Route to full AI agent
        else:
            log.warning("🤖 FAST PATH FALLBACK → Routing to full AI agent")
            log.info("   Reason: Could not determine which project user wants")
            log.info(f"   User message: '{message_text}'")
            log.info(f"   Available projects: {[p.get('nom') for p in projects[:5]]}")
            log.info(
                "   AI agent will use conversation history to understand user intent"
            )

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
    **kwargs,
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
        projects, current_project_id, no_projects_msg = await get_projects_with_context(
            user_id, language
        )

        # Scenario 1: No projects available
        if no_projects_msg:
            return build_no_projects_response(language)

        # Scenario 2: Resolve numeric selection from last tool_outputs
        mentioned_project_id = None
        if message_text and message_text.strip().isdigit() and last_tool_outputs:
            selection_index = int(message_text.strip()) - 1  # Convert to 0-based index
            log.debug(
                f"🔢 Attempting to resolve numeric selection: '{message_text}' (index: {selection_index})"
            )
            log.debug(
                f"📦 Available tool_outputs: {[t.get('tool') for t in last_tool_outputs]}"
            )

            # Find projects in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get("tool") == "list_projects_tool":
                    output_projects = tool_output.get("output", [])
                    log.debug(
                        f"📋 Found list_projects_tool with {len(output_projects)} projects"
                    )

                    if 0 <= selection_index < len(output_projects):
                        mentioned_project_id = output_projects[selection_index].get(
                            "id"
                        )
                        project_name = output_projects[selection_index].get("nom")
                        log.info(
                            f"✅ Resolved numeric selection '{message_text}' → {project_name} (ID: {mentioned_project_id})"
                        )
                        break
                    else:
                        log.warning(
                            f"⚠️ Selection index {selection_index} out of range (0-{len(output_projects) - 1})"
                        )

            if not mentioned_project_id:
                log.warning(
                    f"⚠️ Could not resolve numeric selection '{message_text}' - no list_projects_tool found in tool_outputs"
                )

        # Scenario 3: Extract project name from message if mentioned
        mentioned_project_id_from_text = None
        if not mentioned_project_id and message_text and not current_project_id:
            message_lower = message_text.lower()
            for project in projects:
                project_name = project.get("nom", "").lower()
                if project_name and project_name in message_lower:
                    mentioned_project_id_from_text = project.get("id")
                    log.info(f"📍 Extracted project from message: {project.get('nom')}")
                    break

        # Use mentioned project if found, otherwise use active context
        selected_project_id = (
            mentioned_project_id or mentioned_project_id_from_text or current_project_id
        )
        tool_outputs = []

        # Use centralized translations
        message = get_translation("fr", "update_progress_header")

        # Scenario 4: Has selected project (from message or context)
        if selected_project_id:
            # Get selected project or fallback
            project, project_name, project_id = get_selected_project(
                projects, selected_project_id
            )

            # Set active project in database when user makes a selection
            if (
                mentioned_project_id or mentioned_project_id_from_text
            ):  # User explicitly selected this project
                from src.services.project_context import project_context_service

                await project_context_service.set_active_project(
                    user_id, project_id, project_name
                )
                log.info(f"✅ Set active project: {project_name} (ID: {project_id})")

            message += get_translation("fr", "update_progress_project_context").format(
                project_name=project_name
            )

            # Store the selected project in tool_outputs for context
            tool_outputs.append(
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects([project]),  # Only essential fields
                }
            )

            # Get structured data from actions layer
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += get_translation("fr", "update_progress_no_tasks")
            else:
                tasks = task_result["data"]
                # Store tasks in tool_outputs
                tool_outputs.append(
                    {
                        "tool": "list_tasks_tool",
                        "input": {"user_id": user_id, "project_id": project_id},
                        "output": compact_tasks(tasks),  # Only essential fields
                    }
                )

                message += get_translation("fr", "update_progress_tasks_header")
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    progress = task.get("progress", 0)
                    message += f"{i}. {task['title']} ({progress}%)\n"

            message += get_translation("fr", "update_progress_footer")

        # Scenario 5: Has projects but no selection (ask which project)
        else:
            # Use helper to format project list
            message += format_project_list(projects, language, max_items=5)

            message += get_translation("fr", "update_progress_footer")

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append(
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects(projects[:5]),  # Only essential fields
                }
            )

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs,
        }

    except Exception as e:
        log.error(f"Error in fast path update_progress: {e}")
        # Return None to trigger fallback to full agent
        return None


async def handle_task_details(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    message_text: str = "",
    last_tool_outputs: list = None,
    session_id: str = None,
    **kwargs,
) -> Dict[str, Any]:
    """Handle task details intent with context-aware task selection.

    Displays task description and attachments:
    1. Text message with description and attachment count
    2. Each attachment sent as a separate message (up to 10 attachments)

    Supports:
    - Numeric selection from task list (e.g., "2")
    - Explicit task ID mention
    - Interactive button selections

    Args:
        message_text: User's message text for task selection
        last_tool_outputs: Tool outputs from previous bot message (for resolving numeric selections)
        session_id: Session ID for context

    Returns:
        Dict with message, escalation, tools_called, carousel_data
    """
    log.info(f"🚀 FAST PATH: Handling task details for {user_id}")

    try:
        # Scenario 1: Resolve numeric selection from last tool_outputs (task list)
        selected_task_id = None  # Now UUID (latest API standard)
        task_title = None

        # Log what we received for debugging
        log.info(f"📥 Received message_text: '{message_text}'")
        if last_tool_outputs:
            log.info(
                f"📥 Tool output keys: {[t.get('tool') for t in last_tool_outputs]}"
            )
        else:
            log.warning("⚠️ No last_tool_outputs available")

        # Scenario 1a: Numeric selection from task list
        if message_text and message_text.strip().isdigit() and last_tool_outputs:
            selection_index = int(message_text.strip()) - 1
            log.debug(
                f"🔢 Attempting to resolve numeric task selection: '{message_text}' (index: {selection_index})"
            )

            # Find tasks in last tool_outputs
            for tool_output in last_tool_outputs:
                if tool_output.get("tool") == "list_tasks_tool":
                    output_tasks = tool_output.get("output", [])
                    log.debug(
                        f"📋 Found list_tasks_tool with {len(output_tasks)} tasks"
                    )

                    if 0 <= selection_index < len(output_tasks):
                        selected_task = output_tasks[selection_index]
                        selected_task_id = selected_task.get(
                            "id"
                        )  # Now UUID (primary identifier)
                        task_title = selected_task.get("title")
                        log.info(
                            f"✅ Resolved numeric selection '{message_text}' → {task_title} (UUID: {selected_task_id[:8]}...)"
                        )
                        break
                    else:
                        log.warning(
                            f"⚠️ Selection index {selection_index} out of range (0-{len(output_tasks) - 1})"
                        )

        # Scenario 1b: Check active task context (if user just asks for "details" without specifying)
        if not selected_task_id and not (
            message_text and message_text.strip().isdigit()
        ):
            active_task_id = await project_context_service.get_active_task(user_id)
            if active_task_id:
                log.info(f"📌 Using active task context: {active_task_id[:8]}...")
                selected_task_id = active_task_id
                # We'll need to fetch the title later

        # Scenario 2: No task selected - fallback to AI agent
        if not selected_task_id:
            log.warning("🤖 FAST PATH FALLBACK → Routing to full AI agent")
            log.info("   Reason: Could not determine which task user wants")
            log.info(f"   User message: '{message_text}'")
            return None

        # Scenario 3: Fetch task description and images in parallel
        tool_outputs = []

        # Get structured data from actions layer
        # selected_task_id is now UUID (latest API standard)
        log.info(
            f"📥 Fetching task description and images for task {selected_task_id[:8]}..."
        )
        desc_result = await task_actions.get_task_description(user_id, selected_task_id)
        images_result = await task_actions.get_task_images(user_id, selected_task_id)

        log.info(
            f"📊 Description result: success={
                desc_result.get('success')}, has_data={
                desc_result.get('data') is not None}"
        )
        log.info(
            f"📊 Images result: success={images_result.get('success')}, data_count={len(images_result.get('data', []))}"
        )

        # If we don't have task_title yet (used active context), get it from desc_result
        if not task_title and desc_result.get("success"):
            task_title = desc_result.get("data", {}).get("title", "Tâche")

        # Set active task context (1 hour expiration)
        await project_context_service.set_active_task(
            user_id, selected_task_id, task_title
        )

        # Build response message
        message = get_translation("fr", "task_details_header").format(
            task_title=task_title or "Tâche"
        )

        # Add description section
        if desc_result["success"] and desc_result["data"].get("description"):
            description = desc_result["data"]["description"]
            message += f"\n\n📄 Description:\n{description}"

            # Store description in tool_outputs
            tool_outputs.append(
                {
                    "tool": "get_task_description_tool",
                    "input": {"task_id": selected_task_id},
                    "output": {
                        "description": description[:200]
                    },  # Truncate for metadata
                }
            )
            log.info(f"✅ Added description to message ({len(description)} chars)")
        else:
            message += "\n\n📄 Aucune description disponible pour cette tâche."
            log.warning("⚠️ No description available")

        # Prepare attachment data for sending
        log.info("🔍 Preparing attachment data...")
        log.info(f"   images_result['success'] = {images_result.get('success')}")
        log.info(f"   images_result['data'] = {images_result.get('data')}")

        attachments = None
        if images_result["success"] and images_result["data"]:
            all_attachments = images_result["data"][:10]  # Limit to 10 attachments

            log.info(f"📎 Preparing {len(all_attachments)} attachments")
            for idx, att in enumerate(all_attachments, 1):
                url = att.get("url", "MISSING")
                att_type = att.get("type", "unknown")
                log.info(
                    f"   Attachment {idx}: type={att_type}, url={url[:80] if url != 'MISSING' and url else 'NONE'}..."
                )

            # FILTER OUT attachments without URLs (e.g., PDFs that PlanRadar doesn't provide URLs for)
            attachments_with_urls = [att for att in all_attachments if att.get("url")]
            attachments_without_urls = [
                att for att in all_attachments if not att.get("url")
            ]

            if attachments_without_urls:
                log.warning(
                    f"   ⚠️ Skipping {len(attachments_without_urls)} attachments without URLs:"
                )
                for att in attachments_without_urls:
                    log.warning(f"      - {att.get('type')}: {att.get('title')}")

            if attachments_with_urls:
                # Prepare simple attachments list for direct sending
                attachments = []
                for idx, att in enumerate(attachments_with_urls, 1):
                    # Generate filename from title, ID, or index
                    filename = att.get("title", "").strip()

                    # If no title, use attachment ID or index
                    if not filename:
                        att_id = att.get("id", "")
                        if att_id:
                            filename = f"attachment_{att_id[:8]}"
                        else:
                            filename = f"attachment_{idx}"

                    # Clean filename (remove extension, we'll add correct one based on content type)
                    filename = (
                        filename.replace(".jpg", "")
                        .replace(".jpeg", "")
                        .replace(".png", "")
                        .replace(".pd", "")
                    )

                    attachments.append(
                        {
                            "url": att.get("url"),
                            "content_type": att.get(
                                "content_type", "application/octet-stream"
                            ),
                            "filename": filename,
                        }
                    )

                log.info(
                    f"📦 Prepared {len(attachments)} attachments for direct sending"
                )
                for idx, att in enumerate(attachments, 1):
                    log.info(
                        f"   Attachment {idx}: filename='{att.get('filename')}', type={att.get('content_type')}"
                    )

                # Store attachments in tool_outputs (only those with URLs)
                tool_outputs.append(
                    {
                        "tool": "get_task_images_tool",
                        "input": {"task_id": selected_task_id},
                        "output": {
                            "count": len(attachments_with_urls),
                            "urls": [
                                att.get("url") for att in attachments_with_urls[:3]
                            ],
                        },
                    }
                )

            # Adapt message based on number of attachments
            attachment_count = len(all_attachments)
            sendable_count = len(attachments_with_urls) if attachments_with_urls else 0

            if attachment_count == 1:
                message += "\n\n📎 1 pièce jointe disponible"
            else:
                message += f"\n\n📎 {attachment_count} pièces jointes disponibles"

            # Warn if some attachments can't be sent
            if sendable_count < attachment_count:
                unsendable_count = attachment_count - sendable_count
                message += f"\n⚠️ {unsendable_count} pièce(s) jointe(s) ne peuvent pas être envoyées via WhatsApp"

            log.info(
                f"✅ Added attachment count to message: {attachment_count} total ({sendable_count} sendable)"
            )
        else:
            message += "\n\n📎 Aucune pièce jointe disponible pour cette tâche."
            log.warning(
                f"⚠️ No attachments to display (success={
                    images_result.get('success')}, has_data={
                    bool(
                        images_result.get('data'))})"
            )

        result = {
            "message": message,
            "escalation": False,
            "tools_called": ["get_task_description_tool", "get_task_images_tool"],
            "fast_path": True,
            "tool_outputs": tool_outputs,
            "attachments": attachments,  # Direct attachments for sending
        }

        log.info("📦 Returning result:")
        log.info(f"   message length: {len(result['message'])}")
        log.info(f"   has attachments: {result['attachments'] is not None}")
        if result["attachments"]:
            log.info(f"   attachments count: {len(result['attachments'])}")
        log.info(f"   tool_outputs count: {len(result['tool_outputs'])}")

        return result

    except Exception as e:
        log.error(f"Error in fast path task_details: {e}")
        return None
