# Pipeline Architecture

The message processing pipeline is the core of Lumiera's architecture. It breaks down the complex task of processing WhatsApp messages into 9 discrete, testable stages.

## Overview

### Why a Pipeline?

**Before (God Function):**
- 439 lines of tangled logic
- Difficult to test
- Hard to maintain
- Error handling scattered throughout
- Unclear dependencies

**After (Pipeline):**
- 9 clear stages (< 50 lines each)
- Easily testable
- Maintainable and extensible
- Structured error handling
- Clear data flow

### Pipeline Benefits

✅ **Single Responsibility**: Each stage does one thing
✅ **Testability**: Test each stage in isolation
✅ **Error Handling**: Early exit on failures
✅ **Observability**: Log progress at each stage
✅ **Maintainability**: Easy to understand and modify
✅ **Extensibility**: Easy to add new stages

---

## Pipeline Stages

```python
class MessagePipeline:
    """Pipeline for processing inbound WhatsApp messages."""

    async def process(self, from_number, message_body, ...) -> Result[Dict]:
        """Process message through 9 stages."""

        ctx = MessageContext(...)

        # Stage 1: Authenticate user
        result = await self._authenticate_user(ctx)
        if not result.success:
            return result

        # Stage 2: Get or create session
        result = await self._manage_session(ctx)
        if not result.success:
            return result

        # ... stages 3-9 ...

        return Result.ok({
            "message": ctx.response_text,
            "escalation": ctx.escalation,
            "tools_called": ctx.tools_called,
            "session_id": ctx.session_id
        })
```

---

## Stage 1: Authenticate User

**Purpose**: Verify user identity and load profile.

**Input**: `phone_number` from WhatsApp
**Output**: Populates `ctx.user_id`, `ctx.user_name`, `ctx.user_language`

```python
async def _authenticate_user(self, ctx: MessageContext) -> Result[None]:
    """Stage 1: Authenticate user by phone number."""

    user = await supabase_client.get_user_by_phone(ctx.from_number)
    if not user:
        raise UserNotFoundException(user_id=ctx.from_number)

    ctx.user_id = user['id']
    ctx.user_name = user.get('contact_prenom') or user.get('contact_name', '')
    ctx.user_language = user.get('language', 'fr')

    log.info(f"✅ User authenticated: {ctx.user_id} ({ctx.user_name})")
    return Result.ok(None)
```

**Error Handling**:
- `UserNotFoundException` if user not found
- Returns `Result.fail()` for any errors

**Performance**: ~50-100ms (database query)

---

## Stage 2: Manage Session

**Purpose**: Get active session or create new one.

**Input**: `ctx.user_id`
**Output**: Populates `ctx.session_id`

```python
async def _manage_session(self, ctx: MessageContext) -> Result[None]:
    """Stage 2: Get or create conversation session."""

    session = await session_service.get_or_create_session(ctx.user_id)
    if session:
        ctx.session_id = session['id']
        log.info(f"✅ Session: {ctx.session_id}")
        return Result.ok(None)
    else:
        raise AgentExecutionException(stage="session_management")
```

**Session Logic**:
- Get active session if within 7 hours
- Create new session if:
  - Last message > 7 hours ago
  - Last message outside working hours (before 6 AM or after 8 PM)

**Performance**: ~50-100ms (database query)

---

## Stage 3: Detect Language

**Purpose**: Confirm user's preferred language.

**Input**: `ctx.user_language` (from user profile)
**Output**: Validates `ctx.user_language`

```python
async def _detect_language(self, ctx: MessageContext) -> Result[None]:
    """Stage 3: Detect message language if not in user profile."""

    # Language already set from user profile in authenticate stage
    log.info(f"✅ Language: {ctx.user_language}")
    return Result.ok(None)
```

**Note**: Currently simplified. In the full flow (outside pipeline), language is detected for new messages and user profile is updated if changed.

**Performance**: ~1ms (no external calls)

---

## Stage 4: Process Audio

**Purpose**: Transcribe audio messages to text.

**Input**: `ctx.media_url`, `ctx.media_type`
**Output**: Updates `ctx.message_body` with transcription

