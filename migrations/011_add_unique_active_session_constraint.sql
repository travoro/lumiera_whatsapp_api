-- Migration: Add unique constraint for active conversation sessions
-- Created: 2026-01-17
-- Description: Prevents multiple active sessions per user (race condition fix)
-- Related: Phase 5 of session race condition remediation

-- ============================================================================
-- Problem:
-- Multiple concurrent get_or_create_session() calls could create duplicate
-- active sessions for the same user, causing context loss.
--
-- Solution:
-- Add partial unique index: only ONE active session per subcontractor.
-- Allows multiple ended/escalated sessions for history.
-- ============================================================================

-- Clean up any existing duplicate active sessions before adding constraint
-- Keep the most recent one, end the others
DO $$
DECLARE
    duplicate_record RECORD;
    kept_session_id UUID;
BEGIN
    -- Find users with multiple active sessions
    FOR duplicate_record IN
        SELECT subcontractor_id, COUNT(*) as count
        FROM conversation_sessions
        WHERE status = 'active'
        GROUP BY subcontractor_id
        HAVING COUNT(*) > 1
    LOOP
        RAISE NOTICE 'Found % active sessions for user %',
            duplicate_record.count, duplicate_record.subcontractor_id;

        -- Keep the most recent session (by last_message_at)
        SELECT id INTO kept_session_id
        FROM conversation_sessions
        WHERE subcontractor_id = duplicate_record.subcontractor_id
          AND status = 'active'
        ORDER BY last_message_at DESC
        LIMIT 1;

        RAISE NOTICE '  Keeping session: %', kept_session_id;

        -- End all other active sessions
        UPDATE conversation_sessions
        SET status = 'ended',
            ended_at = NOW(),
            ended_reason = 'duplicate_cleanup',
            updated_at = NOW()
        WHERE subcontractor_id = duplicate_record.subcontractor_id
          AND status = 'active'
          AND id != kept_session_id;

        RAISE NOTICE '  Ended duplicate sessions';
    END LOOP;
END $$;

-- Create partial unique index: only one active session per user
-- Partial index = constraint only applies WHERE status = 'active'
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_session_per_user
    ON conversation_sessions(subcontractor_id)
    WHERE status = 'active';

-- Add comment for documentation
COMMENT ON INDEX idx_unique_active_session_per_user IS
    'Ensures only one active session per subcontractor. Partial index allows multiple ended/escalated sessions for history.';

-- Log success
DO $$
BEGIN
    RAISE NOTICE '✅ Added unique constraint for active conversation sessions';
    RAISE NOTICE '   Database will now prevent duplicate active sessions';
END $$;
