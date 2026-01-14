"""LangChain tools for the WhatsApp agent."""
from typing import Optional, List
from langchain.tools import tool
from src.actions import projects, tasks, incidents, documents
from src.integrations.supabase import supabase_client
from src.services.escalation import escalation_service
from src.services.user_context import user_context_service
from src.utils.logger import log


def _normalize_language_input(language: str) -> str:
    """Normalize language input to ISO 639-1 code.

    Handles both ISO codes ('fr', 'en') and full language names ('french', 'english').
    Case-insensitive and strips whitespace.

    Args:
        language: Language code or full name

    Returns:
        ISO 639-1 language code (e.g., 'fr', 'en', 'es')
        Defaults to 'fr' if language is invalid or not recognized
    """
    if not language:
        return "fr"

    language = language.lower().strip()

    # Map full language names to ISO codes
    language_map = {
        "french": "fr",
        "français": "fr",
        "francais": "fr",
        "english": "en",
        "anglais": "en",
        "spanish": "es",
        "español": "es",
        "espanol": "es",
        "espagnol": "es",
        "portuguese": "pt",
        "português": "pt",
        "portugues": "pt",
        "portugais": "pt",
        "romanian": "ro",
        "română": "ro",
        "romana": "ro",
        "roumain": "ro",
        "arabic": "ar",
        "arabe": "ar",
        "german": "de",
        "deutsch": "de",
        "allemand": "de",
        "italian": "it",
        "italiano": "it",
        "italien": "it",
        "czech": "cs",
        "čeština": "cs",
        "cestina": "cs",
        "tchèque": "cs",
        "slovak": "sk",
        "slovenčina": "sk",
        "slovencina": "sk",
        "slovaque": "sk",
        "hungarian": "hu",
        "magyar": "hu",
        "hongrois": "hu",
        "bulgarian": "bg",
        "български": "bg",
        "bulgare": "bg",
        "serbian": "sr",
        "српски": "sr",
        "serbe": "sr",
        "croatian": "hr",
        "hrvatski": "hr",
        "croate": "hr",
        "slovenian": "sl",
        "slovenščina": "sl",
        "slovène": "sl",
        "ukrainian": "uk",
        "українська": "uk",
        "ukrainien": "uk",
        "russian": "ru",
        "русский": "ru",
        "russe": "ru",
        "lithuanian": "lt",
        "lietuvių": "lt",
        "lituanien": "lt",
        "latvian": "lv",
        "latviešu": "lv",
        "letton": "lv",
        "estonian": "et",
        "eesti": "et",
        "estonien": "et",
        "albanian": "sq",
        "shqip": "sq",
        "albanais": "sq",
        "macedonian": "mk",
        "македонски": "mk",
        "macédonien": "mk",
        "bosnian": "bs",
        "bosanski": "bs",
        "bosnien": "bs",
        "polish": "pl",
        "polski": "pl",
        "polonais": "pl",
    }

    # Check if it's a full name that needs mapping
    if language in language_map:
        normalized = language_map[language]
        log.info(f"🔄 Normalized language: '{language}' → '{normalized}'")
        return normalized

    # Check if it's already a valid ISO code (2 letters)
    if len(language) == 2:
        # Validate against supported languages
        supported = ['fr', 'en', 'es', 'pt', 'ro', 'ar', 'de', 'it',
                     'cs', 'sk', 'hu', 'bg', 'sr', 'hr', 'sl', 'uk',
                     'ru', 'lt', 'lv', 'et', 'sq', 'mk', 'bs', 'pl']
        if language in supported:
            log.info(f"✅ Language already in ISO format: '{language}'")
            return language

    # Unknown language - default to French
    log.warning(f"⚠️ Unknown language '{language}', defaulting to 'fr'")
    return "fr"


@tool
async def list_projects_tool(user_id: str) -> str:
    """List all active construction projects (chantiers) for the user.

    Args:
        user_id: The ID of the user requesting the projects

    Returns:
        A formatted string with the list of projects
    """
    log.info(f"🔧 Tool called: list_projects_tool(user_id={user_id[:8]}...)")

    result = await projects.list_projects(user_id)

    if not result["success"]:
        log.warning(f"❌ list_projects_tool failed: {result['message']}")
        return result["message"]

    if not result["data"]:
        log.info(f"📭 list_projects_tool: No projects found")
        return "Aucun projet actif trouvé."

    # Format projects for display (NO technical IDs shown to users)
    output = f"{result['message']}\n\n"
    for i, project in enumerate(result["data"], 1):
        output += f"{i}. 🏗️ {project['nom']}\n"
        if project.get('location'):
            output += f"   📍 {project['location']}\n"
        output += "\n"

    log.info(f"✅ list_projects_tool: Returned {len(result['data'])} projects")
    return output


