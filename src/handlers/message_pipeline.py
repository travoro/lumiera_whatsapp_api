"""Message processing pipeline - refactored from god function.

Breaks down message processing into discrete, testable stages.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, cast

from src.agent.agent import lumiera_agent
from src.exceptions import (
    AgentExecutionException,
    IntegrationException,
    LumieraException,
    UserNotFoundException,
)
from src.integrations.supabase import supabase_client
from src.services.intent import intent_classifier
from src.services.session import session_service
from src.services.transcription import transcription_service
from src.services.translation import translation_service
from src.utils.logger import log
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
    user: Optional[Dict[str, Any]] = None  # Full user object for handoff checks
    session_id: Optional[str] = None
    human_agent_active: bool = False  # Flag to skip bot processing
    skip_bot_processing: bool = False  # Set when human agent is active
    message_in_french: Optional[str] = None
    last_bot_message: Optional[str] = (
        None  # Last message sent by bot (for menu context)
    )
    recent_messages: list = field(
        default_factory=list
    )  # Last 3 messages for intent context
    intent: Optional[str] = None
    confidence: Optional[float] = None
    response_text: Optional[str] = None
    response_type: Optional[str] = None  # Type of response (text, list, buttons, etc.)
    list_type: Optional[str] = None  # Type of list if response is a list
    attachments: list = field(default_factory=list)  # Media attachments
    agent_used: bool = False  # Whether AI agent was used
    escalation: bool = False
    tools_called: list = field(default_factory=list)
    tool_outputs: list = field(
        default_factory=list
    )  # Structured tool outputs (for short-term memory)

    # FSM session context (for context preservation)
    active_session_id: Optional[str] = None
    fsm_state: Optional[str] = None
    fsm_current_step: Optional[str] = None
    fsm_task_id: Optional[str] = None
    expecting_response: bool = False
    last_bot_options: list = field(default_factory=list)
    should_continue_session: bool = False

    # Context classifier results (for session continuation)
    session_continuation: bool = False
    context_ambiguous: bool = False
    suggestion_context: Optional[Dict[str, Any]] = None
    stay_in_session: bool = False
    pending_action: Optional[Dict[str, Any]] = (
        None  # For interactive choices (issue_choice, etc.)
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "language": self.user_language,
            "session_id": self.session_id,
            "intent": self.intent,
            "confidence": self.confidence,
            "escalation": self.escalation,
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
            "italian": "it",
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
        interactive_data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,  # NEW: Accept session_id
    ) -> Result[Dict[str, Any]]:
        """Process message through pipeline stages.

        Args:
            from_number: User's WhatsApp number
            message_body: Message text
            message_sid: Twilio message SID
            media_url: Media URL if present
            media_type: Media MIME type
            interactive_data: Interactive button data
            session_id: Optional session_id to reuse (prevents duplicate creation)

        Returns:
            Result with response dict or error
        """
        ctx = MessageContext(
            from_number=from_number,
            message_body=message_body,
            message_sid=message_sid,
            media_url=media_url,
            media_type=media_type,
            interactive_data=interactive_data,
            session_id=session_id,  # NEW: Set from parameter to enable reuse
        )

        try:
            # Stage 1: Authenticate user
            result = await self._authenticate_user(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 1.5: Check if human agent has taken over
            result = await self._check_human_agent_handoff(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # If human agent is active, skip all bot processing
            if ctx.skip_bot_processing:
                log.info(
                    "✅ Message saved during human agent handoff - skipping bot processing"
                )
                return Result.ok(
                    {
                        "message": None,  # No bot response
                        "escalation": False,
                        "tools_called": [],
                        "session_id": None,
                        "intent": None,
                        "confidence": 0.0,
                        "detected_language": ctx.user_language or "fr",
                        "human_agent_active": True,
                        "saved_only": True,
                    }
                )

            # Stage 2: Get or create session
            result = await self._manage_session(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 3: Detect language
            result = await self._detect_language(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 4: Process media (download ALL media + transcribe audio)
            if ctx.media_url and ctx.media_type:
                # First, download and store ALL media types permanently
                result = await self._download_and_store_media(ctx)
                if not result.success:
                    return result  # type: ignore[return-value]

                # Then do specific processing (transcription for audio)
                if "audio" in ctx.media_type:
                    result = await self._process_audio(ctx)
                    if not result.success:
                        return result  # type: ignore[return-value]

            # Stage 5: Translate to French (internal language)
            result = await self._translate_to_french(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 5.5: Check for active session (FSM context preservation)
            result = await self._check_active_session(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 6: Classify intent (now with FSM context)
            result = await self._classify_intent(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 7: Route to handler
            result = await self._route_message(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

            # Stage 8: Translate response back to user language
            result = await self._translate_response(ctx)
            if not result.success:
                return result  # type: ignore[return-value]

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
                "detected_language": ctx.user_language,  # Include detected language!
            }

            # Include response_type and list_type if present (from specialized agents)
            if hasattr(ctx, "response_type") and ctx.response_type:
                response_data["response_type"] = ctx.response_type
                log.info(f"📦 Pipeline forwarding response_type: {ctx.response_type}")
            if hasattr(ctx, "list_type") and ctx.list_type:
                response_data["list_type"] = ctx.list_type
                log.info(f"📦 Pipeline forwarding list_type: {ctx.list_type}")

            # Include attachments if present (for task images/files)
            if hasattr(ctx, "attachments") and ctx.attachments:
                response_data["attachments"] = ctx.attachments
                log.info(f"📦 Pipeline forwarding {len(ctx.attachments)} attachments")

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

            ctx.user = user  # Store full user object for handoff checks
            ctx.user_id = user["id"]
            ctx.user_name = user.get("contact_prenom") or user.get("contact_name", "")
            # Normalize language code (handle both "fr" and "french" formats)
            raw_language = user.get("language", "fr")
            ctx.user_language = self._normalize_language_code(raw_language)

            log.info(f"✅ User authenticated: {ctx.user_id} ({ctx.user_name})")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _check_human_agent_handoff(self, ctx: MessageContext) -> Result[None]:
        """Stage 1.5: Check if human agent has taken over conversation.

        If human_agent_active is true and not expired:
        - Save user message with metadata
        - Skip all bot processing (no LLM, no handlers, no response)
        - Return success to end pipeline early

        If expired:
        - Clear handoff flag
        - Continue normal processing
        """
        try:
            # Check handoff status from user object (loaded in Stage 1)
            human_agent_active = ctx.user.get("human_agent_active", False)

            if not human_agent_active:
                # Normal flow - continue to session management
                return Result.ok(None)

            # Check expiration
            expires_at_str = ctx.user.get("human_agent_expires_at")
            if not expires_at_str:
                # Flag is true but no expiration set - shouldn't happen, clear it
                log.warning(
                    f"⚠️ human_agent_active=true but no expires_at for user {ctx.user_id[:8]}... - clearing flag"
                )
                await self._clear_human_agent_handoff(ctx.user_id)
                return Result.ok(None)

            # Parse expiration timestamp
            from datetime import datetime, timezone

            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)

            # Check if expired
            if now >= expires_at:
                # Expired - clear flag and resume normal processing
                log.info(
                    f"🕐 Human agent handoff expired for user {ctx.user_id[:8]}... - resuming bot"
                )
                await self._clear_human_agent_handoff(ctx.user_id)
                return Result.ok(None)

            # Still active - save message only, skip bot processing
            agent_since = ctx.user.get("human_agent_since")
            time_remaining = (expires_at - now).total_seconds() / 3600  # hours
            log.info(
                f"🧑 Human agent active for user {ctx.user_id[:8]}... "
                f"(since: {agent_since}, expires in: {time_remaining:.1f}h) - saving message only"
            )

            # Save inbound message with metadata
            await self._save_human_agent_message(ctx)

            # Set flags to skip all bot processing
            ctx.human_agent_active = True
            ctx.skip_bot_processing = True

            # Return success - pipeline will check these flags and skip stages
            return Result.ok(None)

        except Exception as e:
            log.error(f"Error checking human agent handoff: {e}")
            # On error, continue normal flow to avoid blocking user
            return Result.ok(None)

    async def _clear_human_agent_handoff(self, user_id: str) -> None:
        """Clear human agent handoff flag in database."""
        try:
            supabase_client.client.table("subcontractors").update(
                {
                    "human_agent_active": False,
                    "human_agent_since": None,
                    "human_agent_expires_at": None,
                }
            ).eq("id", user_id).execute()

            log.info(f"✅ Cleared human agent handoff for user {user_id[:8]}...")

        except Exception as e:
            log.error(f"Error clearing human agent handoff: {e}")

    async def _save_human_agent_message(self, ctx: MessageContext) -> None:
        """Save user message during human agent handoff (no bot response)."""
        try:
            # Download and store ANY media if present (even during handoff)
            if ctx.media_url and ctx.media_type:
                # Determine media type for logging
                media_icon = "📎"
                if "image" in ctx.media_type:
                    media_icon = "📸"
                elif "audio" in ctx.media_type:
                    media_icon = "🎵"
                elif "video" in ctx.media_type:
                    media_icon = "🎬"
                elif "application" in ctx.media_type:
                    media_icon = "📄"

                log.info(
                    f"{media_icon} Human agent handoff: Processing {ctx.media_type} before saving"
                )
                log.info(f"   🔗 Original URL: {ctx.media_url[:80]}...")

                storage_url = await self._download_and_store_media_file(
                    media_url=ctx.media_url,
                    user_id=ctx.user_id,
                    message_sid=ctx.message_sid or "unknown",
                    content_type=ctx.media_type,
                )

                if storage_url:
                    ctx.media_url = storage_url
                    log.info(f"   ✅ Media stored: {storage_url[:80]}...")
                else:
                    log.warning(
                        "   ⚠️ Media storage failed - using original URL (may expire)"
                    )

            metadata = {
                "human_agent_active": True,
                "bot_processing_skipped": True,
                "saved_only": True,
            }

            await supabase_client.save_message(
                user_id=ctx.user_id,
                message_text=ctx.message_body or "",
                original_language=ctx.user_language or "fr",
                direction="inbound",
                media_url=ctx.media_url,
                media_type=ctx.media_type,
                metadata=metadata,
                session_id=ctx.session_id,
            )

            log.info("💾 Saved user message during human agent handoff")
            if ctx.media_url:
                url_type = (
                    "Supabase" if "supabase" in ctx.media_url.lower() else "Twilio"
                )
                log.info(f"   📎 Media URL saved ({url_type}): {ctx.media_url[:80]}...")

        except Exception as e:
            log.error(f"Error saving human agent message: {e}")

    async def _manage_session(self, ctx: MessageContext) -> Result[None]:
        """Stage 2: Get or create session and load conversation context."""
        try:
            # NEW: Reuse session_id if already set (from earlier in request)
            if ctx.session_id:
                log.debug(f"✅ Reusing existing session_id: {ctx.session_id}")
                session = await supabase_client.get_session_by_id(ctx.session_id)
                if session:
                    log.info(f"✅ Session: {ctx.session_id} (reused)")
                else:
                    log.warning(
                        f"⚠️ Session {ctx.session_id} not found, creating new one"
                    )
                    ctx.session_id = None  # Reset to trigger new creation below

            # Only call get_or_create if no session yet
            if not ctx.session_id:
                session = await session_service.get_or_create_session(ctx.user_id)
                if session:
                    ctx.session_id = session["id"]
                    log.info(f"✅ Session: {ctx.session_id}")
                else:
                    raise AgentExecutionException(stage="session_management")

            # Load conversation context for intent classification
            # (happens regardless of reuse/create)
            try:
                messages = await supabase_client.get_messages_by_session(
                    ctx.session_id, fields="content,direction,created_at"
                )

                # Sort messages by created_at (oldest to newest)
                sorted_messages = sorted(
                    messages, key=lambda x: x.get("created_at", "")
                )

                # Get last 3 messages for intent context
                if sorted_messages:
                    ctx.recent_messages = sorted_messages[-3:]
                    log.info(
                        f"📜 Loaded {len(ctx.recent_messages)} recent messages "
                        f"for intent context"
                    )

                # Find the last outbound message (from bot to user) for menu context
                outbound_messages = [
                    msg for msg in sorted_messages if msg.get("direction") == "outbound"
                ]
                if outbound_messages:
                    ctx.last_bot_message = outbound_messages[-1].get("content")
                    log.info(
                        f"📜 Last bot message: '{ctx.last_bot_message[:50]}...' "
                        if ctx.last_bot_message and len(ctx.last_bot_message) > 50
                        else f"📜 Last bot message: '{ctx.last_bot_message}'"
                    )

            except Exception as e:
                # Don't fail the pipeline if we can't load messages
                log.warning(f"Could not load conversation context: {e}")
                ctx.last_bot_message = None
                ctx.recent_messages = []

            return Result.ok(None)

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
                    from src.services.language_detection import (
                        language_detection_service,
                    )

                    # Log detection attempt with message preview
                    message_preview = (
                        ctx.message_body[:50] + "..."
                        if len(ctx.message_body) > 50
                        else ctx.message_body
                    )
                    log.info(
                        f"🔍 Detecting language for message: '{message_preview}' "
                        f"(profile: {profile_language})"
                    )

                    detected_language, detection_method = (
                        await language_detection_service.detect_async(
                            ctx.message_body, fallback_language=profile_language
                        )
                    )

                    # Check if detection succeeded (not fallback)
                    if detection_method != "fallback":
                        if detected_language != profile_language:
                            from src.config import settings

                            # Check if we should update the profile based on policy
                            should_update_profile = False
                            update_blocked_reason = None

                            # Check greeting exception policy
                            message_lower = ctx.message_body.strip().lower()
                            is_greeting_exception = (
                                message_lower
                                in settings.language_greeting_exceptions_list
                            )

                            if is_greeting_exception:
                                update_blocked_reason = (
                                    f"greeting exception ('{message_lower}')"
                                )
                            elif (
                                len(ctx.message_body.strip())
                                < settings.language_update_min_message_length
                            ):
                                update_blocked_reason = f"message too short ({
                                    len(
                                        ctx.message_body.strip())} chars < {
                                    settings.language_update_min_message_length})"
                            elif not settings.auto_update_user_language:
                                update_blocked_reason = (
                                    "auto-update disabled in settings"
                                )
                            else:
                                should_update_profile = True

                            if should_update_profile:
                                log.info(
                                    f"🌍 Language detected: {detected_language} "
                                    f"(method: {detection_method}, "
                                    f"profile: {profile_language}) "
                                    "→ Profile will be updated"
                                )

                                # Update user profile language permanently
                                update_success = (
                                    await supabase_client.update_user_language(
                                        ctx.user_id, detected_language
                                    )
                                )

                                if update_success:
                                    log.info(
                                        "✅ User profile language updated: "
                                        f"{profile_language} → {detected_language}"
                                    )
                                else:
                                    log.warning(
                                        f"⚠️ Failed to update profile language "
                                        f"for user {ctx.user_id}"
                                    )
                            else:
                                log.info(
                                    f"🌍 Language detected: {detected_language} "
                                    f"(method: {detection_method}, "
                                    f"profile: {profile_language}) "
                                    f"→ Profile update BLOCKED: {update_blocked_reason}"
                                )

                            # Use detected language for this message
                            # regardless of profile update
                            ctx.user_language = detected_language
                        else:
                            log.info(
                                f"✅ Language detected: {detected_language} "
                                f"(method: {detection_method}) → Matches profile, "
                                f"no update needed"
                            )
                    else:
                        # Fallback method means no confident detection
                        log.info(
                            f"⚠️ Language detection fallback: "
                            f"Using profile language {profile_language} "
                            f"(method: {detection_method})"
                        )
                        ctx.user_language = profile_language

                except Exception as e:
                    log.warning(
                        f"❌ Language detection error: {e} → "
                        f"Using profile language: {profile_language}"
                    )
                    ctx.user_language = profile_language
            else:
                log.info(
                    f"⏩ Message too short for detection → "
                    f"Using profile language: {profile_language}"
                )

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _download_and_store_media(self, ctx: MessageContext) -> Result[None]:
        """Stage 4: Download and store ALL media messages permanently.

        This stage:
        1. Downloads media from source URL (e.g., Twilio)
        2. Uploads to Supabase storage "conversations" bucket for permanent retention
        3. Updates ctx.media_url to point to stored file (not temporary Twilio URL)

        Handles: images, audio, video, documents, etc.
        """
        try:
            if not (ctx.media_url and ctx.media_type):
                log.info("   ⏭️  Skipping media download (no media)")
                return Result.ok(None)

            # Determine media type for logging
            media_icon = "📎"
            if "image" in ctx.media_type:
                media_icon = "📸"
            elif "audio" in ctx.media_type:
                media_icon = "🎵"
            elif "video" in ctx.media_type:
                media_icon = "🎬"
            elif "application" in ctx.media_type:
                media_icon = "📄"

            log.info(
                f"{media_icon} [STAGE 4] Processing {ctx.media_type} message (download + store)"
            )
            log.info(f"   🔗 Original URL: {ctx.media_url[:80]}...")
            log.info(f"   📋 Content-Type: {ctx.media_type}")

            # Download and store media
            storage_url = await self._download_and_store_media_file(
                media_url=ctx.media_url,
                user_id=ctx.user_id,
                message_sid=ctx.message_sid or "unknown",
                content_type=ctx.media_type,
            )

            if storage_url:
                # Update media URL to point to stored file (not Twilio URL)
                original_url = ctx.media_url
                ctx.media_url = storage_url
                log.info("✅ [STAGE 4] Media processed successfully")
                log.info(f"   📍 Stored URL: {storage_url}")
                log.info(
                    "   🔄 Context updated: ctx.media_url changed from Twilio to Supabase"
                )
            else:
                log.warning(
                    "⚠️ [STAGE 4] Media storage failed - using original URL (may expire)"
                )
                log.warning(f"   ⚠️  Will save Twilio URL: {ctx.media_url[:80]}...")

            return Result.ok(None)

        except Exception as e:
            log.error(f"❌ [STAGE 4] Error processing media: {e}")
            import traceback

            log.error(f"   Traceback: {traceback.format_exc()}")
            # Non-fatal: Continue with original URL if storage fails
            return Result.ok(None)

    async def _download_and_store_media_file(
        self,
        media_url: str,
        user_id: str,
        message_sid: str,
        content_type: str,
    ) -> Optional[str]:
        """Download ANY media file from Twilio and upload to Supabase storage.

        Handles images, audio, video, documents, etc.

        Args:
            media_url: Source media URL (e.g., Twilio media URL)
            user_id: User ID for folder organization
            message_sid: Message SID for unique filename
            content_type: Media content type (image/jpeg, audio/ogg, video/mp4, etc.)

        Returns:
            Public URL of stored media in Supabase, or None if failed
        """
        try:
            import uuid

            import httpx

            from src.config import settings

            log.info(f"📥 Downloading media from {media_url[:80]}...")

            # Check if this is a Twilio URL and add authentication
            auth = None
            if "api.twilio.com" in media_url:
                auth = (settings.twilio_account_sid, settings.twilio_auth_token)
                log.info("   🔐 Using Twilio authentication")

            # Download media from source (follow redirects as Twilio returns 307)
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(media_url, auth=auth)
                response.raise_for_status()

            media_data = response.content
            actual_content_type = response.headers.get("content-type", content_type)

            log.info(
                f"   ✅ Downloaded {len(media_data)} bytes ({len(media_data) / 1024:.2f} KB)"
            )

            # Determine file extension based on content type
            extension = ".bin"  # default fallback
            content_lower = actual_content_type.lower()

            # Images
            if "png" in content_lower:
                extension = ".png"
            elif "jpeg" in content_lower or "jpg" in content_lower:
                extension = ".jpg"
            elif "webp" in content_lower:
                extension = ".webp"
            elif "gif" in content_lower:
                extension = ".gif"
            # Audio
            elif "ogg" in content_lower:
                extension = ".ogg"
            elif "mpeg" in content_lower or "mp3" in content_lower:
                extension = ".mp3"
            elif "wav" in content_lower:
                extension = ".wav"
            elif "m4a" in content_lower:
                extension = ".m4a"
            elif "aac" in content_lower:
                extension = ".aac"
            # Video
            elif "mp4" in content_lower:
                extension = ".mp4"
            elif "webm" in content_lower:
                extension = ".webm"
            elif "avi" in content_lower:
                extension = ".avi"
            elif "mov" in content_lower:
                extension = ".mov"
            # Documents
            elif "pdf" in content_lower:
                extension = ".pdf"
            elif "doc" in content_lower or "word" in content_lower:
                extension = ".docx"
            elif "xls" in content_lower or "excel" in content_lower:
                extension = ".xlsx"
            elif "ppt" in content_lower or "powerpoint" in content_lower:
                extension = ".pptx"
            elif "text/plain" in content_lower:
                extension = ".txt"

            # Generate filename: {user_id}/{message_sid}_{uuid}.ext
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{message_sid}_{unique_id}{extension}"
            storage_path = f"{user_id}/{filename}"

            log.info(
                f"   📤 Uploading to Supabase storage: conversations/{storage_path}"
            )

            # Upload to Supabase storage bucket "conversations"
            upload_response = supabase_client.client.storage.from_(
                "conversations"
            ).upload(
                storage_path,
                media_data,
                {"content-type": actual_content_type, "upsert": "false"},
            )

            # Get public URL
            public_url = supabase_client.client.storage.from_(
                "conversations"
            ).get_public_url(storage_path)

            log.info(f"   ✅ Media uploaded successfully: {public_url}")
            return public_url

        except httpx.HTTPStatusError as e:
            log.error(f"   ❌ HTTP error downloading media: {e.response.status_code}")
            return None
        except Exception as e:
            log.error(f"   ❌ Error downloading/uploading media: {e}")
            import traceback

            log.error(f"   Traceback: {traceback.format_exc()}")
            return None

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
            if not (ctx.media_url and ctx.media_type and "audio" in ctx.media_type):
                return Result.ok(None)  # Skip if not audio

            log.info("🎤 Processing audio message (transcribe + store)")

            # Download, store, and transcribe audio
            transcription, storage_url, whisper_detected_lang = (
                await transcription_service.transcribe_and_store_audio(
                    audio_url=ctx.media_url,
                    user_id=ctx.user_id,
                    message_sid=ctx.message_sid or "unknown",
                    target_language=ctx.user_language,
                    content_type=ctx.media_type,
                )
            )

            if not transcription:
                raise IntegrationException(service="Whisper", operation="transcription")

            # Update context with transcription
            ctx.message_body = transcription
            log.info(f"✅ Audio transcribed: {transcription[:50]}...")
            log.info(
                f"🔍 TRACE: Language from transcription service: {whisper_detected_lang}"
            )
            log.info(
                f"🔍 TRACE: Current context language (profile): {ctx.user_language}"
            )

            # Use detected language from transcribed text (already ISO 639-1 code)
            if whisper_detected_lang:
                if whisper_detected_lang != ctx.user_language:
                    log.info(
                        f"🌍 Audio language detected: {whisper_detected_lang} "
                        f"(differs from profile: {ctx.user_language})"
                    )

                    # Update user profile language permanently
                    update_success = await supabase_client.update_user_language(
                        ctx.user_id, whisper_detected_lang
                    )

                    if update_success:
                        log.info(
                            "✅ User profile language updated: "
                            f"{ctx.user_language} → {whisper_detected_lang}"
                        )
                    else:
                        log.warning(
                            f"⚠️ Failed to update profile language "
                            f"for user {ctx.user_id}"
                        )

                    # Use detected language for this message
                    ctx.user_language = whisper_detected_lang
                    log.info(
                        f"🔍 TRACE: Context language UPDATED to: "
                        f"{ctx.user_language}"
                    )
                else:
                    log.info(
                        f"✅ Detected language: {whisper_detected_lang} "
                        f"(matches profile)"
                    )
                    log.info(
                        f"🔍 TRACE: Context language UNCHANGED: " f"{ctx.user_language}"
                    )
            else:
                log.info(
                    "⚠️ No confident language detection from audio, "
                    "keeping profile language"
                )
                log.info(
                    f"🔍 TRACE: Context language UNCHANGED (no detection): "
                    f"{ctx.user_language}"
                )

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
                    ctx.message_body, ctx.user_language
                )
                log.info(f"✅ Translated to French: {ctx.message_in_french[:50]}...")
            else:
                ctx.message_in_french = ctx.message_body

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _check_active_session(self, ctx: MessageContext) -> Result[None]:
        """Stage 5.5: Check for active progress update session.

        Checks if user has active progress update session for context preservation.
        """
        try:
            # Query for active progress update session
            result = (
                supabase_client.client.table("progress_update_sessions")
                .select("*")
                .eq("subcontractor_id", ctx.user_id)
                .gt("expires_at", "now()")
                .order("last_activity", desc=True)
                .limit(1)
                .execute()
            )

            if result.data and len(result.data) > 0:
                session = cast(Dict[str, Any], result.data[0])

                # Extract FSM context
                ctx.active_session_id = session["id"]
                ctx.fsm_state = session.get("fsm_state", "idle")
                ctx.fsm_current_step = session.get("current_step")
                ctx.fsm_task_id = session.get("task_id")

                # Check if bot is expecting a response (from session_metadata)
                metadata = session.get("session_metadata", {})
                if isinstance(metadata, dict):
                    ctx.expecting_response = metadata.get("expecting_response", False)
                    ctx.last_bot_options = metadata.get("available_actions", [])

                # Calculate session age to determine if we should continue
                from datetime import datetime, timezone

                last_activity_str = session.get("last_activity")
                if last_activity_str:
                    try:
                        # Parse last_activity timestamp
                        last_activity = datetime.fromisoformat(
                            last_activity_str.replace("Z", "+00:00")
                        )

                        # Ensure both datetimes are timezone-aware
                        # for accurate comparison
                        if last_activity.tzinfo is None:
                            # Treat naive datetime as UTC
                            last_activity = last_activity.replace(tzinfo=timezone.utc)

                        # Get current time in UTC
                        now = datetime.now(timezone.utc)
                        age_seconds = (now - last_activity).total_seconds()

                        log.info(
                            f"🔄 Active session found: {ctx.active_session_id[:8]}..."
                        )
                        log.info(
                            f"   State: {ctx.fsm_state} | Step: {ctx.fsm_current_step}"
                        )
                        log.info(f"   Expecting response: {ctx.expecting_response}")
                        log.info(f"   Age: {age_seconds:.0f}s")

                        # If expecting response and recent activity (< 5 min = 300s)
                        if ctx.expecting_response and age_seconds < 300:
                            ctx.should_continue_session = True
                            log.info(
                                "   ✅ Should continue session "
                                "(recent activity, expecting response)"
                            )
                        else:
                            log.info(
                                "   💤 Session exists but not expecting response "
                                "or too old"
                            )
                    except Exception as e:
                        log.warning(f"⚠️ Error parsing last_activity timestamp: {e}")
                else:
                    log.info(
                        f"🔄 Active session found: {ctx.active_session_id[:8]}... "
                        f"(no last_activity)"
                    )
            else:
                log.info("💤 No active progress update session for user")

            # Check for active incident session if no progress update session
            if not ctx.active_session_id:
                from src.services.incident.state import incident_state

                incident_session = await incident_state.get_session(ctx.user_id)
                if incident_session:
                    ctx.active_session_id = incident_session.get("id")
                    ctx.fsm_state = incident_session.get("fsm_state")
                    ctx.fsm_current_step = incident_session.get("current_step")

                    # Check if bot is expecting a response
                    session_metadata = incident_session.get("session_metadata", {})
                    if isinstance(session_metadata, dict):
                        ctx.expecting_response = session_metadata.get(
                            "expecting_response", False
                        )
                        ctx.last_bot_options = session_metadata.get(
                            "available_actions", []
                        )

                    # Calculate session age
                    from datetime import datetime, timezone

                    last_activity_str = incident_session.get("last_activity")
                    if last_activity_str:
                        try:
                            last_activity = datetime.fromisoformat(
                                last_activity_str.replace("Z", "+00:00")
                            )
                            if last_activity.tzinfo is None:
                                last_activity = last_activity.replace(
                                    tzinfo=timezone.utc
                                )

                            now = datetime.now(timezone.utc)
                            age_seconds = (now - last_activity).total_seconds()

                            log.info(
                                f"🔄 Active INCIDENT session found: {ctx.active_session_id[:8]}..."
                            )
                            log.info(
                                f"   State: {ctx.fsm_state} | Step: {ctx.fsm_current_step}"
                            )
                            log.info(f"   Expecting response: {ctx.expecting_response}")
                            log.info(f"   Age: {age_seconds:.0f}s")

                            # If expecting response and recent activity (< 5 min)
                            if ctx.expecting_response and age_seconds < 300:
                                ctx.should_continue_session = True
                                log.info(
                                    "   ✅ Should continue incident session "
                                    "(recent activity, expecting response)"
                                )
                            else:
                                log.info(
                                    "   💤 Incident session exists but not expecting response "
                                    "or too old"
                                )
                        except Exception as e:
                            log.warning(
                                f"⚠️ Error parsing last_activity timestamp: {e}"
                            )
                    else:
                        log.info(
                            f"🔄 Active INCIDENT session found: {ctx.active_session_id[:8]}... "
                            f"(no last_activity)"
                        )
                else:
                    log.info("💤 No active incident session for user")

            return Result.ok(None)

        except Exception as e:
            # Non-fatal: FSM is optional enhancement for context preservation
            log.warning(f"⚠️ Error checking active session: {e}")
            return Result.ok(None)

    async def _get_active_specialized_session(
        self, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get active specialized session for user.

        Checks progress_update_sessions and incident_sessions tables for active session.
        Priority order: progress_update > incident (both shouldn't exist simultaneously).

        Returns:
            Dict with session info or None if no active session
        """
        try:
            log.debug(
                f"🔍 Checking for active specialized session for user {user_id[:8]}..."
            )

            # Check for progress_update session first (higher priority)
            from src.services.progress_update import progress_update_state

            progress_session = await progress_update_state.get_session(user_id)

            if progress_session:
                session_info = {
                    "id": progress_session["id"],
                    "type": "progress_update",
                    "primary_intent": "update_progress",
                    "task_id": progress_session.get("task_id"),
                    "project_id": progress_session.get("project_id"),
                    "fsm_state": progress_session.get("fsm_state"),
                    "expecting_response": (
                        progress_session.get("session_metadata", {}).get(
                            "expecting_response", False
                        )
                    ),
                }
                log.info(
                    f"✅ Active session found: {session_info['type']} "
                    f"(state: {session_info['fsm_state']}, "
                    f"expecting_response: {session_info['expecting_response']})"
                )
                return session_info

            # Check for incident session
            from src.services.incident.state import incident_state

            incident_session = await incident_state.get_session(user_id)

            if incident_session:
                session_info = {
                    "id": incident_session["id"],
                    "type": "incident",
                    "primary_intent": "report_incident",
                    "incident_id": incident_session.get("incident_id"),
                    "project_id": incident_session.get("project_id"),
                    "fsm_state": incident_session.get("fsm_state"),
                    "expecting_response": (
                        incident_session.get("session_metadata", {}).get(
                            "expecting_response", False
                        )
                    ),
                }
                log.info(
                    f"✅ Active session found: {session_info['type']} "
                    f"(state: {session_info['fsm_state']}, "
                    f"expecting_response: {session_info['expecting_response']})"
                )
                return session_info

            log.debug(f"ℹ️ No active session found for user {user_id[:8]}...")
            return None
        except Exception as e:
            log.warning(f"⚠️ Error getting active specialized session: {e}")
            return None

    async def _exit_specialized_session(
        self,
        user_id: str,
        session_id: str,
        session_type: str,
        reason: str,
    ):
        """Exit specialized session with cleanup.

        Args:
            user_id: User ID
            session_id: Session ID to exit
            session_type: Type of session ("progress_update", "incident", etc.)
            reason: Reason for exit (for logging)
        """
        log.info(f"🚪 Exiting {session_type} session: {session_id[:8]}...")
        log.info(f"   Reason: {reason}")

        if session_type == "progress_update":
            from src.services.progress_update import progress_update_state

            await progress_update_state.clear_session(user_id, reason=reason)

        elif session_type == "incident":
            from src.services.incident.state import incident_state

            await incident_state.clear_session(user_id, reason=reason)

    async def _classify_intent(self, ctx: MessageContext) -> Result[None]:
        """Stage 6: Classify user intent with LLM-based context awareness.

        Uses context classifier when specialized session is active to determine
        if message continues session or represents intent change.
        """
        try:
            # Check for active specialized session
            active_session = await self._get_active_specialized_session(ctx.user_id)

            if not active_session:
                # No active session - clear any stale FSM context and use standard classification
                ctx.active_session_id = None
                ctx.fsm_state = None
                ctx.expecting_response = False
                ctx.should_continue_session = False
                return await self._standard_intent_classification(ctx)

            # === ACTIVE SESSION EXISTS ===

            log.info(f"📋 Active {active_session['type']} session found")
            log.info(f"   State: {active_session.get('fsm_state')}")
            log.info(
                f"   Expecting response: {active_session.get('expecting_response')}"
            )

            # Only use context classifier for SPECIFIC active states
            # where we're waiting for user input (e.g., collecting_data)
            #
            # DO NOT use for idle/menu states like "awaiting_action" where
            # user can send any new intent (greeting, help, etc.)
            #
            # Example: User is in progress_update session at "awaiting_action" state
            # (idle menu showing options). User sends "bonjour". We should:
            # 1. Exit the idle session
            # 2. Use standard classification → detects "greeting" intent
            # 3. Show greeting handler with quick reply options
            #
            # If we used context classifier here, it might keep session open
            # and trigger LLM response instead of fast greeting handler.

            fsm_state = active_session.get("fsm_state", "")

            # Define states where we should use context classifier
            ACTIVE_STATES_FOR_CONTEXT_CLASSIFICATION = [
                "collecting_data",  # Actively collecting photo/video/data
                "awaiting_action",  # Waiting for user to choose action (add photo, comment, complete, or exit)
                # Add more specific states here as needed
            ]

            # For idle/menu states, exit session and use standard classification
            if fsm_state not in ACTIVE_STATES_FOR_CONTEXT_CLASSIFICATION:
                log.info(
                    f"ℹ️ Session in idle/menu state '{fsm_state}' - "
                    "exiting session and using standard classification"
                )
                # Exit the idle session before classifying new intent
                await self._exit_specialized_session(
                    user_id=ctx.user_id,
                    session_id=active_session["id"],
                    session_type=active_session["type"],
                    reason="new_intent_at_idle_state",
                )

                # CRITICAL: Clear FSM context from ctx so intent classifier doesn't get biased
                ctx.active_session_id = None
                ctx.fsm_state = None
                ctx.expecting_response = False
                ctx.should_continue_session = False
                log.info(
                    "   🧹 Cleared FSM context from ctx - intent classifier will be unbiased"
                )

                return await self._standard_intent_classification(ctx)

            # === CONTINUE ACTIVE SESSION ===
            # We have an active session in a state that expects user response
            # Let the specialized agent handle the message - it will determine if
            # the message is in-context or if the user wants to do something else

            log.info("✅ Continuing active session - letting specialized agent handle")

            ctx.intent = active_session["primary_intent"]
            ctx.confidence = 0.95
            ctx.session_continuation = True

            log.info(f"✅ Staying in {ctx.intent} flow (agent will handle context)")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _standard_intent_classification(
        self, ctx: MessageContext
    ) -> Result[None]:
        """Standard intent classification without session context.

        Used when no active specialized session exists.
        """
        try:
            # Determine media context
            has_media = bool(ctx.media_url)
            media_type_simple = None
            num_media = 1 if has_media else 0

            if has_media and ctx.media_type:
                # Extract simple media type (image, video, audio)
                if "image" in ctx.media_type.lower():
                    media_type_simple = "image"
                elif "video" in ctx.media_type.lower():
                    media_type_simple = "video"
                elif "audio" in ctx.media_type.lower():
                    media_type_simple = "audio"

            if has_media:
                log.info(
                    f"📎 Message has media: {media_type_simple} "
                    f"(url: {ctx.media_url[:50]}...)"
                )

            # Log FSM context values before passing to classifier
            log.info(
                f"📊 Calling intent classifier with FSM context:\n"
                f"   active_session_id: {ctx.active_session_id}\n"
                f"   fsm_state: {ctx.fsm_state}\n"
                f"   expecting_response: {ctx.expecting_response}\n"
                f"   should_continue_session: {ctx.should_continue_session}"
            )

            intent_result = await intent_classifier.classify(
                ctx.message_in_french,
                ctx.user_id,
                last_bot_message=ctx.last_bot_message,  # Menu context
                conversation_history=ctx.recent_messages,  # Last 3 messages
                # FSM context for session continuation (context preservation)
                active_session_id=ctx.active_session_id,
                fsm_state=ctx.fsm_state,
                expecting_response=ctx.expecting_response,
                should_continue_session=ctx.should_continue_session,
                # Media context (critical for photo/video messages)
                has_media=has_media,
                media_type=media_type_simple,
                num_media=num_media,
            )
            ctx.intent = intent_result["intent"]
            ctx.confidence = intent_result.get("confidence", 0.0)

            log.info(f"✅ Intent: {ctx.intent} (confidence: {ctx.confidence:.2%})")
            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _route_message(self, ctx: MessageContext) -> Result[None]:
        """Stage 7: Route to fast path handler or full agent."""
        try:
            from src.config import settings

            # Try fast path for high-confidence intents
            if (
                settings.enable_fast_path_handlers
                and ctx.confidence >= settings.intent_confidence_threshold
            ):
                log.info("🚀 HIGH CONFIDENCE - Attempting fast path")

                # Load last bot message's tool_outputs for resolving numeric selections
                last_tool_outputs: list[Any] = []
                last_bot_message = None
                try:
                    messages = await supabase_client.get_messages_by_session(
                        ctx.session_id, fields="content,direction,metadata"
                    )
                    log.debug(f"📨 Loaded {len(messages)} messages from session")

                    # Find the most recent outbound message (only check last 5 messages)
                    recent_messages = messages[-5:] if len(messages) > 5 else messages
                    for msg in reversed(recent_messages):
                        if msg and msg.get("direction") == "outbound":
                            last_bot_message = msg.get("content", "")
                            metadata = msg.get("metadata", {})
                            last_tool_outputs = (
                                metadata.get("tool_outputs", []) if metadata else []
                            )

                            if last_tool_outputs:
                                log.info(
                                    f"📦 Loaded {len(last_tool_outputs)} tool outputs "
                                    f"from last bot message"
                                )
                                log.debug(
                                    f"📋 Tool outputs: "
                                    f"{[t.get('tool') for t in last_tool_outputs]}"
                                )
                            else:
                                log.debug(
                                    "📭 Last bot message has no tool_outputs in metadata"
                                )
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
                    message_text=ctx.message_in_french,  # For project extraction
                    session_id=ctx.session_id,  # For context queries
                    last_tool_outputs=last_tool_outputs,  # Numeric selections
                    last_bot_message=last_bot_message,  # Menu context
                )

                if result:
                    ctx.response_text = result.get("message")
                    ctx.escalation = result.get("escalation", False)
                    ctx.tools_called = result.get("tools_called", [])
                    ctx.tool_outputs = result.get(
                        "tool_outputs", []
                    )  # Capture tool outputs from fast path

                    # Capture response metadata from specialized handlers
                    if "response_type" in result:
                        ctx.response_type = result.get("response_type")
                    if "list_type" in result:
                        ctx.list_type = result.get("list_type")
                    if "attachments" in result:
                        ctx.attachments = result.get("attachments")
                        if ctx.attachments:
                            log.info(
                                f"📦 Captured {len(ctx.attachments)} attachments "
                                f"from fast path"
                            )
                    if "pending_action" in result:
                        ctx.pending_action = result.get("pending_action")
                        log.info(
                            f"📋 Captured pending_action: {ctx.pending_action.get('type')}"
                        )

                    log.info(
                        f"✅ Fast path succeeded "
                        f"(captured {len(ctx.tool_outputs)} tool outputs)"
                    )
                    return Result.ok(None)
                else:
                    log.warning(
                        "❌ Fast path returned None - checking for specialized routing"
                    )

                    # Check for specialized routing in message.py
                    # before falling back to Opus
                    from src.handlers.message import handle_direct_action

                    specialized_result = await handle_direct_action(
                        action=ctx.intent,
                        user_id=ctx.user_id,
                        phone_number=ctx.from_number,
                        language=ctx.user_language,
                        message_body=ctx.message_in_french,
                        media_url=ctx.media_url,
                        media_type=ctx.media_type,
                        session_id=ctx.session_id,
                    )

                    if specialized_result and specialized_result.get("session_exited"):
                        # Specialized agent exited session - need to reclassify intent
                        log.info(
                            "🔄 Session exited - reclassifying intent without session bias"
                        )

                        # Clear FSM context so intent classifier doesn't think there's an active session
                        ctx.active_session_id = None
                        ctx.fsm_state = None
                        ctx.should_continue_session = False

                        # Reclassify intent WITHOUT session context
                        reclassify_result = await self._standard_intent_classification(
                            ctx
                        )
                        if not reclassify_result.success:
                            return reclassify_result

                        log.info(
                            f"✅ Intent reclassified: {ctx.intent} (confidence: {ctx.confidence:.0%})"
                        )

                        # Now continue with the new intent - fall through to main LLM
                        log.info(
                            f"🤖 Falling back to full AI agent with reclassified intent: {ctx.intent}"
                        )

                    elif specialized_result:
                        log.info(
                            f"✅ Specialized routing succeeded for intent: {ctx.intent}"
                        )
                        ctx.response_text = specialized_result.get("message")
                        ctx.escalation = specialized_result.get("escalation", False)
                        ctx.tools_called = specialized_result.get("tools_called", [])
                        ctx.tool_outputs = specialized_result.get("tool_outputs", [])
                        ctx.agent_used = specialized_result.get("agent_used")
                        ctx.response_type = specialized_result.get(
                            "response_type"
                        )  # For formatting decisions
                        ctx.list_type = specialized_result.get(
                            "list_type"
                        )  # For interactive lists
                        if "attachments" in specialized_result:
                            ctx.attachments = specialized_result.get("attachments")
                            if ctx.attachments:
                                log.info(
                                    f"📦 Captured {len(ctx.attachments)} attachments "
                                    f"from specialized handler"
                                )
                        return Result.ok(None)
                    else:
                        log.warning(
                            "❌ No specialized routing found - parameters unclear"
                        )
                        log.info(
                            "🤖 Falling back to full AI agent to resolve ambiguity"
                        )
                        log.info(f"   Intent: {ctx.intent}")
                        log.info(f"   Message: '{ctx.message_in_french}'")
                        log.info(
                            "   AI will use conversation history "
                            "to understand user intent"
                        )

            # Fallback to full agent
            log.info("⚙️ Using full agent (Opus)")

            # LAYER 1: Build AUTHORITATIVE explicit state
            from src.services.agent_state import agent_state_builder

            agent_state = await agent_state_builder.build_state(
                user_id=ctx.user_id,
                language=ctx.user_language,
                session_id=ctx.session_id,
            )
            state_context = agent_state.to_prompt_context()
            if agent_state.has_active_context():
                log.info(f"📍 Injecting explicit state: project={
                        agent_state.active_project_id}, task={
                        agent_state.active_task_id}")

            # LAYER 2: Load chat history with tool outputs (for short-term memory)
            chat_history: list[Any] = []
            try:
                import json

                from langchain_core.messages import AIMessage, HumanMessage

                # Load messages WITH metadata
                messages = await supabase_client.get_messages_by_session(
                    ctx.session_id, fields="content,direction,metadata,created_at"
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
                    metadata = msg.get("metadata") or {}
                    if msg.get("direction") == "outbound" and metadata.get(
                        "tool_outputs"
                    ):
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
                            log.warning(
                                f"⚠️ Invalid message type at index {idx}: {type(msg)}"
                            )
                            continue

                        # Validate required fields
                        direction = msg.get("direction")
                        if not direction:
                            log.warning(
                                f"⚠️ Message missing 'direction' field at index {idx}"
                            )
                            continue

                        if direction == "inbound":
                            chat_history.append(
                                HumanMessage(content=msg.get("content", ""))
                            )

                        elif direction == "outbound":
                            content = msg.get("content", "")

                            # Check if this message has tool outputs
                            # AND is within last 3 tool-using turns
                            metadata = msg.get("metadata", {})
                            if metadata is None:
                                metadata = {}

                            tool_outputs = (
                                metadata.get("tool_outputs", [])
                                if isinstance(metadata, dict)
                                else []
                            )

                            # Only append tool outputs if from recent turns
                            # (prevent token bloat!)
                            is_recent_enough = (len(messages_for_history) - idx) <= (
                                recent_tool_turns if recent_tool_turns <= 3 else 3
                            )

                            if tool_outputs and is_recent_enough:
                                # Append structured data for agent reference
                                # (compact format)
                                tool_context = "\n[Données précédentes:"
                                for tool_output in tool_outputs:
                                    if not isinstance(tool_output, dict):
                                        log.debug(
                                            f"⚠️ Skipping non-dict tool_output: "
                                            f"{type(tool_output)}"
                                        )
                                        continue

                                    tool_name = tool_output.get("tool", "unknown")
                                    output_data = tool_output.get("output")

                                    # Only include essential structured data
                                    # (not full details)
                                    if (
                                        tool_name == "list_projects_tool"
                                        and isinstance(output_data, list)
                                    ):
                                        # Extract just IDs and names
                                        projects_compact = [
                                            {"id": p.get("id"), "nom": p.get("nom")}
                                            for p in output_data
                                            if isinstance(p, dict)
                                        ]
                                        if projects_compact:
                                            tool_context += f"\nProjets: {
                                                json.dumps(
                                                    projects_compact,
                                                    ensure_ascii=False)}"

                                    elif tool_name == "list_tasks_tool" and isinstance(
                                        output_data, list
                                    ):
                                        # Extract just IDs and titles
                                        tasks_compact = [
                                            {
                                                "id": t.get("id"),
                                                "title": t.get("title"),
                                            }
                                            for t in output_data
                                            if isinstance(t, dict)
                                        ]
                                        if tasks_compact:
                                            tasks_json = json.dumps(
                                                tasks_compact, ensure_ascii=False
                                            )
                                            tool_context += f"\nTâches: {tasks_json}"

                                    elif (
                                        tool_name == "list_documents_tool"
                                        and isinstance(output_data, list)
                                    ):
                                        # Extract just IDs and names
                                        docs_compact = [
                                            {
                                                "id": d.get("id"),
                                                "name": d.get("name"),
                                                "type": d.get("type"),
                                            }
                                            for d in output_data
                                            if isinstance(d, dict)
                                        ]
                                        if docs_compact:
                                            docs_json = json.dumps(
                                                docs_compact, ensure_ascii=False
                                            )
                                            tool_context += f"\nDocuments: {docs_json}"

                                tool_context += "]"
                                content += tool_context

                            chat_history.append(AIMessage(content=content))

                    except Exception as msg_error:
                        # Log error but continue processing other messages
                        # (graceful degradation)
                        log.warning(
                            f"⚠️ Error processing message at index {idx}: "
                            f"{msg_error}"
                        )
                        log.debug(f"   Problematic message: {msg}")
                        continue

                log.info(f"📜 Loaded {len(chat_history)} messages for agent context")
                log.debug(
                    f"   Chat history has "
                    f"{len([m for m in chat_history if isinstance(m, HumanMessage)])} "
                    f"user messages"
                )
                log.debug(
                    f"   Chat history has "
                    f"{len([m for m in chat_history if isinstance(m, AIMessage)])} "
                    f"AI messages"
                )
            except Exception as e:
                log.warning(f"Could not load chat history for agent: {e}")
                log.exception(e)  # Full stack trace for debugging
                log.debug(f"   Session ID: {ctx.session_id}")
                msg_count = len(messages) if "messages" in locals() else "N/A"
                log.debug(f"   Messages loaded: {msg_count}")
                chat_history = []

            log.info("🤖 Invoking full AI agent with conversation context")
            log.debug(f"   User message: '{ctx.message_in_french}'")
            log.debug(f"   Chat history: {len(chat_history)} messages")
            log.debug(
                f"   Explicit state: {state_context if state_context else 'None'}"
            )

            agent_result = await lumiera_agent.process_message(
                user_id=ctx.user_id,
                phone_number=ctx.from_number,
                user_name=ctx.user_name,
                language=ctx.user_language,
                message_text=ctx.message_in_french,
                chat_history=chat_history,
                state_context=state_context,  # NEW: Inject state
            )

            ctx.response_text = agent_result.get("message")
            ctx.escalation = agent_result.get("escalation", False)
            ctx.tools_called = agent_result.get("tools_called", [])

            log.info("✅ AI agent completed")
            resp_len = len(ctx.response_text) if ctx.response_text else 0
            log.debug(f"   Response length: {resp_len} chars")
            log.debug(f"   Tools called: {ctx.tools_called}")
            log.debug(f"   Escalation: {ctx.escalation}")
            ctx.tool_outputs = agent_result.get(
                "tool_outputs", []
            )  # NEW: Store for persistence

            # CRITICAL: If AI agent called list_tasks_tool or list_projects_tool,
            # override intent so message gets formatted as interactive list
            if "list_tasks_tool" in ctx.tools_called:
                log.info(
                    "🔄 AI agent called list_tasks_tool → Overriding intent to 'list_tasks'"
                )
                ctx.intent = "list_tasks"
                ctx.list_type = "tasks"
            elif "list_projects_tool" in ctx.tools_called:
                log.info(
                    "🔄 AI agent called list_projects_tool → Overriding intent to 'list_projects'"
                )
                ctx.intent = "list_projects"
                ctx.list_type = "projects"

            log.info("✅ Agent processed message")
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
                    (
                        detected_lang,
                        method,
                    ) = await language_detection_service.detect_async(
                        ctx.response_text, fallback_language="fr"
                    )

                    if detected_lang != "fr":
                        log.warning(
                            f"⚠️ Agent responded in {detected_lang} "
                            f"instead of French! "
                            f"Response preview: {ctx.response_text[:100]}..."
                        )
                        # Translate from detected language instead
                        ctx.response_text = await translation_service.translate(
                            ctx.response_text,
                            source_language=detected_lang,
                            target_language=ctx.user_language,
                        )
                        log.info(
                            f"✅ Response translated from {detected_lang} "
                            f"to {ctx.user_language}"
                        )
                    else:
                        # Agent correctly responded in French
                        if ctx.user_language != "fr":
                            ctx.response_text = (
                                await translation_service.translate_from_french(
                                    ctx.response_text, ctx.user_language
                                )
                            )
                            log.info(
                                f"✅ Response translated from French "
                                f"to {ctx.user_language}"
                            )
                        else:
                            log.debug(
                                "ℹ️ No translation needed - user language is French"
                            )
                else:
                    # Short response, assume French and translate
                    if ctx.user_language != "fr":
                        ctx.response_text = (
                            await translation_service.translate_from_french(
                                ctx.response_text, ctx.user_language
                            )
                        )
                        log.info(f"✅ Response translated to {ctx.user_language}")
                    else:
                        log.debug("ℹ️ No translation needed - user language is French")

            return Result.ok(None)

        except Exception as e:
            return Result.from_exception(e)

    async def _persist_messages(self, ctx: MessageContext) -> None:
        """Stage 9: Save inbound and outbound messages to database."""
        try:
            log.info("💾 [STAGE 9] Persisting messages to database")

            # Check if there's an active incident session to link messages
            incident_metadata: Dict[str, Any] = {}
            if ctx.active_session_id and ctx.agent_used == "incident":
                from src.services.incident.state import incident_state

                incident_session = await incident_state.get_session(ctx.user_id)
                if incident_session and incident_session.get("incident_id"):
                    incident_metadata["incident_id"] = incident_session["incident_id"]
                    incident_metadata["incident_session_id"] = ctx.active_session_id
                    if ctx.media_url:
                        incident_metadata["incident_action"] = "image"
                    log.debug(
                        f"📎 Linking message to incident {incident_session['incident_id'][:8]}..."
                    )

            # Log media URL being saved
            if ctx.media_url:
                url_type = (
                    "Supabase" if "supabase" in ctx.media_url.lower() else "Twilio"
                )
                log.info("   📎 Saving inbound message with media")
                log.info(f"   🔗 Media URL ({url_type}): {ctx.media_url[:100]}...")
                log.info(f"   📋 Media type: {ctx.media_type}")
            else:
                log.info("   📝 Saving text-only inbound message (no media)")

            # Save inbound message with incident metadata if applicable
            await supabase_client.save_message(
                user_id=ctx.user_id,
                message_text=ctx.message_body,
                original_language=ctx.user_language,
                direction="inbound",
                message_sid=ctx.message_sid,
                media_url=ctx.media_url,
                message_type=(
                    "audio" if ctx.media_type and "audio" in ctx.media_type else "text"
                ),
                session_id=ctx.session_id,
                metadata=incident_metadata if incident_metadata else None,
            )
            log.info("   ✅ Inbound message saved to database")

            # Build metadata for outbound message
            outbound_metadata: Dict[str, Any] = {}

            # Store the intent that generated this response (for list selection routing)
            if ctx.intent:
                outbound_metadata["intent"] = ctx.intent

            # Add escalation metadata if applicable (handled by save_message)
            # Add tool outputs metadata if any (for short-term memory)
            if ctx.tool_outputs:
                outbound_metadata["tool_outputs"] = ctx.tool_outputs
                log.debug(
                    f"💾 Storing {len(ctx.tool_outputs)} tool outputs "
                    f"in message metadata"
                )

            # Add pending_action if any (for interactive choices like issue_choice)
            if ctx.pending_action:
                outbound_metadata["pending_action"] = ctx.pending_action
                log.debug(
                    f"💾 Storing pending_action ({ctx.pending_action.get('type')}) "
                    f"in message metadata"
                )

            # Add incident metadata to outbound message if applicable
            if incident_metadata and incident_metadata.get("incident_id"):
                outbound_metadata["incident_id"] = incident_metadata["incident_id"]
                outbound_metadata["incident_action"] = "response"
                log.debug(
                    f"📎 Linking outbound message to incident {incident_metadata['incident_id'][:8]}..."
                )

            # Save outbound message with metadata
            await supabase_client.save_message(
                user_id=ctx.user_id,
                message_text=ctx.response_text,
                original_language=ctx.user_language,
                direction="outbound",
                session_id=ctx.session_id,
                is_escalation=ctx.escalation,
                metadata=outbound_metadata if outbound_metadata else None,
            )

            log.info("✅ Messages persisted")

        except Exception as e:
            log.error(f"Failed to persist messages: {e}")
            # Don't fail the whole pipeline if persistence fails


# Global pipeline instance
message_pipeline = MessagePipeline()
