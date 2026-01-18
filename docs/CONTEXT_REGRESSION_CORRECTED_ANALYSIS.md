# Context Regression - Corrected Analysis

**Date**: 2026-01-17
**Status**: 🟡 **CLARIFICATION NEEDED**

---

## Executive Summary - CORRECTED

After reviewing commit `1857b07` and user feedback, I need to correct my initial analysis:

### What I Initially Thought (INCORRECT):
- Intent classifier lost access to conversation_history
- Commit 1857b07 broke intent classification

### What Actually Happened (CORRECT):
1. **`intent.py` was NOT modified** in commit 1857b07
2. **`conversation_history` IS being passed** to intent classifier (unchanged)
3. **`agent_state` was NEVER passed** to intent classifier (pre-existing gap)
4. **`user_context` was NEVER passed** to intent classifier either

---

## What Commit 1857b07 Actually Removed

### Files Modified (8 files, 523 lines removed):
1. `migrations/database_migrations_v2.sql` - DROP TABLE user_context
2. `migrations/verify_migrations.py` - Verification logic
3. `src/agent/agent.py` - Memorization instructions (16 lines)
4. `src/agent/tools.py` - remember_user_context_tool (100 lines)
5. `src/handlers/message.py` - user_context usage (1 line)
6. `src/integrations/supabase.py` - Database methods (96 lines)
7. `src/services/user_context.py` - Entire service (217 lines)
8. `src/utils/handler_helpers.py` - Helper functions (adjusted)

### What Was Removed from agent.py:

```python
# 🧠 MÉMORISATION ET PERSONNALISATION
1. ✅ TOUJOURS mémoriser les informations importantes avec remember_user_context_tool
2. ✅ Mémoriser quand l'utilisateur mentionne:
   - Son rôle/métier (ex: "Je suis électricien" → role: electricien)
   - Ses préférences (ex: "Appelez-moi le matin" → preferred_contact_time: morning)
   - Le projet en cours de discussion (ex: "Sur le chantier Rénovation Bureau" → current_project_name: Rénovation Bureau)
   - Des faits utiles (taille équipe, outils préférés, problèmes fréquents)
3. ✅ Utiliser le contexte existant pour personnaliser les réponses
4. ⚠️ Ne PAS redemander des infos déjà mémorisées

Types de contexte à mémoriser:
- 'fact': Faits généraux (rôle, expérience, spécialités)
- 'preference': Préférences utilisateur (horaires, communication)
- 'state': État temporaire (projet actuel, tâche en cours)
- 'entity': Entités nommées (projet favori, lieu fréquent)
```

**Impact**: Full agent (Opus) lost ability to learn and remember user facts.

---

## What Was NOT Affected

### Intent Classifier Still Receives:

✅ **Conversation History** - UNCHANGED
```python
# src/handlers/message_pipeline.py:647-661
intent_result = await intent_classifier.classify(
    ctx.message_in_french,
    ctx.user_id,
    last_bot_message=ctx.last_bot_message,
    conversation_history=ctx.recent_messages,  # ✅ Still works
    active_session_id=ctx.active_session_id,
    fsm_state=ctx.fsm_state,
    expecting_response=ctx.expecting_response,
    should_continue_session=ctx.should_continue_session,
    has_media=has_media,
    media_type=media_type_simple,
    num_media=num_media,
)
```

**Example from Production**:
```
Historique récent de conversation :
Bot: ✅ Session de mise à jour démarrée pour : Task test 1
User: le mur est encore fisurré
Bot: ✅ Commentaire ajouté avec succès !
```

This proves conversation_history IS working and was NOT affected.

---

## Two Separate Issues (Not Caused by Commit 1857b07)

### Issue 1: Intent Classifier Never Had agent_state (Pre-existing Gap)

**What's Missing**:
- ❌ `active_project_id` - Which project user is working on
- ❌ `active_project_name` - Human-readable project name
- ❌ `active_task_id` - Which task user selected
- ❌ `active_task_title` - Human-readable task title

**Where This Data Exists**:
```python
# Stored in database (subcontractors table)
active_project_id: UUID
active_project_last_activity: TIMESTAMP
active_task_id: UUID
active_task_last_activity: TIMESTAMP

# Passed to full agent (Opus)
agent_state = await agent_state_builder.build_state(user_id, language, session_id)
state_context = agent_state.to_prompt_context()  # ✅ Full agent gets this
```

**Impact**:
- Intent classifier can't differentiate "2" (project #2) vs "2" (task #2)
- Lower confidence for numeric selections
- More fallbacks to slow Opus agent
- But this was ALWAYS the case, not a regression

### Issue 2: Full Agent Lost Personalization (Caused by Commit 1857b07)

**What Was Lost**:
```python
# Before: Agent could remember
"Je suis électricien" → remember_user_context_tool(role: "electricien")
"Appelez-moi le matin" → remember_user_context_tool(preferred_contact_time: "morning")
"Le chantier Rénovation Bureau" → remember_user_context_tool(current_project_name: "Rénovation Bureau")

# After: Agent has no memory of learned facts
- Can't remember user's role
- Can't remember preferences
- Can't personalize responses
```

**What Still Works**:
```python
# agent_state still provides authoritative project/task context
[État actuel - Source de vérité]
Projet actif: Champigny (ID: abc-123...)
Tâche active: Réparer le mur (ID: def-456...)
```

---

## Root Cause: Two Context Systems with Different Purposes

### System 1: agent_state (Still Works)

**Purpose**: Authoritative "what user is currently working on"
**Storage**: `subcontractors` table columns
**Content**:
```python
active_project_id: UUID      # Which project RIGHT NOW
active_task_id: UUID         # Which task RIGHT NOW
```

