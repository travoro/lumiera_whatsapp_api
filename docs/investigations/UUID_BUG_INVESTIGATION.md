# UUID Bug Investigation - 2026-01-14

## Issues Reported

1. **Short ID stored in subcontractor table instead of UUID**
   - `active_task_id` contains `zzldlpme` (short ID) instead of UUID

2. **No photos available message**
   - User gets "Aucune photo disponible" even though photos exist

## Root Cause Analysis

### Issue 1: Short ID Being Used

**Evidence from logs** (2026-01-14 19:57:57):
```
✅ Resolved numeric selection '1' → Task test 1 (UUID: zzldlpme...)
```

- `zzldlpme` is a **SHORT ID** (8 characters), not a UUID
- A real UUID would look like: `7aa8d933-59d6-4ccc-b366-33f4aefc6394`

**Code inspection**:
- `src/actions/tasks.py:82` correctly sets `"id": attributes.get("uuid")`
- PlanRadar API **does return UUID** in `attributes.uuid` (verified with API test)
- BUT: The logs show short ID being used, suggesting `attributes.get("uuid")` returns `None`

### Issue 2: 404 Error on Attachments Endpoint

**Evidence from logs** (2026-01-14 19:57:58):
```
❌ PlanRadar API HTTP error: 404 Not Found
URL: https://www.planradar.com/api/v2/.../tickets/zzldlpme/attachments
```

- Attachments endpoint is receiving short ID (`zzldlpme`)
- PlanRadar attachments API **requires UUID**, not short ID
- This causes 404 → "No attachments found" → "Aucune photo disponible"

**Connection**: Both issues stem from the same root cause - short ID being used instead of UUID.

## Hypothesis

The UUID field in PlanRadar's response might be:
1. Named differently than expected (not "uuid")
2. In a different location (not in `attributes`)
3. Null/empty for some tasks
4. Or there's a data transformation bug somewhere in the flow

## Investigation Steps Taken

### 1. Verified PlanRadar API Response

**Result**: UUID **DOES exist** in the correct location:
```python
{
  "id": "zzldlpme",  # Top-level: short ID
  "type": "tickets",
  "attributes": {
    "uuid": "7aa8d933-59d6-4ccc-b366-33f4aefc6394",  # ✅ UUID here!
    "sequential-id": 1,
    ...
  }
}
```

### 2. Added Debug Logging

**File**: `src/actions/tasks.py:79`
```python
log.info(f"   📊 Task from PlanRadar: short_id={short_id_val}, uuid={uuid_val}, has_uuid={uuid_val is not None}")
```

**File**: `src/utils/metadata_helpers.py:51`
```python
log.info(f"   🗜️ compact_tasks: first task id={compact[0].get('id')}, title={compact[0].get('title')}")
```

### 3. Restarted Server

- Server running with PID: **2667899**
- Health check: ✅ Healthy
- Debug logging: ✅ Enabled (INFO level)

## Next Steps - REQUIRES USER TESTING

**Please test by sending a WhatsApp message:**

1. Send: "list tasks" or "tâches"
2. Select a task by number (e.g., "1")
3. Ask for task details

**Then check logs**:
```bash
tail -50 logs/app.log | grep -E "📊|🗜️|UUID|uuid"
```

**Expected to see**:
```
📊 Task from PlanRadar: short_id=zzldlpme, uuid=7aa8d933-..., has_uuid=True
🗜️ compact_tasks: first task id=7aa8d933-..., title=Task test 1
```

**If UUID is None**, we'll see:
```
📊 Task from PlanRadar: short_id=zzldlpme, uuid=None, has_uuid=False
🗜️ compact_tasks: first task id=None, title=Task test 1
```

## Possible Fixes (Pending Investigation Results)

### If UUID is None from API:
1. Check if PlanRadar changed their API response format
2. Add fallback: fetch UUID via `get_task()` endpoint
3. Update API field mapping

### If UUID is Present but Not Used:
1. Check for data transformation bugs in `compact_tasks()`
2. Verify tool_outputs storage/retrieval
3. Check for caching issues

### If Code is Correct but Old Code Running:
1. Verify server restart picked up new code
2. Check for import caching issues
3. Force reload of modules

## Files Modified for Debugging

1. `src/actions/tasks.py` - Added UUID extraction logging
2. `src/utils/metadata_helpers.py` - Added compact_tasks logging
3. Server restarted to apply changes

## Timeline

- **19:41** - Server started with UUID migration code (commit 713f5f0)
- **19:57:50** - list_tasks called, returned 1 task
- **19:57:57** - Task selection resolved to `zzldlpme` (short ID)
- **19:57:58** - Attachments call failed with 404 (short ID used)
- **20:02** - Debug logging added
- **20:04** - Server restarted with debug logging

## Summary

The code **should** be using UUIDs, and the PlanRadar API **does provide** UUIDs. However, in practice, short IDs are being used. Debug logging has been added to identify where the UUID is being lost in the data flow.

**Next: Test with WhatsApp and check logs to see debug output.**
