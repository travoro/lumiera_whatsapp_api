"""Project and content-related intent handlers.

These handlers execute directly without calling the main agent,
providing fast responses for project, document, and incident operations.

IMPORTANT: All handlers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""
from typing import Dict, Any
from src.integrations.supabase import supabase_client
from src.actions import documents as document_actions
from src.utils.whatsapp_formatter import get_translation, get_plural_translation
from src.utils.handler_helpers import get_projects_with_context, format_project_list
from src.utils.metadata_helpers import compact_projects, compact_documents
from src.utils.logger import log

# Import LangChain tools for LangSmith tracing
from src.agent.tools import get_documents_tool


async def handle_list_projects(
    user_id: str,
    user_name: str,
    language: str,
    phone_number: str = None,
    **kwargs
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
                "tool_outputs": []  # No projects to store
            }

        # Format projects list with translation (ALWAYS French)
        message = get_plural_translation("fr", "projects_list_header", len(projects))

        for i, project in enumerate(projects, 1):
            message += f"{i}. 🏗️ {project['nom']}\n"
            if project.get('location'):
                message += f"   📍 {project['location']}\n"
            message += "\n"

        return {
            "message": message,
            "escalation": False,
            "tools_called": ["list_projects_tool"],
            "fast_path": True,
            "tool_outputs": [{
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": compact_projects(projects)  # Only essential fields
            }],
            "list_type": "projects"  # Metadata for robust interactive list handling
        }

    except Exception as e:
        log.error(f"Error in fast path list_projects: {e}")
        # Return None to trigger fallback to full agent
        return None


async def handle_list_documents(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Dict[str, Any]:
    """Handle list documents intent with context-aware project selection.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling list documents for {user_id}")

    try:
        # Use helper to get projects and context
        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True,
                "tool_outputs": []
            }

        # Scenario 2: Single project available - Auto-select it
        if not current_project_id and len(projects) == 1:
            current_project_id = projects[0].get('id')
            project_name = projects[0].get('nom')
            log.info(f"✅ Auto-selected single available project: {project_name} (ID: {current_project_id[:8]}...)")

        # Use centralized translations (ALWAYS French)
        message = get_translation("fr", "list_documents_header")
        tool_outputs = []
        carousel_data = None

        # Scenario 3: Has current project in context or auto-selected
        if current_project_id:
            # Find the current project
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['nom'] if current_project else projects[0]['nom']
            project_id = current_project['id'] if current_project else projects[0]['id']

            message += get_translation("fr", "list_documents_project_context").format(project_name=project_name)

            # Get PlanRadar project ID from database
            from src.integrations.supabase import supabase_client
            planradar_project_id = supabase_client.get_planradar_project_id(project_id)

            if not planradar_project_id:
                message += "❌ Impossible de récupérer les plans pour ce chantier."
                log.error(f"   ❌ No PlanRadar project ID found for project {project_id}")
            else:
                # Fetch all components for this project
                from src.integrations.planradar import planradar_client
                components = await planradar_client.get_project_components(planradar_project_id)

                if not components:
                    message += get_translation("fr", "list_documents_no_documents")
                else:
                    # Fetch plans for each component
                    all_plans = []
                    for component in components:
                        component_id = component.get("id")
                        component_name = component.get("attributes", {}).get("name", "Composant")

                        plans = await planradar_client.get_component_plans(planradar_project_id, component_id)
                        for plan in plans:
                            plan["component_name"] = component_name
                            all_plans.append(plan)

                    if not all_plans:
                        message += get_translation("fr", "list_documents_no_documents")
                    else:
                        # Filter out plans without URLs
                        plans_with_urls = [p for p in all_plans if p.get("url")]
                        plans_without_urls = [p for p in all_plans if not p.get("url")]

                        if plans_without_urls:
                            log.warning(f"   ⚠️ Skipping {len(plans_without_urls)} plans without URLs")

                        if plans_with_urls:
                            plan_count = len(plans_with_urls)
                            message += f"📐 {plan_count} plan(s) disponible(s)\n\n"

                            # Prepare carousel_data for sending plans as attachments
                            carousel_data = {
                                "cards": [
                                    {
                                        "media_url": plan.get("url"),
                                        "media_type": plan.get("content_type", "image/png")
                                    }
                                    for plan in plans_with_urls
                                ]
                            }

                            # Show preview of plans in message
                            for i, plan in enumerate(plans_with_urls[:5], 1):  # Show max 5 in text
                                component = plan.get("component_name", "")
                                plan_name = plan.get("name", "Plan")
                                message += f"{i}. 📐 {plan_name}"
                                if component:
                                    message += f" ({component})"
                                message += "\n"

                            if len(plans_with_urls) > 5:
                                message += f"\n... et {len(plans_with_urls) - 5} autre(s) plan(s)\n"

                        if plans_without_urls:
                            message += f"\n⚠️ {len(plans_without_urls)} plan(s) ne peuvent pas être envoyés via WhatsApp"

            message += "\n" + get_translation("fr", "list_documents_footer")

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list (ALWAYS French)
            message += format_project_list(projects, "fr", max_items=5)

            # Add prompt to select project using centralized translation (ALWAYS French)
            message += get_translation("fr", "list_documents_select_project")

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append({
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": compact_projects(projects[:5])  # Only essential fields
            })

        # Determine list_type based on what we're showing
        list_type = None
        for tool_output in tool_outputs:
            if tool_output.get('tool') == 'list_projects_tool':
                list_type = "projects"
                break

        result = {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs
        }

        if list_type:
            result["list_type"] = list_type

        if carousel_data:
            result["carousel_data"] = carousel_data

        return result

    except Exception as e:
        log.error(f"Error in fast path list_documents: {e}")
        # Return None to trigger fallback to full agent
        return None


async def handle_report_incident(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Dict[str, Any]:
    """Handle report incident intent directly with context-aware project info.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling report incident for {user_id}")

    try:
        # Use helper to get projects and context
        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True,
                "tool_outputs": []
            }

        # Get base template (ALWAYS French)
        template = get_translation("fr", "report_incident")
        tool_outputs = []

        # Scenario 2: Has projects and current project in context
        if current_project_id:
            # Find the current project name
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['nom'] if current_project else projects[0]['nom']

            # Format with current project name
            message = template.replace("{chantier_nom}", project_name)

            # Store current project in tool_outputs for context
            if current_project:
                tool_outputs.append({
                    "tool": "list_projects_tool",
                    "input": {"user_id": user_id},
                    "output": compact_projects([current_project])  # Only essential fields
                })

        # Scenario 3: Has projects but no current project in context
        else:
            # Build message with template header + project section + formatted list (ALWAYS French)
            base_msg = template.split("3. 🏗️")[0]
            base_msg += get_translation("fr", "report_incident_section_header")
            base_msg += format_project_list(projects, "fr", max_items=5)
            base_msg += get_translation("fr", "report_incident_closing")

            message = base_msg

            # Store projects in tool_outputs (user needs to select one)
            tool_outputs.append({
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": compact_projects(projects[:5])  # Only essential fields
            })

        # Determine list_type based on what we're showing
        list_type = None
        for tool_output in tool_outputs:
            if tool_output.get('tool') == 'list_projects_tool':
                list_type = "projects"
                break

        result = {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True,
            "tool_outputs": tool_outputs
        }

        if list_type:
            result["list_type"] = list_type

        return result

    except Exception as e:
        log.error(f"Error in fast path report_incident: {e}")
        # Return None to trigger fallback to full agent
        return None
