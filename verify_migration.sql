-- Verification script for FSM migration
-- Run this to verify the migration was successful

-- 1. Check FSM tables were created
\echo '=== Checking FSM Tables ==='
SELECT tablename FROM pg_tables
WHERE schemaname = 'public' AND tablename LIKE 'fsm_%'
ORDER BY tablename;

-- 2. Check progress_update_sessions columns were added
\echo ''
\echo '=== Checking progress_update_sessions Columns ==='
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'progress_update_sessions'
AND column_name IN ('fsm_state', 'closure_reason', 'session_metadata', 'transition_history')
ORDER BY column_name;

-- 3. Check cleanup function exists
\echo ''
\echo '=== Checking Cleanup Function ==='
SELECT routine_name FROM information_schema.routines
WHERE routine_name = 'cleanup_expired_fsm_records';

-- 4. Count records in each FSM table (should be 0 initially)
\echo ''
\echo '=== Checking FSM Table Counts ==='
SELECT 'fsm_idempotency_records' as table_name, COUNT(*) as count FROM fsm_idempotency_records
UNION ALL
SELECT 'fsm_clarification_requests', COUNT(*) FROM fsm_clarification_requests
UNION ALL
SELECT 'fsm_transition_log', COUNT(*) FROM fsm_transition_log;

-- 5. Test the cleanup function
\echo ''
\echo '=== Testing Cleanup Function ==='
SELECT cleanup_expired_fsm_records() as cleanup_result;

\echo ''
\echo '=== Verification Complete ==='
\echo 'Expected results:'
\echo '- 3 FSM tables (idempotency_records, clarification_requests, transition_log)'
\echo '- 4 new columns in progress_update_sessions'
\echo '- cleanup_expired_fsm_records function exists'
\echo '- All counts should be 0 initially'
\echo '- Cleanup function returns success message'
