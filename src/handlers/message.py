"""Message processing handler."""
from typing import Optional, Dict, Any
import httpx
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.agent.agent import lumiera_agent
from src.services.translation import translation_service
from src.services.transcription import transcription_service
from src.services.escalation import escalation_service
from src.services.memory import memory_service
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.utils.logger import log


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

        # Get or create user
        user = await supabase_client.get_user_by_phone(phone_number)

        if not user:
            # Subcontractor not found - they need to be registered first
            log.error(f"Subcontractor not found for phone {phone_number}. Must be created in Supabase first.")
            error_message = "Désolé, vous devez être enregistré pour utiliser ce service. Veuillez contacter l'administrateur."
            twilio_client.send_message(from_number, error_message)
            return

        user_id = user["id"]
        user_language = user.get("language", "fr")

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

        # Save original message
        await supabase_client.save_message(
            user_id=user_id,
            message_text=message_body,
            original_language=detected_language,
            direction="inbound",
            message_sid=message_sid,
            media_url=media_url,
        )

        # Translate to French if needed
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

        # Process with agent (in French) with conversation history
        response_in_french = await lumiera_agent.process_message(
            user_id=user_id,
            phone_number=phone_number,
            language=user_language,
            message_text=message_in_french,
            chat_history=chat_history,
        )

        log.info(f"Agent response (French): {response_in_french[:100]}...")

        # Translate response back to user language
        if user_language != "fr":
            response_text = await translation_service.translate_from_french(
                response_in_french, user_language
            )
        else:
            response_text = response_in_french

        # Save outbound message
        await supabase_client.save_message(
            user_id=user_id,
            message_text=response_text,
            original_language=user_language,
            direction="outbound",
        )

        # Send response via Twilio
        twilio_client.send_message(from_number, response_text)

        log.info(f"Response sent to {from_number}")

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
