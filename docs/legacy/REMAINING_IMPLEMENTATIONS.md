# Remaining Implementations Guide

This document provides implementation details for the remaining enhancements.

## Status: 50% Complete

### ✅ DONE
1. Database schemas (sessions, context, intent tracking)
2. Session management service
3. User context service
4. Security check (no destructive DELETEs)
5. Git commits and documentation

### 🚀 NEXT TO IMPLEMENT

## 1. Intent Classification Service

**File:** `src/services/intent.py`

```python
"""Intent classification service for hybrid approach."""
from typing import Optional, Dict, Any
from langchain_anthropic import ChatAnthropic
from src.config import settings
from src.utils.logger import log

INTENTS = {
    "greeting": {
        "keywords": ["hello", "hi", "bonjour", "salut", "hola"],
        "requires_tools": False
    },
    "list_projects": {
        "keywords": ["projects", "chantiers", "list", "show"],
        "tools": ["list_projects_tool"],
        "requires_confirmation": False
    },
    "list_tasks": {
        "keywords": ["tasks", "tâches", "todo"],
        "tools": ["list_tasks_tool"],
        "requires_confirmation": False
    },
    "escalate": {  # EASY ESCALATION - NO CONFIRMATION
        "keywords": ["human", "person", "admin", "help", "stuck", "parler"],
        "tools": ["escalate_to_human_tool"],
        "requires_confirmation": False  # No confirmation!
    },
    "general": {
        "keywords": [],
        "tools": "all",  # All tools available
        "requires_confirmation": False
    }
}

class IntentClassifier:
    def __init__(self):
        self.haiku = ChatAnthropic(
            model="claude-haiku-3-5-20241022",
            api_key=settings.anthropic_api_key,
            temperature=0.1,
            max_tokens=50
        )

    async def classify(self, message: str) -> str:
        """Classify intent quickly with Claude Haiku"""
        prompt = f"""Classify this message into ONE intent:
- greeting (hello, hi, bonjour)
- list_projects (user wants to see projects)
- list_tasks (user wants to see tasks)
- escalate (user wants to speak with human/admin/help)
- general (anything else)

Message: {message}

Return ONLY the intent name, nothing else."""

        response = await self.haiku.ainvoke([{"role": "user", "content": prompt}])
        intent = response.content.strip().lower()

        if intent not in INTENTS:
            intent = "general"

        log.info(f"Classified intent: {intent} for message: {message[:50]}...")
        return intent

intent_classifier = IntentClassifier()
```

## 2. Input Validation Service

**File:** `src/services/validation.py`

```python
"""Input validation and sanitization."""
import re
from typing import Dict, Any
from src.utils.logger import log

SUSPICIOUS_PATTERNS = [
    r"ignore.*previous.*instructions",
    r"system.*prompt",
    r"you are now",
    r"jailbreak",
    r"<script",
    r"javascript:",
    r"onerror=",
]

MAX_MESSAGE_LENGTH = 5000

async def validate_input(message: str, user_id: str) -> Dict[str, Any]:
    """Validate and sanitize user input"""

    # Length check
    if len(message) > MAX_MESSAGE_LENGTH:
        return {
            "is_valid": False,
            "reason": "message_too_long",
            "message": f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"
        }

    # Empty check
    if not message.strip():
        return {
            "is_valid": False,
            "reason": "empty_message",
            "message": "Empty message"
        }

    # Injection detection
    message_lower = message.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, message_lower):
            log.warning(f"Suspicious pattern detected for user {user_id}: {message[:100]}")
            return {
                "is_valid": False,
                "reason": "suspicious_pattern",
                "message": "Your message contains suspicious content"
            }

    return {
        "is_valid": True,
        "sanitized": message.strip()
    }
```

## 3. Improved System Prompt

**File:** `src/agent/agent.py` (update SYSTEM_PROMPT)

