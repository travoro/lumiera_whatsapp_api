"""Message processing handler."""
from typing import Optional, Dict, Any
import httpx
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.agent.agent import lumiera_agent
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
) -> None:
    """Process an inbound WhatsApp message.

    Args:
        from_number: The sender's WhatsApp number (format: whatsapp:+33123456789)
        message_body: The message text
        message_sid: Twilio message SID
        media_url: Optional media URL if message includes media
        media_content_type: Content type of media
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

        # Detect language if not just French
        detected_language = await translation_service.detect_language(message_body)

        # Translate to French if needed (do this before validation)
        if detected_language != "fr":
            message_in_french = await translation_service.translate_to_french(
                message_body, detected_language
            )

            # Update user language if it changed
            if detected_language != user_language:
                await supabase_client.create_or_update_user(
                    phone_number=phone_number,
                    language=detected_language,
                )
                user_language = detected_language

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

        # 2. Get or create session
        session = await session_service.get_or_create_session(user_id)
        session_id = session['id'] if session else None
        log.info(f"Using session {session_id} for user {user_id}")

        # 3. Classify intent for analytics and potential routing
        intent_result = await intent_classifier.classify(message_in_french, user_id)
        log.info(f"Intent: {intent_result['intent']} (requires_tools: {intent_result['requires_tools']})")

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
            recent_message_count=8  # Keep last 8 messages as-is
        )

        # Convert recent messages to LangChain format
        chat_history = convert_messages_to_langchain(recent_messages)

        # If there's a summary of older messages, prepend it as context
        if older_summary:
            chat_history.insert(0, SystemMessage(content=f"Contexte de la conversation précédente:\n{older_summary}"))
            log.info(f"Using summarized context + {len(recent_messages)} recent messages")
        else:
            log.info(f"Using {len(chat_history)} messages for context (no summary needed)")

        # Process with agent (in French) with conversation history and context
        response_in_french = await lumiera_agent.process_message(
            user_id=user_id,
            phone_number=phone_number,
            language=user_language,
            message_text=message_in_french,
            chat_history=chat_history,
            user_name=user_name,  # Pass official contact name from database
            user_context=user_context_str,  # Pass user context for personalization
        )

        log.info(f"Agent response (French): {response_in_french[:100]}...")

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
            # Format for interactive messages
            log.info(f"📱 Response text before formatting ({len(response_text)} chars): {response_text[:200]}...")
            message_text, interactive_data = format_for_interactive(response_text)
            log.info(f"📱 Message text after formatting ({len(message_text)} chars): {message_text[:200]}...")
            log.info(f"📱 Interactive data present: {interactive_data is not None}")
        else:
            # Send as plain text - no extraction
            message_text = response_text
            interactive_data = None
            log.info(f"📱 Sending as plain text (no formatting)")

        # Save outbound message with session tracking
        await supabase_client.save_message(
            user_id=user_id,
            message_text=message_text,
            original_language=user_language,
            direction="outbound",
            session_id=session_id,
        )

        # Send response via Twilio with interactive support
        send_whatsapp_message_smart(
            to=from_number,
            text=message_text,
            interactive_data=interactive_data,
            user_name=user_name,
            language=user_language
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
        except:
            pass
