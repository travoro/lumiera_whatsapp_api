"""Script to create greeting menu templates for all languages."""
import asyncio
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from twilio.rest import Client
from src.config import settings
from src.integrations.supabase import supabase_client
from src.utils.logger import log


# Fixed menu options for all languages
MENU_OPTIONS = {
    "fr": [
        {"title": "Voir mes chantiers", "id": "view_sites", "description": "Consulter mes projets actifs"},
        {"title": "Consulter mes taches", "id": "view_tasks", "description": "Voir mes taches assignees"},
        {"title": "Acceder aux documents", "id": "view_documents", "description": "Plans et documents"},
        {"title": "Signaler un incident", "id": "report_incident", "description": "Declarer un probleme"},
        {"title": "Mettre a jour avancement", "id": "update_progress", "description": "Mettre a jour mes taches"},
        {"title": "Parler avec equipe", "id": "talk_team", "description": "Contacter ladministration"},
    ],
    "en": [
        {"title": "View my sites", "id": "view_sites", "description": "Check my active projects"},
        {"title": "Check my tasks", "id": "view_tasks", "description": "See my assigned tasks"},
        {"title": "Access documents", "id": "view_documents", "description": "Plans and documents"},
        {"title": "Report an incident", "id": "report_incident", "description": "Declare a problem"},
        {"title": "Update progress", "id": "update_progress", "description": "Update my tasks"},
        {"title": "Talk to team", "id": "talk_team", "description": "Contact administration"},
    ],
    "es": [
        {"title": "Ver mis obras", "id": "view_sites", "description": "Consultar proyectos activos"},
        {"title": "Ver mis tareas", "id": "view_tasks", "description": "Ver tareas asignadas"},
        {"title": "Acceder documentos", "id": "view_documents", "description": "Planos y documentos"},
        {"title": "Reportar incidente", "id": "report_incident", "description": "Declarar un problema"},
        {"title": "Actualizar progreso", "id": "update_progress", "description": "Actualizar mis tareas"},
        {"title": "Hablar con equipo", "id": "talk_team", "description": "Contactar administracion"},
    ],
    "pt": [
        {"title": "Ver minhas obras", "id": "view_sites", "description": "Consultar projetos ativos"},
        {"title": "Ver minhas tarefas", "id": "view_tasks", "description": "Ver tarefas atribuidas"},
        {"title": "Acessar documentos", "id": "view_documents", "description": "Planos e documentos"},
        {"title": "Relatar incidente", "id": "report_incident", "description": "Declarar um problema"},
        {"title": "Atualizar progresso", "id": "update_progress", "description": "Atualizar minhas tarefas"},
        {"title": "Falar com equipe", "id": "talk_team", "description": "Contatar administracao"},
    ],
    "de": [
        {"title": "Meine Baustellen", "id": "view_sites", "description": "Aktive Projekte ansehen"},
        {"title": "Meine Aufgaben", "id": "view_tasks", "description": "Zugewiesene Aufgaben"},
        {"title": "Dokumente zugreifen", "id": "view_documents", "description": "Plane und Dokumente"},
        {"title": "Vorfall melden", "id": "report_incident", "description": "Problem melden"},
        {"title": "Fortschritt aktualisieren", "id": "update_progress", "description": "Aufgaben aktualisieren"},
        {"title": "Mit Team sprechen", "id": "talk_team", "description": "Verwaltung kontaktieren"},
    ],
    "it": [
        {"title": "Vedi i miei cantieri", "id": "view_sites", "description": "Consultare progetti attivi"},
        {"title": "Vedi i miei compiti", "id": "view_tasks", "description": "Vedere compiti assegnati"},
        {"title": "Accedi ai documenti", "id": "view_documents", "description": "Piani e documenti"},
        {"title": "Segnala incidente", "id": "report_incident", "description": "Dichiarare un problema"},
        {"title": "Aggiorna progresso", "id": "update_progress", "description": "Aggiornare i compiti"},
        {"title": "Parla con il team", "id": "talk_team", "description": "Contattare amministrazione"},
    ],
    "ro": [
        {"title": "Vezi santierele mele", "id": "view_sites", "description": "Consulta proiecte active"},
        {"title": "Vezi sarcinile mele", "id": "view_tasks", "description": "Vezi sarcini atribuite"},
        {"title": "Acceseaza documente", "id": "view_documents", "description": "Planuri si documente"},
        {"title": "Raporteaza incident", "id": "report_incident", "description": "Declara o problema"},
        {"title": "Actualizeaza progres", "id": "update_progress", "description": "Actualizeaza sarcini"},
        {"title": "Vorbeste cu echipa", "id": "talk_team", "description": "Contacteaza administratia"},
    ],
    "pl": [
        {"title": "Zobacz moje place budowy", "id": "view_sites", "description": "Sprawdz aktywne projekty"},
        {"title": "Zobacz moje zadania", "id": "view_tasks", "description": "Zobacz przypisane zadania"},
        {"title": "Dostep do dokumentow", "id": "view_documents", "description": "Plany i dokumenty"},
        {"title": "Zglosz incydent", "id": "report_incident", "description": "Zglaszanie problemu"},
        {"title": "Aktualizuj postep", "id": "update_progress", "description": "Aktualizuj zadania"},
        {"title": "Porozmawiaj z zespolem", "id": "talk_team", "description": "Skontaktuj sie z administracja"},
    ],
    "ar": [
        {"title": "عرض مواقعي", "id": "view_sites", "description": "مشاهدة المشاريع النشطة"},
        {"title": "عرض مهامي", "id": "view_tasks", "description": "رؤية المهام المعينة"},
        {"title": "الوصول للوثائق", "id": "view_documents", "description": "الخطط والوثائق"},
        {"title": "الإبلاغ عن حادث", "id": "report_incident", "description": "الإبلاغ عن مشكلة"},
        {"title": "تحديث التقدم", "id": "update_progress", "description": "تحديث المهام"},
        {"title": "التحدث مع الفريق", "id": "talk_team", "description": "الاتصال بالإدارة"},
    ],
}