@tool
async def list_tasks_tool(user_id: str, project_id: Optional[str] = None, status: Optional[str] = None) -> str:
    """List tasks for a specific project.

    If project_id is not provided, uses the user's active project context (current work project).
    The active project is automatically remembered when the user selects a project and expires after 7 hours.

    Args:
        user_id: The ID of the user requesting tasks
        project_id: The ID of the project (optional - uses active project if not provided)
        status: Optional status filter (e.g., 'open', 'in_progress', 'completed')

    Returns:
        A formatted string with the list of tasks
    """
    log.info(f"🔧 Tool called: list_tasks_tool(user_id={user_id[:8]}..., project_id={project_id[:8] if project_id else 'None'}..., status={status})")

    result = await tasks.list_tasks(user_id, project_id, status)

    if not result["success"]:
        log.warning(f"❌ list_tasks_tool failed: {result['message']}")
        return result["message"]

    if not result["data"]:
        log.info(f"📭 list_tasks_tool: No tasks found")
        # Return detailed message so agent can provide helpful response
        return result["message"]

    # Format tasks for display (NO technical IDs shown to users)
    output = f"{result['message']}\n\n"
    for i, task in enumerate(result["data"], 1):
        output += f"{i}. 📝 **{task['title']}**\n"
        output += f"   Statut: {task['status']}\n"
        if task.get('priority'):
            output += f"   ⚡ Priorité: {task['priority']}\n"
        if task.get('due_date'):
            output += f"   📅 Date limite: {task['due_date']}\n"
        output += "\n"

    log.info(f"✅ list_tasks_tool: Returned {len(result['data'])} tasks")
    return output


@tool
async def get_task_description_tool(user_id: str, task_id: str) -> str:
    """Get the detailed description of a specific task.

    Args:
        user_id: The ID of the user requesting the description
        task_id: The ID of the task

    Returns:
        The task description
    """
    log.info(f"🔧 Tool called: get_task_description_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}...)")

    result = await tasks.get_task_description(user_id, task_id)

    if not result["success"]:
        log.warning(f"❌ get_task_description_tool failed: {result['message']}")
        return result["message"]

    log.info(f"✅ get_task_description_tool: Retrieved description")
    return f"Description de la tâche:\n\n{result['data']['description']}"


@tool
async def get_task_plans_tool(user_id: str, task_id: str) -> str:
    """Get plans/blueprints for a specific task.

    Args:
        user_id: The ID of the user requesting plans
        task_id: The ID of the task

    Returns:
        Information about available plans
    """
    log.info(f"🔧 Tool called: get_task_plans_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}...)")

    result = await tasks.get_task_plans(user_id, task_id)

    if not result["success"]:
        log.warning(f"❌ get_task_plans_tool failed: {result['message']}")
        return result["message"]

    if not result["data"]:
        log.info(f"📭 get_task_plans_tool: No plans found")
        return "Aucun plan trouvé pour cette tâche."

    output = f"{result['message']}\n\n"
    for i, plan in enumerate(result["data"], 1):
        output += f"{i}. {plan.get('name', 'Plan')}\n"
        output += f"   URL: {plan.get('url')}\n\n"

    log.info(f"✅ get_task_plans_tool: Returned {len(result['data'])} plans")
    return output


@tool
async def get_task_images_tool(user_id: str, task_id: str) -> str:
    """Get images attached to a specific task.

    Args:
        user_id: The ID of the user requesting images
        task_id: The ID of the task

    Returns:
        Information about available images
    """
    log.info(f"🔧 Tool called: get_task_images_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}...)")

    result = await tasks.get_task_images(user_id, task_id)

    if not result["success"]:
        log.warning(f"❌ get_task_images_tool failed: {result['message']}")
        return result["message"]

    if not result["data"]:
        log.info(f"📭 get_task_images_tool: No images found")
        return "Aucune image trouvée pour cette tâche."

    output = f"{result['message']}\n\n"
    for i, image in enumerate(result["data"], 1):
        output += f"{i}. {image.get('name', 'Image')}\n"
        output += f"   URL: {image.get('url')}\n\n"

    log.info(f"✅ get_task_images_tool: Returned {len(result['data'])} images")
    return output


