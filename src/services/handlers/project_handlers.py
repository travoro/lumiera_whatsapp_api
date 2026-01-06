"""Project and content-related intent handlers.

These handlers execute directly without calling the main agent,
providing fast responses for project, document, and incident operations.

IMPORTANT: All handlers ALWAYS return French text. Translation to user language
happens in the pipeline (message.py:272-278 or message_pipeline.py:414-465).
"""
from typing import Dict, Any
from src.integrations.supabase import supabase_client
from src.actions import documents as document_actions
from src.utils.whatsapp_formatter import get_translation
from src.utils.handler_helpers import get_projects_with_context, format_project_list
from src.utils.logger import log


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
                "fast_path": True
            }

        # Format projects list with translation (ALWAYS French)
        header_template = get_translation("fr", "projects_list_header")
        message = header_template.format(count=len(projects)) if header_template else f"You have {len(projects)} projects:\n\n"

        for i, project in enumerate(projects, 1):
            message += f"{i}. 🏗️ *{project['name']}*\n"
            if project.get('location'):
                message += f"   📍 {project['location']}\n"
            message += f"   Statut: {project['status']}\n\n"

        return {
            "message": message,
            "escalation": False,
            "tools_called": ["list_projects_tool"],
            "fast_path": True
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
                "fast_path": True
            }

        # Use centralized translations (ALWAYS French)
        message = get_translation("fr", "list_documents_header")

        # Scenario 2: Has current project in context
        if current_project_id:
            # Find the current project
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['name'] if current_project else projects[0]['name']
            project_id = current_project['id'] if current_project else projects[0]['id']

            message += get_translation("fr", "list_documents_project_context").format(project_name=project_name)

            # Get documents for this project using actions layer
            doc_result = await document_actions.get_documents(user_id, project_id)

            if not doc_result["success"] or not doc_result["data"]:
                message += get_translation("fr", "list_documents_no_documents")
            else:
                documents = doc_result["data"]
                for i, doc in enumerate(documents[:10], 1):  # Limit to 10 documents
                    doc_type = doc.get('type', 'document')
                    doc_name = doc.get('name', 'Untitled')

                    # Document type emoji
                    type_emoji = {
                        'pdf': '📕',
                        'image': '🖼️',
                        'plan': '📐',
                        'contract': '📋',
                        'invoice': '🧾'
                    }.get(doc_type, '📄')

                    message += f"{i}. {type_emoji} {doc_name}\n"

            message += get_translation("fr", "list_documents_footer")

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list (ALWAYS French)
            message += format_project_list(projects, "fr", max_items=5)

            # Add prompt to select project using centralized translation (ALWAYS French)
            message += get_translation("fr", "list_documents_select_project")

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

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
                "fast_path": True
            }

        # Get base template (ALWAYS French)
        template = get_translation("fr", "report_incident")

        # Scenario 2: Has projects and current project in context
        if current_project_id:
            # Find the current project name
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['name'] if current_project else projects[0]['name']

            # Format with current project name
            message = template.replace("{chantier_nom}", project_name)

        # Scenario 3: Has projects but no current project in context
        else:
            # Build message with template header + project section + formatted list (ALWAYS French)
            base_msg = template.split("3. 🏗️")[0]
            base_msg += get_translation("fr", "report_incident_section_header")
            base_msg += format_project_list(projects, "fr", max_items=5)
            base_msg += get_translation("fr", "report_incident_closing")

            message = base_msg

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

    except Exception as e:
        log.error(f"Error in fast path report_incident: {e}")
        # Return None to trigger fallback to full agent
        return None
