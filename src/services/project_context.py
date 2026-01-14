"""Project context service for managing active project state."""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from src.integrations.supabase import supabase_client
from src.utils.logger import log


class ProjectContextService:
    """Service for managing subcontractor's active project context.

    Tracks which project a subcontractor is currently working on,
    with automatic expiration after 7 hours of inactivity.
    """

    EXPIRATION_HOURS = 7

    def __init__(self):
        """Initialize project context service."""
        self.client = supabase_client
        log.info("Project context service initialized")

    async def get_active_project(self, user_id: str) -> Optional[str]:
        """Get the currently active project for a subcontractor.

        Returns None if:
        - No active project is set
        - Active project has expired (>7 hours since last activity)

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            Project ID (UUID) if active and not expired, None otherwise
        """
        try:
            # Get subcontractor data
            user = self.client.get_user(user_id)
            if not user:
                return None

            active_project_id = user.get("active_project_id")
            last_activity = user.get("active_project_last_activity")

            # No active project set
            if not active_project_id:
                return None

            # Check if expired
            if self._is_expired(last_activity):
                log.info(f"Active project context expired for user {user_id}")
                await self.clear_active_project(user_id)
                return None

            log.debug(f"Active project for user {user_id}: {active_project_id}")
            return active_project_id

        except Exception as e:
            log.error(f"Error getting active project for user {user_id}: {e}")
            return None

    async def set_active_project(
        self,
        user_id: str,
        project_id: str,
        project_name: Optional[str] = None
    ) -> bool:
        """Set or update the active project for a subcontractor.

        Resets the activity timestamp to NOW.

        Args:
            user_id: Subcontractor ID (UUID)
            project_id: Project ID (UUID) to set as active
            project_name: Optional project name for logging

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.client.table("subcontractors").update({
                "active_project_id": project_id,
                "active_project_last_activity": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()

            if response.data and len(response.data) > 0:
                project_display = project_name if project_name else project_id
                log.info(
                    f"🎯 Set active project for user {user_id}: {project_display}"
                )
                return True
            else:
                log.warning(f"Failed to set active project for user {user_id}")
                return False

        except Exception as e:
            log.error(f"Error setting active project for user {user_id}: {e}")
            return False

    async def touch_activity(self, user_id: str) -> bool:
        """Update the last activity timestamp for the active project context.

        Call this whenever the user performs a project-related action
        to keep the context alive.

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Only update if there's an active project
            user = self.client.get_user(user_id)
            if not user or not user.get("active_project_id"):
                return False

            response = self.client.client.table("subcontractors").update({
                "active_project_last_activity": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()

            if response.data and len(response.data) > 0:
                log.debug(f"Updated active project activity for user {user_id}")
                return True
            return False

        except Exception as e:
            log.error(f"Error touching active project activity for user {user_id}: {e}")
            return False

    async def clear_active_project(self, user_id: str) -> bool:
        """Clear the active project context for a subcontractor.

        Call this when:
        - User explicitly finishes work on a project
        - Context has expired
        - User switches to a different project (will be followed by set_active_project)

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.client.table("subcontractors").update({
                "active_project_id": None,
                "active_project_last_activity": None,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()

            if response.data and len(response.data) > 0:
                log.info(f"🧹 Cleared active project context for user {user_id}")
                return True
            return False

        except Exception as e:
            log.error(f"Error clearing active project for user {user_id}: {e}")
            return False

    async def get_active_project_with_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active project with full details (name, status, etc.).

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            Project dict if active and not expired, None otherwise
        """
        try:
            project_id = await self.get_active_project(user_id)
            if not project_id:
                return None

            # Get project details from Supabase
            response = self.client.client.table("projects").select("*").eq(
                "id", project_id
            ).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None

        except Exception as e:
            log.error(f"Error getting active project details for user {user_id}: {e}")
            return None

    async def get_active_task(self, user_id: str) -> Optional[str]:
        """Get the currently active task for a subcontractor.

        Returns None if:
        - No active task is set
        - Active task has expired (>7 hours since last activity)

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            Task ID (UUID) if active and not expired, None otherwise
        """
        try:
            # Get subcontractor data
            user = self.client.get_user(user_id)
            if not user:
                return None

            active_task_id = user.get("active_task_id")
            last_activity = user.get("active_task_last_activity")

            # No active task set
            if not active_task_id:
                return None

            # Check if expired
            if self._is_expired(last_activity):
                log.info(f"Active task context expired for user {user_id}")
                await self.clear_active_task(user_id)
                return None

            log.debug(f"Active task for user {user_id}: {active_task_id}")
            return active_task_id

        except Exception as e:
            log.error(f"Error getting active task for user {user_id}: {e}")
            return None

    async def set_active_task(
        self,
        user_id: str,
        task_id: str,
        task_title: Optional[str] = None
    ) -> bool:
        """Set or update the active task for a subcontractor.

        Resets the activity timestamp to NOW.

        Args:
            user_id: Subcontractor ID (UUID)
            task_id: Task ID (UUID) to set as active
            task_title: Optional task title for logging

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.client.table("subcontractors").update({
                "active_task_id": task_id,
                "active_task_last_activity": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()

            if response.data and len(response.data) > 0:
                task_display = task_title if task_title else task_id
                log.info(
                    f"🎯 Set active task for user {user_id}: {task_display}"
                )
                return True
            else:
                log.warning(f"Failed to set active task for user {user_id}")
                return False

        except Exception as e:
            log.error(f"Error setting active task for user {user_id}: {e}")
            return False

    async def clear_active_task(self, user_id: str) -> bool:
        """Clear the active task context for a subcontractor.

        Args:
            user_id: Subcontractor ID (UUID)

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.client.table("subcontractors").update({
                "active_task_id": None,
                "active_task_last_activity": None,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()

            if response.data and len(response.data) > 0:
                log.info(f"🧹 Cleared active task context for user {user_id}")
                return True
            return False

        except Exception as e:
            log.error(f"Error clearing active task for user {user_id}: {e}")
            return False

    def _is_expired(self, last_activity: Optional[str]) -> bool:
        """Check if the active project context has expired.

        Args:
            last_activity: ISO format timestamp string

        Returns:
            True if expired (>7 hours) or no activity, False otherwise
        """
        if not last_activity:
            return True

        try:
            # Parse timestamp
            if isinstance(last_activity, str):
                last_activity_dt = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
            else:
                last_activity_dt = last_activity

            # Check if more than 7 hours have passed
            time_since_activity = datetime.utcnow() - last_activity_dt.replace(tzinfo=None)
            return time_since_activity > timedelta(hours=self.EXPIRATION_HOURS)

        except Exception as e:
            log.error(f"Error parsing last activity timestamp: {e}")
            return True  # Treat parsing errors as expired

    async def cleanup_expired_contexts(self) -> int:
        """Clean up expired active project contexts across all subcontractors.

        This can be run periodically as a maintenance task.

        Returns:
            Number of contexts cleared
        """
        try:
            # Get all subcontractors with active projects
            response = self.client.client.table("subcontractors").select(
                "id, active_project_id, active_project_last_activity"
            ).not_.is_("active_project_id", "null").execute()

            if not response.data:
                return 0

            cleared_count = 0
            for user in response.data:
                if self._is_expired(user.get("active_project_last_activity")):
                    await self.clear_active_project(user["id"])
                    cleared_count += 1

            if cleared_count > 0:
                log.info(f"🧹 Cleaned up {cleared_count} expired active project contexts")

            return cleared_count

        except Exception as e:
            log.error(f"Error cleaning up expired contexts: {e}")
            return 0


# Global instance
project_context_service = ProjectContextService()
