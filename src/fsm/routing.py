"""Intent routing and conflict resolution for FSM.

This module provides:
- Priority-based intent hierarchy (P0-P4)
- Session-aware confidence adjustment
- Conflict resolution when multiple intents detected
"""

from typing import Any, Dict, List, Optional, Tuple

from src.fsm.models import FSMContext, IntentClassification, IntentPriority
from src.utils.structured_logger import get_structured_logger

logger = get_structured_logger("fsm.routing")


# ============================================================================
# Intent Priority Mappings
# ============================================================================

INTENT_PRIORITY_MAP: Dict[str, IntentPriority] = {
    # P0: Critical/Explicit commands (highest priority)
    "cancel": IntentPriority.P0_CRITICAL,
    "stop": IntentPriority.P0_CRITICAL,
    "help": IntentPriority.P0_CRITICAL,
    "abandon": IntentPriority.P0_CRITICAL,
    # P1: Explicit action requests
    "progress_update": IntentPriority.P1_EXPLICIT,
    "upload_photo": IntentPriority.P1_EXPLICIT,
    "add_comment": IntentPriority.P1_EXPLICIT,
    "complete_task": IntentPriority.P1_EXPLICIT,
    "create_incident": IntentPriority.P1_EXPLICIT,
    "switch_task": IntentPriority.P1_EXPLICIT,
    # P2: Implicit/contextual actions
    "continue_update": IntentPriority.P2_IMPLICIT,
    "add_more_data": IntentPriority.P2_IMPLICIT,
    "confirm": IntentPriority.P2_IMPLICIT,
    # P3: General queries
    "list_tasks": IntentPriority.P3_GENERAL,
    "task_status": IntentPriority.P3_GENERAL,
    "greeting": IntentPriority.P3_GENERAL,
    "question": IntentPriority.P3_GENERAL,
    # P4: Fallback
    "unknown": IntentPriority.P4_FALLBACK,
    "unclear": IntentPriority.P4_FALLBACK,
}


# ============================================================================
# Intent Hierarchy
# ============================================================================


