-- Create templates table for storing WhatsApp interactive message templates
CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name VARCHAR(100) NOT NULL, -- e.g., 'greeting_menu', 'main_menu'
    language VARCHAR(10) NOT NULL, -- e.g., 'fr', 'en', 'es'
    twilio_content_sid VARCHAR(100) NOT NULL, -- Twilio Content SID
    template_type VARCHAR(50) DEFAULT 'list_picker', -- 'list_picker', 'quick_reply', etc.
    description TEXT, -- Optional description
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure unique combination of template_name and language
    UNIQUE(template_name, language)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_templates_name_language ON templates(template_name, language);
CREATE INDEX IF NOT EXISTS idx_templates_active ON templates(is_active);

-- Add comment
COMMENT ON TABLE templates IS 'Stores WhatsApp interactive message templates with Twilio Content SIDs';
