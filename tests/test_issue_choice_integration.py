"""Integration tests for issue detection and choice handling.

Tests the full flow:
1. Context classifier detects issue in user message
2. Direct handler presents choices to user
3. User selection routing (create report / add comment / skip)
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client."""
    with patch("src.handlers.message.supabase_client") as mock:
        mock.get_user_name = MagicMock(return_value="Test User")
        yield mock


@pytest.fixture
def mock_progress_state():
    """Mock progress update state."""
    with patch("src.services.progress_update.progress_update_state") as mock:
        mock.get_session = AsyncMock(
            return_value={
                "id": "session-123",
                "task_id": "task-456",
                "project_id": "project-789",
                "fsm_state": "awaiting_action",
            }
        )
        mock.clear_session = AsyncMock()
        yield mock


@pytest.fixture
def mock_add_comment_tool():
    """Mock add_progress_comment_tool."""
    with patch("src.services.progress_update.tools.add_progress_comment_tool") as mock:
        mock.ainvoke = AsyncMock(return_value="✅ Commentaire ajouté")
        yield mock


@pytest.fixture
def mock_handle_direct_action_recursive():
    """Mock recursive handle_direct_action calls."""

    async def mock_handler(*args, **kwargs):
        action = kwargs.get("action", "")
        if "report_incident" in action:
            return {
                "message": "📋 Créons un rapport d'incident...",
                "tool_outputs": [],
            }
        return None

    return mock_handler


@pytest.mark.asyncio
async def test_issue_detection_presents_choices():
    """Test that detecting an issue presents user with choices."""
    from src.services.handlers import execute_direct_handler

    result = await execute_direct_handler(
        intent="handle_detected_issue",
        user_id="user-123",
        phone_number="+1234567890",
        user_name="Test User",
        language="fr",
        suggestion_context={
            "issue_detected": True,
            "issue_severity": "high",
            "issue_description": "fuite d'eau",
            "original_message": "travail terminé mais il y a une fuite d'eau",
            "from_session": "progress_update",
            "session_id": "session-123",
        },
    )

    assert result is not None
    assert result["success"] is True
    assert "fuite d'eau" in result["message"]
    assert "🚨" in result["message"]  # High severity emoji
    assert "1. Créer un rapport" in result["message"]
    assert "2. Ajouter un commentaire" in result["message"]
    assert "3. Continuer sans noter" in result["message"]
    assert result["response_type"] == "interactive_list"
    assert result["list_type"] == "option"
    assert result["stay_in_session"] is True

    # Verify pending_action is included
    assert "pending_action" in result
    assert result["pending_action"]["type"] == "issue_choice"
    assert result["pending_action"]["severity"] == "high"
    assert result["pending_action"]["description"] == "fuite d'eau"


@pytest.mark.asyncio
async def test_pending_action_storage():
    """Test that pending_action is properly included in handler result."""
    from src.services.handlers import execute_direct_handler

    result = await execute_direct_handler(
        intent="handle_detected_issue",
        user_id="user-123",
        phone_number="+1234567890",
        user_name="Test User",
        language="fr",
        suggestion_context={
            "issue_detected": True,
            "issue_severity": "medium",
            "issue_description": "vis manquantes",
            "original_message": "il manque des vis",
            "from_session": "progress_update",
            "session_id": "session-123",
        },
    )

    # Verify all pending_action fields are present
    assert "pending_action" in result
    pending = result["pending_action"]
    assert pending["type"] == "issue_choice"
    assert pending["severity"] == "medium"
    assert pending["description"] == "vis manquantes"
    assert pending["original_message"] == "il manque des vis"
    assert pending["from_session"] == "progress_update"


@pytest.mark.asyncio
async def test_severity_levels_show_correct_urgency():
    """Test that different severity levels show appropriate urgency."""
    from src.services.handlers import execute_direct_handler

    # Test high severity
    result_high = await execute_direct_handler(
        intent="handle_detected_issue",
        user_id="user-123",
        phone_number="+1234567890",
        user_name="Test User",
        language="fr",
        suggestion_context={
            "issue_severity": "high",
            "issue_description": "danger électrique",
            "original_message": "attention danger électrique",
        },
    )
    assert "🚨" in result_high["message"]
    assert "important" in result_high["message"]

    # Test medium severity
    result_medium = await execute_direct_handler(
        intent="handle_detected_issue",
        user_id="user-123",
        phone_number="+1234567890",
        user_name="Test User",
        language="fr",
        suggestion_context={
            "issue_severity": "medium",
            "issue_description": "vis manquantes",
            "original_message": "il manque des vis",
        },
    )
    assert "⚠️" in result_medium["message"]
    assert "mérite" in result_medium["message"]

    # Test low severity
    result_low = await execute_direct_handler(
        intent="handle_detected_issue",
        user_id="user-123",
        phone_number="+1234567890",
        user_name="Test User",
        language="fr",
        suggestion_context={
            "issue_severity": "low",
            "issue_description": "peinture imparfaite",
            "original_message": "la peinture n'est pas belle",
        },
    )
    assert "💬" in result_low["message"]
    # Low severity has no urgency message
    assert "important" not in result_low["message"]
