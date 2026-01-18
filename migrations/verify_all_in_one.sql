-- All checks in ONE query result

SELECT
    -- Check 1
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'conversation_sessions'
    ) as "1_conversation_sessions_table",

    -- Check 2
    EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE p.proname = 'get_or_create_session'
        AND n.nspname = 'public'
    ) as "2_get_or_create_session_func",

    -- Check 3
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'conversation_sessions'
        AND indexname = 'idx_unique_active_session_per_user'
    ) as "3_unique_constraint",

    -- Check 4
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages'
        AND column_name = 'session_id'
    ) as "4_session_id_column",

    -- Check 5 (separate query for debugging check)
    (
        SELECT COUNT(*) > 0
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE p.proname = 'get_or_create_session'
        AND n.nspname = 'public'
        AND pg_get_functiondef(p.oid) LIKE '%RAISE NOTICE%'
    ) as "5_rpc_has_debugging";
