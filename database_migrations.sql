-- ============================================================================
-- Lumiera WhatsApp API - Database Migrations
-- ============================================================================
-- This file contains database schema updates for the Lumiera WhatsApp API
-- Run these in your Supabase SQL Editor
-- ============================================================================

-- ============================================================================
-- ACTION LOGS TABLE
-- ============================================================================
-- Tracks all agent actions for auditability and project evolution tracking
-- This helps understand how the project evolved over time

CREATE TABLE IF NOT EXISTS action_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID REFERENCES subcontractors(id) ON DELETE CASCADE,
    action_name TEXT NOT NULL,
    action_type TEXT NOT NULL, -- 'tool_call', 'api_request', 'escalation', etc.
    parameters JSONB,
    result JSONB,
    error TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_action_logs_subcontractor
    ON action_logs(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_action_logs_created_at
    ON action_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_logs_action_name
    ON action_logs(action_name);

-- ============================================================================
-- CONVERSATION SESSIONS TABLE (Optional - for better conversation tracking)
-- ============================================================================
-- Groups messages into conversation sessions for better context management

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID REFERENCES subcontractors(id) ON DELETE CASCADE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    summary TEXT,
    status TEXT DEFAULT 'active', -- 'active', 'ended', 'escalated'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_sessions_subcontractor
    ON conversation_sessions(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_conversation_sessions_status
    ON conversation_sessions(status);

-- ============================================================================
-- ESCALATIONS TABLE (Optional - if not using PlanRadar)
-- ============================================================================
-- Tracks escalations if not storing them in PlanRadar

CREATE TABLE IF NOT EXISTS escalations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID REFERENCES subcontractors(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    context JSONB,
    status TEXT DEFAULT 'pending', -- 'pending', 'in_progress', 'resolved'
    priority TEXT DEFAULT 'medium', -- 'low', 'medium', 'high', 'urgent'
    assigned_to TEXT,
    resolution_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_escalations_subcontractor
    ON escalations(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_escalations_status
    ON escalations(status);

-- ============================================================================
-- Add session_id to messages table (Optional - for session tracking)
-- ============================================================================
-- Links messages to conversation sessions

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'session_id'
    ) THEN
        ALTER TABLE messages ADD COLUMN session_id UUID REFERENCES conversation_sessions(id);
        CREATE INDEX idx_messages_session ON messages(session_id);
    END IF;
END $$;

-- ============================================================================
-- AGENT METRICS TABLE (Optional - for monitoring)
-- ============================================================================
-- Tracks agent performance metrics

CREATE TABLE IF NOT EXISTS agent_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID REFERENCES subcontractors(id) ON DELETE CASCADE,
    metric_type TEXT NOT NULL, -- 'response_time', 'token_usage', 'success_rate', etc.
    metric_value NUMERIC,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_metrics_type
    ON agent_metrics(metric_type);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_created_at
    ON agent_metrics(created_at DESC);

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================
-- Add RLS policies for security

-- Enable RLS on new tables
ALTER TABLE action_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_metrics ENABLE ROW LEVEL SECURITY;

-- Service role can access everything
CREATE POLICY "Service role can access action_logs" ON action_logs
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role can access conversation_sessions" ON conversation_sessions
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role can access escalations" ON escalations
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role can access agent_metrics" ON agent_metrics
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- Functions for maintenance
-- ============================================================================

-- Function to clean old action logs (keep last 90 days)
CREATE OR REPLACE FUNCTION cleanup_old_action_logs()
RETURNS void AS $$
BEGIN
    DELETE FROM action_logs
    WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- Function to update conversation session
CREATE OR REPLACE FUNCTION update_conversation_session()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.session_id IS NOT NULL THEN
        UPDATE conversation_sessions
        SET
            last_message_at = NOW(),
            message_count = message_count + 1,
            updated_at = NOW()
        WHERE id = NEW.session_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update conversation session on new message
DROP TRIGGER IF EXISTS trigger_update_conversation_session ON messages;
CREATE TRIGGER trigger_update_conversation_session
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_session();

-- ============================================================================
-- GRANTS
-- ============================================================================
-- Grant necessary permissions

GRANT ALL ON action_logs TO service_role;
GRANT ALL ON conversation_sessions TO service_role;
GRANT ALL ON escalations TO service_role;
GRANT ALL ON agent_metrics TO service_role;