```python
async def _process_audio(self, ctx: MessageContext) -> Result[None]:
    """Stage 4: Transcribe audio messages."""

    if not (ctx.media_url and ctx.media_type and 'audio' in ctx.media_type):
        return Result.ok(None)  # Skip if not audio

    log.info(f"🎤 Processing audio message")
    transcription = await transcription_service.transcribe_audio(
        ctx.media_url,
        target_language=ctx.user_language
    )

    if transcription:
        ctx.message_body = transcription
        log.info(f"✅ Audio transcribed: {transcription[:50]}...")
        return Result.ok(None)
    else:
        raise IntegrationException(service="Whisper", operation="transcription")
```

**Technology**: OpenAI Whisper API
**Performance**: ~2-5s (depends on audio length)

---

## Stage 5: Translate to French

**Purpose**: Convert message to French (internal processing language).

**Input**: `ctx.message_body`, `ctx.user_language`
**Output**: Populates `ctx.message_in_french`

```python
async def _translate_to_french(self, ctx: MessageContext) -> Result[None]:
    """Stage 5: Translate message to French (internal language)."""

    if ctx.user_language != "fr":
        ctx.message_in_french = await translation_service.translate_to_french(
            ctx.message_body,
            ctx.user_language
        )
        log.info(f"✅ Translated to French: {ctx.message_in_french[:50]}...")
    else:
        ctx.message_in_french = ctx.message_body

    return Result.ok(None)
```

**Why French?**
- Internal language for all processing
- Agent trained on French corpus
- Database content in French
- Consistency across system

**Technology**: Claude Haiku (fast, cheap)
**Performance**: ~200-500ms

---

## Stage 6: Classify Intent

**Purpose**: Determine user intent with confidence score.

**Input**: `ctx.message_in_french`, `ctx.user_id`
**Output**: Populates `ctx.intent`, `ctx.confidence`

```python
async def _classify_intent(self, ctx: MessageContext) -> Result[None]:
    """Stage 6: Classify user intent."""

    intent_result = await intent_classifier.classify(
        ctx.message_in_french,
        ctx.user_id
    )

    ctx.intent = intent_result['intent']
    ctx.confidence = intent_result.get('confidence', 0.0)

    log.info(f"✅ Intent: {ctx.intent} (confidence: {ctx.confidence:.2%})")
    return Result.ok(None)
```

**Intent Classification**:
- Uses Claude Haiku for fast classification
- Keyword matching for exact phrases
- Returns confidence score 0.0-1.0

**Common Intents**:
- `greeting` - Hello, bonjour, hi
- `list_projects` - Show my projects
- `view_tasks` - List tasks
- `report_incident` - Report a problem
- `update_progress` - Update task status
- `escalate_to_human` - Talk to admin
- `general` - Open-ended questions

**Technology**: Claude Haiku + keyword matching
**Performance**: ~200-400ms

---

## Stage 7: Route Message

**Purpose**: Route to fast path handler or full agent based on confidence.

**Input**: `ctx.intent`, `ctx.confidence`
**Output**: Populates `ctx.response_text`, `ctx.escalation`, `ctx.tools_called`

```python
async def _route_message(self, ctx: MessageContext) -> Result[None]:
    """Stage 7: Route to fast path handler or full agent."""

    from src.config import settings

    # Try fast path for high-confidence intents
    if (settings.enable_fast_path_handlers and
        ctx.confidence >= settings.intent_confidence_threshold):

        log.info(f"🚀 HIGH CONFIDENCE - Attempting fast path")

        from src.services.handlers import execute_direct_handler

        result = await execute_direct_handler(
            intent=ctx.intent,
            user_id=ctx.user_id,
            phone_number=ctx.from_number,
            user_name=ctx.user_name,
            language=ctx.user_language
        )

        if result:
            ctx.response_text = result.get("message")
            ctx.escalation = result.get("escalation", False)
            ctx.tools_called = result.get("tools_called", [])
            log.info(f"✅ Fast path succeeded")
            return Result.ok(None)

    # Fallback to full agent
    log.info(f"⚙️ Using full agent (Opus)")
    agent_result = await lumiera_agent.process_message(
        user_id=ctx.user_id,
        phone_number=ctx.from_number,
        user_name=ctx.user_name,
        language=ctx.user_language,
        message_text=ctx.message_in_french
    )

    ctx.response_text = agent_result.get("message")
    ctx.escalation = agent_result.get("escalation", False)
    ctx.tools_called = agent_result.get("tools_called", [])

    log.info(f"✅ Agent processed message")
    return Result.ok(None)
```

