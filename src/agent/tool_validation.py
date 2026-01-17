"""Pydantic models for tool input validation."""

from typing import List, Optional

from pydantic import BaseModel, Field, validator


class ListProjectsInput(BaseModel):
    """List projects - automatically filtered by user_id."""

    user_id: str = Field(..., description="User ID")

    @validator("user_id")
    def validate_user_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("user_id cannot be empty")
        return v.strip()


class ListTasksInput(BaseModel):
    """List tasks for a project."""

    user_id: str = Field(..., description="User ID")
    project_id: str = Field(..., description="Project ID")
    status: Optional[str] = Field(None, description="Status filter")

    @validator("user_id", "project_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()

    @validator("status")
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = ["open", "in_progress", "completed", "blocked", "pending"]
        if v.lower() not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(allowed)}")
        return v.lower()


class GetTaskDescriptionInput(BaseModel):
    """Get task description."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()


class GetTaskPlansInput(BaseModel):
    """Get task plans/blueprints."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()


class GetTaskImagesInput(BaseModel):
    """Get task images."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()


class GetDocumentsInput(BaseModel):
    """Get project documents."""

    user_id: str = Field(..., description="User ID")
    project_id: str = Field(..., description="Project ID")
    folder_id: Optional[str] = Field(None, description="Optional folder ID")

    @validator("user_id", "project_id")
    def validate_required_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()

    @validator("folder_id")
    def validate_folder_id(cls, v):
        if v is None:
            return v
        return v.strip()


class AddTaskCommentInput(BaseModel):
    """Add comment to task."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")
    comment_text: str = Field(..., description="Comment text")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()

    @validator("comment_text")
    def validate_comment(cls, v):
        if not v or len(v.strip()) < 1:
            raise ValueError("Comment cannot be empty")
        if len(v) > 2000:
            raise ValueError("Comment too long (max 2000 characters)")
        return v.strip()


class GetTaskCommentsInput(BaseModel):
    """Get task comments."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()


class SubmitIncidentReportInput(BaseModel):
    """Submit incident report."""

    user_id: str = Field(..., description="User ID")
    project_id: str = Field(..., description="Project ID")
    title: str = Field(..., description="Incident title")
    description: str = Field(..., description="Incident description")
    image_urls: List[str] = Field(..., description="Image URLs (at least one required)")

    @validator("user_id", "project_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()

    @validator("title")
    def validate_title(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError("Title too short (min 3 characters)")
        if len(v) > 200:
            raise ValueError("Title too long (max 200 characters)")
        return v.strip()

    @validator("description")
    def validate_description(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError("Description too short (min 10 characters)")
        if len(v) > 2000:
            raise ValueError("Description too long (max 2000 characters)")
        return v.strip()

    @validator("image_urls")
    def validate_images(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one image is required for incident reports")
        if len(v) > 10:
            raise ValueError("Maximum 10 images per incident report")
        # Validate each URL
        for url in v:
            if not url or not url.startswith("http"):
                raise ValueError(f"Invalid image URL: {url}")
        return v


class UpdateIncidentReportInput(BaseModel):
    """Update incident report."""

    user_id: str = Field(..., description="User ID")
    incident_id: str = Field(..., description="Incident ID")
    additional_text: Optional[str] = Field(None, description="Additional text")
    additional_images: Optional[List[str]] = Field(
        None, description="Additional images"
    )

    @validator("user_id", "incident_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()

    @validator("additional_text")
    def validate_text(cls, v):
        if v is None:
            return v
        if len(v) > 2000:
            raise ValueError("Additional text too long (max 2000 characters)")
        return v.strip()

    @validator("additional_images")
    def validate_images(cls, v):
        if v is None:
            return v
        if len(v) > 10:
            raise ValueError("Maximum 10 additional images")
        for url in v:
            if not url or not url.startswith("http"):
                raise ValueError(f"Invalid image URL: {url}")
        return v


class UpdateTaskProgressInput(BaseModel):
    """Update task progress."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="New status")
    progress_note: Optional[str] = Field(None, description="Progress note")
    image_urls: Optional[List[str]] = Field(None, description="Progress images")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()

    @validator("status")
    def validate_status(cls, v):
        allowed = ["open", "in_progress", "completed", "blocked", "pending"]
        if v.lower() not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(allowed)}")
        return v.lower()

    @validator("progress_note")
    def validate_note(cls, v):
        if v is None:
            return v
        if len(v) > 1000:
            raise ValueError("Progress note too long (max 1000 characters)")
        return v.strip()

    @validator("image_urls")
    def validate_images(cls, v):
        if v is None:
            return v
        if len(v) > 10:
            raise ValueError("Maximum 10 images")
        for url in v:
            if not url or not url.startswith("http"):
                raise ValueError(f"Invalid image URL: {url}")
        return v


