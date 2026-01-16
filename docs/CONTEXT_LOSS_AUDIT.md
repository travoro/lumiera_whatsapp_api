# Context Loss Audit - Progress Update Session

**Date**: 2026-01-16
**Incident Time**: 09:50:23 - 09:50:41 UTC
**Status**: 🔴 **ROOT CAUSE IDENTIFIED**

---

## 📋 Executive Summary

**Issue**: Bot switched from progress update flow to incident reporting when user sent a descriptive message during an active progress update session.

**Root Cause**: Session creation does not set `expecting_response=True` flag. This flag is only set AFTER the first action is taken, creating a gap where the first user response after "Session started" lacks FSM context preservation.

**Impact**: First user message after session start may be misclassified, breaking the conversation flow.

**Severity**: MEDIUM - Affects user experience, but has workaround (conversation history often provides enough context)

---

## 🔍 Timeline of Events

### 09:50:23 - Session Creation
```
✅ User confirms task selection (button click)
✅ Session created: b3c30edb-31af-4a55-85ac-e4e4bbe52c92
✅ FSM state set: idle → awaiting_action
✅ Bot shows options: "📸 Ajouter une photo | 💬 Laisser un commentaire | ✅ Marquer comme terminé"
❌ expecting_response flag: NOT SET (defaults to False)
```

**Session State After Creation:**
```json
{
  "id": "b3c30edb-31af-4a55-85ac-e4e4bbe52c92",
  "subcontractor_id": "ed97770c-ba77-437e-a1a9-e4a8e034d1da",
  "fsm_state": "awaiting_action",
  "current_step": "awaiting_action",
  "session_metadata": {
    // expecting_response: NOT SET ❌
  }
}
```

### 09:50:37 - User Sends Message (14 seconds later)
```
User: "le mur est problematique, voici une photo"
```

This is a DESCRIPTIVE message that contains:
- Problem description ("le mur est problematique")
- Action intent ("voici une photo")
- No explicit keyword like "incident" or "problème"

### 09:50:40 - Active Session Check (Stage 5.5)
```
🔄 Active session found: b3c30edb...
   State: awaiting_action ✅
   Step: awaiting_action ✅
   Expecting response: False ❌ (PROBLEM #1)
   Age: 3617s ❌ (PROBLEM #2 - should be ~17s)

   DECISION: 💤 Session exists but not expecting response or too old
   RESULT: should_continue_session = False
   ACTION: No FSM context hint added to classification prompt
```

**Why Age is Wrong (3617s instead of 17s):**
This suggests the age calculation is comparing against the wrong timestamp or has a timezone issue. The actual elapsed time was 14-17 seconds, not 3617 seconds (1 hour).

### 09:50:41 - Intent Classification WITHOUT FSM Context
```
Classification Prompt:
  ✅ Recent messages included
  ✅ Active session status mentioned
  ❌ FSM context hint NOT included
  ❌ No examples of similar messages → update_progress

Result:
  Intent: report_incident ❌ (WRONG)
  Confidence: 0.90 (HIGH)
  Expected: update_progress ✅
```

**Why It Classified as report_incident:**
Without FSM context hints, the classifier saw:
- Keyword "problematique" (problem)
- User describing an issue
- No explicit "je veux mettre à jour" phrasing
- Defaulted to incident reporting

---

## 🔬 Root Cause Analysis

### Location 1: Session Creation (src/services/progress_update/tools.py)

**Function**: `start_progress_update_session_tool` (lines 348-389)

**What It Does:**
```python
# Create session
response = supabase_client.client.table("progress_update_sessions").insert({
    "subcontractor_id": user_id,
    "task_id": task_id,
    "project_id": project_id,
    "current_step": "awaiting_action",
    "fsm_state": "awaiting_action",  # ✅ Sets FSM state
    "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat()
    # ❌ Does NOT set session_metadata with expecting_response
}).execute()
```