@tool
async def get_documents_tool(user_id: str, project_id: str, folder_id: Optional[str] = None) -> str:
    """Get documents for a project.

    Args:
        user_id: The ID of the user requesting documents
        project_id: The ID of the project
        folder_id: Optional folder ID to filter documents

    Returns:
        Information about available documents
    """
    log.info(f"🔧 Tool called: get_documents_tool(user_id={user_id[:8]}..., project_id={project_id[:8]}..., folder_id={folder_id[:8] if folder_id else 'None'}...)")

    result = await documents.get_documents(user_id, project_id, folder_id)

    if not result["success"]:
        log.warning(f"❌ get_documents_tool failed: {result['message']}")
        return result["message"]

    if not result["data"]:
        log.info(f"📭 get_documents_tool: No documents found")
        return "Aucun document trouvé."

    output = f"{result['message']}\n\n"
    for i, doc in enumerate(result["data"], 1):
        output += f"{i}. {doc['name']}\n"
        output += f"   Type: {doc['type']}\n"
        output += f"   URL: {doc['url']}\n\n"

    log.info(f"✅ get_documents_tool: Returned {len(result['data'])} documents")
    return output


@tool
async def add_task_comment_tool(user_id: str, task_id: str, comment_text: str) -> str:
    """Add a comment to a task.

    Args:
        user_id: The ID of the user adding the comment
        task_id: The ID of the task
        comment_text: The text comment to add (audio should be transcribed first)

    Returns:
        Success or error message
    """
    log.info(f"🔧 Tool called: add_task_comment_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}..., comment_length={len(comment_text)} chars)")

    result = await tasks.add_task_comment(user_id, task_id, comment_text)

    if result["success"]:
        log.info(f"✅ add_task_comment_tool: Comment added successfully")
    else:
        log.warning(f"❌ add_task_comment_tool failed: {result['message']}")

    return result["message"]


@tool
async def get_task_comments_tool(user_id: str, task_id: str) -> str:
    """Get all comments for a task.

    Args:
        user_id: The ID of the user requesting comments
        task_id: The ID of the task

    Returns:
        All comments for the task
    """
    log.info(f"🔧 Tool called: get_task_comments_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}...)")

    result = await tasks.get_task_comments(user_id, task_id)

    if not result["success"]:
        log.warning(f"❌ get_task_comments_tool failed: {result['message']}")
        return result["message"]

    if not result["data"]:
        log.info(f"📭 get_task_comments_tool: No comments found")
        return "Aucun commentaire trouvé pour cette tâche."

    output = f"{result['message']}\n\n"
    for i, comment in enumerate(result["data"], 1):
        output += f"{i}. {comment.get('author', 'Utilisateur')}: {comment.get('text')}\n"
        output += f"   Date: {comment.get('created_at')}\n\n"

    log.info(f"✅ get_task_comments_tool: Returned {len(result['data'])} comments")
    return output


@tool
async def submit_incident_report_tool(
    user_id: str,
    project_id: str,
    title: str,
    description: str,
    image_urls: List[str],
) -> str:
    """Submit a new incident report. Requires at least one image and a text description.

    Args:
        user_id: The ID of the user submitting the report
        project_id: The ID of the project where the incident occurred
        title: The title of the incident
        description: The description of the incident (text or transcribed audio)
        image_urls: List of image URLs (at least one required)

    Returns:
        Success message with incident ID or error message
    """
    log.info(f"🔧 Tool called: submit_incident_report_tool(user_id={user_id[:8]}..., project_id={project_id[:8]}..., title={title[:50]}..., images={len(image_urls)})")

    result = await incidents.submit_incident_report(
        user_id, project_id, title, description, image_urls
    )

    if result["success"]:
        incident_id = result['data']['incident_id']
        log.info(f"✅ submit_incident_report_tool: Incident created (ID: {incident_id[:8]}...)")
        return f"{result['message']} ID de l'incident: {incident_id}"

    log.warning(f"❌ submit_incident_report_tool failed: {result['message']}")
    return result["message"]


@tool
async def update_incident_report_tool(
    user_id: str,
    incident_id: str,
    additional_text: Optional[str] = None,
    additional_images: Optional[List[str]] = None,
) -> str:
    """Update an existing incident report with additional text or images.

    Args:
        user_id: The ID of the user updating the report
        incident_id: The ID of the incident to update
        additional_text: Additional text to add
        additional_images: Additional image URLs to attach

    Returns:
        Success or error message
    """
    log.info(f"🔧 Tool called: update_incident_report_tool(user_id={user_id[:8]}..., incident_id={incident_id[:8]}..., has_text={additional_text is not None}, images={len(additional_images) if additional_images else 0})")

    result = await incidents.update_incident_report(
        user_id, incident_id, additional_text, additional_images
    )

    if result["success"]:
        log.info(f"✅ update_incident_report_tool: Incident updated successfully")
    else:
        log.warning(f"❌ update_incident_report_tool failed: {result['message']}")

    return result["message"]


