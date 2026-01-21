# Complete Analysis: Active Task Not Updated When Switching Tasks

## Executive Summary

**Problem**: When a user switches from one task to another during a progress update flow, the active task in the database is not updated. This causes the system to use the wrong task context.

**Impact**: User confusion, comments added to wrong tasks, wrong task confirmed

**Root Cause**: The progress update agent has no tool to set the active task when user selects from a task list

**Status**: Partially fixed in other flows, but missing in progress update agent flow

---

## Complete Flow Analysis

### ✅ WORKING: Task Selection from Direct List (tasks_1_fr, tasks_2_fr)
**File**: `src/handlers/message.py:380-468`

When user clicks a task from the main task list:
1. User clicks "tasks_2_fr" button
2. Handler resolves: tasks_2 → task at index 1
3. ✅ **Sets active task**: `project_context_service.set_active_task(user_id, task_id, task_title)`
4. Routes to appropriate handler

**Code**:
```python:src/handlers/message.py
# Line 453
await project_context_service.set_active_task(
    user_id, task_id, task_title
)
```

**Status**: ✅ Works correctly

---

### ✅ WORKING: Task Details View
**File**: `src/services/handlers/task_handlers.py:652-658`

When user views task details:
1. User requests task details
2. System retrieves task info
3. ✅ **Sets active task**: `project_context_service.set_active_task(user_id, task_id, task_title)`

**Code**:
```python:src/services/handlers/task_handlers.py
# Line 656
await project_context_service.set_active_task(
    user_id, selected_task_id, task_title
)
```

**Status**: ✅ Works correctly

---

### ❌ BROKEN: Option Selection During Progress Update
**File**: `src/handlers/message.py:778-802`

When user selects option (like "Add comment") from confirmation:
1. User clicks "option_2_fr"
2. Handler finds confirmation data
3. ✅ **Sets active task**: `project_context_service.set_active_task(user_id, task_id, task_title)`
4. Defers to progress update agent

**Code**:
```python:src/handlers/message.py
# Line 792 (added in commit 35abb78)
if task_id:
    await project_context_service.set_active_task(
        user_id, task_id, task_title
    )
```

**Status**: ✅ Fixed in commit 35abb78

---

### ❌ BROKEN: Agent Shows Custom Task List
**File**: `src/services/progress_update/agent.py`

**The Critical Missing Flow**:

1. User has active task "mural"
2. User says "update another task"
3. Session cleared (exit tool called)
4. User sent "le mur est fini" as what they thought was a comment
5. System detects no active session, finds active task "mural"
6. Routes to progress update agent
7. Agent checks `get_active_task_context_tool` → finds "mural"
8. Agent notices user message doesn't match, generates custom response:
   ```
   Je vois que vous vouliez mettre à jour Task test 1,
   mais le système a gardé mural en mémoire.
   Vous souhaitez mettre à jour quelle tâche ?

   1. Task test 1
   2. mural
   ```
9. User selects "1" (Task test 1)
10. ❌ **PROBLEM**: Agent has NO TOOL to set active task!
11. Agent proceeds with old active task "mural"

**What's Missing**:
- Agent needs tool: `set_active_task_tool`
- Agent needs to call it before `start_progress_update_session_tool`

---

## Why This Happens

### The Agent's Dilemma

The progress update agent can show a task selection list in two ways:

**Method 1: From `list_tasks_tool`** (handled by main LLM, not progress agent)
- User sees numbered list
- User clicks button with `tasks_N_fr` payload
- Handler resolves and sets active task ✅

**Method 2: Custom list in agent response** (progress update agent)
- Agent generates text: "1. Task A\n2. Task B"
- User selects "1" or types "1"
- Selection comes back to agent
- ❌ Agent has NO tool to update active task!

### Why Method 2 Fails

The progress update agent is specialized and has limited tools:
- ✅ `get_active_task_context_tool` - Check active task
- ✅ `start_progress_update_session_tool` - Start session
- ✅ `add_progress_comment_tool` - Add comment
- ✅ `add_progress_image_tool` - Add image
- ✅ `mark_task_complete_tool` - Mark complete
- ✅ `exit_progress_update_session_tool` - Exit to main LLM
- ❌ **MISSING**: `set_active_task_tool` - Set active task

---

## The Complete Fix

### Step 1: Create `set_active_task_tool`
**File**: `src/services/progress_update/tools.py`
**Location**: Add after `get_active_task_context_tool`