GREETINGS = {
    "fr": "Bonjour {{1}} !",
    "en": "Hello {{1}}!",
    "es": "Hola {{1}}!",
    "pt": "Ola {{1}}!",
    "de": "Hallo {{1}}!",
    "it": "Ciao {{1}}!",
    "ro": "Buna {{1}}!",
    "pl": "Czesc {{1}}!",
    "ar": "مرحبا {{1}}!",
}

BUTTON_TEXTS = {
    "fr": "Choisir",
    "en": "Choose",
    "es": "Elegir",
    "pt": "Escolher",
    "de": "Wahlen",
    "it": "Scegli",
    "ro": "Alege",
    "pl": "Wybierz",
    "ar": "اختر",
}


async def create_template_for_language(client: Client, language: str) -> dict:
    """Create a greeting template for a specific language."""
    try:
        greeting = GREETINGS[language]
        button_text = BUTTON_TEXTS[language]
        options = MENU_OPTIONS[language]

        # Build template items
        template_items = []
        for option in options:
            template_items.append({
                "item": option["title"],
                "id": option["id"],
                "description": option["description"]
            })

        # Create template using REST API directly
        friendly_name = f"greeting_menu_{language}"

        # Prepare payload
        payload = {
            "friendly_name": friendly_name,
            "language": language,
            "types": {
                "twilio/list-picker": {
                    "body": greeting,
                    "button": button_text,
                    "items": template_items
                }
            }
        }

        log.info(f"Creating template for {language}...")
        log.info(f"Payload: {json.dumps(payload, indent=2)}")

        # Use REST API directly
        import requests
        from requests.auth import HTTPBasicAuth

        url = f"https://content.twilio.com/v1/Content"
        auth = HTTPBasicAuth(settings.twilio_account_sid, settings.twilio_auth_token)

        response = requests.post(
            url,
            auth=auth,
            json=payload
        )

        if response.status_code == 201:
            content_data = response.json()
            content_sid = content_data.get("sid")
            log.info(f"✅ Created {language}: {content_sid}")

            return {
                "template_name": "greeting_menu",
                "language": language,
                "twilio_content_sid": content_sid,
                "template_type": "list_picker",
                "description": f"Greeting menu with 6 fixed options for {language}",
                "is_active": True
            }
        else:
            log.error(f"❌ Error creating template for {language}: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        log.error(f"❌ Error creating template for {language}: {e}")
        return None


async def main():
    """Create all greeting templates and store in database."""
    log.info("=" * 60)
    log.info("Creating greeting menu templates for all languages")
    log.info("=" * 60)

    # Initialize Twilio client
    client = Client(
        settings.twilio_account_sid,
        settings.twilio_auth_token
    )

    # Create templates for all languages
    created_templates = []

    for language in MENU_OPTIONS.keys():
        template_data = await create_template_for_language(client, language)
        if template_data:
            created_templates.append(template_data)

    # Store in database
    log.info(f"\n📝 Storing {len(created_templates)} templates in database...")

    for template in created_templates:
        try:
            result = supabase_client.client.table("templates").insert(template).execute()
            log.info(f"✅ Stored {template['language']} in database")
        except Exception as e:
            log.error(f"❌ Error storing {template['language']}: {e}")

    log.info("\n" + "=" * 60)
    log.info(f"✅ DONE! Created and stored {len(created_templates)} templates")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