**Routing Decision**:
```
Confidence ≥ 90% + Fast path enabled?
   ├─ YES → Try fast path handler
   │         ├─ Success → Return fast path response
   │         └─ Failure → Fallback to full agent
   └─ NO  → Use full agent
```

**Performance**:
- Fast path: ~500ms
- Full agent: ~3-5s

---

## Stage 8: Translate Response

**Purpose**: Translate response back to user's language.

**Input**: `ctx.response_text` (in French), `ctx.user_language`
**Output**: Updates `ctx.response_text` to user language

```python
async def _translate_response(self, ctx: MessageContext) -> Result[None]:
    """Stage 8: Translate response back to user language."""

    if ctx.user_language != "fr" and ctx.response_text:
        ctx.response_text = await translation_service.translate_from_french(
            ctx.response_text,
            ctx.user_language
        )
        log.info(f"✅ Response translated to {ctx.user_language}")

    return Result.ok(None)
```

**Technology**: Claude Haiku
**Performance**: ~200-500ms

---

## Stage 9: Persist Messages

**Purpose**: Save inbound and outbound messages to database.

**Input**: All context data
**Output**: Messages saved to database

```python
async def _persist_messages(self, ctx: MessageContext) -> None:
    """Stage 9: Save inbound and outbound messages to database."""

    try:
        # Save inbound message
        await supabase_client.save_message(
            user_id=ctx.user_id,
            message_text=ctx.message_body,
            original_language=ctx.user_language,
            direction="inbound",
            message_sid=ctx.message_sid,
            media_url=ctx.media_url,
            message_type="audio" if ctx.media_type and 'audio' in ctx.media_type else "text",
            session_id=ctx.session_id
        )

        # Save outbound message
        await supabase_client.save_message(
            user_id=ctx.user_id,
            message_text=ctx.response_text,
            original_language=ctx.user_language,
            direction="outbound",
            session_id=ctx.session_id,
            is_escalation=ctx.escalation
        )

        log.info(f"✅ Messages persisted")

    except Exception as e:
        log.error(f"Failed to persist messages: {e}")
        # Don't fail the whole pipeline if persistence fails
```

**Note**: Persistence failures don't fail the pipeline since the response has already been generated.

**Performance**: ~100-200ms (2 database writes)

---

## Message Context

The `MessageContext` dataclass carries state through the pipeline:

```python
@dataclass
class MessageContext:
    """Context object passed through pipeline stages."""

    # Input
    from_number: str
    message_body: str
    message_sid: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    interactive_data: Optional[Dict[str, Any]] = None

    # Populated by pipeline stages
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_language: Optional[str] = None
    session_id: Optional[str] = None
    message_in_french: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    response_text: Optional[str] = None
    escalation: bool = False
    tools_called: list = field(default_factory=list)
```

**Benefits**:
- ✅ Clear data contract
- ✅ Type safety
- ✅ Easy to test
- ✅ Immutable after creation
- ✅ Self-documenting

---

## Error Handling

Each stage returns a `Result[None]` for structured error handling:

```python
# Success
return Result.ok(None)

# Failure
raise UserNotFoundException(user_id=user_id)
# or
return Result.fail(
    error_code=ErrorCode.USER_NOT_FOUND,
    error_message="User not found",
    user_message="Utilisateur non trouvé"
)
```

**Early Exit**:
If any stage fails, the pipeline exits early and returns the error to the user:

```python
result = await self._authenticate_user(ctx)
if not result.success:
    return result  # Exit pipeline, send error to user
```

**Exception Handling**:
```python
try:
    # All 9 stages
except LumieraException as e:
    return Result.from_exception(e)
except Exception as e:
    return Result.from_exception(e)
```

