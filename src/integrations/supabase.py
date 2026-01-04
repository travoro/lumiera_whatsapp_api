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
        """Get user by WhatsApp phone number."""
        try:
            response = self.client.table("users").select("*").eq(
                "whatsapp_number", phone_number
            ).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            log.error(f"Error getting user by phone: {e}")
            return None

    async def create_or_update_user(
        self,
        phone_number: str,
        language: str = "fr",
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Create or update user profile."""
        try:
            # Check if user exists
            existing_user = await self.get_user_by_phone(phone_number)

            if existing_user:
                # Update existing user
                response = self.client.table("users").update({
                    "language": language,
                    "updated_at": datetime.utcnow().isoformat(),
                    **kwargs
                }).eq("id", existing_user["id"]).execute()
                return response.data[0] if response.data else None
            else:
                # Create new user
                response = self.client.table("users").insert({
                    "whatsapp_number": phone_number,
                    "language": language,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    **kwargs
                }).execute()
                return response.data[0] if response.data else None
        except Exception as e:
            log.error(f"Error creating/updating user: {e}")
            return None

    async def save_message(
        self,
        user_id: str,
        message_text: str,
        original_language: str,
        direction: str,  # 'inbound' or 'outbound'
        message_sid: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> bool:
        """Save message to database for audit trail."""
        try:
            self.client.table("messages").insert({
                "user_id": user_id,
                "message_text": message_text,
                "original_language": original_language,
                "direction": direction,
                "message_sid": message_sid,
                "media_url": media_url,
                "created_at": datetime.utcnow().isoformat(),
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
    ) -> bool:
        """Log action execution for auditability."""
        try:
            self.client.table("action_logs").insert({
                "user_id": user_id,
                "action_name": action_name,
                "parameters": parameters,
                "result": result,
                "error": error,
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
            return True
        except Exception as e:
            log.error(f"Error saving action log: {e}")
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
        """Create escalation record for human handoff."""
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
            log.error(f"Error creating escalation: {e}")
            return None

    async def update_escalation_status(
        self,
        escalation_id: str,
        status: str,
        resolution_note: Optional[str] = None,
    ) -> bool:
        """Update escalation status."""
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
            log.error(f"Error updating escalation: {e}")
            return False

    async def get_active_escalation(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Check if user has an active escalation."""
        try:
            response = self.client.table("escalations").select("*").eq(
                "user_id", user_id
            ).eq("status", "pending").execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            log.error(f"Error checking active escalation: {e}")
            return None

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
