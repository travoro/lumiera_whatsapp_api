# FSM Improvements & Variable Renaming - Summary

**Date**: 2026-01-20
**Commit**: Improved FSM logic with state whitelist + renamed session variables for clarity

---

## Changes Made

### 1. Variable Renaming for Clarity (Session Disambiguation)

**Problem**: Code used ambiguous variable names that mixed two different session types:
- Chat session (general conversation, always active)
- Progress update FSM session (short-lived workflow)

**Solution**: Renamed ALL variables to be explicit about which session they refer to.

#### MessageContext Class Changes

**Before**:
```python
session_id: Optional[str] = None  # Which session?
active_session_id: Optional[str] = None  # Which session?
fsm_state: Optional[str] = None
expecting_response: bool = False
should_continue_session: bool = False
```

**After**:
```python
chat_session_id: Optional[str] = None  # Chat session (general conversation)
progress_update_session_id: Optional[str] = None  # FSM session
progress_update_fsm_state: Optional[str] = None  # FSM state
progress_update_expecting_response: bool = False  # FSM flag
should_continue_progress_update_session: bool = False  # FSM decision
```

**Files affected**:
- `src/handlers/message_pipeline.py` (all references updated)

---

### 2. FSM State Whitelist Logic

**Problem**: Session continuation was based on `expecting_response` flag, which is `True` for the ENTIRE session lifecycle (including IDLE states).

**Solution**: Added FSM state whitelist to distinguish IDLE states from ACTIVE states.

#### New Logic

```python
# Define ACTIVE states (user actively working)
ACTIVE_FSM_STATES = [
    "collecting_data",  # User uploading photos/comments
]

# Check if session is in ACTIVE state
if fsm_state in ACTIVE_FSM_STATES:
    # ACTIVE - continue session
    should_continue_progress_update_session = True
else:
    # IDLE - exit session before classification
    await _exit_progress_update_session(
        user_id, session_id,
        reason="idle_state_new_message"
    )
```

#### FSM States Classification

| State | Type | Behavior |
|-------|------|----------|
| `awaiting_action` | IDLE | Exit session on new message |
| `collecting_data` | ACTIVE | Continue session, use FSM context |

**Why this works**:
- IDLE states: User at menu, can send ANY new intent → Exit session, classify without bias
- ACTIVE states: User working on task → Continue session, message likely related to current task

---

### 3. New Method: `_exit_progress_update_session()`

Added dedicated method to exit FSM sessions with proper cleanup and logging.

```python
async def _exit_progress_update_session(
    self, user_id: str, session_id: str, reason: str
) -> None:
    """Exit progress update FSM session with cleanup.

    Logs FSM transition to 'abandoned' state.
    """
    from src.services.progress_update import progress_update_state

    log.info(f"🚪 Exiting progress update FSM session: {session_id[:8]}...")
    log.info(f"   Reason: {reason}")

    await progress_update_state.clear_session(user_id, reason=reason)
```

**Reasons tracked**:
- `idle_state_new_message` - User sent new intent while in idle state
- `session_expired` - Session too old (>5 minutes)

---

### 4. Enhanced Logging

Added comprehensive logging at every decision point:

#### Session Check Logging

```
🔄 Progress update FSM session found: 13f06000...
   FSM State: awaiting_action | Step: awaiting_action
   Expecting response: True
   Age: 10s
   🚪 FSM state 'awaiting_action' is IDLE (not in whitelist ['collecting_data'])
   User can send any new intent - exiting session before classification
   ✅ Session exited - will classify intent without FSM bias
```

#### Intent Classification Logging

```
📊 Calling intent classifier with FSM context:
   Progress update session ID: None
   FSM state: None
   Should continue session: False
```

#### Agent Invocation Logging

```
🤖 Progress Update Agent starting
   User: Jean (ed97770c...)
   Message: je souhaite modifier une autre tache
   Language: fr
   Media: none
   ⚙️ Invoking agent executor...
```

---

### 5. LangSmith Tracing

**Added**:
- `@traceable` decorator to `IntentClassifier.classify()` in `src/services/intent.py`

**Not Added** (Already Works):
- Progress update agent tracing - LangChain agents auto-trace when `LANGCHAIN_TRACING_V2=true`
- No need to add `@traceable` to agent methods (causes duplicate traces)

**Configuration** (already in .env):
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=lumiera-whatsapp-copilot
LANGCHAIN_ENDPOINT=https://eu.api.smith.langchain.com
LANGCHAIN_API_KEY=lsv2_pt_...
```

---

## Impact

### Before

```
User: "je souhaite modifier une autre tache"
Session state: awaiting_action (IDLE)
↓
Decision: expecting_response=True → Continue session ❌
↓
Intent classifier gets FSM bias: "prefer update_progress"
↓
Result: update_progress (95%) - biased ❌
↓
Agent thinks: User wants different task in SAME project ❌
```

### After

```
User: "je souhaite modifier une autre tache"
Session state: awaiting_action (IDLE)
↓
Whitelist check: "awaiting_action" not in ["collecting_data"]
↓
Decision: IDLE state → Exit session ✅
↓
Intent classifier gets NO FSM bias ✅
↓
Result: update_progress - unbiased classification ✅
↓
Agent starts fresh: "Which project? Which task?" ✅
```

---

## Files Modified

1. **src/handlers/message_pipeline.py**
   - Renamed all session variables (session_id → chat_session_id, etc.)
   - Added FSM state whitelist logic in `_check_active_session()`
   - Added `_exit_progress_update_session()` method
   - Enhanced logging throughout

2. **src/services/intent.py**
   - Added `from langsmith import traceable` import
   - Added `@traceable` decorator to `classify()` method

3. **src/services/progress_update/agent.py**
   - Added logging at agent entry point
   - Added media context logging
   - No `@traceable` needed (LangChain handles it)

---

## Testing Needed

### Manual Testing

1. **Test IDLE state exit**:
   - Start progress update
   - User shown menu (awaiting_action)
   - Send new intent: "bonjour" or "je souhaite modifier une autre tache"
   - Expected: Session exited, intent classified without bias

2. **Test ACTIVE state continuation**:
   - Start progress update
   - Upload photo (state → collecting_data)
   - Send message: "terminé mais fuite d'eau"
   - Expected: Session continues, context classifier used (if implemented)

3. **Test LangSmith tracing**:
   - Send message that triggers intent classification
   - Check LangSmith dashboard for "Intent Classification (Haiku)" trace
   - Check for agent execution trace (should appear automatically)

### Verification

```bash
# Check logs for session exit
tail -f logs/app.log | grep "FSM session found"

# Check logs for whitelist decision
tail -f logs/app.log | grep "FSM state.*is IDLE"

# Check logs for intent classification
tail -f logs/app.log | grep "Calling intent classifier"
```

---

## Rollback if Needed

```bash
# Rollback to before these changes
git reset --hard aa5018d
```

---

## Next Steps

1. Monitor logs for session exit behavior
2. Verify LangSmith traces appear for all LLM calls
3. Fix interactive handler for "Autre projet" option (separate issue)
4. Consider adding more ACTIVE states to whitelist as FSM evolves

---

**End of Summary**