class MarkTaskCompleteInput(BaseModel):
    """Mark task complete."""

    user_id: str = Field(..., description="User ID")
    task_id: str = Field(..., description="Task ID")

    @validator("user_id", "task_id")
    def validate_ids(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID cannot be empty")
        return v.strip()


class SetLanguageInput(BaseModel):
    """Set user language preference."""

    user_id: str = Field(..., description="User ID")
    phone_number: str = Field(..., description="Phone number")
    language: str = Field(..., description="Language code")

    @validator("user_id")
    def validate_user_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("user_id cannot be empty")
        return v.strip()

    @validator("phone_number")
    def validate_phone(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("phone_number cannot be empty")
        # Basic phone validation
        cleaned = v.strip().replace("+", "").replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            raise ValueError("Invalid phone number format")
        return v.strip()

    @validator("language")
    def validate_language(cls, v):
        allowed = ["en", "fr", "es", "pt", "de", "it", "nl", "pl", "ro", "ar"]
        if v.lower() not in allowed:
            raise ValueError(f"Language must be one of: {', '.join(allowed)}")
        return v.lower()


class EscalateToHumanInput(BaseModel):
    """Escalate to human admin."""

    user_id: str = Field(..., description="User ID")
    phone_number: str = Field(..., description="Phone number")
    language: str = Field(..., description="User language")
    reason: str = Field(..., description="Escalation reason")

    @validator("user_id")
    def validate_user_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("user_id cannot be empty")
        return v.strip()

    @validator("phone_number")
    def validate_phone(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("phone_number cannot be empty")
        return v.strip()

    @validator("language")
    def validate_language(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("language cannot be empty")
        return v.strip()

    @validator("reason")
    def validate_reason(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError(
                "Please provide a reason for escalation (min 5 characters)"
            )
        if len(v) > 500:
            raise ValueError("Reason too long (max 500 characters)")
        return v.strip()


# Mapping of tool names to validation models
TOOL_VALIDATION_MODELS = {
    "list_projects_tool": ListProjectsInput,
    "list_tasks_tool": ListTasksInput,
    "get_task_description_tool": GetTaskDescriptionInput,
    "get_task_plans_tool": GetTaskPlansInput,
    "get_task_images_tool": GetTaskImagesInput,
    "get_documents_tool": GetDocumentsInput,
    "add_task_comment_tool": AddTaskCommentInput,
    "get_task_comments_tool": GetTaskCommentsInput,
    "submit_incident_report_tool": SubmitIncidentReportInput,
    "update_incident_report_tool": UpdateIncidentReportInput,
    "update_task_progress_tool": UpdateTaskProgressInput,
    "mark_task_complete_tool": MarkTaskCompleteInput,
    "set_language_tool": SetLanguageInput,
    "escalate_to_human_tool": EscalateToHumanInput,
}


def validate_tool_input(tool_name: str, **kwargs) -> dict:
    """Validate tool input with Pydantic models.

    Args:
        tool_name: Name of the tool
        **kwargs: Tool arguments to validate

    Returns:
        Dict with 'valid' (bool) and either 'data' (dict) or 'error' (str)
    """
    model = TOOL_VALIDATION_MODELS.get(tool_name)

    if not model:
        # No validation model for this tool, allow it
        return {"valid": True, "data": kwargs}

    try:
        validated = model(**kwargs)
        return {"valid": True, "data": validated.dict()}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
    except Exception as e:
        return {"valid": False, "error": f"Validation error: {str(e)}"}
