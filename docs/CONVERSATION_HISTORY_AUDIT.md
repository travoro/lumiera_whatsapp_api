# Conversation History Audit - Is Intent Classifier Receiving Messages?

**Date**: 2026-01-17
**Status**: 🔍 **INVESTIGATION IN PROGRESS**

---

## User's Concern

> "the exemple i provided was from yesterday not from right now so i think the intent agent doesn't receive the last messages"

**Timeline**:
- **Yesterday (2026-01-16)**: User's example showed conversation history working
- **Today (2026-01-17 16:50)**: Commit 1857b07 removed user_context
- **Today (current)**: User suspects intent agent not receiving messages

---

## Code Audit: Is Conversation History Being Passed?

### ✅ Step 1: Intent Classifier Accepts conversation_history Parameter

**File**: `src/services/intent.py:295-310`

```python
async def classify(
    self,
    message: str,
    user_id: str = None,
    last_bot_message: str = None,
    conversation_history: list = None,  # ✅ Parameter exists
    # ... other parameters
) -> Dict[str, Any]:
```

**Status**: ✅ Parameter defined and documented

### ✅ Step 2: Intent Classifier USES conversation_history in Prompt

**File**: `src/services/intent.py:357-368`

```python
# Build conversation context if available
context_section = ""
if conversation_history and len(conversation_history) > 0:  # ✅ Checks if present
    context_section = "\n\nHistorique récent de conversation :\n"
    for msg in conversation_history:  # ✅ Loops through messages
        direction = msg.get("direction", "")
        content = msg.get("content", "")[:200]  # Limit to 200 chars
        if direction == "inbound":
            context_section += f"User: {content}\n"
        elif direction == "outbound":
            context_section += f"Bot: {content}\n"
    context_section += "\n"
```

**Status**: ✅ Conversation history IS used in prompt construction

### ✅ Step 3: Pipeline Loads Messages from Session

**File**: `src/handlers/message_pipeline.py:253-298`

```python
async def _manage_session(self, ctx: MessageContext) -> Result[None]:
    """Stage 2: Get or create conversation session and load conversation context."""
    try:
        session = await session_service.get_or_create_session(ctx.user_id)
        if session:
            ctx.session_id = session["id"]
            log.info(f"✅ Session: {ctx.session_id}")

            # Load conversation context for intent classification
            try:
                messages = await supabase_client.get_messages_by_session(
                    ctx.session_id, fields="content,direction,created_at"
                )  # ✅ Loads messages from database

                # Sort messages by created_at (oldest to newest)
                sorted_messages = sorted(
                    messages, key=lambda x: x.get("created_at", "")
                )

                # Get last 3 messages for intent context
                if sorted_messages:
                    ctx.recent_messages = sorted_messages[-3:]  # ✅ Sets ctx.recent_messages
                    log.info(
                        f"📜 Loaded {len(ctx.recent_messages)} recent messages for intent context"
                    )
```

**Status**: ✅ Messages ARE loaded from database and stored in ctx.recent_messages

### ✅ Step 4: Pipeline Passes Messages to Intent Classifier

**File**: `src/handlers/message_pipeline.py:647-661`

```python
intent_result = await intent_classifier.classify(
    ctx.message_in_french,
    ctx.user_id,
    last_bot_message=ctx.last_bot_message,
    conversation_history=ctx.recent_messages,  # ✅ Passed here
    # ... other parameters
)
```

**Status**: ✅ ctx.recent_messages IS passed as conversation_history

---

## Commit 1857b07 Impact on Conversation History

### Files Modified in Commit 1857b07:

```bash
src/agent/agent.py                    # Removed memorization instructions (16 lines)
src/agent/tools.py                    # Removed remember_user_context_tool (100 lines)
src/handlers/message.py               # Removed user_context_service import (1 line)
src/integrations/supabase.py          # Removed user_context methods (96 lines)
src/services/user_context.py          # Entire file deleted (217 lines)
src/utils/handler_helpers.py          # Adjusted helpers (29 lines)
migrations/database_migrations_v2.sql # Dropped user_context table (66 lines)
migrations/verify_migrations.py       # Removed verification (10 lines)
```

