# Log Analysis - The Smoking Gun

**Date**: 2026-01-17
**Status**: 🔥 **ROOT CAUSE CONFIRMED FROM LOGS**

---

## Critical Log Evidence

### Timeline from Logs (UTC+1: 21:39 = 20:39 UTC):

```
21:39:06 - Session 7cfd9b51 created (greeting)
21:39:17 - Session cfe01709 created (view_sites_fr → Champigny list)
21:39:24 - Session f3acf2bd created (first call in request)
21:39:24 - Session 77df9a8d created (second call in same request!)
21:39:24 - handle_direct_action searches for messages
21:39:24 - "🔍 Searching for tool_outputs in last 0 messages" ← SMOKING GUN!
21:39:24 - "❌ Could not find relevant tool in conversation history"
21:39:24 - "⚠️ Direct action 'option_1' returned None - falling back to AI pipeline"
```

---

## THE SMOKING GUN: "Last 0 Messages"

```
2026-01-17 21:39:24 | INFO | 🔍 Searching for tool_outputs in last 0 messages (target_tool: ANY)
2026-01-17 21:39:24 | WARNING | ❌ Could not find relevant tool in conversation history
2026-01-17 21:39:24 | WARNING | ⚠️ Could not resolve list selection option_1
2026-01-17 21:39:24 | WARNING | ⚠️ Direct action 'option_1' returned None - falling back to AI pipeline
```

**This proves**:
- `handle_direct_action` loaded ZERO messages from session
- The session is empty (just created)
- Can't find tool_outputs (in different session)
- Falls back to pipeline

---

## Complete Log Sequence

### Request 1: User Clicks "View Sites" (21:39:17)

```
21:39:17 | Received webhook from +33652964466
21:39:17 | 📥 Processing message from +33652964466
21:39:17 | Session cfe01709-5562-4385-8e0b-a594d389e1e2 active for user ed97770c
21:39:17 | 🔘 Interactive action detected: view_sites
21:39:17 | 🎯 Direct action handler called for action: view_sites
21:39:17 | 📋 Calling list_projects_tool for user ed97770c
21:39:17 | 🔧 Tool called: list_projects_tool(user_id=ed97770c...)
```

**Result**: Session cfe01709 created, tool_outputs saved to it ✅

### Request 2: User Clicks "Option 1" (21:39:24)

```
21:39:24 | Received webhook from +33652964466
21:39:24 | 📥 Processing message from +33652964466
21:39:24 | Session f3acf2bd-d9d8-4ad8-bcbc-63c45101decb active for user ed97770c  ← NEW SESSION #1
21:39:24 | 📋 Interactive list selection detected: option_1
21:39:24 | 🏷️  Parsed list_type: option, option #1
21:39:24 | 🔍 Searching for tool_outputs in last 0 messages ← ZERO MESSAGES!
21:39:24 | ❌ Could not find relevant tool in conversation history
21:39:24 | ⚠️ Could not resolve list selection option_1
21:39:24 | ⚠️ Direct action 'option_1' returned None - falling back to AI pipeline
21:39:24 | 🔄 Processing message through pipeline
21:39:24 | ✅ User authenticated: ed97770c (Jean)
21:39:24 | Session 77df9a8d-89d0-4f86-9e51-23e06b123bf5 active for user ed97770c  ← NEW SESSION #2
21:39:24 | ✅ Session: 77df9a8d
21:39:24 | 🔍 Detecting language for message: 'option_1_fr'
```

**Result**:
- Two NEW sessions created (f3acf2bd and 77df9a8d)
- Both are empty
- handle_direct_action finds 0 messages
- Falls back to pipeline

---

## Key Findings from Logs

### Finding 1: NO RPC Errors ✅

**Searched for**: "PostgreSQL function failed", "Error calling get_or_create_session RPC"

**Found**: NONE

**Conclusion**: RPC function IS working, no exceptions

### Finding 2: NO Manual Fallback ✅

**Searched for**: "Created new session" (from `_create_session_manual`)

**Found**: NONE

**Conclusion**: Manual fallback is NOT being used

### Finding 3: RPC Creating New Sessions Every Time ❌

**Evidence**:
```
21:39:06 - Session 7cfd9b51 created
21:39:17 - Session cfe01709 created (11 seconds later)
21:39:24 - Session f3acf2bd created (7 seconds later)
21:39:24 - Session 77df9a8d created (same millisecond!)
```

**Conclusion**: RPC function is creating NEW session on every request instead of reusing

### Finding 4: Phase 2 Fix NOT Working ❌

**Evidence**: Two sessions created in SAME request (f3acf2bd and 77df9a8d at 21:39:24)

**Expected** (after Phase 2): Session ID passed through, should reuse f3acf2bd

**Actual**: Second call to `get_or_create_session` created 77df9a8d

**Conclusion**: Phase 2 fix deployed but NOT preventing duplicates within request

### Finding 5: Messages Are Being Saved ✅

**Evidence**: Database query shows messages exist with tool_outputs

**Conclusion**: Message storage works, but sessions are being created too rapidly

---

## Why Phase 2 Fix Isn't Working

**Phase 2** (`d1570b0`): Pass `session_id` through call chain

**Expected Flow**:
```
1. handle_direct_action gets session_id parameter
2. Reuses it instead of calling get_or_create_session
3. One session per request
```