**Who Gets It**:
- ✅ Full agent (Opus) - receives via state_context
- ❌ Intent classifier (Haiku) - does NOT receive

**Status**: Working correctly, but not passed to intent classifier

### System 2: user_context (REMOVED in 1857b07)

**Purpose**: Learned facts and preferences over time
**Storage**: `user_context` table (now deleted)
**Content**:
```json
{
  "role": "electrician",
  "preferred_contact_time": "morning",
  "current_project_name": "Champigny",
  "favorite_tool": "multimeter"
}
```

**Who Got It**:
- ✅ Full agent (Opus) - received via user_context parameter
- ❌ Intent classifier (Haiku) - NEVER received

**Status**: REMOVED, agent can't learn or remember facts

---

## The Real Question: What Regression Are We Seeing?

Based on my analysis, there are THREE possible regressions to investigate:

### Possibility 1: Intent Classification Quality Decreased
**Hypothesis**: Without user_context, intent classification is worse
**Problem**: user_context was NEVER passed to intent classifier
**Verdict**: ❌ This can't be the cause

### Possibility 2: Agent Responses Are Less Personalized
**Hypothesis**: Agent forgot user preferences/facts
**Problem**: Agent can't remember "I'm an electrician" anymore
**Verdict**: ✅ This IS a real regression from commit 1857b07

### Possibility 3: Intent Classifier Can't Handle Project/Task Context
**Hypothesis**: Without agent_state, intent classifier misclassifies numeric selections
**Problem**: agent_state was NEVER passed to intent classifier
**Verdict**: ⚠️ This is a pre-existing gap, not caused by commit 1857b07

---

## What We Need to Clarify

**Questions for User**:

1. **What specific regression are you observing?**
   - Is intent classification confidence lower?
   - Are numeric selections being misclassified?
   - Is the agent less personalized in responses?
   - Are users having to re-select projects more often?

2. **When did this regression start?**
   - After commit 1857b07 specifically?
   - Or is it a longer-standing issue?

3. **What was working before that isn't working now?**
   - Agent remembered user facts? (Yes, this broke)
   - Intent classification was better? (Need evidence)
   - Project/task context was available? (This was never in intent classifier)

---

## Comparison: Before vs After Commit 1857b07

### Intent Classifier:

| Feature | Before 1857b07 | After 1857b07 | Changed? |
|---------|----------------|---------------|----------|
| conversation_history | ✅ Received | ✅ Received | ❌ No |
| last_bot_message | ✅ Received | ✅ Received | ❌ No |
| FSM state | ✅ Received | ✅ Received | ❌ No |
| active_project_id | ❌ NOT received | ❌ NOT received | ❌ No |
| active_task_id | ❌ NOT received | ❌ NOT received | ❌ No |
| user_context (facts) | ❌ NOT received | ❌ NOT received | ❌ No |

**Verdict**: Intent classifier was NOT affected by commit 1857b07

### Full Agent (Opus):

| Feature | Before 1857b07 | After 1857b07 | Changed? |
|---------|----------------|---------------|----------|
| state_context (agent_state) | ✅ Received | ✅ Received | ❌ No |
| user_context (learned facts) | ✅ Received | ❌ Empty string | ✅ YES |
| remember_user_context_tool | ✅ Available | ❌ Removed | ✅ YES |
| conversation_history | ✅ Received | ✅ Received | ❌ No |

**Verdict**: Full agent lost personalization ability

---

## Correct Problem Statement

### What Broke in Commit 1857b07:
✅ **Full agent lost memory and personalization**
- Can't remember user's role ("I'm an electrician")
- Can't remember preferences ("Call me in morning")
- Can't store learned facts
- Can't build up knowledge over time

### What Did NOT Break:
❌ Intent classifier was unchanged
❌ conversation_history still works
❌ agent_state (project/task context) still works for full agent

### What Was Already Missing (Pre-existing):
⚠️ Intent classifier never had agent_state
⚠️ Intent classifier never had user_context
⚠️ Intent classifier relies only on conversation_history + FSM state

---

## Recommended Next Steps

### Step 1: Identify the Actual Regression
**Action**: User describes what specific behavior changed after commit 1857b07

**Possibilities**:
- Agent is less personalized? → Restore user_context or use agent_state
- Intent classification is worse? → Need evidence this actually changed
- Numeric selections fail? → This is pre-existing, add agent_state to intent classifier

### Step 2: Choose Solution Based on Root Cause

**If problem is: Agent personalization**
- Option A: Restore user_context system (brings back learning)
- Option B: Use agent_state for current project/task only (simpler)
- Option C: Hybrid (use agent_state, skip learning system)

**If problem is: Intent classification confidence**
- Option A: Add agent_state to intent classifier (my recommendation)
- Option B: Improve prompt engineering with existing context
- Option C: Collect metrics to prove issue exists

**If problem is: Both**
- Implement both solutions separately

---

## Conclusion

### Corrected Understanding:

1. **Commit 1857b07 did NOT affect intent classifier** - intent.py unchanged
2. **conversation_history IS working** - user's example proves this
3. **Intent classifier never had agent_state** - pre-existing gap
4. **Full agent lost user_context** - real regression for personalization

### Key Insight:

The regression is likely about **full agent personalization**, not intent classification. The intent classifier has the same information it always had.

However, there IS a pre-existing opportunity to improve intent classification by passing agent_state (project/task context), but this isn't a regression - it's a feature gap that existed before commit 1857b07.

---

*Last Updated: 2026-01-17*
*Corrected after user feedback*
