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
        # Use helper to get projects and context
        from src.utils.handler_helpers import get_projects_with_context

        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
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
            # Use helper to format project list
            from src.utils.handler_helpers import format_project_list

            # Extract template header (everything before "3. 🏗️")
            # Add project section header per language
            project_section_headers = {
                "fr": "3. 🏗️ Le chantier concerné\n\n",
                "en": "3. 🏗️ The concerned site\n\n",
                "es": "3. 🏗️ La obra concernida\n\n",
                "pt": "3. 🏗️ A obra em questão\n\n",
                "de": "3. 🏗️ Die betroffene Baustelle\n\n",
                "it": "3. 🏗️ Il cantiere interessato\n\n",
                "ro": "3. 🏗️ Șantierul în cauză\n\n",
                "pl": "3. 🏗️ Plac budowy\n\n",
                "ar": "3. 🏗️ موقع البناء المعني\n\n"
            }

            # Build message with template header + project section + formatted list
            base_msg = template.split("3. 🏗️")[0]
            base_msg += project_section_headers.get(language, project_section_headers["en"])
            base_msg += format_project_list(projects, language, max_items=5)

            # Add closing prompt per language
            closing_prompts = {
                "fr": "\nVous pouvez m'envoyer les éléments un par un, je vous guiderai pas à pas.",
                "en": "\nYou can send me the elements one by one, I'll guide you step by step.",
                "es": "\nPuedes enviarme los elementos uno por uno, te guiaré paso a paso.",
                "pt": "\nVocê pode me enviar os elementos um por um, vou guiá-lo passo a passo.",
                "de": "\nSie können mir die Elemente einzeln senden, ich führe Sie Schritt für Schritt.",
                "it": "\nPuoi inviarmi gli elementi uno per uno, ti guiderò passo dopo passo.",
                "ro": "\nPoți să-mi trimiți elementele unul câte unul, te voi ghida pas cu pas.",
                "pl": "\nMożesz przesyłać mi elementy jeden po drugim, poprowadzę Cię krok po kroku.",
                "ar": "\nيمكنك إرسال العناصر واحدة تلو الأخرى، سأرشدك خطوة بخطوة."
            }
            base_msg += closing_prompts.get(language, closing_prompts["en"])

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


