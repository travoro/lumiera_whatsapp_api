"""Tests for message processing pipeline.

This test suite focuses on the MessagePipeline class and its stages:
1. User lookup and authentication
2. Message translation and transcription
3. Intent classification
4. Intent routing
5. Response generation
6. Message persistence
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
from src.handlers.message_pipeline import MessagePipeline, MessageContext
from src.fsm.models import SessionState


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_services():
    """Mock all services used by the pipeline."""
    with patch("src.handlers.message_pipeline.supabase_client") as mock_supabase, \
         patch("src.handlers.message_pipeline.translation_service") as mock_translation, \
         patch("src.handlers.message_pipeline.transcription_service") as mock_transcription, \
         patch("src.handlers.message_pipeline.intent_classifier") as mock_intent, \
         patch("src.handlers.message_pipeline.intent_router") as mock_router, \
         patch("src.handlers.message_pipeline.lumiera_agent") as mock_agent:

        # Mock user lookup
        mock_supabase.get_user_by_phone = Mock(return_value={
            "id": "user_test_123",
            "whatsapp_number": "+1234567890",
            "name": "Test User",
            "language": "fr",
            "active_project_id": "project_123"
        })

        # Mock translation
        mock_translation.translate_to_french = AsyncMock(return_value="Bonjour")

        # Mock transcription
        mock_transcription.transcribe_audio = AsyncMock(return_value="Hello")

        # Mock intent classification
        mock_intent.classify_intent = AsyncMock(return_value={
            "intent": "greeting",
            "confidence": 0.95
        })

        # Mock intent router
        mock_router.route_intent = AsyncMock(return_value={
            "message": "Bonjour! Comment puis-je vous aider?"
        })

        # Mock AI agent
        mock_agent.process = AsyncMock(return_value="AI response")

        yield {
            "supabase": mock_supabase,
            "translation": mock_translation,
            "transcription": mock_transcription,
            "intent": mock_intent,
            "router": mock_router,
            "agent": mock_agent
        }


# ============================================================================
# Pipeline Stage Tests
# ============================================================================

class TestMessagePipeline:
    """Test MessagePipeline class."""

    @pytest.mark.asyncio
    async def test_pipeline_processes_text_message(self, mock_services):
        """Test pipeline processes a simple text message."""
        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM_test_123"
        )

        # Verify pipeline completed
        assert result is not None
        assert isinstance(result, MessageContext)
        assert result.user_id == "user_test_123"
        assert result.message_body == "Hello"

    @pytest.mark.asyncio
    async def test_pipeline_handles_media_message(self, mock_services):
        """Test pipeline processes messages with media."""
        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Check this photo",
            message_sid="SM_test_124",
            media_url="https://example.com/photo.jpg",
            media_type="image/jpeg"
        )

        # Verify media was captured
        assert result.media_url == "https://example.com/photo.jpg"
        assert result.media_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_pipeline_handles_button_interaction(self, mock_services):
        """Test pipeline processes interactive button clicks."""
        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="",
            message_sid="SM_test_125",
            button_payload="task_123",
            button_text="Task XYZ"
        )

        # Verify button interaction was captured
        assert result.interactive_data is not None
        assert result.interactive_data.get("button_payload") == "task_123"

    @pytest.mark.asyncio
    async def test_pipeline_translates_to_french(self, mock_services):
        """Test pipeline translates user messages to French."""
        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM_test_126"
        )

        # Verify translation was called
        mock_services["translation"].translate_to_french.assert_called()

    @pytest.mark.asyncio
    async def test_pipeline_classifies_intent(self, mock_services):
        """Test pipeline classifies message intent."""
        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM_test_127"
        )

        # Verify intent classification
        mock_services["intent"].classify_intent.assert_called()
        assert result.intent == "greeting"
        assert result.confidence == 0.95


# ============================================================================
# Intent Classification Tests
# ============================================================================

class TestIntentClassification:
    """Test intent classification accuracy."""

    @pytest.mark.asyncio
    async def test_classify_greeting_intent(self, mock_services):
        """Test classification of greeting messages."""
        mock_services["intent"].classify_intent = AsyncMock(return_value={
            "intent": "greeting",
            "confidence": 0.95
        })

        pipeline = MessagePipeline()
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Hi there!",
            message_sid="SM_test_128"
        )

        assert result.intent == "greeting"
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_classify_update_task_intent(self, mock_services):
        """Test classification of task update messages."""
        mock_services["intent"].classify_intent = AsyncMock(return_value={
            "intent": "update_progress",
            "confidence": 0.88
        })

        pipeline = MessagePipeline()
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Update task",
            message_sid="SM_test_129"
        )

        assert result.intent == "update_progress"

    @pytest.mark.asyncio
    async def test_classify_view_tasks_intent(self, mock_services):
        """Test classification of view tasks messages."""
        mock_services["intent"].classify_intent = AsyncMock(return_value={
            "intent": "view_tasks",
            "confidence": 0.92
        })

        pipeline = MessagePipeline()
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Show my tasks",
            message_sid="SM_test_130"
        )

        assert result.intent == "view_tasks"

    @pytest.mark.asyncio
    async def test_classify_report_incident_intent(self, mock_services):
        """Test classification of incident report messages."""
        mock_services["intent"].classify_intent = AsyncMock(return_value={
            "intent": "report_incident",
            "confidence": 0.85
        })

        pipeline = MessagePipeline()
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="There's a problem with the plumbing",
            message_sid="SM_test_131"
        )

        assert result.intent == "report_incident"


# ============================================================================
# Intent Routing Tests
# ============================================================================

class TestIntentRouting:
    """Test intent routing to appropriate handlers."""

    @pytest.mark.asyncio
    async def test_route_to_fast_path(self, mock_services):
        """Test routing to fast path for direct actions."""
        mock_services["router"].route_intent = AsyncMock(return_value={
            "message": "Here are your tasks",
            "fast_path": True
        })

        pipeline = MessagePipeline()
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="View tasks",
            message_sid="SM_test_132"
        )

        # Verify router was called
        mock_services["router"].route_intent.assert_called()

    @pytest.mark.asyncio
    async def test_route_to_specialized_agent(self, mock_services):
        """Test routing to specialized agent for complex tasks."""
        mock_services["router"].route_intent = AsyncMock(return_value=None)
        mock_services["agent"].process = AsyncMock(return_value="AI response")

        pipeline = MessagePipeline()
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Tell me about this project",
            message_sid="SM_test_133"
        )

        # Should fall back to AI agent
        mock_services["agent"].process.assert_called()


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    @pytest.mark.asyncio
    async def test_handle_unknown_user(self, mock_services):
        """Test handling of messages from unknown users."""
        mock_services["supabase"].get_user_by_phone = Mock(return_value=None)

        pipeline = MessagePipeline()

        # Should not crash, should handle gracefully
        result = await pipeline.process(
            from_number="+9999999999",
            message_body="Hello",
            message_sid="SM_test_134"
        )

        # Pipeline should still create a context
        assert result is not None
        assert result.user_id is None or result.user_id == "unknown"

    @pytest.mark.asyncio
    async def test_handle_translation_failure(self, mock_services):
        """Test handling of translation service failures."""
        mock_services["translation"].translate_to_french = AsyncMock(
            side_effect=Exception("Translation API down")
        )

        pipeline = MessagePipeline()

        # Should not crash
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM_test_135"
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_handle_intent_classification_failure(self, mock_services):
        """Test handling of intent classification failures."""
        mock_services["intent"].classify_intent = AsyncMock(
            side_effect=Exception("Intent service down")
        )

        pipeline = MessagePipeline()

        # Should fall back gracefully
        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM_test_136"
        )

        assert result is not None


# ============================================================================
# Session Management Tests
# ============================================================================

class TestSessionManagement:
    """Test session management in pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_tracks_session(self, mock_services):
        """Test pipeline tracks user session."""
        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Update task",
            message_sid="SM_test_137"
        )

        # Session should be tracked
        assert result.session_id is not None or result.user_id is not None

    @pytest.mark.asyncio
    async def test_pipeline_preserves_context(self, mock_services):
        """Test pipeline preserves context across messages."""
        mock_services["supabase"].get_recent_messages = AsyncMock(return_value=[
            {"role": "user", "content": "Previous message"}
        ])

        pipeline = MessagePipeline()

        result = await pipeline.process(
            from_number="+1234567890",
            message_body="Follow up message",
            message_sid="SM_test_138"
        )

        # Context should include recent messages
        assert result.recent_messages is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