```python
@tool
async def set_active_task_tool(
    user_id: str,
    task_id: str,
    task_title: str
) -> str:
    """Set the active task for a user.

    Call this tool IMMEDIATELY after user selects a task from a list.
    This ensures subsequent operations use the correct task.

    WHEN TO USE:
    - User selects a task number from a list you showed ("1", "2", etc.)
    - User confirms they want to work on a specific task
    - You need to switch the active task context

    Args:
        user_id: User ID
        task_id: Task UUID (e.g., "7aa8d933-59d6-4ccc-b366-33f4aefc6394")
        task_title: Task title for logging (e.g., "Task test 1")

    Returns:
        Confirmation message

    Example:
        User says "1" to select task #1 from your list
        → Call: set_active_task_tool(user_id="...", task_id="7aa8d933...", task_title="Task test 1")
        → Then call: start_progress_update_session_tool(user_id="...", task_id="7aa8d933...", project_id="...")
    """
    try:
        from src.services.project_context import project_context_service

        # Set active task in database (1 hour expiration)
        success = await project_context_service.set_active_task(
            user_id, task_id, task_title
        )

        if success:
            log.info(
                f"✅ Agent set active task: {task_title} (ID: {task_id[:8]}...)",
                user_id=user_id
            )
            return f"✅ Active task updated to: {task_title}"
        else:
            log.error(
                f"❌ Failed to set active task: {task_title}",
                user_id=user_id
            )
            return "❌ Failed to update active task"

    except Exception as e:
        log.error(f"Error in set_active_task_tool: {e}")
        return f"❌ Error updating active task: {str(e)}"
```

### Step 2: Export the Tool
**File**: `src/services/progress_update/tools.py`
**Location**: Top of file, `__all__` list

```python
__all__ = [
    "add_progress_comment_tool",
    "add_progress_image_tool",
    "escalate_to_human_tool",
    "exit_progress_update_session_tool",
    "get_active_task_context_tool",
    "get_progress_update_context_tool",
    "mark_task_complete_tool",
    "set_active_task_tool",  # ← ADD THIS
    "start_progress_update_session_tool",
]
```

### Step 3: Add Tool to Agent
**File**: `src/services/progress_update/agent.py`
**Location**: Import section

```python
from src.services.progress_update.tools import (
    add_progress_comment_tool,
    add_progress_image_tool,
    escalate_to_human_tool,
    exit_progress_update_session_tool,
    get_active_task_context_tool,
    get_progress_update_context_tool,
    mark_task_complete_tool,
    set_active_task_tool,  # ← ADD THIS
    start_progress_update_session_tool,
)
```

### Step 4: Update Agent Prompt
**File**: `src/services/progress_update/agent.py`
**Location**: `PROGRESS_UPDATE_PROMPT` string

**Current tools section**:
```
OUTILS DISPONIBLES :
- get_active_task_context_tool : Vérifier le contexte actif (projet/tâche) - UTILISE CECI EN PREMIER!
- get_progress_update_context_tool : Voir l'état de la session de mise à jour
- start_progress_update_session_tool : Démarrer une session pour une tâche
- add_progress_image_tool : Ajouter une photo
- add_progress_comment_tool : Ajouter un commentaire
- mark_task_complete_tool : Marquer comme terminé
- escalate_to_human_tool : Escalader vers un humain en cas d'erreur ou si l'utilisateur demande
- exit_progress_update_session_tool : Sortir de ta session (hors de ton scope)
```

**Update to**:
```
OUTILS DISPONIBLES :
- get_active_task_context_tool : Vérifier le contexte actif (projet/tâche) - UTILISE CECI EN PREMIER!
- set_active_task_tool : Définir la tâche active après que l'utilisateur sélectionne une tâche ← ADD THIS
- get_progress_update_context_tool : Voir l'état de la session de mise à jour
- start_progress_update_session_tool : Démarrer une session pour une tâche
- add_progress_image_tool : Ajouter une photo
- add_progress_comment_tool : Ajouter un commentaire
- mark_task_complete_tool : Marquer comme terminé
- escalate_to_human_tool : Escalader vers un humain en cas d'erreur ou si l'utilisateur demande
- exit_progress_update_session_tool : Sortir de ta session (hors de ton scope)
```

