"""Clarification request handlers and timeout cleanup for FSM.

This module provides:
- Clarification request creation and management
- Timeout handling for stale clarifications
- Session recovery on startup
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.config import settings
from src.fsm.models import (
    ClarificationRequest,
    FSMContext,
    SessionState,
)
from src.integrations.supabase import supabase_client
from src.utils.structured_logger import get_structured_logger

logger = get_structured_logger("fsm.handlers")


# ============================================================================
# Configuration
# ============================================================================

CLARIFICATION_TIMEOUT = 5 * 60  # 5 minutes in seconds
SESSION_RECOVERY_THRESHOLD = 30 * 60  # 30 minutes in seconds


# ============================================================================
# Clarification Manager
# ============================================================================


class ClarificationManager:
    """Manages clarification requests for ambiguous intents."""

    def __init__(self):
        """Initialize clarification manager."""
        self.db = supabase_client

    async def create_clarification(
        self, user_id: str, message: str, options: List[str], context: FSMContext
    ) -> Optional[str]:
        """Create a clarification request for user.

        Args:
            user_id: User's WhatsApp ID
            message: Clarification question to send
            options: List of possible options
            context: Current FSM context

        Returns:
            Clarification request ID if created, None otherwise
        """
        try:
            # Check if there's already a pending clarification
            existing = await self.get_pending_clarification(user_id)
            if existing:
                logger.warning("Pending clarification already exists", user_id=user_id)
                return existing.get("id")

            # Create new clarification request
            expires_at = datetime.utcnow() + timedelta(seconds=CLARIFICATION_TIMEOUT)

            clarification_data = {
                "user_id": user_id,
                "message": message,
                "options": options,
                "fsm_context": context.dict(),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat(),
            }

            response = (
                self.db.client.table("fsm_clarification_requests")
                .insert(clarification_data)
                .execute()
            )

            if response.data and len(response.data) > 0:
                clarification_id = response.data[0]["id"]
                logger.info(
                    "Clarification request created",
                    clarification_id=clarification_id,
                    user_id=user_id,
                    expires_at=expires_at.isoformat(),
                )
                return clarification_id
            return None
        except Exception as e:
            logger.error(f"Error creating clarification: {str(e)}", user_id=user_id)
            return None

    async def get_pending_clarification(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get pending clarification for user.

        Args:
            user_id: User's WhatsApp ID

        Returns:
            Clarification request dict if found, None otherwise
        """
        try:
            response = (
                self.db.client.table("fsm_clarification_requests")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(
                f"Error getting pending clarification: {str(e)}", user_id=user_id
            )
            return None

    async def answer_clarification(self, clarification_id: str, answer: str) -> bool:
        """Mark clarification as answered.

        Args:
            clarification_id: Clarification request ID
            answer: User's answer

        Returns:
            True if successful, False otherwise
        """
        try:
            self.db.client.table("fsm_clarification_requests").update(
                {
                    "status": "answered",
                    "answer": answer,
                    "answered_at": datetime.utcnow().isoformat(),
                }
            ).eq("id", clarification_id).execute()

            logger.info(
                "Clarification answered",
                clarification_id=clarification_id,
                answer=answer,
            )
            return True
        except Exception as e:
            logger.error(
                f"Error answering clarification: {str(e)}",
                clarification_id=clarification_id,
            )
            return False

    async def cancel_clarification(self, clarification_id: str) -> bool:
        """Cancel a clarification request.

        Args:
            clarification_id: Clarification request ID

        Returns:
            True if successful, False otherwise
        """
        try:
            self.db.client.table("fsm_clarification_requests").update(
                {
                    "status": "cancelled",
                }
            ).eq("id", clarification_id).execute()

            logger.info("Clarification cancelled", clarification_id=clarification_id)
            return True
        except Exception as e:
            logger.error(
                f"Error cancelling clarification: {str(e)}",
                clarification_id=clarification_id,
            )
            return False

    async def cleanup_expired_clarifications(self) -> int:
        """Mark expired clarifications as expired and abandon sessions.

        Returns:
            Number of clarifications expired
        """
        try:
            # Find expired pending clarifications
            response = (
                self.db.client.table("fsm_clarification_requests")
                .select("id, user_id")
                .eq("status", "pending")
                .lt("expires_at", datetime.utcnow().isoformat())
                .execute()
            )

            if not response.data:
                return 0

            expired_count = len(response.data)
            expired_ids = [item["id"] for item in response.data]
            user_ids = [item["user_id"] for item in response.data]

            # Mark as expired
            self.db.client.table("fsm_clarification_requests").update(
                {"status": "expired"}
            ).in_("id", expired_ids).execute()

            # Abandon associated sessions
            for user_id in user_ids:
                await self._abandon_user_session(user_id, "clarification_timeout")

            logger.info(f"Cleaned up {expired_count} expired clarifications")
            return expired_count
        except Exception as e:
            logger.error(f"Error cleaning up expired clarifications: {str(e)}")
            return 0

    async def _abandon_user_session(self, user_id: str, reason: str) -> None:
        """Internal helper to abandon user's session.

        Args:
            user_id: User's WhatsApp ID
            reason: Abandonment reason
        """
        try:
            self.db.client.table("progress_update_sessions").update(
                {
                    "fsm_state": SessionState.ABANDONED.value,
                    "closure_reason": reason,
                    "last_activity": datetime.utcnow().isoformat(),
                }
            ).eq("subcontractor_id", user_id).execute()

            logger.info(f"Abandoned session for user: {reason}", user_id=user_id)
        except Exception as e:
            logger.error(f"Error abandoning session: {str(e)}", user_id=user_id)


# ============================================================================
# Session Recovery Manager
# ============================================================================


class SessionRecoveryManager:
    """Manages session recovery on startup and during crashes."""

    def __init__(self):
        """Initialize session recovery manager."""
        self.db = supabase_client

    async def recover_orphaned_sessions(self) -> int:
        """Recover orphaned sessions after server restart.

        This marks sessions with old last_activity as abandoned
        to ensure clean state after crashes.

        Returns:
            Number of sessions recovered
        """
        try:
            threshold = datetime.utcnow() - timedelta(
                seconds=SESSION_RECOVERY_THRESHOLD
            )

            # Find sessions with old activity that aren't already terminal
            response = (
                self.db.client.table("progress_update_sessions")
                .select("id, subcontractor_id")
                .lt("last_activity", threshold.isoformat())
                .not_.in_(
                    "fsm_state",
                    [SessionState.COMPLETED.value, SessionState.ABANDONED.value],
                )
                .execute()
            )

            if not response.data:
                logger.info("No orphaned sessions found")
                return 0

            orphaned_count = len(response.data)
            orphaned_ids = [item["id"] for item in response.data]

            # Mark as abandoned
            self.db.client.table("progress_update_sessions").update(
                {
                    "fsm_state": SessionState.ABANDONED.value,
                    "closure_reason": "recovery_orphaned",
                    "last_activity": datetime.utcnow().isoformat(),
                }
            ).in_("id", orphaned_ids).execute()

            logger.info(f"Recovered {orphaned_count} orphaned sessions")
            return orphaned_count
        except Exception as e:
            logger.error(f"Error recovering orphaned sessions: {str(e)}")
            return 0

    async def recover_on_startup(self) -> Dict[str, int]:
        """Run all recovery procedures on startup.

        Returns:
            Dict with recovery statistics
        """
        logger.info("Running session recovery on startup")

        stats = {
            "orphaned_sessions": 0,
            "expired_clarifications": 0,
        }

        # Recover orphaned sessions
        stats["orphaned_sessions"] = await self.recover_orphaned_sessions()

        # Cleanup expired clarifications
        clarification_manager = ClarificationManager()
        stats["expired_clarifications"] = (
            await clarification_manager.cleanup_expired_clarifications()
        )

        logger.info("Session recovery complete", **stats)

        return stats


# ============================================================================
# Background Cleanup Task
# ============================================================================


async def run_cleanup_task():
    """Background task to periodically cleanup expired records.

    This should be called by a scheduler (e.g., every minute).
    In v1, can be run manually or via simple cron job.
    """
    clarification_manager = ClarificationManager()
    await clarification_manager.cleanup_expired_clarifications()

    logger.debug("Cleanup task completed")


# ============================================================================
# Module Initialization
# ============================================================================

# Global instances
clarification_manager = ClarificationManager()
session_recovery_manager = SessionRecoveryManager()
