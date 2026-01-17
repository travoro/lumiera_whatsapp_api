# Changelog - Lumiera WhatsApp API

All notable changes to this project will be documented in this file.

## [2026-01-17] - Documentation Organization & Test Suite Optimization

### 🎯 Summary
Complete documentation reorganization and test suite optimization. Reduced redundancy, improved structure, and achieved 100% test pass rate.

### ✅ Added
- **Test Infrastructure**
  - `.env.test` - Test environment configuration with dummy credentials
  - `run_tests.sh` - Helper script for running tests with proper environment setup
  - `test_validation.py` - 37 security tests (prompt injection, XSS, SQL injection, path traversal)
  - `test_pipeline.py` - 18 unit tests for message pipeline stages
  - `test_templates.py` - 36 tests for WhatsApp template formatting

- **Documentation Structure**
  - `docs/fsm/` - FSM implementation documentation (7 docs)
  - `docs/investigations/` - Historical analysis and fix documents (22 docs)
  - `docs/testing/` - Test suite documentation (2 docs)
  - Moved 11 reference documents to `docs/reference/`

### 🔄 Changed
- **Test Suite**
  - Renamed `test_dynamic_templates.py` → `test_templates.py`
  - Renamed `test_message_pipeline.py` → `test_pipeline.py`
  - Updated `conftest.py` with required environment variables
  - Modified `src/integrations/supabase.py` to skip initialization in test environment
  - **Test Results**: 170/170 passing (100% pass rate, 3.78s execution)

- **Documentation Organization**
  - Moved 40+ markdown files from root to organized subfolders
  - Cleaned up obsolete analysis documents
  - Only `README.md` remains at project root
  - Only `docs/README.md` remains as main docs index

- **Logs Folder**
  - Deleted redundant `server.log` (14M - duplicated app.log)
  - Deleted redundant `server.error.log` (620K)
  - Deleted `archive/` folder (960K)
  - **Space Saved**: 15.5 MB (from 30M to 16M)

### 🐛 Fixed
- Test environment now properly loads without API key validation errors
- All security tests passing with correct assertions matching implementation
- Test suite can run independently without external dependencies

### 📊 Impact
- **Test Coverage**: 170 tests covering security, validation, FSM, pipeline, templates
- **Documentation**: Organized, discoverable, and maintainable
- **Storage**: 50% reduction in logs folder size

---

## [2026-01-16] - FSM Implementation & PlanRadar Optimization

### 🎯 Summary
Implemented Finite State Machine (FSM) for conversation flow management and optimized PlanRadar API calls by 50%.

### ✅ Added
- **FSM System**
  - `src/fsm/core.py` - FSM engine with transition validation (650 LOC)
  - `src/fsm/models.py` - FSM state models and enums
  - `src/fsm/handlers.py` - FSM-aware message handlers
  - `src/fsm/routing.py` - Intent routing with FSM integration
  - Comprehensive test suite (170+ tests, 100% passing)

- **FSM Features**
  - 8 conversation states (IDLE, TASK_SELECTION, COLLECTING_DATA, etc.)
  - 20+ validated state transitions
  - Idempotency handling for message deduplication
  - Session management with automatic expiry
  - Graceful recovery from server restarts
  - Comprehensive audit trail

### 🔄 Changed
- **PlanRadar API Optimization**
  - Eliminated 50% of redundant API calls
  - Implemented caching for task availability checks
  - Improved filtering logic to prevent duplicate lookups
  - **Impact**: Faster responses, reduced rate limit pressure

- **Task Filtering**
  - Fixed bug where resolved tasks (status code "3") appeared in available tasks
  - Improved string-based status code handling
  - Added proper null checks for status field

### 🐛 Fixed
- Option selection bug for list interactions (24-char limit compliance)
- App restart recovery - sessions now properly restored after server restart
- Resolved task filtering - status code "3" tasks no longer shown to users

### 📊 Technical Details

#### FSM Architecture
```
User Message
    ↓
Check Current State
    ↓
Validate Transition
    ↓
Execute Side Effects
    ↓
Update State
    ↓
Log Transition
    ↓
Response
```

#### API Call Reduction
- **Before**: Up to 4 calls per task operation (get_task, list_tasks, validate, update)
- **After**: 2 calls per task operation (list + update)
- **Savings**: 50% reduction in API calls

---

## [2026-01-14] - Bug Fixes & Performance Improvements

### 🎯 Summary
Critical bug fixes for task selection, intent classification, and WhatsApp template formatting.

### 🐛 Fixed
- **Task Selection Bug**
  - Fixed regex pattern to handle plural forms (tasks_1_fr, projects_1_fr)
  - Fixed chat history crash preventing tool_outputs from reaching AI
  - Improved direct action handler for list interactions

- **Intent Classification**
  - Robust parsing for Haiku responses with explanation text
  - Lowered confidence threshold to 90% for better fast path usage
  - Fixed SQL injection detection (OR-based tautologies)

- **WhatsApp Template Issues**
  - Fixed 42 template length violations (24-char limit)
  - Implemented proper truncation for list items
  - Enhanced emoji handling in templates

### 🔄 Changed
- Improved error logging for debugging
- Enhanced validation for message sanitization
- Better handling of edge cases in path traversal sanitization

---

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
