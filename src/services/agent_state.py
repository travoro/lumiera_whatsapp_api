"""Agent state management - Authoritative explicit state for the LLM.

This module builds the explicit state context that is injected into the agent's prompt.
This state is AUTHORITATIVE - it overrides anything inferred from conversation history.

Key principles:
1. Explicit state is the single source of truth for current context
2. Tools should default to this state (active_project_id, active_task_id)
3. This is separate from conversation history (which is for context only)
4. State should be compact and structured (not bloated)
"""

from dataclasses import dataclass
from typing import Any, Optional

from src.services.project_context import project_context_service
from src.utils.logger import log


@dataclass
class AgentState:
    """Structured state representing the user's current working context.

    This is the authoritative state that the agent uses for decision-making.
    All IDs here are UUIDs that can be directly passed to tools.
    """

    user_id: str
    language: str

    # Active context (most important - these are authoritative)
    active_project_id: Optional[str] = None
    active_project_name: Optional[str] = None
    active_task_id: Optional[str] = None
    active_task_title: Optional[str] = None

    # Metadata (for logging/debugging)
    session_id: Optional[str] = None

    def to_prompt_context(self) -> str:
        """Convert state to a compact string for agent prompt injection.

        Returns:
            Formatted string to be injected into agent prompt
        """
        if not self.active_project_id and not self.active_task_id:
            # No active state - return empty
            return ""

        context_parts = ["[État actuel - Source de vérité]"]

        if self.active_project_id:
            project_info = f"Projet actif: {self.active_project_name or 'N/A'}"
            project_info += f" (ID: {self.active_project_id})"
            context_parts.append(project_info)

        if self.active_task_id:
            task_info = f"Tâche active: {self.active_task_title or 'N/A'}"
            task_info += f" (ID: {self.active_task_id})"
            context_parts.append(task_info)

        context_parts.append("")  # Empty line for separation
        return "\n".join(context_parts)

    def has_active_context(self) -> bool:
        """Check if there is any active state."""
        return bool(self.active_project_id or self.active_task_id)


class AgentStateBuilder:
    """Builds the explicit state context for the agent.

    This service is responsible for:
    1. Loading current active state (project, task)
    2. Formatting it for agent consumption
    3. Ensuring state is authoritative and up-to-date
    """

    async def build_state(
        self, user_id: str, language: str, session_id: Optional[str] = None
    ) -> AgentState:
        """Build the current agent state for a user.

        This loads the authoritative state from the database (active project/task).

        Args:
            user_id: Subcontractor ID
            language: User's language code
            session_id: Optional session ID

        Returns:
            AgentState object with current context
        """
        try:
            # Load active project
            active_project_id = await project_context_service.get_active_project(
                user_id
            )
            active_project_name = None

            if active_project_id:
                project_details = (
                    await project_context_service.get_active_project_with_details(
                        user_id
                    )
                )
                if project_details:
                    active_project_name = project_details.get("nom")

            # Load active task
            active_task_id = await project_context_service.get_active_task(user_id)
            active_task_title = None

            if active_task_id:
                # Try to get task title from PlanRadar or database
                # For now, we'll leave it as None - can be enhanced later
                pass

            return AgentState(
                user_id=user_id,
                language=language,
                session_id=session_id,
                active_project_id=active_project_id,
                active_project_name=active_project_name,
                active_task_id=active_task_id,
                active_task_title=active_task_title,
            )

        except Exception as e:
            log.error(f"Error building agent state for user {user_id}: {e}")
            # Return empty state on error
            return AgentState(user_id=user_id, language=language, session_id=session_id)

    async def update_state_from_tool_result(
        self, user_id: str, tool_name: str, tool_output: Any
    ) -> None:
        """Update agent state based on tool execution results.

        This is called after tools execute to keep state synchronized.
        For example:
        - After list_tasks_tool → update active_project_id
        - After get_task_description_tool → update active_task_id

        Args:
            user_id: Subcontractor ID
            tool_name: Name of the tool that was executed
            tool_output: The structured output from the tool
        """
        try:
            # NOTE: State updates are already handled inside individual tools
            # This method is for future enhancements if we need centralized state updates
            pass

        except Exception as e:
            log.error(f"Error updating state from tool {tool_name}: {e}")


# Global instance
agent_state_builder = AgentStateBuilder()
