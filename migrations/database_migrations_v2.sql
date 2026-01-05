-- ============================================================================
-- Lumiera WhatsApp API - Production Enhancements (v2)
-- ============================================================================
-- Run these migrations after database_migrations.sql
-- ============================================================================

-- ============================================================================
-- CONVERSATION SESSIONS TABLE
-- ============================================================================
-- Smart session management based on working hours (6-7 AM to 8 PM)
-- New session if > 7 hours between messages (one chantier per day)

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID NOT NULL REFERENCES subcontractors(id) ON DELETE CASCADE,

    -- Session timing
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,

    -- Session metadata
    message_count INTEGER DEFAULT 0,
    session_summary TEXT,  -- Auto-generated summary when session ends

    -- Session status
    status TEXT DEFAULT 'active',  -- 'active', 'ended', 'escalated'
    ended_reason TEXT,  -- 'timeout', 'end_of_day', 'escalation', 'user_request'

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes for performance
    CONSTRAINT valid_status CHECK (status IN ('active', 'ended', 'escalated'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_subcontractor
    ON conversation_sessions(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status
    ON conversation_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_dates
    ON conversation_sessions(subcontractor_id, started_at DESC);

-- Add session_id to messages table
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
-- USER CONTEXT TABLE
-- ============================================================================
-- Store learned facts, preferences, and frequently mentioned entities

CREATE TABLE IF NOT EXISTS user_context (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID NOT NULL REFERENCES subcontractors(id) ON DELETE CASCADE,

    -- Context data
    context_key TEXT NOT NULL,  -- 'current_project', 'preferred_language_style', etc.
    context_value TEXT NOT NULL,
    context_type TEXT NOT NULL,  -- 'preference', 'fact', 'entity', 'state'

    -- Metadata
    confidence FLOAT DEFAULT 1.0,  -- 0.0 to 1.0
    source TEXT NOT NULL,  -- 'user_stated', 'inferred', 'system', 'tool'
    metadata JSONB DEFAULT '{}',  -- Additional structured data

    -- Expiry
    expires_at TIMESTAMP WITH TIME ZONE,  -- Optional expiry for temporary context

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint per user + key
    CONSTRAINT unique_user_context UNIQUE(subcontractor_id, context_key),

    -- Validation
    CONSTRAINT valid_context_type CHECK (context_type IN ('preference', 'fact', 'entity', 'state')),
    CONSTRAINT valid_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_context_subcontractor
    ON user_context(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_user_context_type
    ON user_context(context_type);
CREATE INDEX IF NOT EXISTS idx_user_context_expiry
    ON user_context(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================================================
-- INTENT CLASSIFICATION LOG
-- ============================================================================
-- Track intent classification for analytics and monitoring

CREATE TABLE IF NOT EXISTS intent_classifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subcontractor_id UUID REFERENCES subcontractors(id) ON DELETE CASCADE,
    session_id UUID REFERENCES conversation_sessions(id) ON DELETE CASCADE,

    -- Classification data
    message_text TEXT NOT NULL,
    classified_intent TEXT NOT NULL,
    confidence FLOAT,
    classification_method TEXT,  -- 'keyword', 'llm', 'hybrid'

    -- Timing
    classification_duration_ms INTEGER,

    -- Metadata
    model_used TEXT,  -- 'haiku', 'opus', etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_intent_subcontractor
    ON intent_classifications(subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_intent_intent
    ON intent_classifications(classified_intent);
CREATE INDEX IF NOT EXISTS idx_intent_created
    ON intent_classifications(created_at DESC);

-- ============================================================================
-- FUNCTIONS FOR SESSION MANAGEMENT
-- ============================================================================

-- Function to determine if new session should be created
CREATE OR REPLACE FUNCTION should_create_new_session(
    p_subcontractor_id UUID,
    p_last_message_time TIMESTAMP WITH TIME ZONE
) RETURNS BOOLEAN AS $$
DECLARE
    v_hours_diff FLOAT;
    v_last_message_hour INTEGER;
    v_current_hour INTEGER;
BEGIN
    -- No previous message - create new session
    IF p_last_message_time IS NULL THEN
        RETURN TRUE;
    END IF;

    -- Calculate hours difference
    v_hours_diff := EXTRACT(EPOCH FROM (NOW() - p_last_message_time)) / 3600;

    -- If more than 7 hours - new session (subcontractor moved to new chantier)
    IF v_hours_diff > 7 THEN
        RETURN TRUE;
    END IF;

    -- Check working hours (6-7 AM to 8 PM)
    v_last_message_hour := EXTRACT(HOUR FROM p_last_message_time);
    v_current_hour := EXTRACT(HOUR FROM NOW());

    -- If last message was after 8 PM and current is after 6 AM - new day, new session
    IF v_last_message_hour >= 20 AND v_current_hour >= 6 THEN
        RETURN TRUE;
    END IF;

    -- If last message was before 6 AM and current is after 6 AM - new session
    IF v_last_message_hour < 6 AND v_current_hour >= 6 THEN
        RETURN TRUE;
    END IF;

    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Function to get or create session
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_subcontractor_id UUID
) RETURNS UUID AS $$
DECLARE
    v_active_session_id UUID;
    v_last_message_time TIMESTAMP WITH TIME ZONE;
    v_should_create_new BOOLEAN;
BEGIN
    -- Get active session
    SELECT id, last_message_at INTO v_active_session_id, v_last_message_time
    FROM conversation_sessions
    WHERE subcontractor_id = p_subcontractor_id
      AND status = 'active'
    ORDER BY started_at DESC
    LIMIT 1;

    -- Check if we should create new session
    v_should_create_new := should_create_new_session(p_subcontractor_id, v_last_message_time);

    -- If should create new or no active session exists
    IF v_should_create_new OR v_active_session_id IS NULL THEN
        -- End previous session if exists
        IF v_active_session_id IS NOT NULL THEN
            UPDATE conversation_sessions
            SET status = 'ended',
                ended_at = NOW(),
                ended_reason = 'timeout',
                updated_at = NOW()
            WHERE id = v_active_session_id;
        END IF;

        -- Create new session
        INSERT INTO conversation_sessions (subcontractor_id, started_at, last_message_at)
        VALUES (p_subcontractor_id, NOW(), NOW())
        RETURNING id INTO v_active_session_id;
    END IF;

    RETURN v_active_session_id;
END;
$$ LANGUAGE plpgsql;

-- Function to update session on new message
CREATE OR REPLACE FUNCTION update_session_on_message()
RETURNS TRIGGER AS $$
BEGIN
    -- Update session metadata
    UPDATE conversation_sessions
    SET
        last_message_at = NOW(),
        message_count = message_count + 1,
        updated_at = NOW()
    WHERE id = NEW.session_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update session
DROP TRIGGER IF EXISTS trigger_update_session_on_message ON messages;
CREATE TRIGGER trigger_update_session_on_message
    AFTER INSERT ON messages
    FOR EACH ROW
    WHEN (NEW.session_id IS NOT NULL)
    EXECUTE FUNCTION update_session_on_message();

-- ============================================================================
-- CLEANUP FUNCTIONS
-- ============================================================================

-- Function to cleanup expired context
CREATE OR REPLACE FUNCTION cleanup_expired_context()
RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
BEGIN
    DELETE FROM user_context
    WHERE expires_at IS NOT NULL
      AND expires_at < NOW();

    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to generate session summary
CREATE OR REPLACE FUNCTION generate_session_summary(p_session_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_summary TEXT;
    v_message_count INTEGER;
    v_intent_counts JSONB;
BEGIN
    -- Get message count
    SELECT COUNT(*) INTO v_message_count
    FROM messages
    WHERE session_id = p_session_id;

    -- Get intent distribution
    SELECT json_object_agg(classified_intent, count)::jsonb INTO v_intent_counts
    FROM (
        SELECT classified_intent, COUNT(*) as count
        FROM intent_classifications
        WHERE session_id = p_session_id
        GROUP BY classified_intent
    ) intents;

    -- Build summary
    v_summary := format(
        'Session with %s messages. Intents: %s',
        v_message_count,
        COALESCE(v_intent_counts::text, 'none')
    );

    RETURN v_summary;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable RLS on new tables
ALTER TABLE conversation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE intent_classifications ENABLE ROW LEVEL SECURITY;

-- Service role can access everything
CREATE POLICY "Service role full access to sessions" ON conversation_sessions
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to user_context" ON user_context
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to intent_classifications" ON intent_classifications
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- GRANTS
-- ============================================================================

GRANT ALL ON conversation_sessions TO service_role;
GRANT ALL ON user_context TO service_role;
GRANT ALL ON intent_classifications TO service_role;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify tables were created
DO $$
BEGIN
    RAISE NOTICE 'Verifying tables...';

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'conversation_sessions') THEN
        RAISE NOTICE '✓ conversation_sessions table created';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_context') THEN
        RAISE NOTICE '✓ user_context table created';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'intent_classifications') THEN
        RAISE NOTICE '✓ intent_classifications table created';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'messages' AND column_name = 'session_id') THEN
        RAISE NOTICE '✓ session_id column added to messages';
    END IF;
END $$;
