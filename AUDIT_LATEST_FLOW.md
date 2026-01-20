# Complete Flow Audit: "je souhaite modifier une autre tache"

**Timestamp**: 2026-01-20 08:23:34 → 08:24:04
**User**: Jean (ed97770c...)
**Message**: "je souhaite modifier une autre tache"
**Expected**: List of projects (when selecting "Changer de chantier")
**Actual**: Asked for task name again (stuck in loop)

---

## Flow 1: Initial Message Processing (08:23:34 → 08:23:42)

### Step 1: Message Arrives (08:23:34)
```
📥 Webhook received from whatsapp:+33652964466
Message: "je souhaite modifier une autre tache"
Session: b55cd64c-800c-4830-9608-876da7d71461
```

### Step 2: Language Detection (08:23:35)
```
🔍 Detecting language: 'je souhaite modifier une autre tache'
🤖 Claude AI detected language: fr
Duration: ~250ms
LLM: Claude Sonnet (language detection)
```

### Step 3: Active Session Check (08:23:35)
```
🔄 Active session found: 13f06000...
   State: awaiting_action | Step: awaiting_action
   Expecting response: True
   Age: 10s
   ✅ Should continue session (recent activity, expecting response)
```

**CRITICAL DECISION**:
- `should_continue_session = True` was set
- This passes FSM hint to intent classifier
- State is `awaiting_action` (idle menu, not active!)

### Step 4: Intent Classification (08:23:36)
```
🤖 Haiku classification: update_progress (confidence: 0.95)
Duration: ~1000ms
LLM: Claude Haiku (intent classification)
```

**LLM Prompt Included FSM Hint**:
```
⚠️⚠️⚠️ CONTEXTE DE SESSION ACTIVE CRITIQUE ⚠️⚠️⚠️

L'utilisateur est EN TRAIN de mettre à jour une tâche (état FSM: awaiting_action)
Le bot vient de lui présenter des options et ATTEND UNE RÉPONSE.
Ce message est TRÈS PROBABLEMENT une réponse à ces options, PAS un nouveau intent!

RÈGLES PRIORITAIRES:
- Dans le DOUTE, TOUJOURS privilégier "update_progress" (continuer la session)
```

**Result**: Intent classified as `update_progress` with 95% confidence

**Problem**: The FSM hint biased the classifier to keep the session instead of recognizing this as a new intent.

### Step 5: Routing (08:23:36)
```
🚀 HIGH CONFIDENCE - Attempting fast path
❌ Fast path returned None (no handler for update_progress)
✅ Routing update_progress to specialized agent
```

### Step 6: Agent Processing (08:23:36 → 08:23:42)
```
Agent: progress_update_agent
Message passed: "je souhaite modifier une autre tache"
LLM: Claude Sonnet 4 (agent reasoning)
Duration: ~6 seconds
```

**Agent calls tool**: `get_active_task_context_tool`

**Tool execution**:
```
📋 list_tasks called: project_id=ngjdlnb (Champigny)
🔵 PLANRADAR API CALL: GET 1484013/projects/ngjdlnb/tickets
📊 Response data: 1 item(s)
📊 Task zzldlpme: status-id=ol, progress=67%
📌 Only 1 task found - showing confirmation instead of list
```

**Tool returns**:
```json
{
  "active_project_id": "...",
  "active_task_id": null,
  "tasks": [{"id": "7aa8d933...", "title": "Task test 1"}],
  "confirmation": {
    "task_id": "7aa8d933-59d6-4ccc-b366-33f4aefc6394",
    "project_id": "ngjdlnb",
    "task_title": "Task test 1"
  },
  "message": "✅ ACTIVE TASK FOUND (CONFIRMATION NEEDED)..."
}
```

**Agent generates response**:
```
D'accord Jean, vous souhaitez changer de tâche. 👍

Que préférez-vous ?
1. Voir les autres tâches du même chantier
2. Changer de chantier
```

**Metadata**:
```
response_type: interactive_list
list_type: option
tool_outputs: [get_active_task_context_tool with confirmation data]
```

### Step 7: Response Sent (08:23:42)
```
📋 Items extracted: ['Voir les autres tâches d', 'Changer de chantier']
🚀 Sending dynamic list picker with 2 items
✅ Sent message: MMd41aac530b7e9ef7ebbd4c66100f1bb6
```

---

## Flow 2: User Selects "Changer de chantier" (08:23:58 → 08:24:04)

### Step 8: User Clicks Option 2 (08:23:58)
```
🔘 Interactive action detected: option_2
User clicked: "Changer de chantier"
```

