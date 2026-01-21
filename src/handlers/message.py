"""Message processing handler."""

import json
import re
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.tools import escalate_to_human_tool, list_projects_tool
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.services.escalation import escalation_service
from src.services.intent_router import intent_router
from src.services.session import session_service
from src.services.translation import translation_service
from src.utils.logger import log


async def handle_direct_action(
    action: str,
    user_id: str,
    phone_number: str,
    language: str,
    message_body: Optional[str] = None,
    media_url: Optional[str] = None,
    media_type: Optional[str] = None,
    session_id: Optional[str] = None,
    recent_messages: Optional[list] = None,
) -> Optional[Dict[str, Any]]:
    """Handle direct action execution without AI agent.

    Args:
        action: The action to execute (e.g., "view_sites", "talk_team", "update_progress")
        user_id: User's ID
        phone_number: User's WhatsApp phone number
        language: User's language code
        message_body: Optional message text content
        media_url: Optional media URL (for images, voice, etc.)
        media_type: Optional media type
        session_id: Optional session ID (prevents redundant session fetches)

    Returns:
        Dict with 'message' and optional 'tool_outputs' if action was handled,
        None if needs AI conversation flow
    """
    log.info(f"🎯 Direct action handler called for action: {action}")

    # === DIRECT ACTIONS (No AI) ===

    if action == "view_sites":
        # Call list_projects_tool directly
        log.info(f"📋 Calling list_projects_tool for user {user_id}")
        response = await list_projects_tool.ainvoke({"user_id": user_id})

        # Get raw projects data for metadata
        from src.integrations.supabase import supabase_client
        from src.utils.metadata_helpers import compact_projects

        projects = await supabase_client.list_projects(user_id)

        return {
            "message": response,
            "list_type": "projects",  # Ensure button IDs are projects_1_fr, not option_1_fr
            "tool_outputs": [
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects(projects),
                }
            ],
        }

    elif action == "view_tasks":
        # Route through intent router (proper layering)
        log.info(f"📋 Routing view_tasks intent for user {user_id}")
        from src.integrations.supabase import supabase_client

        # Get user name using centralized helper
        user_name = supabase_client.get_user_name(user_id)

        result = await intent_router.route_intent(
            intent="view_tasks",
            user_id=user_id,
            phone_number=phone_number,
            user_name=user_name,
            language=language,
        )

        if result:
            # Return full structured response from handler (including list_type)
            return result
        else:
            # Fallback to AI if fast path fails
            return None

    elif action == "view_documents":
        # Route through intent router (proper layering)
        log.info(f"📄 Routing view_documents intent for user {user_id}")
        from src.integrations.supabase import supabase_client

        # Get user name using centralized helper
        user_name = supabase_client.get_user_name(user_id)

        result = await intent_router.route_intent(
            intent="view_documents",
            user_id=user_id,
            phone_number=phone_number,
            user_name=user_name,
            language=language,
        )

        if result:
            # Return full structured response from handler (including list_type, attachments, etc.)
            return result
        else:
            # Fallback to AI if fast path fails
            return None

    elif action == "talk_team":
        # Escalate to human directly
        log.info(f"🗣️ Escalating user {user_id} to human team")
        response = await escalate_to_human_tool.ainvoke(
            {
                "user_id": user_id,
                "phone_number": phone_number,
                "language": language,
                "reason": "L'utilisateur a demandé à parler avec l'équipe",
            }
        )
        return {
            "message": response,
            "tool_outputs": [],  # No tool outputs for escalation
        }

    # === FAST PATH FOR COMPLEX ACTIONS ===

    elif action == "report_incident":
        # Route through intent router (proper layering)
        log.info(f"🚨 Routing report_incident intent for user {user_id}")
        from src.integrations.supabase import supabase_client

        # Get user name using centralized helper
        user_name = supabase_client.get_user_name(user_id)

        result = await intent_router.route_intent(
            intent="report_incident",
            user_id=user_id,
            phone_number=phone_number,
            user_name=user_name,
            language=language,
        )

        if result:
            # Return full structured response from handler (including list_type, attachments, etc.)
            return result
        else:
            # Fallback to AI if fast path fails
            return None

    elif action == "update_progress":
        # 🛡️ BULLETPROOF CHECK: Only route to progress_update agent if we have confirmed context
        # This prevents routing vague requests that should be handled by main LLM
        from src.integrations.supabase import supabase_client
        from src.services.progress_update import progress_update_state

        # Check if there's an active progress update session
        active_session = await progress_update_state.get_session(user_id)
        has_active_session = active_session is not None

        if not has_active_session:
            # No active session - check if user has active task context
            from src.services.project_context import project_context_service

            active_task_id = await project_context_service.get_active_task(user_id)

            if not active_task_id:
                # No confirmed task - don't route to specialized agent
                log.warning(
                    "⚠️ update_progress intent but no active session or task_id - "
                    "falling back to main LLM for clarification"
                )
                log.info(
                    "   Main LLM will use list_projects_tool and list_tasks_tool to help user select"
                )
                return None  # Fall back to main LLM

            log.info(
                f"✅ Active task found: {active_task_id[:8]}... - proceeding to agent"
            )
        else:
            log.info("✅ Active progress update session found - proceeding to agent")

        # Route to specialized Progress Update Agent
        log.info(f"✅ Routing update_progress to specialized agent for user {user_id}")
        from src.services.progress_update.agent import progress_update_agent

        # Get user name
        user_name = supabase_client.get_user_name(user_id)

        # Get recent chat history (last 5 messages)
        chat_history = await supabase_client.get_recent_messages(user_id, limit=5)

        # Enhance message if it's an interactive button selection
        enhanced_message = message_body
        import re

        button_selection = re.match(r"^option_(\d+)_[a-z]{2}$", message_body.strip())
        if button_selection:
            option_num = int(button_selection.group(1))
            log.info(
                f"🔘 Detected interactive button: option {option_num} - enriching context"
            )

            # Look for the last bot message to find what option this was
            if chat_history:
                for msg in reversed(chat_history):
                    if msg.get("direction") == "outbound":
                        content = msg.get("content", "")
                        # Extract numbered list from message
                        option_text_matches = re.findall(
                            r"^\s*" + str(option_num) + r"\.\s*(.+?)$",
                            content,
                            re.MULTILINE,
                        )
                        if option_text_matches:
                            selected_option_text = option_text_matches[0].strip()
                            log.info(
                                f"✅ Resolved option {option_num} → '{selected_option_text}'"
                            )
                            enhanced_message = f"[UTILISATEUR A CLIQUÉ: {selected_option_text}]\n\nL'utilisateur a sélectionné l'option {option_num}: {selected_option_text}"
                            break

        # Route to specialized agent
        result = await progress_update_agent.process(
            user_id=user_id,
            user_name=user_name,
            language=language,
            message=enhanced_message,
            chat_history=chat_history,
            media_url=media_url,
            media_type=media_type,
        )

        if result.get("success"):
            response = {
                "message": result["message"],
                "tool_outputs": result.get("tool_outputs", []),
                "agent_used": result.get("agent_used"),
            }
            # Pass through response_type and list_type if present (for interactive lists)
            if result.get("response_type"):
                response["response_type"] = result["response_type"]
            if result.get("list_type"):
                response["list_type"] = result["list_type"]
            return response
        elif result.get("session_exited"):
            # Agent gracefully exited session - request is out of scope
            log.info(
                f"🔄 Progress update agent exited session - Reason: {result.get('reroute_reason')}"
            )
            log.info(
                "   → Signaling pipeline to reclassify intent without session bias"
            )
            # Return special marker so pipeline knows to reclassify intent
            return {"session_exited": True, "reclassify_intent": True}
        else:
            # Fallback to full AI if specialized agent fails
            return None

    # Handle interactive list selections (task_1_fr, tasks_1_fr, project_2_fr, projects_2_fr, option_3_fr, etc.)
    # Parse action format: {list_type}_{number}_{language}
    # Supports both singular and plural forms (task/tasks, project/projects)
    import re

    list_match = re.match(r"(tasks?|projects?|option)_(\d+)(?:_[a-z]{2})?", action)

    if list_match:
        list_type = list_match.group(1)
        option_number = list_match.group(2)
        log.info(f"📋 Interactive list selection detected: {action}")
        log.info(f"🏷️  Parsed list_type: {list_type}, option #{option_number}")

        # Get the last bot message to find what was in that position
        from src.integrations.supabase import supabase_client
        from src.services.session import session_service

        # Get session (use passed session_id if available to avoid redundant fetch)
        if not session_id:
            session = await session_service.get_or_create_session(user_id)
            session_id = session["id"]
        else:
            log.debug(f"✅ Using passed session_id: {session_id}")
            # Track metrics: session reused (Phase 7 monitoring)
            from src.services.metrics import metrics_service

            metrics_service.track_session_reused(user_id, session_id)

        # Load recent messages
        messages = await supabase_client.get_messages_by_session(
            session_id, fields="content,direction,metadata,created_at"
        )

        # Limit to last 10 messages
        messages = messages[-10:] if messages else []

        # Find bot message with the specific tool_outputs we need
        # Search for the RIGHT tool, not just any tool_outputs
        target_tool = None
        if list_type in ["task", "tasks"]:
            target_tool = "list_tasks_tool"
        elif list_type in ["project", "projects"]:
            target_tool = "list_projects_tool"
        elif list_type == "option":
            # Option could be from list_projects_tool OR get_active_task_context_tool (progress update confirmation)
            # We'll search for both and check which one we find
            target_tool = None  # Will check both

        log.info(
            f"🔍 Searching for tool_outputs in last {len(messages)} messages (target_tool: {target_tool or 'ANY'})"
        )

        tool_outputs = None
        found_tool_name = None
        previous_intent = None  # Track the intent that generated the list

        for idx, msg in enumerate(reversed(messages)):
            log.debug(
                f"   Message {idx}: direction={msg.get('direction')}, has_metadata={msg.get('metadata') is not None}"
            )
            if msg and msg.get("direction") == "outbound":
                metadata = msg.get("metadata", {})
                msg_tool_outputs = metadata.get("tool_outputs", []) if metadata else []
                msg_intent = (
                    metadata.get("intent") if metadata else None
                )  # Get the intent
                log.debug(
                    f"   Message {idx} tool_outputs: {[t.get('tool') if isinstance(t, dict) else 'invalid' for t in msg_tool_outputs]}"
                )
                log.debug(f"   Message {idx} intent: {msg_intent}")

                if msg_tool_outputs:
                    if target_tool:
                        # Check if this message has the specific tool we're looking for
                        has_target_tool = any(
                            t.get("tool") == target_tool
                            for t in msg_tool_outputs
                            if isinstance(t, dict)
                        )
                        if has_target_tool:
                            tool_outputs = msg_tool_outputs
                            found_tool_name = target_tool
                            previous_intent = msg_intent  # Capture the intent
                            log.info(
                                f"📦 Found tool_outputs with {target_tool} in message {idx}"
                            )
                            log.info(
                                f"🔍 All tool_outputs: {[t.get('tool') for t in tool_outputs]}"
                            )
                            log.info(f"🎯 Previous intent: {previous_intent}")
                            # DEBUG: Log the actual data in list_tasks_tool
                            for t in tool_outputs:
                                if t.get("tool") == "list_tasks_tool":
                                    output_data = t.get("output", [])
                                    log.info(
                                        f"🔍 DEBUG: list_tasks_tool output type={type(output_data)}, len={len(output_data) if isinstance(output_data, (list, dict)) else 'N/A'}"
                                    )
                                    if (
                                        isinstance(output_data, list)
                                        and len(output_data) > 0
                                    ):
                                        log.info(
                                            f"🔍 DEBUG: First item: {output_data[0]}"
                                        )
                            break
                    else:
                        # For "option" type, check if it has list_projects_tool OR get_active_task_context_tool
                        tools_in_msg = [
                            t.get("tool")
                            for t in msg_tool_outputs
                            if isinstance(t, dict)
                        ]
                        if "get_active_task_context_tool" in tools_in_msg:
                            tool_outputs = msg_tool_outputs
                            found_tool_name = "get_active_task_context_tool"
                            previous_intent = msg_intent  # Capture the intent
                            log.info(
                                f"📦 Found tool_outputs with get_active_task_context_tool (progress update confirmation) in message {idx}"
                            )
                            log.info(f"🎯 Previous intent: {previous_intent}")
                            break
                        elif "list_projects_tool" in tools_in_msg:
                            tool_outputs = msg_tool_outputs
                            found_tool_name = "list_projects_tool"
                            previous_intent = msg_intent  # Capture the intent
                            log.info(
                                f"📦 Found tool_outputs with list_projects_tool in message {idx}"
                            )
                            log.info(f"🎯 Previous intent: {previous_intent}")
                            break

        if not tool_outputs:
            log.warning(
                f"❌ Could not find {target_tool or 'relevant tool'} in conversation history"
            )

        if tool_outputs:
            # Route based on list_type parsed from action ID (robust approach)
            # This eliminates ambiguity when multiple tool outputs are present

            if list_type in ["task", "tasks"]:
                # Check if this selection is from progress update intent
                if previous_intent == "update_progress":
                    log.info(
                        "📋 Task selection from update_progress intent → Routing to progress update flow"
                    )

                    # Extract task from tool_outputs
                    for tool_output in tool_outputs:
                        if tool_output.get("tool") == "list_tasks_tool":
                            tasks_output = tool_output.get("output", [])

                            # DEBUG: Log what we got
                            log.info(
                                f"🔍 DEBUG: tasks_output type={type(tasks_output)}, length={len(tasks_output) if isinstance(tasks_output, (list, str)) else 'N/A'}"
                            )
                            if isinstance(tasks_output, list) and len(tasks_output) > 0:
                                log.info(
                                    f"🔍 DEBUG: First task sample: {tasks_output[0]}"
                                )
                            elif isinstance(tasks_output, str):
                                log.info(
                                    f"🔍 DEBUG: tasks_output is string: {tasks_output[:100]}"
                                )

                            # Handle both formats
                            if isinstance(tasks_output, str):
                                # Re-fetch
                                from src.actions import tasks as task_actions
                                from src.services.project_context import (
                                    project_context_service,
                                )

                                project_id = (
                                    await project_context_service.get_active_project(
                                        user_id
                                    )
                                )
                                if not project_id:
                                    log.error("❌ No active project to re-fetch tasks")
                                    return None

                                task_result = await task_actions.list_tasks(
                                    user_id, project_id
                                )
                                if task_result.get("success") and task_result.get(
                                    "data"
                                ):
                                    from src.utils.metadata_helpers import compact_tasks

                                    tasks = compact_tasks(task_result["data"])
                                else:
                                    log.error("❌ Failed to re-fetch tasks")
                                    return None
                            else:
                                tasks = tasks_output

                            # Get the selected task
                            index = int(option_number) - 1
                            if 0 <= index < len(tasks):
                                selected_task = tasks[index]
                                task_id = selected_task.get("id")
                                task_title = selected_task.get("title")

                                log.info(
                                    f"✅ Selected task for progress update: {task_title} (ID: {task_id[:8]}...)"
                                )

                                # Set active task in database so progress update agent can find it
                                from src.services.project_context import (
                                    project_context_service,
                                )

                                await project_context_service.set_active_task(
                                    user_id, task_id, task_title
                                )
                                log.info(
                                    f"✅ Set active task in database: {task_title} (ID: {task_id[:8]}...)"
                                )

                                # Route to progress update with selected task
                                return await handle_direct_action(
                                    action="update_progress",
                                    user_id=user_id,
                                    phone_number=phone_number,
                                    language=language,
                                    message_body=task_title,
                                    session_id=session_id,
                                )
                            else:
                                log.warning(f"⚠️ Task index {index} out of range")
                                return None
                            break

                # Check if task list came from progress update agent's get_active_task_context_tool
                for tool_output in tool_outputs:
                    if tool_output.get("tool") == "get_active_task_context_tool":
                        output_data = tool_output.get("output", {})
                        tasks = output_data.get("tasks", [])

                        if tasks:
                            log.info(
                                f"📋 Found task list from get_active_task_context_tool: {len(tasks)} tasks"
                            )

                            # Get the task at the selected index (1-based)
                            index = int(option_number) - 1
                            if 0 <= index < len(tasks):
                                selected_task = tasks[index]
                                task_id = selected_task.get("id")
                                task_title = selected_task.get("title")

                                log.info(
                                    f"✅ Selected task from progress update agent list: {task_title} (ID: {task_id[:8] if task_id else 'N/A'}...)"
                                )

                                # CRITICAL: Update active task in database
                                from src.services.project_context import (
                                    project_context_service,
                                )

                                await project_context_service.set_active_task(
                                    user_id, task_id, task_title
                                )
                                log.info(
                                    f"✅ Active task updated to: {task_title} (ID: {task_id[:8]}...)"
                                )

                                # Route to progress update with selected task
                                return await handle_direct_action(
                                    action="update_progress",
                                    user_id=user_id,
                                    phone_number=phone_number,
                                    language=language,
                                    message_body=task_title,
                                    session_id=session_id,
                                )
                            else:
                                log.warning(f"⚠️ Task index {index} out of range")
                                return None
                            break

                # Default: User selected a task from the list → Show task details
                for tool_output in tool_outputs:
                    if tool_output.get("tool") == "list_tasks_tool":
                        tasks_output = tool_output.get("output", [])

                        # DEFENSIVE: Handle both old (string) and new (structured list) formats
                        if isinstance(tasks_output, str):
                            # Old format: formatted string - cannot use for selection
                            # Need to re-fetch tasks from database
                            log.warning(
                                f"⚠️ Found old string format in tool_outputs (length: {len(tasks_output)})"
                            )
                            log.warning(
                                "   Re-fetching structured task data from database..."
                            )

                            from src.actions import tasks as task_actions
                            from src.services.project_context import (
                                project_context_service,
                            )

                            # Get active project
                            project_id = (
                                await project_context_service.get_active_project(
                                    user_id
                                )
                            )
                            if not project_id:
                                log.error("   ❌ No active project to re-fetch tasks")
                                return None

                            # Re-fetch tasks
                            task_result = await task_actions.list_tasks(
                                user_id, project_id
                            )
                            if task_result.get("success") and task_result.get("data"):
                                from src.utils.metadata_helpers import compact_tasks

                                tasks = compact_tasks(task_result["data"])
                                log.info(
                                    f"   ✅ Re-fetched {len(tasks)} tasks from database"
                                )
                            else:
                                log.error("   ❌ Failed to re-fetch tasks")
                                return None
                        elif isinstance(tasks_output, list):
                            # New format: structured list of dicts
                            tasks = tasks_output
                            log.info(
                                f"📋 Found {len(tasks)} tasks in tool_outputs (structured format)"
                            )
                        else:
                            log.error(
                                f"❌ Unexpected tool_output format: {type(tasks_output)}"
                            )
                            return None

                        # Get the task at the selected index (1-based)
                        index = int(option_number) - 1
                        if 0 <= index < len(tasks):
                            selected_task = tasks[index]

                            # Ensure selected_task is a dict
                            if not isinstance(selected_task, dict):
                                log.error(
                                    f"❌ selected_task is not a dict: {type(selected_task)}"
                                )
                                return None

                            task_id = selected_task.get("id")
                            task_title = selected_task.get("title")
                            log.info(
                                f"✅ Resolved {list_type}_{option_number} → {task_title} (ID: {task_id[:8] if task_id else 'NONE'}...)"
                            )

                            # Trigger task_details with the selected task
                            from src.integrations.supabase import supabase_client
                            from src.services.handlers import execute_direct_handler

                            user_name = supabase_client.get_user_name(user_id)

                            # Pass updated tool_outputs with structured tasks data (not old string format)
                            updated_tool_outputs = [
                                {
                                    "tool": "list_tasks_tool",
                                    "input": {},
                                    "output": tasks,  # Use the structured tasks we just retrieved
                                }
                            ]

                            result = await execute_direct_handler(
                                intent="task_details",
                                user_id=user_id,
                                phone_number=phone_number,
                                user_name=user_name,
                                language=language,
                                message_text=str(option_number),
                                session_id=session_id,
                                last_tool_outputs=updated_tool_outputs,
                            )

                            if result:
                                log.info("✅ Task details called for selected task")
                                return result
                            else:
                                log.warning("⚠️ Task details handler returned None")
                                return None
                        else:
                            log.warning(
                                f"⚠️ Option {option_number} out of range (0-{len(tasks) - 1})"
                            )
                        break

            elif (
                list_type == "option"
                and found_tool_name == "get_active_task_context_tool"
            ):
                # For "option" type from progress update confirmation
                log.info(
                    "📋 Option selection detected from progress update confirmation"
                )

                # Extract confirmation data from tool_outputs
                confirmation_data = None
                for tool_output in tool_outputs:
                    if tool_output.get("tool") == "get_active_task_context_tool":
                        output = tool_output.get("output", {})
                        if "confirmation" in output:
                            confirmation_data = output["confirmation"]
                            log.info(f"   Found confirmation data: {confirmation_data}")
                            break

                if not confirmation_data:
                    log.error("❌ No confirmation data found in tool_outputs")
                    return None

                # User selected an option from confirmation (1=Yes, 2=No)
                if option_number == "1":
                    # User confirmed - start progress update session directly
                    log.info(
                        "✅ User confirmed task - starting progress update session"
                    )
                    log.info(f"   Task ID: {confirmation_data.get('task_id')}")
                    log.info(f"   Project ID: {confirmation_data.get('project_id')}")

                    from src.integrations.supabase import supabase_client
                    from src.services.progress_update.tools import (
                        start_progress_update_session_tool,
                    )

                    # Get project_id - if not in confirmation data, get from user context
                    project_id = confirmation_data.get("project_id")
                    if not project_id:
                        log.warning(
                            "⚠️ No project_id in confirmation data, fetching from user context"
                        )
                        # Get user's active project
                        user = supabase_client.get_user(user_id)
                        if user and user.get("active_project_id"):
                            active_project_id = user["active_project_id"]
                            project = await supabase_client.get_project(
                                active_project_id, user_id=user_id
                            )
                            if project:
                                project_id = project.get("planradar_project_id")
                                log.info(
                                    f"   ✅ Retrieved project_id from context: {project_id}"
                                )

                    if not project_id:
                        log.error("❌ Cannot start session: no project_id available")
                        return {
                            "message": "❌ Erreur : impossible de démarrer la session de mise à jour. Veuillez réessayer.",
                            "tool_outputs": [],
                            "agent_used": "progress_update",
                        }

                    # Start session directly
                    result_text = await start_progress_update_session_tool.ainvoke(
                        {
                            "user_id": user_id,
                            "task_id": confirmation_data.get("task_id"),
                            "project_id": project_id,
                        }
                    )

                    return {
                        "message": result_text,
                        "tool_outputs": [],
                        "agent_used": "progress_update",
                    }
                else:
                    # User said no - extract the actual option text they selected
                    log.info("❌ User declined - extracting actual option text")

                    # Extract option text from the last bot message
                    selected_option_text = None
                    for msg in reversed(messages):
                        if msg and msg.get("direction") == "outbound":
                            last_bot_content = msg.get("content", "")
                            # Parse numbered options (format: "1. Option text" or "2. Option text")
                            import re

                            options_match = re.findall(
                                r"^\s*(\d+)\.\s*(.+)$", last_bot_content, re.MULTILINE
                            )
                            if options_match:
                                # Find the option matching our number
                                for opt_num, opt_text in options_match:
                                    if opt_num == option_number:
                                        selected_option_text = opt_text.strip()
                                        log.info(
                                            f"✅ Extracted option {option_number} text: '{selected_option_text}'"
                                        )
                                        break
                            if selected_option_text:
                                break

                    # Fallback to default if extraction failed
                    if not selected_option_text:
                        selected_option_text = "Autre tâche"
                        log.warning(
                            f"⚠️ Could not extract option text, using fallback: '{selected_option_text}'"
                        )

                    # 🛡️ BULLETPROOF CHECK: Determine if user wants another project or another task
                    # and call the appropriate tool directly
                    selected_lower = selected_option_text.lower()

                    if "projet" in selected_lower:
                        # User wants to see other projects
                        log.info(
                            "📋 User selected 'Autre projet' - calling list_projects_tool"
                        )
                        from src.actions import projects as projects_actions

                        result = await projects_actions.list_projects(user_id)

                        if result["success"] and result["data"]:
                            # Format projects as numbered list
                            message = f"{result['message']}\n\n"
                            for i, project in enumerate(result["data"], 1):
                                message += f"{i}. 🏗️ {project['nom']}\n"

                            return {
                                "message": message,
                                "tool_outputs": [
                                    {
                                        "tool": "list_projects_tool",
                                        "output": result["data"],
                                    }
                                ],
                                "response_type": "interactive_list",
                                "list_type": "projects",
                            }
                        else:
                            return {"message": result["message"], "tool_outputs": []}

                    elif "tâche" in selected_lower or "tache" in selected_lower:
                        # User wants to see other tasks
                        log.info(
                            "📋 User selected 'Autre tâche' - calling list_tasks_tool"
                        )
                        from src.actions import tasks as tasks_actions
                        from src.services.project_context import project_context_service

                        # Get active project
                        project_id = await project_context_service.get_active_project(
                            user_id
                        )

                        if not project_id:
                            return {
                                "message": "⚠️ Aucun projet actif. Veuillez d'abord sélectionner un projet.",
                                "tool_outputs": [],
                            }

                        result = await tasks_actions.list_tasks(user_id, project_id)

                        if result["success"] and result["data"]:
                            # Format tasks as numbered list
                            message = f"{result['message']}\n\n"
                            for i, task in enumerate(result["data"], 1):
                                emoji = "📝"
                                if task.get("status") == "in_progress":
                                    emoji = "🔨"
                                elif task.get("status") == "completed":
                                    emoji = "✅"
                                message += f"{i}. {emoji} {task['title']}\n"

                            return {
                                "message": message,
                                "tool_outputs": [
                                    {
                                        "tool": "list_tasks_tool",
                                        "output": result["data"],
                                    }
                                ],
                                "response_type": "interactive_list",
                                "list_type": "tasks",
                                "agent_used": "fast_path",
                            }
                        else:
                            return {"message": result["message"], "tool_outputs": []}
                    else:
                        # User selected something other than project/task (e.g., "Add comment")
                        # Set up active task context and defer to progress update agent
                        log.info(
                            f"📝 Option '{selected_option_text}' selected - setting up active task context"
                        )

                        from src.services.project_context import project_context_service

                        # Set active task context with confirmation data
                        task_id = confirmation_data.get("task_id")
                        task_title = confirmation_data.get("task_title")

                        if task_id:
                            await project_context_service.set_active_task(
                                user_id, task_id, task_title
                            )
                            log.info(
                                f"✅ Active task context set: {task_title} (ID: {task_id[:8] if task_id else 'N/A'}...)"
                            )

                        # Return None to defer to progress update agent with active context
                        return None

            elif list_type == "option":
                # Check for pending_action (issue choice, etc.)
                # Fetch recent messages if not provided
                if recent_messages is None:
                    recent_messages = await supabase_client.get_recent_messages(
                        user_id=user_id, limit=5
                    )

                pending_action = None
                for msg in recent_messages[
                    ::-1
                ]:  # Search backwards (most recent first)
                    try:
                        msg_metadata = json.loads(msg.get("metadata", "{}"))
                        if "pending_action" in msg_metadata:
                            pending_action = msg_metadata["pending_action"]
                            log.info(
                                f"📋 Found pending_action: {pending_action.get('type')}"
                            )
                            break
                    except Exception as e:
                        log.warning(f"⚠️ Could not parse message metadata: {e}")

                if pending_action and pending_action.get("type") == "issue_choice":
                    severity = pending_action.get("severity")
                    description = pending_action.get("description")
                    original_message = pending_action.get("original_message")
                    from_session = pending_action.get("from_session")

                    log.info(
                        f"💡 Processing issue choice selection\n"
                        f"   User selected: option_{option_number}\n"
                        f"   Issue severity: {severity}\n"
                        f"   Issue description: {description}\n"
                        f"   From session: {from_session}"
                    )

                    from src.integrations.supabase import supabase_client
                    from src.services.progress_update import progress_update_state

                    if option_number == "1":
                        # Option 1: Create incident report
                        log.info(
                            f"📋 User chose option 1: Create incident report\n"
                            f"   Clearing {from_session} session and routing to incident report"
                        )

                        # Clear the active progress_update session
                        await progress_update_state.clear_session(
                            user_id, reason="issue_escalation_to_incident"
                        )

                        # Route to incident report handler
                        return await handle_direct_action(
                            action="report_incident",
                            user_id=user_id,
                            phone_number=phone_number,
                            language=language,
                            message_body=original_message,
                            session_id=session_id,
                        )

                    elif option_number == "2":
                        # Option 2: Add comment to current task
                        log.info(
                            f"💬 User chose option 2: Add comment to task\n"
                            f"   Staying in {from_session} session"
                        )

                        from src.services.progress_update.tools import (
                            add_progress_comment_tool,
                        )

                        # Get active session to get task_id
                        session = await progress_update_state.get_session(user_id)
                        if not session:
                            log.error("❌ No active session found for adding comment")
                            return {
                                "message": "❌ Erreur : session expirée. Veuillez réessayer.",
                                "tool_outputs": [],
                            }

                        task_id = session.get("task_id")
                        project_id = session.get("project_id")
                        log.info(
                            f"   Task ID: {task_id[:8] if task_id else 'N/A'}...\n"
                            f"   Project ID: {project_id[:8] if project_id else 'N/A'}..."
                        )

                        # Add comment with issue indicator
                        comment_text = f"⚠️ Problème signalé: {original_message}"
                        log.info(f"   Adding comment: {comment_text[:50]}...")

                        try:
                            result = await add_progress_comment_tool.ainvoke(
                                {
                                    "user_id": user_id,
                                    "task_id": task_id,
                                    "project_id": project_id,
                                    "comment": comment_text,
                                }
                            )
                            log.info("✅ Comment added successfully to task")

                            # Continue session - show options
                            if language == "en":
                                message = "✅ Comment added. What would you like to do?\n\n1. Add photo\n2. Mark complete\n3. Add another comment"
                            else:
                                message = "✅ Commentaire ajouté. Que souhaitez-vous faire?\n\n1. Ajouter photo\n2. Marquer terminé\n3. Ajouter commentaire"

                            return {
                                "message": message,
                                "tool_outputs": [],
                                "agent_used": "progress_update",
                                "response_type": "interactive_list",
                                "list_type": "option",
                            }

                        except Exception as e:
                            log.error(f"❌ Error adding comment: {e}")
                            return {
                                "message": f"❌ Erreur lors de l'ajout du commentaire : {str(e)}",
                                "tool_outputs": [],
                            }

                    elif option_number == "3":
                        # Option 3: Skip - continue without noting
                        log.info(
                            f"⏭️ User chose option 3: Skip issue documentation\n"
                            f"   Continuing {from_session} session without noting issue"
                        )

                        # Continue session - show options
                        if language == "en":
                            message = "Okay. What would you like to do?\n\n1. Photo\n2. Comment\n3. Complete"
                        else:
                            message = "D'accord. Que souhaitez-vous faire?\n\n1. Photo\n2. Commentaire\n3. Terminé"

                        log.info("✅ Presenting next options to user")
                        return {
                            "message": message,
                            "tool_outputs": [],
                            "agent_used": "progress_update",
                            "response_type": "interactive_list",
                            "list_type": "option",
                        }

                    else:
                        log.warning(
                            f"⚠️ Invalid option number for issue choice: {option_number}\n"
                            f"   Expected: 1, 2, or 3"
                        )
                        return None

            elif list_type in ["project", "projects", "option"]:
                # User selected a project from the list → Show project tasks
                for tool_output in tool_outputs:
                    if tool_output.get("tool") == "list_projects_tool":
                        projects = tool_output.get("output", [])
                        log.info(f"📋 Found {len(projects)} projects in tool_outputs")

                        # Get the project at the selected index (1-based)
                        index = int(option_number) - 1
                        if 0 <= index < len(projects):
                            selected_project = projects[index]
                            project_id = selected_project.get("id")
                            project_name = selected_project.get("nom")
                            log.info(
                                f"✅ Resolved {list_type}_{option_number} → {project_name} (ID: {project_id[:8]}...)"
                            )

                            # Trigger list_tasks with the selected project
                            from src.integrations.supabase import supabase_client
                            from src.services.handlers import execute_direct_handler

                            user_name = supabase_client.get_user_name(user_id)

                            result = await execute_direct_handler(
                                intent="list_tasks",
                                user_id=user_id,
                                phone_number=phone_number,
                                user_name=user_name,
                                language=language,
                                message_text=project_name,
                                session_id=session_id,
                                last_tool_outputs=tool_outputs,
                            )

                            if result:
                                log.info("✅ List tasks called for selected project")
                                return result
                            else:
                                log.warning("⚠️ List tasks handler returned None")
                                return None
                        else:
                            log.warning(
                                f"⚠️ Option {option_number} out of range (0-{len(projects) - 1})"
                            )
                        break

        log.warning(f"⚠️ Could not resolve list selection {action}")
        return None

    # Unknown action
    log.warning(f"⚠️ Unknown action: {action}")
    return None


