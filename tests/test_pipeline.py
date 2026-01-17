"""Unit tests for message pipeline stages.

Tests each pipeline stage method in isolation with proper mocking.
These are TRUE unit tests - fast, isolated, and testing one thing at a time.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.handlers.message_pipeline import MessagePipeline, MessageContext
from src.utils.result import Result


# ============================================================================
# Utility Method Tests
# ============================================================================

class TestLanguageNormalization:
    """Test language code normalization utility."""

    def test_normalizes_french_full_name(self):
        """Test normalization of 'french' to 'fr'."""
        pipeline = MessagePipeline()
        assert pipeline._normalize_language_code("french") == "fr"

    def test_normalizes_english_full_name(self):
        """Test normalization of 'english' to 'en'."""
        pipeline = MessagePipeline()
        assert pipeline._normalize_language_code("english") == "en"

    def test_preserves_iso_code(self):
        """Test that ISO codes are preserved."""
        pipeline = MessagePipeline()
        assert pipeline._normalize_language_code("fr") == "fr"
        assert pipeline._normalize_language_code("en") == "en"
        assert pipeline._normalize_language_code("es") == "es"

    def test_handles_case_insensitive(self):
        """Test case-insensitive handling."""
        pipeline = MessagePipeline()
        assert pipeline._normalize_language_code("FRENCH") == "fr"
        assert pipeline._normalize_language_code("French") == "fr"

    def test_defaults_to_french_for_unknown(self):
        """Test default to French for unknown languages."""
        pipeline = MessagePipeline()
        assert pipeline._normalize_language_code("unknown") == "fr"
        assert pipeline._normalize_language_code("") == "fr"
        assert pipeline._normalize_language_code(None) == "fr"


# ============================================================================
# Stage 1: User Authentication Tests
# ============================================================================

class TestAuthenticateUser:
    """Test user authentication stage."""

    @pytest.mark.asyncio
    async def test_authenticates_existing_user(self):
        """Test successful authentication of existing user."""
        pipeline = MessagePipeline()
        ctx = MessageContext(
            from_number="+1234567890",
            message_body="Test"
        )

        with patch("src.handlers.message_pipeline.supabase_client") as mock_sb:
            mock_sb.get_user_by_phone = AsyncMock(return_value={
                "id": "user_123",
                "contact_prenom": "John",
                "contact_name": "Doe",
                "language": "fr"
            })

            result = await pipeline._authenticate_user(ctx)

            assert result.success is True
            assert ctx.user_id == "user_123"
            assert ctx.user_name == "John"
            assert ctx.user_language == "fr"

    @pytest.mark.asyncio
    async def test_normalizes_language_code(self):
        """Test language code normalization during authentication."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+1234567890", message_body="Test")

        with patch("src.handlers.message_pipeline.supabase_client") as mock_sb:
            mock_sb.get_user_by_phone = AsyncMock(return_value={
                "id": "user_123",
                "language": "french"  # Full name
            })

            result = await pipeline._authenticate_user(ctx)

            assert result.success is True
            assert ctx.user_language == "fr"  # Normalized to ISO code

    @pytest.mark.asyncio
    async def test_fails_for_unknown_user(self):
        """Test failure when user not found."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+9999999999", message_body="Test")

        with patch("src.handlers.message_pipeline.supabase_client") as mock_sb:
            mock_sb.get_user_by_phone = AsyncMock(return_value=None)

            result = await pipeline._authenticate_user(ctx)

            assert result.success is False


# ============================================================================
# Stage 2: Session Management Tests
# ============================================================================

class TestManageSession:
    """Test session management stage."""

    @pytest.mark.asyncio
    async def test_creates_new_session(self):
        """Test creation of new session."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+1234567890", message_body="Test")
        ctx.user_id = "user_123"

        with patch("src.handlers.message_pipeline.session_service") as mock_session, \
             patch("src.handlers.message_pipeline.supabase_client") as mock_sb:

            mock_session.get_or_create_session = AsyncMock(return_value={
                "id": "session_abc",
                "user_id": "user_123"
            })
            mock_sb.get_messages_by_session = AsyncMock(return_value=[])

            result = await pipeline._manage_session(ctx)

            assert result.success is True
            assert ctx.session_id == "session_abc"

    @pytest.mark.asyncio
    async def test_loads_recent_messages(self):
        """Test loading of recent messages for context."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+1234567890", message_body="Test")
        ctx.user_id = "user_123"

        messages = [
            {"content": "Msg 1", "direction": "inbound", "created_at": "2026-01-17T00:00:00"},
            {"content": "Msg 2", "direction": "outbound", "created_at": "2026-01-17T00:01:00"},
            {"content": "Msg 3", "direction": "inbound", "created_at": "2026-01-17T00:02:00"}
        ]

        with patch("src.handlers.message_pipeline.session_service") as mock_session, \
             patch("src.handlers.message_pipeline.supabase_client") as mock_sb:

            mock_session.get_or_create_session = AsyncMock(return_value={"id": "session_abc"})
            mock_sb.get_messages_by_session = AsyncMock(return_value=messages)

            result = await pipeline._manage_session(ctx)

            assert result.success is True
            assert len(ctx.recent_messages) == 3


# ============================================================================
# Stage 6: Intent Classification Tests
# ============================================================================

class TestClassifyIntent:
    """Test intent classification stage."""

    @pytest.mark.asyncio
    async def test_classifies_text_message(self):
        """Test intent classification for text message."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+1234567890", message_body="Hello")
        ctx.user_id = "user_123"
        ctx.message_in_french = "Bonjour"

        with patch("src.handlers.message_pipeline.intent_classifier") as mock_intent:
            mock_intent.classify = AsyncMock(return_value={
                "intent": "greeting",
                "confidence": 0.95
            })

            result = await pipeline._classify_intent(ctx)

            assert result.success is True
            assert ctx.intent == "greeting"
            assert ctx.confidence == 0.95
            mock_intent.classify.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_media_context(self):
        """Test that media context is included in classification."""
        pipeline = MessagePipeline()
        ctx = MessageContext(
            from_number="+1234567890",
            message_body="Photo",
            media_url="https://example.com/photo.jpg",
            media_type="image/jpeg"
        )
        ctx.user_id = "user_123"
        ctx.message_in_french = "Photo"

        with patch("src.handlers.message_pipeline.intent_classifier") as mock_intent:
            mock_intent.classify = AsyncMock(return_value={
                "intent": "report_incident",
                "confidence": 0.88
            })

            result = await pipeline._classify_intent(ctx)

            assert result.success is True
            # Verify media context was passed
            call_kwargs = mock_intent.classify.call_args.kwargs
            assert call_kwargs.get("has_media") is True
            assert call_kwargs.get("media_type") == "image"