**What It Doesn't Do:**
- Does NOT set `session_metadata.expecting_response = True`
- Does NOT set `session_metadata.last_bot_action`
- Does NOT set `session_metadata.available_actions`

### Location 2: Action Recording (src/services/progress_update/state.py)

**Function**: `add_action()` (lines 189-277)

**What It Does AFTER First Action:**
```python
# Set expecting_response flag in metadata so intent classifier knows
# that bot just showed options and is waiting for user's next action
session_metadata = session.get("session_metadata", {})
session_metadata["expecting_response"] = True  # ✅ Sets it here
session_metadata["last_bot_action"] = f"added_{action_type}"
session_metadata["available_actions"] = ["add_comment", "add_photo", "mark_complete"]
updates["session_metadata"] = session_metadata

log.info(f"🔄 FSM: Setting state='{new_state}', expecting_response=True after {action_type}")
```

**Timeline of Flag Setting:**
1. Session created → expecting_response NOT SET
2. User sends first message → classified WITHOUT FSM context
3. Action processed → expecting_response SET to True
4. User sends second message → classified WITH FSM context ✅

**The Gap:**
Between step 1 and 3, the session exists but the FSM context preservation doesn't activate.

### Location 3: Active Session Check (src/handlers/message_pipeline.py)

**Function**: Stage 5.5 - Check for active sessions (lines 511-563)

**The Check Logic:**
```python
session = await progress_update_state.get_session(user_id)

if session:
    fsm_state = session.get("fsm_state", "idle")
    current_step = session.get("current_step")
    session_metadata = session.get("session_metadata", {})
    expecting_response = session_metadata.get("expecting_response", False)  # ❌ Returns False

    # Calculate age
    last_activity = session.get("last_activity")
    age_seconds = (datetime.utcnow() - last_activity).total_seconds()

    # DECISION LOGIC:
    should_continue_session = (
        expecting_response and  # ❌ False - fails here
        age_seconds < 300  # 5 minutes
    )

    if should_continue_session:
        # Add FSM context hint to classification prompt
        # THIS IS WHAT WE NEED BUT DON'T GET
    else:
        log.info("💤 Session exists but not expecting response or too old")
        # NO FSM context hint added
```

**Why It Fails:**
- `expecting_response = False` (not set at creation)
- `age_seconds = 3617` (wrong calculation - timezone issue?)
- Result: `should_continue_session = False`
- Consequence: No FSM context hint

---

## 📊 Impact Assessment

### What Works:
- ✅ Session is created successfully
- ✅ FSM state is tracked
- ✅ Transition is logged
- ✅ Session persists in database
- ✅ Active session is detected

### What Doesn't Work:
- ❌ First user response after session creation lacks FSM context
- ❌ Age calculation shows wrong value (timezone issue?)
- ❌ Intent classification without FSM hints is less accurate
- ❌ User experience: bot appears to "forget" the context

### Frequency:
- **Every progress update session** experiences this gap
- **Only affects first user message** after session start
- Subsequent messages work correctly (expecting_response set after first action)

### User Impact:
- **Medium**: User may need to rephrase or resend message
- **Workaround exists**: Conversation history often provides enough context
- **Not blocking**: System recovers after first message

---

## 🎯 Why The Gap Exists

### Design Assumption:
The original design assumed users would click a **button** (1, 2, 3) for their first action after "Session started", not send a **freeform text message**.

**Expected Flow:**
```
1. Session created
2. Bot shows: "Choose: 📸 Photo | 💬 Comment | ✅ Complete"
3. User clicks button or types "1", "2", "3"
4. add_action() called → expecting_response = True
5. User sends next message → FSM context active
```

**Actual Flow (User Sent Text):**
```
1. Session created
2. Bot shows: "Choose: 📸 Photo | 💬 Comment | ✅ Complete"
3. User types: "le mur est problematique, voici une photo" ← Freeform text
4. Classified WITHOUT FSM context (expecting_response=False)
5. Misclassified as incident reporting ❌
```

### Why This Design:
Looking at the code history, the `expecting_response` flag was added as part of FSM context preservation (recent enhancement). The original session creation predates this feature.

