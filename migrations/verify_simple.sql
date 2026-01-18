-- Simple verification - shows all results clearly

-- Check conversation_sessions table exists
SELECT
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'conversation_sessions'
    ) as conversation_sessions_exists;

-- Check get_or_create_session function exists
SELECT
    EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE p.proname = 'get_or_create_session'
        AND n.nspname = 'public'
    ) as get_or_create_session_exists;

-- Check unique constraint exists
SELECT
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'conversation_sessions'
        AND indexname = 'idx_unique_active_session_per_user'
    ) as unique_constraint_exists;

-- Check RPC has debugging
SELECT
    pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%' as rpc_has_debugging
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE p.proname = 'get_or_create_session'
AND n.nspname = 'public';

-- Check session_id column in messages
SELECT
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages'
        AND column_name = 'session_id'
    ) as session_id_column_exists;
