# List Option Text Truncation Fix

**Date**: 2026-01-16 12:19 UTC
**Status**: ✅ **FIXED AND DEPLOYED**

---

## 🎯 Problem Reported

**User reported multiple issues**:

1. Option text getting truncated: "Non, changer de tâche/projet" → "Non, changer de tâche/pr"
2. LLM misunderstanding "changer de projet" and responding as "changer de tâche dans le même projet"
3. Need character limits for list options in general

---

## 🔍 Root Cause Analysis

### Issue 1: Text Truncation

**Problem**: WhatsApp interactive lists have a **24-character limit** for list item titles.

**Evidence**:
- File: `src/utils/whatsapp_formatter.py` line 476
- Comment: `"item" (≤24 chars)`
- File: `src/utils/response_parser.py` line 76
- Comment: `# WhatsApp/Twilio limit: 24 characters total (including emoji)`

**Original text**: "Non, changer de tâche/projet" = **30 characters**
**Result**: Text got truncated to 24 chars → "Non, changer de tâche/pr"

---

### Issue 2: Agent Misunderstanding

**Problem**: Agent not distinguishing between "changer de projet" vs "changer de tâche"

**Example from user**:
```
User: "Changer de projet"
Bot: "D'accord Jean, vous souhaitez changer de tâche dans le même projet. 😊"
```

**Root cause**: Agent instructions didn't specify how to handle this clarification.

---

## 🔧 The Fix

### Fix 1: Shorten Option Text

**File**: `src/services/progress_update/tools.py` (lines 65-66 and 114-115)

**Before**:
```
1. Oui, c'est ça
2. Non, changer de tâche/projet"  ← 30 chars (TRUNCATED)
```

**After**:
```
1. Oui, c'est ça
2. Non, autre tâche"  ← 17 chars (FITS!)
```

---

### Fix 2: Add Agent Instructions for Clarification

**File**: `src/services/progress_update/tools.py` (lines 68-74 and 117-123)

**Added**:
```
IMPORTANT: Keep option 2 text SHORT (max 24 chars for WhatsApp limit)!
- If user says 1 or "oui": USE start_progress_update_session_tool
- If user says 2 or "non": Ask user if they want to change task in same project OR change project entirely
  * If user says "changer de projet" or "autre projet": Call list_projects_tool to show all projects
  * If user says "changer de tâche" or "autre tâche": Call get_active_task_context_tool to show task list
```

---

## ✅ Expected Behavior After Fix

### Scenario 1: User Confirms Task

```
Bot: "Je comprends, vous souhaitez mettre à jour la tâche Task test 1 pour le projet Unknown Project ?

1. Oui, c'est ça
2. Non, autre tâche"  ← NO TRUNCATION!

User: [Selects option 1]
Bot: Starts progress update session ✅
```

---

### Scenario 2: User Wants Different Task

```
Bot: "Je comprends, vous souhaitez mettre à jour la tâche Task test 1 pour le projet Unknown Project ?

1. Oui, c'est ça
2. Non, autre tâche"

User: [Selects option 2]
Bot: "Souhaitez-vous changer de tâche dans le même projet, ou changer complètement de projet ?"

User: "Changer de projet"
Bot: Calls list_projects_tool → Shows all projects ✅
```

---

### Scenario 3: User Wants Different Task in Same Project

```
Bot: "Souhaitez-vous changer de tâche dans le même projet, ou changer complètement de projet ?"

User: "Changer de tâche"
Bot: Calls get_active_task_context_tool → Shows task list ✅
```

---

## 📊 WhatsApp Interactive List Limits

### Character Limits:

| Field | Limit | Where Used |
|-------|-------|------------|
| **List item title** | **24 chars** | Option text, task names, etc. |
| **List item description** | **72 chars** | Optional additional info |
| **Button text** | **20 chars** | "Options", "Choose", etc. |
| **Section title** | **24 chars** | Section headers |

### Validation:

**Files that enforce limits**:
1. `src/utils/whatsapp_formatter.py`:
   - `safe_truncate()` function (line 415)
   - Applied at lines 481, 482, 498, 530, 531, 545, 594, 605

