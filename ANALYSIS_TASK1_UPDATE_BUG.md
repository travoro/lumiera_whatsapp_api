# Analysis: Task Update Bug - Session Loss and Confusion

## Timeline of Events

### 1. User Views Tasks (04:19:08)
- User: "voir mes taches"
- System shows list:
  - 1. 🔄 Task test 1 (67%)
  - 2. 🔄 mural

### 2. User Selects Task #2 - "mural" (04:19:20)
- User clicks "tasks_2"
- System resolves: `tasks_2 → mural (ID: b5205811...)`
- Shows task details for "mural"
- ✅ **CORRECT**: User selected mural, system showed mural

### 3. User Requests Update (04:19:39)
- User: "mettre a jour la tache"
- Context: Last message was about "mural" task details
- System finds active task: `b5205811...` (mural)
- Agent shows confirmation: "Do you want to update mural?"
- ✅ **CORRECT**: System correctly identified user wants to update mural

### 4. User Confirms (04:19:55)
- User clicks "option_1" (Yes)
- Confirmation data: `{task_id: b5205811..., project_id: ngjdlnb, task_title: mural}`
- System starts progress update session: `bdb60153-fd87-44ac-9c48-5fadc388be67`
- Shows action menu: "1. 📸 Add photo, 2. 💬 Add comment, 3. ✅ Mark complete"
- ✅ **CORRECT**: Session started for mural task

### 5. User Sends Comment (04:20:48 - **53 seconds later**)
- User: "le mur est fini" (the wall is finished)
- ❌ **BUG #1**: System reports "💤 No active progress update session for user"
- ❌ **BUG #2**: Session `bdb60153...` created at 04:19:55 is LOST in 53 seconds
- System finds active task: `b5205811...` (mural)
- Routes to progress update agent
- ❌ **BUG #3**: Agent shows confusing message:
  > "Je vois que vous vouliez mettre à jour Task test 1, mais le système a gardé mural en mémoire"
  > (I see you wanted to update Task test 1, but the system kept mural in memory)

  **This is false** - user NEVER selected Task test 1, they selected mural

---

## Root Causes Identified

### 🔴 Issue #1: Session Cleared Due to "new_intent_at_idle_state" Logic Error
**Location**: `src/handlers/message_pipeline.py:_classify_intent` (line 795)

**What happened** (04:20:06-04:20:07):
1. Session created at 04:19:55 with state `awaiting_action`
2. System showed menu: "1. Add photo, 2. Add comment, 3. Mark complete"
3. User sent "mettre a jour une autre tache" (update another task) at 04:20:06
4. System found active session (age: 12s, expecting_response: True)
5. **BUG**: Code treats `awaiting_action` as an "idle state":
   ```
   ℹ️ Session in idle state 'awaiting_action' - exiting session and using standard classification
   ```
6. Session cleared: `🧹 Cleared progress update session (reason: new_intent_at_idle_state)`
7. FSM transition: `awaiting_action → abandoned`

**The Logic Error**:
```python
# src/handlers/message_pipeline.py:795
log.info("ℹ️ Session in idle state 'awaiting_action' - exiting session...")
```

**Why this is wrong**:
- `awaiting_action` is NOT an idle state - it's an active state!
- The user is expected to respond with one of:  - Add photo  - Add comment  - Mark complete  - Request different task (exit session)
- The message "mettre a jour une autre tache" IS a valid intent to exit
- **But**: The session should have been cleared BY THE EXIT TOOL, not by this "idle state" check
- **Result**: Session cleared without proper cleanup (active task not cleared)

**Code location**:
```
src/handlers/message_pipeline.py:_classify_intent (line 795)
src/handlers/message_pipeline.py:_exit_specialized_session (line 732)
```

### 🟡 Issue #2: Agent Hallucinates "Task test 1" Request
**Location**: `src/services/progress_update/agent.py:process` (04:20:59)

**Agent output**:
```
"Je vois que vous vouliez mettre à jour Task test 1, mais le système a gardé mural en mémoire"
```

**Reality**:
- User selected task #2 (mural) at 04:19:20
- User confirmed mural at 04:19:55
- User NEVER mentioned or selected "Task test 1"
- All system logs show mural (b5205811...)

**Hypothesis**:
- Agent is looking at conversation history and seeing "Task test 1" from the list shown at 04:19:08
- Agent incorrectly assumes user wanted task #1 because it's first in the list
- Agent ignores the actual selection (tasks_2) and confirmation (mural)

**Check needed**:
- Review agent prompt and conversation history passed to it
- Agent should see:
  1. User selected tasks_2
  2. User confirmed mural
  3. Active task is mural
  4. User is sending comment about mural
- Why is agent confused?

### 🟡 Issue #3: Why Session Check Returns "No Active Session"
**Location**: `src/handlers/message_pipeline.py:_check_active_session` (line 663)

**Log at 04:20:49**:
```
💤 No active progress update session for user
```

**But session exists**:
- Created at 04:19:55: `bdb60153-fd87-44ac-9c48-5fadc388be67`
- State: `awaiting_action`
- Task: `b5205811...` (mural)
- Should still be active

