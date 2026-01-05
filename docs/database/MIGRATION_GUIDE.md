# Migration Guide - Database Schema Update

This guide will help you migrate your Lumiera WhatsApp API to use the new conversation memory system and updated database schema.

## 🎯 Overview

We've made significant improvements:
1. ✅ Aligned code with existing database schema (subcontractors, messages)
2. ✅ Implemented intelligent conversation memory
3. ✅ Enhanced action logging for project evolution tracking
4. ✅ Added new tables for better tracking

## ⚠️ Prerequisites

- Access to Supabase dashboard
- Service role key configured in `.env`
- Backup of your database (recommended)

## 📋 Migration Steps

### Step 1: Backup Your Database (Recommended)

```bash
# In Supabase Dashboard:
# Settings > Database > Backups > Create Backup
```

### Step 2: Run Database Migrations

1. Open your Supabase project at https://app.supabase.com/
2. Navigate to **SQL Editor** in the left sidebar
3. Click **New Query**
4. Copy the entire contents of `database_migrations.sql`
5. Paste and click **Run**

This will create:
- ✅ `action_logs` table
- ✅ `conversation_sessions` table
- ✅ `escalations` table (if needed)
- ✅ `agent_metrics` table
- ✅ Indexes for performance
- ✅ RLS policies
- ✅ Triggers and functions

### Step 3: Verify Tables Were Created

Run this query in Supabase SQL Editor:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('action_logs', 'conversation_sessions', 'escalations', 'agent_metrics')
ORDER BY table_name;
```

You should see all 4 tables listed.

### Step 4: Update Environment Variables

Check that your `.env` file has:

```env
# Media storage bucket should be 'conversations'
MEDIA_STORAGE_BUCKET=conversations

# Verify Supabase credentials
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### Step 5: Restart the Application

```bash
# Kill existing process
ps aux | grep "python -m uvicorn" | grep -v grep | awk '{print $2}' | xargs kill

# Start server
./run.sh
```

### Step 6: Test the Changes

1. **Test Health Check**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"healthy","service":"lumiera-whatsapp-api"}
   ```

2. **Test with WhatsApp**
   - Send a message: "Hello"
   - Send a follow-up: "What did I just say?"
   - Agent should remember your previous message! 🎉

3. **Check Database**
   ```sql
   -- Check messages are being saved
   SELECT * FROM messages ORDER BY created_at DESC LIMIT 5;

   -- Check action logs are being saved
   SELECT * FROM action_logs ORDER BY created_at DESC LIMIT 5;
   ```

## 🔍 Verification Checklist

- [ ] All tables created successfully
- [ ] Server starts without errors
- [ ] Health endpoint returns healthy status
- [ ] WhatsApp messages are received and saved
- [ ] Agent responds with conversation context
- [ ] Action logs are being created
- [ ] No errors in logs (`tail -f logs/errors_*.log`)

## 🐛 Troubleshooting

### Issue: "Could not find the table 'public.action_logs'"

**Solution**: Run the database migrations (Step 2)

### Issue: "Error getting subcontractor by phone"

**Solution**:
1. Verify `subcontractors` table exists
2. Check that it has `contact_telephone` column
3. Verify Supabase credentials in `.env`

### Issue: "Agent doesn't remember previous messages"

**Solution**:
1. Check that `messages` table has data: `SELECT COUNT(*) FROM messages;`
2. Check logs for memory service errors
3. Verify conversation history is being retrieved (check logs for "Retrieved X messages")

### Issue: Server won't start

**Solution**:
```bash
# Check what's using port 8000
lsof -i :8000

# Check logs
tail -f logs/errors_*.log

# Verify virtual environment is activated
source venv/bin/activate

# Reinstall dependencies if needed
pip install -r requirements.txt
```

## 📊 What Changed (Technical Details)

### Database Schema Changes

| Before | After | Reason |
|--------|-------|--------|
| `users` table | `subcontractors` table | Align with existing schema |
| `whatsapp_number` column | `contact_telephone` column | Match existing column names |
| `user_id` in messages | `subcontractor_id` | Consistency |
| `message_text` | `content` | Match existing schema |
| `whatsapp-media` bucket | `conversations` bucket | Use existing bucket |

### New Tables

#### `action_logs`
**Purpose**: Track all agent actions for auditability and evolution tracking

**Columns**:
- `id` - UUID primary key
- `subcontractor_id` - Reference to subcontractor
- `action_name` - Name of action/tool
- `action_type` - Type (tool_call, api_request, etc.)
- `parameters` - Input JSONB
- `result` - Output JSONB
- `error` - Error message if failed
- `duration_ms` - Duration in milliseconds
- `created_at` - Timestamp

#### `conversation_sessions`
**Purpose**: Group messages into sessions for better context

**Columns**:
- `id` - UUID primary key
- `subcontractor_id` - Reference to subcontractor
- `started_at` - Session start time
- `last_message_at` - Last message timestamp
- `message_count` - Number of messages
- `summary` - Auto-generated summary
- `status` - active/ended/escalated

### Code Changes

#### `src/integrations/supabase.py`
- ✅ Updated to use `subcontractors` table
- ✅ Added `get_conversation_history()`
- ✅ Added `get_recent_context()`
- ✅ Enhanced action logging

#### `src/handlers/message.py`
- ✅ Retrieves conversation history
- ✅ Passes history to agent
- ✅ Converts to LangChain format

#### `src/services/memory.py` (NEW)
- ✅ Conversation summarization
- ✅ Memory optimization
- ✅ Context management

## 🎯 Benefits

### For Users
- 🧠 **Agent has memory** - Remembers previous messages
- 💬 **Better conversations** - More natural, contextual responses
- ⚡ **Faster responses** - Optimized context management

### For Developers
- 📊 **Full audit trail** - Every action logged
- 🔍 **Easy debugging** - Detailed action logs
- 📈 **Evolution tracking** - Understand how project evolved
- 🛠️ **Better monitoring** - Performance metrics available

## 🚀 Next Steps

After successful migration:

1. **Monitor Performance**
   - Check response times
   - Monitor token usage
   - Review action logs

2. **Optional: Enable Session Tracking**
   - Link messages to sessions
   - Generate conversation summaries
   - Track session metrics

3. **Optional: Set Up Monitoring**
   - Configure Sentry (if needed)
   - Set up metric dashboards
   - Configure alerts

## 📞 Need Help?

If you encounter issues:
1. Check the logs: `tail -f logs/errors_*.log`
2. Verify database migrations ran successfully
3. Check Supabase dashboard for errors
4. Review this guide's troubleshooting section

## 📝 Rollback (If Needed)

If you need to rollback:

```bash
# Checkout previous commit
git checkout 5639dd6

# Restore .env backup if needed
cp .env.backup .env

# Restart server
./run.sh
```

**Note**: This will lose the memory features but restore functionality.

---

**Migration Date**: 2026-01-05
**Commit**: 28308fd
**Version**: 2.0.0
