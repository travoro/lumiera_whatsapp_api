# Session Race Condition Fix - Deployment Guide

**Date:** 2026-01-17
**Status:** Ready for deployment
**Priority:** HIGH - Fixes critical bug causing context loss in conversations

---

## Overview

This deployment implements a comprehensive fix for the session race condition that was causing:
- Multiple sessions created within seconds
- Tool outputs saved to one session, lookups in another session
- Button clicks failing (handle_direct_action returning None)
- Intent classifier receiving empty conversation history
- "Searching for tool_outputs in last 0 messages" errors

## Root Cause Identified

**The Problem:**
1. `message.py` calls `get_or_create_session()` once (creates/fetches session A)
2. If button click fails, falls back to pipeline
3. Pipeline's `_manage_session()` calls `get_or_create_session()` AGAIN
4. PostgreSQL RPC creates NEW session B (doesn't find session A from 100ms ago)
5. Messages saved to different sessions → context loss

**Why It Happened:**
- Phase 2 fix was incomplete - pipeline still called RPC even when session already existed
- No session_id passed from message.py to pipeline
- No unique constraint to prevent duplicate active sessions

---

## Changes Implemented

### Code Changes

#### 1. `src/handlers/message_pipeline.py`
**Lines 253-313** - `_manage_session()` method

**Before:**
```python
async def _manage_session(self, ctx: MessageContext) -> Result[None]:
    session = await session_service.get_or_create_session(ctx.user_id)
    if session:
        ctx.session_id = session["id"]
        # ... load messages ...
```

**After:**
```python
async def _manage_session(self, ctx: MessageContext) -> Result[None]:
    # NEW: Reuse session_id if already set (from earlier in request)
    if ctx.session_id:
        log.debug(f"✅ Reusing existing session_id: {ctx.session_id}")
        session = await supabase_client.get_session_by_id(ctx.session_id)
        if session:
            log.info(f"✅ Session: {ctx.session_id} (reused)")
        else:
            log.warning(f"⚠️ Session {ctx.session_id} not found, creating new one")
            ctx.session_id = None  # Reset to trigger new creation

    # Only call get_or_create if no session yet
    if not ctx.session_id:
        session = await session_service.get_or_create_session(ctx.user_id)
        if session:
            ctx.session_id = session["id"]
            log.info(f"✅ Session: {ctx.session_id}")
        else:
            raise AgentExecutionException(stage="session_management")

    # Load conversation context (happens regardless of reuse/create)
    # ... load messages ...
```

**Lines 120-152** - `process()` method signature

**Added parameter:**
```python
async def process(
    self,
    from_number: str,
    message_body: str,
    message_sid: Optional[str] = None,
    media_url: Optional[str] = None,
    media_type: Optional[str] = None,
    interactive_data: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,  # NEW: Accept session_id
) -> Result[Dict[str, Any]]:
```

**Lines 144-152** - MessageContext initialization

**Added:**
```python
ctx = MessageContext(
    from_number=from_number,
    message_body=message_body,
    message_sid=message_sid,
    media_url=media_url,
    media_type=media_type,
    interactive_data=interactive_data,
    session_id=session_id,  # NEW: Set from parameter
)
```

#### 2. `src/handlers/message.py`
**Line 953** - Pipeline invocation

**Before:**
```python
result = await message_pipeline.process(
    from_number=phone_number,
    message_body=message_body,
    message_sid=message_sid,
    media_url=media_url,
    media_type=media_content_type,
    interactive_data=interactive_data,
)
```

**After:**
```python
result = await message_pipeline.process(
    from_number=phone_number,
    message_body=message_body,
    message_sid=message_sid,
    media_url=media_url,
    media_type=media_content_type,
    interactive_data=interactive_data,
    session_id=session_id,  # NEW: Pass session_id to prevent duplicate
)
```

#### 3. `src/services/session.py`
**Lines 28-77** - Enhanced logging in `get_or_create_session()`

**Added debug logs:**
- `🔍 Calling RPC for user ...`
- `✅ RPC returned session: ...`
- `❌ RPC returned {id} but get_session_by_id failed!`
- `⚠️ RPC returned None, using fallback`
- Full exception traces with `log.exception(e)`

### Database Changes

#### Migration 011: Phase 5 Unique Constraint
**File:** `migrations/011_add_unique_active_session_constraint.sql`
**Status:** Already exists, needs to be applied

**What it does:**
- Cleans up any existing duplicate active sessions
- Adds partial unique index: `idx_unique_active_session_per_user`
- Ensures only ONE active session per user
- Allows multiple ended/escalated sessions for history

**SQL:**
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_session_per_user
    ON conversation_sessions(subcontractor_id)
    WHERE status = 'active';
```

#### Migration 012: RPC Debugging
**File:** `migrations/012_add_session_rpc_debugging.sql`
**Status:** Created, needs to be applied

**What it does:**
- Adds RAISE NOTICE statements to `get_or_create_session()` function
- Logs when session is found, created, ended, or reused
- Helps diagnose why RPC creates new sessions

**Example output:**
```
🔍 Session lookup for ed97770c-...: found=abc123..., last_msg=2026-01-17 20:39:17
🔍 Should create new: false
♻️  Reusing session: abc123...
```

---

## Deployment Steps

### Step 1: Apply Code Changes

**Option A: Direct deployment (if using automated deployment)**
```bash
git add .
git commit -m "fix: Complete session race condition fix (Phase 2 + logging)

- Prevent duplicate get_or_create_session calls within request
- Pass session_id from message.py to pipeline
- Add session reuse logic in pipeline _manage_session
- Enhanced logging in session service for debugging
- Refs: SESSION_RACE_ROOT_CAUSE_FINAL.md"

git push origin main
```

**Option B: Manual deployment**
1. Copy changes to production server
2. Restart application
3. Verify no syntax errors in logs

### Step 2: Apply Database Migrations

**Via Supabase Dashboard (Recommended):**

1. Go to Supabase Dashboard > SQL Editor

2. **Apply Migration 011** (Unique Constraint):
   - Copy contents of `migrations/011_add_unique_active_session_constraint.sql`
   - Paste into SQL Editor
   - Click "Run"
   - Expected output: "✅ Added unique constraint for active conversation sessions"

3. **Apply Migration 012** (RPC Debugging):
   - Copy contents of `migrations/012_add_session_rpc_debugging.sql`
   - Paste into SQL Editor
   - Click "Run"
   - Expected output: "✅ Session RPC debugging enabled"

4. **Verify Migrations Applied:**
   ```sql
   -- Check unique index exists
   SELECT indexname, indexdef
   FROM pg_indexes
   WHERE tablename = 'conversation_sessions'
   AND indexname = 'idx_unique_active_session_per_user';

   -- Should return 1 row with the index definition
   ```

**Via Command Line (Alternative):**
```bash
cd migrations
python3 apply_session_fixes.py
```

### Step 3: Verify Deployment

#### Check 1: Application Logs
Look for new log entries indicating session reuse:

**Expected logs:**
```
✅ Reusing existing session_id: abc123-def456-...
✅ Session: abc123-def456-... (reused)
📜 Loaded 3 recent messages for intent context
```

**Should NOT see:**
```
Searching for tool_outputs in last 0 messages  ❌
⚠️ Direct action 'option_1' returned None  ❌
```

#### Check 2: Database Session Count
```sql
-- Should show only 1 active session per user
SELECT subcontractor_id, COUNT(*) as active_count
FROM conversation_sessions
WHERE status = 'active'
GROUP BY subcontractor_id
HAVING COUNT(*) > 1;

-- Expected: 0 rows (no duplicates)
```

#### Check 3: PostgreSQL NOTICE Logs
In Supabase Dashboard > Logs > Postgres Logs, look for:
```
🔍 Session lookup for ...
♻️  Reusing session: ...
✨ Created new session: ...  (should be rare)
```

### Step 4: Test Button Click Flow

**Manual Test:**
1. Send "Bonjour" via WhatsApp
2. Bot should show greeting menu
3. Click "View Sites" button
4. Bot should show project list
5. Click a project (e.g., "Champigny")
6. **EXPECTED:** Bot shows tasks for that project
7. **VERIFY IN LOGS:**
   - "✅ Reusing existing session_id"
   - "📦 Found tool_outputs with list_projects_tool"
   - NO "⚠️ Direct action returned None"

**What Fixed:**
- Before: Button clicks created NEW session → 0 messages → handle_direct_action failed
- After: Button clicks REUSE session → messages available → handle_direct_action succeeds

---

## Monitoring & Metrics

### Key Metrics to Watch

#### 1. Session Creation Rate
**Query:**
```sql
SELECT
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as sessions_created
FROM conversation_sessions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

**Expected:** Gradual decrease in sessions per hour (fewer unnecessary sessions)

#### 2. Session Reuse Rate
**From Application Logs:**
```bash
# Count session reuse vs creation
grep "Reusing existing session_id" logs/app.log | wc -l  # Should increase
grep "Created new session" logs/app.log | wc -l         # Should decrease
```

#### 3. Button Click Success Rate
**From Application Logs:**
```bash
# Button clicks that succeeded
grep "Found tool_outputs with" logs/app.log | wc -l

# Button clicks that failed
grep "Direct action.*returned None" logs/app.log | wc -l

# Success rate should be close to 100%
```

#### 4. Intent Classifier Context
**From Application Logs:**
```bash
# Should see conversation history being passed
grep "Loaded [1-9] recent messages for intent context" logs/app.log | wc -l

# Should NOT see empty history
grep "Loaded 0 recent messages" logs/app.log | wc -l
```

### Alert Thresholds

**Set up alerts for:**
- Session creation rate > 10 per minute per user (indicates race condition persists)
- "Direct action returned None" > 5% of button clicks
- "Searching for tool_outputs in last 0 messages" appears at all
- Database constraint violations on `idx_unique_active_session_per_user`

---

## Rollback Plan

If issues occur after deployment:

### Immediate Rollback (Code Only)
```bash
git revert HEAD
git push origin main
# Redeploy previous version
```

### Database Rollback (If Needed)
```sql
-- Remove debugging from RPC (restore original version)
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_subcontractor_id UUID
) RETURNS UUID AS $$
-- ... paste original function from database_migrations_v2.sql ...
$$ LANGUAGE plpgsql;

-- Keep the unique constraint (safe to keep, doesn't cause issues)
-- Only remove if absolutely necessary:
DROP INDEX IF EXISTS idx_unique_active_session_per_user;
```

### Verify Rollback
- Check logs return to previous behavior
- Verify sessions still being created
- No new errors introduced

---

## Success Criteria

✅ **Fix is successful when:**
1. Only ONE session created per user conversation (not multiple per request)
2. Button clicks work correctly (handle_direct_action finds tool_outputs)
3. Intent classifier receives conversation history (not empty)
4. No "Searching for tool_outputs in last 0 messages" warnings
5. Logs show "✅ Reusing existing session_id" frequently
6. Database query shows no duplicate active sessions per user

❌ **Issues to watch for:**
- Database constraint violations (would indicate race condition still exists at DB level)
- Increased latency (session lookup adds minimal overhead, should be <10ms)
- Session not found errors (would indicate session_id being passed incorrectly)

---

## Additional Notes

### Why This Fix Works

**Problem:** Two `get_or_create_session()` calls in same request
**Solution:** Pass session_id from first call to second call, reuse instead of recreating

**Analogy:** Like getting a ticket number at a deli counter, then getting another ticket when you reach the front of the line. We now pass the first ticket through the whole flow.

### Impact on Performance

**Expected:**
- **Latency:** Minimal change (<10ms per request)
  - `get_session_by_id()` is faster than `get_or_create_session_rpc()`
  - Fewer database inserts/updates
- **Database Load:** Reduced
  - Fewer session creation operations
  - Fewer session ending operations
  - Fewer index updates

### Testing in Development

To test locally:
1. Enable debug logging: `LOG_LEVEL=DEBUG` in `.env`
2. Send message sequence: "Bonjour" → "View Sites" → "Champigny"
3. Check logs for session reuse indicators
4. Query database: `SELECT * FROM conversation_sessions WHERE status = 'active'`

---

## Support

**If issues occur:**
1. Check application logs: `/home/ceeai/whatsapp_api/logs/app.log`
2. Check PostgreSQL logs: Supabase Dashboard > Logs > Postgres Logs
3. Run diagnostic query:
   ```sql
   SELECT
       s.id,
       s.subcontractor_id,
       s.status,
       s.created_at,
       COUNT(m.id) as message_count
   FROM conversation_sessions s
   LEFT JOIN messages m ON m.session_id = s.id
   WHERE s.created_at > NOW() - INTERVAL '1 hour'
   GROUP BY s.id
   ORDER BY s.created_at DESC;
   ```

**Contact:** See `docs/SESSION_RACE_ROOT_CAUSE_FINAL.md` for full technical analysis

---

## Related Documentation

- `docs/SESSION_RACE_ROOT_CAUSE_FINAL.md` - Complete root cause analysis
- `docs/LOG_ANALYSIS_SMOKING_GUN.md` - Log evidence of the issue
- `docs/REGRESSION_SUMMARY_AND_DIAGNOSIS.md` - Investigation summary
- `migrations/011_add_unique_active_session_constraint.sql` - Phase 5 migration
- `migrations/012_add_session_rpc_debugging.sql` - RPC debugging enhancement

---

**Deployment Checklist:**

- [ ] Code changes reviewed and tested
- [ ] Database migrations prepared
- [ ] Backup of current database state taken
- [ ] Monitoring alerts configured
- [ ] Rollback plan documented and understood
- [ ] Migration 011 applied successfully
- [ ] Migration 012 applied successfully
- [ ] Code deployed to production
- [ ] Initial smoke tests passed
- [ ] Logs monitored for 1 hour post-deployment
- [ ] Success criteria verified
- [ ] Team notified of deployment