async def handle_update_progress(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Dict[str, Any]:
    """Handle update progress intent with context-aware project and task selection.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling update progress for {user_id}")

    try:
        # Use helper to get projects and context
        from src.utils.handler_helpers import get_projects_with_context

        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True
            }

        # Use centralized translations
        message = get_translation(language, "update_progress_header")

        # Scenario 2: Has current project in context
        if current_project_id:
            # Find the current project
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['name'] if current_project else projects[0]['name']
            project_id = current_project['id'] if current_project else projects[0]['id']

            message += get_translation(language, "update_progress_project_context").format(project_name=project_name)

            # Get tasks for this project using actions layer
            from src.actions import tasks as task_actions
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += get_translation(language, "update_progress_no_tasks")
            else:
                tasks = task_result["data"]
                message += get_translation(language, "update_progress_tasks_header")
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    progress = task.get('progress', 0)
                    message += f"{i}. {task['title']} ({progress}%)\n"

            message += get_translation(language, "update_progress_footer")

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list
            from src.utils.handler_helpers import format_project_list
            message += format_project_list(projects, language, max_items=5)

            message += get_translation(language, "update_progress_footer")

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

    except Exception as e:
        log.error(f"Error in fast path update_progress: {e}")
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
        from src.utils.handler_helpers import get_projects_with_context

        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True
            }

        # Use centralized translations
        message = get_translation(language, "list_documents_header")

        # Scenario 2: Has current project in context
        if current_project_id:
            # Find the current project
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['name'] if current_project else projects[0]['name']
            project_id = current_project['id'] if current_project else projects[0]['id']

            message += get_translation(language, "list_documents_project_context").format(project_name=project_name)

            # Get documents for this project using actions layer
            from src.actions import documents as document_actions
            doc_result = await document_actions.get_documents(user_id, project_id)

            if not doc_result["success"] or not doc_result["data"]:
                message += get_translation(language, "list_documents_no_documents")
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

            message += get_translation(language, "list_documents_footer")

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list
            from src.utils.handler_helpers import format_project_list
            message += format_project_list(projects, language, max_items=5)

            # Add prompt to select project using centralized translation
            message += get_translation(language, "list_documents_select_project")

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


async def handle_list_tasks(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    **kwargs
) -> Dict[str, Any]:
    """Handle list tasks intent with context-aware project selection.

    Returns:
        Dict with message, escalation, tools_called
    """
    log.info(f"🚀 FAST PATH: Handling list tasks for {user_id}")

    try:
        # Use helper to get projects and context
        from src.utils.handler_helpers import get_projects_with_context

        projects, current_project_id, no_projects_msg = await get_projects_with_context(user_id, language)

        # Scenario 1: No projects available
        if no_projects_msg:
            return {
                "message": no_projects_msg,
                "escalation": False,
                "tools_called": [],
                "fast_path": True
            }

        # Base prompt structure by language
        prompts = {
            "fr": {
                "header": "Voici vos tâches. 📋\n\n",
                "project_context": "Pour le chantier **{project_name}** :\n\n",
                "project_list": "Chantiers disponibles :\n",
                "tasks_header": "",
                "no_tasks": "Aucune tâche pour ce chantier.",
                "footer": "\n\nDites-moi si vous souhaitez voir les tâches d'un autre chantier."
            },
            "en": {
                "header": "Here are your tasks. 📋\n\n",
                "project_context": "For the site **{project_name}** :\n\n",
                "project_list": "Available sites:\n",
                "tasks_header": "",
                "no_tasks": "No tasks for this site.",
                "footer": "\n\nLet me know if you want to see tasks for another site."
            },
            "es": {
                "header": "Aquí están tus tareas. 📋\n\n",
                "project_context": "Para la obra **{project_name}** :\n\n",
                "project_list": "Obras disponibles:\n",
                "tasks_header": "",
                "no_tasks": "No hay tareas para esta obra.",
                "footer": "\n\nDime si quieres ver las tareas de otra obra."
            },
            "pt": {
                "header": "Aqui estão suas tarefas. 📋\n\n",
                "project_context": "Para a obra **{project_name}** :\n\n",
                "project_list": "Obras disponíveis:\n",
                "tasks_header": "",
                "no_tasks": "Não há tarefas para esta obra.",
                "footer": "\n\nDiga-me se você quer ver as tarefas de outra obra."
            },
            "de": {
                "header": "Hier sind Ihre Aufgaben. 📋\n\n",
                "project_context": "Für die Baustelle **{project_name}** :\n\n",
                "project_list": "Verfügbare Baustellen:\n",
                "tasks_header": "",
                "no_tasks": "Keine Aufgaben für diese Baustelle.",
                "footer": "\n\nSagen Sie mir, wenn Sie Aufgaben für eine andere Baustelle sehen möchten."
            },
            "it": {
                "header": "Ecco i tuoi compiti. 📋\n\n",
                "project_context": "Per il cantiere **{project_name}** :\n\n",
                "project_list": "Cantieri disponibili:\n",
                "tasks_header": "",
                "no_tasks": "Nessun compito per questo cantiere.",
                "footer": "\n\nDimmi se vuoi vedere i compiti di un altro cantiere."
            },
            "ro": {
                "header": "Iată sarcinile tale. 📋\n\n",
                "project_context": "Pentru șantierul **{project_name}** :\n\n",
                "project_list": "Șantiere disponibile:\n",
                "tasks_header": "",
                "no_tasks": "Nu există sarcini pentru acest șantier.",
                "footer": "\n\nSpune-mi dacă vrei să vezi sarcinile unui alt șantier."
            },
            "pl": {
                "header": "Oto Twoje zadania. 📋\n\n",
                "project_context": "Dla placu budowy **{project_name}** :\n\n",
                "project_list": "Dostępne place budowy:\n",
                "tasks_header": "",
                "no_tasks": "Brak zadań dla tego placu budowy.",
                "footer": "\n\nPowiedz mi, jeśli chcesz zobaczyć zadania dla innego placu budowy."
            },
            "ar": {
                "header": "إليك مهامك. 📋\n\n",
                "project_context": "لموقع البناء **{project_name}** :\n\n",
                "project_list": "مواقع البناء المتاحة:\n",
                "tasks_header": "",
                "no_tasks": "لا توجد مهام لهذا الموقع.",
                "footer": "\n\nأخبرني إذا كنت تريد رؤية مهام موقع آخر."
            }
        }

        # Get language prompts (fallback to English)
        lang_prompts = prompts.get(language, prompts["en"])
        message = lang_prompts["header"]

        # Scenario 2: Has current project in context
        if current_project_id:
            # Find the current project
            current_project = next((p for p in projects if str(p.get('id')) == current_project_id), None)
            project_name = current_project['name'] if current_project else projects[0]['name']
            project_id = current_project['id'] if current_project else projects[0]['id']

            message += lang_prompts["project_context"].format(project_name=project_name)

            # Get tasks for this project using actions layer
            from src.actions import tasks as task_actions
            task_result = await task_actions.list_tasks(user_id, project_id)

            if not task_result["success"] or not task_result["data"]:
                message += lang_prompts["no_tasks"]
            else:
                tasks = task_result["data"]
                message += lang_prompts["tasks_header"]
                for i, task in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                    status = task.get('status', 'pending')
                    progress = task.get('progress', 0)

                    # Status emoji
                    status_emoji = "⏳" if status == "pending" else "✅" if status == "completed" else "🔄"

                    message += f"{i}. {status_emoji} {task['title']}"
                    if progress > 0:
                        message += f" ({progress}%)"
                    message += "\n"

            message += lang_prompts["footer"]

        # Scenario 3: Has projects but no current project in context
        else:
            # Use helper to format project list
            from src.utils.handler_helpers import format_project_list
            message += format_project_list(projects, language, max_items=5)

            # Add prompt to select project
            select_prompts = {
                "fr": "\nDites-moi pour quel chantier vous souhaitez voir les tâches.",
                "en": "\nTell me which site you want to see tasks for.",
                "es": "\nDime para qué obra quieres ver las tareas.",
                "pt": "\nDiga-me para qual obra você quer ver as tarefas.",
                "de": "\nSagen Sie mir, für welche Baustelle Sie Aufgaben sehen möchten.",
                "it": "\nDimmi per quale cantiere vuoi vedere i compiti.",
                "ro": "\nSpune-mi pentru care șantier vrei să vezi sarcinile.",
                "pl": "\nPowiedz mi, dla którego placu budowy chcesz zobaczyć zadania.",
                "ar": "\nأخبرني لأي موقع تريد رؤية المهام."
            }
            message += select_prompts.get(language, select_prompts["en"])

        return {
            "message": message,
            "escalation": False,
            "tools_called": [],
            "fast_path": True
        }

    except Exception as e:
        log.error(f"Error in fast path list_tasks: {e}")
        # Return None to trigger fallback to full agent
        return None


# Intent handler mapping
INTENT_HANDLERS = {
    "greeting": handle_greeting,
    "list_projects": handle_list_projects,
    "list_tasks": handle_list_tasks,
    "list_documents": handle_list_documents,
    "escalate": handle_escalation,
    "report_incident": handle_report_incident,
    "update_progress": handle_update_progress,
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