@tool
async def update_task_progress_tool(
    user_id: str,
    task_id: str,
    status: str,
    progress_note: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
) -> str:
    """Update task progress with status, optional notes, and optional images.

    Args:
        user_id: The ID of the user updating the task
        task_id: The ID of the task to update
        status: New status for the task (e.g., 'in_progress', 'completed')
        progress_note: Optional progress note
        image_urls: Optional list of image URLs showing progress

    Returns:
        Success or error message
    """
    log.info(f"🔧 Tool called: update_task_progress_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}..., status={status}, has_note={progress_note is not None}, images={len(image_urls) if image_urls else 0})")

    result = await tasks.update_task_progress(
        user_id, task_id, status, progress_note, image_urls
    )

    if result["success"]:
        log.info(f"✅ update_task_progress_tool: Task progress updated to {status}")
    else:
        log.warning(f"❌ update_task_progress_tool failed: {result['message']}")

    return result["message"]


@tool
async def mark_task_complete_tool(user_id: str, task_id: str) -> str:
    """Mark a task as complete.

    Args:
        user_id: The ID of the user marking the task complete
        task_id: The ID of the task to mark complete

    Returns:
        Success or error message
    """
    log.info(f"🔧 Tool called: mark_task_complete_tool(user_id={user_id[:8]}..., task_id={task_id[:8]}...)")

    result = await tasks.mark_task_complete(user_id, task_id)

    if result["success"]:
        log.info(f"✅ mark_task_complete_tool: Task marked as complete")
    else:
        log.warning(f"❌ mark_task_complete_tool failed: {result['message']}")

    return result["message"]


@tool
async def set_language_tool(user_id: str, phone_number: str, language: str) -> str:
    """Change the user's preferred language.

    Args:
        user_id: The ID of the user
        phone_number: The user's WhatsApp phone number
        language: The new language code (e.g., 'en', 'fr', 'es') or full name (e.g., 'english', 'french')

    Returns:
        Success or error message
    """
    log.info(f"🔧 Tool called: set_language_tool(user_id={user_id[:8]}..., phone={phone_number}, language={language})")

    # Normalize language input to ISO 639-1 code
    # Handles both ISO codes ("fr", "en") and full names ("french", "english")
    normalized_language = _normalize_language_input(language)

    result = await supabase_client.create_or_update_user(
        phone_number=phone_number,
        language=normalized_language,
    )

    if result:
        log.info(f"✅ set_language_tool: Language changed to {normalized_language}")
        return f"Langue modifiée en: {normalized_language}"

    log.warning(f"❌ set_language_tool failed to update language")
    return "Erreur lors du changement de langue."


@tool
async def escalate_to_human_tool(
    user_id: str,
    phone_number: str,
    language: str,
    reason: str,
) -> str:
    """Escalate the conversation to a human admin.

    Args:
        user_id: The ID of the user
        phone_number: The user's WhatsApp phone number
        language: The user's language
        reason: The reason for escalation

    Returns:
        Success or error message
    """
    log.info(f"🔧 Tool called: escalate_to_human_tool(user_id={user_id[:8]}..., phone={phone_number}, language={language}, reason={reason[:100]}...)")

    # Import execution context to set escalation flag
    from src.agent.agent import execution_context

    escalation_id = await escalation_service.create_escalation(
        user_id=user_id,
        user_phone=phone_number,
        user_language=language,
        reason=reason,
        context={"escalation_type": "user_request"},
    )

    if escalation_id:
        # Set flag to indicate escalation occurred
        execution_context["escalation_occurred"] = True
        execution_context["tools_called"].append("escalate_to_human_tool")
        log.info(f"✅ escalate_to_human_tool: Escalation created (ID: {escalation_id[:8]}...)")
        log.info("🚨 Escalation flag set: is_escalation will be True")

        # ALWAYS return French - translation to user language happens in pipeline
        from src.utils.whatsapp_formatter import get_translation
        success_message = get_translation("fr", "escalation_success", "en")
        return success_message if success_message else "✅ Votre demande a été transmise à l'équipe administrative."

    log.warning(f"❌ escalate_to_human_tool failed to create escalation")
    return "❌ Erreur lors de la transmission de votre demande. Veuillez réessayer."


