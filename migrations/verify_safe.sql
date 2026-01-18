-- ============================================================================
-- SAFE MIGRATION VERIFICATION - Won't error on missing tables
-- ============================================================================

-- Check 1: progress_update_sessions table
SELECT
    'Migration: add_progress_update_sessions.sql' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'progress_update_sessions'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run add_progress_update_sessions.sql'
    END as status;

-- Check 2: fsm_state column
SELECT
    'Migration: 009_fsm_tables.sql - Part 1' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'progress_update_sessions'
            AND column_name = 'fsm_state'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run 009_fsm_tables.sql'
    END as status;

-- Check 3: fsm_idempotency_records table
SELECT
    'Migration: 009_fsm_tables.sql - Part 2' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'fsm_idempotency_records'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run 009_fsm_tables.sql'
    END as status;

-- Check 4: fsm_transition_log table
SELECT
    'Migration: 009_fsm_tables.sql - Part 3' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'fsm_transition_log'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run 009_fsm_tables.sql'
    END as status;

-- Check 5: fsm_clarification_requests table (FIXED: was checking wrong name)
SELECT
    'Migration: 009_fsm_tables.sql - Part 4' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'fsm_clarification_requests'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run 009_fsm_tables.sql'
    END as status;

-- Check 6: Foreign key cascade fix
SELECT
    'Migration: 010_fix_transition_log_cascade.sql' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
            WHERE tc.table_name = 'fsm_transition_log'
            AND tc.constraint_name = 'fsm_transition_log_session_id_fkey'
            AND rc.delete_rule = 'SET NULL'
        ) THEN '✅ APPLIED'
        ELSE '⚠️ SKIP - Only needed if fsm_transition_log exists'
    END as status;

-- Check 7: conversation_sessions table
SELECT
    'Migration: database_migrations_v2.sql - Part 1' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'conversation_sessions'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run database_migrations_v2.sql'
    END as status;

-- Check 8: get_or_create_session function
SELECT
    'Migration: database_migrations_v2.sql - Part 2' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'get_or_create_session'
            AND n.nspname = 'public'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run database_migrations_v2.sql'
    END as status;

-- Check 9: Unique constraint
SELECT
    'Migration: 011_add_unique_active_session_constraint.sql' as migration,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE tablename = 'conversation_sessions'
            AND indexname = 'idx_unique_active_session_per_user'
        ) THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run 011_add_unique_active_session_constraint.sql'
    END as status;

-- Check 10: RPC debugging
SELECT
    'Migration: 012_add_session_rpc_debugging.sql' as migration,
    CASE
        WHEN pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%'
        THEN '✅ APPLIED'
        ELSE '❌ NOT APPLIED - Need to run 012_add_session_rpc_debugging.sql'
    END as status
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname = 'get_or_create_session'
AND n.nspname = 'public';
