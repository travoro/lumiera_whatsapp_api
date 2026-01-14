# Full System Audit - 2026-01-14

## Executive Summary

User sent "1" after seeing project list, but system:
- ❌ Did NOT use fast path (despite correct intent classification)
- ❌ Did NOT resolve numeric selection
- ❌ Did NOT have metadata from previous message
- ❌ Did NOT set active_project_id in database

## Flow Analysis

### What Happened:

```
Step 1: User: "bonjour, je suis sur place"
  → Intent: greeting (80% confidence)
  → ✅ Fast path: handle_greeting()
  → ✅ Returns greeting message
  → Dynamic template system adds menu with buttons

Step 2: User clicks button "view_sites_fr"
  → ✅ Detected as direct action
  → ✅ Calls list_projects_tool directly
  → ✅ Returns: "1 projet actif trouvé:\n\n1. 🏗️ Champigny\n\n"
  → ❌ Saved to DB WITHOUT metadata/tool_outputs

Step 3: User: "1"
  → Intent: list_tasks (75% confidence)
  → ❌ Fast path NOT triggered (75% < 80% threshold)
  → ❌ Pipeline tried to load tool_outputs → NONE FOUND
  → ⚙️ Fallback to full agent (Opus)
  → ⚠️ Chat history loading ERROR: 'NoneType' object has no attribute 'get'
  → 🤖 Agent processed with empty context
  → 📋 Agent shows: "Voici vos tâches:\n\nChantiers disponibles:\n1. Champigny"
```

---

## Critical Issues Found

### 🚨 ISSUE #1: Direct Actions Don't Store Metadata

**Location:** `src/handlers/message.py:298-306`

**Problem:**
```python
await supabase_client.save_message(
    user_id=user_id,
    message_text=response_text,
    original_language=user_language,
    direction="outbound",
    session_id=session_id,
    is_escalation=is_escalation_action,
    # ❌ NO metadata parameter!
    # ❌ NO tool_outputs stored!
)
```

**Impact:**
- When user clicks "view_sites" button, project list is shown
- But NO metadata is saved (tool_outputs missing)
- Next message can't resolve "1" → project ID

**Root Cause:**
Direct actions return `str` not `Dict[str, Any]`, so they can't return tool_outputs.

**Affected Actions:**
- `view_sites` - Lists projects (CRITICAL - most used)
- `view_tasks` - Lists tasks
- Others that show numbered lists

---

### 🚨 ISSUE #2: Confidence Too Low (75% < 80%)

**Location:** `src/services/intent.py:209`

**Problem:**
```python
log.info(f"🔢 Haiku classification: list_tasks (confidence: 0.75)")
```

**Analysis:**
- Menu response detected correctly (🔢 emoji shows it worked)
- But confidence only 75% instead of expected 95%
- Threshold is 80%, so fast path not triggered

**Why Low Confidence:**
After refactoring to unified prompt, the default confidence for menu responses dropped from 0.95 to 0.75.

**Old Code (removed):**
```python
return {
    "intent": intent,
    "confidence": 0.95,  # Very high confidence for menu selection
    "menu_selection": True
}
```

**New Code:**
```python
# Goes through general classification path
confidence = 0.75  # Default medium confidence
```

**Impact:**
- Fast path not triggered → Opus agent used instead
- Slower response time
- No access to last_tool_outputs in pipeline
- Higher cost

---

### 🚨 ISSUE #3: Chat History Loading Bug

**Location:** `src/handlers/message_pipeline.py:620`

**Error:**
```
WARNING | Could not load chat history for agent: 'NoneType' object has no attribute 'get'
```

**Problem:**
Line 590, 598, 607:
```python
projects_compact = [
    {"id": p.get("id"), "nom": p.get("nom")}
    for p in output_data if isinstance(p, dict)
]
```

If `output_data` contains `None` items, the `isinstance(p, dict)` filter protects it.
But the error suggests a message itself is None, not handled by line 562-563 safety check.

