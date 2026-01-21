-- Migration: Fix FSM transition log to support both progress_update and incident sessions
-- Created: 2026-01-21
-- Description: Makes session_id nullable and removes foreign key constraint
--              to allow both progress_update_sessions and incident_sessions to use the log

-- ============================================================================
-- 1. Drop the foreign key constraint
-- ============================================================================

ALTER TABLE fsm_transition_log
DROP CONSTRAINT IF EXISTS fsm_transition_log_session_id_fkey;

-- ============================================================================
-- 2. Make session_id nullable (to support multiple session types)
-- ============================================================================

ALTER TABLE fsm_transition_log
ALTER COLUMN session_id DROP NOT NULL;

-- ============================================================================
-- 3. Add session_type column to distinguish session types
-- ============================================================================

ALTER TABLE fsm_transition_log
ADD COLUMN IF NOT EXISTS session_type TEXT DEFAULT 'progress_update'
    CHECK (session_type IN ('progress_update', 'incident', 'other'));

-- ============================================================================
-- 4. Add comment for documentation
-- ============================================================================

COMMENT ON COLUMN fsm_transition_log.session_id IS 'Session ID (UUID) - can reference progress_update_sessions.id or incident_sessions.id depending on session_type';
COMMENT ON COLUMN fsm_transition_log.session_type IS 'Type of session: progress_update, incident, or other';

-- ============================================================================
-- 5. Update cleanup function to keep incident transitions longer (90 days)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_expired_fsm_records()
RETURNS void AS $$
BEGIN
    -- Delete expired idempotency records
    DELETE FROM fsm_idempotency_records
    WHERE expires_at < NOW();

    -- Mark expired clarifications
    UPDATE fsm_clarification_requests
    SET status = 'expired'
    WHERE status = 'pending' AND expires_at < NOW();

    -- Archive old progress_update transition logs (keep 30 days)
    DELETE FROM fsm_transition_log
    WHERE created_at < NOW() - INTERVAL '30 days'
    AND session_type = 'progress_update';

    -- Archive old incident transition logs (keep 90 days for audit)
    DELETE FROM fsm_transition_log
    WHERE created_at < NOW() - INTERVAL '90 days'
    AND session_type = 'incident';

END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_fsm_records IS 'Cleans up expired idempotency records, clarifications, and old transition logs (30d for progress, 90d for incidents)';
