# FSM Module - Finite State Machine for Session Management

## Overview

This module provides a structured approach to managing user session states, handling state transitions, and resolving intent conflicts in the WhatsApp API.

## Quick Start

```python
from src.fsm import (
    StateManager,
    FSMEngine,
    IntentRouter,
    FSMContext,
    SessionState,
    clarification_manager
)

# Initialize components
state_manager = StateManager()
fsm_engine = FSMEngine(state_manager)
intent_router = IntentRouter()

# Create session context
context = FSMContext(
    user_id="user_123",
    current_state=SessionState.IDLE,
    session_id="session_456",
    task_id="task_789"
)

# Execute state transition
result = await fsm_engine.transition(
    context=context,
    to_state=SessionState.AWAITING_ACTION,
    trigger="start_update"
)

if result.success:
    print(f"Transitioned to {result.to_state}")
else:
    print(f"Transition failed: {result.error}")
```

## Module Structure

```
src/fsm/
├── __init__.py          # Module exports
├── models.py            # Data models (SessionState, FSMContext, etc.)
├── core.py              # Core FSM engine (StateManager, FSMEngine)
├── routing.py           # Intent routing & conflict resolution
├── handlers.py          # Clarification & session recovery
└── README.md            # This file
```

## Core Components

### 1. SessionState (Enum)

Defines valid states for a user session:

- `IDLE` - No active session
- `TASK_SELECTION` - Selecting which task to update
- `AWAITING_ACTION` - Waiting for user action
- `COLLECTING_DATA` - Actively collecting photos/comments
- `CONFIRMATION_PENDING` - Waiting for confirmation
- `COMPLETED` - Session successfully completed
- `ABANDONED` - Session abandoned (timeout or cancelled)

### 2. StateManager

Handles database operations for FSM state persistence.

**Key methods:**
- `get_session(user_id)` - Get active session
- `create_session(user_id, task_id, project_id)` - Create new session
- `update_session_state(session_id, new_state)` - Update state
- `check_idempotency(user_id, message_id)` - Check for duplicates
- `record_idempotency(user_id, message_id, result)` - Record processing

### 3. FSMEngine

Validates and executes state transitions with business logic.

**Key methods:**
- `validate_transition(from_state, to_state, trigger)` - Check if transition is valid
- `transition(context, to_state, trigger, side_effect_fn)` - Execute transition

**Example:**
```python
async def send_notification(context):
    # Side effect function
    print(f"Sending notification to {context.user_id}")

result = await fsm_engine.transition(
    context=context,
    to_state=SessionState.COMPLETED,
    trigger="confirm",
    side_effect_fn=send_notification,
    closure_reason="completed_successfully"
)
```

### 4. IntentRouter

Routes intents with priority-based conflict resolution.

**Priority Levels (P0-P4):**
- **P0**: Critical commands (cancel, stop, help)
- **P1**: Explicit actions (progress_update, upload_photo, create_incident)
- **P2**: Implicit actions (continue_update, add_more_data)
- **P3**: General queries (list_tasks, greetings)
- **P4**: Fallback (unknown)

**Example:**
```python
intent_router = IntentRouter()

# Route single intent
winner, needs_clarification = intent_router.route_intent(
    intent="progress_update",
    confidence=0.85,
    context=context,
    parameters={"task_id": "task_123"}
)

if needs_clarification:
    # Request clarification from user
    pass
elif winner:
    # Process the intent
    print(f"Intent: {winner.intent}, Priority: {winner.priority}")
```

**Conflict resolution:**
```python
# Multiple intents detected
intents = [
    {"intent": "add_comment", "confidence": 0.75, "parameters": {}},
    {"intent": "create_incident", "confidence": 0.72, "parameters": {}}
]

winner, needs_clarification = intent_router.route_multiple_intents(
    intents=intents,
    context=context,
    confidence_threshold=0.70
)
```

### 5. ClarificationManager

Manages clarification requests when intent is ambiguous.

