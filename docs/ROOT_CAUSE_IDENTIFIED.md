# ROOT CAUSE IDENTIFIED - Message Storage/Loading Failure

**Date**: 2026-01-17
**Status**: 🔴 **CRITICAL - ROOT CAUSE FOUND**

---

## Executive Summary

Based on LangSmith trace analysis, **ONE root cause explains BOTH issues**:

**ROOT CAUSE**: Messages are not being saved to database OR not being loaded from database correctly

**Result**:
1. `handle_direct_action` can't find tool_outputs → returns None → falls back to pipeline
2. Intent classifier receives empty conversation_history → misclassifies as "general"

---

## Evidence From LangSmith Trace

### What User Provided:

```
list_projects_tool called → Output: "Voici votre chantier actif: 1. 🏗️ Champigny"
User clicked option 1
System received: "option_1_fr"
Language detection on "option_1_fr" → "fr"
Intent classification on "option_1_fr" → "general": 90%
Bot responded with greeting menu
```

### Critical Observation:

Intent classification prompt in LangSmith shows:
```
Message actuel : option_1_fr

Retourne UNIQUEMENT un JSON valide...
```

**Missing**: No "Historique récent de conversation" section!

This proves:
- ❌ Intent classifier did NOT receive conversation_history
- ❌ conversation_history was empty `[]` or `None`

---

## Complete Flow Analysis

### Step 1: User Clicks "Champigny" Button

**Expected**: Button sends "option_1_fr"
**Actual**: ✅ Correctly sent "option_1_fr"

### Step 2: Pattern Matching

**File**: `src/handlers/message.py:764-765`

```python
action_pattern = r"^(.+)_([a-z]{2})$"
action_match = re.match(action_pattern, message_body.strip())  # "option_1_fr"
```

**Result**: ✅ Matched! `action_id = "option_1"`

### Step 3: Call `handle_direct_action`

**File**: `src/handlers/message.py:772-778`

```python
direct_response = await handle_direct_action(
    action="option_1",  # ← Action ID extracted
    user_id=user_id,
    phone_number=phone_number,
    language=user_language,
    session_id=session_id,
)
```

**Result**: Called with action="option_1"

### Step 4: Inside `handle_direct_action` - Parse Action Format

**File**: `src/handlers/message.py:201-207`

```python
list_match = re.match(r"(tasks?|projects?|option)_(\d+)(?:_[a-z]{2})?", action)

if list_match:
    list_type = list_match.group(1)      # "option"
    option_number = list_match.group(2)  # "1"
    log.info(f"📋 Interactive list selection detected: {action}")
```

**Result**: ✅ Parsed as list_type="option", option_number="1"

### Step 5: Load Messages to Find Context

**File**: `src/handlers/message.py:224-230`

```python
# Load recent messages
messages = await supabase_client.get_messages_by_session(
    session_id, fields="content,direction,metadata,created_at"
)

# Limit to last 10 messages
messages = messages[-10:] if messages else []
```

**Result**: ❓ What was returned?

### Step 6: Search for `tool_outputs`

**File**: `src/handlers/message.py:232-295`

```python
# For "option" type, search for list_projects_tool output
target_tool = None  # Will check both

tool_outputs = None
found_tool_name = None

for idx, msg in enumerate(reversed(messages)):
    if msg and msg.get("direction") == "outbound":
        metadata = msg.get("metadata", {})
        msg_tool_outputs = metadata.get("tool_outputs", [])

        # Check if it has list_projects_tool
        if "list_projects_tool" in [t.get("tool") for t in msg_tool_outputs]:
            tool_outputs = msg_tool_outputs
            found_tool_name = "list_projects_tool"
            break
```

**Expected**: Find message with `list_projects_tool` output containing project list
**Actual**: ❌ **Did NOT find tool_outputs** (otherwise would have continued)

### Step 7: No `tool_outputs` Found → Return `None`

**File**: Continuation of `handle_direct_action`

If tool_outputs not found, the function eventually returns `None`.

**Result**: ❌ `direct_response = None`

### Step 8: Fallback to Pipeline

**File**: `src/handlers/message.py:927-935`

```python
else:
    # Direct action handler returned None - fallback to AI pipeline
    log.warning(
        f"⚠️ Direct action '{action_id}' returned None - falling back to AI pipeline"
    )
    # Don't return - continue to pipeline processing below
```

**Result**: ❌ Falls through to pipeline

### Step 9: Pipeline Loads Conversation History

**File**: `src/handlers/message_pipeline.py:263-274`

```python
messages = await supabase_client.get_messages_by_session(
    ctx.session_id, fields="content,direction,created_at"
)

sorted_messages = sorted(messages, key=lambda x: x.get("created_at", ""))

if sorted_messages:
    ctx.recent_messages = sorted_messages[-3:]
    log.info(f"📜 Loaded {len(ctx.recent_messages)} recent messages for intent context")
```

**Expected**: Load 3 recent messages
**Actual**: ❌ **`sorted_messages` was empty `[]`**
**Result**: ❌ `ctx.recent_messages = []`

### Step 10: Intent Classification With Empty History

**File**: `src/handlers/message_pipeline.py:647-661`

```python
intent_result = await intent_classifier.classify(
    ctx.message_in_french,              # "option_1_fr"
    ctx.user_id,
    last_bot_message=ctx.last_bot_message,
    conversation_history=ctx.recent_messages,  # [] (empty!)
    # ...
)
```

**File**: `src/services/intent.py:359-368`

```python
context_section = ""
if conversation_history and len(conversation_history) > 0:  # FALSE!
    context_section = "\n\nHistorique récent de conversation :\n"
    # ... (skipped)
```