---

## Performance Metrics

### Per Stage Timings

| Stage | Fast Path | Full Agent | Notes |
|-------|-----------|------------|-------|
| 1. Authenticate | ~50ms | ~50ms | Database query |
| 2. Session | ~50ms | ~50ms | Database query |
| 3. Language | ~1ms | ~1ms | No external calls |
| 4. Audio | ~2-5s | ~2-5s | Only if audio message |
| 5. Translate | ~200ms | ~200ms | Claude Haiku |
| 6. Intent | ~300ms | ~300ms | Claude Haiku |
| 7. Route | ~500ms | ~3-5s | **Big difference** |
| 8. Response | ~200ms | ~200ms | Claude Haiku |
| 9. Persist | ~100ms | ~100ms | 2x database writes |
| **Total** | **~1.4s** | **~4-6s** | Excluding audio |

### Cost Per Request

| Component | Fast Path | Full Agent |
|-----------|-----------|------------|
| Intent classification | $0.0001 | $0.0001 |
| Translation (in) | $0.00005 | $0.00005 |
| Route execution | $0.0001 | $0.015 |
| Translation (out) | $0.00005 | $0.00005 |
| **Total** | **~$0.0002** | **~$0.015** |

**Savings**: 75x cheaper for fast path!

---

## Testing Strategy

### Unit Tests

Test each stage independently:

```python
async def test_authenticate_user_success():
    """Test successful authentication."""
    ctx = MessageContext(from_number="+33123456789", ...)
    pipeline = MessagePipeline()

    result = await pipeline._authenticate_user(ctx)

    assert result.success
    assert ctx.user_id is not None
    assert ctx.user_name is not None
```

### Integration Tests

Test full pipeline:

```python
async def test_pipeline_greeting():
    """Test pipeline with greeting message."""
    pipeline = MessagePipeline()

    result = await pipeline.process(
        from_number="+33123456789",
        message_body="bonjour",
        message_sid="SM123"
    )

    assert result.success
    assert "bonjour" in result.data["message"].lower()
    assert result.data["session_id"] is not None
```

### Error Tests

Test error handling:

```python
async def test_pipeline_user_not_found():
    """Test pipeline with unknown user."""
    pipeline = MessagePipeline()

    result = await pipeline.process(
        from_number="+33999999999",
        message_body="hello",
        message_sid="SM123"
    )

    assert not result.success
    assert result.error_code == ErrorCode.USER_NOT_FOUND
```

---

## Extending the Pipeline

### Adding a New Stage

1. **Define the method**:
```python
async def _new_stage(self, ctx: MessageContext) -> Result[None]:
    """Stage N: Description."""
    # Implementation
    return Result.ok(None)
```

2. **Add to pipeline**:
```python
async def process(self, ...) -> Result[Dict]:
    # ... existing stages ...

    # New stage
    result = await self._new_stage(ctx)
    if not result.success:
        return result

    # ... remaining stages ...
```

3. **Update MessageContext** if needed:
```python
@dataclass
class MessageContext:
    # ... existing fields ...
    new_field: Optional[str] = None
```

4. **Write tests**:
```python
async def test_new_stage():
    """Test new stage."""
    # Test implementation
```

### Example: Add Sentiment Analysis Stage

```python
async def _analyze_sentiment(self, ctx: MessageContext) -> Result[None]:
    """Stage 6.5: Analyze message sentiment."""

    sentiment = await sentiment_service.analyze(ctx.message_in_french)
    ctx.sentiment = sentiment  # Add to MessageContext

    log.info(f"✅ Sentiment: {sentiment}")
    return Result.ok(None)
```

---

## Related Documentation

- [Architecture Overview](./README.md) - System architecture
- [Error Handling](./ERROR_HANDLING.md) - Error propagation system
- [Fast Path System](./FAST_PATH_SYSTEM.md) - Performance optimization
- [Agent System](./AGENT_SYSTEM.md) - LangChain agent details
- [Design Decisions](../design-decisions/ARCHITECTURAL_REFACTORS.md) - Why we built the pipeline

---

**Last Updated**: 2026-01-05
**Version**: 2.0.0