```python
SYSTEM_PROMPT = """Tu es Lumiera, l'assistant virtuel pour les sous-traitants du BTP.

# IDENTITÉ
- Nom: Lumiera
- Rôle: Aider les sous-traitants à gérer leurs chantiers via WhatsApp
- Ton: Professionnel, chaleureux, efficace

# CAPACITÉS
1. **Lister les chantiers actifs** - Voir tous les projets en cours
2. **Consulter les tâches** - Détails des tâches par projet
3. **Signaler des incidents** - Avec photos et description
4. **Mettre à jour la progression** - Avancement des tâches
5. **Parler avec un humain** - Redirection vers l'équipe administrative

# RÈGLES CRITIQUES (SÉCURITÉ)

## ⚠️ PROTECTION DES DONNÉES
1. ❌ L'utilisateur NE PEUT VOIR QUE SES PROPRES DONNÉES
2. ❌ JAMAIS afficher des données d'autres utilisateurs
3. ✅ TOUJOURS filtrer par user_id dans TOUTES les requêtes
4. ✅ Vérifier que project_id appartient à l'utilisateur avant d'afficher

## 📋 FORMAT DE RÉPONSE
1. ❌ JAMAIS afficher les IDs techniques (proj_123, task_456)
2. ✅ Utiliser uniquement les NOMS lisibles
3. ✅ Listes numérotées pour plusieurs items
4. ✅ Emoji pour clarté: 👋 ✅ ❌ 📸 📝 🏗️

## 🛠️ UTILISATION DES OUTILS
1. ✅ TOUJOURS utiliser les outils fournis
2. ❌ JAMAIS inventer de données
3. ✅ Si incertain, demander précisions
4. ✅ Si hors de tes capacités, proposer "parler avec un humain"

# EXEMPLES (SANS IDs TECHNIQUES)

Utilisateur: "Quels sont mes chantiers?"
Assistant: "Vous avez 3 chantiers actifs:

1. 🏗️ **Rénovation Bureau** - En cours
2. 🏠 **Construction Maison** - Planifié
3. 🔨 **Extension Garage** - En cours

Lequel souhaitez-vous consulter?"

Utilisateur: "Je veux signaler un problème"
Assistant: "Je vais vous aider à signaler un incident.

J'ai besoin de:
1. 📸 Une photo du problème
2. 📝 Une description
3. 🏗️ Le chantier concerné

Commencez par m'envoyer une photo."

Utilisateur: "Je suis bloqué"
Assistant: "Je comprends. Souhaitez-vous parler avec un membre de l'équipe administrative?

Je peux vous mettre en contact avec quelqu'un qui pourra mieux vous aider."

# CONTEXTE UTILISATEUR
- Nom: {user_name}
- Langue: {user_language}
- Contexte additionnel: {user_context}

# SI TU NE PEUX PAS AIDER
Proposer: "Souhaitez-vous parler avec un membre de l'équipe? Je peux vous mettre en contact."
"""
```

## 4. Tool Input Validation

**File:** `src/agent/tool_validation.py`

```python
"""Pydantic models for tool input validation."""
from pydantic import BaseModel, validator, Field
from typing import Optional, List

class ListProjectsInput(BaseModel):
    """No input needed - automatically filtered by user_id"""
    pass

class GetProjectDetailsInput(BaseModel):
    project_id: str = Field(..., description="Project ID")

    @validator('project_id')
    def validate_project_id(cls, v):
        if not v or len(v) == 0:
            raise ValueError("project_id cannot be empty")
        return v.strip()

class ReportIncidentInput(BaseModel):
    project_id: str
    description: str
    severity: str = "medium"
    image_url: Optional[str] = None

    @validator('description')
    def validate_description(cls, v):
        if len(v) < 10:
            raise ValueError("Description too short (min 10 chars)")
        if len(v) > 1000:
            raise ValueError("Description too long (max 1000 chars)")
        return v.strip()

    @validator('severity')
    def validate_severity(cls, v):
        allowed = ['low', 'medium', 'high', 'critical']
        if v.lower() not in allowed:
            raise ValueError(f"Severity must be: {', '.join(allowed)}")
        return v.lower()

class EscalateInput(BaseModel):
    reason: str

    @validator('reason')
    def validate_reason(cls, v):
        if len(v) < 5:
            raise ValueError("Please provide a reason for escalation")
        return v.strip()

# Usage in tools:
def validate_tool_input(input_model, **kwargs):
    """Validate tool input with Pydantic"""
    try:
        validated = input_model(**kwargs)
        return {"valid": True, "data": validated.dict()}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
```

