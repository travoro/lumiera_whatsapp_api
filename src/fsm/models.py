"""Pydantic models for FSM (Finite State Machine) components.

This module defines the core data models used throughout the FSM system,
including session states, transition rules, and context management.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class SessionState(str, Enum):
    """Valid states for a user session in the FSM.

    State Transitions:
    - IDLE: No active session
    - TASK_SELECTION: User is selecting which task to update
    - AWAITING_ACTION: User has selected task, waiting for action (photo, comment, complete, etc.)
    - COLLECTING_DATA: Actively collecting data (photos, comments, etc.)
    - CONFIRMATION_PENDING: Waiting for user confirmation before finalizing
    - COMPLETED: Session successfully completed
    - ABANDONED: Session abandoned (timeout or user cancelled)
    """
    IDLE = "idle"
    TASK_SELECTION = "task_selection"
    AWAITING_ACTION = "awaiting_action"
    COLLECTING_DATA = "collecting_data"
    CONFIRMATION_PENDING = "confirmation_pending"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class IntentPriority(str, Enum):
    """Priority levels for intent classification.

    Higher priority (P0) takes precedence over lower priority (P4).
    Used for conflict resolution when multiple intents are detected.
    """
    P0_CRITICAL = "P0"  # Explicit commands: cancel, stop, help
    P1_EXPLICIT = "P1"  # Direct action requests: "upload photo", "add comment"
    P2_IMPLICIT = "P2"  # Contextual actions during session
    P3_GENERAL = "P3"   # General queries, greetings
    P4_FALLBACK = "P4"  # Fallback/unknown intents


class TransitionRule(BaseModel):
    """Defines a valid state transition rule.

    Attributes:
        from_state: Source state (or None for any state)
        to_state: Target state
        trigger: What triggers this transition
        conditions: Optional conditions that must be met (not enforced in v1)
        description: Human-readable description of the transition
    """
    from_state: Optional[SessionState] = None  # None = from any state
    to_state: SessionState
    trigger: str
    conditions: Optional[List[str]] = None
    description: str

    class Config:
        use_enum_values = True


class FSMContext(BaseModel):
    """Context information for FSM operations.

    This holds all the necessary information about the current session
    and the user's interaction state.

    Attributes:
        user_id: User's WhatsApp ID
        current_state: Current FSM state
        session_id: Unique session identifier
        task_id: ID of task being updated (if applicable)
        collected_data: Data collected during session (photos, comments, etc.)
        last_activity: Timestamp of last user activity
        intent_history: Recent intents detected (for conflict resolution)
        metadata: Additional context-specific metadata
    """
    user_id: str
    current_state: SessionState
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    collected_data: Dict[str, Any] = Field(default_factory=dict)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    intent_history: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class TransitionResult(BaseModel):
    """Result of attempting a state transition.

    Attributes:
        success: Whether the transition succeeded
        from_state: Source state
        to_state: Target state (or current if failed)
        trigger: What triggered the transition
        error: Error message if transition failed
        context: Updated FSM context after transition
        side_effects: List of side effects executed (for logging)
    """
    success: bool
    from_state: SessionState
    to_state: SessionState
    trigger: str
    error: Optional[str] = None
    context: Optional[FSMContext] = None
    side_effects: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class IntentClassification(BaseModel):
    """Result of intent classification with priority and confidence.

    Attributes:
        intent: Detected intent name
        confidence: Confidence score (0.0 to 1.0)
        priority: Priority level for conflict resolution
        parameters: Extracted parameters from user message
        conflicts_with_session: Whether this intent conflicts with active session
    """
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    priority: IntentPriority
    parameters: Dict[str, Any] = Field(default_factory=dict)
    conflicts_with_session: bool = False

    class Config:
        use_enum_values = True


class ClarificationRequest(BaseModel):
    """Request for user clarification when intent is ambiguous.

    Attributes:
        user_id: User's WhatsApp ID
        message: Clarification question to send to user
        options: List of possible options for user to choose
        context: FSM context when clarification was requested
        created_at: When clarification was requested
        expires_at: When this clarification request expires
    """
    user_id: str
    message: str
    options: List[str]
    context: FSMContext
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime

    class Config:
        use_enum_values = True


class IdempotencyRecord(BaseModel):
    """Record for tracking processed messages to prevent duplicate execution.

    Attributes:
        key: Unique idempotency key (user_id:message_id)
        user_id: User's WhatsApp ID
        message_id: WhatsApp message ID
        processed_at: When the message was processed
        result: Result of processing (for caching)
    """
    key: str
    user_id: str
    message_id: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    result: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True
