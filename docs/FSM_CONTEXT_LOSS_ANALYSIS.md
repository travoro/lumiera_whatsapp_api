# FSM Context Loss Analysis - "le mur est encore fisurré"

**Date**: 2026-01-16
**Issue**: Bot abandoned task update session and started incident creation flow
**Status**: ⚠️ Root cause identified - FSM tables not created

---

## 📋 What Happened

### User Conversation:
```
11:29:56 Bot: 📸 Photo ajoutée avec succès !
             Souhaitez-vous autre chose ?
             1. 💬 Ajouter un commentaire
             2. ✅ Marquer la tâche comme terminée
             3. 📸 Ajouter une autre photo

11:30:07 User: le mur est encore fisurré

11:30:11 Bot: Je vais vous aider à signaler un incident. 🚨
             Pour créer un rapport d'incident, j'ai besoin de :
             1. 📸 Au moins une photo du problème
             2. 📝 Une description écrite ou audio de ce qui s'est passé
             3. 🏗️ Le chantier concerné
```

### What Should Have Happened:
- ✅ User is responding to option #1 (Ajouter un commentaire)
- ✅ "le mur est encore fisurré" is clearly a comment about the task
- ✅ Bot should stay in task update flow
- ✅ Bot should add this as a comment and continue the session

### What Actually Happened:
- ❌ Bot classified message as "report_incident" with 90% confidence
- ❌ Bot abandoned the task update session
- ❌ Bot started a new incident creation flow
- ❌ Complete context loss

---

## 🔍 Root Cause Analysis

### Investigation Timeline:

**1. FSM is Enabled and Running**
```log
08:13:57 | [FSM] Running session recovery on startup
08:13:57 | [FSM] No orphaned sessions found
08:13:57 | ✅ FSM session recovery complete
08:13:57 | ✅ FSM background cleanup task started (runs every 5 minutes)
```
✅ FSM is active

**2. Session Context Was Loaded**
```log
08:30:08 | ✅ Session: c2eee27a-b40b-4187-aea4-15db4ed88bfd
08:30:08 | 📜 Loaded 3 recent messages for intent context
08:30:08 | 📜 Last bot message: '📸 Photo ajoutée avec succès ! Souhaitez-vous autr...'
```
✅ System loaded session and saw the bot's options menu

**3. Intent Classification Ignored Context**
```log
08:30:10 | ✅ JSON parsed successfully: intent=report_incident, confidence=0.9
08:30:10 | 🤖 Haiku classification: report_incident (confidence: 0.9)
08:30:10 | 🚀 HIGH CONFIDENCE - Attempting fast path
08:30:10 | 🚀 FAST PATH: Handling report incident
```
❌ Intent classifier saw "fisurré" (cracked) and classified as incident

**4. FSM State Was Never Checked**
- Message pipeline loaded session ✅
- Message pipeline loaded conversation history ✅
- Intent classifier received conversation history ✅
- **Intent classifier did NOT check FSM state** ❌

**5. Critical Discovery: FSM Tables Don't Exist**
```bash
$ Query fsm_sessions table
Error: Could not find the table 'public.fsm_sessions' in the schema cache
Hint: Perhaps you meant the table 'public.conversation_sessions'
```

### Root Cause:

**The FSM migration (`009_fsm_tables.sql`) was never run!**

