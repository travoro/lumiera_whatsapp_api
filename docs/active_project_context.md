# Active Project Context Feature

## Overview

The Active Project Context feature automatically remembers which project (chantier) a subcontractor is currently working on, eliminating the need to repeatedly specify the project when performing actions like listing tasks, submitting incidents, or updating progress.

## How It Works

### Automatic Context Management

1. **Setting the Context**: When a user selects a project (e.g., to view tasks), that project becomes their "active project"
2. **Using the Context**: Subsequent project-related actions automatically use the active project if no project is specified
3. **Expiration**: The context expires after 7 hours of inactivity
4. **Manual Override**: Users can explicitly mention a different project to switch context

### 7-Hour Expiration Window

The 7-hour expiration window is designed to match typical work shifts:
- Covers a full working day (6-7 AM to 8 PM)
- Automatically resets overnight or between shifts
- Prevents stale context from previous days

## Database Schema

### Added Columns to `subcontractors` Table

```sql
-- Active project reference
active_project_id UUID REFERENCES projects(id) ON DELETE SET NULL

-- Last activity timestamp for expiration tracking
active_project_last_activity TIMESTAMP WITH TIME ZONE
```

### Helper Functions

The migration provides several database functions:

- `is_active_project_expired(timestamp)` - Check if context has expired
- `get_active_project(subcontractor_id)` - Get active project if not expired
- `set_active_project(subcontractor_id, project_id)` - Set/update active project
- `touch_active_project(subcontractor_id)` - Update activity timestamp
- `clear_active_project(subcontractor_id)` - Clear the context
- `cleanup_expired_active_projects()` - Batch cleanup for maintenance

## Implementation

### Service Layer

**File**: `src/services/project_context.py`

```python
from src.services.project_context import project_context_service

# Get active project
project_id = await project_context_service.get_active_project(user_id)

# Set active project
await project_context_service.set_active_project(
    user_id=user_id,
    project_id=project_id,
    project_name="Chantier Bureau"
)

# Update activity timestamp
await project_context_service.touch_activity(user_id)

# Clear context
await project_context_service.clear_active_project(user_id)
```

### Action Integration

**File**: `src/actions/tasks.py`

The `list_tasks` function now accepts an optional `project_id`:

```python
async def list_tasks(
    user_id: str,
    project_id: Optional[str] = None,  # Optional!
    status: Optional[str] = None
) -> Dict[str, Any]:
```

**Behavior**:
- If `project_id` is provided: Use it directly
- If `project_id` is None: Check active project context
- If no active project: Return message asking user to select project

**Automatic Context Update**:
After successfully retrieving tasks, the function automatically:
- Sets the project as active (if it wasn't already)
- Updates the activity timestamp (if it was already active)

### Tool Layer

**File**: `src/agent/tools.py`

The `list_tasks_tool` parameter is now optional:

```python
@tool
async def list_tasks_tool(
    user_id: str,
    project_id: Optional[str] = None,  # Optional!
    status: Optional[str] = None
) -> str:
```

## User Experience

### Scenario 1: Morning Start

```
User: "Show me my tasks"
Bot: "Which project are you working on today?"
     [Lists projects]

User: "Chantier Bureau"
Bot: [Sets active_project = Chantier Bureau]
     [Shows tasks for Chantier Bureau]

User (1 hour later): "Show tasks"
Bot: [Uses cached active_project]
     [Shows tasks for Chantier Bureau]
```

### Scenario 2: Project Switch

```
User: "I'm working on Chantier Garage now"
Bot: [Updates active_project = Chantier Garage]
     "Got it! You're now working on Chantier Garage."
```

### Scenario 3: Context Expiration

```
User (8 hours later): "Show me tasks"
Bot: [Cache expired, active_project = null]
     "Which project are you currently working on?"
```

### Scenario 4: Explicit Project Override

```
User: "Show me tasks for Chantier Maison"
Bot: [Uses specified project, updates active_project]
     [Shows tasks for Chantier Maison]
```

## Agent Instructions

The agent prompt includes instructions for handling active project context:

```
# 🎯 CONTEXTE DE PROJET ACTIF
Le système mémorise automatiquement le projet sur lequel travaille le sous-traitant:
1. Quand l'utilisateur sélectionne un projet, il devient son "projet actif"
2. Le projet actif reste en mémoire pendant 7 heures d'inactivité
3. Si l'utilisateur demande "mes tâches" SANS préciser le projet:
   - Tu peux appeler list_tasks_tool SANS project_id
   - Le système utilisera automatiquement le projet actif
4. Après 7h sans activité, le contexte expire
```

## Future Extensions

### Other Actions to Support

The same pattern can be applied to:

- `submit_incident_report` - Default to active project
- `get_documents` - Default to active project
- `update_task_progress` - Infer project from task context

### Maintenance Tasks

Periodic cleanup can be scheduled:

```python
# Run daily to clean up expired contexts
await project_context_service.cleanup_expired_contexts()
```

### Analytics

Track usage patterns:
- How often do users switch projects?
- What's the average session length per project?
- How often does the context expire?

## Migration

### Running the Migration

```sql
-- Run in Supabase SQL Editor
\i migrations/add_active_project_context.sql
```

### Rollback

If needed, remove the columns:

```sql
ALTER TABLE subcontractors
  DROP COLUMN IF EXISTS active_project_id,
  DROP COLUMN IF EXISTS active_project_last_activity;

-- Drop functions
DROP FUNCTION IF EXISTS is_active_project_expired(TIMESTAMP WITH TIME ZONE);
DROP FUNCTION IF EXISTS get_active_project(UUID);
DROP FUNCTION IF EXISTS set_active_project(UUID, UUID);
DROP FUNCTION IF EXISTS touch_active_project(UUID);
DROP FUNCTION IF EXISTS clear_active_project(UUID);
DROP FUNCTION IF EXISTS cleanup_expired_active_projects();
```

## Benefits

1. **Better UX**: Subcontractors don't repeat project selection constantly
2. **Fewer Errors**: Less manual project selection = fewer mistakes
3. **Natural Conversation**: "show tasks" instead of "show tasks for project X"
4. **Smart Expiration**: 7-hour window covers a work shift, resets next day
5. **Backward Compatible**: Explicit project_id still works, context is optional

## Edge Cases Handled

1. **Multiple Projects**: User must select which one to make active
2. **Deleted Projects**: ON DELETE SET NULL keeps referential integrity
3. **Expired Context**: Gracefully prompts for re-selection
4. **Explicit Override**: User can always specify a different project
5. **Missing Project**: Returns clear message asking for selection
