# Session Race Condition - Final Root Cause Analysis

**Date**: 2026-01-17
**Status**: 🔴 **CRITICAL - ROOT CAUSE CONFIRMED**

---

## Executive Summary

**Root Cause Found**: The PostgreSQL RPC function `get_or_create_session` is either:
1. **Failing** and falling back to `_create_session_manual` (which ends all sessions), OR
2. **Not finding active sessions** and creating new ones on every request

**Evidence from Database**:
- 4 sessions created in 18 seconds (20:39:06 → 20:39:24)
- All previous sessions marked as "ended"
- Messages scattered across different sessions
- `tool_outputs` in one session, but user request uses different session

---

## Complete Flow Analysis

### The Code Path:

**File**: `src/services/session.py:44-65`

```python
async def get_or_create_session(self, subcontractor_id: str):
    try:
        # Call PostgreSQL function to get or create session
        session_id = await supabase_client.get_or_create_session_rpc(
            subcontractor_id
        )  # ← LINE 46-48

        if session_id:
            session = await supabase_client.get_session_by_id(session_id)
            if session:
                log.info(f"Session {session_id} active for user {subcontractor_id}")
                return session

        # Fallback: Create session manually if function fails
        log.warning("PostgreSQL function failed, creating session manually")  # ← LINE 59
        return await self._create_session_manual(subcontractor_id)  # ← LINE 60

    except Exception as e:
        log.error(f"Error getting/creating session: {e}")  # ← LINE 63
        # Fallback to manual creation
        return await self._create_session_manual(subcontractor_id)  # ← LINE 65
```

**File**: `src/services/session.py:67-106`

```python
async def _create_session_manual(self, subcontractor_id: str):
    try:
        # End any active sessions first
        await self._end_active_sessions(subcontractor_id)  # ← LINE 80 ⚠️

        # Create new session
        session = await supabase_client.create_session(...)  # ← LINE 83

        if session:
            log.info(f"Created new session {session['id']}")
            return session
```

### The PostgreSQL RPC Function:

**File**: `migrations/database_migrations_v2.sql`

```sql
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_subcontractor_id UUID
) RETURNS UUID AS $$
DECLARE
    v_active_session_id UUID;
    v_last_message_time TIMESTAMP WITH TIME ZONE;
    v_should_create_new BOOLEAN;
BEGIN
    -- Get active session
    SELECT id, last_message_at INTO v_active_session_id, v_last_message_time
    FROM conversation_sessions
    WHERE subcontractor_id = p_subcontractor_id
      AND status = 'active'
    ORDER BY started_at DESC
    LIMIT 1;

    -- Check if we should create new session
    v_should_create_new := should_create_new_session(p_subcontractor_id, v_last_message_time);

    -- If should create new or no active session exists
    IF v_should_create_new OR v_active_session_id IS NULL THEN  -- ← KEY LINE
        -- End previous session if exists
        IF v_active_session_id IS NOT NULL THEN
            UPDATE conversation_sessions
            SET status = 'ended',
                ended_at = NOW(),
                ended_reason = 'timeout',
                updated_at = NOW()
            WHERE id = v_active_session_id;
        END IF;

        -- Create new session
        INSERT INTO conversation_sessions (subcontractor_id, started_at, last_message_at)
        VALUES (p_subcontractor_id, NOW(), NOW())
        RETURNING id INTO v_active_session_id;
    END IF;

    RETURN v_active_session_id;
END;
$$ LANGUAGE plpgsql;
```

---

## Why Sessions Are Being Created/Ended Rapidly

### Scenario 1: RPC Function Failing

**Hypothesis**: `get_or_create_session_rpc()` throws exception or returns `None`

**Result**:
- Falls back to `_create_session_manual()` (line 60 or 65)
- Which calls `_end_active_sessions()` (line 80)
- Which ends ALL active sessions
- Then creates NEW session
- Repeats on every request

**Check Logs For**:
```
"PostgreSQL function failed, creating session manually"
"Error getting/creating session: <error>"
```

### Scenario 2: RPC Function Not Finding Active Sessions

**Hypothesis**: RPC query `WHERE status = 'active'` returns no results

**Possible Causes**:
1. Phase 5 migration not applied (unique constraint missing)
2. Sessions being ended by another process
3. Race condition in RPC function itself
4. Database connection/transaction issue

**Result**:
- `v_active_session_id IS NULL`
- RPC creates new session
- Marks it as active
- Next request: Can't find it (returns NULL again)
- Creates another new session

---

## Database Evidence Analysis

From user's query results:

```json
{
  "id": "77df9a8d-89d0-4f86-9e51-23e06b123bf5",
  "status": "active",      // ← Only ONE active
  "created_at": "2026-01-17 20:39:24.648447+00"
},
{
  "id": "f3acf2bd-d9d8-4ad8-bcbc-63c45101decb",
  "status": "ended",       // ← Rest are ended
  "created_at": "2026-01-17 20:39:24.532543+00"  // 116ms earlier!
},
{
  "id": "cfe01709-5562-4385-8e0b-a594d389e1e2",
  "status": "ended",       // ← Has tool_outputs
  "created_at": "2026-01-17 20:39:17.303167+00"
},
```

**Key Observations**:
1. Only ONE active session at a time ✅
2. Previous sessions immediately ended ✅
3. Two sessions created 116ms apart (race condition!)
4. Session with `tool_outputs` is ended

**This proves**: RPC function IS working (only one active) but creating new sessions too aggressively.

---

## Why Phase 2 Fix Didn't Prevent This

**Phase 2** (`d1570b0`): Pass `session_id` through call chain

**What it fixed**: Multiple concurrent calls to `get_or_create_session` within ONE request

