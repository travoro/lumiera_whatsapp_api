-- Migration: FSM (Finite State Machine) support for session management
-- Created: 2026-01-16
-- Description: Adds FSM state management, idempotency, and clarification support

-- ============================================================================
-- 1. Extend progress_update_sessions with FSM columns
-- ============================================================================

-- Add FSM state column (replaces current_step with proper FSM states)
ALTER TABLE progress_update_sessions
ADD COLUMN IF NOT EXISTS fsm_state TEXT DEFAULT 'idle'
    CHECK (fsm_state IN (
        'idle',
        'task_selection',
        'awaiting_action',
        'collecting_data',
        'confirmation_pending',
        'completed',
        'abandoned'
    ));

-- Add closure reason for abandoned/completed sessions
ALTER TABLE progress_update_sessions
ADD COLUMN IF NOT EXISTS closure_reason TEXT;

-- Add session metadata (JSON for flexible context storage)
ALTER TABLE progress_update_sessions
ADD COLUMN IF NOT EXISTS session_metadata JSONB DEFAULT '{}'::jsonb;

-- Add transition history (for debugging and audit)
ALTER TABLE progress_update_sessions
ADD COLUMN IF NOT EXISTS transition_history JSONB DEFAULT '[]'::jsonb;

-- ============================================================================
-- 2. Create idempotency records table
-- ============================================================================

CREATE TABLE IF NOT EXISTS fsm_idempotency_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Idempotency key (user_id:message_id)
    idempotency_key TEXT NOT NULL UNIQUE,

    -- User and message info
    user_id TEXT NOT NULL,
    message_id TEXT NOT NULL,

    -- Processing result (cached for duplicate requests)
    result JSONB,

    -- Timestamps
    processed_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours',

    -- Indexes
    CONSTRAINT unique_idempotency_key UNIQUE(idempotency_key)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_idempotency_key ON fsm_idempotency_records(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_idempotency_user ON fsm_idempotency_records(user_id);
CREATE INDEX IF NOT EXISTS idx_idempotency_expiry ON fsm_idempotency_records(expires_at);

-- ============================================================================
-- 3. Create clarification requests table
-- ============================================================================

CREATE TABLE IF NOT EXISTS fsm_clarification_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User info
    user_id TEXT NOT NULL,

    -- Clarification details
    message TEXT NOT NULL,
    options JSONB NOT NULL,  -- Array of possible options

    -- Context snapshot (FSM state when clarification was requested)
    fsm_context JSONB NOT NULL,

    -- Status tracking
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'answered', 'expired', 'cancelled')),
    answer TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '5 minutes',
    answered_at TIMESTAMP,

    -- Constraint: One pending clarification per user
    CONSTRAINT unique_pending_clarification UNIQUE(user_id, status)
);

-- Partial unique index (only for pending clarifications)
CREATE UNIQUE INDEX IF NOT EXISTS idx_clarification_pending
    ON fsm_clarification_requests(user_id)
    WHERE status = 'pending';

-- Index for cleanup of expired clarifications
CREATE INDEX IF NOT EXISTS idx_clarification_expiry ON fsm_clarification_requests(expires_at)
    WHERE status = 'pending';

-- Index for user lookups
CREATE INDEX IF NOT EXISTS idx_clarification_user ON fsm_clarification_requests(user_id);

-- ============================================================================
-- 4. Create transition audit log (optional, for debugging)
-- ============================================================================

CREATE TABLE IF NOT EXISTS fsm_transition_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User and session info
    user_id TEXT NOT NULL,
    session_id UUID REFERENCES progress_update_sessions(id) ON DELETE CASCADE,

    -- Transition details
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    trigger TEXT NOT NULL,

    -- Result
    success BOOLEAN NOT NULL,
    error TEXT,

    -- Context snapshot
    context JSONB,

    -- Side effects executed
    side_effects JSONB DEFAULT '[]'::jsonb,

    -- Correlation ID for tracing
    correlation_id TEXT,

    -- Timestamp
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for querying
CREATE INDEX IF NOT EXISTS idx_transition_user ON fsm_transition_log(user_id);
CREATE INDEX IF NOT EXISTS idx_transition_session ON fsm_transition_log(session_id);
CREATE INDEX IF NOT EXISTS idx_transition_correlation ON fsm_transition_log(correlation_id);
CREATE INDEX IF NOT EXISTS idx_transition_timestamp ON fsm_transition_log(created_at);

-- ============================================================================
-- 5. Add comments for documentation
-- ============================================================================

COMMENT ON COLUMN progress_update_sessions.fsm_state IS 'FSM state: idle, task_selection, awaiting_action, collecting_data, confirmation_pending, completed, abandoned';
COMMENT ON COLUMN progress_update_sessions.closure_reason IS 'Reason for session closure: timeout, user_cancel, completed, error, etc.';
COMMENT ON COLUMN progress_update_sessions.session_metadata IS 'JSON metadata for FSM context (flexible storage)';
COMMENT ON COLUMN progress_update_sessions.transition_history IS 'Array of state transitions for audit trail';

COMMENT ON TABLE fsm_idempotency_records IS 'Prevents duplicate message processing via idempotency keys (user_id:message_id)';
COMMENT ON COLUMN fsm_idempotency_records.idempotency_key IS 'Unique key format: user_id:message_id';
COMMENT ON COLUMN fsm_idempotency_records.result IS 'Cached result for duplicate requests';

COMMENT ON TABLE fsm_clarification_requests IS 'Stores pending clarification requests when user intent is ambiguous';
COMMENT ON COLUMN fsm_clarification_requests.fsm_context IS 'Snapshot of FSM context when clarification was requested';
COMMENT ON COLUMN fsm_clarification_requests.expires_at IS 'Clarification expires after 5 minutes';

COMMENT ON TABLE fsm_transition_log IS 'Audit log of all FSM state transitions (for debugging and monitoring)';
COMMENT ON COLUMN fsm_transition_log.correlation_id IS 'Correlation ID for tracing related operations';

-- ============================================================================
-- 6. Data migration: Map existing current_step to fsm_state
-- ============================================================================

-- Map old current_step values to new fsm_state values
UPDATE progress_update_sessions
SET fsm_state = CASE
    WHEN current_step = 'awaiting_action' THEN 'awaiting_action'
    WHEN current_step = 'awaiting_image' THEN 'collecting_data'
    WHEN current_step = 'awaiting_comment' THEN 'collecting_data'
    WHEN current_step = 'awaiting_confirmation' THEN 'confirmation_pending'
    ELSE 'idle'
END
WHERE fsm_state = 'idle';  -- Only update if not already set

-- ============================================================================
-- 7. Create cleanup function for expired records
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

    -- Archive old transition logs (keep 30 days)
    DELETE FROM fsm_transition_log
    WHERE created_at < NOW() - INTERVAL '30 days';

END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_fsm_records IS 'Cleans up expired idempotency records, clarifications, and old transition logs';

-- Note: This function can be called by a scheduled job (pg_cron or external cron)
-- Example: SELECT cron.schedule('cleanup-fsm', '*/5 * * * *', 'SELECT cleanup_expired_fsm_records()');
