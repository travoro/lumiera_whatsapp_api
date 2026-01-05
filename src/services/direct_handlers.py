"""Direct intent handlers for high-confidence classifications.

These handlers execute directly without calling the main agent,
providing fast responses for simple, unambiguous requests.
"""
from typing import Dict, Any, Optional
from src.integrations.supabase import supabase_client
from src.integrations.twilio import twilio_client
from src.services.escalation import escalation_service
from src.utils.logger import log


async def handle_greeting(
    user_id: str,
    user_name: str,
    language: str
) -> Dict[str, Any]:
    """Handle greeting intent directly.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling greeting for {user_name}")

    # Personalized greeting based on language
    greetings = {
        "fr": f"Bonjour{', ' + user_name if user_name else ''} ! 👋\n\nComment puis-je vous aider aujourd'hui ?\n\n1. 🏗️ Voir mes chantiers actifs\n2. 📋 Consulter mes tâches\n3. 🚨 Signaler un incident\n4. ✅ Mettre à jour ma progression\n5. 🗣️ Parler avec l'équipe\n\nQue souhaitez-vous faire ?",
        "en": f"Hello{', ' + user_name if user_name else ''} ! 👋\n\nHow can I help you today?\n\n1. 🏗️ View my active projects\n2. 📋 Check my tasks\n3. 🚨 Report an incident\n4. ✅ Update my progress\n5. 🗣️ Talk to the team\n\nWhat would you like to do?",
        "es": f"Hola{', ' + user_name if user_name else ''} ! 👋\n\n¿Cómo puedo ayudarte hoy?\n\n1. 🏗️ Ver mis proyectos activos\n2. 📋 Consultar mis tareas\n3. 🚨 Reportar un incidente\n4. ✅ Actualizar mi progreso\n5. 🗣️ Hablar con el equipo\n\n¿Qué te gustaría hacer?",
        "ro": f"Bună{', ' + user_name if user_name else ''} ! 👋\n\nCum te pot ajuta astăzi?\n\n1. 🏗️ Vezi șantierele mele active\n2. 📋 Consultă sarcinile mele\n3. 🚨 Raportează un incident\n4. ✅ Actualizează progresul\n5. 🗣️ Vorbește cu echipa\n\nCe ai dori să faci?",
    }

    message = greetings.get(language, greetings["fr"])

    return {
        "message": message,
        "escalation": False,
        "tools_called": [],
        "fast_path": True
    }


async def handle_list_projects(
    user_id: str,
    user_name: str,
    language: str
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
            messages = {
                "fr": "Vous n'avez pas encore de chantiers actifs.",
                "en": "You don't have any active projects yet.",
                "es": "Aún no tienes proyectos activos.",
                "ro": "Nu ai încă șantiere active.",
            }
            return {
                "message": messages.get(language, messages["fr"]),
                "escalation": False,
                "tools_called": ["list_projects_tool"],
                "fast_path": True
            }

        # Format projects list
        messages = {
            "fr": f"Vous avez {len(projects)} chantier(s) actif(s) :\n\n",
            "en": f"You have {len(projects)} active project(s):\n\n",
            "es": f"Tienes {len(projects)} proyecto(s) activo(s):\n\n",
            "ro": f"Ai {len(projects)} șantier(e) activ(e):\n\n",
        }

        message = messages.get(language, messages["fr"])

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
    reason: str = "User requested to speak with team"
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
            messages = {
                "fr": "✅ Votre demande a été transmise à l'équipe administrative. Un membre de l'équipe vous contactera sous peu.",
                "en": "✅ Your request has been forwarded to the admin team. A team member will contact you shortly.",
                "es": "✅ Tu solicitud ha sido enviada al equipo administrativo. Un miembro del equipo te contactará pronto.",
                "ro": "✅ Cererea ta a fost trimisă echipei administrative. Un membru al echipei te va contacta în curând.",
            }

            return {
                "message": messages.get(language, messages["fr"]),
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


# Intent handler mapping
INTENT_HANDLERS = {
    "greeting": handle_greeting,
    "list_projects": handle_list_projects,
    "escalate": handle_escalation,
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
