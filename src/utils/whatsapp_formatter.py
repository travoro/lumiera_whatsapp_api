"""WhatsApp message formatter with interactive message support."""

from typing import Any, Dict, List, Optional

from src.integrations.twilio import twilio_client
from src.services.dynamic_templates import dynamic_template_service
from src.utils.logger import log

# Robust translation dictionary for WhatsApp interactive messages
TRANSLATIONS = {
    "fr": {
        "greeting": "Bonjour {name}, comment puis-je vous aider aujourd'hui ?",
        "button": "Options",
        "no_projects": "Vous n'avez pas encore de chantiers actifs.",
        "projects_list_header_singular": "Vous avez 1 chantier actif :\n\n",
        "projects_list_header_plural": "Vous avez {count} chantiers actifs :\n\n",
        "projects_found_singular": "Voici votre chantier actif :",
        "projects_found_plural": "Voici vos chantiers actifs :",
        "escalation_success": (
            "✅ Votre demande a été transmise à notre équipe. "
            "Quelqu'un vous contactera sous peu."
        ),
        "report_incident": (
            "Je vais vous aider à signaler un incident. 🚨\n\n"
            "Pour créer un rapport d'incident, j'ai besoin de :\n"
            "1. 📸 Au moins une photo du problème\n"
            "2. 📝 Une description écrite ou audio de ce qui s'est passé\n"
            "3. 🏗️ Le chantier concerné, si ce n'est pas le chantier {chantier_nom}\n\n"
            "Vous pouvez m'envoyer les éléments un par un, je vous guiderai pas à pas."
        ),
        "menu_items": [
            {"title": "🏗️ Voir mes chantiers", "id": "view_sites_fr", "description": ""},
            {
                "title": "✅ Consulter mes taches",
                "id": "view_tasks_fr",
                "description": "",
            },
            {
                "title": "📄 Acceder aux documents",
                "id": "view_documents_fr",
                "description": "",
            },
            {
                "title": "🚨 Signaler un incident",
                "id": "report_incident_fr",
                "description": "",
            },
            {"title": "📊 Progression", "id": "update_progress_fr", "description": ""},
            {"title": "💬 Contacter equipe", "id": "talk_team_fr", "description": ""},
        ],
        "available_projects_header": "Chantiers disponibles :\n",
        "list_projects_header": "Voici vos chantiers :\n\n",
        "list_projects_footer": "Sélectionnez un chantier pour voir les tâches.",
        "list_tasks_header": "Voici vos tâches ",
        "list_tasks_select_header": "Voici vos tâches:\n\n",
        "list_tasks_project_context": "pour le chantier *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "Aucune tâche pour ce chantier.",
        "list_tasks_footer": "\n\nDites-moi si vous souhaitez voir les tâches d'un autre chantier.",
        "list_tasks_select_project": "\nDites-moi pour quel chantier vous souhaitez voir les tâches.",
        "task_details_header": "📋 Détails de la tâche : {task_title}",
        "list_documents_header": "Voici vos documents. 📄\n\n",
        "list_documents_project_context": "Pour le chantier {project_name} :\n\n",
        "list_documents_no_documents": "Aucun document disponible pour ce chantier.",
        "list_documents_footer": "\n\nDites-moi si vous souhaitez voir les documents d'un autre chantier.",
        "list_documents_select_project": "\nDites-moi pour quel chantier vous souhaitez voir les documents.",
        "update_progress_header": "Je vais vous aider à mettre à jour la progression. 📊\n\n",
        "update_progress_project_context": "Pour le chantier **{project_name}**, ",
        "update_progress_tasks_header": "tâches en cours :\n",
        "update_progress_no_tasks": "Aucune tâche en cours pour ce chantier.",
        "update_progress_footer": "\n\nDites-moi quelle tâche vous souhaitez mettre à jour et le nouveau pourcentage.",
        "report_incident_section_header": "3. 🏗️ Le chantier concerné\n\n",
        "report_incident_closing": "\nVous pouvez m'envoyer les éléments un par un, je vous guiderai pas à pas.",
    },
    "en": {
        "greeting": "Hello {name}, how can I help you today?",
        "button": "Options",
        "no_projects": "You don't have any active projects yet.",
        "projects_list_header_singular": "You have 1 active project:\n\n",
        "projects_list_header_plural": "You have {count} active projects:\n\n",
        "projects_found_singular": "Here is your active site:",
        "projects_found_plural": "Here are your active sites:",
        "escalation_success": (
            "✅ Your request has been forwarded to the admin team. "
            "A team member will contact you shortly."
        ),
        "report_incident": (
            "I'll help you report an incident. 🚨\n\n"
            "To create an incident report, I need:\n"
            "1. 📸 At least one photo of the problem\n"
            "2. 📝 A written or audio description of what happened\n"
            "3. 🏗️ The concerned site, if it's not the site {chantier_nom}\n\n"
            "You can send me the elements one by one, I'll guide you step by step."
        ),
        "menu_items": [
            {"title": "🏗️ View my sites", "id": "view_sites_en", "description": ""},
            {"title": "✅ Check my tasks", "id": "view_tasks_en", "description": ""},
            {
                "title": "📄 Access documents",
                "id": "view_documents_en",
                "description": "",
            },
            {
                "title": "🚨 Report incident",
                "id": "report_incident_en",
                "description": "",
            },
            {
                "title": "📊 Update progress",
                "id": "update_progress_en",
                "description": "",
            },
            {"title": "💬 Talk to team", "id": "talk_team_en", "description": ""},
        ],
        "available_projects_header": "Available sites:\n",
        "list_projects_header": "Here are your sites:\n\n",
        "list_projects_footer": "Select a site to view tasks.",
        "list_tasks_header": "Here are your tasks ",
        "list_tasks_project_context": "for the site *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "No tasks for this site.",
        "list_tasks_footer": "\n\nLet me know if you want to see tasks for another site.",
        "list_tasks_select_project": "\nTell me which site you want to see tasks for.",
        "task_details_header": "📋 Task Details: {task_title}",
        "list_documents_header": "Here are your documents. 📄\n\n",
        "list_documents_project_context": "For the site **{project_name}** :\n\n",
        "list_documents_no_documents": "No documents available for this site.",
        "list_documents_footer": "\n\nLet me know if you want to see documents for another site.",
        "list_documents_select_project": "\nTell me which site you want to see documents for.",
        "update_progress_header": "I'll help you update progress. 📊\n\n",
        "update_progress_project_context": "For the site **{project_name}**, ",
        "update_progress_tasks_header": "current tasks:\n",
        "update_progress_no_tasks": "No current tasks for this site.",
        "update_progress_footer": "\n\nTell me which task you want to update and the new percentage.",
        "report_incident_section_header": "3. 🏗️ The concerned site\n\n",
        "report_incident_closing": "\nYou can send me the elements one by one, I'll guide you step by step.",
    },
    "es": {
        "greeting": "Hola {name}, ¿cómo puedo ayudarte hoy?",
        "button": "Opciones",
        "no_projects": "Aún no tienes proyectos activos.",
        "projects_list_header_singular": "Tienes 1 proyecto activo:\n\n",
        "projects_list_header_plural": "Tienes {count} proyectos activos:\n\n",
        "projects_found_singular": "Aquí está tu obra activa:",
        "projects_found_plural": "Aquí están tus obras activas:",
        "escalation_success": (
            "✅ Tu solicitud ha sido enviada al equipo administrativo. "
            "Un miembro del equipo te contactará pronto."
        ),
        "report_incident": (
            "Te ayudaré a reportar un incidente. 🚨\n\n"
            "Para crear un reporte de incidente, necesito:\n"
            "1. 📸 Al menos una foto del problema\n"
            "2. 📝 Una descripción escrita o de audio de lo que pasó\n"
            "3. 🏗️ La obra concernida, si no es la obra {chantier_nom}\n\n"
            "Puedes enviarme los elementos uno por uno, te guiaré paso a paso."
        ),
        "menu_items": [
            {"title": "🏗️ Ver mis obras", "id": "view_sites_es", "description": ""},
            {"title": "✅ Ver mis tareas", "id": "view_tasks_es", "description": ""},
            {
                "title": "📄 Acceder documentos",
                "id": "view_documents_es",
                "description": "",
            },
            {
                "title": "🚨 Reportar incidente",
                "id": "report_incident_es",
                "description": "",
            },
            {
                "title": "📊 Actualizar progreso",
                "id": "update_progress_es",
                "description": "",
            },
            {"title": "💬 Hablar con equipo", "id": "talk_team_es", "description": ""},
        ],
        "available_projects_header": "Obras disponibles:\n",
        "list_projects_header": "Aquí están tus obras:\n\n",
        "list_projects_footer": "Selecciona una obra para ver las tareas.",
        "list_tasks_header": "Aquí están tus tareas ",
        "list_tasks_project_context": "para la obra *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "No hay tareas para esta obra.",
        "list_tasks_footer": "\n\nDime si quieres ver las tareas de otra obra.",
        "list_tasks_select_project": "\nDime para qué obra quieres ver las tareas.",
        "list_documents_header": "Aquí están tus documentos. 📄\n\n",
        "list_documents_project_context": "Para la obra **{project_name}** :\n\n",
        "list_documents_no_documents": "No hay documentos disponibles para esta obra.",
        "list_documents_footer": "\n\nDime si quieres ver los documentos de otra obra.",
        "list_documents_select_project": "\nDime para qué obra quieres ver los documentos.",
        "update_progress_header": "Te ayudaré a actualizar el progreso. 📊\n\n",
        "update_progress_project_context": "Para la obra **{project_name}**, ",
        "update_progress_tasks_header": "tareas en curso:\n",
        "update_progress_no_tasks": "No hay tareas en curso para esta obra.",
        "update_progress_footer": "\n\nDime qué tarea quieres actualizar y el nuevo porcentaje.",
        "report_incident_section_header": "3. 🏗️ La obra concernida\n\n",
        "report_incident_closing": "\nPuedes enviarme los elementos uno por uno, te guiaré paso a paso.",
    },
    "pt": {
        "greeting": "Olá {name}, como posso ajudá-lo hoje?",
        "button": "Opções",
        "no_projects": "Você ainda não tem projetos ativos.",
        "projects_list_header_singular": "Você tem 1 projeto ativo:\n\n",
        "projects_list_header_plural": "Você tem {count} projetos ativos:\n\n",
        "projects_found_singular": "Aqui está sua obra ativa:",
        "projects_found_plural": "Aqui estão suas obras ativas:",
        "escalation_success": (
            "✅ Sua solicitação foi encaminhada para a equipe administrativa. "
            "Um membro da equipe entrará em contato em breve."
        ),
        "report_incident": (
            "Vou ajudá-lo a relatar um incidente. 🚨\n\n"
            "Para criar um relatório de incidente, preciso de:\n"
            "1. 📸 Pelo menos uma foto do problema\n"
            "2. 📝 Uma descrição escrita ou em áudio do que aconteceu\n"
            "3. 🏗️ A obra em questão, se não for a obra {chantier_nom}\n\n"
            "Você pode me enviar os elementos um por um, vou guiá-lo passo a passo."
        ),
        "menu_items": [
            {"title": "🏗️ Ver minhas obras", "id": "view_sites_pt", "description": ""},
            {
                "title": "✅ Ver minhas tarefas",
                "id": "view_tasks_pt",
                "description": "",
            },
            {
                "title": "📄 Acessar documentos",
                "id": "view_documents_pt",
                "description": "",
            },
            {
                "title": "🚨 Relatar incidente",
                "id": "report_incident_pt",
                "description": "",
            },
            {
                "title": "📊 Atualizar progresso",
                "id": "update_progress_pt",
                "description": "",
            },
            {"title": "💬 Falar com equipe", "id": "talk_team_pt", "description": ""},
        ],
        "available_projects_header": "Obras disponíveis:\n",
        "list_tasks_header": "Aqui estão suas tarefas ",
        "list_tasks_project_context": "para a obra *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "Não há tarefas para esta obra.",
        "list_tasks_footer": "\n\nDiga-me se você quer ver as tarefas de outra obra.",
        "list_tasks_select_project": "\nDiga-me para qual obra você quer ver as tarefas.",
        "list_documents_header": "Aqui estão seus documentos. 📄\n\n",
        "list_documents_project_context": "Para a obra **{project_name}** :\n\n",
        "list_documents_no_documents": "Não há documentos disponíveis para esta obra.",
        "list_documents_footer": "\n\nDiga-me se você quer ver os documentos de outra obra.",
        "list_documents_select_project": "\nDiga-me para qual obra você quer ver os documentos.",
        "update_progress_header": "Vou ajudá-lo a atualizar o progresso. 📊\n\n",
        "update_progress_project_context": "Para a obra **{project_name}**, ",
        "update_progress_tasks_header": "tarefas em curso:\n",
        "update_progress_no_tasks": "Não há tarefas em curso para esta obra.",
        "update_progress_footer": "\n\nDiga-me qual tarefa você quer atualizar e a nova porcentagem.",
        "report_incident_section_header": "3. 🏗️ A obra em questão\n\n",
        "report_incident_closing": "\nVocê pode me enviar os elementos um por um, vou guiá-lo passo a passo.",
    },
    "de": {
        "greeting": "Hallo {name}, wie kann ich Ihnen heute helfen?",
        "button": "Optionen",
        "no_projects": "Sie haben noch keine aktiven Projekte.",
        "projects_list_header_singular": "Sie haben 1 aktives Projekt:\n\n",
        "projects_list_header_plural": "Sie haben {count} aktive Projekte:\n\n",
        "projects_found_singular": "Hier ist Ihre aktive Baustelle:",
        "projects_found_plural": "Hier sind Ihre aktiven Baustellen:",
        "escalation_success": (
            "✅ Ihre Anfrage wurde an das Admin-Team weitergeleitet. "
            "Ein Teammitglied wird sich in Kürze bei Ihnen melden."
        ),
        "report_incident": (
            "Ich helfe Ihnen, einen Vorfall zu melden. 🚨\n\n"
            "Um einen Vorfallbericht zu erstellen, benötige ich:\n"
            "1. 📸 Mindestens ein Foto des Problems\n"
            "2. 📝 Eine schriftliche oder Audio-Beschreibung dessen, was passiert ist\n"
            "3. 🏗️ Die betroffene Baustelle, falls es sich nicht um die Baustelle {chantier_nom} handelt\n\n"
            "Sie können mir die Elemente einzeln senden, ich führe Sie Schritt für Schritt."
        ),
        "menu_items": [
            {"title": "🏗️ Meine Baustellen", "id": "view_sites_de", "description": ""},
            {"title": "✅ Meine Aufgaben", "id": "view_tasks_de", "description": ""},
            {"title": "📄 Dokumente", "id": "view_documents_de", "description": ""},
            {
                "title": "🚨 Vorfall melden",
                "id": "report_incident_de",
                "description": "",
            },
            {"title": "📊 Fortschritt", "id": "update_progress_de", "description": ""},
            {"title": "💬 Team kontaktieren", "id": "talk_team_de", "description": ""},
        ],
        "available_projects_header": "Verfügbare Baustellen:\n",
        "list_tasks_header": "Hier sind Ihre Aufgaben ",
        "list_tasks_project_context": "für die Baustelle *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "Keine Aufgaben für diese Baustelle.",
        "list_tasks_footer": "\n\nSagen Sie mir, wenn Sie Aufgaben für eine andere Baustelle sehen möchten.",
        "list_tasks_select_project": "\nSagen Sie mir, für welche Baustelle Sie Aufgaben sehen möchten.",
        "list_documents_header": "Hier sind Ihre Dokumente. 📄\n\n",
        "list_documents_project_context": "Für die Baustelle **{project_name}** :\n\n",
        "list_documents_no_documents": "Keine Dokumente für diese Baustelle verfügbar.",
        "list_documents_footer": "\n\nSagen Sie mir, wenn Sie Dokumente für eine andere Baustelle sehen möchten.",
        "list_documents_select_project": "\nSagen Sie mir, für welche Baustelle Sie Dokumente sehen möchten.",
        "update_progress_header": "Ich helfe Ihnen, den Fortschritt zu aktualisieren. 📊\n\n",
        "update_progress_project_context": "Für die Baustelle **{project_name}**, ",
        "update_progress_tasks_header": "laufende Aufgaben:\n",
        "update_progress_no_tasks": "Keine laufenden Aufgaben für diese Baustelle.",
        "update_progress_footer": (
            "\n\nSagen Sie mir, welche Aufgabe Sie aktualisieren möchten "
            "und den neuen Prozentsatz."
        ),
        "report_incident_section_header": "3. 🏗️ Die betroffene Baustelle\n\n",
        "report_incident_closing": "\nSie können mir die Elemente einzeln senden, ich führe Sie Schritt für Schritt.",
    },
    "it": {
        "greeting": "Ciao {name}, come posso aiutarti oggi?",
        "button": "Opzioni",
        "no_projects": "Non hai ancora progetti attivi.",
        "projects_list_header_singular": "Hai 1 progetto attivo:\n\n",
        "projects_list_header_plural": "Hai {count} progetti attivi:\n\n",
        "projects_found_singular": "Ecco il tuo cantiere attivo:",
        "projects_found_plural": "Ecco i tuoi cantieri attivi:",
        "escalation_success": (
            "✅ La tua richiesta è stata inoltrata al team amministrativo. "
            "Un membro del team ti contatterà a breve."
        ),
        "report_incident": (
            "Ti aiuterò a segnalare un incidente. 🚨\n\n"
            "Per creare un rapporto di incidente, ho bisogno di:\n"
            "1. 📸 Almeno una foto del problema\n"
            "2. 📝 Una descrizione scritta o audio di cosa è successo\n"
            "3. 🏗️ Il cantiere interessato, se non è il cantiere {chantier_nom}\n\n"
            "Puoi inviarmi gli elementi uno per uno, ti guiderò passo dopo passo."
        ),
        "menu_items": [
            {"title": "🏗️ Vedi cantieri", "id": "view_sites_it", "description": ""},
            {"title": "✅ Vedi compiti", "id": "view_tasks_it", "description": ""},
            {
                "title": "📄 Accedi documenti",
                "id": "view_documents_it",
                "description": "",
            },
            {
                "title": "🚨 Segnala incidente",
                "id": "report_incident_it",
                "description": "",
            },
            {
                "title": "📊 Aggiorna progresso",
                "id": "update_progress_it",
                "description": "",
            },
            {"title": "💬 Parla con team", "id": "talk_team_it", "description": ""},
        ],
        "available_projects_header": "Cantieri disponibili:\n",
        "list_tasks_header": "Ecco i tuoi compiti ",
        "list_tasks_project_context": "per il cantiere *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "Nessun compito per questo cantiere.",
        "list_tasks_footer": "\n\nDimmi se vuoi vedere i compiti di un altro cantiere.",
        "list_tasks_select_project": "\nDimmi per quale cantiere vuoi vedere i compiti.",
        "list_documents_header": "Ecco i tuoi documenti. 📄\n\n",
        "list_documents_project_context": "Per il cantiere **{project_name}** :\n\n",
        "list_documents_no_documents": "Nessun documento disponibile per questo cantiere.",
        "list_documents_footer": "\n\nDimmi se vuoi vedere i documenti di un altro cantiere.",
        "list_documents_select_project": "\nDimmi per quale cantiere vuoi vedere i documenti.",
        "update_progress_header": "Ti aiuterò a aggiornare il progresso. 📊\n\n",
        "update_progress_project_context": "Per il cantiere **{project_name}**, ",
        "update_progress_tasks_header": "compiti in corso:\n",
        "update_progress_no_tasks": "Nessun compito in corso per questo cantiere.",
        "update_progress_footer": "\n\nDimmi quale compito vuoi aggiornare e la nuova percentuale.",
        "report_incident_section_header": "3. 🏗️ Il cantiere interessato\n\n",
        "report_incident_closing": "\nPuoi inviarmi gli elementi uno per uno, ti guiderò passo dopo passo.",
    },
    "ro": {
        "greeting": "Bună {name}, cum te pot ajuta astăzi ?",
        "button": "Opțiuni",
        "no_projects": "Nu ai încă șantiere active.",
        "projects_list_header_singular": "Ai 1 șantier activ:\n\n",
        "projects_list_header_plural": "Ai {count} șantiere active:\n\n",
        "projects_found_singular": "Iată șantierul tău activ:",
        "projects_found_plural": "Iată șantierele tale active:",
        "escalation_success": (
            "✅ Cererea ta a fost trimisă echipei administrative. "
            "Un membru al echipei te va contacta în curând."
        ),
        "report_incident": (
            "Te voi ajuta să raportezi un incident. 🚨\n\n"
            "Pentru a crea un raport de incident, am nevoie de:\n"
            "1. 📸 Cel puțin o fotografie a problemei\n"
            "2. 📝 O descriere scrisă sau audio a ceea ce s-a întâmplat\n"
            "3. 🏗️ Șantierul în cauză, dacă nu este șantierul {chantier_nom}\n\n"
            "Poți să-mi trimiți elementele unul câte unul, te voi ghida pas cu pas."
        ),
        "menu_items": [
            {"title": "🏗️ Vezi santierele", "id": "view_sites_ro", "description": ""},
            {"title": "✅ Vezi sarcinile", "id": "view_tasks_ro", "description": ""},
            {
                "title": "📄 Acceseaza documente",
                "id": "view_documents_ro",
                "description": "",
            },
            {
                "title": "🚨 Raporteaza incident",
                "id": "report_incident_ro",
                "description": "",
            },
            {
                "title": "📊 Actualizeaza progres",
                "id": "update_progress_ro",
                "description": "",
            },
            {"title": "💬 Vorbeste cu echipa", "id": "talk_team_ro", "description": ""},
        ],
        "available_projects_header": "Șantiere disponibile:\n",
        "list_tasks_header": "Iată sarcinile tale ",
        "list_tasks_project_context": "pentru șantierul *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "Nu există sarcini pentru acest șantier.",
        "list_tasks_footer": "\n\nSpune-mi dacă vrei să vezi sarcinile unui alt șantier.",
        "list_tasks_select_project": "\nSpune-mi pentru care șantier vrei să vezi sarcinile.",
        "list_documents_header": "Iată documentele tale. 📄\n\n",
        "list_documents_project_context": "Pentru șantierul **{project_name}** :\n\n",
        "list_documents_no_documents": "Nu există documente disponibile pentru acest șantier.",
        "list_documents_footer": "\n\nSpune-mi dacă vrei să vezi documentele unui alt șantier.",
        "list_documents_select_project": "\nSpune-mi pentru care șantier vrei să vezi documentele.",
        "update_progress_header": "Te voi ajuta să actualizezi progresul. 📊\n\n",
        "update_progress_project_context": "Pentru șantierul **{project_name}**, ",
        "update_progress_tasks_header": "sarcini în curs:\n",
        "update_progress_no_tasks": "Nu există sarcini în curs pentru acest șantier.",
        "update_progress_footer": "\n\nSpune-mi ce sarcină vrei să actualizezi și noul procent.",
        "report_incident_section_header": "3. 🏗️ Șantierul în cauză\n\n",
        "report_incident_closing": "\nPoți să-mi trimiți elementele unul câte unul, te voi ghida pas cu pas.",
    },
    "pl": {
        "greeting": "Cześć {name}, jak mogę Ci pomóc dzisiaj?",
        "button": "Opcje",
        "no_projects": "Nie masz jeszcze aktywnych projektów.",
        "projects_list_header_singular": "Masz 1 aktywny projekt:\n\n",
        "projects_list_header_plural": "Masz {count} aktywnych projektów:\n\n",
        "projects_found_singular": "Oto Twój aktywny plac budowy:",
        "projects_found_plural": "Oto Twoje aktywne place budowy:",
        "escalation_success": (
            "✅ Twoje zgłoszenie zostało przekazane do zespołu administracyjnego. "
            "Członek zespołu skontaktuje się z Tobą wkrótce."
        ),
        "report_incident": (
            "Pomogę Ci zgłosić incydent. 🚨\n\n"
            "Aby utworzyć raport o incydencie, potrzebuję:\n"
            "1. 📸 Co najmniej jednego zdjęcia problemu\n"
            "2. 📝 Pisemnego lub audio opisu tego, co się stało\n"
            "3. 🏗️ Placu budowy, którego to dotyczy, jeśli nie jest to plac budowy {chantier_nom}\n\n"
            "Możesz przesyłać mi elementy jeden po drugim, poprowadzę Cię krok po kroku."
        ),
        "menu_items": [
            {
                "title": "🏗️ Zobacz place budowy",
                "id": "view_sites_pl",
                "description": "",
            },
            {"title": "✅ Zobacz zadania", "id": "view_tasks_pl", "description": ""},
            {
                "title": "📄 Dostep do dokumentow",
                "id": "view_documents_pl",
                "description": "",
            },
            {
                "title": "🚨 Zglosz incydent",
                "id": "report_incident_pl",
                "description": "",
            },
            {
                "title": "📊 Aktualizuj postep",
                "id": "update_progress_pl",
                "description": "",
            },
            {"title": "💬 Porozmawiaj", "id": "talk_team_pl", "description": ""},
        ],
        "available_projects_header": "Dostępne place budowy:\n",
        "list_tasks_header": "Oto Twoje zadania ",
        "list_tasks_project_context": "dla placu budowy *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "Brak zadań dla tego placu budowy.",
        "list_tasks_footer": "\n\nPowiedz mi, jeśli chcesz zobaczyć zadania dla innego placu budowy.",
        "list_tasks_select_project": "\nPowiedz mi, dla którego placu budowy chcesz zobaczyć zadania.",
        "list_documents_header": "Oto Twoje dokumenty. 📄\n\n",
        "list_documents_project_context": "Dla placu budowy **{project_name}** :\n\n",
        "list_documents_no_documents": "Brak dokumentów dla tego placu budowy.",
        "list_documents_footer": "\n\nPowiedz mi, jeśli chcesz zobaczyć dokumenty dla innego placu budowy.",
        "list_documents_select_project": "\nPowiedz mi, dla którego placu budowy chcesz zobaczyć dokumenty.",
        "update_progress_header": "Pomogę Ci zaktualizować postęp. 📊\n\n",
        "update_progress_project_context": "Dla placu budowy **{project_name}**, ",
        "update_progress_tasks_header": "bieżące zadania:\n",
        "update_progress_no_tasks": "Brak bieżących zadań dla tego placu budowy.",
        "update_progress_footer": "\n\nPowiedz mi, które zadanie chcesz zaktualizować i nowy procent.",
        "report_incident_section_header": "3. 🏗️ Plac budowy\n\n",
        "report_incident_closing": "\nMożesz przesyłać mi elementy jeden po drugim, poprowadzę Cię krok po kroku.",
    },
    "ar": {
        "greeting": "مرحبا {name}، كيف يمكنني مساعدتك اليوم؟",
        "button": "خيارات",
        "no_projects": "ليس لديك مشاريع نشطة بعد.",
        "projects_list_header_singular": "لديك مشروع نشط واحد:\n\n",
        "projects_list_header_plural": "لديك {count} مشاريع نشطة:\n\n",
        "projects_found_singular": "إليك موقع البناء النشط الخاص بك:",
        "projects_found_plural": "إليك مواقع البناء النشطة الخاصة بك:",
        "escalation_success": "✅ تم إرسال طلبك إلى الفريق الإداري. سيتصل بك أحد أعضاء الفريق قريبًا.",
        "report_incident": (
            "سأساعدك في الإبلاغ عن حادث. 🚨\n\n"
            "لإنشاء تقرير حادث، أحتاج إلى:\n"
            "1. 📸 صورة واحدة على الأقل للمشكلة\n"
            "2. 📝 وصف كتابي أو صوتي لما حدث\n"
            "3. 🏗️ موقع البناء المعني، إذا لم يكن موقع البناء {chantier_nom}\n\n"
            "يمكنك إرسال العناصر واحدة تلو الأخرى، سأرشدك خطوة بخطوة."
        ),
        "menu_items": [
            {"title": "🏗️ عرض مواقعي", "id": "view_sites_ar", "description": ""},
            {"title": "✅ عرض مهامي", "id": "view_tasks_ar", "description": ""},
            {"title": "📄 الوثائق", "id": "view_documents_ar", "description": ""},
            {
                "title": "🚨 الإبلاغ عن حادث",
                "id": "report_incident_ar",
                "description": "",
            },
            {"title": "📊 تحديث التقدم", "id": "update_progress_ar", "description": ""},
            {"title": "💬 التحدث مع الفريق", "id": "talk_team_ar", "description": ""},
        ],
        "available_projects_header": "مواقع البناء المتاحة:\n",
        "list_tasks_header": "إليك مهامك ",
        "list_tasks_project_context": "لموقع البناء *{project_name}* :\n\n",
        "list_tasks_tasks_header": "",
        "list_tasks_no_tasks": "لا توجد مهام لهذا الموقع.",
        "list_tasks_footer": "\n\nأخبرني إذا كنت تريد رؤية مهام موقع آخر.",
        "list_tasks_select_project": "\nأخبرني لأي موقع تريد رؤية المهام.",
        "list_documents_header": "إليك مستنداتك. 📄\n\n",
        "list_documents_project_context": "لموقع البناء **{project_name}** :\n\n",
        "list_documents_no_documents": "لا توجد مستندات متاحة لهذا الموقع.",
        "list_documents_footer": "\n\nأخبرني إذا كنت تريد رؤية مستندات موقع آخر.",
        "list_documents_select_project": "\nأخبرني لأي موقع تريد رؤية المستندات.",
        "update_progress_header": "سأساعدك في تحديث التقدم. 📊\n\n",
        "update_progress_project_context": "لموقع البناء **{project_name}**, ",
        "update_progress_tasks_header": "المهام الجارية:\n",
        "update_progress_no_tasks": "لا توجد مهام جارية لهذا الموقع.",
        "update_progress_footer": "\n\nأخبرني بالمهمة التي تريد تحديثها والنسبة المئوية الجديدة.",
        "report_incident_section_header": "3. 🏗️ موقع البناء المعني\n\n",
        "report_incident_closing": "\nيمكنك إرسال العناصر واحدة تلو الأخرى، سأرشدك خطوة بخطوة.",
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
        log.warning(
            f"Translation not found for {language}.{key}, using {default_language}"
        )
        return TRANSLATIONS[default_language][key]
    else:
        log.error(
            f"Translation not found for {language}.{key} and fallback {default_language}"
        )
        return None


def get_plural_translation(
    language: str, base_key: str, count: int, default_language: str = "en"
) -> str:
    """Get singular or plural translation based on count.

    Args:
        language: Target language code
        base_key: Base translation key (e.g., "projects_list_header")
        count: Number to determine singular/plural
        default_language: Fallback language if target not found

    Returns:
        Translated string with count formatted in
    """
    # Determine singular or plural key
    key = f"{base_key}_singular" if count == 1 else f"{base_key}_plural"

    # Get translation
    translation = get_translation(language, key, default_language)

    if translation:
        # Format with count for plural, singular already has "1" hardcoded
        if count == 1:
            return translation
        else:
            return translation.format(count=count)
    else:
        # Fallback if translation not found
        return f"{count} items"


def safe_truncate(text: str, max_length: int) -> str:
    """Safely truncate text to max length, keeping emojis and punctuation."""
    # Simply truncate to max length while preserving emojis
    # Emojis are fully supported in WhatsApp interactive lists
    truncated = text[:max_length].strip() if text else ""
    return truncated


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

        # Handle greeting with dynamic interactive list
        if is_greeting:
            log.info(
                "✅ Processing greeting with dynamic template (create-send-delete)"
            )

            # Get language-specific content using robust translation system
            greeting_template = get_translation(language, "greeting", "en")
            button_text = get_translation(language, "button", "en")
            menu_items = get_translation(language, "menu_items", "en")

            # Format greeting with user's name
            if greeting_template:
                # Use user's name or fallback to "there"
                name = user_name.strip() if user_name else ""
                greeting = (
                    greeting_template.format(name=name)
                    if name
                    else greeting_template.replace(" {name},", "").replace(
                        "{name},", ""
                    )
                )
            else:
                greeting = "Hello, how can I help you today?"

            log.info(f"📝 Personalized greeting: {greeting[:50]}...")
            log.info(f"📋 Menu items: {len(menu_items)} items")

            # Convert menu items to dynamic template format
            # Each item needs: "item" (≤24 chars), "description" (≤72 chars), "id"
            formatted_items = []
            if menu_items:
                for menu_item in menu_items[:10]:  # Max 10 items for WhatsApp
                    formatted_items.append(
                        {
                            "item": safe_truncate(menu_item.get("title", ""), 24),
                            "description": safe_truncate(
                                menu_item.get("description", ""), 72
                            ),
                            "id": menu_item.get("id", ""),
                        }
                    )

            if not formatted_items:
                # Fallback if no menu items
                log.warning("⚠️ No menu items available, falling back to text")
                sid = twilio_client.send_message(to=to, body=text)
                return sid

            # Use dynamic template service (create → send → delete)
            log.info(
                f"🚀 Sending dynamic list picker with {len(formatted_items)} items"
            )

            result = dynamic_template_service.send_list_picker(
                to_number=to,
                body_text=greeting,
                button_text=(
                    safe_truncate(button_text, 20) if button_text else "Options"
                ),
                items=formatted_items,
                cleanup=True,  # Auto-delete after sending
                language=language,
            )

            if result["success"]:
                log.info(f"✅ Sent greeting via dynamic template to {to}")
                log.info(
                    f"📊 Performance: {result['total_ms']:.0f}ms (create → send → delete)"
                )
                return result["message_sid"]
            else:
                log.error(f"❌ Dynamic template send FAILED: {result.get('error')}")
                # Fallback to regular text
                log.info("📱 Falling back to regular text message")
                sid = twilio_client.send_message(to=to, body=text)
                return sid

        elif msg_type == "list":
            # AI-generated response with interactive list - Use dynamic template
            log.info("✅ Processing list response with dynamic template")
            log.debug(f"📋 Interactive data: {interactive_data}")

            # Extract data from interactive_data
            body_text = interactive_data.get("body_text", text)
            button_text = interactive_data.get("button_text", "Choisir")
            sections = interactive_data.get("sections", [])

            # Convert to dynamic template format
            formatted_items = []
            for section in sections:
                for row in section.get("rows", []):
                    formatted_items.append(
                        {
                            "item": safe_truncate(row.get("title", ""), 24),
                            "description": (
                                safe_truncate(row.get("description", ""), 72)
                                if row.get("description")
                                else ""
                            ),
                            "id": row.get("id", ""),
                        }
                    )

            if not formatted_items:
                log.warning("⚠️ No list items found, falling back to text")
                sid = twilio_client.send_message(to=to, body=text)
                return sid

            log.info(
                f"🚀 Sending dynamic list picker with {len(formatted_items)} items"
            )

            result = dynamic_template_service.send_list_picker(
                to_number=to,
                body_text=body_text,
                button_text=safe_truncate(button_text, 20),
                items=formatted_items,
                cleanup=True,  # Auto-delete after sending
                language=language,
            )

            if result["success"]:
                log.info(f"✅ Sent list via dynamic template to {to}")
                log.info(
                    f"📊 Performance: {result['total_ms']:.0f}ms (create → send → delete)"
                )
                return result["message_sid"]
            else:
                log.error(f"❌ Dynamic template send FAILED: {result.get('error')}")
                # Fallback to regular text
                log.info("📱 Falling back to regular text message")
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
    section_title: str = "Options",
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
    rows: list[dict[str, Any]] = []
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
        "sections": [{"title": section_title[:24], "rows": rows}],  # Max 24 chars
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
                "title": btn.get("title", "Option")[:20],  # Max 20 chars
            }
            for i, btn in enumerate(buttons[:3])  # Max 3 buttons
        ],
    }


def format_text_with_numbered_list(
    intro_text: str, items: List[str], emoji: str = "•"
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
