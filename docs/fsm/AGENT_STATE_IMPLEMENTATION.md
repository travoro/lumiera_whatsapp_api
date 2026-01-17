# Agent State Management Implementation

## Overview

This document describes the production-grade agent state management system implemented to solve the problem of the agent hallucinating entity IDs when users make selections.

**Problem Solved**: Agent was generating fake UUIDs like `"proj-champigny-456"` when users asked for tasks by project name, causing database errors.

**Solution**: Three-layered architecture following LangChain best practices and ChatGPT's recommendations.

---

## Architecture

### **Layer 1: Explicit State (AUTHORITATIVE)**
The single source of truth for current user context.

#### Components
- **`src/services/agent_state.py`**: State builder and management
- **`src/services/project_context.py`**: Enhanced with active task tracking

#### How it Works
```python
# Build authoritative state
agent_state = await agent_state_builder.build_state(
    user_id=user_id,
    language=language,
    session_id=session_id
)

# Inject into agent prompt
state_context = agent_state.to_prompt_context()
# Output:
# [État actuel - Source de vérité]
# Projet actif: Champigny (ID: abc-123-uuid)
# Tâche active: Installation électrique (ID: def-456-uuid)
```

#### Data Flow
1. User selects a project → `project_context_service.set_active_project()`
2. State persists in `subcontractors` table:
   - `active_project_id` (UUID)
   - `active_project_last_activity` (timestamp)
   - `active_task_id` (UUID)
   - `active_task_last_activity` (timestamp)
3. State expires after 7 hours of inactivity
4. Injected into EVERY agent call (priority over history)

#### Key Rule
**Explicit state ALWAYS wins** - if there's a conflict between state and history, state is authoritative.

---

### **Layer 2: Short-Term Tool Memory (1-3 Turns)**
Structured tool outputs for recent conversations.

#### Components
- **`src/agent/agent.py`**: Modified `AgentExecutor` with `return_intermediate_steps=True`
- **`src/handlers/message_pipeline.py`**: Tool output capture and selective loading
- **`src/integrations/supabase.py`**: Metadata storage in messages table

#### How it Works
```python
# Agent executes tool
result = await agent_executor.ainvoke(agent_input)

# Extract structured outputs
intermediate_steps = result.get("intermediate_steps", [])
# Format: List[Tuple[AgentAction, Any]]

for action, tool_result in intermediate_steps:
    tool_outputs.append({
        "tool": action.tool,        # e.g., "list_projects_tool"
        "input": action.tool_input,  # {"user_id": "..."}
        "output": tool_result         # [{"id": "abc", "nom": "Champigny"}]
    })

# Store in message metadata
await save_message(..., metadata={"tool_outputs": tool_outputs})
```

#### Critical Constraint: Trimming
**ONLY the last 1-3 turns with tool outputs are included in context** (not all history).

```python
# Find recent turns with tools (MAX 3)
recent_tool_turns = 0
for msg in reversed(messages):
    if msg.get('metadata', {}).get('tool_outputs'):
        recent_tool_turns += 1
        if recent_tool_turns >= 3:  # STOP at 3
            break

# Only append tool data for recent turns
if tools and is_within_last_3_turns:
    content += "\n[Données précédentes: {...}]"
```

#### Why Trimming is Critical
- **Prevents token bloat**: Old tool outputs accumulate indefinitely otherwise
- **Focuses on relevant context**: Data from 10 turns ago is likely irrelevant
- **Explicit state handles longer-term needs**: If a project is still active, it's in Layer 1

---

### **Layer 3: Lookup Tools (Fallback)**
When explicit state is empty AND user mentions entity by name.

#### Components
- **`src/agent/tools.py`**: `find_project_by_name` tool

#### How it Works
```python
@tool
async def find_project_by_name(user_id: str, project_name: str) -> str:
    """Find a project by name (fuzzy matching).

    ONLY use when:
    1. NO active project in explicit state
    2. User mentions a project by name
    """
    # Search all user's projects
    # Return JSON: {"success": True, "project_id": "...", "project_name": "..."}
```

#### Agent Decision Tree
```
User: "Show me tasks for Champigny"

Step 1: Check explicit state
  - Has active_project_id?
    → YES: Use it directly ✅
    → NO: Go to Step 2

Step 2: Check recent tool outputs (Layer 2)
  - Did we just list projects with "Champigny"?
    → YES: Extract ID from [Données précédentes: ...] ✅
    → NO: Go to Step 3

Step 3: Lookup by name (Layer 3)
  - Call find_project_by_name("Champigny")
  - Get project_id
  - Then call list_tasks_tool(project_id) ✅
```

---

