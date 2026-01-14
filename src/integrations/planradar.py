"""PlanRadar API client for project and task management."""
from typing import Optional, List, Dict, Any
import httpx
from src.config import settings
from src.utils.logger import log


class PlanRadarClient:
    """Client for interacting with PlanRadar API."""

    def __init__(self):
        """Initialize PlanRadar client."""
        self.base_url = settings.planradar_api_url
        self.api_key = settings.planradar_api_key
        self.account_id = settings.planradar_account_id
        self.headers = {
            "X-PlanRadar-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        log.info("PlanRadar client initialized")

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to PlanRadar API."""
        url = f"{self.base_url}/{endpoint}"

        # Log the request details
        log.info(f"🌐 PlanRadar API Request: {method} {endpoint}")
        if params:
            log.info(f"   📝 Query params: {params}")
        if data:
            log.info(f"   📦 Request body: {data}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data,
                    params=params,
                    timeout=30.0,
                )

                # Log response status
                log.info(f"   ✅ Response: {response.status_code}")

                response.raise_for_status()
                result = response.json()

                # Log response summary
                if isinstance(result, dict):
                    if "data" in result:
                        data_count = len(result["data"]) if isinstance(result["data"], list) else 1
                        log.info(f"   📊 Response data: {data_count} item(s)")
                    else:
                        log.info(f"   📊 Response keys: {list(result.keys())}")

                return result
        except httpx.HTTPStatusError as e:
            # Differentiate between rate limit and other errors
            if e.response.status_code == 429:
                log.warning(f"   ⚠️ PlanRadar API rate limit (429)")
                log.warning(f"   URL was: {url}")
                # Return special error structure for rate limits
                return {"_rate_limited": True, "error": "Rate limit exceeded"}
            else:
                log.error(f"   ❌ PlanRadar API HTTP error: {e.response.status_code} {e.response.reason_phrase}")
                log.error(f"   URL was: {url}")
                try:
                    error_body = e.response.json()
                    log.error(f"   Error details: {error_body}")
                except:
                    log.error(f"   Error text: {e.response.text[:200]}")
                return None
        except httpx.HTTPError as e:
            log.error(f"   ❌ PlanRadar API error: {type(e).__name__}: {e}")
            log.error(f"   URL was: {url}")
            return None

    async def list_tasks(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks (tickets) for a specific PlanRadar project.

        Args:
            project_id: The PlanRadar project ID (not the internal DB ID)
            status: Optional status filter

        Returns:
            List of tasks/tickets for the project
        """
        log.info(f"📋 list_tasks called: project_id={project_id[:8]}..., status={status}")

        # PlanRadar v2 API requires customer_id in path
        endpoint = f"{self.account_id}/projects/{project_id}/tickets"
        params = {}
        if status:
            params["status"] = status

        result = await self._request("GET", endpoint, params=params)
        # Check for rate limit error
        if result and result.get("_rate_limited"):
            raise Exception("PlanRadar API rate limit exceeded. Please try again in a few moments.")
        # PlanRadar uses JSON:API format with nested "data" array
        tasks = result.get("data", []) if result else []
        log.info(f"   ✅ Retrieved {len(tasks)} tasks")
        return tasks

    async def get_task(self, task_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific task.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID (required for API v2)
        """
        log.info(f"📄 get_task called: task_id={task_id[:8]}..., project_id={project_id[:8]}...")
        result = await self._request("GET", f"{self.account_id}/projects/{project_id}/tickets/{task_id}")
        task_data = result.get("data") if result else None
        if task_data:
            log.info(f"   ✅ Task retrieved: {task_data.get('id')}")
        else:
            log.warning(f"   ⚠️ Task not found")
        return task_data

    async def get_task_description(self, task_id: str, project_id: str) -> Optional[str]:
        """Get task description.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
        """
        log.info(f"📝 get_task_description called: task_id={task_id[:8]}..., project_id={project_id[:8]}...")
        task = await self.get_task(task_id, project_id)
        description = task.get("description") if task else None
        if description:
            log.info(f"   ✅ Description retrieved ({len(description)} chars)")
        else:
            log.info(f"   ℹ️ No description available")
        return description

    async def get_task_plans(self, task_id: str, project_id: str) -> List[Dict[str, Any]]:
        """Get plans/blueprints associated with a task.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
        """
        log.info(f"🗺️ get_task_plans called: task_id={task_id[:8]}..., project_id={project_id[:8]}...")
        result = await self._request("GET", f"{self.account_id}/projects/{project_id}/tickets/{task_id}/plans")
        plans = result.get("data", []) if result else []
        log.info(f"   ✅ Retrieved {len(plans)} plans")
        return plans

    async def get_task_images(self, task_id: str, project_id: str, task_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get images attached to a task.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
            task_uuid: Deprecated - task_id is now UUID by default, kept for backward compatibility

        Note: PlanRadar attachments endpoint requires UUID
        """
        # Use task_uuid if provided (backward compatibility), otherwise use task_id (which is now UUID)
        uuid_to_use = task_uuid if task_uuid else task_id
        log.info(f"📷 get_task_images called: task_uuid={uuid_to_use[:8]}..., project_id={project_id[:8]}...")

        # Use UUID for attachments endpoint (required by PlanRadar API)
        result = await self._request("GET", f"{self.account_id}/projects/{project_id}/tickets/{uuid_to_use}/attachments")

        if result and result.get("data"):
            attachments = result.get("data", [])
            # Get image URLs from included section (JSON:API format)
            included = result.get("included", [])

            images = []
            for att in attachments:
                # Find corresponding image data in included section
                att_id = att.get("id")
                attachable_type = att.get("attributes", {}).get("attachable-type", "")

                # Look for image in included section
                for inc in included:
                    if inc.get("id") == att_id and "image" in inc.get("type", "").lower():
                        inc_attributes = inc.get("attributes", {})
                        images.append({
                            "id": att_id,
                            "type": inc.get("type"),
                            "title": att.get("attributes", {}).get("title"),
                            "url": inc_attributes.get("image-url"),
                            "thumbnail_url": inc_attributes.get("image-url-thumb"),
                            "content_type": inc_attributes.get("image-content-type"),
                            "file_size": inc_attributes.get("image-file-size"),
                            "metadata": inc_attributes.get("metadata"),
                        })
                        break

            log.info(f"   ✅ Retrieved {len(images)} images (from {len(attachments)} total attachments)")
            return images

        log.info(f"   ℹ️ No attachments found")
        return []

    async def get_documents(
        self,
        project_id: str,
        folder_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get documents for a PlanRadar project.

        Args:
            project_id: The PlanRadar project ID
            folder_id: Optional folder ID filter

        Returns:
            List of documents for the project
        """
        # PlanRadar v2 API requires customer_id in path
        endpoint = f"{self.account_id}/projects/{project_id}/documents"
        params = {}
        if folder_id:
            params["folder_id"] = folder_id

        result = await self._request("GET", endpoint, params=params)
        # Check for rate limit error
        if result and result.get("_rate_limited"):
            raise Exception("PlanRadar API rate limit exceeded. Please try again in a few moments.")
        # PlanRadar uses JSON:API format with nested "data" array
        return result.get("data", []) if result else []

    async def add_task_comment(
        self,
        task_id: str,
        project_id: str,
        comment_text: str,
    ) -> bool:
        """Add a comment to a task.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
            comment_text: The comment text to add
        """
        log.info(f"💬 add_task_comment called: task_id={task_id[:8]}..., project_id={project_id[:8]}..., comment_length={len(comment_text)}")
        data = {
            "text": comment_text,
        }
        result = await self._request("POST", f"{self.account_id}/projects/{project_id}/tickets/{task_id}/comments", data=data)
        success = result is not None
        if success:
            log.info(f"   ✅ Comment added successfully")
        else:
            log.warning(f"   ⚠️ Failed to add comment")
        return success

    async def get_task_comments(self, task_id: str, project_id: str) -> List[Dict[str, Any]]:
        """Get all comments for a task.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
        """
        log.info(f"💬 get_task_comments called: task_id={task_id[:8]}..., project_id={project_id[:8]}...")
        result = await self._request("GET", f"{self.account_id}/projects/{project_id}/tickets/{task_id}/comments")
        comments = result.get("data", []) if result else []
        log.info(f"   ✅ Retrieved {len(comments)} comments")
        return comments

    async def submit_incident_report(
        self,
        project_id: str,
        title: str,
        description: str,
        image_urls: List[str],
        location: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Submit a new incident report (ticket) for a project.

        Args:
            project_id: The PlanRadar project ID
            title: Incident title
            description: Incident description
            image_urls: List of image URLs
            location: Optional location data

        Returns:
            The created ticket/incident ID
        """
        # PlanRadar v2 API requires customer_id in path
        endpoint = f"{self.account_id}/projects/{project_id}/tickets"
        data = {
            "title": title,
            "description": description,
            "type": "incident",
            "attachments": [{"url": url, "type": "image"} for url in image_urls],
        }
        if location:
            data["location"] = location

        result = await self._request("POST", endpoint, data=data)
        # PlanRadar uses JSON:API format with nested "data" object
        if result and result.get("data"):
            return result["data"].get("id")
        return None

    async def update_incident_report(
        self,
        task_id: str,
        project_id: str,
        additional_text: Optional[str] = None,
        additional_images: Optional[List[str]] = None,
    ) -> bool:
        """Update an existing incident report with additional information."""
        # Add comment if text provided
        if additional_text:
            await self.add_task_comment(task_id, project_id, additional_text)

        # Add images if provided
        if additional_images:
            for image_url in additional_images:
                data = {
                    "url": image_url,
                    "type": "image",
                }
                await self._request(
                    "POST",
                    f"{self.account_id}/projects/{project_id}/tickets/{task_id}/attachments",
                    data=data
                )

        return True

    async def update_task_progress(
        self,
        task_id: str,
        project_id: str,
        status: str,
        progress_note: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
    ) -> bool:
        """Update task progress with status, notes, and images.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
            status: New status for the task
            progress_note: Optional progress note
            image_urls: Optional list of image URLs
        """
        # Update status
        data = {"status": status}
        result = await self._request("PATCH", f"{self.account_id}/projects/{project_id}/tickets/{task_id}", data=data)

        if not result:
            return False

        # Add progress note as comment
        if progress_note:
            await self.add_task_comment(task_id, project_id, progress_note)

        # Add progress images
        if image_urls:
            for image_url in image_urls:
                data = {
                    "url": image_url,
                    "type": "image",
                }
                await self._request(
                    "POST",
                    f"{self.account_id}/projects/{project_id}/tickets/{task_id}/attachments",
                    data=data
                )

        return True

    async def mark_task_complete(self, task_id: str, project_id: str) -> bool:
        """Mark a task as complete.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
        """
        data = {"status": "completed"}
        result = await self._request("PATCH", f"{self.account_id}/projects/{project_id}/tickets/{task_id}", data=data)
        return result is not None


# Global instance
planradar_client = PlanRadarClient()
