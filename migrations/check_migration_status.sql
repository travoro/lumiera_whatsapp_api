-- ============================================================================
-- Check Migration Status - Session Race Condition Fixes
-- ============================================================================
-- Run this in Supabase Dashboard > SQL Editor to verify migrations
-- ============================================================================

-- Check 1: Does the unique constraint index exist? (Migration 011)
SELECT
    '=== Migration 011: Unique Constraint ===' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'conversation_sessions'
            AND indexname = 'idx_unique_active_session_per_user'
        ) THEN '✅ APPLIED - Unique constraint exists'
        ELSE '❌ NOT APPLIED - Unique constraint missing'
    END as status;

-- Check 2: Show the index definition if it exists
SELECT
    '=== Index Details ===' as info,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'conversation_sessions'
AND indexname = 'idx_unique_active_session_per_user';

-- Check 3: Test if RPC function has debugging (Migration 012)
-- We can't directly check for RAISE NOTICE, but we can see when function was last modified
SELECT
    '=== Migration 012: RPC Debugging ===' as check_name,
    p.proname as function_name,
    pg_get_functiondef(p.oid) as function_definition
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname = 'get_or_create_session'
AND n.nspname = 'public';

-- Check 4: Are there any duplicate active sessions right now?
SELECT
    '=== Duplicate Active Sessions Check ===' as check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✅ NO DUPLICATES - Database is clean'
        ELSE '⚠️ DUPLICATES FOUND - See details below'
    END as status
FROM (
    SELECT subcontractor_id, COUNT(*) as count
    FROM conversation_sessions
    WHERE status = 'active'
    GROUP BY subcontractor_id
    HAVING COUNT(*) > 1
) duplicates;

-- Check 5: Show any duplicate active sessions (if they exist)
SELECT
    '=== Duplicate Sessions Details ===' as info,
    subcontractor_id,
    COUNT(*) as active_session_count,
    array_agg(id) as session_ids,
    array_agg(created_at ORDER BY created_at) as created_times
FROM conversation_sessions
WHERE status = 'active'
GROUP BY subcontractor_id
HAVING COUNT(*) > 1;

-- Check 6: Recent session activity (last 1 hour)
SELECT
    '=== Recent Session Activity ===' as info,
    COUNT(*) as total_sessions_created,
    COUNT(DISTINCT subcontractor_id) as unique_users,
    COUNT(*) / NULLIF(COUNT(DISTINCT subcontractor_id), 0) as avg_sessions_per_user
FROM conversation_sessions
WHERE created_at > NOW() - INTERVAL '1 hour';

-- Check 7: Session status distribution
SELECT
    '=== Session Status Distribution ===' as info,
    status,
    COUNT(*) as count
FROM conversation_sessions
GROUP BY status
ORDER BY count DESC;