### Step 9: Interactive Handler (08:23:58)
```
📋 Interactive list selection detected: option_2
🏷️  Parsed list_type: option, option #2
🔍 Searching for tool_outputs in last 10 messages
📦 Found tool_outputs with get_active_task_context_tool
   Found confirmation data: {
     'task_id': '7aa8d933...',
     'project_id': 'ngjdlnb',
     'task_title': 'Task test 1'
   }
```

### Step 10: THE BUG - Misinterpretation (08:23:58)
```
❌ User declined - routing to agent for clarification
```

**Code executed** (message.py:584):
```python
else:  # option_number != "1"
    # User said no - route to agent to ask clarification
    log.info("❌ User declined - routing to agent for clarification")

    return await handle_direct_action(
        action="update_progress",
        user_id=user_id,
        phone_number=phone_number,
        language=language,
        message_body="Non, autre tâche",  # ❌ HARDCODED WRONG!
        session_id=session_id,
    )
```

**Problem**:
- Code doesn't check WHAT option 2 was
- Assumes option 2 always means "different task in same project"
- But user actually selected "Changer de chantier" (different project)
- Sends wrong message to agent: "Non, autre tâche"

### Step 11: Agent Processes Wrong Message (08:23:58 → 08:24:04)
```
Agent receives: "Non, autre tâche"
Agent thinks: User wants different task in Champigny project
LLM: Claude Sonnet 4 (agent reasoning)
Duration: ~6 seconds
```

**Agent calls tool again**: `get_active_task_context_tool`

**Tool execution** (same as before):
```
📋 list_tasks called: project_id=ngjdlnb (Champigny)
📊 Retrieved 1 tasks
📌 Only 1 task found - showing confirmation instead of list
```

**Agent generates response**:
```
D'accord Jean ! Vous voulez voir les autres tâches du même chantier ou changer de chantier ?

1. Autres tâches du chantier
2. Changer de chantier
```

**Result**: User gets SAME OPTIONS AGAIN (infinite loop!)

---

## Summary of Issues

### Issue 1: Session Should Have Been Exited

**When**: 08:23:35
**What happened**:
```
State: awaiting_action (idle menu)
Expecting response: True
Age: 10s
Decision: should_continue_session = True ✅
```

**What should have happened**:
```
State: awaiting_action (idle menu)
Check: Is "awaiting_action" an ACTIVE state? NO
Decision: Exit session, classify as new intent
Result: "list_projects" or "update_progress" without session bias
```

**Root cause**: No whitelist check for FSM states. The code uses `expecting_response=True` which is set for the ENTIRE session lifecycle.

### Issue 2: Wrong LLM Prompt

**When**: 08:23:36
**What happened**: Intent classifier received FSM hint:
```
⚠️⚠️⚠️ CONTEXTE DE SESSION ACTIVE CRITIQUE ⚠️⚠️⚠️
L'utilisateur est EN TRAIN de mettre à jour une tâche
Dans le DOUTE, TOUJOURS privilégier "update_progress"
```

**Impact**:
- Biased classification toward `update_progress`
- Should have detected "list_projects" or recognized new intent
- Message "je souhaite modifier une autre tache" clearly states desire to change task

**Root cause**: `should_continue_session=True` was set based on `expecting_response` alone, without checking FSM state.

### Issue 3: Interactive Handler Doesn't Parse Option Label

**When**: 08:23:58
**What happened**: User clicked option 2 "Changer de chantier"

**Code logic**:
```python
if option_number == "1":
    # Confirmed
else:  # Anything else
    # Assume "different task" ❌
    message_body = "Non, autre tâche"
```

**What should happen**:
```python
if option_number == "1":
    # Confirmed
elif option_number == "2":
    # Check what option 2 actually was
    option_label = "Changer de chantier"

    if "chantier" in option_label or "projet" in option_label:
        # Exit session, show projects
        action = "view_sites"
    else:
        # Different task in same project
        message_body = "Non, autre tâche"
```

**Root cause**: Hardcoded assumption that option 2 always means same thing.

---

## LLMs Used in This Flow

### 1. Language Detection (08:23:35)
- **Model**: Claude Sonnet (via LangChain)
- **Input**: "je souhaite modifier une autre tache"
- **Output**: "fr"
- **Duration**: ~250ms
- **Cost**: ~$0.0001

### 2. Intent Classification (08:23:36)
- **Model**: Claude Haiku
- **Input**: Message + FSM hint + conversation history
- **Output**: `{"intent": "update_progress", "confidence": 0.95}`
- **Duration**: ~1000ms
- **Cost**: ~$0.0001
- **Problem**: FSM hint biased the result

