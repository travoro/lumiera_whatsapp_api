#!/bin/bash
# Quick verification script for session race condition fix migrations

echo "============================================================================"
echo "SESSION RACE CONDITION FIX - MIGRATION STATUS CHECK"
echo "============================================================================"
echo ""
echo "This script will help you verify if the database migrations are applied."
echo ""
echo "============================================================================"
echo "INSTRUCTIONS:"
echo "============================================================================"
echo ""
echo "1. Go to Supabase Dashboard: https://supabase.com/dashboard"
echo "2. Navigate to your project"
echo "3. Click 'SQL Editor' in the left sidebar"
echo "4. Copy and paste the queries below (one at a time)"
echo "5. Check the results"
echo ""
echo "============================================================================"
echo "QUERY 1: Check if Migration 011 (Unique Constraint) is applied"
echo "============================================================================"
echo ""
cat << 'EOF'
SELECT
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'conversation_sessions'
            AND indexname = 'idx_unique_active_session_per_user'
        ) THEN '✅ MIGRATION 011 APPLIED - Unique constraint exists'
        ELSE '❌ MIGRATION 011 NOT APPLIED - Need to run migration'
    END as migration_011_status;
EOF
echo ""
echo "Expected result: '✅ MIGRATION 011 APPLIED'"
echo ""
echo "============================================================================"
echo "QUERY 2: Check if Migration 012 (RPC Debugging) is applied"
echo "============================================================================"
echo ""
cat << 'EOF'
SELECT
    CASE
        WHEN pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%'
        THEN '✅ MIGRATION 012 APPLIED - RPC has debugging'
        ELSE '❌ MIGRATION 012 NOT APPLIED - Need to run migration'
    END as migration_012_status
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname = 'get_or_create_session'
AND n.nspname = 'public';
EOF
echo ""
echo "Expected result: '✅ MIGRATION 012 APPLIED'"
echo ""
echo "============================================================================"
echo "QUERY 3: Check for duplicate active sessions (should be 0)"
echo "============================================================================"
echo ""
cat << 'EOF'
SELECT
    subcontractor_id,
    COUNT(*) as active_session_count
FROM conversation_sessions
WHERE status = 'active'
GROUP BY subcontractor_id
HAVING COUNT(*) > 1;
EOF
echo ""
echo "Expected result: 0 rows (no duplicates)"
echo ""
echo "============================================================================"
echo "SUMMARY"
echo "============================================================================"
echo ""
echo "If BOTH migrations show ✅ and NO duplicate sessions → You're all set! ✅"
echo "If either shows ❌ → Need to apply that migration"
echo ""
echo "Migration files are located at:"
echo "  - migrations/011_add_unique_active_session_constraint.sql"
echo "  - migrations/012_add_session_rpc_debugging.sql"
echo ""
echo "============================================================================"
