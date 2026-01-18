"""Metrics tracking service for monitoring session management and performance."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from src.utils.logger import log


class MetricsService:
    """Service for tracking and reporting application metrics.

    Focuses on session management metrics to detect race conditions,
    context loss, and performance issues.
    """

    def __init__(self):
        """Initialize metrics service."""
        # Counters (reset on service restart)
        self.session_created_count = 0
        self.session_reused_count = 0
        self.context_loss_count = 0

        # Per-user session creation tracking (for rate limiting detection)
        # Format: {user_id: [timestamp1, timestamp2, ...]}
        self._user_session_creates: Dict[str, List[datetime]] = defaultdict(list)
        self._window_seconds = 10  # Track creates in 10-second windows

        log.info("Metrics service initialized")

    def track_session_created(self, user_id: str, session_id: str) -> None:
        """Track a new session creation.

        Args:
            user_id: User ID
            session_id: Created session ID
        """
        self.session_created_count += 1

        # Track timestamp for rate detection
        now = datetime.utcnow()
        self._user_session_creates[user_id].append(now)

        # Clean old timestamps (older than window)
        cutoff = now - timedelta(seconds=self._window_seconds)
        self._user_session_creates[user_id] = [
            ts for ts in self._user_session_creates[user_id] if ts > cutoff
        ]

        # Check for suspicious rate (>1 session in window)
        recent_creates = len(self._user_session_creates[user_id])
        if recent_creates > 1:
            log.warning(
                f"⚠️ METRIC ALERT: User {user_id} created {recent_creates} sessions "
                f"in {self._window_seconds}s - possible race condition!"
            )
            log.warning(
                f"   Session IDs: {session_id} (and {recent_creates - 1} others)"
            )

    def track_session_reused(self, user_id: str, session_id: str) -> None:
        """Track a session being reused (passed through call chain).

        Args:
            user_id: User ID
            session_id: Reused session ID
        """
        self.session_reused_count += 1
        log.debug(f"✅ METRIC: Session reused for user {user_id}: {session_id}")

    def track_context_loss(
        self, user_id: str, expected_context: str, actual_context: str
    ) -> None:
        """Track a context loss incident.

        Args:
            user_id: User ID
            expected_context: What context was expected
            actual_context: What context was actually found
        """
        self.context_loss_count += 1
        log.error(
            f"❌ METRIC ALERT: Context loss for user {user_id}! "
            f"Expected: {expected_context}, Got: {actual_context}"
        )

    def get_session_reuse_ratio(self) -> float:
        """Calculate the ratio of session reuses to creates.

        A high ratio (>0.95) indicates Phase 2 is working correctly.

        Returns:
            Ratio (0.0-1.0), or 0.0 if no sessions created yet
        """
        total = self.session_created_count + self.session_reused_count
        if total == 0:
            return 0.0
        return self.session_reused_count / total

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked metrics.

        Returns:
            Dict with metric counts and ratios
        """
        reuse_ratio = self.get_session_reuse_ratio()

        return {
            "sessions_created": self.session_created_count,
            "sessions_reused": self.session_reused_count,
            "session_reuse_ratio": reuse_ratio,
            "context_loss_incidents": self.context_loss_count,
            "reuse_ratio_healthy": reuse_ratio >= 0.95,  # Target: 95%+ reuse
        }

    def log_metrics_summary(self) -> None:
        """Log a summary of current metrics."""
        metrics = self.get_metrics_summary()

        log.info("📊 Session Metrics Summary:")
        log.info(f"   Sessions created: {metrics['sessions_created']}")
        log.info(f"   Sessions reused: {metrics['sessions_reused']}")
        log.info(f"   Reuse ratio: {metrics['session_reuse_ratio']:.2%}")
        log.info(
            f"   Context loss incidents: {metrics['context_loss_incidents']}"
        )

        if metrics["reuse_ratio_healthy"]:
            log.info("   ✅ Reuse ratio is healthy (≥95%)")
        else:
            log.warning(
                "   ⚠️ Reuse ratio below target (<95%) - investigate session handling"
            )

    def reset_metrics(self) -> None:
        """Reset all metrics counters.

        Useful for testing or after addressing issues.
        """
        self.session_created_count = 0
        self.session_reused_count = 0
        self.context_loss_count = 0
        self._user_session_creates.clear()
        log.info("📊 Metrics reset")


# Global instance
metrics_service = MetricsService()
