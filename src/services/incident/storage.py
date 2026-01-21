"""Incident storage operations for local database."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

import httpx

from src.integrations.supabase import supabase_client
from src.utils.logger import log


class IncidentStorage:
    """Manages incident CRUD operations in local database."""

    async def create_incident(
        self,
        user_id: str,
        project_id: str,
        description: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        severity: str = "normal",
    ) -> Optional[str]:
        """Create a new incident record.

        Args:
            user_id: Subcontractor ID who created the incident
            project_id: Project ID this incident belongs to
            description: Initial description (optional)
            image_urls: Initial images (optional)
            severity: Severity level (low, normal, high, critical)

        Returns:
            Incident ID if created successfully, None otherwise
        """
        try:
            incident_data: Dict[str, Any] = {
                "subcontractor_id": user_id,
                "project_id": project_id,
                "created_by": user_id,
                "severity": severity,
                "status": "open",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            if description:
                incident_data["description"] = description
                incident_data["comments_added"] = 1

            if image_urls:
                incident_data["image_urls"] = image_urls
                incident_data["image_count"] = len(image_urls)

            response = (
                supabase_client.client.table("incidents")
                .insert(incident_data)
                .execute()
            )

            if response.data:
                incident = cast(Dict[str, Any], response.data[0])
                incident_id = cast(str, incident["id"])
                log.info(
                    f"✅ Created incident {incident_id} for user {user_id} "
                    f"(project: {project_id})"
                )
                return incident_id

            return None

        except Exception as e:
            log.error(f"Error creating incident: {e}")
            return None

    async def add_comment_to_incident(self, incident_id: str, comment: str) -> bool:
        """Add a comment to an existing incident.

        Uses the append_incident_comment database function to safely
        concatenate comments.

        Args:
            incident_id: Incident ID
            comment: Comment text to append

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the database function for atomic append
            response = supabase_client.client.rpc(
                "append_incident_comment",
                {"p_incident_id": incident_id, "p_comment": comment},
            ).execute()

            # RPC returns boolean result
            if response.data:
                log.info(
                    f"✅ Added comment to incident {incident_id}: {comment[:50]}..."
                )
                return True

            return False

        except Exception as e:
            log.error(f"Error adding comment to incident {incident_id}: {e}")
            return False

    async def download_and_upload_to_supabase(
        self, incident_id: str, twilio_media_url: str
    ) -> Optional[str]:
        """Download image from Twilio and upload to Supabase storage.

        Args:
            incident_id: Incident ID (used for folder structure)
            twilio_media_url: Twilio media URL

        Returns:
            Supabase public URL if successful, None otherwise
        """
        try:
            from src.config import settings

            log.info(f"📥 Downloading image from Twilio: {twilio_media_url[:80]}...")

            # Twilio media URLs require HTTP Basic Auth (account_sid:auth_token)
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)

            # Download image from Twilio
            async with httpx.AsyncClient() as client:
                response = await client.get(twilio_media_url, auth=auth, timeout=30.0)
                response.raise_for_status()

            image_data = response.content
            content_type = response.headers.get("content-type", "image/jpeg")

            log.info(
                f"   ✅ Downloaded {len(image_data)} bytes ({len(image_data) / 1024:.2f} KB)"
            )

            # Determine file extension
            extension = ".jpg"
            if "png" in content_type.lower():
                extension = ".png"
            elif "jpeg" in content_type.lower() or "jpg" in content_type.lower():
                extension = ".jpg"
            elif "webp" in content_type.lower():
                extension = ".webp"
            elif "gif" in content_type.lower():
                extension = ".gif"

            # Generate unique filename using UUID
            filename = f"{uuid.uuid4()}{extension}"
            # Storage path: incidents/{incident_id}/{filename}
            storage_path = f"{incident_id}/{filename}"

            log.info(f"   📤 Uploading to Supabase storage: incidents/{storage_path}")

            # Upload to Supabase storage bucket "incidents"
            upload_response = supabase_client.client.storage.from_("incidents").upload(
                storage_path,
                image_data,
                {"content-type": content_type, "upsert": "false"},
            )

            # Get public URL
            public_url = supabase_client.client.storage.from_(
                "incidents"
            ).get_public_url(storage_path)

            log.info(f"   ✅ Image uploaded successfully: {public_url}")
            return public_url

        except httpx.HTTPStatusError as e:
            log.error(
                f"   ❌ HTTP error downloading from Twilio: {e.response.status_code}"
            )
            return None
        except Exception as e:
            log.error(f"   ❌ Error downloading/uploading image: {e}")
            import traceback

            log.error(f"   Traceback: {traceback.format_exc()}")
            return None

    async def add_image_to_incident(self, incident_id: str, image_url: str) -> bool:
        """Add an image URL to an existing incident.

        Uses the append_incident_image database function to safely
        append to the image_urls array.

        Args:
            incident_id: Incident ID
            image_url: Image URL to append

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the database function for atomic append
            response = supabase_client.client.rpc(
                "append_incident_image",
                {"p_incident_id": incident_id, "p_image_url": image_url},
            ).execute()

            # RPC returns boolean result
            if response.data:
                log.info(f"✅ Added image to incident {incident_id}: {image_url}")
                return True

            return False

        except Exception as e:
            log.error(f"Error adding image to incident {incident_id}: {e}")
            return False

    async def finalize_incident(self, incident_id: str) -> bool:
        """Mark incident as finalized (no longer collecting data).

        This doesn't change status, just marks it as done collecting data.
        Status can be updated separately (open -> in_progress -> resolved).

        Args:
            incident_id: Incident ID

        Returns:
            True if successful, False otherwise
        """
        try:
            response = (
                supabase_client.client.table("incidents")
                .update({"updated_at": datetime.utcnow().isoformat()})
                .eq("id", incident_id)
                .execute()
            )

            if response.data:
                log.info(f"✅ Finalized incident {incident_id}")
                return True

            return False

        except Exception as e:
            log.error(f"Error finalizing incident {incident_id}: {e}")
            return False

    async def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get incident by ID.

        Args:
            incident_id: Incident ID

        Returns:
            Incident dict if found, None otherwise
        """
        try:
            response = (
                supabase_client.client.table("incidents")
                .select("*")
                .eq("id", incident_id)
                .execute()
            )

            if response.data:
                incident = cast(Dict[str, Any], response.data[0])
                return incident

            return None

        except Exception as e:
            log.error(f"Error getting incident {incident_id}: {e}")
            return None

    async def update_incident_status(
        self, incident_id: str, status: str, resolved_by: Optional[str] = None
    ) -> bool:
        """Update incident status.

        Args:
            incident_id: Incident ID
            status: New status (open, in_progress, resolved, closed)
            resolved_by: User ID who resolved (if status is resolved)

        Returns:
            True if successful, False otherwise
        """
        try:
            updates = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
            }

            if status == "resolved" and resolved_by:
                updates["resolved_by"] = resolved_by
                updates["resolved_at"] = datetime.utcnow().isoformat()

            response = (
                supabase_client.client.table("incidents")
                .update(updates)
                .eq("id", incident_id)
                .execute()
            )

            if response.data:
                log.info(f"✅ Updated incident {incident_id} status to {status}")
                return True

            return False

        except Exception as e:
            log.error(f"Error updating incident {incident_id} status: {e}")
            return False

    async def get_incidents_by_user(
        self, user_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get incidents created by user.

        Args:
            user_id: Subcontractor ID
            limit: Maximum number of incidents to return

        Returns:
            List of incident dicts
        """
        try:
            response = (
                supabase_client.client.table("incidents")
                .select("*")
                .eq("subcontractor_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            if response.data:
                incidents = cast(List[Dict[str, Any]], response.data)
                return incidents

            return []

        except Exception as e:
            log.error(f"Error getting incidents for user {user_id}: {e}")
            return []

    async def get_incidents_by_project(
        self, project_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get incidents for a project.

        Args:
            project_id: Project ID
            limit: Maximum number of incidents to return

        Returns:
            List of incident dicts
        """
        try:
            response = (
                supabase_client.client.table("incidents")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            if response.data:
                incidents = cast(List[Dict[str, Any]], response.data)
                return incidents

            return []

        except Exception as e:
            log.error(f"Error getting incidents for project {project_id}: {e}")
            return []


# Global instance
incident_storage = IncidentStorage()
