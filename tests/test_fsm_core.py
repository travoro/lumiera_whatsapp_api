"""Unit tests for FSM core functionality.

Tests:
- Transition validation
- State transitions
- Idempotency
- Session management
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.fsm.core import TRANSITION_RULES, FSMEngine, StateManager
from src.fsm.models import FSMContext, SessionState


class TestTransitionValidation:
    """Test FSM transition rule validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.fsm_engine = FSMEngine(self.state_manager)

    def test_valid_transition_idle_to_task_selection(self):
        """Test valid transition from IDLE to TASK_SELECTION."""
        is_valid, error = self.fsm_engine.validate_transition(
            from_state=SessionState.IDLE,
            to_state=SessionState.TASK_SELECTION,
            trigger="start_update",
        )
        assert is_valid is True
        assert error is None

    def test_valid_transition_awaiting_to_collecting(self):
        """Test valid transition from AWAITING_ACTION to COLLECTING_DATA."""
        is_valid, error = self.fsm_engine.validate_transition(
            from_state=SessionState.AWAITING_ACTION,
            to_state=SessionState.COLLECTING_DATA,
            trigger="start_collection",
        )
        assert is_valid is True
        assert error is None

    def test_valid_self_loop_collecting_data(self):
        """Test valid self-loop in COLLECTING_DATA."""
        is_valid, error = self.fsm_engine.validate_transition(
            from_state=SessionState.COLLECTING_DATA,
            to_state=SessionState.COLLECTING_DATA,
            trigger="add_data",
        )
        assert is_valid is True
        assert error is None

    def test_invalid_transition_idle_to_completed(self):
        """Test invalid transition from IDLE to COMPLETED."""
        is_valid, error = self.fsm_engine.validate_transition(
            from_state=SessionState.IDLE,
            to_state=SessionState.COMPLETED,
            trigger="complete",
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid transition" in error

    def test_invalid_transition_wrong_trigger(self):
        """Test invalid transition with wrong trigger."""
        is_valid, error = self.fsm_engine.validate_transition(
            from_state=SessionState.IDLE,
            to_state=SessionState.TASK_SELECTION,
            trigger="wrong_trigger",
        )
        assert is_valid is False
        assert error is not None

    def test_global_transition_force_abandon(self):
        """Test global transition (from any state) to ABANDONED."""
        # Test from multiple states
        for from_state in [
            SessionState.IDLE,
            SessionState.TASK_SELECTION,
            SessionState.COLLECTING_DATA,
        ]:
            is_valid, error = self.fsm_engine.validate_transition(
                from_state=from_state,
                to_state=SessionState.ABANDONED,
                trigger="force_abandon",
            )
            assert is_valid is True, f"Should allow abandon from {from_state}"
            assert error is None


class TestStateTransitions:
    """Test FSM state transition execution."""

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock state manager."""
        manager = Mock(spec=StateManager)
        manager.update_session_state = AsyncMock(return_value=True)
        manager.log_transition = AsyncMock()
        return manager

    @pytest.fixture
    def fsm_engine(self, mock_state_manager):
        """Create FSM engine with mock state manager."""
        return FSMEngine(mock_state_manager)

    @pytest.fixture
    def sample_context(self):
        """Create sample FSM context."""
        return FSMContext(
            user_id="test_user_123",
            current_state=SessionState.IDLE,
            session_id="session_456",
            task_id="task_789",
            collected_data={},
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_successful_transition(
        self, fsm_engine, sample_context, mock_state_manager
    ):
        """Test successful state transition."""
        result = await fsm_engine.transition(
            context=sample_context,
            to_state=SessionState.TASK_SELECTION,
            trigger="start_update",
        )

        assert result.success is True
        assert result.from_state == SessionState.IDLE
        assert result.to_state == SessionState.TASK_SELECTION
        assert result.trigger == "start_update"
        assert result.context.current_state == SessionState.TASK_SELECTION

        # Verify state manager was called
        mock_state_manager.update_session_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_transition_invalid(self, fsm_engine, sample_context):
        """Test failed transition due to invalid rule."""
        result = await fsm_engine.transition(
            context=sample_context, to_state=SessionState.COMPLETED, trigger="complete"
        )

        assert result.success is False
        assert result.from_state == SessionState.IDLE
        assert result.to_state == SessionState.IDLE  # Stays in current state
        assert result.error is not None
        assert "Invalid transition" in result.error

    @pytest.mark.asyncio
    async def test_transition_with_side_effects(
        self, fsm_engine, sample_context, mock_state_manager
    ):
        """Test transition with side effects execution."""
        side_effect_executed = False

        async def mock_side_effect(context):
            nonlocal side_effect_executed
            side_effect_executed = True

        result = await fsm_engine.transition(
            context=sample_context,
            to_state=SessionState.TASK_SELECTION,
            trigger="start_update",
            side_effect_fn=mock_side_effect,
        )

        assert result.success is True
        assert side_effect_executed is True
        assert "mock_side_effect" in result.side_effects

    @pytest.mark.asyncio
    async def test_transition_with_failing_side_effect(
        self, fsm_engine, sample_context, mock_state_manager
    ):
        """Test that transition succeeds even if side effect fails."""

        async def failing_side_effect(context):
            raise Exception("Side effect failed")

        result = await fsm_engine.transition(
            context=sample_context,
            to_state=SessionState.TASK_SELECTION,
            trigger="start_update",
            side_effect_fn=failing_side_effect,
        )

        # Transition should still succeed
        assert result.success is True
        assert result.to_state == SessionState.TASK_SELECTION
        # Side effect should be marked as failed
        assert any("failed" in se for se in result.side_effects)

    @pytest.mark.asyncio
    async def test_transition_with_closure_reason(
        self, fsm_engine, sample_context, mock_state_manager
    ):
        """Test transition to terminal state with closure reason."""
        sample_context.current_state = SessionState.AWAITING_ACTION

        result = await fsm_engine.transition(
            context=sample_context,
            to_state=SessionState.ABANDONED,
            trigger="timeout",
            closure_reason="session_timeout",
        )

        assert result.success is True

        # Verify closure reason was passed to state manager
        mock_state_manager.update_session_state.assert_called_once()
        call_args = mock_state_manager.update_session_state.call_args
        assert call_args.kwargs["closure_reason"] == "session_timeout"


class TestIdempotency:
    """Test idempotency functionality."""

    @pytest.fixture
    def state_manager(self):
        """Create state manager with mocked DB client."""
        with patch("src.fsm.core.supabase_client") as mock_db:
            manager = StateManager()
            manager.db = mock_db
            return manager

    @pytest.mark.asyncio
    async def test_idempotency_miss(self, state_manager):
        """Test idempotency check when message not processed."""
        state_manager.db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
            []
        )

        result = await state_manager.check_idempotency(
            user_id="user_123", message_id="msg_456"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_idempotency_hit(self, state_manager):
        """Test idempotency check when message already processed."""
        cached_result = {"status": "processed"}
        state_manager.db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"result": cached_result}
        ]

        result = await state_manager.check_idempotency(
            user_id="user_123", message_id="msg_456"
        )

        assert result == cached_result

    @pytest.mark.asyncio
    async def test_record_idempotency(self, state_manager):
        """Test recording message for idempotency."""
        state_manager.db.client.table.return_value.insert.return_value.execute.return_value = (
            Mock()
        )

        success = await state_manager.record_idempotency(
            user_id="user_123", message_id="msg_456", result={"status": "processed"}
        )

        assert success is True
        state_manager.db.client.table.assert_called_with("fsm_idempotency_records")


class TestSessionManagement:
    """Test session management functionality."""

    @pytest.fixture
    def state_manager(self):
        """Create state manager with mocked DB client."""
        with patch("src.fsm.core.supabase_client") as mock_db:
            manager = StateManager()
            manager.db = mock_db
            return manager

    @pytest.mark.asyncio
    async def test_get_session_exists(self, state_manager):
        """Test getting existing session."""
        mock_session = {
            "id": "session_123",
            "subcontractor_id": "user_456",
            "fsm_state": "idle",
        }
        state_manager.db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            mock_session
        ]

        session = await state_manager.get_session("user_456")

        assert session == mock_session

    @pytest.mark.asyncio
    async def test_get_session_not_exists(self, state_manager):
        """Test getting non-existent session."""
        state_manager.db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
            []
        )

        session = await state_manager.get_session("user_456")

        assert session is None

    @pytest.mark.asyncio
    async def test_create_session(self, state_manager):
        """Test creating new session."""
        mock_created_session = {
            "id": "session_123",
            "subcontractor_id": "user_456",
            "task_id": "task_789",
            "fsm_state": "idle",
        }
        state_manager.db.client.table.return_value.insert.return_value.execute.return_value.data = [
            mock_created_session
        ]

        session_id = await state_manager.create_session(
            user_id="user_456", task_id="task_789", project_id="project_012"
        )

        assert session_id == "session_123"

    @pytest.mark.asyncio
    async def test_update_session_state(self, state_manager):
        """Test updating session state."""
        state_manager.db.client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            Mock()
        )

        success = await state_manager.update_session_state(
            session_id="session_123",
            new_state=SessionState.COLLECTING_DATA,
            metadata_update={"photos": 2},
        )

        assert success is True


class TestTransitionRules:
    """Test transition rules are properly defined."""

    def test_all_states_have_rules(self):
        """Ensure all states have at least one transition rule."""
        states_with_rules = set()

        for rule in TRANSITION_RULES:
            if rule.from_state:
                states_with_rules.add(rule.from_state)
            states_with_rules.add(rule.to_state)

        # Check that most states are covered (some might be terminal)
        assert len(states_with_rules) >= 5

    def test_terminal_states_defined(self):
        """Ensure terminal states (COMPLETED, ABANDONED) are reachable."""
        terminal_states = {SessionState.COMPLETED, SessionState.ABANDONED}
        reachable_terminal = set()

        for rule in TRANSITION_RULES:
            if rule.to_state in terminal_states:
                reachable_terminal.add(rule.to_state)

        assert reachable_terminal == terminal_states

    def test_no_duplicate_rules(self):
        """Ensure no duplicate transition rules."""
        rule_signatures = []

        for rule in TRANSITION_RULES:
            signature = (rule.from_state, rule.to_state, rule.trigger)
            assert signature not in rule_signatures, f"Duplicate rule: {signature}"
            rule_signatures.append(signature)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
