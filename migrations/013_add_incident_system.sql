-- Migration 013: Add Incident Reporting System
-- Creates tables and functions for local incident storage

-- ============================================================================
-- Incidents Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subcontractor_id UUID NOT NULL REFERENCES subcontractors(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT,
    description TEXT,  -- Concatenated comments
    severity TEXT DEFAULT 'normal' CHECK (severity IN ('low', 'normal', 'high', 'critical')),
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    image_urls TEXT[],
    image_count INTEGER DEFAULT 0,
    comments_added INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    created_by UUID REFERENCES subcontractors(id),
    resolved_by UUID REFERENCES subcontractors(id)
);

-- ============================================================================
-- Incident Sessions Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS incident_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subcontractor_id UUID NOT NULL REFERENCES subcontractors(id) ON DELETE CASCADE,
    incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    images_uploaded INTEGER DEFAULT 0,
    comments_added INTEGER DEFAULT 0,
    fsm_state TEXT DEFAULT 'idle',
    current_step TEXT DEFAULT 'awaiting_project',
    session_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '2 hours',
    closure_reason TEXT,
    UNIQUE(subcontractor_id)  -- One active session per user
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_incidents_subcontractor ON incidents(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_incidents_project ON incidents(project_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at);
CREATE INDEX IF NOT EXISTS idx_incident_sessions_user ON incident_sessions(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_incident_sessions_expiry ON incident_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_incident_sessions_incident ON incident_sessions(incident_id);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to append an image URL to an incident
CREATE OR REPLACE FUNCTION append_incident_image(
    p_incident_id UUID,
    p_image_url TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE incidents
    SET
        image_urls = array_append(COALESCE(image_urls, ARRAY[]::TEXT[]), p_image_url),
        image_count = image_count + 1,
        updated_at = NOW()
    WHERE id = p_incident_id;
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to append a comment to an incident description
CREATE OR REPLACE FUNCTION append_incident_comment(
    p_incident_id UUID,
    p_comment TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE incidents
    SET
        description = CASE
            WHEN description IS NULL OR description = '' THEN p_comment
            ELSE description || E'\n\n' || p_comment
        END,
        comments_added = comments_added + 1,
        updated_at = NOW()
    WHERE id = p_incident_id;
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to update incident session activity
CREATE OR REPLACE FUNCTION update_incident_session_activity(
    p_subcontractor_id UUID
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE incident_sessions
    SET
        last_activity = NOW(),
        expires_at = NOW() + INTERVAL '2 hours'
    WHERE subcontractor_id = p_subcontractor_id
    AND expires_at > NOW();  -- Only update active sessions
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to get active incident session
CREATE OR REPLACE FUNCTION get_active_incident_session(
    p_subcontractor_id UUID
) RETURNS TABLE(
    id UUID,
    subcontractor_id UUID,
    incident_id UUID,
    project_id UUID,
    images_uploaded INTEGER,
    comments_added INTEGER,
    fsm_state TEXT,
    current_step TEXT,
    session_metadata JSONB,
    created_at TIMESTAMP,
    last_activity TIMESTAMP,
    expires_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id,
        s.subcontractor_id,
        s.incident_id,
        s.project_id,
        s.images_uploaded,
        s.comments_added,
        s.fsm_state,
        s.current_step,
        s.session_metadata,
        s.created_at,
        s.last_activity,
        s.expires_at
    FROM incident_sessions s
    WHERE s.subcontractor_id = p_subcontractor_id
    AND s.expires_at > NOW()
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE incidents IS 'Stores incident reports with descriptions, images, and status tracking';
COMMENT ON TABLE incident_sessions IS 'Tracks active multi-turn incident reporting sessions with 2-hour expiry';
COMMENT ON COLUMN incidents.description IS 'Concatenated comments added during the session';
COMMENT ON COLUMN incidents.image_urls IS 'Array of image URLs uploaded for this incident';
COMMENT ON COLUMN incident_sessions.session_metadata IS 'JSON metadata including expecting_response, last_bot_action, available_actions';
COMMENT ON COLUMN incident_sessions.expires_at IS 'Session expires 2 hours after last activity';
