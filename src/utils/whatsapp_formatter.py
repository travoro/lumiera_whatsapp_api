"""WhatsApp message formatter with interactive message support."""
from typing import Dict, List, Optional, Any
import re
from src.integrations.twilio import twilio_client
from src.services.template_manager import template_manager
from src.utils.logger import log


# Robust translation dictionary for WhatsApp interactive messages
TRANSLATIONS = {
    "fr": {
        "greeting": "Bonjour {name}, comment puis-je vous aider aujourd'hui ?",
        "button": "Options",
        "no_projects": "Vous n'avez pas encore de chantiers actifs.",
        "projects_list_header": "Vous avez {count} chantier(s) actif(s) :\n\n",
        "escalation_success": "✅ Votre demande a été transmise à l'équipe administrative. Un membre de l'équipe vous contactera sous peu.",
        "report_incident": "Je vais vous aider à signaler un incident. 🚨\n\nPour créer un rapport d'incident, j'ai besoin de :\n1. 📸 Au moins une photo du problème\n2. 📝 Une description écrite ou audio de ce qui s'est passé\n3. 🏗️ Le chantier concerné, si ce n'est pas le chantier {chantier_nom}\n\nVous pouvez m'envoyer les éléments un par un, je vous guiderai pas à pas.",
        "menu_items": [
            {"title": "Voir mes chantiers", "id": "view_sites_fr", "description": "Projets actifs"},
            {"title": "Consulter mes taches", "id": "view_tasks_fr", "description": "Taches assignees"},
            {"title": "Acceder aux documents", "id": "view_documents_fr", "description": "Plans et docs"},
            {"title": "Signaler un incident", "id": "report_incident_fr", "description": "Declarer probleme"},
            {"title": "Progression", "id": "update_progress_fr", "description": "Mettre a jour taches"},
            {"title": "Contacter equipe", "id": "talk_team_fr", "description": "Parler administration"},
        ],
    },
    "en": {
        "greeting": "Hello {name}, how can I help you today?",
        "button": "Options",
        "no_projects": "You don't have any active projects yet.",
        "projects_list_header": "You have {count} active project(s):\n\n",
        "escalation_success": "✅ Your request has been forwarded to the admin team. A team member will contact you shortly.",
        "report_incident": "I'll help you report an incident. 🚨\n\nTo create an incident report, I need:\n1. 📸 At least one photo of the problem\n2. 📝 A written or audio description of what happened\n3. 🏗️ The concerned site, if it's not the site {chantier_nom}\n\nYou can send me the elements one by one, I'll guide you step by step.",
        "menu_items": [
            {"title": "View my sites", "id": "view_sites_en", "description": "Active projects"},
            {"title": "Check my tasks", "id": "view_tasks_en", "description": "Assigned tasks"},
            {"title": "Access documents", "id": "view_documents_en", "description": "Plans and docs"},
            {"title": "Report incident", "id": "report_incident_en", "description": "Declare problem"},
            {"title": "Update progress", "id": "update_progress_en", "description": "Update tasks"},
            {"title": "Talk to team", "id": "talk_team_en", "description": "Contact admin"},
        ],
    },
    "es": {
        "greeting": "Hola {name}, ¿cómo puedo ayudarte hoy?",
        "button": "Opciones",
        "no_projects": "Aún no tienes proyectos activos.",
        "projects_list_header": "Tienes {count} proyecto(s) activo(s):\n\n",
        "escalation_success": "✅ Tu solicitud ha sido enviada al equipo administrativo. Un miembro del equipo te contactará pronto.",
        "report_incident": "Te ayudaré a reportar un incidente. 🚨\n\nPara crear un reporte de incidente, necesito:\n1. 📸 Al menos una foto del problema\n2. 📝 Una descripción escrita o de audio de lo que pasó\n3. 🏗️ La obra concernida, si no es la obra {chantier_nom}\n\nPuedes enviarme los elementos uno por uno, te guiaré paso a paso.",
        "menu_items": [
            {"title": "Ver mis obras", "id": "view_sites_es", "description": "Proyectos activos"},
            {"title": "Ver mis tareas", "id": "view_tasks_es", "description": "Tareas asignadas"},
            {"title": "Acceder documentos", "id": "view_documents_es", "description": "Planos y docs"},
            {"title": "Reportar incidente", "id": "report_incident_es", "description": "Declarar problema"},
            {"title": "Actualizar progreso", "id": "update_progress_es", "description": "Actualizar tareas"},
            {"title": "Hablar con equipo", "id": "talk_team_es", "description": "Contactar admin"},
        ],
    },
    "pt": {
        "greeting": "Olá {name}, como posso ajudá-lo hoje?",
        "button": "Opções",
        "no_projects": "Você ainda não tem projetos ativos.",
        "projects_list_header": "Você tem {count} projeto(s) ativo(s):\n\n",
        "escalation_success": "✅ Sua solicitação foi encaminhada para a equipe administrativa. Um membro da equipe entrará em contato em breve.",
        "report_incident": "Vou ajudá-lo a relatar um incidente. 🚨\n\nPara criar um relatório de incidente, preciso de:\n1. 📸 Pelo menos uma foto do problema\n2. 📝 Uma descrição escrita ou em áudio do que aconteceu\n3. 🏗️ A obra em questão, se não for a obra {chantier_nom}\n\nVocê pode me enviar os elementos um por um, vou guiá-lo passo a passo.",
        "menu_items": [
            {"title": "Ver minhas obras", "id": "view_sites_pt", "description": "Projetos ativos"},
            {"title": "Ver minhas tarefas", "id": "view_tasks_pt", "description": "Tarefas atribuidas"},
            {"title": "Acessar documentos", "id": "view_documents_pt", "description": "Planos e docs"},
            {"title": "Relatar incidente", "id": "report_incident_pt", "description": "Declarar problema"},
            {"title": "Atualizar progresso", "id": "update_progress_pt", "description": "Atualizar tarefas"},
            {"title": "Falar com equipe", "id": "talk_team_pt", "description": "Contatar admin"},
        ],
    },
    "de": {
        "greeting": "Hallo {name}, wie kann ich Ihnen heute helfen?",
        "button": "Optionen",
        "no_projects": "Sie haben noch keine aktiven Projekte.",
        "projects_list_header": "Sie haben {count} aktive(s) Projekt(e):\n\n",
        "escalation_success": "✅ Ihre Anfrage wurde an das Admin-Team weitergeleitet. Ein Teammitglied wird sich in Kürze bei Ihnen melden.",
        "report_incident": "Ich helfe Ihnen, einen Vorfall zu melden. 🚨\n\nUm einen Vorfallbericht zu erstellen, benötige ich:\n1. 📸 Mindestens ein Foto des Problems\n2. 📝 Eine schriftliche oder Audio-Beschreibung dessen, was passiert ist\n3. 🏗️ Die betroffene Baustelle, falls es sich nicht um die Baustelle {chantier_nom} handelt\n\nSie können mir die Elemente einzeln senden, ich führe Sie Schritt für Schritt.",
        "menu_items": [
            {"title": "Meine Baustellen", "id": "view_sites_de", "description": "Aktive Projekte"},
            {"title": "Meine Aufgaben", "id": "view_tasks_de", "description": "Zugewiesene Aufgaben"},
            {"title": "Dokumente", "id": "view_documents_de", "description": "Plane und Docs"},
            {"title": "Vorfall melden", "id": "report_incident_de", "description": "Problem melden"},
            {"title": "Fortschritt", "id": "update_progress_de", "description": "Aufgaben update"},
            {"title": "Team kontaktieren", "id": "talk_team_de", "description": "Admin kontakt"},
        ],
    },
    "it": {
        "greeting": "Ciao {name}, come posso aiutarti oggi?",
        "button": "Opzioni",
        "no_projects": "Non hai ancora progetti attivi.",
        "projects_list_header": "Hai {count} progetto/i attivo/i:\n\n",
        "escalation_success": "✅ La tua richiesta è stata inoltrata al team amministrativo. Un membro del team ti contatterà a breve.",
        "report_incident": "Ti aiuterò a segnalare un incidente. 🚨\n\nPer creare un rapporto di incidente, ho bisogno di:\n1. 📸 Almeno una foto del problema\n2. 📝 Una descrizione scritta o audio di cosa è successo\n3. 🏗️ Il cantiere interessato, se non è il cantiere {chantier_nom}\n\nPuoi inviarmi gli elementi uno per uno, ti guiderò passo dopo passo.",
        "menu_items": [
            {"title": "Vedi cantieri", "id": "view_sites_it", "description": "Progetti attivi"},
            {"title": "Vedi compiti", "id": "view_tasks_it", "description": "Compiti assegnati"},
            {"title": "Accedi documenti", "id": "view_documents_it", "description": "Piani e docs"},
            {"title": "Segnala incidente", "id": "report_incident_it", "description": "Dichiarare problema"},
            {"title": "Aggiorna progresso", "id": "update_progress_it", "description": "Aggiornare compiti"},
            {"title": "Parla con team", "id": "talk_team_it", "description": "Contattare admin"},
        ],
    },
    "ro": {
        "greeting": "Bună {name}, cum te pot ajuta astăzi ?",
        "button": "Opțiuni",
        "no_projects": "Nu ai încă șantiere active.",
        "projects_list_header": "Ai {count} șantier(e) activ(e):\n\n",
        "escalation_success": "✅ Cererea ta a fost trimisă echipei administrative. Un membru al echipei te va contacta în curând.",
        "report_incident": "Te voi ajuta să raportezi un incident. 🚨\n\nPentru a crea un raport de incident, am nevoie de:\n1. 📸 Cel puțin o fotografie a problemei\n2. 📝 O descriere scrisă sau audio a ceea ce s-a întâmplat\n3. 🏗️ Șantierul în cauză, dacă nu este șantierul {chantier_nom}\n\nPoți să-mi trimiți elementele unul câte unul, te voi ghida pas cu pas.",
        "menu_items": [
            {"title": "Vezi santierele", "id": "view_sites_ro", "description": "Proiecte active"},
            {"title": "Vezi sarcinile", "id": "view_tasks_ro", "description": "Sarcini atribuite"},
            {"title": "Acceseaza documente", "id": "view_documents_ro", "description": "Planuri si docs"},
            {"title": "Raporteaza incident", "id": "report_incident_ro", "description": "Declara problema"},
            {"title": "Actualizeaza progres", "id": "update_progress_ro", "description": "Actualizeaza sarcini"},
            {"title": "Vorbeste cu echipa", "id": "talk_team_ro", "description": "Contacteaza admin"},
        ],
    },
    "pl": {
        "greeting": "Cześć {name}, jak mogę Ci pomóc dzisiaj?",
        "button": "Opcje",
        "no_projects": "Nie masz jeszcze aktywnych projektów.",
        "projects_list_header": "Masz {count} aktywny(ch) projekt(ów):\n\n",
        "escalation_success": "✅ Twoje zgłoszenie zostało przekazane do zespołu administracyjnego. Członek zespołu skontaktuje się z Tobą wkrótce.",
        "report_incident": "Pomogę Ci zgłosić incydent. 🚨\n\nAby utworzyć raport o incydencie, potrzebuję:\n1. 📸 Co najmniej jednego zdjęcia problemu\n2. 📝 Pisemnego lub audio opisu tego, co się stało\n3. 🏗️ Placu budowy, którego to dotyczy, jeśli nie jest to plac budowy {chantier_nom}\n\nMożesz przesyłać mi elementy jeden po drugim, poprowadzę Cię krok po kroku.",
        "menu_items": [
            {"title": "Zobacz place budowy", "id": "view_sites_pl", "description": "Aktywne projekty"},
            {"title": "Zobacz zadania", "id": "view_tasks_pl", "description": "Przypisane zadania"},
            {"title": "Dostep do dokumentow", "id": "view_documents_pl", "description": "Plany i docs"},
            {"title": "Zglosz incydent", "id": "report_incident_pl", "description": "Zglaszanie problemu"},
            {"title": "Aktualizuj postep", "id": "update_progress_pl", "description": "Aktualizuj zadania"},
            {"title": "Porozmawiaj", "id": "talk_team_pl", "description": "Kontakt z admin"},
        ],
    },
    "ar": {
        "greeting": "مرحبا {name}، كيف يمكنني مساعدتك اليوم؟",
        "button": "خيارات",
        "no_projects": "ليس لديك مشاريع نشطة بعد.",
        "projects_list_header": "لديك {count} مشروع (مشاريع) نشط:\n\n",
        "escalation_success": "✅ تم إرسال طلبك إلى الفريق الإداري. سيتصل بك أحد أعضاء الفريق قريبًا.",
        "report_incident": "سأساعدك في الإبلاغ عن حادث. 🚨\n\nلإنشاء تقرير حادث، أحتاج إلى:\n1. 📸 صورة واحدة على الأقل للمشكلة\n2. 📝 وصف كتابي أو صوتي لما حدث\n3. 🏗️ موقع البناء المعني، إذا لم يكن موقع البناء {chantier_nom}\n\nيمكنك إرسال العناصر واحدة تلو الأخرى، سأرشدك خطوة بخطوة.",
        "menu_items": [
            {"title": "عرض مواقعي", "id": "view_sites_ar", "description": "المشاريع النشطة"},
            {"title": "عرض مهامي", "id": "view_tasks_ar", "description": "المهام المعينة"},
            {"title": "الوثائق", "id": "view_documents_ar", "description": "الخطط والوثائق"},
            {"title": "الإبلاغ عن حادث", "id": "report_incident_ar", "description": "الإبلاغ عن مشكلة"},
            {"title": "تحديث التقدم", "id": "update_progress_ar", "description": "تحديث المهام"},
            {"title": "التحدث مع الفريق", "id": "talk_team_ar", "description": "الاتصال بالإدارة"},
        ],
    },
}