### Files NOT Modified:

- ❌ `src/services/intent.py` - Intent classifier UNCHANGED
- ❌ `src/handlers/message_pipeline.py` - Message loading UNCHANGED
- ❌ Message storage logic - UNCHANGED

**Conclusion**: Commit 1857b07 did NOT touch any code related to conversation history loading or passing.

---

## Potential Issues (Hypotheses)

### Hypothesis 1: Messages Not Being Saved to Database ⚠️

**Symptom**:
- Messages sent but not stored in database
- When loaded, `messages` array is empty
- `ctx.recent_messages` becomes `[]`
- Intent classifier receives empty conversation_history

**Check**:
```sql
SELECT id, session_id, content, direction, created_at
FROM messages
WHERE session_id = '<session_id>'
ORDER BY created_at DESC
LIMIT 10;
```

**Look for**:
- Are recent messages present?
- Do they have correct session_id?
- Is content field populated?

### Hypothesis 2: Session Race Condition Side Effect ⚠️

**Symptom**:
- Multiple sessions created per user
- Messages saved to wrong session
- Current session has no message history

**Check**:
```sql
SELECT id, status, created_at
FROM conversation_sessions
WHERE subcontractor_id = '<user_id>'
ORDER BY created_at DESC;
```

**Look for**:
- Multiple active sessions?
- Current session different from message session?

**Status**: Should be FIXED by session race condition remediation (Phases 1-8)

### Hypothesis 3: Message Loading Fails Silently ⚠️

**Symptom**:
- Exception thrown in `_manage_session`
- Caught by try/except block (line 293-297)
- Sets `ctx.recent_messages = []` as fallback
- No messages passed to intent classifier

**Check logs for**:
```
"Could not load conversation context: <error>"
```

**Root Cause**: Database query error, permissions issue, or schema change

### Hypothesis 4: Messages Load but Are Filtered Out ⚠️

**Symptom**:
- Messages retrieved from database
- But `sorted_messages` is empty or has wrong format
- `ctx.recent_messages` becomes `[]`

**Check**:
- Do messages have `created_at` field?
- Is `created_at` in sortable format?
- Are messages being filtered out somehow?

### Hypothesis 5: User Example Was From Different Environment ⚠️

**Symptom**:
- Yesterday's example from staging/dev environment
- Today's issue on production
- Different database state

**Check**:
- Which environment was the example from?
- Which environment has the issue?
- Are they using the same database?

---

## Diagnostic Steps

### Step 1: Check Logs for Current Request

**Look for these log lines**:

```bash
# Should see:
✅ Session: <session_id>
📜 Loaded X recent messages for intent context
📜 Last bot message: '...'

# If issue exists, might see:
⚠️ Could not load conversation context: <error>
# OR
📜 Loaded 0 recent messages for intent context
```

### Step 2: Check Database State

**Query 1: Are messages being saved?**
```sql
SELECT COUNT(*) as message_count, session_id
FROM messages
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY session_id
ORDER BY message_count DESC
LIMIT 10;
```

**Query 2: What messages exist for user's session?**
```sql
SELECT m.id, m.session_id, m.content, m.direction, m.created_at
FROM messages m
JOIN conversation_sessions s ON m.session_id = s.id
WHERE s.subcontractor_id = '<user_id>'
ORDER BY m.created_at DESC
LIMIT 20;
```

**Query 3: Are there multiple active sessions?**
```sql
SELECT id, status, created_at, updated_at
FROM conversation_sessions
WHERE subcontractor_id = '<user_id>'
ORDER BY created_at DESC;
```

### Step 3: Add Debug Logging (Temporary)