**Possible causes**:
1. Session expired (expiry time < 1 minute?)
2. Session cleared by another process
3. Query checking wrong table/column
4. Session ID not matching

**Code to review**:
```python
# src/handlers/message_pipeline.py:_check_active_session
session = await progress_update_state.get_session(ctx.user_id)
```

---

## Expected Behavior

### Scenario 1: User Wants to Switch Tasks (04:20:06)
When user sends "mettre a jour une autre tache":

1. ✅ System should find active session in `awaiting_action` state
2. ✅ System should route message TO progress update agent (not exit immediately)
3. ✅ Progress update agent should recognize "autre tache" = out of scope
4. ✅ Agent should call `exit_progress_update_session_tool(reason="user_wants_different_task")`
5. ✅ Exit tool should:
   - Clear session with proper FSM transition
   - Clear active task context (b5205811... / mural)
   - Return signal to main LLM
6. ✅ Main LLM should show task list:
   - 1. Task test 1 (67%)
   - 2. mural

**What actually happened**:
- ❌ Pipeline exited session BEFORE routing to agent
- ❌ Active task context NOT cleared
- ❌ Intent classified as "general" (wrong)
- ❌ Fell back to full AI agent
- ❌ Eventually showed task list, but took longer path

### Scenario 2: User Sends Comment (04:20:48)
When user sends "le mur est fini":

1. ✅ System should find NO active session (cleared at 04:20:07)
2. ✅ System should find active task: b5205811... (mural) - **Problem: should have been cleared!**
3. ✅ Intent: update_progress (correct)
4. ✅ Routes to progress update agent
5. ❌ **Bug**: Agent finds active task "mural" instead of "Task test 1"
6. ❌ Agent shows confusing confirmation mixing both tasks

---

## Action Items

### 1. 🔴 CRITICAL: Fix "awaiting_action" Treated as Idle State
**File**: `src/handlers/message_pipeline.py:_classify_intent` (line 795)

**Current code** (WRONG):
```python
log.info("ℹ️ Session in idle state 'awaiting_action' - exiting session and using standard classification")
```

**Problem**: `awaiting_action` is NOT an idle state!

**Solution**: Do NOT exit session based on state name. Instead:
1. Route message to progress update agent
2. Let agent decide if message is in-scope or out-of-scope
3. Agent will call exit tool if needed
4. Exit tool will properly clear session AND active task context

**What to change**:
```python
# REMOVE this logic:
if ctx.fsm_state in ["awaiting_action", "idle"]:
    log.info("Exiting session at idle state")
    await self._exit_specialized_session(...)

# INSTEAD: Always route to agent when session is active
if ctx.active_session_id:
    log.info("Active session found - routing to progress update agent")
    return Result(success=True, data={"intent": "progress_update", ...})
```

### 2. 🟡 Ensure Exit Tool Clears Active Task Context
**File**: `src/services/progress_update/tools.py:exit_progress_update_session_tool`

**Status**: ✅ ALREADY FIXED in commit 35abb78

**Verification needed**:
- [ ] Test that exit tool actually clears active task when reason contains "different_task"
- [ ] Confirm `project_context_service.clear_active_task()` is being called

### 3. 🟢 Improve Session State Documentation
**File**: `src/services/progress_update/state.py`

**Add clear documentation**:
```python
# FSM States:
# - idle: No active session
# - awaiting_action: Session active, waiting for user to choose action
#   (add photo, add comment, mark complete, or request different task)
# - collecting_data: Session active, collecting specific data (e.g., waiting for image upload)
# - abandoned: Session exited by user or system
# - completed: Task marked as complete

# IMPORTANT: "awaiting_action" is an ACTIVE state, not idle!
# Do NOT exit session just because state is "awaiting_action"
```

### 4. 🟢 Add Integration Test
**File**: `tests/integration/test_progress_update_flow.py`

**Test scenario**:
```python
async def test_switch_task_during_progress_update():
    """Test that user can switch tasks during progress update."""
    # 1. User requests to update task
    # 2. System asks for confirmation
    # 3. User confirms task A
    # 4. System starts session for task A
    # 5. User sends "update another task"
    # 6. Agent should exit session and show task list
    # 7. Active task context should be cleared
    # 8. User selects task B
    # 9. System should start session for task B (not task A)
    pass
```

---

## Key Log Excerpts

### Session Creation (04:19:55)
```
✅ Created/updated progress update session bdb60153-fd87-44ac-9c48-5fadc388be67 for user ed97770c...
🔄 FSM: Set expecting_response=True at session creation
📊 FSM Transition logged: idle → awaiting_action (trigger: start_update)
```

### Session Lost (04:20:48 - 53 seconds later)
```
💤 No active progress update session for user
```

### Agent Confusion (04:20:59)
```
Agent output: "Je vois que vous vouliez mettre à jour Task test 1,
              mais le système a gardé mural en mémoire"
```
**FALSE** - User never requested Task test 1