def get_translation(language: str, key: str, default_language: str = "en") -> Any:
    """Get translation for a specific language with fallback.

    Args:
        language: Target language code
        key: Translation key (e.g., "greeting", "button", "menu_items")
        default_language: Fallback language if target not found

    Returns:
        Translation value or fallback
    """
    if language in TRANSLATIONS and key in TRANSLATIONS[language]:
        return TRANSLATIONS[language][key]
    elif default_language in TRANSLATIONS and key in TRANSLATIONS[default_language]:
        log.warning(f"Translation not found for {language}.{key}, using {default_language}")
        return TRANSLATIONS[default_language][key]
    else:
        log.error(f"Translation not found for {language}.{key} and fallback {default_language}")
        return None


def safe_truncate(text: str, max_length: int) -> str:
    """Safely truncate text to max length, removing emojis but keeping punctuation."""
    # Remove emojis and problematic special characters, but KEEP common punctuation
    # Keep: letters, numbers, spaces, hyphens, commas, periods, question marks, exclamation marks, colons, apostrophes
    text_clean = re.sub(r'[^\w\s\-,.\?!:\'\u00C0-\u017F]', '', text).strip()
    # Truncate to max length
    return text_clean[:max_length] if text_clean else text[:max_length]


def send_whatsapp_message_smart(
    to: str,
    text: str,
    interactive_data: Optional[Dict[str, Any]] = None,
    user_name: str = "",
    language: str = "fr",
    is_greeting: bool = False,
) -> Optional[str]:
    """Send WhatsApp message with automatic fallback from interactive to text.

    Args:
        to: Recipient phone number
        text: Message text content (FULL text including list for fallback)
        interactive_data: Optional dict with interactive message data:
            - type: "list" or "buttons"
            - For list: button_text, body_text, sections
            - For buttons: buttons list
        user_name: User's name for personalization
        language: User's language code (e.g., "fr", "en", "es")
        is_greeting: Whether this is a greeting message (use universal template)

    Returns:
        Message SID if successful
    """
    # Interactive messages - ENABLED via universal Content Template!
    ENABLE_INTERACTIVE = True

    # Try interactive message first if data provided and enabled
    # OR if this is a greeting (greeting template has built-in menu)
    if ENABLE_INTERACTIVE and (interactive_data or is_greeting):
        msg_type = interactive_data.get("type") if interactive_data else None

        # Handle greeting with universal template (has built-in menu)
        if is_greeting:
            log.info(f"✅ Processing greeting with universal template")

            # Get language-specific content using robust translation system
            greeting_template = get_translation(language, "greeting", "en")
            button_text = get_translation(language, "button", "en")
            menu_items = get_translation(language, "menu_items", "en")

            # Format greeting with user's name
            if greeting_template:
                # Use user's name or fallback to "there"
                name = user_name.strip() if user_name else ""
                greeting = greeting_template.format(name=name) if name else greeting_template.replace(" {name},", "").replace("{name},", "")
            else:
                greeting = "Hello, how can I help you today?"

            log.info(f"📝 Personalized greeting: {greeting[:50]}...")

            # Build content variables with strict character limits
            # Variable 1: Body text (max 1024 chars)
            # Variable 2: Button text (max 20 chars)
            # Variables 3-20: 6 items (title 24, id 200, description 72 each)
            content_variables = {
                "1": safe_truncate(greeting, 1024),
                "2": safe_truncate(button_text, 20) if button_text else "Options",
            }

            # Add 6 menu items with strict limits
            if not menu_items:
                menu_items = []

            for idx in range(6):
                if idx < len(menu_items):
                    item = menu_items[idx]
                    title = item.get("title", f"Option {idx+1}")
                    item_id = item.get("id", f"option_{idx+1}")
                    description = item.get("description", "")
                else:
                    # Pad with empty items if less than 6
                    title = ""
                    item_id = f"empty_{idx+1}"
                    description = ""

                # Calculate variable positions: 3,4,5 for item 0; 6,7,8 for item 1; etc.
                var_base = (idx * 3) + 3

                content_variables[str(var_base)] = safe_truncate(title, 24)
                content_variables[str(var_base + 1)] = safe_truncate(item_id, 200)
                content_variables[str(var_base + 2)] = safe_truncate(description, 72)

            log.info(f"📝 Content variables prepared:")
            log.info(f"   Body length: {len(content_variables['1'])} chars")
            log.info(f"   Button: {content_variables['2']}")
            log.info(f"   Items: {len([k for k in content_variables if k.isdigit() and int(k) >= 3]) // 3}")

            # Get universal template from database
            content_sid = template_manager.get_template_from_database("greeting_menu", "all")

            if not content_sid:
                log.error(f"❌ Universal template not found in database")
                # Fallback to text
                log.info("📱 Sending as regular text message")
                sid = twilio_client.send_message(to=to, body=text)
                return sid

            log.info(f"📋 Using universal template: {content_sid}")

            # Send using content template
            sid = twilio_client.send_message_with_content(
                to=to,
                content_sid=content_sid,
                content_variables=content_variables
            )

            if sid:
                log.info(f"✅ Sent greeting via template to {to}, SID: {sid}")
                return sid
            else:
                log.error(f"❌ Content template send FAILED, falling back to text")
                # Fallback to regular text
                sid = twilio_client.send_message(to=to, body=text)
                return sid

        elif msg_type == "list":
            # AI-generated response with interactive list - DON'T use greeting template
            log.info(f"⚠️ AI response with interactive list - falling back to plain text")
            log.info(f"   (Universal template only for greetings)")
            # Send as regular text message (the formatted text includes the list)
            sid = twilio_client.send_message(to=to, body=text)
            return sid

        elif msg_type == "buttons":
            # Buttons not yet implemented
            log.warning("⚠️ Interactive buttons not yet implemented, sending as text")

    # Fallback to regular text message
    log.info("📱 Sending as regular text message")
    sid = twilio_client.send_message(to=to, body=text)
    return sid


