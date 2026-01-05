"""User context service for personalization and learned facts."""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from src.integrations.supabase import supabase_client
from src.utils.logger import log


class UserContextService:
    """Service for managing user context, preferences, and learned facts."""

    def __init__(self):
        """Initialize user context service."""
        log.info("User context service initialized")

    async def set_context(
        self,
        subcontractor_id: str,
        key: str,
        value: str,
        context_type: str = 'fact',
        source: str = 'system',
        confidence: float = 1.0,
        expires_in_hours: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Set or update user context.

        Args:
            subcontractor_id: User ID
            key: Context key (e.g., 'current_project')
            value: Context value
            context_type: Type of context ('preference', 'fact', 'entity', 'state')
            source: Source of context ('user_stated', 'inferred', 'system', 'tool')
            confidence: Confidence level (0.0 to 1.0)
            expires_in_hours: Optional expiry in hours
            metadata: Optional metadata dict

        Returns:
            True if successful
        """
        try:
            data = {
                'subcontractor_id': subcontractor_id,
                'context_key': key,
                'context_value': value,
                'context_type': context_type,
                'source': source,
                'confidence': confidence,
                'metadata': metadata or {},
                'updated_at': datetime.utcnow().isoformat()
            }

            if expires_in_hours:
                expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
                data['expires_at'] = expires_at.isoformat()

            # Upsert (insert or update)
            supabase_client.client.table('user_context').upsert(
                data,
                on_conflict='subcontractor_id,context_key'
            ).execute()

            log.info(f"Set context '{key}' = '{value}' for user {subcontractor_id}")
            return True

        except Exception as e:
            log.error(f"Error setting user context: {e}")
            return False

    async def get_context(
        self,
        subcontractor_id: str,
        key: str
    ) -> Optional[str]:
        """Get user context value.

        Args:
            subcontractor_id: User ID
            key: Context key

        Returns:
            Context value or None
        """
        try:
            response = supabase_client.client.table('user_context').select(
                'context_value'
            ).eq('subcontractor_id', subcontractor_id).eq(
                'context_key', key
            ).execute()

            if response.data and len(response.data) > 0:
                # Check if expired
                context = response.data[0]
                if 'expires_at' in context and context['expires_at']:
                    expires_at = datetime.fromisoformat(context['expires_at'].replace('Z', '+00:00'))
                    if datetime.utcnow() > expires_at:
                        # Context expired
                        await self.delete_context(subcontractor_id, key)
                        return None

                return context['context_value']

            return None

        except Exception as e:
            log.error(f"Error getting user context: {e}")
            return None

    async def get_all_context(
        self,
        subcontractor_id: str,
        context_type: Optional[str] = None
    ) -> Dict[str, str]:
        """Get all context for a user.

        Args:
            subcontractor_id: User ID
            context_type: Optional filter by type

        Returns:
            Dict of context key-value pairs
        """
        try:
            query = supabase_client.client.table('user_context').select('*').eq(
                'subcontractor_id', subcontractor_id
            )

            if context_type:
                query = query.eq('context_type', context_type)

            response = query.execute()

            if not response.data:
                return {}

            # Filter out expired contexts
            now = datetime.utcnow()
            context_dict = {}

            for item in response.data:
                # Check expiry
                if item.get('expires_at'):
                    expires_at = datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00'))
                    if now > expires_at:
                        continue  # Skip expired

                context_dict[item['context_key']] = item['context_value']

            return context_dict

        except Exception as e:
            log.error(f"Error getting all context: {e}")
            return {}

    async def delete_context(
        self,
        subcontractor_id: str,
        key: str
    ) -> bool:
        """Delete user context.

        Args:
            subcontractor_id: User ID
            key: Context key

        Returns:
            True if successful
        """
        try:
            supabase_client.client.table('user_context').delete().eq(
                'subcontractor_id', subcontractor_id
            ).eq('context_key', key).execute()

            log.info(f"Deleted context '{key}' for user {subcontractor_id}")
            return True

        except Exception as e:
            log.error(f"Error deleting user context: {e}")
            return False

    async def cleanup_expired(self) -> int:
        """Clean up expired contexts.

        Returns:
            Number of contexts deleted
        """
        try:
            # Call PostgreSQL function
            result = supabase_client.client.rpc('cleanup_expired_context').execute()

            if result.data is not None:
                count = result.data
                log.info(f"Cleaned up {count} expired contexts")
                return count

            return 0

        except Exception as e:
            log.error(f"Error cleaning up expired contexts: {e}")
            return 0

    async def get_context_for_agent(
        self,
        subcontractor_id: str
    ) -> str:
        """Get formatted context string for agent.

        Args:
            subcontractor_id: User ID

        Returns:
            Formatted context string
        """
        try:
            contexts = await self.get_all_context(subcontractor_id)

            if not contexts:
                return ""

            # Format for agent
            lines = []
            for key, value in contexts.items():
                # Convert key to readable format
                readable_key = key.replace('_', ' ').title()
                lines.append(f"- {readable_key}: {value}")

            return "\n".join(lines)

        except Exception as e:
            log.error(f"Error getting context for agent: {e}")
            return ""


# Global instance
user_context_service = UserContextService()
