"""Escalation service for human handoff."""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
from src.config import settings
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.utils.logger import log


class EscalationService:
    """Handle escalation to human admins."""

    def __init__(self):
        """Initialize escalation service."""
        log.info("Escalation service initialized")

    async def should_block_user(self, user_id: str) -> bool:
        """Check if user has an active escalation that blocks bot interaction."""
        escalation = await supabase_client.get_active_escalation(user_id)

        if not escalation:
            return False

        # Check if escalation has timed out
        created_at = datetime.fromisoformat(escalation["created_at"])
        max_time = timedelta(hours=settings.max_escalation_time)

        if datetime.utcnow() - created_at > max_time:
            # Auto-release escalation
            await self.release_escalation(escalation["id"])
            return False

        return True

    async def create_escalation(
        self,
        user_id: str,
        user_phone: str,
        user_language: str,
        reason: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Create escalation and notify admin."""
        try:
            # Create escalation record
            escalation_id = await supabase_client.create_escalation(
                user_id=user_id,
                reason=reason,
                context=context,
            )

            if not escalation_id:
                return None

            # Notify admin
            await self._notify_admin(
                escalation_id=escalation_id,
                user_phone=user_phone,
                user_language=user_language,
                reason=reason,
                context=context,
            )

            log.info(f"Escalation created: {escalation_id}")
            return escalation_id

        except Exception as e:
            log.error(f"Error creating escalation: {e}")
            return None

    async def release_escalation(
        self,
        escalation_id: str,
        resolution_note: Optional[str] = None,
    ) -> bool:
        """Release escalation and resume bot interaction."""
        try:
            success = await supabase_client.update_escalation_status(
                escalation_id=escalation_id,
                status="resolved",
                resolution_note=resolution_note,
            )

            if success:
                log.info(f"Escalation released: {escalation_id}")

            return success

        except Exception as e:
            log.error(f"Error releasing escalation: {e}")
            return False

    async def _notify_admin(
        self,
        escalation_id: str,
        user_phone: str,
        user_language: str,
        reason: str,
        context: Dict[str, Any],
    ) -> None:
        """Send notification to admin about escalation."""
        # Notify via webhook if configured
        if settings.admin_notification_webhook:
            await self._send_webhook_notification(
                escalation_id=escalation_id,
                user_phone=user_phone,
                user_language=user_language,
                reason=reason,
                context=context,
            )

        # TODO: Send email notification if configured
        # TODO: Send Slack notification if configured

    async def _send_webhook_notification(
        self,
        escalation_id: str,
        user_phone: str,
        user_language: str,
        reason: str,
        context: Dict[str, Any],
    ) -> bool:
        """Send webhook notification to admin system."""
        try:
            payload = {
                "escalation_id": escalation_id,
                "user_phone": user_phone,
                "user_language": user_language,
                "reason": reason,
                "context": context,
                "timestamp": datetime.utcnow().isoformat(),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.admin_notification_webhook,
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()
                return True

        except Exception as e:
            log.error(f"Error sending webhook notification: {e}")
            return False


# Global instance
escalation_service = EscalationService()