**In message_pipeline.py, add after line 274**:
```python
if sorted_messages:
    ctx.recent_messages = sorted_messages[-3:]
    log.info(f"📜 Loaded {len(ctx.recent_messages)} recent messages for intent context")

    # TEMPORARY DEBUG
    for i, msg in enumerate(ctx.recent_messages):
        log.debug(f"  Message {i+1}: direction={msg.get('direction')}, content={msg.get('content', '')[:50]}")
```

**In intent.py, add after line 359**:
```python
if conversation_history and len(conversation_history) > 0:
    context_section = "\n\nHistorique récent de conversation :\n"

    # TEMPORARY DEBUG
    log.debug(f"🔍 Intent classifier received {len(conversation_history)} messages in conversation_history")

    for msg in conversation_history:
        # ... existing code
```

### Step 4: Test Scenario

1. Send message: "Mes projets"
2. Bot responds with project list
3. Check logs: Was message saved?
4. Send message: "1"
5. Check logs:
   - How many messages loaded?
   - Was conversation_history passed to intent classifier?
   - What did intent classifier receive?

---

## Expected Behavior (If Working Correctly)

### Log Sequence:

```
# User sends "Mes projets"
✅ User authenticated: <user_id> (John)
✅ Session: <session_id>
📜 Loaded 2 recent messages for intent context
📜 Last bot message: 'Bonjour John! ...'
✅ Intent: list_projects (confidence: 98%)

# Bot responds with project list
# Message saved to database

# User sends "1"
✅ User authenticated: <user_id> (John)
✅ Session: <session_id>  # Same session
📜 Loaded 3 recent messages for intent context  # Now includes previous exchange
  Message 1: direction=outbound, content=Bonjour John! ...
  Message 2: direction=inbound, content=Mes projets
  Message 3: direction=outbound, content=Voici vos projets: 1. Champigny ...
📜 Last bot message: 'Voici vos projets: 1. Champigny ...'
🔍 Intent classifier received 3 messages in conversation_history
✅ Intent: task_details (confidence: 85%)
```

### Conversation History in Intent Prompt:

```
Historique récent de conversation :
Bot: Bonjour John! Comment puis-je vous aider aujourd'hui?
User: Mes projets
Bot: Voici vos projets: 1. Champigny 2. Rénovation Bureau

Message actuel : 1
```

---

## Findings Summary

### ✅ Confirmed: Code Is Correct

1. Intent classifier accepts conversation_history parameter ✅
2. Intent classifier uses conversation_history in prompt ✅
3. Pipeline loads messages from database ✅
4. Pipeline passes messages to intent classifier ✅
5. Commit 1857b07 did NOT modify this code path ✅

### ❓ Unknown: Runtime Behavior

1. Are messages actually being saved to database? ❓
2. Are messages being loaded successfully? ❓
3. Is conversation_history array populated or empty? ❓
4. Are there errors during message loading? ❓

### 🎯 Recommendation

**The code is correct and unchanged**. The issue, if it exists, is likely:

1. **Messages not being saved** - Check message storage code
2. **Session mismatch** - Messages in one session, loading from another (race condition)
3. **Database query error** - Check logs for "Could not load conversation context"
4. **Different environment** - User's example vs current issue environment

**Next Action**: Review logs from a current failed case to identify which hypothesis is correct.

---

## Key Insight

The user's concern is valid: **IF** the intent classifier is not receiving conversation history, it would significantly impact classification quality.

**However**, the code analysis shows that conversation history passing was NOT affected by commit 1857b07. The architecture is still intact.

**Therefore**, if there IS an issue with conversation history, it must be:
- A runtime problem (messages not saved/loaded)
- A pre-existing issue that wasn't noticed before
- A side effect from another change
- An environment-specific issue

The diagnostic steps above will identify the actual problem.

---

*Audit complete - Awaiting log analysis to confirm runtime behavior*
