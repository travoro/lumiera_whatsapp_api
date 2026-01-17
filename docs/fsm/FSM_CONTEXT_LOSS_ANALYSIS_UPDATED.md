# FSM Context Loss Analysis - UPDATED

**Date**: 2026-01-16
**Issue**: Bot abandoned task update session and started incident creation flow
**Status**: 🔴 **ROOT CAUSE CONFIRMED**

---

## ✅ What We Now Know

### Database State (Confirmed):

**FSM Tables Exist and Are Working:**
- ✅ `fsm_idempotency_records` - EXISTS, has 7+ entries
- ✅ `fsm_clarification_requests` - EXISTS
- ✅ `progress_update_sessions.fsm_state` column - EXISTS

**Active Session at Time of Issue:**
```
Session ID: 824f330f-e9da-4417-bd08-4d8e43179fcd
├─ subcontractor_id: ed97770c-ba77-437e-a1a9-e4a8e034d1da
├─ task_id: 7aa8d933-59d6-4ccc-b366-33f4aefc6394
├─ current_step: "awaiting_action" ✅
├─ fsm_state: "idle" ❌ ← PROBLEM #1
├─ images_uploaded: 1
├─ last_activity: 2026-01-16T07:29:54 (13 seconds before error)
└─ expires_at: 2026-01-16T09:29:15 (still valid)
```

**Idempotency Record for Problematic Message:**
```
Message ID: SM7af81d92502238d3784d4b5f62d79488
├─ Processed: 2026-01-16T07:30:10
├─ Intent: "report_incident" ❌ ← PROBLEM #2
└─ Should have been: "update_progress" (continue session)
```

---

## 🔴 Confirmed Root Causes

### Problem 1: FSM State Not Being Set
**Symptom**: `fsm_state` is stuck at `"idle"` even though session is active

**Evidence**:
- Session has `current_step = "awaiting_action"` (correct)
- But `fsm_state = "idle"` (wrong)
- Bot just sent options menu 13 seconds ago
- User is clearly responding to those options

**Root Cause**: Progress update agent sets `current_step` but doesn't update `fsm_state`

**Location**: `src/services/progress_update/agent.py`

### Problem 2: Intent Classifier Doesn't Check Active Sessions
**Symptom**: Message classified as `"report_incident"` instead of continuing task update

**Evidence from logs**:
```
08:30:08 | ✅ Session: c2eee27a-b40b-4187-aea4-15db4ed88bfd
08:30:08 | 📜 Loaded 3 recent messages
08:30:08 | 📜 Last bot message: '📸 Photo ajoutée avec succès ! Souhaitez-vous autr...'
08:30:10 | 🤖 Haiku classification: report_incident (confidence: 0.9)
```

**What happened**:
1. ✅ System loaded session
2. ✅ System loaded conversation history
3. ✅ System saw bot's options menu
4. ❌ **Intent classifier NEVER checked if user has active session**
5. ❌ Classified based on keywords alone ("fisurré" → incident)

**Root Cause**: No integration between active session state and intent classification

### Problem 3: Missing `expecting_response` Flag
**Symptom**: No way to know if bot is waiting for a response

**Current state**:
- Session has `current_step` (legacy field)
- Session has `fsm_state` (but not being updated)
- Session has NO `expecting_response` flag

**Needed**: Boolean flag to indicate "bot just asked a question, expecting response"

---

## 🔍 Detailed Flow Analysis

### What Should Have Happened:

```
07:29:54 Bot: Photo ajoutée avec succès!
              Souhaitez-vous autre chose?
              1. Ajouter un commentaire
              2. Marquer terminée
              3. Ajouter une autre photo

         [Session state should be updated to:]
         ├─ fsm_state: "collecting_data"
         ├─ expecting_response: TRUE
         └─ last_bot_options: ["add_comment", "mark_complete", "add_photo"]

07:30:07 User: le mur est encore fisurré

         [BEFORE intent classification:]
         1. Check: Does user have active session? → YES
         2. Check: Is session expecting response? → YES
         3. Check: What state is session in? → "collecting_data"
         4. Conclusion: User is responding to options

         [Intent classification with context:]
         "User is in middle of task update, just added photo,
          bot asked for next action. Message 'le mur est encore
          fisurré' is clearly a COMMENT (option #1), not a new
          incident."

         → Intent: update_progress (confidence: 95%)
         → Action: add_comment
         → Stay in session

07:30:11 Bot: ✅ Commentaire ajouté : "le mur est encore fisurré"

              Souhaitez-vous autre chose?
              1. Marquer terminée
              2. Ajouter une autre photo
```

