# FSM Implementation Plan: Task Update System Refactoring

**Date:** 2026-01-16
**Target System:** Lumiera WhatsApp API - Conversational Task Update Flow
**Plan Type:** Phased Refactoring with Backward Compatibility
**Estimated Duration:** 4-6 weeks (with testing)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Guiding Principles](#2-guiding-principles)
3. [Phase 0: Foundation & Preparation](#phase-0-foundation--preparation-week-1)
4. [Phase 1: State Management Consolidation](#phase-1-state-management-consolidation-week-2)
5. [Phase 2: FSM Core Implementation](#phase-2-fsm-core-implementation-week-3)
6. [Phase 3: Intent Hierarchy & Routing](#phase-3-intent-hierarchy--routing-week-4)
7. [Phase 4: Clarification & Error Handling](#phase-4-clarification--error-handling-week-5)
8. [Phase 5: Testing & Optimization](#phase-5-testing--optimization-week-6)
9. [Rollback Plan](#rollback-plan)
10. [Success Metrics](#success-metrics)

---

## 1. Executive Summary

### Problem Statement
The current task update system suffers from:
- **AI-owned state transitions** (non-deterministic)
- **4 overlapping state management systems** (coordination issues)
- **Intent classification overriding session context** (data corruption risk)
- **350+ line nested list selection logic** (unmaintainable)
- **No draft/resume mechanism** (lost work)

### Solution Overview
Implement **explicit FSM with AI as advisor**, not decision maker:
```
FROM: Intent → AI decides → State changes (implicit)
TO:   Intent → FSM validates → AI advises → State changes (explicit)
```

### Key Benefits
- 🎯 Predictable bugs (state machine visible)
- 📊 Meaningful logs (all transitions logged)
- 🎨 Consistent UX (deterministic behavior)
- 🛡️ Contained AI mistakes (FSM validates)

### Risk Mitigation
- **Phased rollout** - one component at a time
- **Feature flags** - toggle between old/new system
- **Backward compatibility** - existing flows unaffected
- **Extensive testing** - 50+ scenario tests
- **Rollback plan** - revert in < 30 minutes

---

## 2. Guiding Principles

### Architecture Consistency
1. **Reuse existing patterns** - Don't reinvent the wheel
2. **Single Responsibility** - One module, one job
3. **Clear boundaries** - FSM → Routing → Handlers → Tools
4. **Type safety** - Pydantic models everywhere
5. **Backward compatible** - Old flows work during transition

### Code Quality
1. **Short functions** - Max 50 lines per function
2. **Shallow nesting** - Max 3 levels deep
3. **Documented** - Docstrings + inline comments
4. **Tested** - Unit tests for all state transitions
5. **Logged** - Every transition, conflict, error

### Simplicity Over Cleverness
1. **Explicit > Implicit** - State visible in code
2. **Simple > Complex** - Readable by junior devs
3. **Standard > Custom** - Use Python stdlib when possible
4. **Boring > Exciting** - Proven patterns over novel approaches

### Remove Redundancy
1. **Consolidate state systems** - 4 → 1
2. **Standardize responses** - Single envelope format
3. **Extract common logic** - Decorators for error handling
4. **Centralize config** - No magic numbers

### Extensive Observability
1. **Log all state changes** - With before/after context
2. **Log all conflicts** - Intent vs session
3. **Log all clarifications** - Questions asked + answers
4. **Structured logs** - JSON format for parsing
5. **Correlation IDs** - Track full conversation flow

---

## Phase 0: Foundation & Preparation (Week 1)

### Goals
- Set up infrastructure for phased rollout
- Create base classes/interfaces
- Implement feature flags
- Establish logging standards

### Tasks

#### 0.1 Feature Flag System (Day 1)
**File:** `src/config.py`

```python
class FeatureFlags(BaseSettings):
    """Feature flags for gradual rollout"""

    # FSM rollout flags
    enable_fsm: bool = False  # Master switch for FSM
    enable_state_consolidation: bool = False
    enable_intent_hierarchy: bool = False
    enable_draft_resume: bool = False

    # Monitoring flags
    enable_structured_logging: bool = True
    enable_state_transition_logs: bool = True

    # Rollback flags
    force_legacy_routing: bool = False

    class Config:
        env_prefix = "FEATURE_"
```

**Testing:**
- [ ] Flags load from environment
- [ ] Flags default to safe values (False)
- [ ] Flags can be toggled without restart (reload config)

---

#### 0.2 Structured Logging Setup (Day 1-2)
**File:** `src/utils/structured_logger.py`

```python
from loguru import logger
import json
from contextvars import ContextVar
from typing import Optional, Dict, Any

# Correlation ID for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)

class StructuredLogger:
    """Wrapper for structured logging with correlation IDs"""

    def __init__(self, module_name: str):
        self.module = module_name

    def _build_context(self, event: str, **kwargs) -> Dict[str, Any]:
        """Build structured log context"""
        context = {
            "module": self.module,
            "event": event,
            "correlation_id": correlation_id_var.get(),
            **kwargs
        }
        return context

    def log_state_transition(
        self,
        user_id: str,
        from_state: str,
        to_state: str,
        trigger: str,
        session_id: Optional[str] = None
    ):
        """Log FSM state transition"""
        context = self._build_context(
            event="state_transition",
            user_id=user_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            session_id=session_id
        )
        logger.info(json.dumps(context))

    def log_intent_conflict(
        self,
        user_id: str,
        current_intent: str,
        new_intent: str,
        session_state: str,
        resolution: str
    ):
        """Log intent conflict and resolution"""
        context = self._build_context(
            event="intent_conflict",
            user_id=user_id,
            current_intent=current_intent,
            new_intent=new_intent,
            session_state=session_state,
            resolution=resolution
        )
        logger.warning(json.dumps(context))

    def log_clarification(
        self,
        user_id: str,
        question: str,
        options: list,
        reason: str
    ):
        """Log clarification question asked to user"""
        context = self._build_context(
            event="clarification_asked",
            user_id=user_id,
            question=question,
            options=options,
            reason=reason
        )
        logger.info(json.dumps(context))

# Usage:
# log = StructuredLogger(__name__)
# log.log_state_transition(user_id, "IDLE", "TASK_SELECTION", "update_intent")
```

**Testing:**
- [ ] Logs output as JSON
- [ ] Correlation IDs propagate through request
- [ ] All log methods work correctly

---

#### 0.3 Base FSM Classes (Day 2-3)
**File:** `src/fsm/base.py`

```python
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class SessionState(str, Enum):
    """FSM states for task update flow"""
    IDLE = "idle"
    TASK_SELECTION = "task_selection"
    AWAITING_ACTION = "awaiting_action"
    COLLECTING_DATA = "collecting_data"
    CONFIRMATION_PENDING = "confirmation_pending"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

class StateTransition(BaseModel):
    """Represents a state transition"""
    from_state: SessionState
    to_state: SessionState
    trigger: str  # What caused the transition
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class FSMContext(BaseModel):
    """Context passed to FSM for decision making"""
    user_id: str
    current_state: SessionState
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    project_id: Optional[str] = None
    intent: str
    message: str
    confidence: float
    active_task_id: Optional[str] = None  # From context service

class FSMTransitionRule(BaseModel):
    """Defines a valid state transition"""
    from_state: SessionState
    to_state: SessionState
    triggers: List[str]  # What can cause this transition
    validators: List[str] = []  # Validation functions to run
    side_effects: List[str] = []  # Side effects to trigger (save draft, etc)

# Define valid transitions (FSM rules)
TRANSITION_RULES: Dict[SessionState, List[FSMTransitionRule]] = {
    SessionState.IDLE: [
        FSMTransitionRule(
            from_state=SessionState.IDLE,
            to_state=SessionState.TASK_SELECTION,
            triggers=["update_intent", "user_requests_update"],
            validators=["user_authenticated", "no_active_session"]
        )
    ],
    SessionState.TASK_SELECTION: [
        FSMTransitionRule(
            from_state=SessionState.TASK_SELECTION,
            to_state=SessionState.AWAITING_ACTION,
            triggers=["task_selected", "task_confirmed"],
            validators=["task_exists", "user_has_permission"],
            side_effects=["create_session", "log_session_start"]
        ),
        FSMTransitionRule(
            from_state=SessionState.TASK_SELECTION,
            to_state=SessionState.ABANDONED,
            triggers=["user_cancels", "conflicting_intent", "timeout"],
            side_effects=["cleanup_temp_state"]
        )
    ],
    SessionState.AWAITING_ACTION: [
        FSMTransitionRule(
            from_state=SessionState.AWAITING_ACTION,
            to_state=SessionState.COLLECTING_DATA,
            triggers=["photo_received", "comment_received"],
            side_effects=["save_data", "increment_counter"]
        ),
        FSMTransitionRule(
            from_state=SessionState.AWAITING_ACTION,
            to_state=SessionState.CONFIRMATION_PENDING,
            triggers=["completion_signal", "user_says_done"],
            validators=["at_least_one_update"],
            side_effects=["prepare_summary"]
        ),
        FSMTransitionRule(
            from_state=SessionState.AWAITING_ACTION,
            to_state=SessionState.ABANDONED,
            triggers=["user_cancels", "conflicting_high_priority_intent", "timeout"],
            side_effects=["save_draft", "clear_session", "notify_user"]
        )
    ],
    SessionState.COLLECTING_DATA: [
        FSMTransitionRule(
            from_state=SessionState.COLLECTING_DATA,
            to_state=SessionState.AWAITING_ACTION,
            triggers=["data_saved"],
            side_effects=["confirm_save", "prompt_next_action"]
        )
    ],
    SessionState.CONFIRMATION_PENDING: [
        FSMTransitionRule(
            from_state=SessionState.CONFIRMATION_PENDING,
            to_state=SessionState.COMPLETED,
            triggers=["user_confirms"],
            validators=["session_valid"],
            side_effects=["mark_task_complete", "clear_session", "send_confirmation"]
        ),
        FSMTransitionRule(
            from_state=SessionState.CONFIRMATION_PENDING,
            to_state=SessionState.AWAITING_ACTION,
            triggers=["user_declines", "user_goes_back"],
            side_effects=["cancel_completion"]
        )
    ],
    SessionState.COMPLETED: [],  # Terminal state
    SessionState.ABANDONED: []   # Terminal state
}

class FSMValidationError(Exception):
    """Raised when state transition validation fails"""
    pass

class FSMTransitionError(Exception):
    """Raised when invalid transition attempted"""
    pass
```

**Testing:**
- [ ] All states defined
- [ ] All transition rules valid
- [ ] Enum serialization works
- [ ] Pydantic models validate correctly

---

#### 0.4 Documentation Templates (Day 3)
**Files:**
- `docs/architecture/FSM_STATES.md` - State definitions
- `docs/architecture/FSM_TRANSITIONS.md` - Transition rules
- `docs/architecture/INTENT_HIERARCHY.md` - Priority levels

**Content:** Document all FSM states, transitions, and intent priorities

---

#### 0.5 Testing Infrastructure (Day 3-4)
**File:** `tests/test_fsm_base.py`

```python
import pytest
from src.fsm.base import SessionState, FSMContext, TRANSITION_RULES

class TestFSMBase:
    """Test FSM foundation"""

    def test_all_states_have_transition_rules(self):
        """Every state should have defined transitions"""
        for state in SessionState:
            assert state in TRANSITION_RULES

    def test_transition_rules_reference_valid_states(self):
        """All transition rules reference valid states"""
        for state, rules in TRANSITION_RULES.items():
            for rule in rules:
                assert rule.from_state in SessionState
                assert rule.to_state in SessionState

    def test_terminal_states_have_no_outbound_transitions(self):
        """COMPLETED and ABANDONED should be terminal"""
        assert TRANSITION_RULES[SessionState.COMPLETED] == []
        assert TRANSITION_RULES[SessionState.ABANDONED] == []

    def test_fsm_context_validation(self):
        """FSMContext validates correctly"""
        context = FSMContext(
            user_id="user123",
            current_state=SessionState.IDLE,
            intent="update_progress",
            message="Update task",
            confidence=0.95
        )
        assert context.user_id == "user123"
        assert context.current_state == SessionState.IDLE
```

**Testing:**
- [ ] All FSM base tests pass
- [ ] 100% coverage on base classes

---

### Phase 0 Deliverables
- ✅ Feature flags configured
- ✅ Structured logging operational
- ✅ Base FSM classes defined
- ✅ Documentation templates created
- ✅ Testing infrastructure ready

### Phase 0 Acceptance Criteria
- [ ] Feature flags toggle without restart
- [ ] Structured logs output JSON
- [ ] All FSM base tests pass
- [ ] Documentation reviewed and approved

---

## Phase 1: State Management Consolidation (Week 2)

### Goals
- Consolidate 4 overlapping state systems into 1
- Create unified `StateManager` interface
- Maintain backward compatibility with existing code
- Add comprehensive logging

### Current State Analysis

**4 Systems to Consolidate:**
1. **`project_context.py`** - DB-backed active project/task (7h/24h expiry)
2. **`agent_state.py`** - Prompt injection context (built fresh each request)
3. **`execution_context.py`** - Thread-safe tool call tracking (request-scoped)
4. **`user_context.py`** - User personalization (facts/preferences)

**Key Challenge:** Maintain backward compatibility while consolidating

---

### Tasks

#### 1.1 Create Unified StateManager (Day 1-2)
**File:** `src/fsm/state_manager.py`

```python
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger
from src.integrations.supabase import supabase_client
from src.services.project_context import ProjectContextService
from src.agent.execution_context import get_execution_context
from src.fsm.base import SessionState, FSMContext
from src.utils.structured_logger import StructuredLogger

log = StructuredLogger(__name__)

class UpdateSession(BaseModel):
    """Unified session model"""
    session_id: str
    user_id: str
    task_id: str
    project_id: str
    state: SessionState
    images_uploaded: int = 0
    comments_added: int = 0
    status_changed: bool = False
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

class StateManager:
    """
    Unified state management for conversational AI flows.

    Consolidates:
    - DB state (active project/task, sessions)
    - Execution state (tool calls, escalations)
    - User personalization (kept separate, referenced)

    Responsibilities:
    - Get/set active project/task context
    - Create/update/close update sessions
    - Validate state transitions
    - Coordinate cascade updates (project change → clear task)
    """

    def __init__(self):
        self.project_context = ProjectContextService()

    # ===== PROJECT/TASK CONTEXT (DB Layer) =====

    async def get_active_project(self, user_id: str) -> Optional[str]:
        """Get active project ID for user (7h expiration)"""
        return await self.project_context.get_active_project(user_id)

    async def set_active_project(
        self,
        user_id: str,
        project_id: str,
        project_name: str
    ) -> bool:
        """
        Set active project for user.

        Side effects:
        - Clears active task (cascade)
        - Logs state change
        """
        success = await self.project_context.set_active_project(
            user_id, project_id, project_name
        )

        if success:
            # Cascade: Clear active task when project changes
            await self.clear_active_task(user_id)
            log.log_state_transition(
                user_id=user_id,
                from_state="no_project",
                to_state="project_selected",
                trigger=f"set_project:{project_id}"
            )

        return success

    async def get_active_task(self, user_id: str) -> Optional[str]:
        """Get active task ID for user (24h expiration)"""
        return await self.project_context.get_active_task(user_id)

    async def set_active_task(
        self,
        user_id: str,
        task_id: str,
        task_title: str
    ) -> bool:
        """Set active task for user"""
        success = await self.project_context.set_active_task(
            user_id, task_id, task_title
        )

        if success:
            log.log_state_transition(
                user_id=user_id,
                from_state="no_task",
                to_state="task_selected",
                trigger=f"set_task:{task_id}"
            )

        return success

    async def clear_active_task(self, user_id: str) -> bool:
        """Clear active task for user"""
        return await self.project_context.clear_active_task(user_id)

    # ===== UPDATE SESSION (Session Layer) =====

    async def get_active_session(self, user_id: str) -> Optional[UpdateSession]:
        """Get active update session for user"""
        result = await supabase_client.table("progress_update_sessions") \
            .select("*") \
            .eq("subcontractor_id", user_id) \
            .is_("completed_at", None) \
            .gt("expires_at", datetime.utcnow().isoformat()) \
            .single() \
            .execute()

        if result.data:
            return UpdateSession(**result.data)
        return None

    async def create_session(
        self,
        user_id: str,
        task_id: str,
        project_id: str,
        initial_state: SessionState = SessionState.AWAITING_ACTION
    ) -> UpdateSession:
        """
        Create new update session.

        Validations:
        - No active session exists
        - User has permission for task

        Side effects:
        - Sets active task context
        - Logs session creation
        """
        # Check for existing session
        existing = await self.get_active_session(user_id)
        if existing:
            raise ValueError(f"User {user_id} already has active session {existing.session_id}")

        # Create session
        now = datetime.utcnow()
        session_data = {
            "subcontractor_id": user_id,
            "task_id": task_id,
            "project_id": project_id,
            "current_step": initial_state.value,
            "images_uploaded": 0,
            "comments_added": 0,
            "status_changed": False,
            "created_at": now.isoformat(),
            "last_activity": now.isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        }

        result = await supabase_client.table("progress_update_sessions") \
            .insert(session_data) \
            .execute()

        session = UpdateSession(**result.data[0])

        # Set active task context
        await self.set_active_task(user_id, task_id, f"Task {task_id}")

        # Log session creation
        log.log_state_transition(
            user_id=user_id,
            from_state=SessionState.IDLE.value,
            to_state=initial_state.value,
            trigger="create_session",
            session_id=session.session_id
        )

        logger.info(f"✅ Session created: {session.session_id} for task {task_id}")

        return session

    async def update_session_state(
        self,
        session_id: str,
        new_state: SessionState,
        trigger: str
    ) -> bool:
        """
        Update session state with FSM validation.

        Validates transition is allowed before applying.
        Logs all state changes.
        """
        # TODO: Add FSM validation here (Phase 2)

        result = await supabase_client.table("progress_update_sessions") \
            .update({
                "current_step": new_state.value,
                "last_activity": datetime.utcnow().isoformat()
            }) \
            .eq("id", session_id) \
            .execute()

        if result.data:
            # Log transition
            # (from_state retrieved from session before update)
            logger.info(f"🔄 Session {session_id} transitioned to {new_state.value}")
            return True

        return False

    async def increment_action_count(
        self,
        session_id: str,
        action_type: str  # "image", "comment", "complete"
    ) -> bool:
        """Increment session action counter"""
        field_map = {
            "image": "images_uploaded",
            "comment": "comments_added",
            "complete": "status_changed"
        }

        field = field_map.get(action_type)
        if not field:
            logger.warning(f"Unknown action type: {action_type}")
            return False

        # Use atomic increment
        result = await supabase_client.rpc(
            "increment_session_counter",
            {"session_id": session_id, "field": field}
        )

        logger.info(f"📊 Session {session_id}: {action_type} count incremented")
        return result

    async def close_session(
        self,
        session_id: str,
        final_state: SessionState,
        reason: str
    ) -> bool:
        """
        Close session with final state (COMPLETED or ABANDONED).

        Side effects:
        - Saves draft if ABANDONED
        - Clears active task if COMPLETED
        - Logs closure
        """
        if final_state not in [SessionState.COMPLETED, SessionState.ABANDONED]:
            raise ValueError(f"Invalid final state: {final_state}")

        now = datetime.utcnow()
        result = await supabase_client.table("progress_update_sessions") \
            .update({
                "current_step": final_state.value,
                "completed_at": now.isoformat(),
                "closure_reason": reason
            }) \
            .eq("id", session_id) \
            .execute()

        if result.data:
            session = result.data[0]

            # Side effects
            if final_state == SessionState.ABANDONED:
                await self._save_draft(session)

            # Log closure
            log.log_state_transition(
                user_id=session["subcontractor_id"],
                from_state=session["current_step"],
                to_state=final_state.value,
                trigger=reason,
                session_id=session_id
            )

            logger.info(f"✅ Session {session_id} closed: {final_state.value}")
            return True

        return False

    async def _save_draft(self, session: Dict[str, Any]):
        """Save session as draft for potential resume"""
        # TODO: Implement draft saving (Phase 4)
        logger.info(f"💾 Draft saved for session {session['id']}")

    # ===== EXECUTION CONTEXT (Request-Scoped) =====

    def get_execution_context(self):
        """Get current request execution context"""
        return get_execution_context()

    # ===== COMBINED CONTEXT FOR FSM =====

    async def build_fsm_context(
        self,
        user_id: str,
        intent: str,
        message: str,
        confidence: float
    ) -> FSMContext:
        """
        Build complete FSM context for decision making.

        Combines:
        - Active project/task (DB)
        - Active session (DB)
        - Execution context (thread-local)
        """
        session = await self.get_active_session(user_id)
        active_task = await self.get_active_task(user_id)

        return FSMContext(
            user_id=user_id,
            current_state=SessionState(session.state) if session else SessionState.IDLE,
            session_id=session.session_id if session else None,
            task_id=session.task_id if session else None,
            project_id=session.project_id if session else None,
            intent=intent,
            message=message,
            confidence=confidence,
            active_task_id=active_task
        )

# Singleton instance
state_manager = StateManager()
```

**Testing:**
- [ ] All CRUD operations work
- [ ] Cascade updates work (project → task)
- [ ] Session creation validates constraints
- [ ] Atomic increment works
- [ ] Structured logs output correctly

---

#### 1.2 Create Backward Compatibility Layer (Day 2-3)
**File:** `src/fsm/compat.py`

```python
"""
Backward compatibility shims for existing code.

Allows old code to work unchanged while new code uses StateManager.
"""

from src.fsm.state_manager import state_manager

# Alias for old project_context usage
class ProjectContextServiceCompat:
    """Compatibility shim for project_context.py"""

    async def get_active_project(self, user_id: str):
        return await state_manager.get_active_project(user_id)

    async def set_active_project(self, user_id: str, project_id: str, project_name: str):
        return await state_manager.set_active_project(user_id, project_id, project_name)

    async def get_active_task(self, user_id: str):
        return await state_manager.get_active_task(user_id)

    async def set_active_task(self, user_id: str, task_id: str, task_title: str):
        return await state_manager.set_active_task(user_id, task_id, task_title)

# Export for drop-in replacement
project_context_service = ProjectContextServiceCompat()
```

**Migration Strategy:**
1. Keep old `project_context.py` unchanged
2. Add `from src.fsm.compat import project_context_service` to new code
3. Gradually migrate old imports to new `state_manager`
4. Remove old code in Phase 5

---

#### 1.3 Database Schema Updates (Day 3)
**File:** `migrations/008_add_session_closure_fields.sql`

```sql
-- Add closure tracking fields to progress_update_sessions
ALTER TABLE progress_update_sessions
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS closure_reason TEXT;

-- Add index for active session lookups
CREATE INDEX IF NOT EXISTS idx_active_sessions
ON progress_update_sessions(subcontractor_id, expires_at)
WHERE completed_at IS NULL;

-- Create function for atomic counter increment
CREATE OR REPLACE FUNCTION increment_session_counter(
    session_id UUID,
    field TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    IF field = 'images_uploaded' THEN
        UPDATE progress_update_sessions
        SET images_uploaded = images_uploaded + 1,
            last_activity = NOW()
        WHERE id = session_id;
    ELSIF field = 'comments_added' THEN
        UPDATE progress_update_sessions
        SET comments_added = comments_added + 1,
            last_activity = NOW()
        WHERE id = session_id;
    ELSIF field = 'status_changed' THEN
        UPDATE progress_update_sessions
        SET status_changed = TRUE,
            last_activity = NOW()
        WHERE id = session_id;
    ELSE
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Add unique constraint to prevent duplicate active sessions
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_session
ON progress_update_sessions(subcontractor_id)
WHERE completed_at IS NULL;
```

**Testing:**
- [ ] Migration runs without errors
- [ ] Indexes improve query performance
- [ ] Atomic increment function works
- [ ] Unique constraint prevents duplicates

---

#### 1.4 Integration Testing (Day 4)
**File:** `tests/test_state_manager.py`

```python
import pytest
from src.fsm.state_manager import state_manager, UpdateSession
from src.fsm.base import SessionState

@pytest.mark.asyncio
class TestStateManager:
    """Integration tests for unified state management"""

    async def test_session_lifecycle(self):
        """Test complete session lifecycle"""
        user_id = "test_user_123"

        # 1. Create session
        session = await state_manager.create_session(
            user_id=user_id,
            task_id="task_1",
            project_id="project_1"
        )
        assert session.state == SessionState.AWAITING_ACTION
        assert session.images_uploaded == 0

        # 2. Increment counters
        await state_manager.increment_action_count(session.session_id, "image")
        await state_manager.increment_action_count(session.session_id, "image")

        # 3. Get session (verify counters)
        updated = await state_manager.get_active_session(user_id)
        assert updated.images_uploaded == 2

        # 4. Close session
        closed = await state_manager.close_session(
            session.session_id,
            SessionState.COMPLETED,
            "user_confirmed"
        )
        assert closed

        # 5. Verify no active session
        final = await state_manager.get_active_session(user_id)
        assert final is None

    async def test_cascade_update(self):
        """Test project change clears task"""
        user_id = "test_user_456"

        # Set task
        await state_manager.set_active_task(user_id, "task_1", "Task 1")
        task = await state_manager.get_active_task(user_id)
        assert task == "task_1"

        # Change project (should clear task)
        await state_manager.set_active_project(user_id, "project_2", "Project 2")
        task_after = await state_manager.get_active_task(user_id)
        assert task_after is None

    async def test_duplicate_session_prevention(self):
        """Test cannot create duplicate active sessions"""
        user_id = "test_user_789"

        # Create first session
        session1 = await state_manager.create_session(
            user_id=user_id,
            task_id="task_1",
            project_id="project_1"
        )
        assert session1

        # Attempt duplicate (should fail)
        with pytest.raises(ValueError, match="already has active session"):
            await state_manager.create_session(
                user_id=user_id,
                task_id="task_2",
                project_id="project_1"
            )
```

**Testing:**
- [ ] All state manager tests pass
- [ ] Cascade updates work correctly
- [ ] Duplicate prevention works
- [ ] Atomic operations are thread-safe

---

### Phase 1 Deliverables
- ✅ Unified `StateManager` class
- ✅ Backward compatibility layer
- ✅ Database schema updated
- ✅ Integration tests passing

### Phase 1 Acceptance Criteria
- [ ] All existing code works unchanged
- [ ] New code can use `StateManager`
- [ ] No performance regression (<50ms overhead)
- [ ] Structured logs show state changes
- [ ] 90%+ test coverage on StateManager

---

## Phase 2: FSM Core Implementation (Week 3)

### Goals
- Implement FSM transition validation
- Add state machine logic to session updates
- Ensure all transitions are logged
- Validate transitions before executing

### Tasks

#### 2.1 FSM Engine (Day 1-2)
**File:** `src/fsm/engine.py`

```python
from typing import Optional, Callable, Dict, Any
from loguru import logger
from src.fsm.base import (
    SessionState,
    FSMContext,
    FSMTransitionRule,
    TRANSITION_RULES,
    FSMValidationError,
    FSMTransitionError
)
from src.utils.structured_logger import StructuredLogger

log = StructuredLogger(__name__)

# Type aliases for validators and side effects
Validator = Callable[[FSMContext], bool]
SideEffect = Callable[[FSMContext], None]

class FSMEngine:
    """
    Finite State Machine engine for task update flow.

    Responsibilities:
    - Validate state transitions
    - Execute validators before transition
    - Execute side effects after transition
    - Log all transitions and failures
    """

    def __init__(self):
        self.validators: Dict[str, Validator] = {}
        self.side_effects: Dict[str, SideEffect] = {}
        self._register_default_validators()
        self._register_default_side_effects()

    def _register_default_validators(self):
        """Register built-in validators"""
        self.register_validator("user_authenticated", self._validate_user_authenticated)
        self.register_validator("no_active_session", self._validate_no_active_session)
        self.register_validator("task_exists", self._validate_task_exists)
        self.register_validator("user_has_permission", self._validate_user_has_permission)
        self.register_validator("at_least_one_update", self._validate_at_least_one_update)
        self.register_validator("session_valid", self._validate_session_valid)

    def _register_default_side_effects(self):
        """Register built-in side effects"""
        self.register_side_effect("create_session", self._side_effect_create_session)
        self.register_side_effect("save_draft", self._side_effect_save_draft)
        self.register_side_effect("clear_session", self._side_effect_clear_session)
        self.register_side_effect("notify_user", self._side_effect_notify_user)
        self.register_side_effect("log_session_start", self._side_effect_log_session_start)

    def register_validator(self, name: str, func: Validator):
        """Register custom validator function"""
        self.validators[name] = func
        logger.debug(f"Registered validator: {name}")

    def register_side_effect(self, name: str, func: SideEffect):
        """Register custom side effect function"""
        self.side_effects[name] = func
        logger.debug(f"Registered side effect: {name}")

    def can_transition(
        self,
        from_state: SessionState,
        to_state: SessionState,
        trigger: str
    ) -> bool:
        """
        Check if transition is allowed by FSM rules.

        Returns True if:
        - Transition rule exists for from_state → to_state
        - Trigger is in allowed triggers for that rule
        """
        rules = TRANSITION_RULES.get(from_state, [])

        for rule in rules:
            if rule.to_state == to_state and trigger in rule.triggers:
                return True

        return False

    def get_transition_rule(
        self,
        from_state: SessionState,
        to_state: SessionState,
        trigger: str
    ) -> Optional[FSMTransitionRule]:
        """Get the transition rule for this transition"""
        rules = TRANSITION_RULES.get(from_state, [])

        for rule in rules:
            if rule.to_state == to_state and trigger in rule.triggers:
                return rule

        return None

    async def validate_transition(
        self,
        context: FSMContext,
        to_state: SessionState,
        trigger: str
    ) -> bool:
        """
        Validate if transition can proceed.

        Steps:
        1. Check FSM rules allow transition
        2. Run all validators for this transition
        3. Log validation result

        Raises FSMValidationError if validation fails.
        """
        from_state = context.current_state

        # Check FSM rules
        if not self.can_transition(from_state, to_state, trigger):
            log.log_state_transition(
                user_id=context.user_id,
                from_state=from_state.value,
                to_state=to_state.value,
                trigger=trigger,
                session_id=context.session_id
            )
            raise FSMTransitionError(
                f"Invalid transition: {from_state.value} → {to_state.value} "
                f"(trigger: {trigger})"
            )

        # Get rule and run validators
        rule = self.get_transition_rule(from_state, to_state, trigger)
        if rule:
            for validator_name in rule.validators:
                validator = self.validators.get(validator_name)
                if not validator:
                    logger.warning(f"Validator not found: {validator_name}")
                    continue

                try:
                    if not await validator(context):
                        raise FSMValidationError(
                            f"Validation failed: {validator_name}"
                        )
                except Exception as e:
                    logger.error(f"Validator {validator_name} raised error: {e}")
                    raise FSMValidationError(f"Validator error: {validator_name}")

        logger.info(f"✅ Transition validated: {from_state.value} → {to_state.value}")
        return True

    async def execute_transition(
        self,
        context: FSMContext,
        to_state: SessionState,
        trigger: str
    ) -> bool:
        """
        Execute state transition with validation and side effects.

        Steps:
        1. Validate transition (raises if invalid)
        2. Update state in database
        3. Execute side effects
        4. Log transition

        Returns True on success.
        """
        from_state = context.current_state

        # 1. Validate
        await self.validate_transition(context, to_state, trigger)

        # 2. Update state (via StateManager)
        from src.fsm.state_manager import state_manager
        if context.session_id:
            await state_manager.update_session_state(
                context.session_id,
                to_state,
                trigger
            )

        # 3. Execute side effects
        rule = self.get_transition_rule(from_state, to_state, trigger)
        if rule:
            for side_effect_name in rule.side_effects:
                side_effect = self.side_effects.get(side_effect_name)
                if not side_effect:
                    logger.warning(f"Side effect not found: {side_effect_name}")
                    continue

                try:
                    await side_effect(context)
                except Exception as e:
                    logger.error(f"Side effect {side_effect_name} failed: {e}")
                    # Continue with other side effects

        # 4. Log transition
        log.log_state_transition(
            user_id=context.user_id,
            from_state=from_state.value,
            to_state=to_state.value,
            trigger=trigger,
            session_id=context.session_id
        )

        logger.info(f"✅ Transition executed: {from_state.value} → {to_state.value}")
        return True

    # ===== BUILT-IN VALIDATORS =====

    async def _validate_user_authenticated(self, context: FSMContext) -> bool:
        """User must be authenticated"""
        return bool(context.user_id)

    async def _validate_no_active_session(self, context: FSMContext) -> bool:
        """User must not have active session"""
        from src.fsm.state_manager import state_manager
        session = await state_manager.get_active_session(context.user_id)
        return session is None

    async def _validate_task_exists(self, context: FSMContext) -> bool:
        """Task must exist"""
        # TODO: Check task exists in PlanRadar
        return context.task_id is not None

    async def _validate_user_has_permission(self, context: FSMContext) -> bool:
        """User must have permission for task"""
        # TODO: Check user permission
        return True

    async def _validate_at_least_one_update(self, context: FSMContext) -> bool:
        """Session must have at least one update action"""
        from src.fsm.state_manager import state_manager
        session = await state_manager.get_active_session(context.user_id)
        if not session:
            return False
        return session.images_uploaded > 0 or session.comments_added > 0

    async def _validate_session_valid(self, context: FSMContext) -> bool:
        """Session must exist and not be expired"""
        from src.fsm.state_manager import state_manager
        session = await state_manager.get_active_session(context.user_id)
        return session is not None

    # ===== BUILT-IN SIDE EFFECTS =====

    async def _side_effect_create_session(self, context: FSMContext):
        """Create session (called from state transition)"""
        # NOTE: Session creation handled separately
        logger.debug("Side effect: create_session")

    async def _side_effect_save_draft(self, context: FSMContext):
        """Save session as draft"""
        logger.info(f"💾 Saving draft for user {context.user_id}")
        # TODO: Implement draft saving

    async def _side_effect_clear_session(self, context: FSMContext):
        """Clear active session"""
        from src.fsm.state_manager import state_manager
        if context.session_id:
            await state_manager.close_session(
                context.session_id,
                SessionState.ABANDONED,
                "auto_clear"
            )

    async def _side_effect_notify_user(self, context: FSMContext):
        """Notify user of state change"""
        logger.debug(f"📬 Notify user {context.user_id}")
        # TODO: Send notification

    async def _side_effect_log_session_start(self, context: FSMContext):
        """Log session start event"""
        logger.info(f"🚀 Session started for user {context.user_id}")

# Singleton instance
fsm_engine = FSMEngine()
```

**Testing:**
- [ ] All validators registered
- [ ] All side effects registered
- [ ] Invalid transitions raise errors
- [ ] Valid transitions execute successfully
- [ ] Side effects run in order

---

#### 2.2 Integrate FSM into StateManager (Day 2-3)
**File:** `src/fsm/state_manager.py` (update)

```python
# Add FSM validation to state updates

from src.fsm.engine import fsm_engine

class StateManager:
    # ... existing code ...

    async def transition_session(
        self,
        user_id: str,
        to_state: SessionState,
        trigger: str,
        message: str = "",
        intent: str = ""
    ) -> bool:
        """
        Transition session state with FSM validation.

        This is the PRIMARY method for state changes.
        All state updates should go through this method.
        """
        # Build FSM context
        context = await self.build_fsm_context(
            user_id=user_id,
            intent=intent,
            message=message,
            confidence=1.0  # Assuming high confidence for direct transitions
        )

        # Execute FSM transition (validates + side effects)
        success = await fsm_engine.execute_transition(context, to_state, trigger)

        return success

    async def update_session_state(self, session_id, new_state, trigger):
        """
        DEPRECATED: Use transition_session() instead.

        Kept for backward compatibility during migration.
        """
        logger.warning("update_session_state() is deprecated, use transition_session()")
        # Direct update without FSM validation
        # ... existing code ...
```

---

#### 2.3 Update Progress Update Agent (Day 3-4)
**File:** `src/services/progress_update/agent.py` (update)

```python
# Replace direct session updates with FSM transitions

from src.fsm.state_manager import state_manager
from src.fsm.base import SessionState

async def start_progress_update_session_tool(
    subcontractor_id: str,
    task_id: str,
    project_id: str
) -> dict:
    """
    Start progress update session with FSM.

    Old way:
        create_session() → direct DB insert

    New way:
        transition_session(IDLE → TASK_SELECTION) → FSM validates → create_session()
    """
    try:
        # FSM transition: IDLE → TASK_SELECTION
        await state_manager.transition_session(
            user_id=subcontractor_id,
            to_state=SessionState.TASK_SELECTION,
            trigger="user_requests_update",
            intent="update_progress"
        )

        # Then transition: TASK_SELECTION → AWAITING_ACTION
        session = await state_manager.create_session(
            user_id=subcontractor_id,
            task_id=task_id,
            project_id=project_id,
            initial_state=SessionState.AWAITING_ACTION
        )

        return {
            "success": True,
            "session_id": session.session_id,
            "message": "Session started"
        }

    except FSMTransitionError as e:
        logger.error(f"FSM transition failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def add_progress_image_tool(subcontractor_id, image_url):
    """Add image with FSM state transition"""

    # Transition: AWAITING_ACTION → COLLECTING_DATA
    await state_manager.transition_session(
        user_id=subcontractor_id,
        to_state=SessionState.COLLECTING_DATA,
        trigger="photo_received"
    )

    # Upload image to PlanRadar
    # ...

    # Transition back: COLLECTING_DATA → AWAITING_ACTION
    await state_manager.transition_session(
        user_id=subcontractor_id,
        to_state=SessionState.AWAITING_ACTION,
        trigger="data_saved"
    )

    return {"success": True}

async def mark_task_complete_tool(subcontractor_id, task_id):
    """Mark task complete with FSM"""

    # Transition: AWAITING_ACTION → CONFIRMATION_PENDING
    await state_manager.transition_session(
        user_id=subcontractor_id,
        to_state=SessionState.CONFIRMATION_PENDING,
        trigger="completion_signal"
    )

    # ... wait for user confirmation ...

    # Transition: CONFIRMATION_PENDING → COMPLETED
    await state_manager.transition_session(
        user_id=subcontractor_id,
        to_state=SessionState.COMPLETED,
        trigger="user_confirms"
    )

    return {"success": True}
```

---

### Phase 2 Deliverables
- ✅ FSM engine implemented
- ✅ State transitions validated
- ✅ Progress update agent migrated
- ✅ All transitions logged

### Phase 2 Acceptance Criteria
- [ ] All FSM tests pass
- [ ] Invalid transitions blocked
- [ ] State logs show before/after
- [ ] Progress updates work via FSM
- [ ] No regression in existing functionality

---

## Phase 3: Intent Hierarchy & Routing (Week 4)

### Goals
- Implement intent priority system
- Add session-aware confidence adjustment
- Handle intent conflicts with clarification
- Route based on priority + session state

### Tasks

#### 3.1 Intent Hierarchy Definition (Day 1)
**File:** `src/fsm/intent_hierarchy.py`

```python
from enum import Enum
from typing import List, Dict
from pydantic import BaseModel

class IntentPriority(int, Enum):
    """Intent priority levels (lower number = higher priority)"""
    P0_SYSTEM = 0      # Errors, escalations (always override)
    P1_DESTRUCTIVE = 1 # Delete, cancel (require confirmation)
    P2_STATEFUL = 2    # Update, report incident (conflict resolution)
    P3_NAVIGATIONAL = 3 # List, view (auto-close sessions)
    P4_INFORMATIONAL = 4 # Details, status (never conflict)

class IntentConfig(BaseModel):
    """Configuration for an intent"""
    name: str
    priority: IntentPriority
    requires_confirmation: bool = False
    closes_session: bool = False
    allows_parallel_session: bool = False

# Intent registry
INTENT_REGISTRY: Dict[str, IntentConfig] = {
    # P0: System intents
    "escalate": IntentConfig(
        name="escalate",
        priority=IntentPriority.P0_SYSTEM,
        closes_session=True
    ),

    # P1: Destructive intents
    "delete_task": IntentConfig(
        name="delete_task",
        priority=IntentPriority.P1_DESTRUCTIVE,
        requires_confirmation=True,
        closes_session=True
    ),
    "cancel_task": IntentConfig(
        name="cancel_task",
        priority=IntentPriority.P1_DESTRUCTIVE,
        requires_confirmation=True,
        closes_session=True
    ),

    # P2: Stateful intents
    "update_progress": IntentConfig(
        name="update_progress",
        priority=IntentPriority.P2_STATEFUL,
        allows_parallel_session=False
    ),
    "report_incident": IntentConfig(
        name="report_incident",
        priority=IntentPriority.P2_STATEFUL,
        allows_parallel_session=False
    ),

    # P3: Navigational intents
    "list_projects": IntentConfig(
        name="list_projects",
        priority=IntentPriority.P3_NAVIGATIONAL,
        closes_session=True  # Save draft, close session
    ),
    "list_tasks": IntentConfig(
        name="list_tasks",
        priority=IntentPriority.P3_NAVIGATIONAL,
        closes_session=True
    ),
    "view_documents": IntentConfig(
        name="view_documents",
        priority=IntentPriority.P3_NAVIGATIONAL,
        closes_session=False  # Can view docs during update
    ),
    "greeting": IntentConfig(
        name="greeting",
        priority=IntentPriority.P3_NAVIGATIONAL,
        closes_session=True  # Reset context on greeting
    ),

    # P4: Informational intents
    "task_details": IntentConfig(
        name="task_details",
        priority=IntentPriority.P4_INFORMATIONAL,
        closes_session=False
    ),
    "project_status": IntentConfig(
        name="project_status",
        priority=IntentPriority.P4_INFORMATIONAL,
        closes_session=False
    ),
    "general": IntentConfig(
        name="general",
        priority=IntentPriority.P4_INFORMATIONAL,
        closes_session=False
    ),
}

def get_intent_config(intent: str) -> IntentConfig:
    """Get configuration for intent"""
    return INTENT_REGISTRY.get(
        intent,
        IntentConfig(name=intent, priority=IntentPriority.P4_INFORMATIONAL)
    )

def should_intent_override_session(
    new_intent: str,
    session_intent: str
) -> bool:
    """
    Determine if new intent should override active session.

    Rules:
    - P0 always overrides
    - P1 requires confirmation
    - P2 conflicts with P2 (ask clarification)
    - P3 auto-closes session
    - P4 never overrides
    """
    new_config = get_intent_config(new_intent)
    session_config = get_intent_config(session_intent)

    if new_config.priority < session_config.priority:
        # Higher priority → override
        return True
    elif new_config.priority == session_config.priority:
        # Same priority → conflict (ask clarification)
        return False
    else:
        # Lower priority → don't override
        return False
```

**Testing:**
- [ ] All intents have priority
- [ ] Priority comparison works
- [ ] Override logic correct

---

#### 3.2 Session-Aware Confidence Adjustment (Day 1-2)
**File:** `src/fsm/confidence_adjuster.py`

```python
from typing import Optional
from loguru import logger
from src.fsm.base import FSMContext
from src.fsm.intent_hierarchy import get_intent_config, should_intent_override_session

class ConfidenceAdjuster:
    """
    Adjusts intent confidence based on session context.

    Factors:
    1. Base intent confidence (from Haiku)
    2. Session context match (does intent align with session?)
    3. Conversation flow match (responding to bot prompt?)
    4. Ambiguity penalty (conflicting signals?)
    """

    def __init__(self):
        self.session_conflict_penalty = 0.30  # -30% if intent conflicts with session
        self.flow_alignment_boost = 0.10      # +10% if responding to prompt
        self.ambiguity_penalty = 0.10         # -10% if ambiguous

    def adjust_confidence(
        self,
        base_confidence: float,
        new_intent: str,
        context: FSMContext,
        last_bot_message: Optional[str] = None
    ) -> float:
        """
        Adjust confidence based on context.

        Returns adjusted confidence (0.0-1.0)
        """
        adjusted = base_confidence

        # Factor 1: Session context match
        if context.session_id:
            # User has active session
            session_intent = self._get_session_intent(context)

            if session_intent and new_intent != session_intent:
                # Intent conflicts with session
                penalty = self.session_conflict_penalty
                adjusted -= penalty
                logger.debug(
                    f"Session conflict: {new_intent} != {session_intent}, "
                    f"confidence {base_confidence:.2f} → {adjusted:.2f}"
                )

        # Factor 2: Conversation flow match
        if last_bot_message and self._is_response_to_prompt(last_bot_message):
            # User responding to bot question
            boost = self.flow_alignment_boost
            adjusted += boost
            logger.debug(
                f"Flow alignment boost: confidence {adjusted - boost:.2f} → {adjusted:.2f}"
            )

        # Factor 3: Ambiguity penalty
        if self._is_ambiguous(new_intent, context):
            penalty = self.ambiguity_penalty
            adjusted -= penalty
            logger.debug(
                f"Ambiguity penalty: confidence {adjusted + penalty:.2f} → {adjusted:.2f}"
            )

        # Clamp to [0.0, 1.0]
        adjusted = max(0.0, min(1.0, adjusted))

        logger.info(
            f"Confidence adjusted: {base_confidence:.2f} → {adjusted:.2f} "
            f"(intent: {new_intent})"
        )

        return adjusted

    def _get_session_intent(self, context: FSMContext) -> Optional[str]:
        """Get intent associated with active session"""
        # For update progress sessions, intent is "update_progress"
        if context.current_state in [
            SessionState.TASK_SELECTION,
            SessionState.AWAITING_ACTION,
            SessionState.COLLECTING_DATA,
            SessionState.CONFIRMATION_PENDING
        ]:
            return "update_progress"
        return None

    def _is_response_to_prompt(self, last_bot_message: str) -> bool:
        """Check if last bot message was a question/prompt"""
        question_markers = ["?", "What", "Which", "Would you like"]
        return any(marker in last_bot_message for marker in question_markers)

    def _is_ambiguous(self, intent: str, context: FSMContext) -> bool:
        """Check if message has ambiguous intent"""
        # Ambiguous if:
        # - Message contains incident keywords during update session
        # - Message is very short (<3 words)
        # - Message contains completion signal ("done") but unclear what's done

        ambiguous_keywords = ["problem", "issue", "broken", "done", "finished"]
        if context.session_id and any(kw in context.message.lower() for kw in ambiguous_keywords):
            return True

        if len(context.message.split()) < 3 and intent == "general":
            return True

        return False

# Singleton instance
confidence_adjuster = ConfidenceAdjuster()
```

**Testing:**
- [ ] Confidence adjusts for session conflict
- [ ] Confidence boosts for flow alignment
- [ ] Ambiguity detection works
- [ ] Clamping to [0,1] works

---

#### 3.3 Conflict Resolution Router (Day 2-3)
**File:** `src/fsm/conflict_resolver.py`

```python
from typing import Optional, Dict, Any
from loguru import logger
from src.fsm.base import FSMContext, SessionState
from src.fsm.intent_hierarchy import get_intent_config, IntentPriority
from src.utils.structured_logger import StructuredLogger

log = StructuredLogger(__name__)

class ConflictResolver:
    """
    Resolves intent conflicts with active sessions.

    Determines if:
    - New intent overrides session
    - Clarification needed
    - New intent executes inline (parallel)
    """

    async def resolve_conflict(
        self,
        new_intent: str,
        confidence: float,
        context: FSMContext
    ) -> Dict[str, Any]:
        """
        Resolve intent conflict.

        Returns:
        {
            "action": "override" | "clarify" | "inline" | "execute",
            "clarification": Optional[Dict] (question + options),
            "close_session": bool,
            "save_draft": bool
        }
        """
        # No session → no conflict
        if not context.session_id:
            return {
                "action": "execute",
                "close_session": False,
                "save_draft": False
            }

        # Get intent configs
        new_config = get_intent_config(new_intent)
        session_intent = self._get_session_intent(context)
        session_config = get_intent_config(session_intent) if session_intent else None

        # Log potential conflict
        log.log_intent_conflict(
            user_id=context.user_id,
            current_intent=session_intent or "none",
            new_intent=new_intent,
            session_state=context.current_state.value,
            resolution="analyzing"
        )

        # Priority-based resolution
        if new_config.priority == IntentPriority.P0_SYSTEM:
            # System intents always override
            return {
                "action": "override",
                "close_session": True,
                "save_draft": True,
                "reason": "system_priority"
            }

        elif new_config.priority == IntentPriority.P1_DESTRUCTIVE:
            # Destructive intents require confirmation
            return {
                "action": "clarify",
                "clarification": {
                    "question": f"You have an active update for Task {context.task_id}. "
                               f"Do you want to abandon it and {new_intent}?",
                    "options": [
                        {"label": f"{new_intent.replace('_', ' ').title()}", "value": "confirm"},
                        {"label": "Continue update", "value": "cancel"}
                    ]
                },
                "close_session": False,  # Wait for user response
                "save_draft": False
            }

        elif new_config.priority == IntentPriority.P2_STATEFUL:
            # Stateful intent conflicts with stateful session
            if session_config and session_config.priority == IntentPriority.P2_STATEFUL:
                # Same priority → ask clarification
                return {
                    "action": "clarify",
                    "clarification": self._build_stateful_clarification(
                        new_intent, session_intent, context
                    ),
                    "close_session": False,
                    "save_draft": False
                }
            else:
                # Different priority → execute new intent
                return {
                    "action": "override",
                    "close_session": True,
                    "save_draft": True,
                    "reason": "higher_priority"
                }

        elif new_config.priority == IntentPriority.P3_NAVIGATIONAL:
            # Navigational intents close session
            if new_config.closes_session:
                return {
                    "action": "override",
                    "close_session": True,
                    "save_draft": True,
                    "reason": "navigation"
                }
            else:
                # Execute inline (e.g., view documents during update)
                return {
                    "action": "inline",
                    "close_session": False,
                    "save_draft": False
                }

        elif new_config.priority == IntentPriority.P4_INFORMATIONAL:
            # Informational intents never conflict
            return {
                "action": "inline",
                "close_session": False,
                "save_draft": False
            }

        # Default: execute new intent
        return {
            "action": "execute",
            "close_session": False,
            "save_draft": False
        }

    def _get_session_intent(self, context: FSMContext) -> Optional[str]:
        """Get intent for active session"""
        if context.current_state in [
            SessionState.TASK_SELECTION,
            SessionState.AWAITING_ACTION,
            SessionState.COLLECTING_DATA,
            SessionState.CONFIRMATION_PENDING
        ]:
            return "update_progress"
        return None

    def _build_stateful_clarification(
        self,
        new_intent: str,
        session_intent: str,
        context: FSMContext
    ) -> Dict[str, Any]:
        """Build clarification question for stateful conflict"""

        if new_intent == "report_incident" and session_intent == "update_progress":
            # Special case: Problem keyword during update
            return {
                "question": "I heard you mention a problem. Are you:",
                "options": [
                    {
                        "label": f"Describing issue with Task {context.task_id}",
                        "value": "comment",
                        "description": "Add as comment to current update"
                    },
                    {
                        "label": "Reporting new separate incident",
                        "value": "new_incident",
                        "description": "Save current update and create incident"
                    }
                ]
            }

        else:
            # Generic conflict
            return {
                "question": f"You're currently {session_intent.replace('_', ' ')}. "
                           f"Do you want to switch to {new_intent.replace('_', ' ')}?",
                "options": [
                    {"label": f"Finish {session_intent}", "value": "continue"},
                    {"label": f"Switch to {new_intent}", "value": "switch"}
                ]
            }

# Singleton instance
conflict_resolver = ConflictResolver()
```

**Testing:**
- [ ] P0 intents override
- [ ] P1 intents ask confirmation
- [ ] P2 conflicts detected
- [ ] P3 intents close session
- [ ] P4 intents execute inline

---

#### 3.4 Integrate into Message Pipeline (Day 3-4)
**File:** `src/handlers/message_pipeline.py` (update)

```python
# Update routing stage to use intent hierarchy

from src.fsm.confidence_adjuster import confidence_adjuster
from src.fsm.conflict_resolver import conflict_resolver
from src.fsm.state_manager import state_manager

async def _route_message(self, ctx: MessageContext) -> Result[None]:
    """
    Route message with intent hierarchy and conflict resolution.

    Steps:
    1. Build FSM context
    2. Adjust confidence based on session
    3. Resolve conflicts if session active
    4. Route to handler based on resolution
    """

    # 1. Build FSM context
    fsm_context = await state_manager.build_fsm_context(
        user_id=ctx.user_id,
        intent=ctx.intent,
        message=ctx.message_in_french,
        confidence=ctx.confidence
    )

    # 2. Adjust confidence (session-aware)
    adjusted_confidence = confidence_adjuster.adjust_confidence(
        base_confidence=ctx.confidence,
        new_intent=ctx.intent,
        context=fsm_context,
        last_bot_message=ctx.last_bot_message
    )

    ctx.confidence = adjusted_confidence  # Update context

    # 3. Resolve conflicts
    resolution = await conflict_resolver.resolve_conflict(
        new_intent=ctx.intent,
        confidence=adjusted_confidence,
        context=fsm_context
    )

    # 4. Route based on resolution
    if resolution["action"] == "clarify":
        # Ask clarification question
        clarification = resolution["clarification"]
        ctx.response_text = self._format_clarification(clarification)
        ctx.response_type = "interactive_list"
        ctx.list_type = "clarification"
        # Store clarification context for next message
        return Result.ok(None)

    elif resolution["action"] == "override":
        # Override session: save draft, close session
        if resolution["save_draft"]:
            await state_manager.transition_session(
                user_id=ctx.user_id,
                to_state=SessionState.ABANDONED,
                trigger="intent_override",
                intent=ctx.intent
            )
        # Execute new intent
        return await self._execute_intent(ctx)

    elif resolution["action"] == "inline":
        # Execute inline (keep session active)
        result = await self._execute_intent(ctx)
        # Add reminder about active session
        if fsm_context.session_id:
            ctx.response_text += f"\n\nYou're still updating Task {fsm_context.task_id}."
        return result

    else:  # "execute"
        # Normal execution (no conflict)
        return await self._execute_intent(ctx)

def _format_clarification(self, clarification: Dict[str, Any]) -> str:
    """Format clarification question for user"""
    question = clarification["question"]
    options = clarification["options"]

    # Format with numbered options
    formatted = f"{question}\n\n"
    for i, option in enumerate(options, 1):
        label = option["label"]
        desc = option.get("description", "")
        formatted += f"{i}. {label}"
        if desc:
            formatted += f" - {desc}"
        formatted += "\n"

    return formatted.strip()
```

---

### Phase 3 Deliverables
- ✅ Intent hierarchy defined
- ✅ Confidence adjustment implemented
- ✅ Conflict resolver operational
- ✅ Message pipeline integrated

### Phase 3 Acceptance Criteria
- [ ] Intent priorities enforce correctly
- [ ] Confidence adjusts for session context
- [ ] Conflicts trigger clarifications
- [ ] Users receive clear options
- [ ] All edge cases handled

---

## Phase 4: Clarification & Error Handling (Week 5)

### Goals
- Implement clarification question system
- Add draft saving on abandonment
- Implement draft resume prompts
- Enhance error handling and logging

*(Detailed tasks for Phases 4-5 continue... due to length constraints, I'll provide the structure)*

### Tasks

#### 4.1 Clarification Question System
- Build clarification templates
- Store clarification context
- Handle user responses

#### 4.2 Draft Saving Mechanism
- Save session state as draft
- Query drafts on next update
- Resume from draft

#### 4.3 Enhanced Error Handling
- Decorator-based error handling
- Automatic escalation on critical errors
- User-friendly error messages

#### 4.4 Comprehensive Logging
- Log all clarifications
- Log draft saves/resumes
- Structured event logs

---

## Phase 5: Testing & Optimization (Week 6)

### Goals
- End-to-end scenario testing
- Performance optimization
- Documentation completion
- Gradual rollout with feature flags

### Tasks

#### 5.1 Scenario Testing (50+ test cases)
- All 12 scenarios from audit
- Edge cases and error conditions
- Concurrent user simulations

#### 5.2 Performance Optimization
- Database query optimization
- Caching strategy
- Latency benchmarks

#### 5.3 Documentation
- Developer guide
- Architecture diagrams
- Troubleshooting guide

#### 5.4 Gradual Rollout
- Enable FSM for 10% of users
- Monitor metrics
- Expand to 50%, then 100%

---

## Rollback Plan

### If Issues Occur

**Step 1: Immediate Actions (< 5 minutes)**
```bash
# Disable FSM via feature flag
export FEATURE_ENABLE_FSM=false
export FEATURE_FORCE_LEGACY_ROUTING=true

# Restart services
pm2 restart whatsapp-api
```

**Step 2: Database Rollback (< 10 minutes)**
```sql
-- Revert schema changes if needed
-- Migrations are reversible
```

**Step 3: Code Rollback (< 30 minutes)**
```bash
# Revert to last stable commit
git revert <fsm-commit-range>
git push origin main

# Deploy previous version
./deploy.sh rollback
```

**Rollback Triggers:**
- Error rate > 5%
- Session abandonment > 40%
- User complaints > 10/hour
- Data corruption detected

---

## Success Metrics

### Pre-Implementation Baseline
- Session abandonment rate: Unknown (estimate 30-40%)
- Fast path success rate: 45-50%
- Intent conflict rate: Unknown
- Average session duration: Unknown
- Orphaned sessions: Unknown

### Post-Implementation Targets

| Metric | Baseline | Target | Critical Threshold |
|--------|----------|--------|-------------------|
| Session abandonment rate | 35% | < 20% | < 25% |
| Fast path success rate | 47% | > 60% | > 55% |
| Intent conflict resolution | N/A | > 95% | > 90% |
| Session completion rate | Unknown | > 70% | > 60% |
| Orphaned sessions (2h+) | Unknown | 0 | < 5% |
| Average resolution time | N/A | < 3 minutes | < 5 min |
| Clarification answer rate | N/A | > 80% | > 70% |
| Draft resume rate | N/A | > 50% | > 30% |

### Monitoring Dashboard

**Key Metrics to Track:**
- Real-time session count
- State transition graph
- Intent conflict frequency
- Clarification effectiveness
- Draft save/resume rates
- Error rates by component
- User satisfaction (via feedback)

---

## Implementation Timeline Summary

| Phase | Duration | Key Deliverables | Risk Level |
|-------|----------|-----------------|------------|
| Phase 0: Foundation | Week 1 | Feature flags, logging, base classes | LOW |
| Phase 1: State Consolidation | Week 2 | Unified StateManager | MEDIUM |
| Phase 2: FSM Core | Week 3 | FSM engine, validation | MEDIUM |
| Phase 3: Intent Hierarchy | Week 4 | Conflict resolution, routing | HIGH |
| Phase 4: Clarification | Week 5 | Draft saving, error handling | MEDIUM |
| Phase 5: Testing & Rollout | Week 6 | Full testing, gradual release | LOW |

**Total Duration:** 6 weeks
**Recommended Team Size:** 2-3 developers
**QA Requirements:** 1 dedicated tester for Phase 5

---

## Best Practices Enforced

### Code Quality
- ✅ Max 50 lines per function
- ✅ Max 3 levels of nesting
- ✅ Docstrings on all public methods
- ✅ Type hints everywhere
- ✅ Pydantic models for data

### Architecture
- ✅ Single responsibility per class
- ✅ Explicit state over implicit
- ✅ Dependency injection
- ✅ No circular dependencies
- ✅ Clear module boundaries

### Testing
- ✅ Unit tests for all FSM logic
- ✅ Integration tests for state management
- ✅ End-to-end scenario tests
- ✅ Performance benchmarks
- ✅ 85%+ code coverage

### Logging
- ✅ Structured JSON logs
- ✅ Correlation IDs for tracing
- ✅ All state transitions logged
- ✅ All conflicts logged
- ✅ All errors logged with context

### Documentation
- ✅ Architecture decision records (ADRs)
- ✅ API documentation
- ✅ Developer onboarding guide
- ✅ Troubleshooting runbooks
- ✅ Inline code comments

---

## Conclusion

This implementation plan provides a **phased, low-risk approach** to refactoring the task update system with an explicit FSM. The plan prioritizes:

1. **Backward compatibility** - existing code works during transition
2. **Gradual rollout** - feature flags enable controlled deployment
3. **Comprehensive testing** - 50+ scenario tests before production
4. **Extensive logging** - all transitions and conflicts visible
5. **Clean architecture** - removing redundancy, maintaining simplicity

By following this plan, the system will transition from **AI-owned state transitions** (unpredictable) to **FSM-governed transitions with AI as advisor** (predictable), resulting in:

- 🎯 Predictable bugs
- 📊 Meaningful logs
- 🎨 Consistent UX
- 🛡️ Contained AI mistakes

**Next Step:** Review and approve this plan, then begin Phase 0 implementation.

---

**Document Version:** 1.0
**Date:** 2026-01-16
**Status:** Ready for Implementation
**Approval Required:** Tech Lead, Product Owner
