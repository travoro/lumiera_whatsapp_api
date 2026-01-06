-- Migration: Add whatsapp_templates table for tracking dynamic templates
-- This table tracks all dynamically created WhatsApp templates for cleanup

CREATE TABLE IF NOT EXISTS whatsapp_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_sid TEXT NOT NULL UNIQUE,
    template_type TEXT NOT NULL,
    friendly_name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted', 'deletion_failed')),
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Indexes
    CONSTRAINT whatsapp_templates_content_sid_key UNIQUE (content_sid)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_whatsapp_templates_status ON whatsapp_templates(status);
CREATE INDEX IF NOT EXISTS idx_whatsapp_templates_created_at ON whatsapp_templates(created_at);
CREATE INDEX IF NOT EXISTS idx_whatsapp_templates_template_type ON whatsapp_templates(template_type);

-- Create table for template usage tracking
CREATE TABLE IF NOT EXISTS template_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_sid TEXT NOT NULL,
    message_sid TEXT NOT NULL,
    to_number TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key
    FOREIGN KEY (content_sid) REFERENCES whatsapp_templates(content_sid) ON DELETE CASCADE
);

-- Create index for usage queries
CREATE INDEX IF NOT EXISTS idx_template_usage_content_sid ON template_usage(content_sid);
CREATE INDEX IF NOT EXISTS idx_template_usage_sent_at ON template_usage(sent_at);

-- Add comments
COMMENT ON TABLE whatsapp_templates IS 'Tracks dynamically created WhatsApp templates for automatic cleanup';
COMMENT ON TABLE template_usage IS 'Tracks template usage for analytics';

COMMENT ON COLUMN whatsapp_templates.content_sid IS 'Twilio Content SID (HX...)';
COMMENT ON COLUMN whatsapp_templates.template_type IS 'Type of template (twilio/list-picker, twilio/quick-reply, etc.)';
COMMENT ON COLUMN whatsapp_templates.status IS 'Template status (active, deleted, deletion_failed)';
COMMENT ON COLUMN whatsapp_templates.error_message IS 'Error message if deletion failed';
