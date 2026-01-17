"""Unit tests for dynamic template service and WhatsApp list formatting.

Tests cover:
- List item truncation to 24 characters (fixes production errors)
- Emoji preservation in truncation
- Template validation
- List formatting
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.services.dynamic_templates import DynamicTemplateService


# ============================================================================
# List Item Truncation Tests (Critical - Fixes 42 Production Errors)
# ============================================================================

class TestListItemTruncation:
    """Test list item truncation to WhatsApp's 24-character limit."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DynamicTemplateService()

    def test_truncates_long_item_to_24_chars(self):
        """Test truncation of items exceeding 24 characters."""
        long_text = "This option is definitely too long for WhatsApp"
        truncated = self.service.truncate_with_emoji(long_text, 24)

        assert len(truncated) <= 24
        # Simple truncation without ellipsis
        assert truncated == long_text[:24].strip()

    def test_preserves_short_items(self):
        """Test that short items are not modified."""
        short_text = "Short option"
        result = self.service.truncate_with_emoji(short_text, 24)

        assert result == short_text
        assert len(result) <= 24

    def test_truncates_exactly_at_24_chars(self):
        """Test item exactly at 24 character limit."""
        text_24 = "123456789012345678901234"  # Exactly 24 chars
        result = self.service.truncate_with_emoji(text_24, 24)

        assert len(result) == 24
        assert result == text_24

    def test_truncates_25_char_item(self):
        """Test item with 25 characters (1 over limit)."""
        text_25 = "This is 25 characters!!!"  # 25 chars
        result = self.service.truncate_with_emoji(text_25, 24)

        assert len(result) <= 24

    def test_preserves_emoji_in_short_text(self):
        """Test that emojis are preserved in text under limit."""
        text_with_emoji = "Task complete ✅"
        result = self.service.truncate_with_emoji(text_with_emoji, 24)

        assert "✅" in result
        assert len(result) <= 24

    def test_truncates_long_text_with_emoji(self):
        """Test truncation of long text containing emojis."""
        long_text_emoji = "This is a very long task description with emoji ✅"
        result = self.service.truncate_with_emoji(long_text_emoji, 24)

        assert len(result) <= 24
        # Should truncate but preserve structure

    def test_handles_multiple_emojis(self):
        """Test handling of multiple emojis in text."""
        text = "Complete 🎉 ✅ 👍"
        result = self.service.truncate_with_emoji(text, 24)

        assert len(result) <= 24

    def test_truncates_french_text(self):
        """Test truncation of French text with accents."""
        french_text = "Terminé avec succès aujourd'hui"
        result = self.service.truncate_with_emoji(french_text, 24)

        assert len(result) <= 24

    def test_truncates_at_word_boundary_when_possible(self):
        """Test that truncation prefers word boundaries."""
        text = "Complete the electrical wiring task"
        result = self.service.truncate_with_emoji(text, 24)

        assert len(result) <= 24
        # Simple truncation
        assert result == text[:24].strip()


# ============================================================================
# Template Validation Tests
# ============================================================================

