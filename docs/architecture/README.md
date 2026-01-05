# Architecture Overview

This document provides a comprehensive overview of the Lumiera WhatsApp API architecture, design patterns, and key components.

## Table of Contents
- [System Architecture](#system-architecture)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Design Patterns](#design-patterns)
- [Scalability](#scalability)
- [Security Architecture](#security-architecture)

---

## System Architecture

### High-Level Architecture

```
┌─────────────────┐
│  WhatsApp User  │
└────────┬────────┘
         │ (Twilio WhatsApp API)
         ↓
┌─────────────────────────────────────────────────────────┐
│              Lumiera WhatsApp API (FastAPI)             │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │         Message Processing Pipeline             │   │
│  │  1. Authenticate  → 2. Session → 3. Language    │   │
│  │  4. Audio → 5. Translate → 6. Intent → 7. Route│   │
│  │  8. Response → 9. Persist                       │   │
│  └────────────────────────────────────────────────┘   │
│                        ↓                                │
│  ┌──────────────────────────────────────┐             │
│  │  Intent Router (Confidence-Based)     │             │
│  │                                        │             │
│  │  High Confidence (≥90%)  │  Low (<90%)│             │
│  │         ↓                 │      ↓     │             │
│  │   Fast Path Handler    Full Agent     │             │
│  │   (Direct execution)   (Claude Opus)  │             │
│  └──────────────────────────────────────┘             │
└──────────┬──────────────────────┬──────────────────────┘
           │                      │
           ↓                      ↓
    ┌─────────────┐      ┌────────────────┐
    │  Supabase   │      │ PlanRadar API  │
    │  Database   │      │ (Projects/Tasks)│
    └─────────────┘      └────────────────┘
```

### Technology Stack

**Core Framework:**
- **Python 3.11+**: Modern Python with async support
- **FastAPI**: High-performance web framework
- **Uvicorn**: ASGI server

**AI/ML:**
- **LangChain**: Agent orchestration framework
- **Claude Opus 4.5**: Advanced reasoning and tool use (Anthropic)
- **Claude Haiku**: Fast intent classification
- **OpenAI Whisper**: Audio transcription

**Integrations:**
- **Twilio**: WhatsApp messaging API
- **Supabase**: PostgreSQL database + storage
- **PlanRadar**: Project management platform

**Infrastructure:**
- **Nginx**: Reverse proxy with SSL
- **Supervisor**: Process management
- **Docker**: Containerization (optional)

---

## Core Components

### 1. Message Pipeline (`src/handlers/message_pipeline.py`)

The **heart of the system** - processes all inbound messages through 9 discrete stages:

```python
class MessagePipeline:
    """Pipeline for processing inbound WhatsApp messages."""

    async def process(self, from_number, message_body, ...) -> Result:
        """Process message through all 9 stages."""

        # Stage 1: Authenticate user
        # Stage 2: Get or create session
        # Stage 3: Detect language
        # Stage 4: Process audio (if applicable)
        # Stage 5: Translate to French
        # Stage 6: Classify intent
        # Stage 7: Route to handler/agent
        # Stage 8: Translate response
        # Stage 9: Persist messages
```

**Benefits:**
- ✅ Testable stages
- ✅ Clear separation of concerns
- ✅ Easy to add new stages
- ✅ Structured error handling
- ✅ Early exit on failures

[Learn more →](./PIPELINE_ARCHITECTURE.md)

### 2. Intent Router (`src/services/intent_router.py`)

Routes user intents to appropriate handlers based on confidence:

```python
class IntentRouter:
    """Centralized intent routing with confidence-based optimization."""

    async def route_intent(self, intent, user_id, ...) -> Optional[Dict]:
        """Route intent to fast path handler or return None for full agent."""

        handler = self._get_handler(intent)
        if not handler:
            return None  # Fallback to full agent

        return await handler(user_id=user_id, ...)
```

**Supported Fast Path Intents:**
- `greeting` - Welcome message + interactive menu
- `list_projects` - Direct database query
- `view_tasks` - Context-aware task listing
- `view_documents` - Project documents access
- `report_incident` - Incident reporting flow
- `update_progress` - Progress update flow
- `escalate_to_human` - Human handoff

[Learn more →](./FAST_PATH_SYSTEM.md)

### 3. LangChain Agent (`src/agent/agent.py`)

Full AI agent with tool calling for complex interactions:

```python
class LumieraAgent:
    """Claude Opus 4.5 agent with tool calling."""

    async def process_message(
        self,
        user_id: str,
        message_text: str,
        chat_history: List[BaseMessage],
        user_context: str,
        ...
    ) -> Dict:
        """Process message with full agent capabilities."""

        # Execute agent with tools
        result = await self.agent_executor.ainvoke({
            "input": message_text,
            "chat_history": chat_history,
            "user_context": user_context,
        })

        return {
            "message": result["output"],
            "escalation": ctx.escalation_occurred,
            "tools_called": ctx.tools_called,
        }
```

**Available Tools:**
- `list_projects_tool` - List user's projects
- `list_tasks_tool` - List project tasks
- `get_task_description_tool` - Get task details
- `submit_incident_report_tool` - Create incident
- `update_task_progress_tool` - Update progress
- `escalate_to_human_tool` - Human handoff
- And 10+ more...

[Learn more →](./AGENT_SYSTEM.md)

### 4. Error Handling System

Structured error propagation throughout the system:

```python
# Custom exceptions with error codes
class LumieraException(Exception):
    def __init__(self, message, error_code, user_message, details):
        """Structured exception with context."""

# Result wrapper for error propagation
@dataclass
class Result(Generic[T]):
    success: bool
    data: Optional[T]
    error_code: Optional[ErrorCode]
    error_message: Optional[str]
    user_message: Optional[str]

    @staticmethod
    def ok(data: T) -> 'Result[T]':
        """Create successful result."""

    @staticmethod
    def fail(error_code, message) -> 'Result[T]':
        """Create failed result."""
```

**Error Codes:**
- `USER_1001` - User not found
- `PROJECT_2001` - Project not found
- `INTEGRATION_3001` - Database error
- `LOGIC_4001` - Invalid intent
- `SYSTEM_5001` - Internal error
- And 15+ more...

[Learn more →](./ERROR_HANDLING.md)

### 5. Translation Service (`src/services/translation.py`)

Automatic translation between user language and French (internal language):

```python
class TranslationService:
    """Bidirectional translation using Claude."""

    async def translate_to_french(self, text: str, from_lang: str) -> str:
        """Translate user message to French for processing."""

    async def translate_from_french(self, text: str, to_lang: str) -> str:
        """Translate response back to user language."""

    async def detect_language(self, text: str) -> str:
        """Detect language of user message."""
```

**Supported Languages (9):**
- French (fr) - Internal language
- English (en)
- Spanish (es)
- Portuguese (pt)
- German (de)
- Italian (it)
- Romanian (ro)
- Polish (pl)
- Arabic (ar)

### 6. Session Management (`src/services/session.py`)

Intelligent conversation session tracking:

```python
class SessionService:
    """Smart session management with time-based detection."""

    async def get_or_create_session(self, user_id: str) -> Dict:
        """
        Get active session or create new one.
        - New session after 7 hours of inactivity
        - Or if last message was outside working hours (6-8 AM)
        """
```

**Session Logic:**
- Sessions timeout after 7 hours
- New session if last message before 6 AM or after 8 PM
- Session tracking for context and analytics

### 7. Database Client (`src/integrations/supabase.py`)

Repository pattern for all database operations:

```python
class SupabaseClient:
    """Supabase client with repository methods."""

    # User management
    async def get_user_by_phone(self, phone: str) -> Dict
    async def create_or_update_user(self, phone, **kwargs) -> Dict

    # Message operations
    async def save_message(self, user_id, message_text, ...) -> Dict
    async def get_conversation_history(self, user_id, limit) -> List

    # Project operations
    async def get_user_projects(self, user_id) -> List
    async def get_project_by_id(self, project_id) -> Dict

    # And 16+ more methods...
```

**Benefits:**
- ✅ Centralized database access
- ✅ Consistent error handling
- ✅ Easy to mock for testing
- ✅ Type safety with return types

---

## Data Flow

### Inbound Message Flow

```
1. User sends WhatsApp message
   ↓
2. Twilio receives and forwards to webhook
   ↓
3. FastAPI endpoint: POST /webhook/whatsapp
   ↓
4. Message Pipeline processes (9 stages)
   ↓
5. Intent Router determines path
   ↓
6a. Fast Path Handler (high confidence)
    - Direct execution
    - Quick response
   ↓
6b. Full Agent (low confidence)
    - LangChain agent
    - Tool calling
    - Complex reasoning
   ↓
7. Response generated (in French)
   ↓
8. Translation to user language
   ↓
9. Interactive formatting (menus, buttons)
   ↓
10. Twilio sends WhatsApp message
    ↓
11. User receives response
```

### Fast Path vs Full Agent

**Fast Path** (≥90% confidence):
```
Message → Intent Classification (Haiku)
       → Fast Path Handler (Direct)
       → Response (500ms, $0.0001)
```

**Full Agent** (<90% confidence):
```
Message → Intent Classification (Haiku)
       → Full Agent (Opus)
       → Tool Calling
       → Context Retrieval
       → Reasoning
       → Response (3-5s, $0.015)
```

**Performance Impact:**
- 50% of messages use fast path
- 3-5x faster response time
- 50% cost reduction
- Same quality user experience

[Learn more →](./FAST_PATH_SYSTEM.md)

---

## Design Patterns

### 1. Pipeline Pattern
Message processing broken into discrete, testable stages:
- ✅ Single Responsibility Principle
- ✅ Easy to test each stage independently
- ✅ Clear error handling at each step
- ✅ Easy to add new stages

### 2. Repository Pattern
Database access centralized in SupabaseClient:
- ✅ Separation of concerns
- ✅ Easy to mock for testing
- ✅ Consistent error handling
- ✅ Type safety

### 3. Strategy Pattern
Intent routing with interchangeable handlers:
- ✅ Fast path vs full agent selection
- ✅ Easy to add new handlers
- ✅ Confidence-based routing

### 4. Result Pattern
Error handling without exceptions:
- ✅ Explicit success/failure
- ✅ Type-safe error propagation
- ✅ Early exit on failures
- ✅ Structured error context

### 5. Context Manager Pattern
Thread-safe execution context:
- ✅ Automatic cleanup
- ✅ Isolated per request
- ✅ Safe for concurrent requests

---

## Scalability

### Current Capacity
- **Concurrent requests**: 50+ (limited by FastAPI workers)
- **Response time**: 0.5-5s depending on path
- **Database**: Supabase (auto-scaling)
- **API rate limits**: Anthropic (5000 req/min for Haiku, 4000 for Opus)

### Bottlenecks
1. **Claude API calls**: Rate limited by Anthropic
2. **Database queries**: Mitigated by connection pooling
3. **Twilio webhooks**: Handled asynchronously

### Scaling Strategies
1. **Horizontal scaling**: Add more FastAPI workers
2. **Caching**: Cache intent classifications, translations
3. **Queue system**: Add RabbitMQ/Redis for async processing
4. **Database read replicas**: For high read loads
5. **CDN**: For media files

### Performance Optimizations
- ✅ Fast path for common intents (50% requests)
- ✅ Async operations throughout
- ✅ Database connection pooling
- ✅ Cached translations for common phrases
- ✅ Lazy loading of heavy dependencies

---

## Security Architecture

### Authentication
- **User**: WhatsApp phone number (validated by Twilio)
- **Webhook**: Twilio signature verification
- **Database**: Service role key (never exposed to clients)

### Authorization
- **User isolation**: All queries filtered by user_id
- **RLS policies**: Row-level security in Supabase
- **Tool permissions**: Users can only access their own data

### Input Validation
- **Prompt injection prevention**: Pattern detection + sanitization
- **SQL injection prevention**: Parameterized queries
- **XSS prevention**: Output sanitization
- **Rate limiting**: Per user/phone number

### Error Handling
- **No sensitive data in logs**: PII redacted
- **User-friendly error messages**: No technical details exposed
- **Escalation on security events**: Admin notified

### Audit Trail
- **All messages logged**: Full conversation history
- **Action logs**: All tool calls tracked
- **Error tracking**: All failures logged
- **Escalations tracked**: Manual review possible

[Learn more →](../security/BEST_PRACTICES.md)

---

## Monitoring & Observability

### Logging
- **Structured logging**: JSON format with context
- **Log levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Rotation**: Daily log files
- **Retention**: 90 days

### Metrics (Planned)
- **Response time**: P50, P95, P99
- **Success rate**: By intent, by path
- **Error rate**: By error code
- **Fast path usage**: % of requests
- **Cost tracking**: API usage by model

### Tracing (Optional)
- **LangSmith**: LangChain execution traces
- **Sentry**: Error tracking and alerting

---

## Related Documentation

- [Pipeline Architecture](./PIPELINE_ARCHITECTURE.md) - Detailed pipeline docs
- [Error Handling](./ERROR_HANDLING.md) - Error propagation system
- [Fast Path System](./FAST_PATH_SYSTEM.md) - Performance optimization
- [Agent System](./AGENT_SYSTEM.md) - LangChain agent details
- [Design Decisions](../design-decisions/README.md) - Why things are built this way
- [Database Schema](../database/SCHEMA.md) - Complete schema reference

---

**Last Updated**: 2026-01-05
**Version**: 2.0.0
