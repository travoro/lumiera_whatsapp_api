"""Unit tests for LLM-based context classifier.

Tests the ContextClassifier service that determines if messages
continue active sessions or represent intent changes.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.context_classifier import ContextClassifier

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def context_classifier():
    """Create a ContextClassifier instance with mocked LLM."""
    with patch("src.services.context_classifier.ChatAnthropic") as mock_llm:
        classifier = ContextClassifier()
        classifier.llm = Mock()
        yield classifier, mock_llm


def create_mock_llm_response(classification_result: dict) -> Mock:
    """Helper to create mock LLM response."""
    mock_response = Mock()
    mock_response.content = json.dumps(classification_result)
    return mock_response


# ============================================================================
# Test Category 1: Clear IN_CONTEXT Messages
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simple_yes_response(context_classifier):
    """Test that simple 'yes' response is classified as IN_CONTEXT."""
    classifier, _ = context_classifier

    # Mock LLM response
    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "IN_CONTEXT",
                "confidence": 0.95,
                "reasoning": "Direct affirmative response to bot question",
                "intent_change_type": None,
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Oui",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Souhaitez-vous ajouter une photo?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "IN_CONTEXT"
    assert result["confidence"] >= 0.9
    assert result["issue_mentioned"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_numeric_selection(context_classifier):
    """Test that numeric selections (1, 2, 3) are IN_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "IN_CONTEXT",
                "confidence": 0.95,
                "reasoning": "Numeric selection when bot showed options",
                "intent_change_type": None,
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="1",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="1. Ajouter photo\n2. Ajouter commentaire",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "IN_CONTEXT"
    assert result["confidence"] >= 0.9


