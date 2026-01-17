"""Structured logging utility for FSM operations with correlation IDs and JSON formatting.

This module provides structured logging capabilities specifically designed for
tracking FSM (Finite State Machine) operations, state transitions, and related events.
"""

import json
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

# Context variable for correlation ID (thread-safe)
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


class StructuredLogger:
    """Structured logger with JSON formatting and correlation ID support."""

    def __init__(self, component: str):
        """Initialize structured logger for a component.

        Args:
            component: Name of the component (e.g., "fsm.core", "fsm.routing")
        """
        self.component = component

    def _format_structured_log(
        self, level: str, message: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Format log entry as structured JSON.

        Args:
            level: Log level (INFO, WARNING, ERROR, etc.)
            message: Log message
            **kwargs: Additional structured data

        Returns:
            Structured log entry as dictionary
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "component": self.component,
            "message": message,
            "correlation_id": correlation_id_var.get(),
        }

        # Add any additional structured data
        if kwargs:
            log_entry["data"] = kwargs

        return log_entry

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Internal logging method.

        Args:
            level: Log level
            message: Log message
            **kwargs: Additional structured data
        """
        structured_data = self._format_structured_log(level, message, **kwargs)
        log_message = f"[FSM] {message} | {json.dumps(structured_data, default=str)}"

        # Use loguru logger with appropriate level
        if level == "DEBUG":
            logger.debug(log_message)
        elif level == "INFO":
            logger.info(log_message)
        elif level == "WARNING":
            logger.warning(log_message)
        elif level == "ERROR":
            logger.error(log_message)
        elif level == "CRITICAL":
            logger.critical(log_message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with structured data."""
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message with structured data."""
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with structured data."""
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with structured data."""
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message with structured data."""
        self._log("CRITICAL", message, **kwargs)

    def log_transition(
        self,
        user_id: str,
        from_state: str,
        to_state: str,
        trigger: str,
        success: bool = True,
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Log FSM state transition with structured data.

        Args:
            user_id: User identifier
            from_state: Source state
            to_state: Target state
            trigger: What triggered the transition
            success: Whether transition succeeded
            error: Error message if transition failed
            **kwargs: Additional context
        """
        self.info(
            f"State transition: {from_state} -> {to_state}",
            user_id=user_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            success=success,
            error=error,
            **kwargs,
        )


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for current context.

    Args:
        correlation_id: Optional correlation ID. If None, generates new UUID.

    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID from context.

    Returns:
        Current correlation ID or None if not set
    """
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    correlation_id_var.set(None)


def get_structured_logger(component: str) -> StructuredLogger:
    """Factory function to create a structured logger for a component.

    Args:
        component: Name of the component

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(component)
