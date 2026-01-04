"""Message processing handler."""
from typing import Optional, Dict, Any
import httpx
from src.agent.agent import lumiera_agent
from src.services.translation import translation_service
from src.services.transcription import transcription_service
from src.services.escalation import escalation_service
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.utils.logger import log


async def process_inbound_message(
    from_number: str,
    message_body: str,
    message_sid: str,
    media_url: Optional[str] = None,
    media_content_type: Optional[str] = None,
) -> None:
    """Process an inbound WhatsApp message.

    Args:
        from_number: The sender's WhatsApp number
        message_body: The message text
        message_sid: Twilio message SID
        media_url: Optional media URL if message includes media
        media_content_type: Content type of media
    """
    try:
        log.info(f"Processing message from {from_number}")

        # Get or create user
        user = await supabase_client.get_user_by_phone(from_number)

        if not user:
            # Create new user with default language
            user = await supabase_client.create_or_update_user(
                phone_number=from_number,
                language="fr",
            )

        if not user:
            log.error("Failed to create/get user")
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
                    phone_number=from_number,
                    language=detected_language,
                )
                user_language = detected_language

        else:
            message_in_french = message_body

        log.info(f"Message in French: {message_in_french[:100]}...")

        # Process with agent (in French)
        response_in_french = await lumiera_agent.process_message(
            user_id=user_id,
            phone_number=from_number,
            language=user_language,
            message_text=message_in_french,
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