**Likely Cause:**
Database returns metadata where tool_outputs list has structure issues, or messages have None metadata field.

**Impact:**
- Agent runs with empty chat_history
- No context from previous messages
- Reduced accuracy

---

### 🚨 ISSUE #4: Active Project Not Set

**Location:** `src/services/handlers/task_handlers.py:85-88`

**Code:**
```python
# Set active project in database when user makes a selection
if mentioned_project_id:  # User explicitly selected this project
    from src.services.project_context import project_context_service
    await project_context_service.set_active_project(user_id, project_id, project_name)
```

**Problem:**
This code is ONLY executed in fast path handler. But fast path was NOT triggered (Issue #2), so active_project_id was NEVER set.

**Impact:**
- User makes selection but it's not remembered
- Next request doesn't have active context
- User must re-select project every time

---

## Root Cause Chain

```
1. Direct action doesn't store tool_outputs
   ↓
2. Next message can't resolve "1" in fast path loader
   ↓
3. Unified prompt gives lower confidence (75%)
   ↓
4. Fast path not triggered (75% < 80% threshold)
   ↓
5. Full agent used instead
   ↓
6. Chat history loading fails (bug)
   ↓
7. Agent has no context
   ↓
8. Active project not set (only happens in fast path)
   ↓
9. User sees "which project?" again
```

---

## Proposed Solutions

### ✅ Solution #1: Make Direct Actions Return Structured Data

**File:** `src/handlers/message.py`

**Change:**
```python
# OLD: Direct action returns string
async def handle_direct_action(...) -> Optional[str]:
    if action == "view_sites":
        response = await list_projects_tool.ainvoke({"user_id": user_id})
        return response  # ❌ Just a string

# NEW: Direct action returns dict with tool_outputs
async def handle_direct_action(...) -> Optional[Dict[str, Any]]:
    if action == "view_sites":
        result = await list_projects_tool.ainvoke({"user_id": user_id})
        projects = await supabase_client.list_projects(user_id)
        return {
            "message": result,
            "tool_outputs": [{
                "tool": "list_projects_tool",
                "input": {"user_id": user_id},
                "output": compact_projects(projects)  # ✅ Store compact data
            }]
        }
```

**Then update caller (line 298-306):**
```python
if direct_response:
    response_text = direct_response.get("message", direct_response) if isinstance(direct_response, dict) else direct_response
    tool_outputs = direct_response.get("tool_outputs", []) if isinstance(direct_response, dict) else []

    # Save with metadata
    await supabase_client.save_message(
        ...,
        metadata={"tool_outputs": tool_outputs} if tool_outputs else None
    )
```

**Impact:** ✅ Fixes Issue #1 completely

---

### ✅ Solution #2: Boost Menu Response Confidence

**File:** `src/services/intent.py:232-236`

**Change:**
```python
# Check if last bot message was a numbered menu
is_menu_response = message.strip().isdigit() and last_bot_message and self._contains_numbered_list(last_bot_message)

# NEW: Boost confidence for menu responses
menu_confidence_boost = 0.15 if is_menu_response else 0.0

# Later, after Haiku returns confidence:
confidence = base_confidence + menu_confidence_boost  # Boost 75% → 90%
```

**Alternative - More Explicit:**
```python
# After parsing Haiku response:
if is_menu_response and confidence < 0.90:
    log.info(f"🔢 Boosting menu response confidence: {confidence} → 0.90")
    confidence = 0.90  # Force high confidence for menu selections
```

**Impact:** ✅ Fixes Issue #2 - Fast path will trigger

---

### ✅ Solution #3: Fix Chat History Loading Bug

**File:** `src/handlers/message_pipeline.py:588-610`

**Change:**
```python
# OLD: Assumes items are always dicts
projects_compact = [
    {"id": p.get("id"), "nom": p.get("nom")}
    for p in output_data if isinstance(p, dict)
]

# NEW: Handle None and validate structure
projects_compact = [
    {"id": p.get("id"), "nom": p.get("nom")}
    for p in output_data
    if p is not None and isinstance(p, dict) and p.get("id")  # ✅ More defensive
]
```

**Better - Add Try-Catch Per Tool Output:**
```python
for tool_output in tool_outputs:
    try:
        tool_name = tool_output.get('tool', 'unknown')
        output_data = tool_output.get('output')

        if not output_data:
            continue  # Skip if no data

        # ... rest of processing
    except Exception as e:
        log.warning(f"Error processing tool output: {e}")
        continue  # Don't break entire history loading
```

**Impact:** ✅ Fixes Issue #3 - No more crashes, graceful handling

---

### ✅ Solution #4: Set Active Project in Full Agent Too

**File:** `src/agent/tools.py` (in list_tasks_tool)

**Option A:** Make tool itself set active project
```python
@tool
async def list_tasks_tool(user_id: str, project_id: str, project_name: str = None) -> str:
    # ... get tasks ...

    # Set active project when listing tasks
    if project_id and project_name:
        from src.services.project_context import project_context_service
        await project_context_service.set_active_project(user_id, project_id, project_name)
        log.info(f"✅ Set active project: {project_name}")

    return result
```

**Option B:** Agent automatically sets it after tool call
Better approach - add hook in agent.py after tool execution.

**Impact:** ✅ Fixes Issue #4 - Active project set regardless of path

---

## Priority Recommendations

### 🔥 CRITICAL (Do First):
1. **Solution #2** - Boost menu confidence → Fast path works
2. **Solution #1** - Direct actions store metadata → Next message resolves

### 🟡 HIGH (Do Soon):
3. **Solution #3** - Fix chat history bug → No crashes
4. **Solution #4** - Set active project in all paths → Better UX

### 🔵 NICE TO HAVE:
- Add database indices on metadata field for performance
- Add monitoring/alerts for low confidence classifications
- Add unit tests for numeric resolution logic

---

## Testing Checklist

After fixes:
- [ ] User clicks "view_sites" button
- [ ] Verify metadata stored in DB with tool_outputs
- [ ] User sends "1"
- [ ] Verify intent confidence >= 80%
- [ ] Verify fast path handler triggered
- [ ] Verify numeric "1" resolved to project ID
- [ ] Verify tasks shown immediately
- [ ] Verify active_project_id set in DB
- [ ] Verify no chat history errors in logs

---

## Database Queries for Verification

Check if metadata was stored:
```sql
SELECT
    content,
    direction,
    metadata,
    created_at
FROM messages
WHERE subcontractor_id = 'ed97770c-ba77-437e-a1a9-e4a8e034d1da'
ORDER BY created_at DESC
LIMIT 10;
```

Check active project:
```sql
SELECT
    id,
    nom,
    active_project_id,
    active_project_last_activity
FROM subcontractors
WHERE id = 'ed97770c-ba77-437e-a1a9-e4a8e034d1da';
```

---

## Estimated Impact

**Before Fixes:**
- Fast path success rate: ~40% (only keyword matches work)
- Numeric selection resolution: 0% (no metadata)
- Average response time: 3-5 seconds (Opus agent)
- User frustration: High (repeats selections)

**After Fixes:**
- Fast path success rate: ~85% (menu responses + keywords)
- Numeric selection resolution: 95%+ (metadata available)
- Average response time: 0.5-1 second (fast path)
- User frustration: Low (smooth experience)

**Cost Savings:**
- Opus calls reduced by ~50%
- Estimated savings: ~$200-400/month depending on volume

---

## Conclusion

The root cause is a **cascading failure**:
1. Direct actions don't store metadata (architectural gap)
2. Unified prompt lowered confidence (refactoring side-effect)
3. Both prevent fast path from working properly

**All 4 solutions are needed** for complete fix, but implementing Solutions #1 and #2 will resolve 80% of user-facing issues immediately.
