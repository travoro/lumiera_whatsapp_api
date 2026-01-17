# FSM Integration - Next Steps

**Date:** 2026-01-16
**Current Status:** ✅ Code Complete, 🔄 Integration Pending
**Goal:** Activate FSM system in production

---

## 📋 Quick Summary

**What's Done:**
- ✅ All FSM code written (`src/fsm/`)
- ✅ All tests passing (95 total tests)
- ✅ Database migration created
- ✅ Feature flag configured (`enable_fsm = False`)

**What's Left:**
- 🔄 Run database migration
- 🔄 Test FSM manually
- 🔄 Integrate into message pipeline
- 🔄 Add startup hooks
- 🔄 Enable feature flag
- 🔄 Monitor and verify

---

## 🚀 Step-by-Step Integration Guide

### Step 1: Run Database Migration (5 minutes)

**Purpose:** Create FSM tables in PostgreSQL

```bash
# Check connection
echo $SUPABASE_DB_URL

# Run migration
psql $SUPABASE_DB_URL -f migrations/009_fsm_tables.sql

# Verify tables created
psql $SUPABASE_DB_URL -c "\\dt fsm_*"
psql $SUPABASE_DB_URL -c "\\d+ progress_update_sessions"
```

**Expected Output:**
```
fsm_idempotency_records
fsm_clarification_requests
fsm_transition_log
```

**Verify Columns Added to `progress_update_sessions`:**
- `fsm_state` (text)
- `closure_reason` (text)
- `session_metadata` (jsonb)
- `transition_history` (jsonb)

**Rollback Plan (if issues):**
```sql
-- Rollback script (if needed)
DROP TABLE IF EXISTS fsm_transition_log CASCADE;
DROP TABLE IF EXISTS fsm_clarification_requests CASCADE;
DROP TABLE IF EXISTS fsm_idempotency_records CASCADE;

ALTER TABLE progress_update_sessions
DROP COLUMN IF EXISTS fsm_state,
DROP COLUMN IF EXISTS closure_reason,
DROP COLUMN IF EXISTS session_metadata,
DROP COLUMN IF EXISTS transition_history;
```

---

### Step 2: Test FSM with Feature Flag Disabled (10 minutes)

**Purpose:** Verify FSM infrastructure works but doesn't interfere

```bash
# Run all tests (should all pass)
source venv/bin/activate
pytest tests/test_fsm_core.py tests/test_scenarios.py tests/test_integration_comprehensive.py -v

# Check logs for FSM activity (should be none with flag disabled)
tail -f logs/app.log | grep -i "fsm"
```

**Expected:** No FSM activity since flag is `False`

---

### Step 3: Integrate FSM into Message Pipeline (30-60 minutes)

**Two options:**

#### Option A: Minimal Integration (Recommended for v1)
Add only idempotency checking - least risky.

**File:** `src/handlers/message.py`

```python
from src.config import settings

async def process_inbound_message(...):
    """Process inbound message"""

    # Add at the very start (after logging)
    if settings.enable_fsm:
        from src.fsm.core import StateManager
        state_manager = StateManager()

        # Check idempotency (prevent duplicate processing)
        cached_response = await state_manager.check_idempotency(
            user_id=from_number,
            message_sid=message_sid
        )

        if cached_response:
            logger.info(f"Returning cached response for duplicate message {message_sid}")
            return cached_response

    # ... existing code ...

    # Add at the end (before returning)
    if settings.enable_fsm and response_text:
        await state_manager.record_idempotency(
            user_id=from_number,
            message_sid=message_sid,
            response={"body": response_text, "media": media_urls}
        )
```

**Benefits:**
- Prevents duplicate message processing
- Zero risk to existing flows
- Can be enabled immediately

#### Option B: Full Integration (More features, more risk)
Add intent routing, clarification, and conflict resolution.

**File:** `src/handlers/message_pipeline.py`