### What Actually Happened:

```
07:29:54 Bot: Photo ajoutée avec succès!
              Souhaitez-vous autre chose?
              [Options sent]

         [Session state NOT updated:]
         ├─ fsm_state: "idle" ❌ (should be "collecting_data")
         ├─ expecting_response: NOT CHECKED ❌
         └─ No indication bot is waiting

07:30:07 User: le mur est encore fisurré

         [Intent classification WITHOUT session context:]
         "Message contains 'fisurré' (cracked) which is a problem
          keyword. No active session context checked."

         → Intent: report_incident (confidence: 90%)
         → ABANDONS task update session
         → Starts NEW incident flow

07:30:11 Bot: Je vais vous aider à signaler un incident 🚨
              [Completely different flow]
```

---

## 💡 Solution Design

### Fix 1: Progress Update Agent Must Set FSM State

**File**: `src/services/progress_update/agent.py`

**After sending options menu**, update the session:

```python
# After successfully adding photo/comment and showing options:
from src.integrations.supabase import supabase_client

# Update session with FSM state
await supabase_client.client.table('progress_update_sessions').update({
    'fsm_state': 'collecting_data',  # Or 'awaiting_action'
    'session_metadata': {
        'expecting_response': True,
        'last_bot_action': 'show_options',
        'available_actions': ['add_comment', 'mark_complete', 'add_photo']
    },
    'last_activity': 'now()'
}).eq('id', session_id).execute()
```

**Key changes**:
- Set `fsm_state` to proper value (not "idle")
- Store `expecting_response` flag in `session_metadata`
- Record what options were shown

---

### Fix 2: Check Active Session Before Intent Classification

**File**: `src/handlers/message_pipeline.py`

**Add new stage before intent classification**:

```python
async def _check_active_session(self, ctx: MessageContext) -> Result[None]:
    """Stage 5.5: Check if user has active progress update session."""
    try:
        # Query for active session
        result = supabase_client.client.table('progress_update_sessions')\
            .select('*')\
            .eq('subcontractor_id', ctx.user_id)\
            .gt('expires_at', 'now()')\
            .order('last_activity', desc=True)\
            .limit(1)\
            .execute()

        if result.data and len(result.data) > 0:
            session = result.data[0]

            # Extract FSM context
            ctx.active_session_id = session['id']
            ctx.fsm_state = session.get('fsm_state', 'idle')
            ctx.fsm_current_step = session.get('current_step')
            ctx.fsm_task_id = session.get('task_id')

            # Check if bot is expecting a response
            metadata = session.get('session_metadata', {})
            ctx.expecting_response = metadata.get('expecting_response', False)
            ctx.last_bot_options = metadata.get('available_actions', [])

            # Calculate session age
            from datetime import datetime
            last_activity = datetime.fromisoformat(session['last_activity'].replace('Z', '+00:00'))
            age_seconds = (datetime.now(last_activity.tzinfo) - last_activity).total_seconds()

            log.info(f"🔄 Active session found: {ctx.active_session_id[:8]}...")
            log.info(f"   State: {ctx.fsm_state} | Step: {ctx.fsm_current_step}")
            log.info(f"   Expecting response: {ctx.expecting_response}")
            log.info(f"   Age: {age_seconds:.0f}s")

            # If expecting response and recent activity (< 5 minutes)
            if ctx.expecting_response and age_seconds < 300:
                ctx.should_continue_session = True
                log.info(f"   ✅ Should continue session (recent activity)")
        else:
            log.info(f"💤 No active session for user")

        return Result.ok(None)

    except Exception as e:
        log.warning(f"⚠️ Error checking active session: {e}")
        return Result.ok(None)  # Non-fatal
```

