"""Project and content-related intent handlers.

These handlers execute directly without calling the main agent,
providing fast responses for project, document, and incident operations.

IMPORTANT: All handlers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""

from typing import Any, Dict

from src.actions import documents as document_actions

# Import LangChain tools for LangSmith tracing
from src.agent.tools import get_documents_tool
from src.integrations.supabase import supabase_client
from src.utils.handler_helpers import format_project_list, get_projects_with_context
from src.utils.logger import log
from src.utils.metadata_helpers import compact_documents, compact_projects
from src.utils.whatsapp_formatter import get_plural_translation, get_translation


async def handle_list_projects(
    user_id: str, user_name: str, language: str, phone_number: str = None, **kwargs
) -> Dict[str, Any]:
    """Handle list projects intent directly.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Listing projects for {user_id}")

    try:
        # Get projects from database
        projects = await supabase_client.list_projects(user_id)

        if not projects:
            return {
                "message": get_translation("fr", "no_projects"),
                "escalation": False,
                "tools_called": ["list_projects_tool"],
                "fast_path": True,
                "tool_outputs": [],  # No projects to store
            }

        # Format projects list with translation (ALWAYS French)
        message = get_plural_translation("fr", "projects_list_header", len(projects))

        for i, project in enumerate(projects, 1):
            message += f"{i}. 🏗️ {project['nom']}\n"
            if project.get("location"):
                message += f"   📍 {project['location']}\n"
            message += "\n"

        return {
            "message": message,
            "escalation": False,
            "tools_called": ["list_projects_tool"],
            "fast_path": True,
            "tool_outputs": [
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects(projects),  # Only essential fields
                }
            ],
            "list_type": "projects",  # Metadata for robust interactive list handling
        }

    except Exception as e:
        log.error(f"Error in fast path list_projects: {e}")
        # Return None to trigger fallback to full agent
        return None


