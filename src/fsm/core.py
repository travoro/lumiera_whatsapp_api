"""FSM core engine with state management and transition validation.

This module combines StateManager (database operations) and FSMEngine
(business logic) into a cohesive system for managing user session states.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.fsm.models import FSMContext, SessionState, TransitionResult, TransitionRule
from src.integrations.supabase import supabase_client
from src.utils.structured_logger import get_structured_logger, set_correlation_id

logger = get_structured_logger("fsm.core")


# ============================================================================
# Transition Rules Definition
# ============================================================================

TRANSITION_RULES: List[TransitionRule] = [
    # From IDLE
    TransitionRule(
        from_state=SessionState.IDLE,
        to_state=SessionState.TASK_SELECTION,
        trigger="start_update",
        description="User initiates progress update",
    ),
    TransitionRule(
        from_state=SessionState.IDLE,
        to_state=SessionState.ABANDONED,
        trigger="explicit_cancel",
        description="User explicitly cancels",
    ),
    # From TASK_SELECTION
    TransitionRule(
        from_state=SessionState.TASK_SELECTION,
        to_state=SessionState.AWAITING_ACTION,
        trigger="task_selected",
        description="User selects a task to update",
    ),
    TransitionRule(
        from_state=SessionState.TASK_SELECTION,
        to_state=SessionState.ABANDONED,
        trigger="cancel",
        description="User cancels task selection",
    ),
    # From AWAITING_ACTION
    TransitionRule(
        from_state=SessionState.AWAITING_ACTION,
        to_state=SessionState.COLLECTING_DATA,
        trigger="start_collection",
        description="User starts providing photos/comments",
    ),
    TransitionRule(
        from_state=SessionState.AWAITING_ACTION,
        to_state=SessionState.CONFIRMATION_PENDING,
        trigger="request_confirmation",
        description="User requests to finalize update",
    ),
    TransitionRule(
        from_state=SessionState.AWAITING_ACTION,
        to_state=SessionState.ABANDONED,
        trigger="timeout",
        description="Session timeout due to inactivity",
    ),
    # From COLLECTING_DATA
    TransitionRule(
        from_state=SessionState.COLLECTING_DATA,
        to_state=SessionState.COLLECTING_DATA,
        trigger="add_data",
        description="User adds more photos/comments (self-loop)",
    ),
    TransitionRule(
        from_state=SessionState.COLLECTING_DATA,
        to_state=SessionState.CONFIRMATION_PENDING,
        trigger="request_confirmation",
        description="User requests to complete update",
    ),
    TransitionRule(
        from_state=SessionState.COLLECTING_DATA,
        to_state=SessionState.ABANDONED,
        trigger="cancel",
        description="User cancels data collection",
    ),
    # From CONFIRMATION_PENDING
    TransitionRule(
        from_state=SessionState.CONFIRMATION_PENDING,
        to_state=SessionState.COMPLETED,
        trigger="confirm",
        description="User confirms completion",
    ),
    TransitionRule(
        from_state=SessionState.CONFIRMATION_PENDING,
        to_state=SessionState.COLLECTING_DATA,
        trigger="continue_editing",
        description="User wants to add more data",
    ),
    TransitionRule(
        from_state=SessionState.CONFIRMATION_PENDING,
        to_state=SessionState.ABANDONED,
        trigger="cancel",
        description="User cancels before completion",
    ),
    # Global transitions (from any state)
    TransitionRule(
        from_state=None,  # From any state
        to_state=SessionState.ABANDONED,
        trigger="force_abandon",
        description="Force abandon (system/admin action)",
    ),
    TransitionRule(
        from_state=None,  # From any state
        to_state=SessionState.IDLE,
        trigger="reset",
        description="Reset to idle state",
    ),
]


# ============================================================================
# StateManager - Database Operations
# ============================================================================


class StateManager:
    """Manages FSM state persistence in database with transaction support."""

    def __init__(self):
        """Initialize state manager."""
        self.db = supabase_client

    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active session for user.

        Args:
            user_id: User's WhatsApp ID

        Returns:
            Session dict if found, None otherwise
        """
        try:
            response = (
                self.db.client.table("progress_update_sessions")
                .select("*")
                .eq("subcontractor_id", user_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting session: {str(e)}", user_id=user_id)
            return None

    async def create_session(
        self,
        user_id: str,
        task_id: str,
        project_id: str,
        initial_state: SessionState = SessionState.IDLE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create new session for user.

        Args:
            user_id: User's WhatsApp ID
            task_id: Task ID
            project_id: Project ID
            initial_state: Initial FSM state
            metadata: Optional session metadata

        Returns:
            Session ID if created, None otherwise
        """
        try:
            session_data = {
                "subcontractor_id": user_id,
                "task_id": task_id,
                "project_id": project_id,
                "fsm_state": initial_state.value,
                "session_metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
            }

            response = (
                self.db.client.table("progress_update_sessions")
                .insert(session_data)
                .execute()
            )

            if response.data and len(response.data) > 0:
                session_id = response.data[0]["id"]
                logger.info(
                    f"Session created: {session_id}",
                    user_id=user_id,
                    task_id=task_id,
                    initial_state=initial_state.value,
                )
                return session_id
            return None
        except Exception as e:
            logger.error(f"Error creating session: {str(e)}", user_id=user_id)
            return None

    async def update_session_state(
        self,
        session_id: str,
        new_state: SessionState,
        metadata_update: Optional[Dict[str, Any]] = None,
        closure_reason: Optional[str] = None,
    ) -> bool:
        """Update session state in database.

        Args:
            session_id: Session ID
            new_state: New FSM state
            metadata_update: Optional metadata to merge
            closure_reason: Optional closure reason

        Returns:
            True if successful, False otherwise
        """
        try:
            update_data: Dict[str, Any] = {
                "fsm_state": new_state.value,
                "last_activity": datetime.utcnow().isoformat(),
            }

            if metadata_update:
                # Note: This will replace the entire metadata object
                # For partial updates, need to fetch-modify-update
                update_data["session_metadata"] = metadata_update

            if closure_reason:
                update_data["closure_reason"] = closure_reason

            self.db.client.table("progress_update_sessions").update(update_data).eq(
                "id", session_id
            ).execute()

            logger.info(
                f"Session state updated: {new_state.value}", session_id=session_id
            )
            return True
        except Exception as e:
            logger.error(
                f"Error updating session state: {str(e)}", session_id=session_id
            )
            return False

    async def log_transition(
        self,
        user_id: str,
        session_id: str,
        from_state: SessionState,
        to_state: SessionState,
        trigger: str,
        success: bool,
        error: Optional[str] = None,
        context: Optional[FSMContext] = None,
        side_effects: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log state transition to audit table.

        Args:
            user_id: User's WhatsApp ID
            session_id: Session ID
            from_state: Source state
            to_state: Target state
            trigger: What triggered the transition
            success: Whether transition succeeded
            error: Error message if failed
            context: FSM context snapshot
            side_effects: List of side effects executed
            correlation_id: Correlation ID for tracing
        """
        try:
            log_data = {
                "user_id": user_id,
                "session_id": session_id,
                "from_state": from_state.value,
                "to_state": to_state.value,
                "trigger": trigger,
                "success": success,
                "error": error,
                "context": context.dict() if context else None,
                "side_effects": side_effects or [],
                "correlation_id": correlation_id,
                "created_at": datetime.utcnow().isoformat(),
            }

            self.db.client.table("fsm_transition_log").insert(log_data).execute()
        except Exception as e:
            # Don't fail the transition if logging fails
            logger.warning(f"Error logging transition: {str(e)}")

    async def check_idempotency(
        self, user_id: str, message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check if message was already processed (idempotency).

        Args:
            user_id: User's WhatsApp ID
            message_id: WhatsApp message ID

        Returns:
            Cached result if already processed, None otherwise
        """
        try:
            idempotency_key = f"{user_id}:{message_id}"
            response = (
                self.db.client.table("fsm_idempotency_records")
                .select("*")
                .eq("idempotency_key", idempotency_key)
                .execute()
            )

            if response.data and len(response.data) > 0:
                logger.info(
                    "Idempotency hit - message already processed",
                    idempotency_key=idempotency_key,
                )
                return response.data[0].get("result")
            return None
        except Exception as e:
            logger.error(f"Error checking idempotency: {str(e)}")
            return None

    async def record_idempotency(
        self, user_id: str, message_id: str, result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Record message as processed for idempotency.

        Args:
            user_id: User's WhatsApp ID
            message_id: WhatsApp message ID
            result: Optional result to cache

        Returns:
            True if recorded, False otherwise
        """
        try:
            idempotency_key = f"{user_id}:{message_id}"
            record_data = {
                "idempotency_key": idempotency_key,
                "user_id": user_id,
                "message_id": message_id,
                "result": result,
                "processed_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
            }

            self.db.client.table("fsm_idempotency_records").insert(
                record_data
            ).execute()

            logger.debug("Idempotency recorded", idempotency_key=idempotency_key)
            return True
        except Exception as e:
            logger.warning(f"Error recording idempotency: {str(e)}")
            return False


# ============================================================================
# FSMEngine - Business Logic & Transition Validation
# ============================================================================


class FSMEngine:
    """FSM engine for validating and executing state transitions."""

    def __init__(self, state_manager: StateManager):
        """Initialize FSM engine with dependency injection.

        Args:
            state_manager: StateManager instance for database operations
        """
        self.state_manager = state_manager
        self.transition_rules = TRANSITION_RULES

    def validate_transition(
        self, from_state: SessionState, to_state: SessionState, trigger: str
    ) -> tuple[bool, Optional[str]]:
        """Validate if a state transition is allowed.

        Args:
            from_state: Source state (enum or string)
            to_state: Target state (enum or string)
            trigger: What triggers the transition

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Normalize states to enums for comparison
        if isinstance(from_state, str):
            from_state = SessionState(from_state)
        if isinstance(to_state, str):
            to_state = SessionState(to_state)

        # Check if transition rule exists
        for rule in self.transition_rules:
            # Match exact from_state or global rule (from_state=None)
            if (
                (rule.from_state == from_state or rule.from_state is None)
                and rule.to_state == to_state
                and rule.trigger == trigger
            ):
                return True, None

        error = f"Invalid transition: {from_state.value} -> {to_state.value} (trigger: {trigger})"
        logger.warning(
            "Transition validation failed",
            from_state=from_state.value,
            to_state=to_state.value,
            trigger=trigger,
        )
        return False, error

    async def transition(
        self,
        context: FSMContext,
        to_state: SessionState,
        trigger: str,
        side_effect_fn: Optional[Callable] = None,
        closure_reason: Optional[str] = None,
    ) -> TransitionResult:
        """Execute a state transition with validation and side effects.

        This method:
        1. Validates the transition is allowed
        2. Updates state in database (atomic)
        3. Executes side effects if provided
        4. Logs the transition
        5. Returns result

        Args:
            context: Current FSM context
            to_state: Target state
            trigger: What triggers this transition
            side_effect_fn: Optional async function to execute (e.g., send notification)
            closure_reason: Optional closure reason for terminal states

        Returns:
            TransitionResult with success status and updated context
        """
        from_state = context.current_state

        # Set correlation ID for tracing (wrapped in try/except for test compatibility)
        correlation_id = None
        try:
            correlation_id = set_correlation_id()
        except Exception:
            # In tests, correlation ID may not work properly - that's okay
            import uuid

            correlation_id = str(uuid.uuid4())

        # Normalize states for processing (validate_transition will also normalize)
        if isinstance(from_state, str):
            from_state = SessionState(from_state)
        if isinstance(to_state, str):
            to_state = SessionState(to_state)

        logger.log_transition(
            user_id=context.user_id,
            from_state=from_state.value,
            to_state=to_state.value,
            trigger=trigger,
            success=True,  # Will update if fails
        )

        # Validate transition
        is_valid, error = self.validate_transition(from_state, to_state, trigger)
        if not is_valid:
            return TransitionResult(
                success=False,
                from_state=from_state,
                to_state=from_state,  # Stay in current state
                trigger=trigger,
                error=error,
                context=context,
            )

        # Update state in database (atomic operation)
        if context.session_id:
            success = await self.state_manager.update_session_state(
                session_id=context.session_id,
                new_state=to_state,
                metadata_update=context.metadata,
                closure_reason=closure_reason,
            )

            if not success:
                return TransitionResult(
                    success=False,
                    from_state=from_state,
                    to_state=from_state,
                    trigger=trigger,
                    error="Failed to update session state in database",
                    context=context,
                )

        # Execute side effects
        side_effects_executed = []
        if side_effect_fn:
            try:
                await side_effect_fn(context)
                side_effects_executed.append(side_effect_fn.__name__)
            except Exception as e:
                logger.error(f"Side effect failed: {str(e)}", trigger=trigger)
                # Don't fail transition if side effect fails
                side_effects_executed.append(f"{side_effect_fn.__name__} (failed)")

        # Update context
        context.current_state = to_state
        context.last_activity = datetime.utcnow()

        # Log transition to audit table
        if context.session_id:
            await self.state_manager.log_transition(
                user_id=context.user_id,
                session_id=context.session_id,
                from_state=from_state,
                to_state=to_state,
                trigger=trigger,
                success=True,
                context=context,
                side_effects=side_effects_executed,
                correlation_id=correlation_id,
            )

        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            context=context,
            side_effects=side_effects_executed,
        )

    @asynccontextmanager
    async def atomic_transition(self, context: FSMContext):
        """Context manager for atomic transitions with rollback.

        Usage:
            async with fsm_engine.atomic_transition(context) as transition:
                await transition(to_state, trigger)

        Note: This is a simplified version. Full transactional support would
        require Supabase connection pooling and transaction management.
        """
        # For v1, we rely on Supabase's built-in transaction support
        # Future enhancement: Implement explicit BEGIN/COMMIT/ROLLBACK
        try:
            yield self.transition
        except Exception as e:
            logger.error(f"Atomic transition failed: {str(e)}")
            raise
