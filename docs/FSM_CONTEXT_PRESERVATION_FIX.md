# FSM Context Preservation Fix - Implementation Complete

**Date**: 2026-01-16
**Issue**: Context loss during multi-turn conversations (task updates)
**Status**: ✅ **IMPLEMENTED**

---

## 🎯 Problem Summary

When users were in the middle of updating a task:
1. User adds photo → Bot shows options ("Souhaitez-vous autre chose?")
2. User responds with comment → Bot ABANDONED session and started new flow

**Root Cause**: Intent classifier didn't check if user had active session, so it treated every message as isolated.

---

## ✅ Solution Implemented

### Phase 1: Progress Update Agent Sets FSM State

**File**: `src/services/progress_update/state.py`

**Changes**:
- `create_session()`: Sets initial `fsm_state = "awaiting_action"`
- `add_action()`: After image/comment, sets:
  - `fsm_state = "collecting_data"`
  - `session_metadata.expecting_response = True`
  - `session_metadata.available_actions = ["add_comment", "add_photo", "mark_complete"]`

**Code added** (lines 136-148):
```python
# Update FSM state to indicate we're collecting data and expecting response
updates["fsm_state"] = "collecting_data"

# Set expecting_response flag in metadata
session_metadata = session.get("session_metadata", {})
session_metadata["expecting_response"] = True
session_metadata["last_bot_action"] = f"added_{action_type}"
session_metadata["available_actions"] = ["add_comment", "add_photo", "mark_complete"]
updates["session_metadata"] = session_metadata

log.info(f"🔄 FSM: Setting state='collecting_data', expecting_response=True after {action_type}")
```

---

### Phase 2: Message Pipeline Checks Active Session

**File**: `src/handlers/message_pipeline.py`

**Changes**:

1. **Updated MessageContext dataclass** (lines 46-53):
   - Added FSM fields: `active_session_id`, `fsm_state`, `fsm_current_step`, `fsm_task_id`
   - Added: `expecting_response`, `last_bot_options`, `should_continue_session`

2. **Added `_check_active_session()` stage** (lines 471-529):
   - Queries `progress_update_sessions` for active session
   - Extracts FSM state and metadata
   - Sets `should_continue_session = True` if:
     - Session exists
     - `expecting_response = True`
     - Last activity < 5 minutes ago

3. **Integrated into pipeline** (lines 162-165):
   - Added Stage 5.5 between translation and intent classification
   - Passes FSM context to intent classifier

**Key logic**:
```python
# If expecting response and recent activity (< 5 minutes)
if ctx.expecting_response and age_seconds < 300:
    ctx.should_continue_session = True
    log.info(f"   ✅ Should continue session (recent activity, expecting response)")
```

---

### Phase 3: Intent Classifier Uses Session Context

**File**: `src/services/intent.py`

**Changes**:

1. **Updated method signature** (lines 149-160):
   - Added FSM parameters: `active_session_id`, `fsm_state`, `expecting_response`, `should_continue_session`

2. **Added FSM context hint** (lines 218-249):
   - When `should_continue_session = True`, adds critical context to prompt
   - Tells Claude that user is responding to options, not starting new flow
   - Provides explicit examples:
     - "le mur est encore fisurré" → `update_progress:95` (comment, not incident)
     - "il y a un problème avec la peinture" → `update_progress:95` (comment, not incident)
   - In doubt, prefer continuing session over starting new flow

**FSM hint added to prompt**:
```
⚠️⚠️⚠️ CONTEXTE DE SESSION ACTIVE CRITIQUE ⚠️⚠️⚠️

L'utilisateur est EN TRAIN de mettre à jour une tâche (état FSM: {fsm_state})
Le bot vient de lui présenter des options et ATTEND UNE RÉPONSE.
Ce message est TRÈS PROBABLEMENT une réponse à ces options, PAS un nouveau intent!

RÈGLES PRIORITAIRES :
1. Si le message peut être interprété comme un commentaire/description,
   c'est "update_progress" pour CONTINUER la session active,
   PAS "report_incident" pour créer un nouvel incident.

2. EXEMPLES dans ce contexte :
   - "le mur est encore fisurré" → update_progress:95
   - "il y a un problème avec la peinture" → update_progress:95
   - "c'est fait" / "terminé" → update_progress:90

3. Classifier comme NOUVEAU intent seulement si EXPLICITE :
   - "Annuler" / "Stop" / "Non merci"
   - "Je veux faire autre chose"
   - Demande CLAIRE d'action différente ("Montre les documents")

4. Dans le DOUTE, TOUJOURS privilégier "update_progress"
```

---

## 🔄 Flow Comparison

