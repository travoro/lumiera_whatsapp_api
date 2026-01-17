"""Progress update session state management."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.integrations.supabase import supabase_client
from src.utils.logger import log


class ProgressUpdateState:
    """Manages progress update conversation state."""

    SESSION_EXPIRY_HOURS = 2

    async def _log_transition(
        self,
        user_id: str,
        session_id: Optional[str],
        from_state: str,
        to_state: str,
        trigger: str,
        success: bool = True,
        error: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log FSM state transition to audit table.

        Args:
            user_id: User ID
            session_id: Session ID (if applicable)
            from_state: Previous FSM state
            to_state: New FSM state
            trigger: What caused the transition
            success: Whether transition succeeded
            error: Error message if failed
            context: Additional context data
        """
        try:
            result = (
                supabase_client.client.table("fsm_transition_log")
                .insert(
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "from_state": from_state,
                        "to_state": to_state,
                        "trigger": trigger,
                        "success": success,
                        "error": error,
                        "context": context or {},
                    }
                )
                .execute()
            )

            # Log detailed result for debugging
            if result and result.data:
                inserted_id = result.data[0]["id"]
                log.info(
                    f"📊 FSM Transition logged: {from_state} → {to_state} (trigger: {trigger}, session: {session_id}, id: {inserted_id})"
                )

                # VERIFICATION: Immediately query back to confirm persistence
                verify_result = (
                    supabase_client.client.table("fsm_transition_log")
                    .select("*")
                    .eq("id", inserted_id)
                    .execute()
                )
                if verify_result and verify_result.data:
                    log.info(
                        f"   ✅ Verified: Transition {inserted_id} exists in database"
                    )
                else:
                    log.error(
                        f"   ❌ CRITICAL: Transition {inserted_id} NOT found immediately after insert!"
                    )
            else:
                log.warning(f"⚠️ FSM transition log returned no data")

        except Exception as e:
            # Non-fatal: logging shouldn't break the flow
            log.error(f"⚠️ Failed to log FSM transition {from_state} → {to_state}: {e}")
            import traceback

            log.error(f"   Traceback: {traceback.format_exc()}")

    async def create_session(
        self, user_id: str, task_id: str, project_id: str
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
            response = (
                supabase_client.client.table("progress_update_sessions")
                .insert(
                    {
                        "subcontractor_id": user_id,
                        "task_id": task_id,
                        "project_id": project_id,
                        "current_step": "awaiting_action",
                        "fsm_state": "awaiting_action",  # Set initial FSM state
                        "expires_at": (
                            datetime.utcnow()
                            + timedelta(hours=self.SESSION_EXPIRY_HOURS)
                        ).isoformat(),
                    }
                )
                .execute()
            )

            if response.data:
                session_id = response.data[0]["id"]
                log.info(
                    f"✅ Created progress update session {session_id} for user {user_id}"
                )

                # Set expecting_response flag immediately after session creation
                # This ensures FSM context preservation works from the first user message
                await self.update_session(
                    user_id=user_id,
                    fsm_state="awaiting_action",
                    session_metadata={
                        "expecting_response": True,
                        "last_bot_action": "session_started",
                        "available_actions": [
                            "add_comment",
                            "add_photo",
                            "mark_complete",
                        ],
                    },
                )
                log.info(f"🔄 FSM: Set expecting_response=True at session creation")

                # Log transition: idle → awaiting_action
                await self._log_transition(
                    user_id=user_id,
                    session_id=session_id,
                    from_state="idle",
                    to_state="awaiting_action",
                    trigger="start_update",
                    context={"task_id": task_id, "project_id": project_id},
                )

                return session_id
            return None

        except Exception as e:
            log.error(f"Error creating progress update session: {e}")
            # Log failed transition
            await self._log_transition(
                user_id=user_id,
                session_id=None,
                from_state="idle",
                to_state="awaiting_action",
                trigger="start_update",
                success=False,
                error=str(e),
            )
            return None

    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active session for user (if not expired).

        Args:
            user_id: Subcontractor ID

        Returns:
            Session dict if active and not expired, None otherwise
        """
        try:
            response = (
                supabase_client.client.table("progress_update_sessions")
                .select("*")
                .eq("subcontractor_id", user_id)
                .execute()
            )

            if response.data:
                session = response.data[0]
                # Check expiration
                from datetime import timezone

                expires_at = datetime.fromisoformat(
                    session["expires_at"].replace("Z", "+00:00")
                )

                # Ensure timezone-aware comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                if now < expires_at:
                    return session
                else:
                    # Expired, clean up
                    log.info(f"Session expired for user {user_id}, cleaning up")
                    await self.clear_session(user_id, reason="timeout")
            return None

        except Exception as e:
            log.error(f"Error getting progress update session: {e}")
            return None

    async def update_session(self, user_id: str, **updates) -> bool:
        """Update session state fields.

        Args:
            user_id: Subcontractor ID
            **updates: Fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            updates["last_activity"] = datetime.utcnow().isoformat()

            response = (
                supabase_client.client.table("progress_update_sessions")
                .update(updates)
                .eq("subcontractor_id", user_id)
                .execute()
            )

            return bool(response.data)

        except Exception as e:
            log.error(f"Error updating progress update session: {e}")
            return False

    async def add_action(
        self, user_id: str, action_type: str  # 'image', 'comment', 'complete'
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

            # Capture old state before updating
            old_state = session.get("fsm_state", "idle")
            session_id = session.get("id")

            updates = {}
            if action_type == "image":
                updates["images_uploaded"] = session["images_uploaded"] + 1
            elif action_type == "comment":
                updates["comments_added"] = session["comments_added"] + 1
            elif action_type == "complete":
                updates["status_changed"] = True

            # Update FSM state to indicate we're collecting data and expecting response
            # This is critical for context preservation when user responds to options
            new_state = "collecting_data" if action_type != "complete" else "completed"
            updates["fsm_state"] = new_state

            # Set expecting_response flag in metadata so intent classifier knows
            # that bot just showed options and is waiting for user's next action
            session_metadata = session.get("session_metadata", {})
            session_metadata["expecting_response"] = True
            session_metadata["last_bot_action"] = f"added_{action_type}"
            session_metadata["available_actions"] = [
                "add_comment",
                "add_photo",
                "mark_complete",
            ]
            updates["session_metadata"] = session_metadata

            log.info(
                f"🔄 FSM: Setting state='{new_state}', expecting_response=True after {action_type}"
            )

            # Update session
            success = await self.update_session(user_id, **updates)

            # Log transition
            if success:
                await self._log_transition(
                    user_id=user_id,
                    session_id=session_id,
                    from_state=old_state,
                    to_state=new_state,
                    trigger=f"add_{action_type}",
                    context={
                        "action_type": action_type,
                        "images_uploaded": updates.get(
                            "images_uploaded", session.get("images_uploaded")
                        ),
                        "comments_added": updates.get(
                            "comments_added", session.get("comments_added")
                        ),
                        "status_changed": updates.get(
                            "status_changed", session.get("status_changed")
                        ),
                    },
                )
            else:
                await self._log_transition(
                    user_id=user_id,
                    session_id=session_id,
                    from_state=old_state,
                    to_state=new_state,
                    trigger=f"add_{action_type}",
                    success=False,
                    error="Failed to update session",
                )

            return success

        except Exception as e:
            log.error(f"Error recording action in progress update session: {e}")
            await self._log_transition(
                user_id=user_id,
                session_id=session.get("id") if session else None,
                from_state=(
                    session.get("fsm_state", "unknown") if session else "unknown"
                ),
                to_state="collecting_data",
                trigger=f"add_{action_type}",
                success=False,
                error=str(e),
            )
            return False

    async def clear_session(self, user_id: str, reason: str = "user_cancel") -> bool:
        """Delete session for user.

        Args:
            user_id: Subcontractor ID
            reason: Reason for clearing (user_cancel, timeout, error, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get session info before deleting for transition log
            session = await self.get_session(user_id)
            session_id = session.get("id") if session else None
            old_state = session.get("fsm_state", "unknown") if session else "unknown"

            # Log transition to abandoned state BEFORE deleting session
            # (to avoid foreign key constraint violation)
            if session:
                await self._log_transition(
                    user_id=user_id,
                    session_id=session_id,
                    from_state=old_state,
                    to_state="abandoned",
                    trigger=reason,
                    context={"reason": reason},
                )

            # Now delete the session
            response = (
                supabase_client.client.table("progress_update_sessions")
                .delete()
                .eq("subcontractor_id", user_id)
                .execute()
            )

            if response.data:
                log.info(
                    f"🧹 Cleared progress update session for user {user_id} (reason: {reason})"
                )
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
            response = (
                supabase_client.client.table("progress_update_sessions")
                .select("id, subcontractor_id")
                .lt("expires_at", now)
                .execute()
            )

            if not response.data:
                return 0

            cleaned_count = 0
            for session in response.data:
                await self.clear_session(session["subcontractor_id"], reason="expired")
                cleaned_count += 1

            if cleaned_count > 0:
                log.info(
                    f"🧹 Cleaned up {cleaned_count} expired progress update sessions"
                )

            return cleaned_count

        except Exception as e:
            log.error(f"Error cleaning up expired sessions: {e}")
            return 0


# Global instance
progress_update_state = ProgressUpdateState()