@pytest.mark.unit
@pytest.mark.asyncio
async def test_completion_status(context_classifier):
    """Test that completion statements are IN_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "IN_CONTEXT",
                "confidence": 0.90,
                "reasoning": "Status update about task completion - in scope",
                "intent_change_type": None,
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Travail terminé",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Souhaitez-vous autre chose?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "IN_CONTEXT"
    assert result["confidence"] >= 0.85


# ============================================================================
# Test Category 2: Clear OUT_OF_CONTEXT - Navigation
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_explicit_task_change(context_classifier):
    """Test that 'changer de tâche' triggers OUT_OF_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "Explicit navigation - user wants to change task",
                "intent_change_type": "change_task",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": True,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Changer de tâche",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Que souhaitez-vous faire?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["intent_change_type"] == "change_task"
    assert result["suggest_task_switch"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_view_projects_request(context_classifier):
    """Test that 'voir mes projets' triggers OUT_OF_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "User wants to view projects - clear navigation",
                "intent_change_type": "change_project",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": True,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Je veux voir mes projets",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Souhaitez-vous continuer?",
        expecting_response=False,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["intent_change_type"] == "change_project"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_command(context_classifier):
    """Test that 'annuler' triggers OUT_OF_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "Explicit cancel command",
                "intent_change_type": "general",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Annuler",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Envoyez une photo",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["confidence"] >= 0.9


# ============================================================================
# Test Category 3: Issue Detection
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_issue_with_completion(context_classifier):
    """Test that 'fini mais il y a une fuite' detects issue."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.90,
                "reasoning": "User completed but mentions water leak - new incident",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "suggest_incident_report": True,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="J'ai terminé mais il y a une fuite",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Avez-vous terminé?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["issue_mentioned"] is True
    assert result["suggest_incident_report"] is True
    assert result["intent_change_type"] == "report_incident"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broken_wall_issue(context_classifier):
    """Test that 'le mur est cassé' is detected as issue."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "User reports broken wall - clear incident",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "suggest_incident_report": True,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Le mur est cassé",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Comment va le travail?",
        expecting_response=False,
        user_language="fr",
    )

    assert result["issue_mentioned"] is True
    assert result["suggest_incident_report"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ras_no_issue(context_classifier):
    """Test that 'RAS' (Rien À Signaler) is NOT detected as issue."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "IN_CONTEXT",
                "confidence": 0.90,
                "reasoning": "RAS = Rien À Signaler = No problem",
                "intent_change_type": None,
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Terminé, RAS",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Comment s'est passé le travail?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "IN_CONTEXT"
    assert result["issue_mentioned"] is False
    assert result["suggest_incident_report"] is False


# ============================================================================
# Test Category 3b: Issue Severity Assessment
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_high_severity_issue(context_classifier):
    """Test that dangerous issues are classified as high severity."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "Electrical hazard is high severity safety issue",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "issue_severity": "high",
                "issue_description": "danger électrique",
                "suggest_user_choice": True,
                "suggest_incident_report": False,  # Now we ask user
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Attention il y a un danger électrique",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Comment ça se passe?",
        expecting_response=False,
        user_language="fr",
    )

    assert result["issue_mentioned"] is True
    assert result["issue_severity"] == "high"
    assert result["suggest_user_choice"] is True
    assert (
        "électrique" in result["issue_description"]
        or "danger" in result["issue_description"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_medium_severity_issue(context_classifier):
    """Test that quality/material issues are medium severity."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.85,
                "reasoning": "Missing materials is medium severity",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "issue_severity": "medium",
                "issue_description": "vis manquantes",
                "suggest_user_choice": True,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="J'ai fini mais il manque des vis",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Terminé?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["issue_mentioned"] is True
    assert result["issue_severity"] == "medium"
    assert result["suggest_user_choice"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_low_severity_issue(context_classifier):
    """Test that cosmetic issues are low severity."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.80,
                "reasoning": "Paint quality is cosmetic/low severity",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "issue_severity": "low",
                "issue_description": "peinture imparfaite",
                "suggest_user_choice": True,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="La peinture n'est pas parfaite",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Avez-vous terminé?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["issue_mentioned"] is True
    assert result["issue_severity"] == "low"
    assert result["suggest_user_choice"] is True
    assert "peinture" in result["issue_description"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_water_leak_high_severity(context_classifier):
    """Test that water leaks are high severity."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "Water leak is high severity issue",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "issue_severity": "high",
                "issue_description": "fuite d'eau",
                "suggest_user_choice": True,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Terminé mais il y a une fuite d'eau",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Travail terminé?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["issue_mentioned"] is True
    assert result["issue_severity"] == "high"
    assert (
        "fuite" in result["issue_description"] or "eau" in result["issue_description"]
    )


# ============================================================================
# Test Category 4: Task/Project Switching
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_switch_to_next_task(context_classifier):
    """Test that 'je passe à la tâche suivante' triggers switch."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "User explicitly moving to next task",
                "intent_change_type": "change_task",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": True,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Je passe à la tâche suivante",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Terminé avec cette tâche?",
        expecting_response=False,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["suggest_task_switch"] is True
    assert result["intent_change_type"] == "change_task"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_switch_to_other_project(context_classifier):
    """Test that 'autre projet' triggers project switch."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "User wants another project",
                "intent_change_type": "change_project",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": True,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Autre projet s'il vous plaît",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Que voulez-vous faire?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["intent_change_type"] == "change_project"


# ============================================================================
# Test Category 5: Ambiguous Cases
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambiguous_ok(context_classifier):
    """Test that 'ok' alone is ambiguous but defaults to IN_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "IN_CONTEXT",
                "confidence": 0.65,
                "reasoning": "Very short acknowledgment - likely continuing",
                "intent_change_type": None,
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Ok",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Terminé?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "IN_CONTEXT"
    assert 0.6 <= result["confidence"] <= 0.75


@pytest.mark.unit
@pytest.mark.asyncio
async def test_help_with_question(context_classifier):
    """Test that 'aide' when bot asked question is IN_CONTEXT."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "IN_CONTEXT",
                "confidence": 0.70,
                "reasoning": "Bot just asked question, user needs clarification",
                "intent_change_type": None,
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Aide",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Que souhaitez-vous faire?\n1. Photo\n2. Commentaire",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "IN_CONTEXT"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_help_without_question(context_classifier):
    """Test that 'aide' without bot question triggers escalation."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.75,
                "reasoning": "No recent bot question, user wants human help",
                "intent_change_type": "escalate",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Aide",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="",  # No recent bot message
        expecting_response=False,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["intent_change_type"] == "escalate"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_greeting_mid_session(context_classifier):
    """Test that 'bonjour' mid-session triggers restart."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.85,
                "reasoning": "Greeting mid-session indicates restart",
                "intent_change_type": "general",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Bonjour",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Souhaitez-vous continuer?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["confidence"] >= 0.8


# ============================================================================
# Test Error Handling
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_error_fallback(context_classifier):
    """Test that LLM errors gracefully fallback to IN_CONTEXT."""
    classifier, _ = context_classifier

    # Simulate LLM error
    classifier.llm.ainvoke = AsyncMock(side_effect=Exception("API timeout"))

    result = await classifier.classify_message_context(
        message="Test message",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Test?",
        expecting_response=True,
        user_language="fr",
    )

    # Should fallback to IN_CONTEXT to avoid disrupting flow
    assert result["context"] == "IN_CONTEXT"
    assert result["confidence"] == 0.5
    assert "Error during classification" in result["reasoning"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_json_fallback(context_classifier):
    """Test handling of malformed JSON from LLM."""
    classifier, _ = context_classifier

    # Mock malformed response
    mock_response = Mock()
    mock_response.content = "This is not valid JSON"
    classifier.llm.ainvoke = AsyncMock(return_value=mock_response)

    result = await classifier.classify_message_context(
        message="Test",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Test?",
        expecting_response=True,
        user_language="fr",
    )

    # Should fallback gracefully
    assert result["context"] == "IN_CONTEXT"
    assert result["confidence"] == 0.5


# ============================================================================
# Test Multi-Language Support
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_english_navigation(context_classifier):
    """Test that English navigation messages work."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.95,
                "reasoning": "User wants to change task - English",
                "intent_change_type": "change_task",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": True,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Change task",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="What do you want to do?",
        expecting_response=True,
        user_language="en",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["suggest_task_switch"] is True


# ============================================================================
# Test Prompt Building
# ============================================================================


@pytest.mark.unit
def test_prompt_includes_session_context(context_classifier):
    """Test that prompt includes all necessary context."""
    classifier, _ = context_classifier

    prompt = classifier._build_classification_prompt(
        message="Test message",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="What next?",
        expecting_response=True,
        session_metadata={"test": "data"},
        user_language="fr",
    )

    # Check key elements are in prompt
    assert "progress_update" in prompt
    assert "awaiting_action" in prompt
    assert "What next?" in prompt
    assert "Test message" in prompt
    assert "Oui" in prompt  # Bot expecting response
    assert "CONTEXTE SPÉCIFIQUE - Mise à jour de progression" in prompt


@pytest.mark.unit
def test_prompt_includes_special_cases(context_classifier):
    """Test that prompt includes special case handling."""
    classifier, _ = context_classifier

    prompt = classifier._build_classification_prompt(
        message="Test",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="",
        expecting_response=False,
        session_metadata=None,
        user_language="fr",
    )

    # Check special cases are documented
    assert "RAS" in prompt  # French acronym
    assert "Aide" in prompt  # Ambiguous help
    assert "Bonjour" in prompt  # Mid-session greeting
    assert "CAS PARTICULIERS" in prompt


# ============================================================================
# Integration-Style Tests (More Complex Scenarios)
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_complex_issue_detection_scenario(context_classifier):
    """Test complex scenario: completion + issue + suggestion."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.92,
                "reasoning": "User completed work but found safety issue",
                "intent_change_type": "report_incident",
                "issue_mentioned": True,
                "suggest_incident_report": True,
                "suggest_task_switch": False,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Peinture terminée mais attention il y a danger électrique",
        session_type="progress_update",
        session_state="collecting_data",
        last_bot_message="Avez-vous fini?",
        expecting_response=True,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["issue_mentioned"] is True
    assert result["suggest_incident_report"] is True
    # Reasoning should mention issue/safety (not checking exact words to avoid brittleness)
    assert len(result["reasoning"]) > 10  # Has meaningful reasoning


@pytest.mark.unit
@pytest.mark.asyncio
async def test_project_switch_with_completion(context_classifier):
    """Test: user finishes and immediately wants new project."""
    classifier, _ = context_classifier

    classifier.llm.ainvoke = AsyncMock(
        return_value=create_mock_llm_response(
            {
                "context": "OUT_OF_CONTEXT",
                "confidence": 0.90,
                "reasoning": "Completion acknowledged, now switching to new project",
                "intent_change_type": "change_project",
                "issue_mentioned": False,
                "suggest_incident_report": False,
                "suggest_task_switch": True,
            }
        )
    )

    result = await classifier.classify_message_context(
        message="Fait. Maintenant le projet Champigny",
        session_type="progress_update",
        session_state="awaiting_action",
        last_bot_message="Autre chose?",
        expecting_response=False,
        user_language="fr",
    )

    assert result["context"] == "OUT_OF_CONTEXT"
    assert result["intent_change_type"] == "change_project"
    assert result["suggest_task_switch"] is True