### Before Fix:
```
Bot: Photo ajoutée! Souhaitez-vous autre chose?
     [Session state NOT updated]

User: le mur est encore fisurré

[Intent classification]:
  ❌ No active session check
  ❌ Keywords: "fisurré" → report_incident (90%)

Bot: Je vais vous aider à signaler un incident 🚨
     [WRONG - abandoned task update]
```

### After Fix:
```
Bot: Photo ajoutée! Souhaitez-vous autre chose?
     [Session updated]:
       fsm_state = "collecting_data"
       expecting_response = True

User: le mur est encore fisurré

[Stage 5.5: Check active session]:
  ✅ Active session found
  ✅ Expecting response: TRUE
  ✅ Age: 13s (< 300s)
  ✅ should_continue_session = TRUE

[Intent classification with FSM context]:
  ✅ FSM hint added to prompt
  ✅ "User is responding to options, this is a comment"
  ✅ Intent: update_progress (95%)

Bot: ✅ Commentaire ajouté : "le mur est encore fisurré"
     Souhaitez-vous autre chose?
     [Continues session correctly]
```

---

## 📊 Testing Scenarios

### Scenario 1: Continue Task Update ✅
```
1. User starts task update
2. User adds photo
3. Bot shows options, sets expecting_response=True
4. User says "le mur est encore fisurré"
5. Expected: Classified as update_progress, adds comment
6. Expected: Session continues
```

### Scenario 2: Explicit Cancel
```
1. User in task update (expecting_response=True)
2. User says "annuler" or "stop"
3. Expected: Classified as general/cancel intent
4. Expected: Session abandoned appropriately
```

### Scenario 3: Session Too Old
```
1. User in task update
2. Bot showed options 10 minutes ago
3. User finally responds
4. Expected: should_continue_session=False (age > 5min)
5. Expected: Classified without FSM hint (fresh start)
```

---

## 🔍 Key Logs to Monitor

After this fix, successful context preservation will show:

```
🔄 FSM: Setting state='collecting_data', expecting_response=True after image
...
🔄 Active session found: 824f330f...
   State: collecting_data | Step: awaiting_action
   Expecting response: True
   Age: 13s
   ✅ Should continue session (recent activity, expecting response)
...
✅ Intent: update_progress (confidence: 95.00%)
```

Failed context preservation would show:
```
💤 No active progress update session for user
...
✅ Intent: report_incident (confidence: 90.00%)
```

---

## 📝 Files Modified

1. **src/services/progress_update/state.py**
   - Lines 39: Set initial fsm_state in create_session()
   - Lines 136-148: Set FSM state and expecting_response in add_action()

2. **src/handlers/message_pipeline.py**
   - Lines 46-53: Added FSM fields to MessageContext
   - Lines 162-165: Added Stage 5.5 to pipeline
   - Lines 471-529: New _check_active_session() method
   - Lines 544-548: Pass FSM context to intent classifier

3. **src/services/intent.py**
   - Lines 156-159: Added FSM parameters to classify()
   - Lines 218-249: Added FSM context hint to prompt

---

## ✅ Deployment

**Application restarted**: 2026-01-16 09:20:52
**Status**: ✅ Running with FSM context preservation
**Ready for testing**: Yes

---

## 🧪 How to Verify

1. **Start a task update via WhatsApp**
2. **Add a photo** - Bot should respond with options
3. **Send a message that looks like a comment**: "le mur est fissuré" or "problème avec la peinture"
4. **Check logs for**:
   - `🔄 FSM: Setting state='collecting_data', expecting_response=True`
   - `🔄 Active session found`
   - `✅ Should continue session`
   - `✅ Intent: update_progress`
5. **Verify bot response**: Should add comment and continue session, NOT start incident flow

---

## 💡 Benefits

1. ✅ **No more context loss** during multi-turn conversations
2. ✅ **Natural conversation flow** - users can respond naturally to options
3. ✅ **Fewer abandoned sessions** - system understands user is mid-flow
4. ✅ **Better user experience** - bot doesn't randomly switch contexts
5. ✅ **FSM actually working** - not just for idempotency anymore

---

## 🔮 Next Steps

**Immediate**:
- [ ] Test on WhatsApp with real user
- [ ] Monitor logs for context preservation
- [ ] Verify no regressions in other flows

**Future Enhancements**:
- [ ] Add FSM state visualization in logs
- [ ] Create metrics dashboard for session continuity rate
- [ ] Extend to other multi-turn flows (incident creation, etc.)

---

**Implementation Time**: ~2 hours
**Status**: ✅ Complete and deployed
**Priority**: 🔴 Critical fix for core functionality
