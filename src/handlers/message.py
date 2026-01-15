"""Message processing handler."""
from typing import Optional, Dict, Any
import httpx
import re
import os
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.agent.agent import lumiera_agent
from src.agent.tools import (
    list_projects_tool,
    escalate_to_human_tool,
)
from src.services.translation import translation_service
from src.services.transcription import transcription_service
from src.services.escalation import escalation_service
from src.services.memory import memory_service
from src.services.session import session_service
from src.services.user_context import user_context_service
from src.services.validation import validate_input
from src.services.intent import intent_classifier
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.utils.logger import log
from src.utils.whatsapp_formatter import send_whatsapp_message_smart
from src.utils.response_parser import format_for_interactive
from src.services.intent_router import intent_router




async def handle_direct_action(
    action: str,
    user_id: str,
    phone_number: str,
    language: str,
) -> Optional[Dict[str, Any]]:
    """Handle direct action execution without AI agent.

    Args:
        action: The action to execute (e.g., "view_sites", "talk_team")
        user_id: User's ID
        phone_number: User's WhatsApp phone number
        language: User's language code

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
            "tool_outputs": [{
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": compact_projects(projects)
            }]
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
            language=language
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
            language=language
        )

        if result:
            # Return full structured response from handler (including list_type, carousel_data, etc.)
            return result
        else:
            # Fallback to AI if fast path fails
            return None

    elif action == "talk_team":
        # Escalate to human directly
        log.info(f"🗣️ Escalating user {user_id} to human team")
        response = await escalate_to_human_tool.ainvoke({
            "user_id": user_id,
            "phone_number": phone_number,
            "language": language,
            "reason": "L'utilisateur a demandé à parler avec l'équipe",
        })
        return {
            "message": response,
            "tool_outputs": []  # No tool outputs for escalation
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
            language=language
        )

        if result:
            # Return full structured response from handler (including list_type, carousel_data, etc.)
            return result
        else:
            # Fallback to AI if fast path fails
            return None

    elif action == "update_progress":
        # Route through intent router (proper layering)
        log.info(f"✅ Routing update_progress intent for user {user_id}")
        from src.integrations.supabase import supabase_client

        # Get user name using centralized helper
        user_name = supabase_client.get_user_name(user_id)

        result = await intent_router.route_intent(
            intent="update_progress",
            user_id=user_id,
            phone_number=phone_number,
            user_name=user_name,
            language=language
        )

        if result:
            # Return full structured response from handler (including list_type, carousel_data, etc.)
            return result
        else:
            # Fallback to AI if fast path fails
            return None

    # Handle interactive list selections (task_1_fr, tasks_1_fr, project_2_fr, projects_2_fr, option_3_fr, etc.)
    # Parse action format: {list_type}_{number}_{language}
    # Supports both singular and plural forms (task/tasks, project/projects)
    import re
    list_match = re.match(r'(tasks?|projects?|option)_(\d+)(?:_[a-z]{2})?', action)

    if list_match:
        list_type = list_match.group(1)
        option_number = list_match.group(2)
        log.info(f"📋 Interactive list selection detected: {action}")
        log.info(f"🏷️  Parsed list_type: {list_type}, option #{option_number}")

        # Get the last bot message to find what was in that position
        from src.integrations.supabase import supabase_client
        from src.services.session import session_service

        # Get session
        session = await session_service.get_or_create_session(user_id)
        session_id = session["id"]

        # Load recent messages
        messages = await supabase_client.get_messages_by_session(
            session_id,
            fields='content,direction,metadata,created_at'
        )

        # Limit to last 10 messages
        messages = messages[-10:] if messages else []

        # Find bot message with the specific tool_outputs we need
        # Search for the RIGHT tool, not just any tool_outputs
        target_tool = None
        if list_type in ["task", "tasks"]:
            target_tool = 'list_tasks_tool'
        elif list_type in ["project", "projects", "option"]:
            target_tool = 'list_projects_tool'

        log.info(f"🔍 Searching for {target_tool} in last {len(messages)} messages")

        tool_outputs = None
        for idx, msg in enumerate(reversed(messages)):
            log.debug(f"   Message {idx}: direction={msg.get('direction')}, has_metadata={msg.get('metadata') is not None}")
            if msg and msg.get('direction') == 'outbound':
                metadata = msg.get('metadata', {})
                msg_tool_outputs = metadata.get('tool_outputs', []) if metadata else []
                log.debug(f"   Message {idx} tool_outputs: {[t.get('tool') if isinstance(t, dict) else 'invalid' for t in msg_tool_outputs]}")

                if msg_tool_outputs:
                    # Check if this message has the tool we're looking for
                    has_target_tool = any(t.get('tool') == target_tool for t in msg_tool_outputs if isinstance(t, dict))
                    if has_target_tool:
                        tool_outputs = msg_tool_outputs
                        log.info(f"📦 Found tool_outputs with {target_tool} in message {idx}")
                        log.info(f"🔍 All tool_outputs: {[t.get('tool') for t in tool_outputs]}")
                        break

        if not tool_outputs:
            log.warning(f"❌ Could not find {target_tool} in conversation history")

        if tool_outputs:
            # Route based on list_type parsed from action ID (robust approach)
            # This eliminates ambiguity when multiple tool outputs are present

            if list_type in ["task", "tasks"]:
                # User selected a task from the list → Show task details
                for tool_output in tool_outputs:
                    if tool_output.get('tool') == 'list_tasks_tool':
                        tasks_output = tool_output.get('output', [])

                        # DEFENSIVE: Handle both old (string) and new (structured list) formats
                        if isinstance(tasks_output, str):
                            # Old format: formatted string - cannot use for selection
                            # Need to re-fetch tasks from database
                            log.warning(f"⚠️ Found old string format in tool_outputs (length: {len(tasks_output)})")
                            log.warning(f"   Re-fetching structured task data from database...")

                            from src.actions import tasks as task_actions
                            from src.services.project_context import project_context_service

                            # Get active project
                            project_id = await project_context_service.get_active_project(user_id)
                            if not project_id:
                                log.error(f"   ❌ No active project to re-fetch tasks")
                                return None

                            # Re-fetch tasks
                            task_result = await task_actions.list_tasks(user_id, project_id)
                            if task_result.get("success") and task_result.get("data"):
                                from src.utils.metadata_helpers import compact_tasks
                                tasks = compact_tasks(task_result["data"])
                                log.info(f"   ✅ Re-fetched {len(tasks)} tasks from database")
                            else:
                                log.error(f"   ❌ Failed to re-fetch tasks")
                                return None
                        elif isinstance(tasks_output, list):
                            # New format: structured list of dicts
                            tasks = tasks_output
                            log.info(f"📋 Found {len(tasks)} tasks in tool_outputs (structured format)")
                        else:
                            log.error(f"❌ Unexpected tool_output format: {type(tasks_output)}")
                            return None

                        # Get the task at the selected index (1-based)
                        index = int(option_number) - 1
                        if 0 <= index < len(tasks):
                            selected_task = tasks[index]

                            # Ensure selected_task is a dict
                            if not isinstance(selected_task, dict):
                                log.error(f"❌ selected_task is not a dict: {type(selected_task)}")
                                return None

                            task_id = selected_task.get('id')
                            task_title = selected_task.get('title')
                            log.info(f"✅ Resolved {list_type}_{option_number} → {task_title} (ID: {task_id[:8] if task_id else 'NONE'}...)")

                            # Trigger task_details with the selected task
                            from src.services.handlers import execute_direct_handler
                            from src.integrations.supabase import supabase_client

                            user_name = supabase_client.get_user_name(user_id)

                            # Pass updated tool_outputs with structured tasks data (not old string format)
                            updated_tool_outputs = [
                                {
                                    'tool': 'list_tasks_tool',
                                    'input': {},
                                    'output': tasks  # Use the structured tasks we just retrieved
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
                                last_tool_outputs=updated_tool_outputs
                            )

                            if result:
                                log.info(f"✅ Task details called for selected task")
                                return result
                            else:
                                log.warning(f"⚠️ Task details handler returned None")
                                return None
                        else:
                            log.warning(f"⚠️ Option {option_number} out of range (0-{len(tasks)-1})")
                        break

            elif list_type in ["project", "projects", "option"]:
                # User selected a project from the list → Show project tasks
                for tool_output in tool_outputs:
                    if tool_output.get('tool') == 'list_projects_tool':
                        projects = tool_output.get('output', [])
                        log.info(f"📋 Found {len(projects)} projects in tool_outputs")

                        # Get the project at the selected index (1-based)
                        index = int(option_number) - 1
                        if 0 <= index < len(projects):
                            selected_project = projects[index]
                            project_id = selected_project.get('id')
                            project_name = selected_project.get('nom')
                            log.info(f"✅ Resolved {list_type}_{option_number} → {project_name} (ID: {project_id[:8]}...)")

                            # Trigger list_tasks with the selected project
                            from src.services.handlers import execute_direct_handler
                            from src.integrations.supabase import supabase_client

                            user_name = supabase_client.get_user_name(user_id)

                            result = await execute_direct_handler(
                                intent="list_tasks",
                                user_id=user_id,
                                phone_number=phone_number,
                                user_name=user_name,
                                language=language,
                                message_text=project_name,
                                session_id=session_id,
                                last_tool_outputs=tool_outputs
                            )

                            if result:
                                log.info(f"✅ List tasks called for selected project")
                                return result
                            else:
                                log.warning(f"⚠️ List tasks handler returned None")
                                return None
                        else:
                            log.warning(f"⚠️ Option {option_number} out of range (0-{len(projects)-1})")
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
    langchain_messages = []
    for msg in messages:
        content = msg.get("content", "")
        direction = msg.get("direction", "")

        if direction == "inbound":
            langchain_messages.append(HumanMessage(content=content))
        elif direction == "outbound":
            langchain_messages.append(AIMessage(content=content))

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

        # Quick user lookup for escalation blocking and direct actions
        user = await supabase_client.get_user_by_phone(phone_number)

        if not user:
            # Unknown user - detect language and send error message
            log.warning(f"Unknown phone number: {phone_number}. Subcontractor not registered.")
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
        session_id = session['id'] if session else None

        # Handle interactive button actions (direct actions bypass pipeline)
        action_pattern = r'^(.+)_([a-z]{2})$'
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
            )

            log.info(f"📋 Direct response received: type={type(direct_response)}, is_dict={isinstance(direct_response, dict)}")

            if direct_response:
                # Handle both string and dict responses (backward compatible)
                if isinstance(direct_response, dict):
                    response_message = direct_response.get("message", "")
                    tool_outputs = direct_response.get("tool_outputs", [])
                    carousel_data = direct_response.get("carousel_data")
                    log.info(f"📦 Dict response keys: {list(direct_response.keys())}")
                    log.info(f"   has carousel_data key: {'carousel_data' in direct_response}")
                    log.info(f"   carousel_data value: {carousel_data}")
                else:
                    response_message = direct_response
                    tool_outputs = []
                    carousel_data = None
                    log.info(f"📝 String response (no carousel_data)")

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
                    log.info(f"ℹ️ No translation needed (user language is French)")

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
                    escalation_reason="User requested to talk to team via direct action" if is_escalation_action else None,
                    metadata=metadata if metadata else None,
                )

                # Send response with interactive formatting
                log.info(f"📱 Formatting direct action response for potential interactive list")

                # Import formatting utilities
                from src.utils.response_parser import format_for_interactive
                from src.utils.whatsapp_formatter import send_whatsapp_message_smart

                # Extract list_type from response metadata (defaults to "option" if not provided)
                # Use direct_response if it's a dict, otherwise default to "option"
                list_type = direct_response.get("list_type", "option") if isinstance(direct_response, dict) else "option"
                log.info(f"🏷️  List type for interactive formatting: {list_type}")

                # Format for interactive if applicable (e.g., list_projects, list_tasks)
                formatted_text, interactive_data = format_for_interactive(response_text, user_language, list_type)

                send_whatsapp_message_smart(
                    to=from_number,
                    text=formatted_text,
                    interactive_data=interactive_data,
                    user_name=user_name,
                    language=user_language,
                    is_greeting=False  # Direct actions are not greetings
                )

                log.info(f"📤 Direct action response sent (interactive: {interactive_data is not None})")

                # Send attachments one by one as separate messages
                log.info(f"🔍 Checking for carousel_data: {carousel_data is not None}")
                if carousel_data:
                    log.info(f"   carousel_data keys: {list(carousel_data.keys())}")
                    log.info(f"   Has cards: {carousel_data.get('cards') is not None}")
                    if carousel_data.get('cards'):
                        log.info(f"   Number of cards: {len(carousel_data.get('cards'))}")

                if carousel_data and carousel_data.get("cards"):
                    cards = carousel_data["cards"]
                    log.info(f"📎 Sending {len(cards)} attachments one by one")

                    try:
                        from src.integrations.twilio import twilio_client
                        import time

                        for idx, card in enumerate(cards, 1):
                            media_url = card.get('media_url')
                            media_type = card.get('media_type', 'unknown')
                            media_name = card.get('media_name', 'document')

                            if not media_url:
                                log.warning(f"   ⚠️ Attachment {idx}: No media_url, skipping")
                                continue

                            # Log what type of file we're sending
                            file_type = "PDF document" if "pdf" in media_type.lower() else f"{media_type}"
                            log.info(f"   📤 Sending attachment {idx}/{len(cards)}: {file_type}")
                            log.info(f"      Name: {media_name}")
                            log.info(f"      URL: {media_url[:80]}...")

                            # Download the file to temp storage (to avoid Twilio error 63019)
                            log.info(f"   📥 Step 1: Downloading file from external URL...")
                            local_file_path = twilio_client.download_and_upload_media(
                                media_url=media_url,
                                content_type=media_type,
                                filename=media_name  # Save with actual filename
                            )

                            if not local_file_path:
                                log.error(f"   ❌ Failed to download attachment {idx}, skipping")
                                continue

                            # Send the local file without text (just the file)
                            log.info(f"   📤 Step 2: Uploading and sending file via Twilio...")
                            from src.config import settings
                            message_sid = twilio_client.send_message_with_local_media(
                                to=from_number,
                                body=" ",  # No text, just the file
                                local_file_path=local_file_path,
                                server_url=settings.server_url
                            )

                            # Note: We do NOT delete the file immediately because Twilio needs to download it
                            # The media handler will auto-cleanup the file after 5 minutes
                            log.info(f"   ⏰ File will auto-cleanup in 5 minutes")

                            if message_sid:
                                log.info(f"   ✅ {file_type} successfully sent to Twilio")
                                log.info(f"   📬 Message SID: {message_sid}")

                                # Fetch message status to check for delivery issues (immediate)
                                try:
                                    fetched_msg = twilio_client.client.messages(message_sid).fetch()
                                    log.info(f"   📊 Initial status: {fetched_msg.status}")
                                    if fetched_msg.error_code:
                                        log.error(f"   ⚠️ Twilio error code: {fetched_msg.error_code}")
                                    if fetched_msg.error_message:
                                        log.error(f"   ⚠️ Twilio error message: {fetched_msg.error_message}")
                                except Exception as fetch_error:
                                    log.warning(f"   ⚠️ Could not fetch immediate status: {fetch_error}")

                                # Wait a bit and check final status
                                try:
                                    log.info(f"   ⏳ Waiting 3 seconds for Twilio to process media...")
                                    time.sleep(3)
                                    fetched_msg = twilio_client.client.messages(message_sid).fetch()
                                    log.info(f"   📊 Final status: {fetched_msg.status}")

                                    if fetched_msg.status in ['failed', 'undelivered']:
                                        log.error(f"   ❌ Message failed to deliver!")
                                        if fetched_msg.error_code:
                                            log.error(f"   ⚠️ Error code: {fetched_msg.error_code}")
                                        if fetched_msg.error_message:
                                            log.error(f"   ⚠️ Error message: {fetched_msg.error_message}")
                                    elif fetched_msg.status == 'sent':
                                        log.info(f"   ✅ Message successfully sent to WhatsApp!")
                                    elif fetched_msg.status == 'delivered':
                                        log.info(f"   ✅ Message delivered to recipient!")
                                    else:
                                        log.info(f"   ℹ️ Message still processing (status: {fetched_msg.status})")
                                except Exception as fetch_error:
                                    log.warning(f"   ⚠️ Could not fetch final status: {fetch_error}")
                            else:
                                log.error(f"   ❌ Failed to send attachment {idx}")

                            # Small delay between messages to avoid rate limits
                            if idx < len(cards):
                                time.sleep(0.3)

                        log.info(f"✅ SUCCESS: Recovered and pushed all {len(cards)} attachment(s) to Twilio")

                    except Exception as attachment_error:
                        log.error(f"❌ Error sending attachments: {attachment_error}", exc_info=True)
                else:
                    log.info(f"ℹ️ No attachments to send")

                return
            else:
                # Direct action handler returned None - fallback to AI pipeline
                log.warning(f"⚠️ Direct action '{action_id}' returned None - falling back to AI pipeline")
                log.info(f"   Handler could not resolve parameters, letting AI agent handle it")
                # Don't return - continue to pipeline processing below

        # === PHASE 2: CORE PROCESSING - USE PIPELINE ===
        from src.handlers.message_pipeline import message_pipeline

        # Convert button data to interactive_data format
        interactive_data = None
        if button_payload or button_text:
            interactive_data = {
                "payload": button_payload,
                "text": button_text
            }

        log.info(f"🔄 Processing message through pipeline")
        result = await message_pipeline.process(
            from_number=phone_number,
            message_body=message_body,
            message_sid=message_sid,
            media_url=media_url,
            media_type=media_content_type,
            interactive_data=interactive_data
        )

        if not result.success:
            # Pipeline error - send user-friendly message
            log.error(f"Pipeline failed: {result.error_message}")
            error_msg = result.user_message or "Désolé, une erreur s'est produite. Veuillez réessayer."

            if user_language != "fr":
                error_msg = await translation_service.translate_from_french(error_msg, user_language)

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
            log.info(f"🌍 Using detected language: {detected_language} (profile: {user_language})")
        user_language = detected_language

        # Intent-driven response formatting
        # Only format as interactive lists for specific intents where we expect structured data
        INTERACTIVE_LIST_INTENTS = {"greeting", "list_projects", "list_tasks"}

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

        if intent in INTERACTIVE_LIST_INTENTS:
            log.info(f"📱 Intent '{intent}' expects structured data → Formatting as interactive list")

            # Infer list_type from intent (for robust option ID generation)
            if intent in ["list_tasks", "view_tasks"]:
                list_type = "tasks"
            elif intent in ["list_projects", "switch_project"]:
                list_type = "projects"
            else:
                list_type = "option"  # Fallback for other intents

            log.info(f"🏷️  Inferred list_type from intent: {list_type}")
            message_text, interactive_data = format_for_interactive(response_text, user_language, list_type)
        else:
            log.info(f"📱 Intent '{intent}' is conversational → Sending as plain text")
            # Agent output is normalized to string in agent.py
            message_text = response_text
            interactive_data = None

        # Detect greeting for special handling (dynamic template with menu)
        is_greeting_intent = (intent == "greeting")
        if is_greeting_intent:
            log.info(f"✅ Greeting intent (confidence: {confidence:.2%}) → Will use dynamic template with menu")

        # Send response via Twilio
        send_whatsapp_message_smart(
            to=from_number,
            text=message_text,
            interactive_data=interactive_data,
            user_name=user_name,
            language=user_language,
            is_greeting=is_greeting_intent
        )

        log.info(f"📤 Response sent to {from_number} (interactive: {interactive_data is not None})")

        # Check for attachments and send one by one as separate messages
        carousel_data = response_data.get("carousel_data")
        if carousel_data and carousel_data.get("cards"):
            cards = carousel_data["cards"]
            log.info(f"📎 Sending {len(cards)} attachments one by one")

            try:
                from src.integrations.twilio import twilio_client
                import time

                for idx, card in enumerate(cards, 1):
                    media_url = card.get('media_url')
                    media_type = card.get('media_type', 'unknown')
                    media_name = card.get('media_name', 'document')

                    if not media_url:
                        log.warning(f"   ⚠️ Attachment {idx}: No media_url, skipping")
                        continue

                    file_type = "PDF document" if "pdf" in media_type.lower() else f"{media_type}"
                    log.info(f"   📤 Sending attachment {idx}/{len(cards)}: {file_type}")
                    log.info(f"      Name: {media_name}")
                    log.info(f"      URL: {media_url[:80]}...")

                    # Download the file to temp storage (to avoid Twilio error 63019)
                    log.info(f"   📥 Step 1: Downloading file from external URL...")
                    local_file_path = twilio_client.download_and_upload_media(
                        media_url=media_url,
                        content_type=media_type,
                        filename=media_name  # Save with actual filename
                    )

                    if not local_file_path:
                        log.error(f"   ❌ Failed to download attachment {idx}, skipping")
                        continue

                    # Send the local file without text (just the file)
                    log.info(f"   📤 Step 2: Uploading and sending file via Twilio...")
                    from src.config import settings
                    message_sid = twilio_client.send_message_with_local_media(
                        to=from_number,
                        body=" ",  # No text, just the file
                        local_file_path=local_file_path,
                        server_url=settings.server_url
                    )

                    # Note: We do NOT delete the file immediately because Twilio needs to download it
                    # The media handler will auto-cleanup the file after 5 minutes
                    log.info(f"   ⏰ File will auto-cleanup in 5 minutes")

                    if message_sid:
                        log.info(f"   ✅ {file_type} sent: {message_sid}")
                    else:
                        log.error(f"   ❌ Failed to send attachment {idx}")

                    # Small delay between messages to avoid rate limits
                    if idx < len(cards):
                        time.sleep(0.3)

                log.info(f"✅ All {len(cards)} attachments sent successfully")

            except Exception as attachment_error:
                log.error(f"❌ Error sending attachments: {attachment_error}", exc_info=True)

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
                    user_id=user_id if 'user_id' in locals() else "unknown",
                    message_text=f"CRITICAL ERROR - User not notified: {str(e)[:200]}",
                    original_language="en",
                    direction="outbound",
                    is_escalation=True,
                    escalation_reason="Critical error - user notification failed"
                )
            except Exception as db_error:
                log.error(f"CRITICAL: Database logging also failed: {db_error}")
