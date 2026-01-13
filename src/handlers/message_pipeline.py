"""Message processing pipeline - refactored from god function.

Breaks down message processing into discrete, testable stages.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from src.integrations.supabase import supabase_client
from src.services.translation import translation_service
from src.services.transcription import transcription_service
from src.services.session import session_service
from src.services.intent import intent_classifier
from src.services.intent_router import intent_router
from src.agent.agent import lumiera_agent
from src.utils.logger import log
from src.exceptions import *
from src.utils.result import Result


@dataclass
class MessageContext:
    """Context object passed through pipeline stages."""

    # Input
    from_number: str
    message_body: str
    message_sid: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    interactive_data: Optional[Dict[str, Any]] = None

    # Populated by pipeline stages
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_language: Optional[str] = None
    session_id: Optional[str] = None
    message_in_french: Optional[str] = None
    last_bot_message: Optional[str] = None  # Last message sent by bot (for menu context)
    intent: Optional[str] = None
    confidence: Optional[float] = None
    response_text: Optional[str] = None
    escalation: bool = False
    tools_called: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "language": self.user_language,
            "session_id": self.session_id,
            "intent": self.intent,
            "confidence": self.confidence,
            "escalation": self.escalation
        }


class MessagePipeline:
    """Pipeline for processing inbound WhatsApp messages."""

    async def process(
        self,
        from_number: str,
        message_body: str,
        message_sid: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        interactive_data: Optional[Dict[str, Any]] = None
    ) -> Result[Dict[str, Any]]:
        """Process message through pipeline stages.

        Args:
            from_number: User's WhatsApp number
            message_body: Message text
            message_sid: Twilio message SID
            media_url: Media URL if present
            media_type: Media MIME type
            interactive_data: Interactive button data

        Returns:
            Result with response dict or error
        """
        ctx = MessageContext(
            from_number=from_number,
            message_body=message_body,
            message_sid=message_sid,
            media_url=media_url,
            media_type=media_type,
            interactive_data=interactive_data
        )

        try:
            # Stage 1: Authenticate user
            result = await self._authenticate_user(ctx)
            if not result.success:
                return result

            # Stage 2: Get or create session
            result = await self._manage_session(ctx)
            if not result.success:
                return result

            # Stage 3: Detect language
            result = await self._detect_language(ctx)
            if not result.success:
                return result

            # Stage 4: Process media (audio transcription)
            if ctx.media_url and ctx.media_type and 'audio' in ctx.media_type:
                result = await self._process_audio(ctx)
                if not result.success:
                    return result

            # Stage 5: Translate to French (internal language)
            result = await self._translate_to_french(ctx)
            if not result.success:
                return result

            # Stage 6: Classify intent
            result = await self._classify_intent(ctx)
            if not result.success:
                return result

            # Stage 7: Route to handler
            result = await self._route_message(ctx)
            if not result.success:
                return result

            # Stage 8: Translate response back to user language
            result = await self._translate_response(ctx)
            if not result.success:
                return result

            # Stage 9: Save to database
            await self._persist_messages(ctx)

            # Return final response (including detected language!)
            return Result.ok({
                "message": ctx.response_text,
                "escalation": ctx.escalation,
                "tools_called": ctx.tools_called,
                "session_id": ctx.session_id,
                "intent": ctx.intent,
                "confidence": ctx.confidence,
                "detected_language": ctx.user_language  # Include detected language!
            })

        except LumieraException as e:
            log.error(f"Pipeline error: {e}")
            return Result.from_exception(e)
        except Exception as e:
            log.error(f"Unexpected pipeline error: {e}")
            return Result.from_exception(e)

    async def _authenticate_user(self, ctx: MessageContext) -> Result[None]:
        """Stage 1: Authenticate user by phone number."""
        try:
            user = await supabase_client.get_user_by_phone(ctx.from_number)
            if not user:
                raise UserNotFoundException(user_id=ctx.from_number)

            ctx.user_id = user['id']
            ctx.user_name = user.get('contact_prenom') or user.get('contact_name', '')
            ctx.user_language = user.get('language', 'fr')

            log.info(f"✅ User authenticated: {ctx.user_id} ({ctx.user_name})")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _manage_session(self, ctx: MessageContext) -> Result[None]:
        """Stage 2: Get or create conversation session and load last bot message."""
        try:
            session = await session_service.get_or_create_session(ctx.user_id)
            if session:
                ctx.session_id = session['id']
                log.info(f"✅ Session: {ctx.session_id}")

                # Load last bot message for menu context (used by intent classifier)
                try:
                    messages = await supabase_client.get_messages_by_session(
                        ctx.session_id,
                        fields='content,direction,created_at'
                    )
                    # Find the last outbound message (from bot to user)
                    outbound_messages = [
                        msg for msg in messages
                        if msg.get('direction') == 'outbound'
                    ]
                    if outbound_messages:
                        # Sort by created_at to get the most recent
                        outbound_messages.sort(
                            key=lambda x: x.get('created_at', ''),
                            reverse=True
                        )
                        ctx.last_bot_message = outbound_messages[0].get('content')
                        log.info(f"📜 Loaded last bot message for menu context: '{ctx.last_bot_message[:50]}...' " if ctx.last_bot_message and len(ctx.last_bot_message) > 50 else f"📜 Loaded last bot message: '{ctx.last_bot_message}'")
                except Exception as e:
                    # Don't fail the pipeline if we can't load the last message
                    log.warning(f"Could not load last bot message: {e}")
                    ctx.last_bot_message = None

                return Result.ok(None)
            else:
                raise AgentExecutionException(stage="session_management")

        except Exception as e:
            return Result.from_exception(e)

    async def _detect_language(self, ctx: MessageContext) -> Result[None]:
        """Stage 3: Detect message language from content or use profile default."""
        try:
            profile_language = ctx.user_language  # From user profile
            detected_language = profile_language  # Default to profile

            # Try to detect language from message content using robust hybrid detection
            if ctx.message_body and len(ctx.message_body.strip()) > 2:
                try:
                    from src.services.language_detection import language_detection_service

                    # Log detection attempt with message preview
                    message_preview = ctx.message_body[:50] + "..." if len(ctx.message_body) > 50 else ctx.message_body
                    log.info(f"🔍 Detecting language for message: '{message_preview}' (profile: {profile_language})")

                    detected_language, detection_method = await language_detection_service.detect_async(
                        ctx.message_body,
                        fallback_language=profile_language
                    )

                    # Check if detection succeeded (not fallback)
                    if detection_method != 'fallback':
                        if detected_language != profile_language:
                            from src.config import settings

                            # Check if we should update the profile based on policy
                            should_update_profile = False
                            update_blocked_reason = None

                            # Check greeting exception policy
                            message_lower = ctx.message_body.strip().lower()
                            is_greeting_exception = message_lower in settings.language_greeting_exceptions_list

                            if is_greeting_exception:
                                update_blocked_reason = f"greeting exception ('{message_lower}')"
                            elif len(ctx.message_body.strip()) < settings.language_update_min_message_length:
                                update_blocked_reason = f"message too short ({len(ctx.message_body.strip())} chars < {settings.language_update_min_message_length})"
                            elif not settings.auto_update_user_language:
                                update_blocked_reason = "auto-update disabled in settings"
                            else:
                                should_update_profile = True

                            if should_update_profile:
                                log.info(
                                    f"🌍 Language detected: {detected_language} "
                                    f"(method: {detection_method}, profile: {profile_language}) "
                                    f"→ Profile will be updated"
                                )

                                # Update user profile language permanently
                                update_success = await supabase_client.update_user_language(
                                    ctx.user_id,
                                    detected_language
                                )

                                if update_success:
                                    log.info(
                                        f"✅ User profile language updated: "
                                        f"{profile_language} → {detected_language}"
                                    )
                                else:
                                    log.warning(
                                        f"⚠️ Failed to update profile language for user {ctx.user_id}"
                                    )
                            else:
                                log.info(
                                    f"🌍 Language detected: {detected_language} "
                                    f"(method: {detection_method}, profile: {profile_language}) "
                                    f"→ Profile update BLOCKED: {update_blocked_reason}"
                                )

                            # Use detected language for this message regardless of profile update
                            ctx.user_language = detected_language
                        else:
                            log.info(
                                f"✅ Language detected: {detected_language} "
                                f"(method: {detection_method}) → Matches profile, no update needed"
                            )
                    else:
                        # Fallback method means no confident detection
                        log.info(
                            f"⚠️ Language detection fallback: Using profile language {profile_language} "
                            f"(method: {detection_method})"
                        )
                        ctx.user_language = profile_language

                except Exception as e:
                    log.warning(
                        f"❌ Language detection error: {e} → Using profile language: {profile_language}"
                    )
                    ctx.user_language = profile_language
            else:
                log.info(f"⏩ Message too short for detection → Using profile language: {profile_language}")

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _process_audio(self, ctx: MessageContext) -> Result[None]:
        """Stage 4: Transcribe and store audio messages.

        This stage:
        1. Downloads audio from source URL (e.g., Twilio)
        2. Uploads to Supabase storage for permanent retention
        3. Transcribes to text in original language
        4. Updates ctx.message_body with transcription
        5. Updates ctx.media_url to point to stored file
        """
        try:
            if not (ctx.media_url and ctx.media_type and 'audio' in ctx.media_type):
                return Result.ok(None)  # Skip if not audio

            log.info(f"🎤 Processing audio message (transcribe + store)")

            # Download, store, and transcribe audio
            transcription, storage_url, whisper_detected_lang = await transcription_service.transcribe_and_store_audio(
                audio_url=ctx.media_url,
                user_id=ctx.user_id,
                message_sid=ctx.message_sid or "unknown",
                target_language=ctx.user_language,
                content_type=ctx.media_type
            )

            if not transcription:
                raise IntegrationException(service="Whisper", operation="transcription")

            # Update context with transcription
            ctx.message_body = transcription
            log.info(f"✅ Audio transcribed: {transcription[:50]}...")
            log.info(f"🔍 TRACE: Language from transcription service: {whisper_detected_lang}")
            log.info(f"🔍 TRACE: Current context language (profile): {ctx.user_language}")

            # Use detected language from transcribed text (already ISO 639-1 code)
            if whisper_detected_lang:
                if whisper_detected_lang != ctx.user_language:
                    log.info(
                        f"🌍 Audio language detected: {whisper_detected_lang} "
                        f"(differs from profile: {ctx.user_language})"
                    )

                    # Update user profile language permanently
                    update_success = await supabase_client.update_user_language(
                        ctx.user_id,
                        whisper_detected_lang
                    )

                    if update_success:
                        log.info(
                            f"✅ User profile language updated: "
                            f"{ctx.user_language} → {whisper_detected_lang}"
                        )
                    else:
                        log.warning(
                            f"⚠️ Failed to update profile language for user {ctx.user_id}"
                        )

                    # Use detected language for this message
                    ctx.user_language = whisper_detected_lang
                    log.info(f"🔍 TRACE: Context language UPDATED to: {ctx.user_language}")
                else:
                    log.info(f"✅ Detected language: {whisper_detected_lang} (matches profile)")
                    log.info(f"🔍 TRACE: Context language UNCHANGED: {ctx.user_language}")
            else:
                log.info("⚠️ No confident language detection from audio, keeping profile language")
                log.info(f"🔍 TRACE: Context language UNCHANGED (no detection): {ctx.user_language}")

            # Update media URL to point to stored file (not Twilio URL)
            if storage_url:
                ctx.media_url = storage_url
                log.info(f"✅ Audio stored: {storage_url}")
            else:
                log.warning("Audio transcribed but storage failed - using original URL")

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _translate_to_french(self, ctx: MessageContext) -> Result[None]:
        """Stage 5: Translate message to French (internal language)."""
        try:
            if ctx.user_language != "fr":
                ctx.message_in_french = await translation_service.translate_to_french(
                    ctx.message_body,
                    ctx.user_language
                )
                log.info(f"✅ Translated to French: {ctx.message_in_french[:50]}...")
            else:
                ctx.message_in_french = ctx.message_body

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _classify_intent(self, ctx: MessageContext) -> Result[None]:
        """Stage 6: Classify user intent with menu context awareness."""
        try:
            intent_result = await intent_classifier.classify(
                ctx.message_in_french,
                ctx.user_id,
                last_bot_message=ctx.last_bot_message  # Pass for menu context
            )
            ctx.intent = intent_result['intent']
            ctx.confidence = intent_result.get('confidence', 0.0)

            log.info(f"✅ Intent: {ctx.intent} (confidence: {ctx.confidence:.2%})")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _route_message(self, ctx: MessageContext) -> Result[None]:
        """Stage 7: Route to fast path handler or full agent."""
        try:
            from src.config import settings

            # Try fast path for high-confidence intents
            if settings.enable_fast_path_handlers and ctx.confidence >= settings.intent_confidence_threshold:
                log.info(f"🚀 HIGH CONFIDENCE - Attempting fast path")

                # Try fast path through router
                from src.services.handlers import execute_direct_handler

                result = await execute_direct_handler(
                    intent=ctx.intent,
                    user_id=ctx.user_id,
                    phone_number=ctx.from_number,
                    user_name=ctx.user_name,
                    language=ctx.user_language
                )

                if result:
                    ctx.response_text = result.get("message")
                    ctx.escalation = result.get("escalation", False)
                    ctx.tools_called = result.get("tools_called", [])
                    log.info(f"✅ Fast path succeeded")
                    return Result.ok(None)

            # Fallback to full agent
            log.info(f"⚙️ Using full agent (Opus)")

            # Load chat history for agent context
            chat_history = []
            try:
                from langchain_core.messages import HumanMessage, AIMessage
                messages = await supabase_client.get_messages_by_session(
                    ctx.session_id,
                    fields='content,direction,created_at'
                )
                # Convert to LangChain message format (last 10 messages for context)
                for msg in messages[-10:]:
                    if msg.get('direction') == 'inbound':
                        chat_history.append(HumanMessage(content=msg.get('content', '')))
                    elif msg.get('direction') == 'outbound':
                        chat_history.append(AIMessage(content=msg.get('content', '')))
                log.info(f"📜 Loaded {len(chat_history)} messages for agent context")
            except Exception as e:
                log.warning(f"Could not load chat history for agent: {e}")
                chat_history = []

            agent_result = await lumiera_agent.process_message(
                user_id=ctx.user_id,
                phone_number=ctx.from_number,
                user_name=ctx.user_name,
                language=ctx.user_language,
                message_text=ctx.message_in_french,
                chat_history=chat_history
            )

            ctx.response_text = agent_result.get("message")
            ctx.escalation = agent_result.get("escalation", False)
            ctx.tools_called = agent_result.get("tools_called", [])

            log.info(f"✅ Agent processed message")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _translate_response(self, ctx: MessageContext) -> Result[None]:
        """Stage 8: Translate response back to user language."""
        try:
            if ctx.user_language != "fr" and ctx.response_text:
                # Validate agent responded in French (architectural requirement)
                from src.services.language_detection import language_detection_service

                # Only check if response is substantial enough
                if len(ctx.response_text.strip()) > 10:
                    detected_lang, method = await language_detection_service.detect_async(
                        ctx.response_text,
                        fallback_language="fr"
                    )

                    if detected_lang != "fr":
                        log.warning(
                            f"⚠️ Agent responded in {detected_lang} instead of French! "
                            f"Response preview: {ctx.response_text[:100]}..."
                        )
                        # Translate from detected language instead
                        ctx.response_text = await translation_service.translate(
                            ctx.response_text,
                            source_language=detected_lang,
                            target_language=ctx.user_language
                        )
                        log.info(f"✅ Response translated from {detected_lang} to {ctx.user_language}")
                    else:
                        # Agent correctly responded in French
                        if ctx.user_language != "fr":
                            ctx.response_text = await translation_service.translate_from_french(
                                ctx.response_text,
                                ctx.user_language
                            )
                            log.info(f"✅ Response translated from French to {ctx.user_language}")
                        else:
                            log.debug(f"ℹ️ No translation needed - user language is French")
                else:
                    # Short response, assume French and translate
                    if ctx.user_language != "fr":
                        ctx.response_text = await translation_service.translate_from_french(
                            ctx.response_text,
                            ctx.user_language
                        )
                        log.info(f"✅ Response translated to {ctx.user_language}")
                    else:
                        log.debug(f"ℹ️ No translation needed - user language is French")

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _persist_messages(self, ctx: MessageContext) -> None:
        """Stage 9: Save inbound and outbound messages to database."""
        try:
            # Save inbound message
            await supabase_client.save_message(
                user_id=ctx.user_id,
                message_text=ctx.message_body,
                original_language=ctx.user_language,
                direction="inbound",
                message_sid=ctx.message_sid,
                media_url=ctx.media_url,
                message_type="audio" if ctx.media_type and 'audio' in ctx.media_type else "text",
                session_id=ctx.session_id
            )

            # Save outbound message
            await supabase_client.save_message(
                user_id=ctx.user_id,
                message_text=ctx.response_text,
                original_language=ctx.user_language,
                direction="outbound",
                session_id=ctx.session_id,
                is_escalation=ctx.escalation
            )

            log.info(f"✅ Messages persisted")

        except Exception as e:
            log.error(f"Failed to persist messages: {e}")
            # Don't fail the whole pipeline if persistence fails


# Global pipeline instance
message_pipeline = MessagePipeline()
