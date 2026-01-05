-- Migration: Add active column to projects table
-- Date: 2026-01-05
-- Description: Add the missing 'active' column to projects table for filtering active/inactive projects

-- Add active column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'projects'
        AND column_name = 'active'
    ) THEN
        ALTER TABLE projects
        ADD COLUMN active BOOLEAN DEFAULT true;

        RAISE NOTICE 'Added active column to projects table';

        -- Set all existing projects to active
        UPDATE projects SET active = true WHERE active IS NULL;

        RAISE NOTICE 'Set all existing projects to active=true';
    ELSE
        RAISE NOTICE 'Column active already exists in projects table';
    END IF;
END $$;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(active);

COMMENT ON COLUMN projects.active IS 'Flag to indicate if project is currently active';