@tool
async def remember_user_context_tool(
    user_id: str,
    key: str,
    value: str,
    context_type: str = 'fact'
) -> str:
    """Remember important information about the user for future personalization.

    Use this tool to learn and store facts, preferences, or context about the user
    that will help personalize future conversations.

    Args:
        user_id: The ID of the user
        key: Context key (use snake_case, e.g., 'preferred_contact_time', 'current_project_name')
        value: Context value (the information to remember)
        context_type: Type of context - one of:
            - 'fact': General facts about the user (role, team size, etc.)
            - 'preference': User preferences (communication style, etc.)
            - 'state': Temporary state (current_task, reporting_incident, etc.)
            - 'entity': Named entities (favorite_project, frequent_location, etc.)

    Returns:
        Success or error message

    Examples:
        - User mentions "I'm an electrician" → remember_user_context(user_id, "role", "electrician", "fact")
        - User says "Call me in the morning" → remember_user_context(user_id, "preferred_contact_time", "morning", "preference")
        - User discussing "Building ABC project" → remember_user_context(user_id, "current_project_name", "Building ABC", "state")
    """
    log.info(f"🔧 Tool called: remember_user_context_tool(user_id={user_id[:8]}..., key={key}, value={value[:50]}..., type={context_type})")

    success = await user_context_service.set_context(
        subcontractor_id=user_id,
        key=key,
        value=value,
        context_type=context_type,
        source='inferred',
        confidence=0.8
    )

    if success:
        log.info(f"✅ remember_user_context_tool: Context saved ({key}={value[:30]}...)")
        return f"✅ Remembered: {key} = {value}"

    log.warning(f"❌ remember_user_context_tool failed to save context")
    return f"❌ Could not remember context"


@tool
async def find_project_by_name(user_id: str, project_name: str) -> str:
    """Find a project by its name when the user mentions it.

    IMPORTANT: Only use this tool when:
    1. NO active project exists in the explicit state
    2. User mentions a project by name
    3. You need the project_id to call another tool

    Args:
        user_id: The ID of the user
        project_name: The name or partial name of the project (case-insensitive)

    Returns:
        JSON string with project details if found, or error message
    """
    import json
    from src.actions import projects

    log.info(f"🔧 Tool called: find_project_by_name(user_id={user_id[:8]}..., project_name={project_name})")

    result = await projects.list_projects(user_id)

    if not result["success"] or not result["data"]:
        log.warning(f"❌ find_project_by_name: No projects found for user")
        return json.dumps({
            "success": False,
            "error": "no_projects",
            "message": "Aucun projet trouvé pour cet utilisateur"
        })

    # Search for project by name (fuzzy matching)
    project_name_lower = project_name.lower().strip()
    matches = []

    for project in result["data"]:
        project_nom = project.get("nom", "").lower()
        # Exact match
        if project_nom == project_name_lower:
            log.info(f"✅ find_project_by_name: Exact match found - {project['nom']} (ID: {project['id'][:8]}...)")
            return json.dumps({
                "success": True,
                "project_id": project["id"],
                "project_name": project["nom"],
                "match_type": "exact"
            })
        # Partial match
        elif project_name_lower in project_nom or project_nom in project_name_lower:
            matches.append(project)

    # Single partial match found
    if len(matches) == 1:
        log.info(f"✅ find_project_by_name: Partial match found - {matches[0]['nom']} (ID: {matches[0]['id'][:8]}...)")
        return json.dumps({
            "success": True,
            "project_id": matches[0]["id"],
            "project_name": matches[0]["nom"],
            "match_type": "partial"
        })

    # Multiple matches - return list for disambiguation
    elif len(matches) > 1:
        log.info(f"📋 find_project_by_name: Multiple matches found ({len(matches)} projects)")
        return json.dumps({
            "success": False,
            "error": "multiple_matches",
            "message": f"Plusieurs projets correspondent à '{project_name}'",
            "matches": [{"name": p["nom"]} for p in matches]
        })

    # No matches
    else:
        log.warning(f"❌ find_project_by_name: No matches found for '{project_name}'")
        return json.dumps({
            "success": False,
            "error": "not_found",
            "message": f"Aucun projet trouvé avec le nom '{project_name}'"
        })


# List of all tools
all_tools = [
    list_projects_tool,
    list_tasks_tool,
    get_task_description_tool,
    get_task_plans_tool,
    get_task_images_tool,
    get_documents_tool,
    add_task_comment_tool,
    get_task_comments_tool,
    submit_incident_report_tool,
    update_incident_report_tool,
    update_task_progress_tool,
    mark_task_complete_tool,
    set_language_tool,
    escalate_to_human_tool,
    remember_user_context_tool,
    find_project_by_name,  # Layer 3: Fallback lookup when no explicit state
]
