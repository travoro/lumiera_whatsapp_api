"""Supabase client for database operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from supabase import Client, create_client

from src.config import settings
from src.utils.logger import log


class SupabaseClient:
    """Client for interacting with Supabase database and storage."""

    def __init__(self):
        """Initialize Supabase client."""
        self.client: Client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        log.info("Supabase client initialized")

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get subcontractor by ID (synchronous for compatibility).

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            Subcontractor dict if found, None otherwise
        """
        try:
            response = (
                self.client.table("subcontractors")
                .select("*")
                .eq("id", user_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return cast(Dict[str, Any], response.data[0])
            return None
        except Exception as e:
            log.error(f"Error getting subcontractor {user_id}: {e}")
            return None

    def get_user_name(self, user_id: str) -> str:
        """Get subcontractor contact name (convenience method).

        Args:
            user_id: Subcontractor ID

        Returns:
            Contact name or empty string if not found
        """
        try:
            user = self.get_user(user_id)
            if user:
                # Try different name fields in order of preference
                return (
                    user.get("contact_prenom")
                    or user.get("contact_name")
                    or user.get("raison_sociale")
                    or ""
                )
            return ""
        except Exception as e:
            log.error(f"Error getting user name for {user_id}: {e}")
            return ""

    async def get_user_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get subcontractor by WhatsApp phone number.

        IMPORTANT: This method ONLY looks up existing subcontractors.
        Subcontractors can ONLY be created by admins in the backoffice.
        Never auto-create subcontractors in the code.

        Args:
            phone_number: Phone number without 'whatsapp:' prefix (e.g., +33123456789)

        Returns:
            Subcontractor dict if found, None otherwise
        """
        try:
            response = (
                self.client.table("subcontractors")
                .select("*")
                .eq("contact_telephone", phone_number)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return cast(Dict[str, Any], response.data[0])
            return None
        except Exception as e:
            log.error(f"Error getting subcontractor by phone: {e}")
            return None

    async def update_user_language(self, user_id: str, language: str) -> bool:
        """Update user's preferred language in profile.

        This is called when language detection determines the user is speaking
        a different language than their profile setting.

        Args:
            user_id: Subcontractor ID (UUID)
            language: ISO 639-1 language code (e.g., 'fr', 'en', 'ro')

        Returns:
            True if update successful, False otherwise
        """
        try:
            response = (
                self.client.table("subcontractors")
                .update({"language": language})
                .eq("id", user_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                log.info(
                    "🔄 Updated user language in profile: "
                    f"user_id={user_id}, new_language={language}"
                )
                return True
            else:
                log.warning(f"Failed to update user language: user_id={user_id}")
                return False

        except Exception as e:
            log.error(f"Error updating user language: {e}")
            return False

    async def create_or_update_user(
        self, phone_number: str, language: str = "fr", **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Update existing subcontractor profile (lookup only - no auto-create).

        Note: Subcontractors must be created in advance with all required fields
        (raison_sociale, forme_juridique, siren, siret, etc.).
        This method only updates language preference.
        """
        try:
            # Check if subcontractor exists
            existing_user = await self.get_user_by_phone(phone_number)

            if existing_user:
                # Update existing subcontractor's language
                response = (
                    self.client.table("subcontractors")
                    .update(
                        {
                            "language": language,
                            "updated_at": datetime.utcnow().isoformat(),
                            **kwargs,
                        }
                    )
                    .eq("id", existing_user["id"])
                    .execute()
                )
                log.info(
                    f"Updated subcontractor {existing_user['id']} language to {language}"
                )
                return (
                    cast(Dict[str, Any], response.data[0])
                    if response.data
                    else existing_user
                )
            else:
                # Subcontractor not found - cannot auto-create
                log.warning(
                    f"Subcontractor with phone {phone_number} not found. Create manually in Supabase first."
                )
                return None
        except Exception as e:
            log.error(f"Error updating subcontractor: {e}")
            return None

    async def save_message(
        self,
        user_id: str,
        message_text: str,
        original_language: str,
        direction: str,  # 'inbound' or 'outbound'
        message_sid: Optional[str] = None,
        media_url: Optional[str] = None,
        message_type: str = "text",
        media_type: Optional[str] = None,
        session_id: Optional[str] = None,
        is_escalation: bool = False,
        escalation_reason: Optional[str] = None,
        need_human: bool = False,  # DEPRECATED: Use is_escalation instead
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Save message to database for audit trail with session tracking.

        Args:
            user_id: User ID
            message_text: Message content
            original_language: Language code
            direction: 'inbound' or 'outbound'
            message_sid: Twilio message SID
            media_url: Media URL if present
            message_type: Type of message (text, image, etc.)
            media_type: MIME type of media
            session_id: Conversation session ID
            is_escalation: Flag to mark this as an escalation
            escalation_reason: Reason for escalation if applicable
            need_human: DEPRECATED - Use is_escalation instead. Kept for backward compatibility.
            source: Message source ('user', 'agent', 'whatsapp'). Auto-detected if not provided.
            metadata: Additional metadata to store (e.g., tool_outputs for short-term memory)
        """
        try:
            # Auto-detect source if not provided
            if source is None:
                source = "user" if direction == "inbound" else "agent"

            message_data: Dict[str, Any] = {
                "subcontractor_id": user_id,
                "content": message_text,
                "language": original_language,
                "direction": direction,
                "twilio_sid": message_sid,
                "media_url": media_url,
                "message_type": message_type,
                "media_type": media_type,
                "status": "delivered",
                "source": source,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            # Add session_id if provided (from migrations v2)
            if session_id:
                message_data["session_id"] = session_id

            # Build metadata (merge provided metadata with escalation data)
            message_metadata = metadata.copy() if metadata else {}

            # BACKWARD COMPATIBILITY: Convert need_human to is_escalation
            if need_human and not is_escalation:
                log.warning(
                    "need_human parameter is deprecated. Converting to is_escalation=True"
                )
                is_escalation = True

            # Add escalation metadata if applicable (standardized format)
            if is_escalation:
                message_metadata["is_escalation"] = True
                message_metadata["escalation_reason"] = escalation_reason
                message_metadata["escalation_timestamp"] = datetime.utcnow().isoformat()

            # Save metadata if any data is present
            if message_metadata:
                message_data["metadata"] = message_metadata

            self.client.table("messages").insert(message_data).execute()
            return True
        except Exception as e:
            log.error(f"Error saving message: {e}")
            return False

    async def save_action_log(
        self,
        user_id: str,
        action_name: str,
        parameters: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        action_type: str = "tool_call",
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Log action execution for auditability and project evolution tracking.

        This is critical for understanding how the project evolved over time.

        Args:
            user_id: Subcontractor ID
            action_name: Name of the action/tool
            parameters: Input parameters
            result: Result of the action
            error: Error message if failed
            action_type: Type of action (tool_call, api_request, etc.)
            duration_ms: Duration in milliseconds
        """
        try:
            self.client.table("action_logs").insert(
                {
                    "subcontractor_id": user_id,
                    "action_name": action_name,
                    "action_type": action_type,
                    "parameters": parameters,
                    "result": result,
                    "error": error,
                    "duration_ms": duration_ms,
                    "created_at": datetime.utcnow().isoformat(),
                }
            ).execute()
            log.info(f"Action logged: {action_name} for user {user_id}")
            return True
        except Exception as e:
            # Log warning but don't fail the main operation
            log.warning(
                f"Could not save action log (table may not exist - run migrations): {e}"
            )
            return False

    async def list_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """List all active projects (chantiers) for a user.

        SECURITY: Filters projects by subcontractor_id to prevent unauthorized access.
        """
        try:
            response = (
                self.client.table("projects")
                .select("*")
                .eq("active", True)
                .eq("subcontractor_id", user_id)
                .execute()
            )

            log.info(
                f"Retrieved {len(response.data) if response.data else 0} projects for user {user_id}"
            )
            return cast(List[Dict[str, Any]], response.data) if response.data else []
        except Exception as e:
            log.error(f"Error listing projects for user {user_id}: {e}")
            return []

    async def get_project(
        self, project_id: str, user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get specific project details.

        Args:
            project_id: The project ID to retrieve
            user_id: Optional user ID for authorization check

        SECURITY: If user_id provided, ensures project belongs to user.
        """
        try:
            query = self.client.table("projects").select("*").eq("id", project_id)

            # Add user filtering for security if user_id provided
            if user_id:
                query = query.eq("subcontractor_id", user_id)

            response = query.execute()

            if response.data and len(response.data) > 0:
                return cast(Dict[str, Any], response.data[0])
            return None
        except Exception as e:
            log.error(f"Error getting project {project_id}: {e}")
            return None

    async def get_escalation_messages(self, user_id: str, limit: int = 10) -> list:
        """Get recent escalation messages for a user.

        Escalations are stored as messages with metadata.is_escalation = true.
        No separate escalations table needed.
        """
        try:
            response = (
                self.client.table("messages")
                .select("*")
                .eq("subcontractor_id", user_id)
                .order("created_at", desc=True)
                .limit(limit * 2)
                .execute()
            )

            if not response.data:
                return []

            # Filter for escalation messages
            messages = cast(List[Dict[str, Any]], response.data)
            escalations = [
                msg
                for msg in messages
                if msg.get("metadata", {}).get("is_escalation", False)
            ]

            return escalations[:limit]

        except Exception as e:
            log.error(f"Error getting escalation messages: {e}")
            return []

    async def get_conversation_history(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent conversation history for a user.

        Args:
            user_id: The subcontractor ID
            limit: Number of recent messages to retrieve (default 20)

        Returns:
            List of messages in chronological order (oldest first)
            Note: Filters out messages with null/empty content
        """
        try:
            response = (
                self.client.table("messages")
                .select("id, direction, content, language, created_at")
                .eq("subcontractor_id", user_id)
                .order("created_at", desc=True)
                .limit(limit * 2)
                .execute()
            )  # Get more to account for filtering

            if response.data:
                # Filter out messages with null or empty content
                messages_data = cast(List[Dict[str, Any]], response.data)
                valid_messages = [
                    msg
                    for msg in messages_data
                    if msg.get("content") and msg["content"].strip()
                ]

                # Limit to requested number after filtering
                valid_messages = valid_messages[:limit]

                # Reverse to get chronological order (oldest first)
                messages = list(reversed(valid_messages))
                log.info(f"Retrieved {len(messages)} valid messages for user {user_id}")
                return messages
            return []
        except Exception as e:
            log.warning(f"Error retrieving conversation history: {e}")
            return []

    async def get_recent_context(
        self,
        user_id: str,
        max_messages: int = 10,
    ) -> str:
        """Get recent conversation context as a formatted string.

        Args:
            user_id: The subcontractor ID
            max_messages: Maximum number of recent messages to include

        Returns:
            Formatted conversation history string
        """
        try:
            messages = await self.get_conversation_history(user_id, limit=max_messages)

            if not messages:
                return ""

            # Format messages for context
            context_lines = []
            for msg in messages:
                role = "User" if msg["direction"] == "inbound" else "Assistant"
                content = msg["content"]
                context_lines.append(f"{role}: {content}")

            return "\n".join(context_lines)
        except Exception as e:
            log.warning(f"Error getting recent context: {e}")
            return ""

    async def upload_media(
        self,
        file_data: bytes,
        file_name: str,
        content_type: str,
    ) -> Optional[str]:
        """Upload media file to Supabase storage."""
        try:
            response = self.client.storage.from_(settings.media_storage_bucket).upload(
                file_name, file_data, {"content-type": content_type}
            )

            # Get public URL
            public_url = self.client.storage.from_(
                settings.media_storage_bucket
            ).get_public_url(file_name)

            return public_url
        except Exception as e:
            log.error(f"Error uploading media: {e}")
            return None

    # ==================== SESSION OPERATIONS ====================

    async def get_or_create_session_rpc(self, subcontractor_id: str) -> Optional[str]:
        """Call PostgreSQL RPC function to get or create session.

        Args:
            subcontractor_id: The subcontractor's ID

        Returns:
            Session ID if successful, None otherwise
        """
        try:
            result = self.client.rpc(
                "get_or_create_session", {"p_subcontractor_id": subcontractor_id}
            ).execute()
            return cast(Optional[str], result.data) if result.data else None
        except Exception as e:
            log.error(f"Error calling get_or_create_session RPC: {e}")
            return None

    async def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details by ID.

        Args:
            session_id: Session ID

        Returns:
            Session dict if found, None otherwise
        """
        try:
            response = (
                self.client.table("conversation_sessions")
                .select("*")
                .eq("id", session_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return cast(Dict[str, Any], response.data[0])
            return None
        except Exception as e:
            log.error(f"Error getting session {session_id}: {e}")
            return None

    async def create_session(
        self, subcontractor_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a new conversation session.

        Args:
            subcontractor_id: The subcontractor's ID
            data: Session data dict

        Returns:
            Created session dict if successful, None otherwise
        """
        try:
            response = self.client.table("conversation_sessions").insert(data).execute()

            if response.data and len(response.data) > 0:
                return cast(Dict[str, Any], response.data[0])
            return None
        except Exception as e:
            log.error(f"Error creating session: {e}")
            return None

    async def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Update session data.

        Args:
            session_id: Session ID
            data: Update data dict

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.table("conversation_sessions").update(data).eq(
                "id", session_id
            ).execute()
            return True
        except Exception as e:
            log.error(f"Error updating session {session_id}: {e}")
            return False

    async def end_sessions_for_user(
        self, subcontractor_id: str, end_data: Dict[str, Any]
    ) -> bool:
        """End all active sessions for a user.

        Args:
            subcontractor_id: The subcontractor's ID
            end_data: Data for ending sessions (status, ended_at, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.table("conversation_sessions").update(end_data).eq(
                "subcontractor_id", subcontractor_id
            ).eq("status", "active").execute()
            return True
        except Exception as e:
            log.error(f"Error ending sessions for user {subcontractor_id}: {e}")
            return False

    async def generate_session_summary_rpc(self, session_id: str) -> Optional[str]:
        """Call PostgreSQL RPC function to generate session summary.

        Args:
            session_id: Session ID

        Returns:
            Summary text if successful, None otherwise
        """
        try:
            result = self.client.rpc(
                "generate_session_summary", {"p_session_id": session_id}
            ).execute()
            return cast(Optional[str], result.data) if result.data else None
        except Exception as e:
            log.error(f"Error calling generate_session_summary RPC: {e}")
            return None

    async def get_messages_by_session(
        self, session_id: str, fields: str = "*"
    ) -> List[Dict[str, Any]]:
        """Get messages for a specific session.

        Args:
            session_id: Session ID
            fields: Fields to select (default: '*')

        Returns:
            List of message dicts
        """
        try:
            response = (
                self.client.table("messages")
                .select(fields)
                .eq("session_id", session_id)
                .execute()
            )
            return cast(List[Dict[str, Any]], response.data) if response.data else []
        except Exception as e:
            log.error(f"Error getting messages for session {session_id}: {e}")
            return []

    async def get_sessions_for_user(
        self, subcontractor_id: str
    ) -> List[Dict[str, Any]]:
        """Get all sessions for a user.

        Args:
            subcontractor_id: The subcontractor's ID

        Returns:
            List of session dicts
        """
        try:
            response = (
                self.client.table("conversation_sessions")
                .select("*")
                .eq("subcontractor_id", subcontractor_id)
                .execute()
            )
            return cast(List[Dict[str, Any]], response.data) if response.data else []
        except Exception as e:
            log.error(f"Error getting sessions for user {subcontractor_id}: {e}")
            return []

    # ==================== TEMPLATE OPERATIONS ====================

    async def get_template(
        self, template_name: str, language: str, is_active: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get template by name and language.

        Args:
            template_name: Template name
            language: Language code
            is_active: Filter by active status (default: True)

        Returns:
            Template dict if found, None otherwise
        """
        try:
            response = (
                self.client.table("templates")
                .select("twilio_content_sid")
                .eq("template_name", template_name)
                .eq("language", language)
                .eq("is_active", is_active)
                .single()
                .execute()
            )

            return cast(Dict[str, Any], response.data) if response.data else None
        except Exception as e:
            log.warning(f"Template not found or error: {e}")
            return None

    # ==================== INTENT OPERATIONS ====================

    async def log_intent_classification(self, data: Dict[str, Any]) -> bool:
        """Log intent classification for analytics.

        Args:
            data: Classification data dict

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.table("intent_classifications").insert(data).execute()
            return True
        except Exception as e:
            log.warning(f"Error logging intent classification: {e}")
            return False

    # ==================== PROGRESS UPDATE HELPERS ====================

    async def get_recent_messages(self, user_id: str, limit: int = 5) -> list:
        """Get recent message history for user.

        Args:
            user_id: User ID
            limit: Number of messages to retrieve

        Returns:
            List of recent messages (dicts with role, content)
        """
        try:
            response = (
                self.client.table("messages")
                .select("content, direction, created_at")
                .eq("subcontractor_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            if response.data:
                messages = []
                messages_data = cast(List[Dict[str, Any]], response.data)
                for msg in reversed(messages_data):  # Chronological order
                    # Skip messages with empty content (e.g., image-only messages)
                    # Claude API requires all messages to have non-empty content
                    if not msg["content"] or not msg["content"].strip():
                        continue

                    role = "user" if msg["direction"] == "inbound" else "assistant"
                    messages.append({"role": role, "content": msg["content"]})
                return messages
            return []

        except Exception as e:
            log.error(f"Error getting recent messages: {e}")
            return []

    # REMOVED: get_task() method
    # Tasks are stored in PlanRadar, not in Supabase.
    # Use planradar_client.get_task(task_id, project_id) instead.


# Global instance
# Skip instantiation in test environment to avoid API key validation
# Use settings.environment instead of os.getenv to ensure consistency with config

if settings.environment == "test":
    supabase_client = None  # Will be mocked by pytest fixtures
else:
    supabase_client = SupabaseClient()