**Session creation** was designed to:
- Track what user is doing (fsm_state)
- Store progress (images, comments, status)
- Enforce expiry (2 hours)

**FSM context preservation** was added later to:
- Help intent classification during multi-turn flows
- Prevent context switching (update → incident)
- Improve user experience

**The gap** exists because session creation wasn't updated when FSM context preservation was added.

---

## 🔍 Secondary Issue: Age Calculation

### The Problem:
```
Created: 2026-01-16 09:50:23
Message: 2026-01-16 09:50:37 (14 seconds later)
Calculated age: 3617 seconds (1 hour 17 seconds)
```

### Possible Causes:

**1. Timezone Mismatch:**
```python
# session.get("last_activity") might be:
# - UTC with 'Z' suffix: "2026-01-16T09:50:23Z"
# - UTC with +00:00: "2026-01-16T09:50:23+00:00"
# - Naive datetime: "2026-01-16T09:50:23"

# If datetime.fromisoformat() doesn't handle timezone correctly:
last_activity = datetime.fromisoformat(session["last_activity"].replace('Z', '+00:00'))
age_seconds = (datetime.utcnow() - last_activity).total_seconds()
# If last_activity is timezone-aware and utcnow() is naive, this could fail
```

**2. Wrong Session Retrieved:**
```python
# Maybe querying old session instead of new one?
# User might have multiple sessions in database?
```

**3. last_activity Not Set at Creation:**
```python
# If last_activity is NULL, get_session might use created_at instead
# But created_at could be from an old session?
```

### Evidence:
From logs at 09:50:40:
```
🔄 Active session found: b3c30edb-31af-4a55-85ac-e4e4bbe52c92
   Age: 3617s
```

Session ID matches the one created at 09:50:23, so it's the correct session. This points to **timezone mismatch** as the most likely cause.

---

## 💡 Solution Options

### Option 1: Set expecting_response at Session Creation (RECOMMENDED)

**Where**: `src/services/progress_update/tools.py` line 348-389

**Change**:
```python
# After session is created and before returning:
await progress_update_state.update_session(
    user_id=user_id,
    session_metadata={
        "expecting_response": True,
        "last_bot_action": "session_started",
        "available_actions": ["add_comment", "add_photo", "mark_complete"]
    }
)
```

**Pros:**
- ✅ Closes the gap completely
- ✅ First message gets FSM context
- ✅ Consistent with design intent
- ✅ Simple implementation

**Cons:**
- ❌ Adds one extra database call at session creation
- ❌ Minimal performance impact

**Impact:**
- HIGH - Fixes the root cause
- LOW RISK - No breaking changes

---

### Option 2: Fix Age Calculation

**Where**: `src/handlers/message_pipeline.py` line 520-530

**Change**:
```python
# Ensure timezone-aware comparison
last_activity_str = session.get("last_activity")
if last_activity_str:
    last_activity = datetime.fromisoformat(last_activity_str.replace('Z', '+00:00'))
    # Ensure both datetimes are timezone-aware or both naive
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    age_seconds = (now - last_activity).total_seconds()
else:
    age_seconds = 0
```

**Pros:**
- ✅ Fixes incorrect age calculation
- ✅ More accurate session timeout detection
- ✅ Helps with other edge cases

**Cons:**
- ❌ Doesn't fix the expecting_response gap
- ❌ Still need Option 1 for complete fix

**Impact:**
- MEDIUM - Improves accuracy but doesn't solve main issue
- LOW RISK - Improves existing logic

---

### Option 3: Accept the Gap (NOT RECOMMENDED)

**Justification**: Conversation history usually provides enough context

**Pros:**
- ✅ No code changes needed
- ✅ Minimal risk

**Cons:**
- ❌ Poor user experience (bot appears forgetful)
- ❌ Inconsistent behavior
- ❌ Doesn't match design intent
- ❌ Will cause confusion in production

**Impact:**
- NEGATIVE - User frustration continues