```python
from src.config import settings
from src.fsm import IntentRouter, clarification_manager
from src.fsm.core import StateManager

async def _classify_intent(self, ctx: MessageContext):
    """Classify intent with FSM support"""

    if settings.enable_fsm:
        state_manager = StateManager()

        # 1. Check for pending clarification
        clarification = await clarification_manager.get_pending_clarification(ctx.user_id)
        if clarification:
            # User is responding to clarification
            ctx.intent = "clarification_response"
            ctx.metadata["clarification_id"] = clarification["id"]
            ctx.metadata["clarification_options"] = clarification["options"]
            return Result.ok(None)

        # 2. Get session context
        session = await state_manager.get_session(ctx.user_id)
        fsm_context = {
            "user_id": ctx.user_id,
            "current_state": session["fsm_state"] if session else "idle",
            "session_id": session["id"] if session else None,
            "task_id": session["task_id"] if session else None
        }

        # 3. Route through FSM
        intent_router = IntentRouter()
        winner, needs_clarification, clarification_request = intent_router.route_intent(
            intent=ctx.intent,
            confidence=ctx.confidence,
            context=fsm_context,
            message=ctx.message_in_french
        )

        # 4. Handle clarification
        if needs_clarification:
            # Create clarification request
            clarif_id = await clarification_manager.create_clarification(
                user_id=ctx.user_id,
                question=clarification_request["question"],
                options=clarification_request["options"],
                context={"intent": ctx.intent, "confidence": ctx.confidence}
            )

            # Format clarification message
            ctx.response_text = self._format_clarification(clarification_request)
            ctx.response_type = "interactive_list"
            return Result.ok(None)

        # 5. Use winner intent
        ctx.intent = winner["intent"]
        ctx.confidence = winner["confidence"]

    # Continue with existing logic
    return Result.ok(None)
```

**Benefits:**
- Full FSM features (conflict resolution, clarification)
- Better user experience
- Handles ambiguous cases

**Risks:**
- More complex integration
- Needs thorough testing

---

### Step 4: Add Startup Hooks (5 minutes)

**Purpose:** Recover orphaned sessions on server restart

**File:** `main.py` (or wherever FastAPI app is defined)

```python
from fastapi import FastAPI
from src.config import settings

app = FastAPI()

@app.on_event("startup")
async def startup():
    """Run startup tasks"""
    logger.info("Server starting up...")

    if settings.enable_fsm:
        from src.fsm.handlers import session_recovery_manager

        # Recover orphaned sessions
        stats = await session_recovery_manager.recover_on_startup()
        logger.info(f"FSM session recovery complete: {stats}")

    logger.info("Server startup complete")
```

---

### Step 5: Add Background Cleanup Task (10 minutes)

**Purpose:** Clean up expired clarifications and idempotency records

**Option A: Using APScheduler (if installed)**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.fsm.handlers import run_cleanup_task

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('interval', minutes=5)
async def fsm_cleanup():
    if settings.enable_fsm:
        await run_cleanup_task()

scheduler.start()
```

**Option B: Using Cron Job**

```bash
# Add to crontab
*/5 * * * * psql $SUPABASE_DB_URL -c "SELECT cleanup_expired_fsm_records()"
```

**Option C: Manual (for testing)**

```python
# Run manually when needed
from src.fsm.handlers import run_cleanup_task
await run_cleanup_task()
```

---

### Step 6: Enable FSM Feature Flag (1 minute)

**Testing (locally first):**

```python
# In .env.local or .env.development
ENABLE_FSM=true
```

**Then restart:**
```bash
pm2 restart whatsapp-api
```

**Production (when ready):**

```bash
# Set environment variable
export ENABLE_FSM=true

# Or in .env
echo "ENABLE_FSM=true" >> .env

# Restart
pm2 restart whatsapp-api
```

---

### Step 7: Monitor and Verify (Ongoing)

**Check FSM is working:**

```sql
-- Check active sessions (should match active users)
SELECT COUNT(*) as active_sessions
FROM progress_update_sessions
WHERE fsm_state NOT IN ('completed', 'abandoned');

-- Check recent transitions (should show activity)
SELECT from_state, to_state, COUNT(*) as count
FROM fsm_transition_log
WHERE logged_at > NOW() - INTERVAL '1 hour'
GROUP BY from_state, to_state;

-- Check clarifications (if Option B integration)
SELECT status, COUNT(*)
FROM fsm_clarification_requests
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY status;

-- Check idempotency records
SELECT COUNT(*) as duplicate_messages_prevented
FROM fsm_idempotency_records
WHERE created_at > NOW() - INTERVAL '1 hour';
```

**Monitor Logs:**

```bash
# Watch for FSM activity
tail -f logs/app.log | grep -E "(FSM|transition|clarification|idempotency)"