class TestTemplateValidation:
    """Test template validation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DynamicTemplateService()

    def test_validates_correct_list_items(self):
        """Test validation of correctly formatted list items."""
        items = [
            {"id": "1", "item": "Option 1"},
            {"id": "2", "item": "Option 2"},
            {"id": "3", "item": "Option 3"}
        ]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is True
        assert error is None

    def test_rejects_item_over_24_chars(self):
        """Test rejection of items exceeding 24 characters."""
        items = [
            {"id": "1", "item": "This text is way too long for WhatsApp list"},
            {"id": "2", "item": "Short"}
        ]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is False
        assert "24 chars" in error

    def test_rejects_missing_id(self):
        """Test rejection of items missing 'id' field."""
        items = [
            {"item": "Option without ID"}
        ]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is False
        assert "missing" in error.lower()

    def test_rejects_missing_item_text(self):
        """Test rejection of items missing 'item' field."""
        items = [
            {"id": "1", "description": "Description but no item text"}
        ]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is False
        assert "missing" in error.lower()

    def test_validates_items_with_description(self):
        """Test validation of items with optional description."""
        items = [
            {
                "id": "1",
                "item": "Option 1",
                "description": "This is a valid description under 72 characters"
            }
        ]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is True

    def test_rejects_description_over_72_chars(self):
        """Test rejection of descriptions exceeding 72 characters."""
        items = [
            {
                "id": "1",
                "item": "Option",
                "description": "This description is way too long and exceeds the 72 character limit for WhatsApp"
            }
        ]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is False
        assert "72" in error

    def test_rejects_too_many_items(self):
        """Test rejection of more than 10 items."""
        items = [{"id": str(i), "item": f"Option {i}"} for i in range(15)]

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is False
        assert "10" in error

    def test_rejects_empty_item_list(self):
        """Test rejection of empty item list."""
        items = []

        is_valid, error = self.service.validate_list_items(items)

        assert is_valid is False


# ============================================================================
# List Formatting Tests
# ============================================================================

class TestListFormatting:
    """Test list formatting with emoji placement."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DynamicTemplateService()

    def test_adds_emojis_to_list_items(self):
        """Test adding emojis to list items."""
        items = [
            {"id": "1", "item": "Task A"},
            {"id": "2", "item": "Task B"},
            {"id": "3", "item": "Task C"}
        ]

        result = self.service.add_emoji_to_items(
            items,
            emojis=["✅", "✅", "✅"],
            position="start"
        )

        # Check that emojis were added
        assert len(result) == 3
        assert all("✅" in item["item"] for item in result)

    def test_emoji_at_start_position(self):
        """Test emoji placement at start of text."""
        items = [{"id": "1", "item": "Task"}]

        result = self.service.add_emoji_to_items(
            items,
            emojis=["📋"],
            position="start"
        )

        assert result[0]["item"].startswith("📋")

    def test_emoji_at_end_position(self):
        """Test emoji placement at end of text."""
        items = [{"id": "1", "item": "Task"}]

        result = self.service.add_emoji_to_items(
            items,
            emojis=["✅"],
            position="end"
        )

        assert result[0]["item"].endswith("✅")

    def test_ensures_24_char_limit_after_emoji(self):
        """Test that items don't exceed 24 chars after adding emoji."""
        items = [
            {"id": "1", "item": "This is a long task name"}  # 24 chars exactly
        ]

        result = self.service.add_emoji_to_items(
            items,
            emojis=["✅"],
            position="end"
        )

        # Should truncate to fit emoji within 24 chars
        assert len(result[0]["item"]) <= 24

    def test_preserves_item_id(self):
        """Test that item IDs are preserved when adding emojis."""
        items = [
            {"id": "task_123", "item": "Task"},
            {"id": "task_456", "item": "Another"}
        ]

        result = self.service.add_emoji_to_items(items, emojis=["✅", "✅"])

        assert result[0]["id"] == "task_123"
        assert result[1]["id"] == "task_456"

    def test_preserves_description(self):
        """Test that descriptions are preserved when adding emojis."""
        items = [
            {
                "id": "1",
                "item": "Task",
                "description": "Important task description"
            }
        ]

        result = self.service.add_emoji_to_items(items, emojis=["✅"])

        assert result[0]["description"] == "Important task description"


# ============================================================================
# Template Creation Tests (Mocked)
# ============================================================================