The code is:
- ✅ Trying to check idempotency via FSM (but fails silently)
- ✅ Running session recovery (but finds no sessions because table doesn't exist)
- ✅ Running cleanup tasks (but has nothing to clean)
- ❌ **Not actually storing or checking FSM state**

The FSM integration exists in code but has no database backing, so:
1. Sessions are created in `progress_update_sessions` table
2. BUT fsm_state column doesn't exist (migration not run)
3. FSM StateManager tries to query non-existent tables
4. Errors are caught/ignored silently
5. System falls back to stateless intent classification

---

## 🔧 Technical Analysis

### Current Architecture Gaps:

#### 1. FSM Not Integrated with Intent Classification

**File: `src/services/intent.py` (lines 213-237)**
```python
prompt = f"""Classifie ce message dans UN seul intent avec confiance :
- greeting (hello, hi, bonjour, salut, etc.)
- list_projects (l'utilisateur veut voir ses projets/chantiers)
- list_tasks (l'utilisateur veut voir les tâches pour un projet)
- view_documents (l'utilisateur veut voir les documents/plans d'un projet)
- task_details (l'utilisateur veut voir les détails/description/photos d'une tâche spécifique)
- report_incident (l'utilisateur veut signaler un problème/incident)
- update_progress (l'utilisateur veut mettre à jour la progression d'une tâche)
- escalate (l'utilisateur veut parler à un humain/admin/aide)
- general (tout le reste - questions, clarifications, demandes complexes)

RÈGLES DE CONTEXTE IMPORTANTES :
- Si historique montre LISTE DE PROJETS (🏗️, "projet", "chantier") ET utilisateur sélectionne numéro → list_tasks:95
- Si historique montre LISTE DE TÂCHES (📝, "tâche") ET utilisateur sélectionne numéro → task_details:90
...
```

**Problem**:
- Prompt has context rules for menu navigation
- But NO rules for "bot just asked options, user is responding"
- No FSM state awareness

#### 2. Message Pipeline Doesn't Check FSM State

**File: `src/handlers/message_pipeline.py` (line 462-478)**
```python
async def _classify_intent(self, ctx: MessageContext) -> Result[None]:
    """Stage 6: Classify user intent with conversation context."""
    try:
        intent_result = await intent_classifier.classify(
            ctx.message_in_french,
            ctx.user_id,
            last_bot_message=ctx.last_bot_message,
            conversation_history=ctx.recent_messages
        )
        ctx.intent = intent_result['intent']
        ctx.confidence = intent_result.get('confidence', 0.0)
```

**Problem**:
- Loads session ✅
- Loads conversation history ✅
- Passes to intent classifier ✅
- **But never checks FSM state** ❌

**Missing logic**:
```python
# This should happen BEFORE intent classification:
active_session = await state_manager.get_session(ctx.user_id)
if active_session and active_session['expecting_response']:
    # User is in middle of a flow, use context-aware classification
    ctx.fsm_state = active_session['state']
    ctx.fsm_action = active_session['action']
```

#### 3. StateManager Not Imported in Pipeline

**File: `src/handlers/message_pipeline.py` (lines 1-16)**
```python
from src.integrations.supabase import supabase_client
from src.services.translation import translation_service
from src.services.transcription import transcription_service
from src.services.session import session_service
from src.services.intent import intent_classifier
from src.services.intent_router import intent_router
from src.agent.agent import lumiera_agent
```

**Missing**: `from src.fsm.core import StateManager`

#### 4. StateManager Only Used for Idempotency

**File: `src/handlers/message.py` (lines 726-732, 1084-1088)**
```python
# Only used twice:
# 1. Check if message was already processed
cached_response = await state_manager.check_idempotency(
    user_id=phone_number,
    message_id=message_sid
)

# 2. Record that message was processed
await state_manager.record_idempotency(
    user_id=phone_number,
    message_id=message_sid,
    result={"status": "processed", ...}
)
```

**Problem**: FSM is ONLY used for idempotency, not for conversation flow management!

---

## 📊 Comparison: Expected vs Actual

### Expected FSM Integration (From Implementation Plan):

```
Message arrives
    ↓
1. Check idempotency (using FSM) ✅ (attempted)
    ↓
2. Load user session ✅ (done)
    ↓
3. Check FSM state ❌ (MISSING)
    ↓
    Is user in active session?
    ├─ YES → Use context-aware classification
    │         Priority: continue current flow
    │         "le mur est encore fisurré" → comment in task update
    │
    └─ NO → Use normal intent classification
              Keywords: "fisurré" → report_incident
    ↓
4. Route to handler
```

### Actual Implementation:

```
Message arrives
    ↓
1. Check idempotency (fails silently, tables don't exist)
    ↓
2. Load user session ✅
    ↓
3. Load conversation history ✅
    ↓
4. Classify intent (ignores FSM state) ❌
   → Keywords: "fisurré" → report_incident
    ↓
5. Route to incident handler (wrong!)
```

---

## 🎯 Solution Design

### Phase 1: Database Setup (Required First)

**1. Run FSM Migration**
```bash
# Apply migration to create FSM tables
# This adds:
# - fsm_state column to progress_update_sessions
# - fsm_idempotency_records table
# - fsm_clarification_requests table
# - fsm_transition_log table

venv/bin/python3 scripts/run_migration.py migrations/009_fsm_tables.sql
```

**Why First**: Code is already trying to use these tables. Need to create them.

---

### Phase 2: Integrate FSM State into Intent Classification

**Goal**: Make intent classifier aware of active FSM sessions

**Changes Needed**:

#### A. Update Message Pipeline (src/handlers/message_pipeline.py)

**Add FSM state check before classification**:

```python
async def _check_fsm_state(self, ctx: MessageContext) -> Result[None]:
    """Stage 5.5: Check if user is in an active FSM session."""
    try:
        from src.fsm.core import StateManager
        state_manager = StateManager()

        # Get active session for user
        active_session = await state_manager.get_session(ctx.user_id)

        if active_session:
            ctx.fsm_state = active_session.get('state')
            ctx.fsm_action = active_session.get('action')
            ctx.fsm_task_id = active_session.get('task_id')
            ctx.expecting_response = active_session.get('expecting_response', False)

            log.info(f"🔄 FSM Session Active: state={ctx.fsm_state}, action={ctx.fsm_action}")
        else:
            log.info(f"💤 No active FSM session for user")

        return Result.ok(None)

    except Exception as e:
        # Non-fatal: FSM is optional enhancement
        log.warning(f"⚠️ FSM state check failed: {e}")
        return Result.ok(None)
```

**Update pipeline flow**:
```python
async def process(self, ...):
    # ... existing stages ...

    # Stage 5: Manage session
    result = await self._manage_session(ctx)
    if result.is_error:
        return result

    # Stage 5.5: Check FSM state (NEW!)
    result = await self._check_fsm_state(ctx)
    if result.is_error:
        return result

    # Stage 6: Classify intent (now with FSM context)
    result = await self._classify_intent(ctx)
    if result.is_error:
        return result
```

#### B. Update Intent Classifier (src/services/intent.py)

**Add FSM context to classification**:

```python
async def classify(
    self,
    message: str,
    user_id: str,
    last_bot_message: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None,
    fsm_state: Optional[str] = None,  # NEW
    fsm_action: Optional[str] = None,  # NEW
    expecting_response: bool = False   # NEW
) -> Dict[str, Any]:
    """Classify intent with FSM context awareness."""

    # Build context section
    context_section = ""
    if conversation_history:
        context_section += "Historique récent :\n"
        # ... existing code ...

    # Add FSM context (NEW!)
    fsm_hint = ""
    if expecting_response and fsm_state:
        if fsm_action == "task_update":
            fsm_hint = f"""
⚠️ CONTEXTE FSM CRITIQUE :
- L'utilisateur est EN TRAIN de mettre à jour une tâche (état: {fsm_state})
- Le bot vient de demander une action (commentaire/photo/compléter)
- Ce message est probablement une RÉPONSE à cette demande
- NE PAS classifier comme nouveau intent SAUF si l'utilisateur dit explicitement :
  * "Annuler" / "Stop" / "Non merci"
  * "Je veux faire autre chose"
  * Demande explicite d'une action différente

RÈGLE: Si le message peut être interprété comme un commentaire de tâche (texte descriptif,
observation, description de problème), alors c'est "update_progress" pour continuer la
session active, PAS "report_incident".

Exemple: "le mur est encore fisurré" dans ce contexte = commentaire sur tâche en cours
         (update_progress:95), PAS un nouvel incident (report_incident:30)
"""

    prompt = f"""Classifie ce message dans UN seul intent avec confiance :
    [... existing intents ...]

    {fsm_hint}
    {context_section}

    Message actuel : {message}
    [... rest of prompt ...]
    """
```

**Key changes**:
1. Accept FSM context parameters
2. Add FSM hint to prompt when user is in active session
3. Explicitly tell Claude to prioritize session continuation
4. Lower confidence for new intents when in session

#### C. Update MessageContext Dataclass

```python
@dataclass
class MessageContext:
    """Context object passed through pipeline stages."""

    # ... existing fields ...

    # FSM state (NEW)
    fsm_state: Optional[str] = None
    fsm_action: Optional[str] = None
    fsm_task_id: Optional[str] = None
    expecting_response: bool = False
```

#### D. Pass FSM Context to Classifier

```python
async def _classify_intent(self, ctx: MessageContext) -> Result[None]:
    """Stage 6: Classify user intent with conversation context."""
    try:
        intent_result = await intent_classifier.classify(
            ctx.message_in_french,
            ctx.user_id,
            last_bot_message=ctx.last_bot_message,
            conversation_history=ctx.recent_messages,
            fsm_state=ctx.fsm_state,              # NEW
            fsm_action=ctx.fsm_action,            # NEW
            expecting_response=ctx.expecting_response  # NEW
        )
```

---

### Phase 3: Progress Update Agent Must Set FSM State

**Problem**: Progress update agent sends options but doesn't set `expecting_response=True`

**File: `src/services/progress_update/agent.py`**

**After sending "Souhaitez-vous autre chose?" options**:
```python
# Update FSM session to indicate we're expecting a response
from src.fsm.core import StateManager
state_manager = StateManager()

await state_manager.update_session(
    user_id=user_id,
    updates={
        'expecting_response': True,
        'state': SessionState.AWAITING_ACTION,
        'last_bot_options': ['add_comment', 'mark_complete', 'add_photo']
    }
)
```

---

### Phase 4: Testing Strategy

**Test Scenario 1: Resume Task Update**
```
1. User starts task update
2. User adds photo → FSM state = COLLECTING_DATA
3. Bot asks: "Souhaitez-vous autre chose?" → expecting_response=True
4. User says: "le mur est encore fisurré"
5. Expected: Classified as update_progress (continue session)
6. Expected: Comment added to task
7. Expected: Bot stays in task update flow
```

**Test Scenario 2: Explicit Cancel**
```
1. User in task update (expecting_response=True)
2. User says: "Non merci" or "Annuler"
3. Expected: Session abandoned
4. Expected: Bot confirms cancellation
```

**Test Scenario 3: New Intent Mid-Update**
```
1. User in task update (expecting_response=True)
2. User says: "Montrez-moi mes documents"
3. Expected: Bot asks: "Voulez-vous terminer la mise à jour d'abord ?"
4. Expected: Clarification flow
```

---

## 📈 Expected Impact

### Before Fix:
- ❌ Context loss on every multi-step interaction
- ❌ User confusion (flow switches unexpectedly)
- ❌ FSM provides no value (only idempotency)

### After Fix:
- ✅ Context preserved during multi-step flows
- ✅ Intent classification respects active sessions
- ✅ User can naturally respond to options
- ✅ FSM actively manages conversation state

---

## 🚀 Implementation Checklist

### Step 1: Database (30 minutes)
- [ ] Run migration: `009_fsm_tables.sql`
- [ ] Verify tables created:
  - [ ] `fsm_idempotency_records`
  - [ ] `fsm_clarification_requests`
  - [ ] `fsm_transition_log`
  - [ ] `progress_update_sessions.fsm_state` column
- [ ] Test FSM StateManager can query tables

### Step 2: Pipeline Integration (1 hour)
- [ ] Add `_check_fsm_state()` stage to message pipeline
- [ ] Update `MessageContext` dataclass with FSM fields
- [ ] Import `StateManager` in pipeline
- [ ] Pass FSM context to intent classifier
- [ ] Add logging for FSM state checks

### Step 3: Intent Classifier (1 hour)
- [ ] Add FSM parameters to `classify()` method
- [ ] Build FSM hint section in prompt
- [ ] Test with sample messages
- [ ] Verify intent confidence adjustments

### Step 4: Progress Update Agent (30 minutes)
- [ ] Set `expecting_response=True` after showing options
- [ ] Update FSM state to AWAITING_ACTION
- [ ] Store last bot options in session

### Step 5: Testing (1 hour)
- [ ] Test Scenario 1: Resume task update
- [ ] Test Scenario 2: Explicit cancel
- [ ] Test Scenario 3: New intent mid-update
- [ ] Monitor logs for FSM state transitions
- [ ] Verify no context loss

**Total Time**: ~4 hours

---

## 📝 Files to Modify

### Database:
1. Run `migrations/009_fsm_tables.sql`

### Code Changes:
1. `src/handlers/message_pipeline.py` - Add FSM state checking
2. `src/services/intent.py` - Add FSM context awareness
3. `src/services/progress_update/agent.py` - Set expecting_response flag
4. `src/fsm/core.py` - Verify StateManager works with new tables

### Documentation:
1. This file: `docs/FSM_CONTEXT_LOSS_ANALYSIS.md`
2. Update: `docs/architecture/FSM_IMPLEMENTATION_SUMMARY.md`

---

## 🎯 Success Criteria

When this is fixed, the conversation should go:

```
Bot: 📸 Photo ajoutée avec succès !
     Souhaitez-vous autre chose ?
     1. 💬 Ajouter un commentaire
     2. ✅ Marquer la tâche comme terminée
     3. 📸 Ajouter une autre photo

User: le mur est encore fisurré

Bot: ✅ Commentaire ajouté : "le mur est encore fisurré"

     Souhaitez-vous autre chose ?
     1. ✅ Marquer la tâche comme terminée
     2. 📸 Ajouter une autre photo
     3. ❌ Annuler
```

**Key indicators**:
- ✅ Intent classified as `update_progress` (NOT `report_incident`)
- ✅ Message added as comment to active task
- ✅ Session continues (not abandoned)
- ✅ FSM logs show: "FSM Session Active: state=collecting_data"

---

**Status**: ⚠️ Awaiting approval to implement solution
**Priority**: **HIGH** - Core FSM functionality broken
**Impact**: All multi-turn conversations currently lose context