---

## 📈 Verification Evidence

### From FSM_VERIFICATION_REPORT.md:
This gap was already identified during FSM implementation:

```markdown
### Remaining Gap:
- ⚠️ First response after session creation doesn't have `expecting_response` flag
- ⚠️ Age calculation might have timezone issues

### Impact of Gap:
- **Low**: First message still classified correctly (90% confidence)
- **Mitigation**: Conversation history provides sufficient context
- **Future**: Could set `expecting_response = True` at session creation
```

**Status Update**: The impact was underestimated. In production, this caused a complete context switch (update → incident), not just lower confidence.

---

## 🎯 Recommendation

### Primary Fix: Option 1 + Option 2 (Combined)

**Implement both fixes:**

1. **Set expecting_response at session creation** (Option 1)
   - Closes the primary gap
   - Ensures FSM context from first message
   - Minimal code change

2. **Fix age calculation** (Option 2)
   - Ensures accurate timeout detection
   - Prevents false "too old" decisions
   - Improves overall reliability

### Implementation Priority:

**HIGH PRIORITY (Fix Now):**
- Option 1: Set expecting_response at session creation
- Option 2: Fix age calculation timezone handling

**Why Both:**
- Option 1 fixes the primary issue (expecting_response)
- Option 2 fixes secondary issue (age calculation)
- Combined: Complete solution with no gaps

---

## 📋 Implementation Checklist

When implementing the fix:

- [ ] **Update `start_progress_update_session_tool`** to set expecting_response=True
- [ ] **Fix age calculation** in message_pipeline.py Stage 5.5
- [ ] **Test with freeform text** after session creation
- [ ] **Test with button clicks** (original flow)
- [ ] **Verify FSM context hint** appears in classification
- [ ] **Verify correct intent classification** (update_progress not incident)
- [ ] **Check age calculation** shows correct seconds
- [ ] **Update FSM_VERIFICATION_REPORT.md** to reflect fix

---

## 📊 Testing Scenarios

### Test Case 1: Freeform Text After Session Start
```
1. Start progress update session
2. Wait 10 seconds
3. Send: "le mur est problematique, voici une photo"
4. EXPECTED: Classified as update_progress
5. VERIFY: FSM context hint in logs
6. VERIFY: Age shows ~10 seconds
```

### Test Case 2: Button Click After Session Start
```
1. Start progress update session
2. Click "💬 Laisser un commentaire" button
3. Send: "work completed"
4. EXPECTED: Classified as update_progress
5. VERIFY: Session continues smoothly
```

### Test Case 3: Delayed Response
```
1. Start progress update session
2. Wait 4 minutes
3. Send: "here's a photo"
4. EXPECTED: Still classified as update_progress (< 5 min)
5. VERIFY: Age shows ~240 seconds
6. VERIFY: FSM context hint present
```

### Test Case 4: Expired Session
```
1. Start progress update session
2. Wait 6 minutes
3. Send: "update task"
4. EXPECTED: No FSM context hint (> 5 min timeout)
5. VERIFY: Age shows ~360 seconds
6. VERIFY: should_continue_session = False
```

---

## ✅ Conclusion

**Status**: ROOT CAUSE IDENTIFIED ✅

**Primary Issue**: Session creation doesn't set `expecting_response=True`, creating a gap where first user response lacks FSM context preservation.

**Secondary Issue**: Age calculation has timezone mismatch, showing incorrect elapsed time.

**Impact**: User experience degradation - bot appears to lose context during active session.

**Solution**: Implement Option 1 + Option 2 (set expecting_response at creation + fix age calculation).

**Confidence**: HIGH - Root cause clearly identified, solution straightforward, low risk.

**Next Steps**:
1. User approval of analysis
2. Implement fixes
3. Test all scenarios
4. Deploy to production
5. Monitor logs for verification

---

**Analyzed By**: Claude Code
**Date**: 2026-01-16
**Confidence**: HIGH - Clear evidence from logs, code review, and user report
