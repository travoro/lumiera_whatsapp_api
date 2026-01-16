"""Finite State Machine (FSM) module for session management.

This module provides a structured approach to managing user session states,
handling state transitions, and resolving intent conflicts.
"""
from src.fsm.models import (
    SessionState,
    FSMContext,
    TransitionRule,
    IntentPriority,
    IntentClassification,
)
from src.fsm.core import StateManager, FSMEngine
from src.fsm.routing import IntentRouter
from src.fsm.handlers import (
    ClarificationManager,
    SessionRecoveryManager,
    clarification_manager,
    session_recovery_manager,
)

__all__ = [
    "SessionState",
    "FSMContext",
    "TransitionRule",
    "IntentPriority",
    "IntentClassification",
    "StateManager",
    "FSMEngine",
    "IntentRouter",
    "ClarificationManager",
    "SessionRecoveryManager",
    "clarification_manager",
    "session_recovery_manager",
]
