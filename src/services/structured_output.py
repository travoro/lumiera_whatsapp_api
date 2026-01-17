"""Structured output models for WhatsApp rich media responses."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, validator


class WhatsAppButton(BaseModel):
    """WhatsApp interactive button."""

    text: str = Field(..., max_length=20, description="Button text")
    payload: str = Field(..., description="Data payload when button is clicked")

    @validator("text")
    def validate_text(cls, v):
        if len(v) > 20:
            raise ValueError("Button text must be 20 characters or less")
        return v.strip()


class WhatsAppListItem(BaseModel):
    """Item in a WhatsApp list."""

    id: str = Field(..., description="Unique identifier for this item")
    title: str = Field(..., max_length=24, description="Item title")
    description: Optional[str] = Field(
        None, max_length=72, description="Item description"
    )

    @validator("title")
    def validate_title(cls, v):
        if len(v) > 24:
            raise ValueError("List item title must be 24 characters or less")
        return v.strip()

    @validator("description")
    def validate_description(cls, v):
        if v and len(v) > 72:
            raise ValueError("List item description must be 72 characters or less")
        return v.strip() if v else None


class WhatsAppListSection(BaseModel):
    """Section in a WhatsApp list."""

    title: str = Field(..., max_length=24, description="Section title")
    items: List[WhatsAppListItem] = Field(
        ..., min_length=1, description="Items in this section"
    )

    @validator("title")
    def validate_title(cls, v):
        if len(v) > 24:
            raise ValueError("Section title must be 24 characters or less")
        return v.strip()


class ProjectListOutput(BaseModel):
    """Structured output for project list."""

    message_type: Literal["project_list"] = "project_list"
    intro_text: str = Field(..., description="Introduction message")
    projects: List[WhatsAppListItem] = Field(..., description="List of projects")

    def to_whatsapp_format(self) -> dict:
        """Convert to WhatsApp list message format.

        Returns:
            Dict ready for WhatsApp Business API
        """
        return {
            "type": "list",
            "body": self.intro_text,
            "button_text": "Voir les projets",
            "sections": [
                {
                    "title": "Vos chantiers actifs",
                    "rows": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "description": item.description or "",
                        }
                        for item in self.projects[
                            :10
                        ]  # WhatsApp limit: 10 items per section
                    ],
                }
            ],
        }

    def to_text_fallback(self) -> str:
        """Convert to plain text for compatibility.

        Returns:
            Formatted text message
        """
        text = f"{self.intro_text}\n\n"
        for i, project in enumerate(self.projects, 1):
            text += f"{i}. 🏗️ **{project.title}**\n"
            if project.description:
                text += f"   {project.description}\n"
            text += "\n"
        return text.strip()


class TaskListOutput(BaseModel):
    """Structured output for task list."""

    message_type: Literal["task_list"] = "task_list"
    intro_text: str = Field(..., description="Introduction message")
    tasks: List[WhatsAppListItem] = Field(..., description="List of tasks")

    def to_whatsapp_format(self) -> dict:
        """Convert to WhatsApp list message format."""
        return {
            "type": "list",
            "body": self.intro_text,
            "button_text": "Voir les tâches",
            "sections": [
                {
                    "title": "Tâches du projet",
                    "rows": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "description": item.description or "",
                        }
                        for item in self.tasks[:10]
                    ],
                }
            ],
        }

    def to_text_fallback(self) -> str:
        """Convert to plain text for compatibility."""
        text = f"{self.intro_text}\n\n"
        for i, task in enumerate(self.tasks, 1):
            text += f"{i}. 📝 **{task.title}**\n"
            if task.description:
                text += f"   {task.description}\n"
            text += "\n"
        return text.strip()


class MediaCarouselOutput(BaseModel):
    """Structured output for media carousel (images/plans)."""

    message_type: Literal["media_carousel"] = "media_carousel"
    intro_text: str = Field(..., description="Introduction message")
    media_items: List[dict] = Field(..., description="Media items with URLs")

    def to_whatsapp_format(self) -> List[dict]:
        """Convert to multiple WhatsApp media messages.

        Returns:
            List of message dicts to send sequentially
        """
        messages = [{"type": "text", "body": self.intro_text}]

        for item in self.media_items[:10]:  # Limit to 10 items
            messages.append(
                {
                    "type": "image",
                    "url": item.get("url"),
                    "caption": item.get("name", ""),
                }
            )

        return messages

    def to_text_fallback(self) -> str:
        """Convert to plain text with URLs."""
        text = f"{self.intro_text}\n\n"
        for i, item in enumerate(self.media_items, 1):
            text += f"{i}. 📸 **{item.get('name', 'Media')}**\n"
            text += f"   {item.get('url')}\n\n"
        return text.strip()


class ActionButtonsOutput(BaseModel):
    """Structured output for action buttons."""

    message_type: Literal["action_buttons"] = "action_buttons"
    intro_text: str = Field(..., description="Introduction message")
    buttons: List[WhatsAppButton] = Field(
        ..., max_length=3, description="Action buttons (max 3)"
    )

    @validator("buttons")
    def validate_buttons(cls, v):
        if len(v) > 3:
            raise ValueError("WhatsApp allows maximum 3 buttons")
        return v

    def to_whatsapp_format(self) -> dict:
        """Convert to WhatsApp button message format."""
        return {
            "type": "buttons",
            "body": self.intro_text,
            "buttons": [
                {"type": "reply", "reply": {"id": btn.payload, "title": btn.text}}
                for btn in self.buttons
            ],
        }

    def to_text_fallback(self) -> str:
        """Convert to plain text with numbered options."""
        text = f"{self.intro_text}\n\n"
        for i, btn in enumerate(self.buttons, 1):
            text += f"{i}. {btn.text}\n"
        return text.strip()


class EscalationOutput(BaseModel):
    """Structured output for escalation to human."""

    message_type: Literal["escalation"] = "escalation"
    message: str = Field(..., description="Escalation confirmation message")
    reason: str = Field(..., description="Reason for escalation")

    def to_text_fallback(self) -> str:
        """Convert to plain text."""
        return f"✅ {self.message}\n\nRaison: {self.reason}"


class GenericTextOutput(BaseModel):
    """Generic text output for non-structured responses."""

    message_type: Literal["text"] = "text"
    text: str = Field(..., description="Message text")

    def to_text_fallback(self) -> str:
        """Return as plain text."""
        return self.text


# Union type for all possible outputs
AgentOutput = (
    ProjectListOutput
    | TaskListOutput
    | MediaCarouselOutput
    | ActionButtonsOutput
    | EscalationOutput
    | GenericTextOutput
)


def format_output_for_whatsapp(output: BaseModel, use_rich_media: bool = True) -> str:
    """Format structured output for WhatsApp.

    Args:
        output: Pydantic model output from agent
        use_rich_media: If True, use rich media when possible. If False, use text fallback.

    Returns:
        Formatted message string (or dict for rich media)
    """
    # For now, always use text fallback for compatibility
    # In future, can conditionally use rich media based on WhatsApp Business API tier
    if hasattr(output, "to_text_fallback"):
        return output.to_text_fallback()
    elif hasattr(output, "text"):
        return output.text
    else:
        return str(output)