# ============================================================================
# Stage 9: Message Persistence Tests
# ============================================================================

class TestPersistMessages:
    """Test message persistence stage."""

    @pytest.mark.asyncio
    async def test_saves_inbound_and_outbound(self):
        """Test saving both inbound and outbound messages."""
        pipeline = MessagePipeline()
        ctx = MessageContext(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM123"
        )
        ctx.user_id = "user_123"
        ctx.session_id = "session_abc"
        ctx.user_language = "fr"
        ctx.response_text = "Bonjour!"
        ctx.escalation = False
        ctx.tool_outputs = []

        with patch("src.handlers.message_pipeline.supabase_client") as mock_sb:
            mock_sb.save_message = AsyncMock(return_value=True)

            await pipeline._persist_messages(ctx)

            # Verify both messages were saved
            assert mock_sb.save_message.call_count == 2

            # Check inbound call
            inbound_call = mock_sb.save_message.call_args_list[0]
            assert inbound_call.kwargs["direction"] == "inbound"
            assert inbound_call.kwargs["message_text"] == "Hello"

            # Check outbound call
            outbound_call = mock_sb.save_message.call_args_list[1]
            assert outbound_call.kwargs["direction"] == "outbound"
            assert outbound_call.kwargs["message_text"] == "Bonjour!"

    @pytest.mark.asyncio
    async def test_includes_tool_outputs_in_metadata(self):
        """Test that tool outputs are included in outbound metadata."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+1234567890", message_body="Test")
        ctx.user_id = "user_123"
        ctx.session_id = "session_abc"
        ctx.user_language = "fr"
        ctx.response_text = "Response"
        ctx.escalation = False
        ctx.intent = "view_tasks"
        ctx.tool_outputs = [{"tool": "list_tasks", "result": "success"}]

        with patch("src.handlers.message_pipeline.supabase_client") as mock_sb:
            mock_sb.save_message = AsyncMock(return_value=True)

            await pipeline._persist_messages(ctx)

            # Check outbound metadata
            outbound_call = mock_sb.save_message.call_args_list[1]
            metadata = outbound_call.kwargs.get("metadata")

            assert metadata is not None
            assert "tool_outputs" in metadata
            assert len(metadata["tool_outputs"]) == 1

    @pytest.mark.asyncio
    async def test_handles_persistence_failure_gracefully(self):
        """Test that persistence failures don't crash the pipeline."""
        pipeline = MessagePipeline()
        ctx = MessageContext(from_number="+1234567890", message_body="Test")
        ctx.user_id = "user_123"
        ctx.session_id = "session_abc"
        ctx.user_language = "fr"
        ctx.response_text = "Response"
        ctx.escalation = False
        ctx.tool_outputs = []

        with patch("src.handlers.message_pipeline.supabase_client") as mock_sb:
            mock_sb.save_message = AsyncMock(side_effect=Exception("DB error"))

            # Should not raise exception
            await pipeline._persist_messages(ctx)


# ============================================================================
# MessageContext Tests
# ============================================================================

class TestMessageContext:
    """Test MessageContext dataclass."""

    def test_creates_context_with_required_fields(self):
        """Test creation with required fields only."""
        ctx = MessageContext(
            from_number="+1234567890",
            message_body="Hello"
        )

        assert ctx.from_number == "+1234567890"
        assert ctx.message_body == "Hello"
        assert ctx.user_id is None
        assert ctx.session_id is None

    def test_creates_context_with_all_fields(self):
        """Test creation with all fields."""
        ctx = MessageContext(
            from_number="+1234567890",
            message_body="Hello",
            message_sid="SM123",
            media_url="https://example.com/photo.jpg",
            media_type="image/jpeg",
            interactive_data={"button": "clicked"}
        )

        assert ctx.message_sid == "SM123"
        assert ctx.media_url == "https://example.com/photo.jpg"
        assert ctx.media_type == "image/jpeg"
        assert ctx.interactive_data == {"button": "clicked"}

    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        ctx = MessageContext(from_number="+1234567890", message_body="Test")
        ctx.user_id = "user_123"
        ctx.intent = "greeting"
        ctx.confidence = 0.95

        result = ctx.to_dict()

        assert result["user_id"] == "user_123"
        assert result["intent"] == "greeting"
        assert result["confidence"] == 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