2. `src/utils/response_parser.py`:
   - Title truncation at line 89: `title[:24]`
   - Description truncation at line 90: `description[:72]`

---

## 🧪 Testing

### Test 1: Confirmation Dialog

```
1. Send: "mise à jour"
2. Expect: Confirmation with options:
   - "Oui, c'est ça"
   - "Non, autre tâche"  ← FULL TEXT VISIBLE
```

### Test 2: Change Project Flow

```
1. Send: "mise à jour"
2. Select: "Non, autre tâche"
3. Expect: "Souhaitez-vous changer de tâche dans le même projet, ou changer complètement de projet ?"
4. Send: "Changer de projet"
5. Expect: List of all projects ✅
```

### Test 3: Change Task Flow

```
1. Send: "mise à jour"
2. Select: "Non, autre tâche"
3. Send: "Changer de tâche"
4. Expect: List of tasks in current project ✅
```

---

## 🔍 Log Signatures

**What to look for**:

```
AGENT INSTRUCTIONS - This is a CONFIRMATION, not a task list!
Say: "Je comprends, vous souhaitez mettre à jour la tâche...

1. Oui, c'est ça
2. Non, autre tâche"

IMPORTANT: This should be formatted as list_type="option" (not "tasks")!
IMPORTANT: Keep option 2 text SHORT (max 24 chars for WhatsApp limit)!
```

---

## 📋 Files Changed

1. **src/services/progress_update/tools.py**
   - Lines 65-66: Changed "Non, changer de tâche/projet" → "Non, autre tâche"
   - Lines 68-74: Added agent instructions for handling clarification
   - Lines 114-115: Same change for second confirmation
   - Lines 117-123: Same agent instructions

---

## ⚠️ Important Notes

### For Developers:

1. **Always check character limits** when creating list options:
   - Title: 24 chars max
   - Description: 72 chars max
   - Button text: 20 chars max

2. **Use short, clear text** for options:
   - ✅ "Non, autre tâche" (17 chars)
   - ❌ "Non, changer de tâche/projet" (30 chars)

3. **Add clarification flows** when needed:
   - If option is ambiguous, ask follow-up question
   - Agent can call different tools based on user's clarification

### For LLM Instructions:

Always include character limit reminders in agent instructions:
```
IMPORTANT: Keep option text SHORT (max 24 chars for WhatsApp limit)!
```

---

## 📈 Impact

### Before Fix:
- ❌ Option text truncated: "...tâche/pr"
- ❌ User confused by truncation
- ❌ Agent misunderstood "changer de projet"
- ❌ Poor user experience

### After Fix:
- ✅ Option text fits: "Non, autre tâche"
- ✅ Full text visible to user
- ✅ Agent asks clarification
- ✅ Agent correctly handles "changer de projet" vs "changer de tâche"
- ✅ Better user experience

---

## ✅ Deployment Status

**Server Status**: ✅ RUNNING with fix
**Deployed**: 2026-01-16 12:19:12 UTC
**Process**: Restarted with changes

**Files Changed**:
1. `src/services/progress_update/tools.py` - Shortened option text, added clarification logic

---

## 💡 Summary

**What Changed**:
- ❌ Removed long text: "Non, changer de tâche/projet" (30 chars)
- ✅ Added short text: "Non, autre tâche" (17 chars)
- ✅ Added clarification flow for "changer de projet" vs "changer de tâche"
- ✅ Added character limit reminder in agent instructions

**Why**:
- WhatsApp has 24-character limit for list item titles
- Long text was being truncated mid-word
- Agent needed better instructions for handling ambiguous responses

**Result**:
- Full text visible in WhatsApp
- Agent asks clarification when user says "non"
- Agent correctly distinguishes "changer de projet" vs "changer de tâche"
- Better user experience

---

**Fixed By**: Claude Code
**Requested By**: User
**Date**: 2026-01-16 12:19 UTC
**Confidence**: HIGH - Character limits are enforced by WhatsApp/Twilio