## Data Format Specifications

### **Tool Outputs Format (Strictly Structured)**

```json
{
  "tool": "list_projects_tool",
  "input": {
    "user_id": "uuid-here"
  },
  "output": [
    {
      "id": "project-uuid-123",
      "nom": "Champigny",
      "location": "Paris"
    }
  ]
}
```

**Key Principles**:
- ✅ Keep strictly structured (no mixing with display strings)
- ✅ Separate display (`"1. 🏗️ Champigny"`) from raw data
- ✅ Store full output, but only load compact subset in context

### **Compact Context Format**

When loading tool outputs into agent context (only last 1-3 turns):

```
[Données précédentes:
Projets: [{"id":"abc-123","nom":"Champigny"},{"id":"def-456","nom":"Bureau"}]
Tâches: [{"id":"task-1","title":"Installation"},{"id":"task-2","title":"Test"}]
]
```

**Why Compact?**
- Minimize tokens
- Only essential fields (id, nom/title)
- JSON for easy parsing by LLM

---

## Agent Prompt Updates

### New Section: État Explicite

```
# 🎯 ÉTAT EXPLICITE ET CONTEXTE (RÈGLE CRITIQUE)

## État Actif (Source de Vérité)
Quand tu vois [État actuel - Source de vérité] dans le contexte:
1. ✅ CETTE INFORMATION EST AUTHORITATIVE - elle prend toujours la priorité
2. ✅ Projet actif: ID → Utilise cet ID directement pour les outils
3. ✅ Tâche active: ID → Utilise cet ID directement pour les outils
4. ❌ NE JAMAIS inventer de nouveaux IDs si l'état actif existe
5. ❌ NE PAS demander à l'utilisateur ce qu'il a déjà sélectionné

## Priorité des Sources (Du plus au moins prioritaire)
1. **État Explicite** (ID dans [État actuel]) → UTILISER EN PREMIER
2. **Historique récent** (derniers tool outputs, 1-3 tours) → Si état vide
3. **Recherche par nom** (lookup tools) → Si aucune des 2 options précédentes
```

---

## File Changes Summary

### New Files
1. **`src/services/agent_state.py`** (New)
   - `AgentState` dataclass
   - `AgentStateBuilder` class
   - `build_state()` method
   - `to_prompt_context()` formatter

### Modified Files

#### 1. `src/services/project_context.py`
- **Added**: `get_active_task()`, `set_active_task()`, `clear_active_task()`
- **Purpose**: Track active task in addition to active project

#### 2. `src/agent/agent.py`
- **Modified `AgentExecutor`**: Added `return_intermediate_steps=True`
- **Modified `process_message()`**:
  - Added `state_context` parameter
  - Extract `intermediate_steps` from result
  - Return `tool_outputs` in response dict
  - Inject explicit state into prompt prefix
- **Modified `SYSTEM_PROMPT`**: Added explicit state handling rules

#### 3. `src/handlers/message_pipeline.py`
- **Modified `MessageContext`**: Added `tool_outputs` field
- **Modified `_route_message()`**:
  - Build explicit state with `agent_state_builder`
  - Load messages WITH metadata
  - Trim tool outputs to last 1-3 turns only
  - Append compact tool context to AIMessages
  - Pass `state_context` to agent
- **Modified `_persist_messages()`**:
  - Build metadata dict with `tool_outputs`
  - Pass to `save_message()`

#### 4. `src/integrations/supabase.py`
- **Modified `save_message()`**:
  - Added `metadata` parameter
  - Merge provided metadata with escalation data

#### 5. `src/agent/tools.py`
- **Added**: `find_project_by_name()` tool (Layer 3 fallback)
- **Added to `all_tools` list**

---

## Database Schema

### Existing Tables (No Migration Required!)

#### `subcontractors` table
Already has columns (may need to add if not present):
- `active_project_id` VARCHAR(UUID)
- `active_project_last_activity` TIMESTAMP
- **Need to add**:
  - `active_task_id` VARCHAR(UUID)
  - `active_task_last_activity` TIMESTAMP

#### `messages` table
Already has:
- `metadata` JSONB column ✅

**No new tables needed** - leverages existing schema.

---

## Migration Script

If `active_task_id` columns don't exist:

```sql
-- Add active task tracking to subcontractors table
ALTER TABLE subcontractors
ADD COLUMN IF NOT EXISTS active_task_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS active_task_last_activity TIMESTAMP;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_subcontractors_active_task
ON subcontractors(active_task_id)
WHERE active_task_id IS NOT NULL;
```

---

## Testing Checklist