**Add new section after "RÈGLES IMPORTANTES"**:
```
4. **Sélection de tâche** :
   - Si get_active_task_context_tool retourne une liste de tâches avec IDs
   - ET l'utilisateur sélectionne un numéro (1, 2, etc.)
   - TOUJOURS appeler set_active_task_tool AVANT start_progress_update_session_tool
   - Séquence correcte :
     1. get_active_task_context_tool (obtenir la liste avec IDs)
     2. Utilisateur sélectionne "1"
     3. set_active_task_tool(user_id="{user_id}", task_id="7aa8d933...", task_title="Task test 1")
     4. start_progress_update_session_tool(user_id="{user_id}", task_id="7aa8d933...", project_id="ngjdlnb")
```

### Step 5: Update `get_active_task_context_tool` to Return Task IDs
**File**: `src/services/progress_update/tools.py`
**Location**: `get_active_task_context_tool` function

**Current behavior**: Returns task list without IDs in a way agent can't parse

**Needed**: Return task list WITH IDs that agent can extract

**Update return format when showing task list**:
```python
# Current (problematic):
return f"""Show the user this list:
1. Task test 1
2. mural

Task ID mapping:
Number 1 = ID 7aa8d933-59d6-4ccc-b366-33f4aefc6394
Number 2 = ID b5205811-c0dd-408e-9eec-94550bfe6dbc"""

# Better format for agent to parse:
return f"""✅ TASK LIST (call set_active_task_tool after user selects):

Tasks:
1. Task test 1 [ID: 7aa8d933-59d6-4ccc-b366-33f4aefc6394]
2. mural [ID: b5205811-c0dd-408e-9eec-94550bfe6dbc]

Project ID: ngjdlnb

AGENT INSTRUCTIONS:
When user selects a number (e.g., "1"), do this:
1. Extract task_id for that number (e.g., "7aa8d933-59d6-4ccc-b366-33f4aefc6394")
2. Call: set_active_task_tool(user_id="{user_id}", task_id="<extracted_id>", task_title="<task_title>")
3. Call: start_progress_update_session_tool(user_id="{user_id}", task_id="<same_id>", project_id="ngjdlnb")

Show the user a simple numbered list without IDs."""
```

---

## Testing Checklist

### Test 1: Switch Task During Progress Update
```
1. Start: Active task = "mural"
2. User: "update another task"
3. Agent: Shows list with task IDs in observation
4. User: Selects "1" (Task test 1)
5. ✅ Verify: set_active_task_tool called with task_id for "Task test 1"
6. ✅ Verify: Active task in DB = "Task test 1" (7aa8d933...)
7. ✅ Verify: start_progress_update_session_tool called with same task_id
8. User: "work is done"
9. ✅ Verify: Comment added to "Task test 1", NOT "mural"
```

### Test 2: Agent-Generated Task List
```
1. User says "le mur est fini" (agent thinks this is for Task test 1)
2. Agent finds active task "mural" (wrong)
3. Agent shows custom list asking which task
4. User selects "1" (Task test 1)
5. ✅ Verify: Agent calls set_active_task_tool
6. ✅ Verify: Active task updated
7. ✅ Verify: Session started for correct task
```

### Test 3: No Regression on Existing Flows
```
1. User clicks "tasks_1_fr" from main task list
2. ✅ Verify: Active task set by handler (src/handlers/message.py:453)
3. ✅ Verify: Works as before
```

---

## Migration Notes

### Backward Compatibility
- New tool is additive, doesn't break existing functionality
- Existing `set_active_task` calls in handlers remain unchanged
- Agent gets new capability without affecting other code paths

### Deployment Steps
1. Deploy new tool code
2. Verify tool appears in agent's tool list
3. Test with sample user selections
4. Monitor logs for `set_active_task_tool` calls
5. Confirm active task updates correctly

### Monitoring
Watch for:
- `✅ Agent set active task` log entries
- Active task context changes in database
- Progress update sessions using correct task_id

---

## Summary

**The core issue**: The progress update agent cannot set the active task when user selects from a task list the agent shows.

**The solution**: Add `set_active_task_tool` that agent can call before starting a session.

**Files to modify**:
1. `src/services/progress_update/tools.py` - Add new tool
2. `src/services/progress_update/agent.py` - Import and document tool
3. `src/services/progress_update/tools.py` - Update `get_active_task_context_tool` output format

**Expected outcome**: When user switches tasks during progress update flow, active task is correctly updated and subsequent operations use the right task.
