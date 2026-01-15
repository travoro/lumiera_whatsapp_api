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
    recent_messages: list = field(default_factory=list)  # Last 3 messages for intent context
    intent: Optional[str] = None
    confidence: Optional[float] = None
    response_text: Optional[str] = None
    escalation: bool = False
    tools_called: list = field(default_factory=list)
    tool_outputs: list = field(default_factory=list)  # Structured tool outputs (for short-term memory)

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

    def _normalize_language_code(self, language: str) -> str:
        """Normalize language code to ISO 639-1 format.

        Handles both ISO codes (fr, en, es) and full names (french, english, spanish).
        """
        if not language:
            return "fr"

        language = language.lower().strip()

        # Map full language names to ISO codes
        language_map = {
            "french": "fr",
            "english": "en",
            "spanish": "es",
            "portuguese": "pt",
            "romanian": "ro",
            "arabic": "ar",
            "german": "de",
            "italian": "it"
        }

        # If it's a full name, convert to ISO code
        if language in language_map:
            return language_map[language]

        # If it's already an ISO code (2 chars), return as-is
        if len(language) == 2:
            return language

        # Default to French
        return "fr"

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

            # Return final response (including detected language and response metadata!)
            response_data = {
                "message": ctx.response_text,
                "escalation": ctx.escalation,
                "tools_called": ctx.tools_called,
                "session_id": ctx.session_id,
                "intent": ctx.intent,
                "confidence": ctx.confidence,
                "detected_language": ctx.user_language  # Include detected language!
            }

            # Include response_type and list_type if present (from specialized agents)
            if hasattr(ctx, 'response_type') and ctx.response_type:
                response_data["response_type"] = ctx.response_type
                log.info(f"📦 Pipeline forwarding response_type: {ctx.response_type}")
            if hasattr(ctx, 'list_type') and ctx.list_type:
                response_data["list_type"] = ctx.list_type
                log.info(f"📦 Pipeline forwarding list_type: {ctx.list_type}")

            return Result.ok(response_data)

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
            # Normalize language code (handle both "fr" and "french" formats)
            raw_language = user.get('language', 'fr')
            ctx.user_language = self._normalize_language_code(raw_language)

            log.info(f"✅ User authenticated: {ctx.user_id} ({ctx.user_name})")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _manage_session(self, ctx: MessageContext) -> Result[None]:
        """Stage 2: Get or create conversation session and load conversation context."""
        try:
            session = await session_service.get_or_create_session(ctx.user_id)
            if session:
                ctx.session_id = session['id']
                log.info(f"✅ Session: {ctx.session_id}")

                # Load conversation context for intent classification
                try:
                    messages = await supabase_client.get_messages_by_session(
                        ctx.session_id,
                        fields='content,direction,created_at'
                    )

                    # Sort messages by created_at (oldest to newest)
                    sorted_messages = sorted(
                        messages,
                        key=lambda x: x.get('created_at', '')
                    )

                    # Get last 3 messages for intent context
                    if sorted_messages:
                        ctx.recent_messages = sorted_messages[-3:]
                        log.info(f"📜 Loaded {len(ctx.recent_messages)} recent messages for intent context")

                    # Find the last outbound message (from bot to user) for menu context
                    outbound_messages = [
                        msg for msg in sorted_messages
                        if msg.get('direction') == 'outbound'
                    ]
                    if outbound_messages:
                        ctx.last_bot_message = outbound_messages[-1].get('content')
                        log.info(f"📜 Last bot message: '{ctx.last_bot_message[:50]}...' " if ctx.last_bot_message and len(ctx.last_bot_message) > 50 else f"📜 Last bot message: '{ctx.last_bot_message}'")

                except Exception as e:
                    # Don't fail the pipeline if we can't load messages
                    log.warning(f"Could not load conversation context: {e}")
                    ctx.last_bot_message = None
                    ctx.recent_messages = []

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
        """Stage 6: Classify user intent with conversation context."""
        try:
            intent_result = await intent_classifier.classify(
                ctx.message_in_french,
                ctx.user_id,
                last_bot_message=ctx.last_bot_message,  # Pass for menu context
                conversation_history=ctx.recent_messages  # Pass last 3 messages for better context
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

                # Load last bot message's tool_outputs for resolving numeric selections
                last_tool_outputs = []
                last_bot_message = None
                try:
                    messages = await supabase_client.get_messages_by_session(
                        ctx.session_id,
                        fields='content,direction,metadata'
                    )
                    log.debug(f"📨 Loaded {len(messages)} messages from session")

                    # Find the most recent outbound message (only check last 5 messages)
                    recent_messages = messages[-5:] if len(messages) > 5 else messages
                    for msg in reversed(recent_messages):
                        if msg and msg.get('direction') == 'outbound':
                            last_bot_message = msg.get('content', '')
                            metadata = msg.get('metadata', {})
                            last_tool_outputs = metadata.get('tool_outputs', []) if metadata else []

                            if last_tool_outputs:
                                log.info(f"📦 Loaded {len(last_tool_outputs)} tool outputs from last bot message")
                                log.debug(f"📋 Tool outputs: {[t.get('tool') for t in last_tool_outputs]}")
                            else:
                                log.debug(f"📭 Last bot message has no tool_outputs in metadata")
                            break
                except Exception as e:
                    log.warning(f"⚠️ Could not load last message tool_outputs: {e}")

                # Try fast path through router
                from src.services.handlers import execute_direct_handler

                result = await execute_direct_handler(
                    intent=ctx.intent,
                    user_id=ctx.user_id,
                    phone_number=ctx.from_number,
                    user_name=ctx.user_name,
                    language=ctx.user_language,
                    message_text=ctx.message_in_french,  # Pass message for project name extraction
                    session_id=ctx.session_id,  # Pass session for context queries
                    last_tool_outputs=last_tool_outputs,  # For resolving numeric selections
                    last_bot_message=last_bot_message  # For menu context
                )

                if result:
                    ctx.response_text = result.get("message")
                    ctx.escalation = result.get("escalation", False)
                    ctx.tools_called = result.get("tools_called", [])
                    ctx.tool_outputs = result.get("tool_outputs", [])  # Capture tool outputs from fast path
                    log.info(f"✅ Fast path succeeded (captured {len(ctx.tool_outputs)} tool outputs)")
                    return Result.ok(None)
                else:
                    log.warning(f"❌ Fast path returned None - checking for specialized routing")

                    # Check for specialized routing in message.py before falling back to Opus
                    from src.handlers.message import handle_direct_action

                    specialized_result = await handle_direct_action(
                        action=ctx.intent,
                        user_id=ctx.user_id,
                        phone_number=ctx.from_number,
                        language=ctx.user_language,
                        message_body=ctx.message_in_french,
                        media_url=ctx.media_url,
                        media_type=ctx.media_type
                    )

                    if specialized_result:
                        log.info(f"✅ Specialized routing succeeded for intent: {ctx.intent}")
                        ctx.response_text = specialized_result.get("message")
                        ctx.escalation = specialized_result.get("escalation", False)
                        ctx.tools_called = specialized_result.get("tools_called", [])
                        ctx.tool_outputs = specialized_result.get("tool_outputs", [])
                        ctx.agent_used = specialized_result.get("agent_used")
                        ctx.response_type = specialized_result.get("response_type")  # For formatting decisions
                        ctx.list_type = specialized_result.get("list_type")  # For interactive lists
                        return Result.ok(None)
                    else:
                        log.warning(f"❌ No specialized routing found - parameters unclear")
                        log.info(f"🤖 Falling back to full AI agent to resolve ambiguity")
                        log.info(f"   Intent: {ctx.intent}")
                        log.info(f"   Message: '{ctx.message_in_french}'")
                        log.info(f"   AI will use conversation history to understand user intent")

            # Fallback to full agent
            log.info(f"⚙️ Using full agent (Opus)")

            # LAYER 1: Build AUTHORITATIVE explicit state
            from src.services.agent_state import agent_state_builder
            agent_state = await agent_state_builder.build_state(
                user_id=ctx.user_id,
                language=ctx.user_language,
                session_id=ctx.session_id
            )
            state_context = agent_state.to_prompt_context()
            if agent_state.has_active_context():
                log.info(f"📍 Injecting explicit state: project={agent_state.active_project_id}, task={agent_state.active_task_id}")

            # LAYER 2: Load chat history with tool outputs (for short-term memory)
            chat_history = []
            try:
                from langchain_core.messages import HumanMessage, AIMessage
                import json

                # Load messages WITH metadata
                messages = await supabase_client.get_messages_by_session(
                    ctx.session_id,
                    fields='content,direction,metadata,created_at'
                )

                # Convert to LangChain message format (last 10 messages for context)
                # BUT only include tool outputs from the LAST 1-3 turns (prevent bloat!)
                messages_for_history = messages[-10:] if messages else []

                # Find how many recent turns have tool outputs
                recent_tool_turns = 0
                for msg in reversed(messages_for_history):
                    if not msg or not isinstance(msg, dict):
                        continue
                    # Handle case where metadata is explicitly None in database
                    metadata = msg.get('metadata') or {}
                    if msg.get('direction') == 'outbound' and metadata.get('tool_outputs'):
                        recent_tool_turns += 1
                        if recent_tool_turns >= 3:  # MAX 3 turns with tool outputs
                            break

                for idx, msg in enumerate(messages_for_history):
                    try:
                        # Safety check: skip None messages
                        if not msg:
                            log.debug(f"⚠️ Skipping None message at index {idx}")
                            continue

                        # Validate message structure (must be a dict)
                        if not isinstance(msg, dict):
                            log.warning(f"⚠️ Invalid message type at index {idx}: {type(msg)}")
                            continue

                        # Validate required fields
                        direction = msg.get('direction')
                        if not direction:
                            log.warning(f"⚠️ Message missing 'direction' field at index {idx}")
                            continue

                        if direction == 'inbound':
                            chat_history.append(HumanMessage(content=msg.get('content', '')))

                        elif direction == 'outbound':
                            content = msg.get('content', '')

                            # Check if this message has tool outputs AND is within last 3 tool-using turns
                            metadata = msg.get('metadata', {})
                            if metadata is None:
                                metadata = {}

                            tool_outputs = metadata.get('tool_outputs', []) if isinstance(metadata, dict) else []

                            # Only append tool outputs if from recent turns (prevent token bloat!)
                            is_recent_enough = (len(messages_for_history) - idx) <= (recent_tool_turns if recent_tool_turns <= 3 else 3)

                            if tool_outputs and is_recent_enough:
                                # Append structured data for agent reference (compact format)
                                tool_context = "\n[Données précédentes:"
                                for tool_output in tool_outputs:
                                    if not isinstance(tool_output, dict):
                                        log.debug(f"⚠️ Skipping non-dict tool_output: {type(tool_output)}")
                                        continue

                                    tool_name = tool_output.get('tool', 'unknown')
                                    output_data = tool_output.get('output')

                                    # Only include essential structured data (not full details)
                                    if tool_name == 'list_projects_tool' and isinstance(output_data, list):
                                        # Extract just IDs and names
                                        projects_compact = [
                                            {"id": p.get("id"), "nom": p.get("nom")}
                                            for p in output_data if isinstance(p, dict)
                                        ]
                                        if projects_compact:
                                            tool_context += f"\nProjets: {json.dumps(projects_compact, ensure_ascii=False)}"

                                    elif tool_name == 'list_tasks_tool' and isinstance(output_data, list):
                                        # Extract just IDs and titles
                                        tasks_compact = [
                                            {"id": t.get("id"), "title": t.get("title")}
                                            for t in output_data if isinstance(t, dict)
                                        ]
                                        if tasks_compact:
                                            tool_context += f"\nTâches: {json.dumps(tasks_compact, ensure_ascii=False)}"

                                    elif tool_name == 'list_documents_tool' and isinstance(output_data, list):
                                        # Extract just IDs and names
                                        docs_compact = [
                                            {"id": d.get("id"), "name": d.get("name"), "type": d.get("type")}
                                            for d in output_data if isinstance(d, dict)
                                        ]
                                        if docs_compact:
                                            tool_context += f"\nDocuments: {json.dumps(docs_compact, ensure_ascii=False)}"

                                tool_context += "]"
                                content += tool_context

                            chat_history.append(AIMessage(content=content))

                    except Exception as msg_error:
                        # Log error but continue processing other messages (graceful degradation)
                        log.warning(f"⚠️ Error processing message at index {idx}: {msg_error}")
                        log.debug(f"   Problematic message: {msg}")
                        continue

                log.info(f"📜 Loaded {len(chat_history)} messages for agent context")
                log.debug(f"   Chat history has {len([m for m in chat_history if isinstance(m, HumanMessage)])} user messages")
                log.debug(f"   Chat history has {len([m for m in chat_history if isinstance(m, AIMessage)])} AI messages")
            except Exception as e:
                log.warning(f"Could not load chat history for agent: {e}")
                log.exception(e)  # Full stack trace for debugging
                log.debug(f"   Session ID: {ctx.session_id}")
                log.debug(f"   Messages loaded: {len(messages) if 'messages' in locals() else 'N/A'}")
                chat_history = []

            log.info(f"🤖 Invoking full AI agent with conversation context")
            log.debug(f"   User message: '{ctx.message_in_french}'")
            log.debug(f"   Chat history: {len(chat_history)} messages")
            log.debug(f"   Explicit state: {state_context if state_context else 'None'}")

            agent_result = await lumiera_agent.process_message(
                user_id=ctx.user_id,
                phone_number=ctx.from_number,
                user_name=ctx.user_name,
                language=ctx.user_language,
                message_text=ctx.message_in_french,
                chat_history=chat_history,
                state_context=state_context  # NEW: Inject explicit state
            )

            ctx.response_text = agent_result.get("message")
            ctx.escalation = agent_result.get("escalation", False)
            ctx.tools_called = agent_result.get("tools_called", [])

            log.info(f"✅ AI agent completed")
            log.debug(f"   Response length: {len(ctx.response_text) if ctx.response_text else 0} chars")
            log.debug(f"   Tools called: {ctx.tools_called}")
            log.debug(f"   Escalation: {ctx.escalation}")
            ctx.tool_outputs = agent_result.get("tool_outputs", [])  # NEW: Store for persistence

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

            # Build metadata for outbound message
            outbound_metadata = {}

            # Add escalation metadata if applicable (handled by save_message)
            # Add tool outputs metadata if any (for short-term memory)
            if ctx.tool_outputs:
                outbound_metadata["tool_outputs"] = ctx.tool_outputs
                log.debug(f"💾 Storing {len(ctx.tool_outputs)} tool outputs in message metadata")

            # Save outbound message with metadata
            await supabase_client.save_message(
                user_id=ctx.user_id,
                message_text=ctx.response_text,
                original_language=ctx.user_language,
                direction="outbound",
                session_id=ctx.session_id,
                is_escalation=ctx.escalation,
                metadata=outbound_metadata if outbound_metadata else None
            )

            log.info(f"✅ Messages persisted")

        except Exception as e:
            log.error(f"Failed to persist messages: {e}")
            # Don't fail the whole pipeline if persistence fails


# Global pipeline instance
message_pipeline = MessagePipeline()