**Example:**
```python
from src.fsm.handlers import clarification_manager

# Create clarification
clarification_id = await clarification_manager.create_clarification(
    user_id="user_123",
    message="Did you mean to add a comment or create an incident?",
    options=["Add comment", "Create incident"],
    context=context
)

# Check for pending clarification
pending = await clarification_manager.get_pending_clarification("user_123")

# Answer clarification
await clarification_manager.answer_clarification(
    clarification_id=clarification_id,
    answer="Add comment"
)
```

### 6. SessionRecoveryManager

Recovers orphaned sessions after crashes or restarts.

**Example:**
```python
from src.fsm.handlers import session_recovery_manager

# Run on server startup
stats = await session_recovery_manager.recover_on_startup()
print(f"Recovered {stats['orphaned_sessions']} orphaned sessions")
print(f"Expired {stats['expired_clarifications']} clarifications")
```

## Transition Rules

The FSM defines 15 transition rules. Here are the key ones:

```python
# From IDLE
IDLE → TASK_SELECTION (trigger: "start_update")
IDLE → ABANDONED (trigger: "explicit_cancel")

# From TASK_SELECTION
TASK_SELECTION → AWAITING_ACTION (trigger: "task_selected")
TASK_SELECTION → ABANDONED (trigger: "cancel")

# From AWAITING_ACTION
AWAITING_ACTION → COLLECTING_DATA (trigger: "start_collection")
AWAITING_ACTION → CONFIRMATION_PENDING (trigger: "request_confirmation")
AWAITING_ACTION → ABANDONED (trigger: "timeout")

# From COLLECTING_DATA
COLLECTING_DATA → COLLECTING_DATA (trigger: "add_data")  # Self-loop
COLLECTING_DATA → CONFIRMATION_PENDING (trigger: "request_confirmation")
COLLECTING_DATA → ABANDONED (trigger: "cancel")

# From CONFIRMATION_PENDING
CONFIRMATION_PENDING → COMPLETED (trigger: "confirm")
CONFIRMATION_PENDING → COLLECTING_DATA (trigger: "continue_editing")
CONFIRMATION_PENDING → ABANDONED (trigger: "cancel")

# Global transitions (from any state)
ANY → ABANDONED (trigger: "force_abandon")
ANY → IDLE (trigger: "reset")
```

## Configuration

Enable FSM in `config.py`:

```python
enable_fsm: bool = True  # Feature flag
```

Adjust timeouts in `handlers.py`:

```python
CLARIFICATION_TIMEOUT = 5 * 60  # 5 minutes
SESSION_RECOVERY_THRESHOLD = 30 * 60  # 30 minutes
```

## Database Tables

The FSM module uses these tables:

1. **progress_update_sessions** (extended)
   - `fsm_state` - Current FSM state
   - `closure_reason` - Why session ended
   - `session_metadata` - Flexible JSONB storage
   - `transition_history` - Audit trail

2. **fsm_idempotency_records**
   - Prevents duplicate message processing
   - Key format: `user_id:message_id`
   - Expires after 24 hours

3. **fsm_clarification_requests**
   - Stores pending clarifications
   - Expires after 5 minutes
   - Status: pending, answered, expired, cancelled

4. **fsm_transition_log**
   - Audit log of all transitions
   - Includes correlation IDs for tracing
   - Keeps 30 days of history

## Logging

The FSM uses structured logging with correlation IDs:

```python
from src.utils.structured_logger import get_structured_logger, set_correlation_id

logger = get_structured_logger("fsm.custom")

# Set correlation ID for request
correlation_id = set_correlation_id()

# Log with structured data
logger.info(
    "Processing user request",
    user_id="user_123",
    session_id="session_456",
    current_state="awaiting_action"
)

# Log transition
logger.log_transition(
    user_id="user_123",
    from_state="idle",
    to_state="task_selection",
    trigger="start_update",
    success=True
)
```

## Testing

Run tests:

```bash
# Unit tests
pytest tests/test_fsm_core.py -v

# Scenario tests
pytest tests/test_scenarios.py -v

# All FSM tests
pytest tests/ -v -k "fsm or scenario"
```