async def handle_list_documents(
    user_id: str, phone_number: str, user_name: str, language: str, **kwargs
) -> Dict[str, Any]:
    """Handle list documents intent with context-aware project selection.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling list documents for {user_id}")

    try:
        # Use helper to get projects and context
        projects, current_project_id, no_projects_msg = await get_projects_with_context(
            user_id, language
        )

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True,
                "tool_outputs": [],
            }

        # Scenario 2: Single project available - Auto-select it
        if not current_project_id and len(projects) == 1:
            current_project_id = projects[0].get("id")
            project_name = projects[0].get("nom")
            log.info(
                f"✅ Auto-selected single available project: {project_name} (ID: {current_project_id[:8]}...)"
            )

        # Use centralized translations (ALWAYS French)
        message = ""  # Start with empty message, we'll build a simple one-liner
        tool_outputs = []
        attachments = None

        # Scenario 3: Has current project in context or auto-selected
        if current_project_id:
            # Find the current project
            current_project = next(
                (p for p in projects if str(p.get("id")) == current_project_id), None
            )
            project_name = (
                current_project["nom"] if current_project else projects[0]["nom"]
            )
            project_id = current_project["id"] if current_project else projects[0]["id"]

            # Don't add header or project context - we'll add a simple one-liner when we have the count

            # Get PlanRadar project ID from database
            from src.integrations.supabase import supabase_client

            project = await supabase_client.get_project(project_id, user_id=user_id)

            if not project:
                message = "❌ Impossible de récupérer les informations du projet."
                log.error(f"   ❌ Project not found in database: {project_id}")
            else:
                planradar_project_id = project.get("planradar_project_id")

                if not planradar_project_id:
                    message = "❌ Ce projet n'est pas lié à PlanRadar."
                    log.error(f"   ❌ No PlanRadar project ID for project {project_id}")
                else:
                    # Fetch all documents (plans) using unified method
                    from src.integrations.planradar import planradar_client

                    log.info(f"🔍 DEBUG: About to call get_project_documents")
                    log.info(f"   Project name: {project_name}")
                    log.info(f"   Project ID (database): {project_id}")
                    log.info(f"   PlanRadar project ID: {planradar_project_id}")

                    try:
                        plans = await planradar_client.get_project_documents(
                            planradar_project_id
                        )

                        log.info(f"🔍 DEBUG: get_project_documents returned")
                        log.info(f"   Type: {type(plans)}")
                        log.info(f"   Count: {len(plans) if plans else 0}")
                        if plans:
                            log.info(f"   First plan keys: {list(plans[0].keys())}")
                            log.info(f"   First plan sample: {plans[0]}")
                    except Exception as pr_error:
                        log.error(
                            f"❌ Exception calling get_project_documents: {pr_error}"
                        )
                        import traceback

                        log.error(f"   Traceback: {traceback.format_exc()}")
                        plans = []

                    if not plans:
                        message = (
                            f"Aucun plan disponible pour le chantier {project_name}."
                        )
                    else:
                        plan_count = len(plans)
                        # Simple one-line message
                        plan_word = "plan" if plan_count == 1 else "plans"
                        message += f"Voici {plan_count} {plan_word} pour le chantier {project_name}. 📐"

                        # Prepare attachments for sending plans directly
                        # Use component name (e.g., "Principal", "SDB") without extension
                        attachments = [
                            {
                                "url": plan.get("url"),
                                "content_type": plan.get("content_type", "image/png"),
                                "filename": plan.get("component_name", "document"),
                            }
                            for plan in plans
                        ]

            # No footer needed anymore since message is self-contained

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list (ALWAYS French)
            message += format_project_list(projects, "fr", max_items=5)

            # Add prompt to select project using centralized translation (ALWAYS French)
            message += get_translation("fr", "list_documents_select_project")

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append(
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects(projects[:5]),  # Only essential fields
                }
            )

        # Determine list_type based on what we're showing
        list_type = None
        for tool_output in tool_outputs:
            if tool_output.get("tool") == "list_projects_tool":
                list_type = "projects"
                break

        result = {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs,
        }

        if list_type:
            result["list_type"] = list_type

        if attachments:
            result["attachments"] = attachments

        return result

    except Exception as e:
        log.error(f"❌ Error in fast path list_documents: {e}")
        import traceback

        log.error(f"   Traceback: {traceback.format_exc()}")
        # Return None to trigger fallback to full agent
        return None


async def handle_report_incident(
    user_id: str, phone_number: str, user_name: str, language: str, **kwargs
) -> Dict[str, Any]:
    """Handle report incident intent directly with context-aware project info.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling report incident for {user_id}")

    try:
        # Use helper to get projects and context
        projects, current_project_id, no_projects_msg = await get_projects_with_context(
            user_id, language
        )

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True,
                "tool_outputs": [],
            }

        # Get base template (ALWAYS French)
        template = get_translation("fr", "report_incident")
        tool_outputs = []

        # Scenario 2: Has projects and current project in context
        if current_project_id:
            # Find the current project name
            current_project = next(
                (p for p in projects if str(p.get("id")) == current_project_id), None
            )
            project_name = (
                current_project["nom"] if current_project else projects[0]["nom"]
            )

            # Format with current project name
            message = template.replace("{chantier_nom}", project_name)

            # Store current project in tool_outputs for context
            if current_project:
                tool_outputs.append(
                    {
                        "tool": "list_projects_tool",
                        "input": {"user_id": user_id},
                        "output": compact_projects(
                            [current_project]
                        ),  # Only essential fields
                    }
                )

        # Scenario 3: Has projects but no current project in context
        else:
            # Build message with template header + project section + formatted list (ALWAYS French)
            base_msg = template.split("3. 🏗️")[0]
            base_msg += get_translation("fr", "report_incident_section_header")
            base_msg += format_project_list(projects, "fr", max_items=5)
            base_msg += get_translation("fr", "report_incident_closing")

            message = base_msg

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append(
                {
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects(projects[:5]),  # Only essential fields
                }
            )

        # Determine list_type based on what we're showing
        list_type = None
        for tool_output in tool_outputs:
            if tool_output.get("tool") == "list_projects_tool":
                list_type = "projects"
                break

        result = {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs,
        }

        if list_type:
            result["list_type"] = list_type

        return result

    except Exception as e:
        log.error(f"Error in fast path report_incident: {e}")
        # Return None to trigger fallback to full agent
        return None
