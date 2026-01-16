-- Migration: Fix fsm_transition_log CASCADE DELETE
-- Created: 2026-01-16
-- Description: Remove ON DELETE CASCADE to preserve audit logs after session deletion
-- Issue: Transition logs were being deleted when sessions were deleted, defeating audit purpose

-- ============================================================================
-- 1. Drop existing foreign key constraint
-- ============================================================================

ALTER TABLE fsm_transition_log
DROP CONSTRAINT IF EXISTS fsm_transition_log_session_id_fkey;

-- ============================================================================
-- 2. Add new foreign key constraint WITHOUT CASCADE
-- ============================================================================

-- ON DELETE SET NULL: When session is deleted, keep the transition log but null out session_id
-- This preserves the audit trail while allowing session cleanup
ALTER TABLE fsm_transition_log
ADD CONSTRAINT fsm_transition_log_session_id_fkey
    FOREIGN KEY (session_id)
    REFERENCES progress_update_sessions(id)
    ON DELETE SET NULL;

-- ============================================================================
-- 3. Add comment explaining the change
-- ============================================================================

COMMENT ON CONSTRAINT fsm_transition_log_session_id_fkey ON fsm_transition_log IS
'Foreign key to progress_update_sessions with ON DELETE SET NULL to preserve audit logs after session deletion';

-- ============================================================================
-- Purpose: Audit logs should be permanent
-- ============================================================================
--
-- Transition logs are for debugging, analytics, and audit compliance.
-- They should NOT be deleted when sessions are cleaned up.
--
-- Before: ON DELETE CASCADE → transitions deleted with session
-- After:  ON DELETE SET NULL → transitions preserved, session_id nulled
--
-- This allows us to:
-- - Debug issues after sessions expire/complete
-- - Analyze user behavior patterns over time
-- - Meet audit/compliance requirements
-- - Track session lifetime and abandonment rates
--
