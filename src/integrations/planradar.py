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
        """Get all attachments (images, documents, etc.) attached to a task.

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
            task_uuid: Deprecated - task_id is now UUID by default, kept for backward compatibility

        Returns:
            List of all attachments (images, PDFs, documents, etc.)

        Note: PlanRadar attachments endpoint requires UUID
        """
        # Use task_uuid if provided (backward compatibility), otherwise use task_id (which is now UUID)
        uuid_to_use = task_uuid if task_uuid else task_id
        log.info(f"📎 get_task_images called (returns all attachments): task_uuid={uuid_to_use[:8]}..., project_id={project_id[:8]}...")

        # Use UUID for attachments endpoint (required by PlanRadar API)
        result = await self._request("GET", f"{self.account_id}/projects/{project_id}/tickets/{uuid_to_use}/attachments")

        if result and result.get("data"):
            attachments = result.get("data", [])
            # Get all attachment URLs from included section (JSON:API format)
            included = result.get("included", [])

            all_attachments = []
            for att in attachments:
                # Find corresponding attachment data in included section
                att_id = att.get("id")
                att_title = att.get("attributes", {}).get("title", "")

                # Look for attachment in included section
                for inc in included:
                    if inc.get("id") == att_id:
                        inc_type = inc.get("type", "").lower()
                        inc_attributes = inc.get("attributes", {})

                        # Handle images
                        if "image" in inc_type:
                            all_attachments.append({
                                "id": att_id,
                                "type": "image",
                                "title": att_title,
                                "url": inc_attributes.get("image-url"),
                                "thumbnail_url": inc_attributes.get("image-url-thumb"),
                                "content_type": inc_attributes.get("image-content-type"),
                                "file_size": inc_attributes.get("image-file-size"),
                                "metadata": inc_attributes.get("metadata"),
                            })
                        # Handle documents (PDFs, etc.)
                        elif "document" in inc_type:
                            all_attachments.append({
                                "id": att_id,
                                "type": "document",
                                "title": att_title,
                                "url": inc_attributes.get("url"),
                                "content_type": inc_attributes.get("document-content-type"),
                                "file_size": inc_attributes.get("document-file-size"),
                                "metadata": inc_attributes.get("metadata"),
                            })
                        # Handle any other attachment types
                        else:
                            log.debug(f"   Unknown attachment type: {inc_type}, attempting to extract URL")
                            # Try to find any URL field
                            url = None
                            for key, value in inc_attributes.items():
                                if "url" in key.lower() and value:
                                    url = value
                                    break

                            if url:
                                all_attachments.append({
                                    "id": att_id,
                                    "type": inc_type,
                                    "title": att_title,
                                    "url": url,
                                    "content_type": inc_attributes.get("content-type"),
                                    "file_size": inc_attributes.get("file-size"),
                                    "metadata": inc_attributes.get("metadata"),
                                })
                        break

            log.info(f"   ✅ Retrieved {len(all_attachments)} attachments (from {len(attachments)} total)")
            log.info(f"   Types: {', '.join(set(att.get('type', 'unknown') for att in all_attachments))}")
            return all_attachments

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

    async def get_project_components(
        self,
        project_id: str,
        last_sync_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all components of a project.

        Args:
            project_id: The PlanRadar project ID
            last_sync_date: Optional Unix timestamp - only components created after this will be returned

        Returns:
            List of components for the project
        """
        log.info(f"🏗️ get_project_components called: project_id={project_id[:8]}...")
        endpoint = f"{self.account_id}/projects/{project_id}/components/project_components"
        params = {}
        if last_sync_date:
            params["last_sync_date"] = last_sync_date

        result = await self._request("GET", endpoint, params=params)
        # Check for rate limit error
        if result and result.get("_rate_limited"):
            raise Exception("PlanRadar API rate limit exceeded. Please try again in a few moments.")
        # PlanRadar uses JSON:API format with nested "data" array
        components = result.get("data", []) if result else []
        log.info(f"   ✅ Retrieved {len(components)} components")
        return components

    async def get_component_plans(
        self,
        project_id: str,
        component_id: str,
        is_simple: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get all plans of a component.

        Args:
            project_id: The PlanRadar project ID
            component_id: The component ID
            is_simple: If True, retrieves simple plan versions data

        Returns:
            List of plans for the component
        """
        log.info(f"📐 get_component_plans called: project_id={project_id[:8]}..., component_id={component_id[:8]}...")
        endpoint = f"{self.account_id}/projects/{project_id}/components/{component_id}/plans"
        params = {}
        if is_simple:
            params["is_simple"] = "true"

        result = await self._request("GET", endpoint, params=params)
        # Check for rate limit error
        if result and result.get("_rate_limited"):
            raise Exception("PlanRadar API rate limit exceeded. Please try again in a few moments.")

        # PlanRadar uses JSON:API format
        if result and result.get("data"):
            plans = result.get("data", [])
            included = result.get("included", [])

            # Extract plan URLs from included section
            all_plans = []
            for plan in plans:
                plan_id = plan.get("id")
                plan_attributes = plan.get("attributes", {})

                # Find corresponding data in included section
                for inc in included:
                    if inc.get("id") == plan_id:
                        inc_attributes = inc.get("attributes", {})

                        # Extract plan URL (could be image-url or other field)
                        plan_url = (inc_attributes.get("image-url") or
                                   inc_attributes.get("url") or
                                   inc_attributes.get("file-url"))

                        all_plans.append({
                            "id": plan_id,
                            "name": plan_attributes.get("name") or plan_attributes.get("title", "Plan"),
                            "url": plan_url,
                            "thumbnail_url": inc_attributes.get("image-url-thumb"),
                            "content_type": inc_attributes.get("content-type") or inc_attributes.get("image-content-type"),
                            "attributes": plan_attributes
                        })
                        break

            log.info(f"   ✅ Retrieved {len(all_plans)} plans")
            return all_plans

        log.info(f"   ℹ️ No plans found")
        return []

    async def get_project_documents(
        self,
        project_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all documents (plans) for a project by fetching all components and their plans.

        This is a unified method that:
        1. Fetches all components for the project
        2. For each component, fetches all its plans
        3. Returns all plans with URLs, filtered and ready to send

        Args:
            project_id: The PlanRadar project ID

        Returns:
            List of all plans across all components, with URLs and metadata
        """
        log.info(f"📚 get_project_documents called: project_id={project_id[:8]}...")

        try:
            # Step 1: Fetch all components for this project
            components = await self.get_project_components(project_id)

            if not components:
                log.info(f"   ℹ️ No components found for project")
                return []

            # Step 2: Fetch plans for each component
            all_plans = []
            for component in components:
                component_id = component.get("id")
                component_name = component.get("attributes", {}).get("name", "Composant")

                plans = await self.get_component_plans(project_id, component_id)
                for plan in plans:
                    plan["component_name"] = component_name
                    all_plans.append(plan)

            if not all_plans:
                log.info(f"   ℹ️ No plans found across all components")
                return []

            # Step 3: Filter plans with valid URLs
            plans_with_urls = [p for p in all_plans if p.get("url")]
            plans_without_urls = [p for p in all_plans if not p.get("url")]

            if plans_without_urls:
                log.warning(f"   ⚠️ Filtered out {len(plans_without_urls)} plans without URLs:")
                for p in plans_without_urls[:3]:  # Show first 3
                    log.warning(f"      - {p.get('name')} ({p.get('component_name')})")

            log.info(f"   ✅ Retrieved {len(plans_with_urls)} sendable plans (filtered {len(plans_without_urls)} without URLs)")
            return plans_with_urls

        except Exception as e:
            log.error(f"   ❌ Error fetching project documents: {e}")
            return []

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