**Update MessageContext**:
```python
@dataclass
class MessageContext:
    # ... existing fields ...

    # FSM session context (NEW)
    active_session_id: Optional[str] = None
    fsm_state: Optional[str] = None
    fsm_current_step: Optional[str] = None
    fsm_task_id: Optional[str] = None
    expecting_response: bool = False
    last_bot_options: list = field(default_factory=list)
    should_continue_session: bool = False
```

**Update pipeline flow**:
```python
async def process(self, ...):
    # ... existing stages ...

    # Stage 5: Manage session
    result = await self._manage_session(ctx)

    # Stage 5.5: Check active session (NEW!)
    result = await self._check_active_session(ctx)

    # Stage 6: Classify intent (now with session context)
    result = await self._classify_intent(ctx)
```

---

### Fix 3: Intent Classifier Uses Session Context

**File**: `src/services/intent.py`

**Update classify method signature**:
```python
async def classify(
    self,
    message: str,
    user_id: str,
    last_bot_message: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None,
    # NEW parameters:
    active_session_id: Optional[str] = None,
    fsm_state: Optional[str] = None,
    expecting_response: bool = False,
    should_continue_session: bool = False
) -> Dict[str, Any]:
```

**Add session context to prompt**:
```python
# Build FSM context hint
fsm_hint = ""
if should_continue_session and expecting_response:
    fsm_hint = f"""
⚠️ CONTEXTE DE SESSION ACTIVE CRITIQUE :

L'utilisateur est EN TRAIN de mettre à jour une tâche (état: {fsm_state})
Le bot vient de lui présenter des options et attend une réponse.
Ce message est TRÈS PROBABLEMENT une réponse à ces options.

RÈGLES PRIORITAIRES :
1. Si le message peut être interprété comme un commentaire/description (texte descriptif,
   observation, mention de problème), c'est "update_progress" pour CONTINUER la session,
   PAS un nouveau "report_incident".

2. Ne classifier comme NOUVEAU intent QUE si l'utilisateur dit EXPLICITEMENT :
   - "Annuler" / "Stop" / "Non merci" / "Laisse tomber"
   - "Je veux faire autre chose"
   - Demande claire d'une action différente ("Montre-moi les documents")

3. Exemples dans ce contexte :
   - "le mur est encore fisurré" → update_progress:95 (commentaire sur tâche)
   - "il y a un problème avec la peinture" → update_progress:95 (commentaire)
   - "c'est fait" → update_progress:90 (probablement veut marquer terminé)
   - "annuler" → general:85 (veut arrêter)
   - "montre les documents" → view_documents:80 (nouvelle action différente)

IMPORTANT : Dans le doute, CONTINUER la session active (update_progress) plutôt que
de commencer un nouveau flow.
"""

# Add to classification prompt
prompt = f"""Classifie ce message dans UN seul intent avec confiance :
[... existing intents ...]

{fsm_hint}
{context_section}

Message actuel : {message}
[... rest ...]
"""
```

**Update classification call in pipeline**:
```python
async def _classify_intent(self, ctx: MessageContext) -> Result[None]:
    """Stage 6: Classify user intent with conversation context."""
    try:
        intent_result = await intent_classifier.classify(
            ctx.message_in_french,
            ctx.user_id,
            last_bot_message=ctx.last_bot_message,
            conversation_history=ctx.recent_messages,
            # NEW: Pass session context
            active_session_id=ctx.active_session_id,
            fsm_state=ctx.fsm_state,
            expecting_response=ctx.expecting_response,
            should_continue_session=ctx.should_continue_session
        )
```

---

### Fix 4: Add Migration for `expecting_response` Column (Optional)

Since we're using `session_metadata` JSONB, we don't need a new column. But for performance and clarity, we could add:

```sql
-- Optional: Add explicit column for expecting_response
ALTER TABLE progress_update_sessions
ADD COLUMN IF NOT EXISTS expecting_response BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_progress_sessions_expecting
ON progress_update_sessions(subcontractor_id, expecting_response)
WHERE expecting_response = TRUE;
```

**But this is optional** - we can use `session_metadata->>'expecting_response'` for now.

---

## 📋 Implementation Checklist