**Actual Flow** (from logs):
```
1. Line 760: session = await session_service.get_or_create_session(user_id)
   → Creates f3acf2bd
2. Line 772: direct_response = await handle_direct_action(..., session_id=session_id)
   → handle_direct_action should reuse f3acf2bd
3. BUT: handle_direct_action calls get_messages_by_session(session_id, ...)
   → Returns 0 messages (session just created!)
4. Line 941: pipeline.process() called (fallback)
5. Line 254: _manage_session() calls get_or_create_session() again
   → Creates 77df9a8d!
```

---

## The Real Problem

### Problem 1: RPC Creating New Sessions Too Aggressively

**The RPC function** (`get_or_create_session`):
```sql
-- Get active session
SELECT id, last_message_at INTO v_active_session_id, v_last_message_time
FROM conversation_sessions
WHERE subcontractor_id = p_subcontractor_id
  AND status = 'active'
ORDER BY started_at DESC
LIMIT 1;
```

**Question**: Why isn't this finding the previous session?

**Possible causes**:
1. Previous session marked as "ended" before next request
2. Transaction isolation - can't see recent session
3. Race condition in database query itself

### Problem 2: Empty Sessions

**When new session created**:
- Session has NO messages
- handle_direct_action searches session for tool_outputs
- Finds 0 messages
- Can't find tool_outputs
- Returns None

**Why this breaks everything**:
- User clicked button after seeing project list
- Project list was in OLD session (cfe01709)
- New session (f3acf2bd) is empty
- Can't process button click
- Falls back to pipeline

---

## Why Sessions Are Being Marked as "Ended"

**From database query**: All previous sessions have status='ended'

**Hypothesis**: The RPC function's logic:
```sql
IF v_should_create_new OR v_active_session_id IS NULL THEN
    -- End previous session if exists
    IF v_active_session_id IS NOT NULL THEN
        UPDATE conversation_sessions
        SET status = 'ended',
            ended_at = NOW(),
            ended_reason = 'timeout',
            updated_at = NOW()
        WHERE id = v_active_session_id;
    END IF;
```

**The function is deciding to create new session**, which ends the old one.

**But why?**

Let's check `should_create_new_session` logic:
```sql
-- If more than 7 hours - new session
IF v_hours_diff > 7 THEN
    RETURN TRUE;
END IF;

-- If last message was after 8 PM and current is after 6 AM - new day, new session
IF v_last_message_hour >= 20 AND v_current_hour >= 6 THEN
    RETURN TRUE;
END IF;
```

**Checking the timestamps**:
- 21:39:06 → 21:39:17 = 11 seconds (< 7 hours) ✓
- 21:39:17 → 21:39:24 = 7 seconds (< 7 hours) ✓
- Both are at 21:39 (9:39 PM), between 6-20 ✓

**None of these conditions should trigger new session!**

---

## The Root Cause

**Most likely**: Transaction or race condition issue

**Scenario**:
1. User sends "view_sites_fr" at 21:39:17
2. RPC looks for active session: finds NONE (or previous is being ended)
3. Creates session cfe01709
4. Processes request, saves message with tool_outputs
5. User sends "option_1_fr" at 21:39:24 (7 seconds later)
6. RPC looks for active session: **DOESN'T FIND cfe01709**
7. Creates new session f3acf2bd
8. handle_direct_action uses f3acf2bd (empty)
9. Can't find tool_outputs
10. Returns None
11. Falls back to pipeline
12. Pipeline calls get_or_create_session AGAIN
13. Creates session 77df9a8d

**Why RPC doesn't find cfe01709**:
- Database transaction not committed yet?
- Query timing issue?
- Status not set correctly?
- Unique constraint issue?

---

## Verification Needed

### Check 1: Transaction Isolation

**Question**: Is session creation in a transaction that's not committed immediately?

**Test**: Add logging in RPC function to see what it finds

### Check 2: Database Timing

**Question**: Is there a delay between INSERT and SELECT finding it?

**Test**: Check if `last_message_at` is being updated

### Check 3: Phase 5 Migration

**Question**: Is the unique constraint applied?

**SQL**:
```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'conversation_sessions'
AND indexname = 'idx_unique_active_session_per_user';
```

---

## Immediate Action Required

Based on logs, we need to:

1. **Check why RPC doesn't find previous session**
   - Debug RPC query
   - Check transaction isolation
   - Verify Phase 5 constraint applied

2. **Fix Phase 2 implementation**
   - Pipeline still calling get_or_create_session in _manage_session
   - Should reuse session from earlier in request

3. **Consider workaround**
   - Increase delay before new session?
   - Cache session ID in application memory?
   - Use database-level locking?

---

## Conclusion

**Confirmed from Logs**:
- ✅ RPC function IS working (no errors)
- ✅ Phase 2 fix IS deployed (commit in git)
- ❌ RPC creating new sessions every time
- ❌ New sessions are empty (0 messages)
- ❌ handle_direct_action can't find tool_outputs
- ❌ Falls back to pipeline
- ❌ Pipeline creates ANOTHER session
- ❌ Intent classifier gets no history

**Root Cause**: PostgreSQL RPC function `get_or_create_session` is not finding recently created active sessions, causing it to create new ones.

**Most Likely Reason**: Transaction isolation, timing issue, or the `should_create_new_session` logic has a bug we haven't identified yet.

**Next Step**: Debug the RPC function to see why it's not finding previous active sessions.

---

*Log analysis complete - Ready for fix implementation*
