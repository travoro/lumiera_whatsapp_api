-- ============================================================================
-- SESSION RACE CONDITION FIX - REQUIRED MIGRATIONS ONLY
-- ============================================================================
-- This checks ONLY the migrations needed for the session race fix
-- Skips FSM tables (009, 010) as they're for a different feature
-- ============================================================================

-- Check 1: conversation_sessions table (CRITICAL)
SELECT
    '1. conversation_sessions table' as check_item,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'conversation_sessions'
        ) THEN '✅ EXISTS'
        ELSE '❌ MISSING - Need database_migrations_v2.sql'
    END as status;

-- Check 2: get_or_create_session function (CRITICAL)
SELECT
    '2. get_or_create_session function' as check_item,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'get_or_create_session'
            AND n.nspname = 'public'
        ) THEN '✅ EXISTS'
        ELSE '❌ MISSING - Need database_migrations_v2.sql'
    END as status;

-- Check 3: should_create_new_session function (CRITICAL)
SELECT
    '3. should_create_new_session function' as check_item,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE p.proname = 'should_create_new_session'
            AND n.nspname = 'public'
        ) THEN '✅ EXISTS'
        ELSE '❌ MISSING - Need database_migrations_v2.sql'
    END as status;

-- Check 4: Unique constraint on active sessions (CRITICAL - Phase 5)
SELECT
    '4. Unique active session constraint' as check_item,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE tablename = 'conversation_sessions'
            AND indexname = 'idx_unique_active_session_per_user'
        ) THEN '✅ EXISTS'
        ELSE '❌ MISSING - Need 011_add_unique_active_session_constraint.sql'
    END as status;

-- Check 5: RPC function has debugging (CRITICAL)
SELECT
    '5. RPC debugging (RAISE NOTICE)' as check_item,
    CASE
        WHEN pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%'
        THEN '✅ EXISTS'
        ELSE '❌ MISSING - Need 012_add_session_rpc_debugging.sql'
    END as status
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname = 'get_or_create_session'
AND n.nspname = 'public';

-- Check 6: session_id column in messages table (CRITICAL)
SELECT
    '6. session_id column in messages' as check_item,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'messages'
            AND column_name = 'session_id'
        ) THEN '✅ EXISTS'
        ELSE '❌ MISSING - Need database_migrations_v2.sql'
    END as status;

-- ============================================================================
-- SUMMARY
-- ============================================================================
SELECT
    '=== RESULT ===' as summary,
    CASE
        WHEN (
            -- All checks must pass
            EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'conversation_sessions')
            AND EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = 'get_or_create_session' AND n.nspname = 'public')
            AND EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'conversation_sessions' AND indexname = 'idx_unique_active_session_per_user')
            AND EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = 'get_or_create_session' AND n.nspname = 'public' AND pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%')
        ) THEN '✅ ALL REQUIRED MIGRATIONS APPLIED - Ready to deploy code!'
        ELSE '❌ SOME MIGRATIONS MISSING - See above for which ones'
    END as overall_status;

-- ============================================================================
-- BONUS: Check for duplicate active sessions
-- ============================================================================
SELECT
    '=== Duplicate Check ===' as bonus_check,
    COUNT(*) as duplicate_count,
    CASE
        WHEN COUNT(*) = 0 THEN '✅ No duplicate active sessions'
        ELSE '⚠️ Duplicates exist - 011 migration will clean them'
    END as status
FROM (
    SELECT subcontractor_id, COUNT(*) as cnt
    FROM conversation_sessions
    WHERE status = 'active'
    GROUP BY subcontractor_id
    HAVING COUNT(*) > 1
) dupes;