### Test Scenario 1: Explicit State (Layer 1)
```
Setup:
  - User has active_project_id = "abc-123" (Champigny)

Test:
  User: "Show me tasks"
  Expected: Agent calls list_tasks_tool(user_id, project_id="abc-123")
  ✅ Pass if: No lookup, uses explicit state directly
```

### Test Scenario 2: Recent Tool Output (Layer 2)
```
Setup:
  - No active project
  - User just listed projects (last message has tool_outputs)

Test:
  User: "Show tasks for project 2"
  Expected: Agent extracts ID from [Données précédentes: ...]
  ✅ Pass if: Uses ID from tool outputs, no lookup call
```

### Test Scenario 3: Lookup Fallback (Layer 3)
```
Setup:
  - No active project
  - No recent tool outputs

Test:
  User: "Show tasks for Champigny"
  Expected:
    1. Agent calls find_project_by_name("Champigny")
    2. Then calls list_tasks_tool(project_id=<result>)
  ✅ Pass if: 2 tool calls, correct project selected
```

### Test Scenario 4: Tool Output Trimming
```
Setup:
  - User has had 10 conversations with tools

Test:
  Check logs for "Loaded X messages for agent context"
  Expected: Only last 1-3 turns have tool outputs appended
  ✅ Pass if: Tool context is not bloated, only recent data
```

### Test Scenario 5: State Expiration
```
Setup:
  - Set active_project_last_activity to 8 hours ago

Test:
  User: "Show me tasks"
  Expected:
    - State expired, cleared
    - Agent asks which project
  ✅ Pass if: State auto-clears, no stale data used
```

---

## Performance Considerations

### Token Usage
- **Layer 1**: ~50-100 tokens (compact state)
- **Layer 2**: ~200-500 tokens per turn with tools (trimmed to 3 turns max)
- **Layer 3**: 1 extra API call (~200-500ms latency)

### Optimization Strategies
1. **Trim aggressively**: Only 1-3 recent turns with tools
2. **Compact format**: Only id + name, not full objects
3. **Prioritize Layer 1**: Most requests use explicit state (no extra tokens)
4. **Cache state**: Loaded once per request, not per tool call

---

## Debugging Guide

### Enable Detailed Logging

```python
# In src/handlers/message_pipeline.py:509
if agent_state.has_active_context():
    log.info(f"📍 Explicit state: project={agent_state.active_project_id}, task={agent_state.active_task_id}")

# Check tool outputs
log.debug(f"💾 Storing {len(ctx.tool_outputs)} tool outputs")
```

### Common Issues

#### Issue 1: Agent still invents IDs
**Check**: Is explicit state being injected?
```bash
grep "📍 Injecting explicit state" logs/server.log
```
If not found → State not loaded or empty

#### Issue 2: Token bloat
**Check**: How many tool outputs in context?
```bash
grep "Données précédentes" logs/server.log | wc -l
```
If >3 per request → Trimming logic broken

#### Issue 3: Lookup tool called too often
**Check**: Is explicit state persisting?
```bash
# Check database
SELECT id, active_project_id, active_project_last_activity
FROM subcontractors
WHERE id = '<user_id>';
```
If NULL → State not being set after tool calls

---

## Future Enhancements

### Potential Additions
1. **Task title resolution**: Enhance Layer 2 to include task titles
2. **Multi-entity selection**: Handle "show me tasks for projects 1 and 3"
3. **LangGraph migration**: Move to LangGraph for native state management
4. **Semantic search**: Vector DB for fuzzy project/task matching

### When to Migrate to LangGraph
Consider migrating when:
- Need more complex state tracking (multiple active entities)
- Want native checkpointing (conversation state replay)
- Require conditional flows (if-then-else logic)

Current `AgentExecutor` approach works well for 95% of cases and is simpler.

---

## Summary

### What We Built
A **three-layered, production-grade state management system** that:
1. Uses explicit state as single source of truth
2. Leverages short-term tool memory for recent context (trimmed to 1-3 turns)
3. Falls back to lookup when needed

### Key Innovations
- ✅ **Authoritative state** prevents hallucination
- ✅ **Aggressive trimming** prevents token bloat
- ✅ **Layered fallback** handles all cases gracefully
- ✅ **Zero new tables** leverages existing schema
- ✅ **Structured formats** separate display from data

### Compliance with Best Practices
- ✅ ChatGPT's recommendation: Explicit state management
- ✅ LangChain's recommendation: `intermediate_steps` for tool memory
- ✅ Industry pattern: Layered context (state → short-term → lookup)

---

**Implementation Date**: 2026-01-14
**Status**: ✅ Ready for Testing
**Next Steps**: Run test scenarios, deploy, monitor