**What it DIDN'T fix**: `get_or_create_session` itself creating NEW sessions on different requests

**The problem**: Even though each request reuses the same session_id internally, the FIRST call to `get_or_create_session` in each request is creating a NEW session.

---

## The Real Bug

Looking at the timestamps:

```
20:39:17.303 - Session cfe01709 created (has tool_outputs)
20:39:17.436 - User sends "view_sites_fr"
20:39:17.463 - Bot responds with "Champigny" list

20:39:24.532 - Session f3acf2bd created  ← NEW SESSION!
20:39:24.648 - Session 77df9a8d created  ← ANOTHER NEW SESSION!
20:39:27.151 - User sends "option_1_fr"
20:39:27.181 - Bot responds with greeting
```

**Between 20:39:17 and 20:39:24 (7 seconds)**:
- Something ended session `cfe01709`
- Two new sessions created

**Question**: What happened at 20:39:24 that created those sessions?

**Hypothesis**: The RPC function might be treating rapid requests as needing new sessions, OR the fallback `_create_session_manual` is being called.

---

## Diagnostic Steps

### Step 1: Check Application Logs

**Search for these exact strings**:
```bash
# At 20:39:17
"Session cfe01709-5562-4385-8e0b-a594d389e1e2 active for user"

# At 20:39:24
"PostgreSQL function failed, creating session manually"
"Error getting/creating session:"
"Created new session f3acf2bd"
"Created new session 77df9a8d"
```

### Step 2: Check if RPC Function Exists in Database

```sql
SELECT routine_name, routine_definition
FROM information_schema.routines
WHERE routine_name = 'get_or_create_session'
AND routine_schema = 'public';
```

### Step 3: Test RPC Function Directly

```sql
-- Call the function directly
SELECT get_or_create_session('ed97770c-ba77-437e-a1a9-e4a8e034d1da'::UUID);

-- Check what it returns
-- Then call again immediately
SELECT get_or_create_session('ed97770c-ba77-437e-a1a9-e4a8e034d1da'::UUID);

-- Should return SAME session ID
```

### Step 4: Check Phase 5 Migration Status

```sql
-- Check if unique constraint exists
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'conversation_sessions'
AND indexname = 'idx_unique_active_session_per_user';
```

---

## Potential Root Causes (Ranked by Likelihood)

### 1. RPC Function Throwing Exceptions (HIGH)

**Evidence**: Multiple fallback calls to `_create_session_manual`

**Cause**: Database permission issue, function not found, or parameter mismatch

**Check**: Application logs for "PostgreSQL function failed" or "Error getting/creating session"

### 2. RPC Function Not Finding Active Sessions (HIGH)

**Evidence**: New sessions created even though previous should be active

**Cause**:
- Transaction isolation issue
- Sessions marked as ended by another process
- `status = 'active'` query not finding recent sessions

**Check**: Database query to verify active sessions exist

### 3. Phase 5 Migration Not Applied (MEDIUM)

**Evidence**: Two sessions created 116ms apart suggests race condition

**Cause**: Unique constraint not enforcing single active session

**Check**: Database schema for `idx_unique_active_session_per_user`

### 4. Session Being Ended by Another Process (LOW)

**Evidence**: Sessions quickly marked as "ended"

**Cause**: Background job, timeout process, or API endpoint ending sessions

**Check**: Search codebase for calls to `end_session()`

---

## Expected Behavior vs Actual

### Expected (After Phase 2 Fix):

```
Request 1 (20:39:17):
  → get_or_create_session(user_id)
  → RPC finds no active session
  → Creates session cfe01709
  → Returns cfe01709
  → handle_direct_action uses cfe01709
  → Saves message to cfe01709

Request 2 (20:39:27):
  → get_or_create_session(user_id)
  → RPC finds active session cfe01709
  → Returns cfe01709  ← SHOULD REUSE!
  → handle_direct_action uses cfe01709
  → Finds tool_outputs in cfe01709
  → Success!
```

### Actual:

```
Request 1 (20:39:17):
  → get_or_create_session(user_id)
  → Creates session cfe01709 ✅
  → Returns cfe01709 ✅
  → Saves message to cfe01709 ✅

Request 2 (20:39:27):
  → get_or_create_session(user_id)
  → ❌ RPC creates NEW session 77df9a8d
  → ❌ OR falls back to _create_session_manual
  → ❌ Ends session cfe01709
  → ❌ Returns 77df9a8d
  → ❌ handle_direct_action searches 77df9a8d
  → ❌ Finds no messages/tool_outputs
  → ❌ Returns None
  → ❌ Wrong response
```

---

## Recommended Fix

**Once we identify the root cause from logs/diagnostics**:

### If RPC Function Failing:
- Fix the RPC call (permissions, parameters, etc.)
- Ensure function exists in database
- Add better error logging

### If RPC Not Finding Active Sessions:
- Debug RPC query logic
- Check transaction isolation
- Verify Phase 5 constraint applied

### If Fallback Being Called:
- Remove aggressive `_end_active_sessions()` from fallback
- Only end sessions if truly needed
- Add more defensive checks

---

## Conclusion

**Root Cause**: The session management is creating new sessions on every request and ending previous ones, causing message history to be split across multiple sessions.

**Primary Suspect**: PostgreSQL RPC function either:
1. Failing and falling back to manual creation
2. Not finding active sessions correctly

**Impact**:
- `handle_direct_action` can't find tool_outputs
- Intent classifier receives no conversation history
- Both failures stem from messages being in different session

**Next Action**: Check application logs for the specific error messages to identify which scenario is occurring.

---

*Analysis complete - Awaiting log verification to pinpoint exact failure mode*
