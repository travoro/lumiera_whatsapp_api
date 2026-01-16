"""Progress update session state management."""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from src.integrations.supabase import supabase_client
from src.utils.logger import log


class ProgressUpdateState:
    """Manages progress update conversation state."""

    SESSION_EXPIRY_HOURS = 2

    async def create_session(
        self,
        user_id: str,
        task_id: str,
        project_id: str
    ) -> Optional[str]:
        """Create a new progress update session.

        Args:
            user_id: Subcontractor ID
            task_id: Task ID to update
            project_id: PlanRadar project ID

        Returns:
            Session ID if created successfully, None otherwise
        """
        try:
            # Clear any existing session for this user
            await self.clear_session(user_id)

            # Create new session
            response = supabase_client.client.table("progress_update_sessions").insert({
                "subcontractor_id": user_id,
                "task_id": task_id,
                "project_id": project_id,
                "current_step": "awaiting_action",
                "fsm_state": "awaiting_action",  # Set initial FSM state
                "expires_at": (datetime.utcnow() + timedelta(hours=self.SESSION_EXPIRY_HOURS)).isoformat()
            }).execute()

            if response.data:
                session_id = response.data[0]["id"]
                log.info(f"✅ Created progress update session {session_id} for user {user_id}")
                return session_id
            return None

        except Exception as e:
            log.error(f"Error creating progress update session: {e}")
            return None

    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active session for user (if not expired).

        Args:
            user_id: Subcontractor ID

        Returns:
            Session dict if active and not expired, None otherwise
        """
        try:
            response = supabase_client.client.table("progress_update_sessions").select("*").eq(
                "subcontractor_id", user_id
            ).execute()

            if response.data:
                session = response.data[0]
                # Check expiration
                expires_at = datetime.fromisoformat(session["expires_at"].replace('Z', '+00:00'))
                if datetime.utcnow() < expires_at.replace(tzinfo=None):
                    return session
                else:
                    # Expired, clean up
                    log.info(f"Session expired for user {user_id}, cleaning up")
                    await self.clear_session(user_id)
            return None

        except Exception as e:
            log.error(f"Error getting progress update session: {e}")
            return None

    async def update_session(
        self,
        user_id: str,
        **updates
    ) -> bool:
        """Update session state fields.

        Args:
            user_id: Subcontractor ID
            **updates: Fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            updates["last_activity"] = datetime.utcnow().isoformat()

            response = supabase_client.client.table("progress_update_sessions").update(
                updates
            ).eq("subcontractor_id", user_id).execute()

            return bool(response.data)

        except Exception as e:
            log.error(f"Error updating progress update session: {e}")
            return False

    async def add_action(
        self,
        user_id: str,
        action_type: str  # 'image', 'comment', 'complete'
    ) -> bool:
        """Record that user completed an action.

        Args:
            user_id: Subcontractor ID
            action_type: Type of action ('image', 'comment', 'complete')

        Returns:
            True if successful, False otherwise
        """
        try:
            session = await self.get_session(user_id)
            if not session:
                return False

            updates = {}
            if action_type == "image":
                updates["images_uploaded"] = session["images_uploaded"] + 1
            elif action_type == "comment":
                updates["comments_added"] = session["comments_added"] + 1
            elif action_type == "complete":
                updates["status_changed"] = True

            # Update FSM state to indicate we're collecting data and expecting response
            # This is critical for context preservation when user responds to options
            updates["fsm_state"] = "collecting_data"

            # Set expecting_response flag in metadata so intent classifier knows
            # that bot just showed options and is waiting for user's next action
            session_metadata = session.get("session_metadata", {})
            session_metadata["expecting_response"] = True
            session_metadata["last_bot_action"] = f"added_{action_type}"
            session_metadata["available_actions"] = ["add_comment", "add_photo", "mark_complete"]
            updates["session_metadata"] = session_metadata

            log.info(f"🔄 FSM: Setting state='collecting_data', expecting_response=True after {action_type}")

            return await self.update_session(user_id, **updates)

        except Exception as e:
            log.error(f"Error recording action in progress update session: {e}")
            return False

    async def clear_session(self, user_id: str) -> bool:
        """Delete session for user.

        Args:
            user_id: Subcontractor ID

        Returns:
            True if successful, False otherwise
        """
        try:
            response = supabase_client.client.table("progress_update_sessions").delete().eq(
                "subcontractor_id", user_id
            ).execute()

            if response.data:
                log.info(f"🧹 Cleared progress update session for user {user_id}")
            return True

        except Exception as e:
            log.error(f"Error clearing progress update session: {e}")
            return False

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions across all users.

        Returns:
            Number of sessions cleaned up
        """
        try:
            # Get all expired sessions
            now = datetime.utcnow().isoformat()
            response = supabase_client.client.table("progress_update_sessions").select(
                "id, subcontractor_id"
            ).lt("expires_at", now).execute()

            if not response.data:
                return 0

            cleaned_count = 0
            for session in response.data:
                await self.clear_session(session["subcontractor_id"])
                cleaned_count += 1

            if cleaned_count > 0:
                log.info(f"🧹 Cleaned up {cleaned_count} expired progress update sessions")

            return cleaned_count

        except Exception as e:
            log.error(f"Error cleaning up expired sessions: {e}")
            return 0


# Global instance
progress_update_state = ProgressUpdateState()
