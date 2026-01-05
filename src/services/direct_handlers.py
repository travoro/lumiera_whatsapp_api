"""Direct intent handlers for high-confidence classifications.

These handlers execute directly without calling the main agent,
providing fast responses for simple, unambiguous requests.
"""
from typing import Dict, Any, Optional
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.services.escalation import escalation_service
from src.utils.whatsapp_formatter import get_translation
from src.utils.logger import log


async def handle_greeting(
    user_id: str,
    user_name: str,
    language: str,
    phone_number: str = None,
    **kwargs
) -> Dict[str, Any]:
    """Handle greeting intent directly.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling greeting for {user_name}")

    # Format name for greeting (with comma if provided)
    name_part = f", {user_name}" if user_name else ""

    # Get translated greeting from centralized translations
    greeting_template = get_translation(language, "greeting")
    message = greeting_template.format(name=name_part) if greeting_template else f"Hello{name_part}!"

    return {
        "message": message,
        "escalation": False,
        "tools_called": [],
        "fast_path": True
    }


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
                "message": get_translation(language, "no_projects"),
                "escalation": False,
                "tools_called": ["list_projects_tool"],
                "fast_path": True
            }

        # Format projects list with translation
        header_template = get_translation(language, "projects_list_header")
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


async def handle_escalation(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    reason: str = "User requested to speak with team",
    **kwargs
) -> Dict[str, Any]:
    """Handle escalation intent directly.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Escalating for {user_id}")

    try:
        escalation_id = await escalation_service.create_escalation(
            user_id=user_id,
            user_phone=phone_number,
            user_language=language,
            reason=reason,
            context={"escalation_type": "direct_intent", "fast_path": True},
        )

        if escalation_id:
            return {
                "message": get_translation(language, "escalation_success"),
                "escalation": True,
                "tools_called": ["escalate_to_human_tool"],
                "fast_path": True
            }
        else:
            # Escalation failed, return None to trigger full agent
            return None

    except Exception as e:
        log.error(f"Error in fast path escalation: {e}")
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
        # Import user_context service
        from src.services.user_context import user_context_service

        # Check for current project in context
        current_project_id = await user_context_service.get_context(user_id, 'current_project')

        # Get user's projects
        projects = await supabase_client.list_projects(user_id)

        # Scenario 1: No projects available
        if not projects:
            message = get_translation(language, "no_projects")
            return {
                "message": message,
                "escalation": False,
                "tools_called": [],
                "fast_path": True
            }

        # Get base template
        template = get_translation(language, "report_incident")

        # Scenario 2: Has projects and current project in context
        if current_project_id:
            # Find the current project name
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['name'] if current_project else projects[0]['name']

            # Format with current project name
            message = template.replace("{chantier_nom}", project_name)

        # Scenario 3: Has projects but no current project in context
        else:
            # Remove the conditional part about current project
            # Replace "si ce n'est pas le chantier {chantier_nom}" with list of projects
            if language == "fr":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ Le chantier concerné\n\n"
                base_msg += "Chantiers disponibles :\n"
            elif language == "en":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ The concerned site\n\n"
                base_msg += "Available sites:\n"
            elif language == "es":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ La obra concernida\n\n"
                base_msg += "Obras disponibles:\n"
            elif language == "pt":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ A obra em questão\n\n"
                base_msg += "Obras disponíveis:\n"
            elif language == "de":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ Die betroffene Baustelle\n\n"
                base_msg += "Verfügbare Baustellen:\n"
            elif language == "it":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ Il cantiere interessato\n\n"
                base_msg += "Cantieri disponibili:\n"
            elif language == "ro":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ Șantierul în cauză\n\n"
                base_msg += "Șantiere disponibile:\n"
            elif language == "pl":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ Plac budowy\n\n"
                base_msg += "Dostępne place budowy:\n"
            elif language == "ar":
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ موقع البناء المعني\n\n"
                base_msg += "مواقع البناء المتاحة:\n"
            else:
                base_msg = template.split("3. 🏗️")[0] + "3. 🏗️ The concerned site\n\n"
                base_msg += "Available sites:\n"

            # Add project list
            for i, project in enumerate(projects[:5], 1):  # Limit to 5 projects
                base_msg += f"{i}. {project['name']}\n"

            # Add closing
            if language == "fr":
                base_msg += "\nVous pouvez m'envoyer les éléments un par un, je vous guiderai pas à pas."
            elif language == "en":
                base_msg += "\nYou can send me the elements one by one, I'll guide you step by step."
            elif language == "es":
                base_msg += "\nPuedes enviarme los elementos uno por uno, te guiaré paso a paso."
            elif language == "pt":
                base_msg += "\nVocê pode me enviar os elementos um por um, vou guiá-lo passo a passo."
            elif language == "de":
                base_msg += "\nSie können mir die Elemente einzeln senden, ich führe Sie Schritt für Schritt."
            elif language == "it":
                base_msg += "\nPuoi inviarmi gli elementi uno per uno, ti guiderò passo dopo passo."
            elif language == "ro":
                base_msg += "\nPoți să-mi trimiți elementele unul câte unul, te voi ghida pas cu pas."
            elif language == "pl":
                base_msg += "\nMożesz przesyłać mi elementy jeden po drugim, poprowadzę Cię krok po kroku."
            elif language == "ar":
                base_msg += "\nيمكنك إرسال العناصر واحدة تلو الأخرى، سأرشدك خطوة بخطوة."
            else:
                base_msg += "\nYou can send me the elements one by one, I'll guide you step by step."

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


# Intent handler mapping
INTENT_HANDLERS = {
    "greeting": handle_greeting,
    "list_projects": handle_list_projects,
    "escalate": handle_escalation,
    "report_incident": handle_report_incident,
    # Add more handlers as needed
}


async def execute_direct_handler(
    intent: str,
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """Execute direct handler for given intent.

    Args:
        intent: Intent name
        user_id: User ID
        phone_number: User phone number
        user_name: User name
        language: User language
        **kwargs: Additional parameters

    Returns:
        Dict with message, escalation, tools_called if successful
        None if handler fails (triggers fallback to full agent)
    """
    handler = INTENT_HANDLERS.get(intent)

    if not handler:
        log.warning(f"No direct handler for intent: {intent}")
        return None

    try:
        result = await handler(
            user_id=user_id,
            phone_number=phone_number,
            user_name=user_name,
            language=language,
            **kwargs
        )

        if result:
            log.info(f"✅ Fast path successful for intent: {intent}")
        else:
            log.warning(f"⚠️ Fast path handler returned None for intent: {intent}")

        return result

    except Exception as e:
        log.error(f"❌ Fast path failed for intent {intent}: {e}")
        return None
