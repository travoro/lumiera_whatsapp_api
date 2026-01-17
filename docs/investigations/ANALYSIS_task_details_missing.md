# Analysis: Task Details Not Loading (Description & Images Missing)

**Date:** 2026-01-14
**Issue:** Task descriptions and images are not retrieved from PlanRadar API

---

## The Problem

When users select a task to view details, they receive only:
```
📋 Détails de la tâche : Task test 1
```

Missing:
- ❌ Task description
- ❌ Task images/photos
- ❌ Status, due date, assignee

---

## Root Cause: Incorrect API URL

**Location:** `src/integrations/planradar.py:86`

```python
async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific task."""
    result = await self._request("GET", f"tickets/{task_id}")  # ❌ WRONG
    return result.get("data") if result else None
```

**Error in logs:**
```
ERROR | PlanRadar API HTTP error: Client error '404 Not Found'
for url 'https://www.planradar.com/api/v2/tickets/zzldlpme'
```

**The Problem:**
- Current URL: `https://www.planradar.com/api/v2/tickets/zzldlpme` ❌
- Correct URL: `https://www.planradar.com/api/v2/1484013/tickets/zzldlpme` ✅

Missing `account_id` (1484013) in the path!

---

## Why This Happens

### Correct Pattern (list_tasks)

**Location:** `src/integrations/planradar.py:72`

```python
async def list_tasks(self, project_id: str, status: Optional[str] = None):
    endpoint = f"{self.account_id}/projects/{project_id}/tickets"  # ✅ Has account_id
    result = await self._request("GET", endpoint, params=params)
```

**URL:** `https://www.planradar.com/api/v2/1484013/projects/ngjdlnb/tickets` ✅

### Broken Pattern (get_task)

```python
async def get_task(self, task_id: str):
    result = await self._request("GET", f"tickets/{task_id}")  # ❌ No account_id
```

**URL:** `https://www.planradar.com/api/v2/tickets/zzldlpme` ❌

---

## Affected Methods

All these methods in `planradar.py` have the same issue:

1. **get_task** (line 86)
   ```python
   f"tickets/{task_id}"  # ❌ Should be: f"{self.account_id}/tickets/{task_id}"
   ```

2. **get_task_description** (line 91)
   - Calls `get_task` internally, so inherits the bug

3. **get_task_plans** (line 96)
   ```python
   f"tickets/{task_id}/plans"  # ❌ Should be: f"{self.account_id}/tickets/{task_id}/plans"
   ```

4. **get_task_images** (line 101)
   ```python
   f"tickets/{task_id}/attachments"  # ❌ Should be: f"{self.account_id}/tickets/{task_id}/attachments"
   ```

5. **get_task_comments** (line 151)
   ```python
   f"tickets/{task_id}/comments"  # ❌ Should be: f"{self.account_id}/tickets/{task_id}/comments"
   ```

---

## Impact

### Current Behavior:
```
User: Click "🔄 Task test 1"
System: Resolves task ID: "zzldlpme" ✓
System: Calls PlanRadar API: /tickets/zzldlpme ✗
PlanRadar: 404 Not Found ✗
System: Returns only title, no description/images ✗
User: Sees "📋 Détails de la tâche : Task test 1" (incomplete)
```

### Expected Behavior:
```
User: Click "🔄 Task test 1"
System: Resolves task ID: "zzldlpme" ✓
System: Calls PlanRadar API: /1484013/tickets/zzldlpme ✓
PlanRadar: Returns full task data ✓
System: Displays description + photos carousel ✓
User: Sees complete task details with images
```

---

## The Fix

### Fix All Affected Methods

**File:** `src/integrations/planradar.py`

**1. Fix get_task (line 86):**
```python
# OLD
result = await self._request("GET", f"tickets/{task_id}")

# NEW
result = await self._request("GET", f"{self.account_id}/tickets/{task_id}")
```

**2. Fix get_task_plans (line 96):**
```python
# OLD
result = await self._request("GET", f"tickets/{task_id}/plans")

# NEW
result = await self._request("GET", f"{self.account_id}/tickets/{task_id}/plans")
```

**3. Fix get_task_images (line 101):**
```python
# OLD
result = await self._request("GET", f"tickets/{task_id}/attachments")

# NEW
result = await self._request("GET", f"{self.account_id}/tickets/{task_id}/attachments")
```

**4. Fix get_task_comments (line 151):**
```python
# OLD
result = await self._request("GET", f"tickets/{task_id}/comments")

# NEW
result = await self._request("GET", f"{self.account_id}/tickets/{task_id}/comments")
```

---

## Why This Wasn't Caught Earlier

1. **list_tasks works** - Uses correct URL format with account_id
2. **Task IDs are correct** - System correctly resolves "zzldlpme" from button clicks
3. **Graceful degradation** - System returns task title even when API fails
4. **No loud errors** - Just logged as errors, doesn't crash

Result: Users see "some" information (just the title), so bug was subtle.

---

## Testing After Fix

### Test 1: Button Click Flow
```
1. Send "bonjour"
2. Click "view_tasks"
3. Click task "🔄 Task test 1"
```

**Expected:**
```
📋 Détails de la tâche : Task test 1

📄 Description:
[Full task description from PlanRadar]

📸 Images:
[Carousel with task photos if available]
```

**Verify logs:**
```
✅ GET /1484013/tickets/zzldlpme → 200 OK
✅ GET /1484013/tickets/zzldlpme/attachments → 200 OK
✅ Task description retrieved
✅ X images found
```

### Test 2: Natural Language
```
User: "show me details of task 1"
```

**Expected:** Same rich response with description + images

---

## Related Issues

### None! This is an isolated bug.

The rest of the task system works correctly:
- ✅ Task listing works (correct URL)
- ✅ Task ID resolution works (correct IDs)
- ✅ Task context tracking works
- ✅ Task handlers work (just missing API data)

Only the PlanRadar client methods for individual task details are broken.

---

## Summary

**Issue:** PlanRadar API endpoints for individual tasks are missing `account_id` in URL path

**Fix:** Add `{self.account_id}/` prefix to all ticket detail endpoints

**Impact:** Task details will show full descriptions and photos instead of just titles

**Risk:** Very low - simple URL fix, existing code already uses account_id for list_tasks

**Files Changed:** 1 file (`src/integrations/planradar.py`), 5 methods

---

## Next Steps

1. Apply the fix (4 URL changes)
2. Test with existing task "zzldlpme" (Task test 1)
3. Verify description and images load
4. Commit with message: "Fix: Add account_id to PlanRadar task detail endpoints"