def convert_messages_to_langchain(messages: list) -> list:
    """Convert database messages to LangChain message format.

    Args:
        messages: List of message dicts from database

    Returns:
        List of LangChain messages (HumanMessage, AIMessage)
    """
    langchain_messages: list[Any] = []
    for msg in messages:
        content = msg.get("content", "")
        direction = msg.get("direction", "")

        if direction == "inbound":
            langchain_messages.append(HumanMessage(content=content))
        elif direction == "outbound":
            langchain_messages.append(AIMessage(content=content))  # type: ignore[arg-type]

    return langchain_messages


async def process_inbound_message(
    from_number: str,
    message_body: str,
    message_sid: str,
    media_url: Optional[str] = None,
    media_content_type: Optional[str] = None,
    button_payload: Optional[str] = None,
    button_text: Optional[str] = None,
) -> None:
    """Process an inbound WhatsApp message using pipeline architecture.

    Args:
        from_number: The sender's WhatsApp number (format: whatsapp:+33123456789)
        message_body: The message text
        message_sid: Twilio message SID
        media_url: Optional media URL if message includes media
        media_content_type: Content type of media
        button_payload: Optional interactive list selection ID (e.g., "view_sites")
        button_text: Optional interactive list selection display text
    """
    try:
        # === PHASE 1: PRE-PROCESSING ===
        # Normalize phone number - remove 'whatsapp:' prefix if present
        phone_number = from_number.replace("whatsapp:", "").strip()
        log.info(f"📥 Processing message from {phone_number}")

        # FSM: Check for duplicate message (idempotency)
        from src.config import settings

        if settings.enable_fsm:
            from src.fsm.core import StateManager

            state_manager = StateManager()

            # Check if we've already processed this message
            cached_response = await state_manager.check_idempotency(
                user_id=phone_number, message_id=message_sid
            )

            if cached_response:
                log.info(
                    f"🔁 Duplicate message {message_sid} - returning cached response"
                )
                # Message already processed, skip reprocessing
                # (Response already sent in previous processing)
                return

        # Quick user lookup for escalation blocking and direct actions
        user = await supabase_client.get_user_by_phone(phone_number)

        if not user:
            # Unknown user - detect language and send error message
            log.warning(
                f"Unknown phone number: {phone_number}. Subcontractor not registered."
            )
            detected_language = await translation_service.detect_language(message_body)

            error_messages = {
                "en": "Sorry, I don't know you. Only registered subcontractors can use this service. Please contact your administrator to get registered.",
                "fr": "Désolé, je ne vous connais pas. Seuls les sous-traitants enregistrés peuvent utiliser ce service. Veuillez contacter votre administrateur pour être enregistré.",
                "es": "Lo siento, no te conozco. Solo los subcontratistas registrados pueden usar este servicio. Por favor contacta a tu administrador para registrarte.",
                "pt": "Desculpe, não te conheço. Apenas subempreiteiros registados podem usar este serviço. Por favor contacta o teu administrador para te registares.",
                "de": "Entschuldigung, ich kenne Sie nicht. Nur registrierte Subunternehmer können diesen Service nutzen. Bitte kontaktieren Sie Ihren Administrator zur Registrierung.",
                "it": "Mi dispiace, non ti conosco. Solo i subappaltatori registrati possono utilizzare questo servizio. Contatta il tuo amministratore per registrarti.",
                "ro": "Îmi pare rău, nu te cunosc. Doar subantreprenorii înregistrați pot folosi acest serviciu. Te rog contactează administratorul pentru a te înregistra.",
                "pl": "Przepraszam, nie znam Cię. Tylko zarejestrowani podwykonawcy mogą korzystać z tej usługi. Skontaktuj się z administratorem, aby się zarejestrować.",
                "ar": "عذراً، لا أعرفك. يمكن فقط للمقاولين المسجلين استخدام هذه الخدمة. يرجى الاتصال بالمسؤول للتسجيل.",
            }

            error_message = error_messages.get(detected_language, error_messages["en"])
            twilio_client.send_message(from_number, error_message)
            log.info(f"Sent 'unknown user' message in {detected_language}")
            return

        user_id = user["id"]
        user_language = user.get("language", "fr")
        user_name = user.get("contact_prenom", "")

        # Check escalation blocking
        is_blocked = await escalation_service.should_block_user(user_id)
        if is_blocked:
            response_text = await translation_service.translate_from_french(
                "Votre conversation est actuellement gérée par un administrateur. Vous serez contacté sous peu.",
                user_language,
            )
            twilio_client.send_message(from_number, response_text)
            log.info(f"User {user_id} is blocked due to active escalation")
            return

        # Get or create session early (for direct actions)
        session = await session_service.get_or_create_session(user_id)
        session_id = session["id"] if session else None

        # Check if message is a plain number and convert to action format if needed
        plain_number_match = re.match(r"^\s*(\d+)\s*$", message_body.strip())
        if plain_number_match:
            number = plain_number_match.group(1)
            log.info(f"🔢 Plain number detected: {number}")

            # Check last bot message to determine list type
            messages = await supabase_client.get_messages_by_session(
                session_id, fields="direction,metadata,created_at"
            )
            messages = messages[-5:] if messages else []

            # Look for most recent list
            for msg in reversed(messages):
                if msg and msg.get("direction") == "outbound":
                    metadata = msg.get("metadata", {})
                    response_type = metadata.get("response_type") if metadata else None
                    list_type = metadata.get("list_type") if metadata else None

                    if response_type == "interactive_list" and list_type:
                        log.info(
                            f"✅ Found recent list (type={list_type}) - converting to action format"
                        )
                        # Convert to action format: tasks_2_fr or option_2_fr
                        message_body = f"{list_type}_{number}_{user_language}"
                        log.info(f"🔄 Converted plain number to action: {message_body}")
                        break

        # Handle interactive button actions (direct actions bypass pipeline)
        action_pattern = r"^(.+)_([a-z]{2})$"
        action_match = re.match(action_pattern, message_body.strip())

        if action_match:
            action_id = action_match.group(1)
            log.info(f"🔘 Interactive action detected: {action_id}")
            log.info(f"🌍 User language from profile: {user_language}")

            direct_response = await handle_direct_action(
                action=action_id,
                user_id=user_id,
                phone_number=phone_number,
                language=user_language,
                session_id=session_id,
            )

            log.info(
                f"📋 Direct response received: type={type(direct_response)}, is_dict={isinstance(direct_response, dict)}"
            )

            if direct_response:
                # Handle both string and dict responses (backward compatible)
                if isinstance(direct_response, dict):
                    response_message = direct_response.get("message", "")
                    tool_outputs = direct_response.get("tool_outputs", [])
                    attachments = direct_response.get("attachments")
                    log.info(f"📦 Dict response keys: {list(direct_response.keys())}")
                    if attachments:
                        log.info(f"   has attachments: {len(attachments)} files")
                else:
                    response_message = direct_response
                    tool_outputs = []
                    attachments = None
                    log.info("📝 String response (no attachments)")

                log.info(f"✅ Direct action '{action_id}' executed successfully")
                log.info(f"🔤 Handler response (French): {response_message[:100]}...")

                # Translate response if needed
                if user_language != "fr":
                    log.info(f"🔄 Translating from French to {user_language}")
                    response_text = await translation_service.translate_from_french(
                        response_message, user_language
                    )
                    log.info(f"✅ Translated response: {response_text[:100]}...")
                else:
                    response_text = response_message
                    log.info("ℹ️ No translation needed (user language is French)")

                # Check if escalation action
                is_escalation_action = action_id == "talk_team"

                # Build metadata
                metadata = {}
                if tool_outputs:
                    metadata["tool_outputs"] = tool_outputs
                    log.info(f"💾 Storing {len(tool_outputs)} tool outputs in metadata")

                # Save messages to database
                await supabase_client.save_message(
                    user_id=user_id,
                    message_text=message_body,
                    original_language=user_language,
                    direction="inbound",
                    message_sid=message_sid,
                    session_id=session_id,
                )

                await supabase_client.save_message(
                    user_id=user_id,
                    message_text=response_text,
                    original_language=user_language,
                    direction="outbound",
                    session_id=session_id,
                    is_escalation=is_escalation_action,
                    escalation_reason=(
                        "User requested to talk to team via direct action"
                        if is_escalation_action
                        else None
                    ),
                    metadata=metadata if metadata else None,
                )

                # Send response with interactive formatting
                log.info(
                    "📱 Formatting direct action response for potential interactive list"
                )

                # Import formatting utilities
                from src.utils.response_parser import format_for_interactive
                from src.utils.whatsapp_formatter import send_whatsapp_message_smart

                # Extract list_type from response metadata (defaults to "option" if not provided)
                # Use direct_response if it's a dict, otherwise default to "option"
                list_type = (
                    direct_response.get("list_type", "option")
                    if isinstance(direct_response, dict)
                    else "option"
                )
                log.info(f"🏷️  List type for interactive formatting: {list_type}")

                # Format for interactive if applicable (e.g., list_projects, list_tasks)
                formatted_text, interactive_data = format_for_interactive(
                    response_text, user_language, list_type
                )

                send_whatsapp_message_smart(
                    to=from_number,
                    text=formatted_text,
                    interactive_data=interactive_data,
                    user_name=user_name,
                    language=user_language,
                    is_greeting=False,  # Direct actions are not greetings
                )

                log.info(
                    f"📤 Direct action response sent (interactive: {interactive_data is not None})"
                )

                # Send attachments directly
                if attachments:
                    log.info(f"📎 Sending {len(attachments)} attachments")

                    try:
                        from src.config import settings
                        from src.integrations.twilio import twilio_client

                        # Send each attachment as a separate message
                        for idx, att in enumerate(attachments, 1):
                            url = att.get("url")
                            content_type = att.get(
                                "content_type", "application/octet-stream"
                            )
                            filename = att.get("filename", f"attachment_{idx}")

                            log.info(
                                f"📤 Sending attachment {idx}/{len(attachments)}: {content_type} - {filename}"
                            )

                            try:
                                # Download the file locally first (fixes Twilio error 63019)
                                # PlanRadar S3 URLs are signed and expire, so Twilio can't download them directly
                                log.info(
                                    "📥 Downloading attachment from external URL to avoid Twilio 63019 error"
                                )
                                local_file_path = (
                                    twilio_client.download_and_upload_media(
                                        media_url=url,
                                        content_type=content_type,
                                        filename=filename,
                                    )
                                )

                                if not local_file_path:
                                    log.error(
                                        f"❌ Failed to download attachment {idx}/{len(attachments)}"
                                    )
                                    continue

                                # Send via temporary hosting
                                log.info("📤 Sending attachment via temporary hosting")
                                twilio_client.send_message_with_local_media(
                                    to=from_number,
                                    body=filename,  # Use filename as caption
                                    local_file_path=local_file_path,
                                    server_url=settings.server_url,
                                )
                                log.info(
                                    f"✅ Attachment {idx}/{len(attachments)} sent successfully"
                                )

                            except Exception as att_error:
                                log.error(
                                    f"❌ Failed to send attachment {idx}/{len(attachments)}: {att_error}"
                                )

                    except Exception as attachment_error:
                        log.error(
                            f"❌ Error sending attachments: {attachment_error}",
                            exc_info=True,
                        )
                else:
                    log.info("ℹ️ No attachments to send")

                return
            else:
                # Direct action handler returned None - fallback to AI pipeline
                log.warning(
                    f"⚠️ Direct action '{action_id}' returned None - falling back to AI pipeline"
                )
                log.info(
                    "   Handler could not resolve parameters, letting AI agent handle it"
                )
                # Don't return - continue to pipeline processing below

        # === PHASE 2: CORE PROCESSING - USE PIPELINE ===
        from src.handlers.message_pipeline import message_pipeline

        # Convert button data to interactive_data format
        interactive_data = None
        if button_payload or button_text:
            interactive_data = {"payload": button_payload, "text": button_text}

        log.info("🔄 Processing message through pipeline")
        result = await message_pipeline.process(
            from_number=phone_number,
            message_body=message_body,
            message_sid=message_sid,
            media_url=media_url,
            media_type=media_content_type,
            interactive_data=interactive_data,
            session_id=session_id,  # NEW: Pass session_id to prevent duplicate creation
        )

        if not result.success:
            # Pipeline error - send user-friendly message
            log.error(f"Pipeline failed: {result.error_message}")
            error_msg = (
                result.user_message
                or "Désolé, une erreur s'est produite. Veuillez réessayer."
            )

            if user_language != "fr":
                error_msg = await translation_service.translate_from_french(
                    error_msg, user_language
                )

            twilio_client.send_message(from_number, error_msg)
            return

        # === PHASE 3: POST-PROCESSING ===
        response_data = result.data
        response_text = response_data["message"]
        escalation = response_data["escalation"]
        session_id = response_data["session_id"]
        intent = response_data.get("intent")
        confidence = response_data.get("confidence", 0.0)
        detected_language = response_data.get("detected_language", user_language)

        # Use detected language (from pipeline) instead of profile language
        if detected_language != user_language:
            log.info(
                f"🌍 Using detected language: {detected_language} (profile: {user_language})"
            )
        user_language = detected_language

        # Intent-driven response formatting
        # Only format as interactive lists for specific intents where we expect structured data
        INTERACTIVE_LIST_INTENTS = {
            "greeting",
            "list_projects",
            "list_tasks",
            "update_progress",
        }

        # These intents have structured, limited-size outputs suitable for WhatsApp interactive lists (max 10 items):
        # - greeting: Fixed menu (6 items)
        # - list_projects: Typically 1-5 projects per subcontractor
        # - list_tasks: Usually 5-10 tasks per project
        #
        # All other intents use plain text:
        # - list_documents: Can be 20+ documents (exceeds WhatsApp limit, needs scrollable text)
        # - escalate: Simple confirmation message
        # - report_incident: Conversational guidance flow
        # - update_progress: Conversational feedback
        # - general: AI conversational response (may include suggestions, but not structured data)

        # Import formatting utilities
        from src.utils.response_parser import format_for_interactive
        from src.utils.whatsapp_formatter import send_whatsapp_message_smart

        # Check if specialized agent provided response_type metadata
        response_type = response_data.get("response_type", None)
        log.info(f"🎯 Handler received response_type: {response_type}")
        log.info(f"   list_type: {response_data.get('list_type')}")
        log.info(f"   intent: {intent}")

        # Decision logic based on response_type (from specialized agents) or intent
        if response_type == "interactive_list":
            # Agent explicitly indicated this should be interactive
            log.info(
                "📱 Agent response_type=interactive_list → Formatting as interactive"
            )
            list_type = response_data.get("list_type", "option")
            log.info(f"🏷️  List type: {list_type}")
            message_text, interactive_data = format_for_interactive(
                response_text, user_language, list_type
            )

        elif response_type == "escalation":
            # Agent escalated to human
            log.info(
                "🔧 Agent response_type=escalation → Plain text with escalation flag"
            )
            message_text = response_text
            interactive_data = None

        elif response_type == "no_tasks_available":
            # No tasks available - agent provided options but they're informational
            log.info(
                "⚠️ Agent response_type=no_tasks_available → Plain text (no interactive)"
            )
            message_text = response_text
            interactive_data = None

        elif response_type == "session_started":
            # Session started - could format action menu as interactive
            log.info(
                "✅ Agent response_type=session_started → Plain text (action menu)"
            )
            message_text = response_text
            interactive_data = None

        elif intent in INTERACTIVE_LIST_INTENTS:
            # Fallback: Intent-based detection (for non-specialized agents)
            log.info(
                f"📱 Intent '{intent}' in INTERACTIVE_LIST_INTENTS → Formatting as interactive list"
            )

            # Use list_type from handler if provided, otherwise infer from intent
            list_type = response_data.get("list_type")
            if list_type:
                log.info(f"🏷️  Using list_type from handler: {list_type}")
            else:
                # Infer list_type from intent
                # IMPORTANT: Only infer "tasks" or "projects" for explicit list intents
                # For update_progress and other intents, default to "option" since they
                # typically show action options, not task/project lists
                if intent in ["list_tasks", "view_tasks"]:
                    list_type = "tasks"
                elif intent in ["list_projects", "switch_project"]:
                    list_type = "projects"
                else:
                    # Default to "option" for all other intents (including update_progress)
                    # Options like "Add photo", "Mark complete", etc. should use option type
                    list_type = "option"

                log.info(f"🏷️  Inferred list_type from intent '{intent}': {list_type}")

            message_text, interactive_data = format_for_interactive(
                response_text, user_language, list_type
            )

        else:
            # Default: Plain text
            log.info(f"📱 Intent '{intent}' is conversational → Sending as plain text")
            message_text = response_text
            interactive_data = None

        # Detect greeting for special handling (dynamic template with menu)
        is_greeting_intent = intent == "greeting"
        if is_greeting_intent:
            log.info(
                f"✅ Greeting intent (confidence: {confidence:.2%}) → Will use dynamic template with menu"
            )

        # Send response via Twilio
        send_whatsapp_message_smart(
            to=from_number,
            text=message_text,
            interactive_data=interactive_data,
            user_name=user_name,
            language=user_language,
            is_greeting=is_greeting_intent,
        )

        log.info(
            f"📤 Response sent to {from_number} (interactive: {interactive_data is not None})"
        )

        # Check for attachments and send them directly
        attachments = response_data.get("attachments")
        if attachments:
            log.info(f"📎 Sending {len(attachments)} attachments")

            try:
                from src.integrations.twilio import twilio_client

                # Send each attachment as a separate message
                for idx, att in enumerate(attachments, 1):
                    url = att.get("url")
                    content_type = att.get("content_type", "application/octet-stream")
                    filename = att.get("filename", f"attachment_{idx}")

                    log.info(
                        f"📤 Sending attachment {idx}/{len(attachments)}: {content_type} - {filename}"
                    )

                    try:
                        # Send media message with URL
                        twilio_client.send_message(
                            to=from_number,
                            body=filename,  # Use filename as caption
                            media_url=[url],  # Must be a list
                        )
                        log.info(
                            f"✅ Attachment {idx}/{len(attachments)} sent successfully"
                        )

                    except Exception as att_error:
                        log.error(
                            f"❌ Failed to send attachment {idx}/{len(attachments)}: {att_error}"
                        )

            except Exception as attachment_error:
                log.error(
                    f"❌ Error sending attachments: {attachment_error}", exc_info=True
                )

        # FSM: Record successful message processing (idempotency)
        if settings.enable_fsm:
            try:
                await state_manager.record_idempotency(
                    user_id=phone_number,
                    message_id=message_sid,
                    result={
                        "status": "processed",
                        "intent": intent if "intent" in locals() else None,
                    },
                )
                log.info(f"✅ Idempotency recorded for message {message_sid}")
            except Exception as idempotency_error:
                # Don't fail the whole request if idempotency recording fails
                log.warning(f"Failed to record idempotency: {idempotency_error}")

    except Exception as e:
        log.error(f"Error processing message: {e}")
        import traceback

        log.error(f"Traceback: {traceback.format_exc()}")

        # Send error message to user
        try:
            error_msg = "Désolé, une erreur s'est produite. Veuillez réessayer."
            if user_language and user_language != "fr":
                error_msg = await translation_service.translate_from_french(
                    error_msg, user_language
                )
            twilio_client.send_message(from_number, error_msg)
        except Exception as error_notification_failure:
            # Critical: Failed to notify user of error
            log.error(
                f"CRITICAL: Failed to send error notification to user {from_number}. "
                f"Original error: {str(e)[:200]}, "
                f"Notification failure: {error_notification_failure}"
            )
            # Last resort: attempt to save to database for manual follow-up
            try:
                await supabase_client.save_message(
                    user_id=user_id if "user_id" in locals() else "unknown",
                    message_text=f"CRITICAL ERROR - User not notified: {str(e)[:200]}",
                    original_language="en",
                    direction="outbound",
                    is_escalation=True,
                    escalation_reason="Critical error - user notification failed",
                )
            except Exception as db_error:
                log.error(f"CRITICAL: Database logging also failed: {db_error}")
