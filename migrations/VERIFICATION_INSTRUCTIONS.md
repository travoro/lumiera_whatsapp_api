# Complete Migration Verification Instructions

## Overview
This will check ALL migrations from the last 4 days to ensure your database is fully up to date.

---

## Step 1: Run Comprehensive Verification

1. **Open Supabase Dashboard**: https://supabase.com/dashboard
2. **Navigate to SQL Editor** (left sidebar)
3. **Copy and paste this ENTIRE file**: `migrations/verify_all_recent_migrations.sql`
4. **Click "Run"**

---

## Step 2: Check Results

You should see multiple checks like this:

```
✅ APPLIED - progress_update_sessions table exists
✅ APPLIED - fsm_state column exists
✅ APPLIED - fsm_idempotency_records table exists
✅ APPLIED - fsm_transition_log table exists
✅ APPLIED - fsm_clarification_records table exists
✅ APPLIED - Foreign key uses ON DELETE SET NULL
✅ APPLIED - conversation_sessions table exists
✅ APPLIED - get_or_create_session function exists
✅ APPLIED - should_create_new_session function exists
✅ APPLIED - Unique constraint exists
✅ APPLIED - RPC has debugging
```

---

## Step 3: If Any Show ❌ NOT APPLIED

### If `add_progress_update_sessions.sql` not applied:
```bash
# Run this file in SQL Editor:
cat migrations/add_progress_update_sessions.sql
```

### If `009_fsm_tables.sql` not applied:
```bash
# Run this file in SQL Editor:
cat migrations/009_fsm_tables.sql
```

### If `010_fix_transition_log_cascade.sql` not applied:
```bash
# Run this file in SQL Editor:
cat migrations/010_fix_transition_log_cascade.sql
```

### If `database_migrations_v2.sql` not applied:
```bash
# Run this file in SQL Editor:
cat migrations/database_migrations_v2.sql
```

### If `011_add_unique_active_session_constraint.sql` not applied:
```bash
# Run this file in SQL Editor:
cat migrations/011_add_unique_active_session_constraint.sql
```

### If `012_add_session_rpc_debugging.sql` not applied:
```bash
# Run this file in SQL Editor:
cat migrations/012_add_session_rpc_debugging.sql
```

---

## Step 4: Re-run Verification

After applying any missing migrations, run the verification script again to confirm all checks pass.

---

## Quick Reference: What Each Migration Does

| Migration | Date | Purpose |
|-----------|------|---------|
| `add_progress_update_sessions.sql` | Jan 15 | Adds progress update session tracking |
| `009_fsm_tables.sql` | Jan 16 | Adds FSM (Finite State Machine) support |
| `010_fix_transition_log_cascade.sql` | Jan 16 | Fixes foreign key cascade for audit logs |
| `database_migrations_v2.sql` | Jan 17 | Core conversation sessions and RPC functions |
| `011_add_unique_active_session_constraint.sql` | Jan 17 | Prevents duplicate active sessions (CRITICAL) |
| `012_add_session_rpc_debugging.sql` | Jan 17 | Adds debugging to RPC function (CRITICAL) |

**CRITICAL** = Required for session race condition fix

---

## If Everything Shows ✅

**You're all set!** All migrations are applied correctly. You can proceed to deploy the code changes.

---

## Need Help?

If you see any unexpected results or errors, let me know which migration check failed and I'll help you fix it.