# Watch for errors
tail -f logs/app.log | grep -i "ERROR"
```

**Key Metrics:**

| Metric | Query | Expected |
|--------|-------|----------|
| Stuck sessions | `SELECT COUNT(*) FROM progress_update_sessions WHERE fsm_state NOT IN ('completed', 'abandoned') AND last_activity < NOW() - INTERVAL '2 hours'` | 0 |
| Clarifications answered | `SELECT COUNT(*) FILTER (WHERE status = 'answered') * 100.0 / NULLIF(COUNT(*), 0) FROM fsm_clarification_requests` | >80% |
| Invalid transitions | `SELECT COUNT(*) FROM fsm_transition_log WHERE success = false` | 0-5 |
| Duplicate prevention | `SELECT COUNT(*) FROM fsm_idempotency_records WHERE created_at > NOW() - INTERVAL '1 day'` | >0 (proves it's working) |

---

## 🎯 Recommended Rollout Plan

### Phase 1: Minimal Risk (Day 1)
1. ✅ Run database migration
2. ✅ Test with `enable_fsm=False` (verify no impact)
3. ✅ Implement Option A (idempotency only)
4. ✅ Enable `enable_fsm=True` for YOUR account only
5. ✅ Test manually via WhatsApp
6. ✅ Monitor for 2-4 hours

**Success Criteria:** No errors, idempotency records show up in database

### Phase 2: Full Features (Day 2-3)
1. ✅ Implement Option B (full FSM integration)
2. ✅ Test all 12 audit scenarios manually
3. ✅ Enable for 2-3 friendly users
4. ✅ Monitor clarifications effectiveness
5. ✅ Fix any issues found

**Success Criteria:** Clarifications work, conflicts resolved correctly

### Phase 3: Production (Day 4+)
1. ✅ Enable for all users
2. ✅ Monitor metrics (queries above)
3. ✅ Collect user feedback
4. ✅ Iterate on clarification wording

**Success Criteria:** <5% error rate, >80% clarification answer rate

---

## ⚠️ Troubleshooting Guide

### Issue: Migration fails

**Error:** `relation "fsm_idempotency_records" already exists`

**Solution:**
```sql
-- Check what exists
\dt fsm_*

-- If tables exist but incomplete, drop and recreate
DROP TABLE IF EXISTS fsm_transition_log CASCADE;
DROP TABLE IF EXISTS fsm_clarification_requests CASCADE;
DROP TABLE IF EXISTS fsm_idempotency_records CASCADE;

-- Re-run migration
\i migrations/009_fsm_tables.sql
```

### Issue: Tests fail after migration

**Solution:**
```bash
# Clear pytest cache
rm -rf .pytest_cache __pycache__ tests/__pycache__

# Reinstall dependencies
pip install -r requirements.txt

# Run tests again
pytest tests/test_fsm_core.py -v
```

### Issue: FSM not activating

**Check:**
1. Environment variable: `echo $ENABLE_FSM`
2. Config: `python -c "from src.config import settings; print(settings.enable_fsm)"`
3. Import: Verify `from src.fsm.core import StateManager` works

### Issue: Duplicate messages not prevented

**Check:**
1. Idempotency integration added (Step 3)
2. Records in database: `SELECT * FROM fsm_idempotency_records LIMIT 10`
3. Logs show idempotency checks

### Issue: Clarifications not expiring

**Solution:**
- Ensure cleanup task running (Step 5)
- Run manually: `SELECT cleanup_expired_fsm_records()`

---

## 📝 Integration Checklist

Use this checklist to track progress:

### Database
- [ ] Migration run successfully
- [ ] Tables verified (fsm_* tables exist)
- [ ] Columns added to progress_update_sessions
- [ ] Test query works

### Code Integration
- [ ] Option A (idempotency) implemented OR
- [ ] Option B (full FSM) implemented
- [ ] Startup hooks added
- [ ] Cleanup task configured
- [ ] Code tested locally

### Testing
- [ ] All unit tests pass (21 tests)
- [ ] All scenario tests pass (14 tests)
- [ ] All integration tests pass (60 tests)
- [ ] Manual testing via WhatsApp

### Deployment
- [ ] Feature flag enabled
- [ ] Server restarted
- [ ] Logs show FSM activity
- [ ] Database shows records
- [ ] Monitoring queries set up

### Verification
- [ ] Idempotency working (duplicates prevented)
- [ ] Sessions tracked correctly
- [ ] Transitions logged
- [ ] No errors in logs for 24 hours

---

## 🎉 Success!

Once all items checked:
- ✅ FSM is fully integrated
- ✅ Users get better experience
- ✅ System handles edge cases
- ✅ Logs show what's happening
- ✅ No more stuck sessions!

---

**Next Action:** Start with Step 1 (run database migration) and work through each step sequentially.
