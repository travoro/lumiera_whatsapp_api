-- Migration: Add progress_update_sessions table for multi-step progress update feature
-- Created: 2026-01-15
-- Description: Track conversation state for progress update flows with session expiry

-- Create progress update sessions table
CREATE TABLE IF NOT EXISTS progress_update_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subcontractor_id UUID NOT NULL REFERENCES subcontractors(id) ON DELETE CASCADE,
    task_id UUID NOT NULL,
    project_id UUID NOT NULL,

    -- Action tracking
    images_uploaded INTEGER DEFAULT 0 CHECK (images_uploaded >= 0),
    comments_added INTEGER DEFAULT 0 CHECK (comments_added >= 0),
    status_changed BOOLEAN DEFAULT false,

    -- Conversation state
    current_step TEXT DEFAULT 'awaiting_action',
    awaiting_confirmation_for TEXT,
    pending_image_urls TEXT[],

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '2 hours',

    -- Constraints
    UNIQUE(subcontractor_id)  -- One active session per user
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_progress_sessions_user ON progress_update_sessions(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_progress_sessions_expiry ON progress_update_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_progress_sessions_task ON progress_update_sessions(task_id);

-- Add comments for documentation
COMMENT ON TABLE progress_update_sessions IS 'Tracks multi-step progress update conversation state with 2-hour expiration';
COMMENT ON COLUMN progress_update_sessions.subcontractor_id IS 'User performing the progress update (unique constraint ensures one active session per user)';
COMMENT ON COLUMN progress_update_sessions.task_id IS 'Task being updated';
COMMENT ON COLUMN progress_update_sessions.project_id IS 'Project ID (PlanRadar project ID)';
COMMENT ON COLUMN progress_update_sessions.images_uploaded IS 'Count of images uploaded in this session';
COMMENT ON COLUMN progress_update_sessions.comments_added IS 'Count of comments added in this session';
COMMENT ON COLUMN progress_update_sessions.status_changed IS 'Whether task status was changed to complete';
COMMENT ON COLUMN progress_update_sessions.current_step IS 'Current conversation step (awaiting_action, awaiting_image, awaiting_comment, etc.)';
COMMENT ON COLUMN progress_update_sessions.expires_at IS 'Session expiration time (2 hours from creation)';
