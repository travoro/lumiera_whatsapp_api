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
            List of components for the project with selected-plan relationships
        """
        log.info(f"🏗️ STEP 1: Fetching project components")
        log.info(f"   Project ID: {project_id}")
        endpoint = f"{self.account_id}/projects/{project_id}/components/project_components"
        params = {}
        if last_sync_date:
            params["last_sync_date"] = last_sync_date

        log.info(f"   🌐 API Request: GET {endpoint}")
        result = await self._request("GET", endpoint, params=params)

        # Check for rate limit error
        if result and result.get("_rate_limited"):
            raise Exception("PlanRadar API rate limit exceeded. Please try again in a few moments.")

        # PlanRadar uses JSON:API format with nested "data" array
        components = result.get("data", []) if result else []
        included = result.get("included", []) if result else []

        log.info(f"   ✅ Retrieved {len(components)} component(s)")
        log.info(f"   📦 Included section has {len(included)} item(s)")

        # Log component details
        for idx, comp in enumerate(components, 1):
            comp_id = comp.get("id")
            comp_attrs = comp.get("attributes", {})
            comp_name = comp_attrs.get("name", "Unnamed")
            comp_type = comp_attrs.get("component-type")
            file_name = comp_attrs.get("file-name", "N/A")

            log.info(f"   📋 Component {idx}/{len(components)}:")
            log.info(f"      ID: {comp_id}")
            log.info(f"      Name: {comp_name}")
            log.info(f"      Type: {comp_type}")
            log.info(f"      File: {file_name}")

            # Check for selected-plan relationship
            relationships = comp.get("relationships", {})
            selected_plan = relationships.get("selected-plan", {}).get("data")
            if selected_plan:
                plan_id = selected_plan.get("id")
                plan_type = selected_plan.get("type")
                log.info(f"      🔗 Selected plan: {plan_id} (type: {plan_type})")
            else:
                log.info(f"      ℹ️ No selected plan relationship")

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
            List of plans for the component with original-url for PDF download
        """
        log.info(f"📐 STEP 2: Fetching plans for component {component_id}")
        endpoint = f"{self.account_id}/projects/{project_id}/components/{component_id}/plans"
        params = {}
        if is_simple:
            params["is_simple"] = "true"

        log.info(f"   🌐 API Request: GET {endpoint}")
        result = await self._request("GET", endpoint, params=params)

        # Check for rate limit error
        if result and result.get("_rate_limited"):
            raise Exception("PlanRadar API rate limit exceeded. Please try again in a few moments.")

        # PlanRadar uses JSON:API format
        if result and result.get("data"):
            plans = result.get("data", [])
            included = result.get("included", [])

            log.info(f"   📊 Response contains {len(plans)} plan(s) in data section")
            log.info(f"   📦 Response contains {len(included)} item(s) in included section")

            # Log included section IDs for debugging
            if included:
                included_ids = [inc.get("id") for inc in included]
                log.info(f"   🔍 Included section IDs: {included_ids}")

            # Extract plan URLs from response
            all_plans = []
            for idx, plan in enumerate(plans, 1):
                plan_id = plan.get("id")
                plan_type = plan.get("type")
                plan_attributes = plan.get("attributes", {})
                plan_relationships = plan.get("relationships", {})

                log.info(f"   📄 Plan {idx}/{len(plans)}: {plan_id}")
                log.info(f"      Type: {plan_type}")
                log.info(f"      Attributes available: {list(plan_attributes.keys())}")

                # Extract key plan info
                plan_name = plan_attributes.get("name", "Unnamed Plan")
                file_size = plan_attributes.get("download-filesize")
                content_type = (plan_attributes.get("planfile-content-type") or
                               plan_attributes.get("content-type") or
                               plan_attributes.get("image-content-type"))

                log.info(f"      Name: {plan_name}")
                log.info(f"      Content-Type: {content_type}")
                log.info(f"      File Size: {file_size} bytes" if file_size else "      File Size: unknown")

                # PRIORITY 1: Try to extract original-url (the actual PDF)
                original_url = plan_attributes.get("original-url")
                if original_url:
                    log.info(f"      ✅ Found original-url (full PDF):")
                    log.info(f"         {original_url[:120]}...")

                # PRIORITY 2: Fallback URLs
                thumb_big_url = plan_attributes.get("plan-thumb-big-url")
                thumb_small_url = plan_attributes.get("plan-thumb-small-url")
                zip_url = plan_attributes.get("plan-zip-url")

                if thumb_big_url:
                    log.info(f"      📸 Thumbnail (big): {thumb_big_url[:80]}...")
                if thumb_small_url:
                    log.info(f"      📸 Thumbnail (small): {thumb_small_url[:80]}...")
                if zip_url:
                    log.info(f"      📦 Plan ZIP: {zip_url[:80]}...")

                # Select the best URL (prioritize original-url for full PDF)
                direct_url = (original_url or
                             thumb_big_url or
                             thumb_small_url or
                             plan_attributes.get("image-url") or
                             plan_attributes.get("url") or
                             plan_attributes.get("file-url"))

                if direct_url:
                    # Determine which URL we're using
                    if direct_url == original_url:
                        url_source = "original-url (full PDF)"
                    elif direct_url == thumb_big_url:
                        url_source = "plan-thumb-big-url (preview)"
                    elif direct_url == thumb_small_url:
                        url_source = "plan-thumb-small-url (thumbnail)"
                    else:
                        url_source = "fallback URL field"

                    log.info(f"      🔗 Selected URL source: {url_source}")

                    # Default to PDF if filename suggests it's a PDF and no content_type
                    if not content_type and plan_name.lower().endswith('.pdf'):
                        content_type = "application/pdf"
                        log.info(f"      ℹ️ Inferred content-type as application/pdf from filename")

                    plan_data = {
                        "id": plan_id,
                        "name": plan_name,
                        "url": direct_url,
                        "thumbnail_url": thumb_small_url or plan_attributes.get("image-url-thumb"),
                        "content_type": content_type,
                        "file_size": file_size,
                        "attributes": plan_attributes
                    }
                    all_plans.append(plan_data)
                    log.info(f"      ✅ Plan successfully extracted with URL")
                else:
                    # Try to find in included section (fallback)
                    log.info(f"      ⚠️ No direct URL in plan attributes, checking included section...")
                    found_in_included = False
                    for inc in included:
                        inc_id = inc.get("id")
                        inc_type = inc.get("type")

                        if inc_id == plan_id:
                            inc_attributes = inc.get("attributes", {})
                            log.info(f"      📦 Found plan in included section (type: {inc_type})")
                            log.info(f"         Included attributes: {list(inc_attributes.keys())}")

                            # Extract plan URL from included section
                            plan_url = (inc_attributes.get("original-url") or
                                       inc_attributes.get("image-url") or
                                       inc_attributes.get("url") or
                                       inc_attributes.get("file-url"))

                            if plan_url:
                                log.info(f"      ✅ Found URL in included section: {plan_url[:80]}...")
                                plan_data = {
                                    "id": plan_id,
                                    "name": plan_name,
                                    "url": plan_url,
                                    "thumbnail_url": inc_attributes.get("image-url-thumb"),
                                    "content_type": inc_attributes.get("content-type") or inc_attributes.get("image-content-type"),
                                    "file_size": inc_attributes.get("file-size"),
                                    "attributes": plan_attributes
                                }
                                all_plans.append(plan_data)
                            else:
                                log.warning(f"      ❌ No URL found in included section")
                                log.warning(f"         Available keys: {list(inc_attributes.keys())}")

                            found_in_included = True
                            break

                    if not found_in_included:
                        log.warning(f"      ❌ Plan {plan_id} not found in included section either")

            log.info(f"   ✅ Successfully extracted {len(all_plans)} plan(s) with URLs")
            return all_plans

        log.info(f"   ℹ️ No plans found in response")
        return []

    async def get_project_documents(
        self,
        project_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all documents (plans) for a project by fetching all components and their plans.

        This is a unified method that follows the PlanRadar workflow:
        1. GET /projects/{project_id}/components/project_components - Get all components
        2. For each component: GET /projects/{project_id}/components/{component_id}/plans - Get plans
        3. Extract original-url from plan attributes for full PDF access
        4. Return all plans with URLs, filtered and ready to send

        Args:
            project_id: The PlanRadar project ID

        Returns:
            List of all plans across all components, with URLs and metadata
        """
        log.info(f"📚 ========== GET PROJECT DOCUMENTS WORKFLOW ==========")
        log.info(f"   Project ID: {project_id}")

        try:
            # Step 1: Fetch all components for this project
            log.info(f"\n🏗️ STEP 1: Fetching all project components...")
            components = await self.get_project_components(project_id)

            if not components:
                log.info(f"   ⚠️ No components found for project {project_id}")
                return []

            log.info(f"   ✅ Found {len(components)} component(s)")

            # Step 2: Fetch plans for each component
            log.info(f"\n📐 STEP 2: Fetching plans for each component...")
            all_plans = []
            for idx, component in enumerate(components, 1):
                component_id = component.get("id")
                component_attrs = component.get("attributes", {})
                component_name = component_attrs.get("name", "Composant")

                log.info(f"\n   🔄 Processing component {idx}/{len(components)}: {component_name}")
                log.info(f"      Component ID: {component_id}")

                plans = await self.get_component_plans(project_id, component_id)
                log.info(f"      ✅ Retrieved {len(plans)} plan(s) for this component")

                for plan in plans:
                    plan["component_name"] = component_name
                    plan["component_id"] = component_id
                    all_plans.append(plan)

            if not all_plans:
                log.info(f"\n   ℹ️ No plans found across all {len(components)} components")
                return []

            log.info(f"\n   📊 Total plans collected: {len(all_plans)}")

            # Step 3: Filter plans with valid URLs
            log.info(f"\n🔍 STEP 3: Filtering plans with valid URLs...")
            plans_with_urls = [p for p in all_plans if p.get("url")]
            plans_without_urls = [p for p in all_plans if not p.get("url")]

            if plans_without_urls:
                log.warning(f"   ⚠️ Filtered out {len(plans_without_urls)} plan(s) without URLs:")
                for p in plans_without_urls[:3]:  # Show first 3
                    log.warning(f"      - {p.get('name')} (component: {p.get('component_name')})")

            if plans_with_urls:
                log.info(f"\n   ✅ Successfully recovered {len(plans_with_urls)} document(s) with URLs:")
                for idx, p in enumerate(plans_with_urls, 1):
                    content_type = p.get('content_type', 'unknown')
                    file_size = p.get('file_size')
                    file_type = "PDF" if "pdf" in content_type.lower() else content_type

                    log.info(f"      {idx}. {p.get('name')}")
                    log.info(f"         Type: {file_type}")
                    log.info(f"         Size: {file_size} bytes" if file_size else "         Size: unknown")
                    log.info(f"         Component: {p.get('component_name')}")
                    log.info(f"         URL: {p.get('url')[:100]}...")
            else:
                log.warning(f"   ⚠️ No documents with valid URLs found")

            log.info(f"\n📚 ========== WORKFLOW COMPLETE: {len(plans_with_urls)} documents ready ==========\n")

            return plans_with_urls

        except Exception as e:
            log.error(f"\n   ❌ Error fetching project documents: {e}")
            import traceback
            log.error(f"   Traceback: {traceback.format_exc()}")
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
        status_id: int,  # 1=Open, 2=In-Progress, 3=Resolved, etc.
        progress: Optional[int] = None,  # 0-100
        progress_note: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
    ) -> bool:
        """Update task progress with status, notes, and images.

        According to PlanRadar API docs:
        - Status IDs: 1=Open, 2=In-Progress, 3=Resolved, 4=Feedback, 5=Closed, 6=Rejected
        - Use PUT method with JSON:API format

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
            status_id: Status ID (1=Open, 2=In-Progress, 3=Resolved, 4=Feedback, 5=Closed, 6=Rejected)
            progress: Progress percentage (0-100)
            progress_note: Optional progress note
            image_urls: Optional list of image URLs

        Returns:
            True if successful
        """
        # Update status and progress using JSON:API format
        data = {
            "data": {
                "attributes": {
                    "status-id": status_id
                }
            }
        }

        if progress is not None:
            data["data"]["attributes"]["progress"] = progress

        result = await self._request(
            "PUT",
            f"{self.account_id}/projects/{project_id}/tickets/{task_id}",
            data=data
        )

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

    async def mark_task_complete(
        self,
        task_id: str,
        project_id: str,
        set_progress_100: bool = True
    ) -> bool:
        """Mark a task as complete (Resolved status).

        According to PlanRadar API docs:
        - Status ID 3 = Resolved (task done)
        - Use PUT method with JSON:API format

        Args:
            task_id: The task UUID (primary identifier, latest API standard)
            project_id: The PlanRadar project ID
            set_progress_100: If True, also set progress to 100%

        Returns:
            True if successful
        """
        # Use correct JSON:API format
        data = {
            "data": {
                "attributes": {
                    "status-id": 3,  # 3 = Resolved (task done)
                }
            }
        }

        # Optionally set progress to 100%
        if set_progress_100:
            data["data"]["attributes"]["progress"] = 100

        # Use PUT method (not PATCH)
        result = await self._request(
            "PUT",
            f"{self.account_id}/projects/{project_id}/tickets/{task_id}",
            data=data
        )
        return result is not None


# Global instance
planradar_client = PlanRadarClient()
