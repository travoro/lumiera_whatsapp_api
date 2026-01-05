"""Message processing handler."""
from typing import Optional, Dict, Any
import httpx
import re
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
) -> Optional[str]:
    """Handle direct action execution without AI agent.

    Args:
        action: The action to execute (e.g., "view_sites", "talk_team")
        user_id: User's ID
        phone_number: User's WhatsApp phone number
        language: User's language code

    Returns:
        Response text if action was handled, None if needs AI conversation flow
    """
    log.info(f"🎯 Direct action handler called for action: {action}")

    # === DIRECT ACTIONS (No AI) ===

    if action == "view_sites":
        # Call list_projects_tool directly
        log.info(f"📋 Calling list_projects_tool for user {user_id}")
        response = await list_projects_tool.ainvoke({"user_id": user_id})
        return response

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
            return result.get("message")
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
            return result.get("message")
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
        return response

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
            return result.get("message")
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
            return result.get("message")
        else:
            # Fallback to AI if fast path fails
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
    """Process an inbound WhatsApp message.

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
        # Normalize phone number - remove 'whatsapp:' prefix if present
        phone_number = from_number.replace("whatsapp:", "").strip()
        log.info(f"Processing message from {phone_number} (original: {from_number})")

        # Get subcontractor (lookup only - never auto-create)
        user = await supabase_client.get_user_by_phone(phone_number)

        if not user:
            # Subcontractor not found - only admins can create them in backoffice
            log.warning(f"Unknown phone number: {phone_number}. Subcontractor not registered.")

            # Detect language of incoming message to respond appropriately
            detected_language = await translation_service.detect_language(message_body)

            # Respond in their language with "I don't know you" message
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

            log.info(f"Sent 'unknown user' message in {detected_language} to {phone_number}")
            return

        user_id = user["id"]
        user_language = user.get("language", "fr")
        user_name = user.get("contact_prenom", "")  # Get contact first name

        # Check if user has active escalation
        is_blocked = await escalation_service.should_block_user(user_id)
        if is_blocked:
            # User is escalated, notify them
            response_text = await translation_service.translate_from_french(
                "Votre conversation est actuellement gérée par un administrateur. Vous serez contacté sous peu.",
                user_language,
            )
            twilio_client.send_message(from_number, response_text)
            return

        # Get or create session early (so direct actions also get session_id)
        session = await session_service.get_or_create_session(user_id)
        session_id = session['id'] if session else None
        log.info(f"Session {session_id} for user {user_id}")

        # Handle audio message
        if media_url and media_content_type and media_content_type.startswith("audio"):
            log.info("Processing audio message")
            # Transcribe audio to French
            transcribed_text = await transcription_service.transcribe_audio(
                media_url, translate_to_french=True
            )

            if transcribed_text:
                message_body = transcribed_text
                log.info(f"Audio transcribed: {transcribed_text[:100]}...")
            else:
                response_text = await translation_service.translate_from_french(
                    "Désolé, je n'ai pas pu transcrire votre message audio.",
                    user_language,
                )
                twilio_client.send_message(from_number, response_text)
                return

        # Check if Body contains an interactive list action (e.g., "view_sites_es", "option_1_fr")
        # Pattern: action_name followed by underscore and 2-letter language code
        action_pattern = r'^(.+)_([a-z]{2})$'
        action_match = re.match(action_pattern, message_body.strip())

        is_interactive_response = action_match is not None
        action_id = None

        if is_interactive_response:
            # Extract action and language from the pattern
            action_id = action_match.group(1)  # e.g., "view_sites" or "option_1"
            action_language = action_match.group(2)  # e.g., "es", "fr"

            log.info(f"🔘 Interactive action detected: {action_id} (language: {action_language})")

            # Try to handle as direct action
            direct_response = await handle_direct_action(
                action=action_id,
                user_id=user_id,
                phone_number=phone_number,
                language=user_language,
            )

            if direct_response:
                # Direct action was handled successfully
                log.info(f"✅ Direct action '{action_id}' executed successfully")

                # Translate response to user's language
                if user_language != "fr":
                    response_text = await translation_service.translate_from_french(
                        direct_response, user_language
                    )
                else:
                    response_text = direct_response

                # Check if this is an escalation action (talk_team)
                is_escalation_action = action_id == "talk_team"

                # Save the interaction to database
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
                    need_human=is_escalation_action,  # Set need_human=True for escalations
                )

                # Send response (no interactive formatting for direct actions)
                twilio_client.send_message(from_number, response_text)
                log.info(f"📤 Direct action response sent to {from_number}")
                return

            # Direct action not handled, continue with normal flow using action_id
            message_in_french = action_id  # Use action without language suffix
            detected_language = user_language  # Keep current language
            log.info(f"⚙️ Action '{action_id}' will be processed by AI agent")
        else:
            # Regular text message - detect language with smart context
            # Don't detect language for very short messages or pure numbers
            message_stripped = message_body.strip()
            is_very_short = len(message_stripped) < 5
            is_number = message_stripped.isdigit()

            if is_very_short or is_number:
                # Keep current user language for short/numeric messages
                detected_language = user_language
                log.info(f"⚠️ Message too short/numeric ('{message_body}'), keeping current language: {user_language}")
            else:
                # Detect language for substantial messages
                detected_language = await translation_service.detect_language(message_body)
                log.info(f"Detected language: {detected_language} (original message: {message_body[:50]}...)")

                # Update user language if it changed (only for typed messages)
                if detected_language != user_language:
                    await supabase_client.create_or_update_user(
                        phone_number=phone_number,
                        language=detected_language,
                    )
                    user_language = detected_language
                    log.info(f"Updated user language to: {detected_language}")

            # Translate to French if needed (do this before validation)
            if detected_language != "fr":
                message_in_french = await translation_service.translate_to_french(
                    message_body, detected_language
                )
            else:
                message_in_french = message_body

            log.info(f"Message in French: {message_in_french[:100]}...")

        # === PHASE 2: VALIDATION, SESSION, INTENT, CONTEXT ===

        # 1. Validate input for security
        validation_result = await validate_input(message_in_french, user_id)
        if not validation_result["is_valid"]:
            error_msg = validation_result["message"]
            log.warning(f"Invalid input from user {user_id}: {validation_result['reason']}")

            # Translate and send error
            if user_language != "fr":
                error_msg = await translation_service.translate_from_french(error_msg, user_language)
            twilio_client.send_message(from_number, error_msg)
            return

        # Use sanitized message
        message_in_french = validation_result["sanitized"]

        # 2. Session already created earlier (line 185)

        # 3. Classify intent for analytics and HYBRID ROUTING
        intent_result = await intent_classifier.classify(message_in_french, user_id)
        confidence = intent_result.get('confidence', 0.0)
        log.info(f"Intent: {intent_result['intent']} | Confidence: {confidence:.2%} | Requires tools: {intent_result['requires_tools']}")

        # 🚀 HYBRID ROUTING: Use fast path for high-confidence simple intents
        from src.config import settings
        CONFIDENCE_THRESHOLD = settings.intent_confidence_threshold
        USE_FAST_PATH = settings.enable_fast_path_handlers

        agent_result = None
        used_fast_path = False

        if USE_FAST_PATH and confidence >= CONFIDENCE_THRESHOLD:
            intent = intent_result['intent']
            log.info(f"🚀 HIGH CONFIDENCE ({confidence:.2%}) - Attempting fast path for: {intent}")

            # Import direct handlers
            from src.services.handlers import execute_direct_handler

            # Try direct execution
            agent_result = await execute_direct_handler(
                intent=intent,
                user_id=user_id,
                phone_number=phone_number,
                user_name=user_name,
                language=user_language,
                reason=message_in_french  # For escalation
            )

            if agent_result:
                used_fast_path = True
                log.info(f"✅ FAST PATH SUCCESS: {intent} executed directly (saved Opus call)")
            else:
                log.warning(f"⚠️ FAST PATH FAILED: Falling back to full agent for {intent}")

        # If fast path not used or failed, use full agent
        if not agent_result:
            if confidence < CONFIDENCE_THRESHOLD:
                log.info(f"⚙️ LOW CONFIDENCE ({confidence:.2%}) - Using full agent (Opus)")
            else:
                log.info(f"⚙️ FALLBACK - Using full agent (Opus)")

            # 4. Get user context for personalization
            user_context_str = await user_context_service.get_context_for_agent(user_id)
            if user_context_str:
                log.info(f"Retrieved user context: {len(user_context_str)} chars")

            # 5. Save inbound message with session tracking
            await supabase_client.save_message(
                user_id=user_id,
                message_text=message_body,
                original_language=detected_language,
                direction="inbound",
                message_sid=message_sid,
                media_url=media_url,
                session_id=session_id,
            )

            # Retrieve conversation history for context
            full_conversation_history = await supabase_client.get_conversation_history(
                user_id=user_id,
                limit=30  # Get more messages for potential summarization
            )

            # Optimize conversation history (summarize if too long)
            recent_messages, older_summary = await memory_service.get_optimized_history(
                messages=full_conversation_history,
                recent_message_count=15,  # Keep last 15 messages as-is (increased from 8)
                user_id=user_id  # Pass user_id for caching
            )

            # Convert recent messages to LangChain format
            chat_history = convert_messages_to_langchain(recent_messages)

            # If there's a summary of older messages, prepend it as context
            if older_summary:
                chat_history.insert(0, SystemMessage(content=f"Contexte de la conversation précédente:\n{older_summary}"))
                log.info(f"Using summarized context + {len(recent_messages)} recent messages")
            else:
                log.info(f"Using {len(chat_history)} messages for context (no summary needed)")

            # Add context if this is an interactive list response
            if is_interactive_response:
                context_msg = f"[CONTEXTE: L'utilisateur a sélectionné l'option '{button_payload}' depuis un menu interactif. Texte de l'option: '{button_text}']"
                chat_history.insert(0, SystemMessage(content=context_msg))
                log.info(f"Added interactive response context to chat history")

            # Process with agent (in French) with conversation history and context
            agent_result = await lumiera_agent.process_message(
                user_id=user_id,
                phone_number=phone_number,
                language=user_language,
                message_text=message_in_french,
                chat_history=chat_history,
                user_name=user_name,  # Pass official contact name from database
                user_context=user_context_str,  # Pass user context for personalization
            )
        else:
            # Fast path was successful - still save inbound message
            await supabase_client.save_message(
                user_id=user_id,
                message_text=message_body,
                original_language=detected_language,
                direction="inbound",
                message_sid=message_sid,
                media_url=media_url,
                session_id=session_id,
            )

        # Extract structured data from agent result
        if isinstance(agent_result, dict):
            response_in_french = agent_result.get("message", agent_result.get("output", ""))
            is_agent_escalation = agent_result.get("escalation", agent_result.get("escalation_occurred", False))
            tools_called = agent_result.get("tools_called", [])
        else:
            # Fallback for backward compatibility (if agent returns string)
            response_in_french = agent_result
            is_agent_escalation = False
            tools_called = []

        # Ensure response_in_french is always a string (defensive check)
        if not isinstance(response_in_french, str):
            log.warning(f"Agent returned non-string response: {type(response_in_french)}")

            # Handle Claude API content blocks format: [{'text': '...', 'type': 'text', 'index': 0}]
            if isinstance(response_in_french, list) and len(response_in_french) > 0:
                if isinstance(response_in_french[0], dict) and 'text' in response_in_french[0]:
                    response_in_french = response_in_french[0]['text']
                    log.info("Extracted text from content blocks")
                else:
                    response_in_french = str(response_in_french)
            elif response_in_french:
                response_in_french = str(response_in_french)
            else:
                response_in_french = "Désolé, une erreur s'est produite."

        log.info(f"Agent response (French): {response_in_french[:100]}...")
        log.info(f"Agent escalation: {is_agent_escalation}")
        log.info(f"Tools called: {tools_called}")

        # Translate response back to user language
        if user_language != "fr":
            response_text = await translation_service.translate_from_french(
                response_in_french, user_language
            )
        else:
            response_text = response_in_french

        # Interactive formatting - NOW ENABLED via direct Twilio REST API!
        # Using requests library to call Twilio API directly (Python SDK doesn't support it yet)
        USE_INTERACTIVE_FORMATTING = True

        if USE_INTERACTIVE_FORMATTING:
            # Format for interactive messages, passing user language for ID suffixes
            log.info(f"📱 Response text before formatting ({len(response_text)} chars): {response_text[:200]}...")
            message_text, interactive_data = format_for_interactive(response_text, user_language)
            log.info(f"📱 Message text after formatting ({len(message_text)} chars): {message_text[:200]}...")
            log.info(f"📱 Interactive data present: {interactive_data is not None}")
        else:
            # Send as plain text - no extraction
            message_text = response_text
            interactive_data = None
            log.info(f"📱 Sending as plain text (no formatting)")

        # is_agent_escalation is already set from agent result (tool call detection)
        # No need for keyword matching - the agent tells us if it called escalate_to_human_tool

        # Save outbound message with session tracking
        await supabase_client.save_message(
            user_id=user_id,
            message_text=message_text,
            original_language=user_language,
            direction="outbound",
            session_id=session_id,
            need_human=is_agent_escalation,  # Set need_human=True for escalations
        )

        # Check if this is a greeting intent (to use universal template)
        is_greeting_intent = intent_result.get('intent', '') in ['greeting', 'hello', 'bonjour', 'hola']

        # Send response via Twilio with interactive support
        send_whatsapp_message_smart(
            to=from_number,
            text=message_text,
            interactive_data=interactive_data,
            user_name=user_name,
            language=user_language,
            is_greeting=is_greeting_intent
        )

        if interactive_data:
            log.info(f"Interactive message sent to {from_number}")
        else:
            log.info(f"Text message sent to {from_number}")

    except Exception as e:
        log.error(f"Error processing message: {e}")

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
                    need_human=True
                )
            except Exception as db_error:
                log.error(f"CRITICAL: Database logging also failed: {db_error}")