def format_menu_as_interactive_list(
    intro_text: str,
    options: List[Dict[str, str]],
    button_text: str = "Choose an option",
    section_title: str = "Options"
) -> Dict[str, Any]:
    """Format a menu into WhatsApp interactive list format.

    Args:
        intro_text: Introduction message
        options: List of dicts with 'id', 'title', and optional 'description'
        button_text: Text for the list button
        section_title: Title for the section

    Returns:
        Dict with formatted interactive list data
    """
    # Build rows from options
    rows = []
    for opt in options[:10]:  # WhatsApp limit: 10 items
        row = {
            "id": opt.get("id", f"opt_{len(rows)}"),
            "title": opt.get("title", "Option")[:24],  # Max 24 chars
        }
        if "description" in opt and opt["description"]:
            row["description"] = opt["description"][:72]  # Max 72 chars
        rows.append(row)

    return {
        "type": "list",
        "button_text": button_text,
        "sections": [
            {
                "title": section_title[:24],  # Max 24 chars
                "rows": rows
            }
        ]
    }


def format_menu_as_interactive_buttons(
    intro_text: str,
    buttons: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Format a menu into WhatsApp interactive buttons format (max 3).

    Args:
        intro_text: Introduction message
        buttons: List of dicts with 'id' and 'title'

    Returns:
        Dict with formatted interactive buttons data
    """
    return {
        "type": "buttons",
        "buttons": [
            {
                "id": btn.get("id", f"btn_{i}"),
                "title": btn.get("title", "Option")[:20]  # Max 20 chars
            }
            for i, btn in enumerate(buttons[:3])  # Max 3 buttons
        ]
    }


def format_text_with_numbered_list(
    intro_text: str,
    items: List[str],
    emoji: str = "•"
) -> str:
    """Format a text message with a numbered list.

    Args:
        intro_text: Introduction message
        items: List of items to display
        emoji: Emoji to use as bullet (default: •)

    Returns:
        Formatted text message
    """
    text = f"{intro_text}\n\n"
    for i, item in enumerate(items, 1):
        text += f"{i}. {emoji} {item}\n"
    return text.strip()