### 3. Agent Reasoning #1 (08:23:36 → 08:23:42)
- **Model**: Claude Sonnet 4
- **Agent**: progress_update_agent
- **Input**: "je souhaite modifier une autre tache"
- **Tools called**: get_active_task_context_tool
- **Output**: "Que préférez-vous ? 1. Voir les autres tâches 2. Changer de chantier"
- **Duration**: ~6 seconds
- **Cost**: ~$0.003

### 4. Agent Reasoning #2 (08:23:58 → 08:24:04)
- **Model**: Claude Sonnet 4
- **Agent**: progress_update_agent
- **Input**: "Non, autre tâche" (WRONG MESSAGE!)
- **Tools called**: get_active_task_context_tool
- **Output**: "Vous voulez voir les autres tâches ou changer de chantier ?" (LOOP!)
- **Duration**: ~6 seconds
- **Cost**: ~$0.003

**Total LLM calls**: 4
**Total duration**: ~13 seconds
**Total cost**: ~$0.0062

---

## Why You Didn't See Project List

### Expected Flow (If Working Correctly):

```
User: "je souhaite modifier une autre tache"
↓
FSM check: State = awaiting_action (idle)
↓
Exit session (not in active state whitelist)
↓
Intent classification: "list_projects" or "update_progress" (without session bias)
↓
If "update_progress" → Agent asks which project
↓
User selects project → Shows tasks in that project
```

### Actual Flow (What Happened):

```
User: "je souhaite modifier une autre tache"
↓
FSM check: expecting_response=True, age=10s
↓
should_continue_session = True ❌
↓
Intent classification WITH FSM bias: "update_progress" (95%)
↓
Agent thinks: User wants different task in CURRENT project (Champigny)
↓
Agent offers: 1. Other tasks 2. Change project
↓
User clicks: "Change project" (option 2)
↓
Code assumes: "Different task in same project" ❌
↓
Sends to agent: "Non, autre tâche"
↓
Agent LOOPS: Asks same question again
```

---

## Root Causes Analysis

### 1. No FSM State Whitelist

**Current code** (message_pipeline.py:635):
```python
# If expecting response and recent activity (< 5 min = 300s)
if ctx.expecting_response and age_seconds < 300:
    ctx.should_continue_session = True
```

**Problem**: `expecting_response=True` for ENTIRE session, including idle states.

**What's needed**:
```python
# Only continue session if in ACTIVE state
ACTIVE_STATES = ["collecting_data"]

if ctx.fsm_state in ACTIVE_STATES and age_seconds < 300:
    ctx.should_continue_session = True
else:
    # Exit idle session
    await exit_session(reason="idle_state_new_intent")
```

### 2. Intent Classifier Gets Wrong Context

**Current code** (intent.py:416):
```python
if should_continue_session and expecting_response:
    fsm_hint = """
    ⚠️⚠️⚠️ CONTEXTE DE SESSION ACTIVE CRITIQUE ⚠️⚠️⚠️
    Dans le DOUTE, TOUJOURS privilégier "update_progress"
    """
```

**Problem**: This hint is added even when session is in IDLE state.

**What's needed**: Don't add FSM hint when session is idle, or exit session before classification.

### 3. Interactive Handler Doesn't Check Option Content

**Current code** (message.py:584):
```python
else:  # option_number == "2"
    # Assume "different task"
    message_body = "Non, autre tâche"
```

**Problem**: Hardcoded assumption about what option 2 means.

**What's needed**:
```python
elif option_number == "2":
    # Parse what option 2 actually was
    # If "chantier" or "projet" → list_projects
    # If "tâche" → different task
```

---

## Recommendations

### Priority 1: Add FSM State Whitelist

Exit sessions when in idle states (`awaiting_action`), only keep sessions alive in active states (`collecting_data`).

### Priority 2: Fix Interactive Handler

Parse option labels or add metadata to know what each option does.

### Priority 3: Remove FSM Hint for Idle States

Don't add the biasing FSM hint when session is in idle state.

---

## Comparison with Earlier Rollback Version

**Note**: We rolled back to commit `aa5018d` (before context classifier was added).

**What was removed**:
- Context classifier (LLM-based IN_CONTEXT vs OUT_OF_CONTEXT detection)
- Issue detection system
- Whitelist-based session exit logic

**What we're left with**:
- FSM states exist but no whitelist check
- `expecting_response` flag used for entire session
- Intent classifier gets FSM hint even in idle states

**The irony**: The context classifier approach had the RIGHT architecture (whitelist check), but we removed it to simplify. Now we need to add back the FSM whitelist logic WITHOUT the expensive context classifier LLM.

---

**End of Audit**
