"""Session management service for conversation tracking."""

from datetime import datetime
from typing import Any, Dict, Optional

from src.integrations.supabase import supabase_client
from src.services.metrics import metrics_service
from src.utils.logger import log


class SessionManagementService:
    """Service for managing conversation sessions.

    Smart session detection based on:
    - Working hours: 6-7 AM to 8 PM
    - Time gap: > 7 hours = new session (one chantier per day)
    - Day boundaries: New day = new session
    """

    def __init__(self):
        """Initialize session management service."""
        self.working_hours_start = 6  # 6 AM
        self.working_hours_end = 20  # 8 PM
        self.session_timeout_hours = 7  # New session after 7 hours

        log.info("Session management service initialized")

    async def get_or_create_session(
        self, subcontractor_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get active session or create new one if needed.

        Uses PostgreSQL function for smart session detection:
        - Checks time since last message
        - Considers working hours
        - Creates new session if needed

        Args:
            subcontractor_id: The subcontractor's ID

        Returns:
            Session dict with id, started_at, etc.
        """
        try:
            log.debug(f"🔍 Calling RPC for user {subcontractor_id[:8]}...")

            # Call PostgreSQL function to get or create session
            session_id = await supabase_client.get_or_create_session_rpc(
                subcontractor_id
            )

            if session_id:
                log.debug(f"✅ RPC returned session: {session_id}")

                # Get full session details
                session = await supabase_client.get_session_by_id(session_id)

                if session:
                    log.info(f"Session {session_id} active for user {subcontractor_id[:8]}...")
                    return session
                else:
                    log.error(f"❌ RPC returned {session_id} but get_session_by_id failed!")
                    log.warning("⚠️ Session returned by RPC doesn't exist, using fallback")

            else:
                log.warning("⚠️ RPC returned None, using fallback")

            # Fallback: Create session manually if function fails
            log.warning("📝 Creating session manually (fallback)")
            return await self._create_session_manual(subcontractor_id)

        except Exception as e:
            log.error(f"❌ Error getting/creating session: {e}")
            log.exception(e)  # Full stack trace for debugging
            # Fallback to manual creation
            log.warning("📝 Using manual session creation due to error")
            return await self._create_session_manual(subcontractor_id)

    async def _create_session_manual(
        self, subcontractor_id: str
    ) -> Optional[Dict[str, Any]]:
        """Manually create a new session (fallback).

        Args:
            subcontractor_id: The subcontractor's ID

        Returns:
            New session dict
        """
        try:
            # End any active sessions first
            await self._end_active_sessions(subcontractor_id)

            # Create new session
            session = await supabase_client.create_session(
                subcontractor_id,
                {
                    "subcontractor_id": subcontractor_id,
                    "started_at": datetime.utcnow().isoformat(),
                    "last_message_at": datetime.utcnow().isoformat(),
                    "status": "active",
                    "message_count": 0,
                },
            )

            if session:
                log.info(
                    f"Created new session {session['id']} for user {subcontractor_id}"
                )
                # Track metrics
                metrics_service.track_session_created(subcontractor_id, session["id"])
                return session

            return None

        except Exception as e:
            log.error(f"Error creating session manually: {e}")
            return None

    async def _end_active_sessions(self, subcontractor_id: str):
        """End all active sessions for a user.

        Args:
            subcontractor_id: The subcontractor's ID
        """
        try:
            success = await supabase_client.end_sessions_for_user(
                subcontractor_id,
                {
                    "status": "ended",
                    "ended_at": datetime.utcnow().isoformat(),
                    "ended_reason": "timeout",
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

            if success:
                log.info(f"Ended active sessions for user {subcontractor_id}")

        except Exception as e:
            log.error(f"Error ending active sessions: {e}")

    async def end_session(
        self,
        session_id: str,
        reason: str = "user_request",
        generate_summary: bool = True,
    ) -> bool:
        """End a session.

        Args:
            session_id: Session ID to end
            reason: Reason for ending ('timeout', 'end_of_day', 'escalation', 'user_request')
            generate_summary: Whether to generate summary

        Returns:
            True if successful
        """
        try:
            update_data = {
                "status": "ended",
                "ended_at": datetime.utcnow().isoformat(),
                "ended_reason": reason,
                "updated_at": datetime.utcnow().isoformat(),
            }

            # Generate summary if requested
            if generate_summary:
                summary = await self._generate_session_summary(session_id)
                if summary:
                    update_data["session_summary"] = summary

            success = await supabase_client.update_session(session_id, update_data)

            if success:
                log.info(f"Ended session {session_id}, reason: {reason}")
            return success

        except Exception as e:
            log.error(f"Error ending session: {e}")
            return False

    async def _generate_session_summary(self, session_id: str) -> Optional[str]:
        """Generate a summary of the session.

        Args:
            session_id: Session ID

        Returns:
            Summary text
        """
        try:
            # Call PostgreSQL function
            summary = await supabase_client.generate_session_summary_rpc(session_id)

            if summary:
                return summary

            # Fallback: Simple summary
            messages = await supabase_client.get_messages_by_session(
                session_id, "direction"
            )

            if messages:
                count = len(messages)
                return f"Session with {count} messages exchanged"

            return None

        except Exception as e:
            log.error(f"Error generating session summary: {e}")
            return None

    async def escalate_session(self, session_id: str) -> bool:
        """Mark session as escalated to human.

        Args:
            session_id: Session ID

        Returns:
            True if successful
        """
        try:
            success = await supabase_client.update_session(
                session_id,
                {"status": "escalated", "updated_at": datetime.utcnow().isoformat()},
            )

            if success:
                log.info(f"Session {session_id} escalated to human")
            return success

        except Exception as e:
            log.error(f"Error escalating session: {e}")
            return False

    async def get_session_stats(self, subcontractor_id: str) -> Dict[str, Any]:
        """Get session statistics for a user.

        Args:
            subcontractor_id: The subcontractor's ID

        Returns:
            Dict with stats
        """
        try:
            # Get all sessions
            sessions = await supabase_client.get_sessions_for_user(subcontractor_id)

            if not sessions:
                return {
                    "total_sessions": 0,
                    "active_sessions": 0,
                    "ended_sessions": 0,
                    "escalated_sessions": 0,
                    "total_messages": 0,
                }

            total = len(sessions)
            active = len([s for s in sessions if s["status"] == "active"])
            ended = len([s for s in sessions if s["status"] == "ended"])
            escalated = len([s for s in sessions if s["status"] == "escalated"])
            total_messages = sum(s.get("message_count", 0) for s in sessions)

            return {
                "total_sessions": total,
                "active_sessions": active,
                "ended_sessions": ended,
                "escalated_sessions": escalated,
                "total_messages": total_messages,
                "avg_messages_per_session": total_messages / total if total > 0 else 0,
            }

        except Exception as e:
            log.error(f"Error getting session stats: {e}")
            return {}


# Global instance
session_service = SessionManagementService()