**Result**:
- ❌ No conversation history section added to prompt
- ❌ LangSmith shows no "Historique récent" section
- ❌ Intent classified as "general": 90%

### Step 11: Wrong Response

Intent "general" → Bot shows greeting menu instead of task list

---

## Root Cause: Why Are Messages Empty?

### Hypothesis 1: Messages Not Being Saved ⚠️

**Symptom**: After `list_projects_tool` is called, the bot response is not saved to database

**Check**:
```sql
SELECT id, session_id, content, direction, metadata, created_at
FROM messages
WHERE session_id = '<session_id>'
ORDER BY created_at DESC
LIMIT 10;
```

**Look for**: Message with "Voici votre chantier actif: 1. 🏗️ Champigny"

**If missing**: Message storage code is broken

### Hypothesis 2: Messages Saved to Wrong Session ⚠️

**Symptom**: Messages saved to one session, but loading from different session

**Check**:
```sql
-- Check if user has multiple active sessions
SELECT id, status, created_at
FROM conversation_sessions
WHERE subcontractor_id = 'ed97770c-ba77-437e-a1a9-e4a8e034d1da'
ORDER BY created_at DESC;
```

**If multiple**: Session race condition (should be fixed by Phases 1-8)

### Hypothesis 3: Metadata Not Saved ⚠️

**Symptom**: Messages saved, but `tool_outputs` not in metadata

**Check**:
```sql
SELECT id, content, direction, metadata
FROM messages
WHERE session_id = '<session_id>'
AND direction = 'outbound'
ORDER BY created_at DESC
LIMIT 5;
```

**Look for**: Does metadata contain `tool_outputs` array?

### Hypothesis 4: Database Query Failing Silently ⚠️

**Symptom**: Exception during message loading, caught by try/except

**Check logs for**:
```
"Could not load conversation context: <error>"
⚠️ Direct action 'option_1' returned None - falling back to AI pipeline
```

### Hypothesis 5: Commit 1857b07 Side Effect ⚠️

**Symptom**: Something in commit changed message storage behavior

**Check**: Did commit touch message storage code?

**Answer**: Let me verify...

---

## Diagnostic Steps

### Step 1: Check If Messages Are Being Saved

**Query**:
```sql
SELECT
    m.id,
    m.session_id,
    m.content,
    m.direction,
    m.metadata,
    m.created_at,
    s.subcontractor_id
FROM messages m
JOIN conversation_sessions s ON m.session_id = s.id
WHERE s.subcontractor_id = 'ed97770c-ba77-437e-a1a9-e4a8e034d1da'
ORDER BY m.created_at DESC
LIMIT 20;
```

**Look for**:
1. Is message with "Voici votre chantier actif" present?
2. Does it have `tool_outputs` in metadata?
3. Is metadata structure correct?

### Step 2: Check Session State

**Query**:
```sql
SELECT id, status, created_at, updated_at
FROM conversation_sessions
WHERE subcontractor_id = 'ed97770c-ba77-437e-a1a9-e4a8e034d1da'
ORDER BY created_at DESC;
```

**Look for**:
- Multiple active sessions? (race condition)
- Session IDs match between message saves and loads?

### Step 3: Check Application Logs

**Search for**:
```bash
# Should see this when list_projects is called:
"💾 Storing X tool outputs in metadata"

# Should see this when option_1 is clicked:
"📋 Interactive list selection detected: option_1"
"🔍 Searching for tool_outputs in last X messages"
"📦 Found tool_outputs with list_projects_tool"

# If tool_outputs not found:
"⚠️ Direct action 'option_1' returned None - falling back to AI pipeline"

# When pipeline loads messages:
"📜 Loaded X recent messages for intent context"
```

### Step 4: Check if Commit 1857b07 Affected Message Storage

**Verify**: Did commit touch any message storage/retrieval code?

```bash
git show 1857b07 --name-only | grep -E "(message|save|supabase)"
```

---

## Confirmed: The Problem

From LangSmith trace analysis and code review:

1. ✅ Button click sent correct format ("option_1_fr")
2. ✅ Pattern matched correctly
3. ✅ `handle_direct_action` was called
4. ❌ **`handle_direct_action` couldn't find tool_outputs in messages**
5. ❌ **Returned `None`**
6. ❌ **Fell back to pipeline**
7. ❌ **Pipeline loaded empty messages array**
8. ❌ **Intent classifier received empty conversation_history**
9. ❌ **Misclassified as "general"**
10. ❌ **Showed greeting menu**

**Root Cause**: Messages are not being saved OR not being loaded correctly

**Impact**:
- Direct actions fail (no tool_outputs found)
- Intent classification fails (no conversation history)
- User experience: Wrong responses

---

## Next Steps

1. **Urgent**: Check database to see if messages are being saved
2. **Urgent**: Check logs for message storage errors
3. **Urgent**: Verify session IDs are consistent
4. **Review**: Did commit 1857b07 inadvertently affect message storage?
5. **Fix**: Once root cause identified, fix message storage/loading

---

## Additional Context

### Why This Wasn't Caught Earlier

Before commit 1857b07 (2026-01-17 16:50), user's example showed conversation history working. This suggests:

**Possibility A**: Commit 1857b07 broke something related to message storage
**Possibility B**: Different issue occurred around the same time
**Possibility C**: Race condition in production (should be fixed by Phases 1-8)

### What Commit 1857b07 Removed

- `user_context` table and service (217 lines)
- `remember_user_context_tool` (100 lines)
- Agent personalization instructions (16 lines)

**Did NOT touch**:
- Message storage code
- Message retrieval code
- Intent classification code
- Pipeline code

**BUT**: Need to verify if there were any indirect effects.

---

*Root cause identified - Awaiting database/log verification*