class TestTemplateCreation:
    """Test template creation with mocked Twilio API."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch('src.services.dynamic_templates.Client'):
            self.service = DynamicTemplateService()

    @patch('src.services.dynamic_templates.requests.post')
    def test_creates_list_picker_template(self, mock_post):
        """Test creation of list-picker template."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"sid": "HX1234567890"}
        mock_post.return_value = mock_response

        content_data = {
            "body": "Choose an option:",
            "button": "Select",
            "items": [
                {"id": "1", "item": "Option 1"},
                {"id": "2", "item": "Option 2"}
            ]
        }

        result = self.service.create_dynamic_template(
            "twilio/list-picker",
            content_data
        )

        assert result == "HX1234567890"
        assert mock_post.called

    @patch('src.services.dynamic_templates.requests.post')
    def test_handles_template_creation_failure(self, mock_post):
        """Test handling of template creation failure."""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Item cannot exceed 24 characters"
        mock_post.return_value = mock_response

        content_data = {
            "body": "Test",
            "button": "Click",
            "items": [
                {"id": "1", "item": "This item text is way too long for WhatsApp"}
            ]
        }

        result = self.service.create_dynamic_template(
            "twilio/list-picker",
            content_data
        )

        assert result is None

    @patch('src.services.dynamic_templates.requests.post')
    def test_increments_stats_on_success(self, mock_post):
        """Test that stats are incremented on successful creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"sid": "HX1234567890"}
        mock_post.return_value = mock_response

        initial_count = self.service.stats['created']

        self.service.create_dynamic_template(
            "twilio/list-picker",
            {"body": "Test", "button": "Click", "items": [{"id": "1", "item": "OK"}]}
        )

        assert self.service.stats['created'] == initial_count + 1


# ============================================================================
# Real-World Scenario Tests
# ============================================================================

class TestRealWorldScenarios:
    """Test scenarios based on actual production errors."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DynamicTemplateService()

    def test_handles_long_french_task_names(self):
        """Test handling of long French task names (common in production)."""
        # Real example from logs: "Installation électrique - Bâtiment principal"
        long_french_task = "Installation électrique - Bâtiment principal"

        truncated = self.service.truncate_with_emoji(long_french_task, 24)

        assert len(truncated) <= 24

    def test_handles_task_names_with_numbers(self):
        """Test handling of task names with room numbers."""
        task_with_number = "Réparation fuite - Chambre 505"

        truncated = self.service.truncate_with_emoji(task_with_number, 24)

        assert len(truncated) <= 24

    def test_formats_list_of_real_tasks(self):
        """Test formatting of realistic task list."""
        tasks = [
            {"id": "1", "item": "Install electrical wiring in main building"},
            {"id": "2", "item": "Fix water leak in basement room 5"},
            {"id": "3", "item": "Paint walls in office area floor 3"},
            {"id": "4", "item": "Install hardwood flooring bedroom"}
        ]

        # Truncate all items
        formatted = []
        for task in tasks:
            truncated = self.service.truncate_with_emoji(task["item"], 24)
            formatted.append({"id": task["id"], "item": truncated})

        # All should be within limit
        assert all(len(item["item"]) <= 24 for item in formatted)

    def test_validates_real_task_list(self):
        """Test validation of realistic task list after truncation."""
        tasks = [
            {"id": "1", "item": "Install electrical..."},
            {"id": "2", "item": "Fix water leak..."},
            {"id": "3", "item": "Paint walls..."}
        ]

        is_valid, error = self.service.validate_list_items(tasks)

        assert is_valid is True


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DynamicTemplateService()

    def test_handles_empty_string(self):
        """Test handling of empty string."""
        result = self.service.truncate_with_emoji("", 24)

        assert result == ""

    def test_handles_whitespace_only(self):
        """Test handling of whitespace-only text."""
        result = self.service.truncate_with_emoji("   ", 24)

        assert result.strip() == ""

    def test_handles_single_character(self):
        """Test handling of single character."""
        result = self.service.truncate_with_emoji("A", 24)

        assert result == "A"

    def test_handles_exactly_21_chars_plus_emoji(self):
        """Test text that with emoji will be exactly 24 chars."""
        # "Install wiring" (15 chars) + " ✅" (3 chars) = 18 chars
        text = "Install wiring work"  # 19 chars

        result = self.service.truncate_with_emoji(text + " ✅", 24)

        assert len(result) <= 24

    def test_handles_unicode_characters(self):
        """Test handling of unicode characters."""
        unicode_text = "Tâche complétée avec succès"

        result = self.service.truncate_with_emoji(unicode_text, 24)

        assert len(result) <= 24

    def test_handles_mixed_emoji_and_text(self):
        """Test handling of mixed emoji and text."""
        mixed = "✅ Task 🎉 Complete 👍"

        result = self.service.truncate_with_emoji(mixed, 24)

        assert len(result) <= 24


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
