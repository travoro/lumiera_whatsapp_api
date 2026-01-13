-- ============================================================================
-- Add Active Project Context to Subcontractors Table
-- ============================================================================
-- Tracks which project a subcontractor is currently working on
-- Expires after 7 hours of inactivity
-- ============================================================================

-- Add columns to subcontractors table
DO $$
BEGIN
    -- Add active_project_id column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'subcontractors' AND column_name = 'active_project_id'
    ) THEN
        ALTER TABLE subcontractors
        ADD COLUMN active_project_id UUID REFERENCES projects(id) ON DELETE SET NULL;

        RAISE NOTICE '✓ Added active_project_id column to subcontractors';
    ELSE
        RAISE NOTICE 'active_project_id column already exists';
    END IF;

    -- Add active_project_last_activity column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'subcontractors' AND column_name = 'active_project_last_activity'
    ) THEN
        ALTER TABLE subcontractors
        ADD COLUMN active_project_last_activity TIMESTAMP WITH TIME ZONE;

        RAISE NOTICE '✓ Added active_project_last_activity column to subcontractors';
    ELSE
        RAISE NOTICE 'active_project_last_activity column already exists';
    END IF;
END $$;

-- Create index for better query performance when filtering by active project
CREATE INDEX IF NOT EXISTS idx_subcontractors_active_project
    ON subcontractors(active_project_id)
    WHERE active_project_id IS NOT NULL;

-- Create index for expiration queries
CREATE INDEX IF NOT EXISTS idx_subcontractors_active_project_activity
    ON subcontractors(active_project_last_activity)
    WHERE active_project_last_activity IS NOT NULL;

-- ============================================================================
-- Helper Function: Check if Active Project is Expired
-- ============================================================================
-- Returns TRUE if the active project context has expired (>7 hours since last activity)

CREATE OR REPLACE FUNCTION is_active_project_expired(
    p_last_activity TIMESTAMP WITH TIME ZONE
) RETURNS BOOLEAN AS $$
BEGIN
    -- No last activity = expired
    IF p_last_activity IS NULL THEN
        RETURN TRUE;
    END IF;

    -- Check if more than 7 hours have passed
    RETURN (NOW() - p_last_activity) > INTERVAL '7 hours';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- Helper Function: Get Active Project for Subcontractor
-- ============================================================================
-- Returns active project ID if not expired, NULL otherwise

CREATE OR REPLACE FUNCTION get_active_project(
    p_subcontractor_id UUID
) RETURNS UUID AS $$
DECLARE
    v_active_project_id UUID;
    v_last_activity TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Get active project and last activity
    SELECT active_project_id, active_project_last_activity
    INTO v_active_project_id, v_last_activity
    FROM subcontractors
    WHERE id = p_subcontractor_id;

    -- Return NULL if no active project or if expired
    IF v_active_project_id IS NULL OR is_active_project_expired(v_last_activity) THEN
        RETURN NULL;
    END IF;

    RETURN v_active_project_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Helper Function: Set Active Project for Subcontractor
-- ============================================================================
-- Sets or updates the active project and resets the activity timestamp

CREATE OR REPLACE FUNCTION set_active_project(
    p_subcontractor_id UUID,
    p_project_id UUID
) RETURNS VOID AS $$
BEGIN
    UPDATE subcontractors
    SET
        active_project_id = p_project_id,
        active_project_last_activity = NOW(),
        updated_at = NOW()
    WHERE id = p_subcontractor_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Helper Function: Touch Active Project Activity
-- ============================================================================
-- Updates the last activity timestamp to keep the context alive

CREATE OR REPLACE FUNCTION touch_active_project(
    p_subcontractor_id UUID
) RETURNS VOID AS $$
BEGIN
    UPDATE subcontractors
    SET
        active_project_last_activity = NOW(),
        updated_at = NOW()
    WHERE id = p_subcontractor_id
      AND active_project_id IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Helper Function: Clear Active Project Context
-- ============================================================================
-- Clears the active project context for a subcontractor

CREATE OR REPLACE FUNCTION clear_active_project(
    p_subcontractor_id UUID
) RETURNS VOID AS $$
BEGIN
    UPDATE subcontractors
    SET
        active_project_id = NULL,
        active_project_last_activity = NULL,
        updated_at = NOW()
    WHERE id = p_subcontractor_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Cleanup Function: Clear Expired Active Projects
-- ============================================================================
-- Cleans up expired active project contexts (run periodically)

CREATE OR REPLACE FUNCTION cleanup_expired_active_projects()
RETURNS INTEGER AS $$
DECLARE
    v_cleared_count INTEGER;
BEGIN
    UPDATE subcontractors
    SET
        active_project_id = NULL,
        active_project_last_activity = NULL,
        updated_at = NOW()
    WHERE active_project_id IS NOT NULL
      AND is_active_project_expired(active_project_last_activity);

    GET DIAGNOSTICS v_cleared_count = ROW_COUNT;

    IF v_cleared_count > 0 THEN
        RAISE NOTICE '✓ Cleared % expired active project contexts', v_cleared_count;
    END IF;

    RETURN v_cleared_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Active Project Context Migration Complete';
    RAISE NOTICE '============================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Added columns:';
    RAISE NOTICE '  - active_project_id (UUID, FK to projects)';
    RAISE NOTICE '  - active_project_last_activity (TIMESTAMP)';
    RAISE NOTICE '';
    RAISE NOTICE 'Created functions:';
    RAISE NOTICE '  - is_active_project_expired(timestamp) -> boolean';
    RAISE NOTICE '  - get_active_project(subcontractor_id) -> project_id';
    RAISE NOTICE '  - set_active_project(subcontractor_id, project_id)';
    RAISE NOTICE '  - touch_active_project(subcontractor_id)';
    RAISE NOTICE '  - clear_active_project(subcontractor_id)';
    RAISE NOTICE '  - cleanup_expired_active_projects() -> count';
    RAISE NOTICE '';
    RAISE NOTICE 'Context expires after 7 hours of inactivity';
    RAISE NOTICE '============================================================';
END $$;