### Phase 1: Progress Update Agent (30 min)
- [ ] Find where agent sends "Souhaitez-vous autre chose?" options
- [ ] Add session update after sending options:
  - [ ] Set `fsm_state` to "collecting_data"
  - [ ] Set `session_metadata.expecting_response` to TRUE
  - [ ] Store available actions in metadata
- [ ] Update `last_activity` timestamp
- [ ] Test: Verify session state changes in database

### Phase 2: Message Pipeline Integration (1 hour)
- [ ] Add `_check_active_session()` stage (before intent classification)
- [ ] Update `MessageContext` dataclass with FSM fields
- [ ] Query for active session by user_id
- [ ] Extract FSM context and check if expecting response
- [ ] Set `should_continue_session` flag if appropriate
- [ ] Add comprehensive logging
- [ ] Test: Verify active session is detected

### Phase 3: Intent Classifier Updates (1 hour)
- [ ] Add FSM parameters to `classify()` method signature
- [ ] Build FSM context hint for prompt
- [ ] Add session continuation rules to prompt
- [ ] Pass session context from pipeline to classifier
- [ ] Test with sample messages:
  - [ ] "le mur est encore fisurré" → update_progress:95
  - [ ] "annuler" → general:85
  - [ ] "montrez-moi les documents" → view_documents:80

### Phase 4: Testing (1 hour)
- [ ] **Test Scenario 1**: Continue task update
  - User adds photo
  - Bot shows options
  - User says "le mur est encore fisurré"
  - Expected: Adds comment, stays in session

- [ ] **Test Scenario 2**: Explicit cancel
  - User in task update
  - User says "annuler"
  - Expected: Session abandoned

- [ ] **Test Scenario 3**: New intent mid-update
  - User in task update
  - User says "montrez-moi les documents"
  - Expected: Clarification or switches context

- [ ] Monitor logs for:
  - Active session detection
  - FSM state values
  - Intent classification with context
  - No context loss

### Phase 5: Cleanup (30 min)
- [ ] Update documentation
- [ ] Add inline comments
- [ ] Consider adding telemetry/metrics
- [ ] Review error handling

**Total Time**: ~4 hours

---

## 🎯 Success Criteria

### Before Fix:
```
Bot: Photo ajoutée! Souhaitez-vous autre chose?
User: le mur est encore fisurré

[Session state]: fsm_state='idle', no expecting_response
[Classification]: report_incident (confidence: 90%)
[Action]: Abandons task update, starts incident flow ❌
```

### After Fix:
```
Bot: Photo ajoutée! Souhaitez-vous autre chose?

[Session update]:
  fsm_state='collecting_data'
  session_metadata={'expecting_response': True, ...}

User: le mur est encore fisurré

[Active session check]:
  ✅ Active session found: 824f330f...
  ✅ State: collecting_data
  ✅ Expecting response: TRUE
  ✅ Should continue session: TRUE

[Classification with context]:
  "User is in active task update session, expecting response,
   message is a comment about the task"
  → Intent: update_progress (confidence: 95%)

[Action]: Adds comment, continues session ✅

Bot: ✅ Commentaire ajouté : "le mur est encore fisurré"
     Souhaitez-vous autre chose?
```

---

## 📊 Key Metrics to Monitor

After implementation, track:
1. **Session continuity rate**: % of multi-turn flows that complete without context loss
2. **Intent classification accuracy**: % correctly classified when in active session
3. **False abandonment rate**: % of sessions incorrectly abandoned
4. **User satisfaction**: Fewer "bot confused me" type issues

---

## 🚀 Next Steps

1. **Review this analysis** - Confirm understanding
2. **Approve implementation plan** - 4 hours estimated
3. **Implement Phase 1** - Progress update agent fixes
4. **Implement Phase 2** - Pipeline integration
5. **Implement Phase 3** - Intent classifier updates
6. **Test thoroughly** - All scenarios
7. **Deploy and monitor** - Watch for improvements

---

**Status**: ✅ **ROOT CAUSE IDENTIFIED - READY FOR IMPLEMENTATION**
**Priority**: 🔴 **CRITICAL** - All multi-turn conversations lose context
**Confidence**: 🟢 **HIGH** - Database inspection confirms analysis
