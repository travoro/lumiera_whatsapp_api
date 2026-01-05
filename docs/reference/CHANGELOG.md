# Changelog - Lumiera WhatsApp API

All notable changes to this project will be documented in this file.

## [2026-01-05] - Major Database Schema Update + Conversation Memory

### 🎯 Summary
Aligned the codebase with existing database schema and implemented intelligent conversation memory system for better user experience.

### ✅ Added

#### Conversation Memory System
- **Intelligent Memory Management**: Agent now remembers conversation history
  - Retrieves last 30 messages from database
  - Summarizes older messages to prevent context overflow
  - Keeps last 8 messages as-is for recent context
  - Uses Claude Haiku for fast, efficient summarization

- **New Service**: `src/services/memory.py`
  - `ConversationMemoryService` class
  - Smart summarization for long conversations
  - Optimized context management

#### Database Improvements
- **Migration File**: `database_migrations.sql`
  - `action_logs` table with enhanced schema
  - `conversation_sessions` table (optional)
  - `escalations` table (optional)
  - `agent_metrics` table (optional)
  - Indexes for performance
  - RLS policies for security
  - Maintenance functions

- **Action Logging Enhancements**
  - Added `action_type` field
  - Added `duration_ms` for performance tracking
  - Better documentation for evolution tracking
  - Changed to use `subcontractor_id`

#### Infrastructure
- Nginx SSL configuration (`whatsapp-api.lumiera.paris.conf`)
- Database schema check script (`check_db_schema.py`)
- Setup scripts for deployment

### 🔄 Changed

#### Database Schema Alignment
- **User Management**
  - Changed from `users` table → `subcontractors` table
  - Changed from `whatsapp_number` → `contact_telephone`

- **Messages Table**
  - `user_id` → `subcontractor_id`
  - `message_text` → `content`
  - `original_language` → `language`
  - `message_sid` → `twilio_sid`
  - Added: `message_type`, `media_type`, `status`, `source`

- **Media Storage**
  - Changed bucket: `whatsapp-media` → `conversations`

#### Code Updates
- `src/integrations/supabase.py`
  - Updated all database queries to use new schema
  - Added `get_conversation_history()` method
  - Added `get_recent_context()` method
  - Enhanced action logging

- `src/handlers/message.py`
  - Added conversation history retrieval
  - Integrated memory service
  - Convert messages to LangChain format
  - Pass chat history to agent

### 🐛 Fixed
- Agent no longer loses conversation context between messages
- Database queries now work with existing schema
- Media uploads now use correct storage bucket
- Action logs gracefully handle missing table (with warning)

### 📝 Migration Required

**IMPORTANT**: Run the following SQL in your Supabase SQL Editor:

```bash
# Copy and run the contents of database_migrations.sql in Supabase
```

This will create:
- `action_logs` table (required for tracking)
- `conversation_sessions` table (optional)
- `escalations` table (optional)
- `agent_metrics` table (optional)

### 🎯 Impact

#### For Users
- ✅ Agent remembers previous messages
- ✅ More contextual, intelligent responses
- ✅ Better handling of follow-up questions
- ✅ Seamless conversation flow

#### For Developers
- ✅ All actions logged for debugging
- ✅ Project evolution tracking
- ✅ Better understanding of user interactions
- ✅ Performance metrics available
- ✅ Conversation analytics possible

#### Performance
- 📉 Reduced token usage for long conversations (summarization)
- 📈 Better memory management
- ⚡ Fast summarization with Claude Haiku
- 🎯 Optimized context window usage

### 📊 Technical Details

#### Memory Architecture
```
Message Received
    ↓
Retrieve last 30 messages
    ↓
Check length > 8?
├─ YES → Summarize first 22, keep last 8
└─ NO  → Keep all messages
    ↓
Convert to LangChain format
    ↓
Pass to agent with context
    ↓
Agent responds (with memory!)
    ↓
Save message to DB
```

#### Action Logging
Every tool call, API request, and escalation is now logged with:
- Subcontractor ID
- Action name and type
- Input parameters
- Result/output
- Error (if any)
- Duration in milliseconds
- Timestamp

This enables:
- Full audit trail
- Project evolution analysis
- Performance monitoring
- Debugging and troubleshooting

### 🚀 Next Steps

1. **Run Database Migrations**
   ```sql
   -- Run database_migrations.sql in Supabase
   ```

2. **Test the Changes**
   - Send WhatsApp messages
   - Verify conversation memory works
   - Check action logs are being created
   - Monitor performance

3. **Optional Enhancements**
   - Enable conversation sessions
   - Set up agent metrics monitoring
   - Configure escalations workflow

### 🔗 Commit
- Commit: `28308fd`
- Branch: `main`
- Pushed to: `git@github.com:travoro/lumiera_whatsapp_api.git`

---

## How to Use This Changelog

This changelog follows [Keep a Changelog](https://keepachangelog.com/) principles:
- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes

Each entry includes:
- Date of change
- What changed
- Why it changed
- Impact on users/developers
- Migration steps if needed
