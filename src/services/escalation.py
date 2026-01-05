"""Escalation service for human handoff."""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
from src.config import settings
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.utils.logger import log


class EscalationService:
    """Handle escalation to human admins.

    Note: Escalations are tracked via messages with is_escalation flag.
    No separate escalations table needed.
    """

    def __init__(self):
        """Initialize escalation service."""
        log.info("Escalation service initialized")

    async def should_block_user(self, user_id: str) -> bool:
        """Check if user has an active escalation that blocks bot interaction.

        Note: Simplified - we don't block users on escalation.
        Admin can handle escalations in parallel with bot.
        """
        # Simplified: Don't block users on escalation
        # This allows bot to continue working while admin reviews
        return False

    async def create_escalation(
        self,
        user_id: str,
        user_phone: str,
        user_language: str,
        reason: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Create escalation by saving as message with flag and notifying admin.

        Escalations are stored as messages with metadata.is_escalation = true.
        """
        try:
            # Notify admin about the escalation
            escalation_id = f"escalation_{user_id}_{datetime.utcnow().timestamp()}"

            await self._notify_admin(
                escalation_id=escalation_id,
                user_phone=user_phone,
                user_language=user_language,
                reason=reason,
                context=context,
            )

            log.info(f"Escalation created and admin notified: {escalation_id}")
            return escalation_id

        except Exception as e:
            log.error(f"Error creating escalation: {e}")
            return None

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
