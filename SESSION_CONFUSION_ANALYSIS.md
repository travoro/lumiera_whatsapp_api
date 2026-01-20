# Session Confusion & Tracing Issues - Complete Analysis

**Date**: 2026-01-20
**Critical Discovery**: We have TWO different types of sessions, and they're being confused

---

## The Two Sessions

### Session 1: Chat Session (General Conversation)

**Table**: `sessions`
**ID in your case**: `b55cd64c-800c-4830-9608-876da7d71461`
**Field in code**: `ctx.session_id`

**Purpose**:
- Track the general conversation between user and bot
- Store ALL messages (inbound + outbound)
- Persist conversation history
- Used for loading recent messages for context

**Lifecycle**:
- Created: When user first sends a message
- Persists: For the entire conversation (hours/days)
- Never exits: Always active for the user

**Log**:
```
Session b55cd64c-800c-4830-9608-876da7d71461 active for user ed97770c...
```

---

### Session 2: Progress Update Session (FSM Workflow)

**Table**: `progress_update_sessions`
**ID in your case**: `13f06000...`
**Field in code**: `ctx.active_session_id`

**Purpose**:
- FSM (Finite State Machine) for multi-step progress update flow
- Track which task user is updating
- Track FSM state (awaiting_action, collecting_data, etc.)
- Track what user has done (photos uploaded, comments added)

**Lifecycle**:
- Created: When user starts updating a task
- Active: While user is working on the update
- Exits: When update is complete OR user abandons it
- Short-lived: Minutes, not hours

**FSM States**:
- `idle` - No session exists
- `awaiting_action` - Session created, user shown menu (IDLE!)
- `collecting_data` - User actively uploading photos/comments (ACTIVE!)
- `completed` - User finished
- `abandoned` - User left or session expired

**Log**:
```
🔄 Active session found: 13f06000...
   State: awaiting_action | Step: awaiting_action
   Expecting response: True
   Age: 10s
```

---

## The Critical Confusion

### What `should_continue_session` Means

**Code location**: `message_pipeline.py:69, 636`

```python
# MessageContext field
should_continue_session: bool = False

# Decision logic (line 634-640)
# If expecting response and recent activity (< 5 min = 300s)
if ctx.expecting_response and age_seconds < 300:
    ctx.should_continue_session = True
    log.info("✅ Should continue session (recent activity, expecting response)")
```

**What it refers to**: The **PROGRESS UPDATE SESSION** (FSM session), NOT the chat session!

**What it controls**: Whether to tell the intent classifier "user is in middle of progress update flow, bias toward continuing"

---

## The Problem Explained

### Your Case (08:23:35)

**State of the world**:
```
Chat session: b55cd64c... (always active)
Progress update session: 13f06000...
  ├─ State: awaiting_action (IDLE MENU!)
  ├─ expecting_response: True
  ├─ Age: 10 seconds
  └─ Task: Task test 1 (Champigny)
```

**You sent**: "je souhaite modifier une autre tache"

**Decision made** (line 635-636):
```python
if ctx.expecting_response and age_seconds < 300:  # True and 10 < 300
    ctx.should_continue_session = True  # ✅ Set to True
```

**Result**:
- `should_continue_session = True` was set
- This flag was passed to intent classifier
- Intent classifier got biased prompt: "User in active session, prefer update_progress"

---

## Why This is WRONG

### The FSM State Matters!

**`awaiting_action` is an IDLE state**, not an active state:

| State | Type | User Activity | expecting_response | should_continue? |
|-------|------|--------------|-------------------|------------------|
| `awaiting_action` | IDLE | Staring at menu, deciding | True | **NO! (False)** |
| `collecting_data` | ACTIVE | Uploading photos, adding comments | True | **YES! (True)** |

**Why `awaiting_action` is IDLE**:
- User was just shown a menu
- User is **deciding** what to do next
- User can:
  - Select a menu option (upload photo, add comment)
  - Send a **completely new intent** ("bonjour", "liste mes projets")
  - Abandon the flow entirely

