"""Centralized translations for fast path handlers and direct responses."""

# Fast path response templates
FAST_PATH_TRANSLATIONS = {
    "greeting": {
        "fr": "Bonjour{name} ! 👋\n\nComment puis-je vous aider aujourd'hui ?\n\n1. 🏗️ Voir mes chantiers actifs\n2. 📋 Consulter mes tâches\n3. 🚨 Signaler un incident\n4. ✅ Mettre à jour ma progression\n5. 🗣️ Parler avec l'équipe\n\nQue souhaitez-vous faire ?",
        "en": "Hello{name}! 👋\n\nHow can I help you today?\n\n1. 🏗️ View my active projects\n2. 📋 Check my tasks\n3. 🚨 Report an incident\n4. ✅ Update my progress\n5. 🗣️ Talk to the team\n\nWhat would you like to do?",
        "es": "¡Hola{name}! 👋\n\n¿Cómo puedo ayudarte hoy?\n\n1. 🏗️ Ver mis proyectos activos\n2. 📋 Consultar mis tareas\n3. 🚨 Reportar un incidente\n4. ✅ Actualizar mi progreso\n5. 🗣️ Hablar con el equipo\n\n¿Qué te gustaría hacer?",
        "pt": "Olá{name}! 👋\n\nComo posso ajudá-lo hoje?\n\n1. 🏗️ Ver meus projetos ativos\n2. 📋 Consultar minhas tarefas\n3. 🚨 Relatar um incidente\n4. ✅ Atualizar meu progresso\n5. 🗣️ Falar com a equipe\n\nO que você gostaria de fazer?",
        "ar": "مرحبا{name}! 👋\n\nكيف يمكنني مساعدتك اليوم؟\n\n1. 🏗️ عرض مشاريعي النشطة\n2. 📋 التحقق من مهامي\n3. 🚨 الإبلاغ عن حادث\n4. ✅ تحديث تقدمي\n5. 🗣️ التحدث مع الفريق\n\nماذا تريد أن تفعل؟",
        "de": "Hallo{name}! 👋\n\nWie kann ich Ihnen heute helfen?\n\n1. 🏗️ Meine aktiven Projekte ansehen\n2. 📋 Meine Aufgaben überprüfen\n3. 🚨 Einen Vorfall melden\n4. ✅ Meinen Fortschritt aktualisieren\n5. 🗣️ Mit dem Team sprechen\n\nWas möchten Sie tun?",
        "it": "Ciao{name}! 👋\n\nCome posso aiutarti oggi?\n\n1. 🏗️ Visualizza i miei progetti attivi\n2. 📋 Controlla le mie attività\n3. 🚨 Segnala un incidente\n4. ✅ Aggiorna i miei progressi\n5. 🗣️ Parla con il team\n\nCosa vorresti fare?",
    },
    "no_projects": {
        "fr": "Vous n'avez pas encore de chantiers actifs.",
        "en": "You don't have any active projects yet.",
        "es": "Aún no tienes proyectos activos.",
        "pt": "Você ainda não tem projetos ativos.",
        "ar": "ليس لديك مشاريع نشطة بعد.",
        "de": "Sie haben noch keine aktiven Projekte.",
        "it": "Non hai ancora progetti attivi.",
    },
    "projects_list_header": {
        "fr": "Vous avez {count} chantier(s) actif(s) :\n\n",
        "en": "You have {count} active project(s):\n\n",
        "es": "Tienes {count} proyecto(s) activo(s):\n\n",
        "pt": "Você tem {count} projeto(s) ativo(s):\n\n",
        "ar": "لديك {count} مشروع (مشاريع) نشط:\n\n",
        "de": "Sie haben {count} aktive(s) Projekt(e):\n\n",
        "it": "Hai {count} progetto/i attivo/i:\n\n",
    },
    "escalation_success": {
        "fr": "✅ Votre demande a été transmise à l'équipe administrative. Un membre de l'équipe vous contactera sous peu.",
        "en": "✅ Your request has been forwarded to the admin team. A team member will contact you shortly.",
        "es": "✅ Tu solicitud ha sido enviada al equipo administrativo. Un miembro del equipo te contactará pronto.",
        "pt": "✅ Sua solicitação foi encaminhada para a equipe administrativa. Um membro da equipe entrará em contato em breve.",
        "ar": "✅ تم إرسال طلبك إلى الفريق الإداري. سيتصل بك أحد أعضاء الفريق قريبًا.",
        "de": "✅ Ihre Anfrage wurde an das Admin-Team weitergeleitet. Ein Teammitglied wird sich in Kürze bei Ihnen melden.",
        "it": "✅ La tua richiesta è stata inoltrata al team amministrativo. Un membro del team ti contatterà a breve.",
    },
    "report_incident": {
        "fr": "Je vais vous aider à signaler un incident. 🚨\n\nPour créer un rapport d'incident, j'ai besoin de :\n\n1. 📸 *Au moins une photo* du problème\n2. 📝 *Une description* de ce qui s'est passé\n3. 🏗️ *Le chantier concerné*\n\nPouvez-vous m'envoyer une photo du problème ?",
        "en": "I'll help you report an incident. 🚨\n\nTo create an incident report, I need:\n\n1. 📸 *At least one photo* of the problem\n2. 📝 *A description* of what happened\n3. 🏗️ *The project concerned*\n\nCan you send me a photo of the problem?",
        "es": "Te ayudaré a reportar un incidente. 🚨\n\nPara crear un reporte de incidente, necesito:\n\n1. 📸 *Al menos una foto* del problema\n2. 📝 *Una descripción* de lo que pasó\n3. 🏗️ *El proyecto concernido*\n\n¿Puedes enviarme una foto del problema?",
        "pt": "Vou ajudá-lo a relatar um incidente. 🚨\n\nPara criar um relatório de incidente, preciso de:\n\n1. 📸 *Pelo menos uma foto* do problema\n2. 📝 *Uma descrição* do que aconteceu\n3. 🏗️ *O projeto em questão*\n\nVocê pode me enviar uma foto do problema?",
        "ar": "سأساعدك في الإبلاغ عن حادث. 🚨\n\nلإنشاء تقرير حادث، أحتاج إلى:\n\n1. 📸 *صورة واحدة على الأقل* للمشكلة\n2. 📝 *وصف* لما حدث\n3. 🏗️ *المشروع المعني*\n\nهل يمكنك إرسال صورة للمشكلة؟",
        "de": "Ich helfe Ihnen, einen Vorfall zu melden. 🚨\n\nUm einen Vorfallbericht zu erstellen, benötige ich:\n\n1. 📸 *Mindestens ein Foto* des Problems\n2. 📝 *Eine Beschreibung* dessen, was passiert ist\n3. 🏗️ *Das betroffene Projekt*\n\nKönnen Sie mir ein Foto des Problems senden?",
        "it": "Ti aiuterò a segnalare un incidente. 🚨\n\nPer creare un rapporto di incidente, ho bisogno di:\n\n1. 📸 *Almeno una foto* del problema\n2. 📝 *Una descrizione* di cosa è successo\n3. 🏗️ *Il progetto interessato*\n\nPuoi inviarmi una foto del problema?",
    },
}


def get_translation(key: str, language: str, **kwargs) -> str:
    """Get translated text for a given key and language.

    Args:
        key: Translation key (e.g., 'greeting', 'no_projects')
        language: Language code (fr, en, es, pt, ar, de, it)
        **kwargs: Format arguments for string interpolation

    Returns:
        Translated and formatted string
    """
    # Get translation dict for key
    translations = FAST_PATH_TRANSLATIONS.get(key, {})

    # Get translation for language, fallback to French
    text = translations.get(language, translations.get("fr", ""))

    # Format with kwargs if provided
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError as e:
            # If formatting fails, return unformatted text
            pass

    return text
