-- ============================================================================
-- COMPREHENSIVE MIGRATION VERIFICATION - Last 4 Days
-- ============================================================================
-- Run this in Supabase Dashboard > SQL Editor to verify ALL recent migrations
-- ============================================================================

-- ============================================================================
-- MIGRATION: add_progress_update_sessions.sql (Jan 15)
-- ============================================================================
SELECT
    '=== Migration: add_progress_update_sessions.sql (Jan 15) ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'progress_update_sessions'
        ) THEN '✅ APPLIED - progress_update_sessions table exists'
        ELSE '❌ NOT APPLIED - Table missing'
    END as status;

-- ============================================================================
-- MIGRATION: 009_fsm_tables.sql (Jan 16)
-- ============================================================================

-- Check 1: FSM columns in progress_update_sessions
SELECT
    '=== Migration 009: FSM Tables (Jan 16) - Part 1 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'progress_update_sessions'
            AND column_name = 'fsm_state'
        ) THEN '✅ APPLIED - fsm_state column exists'
        ELSE '❌ NOT APPLIED - fsm_state column missing'
    END as status;

-- Check 2: fsm_idempotency_records table
SELECT
    '=== Migration 009: FSM Tables (Jan 16) - Part 2 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'fsm_idempotency_records'
        ) THEN '✅ APPLIED - fsm_idempotency_records table exists'
        ELSE '❌ NOT APPLIED - Table missing'
    END as status;

-- Check 3: fsm_transition_log table
SELECT
    '=== Migration 009: FSM Tables (Jan 16) - Part 3 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'fsm_transition_log'
        ) THEN '✅ APPLIED - fsm_transition_log table exists'
        ELSE '❌ NOT APPLIED - Table missing'
    END as status;

-- Check 4: fsm_clarification_records table
SELECT
    '=== Migration 009: FSM Tables (Jan 16) - Part 4 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'fsm_clarification_records'
        ) THEN '✅ APPLIED - fsm_clarification_records table exists'
        ELSE '❌ NOT APPLIED - Table missing'
    END as status;

-- ============================================================================
-- MIGRATION: 010_fix_transition_log_cascade.sql (Jan 16)
-- ============================================================================
SELECT
    '=== Migration 010: Fix Transition Log CASCADE (Jan 16) ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
            WHERE tc.table_name = 'fsm_transition_log'
            AND tc.constraint_name = 'fsm_transition_log_session_id_fkey'
            AND rc.delete_rule = 'SET NULL'
        ) THEN '✅ APPLIED - Foreign key uses ON DELETE SET NULL'
        ELSE '⚠️ CHECK NEEDED - Foreign key may need update'
    END as status;

-- ============================================================================
-- MIGRATION: database_migrations_v2.sql (Core tables)
-- ============================================================================

-- Check 1: conversation_sessions table
SELECT
    '=== Migration: database_migrations_v2.sql - Part 1 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'conversation_sessions'
        ) THEN '✅ APPLIED - conversation_sessions table exists'
        ELSE '❌ NOT APPLIED - Table missing'
    END as status;

-- Check 2: get_or_create_session function
SELECT
    '=== Migration: database_migrations_v2.sql - Part 2 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'get_or_create_session'
            AND n.nspname = 'public'
        ) THEN '✅ APPLIED - get_or_create_session function exists'
        ELSE '❌ NOT APPLIED - Function missing'
    END as status;

-- Check 3: should_create_new_session function
SELECT
    '=== Migration: database_migrations_v2.sql - Part 3 ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'should_create_new_session'
            AND n.nspname = 'public'
        ) THEN '✅ APPLIED - should_create_new_session function exists'
        ELSE '❌ NOT APPLIED - Function missing'
    END as status;

-- ============================================================================
-- MIGRATION: 011_add_unique_active_session_constraint.sql (Jan 17)
-- ============================================================================
SELECT
    '=== Migration 011: Unique Active Session Constraint (Jan 17) ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'conversation_sessions'
            AND indexname = 'idx_unique_active_session_per_user'
        ) THEN '✅ APPLIED - Unique constraint exists'
        ELSE '❌ NOT APPLIED - Need to run migration'
    END as status;

-- ============================================================================
-- MIGRATION: 012_add_session_rpc_debugging.sql (Jan 17)
-- ============================================================================
SELECT
    '=== Migration 012: RPC Debugging (Jan 17) ===' as check_name,
    CASE
        WHEN pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%'
        THEN '✅ APPLIED - RPC has debugging'
        ELSE '❌ NOT APPLIED - Need to run migration'
    END as status
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname = 'get_or_create_session'
AND n.nspname = 'public';

-- ============================================================================
-- SUMMARY: Count all checks
-- ============================================================================
SELECT
    '=== SUMMARY ===' as summary,
    'Check results above - All should show ✅ APPLIED' as instruction;

-- ============================================================================
-- BONUS: Show table counts to verify data integrity
-- ============================================================================
SELECT
    '=== Table Row Counts (for reference) ===' as info,
    (SELECT COUNT(*) FROM conversation_sessions) as conversation_sessions,
    (SELECT COUNT(*) FROM progress_update_sessions) as progress_update_sessions,
    (SELECT COUNT(*) FROM fsm_idempotency_records) as fsm_idempotency_records,
    (SELECT COUNT(*) FROM fsm_transition_log) as fsm_transition_log,
    (SELECT COUNT(*) FROM fsm_clarification_records) as fsm_clarification_records;