**Why `collecting_data` is ACTIVE**:
- User **just took action** (uploaded photo, sent comment)
- User is **in the middle** of working
- Next message is **highly likely** related to current task
- Example: "terminé mais fuite d'eau" (finished but there's a leak)

---

## The Correct Logic

### Current (Broken)

```python
# Line 634-640
if ctx.expecting_response and age_seconds < 300:
    ctx.should_continue_session = True
```

**Problem**:
- `expecting_response=True` for ENTIRE session lifecycle
- Doesn't distinguish IDLE states from ACTIVE states
- Biases intent classification even when user is just looking at a menu

### What It Should Be

```python
# Define which states are ACTIVE (user is working)
ACTIVE_FSM_STATES = [
    "collecting_data",  # User uploading/commenting
]

# Only continue session if in ACTIVE state
if ctx.fsm_state in ACTIVE_FSM_STATES and age_seconds < 300:
    ctx.should_continue_session = True
else:
    # IDLE state or too old → Don't bias classification
    ctx.should_continue_session = False
```

**OR even better - exit the session entirely**:

```python
# Define which states are ACTIVE
ACTIVE_FSM_STATES = ["collecting_data"]

if ctx.fsm_state not in ACTIVE_FSM_STATES:
    # Session is IDLE - exit it before classification
    log.info(f"Session in idle state '{ctx.fsm_state}' - exiting before classification")

    await clear_progress_update_session(
        user_id=ctx.user_id,
        reason="idle_state_new_message"
    )

    # Now classify without session bias
    ctx.should_continue_session = False
    ctx.active_session_id = None
    ctx.fsm_state = None
```

---

## Your Specific Case - Step by Step

### What Happened

```
08:23:35 - Check for progress update session
├─ Found session: 13f06000...
├─ State: awaiting_action (IDLE!)
├─ expecting_response: True
├─ Age: 10s
├─ Decision: expecting_response=True AND age=10s < 300s
└─ Result: should_continue_session = True ❌ WRONG!

08:23:36 - Intent classification
├─ should_continue_session = True
├─ Adds FSM hint to prompt:
│  "⚠️ USER IN ACTIVE SESSION - prefer update_progress"
├─ Claude Haiku classifies: update_progress (95%)
└─ User's new intent was ignored ❌

08:23:36 - Route to agent
├─ Intent: update_progress
└─ Agent thinks: User wants different task in current project ❌
```

### What Should Have Happened

```
08:23:35 - Check for progress update session
├─ Found session: 13f06000...
├─ State: awaiting_action (IDLE!)
├─ Check: Is "awaiting_action" in ACTIVE_STATES ["collecting_data"]?
├─ Answer: NO
├─ Decision: Exit session (idle state, user sent new message)
└─ Result:
   ├─ Session cleared (reason: "idle_state_new_message")
   ├─ should_continue_session = False
   └─ active_session_id = None

08:23:36 - Intent classification
├─ should_continue_session = False
├─ NO FSM hint in prompt ✅
├─ Claude Haiku classifies: Probably "update_progress" still, OR maybe "list_projects"
└─ But WITHOUT session bias

08:23:36 - Route to agent
├─ Intent: update_progress (or list_projects)
├─ NO active session exists
└─ Agent starts fresh: "Which project? Which task?" ✅
```

---

## The `expecting_response` Flag - Why It's Misleading

### How It's Set

**At session creation** (`state.py:145`):
```python
await self.update_session(
    user_id=user_id,
    fsm_state="awaiting_action",
    session_metadata={
        "expecting_response": True,  # Set immediately
        "last_bot_action": "session_started",
        "available_actions": ["add_comment", "add_photo", "mark_complete"],
    },
)
```

**After user uploads photo** (`state.py:291`):
```python
session_metadata["expecting_response"] = True  # STILL True!
session_metadata["last_bot_action"] = "added_image"
```

**The problem**: `expecting_response` is **ALWAYS True** during the entire session:
- Session created → `True`
- User shown menu → `True`
- User uploads photo → `True`
- Bot shows options → `True`
- Session ends → Cleared

It doesn't distinguish between:
- "Bot showed menu, user can do anything" (IDLE)
- "Bot just processed user's photo, waiting for next action" (ACTIVE)

---

## Summary: Why `should_continue_session` Should Be False

### Question: "Why should it be False?"

**Answer**: Because the session is in an **IDLE state** (`awaiting_action`), not an ACTIVE state.

### The Rule:

```
IDLE states (user at menu, deciding what to do):
├─ should_continue_session = False
├─ Don't bias intent classification
└─ OR: Exit session entirely, let user start fresh

ACTIVE states (user actively working on task):
├─ should_continue_session = True
├─ Bias toward continuing current flow
└─ Context matters (message likely related to current task)
```

### In Your Case:

```
State: awaiting_action (IDLE)
User message: "je souhaite modifier une autre tache"
Decision: should_continue_session = False

Why: User is clearly stating a NEW intent, not responding to menu
Result: Classify without bias, recognize "different task" request
```

---

## The LangSmith Tracing Issue

### What You Observed

"In LangSmith I only have the language detection in the last 30 minutes"

### Why This Happens

**Files checked**:
- ✅ `transcription.py` - Has `@traceable` decorator
- ❌ `intent.py` - NO `@traceable` decorator
- ❌ `progress_update/agent.py` - NO `@traceable` decorator

**Result**: Only language detection shows up in LangSmith, because only that code path has tracing!

### Missing Traces

**Intent classification** (`intent.py:295`):
```python
async def classify(self, ...):
    """Classify intent with Claude Haiku."""
    # NO @traceable decorator!

    response = await self.llm.ainvoke(prompt)
    # This LLM call is NOT traced in LangSmith ❌
```

**Agent reasoning** (`progress_update/agent.py:178`):
```python
async def process(self, ...):
    """Process progress update request."""
    # NO @traceable decorator!

    result = await self.agent_executor.ainvoke({...})
    # This LLM call is NOT traced in LangSmith ❌
```

### What Needs To Be Added

**1. Intent classifier** (`intent.py`):
```python
from langsmith import traceable  # Import

@traceable(name="Intent Classification (Haiku)")  # Add decorator
async def classify(self, ...):
    # ... existing code
```

**2. Progress update agent** (`progress_update/agent.py`):
```python
from langsmith import traceable  # Import

@traceable(name="Progress Update Agent (Sonnet 4)")  # Add decorator
async def process(self, ...):
    # ... existing code
```

**3. Language detection** (probably already has it):
```python
# Already working - this is why you see it in LangSmith
@traceable(name="Language Detection")
async def detect_with_claude(self, ...):
    # ... existing code
```

---

## Complete Flow With Session Context

### Your Message Flow (Actual)

```
USER: "je souhaite modifier une autre tache"
│
├─ Chat Session: b55cd64c... (always exists)
│  └─ Purpose: Store messages, conversation history
│
├─ Progress Update Session: 13f06000... (FSM session)
│  ├─ State: awaiting_action (IDLE)
│  ├─ expecting_response: True
│  ├─ Task: Task test 1 (Champigny)
│  └─ Age: 10 seconds
│
├─ Decision (Line 635):
│  ├─ expecting_response=True AND age=10s < 300s → TRUE
│  └─ should_continue_session = True ❌
│
├─ Intent Classification:
│  ├─ Receives FSM hint (biased prompt) ❌
│  ├─ Result: update_progress (95%)
│  └─ LangSmith: NOT TRACED ❌
│
├─ Route to Agent:
│  ├─ Agent: progress_update_agent
│  ├─ Message: "je souhaite modifier une autre tache"
│  ├─ Session: 13f06000... (still active)
│  └─ LangSmith: NOT TRACED ❌
│
└─ Agent Response:
   ├─ Calls: get_active_task_context_tool (project=Champigny)
   ├─ Thinks: User wants different task in SAME project
   └─ Shows: "1. Other tasks 2. Change project"
```

### What Should Happen (Fixed)

```
USER: "je souhaite modifier une autre tache"
│
├─ Chat Session: b55cd64c... (always exists)
│  └─ Purpose: Store messages, conversation history
│
├─ Progress Update Session: 13f06000... (FSM session)
│  ├─ State: awaiting_action (IDLE) 👈 CHECK THIS!
│  ├─ Check: Is "awaiting_action" in ["collecting_data"]? NO
│  └─ Action: EXIT SESSION ✅
│     ├─ Clear from database
│     ├─ Log transition: awaiting_action → abandoned
│     └─ Reason: "idle_state_new_message"
│
├─ Decision:
│  ├─ No active session anymore
│  └─ should_continue_session = False ✅
│
├─ Intent Classification:
│  ├─ NO FSM hint (unbiased) ✅
│  ├─ Result: update_progress (or list_projects)
│  └─ LangSmith: TRACED ✅ (after adding @traceable)
│
├─ Route to Agent:
│  ├─ Agent: progress_update_agent
│  ├─ Message: "je souhaite modifier une autre tache"
│  ├─ Session: NONE (fresh start)
│  └─ LangSmith: TRACED ✅ (after adding @traceable)
│
└─ Agent Response:
   ├─ Calls: get_active_task_context_tool (no project context)
   ├─ Asks: "Which project do you want to work on?"
   └─ Shows: List of ALL projects ✅
```

---

## Recommendations

### 1. Fix Session Exit Logic (High Priority)

Add FSM state whitelist to exit IDLE sessions:

```python
# message_pipeline.py:634
ACTIVE_FSM_STATES = ["collecting_data"]

if ctx.fsm_state not in ACTIVE_FSM_STATES:
    # IDLE state - exit session before classification
    await clear_progress_update_session(
        user_id=ctx.user_id,
        reason="idle_state_new_message"
    )
    ctx.should_continue_session = False
    ctx.active_session_id = None
elif age_seconds < 300:
    # ACTIVE state and recent - continue session
    ctx.should_continue_session = True
else:
    # Too old - don't continue
    ctx.should_continue_session = False
```

### 2. Add LangSmith Tracing (High Priority)

**Why**: You can't debug what you can't see!

Add `@traceable` to:
- `intent.py:classify()` - Intent classification
- `progress_update/agent.py:process()` - Agent reasoning

### 3. Fix Interactive Handler (Medium Priority)

Parse option labels instead of assuming what option 2 means.

### 4. Document Session Types (Low Priority)

Add clear comments/docs explaining the two session types to prevent future confusion.

---

## Conclusion

**The session confusion**:
- `should_continue_session` refers to the **PROGRESS UPDATE SESSION** (FSM), not chat session
- It should be `False` when session is in IDLE state (`awaiting_action`)
- It should be `True` ONLY when session is in ACTIVE state (`collecting_data`)

**The current bug**:
- Uses `expecting_response` flag (always True) instead of checking FSM state
- Doesn't distinguish IDLE from ACTIVE
- Biases intent classification even when user is just looking at a menu

**The fix**:
- Check FSM state against whitelist
- Exit session if in IDLE state
- Only set `should_continue_session=True` for ACTIVE states

**The LangSmith issue**:
- Missing `@traceable` decorators on intent classifier and agent
- Only language detection is traced
- Can't see the LLM reasoning that's causing the bugs

---

**End of Analysis**