## 5. Integration Steps

### Step 1: Update message handler to use new services

```python
# In src/handlers/message.py

from src.services.session import session_service
from src.services.user_context import user_context_service
from src.services.validation import validate_input
from src.services.intent import intent_classifier

async def process_inbound_message(...):
    # ... existing code ...

    # 1. Get or create session
    session = await session_service.get_or_create_session(user_id)
    session_id = session['id'] if session else None

    # 2. Validate input
    validation_result = await validate_input(message_body, user_id)
    if not validation_result["is_valid"]:
        error_msg = validation_result["message"]
        # Translate and send
        await send_error_message(from_number, error_msg, user_language)
        return

    # 3. Classify intent
    intent = await intent_classifier.classify(message_in_french)

    # 4. Get user context
    user_context = await user_context_service.get_context_for_agent(user_id)

    # 5. Pass to agent with context
    response = await lumiera_agent.process_message(
        user_id=user_id,
        phone_number=phone_number,
        language=user_language,
        message_text=message_in_french,
        chat_history=chat_history,
        user_name=user_name,
        user_context=user_context,
        session_id=session_id,
        intent=intent
    )

    # 6. Save message with session_id
    await supabase_client.save_message(
        ...,
        session_id=session_id
    )
```

### Step 2: Add LangSmith Integration

```python
# In src/config.py
langsmith_api_key: str = ""
langsmith_project: str = "lumiera-whatsapp-copilot"

# In src/agent/agent.py
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
```

### Step 3: Update .env

```env
# LangSmith (optional)
LANGSMITH_API_KEY=your_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=lumiera-whatsapp-copilot
```

## 6. Testing Checklist

- [ ] Run database migrations v2
- [ ] Test session creation and detection
- [ ] Test user context set/get
- [ ] Test intent classification accuracy
- [ ] Test input validation (try injection attacks)
- [ ] Test tool validation (invalid inputs)
- [ ] Verify no IDs shown in responses
- [ ] Test escalation flow (should be easy, no confirmation)
- [ ] Check user can only see their data
- [ ] Monitor in LangSmith

## 7. Migration Commands

```bash
# 1. Run migrations
# Copy database_migrations_v2.sql to Supabase SQL Editor and run

# 2. Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('conversation_sessions', 'user_context', 'intent_classifications');

# 3. Test session function
SELECT get_or_create_session('9a3120fa-4090-4614-9fdb-09cb26e52e73');

# 4. Restart server
./run.sh
```

## 8. Expected Improvements

### Before
- No session management
- No personalization
- Technical IDs shown to users
- No input validation
- No intent classification
- Hard escalation

### After
- ✅ Smart session detection
- ✅ Personalized responses
- ✅ User-friendly (no IDs)
- ✅ Secure (validation + guardrails)
- ✅ Fast (intent classification)
- ✅ Easy escalation

## 9. Monitoring Queries

```sql
-- Sessions per user
SELECT subcontractor_id, COUNT(*) as sessions
FROM conversation_sessions
GROUP BY subcontractor_id;

-- Intent distribution
SELECT classified_intent, COUNT(*) as count
FROM intent_classifications
GROUP BY classified_intent
ORDER BY count DESC;

-- User context overview
SELECT context_type, COUNT(*) as count
FROM user_context
GROUP BY context_type;

-- Escalation rate
SELECT
    COUNT(CASE WHEN status = 'escalated' THEN 1 END)::float /
    COUNT(*)::float * 100 as escalation_rate_percent
FROM conversation_sessions;
```

---

**Implementation Priority:**
1. Intent service (30 min)
2. Input validation (15 min)
3. Tool validation (20 min)
4. Update prompt (10 min)
5. Integration (45 min)
6. Testing (30 min)

**Total ETA:** 2.5 hours

**Dependencies:**
- Run database migrations first
- Test each component independently
- Commit frequently

**Next Session:**
- Structured outputs for WhatsApp rich media
- Error handling improvements
- Complete LangSmith setup