## Common Patterns

### Pattern 1: Check Idempotency

```python
from src.fsm.core import StateManager

state_manager = StateManager()

# Check if message already processed
cached = await state_manager.check_idempotency(user_id, message_id)
if cached:
    return cached  # Return cached result

# Process message...
result = {"status": "processed", "message": "Done"}

# Record for future duplicate checks
await state_manager.record_idempotency(user_id, message_id, result)
```

### Pattern 2: Handle Ambiguous Intent

```python
from src.fsm import IntentRouter
from src.fsm.handlers import clarification_manager

router = IntentRouter()

# Route intent
winner, needs_clarification = router.route_intent(
    intent="progress_update",
    confidence=0.75,
    context=context
)

if needs_clarification:
    # Create clarification request
    await clarification_manager.create_clarification(
        user_id=user_id,
        message="Which task do you want to update?",
        options=["Task A", "Task B"],
        context=context
    )
    return {"message": "Please choose: 1. Task A, 2. Task B"}
else:
    # Process the intent
    pass
```

### Pattern 3: Execute Transition with Side Effects

```python
from src.fsm import FSMEngine, StateManager

state_manager = StateManager()
fsm_engine = FSMEngine(state_manager)

async def notify_completion(context):
    # Send notification
    print(f"Task {context.task_id} completed!")

result = await fsm_engine.transition(
    context=context,
    to_state=SessionState.COMPLETED,
    trigger="confirm",
    side_effect_fn=notify_completion,
    closure_reason="user_confirmed"
)

if result.success:
    print(f"Transition successful: {result.from_state} → {result.to_state}")
    print(f"Side effects executed: {result.side_effects}")
else:
    print(f"Transition failed: {result.error}")
```

## Monitoring

Check FSM health with these queries:

```sql
-- Active sessions
SELECT COUNT(*) FROM progress_update_sessions
WHERE fsm_state NOT IN ('completed', 'abandoned');

-- Abandoned reasons
SELECT closure_reason, COUNT(*)
FROM progress_update_sessions
WHERE fsm_state = 'abandoned'
GROUP BY closure_reason;

-- Clarification effectiveness
SELECT
  COUNT(*) FILTER (WHERE status = 'answered') * 100.0 / COUNT(*) as answer_rate
FROM fsm_clarification_requests;

-- Recent transitions
SELECT from_state, to_state, COUNT(*)
FROM fsm_transition_log
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY from_state, to_state
ORDER BY COUNT(*) DESC;
```

## Error Handling

The FSM handles errors gracefully:

1. **Invalid transitions** - Rejected with error message, state unchanged
2. **Database errors** - Logged, transition fails gracefully
3. **Side effect failures** - Logged but don't fail transition
4. **Idempotency** - Duplicate requests return cached result

## Best Practices

1. **Always check idempotency** for user actions
2. **Use correlation IDs** for request tracing
3. **Handle clarifications** when confidence is low
4. **Log transitions** for debugging
5. **Run cleanup tasks** periodically (every 5 minutes)
6. **Monitor metrics** for stuck sessions
7. **Test transitions** before deploying

## Troubleshooting

### Sessions stuck in non-terminal state
Run session recovery:
```python
from src.fsm.handlers import session_recovery_manager
await session_recovery_manager.recover_orphaned_sessions()
```

### Clarifications not expiring
Run cleanup manually:
```python
from src.fsm.handlers import clarification_manager
await clarification_manager.cleanup_expired_clarifications()
```

### Invalid transitions logged
Check transition rules in `src/fsm/core.py:TRANSITION_RULES`

## Further Reading

- `FSM_IMPLEMENTATION_SUMMARY.md` - Complete implementation details
- `docs/architecture/IMPLEMENTATION_PLAN.md` - Original plan
- Tests in `tests/test_fsm_core.py` and `tests/test_scenarios.py`

---

**Questions?** Check the inline code documentation or review the tests for usage examples.
