"""Handlers for AI-detected suggestions (issues, completions, etc.).

These handlers present users with choices when the AI detects something
that could be handled multiple ways (e.g., issue → incident report or comment).
"""

from typing import Any, Dict

from src.utils.logger import log


async def handle_detected_issue_choice(
    user_id: str,
    phone_number: str,
    user_name: str,
    language: str,
    suggestion_context: dict,
    **kwargs,
) -> Dict[str, Any]:
    """Present user with options for handling detected issue.

    Args:
        user_id: User's ID
        phone_number: User's phone number (not used but required by handler interface)
        user_name: User's name
        language: User's language
        suggestion_context: Context from context classifier containing:
            - issue_severity: "low" | "medium" | "high"
            - issue_description: Brief description
            - original_message: User's original message
            - from_session: Session type where issue was detected
            - session_id: Active session ID
        **kwargs: Additional arguments (for compatibility)

    Returns:
        Dict with formatted response and metadata
    """
    severity = suggestion_context.get("issue_severity", "medium")
    issue_desc = suggestion_context.get("issue_description", "un problème")
    original_message = suggestion_context.get("original_message", "")
    from_session = suggestion_context.get("from_session", "session")

    log.info(
        f"💡 Presenting issue choice to user {user_id[:8]}...\n"
        f"   Severity: {severity}\n"
        f"   Issue: {issue_desc}\n"
        f"   From session: {from_session}\n"
        f"   Original message: {original_message[:50]}..."
    )

    # Severity-based message customization
    if severity == "high":
        emoji = "🚨"
        urgency = "Ce problème semble important et nécessite attention."
    elif severity == "medium":
        emoji = "⚠️"
        urgency = "Ce problème mérite d'être noté."
    else:  # low
        emoji = "💬"
        urgency = ""

    # Build message
    message = f"""{emoji} J'ai remarqué que vous mentionnez {issue_desc}. {urgency}

Comment souhaitez-vous procéder?

1. Créer un rapport
2. Ajouter un commentaire
3. Continuer sans noter"""

    return {
        "success": True,
        "message": message,
        "response_type": "interactive_list",
        "list_type": "option",
        "stay_in_session": True,  # Don't exit session yet
        "pending_action": {
            "type": "issue_choice",
            "severity": severity,
            "description": issue_desc,
            "original_message": original_message,
            "from_session": from_session,
        },
    }


async def handle_issue_choice_selection(
    user_id: str,
    choice: int,
    pending_action: dict,
) -> Dict[str, Any]:
    """Handle user's choice for issue handling.

    Args:
        user_id: User's ID
        choice: 1=Create report, 2=Add comment, 3=Skip
        pending_action: Context from previous issue choice prompt

    Returns:
        Dict with action to take
    """
    severity = pending_action.get("severity")
    description = pending_action.get("description")
    original_message = pending_action.get("original_message")
    from_session = pending_action.get("from_session")

    log.info(f"👤 User {user_id[:8]}... chose option {choice} for issue: {description}")

    if choice == 1:
        # Create incident report
        log.info("📋 Routing to incident report creation")
        return {
            "action": "create_incident_report",
            "exit_current_session": True,
            "pre_fill_data": {
                "description": original_message,
                "severity": severity,
            },
        }

    elif choice == 2:
        # Add comment to task
        log.info("💬 Adding issue as comment to current task")
        return {
            "action": "add_comment_to_task",
            "exit_current_session": False,
            "comment_text": f"⚠️ Problème signalé: {original_message}",
        }

    elif choice == 3:
        # Skip - continue without noting
        log.info("⏭️ User chose to skip issue documentation")
        return {
            "action": "continue_session",
            "exit_current_session": False,
        }

    else:
        log.warning(f"⚠️ Invalid choice: {choice}")
        return {
            "action": "continue_session",
            "exit_current_session": False,
        }
