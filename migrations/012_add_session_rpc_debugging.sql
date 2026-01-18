-- ============================================================================
-- Session RPC Debugging Enhancement
-- ============================================================================
-- Adds RAISE NOTICE statements to get_or_create_session function for debugging
-- This helps diagnose why the function is creating new sessions so frequently
-- ============================================================================

-- Enhanced version with logging
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_subcontractor_id UUID
) RETURNS UUID AS $$
DECLARE
    v_active_session_id UUID;
    v_last_message_time TIMESTAMP WITH TIME ZONE;
    v_should_create_new BOOLEAN;
BEGIN
    -- Get active session
    SELECT id, last_message_at INTO v_active_session_id, v_last_message_time
    FROM conversation_sessions
    WHERE subcontractor_id = p_subcontractor_id
      AND status = 'active'
    ORDER BY started_at DESC
    LIMIT 1;

    -- Log what we found (using RAISE NOTICE for debugging)
    RAISE NOTICE '🔍 Session lookup for %: found=%, last_msg=%',
        p_subcontractor_id, v_active_session_id, v_last_message_time;

    -- Check if we should create new session
    v_should_create_new := should_create_new_session(p_subcontractor_id, v_last_message_time);

    RAISE NOTICE '🔍 Should create new: %', v_should_create_new;

    -- If should create new or no active session exists
    IF v_should_create_new OR v_active_session_id IS NULL THEN
        -- End previous session if exists
        IF v_active_session_id IS NOT NULL THEN
            UPDATE conversation_sessions
            SET status = 'ended',
                ended_at = NOW(),
                ended_reason = 'timeout',
                updated_at = NOW()
            WHERE id = v_active_session_id;

            RAISE NOTICE '🔚 Ended session: %', v_active_session_id;
        END IF;

        -- Create new session
        INSERT INTO conversation_sessions (subcontractor_id, started_at, last_message_at, status)
        VALUES (p_subcontractor_id, NOW(), NOW(), 'active')
        RETURNING id INTO v_active_session_id;

        RAISE NOTICE '✨ Created new session: %', v_active_session_id;
    ELSE
        RAISE NOTICE '♻️  Reusing session: %', v_active_session_id;
    END IF;

    RETURN v_active_session_id;
END;
$$ LANGUAGE plpgsql;

-- Verification
DO $$
BEGIN
    RAISE NOTICE '✅ Session RPC debugging enabled';
    RAISE NOTICE 'ℹ️  NOTICE messages will appear in PostgreSQL logs';
    RAISE NOTICE 'ℹ️  Check Supabase Dashboard > Logs > Postgres Logs';
END $$;
