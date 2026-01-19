"""Shared pytest fixtures and configuration for all test suites.

This module provides common fixtures that can be used across all test files:
- Mock services (Twilio, Supabase, Anthropic, PlanRadar)
- Test data (users, tasks, messages)
- Helper utilities
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (slow)"
    )
    config.addinivalue_line("markers", "unit: mark test as unit test (fast)")
    config.addinivalue_line("markers", "fsm: mark test as FSM-related test")
    config.addinivalue_line("markers", "pipeline: mark test as pipeline test")
    config.addinivalue_line("markers", "pattern: mark test as user pattern test")
    config.addinivalue_line(
        "markers",
        "requires_db: mark test as requiring real database (skip in CI with dummy credentials)",
    )


def pytest_collection_modifyitems(config, items):
    """Automatically skip integration tests that require real database."""
    import os

    # Check if we're using dummy test credentials (CI environment)
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    is_test_env = "test" in supabase_key.lower()

    skip_db = pytest.mark.skip(
        reason="Requires real database connection (not available in CI with dummy credentials)"
    )

    for item in items:
        # Skip session race condition tests - they need real Supabase/database
        if "test_session_race_conditions" in str(item.fspath):
            # These specific tests call real session_service and need database
            test_name = item.name
            needs_db_tests = [
                "test_no_duplicate_sessions_on_concurrent_creates",
                "test_session_reuse_ratio_healthy",
                "test_context_preserved_across_actions",
                "test_progress_update_session_reset_on_new_task",
                "test_no_orphaned_sessions_after_error",
            ]

            if test_name in needs_db_tests and is_test_env:
                item.add_marker(skip_db)


# ============================================================================
# Mock Service Fixtures
# ============================================================================


@pytest.fixture
def mock_twilio_client():
    """Mock Twilio client for all tests."""
    with patch("src.handlers.message.twilio_client") as mock:
        mock.send_message = AsyncMock(return_value="SM_mock_123")
        mock.send_interactive_list = AsyncMock(return_value="SM_mock_123")
        mock.download_and_upload_media = Mock(return_value="/tmp/mock_file.jpg")
        mock.send_message_with_local_media = Mock(return_value="SM_mock_123")
        mock.validate_webhook = Mock(return_value=True)
        yield mock


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for all tests."""
    with patch("src.integrations.supabase.supabase_client") as mock:
        # Default mock user data
        mock_user_data = {
            "id": "user_test_123",
            "whatsapp_number": "+1234567890",
            "name": "Test User",
            "language": "fr",
            "active_project_id": "project_123",
            "active_task_id": "task_456",
        }

        # Mock user methods
        mock.get_user_by_phone = Mock(return_value=mock_user_data)
        mock.get_user_name = Mock(return_value="Test User")
        mock.get_recent_messages = AsyncMock(return_value=[])
        mock.save_message = AsyncMock(return_value=True)
        mock.list_projects = AsyncMock(return_value=[])

        # Mock the client.table() chain for queries
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_execute = Mock()

        mock_execute.data = [mock_user_data]
        mock_eq.execute = Mock(return_value=mock_execute)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_table.select = Mock(return_value=mock_select)
        mock.client.table = Mock(return_value=mock_table)

        yield mock


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic/Claude API client."""
    with patch("langchain_anthropic.ChatAnthropic") as mock:
        mock_response = Mock()
        mock_response.content = "Je peux vous aider avec ça!"
        mock.return_value.ainvoke = AsyncMock(return_value=mock_response)
        yield mock


@pytest.fixture
def mock_planradar_client():
    """Mock PlanRadar API client."""
    with patch("src.integrations.planradar.PlanRadarClient") as mock:
        # Mock task list
        mock.return_value.get_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task_1",
                    "title": "Install electrical wiring",
                    "status": "open",
                },
                {"id": "task_2", "title": "Fix water leak", "status": "open"},
                {"id": "task_3", "title": "Paint walls", "status": "in_progress"},
            ]
        )
        # Mock task update
        mock.return_value.update_task = AsyncMock(return_value=True)
        # Mock photo upload
        mock.return_value.upload_photo = AsyncMock(
            return_value={"photo_id": "photo_123"}
        )
        yield mock


@pytest.fixture
async def all_mocked_services(
    mock_twilio_client,
    mock_supabase_client,
    mock_anthropic_client,
    mock_planradar_client,
):
    """Fixture that provides all mocked services together."""
    with patch("src.config.settings.enable_fsm", True):
        yield {
            "twilio": mock_twilio_client,
            "supabase": mock_supabase_client,
            "anthropic": mock_anthropic_client,
            "planradar": mock_planradar_client,
        }


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sample_user():
    """Sample user data for tests."""
    return {
        "id": "user_test_123",
        "whatsapp_number": "+1234567890",
        "name": "Test User",
        "email": "testuser@example.com",
        "language": "fr",
        "active_project_id": "project_123",
        "active_task_id": "task_456",
        "created_at": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_tasks():
    """Sample task list for tests."""
    return [
        {
            "id": "task_1",
            "title": "Install electrical wiring",
            "description": "Install wiring in main building",
            "status": "open",
            "priority": "high",
            "assigned_to": "user_test_123",
        },
        {
            "id": "task_2",
            "title": "Fix water leak",
            "description": "Repair leak in basement",
            "status": "open",
            "priority": "critical",
            "assigned_to": "user_test_123",
        },
        {
            "id": "task_3",
            "title": "Paint walls",
            "description": "Paint walls in office area",
            "status": "in_progress",
            "priority": "medium",
            "assigned_to": "user_test_123",
        },
        {
            "id": "task_4",
            "title": "Install flooring",
            "description": "Install hardwood flooring",
            "status": "open",
            "priority": "low",
            "assigned_to": "user_test_123",
        },
    ]


@pytest.fixture
def sample_messages():
    """Sample message patterns for tests."""
    return {
        # Greetings
        "greeting_french": "Bonjour",
        "greeting_english": "Hello",
        "greeting_casual": "Hey",
        # Task operations
        "update_task": "Update task",
        "view_tasks": "Show my tasks",
        "complete_task": "Mark as complete",
        "cancel": "Cancel",
        # Vague messages
        "vague_done": "Done",
        "vague_finished": "Finished",
        "vague_ok": "OK",
        # Detailed messages
        "detailed_update": "Wall painting is 80% complete, need one more day",
        "problem_report": "There's a problem with the electrical wiring in room 5",
        # Questions
        "ask_address": "What's the project address?",
        "ask_deadline": "When is the deadline?",
        # Confirmation
        "yes": "Yes",
        "no": "No",
        "confirm": "Yes, confirm",
    }


@pytest.fixture
def sample_webhook_data():
    """Sample Twilio webhook data."""
    return {
        "From": "+1234567890",
        "Body": "Hello",
        "MessageSid": "SM_test_123",
        "MediaUrl0": None,
        "MediaContentType0": None,
        "ButtonPayload": None,
        "ButtonText": None,
    }


# ============================================================================
# Helper Utilities
# ============================================================================


@pytest.fixture
def freeze_time():
    """Utility to freeze time for tests."""

    def _freeze(frozen_time):
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = frozen_time
            return mock_datetime

    return _freeze


@pytest.fixture
def assert_no_errors(caplog):
    """Utility to assert no errors were logged during test."""

    def _check():
        errors = [record for record in caplog.records if record.levelname == "ERROR"]
        assert len(errors) == 0, f"Found {len(errors)} errors in logs: {errors}"

    return _check


# ============================================================================
# FSM-Specific Fixtures
# ============================================================================


@pytest.fixture
def mock_fsm_state_manager():
    """Mock FSM StateManager for FSM tests."""
    with patch("src.fsm.core.StateManager") as mock:
        mock.get_session = AsyncMock(return_value=None)
        mock.create_session = AsyncMock(return_value="session_123")
        mock.update_session_state = AsyncMock(return_value=True)
        mock.log_transition = AsyncMock()
        mock.check_idempotency = AsyncMock(return_value=None)
        mock.record_idempotency = AsyncMock(return_value=True)
        yield mock


@pytest.fixture
def mock_intent_router():
    """Mock IntentRouter for routing tests."""
    with patch("src.fsm.routing.IntentRouter") as mock:
        mock.return_value.route = AsyncMock(
            return_value={"intent": "greeting", "confidence": 0.95}
        )
        yield mock


# ============================================================================
# Test Environment Configuration
# ============================================================================


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Automatically set up test environment for all tests."""
    # Set test-specific environment variables
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    # Disable external API calls by default
    monkeypatch.setenv("DISABLE_EXTERNAL_APIS", "true")

    # Set required API keys and credentials (dummy values for tests)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test_twilio_sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test_twilio_token")
    monkeypatch.setenv("TWILIO_WHATSAPP_NUMBER", "+1234567890")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test_anon_key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_service_role_key")
    monkeypatch.setenv("PLANRADAR_API_KEY", "test_planradar_key")
    monkeypatch.setenv("PLANRADAR_ACCOUNT_ID", "test_account_id")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_12345678901234567890")

    yield


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Cleanup resources after each test."""
    yield
    # Add any necessary cleanup here
    # e.g., clear caches, close connections, etc.


# ============================================================================
# Performance Monitoring
# ============================================================================


@pytest.fixture
def performance_tracker():
    """Track test performance metrics."""
    import time

    class PerformanceTracker:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = time.time()

        def stop(self):
            self.end_time = time.time()

        def duration(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

    return PerformanceTracker()
