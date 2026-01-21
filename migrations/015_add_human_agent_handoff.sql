-- Migration 015: Add human agent handoff fields to subcontractors table
-- Purpose: Allow human agents to take over conversations from bot
-- When human agent is active, bot only saves messages without processing

-- Add handoff fields to subcontractors table
ALTER TABLE subcontractors
ADD COLUMN IF NOT EXISTS human_agent_active BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS human_agent_since TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS human_agent_expires_at TIMESTAMP WITH TIME ZONE;

-- Create index for fast lookups when checking handoff status
CREATE INDEX IF NOT EXISTS idx_subcontractors_human_agent
ON subcontractors(human_agent_active, human_agent_expires_at)
WHERE human_agent_active = true;

-- Add helpful comments for documentation
COMMENT ON COLUMN subcontractors.human_agent_active IS
'True when human agent has taken over conversation. Bot will only save messages without processing.';

COMMENT ON COLUMN subcontractors.human_agent_since IS
'Timestamp when human agent first took over. Updated on every agent message to track activity.';

COMMENT ON COLUMN subcontractors.human_agent_expires_at IS
'When handoff expires (human_agent_since + 7 hours). Bot resumes normal processing after this time.';

-- Verification query
DO $$
BEGIN
    -- Check if columns were added successfully
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'subcontractors'
        AND column_name = 'human_agent_active'
    ) THEN
        RAISE NOTICE '✅ Migration 015 completed successfully';
        RAISE NOTICE '   - Added human_agent_active column';
        RAISE NOTICE '   - Added human_agent_since column';
        RAISE NOTICE '   - Added human_agent_expires_at column';
        RAISE NOTICE '   - Created index idx_subcontractors_human_agent';
    ELSE
        RAISE EXCEPTION '❌ Migration 015 failed: Columns not created';
    END IF;
END $$;
