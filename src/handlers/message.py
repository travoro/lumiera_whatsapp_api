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

            direct_response = await handle_direct_action(
                action=action_id,
                user_id=user_id,
                phone_number=phone_number,
                language=user_language,
            )

            if direct_response:
                log.info(f"✅ Direct action '{action_id}' executed successfully")

                # Translate response if needed
                if user_language != "fr":
                    response_text = await translation_service.translate_from_french(
                        direct_response, user_language
                    )
                else:
                    response_text = direct_response

                # Check if escalation action
                is_escalation_action = action_id == "talk_team"

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
                    need_human=is_escalation_action,
                )

                # Send response
                twilio_client.send_message(from_number, response_text)
                log.info(f"📤 Direct action response sent")
                return

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

        if intent in INTERACTIVE_LIST_INTENTS:
            log.info(f"📱 Intent '{intent}' expects structured data → Formatting as interactive list")
            message_text, interactive_data = format_for_interactive(response_text, user_language)
        else:
            log.info(f"📱 Intent '{intent}' is conversational → Sending as plain text")
            # Type safety: Agent may return list instead of string (LangChain quirk)
            if isinstance(response_text, list):
                log.info(f"📝 Agent returned list type, joining into string")
                message_text = '\n'.join(str(item) for item in response_text)
            else:
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
