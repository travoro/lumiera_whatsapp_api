"""Session management service for conversation tracking."""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from src.integrations.supabase import supabase_client
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

    async def get_or_create_session(self, subcontractor_id: str) -> Optional[Dict[str, Any]]:
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
            # Call PostgreSQL function to get or create session
            result = supabase_client.client.rpc(
                'get_or_create_session',
                {'p_subcontractor_id': subcontractor_id}
            ).execute()

            if result.data:
                session_id = result.data

                # Get full session details
                session_response = supabase_client.client.table('conversation_sessions').select('*').eq(
                    'id', session_id
                ).execute()

                if session_response.data and len(session_response.data) > 0:
                    session = session_response.data[0]
                    log.info(f"Session {session_id} active for user {subcontractor_id}")
                    return session

            # Fallback: Create session manually if function fails
            log.warning("PostgreSQL function failed, creating session manually")
            return await self._create_session_manual(subcontractor_id)

        except Exception as e:
            log.error(f"Error getting/creating session: {e}")
            # Fallback to manual creation
            return await self._create_session_manual(subcontractor_id)

    async def _create_session_manual(self, subcontractor_id: str) -> Optional[Dict[str, Any]]:
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
            response = supabase_client.client.table('conversation_sessions').insert({
                'subcontractor_id': subcontractor_id,
                'started_at': datetime.utcnow().isoformat(),
                'last_message_at': datetime.utcnow().isoformat(),
                'status': 'active',
                'message_count': 0
            }).execute()

            if response.data and len(response.data) > 0:
                session = response.data[0]
                log.info(f"Created new session {session['id']} for user {subcontractor_id}")
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
            supabase_client.client.table('conversation_sessions').update({
                'status': 'ended',
                'ended_at': datetime.utcnow().isoformat(),
                'ended_reason': 'timeout',
                'updated_at': datetime.utcnow().isoformat()
            }).eq('subcontractor_id', subcontractor_id).eq('status', 'active').execute()

            log.info(f"Ended active sessions for user {subcontractor_id}")

        except Exception as e:
            log.error(f"Error ending active sessions: {e}")

    async def end_session(
        self,
        session_id: str,
        reason: str = 'user_request',
        generate_summary: bool = True
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
                'status': 'ended',
                'ended_at': datetime.utcnow().isoformat(),
                'ended_reason': reason,
                'updated_at': datetime.utcnow().isoformat()
            }

            # Generate summary if requested
            if generate_summary:
                summary = await self._generate_session_summary(session_id)
                if summary:
                    update_data['session_summary'] = summary

            supabase_client.client.table('conversation_sessions').update(
                update_data
            ).eq('id', session_id).execute()

            log.info(f"Ended session {session_id}, reason: {reason}")
            return True

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
            result = supabase_client.client.rpc(
                'generate_session_summary',
                {'p_session_id': session_id}
            ).execute()

            if result.data:
                return result.data

            # Fallback: Simple summary
            messages = supabase_client.client.table('messages').select(
                'direction'
            ).eq('session_id', session_id).execute()

            if messages.data:
                count = len(messages.data)
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
            supabase_client.client.table('conversation_sessions').update({
                'status': 'escalated',
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', session_id).execute()

            log.info(f"Session {session_id} escalated to human")
            return True

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
            sessions = supabase_client.client.table('conversation_sessions').select(
                '*'
            ).eq('subcontractor_id', subcontractor_id).execute()

            if not sessions.data:
                return {
                    'total_sessions': 0,
                    'active_sessions': 0,
                    'ended_sessions': 0,
                    'escalated_sessions': 0,
                    'total_messages': 0
                }

            total = len(sessions.data)
            active = len([s for s in sessions.data if s['status'] == 'active'])
            ended = len([s for s in sessions.data if s['status'] == 'ended'])
            escalated = len([s for s in sessions.data if s['status'] == 'escalated'])
            total_messages = sum(s.get('message_count', 0) for s in sessions.data)

            return {
                'total_sessions': total,
                'active_sessions': active,
                'ended_sessions': ended,
                'escalated_sessions': escalated,
                'total_messages': total_messages,
                'avg_messages_per_session': total_messages / total if total > 0 else 0
            }

        except Exception as e:
            log.error(f"Error getting session stats: {e}")
            return {}


# Global instance
session_service = SessionManagementService()