class IntentHierarchy:
    """Manages intent priority hierarchy for conflict resolution."""

    def __init__(self):
        """Initialize intent hierarchy."""
        self.priority_map = INTENT_PRIORITY_MAP

    def get_priority(self, intent: str) -> IntentPriority:
        """Get priority for an intent.

        Args:
            intent: Intent name

        Returns:
            Priority level (defaults to P4 if not found)
        """
        return self.priority_map.get(intent, IntentPriority.P4_FALLBACK)

    def assign_priority(
        self,
        intent: str,
        confidence: float,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> IntentClassification:
        """Assign priority to an intent classification.

        Args:
            intent: Intent name
            confidence: Confidence score (0.0 to 1.0)
            parameters: Optional extracted parameters

        Returns:
            IntentClassification with assigned priority
        """
        priority = self.get_priority(intent)

        return IntentClassification(
            intent=intent,
            confidence=confidence,
            priority=priority,
            parameters=parameters or {},
            conflicts_with_session=False,  # Will be set by ConfidenceAdjuster
        )

    def compare_priorities(
        self, intent1: IntentClassification, intent2: IntentClassification
    ) -> int:
        """Compare priorities of two intents.

        Args:
            intent1: First intent
            intent2: Second intent

        Returns:
            -1 if intent1 has higher priority, 1 if intent2 has higher priority, 0 if equal
        """
        priority_order = [
            IntentPriority.P0_CRITICAL,
            IntentPriority.P1_EXPLICIT,
            IntentPriority.P2_IMPLICIT,
            IntentPriority.P3_GENERAL,
            IntentPriority.P4_FALLBACK,
        ]

        idx1 = priority_order.index(intent1.priority)
        idx2 = priority_order.index(intent2.priority)

        if idx1 < idx2:
            return -1  # intent1 higher priority
        elif idx1 > idx2:
            return 1  # intent2 higher priority
        else:
            return 0  # equal priority


# ============================================================================
# Confidence Adjuster
# ============================================================================


class ConfidenceAdjuster:
    """Adjusts confidence scores based on session context."""

    CONFLICT_PENALTY = 0.30  # 30% confidence penalty for conflicts

    def __init__(self):
        """Initialize confidence adjuster."""
        pass

    def detect_conflict(
        self, intent: IntentClassification, context: Optional[FSMContext]
    ) -> bool:
        """Detect if intent conflicts with active session.

        Args:
            intent: Intent to check
            context: Current FSM context (None if no active session)

        Returns:
            True if conflict detected, False otherwise
        """
        if not context:
            return False

        # No session active (IDLE state) - no conflict
        current_state = (
            context.current_state
            if isinstance(context.current_state, str)
            else context.current_state.value
        )
        if current_state == "idle":
            return False

        # Check if intent would disrupt active session
        # P0 commands never conflict (cancel/stop/help)
        if intent.priority == IntentPriority.P0_CRITICAL:
            return False

        # Starting new update while one is active
        if intent.intent == "progress_update" and context.task_id:
            return True

        # Creating incident during update (ambiguous)
        if intent.intent == "create_incident" and context.task_id:
            return True

        # Switching tasks during active update
        if intent.intent == "switch_task" and context.task_id:
            return True

        return False

    def adjust_confidence(
        self, intent: IntentClassification, context: Optional[FSMContext]
    ) -> IntentClassification:
        """Adjust confidence score based on session context.

        Args:
            intent: Intent classification
            context: Current FSM context

        Returns:
            Intent with adjusted confidence
        """
        has_conflict = self.detect_conflict(intent, context)

        if has_conflict:
            # Apply confidence penalty
            adjusted_confidence = max(0.0, intent.confidence - self.CONFLICT_PENALTY)

            logger.info(
                f"Conflict detected: {intent.intent}",
                original_confidence=intent.confidence,
                adjusted_confidence=adjusted_confidence,
                user_id=context.user_id if context else None,
            )

            # Update intent with adjusted confidence
            intent.confidence = adjusted_confidence
            intent.conflicts_with_session = True

        return intent


# ============================================================================
# Conflict Resolver
# ============================================================================


class ConflictResolver:
    """Resolves conflicts between multiple intent classifications."""

    def __init__(
        self, hierarchy: IntentHierarchy, confidence_adjuster: ConfidenceAdjuster
    ):
        """Initialize conflict resolver.

        Args:
            hierarchy: Intent hierarchy for priority comparison
            confidence_adjuster: Confidence adjuster for session awareness
        """
        self.hierarchy = hierarchy
        self.confidence_adjuster = confidence_adjuster

    def resolve(
        self,
        intents: List[IntentClassification],
        context: Optional[FSMContext],
        confidence_threshold: float = 0.70,
    ) -> Tuple[Optional[IntentClassification], bool]:
        """Resolve conflicts between multiple intents.

        Strategy:
        1. Adjust confidence scores based on session context
        2. Filter intents below threshold
        3. Sort by priority, then confidence
        4. If top intent has conflict, request clarification
        5. Return winner or None if clarification needed

        Args:
            intents: List of intent classifications
            context: Current FSM context
            confidence_threshold: Minimum confidence threshold

        Returns:
            Tuple of (winning_intent or None, needs_clarification)
        """
        if not intents:
            logger.warning("No intents to resolve")
            return None, False

        # Step 1: Adjust confidence scores
        adjusted_intents = [
            self.confidence_adjuster.adjust_confidence(intent, context)
            for intent in intents
        ]

        # Step 2: Filter by confidence threshold
        valid_intents = [
            intent
            for intent in adjusted_intents
            if intent.confidence >= confidence_threshold
        ]

        if not valid_intents:
            logger.info(
                f"All intents below threshold ({confidence_threshold})",
                user_id=context.user_id if context else None,
            )
            return None, True  # Need clarification

        # Step 3: Sort by priority (higher priority first), then confidence
        sorted_intents = sorted(
            valid_intents,
            key=lambda i: (
                list(IntentPriority).index(i.priority),  # Lower index = higher priority
                -i.confidence,  # Higher confidence first (negative for descending)
            ),
        )

        winner = sorted_intents[0]

        # Step 4: Check if winner has conflict
        if winner.conflicts_with_session:
            logger.info(
                f"Winner has conflict, requesting clarification: {winner.intent}",
                confidence=winner.confidence,
                user_id=context.user_id if context else None,
            )
            return None, True  # Need clarification

        # Step 5: Check if there are multiple high-confidence intents (ambiguous)
        if len(sorted_intents) > 1:
            second = sorted_intents[1]
            confidence_gap = winner.confidence - second.confidence

            # Only request clarification if priorities are same AND confidence gap is small
            # If priorities differ (e.g., P0 vs P1), priority resolves the ambiguity
            if winner.priority == second.priority and confidence_gap < 0.15:
                logger.info(
                    f"Ambiguous: {winner.intent} vs {second.intent}",
                    gap=confidence_gap,
                    user_id=context.user_id if context else None,
                )
                return None, True  # Need clarification

        logger.info(
            f"Resolved intent: {winner.intent}",
            confidence=winner.confidence,
            priority=winner.priority,
            user_id=context.user_id if context else None,
        )

        return winner, False


# ============================================================================
# IntentRouter - Main Interface
# ============================================================================


class IntentRouter:
    """Main interface for intent routing with conflict resolution."""

    def __init__(self):
        """Initialize intent router."""
        self.hierarchy = IntentHierarchy()
        self.confidence_adjuster = ConfidenceAdjuster()
        self.conflict_resolver = ConflictResolver(
            self.hierarchy, self.confidence_adjuster
        )

    def route_intent(
        self,
        intent: str,
        confidence: float,
        context: Optional[FSMContext],
        parameters: Optional[Dict[str, Any]] = None,
        confidence_threshold: float = 0.70,
    ) -> Tuple[Optional[IntentClassification], bool]:
        """Route a single intent with session awareness.

        Args:
            intent: Intent name
            confidence: Confidence score
            context: Current FSM context
            parameters: Optional extracted parameters
            confidence_threshold: Minimum confidence threshold

        Returns:
            Tuple of (intent_classification or None, needs_clarification)
        """
        # Assign priority
        intent_classification = self.hierarchy.assign_priority(
            intent=intent, confidence=confidence, parameters=parameters
        )

        # Resolve (single intent still goes through conflict resolution)
        return self.conflict_resolver.resolve(
            intents=[intent_classification],
            context=context,
            confidence_threshold=confidence_threshold,
        )

    def route_multiple_intents(
        self,
        intents: List[Dict[str, Any]],
        context: Optional[FSMContext],
        confidence_threshold: float = 0.70,
    ) -> Tuple[Optional[IntentClassification], bool]:
        """Route multiple intents with conflict resolution.

        Args:
            intents: List of intent dicts with 'intent', 'confidence', 'parameters'
            context: Current FSM context
            confidence_threshold: Minimum confidence threshold

        Returns:
            Tuple of (winning_intent or None, needs_clarification)
        """
        # Assign priorities to all intents
        intent_classifications = [
            self.hierarchy.assign_priority(
                intent=item["intent"],
                confidence=item["confidence"],
                parameters=item.get("parameters"),
            )
            for item in intents
        ]

        # Resolve conflicts
        return self.conflict_resolver.resolve(
            intents=intent_classifications,
            context=context,
            confidence_threshold=confidence_threshold,
        )
