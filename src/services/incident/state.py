"""Incident session state management."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast

from src.integrations.supabase import supabase_client
from src.utils.logger import log


class IncidentState:
    """Manages incident conversation session state."""

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
                        "session_type": "incident",  # Identify this as incident session
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

            if result and result.data:
                inserted_data = cast(Dict[str, Any], result.data[0])
                inserted_id = cast(str, inserted_data["id"])
                log.info(
                    f"📊 FSM Transition logged: {from_state} → {to_state} "
                    f"(trigger: {trigger}, session: {session_id}, id: {inserted_id})"
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
                        f"   ❌ CRITICAL: Transition {inserted_id} NOT found "
                        f"immediately after insert!"
                    )
            else:
                log.warning("⚠️ FSM transition log returned no data")

        except Exception as e:
            # Non-fatal: logging shouldn't break the flow
            log.error(f"⚠️ Failed to log FSM transition {from_state} → {to_state}: {e}")
            import traceback

            log.error(f"   Traceback: {traceback.format_exc()}")

    async def create_session(
        self, user_id: str, project_id: str, incident_id: str
    ) -> Optional[str]:
        """Create a new incident session.

        Uses UPSERT to atomically replace any existing session for this user.
        This prevents race conditions from concurrent session creation.

        Args:
            user_id: Subcontractor ID
            project_id: Project ID
            incident_id: Incident ID being reported

        Returns:
            Session ID if created successfully, None otherwise
        """
        try:
            # Use UPSERT to atomically replace existing session
            # Database has UNIQUE(subcontractor_id) constraint
            response = (
                supabase_client.client.table("incident_sessions")
                .upsert(
                    {
                        "subcontractor_id": user_id,
                        "incident_id": incident_id,
                        "project_id": project_id,
                        "current_step": "collecting_data",
                        "fsm_state": "collecting_data",
                        "expires_at": (
                            datetime.utcnow()
                            + timedelta(hours=self.SESSION_EXPIRY_HOURS)
                        ).isoformat(),
                        "images_uploaded": 0,
                        "comments_added": 0,
                        "created_at": datetime.utcnow().isoformat(),
                        "last_activity": datetime.utcnow().isoformat(),
                    },
                    on_conflict="subcontractor_id",
                )
                .execute()
            )

            if response.data:
                session_data = cast(Dict[str, Any], response.data[0])
                session_id = cast(str, session_data["id"])
                log.info(
                    f"✅ Created/updated incident session {session_id} for user {user_id} "
                    f"(incident: {incident_id})"
                )

                # Set expecting_response flag immediately after session creation
                await self.update_session(
                    user_id=user_id,
                    fsm_state="collecting_data",
                    session_metadata={
                        "expecting_response": True,
                        "last_bot_action": "session_started",
                        "available_actions": [
                            "add_comment",
                            "add_image",
                            "finalize",
                        ],
                    },
                )
                log.info("🔄 FSM: Set expecting_response=True at session creation")

                # Log transition: idle → collecting_data
                await self._log_transition(
                    user_id=user_id,
                    session_id=session_id,
                    from_state="idle",
                    to_state="collecting_data",
                    trigger="start_incident",
                    context={"incident_id": incident_id, "project_id": project_id},
                )

                return session_id
            return None

        except Exception as e:
            log.error(f"Error creating incident session: {e}")
            await self._log_transition(
                user_id=user_id,
                session_id=None,
                from_state="idle",
                to_state="collecting_data",
                trigger="start_incident",
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
                supabase_client.client.table("incident_sessions")
                .select("*")
                .eq("subcontractor_id", user_id)
                .execute()
            )

            if response.data:
                session = cast(Dict[str, Any], response.data[0])
                # Check expiration
                expires_at_str = cast(str, session["expires_at"])
                expires_at = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )

                # Ensure timezone-aware comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                if now < expires_at:
                    return session
                else:
                    # Expired, clean up
                    log.info(
                        f"Incident session expired for user {user_id}, cleaning up"
                    )
                    await self.clear_session(user_id, reason="timeout")
            return None

        except Exception as e:
            log.error(f"Error getting incident session: {e}")
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
                supabase_client.client.table("incident_sessions")
                .update(updates)
                .eq("subcontractor_id", user_id)
                .execute()
            )

            return bool(response.data)

        except Exception as e:
            log.error(f"Error updating incident session: {e}")
            return False

    async def add_action(
        self, user_id: str, action_type: str  # 'image', 'comment', 'finalize'
    ) -> bool:
        """Record that user completed an action.

        Args:
            user_id: Subcontractor ID
            action_type: Type of action ('image', 'comment', 'finalize')

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

            # Update FSM state
            new_state = "completed" if action_type == "finalize" else "collecting_data"
            updates["fsm_state"] = new_state

            # Set expecting_response flag in metadata
            session_metadata = session.get("session_metadata", {})
            session_metadata["expecting_response"] = True
            session_metadata["last_bot_action"] = f"added_{action_type}"
            session_metadata["available_actions"] = [
                "add_comment",
                "add_image",
                "finalize",
            ]
            updates["session_metadata"] = session_metadata

            log.info(
                f"🔄 FSM: Setting state='{new_state}', expecting_response=True "
                f"after {action_type}"
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
            log.error(f"Error recording action in incident session: {e}")
            session = await self.get_session(user_id)
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
                supabase_client.client.table("incident_sessions")
                .delete()
                .eq("subcontractor_id", user_id)
                .execute()
            )

            if response.data:
                log.info(
                    f"🧹 Cleared incident session for user {user_id} (reason: {reason})"
                )
            return True

        except Exception as e:
            log.error(f"Error clearing incident session: {e}")
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
                supabase_client.client.table("incident_sessions")
                .select("id, subcontractor_id")
                .lt("expires_at", now)
                .execute()
            )

            if not response.data:
                return 0

            cleaned_count = 0
            sessions = cast(list[Dict[str, Any]], response.data)
            for session in sessions:
                subcontractor_id = cast(str, session["subcontractor_id"])
                await self.clear_session(subcontractor_id, reason="expired")
                cleaned_count += 1

            if cleaned_count > 0:
                log.info(f"🧹 Cleaned up {cleaned_count} expired incident sessions")

            return cleaned_count

        except Exception as e:
            log.error(f"Error cleaning up expired incident sessions: {e}")
            return 0


# Global instance
incident_state = IncidentState()
