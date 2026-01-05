"""Supabase client for database operations."""
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from datetime import datetime
from src.config import settings
from src.utils.logger import log


class SupabaseClient:
    """Client for interacting with Supabase database and storage."""

    def __init__(self):
        """Initialize Supabase client."""
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
        log.info("Supabase client initialized")

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
            response = self.client.table("subcontractors").select("*").eq(
                "contact_telephone", phone_number
            ).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            log.error(f"Error getting subcontractor by phone: {e}")
            return None

    async def create_or_update_user(
        self,
        phone_number: str,
        language: str = "fr",
        **kwargs
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
                response = self.client.table("subcontractors").update({
                    "language": language,
                    "updated_at": datetime.utcnow().isoformat(),
                    **kwargs
                }).eq("id", existing_user["id"]).execute()
                log.info(f"Updated subcontractor {existing_user['id']} language to {language}")
                return response.data[0] if response.data else existing_user
            else:
                # Subcontractor not found - cannot auto-create
                log.warning(f"Subcontractor with phone {phone_number} not found. Create manually in Supabase first.")
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
    ) -> bool:
        """Save message to database for audit trail."""
        try:
            self.client.table("messages").insert({
                "subcontractor_id": user_id,
                "content": message_text,
                "language": original_language,
                "direction": direction,
                "twilio_sid": message_sid,
                "media_url": media_url,
                "message_type": message_type,
                "media_type": media_type,
                "status": "delivered",
                "source": "whatsapp",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()
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
            self.client.table("action_logs").insert({
                "subcontractor_id": user_id,
                "action_name": action_name,
                "action_type": action_type,
                "parameters": parameters,
                "result": result,
                "error": error,
                "duration_ms": duration_ms,
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
            log.info(f"Action logged: {action_name} for user {user_id}")
            return True
        except Exception as e:
            # Log warning but don't fail the main operation
            log.warning(f"Could not save action log (table may not exist - run migrations): {e}")
            return False

    async def list_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """List all active projects (chantiers) for a user."""
        try:
            response = self.client.table("projects").select(
                "*"
            ).eq("active", True).execute()

            return response.data if response.data else []
        except Exception as e:
            log.error(f"Error listing projects: {e}")
            return []

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get specific project details."""
        try:
            response = self.client.table("projects").select("*").eq(
                "id", project_id
            ).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            log.error(f"Error getting project: {e}")
            return None

    async def create_escalation(
        self,
        user_id: str,
        reason: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Create escalation record for human handoff (optional - table may not exist)."""
        try:
            response = self.client.table("escalations").insert({
                "user_id": user_id,
                "reason": reason,
                "context": context,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
            }).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]["id"]
            return None
        except Exception as e:
            # Table may not exist - just log warning
            log.warning(f"Could not create escalation (table may not exist): {e}")
            return None

    async def update_escalation_status(
        self,
        escalation_id: str,
        status: str,
        resolution_note: Optional[str] = None,
    ) -> bool:
        """Update escalation status (optional - table may not exist)."""
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
            }
            if resolution_note:
                update_data["resolution_note"] = resolution_note

            self.client.table("escalations").update(update_data).eq(
                "id", escalation_id
            ).execute()
            return True
        except Exception as e:
            log.warning(f"Could not update escalation (table may not exist): {e}")
            return False

    async def get_active_escalation(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Check if user has an active escalation (optional - table may not exist)."""
        try:
            response = self.client.table("escalations").select("*").eq(
                "user_id", user_id
            ).eq("status", "pending").execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            log.warning(f"Could not check active escalation (table may not exist): {e}")
            return None

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
        """
        try:
            response = self.client.table("messages").select(
                "id, direction, content, language, created_at"
            ).eq("subcontractor_id", user_id).order(
                "created_at", desc=True
            ).limit(limit).execute()

            if response.data:
                # Reverse to get chronological order (oldest first)
                messages = list(reversed(response.data))
                log.info(f"Retrieved {len(messages)} messages for user {user_id}")
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
            response = self.client.storage.from_(
                settings.media_storage_bucket
            ).upload(file_name, file_data, {
                "content-type": content_type
            })

            # Get public URL
            public_url = self.client.storage.from_(
                settings.media_storage_bucket
            ).get_public_url(file_name)

            return public_url
        except Exception as e:
            log.error(f"Error uploading media: {e}")
            return None


# Global instance
supabase_client = SupabaseClient()
