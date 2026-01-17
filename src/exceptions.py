"""Custom exceptions for structured error handling and propagation.

This module provides domain-specific exceptions with error codes for
proper error context propagation throughout the application.
"""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    """Standard error codes for categorizing failures."""

    # User/Authentication errors (1xxx)
    USER_NOT_FOUND = "USER_1001"
    USER_UNAUTHORIZED = "USER_1002"
    INVALID_PHONE_NUMBER = "USER_1003"

    # Project/Resource errors (2xxx)
    PROJECT_NOT_FOUND = "PROJECT_2001"
    NO_PROJECTS = "PROJECT_2002"
    PROJECT_ACCESS_DENIED = "PROJECT_2003"
    TASK_NOT_FOUND = "PROJECT_2004"
    DOCUMENT_NOT_FOUND = "PROJECT_2005"

    # Integration errors (3xxx)
    DATABASE_ERROR = "INTEGRATION_3001"
    PLANRADAR_API_ERROR = "INTEGRATION_3002"
    TWILIO_ERROR = "INTEGRATION_3003"
    TRANSLATION_ERROR = "INTEGRATION_3004"
    TRANSCRIPTION_ERROR = "INTEGRATION_3005"

    # Business logic errors (4xxx)
    INVALID_INTENT = "LOGIC_4001"
    HANDLER_NOT_FOUND = "LOGIC_4002"
    VALIDATION_ERROR = "LOGIC_4003"
    SESSION_ERROR = "LOGIC_4004"

    # System errors (5xxx)
    INTERNAL_ERROR = "SYSTEM_5001"
    TIMEOUT_ERROR = "SYSTEM_5002"
    CONFIGURATION_ERROR = "SYSTEM_5003"
    AGENT_ERROR = "SYSTEM_5004"


class LumieraException(Exception):
    """Base exception for all Lumiera application errors.

    All custom exceptions should inherit from this to enable
    structured error handling and propagation.
    """

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        """Initialize exception with structured error information.

        Args:
            message: Technical error message (for logging)
            error_code: Standard error code for categorization
            user_message: User-friendly message (for display)
            details: Additional error context
            original_exception: Original exception if wrapping
        """
        super().__init__(message)
        self.error_code = error_code
        self.user_message = user_message or "Une erreur s'est produite"
        self.details = details or {}
        self.original_exception = original_exception

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "success": False,
            "error_code": self.error_code.value,
            "message": str(self),
            "user_message": self.user_message,
            "details": self.details,
        }


class UserNotFoundException(LumieraException):
    """Raised when user is not found in database."""

    def __init__(self, user_id: str, **kwargs):
        super().__init__(
            message=f"User not found: {user_id}",
            error_code=ErrorCode.USER_NOT_FOUND,
            user_message="Utilisateur non trouvé",
            details={"user_id": user_id},
            **kwargs,
        )


class ProjectNotFoundException(LumieraException):
    """Raised when project is not found or user has no access."""

    def __init__(
        self, project_id: Optional[str] = None, user_id: Optional[str] = None, **kwargs
    ):
        super().__init__(
            message=(
                f"Project not found: {project_id}"
                if project_id
                else "No projects found"
            ),
            error_code=(
                ErrorCode.PROJECT_NOT_FOUND if project_id else ErrorCode.NO_PROJECTS
            ),
            user_message="Projet non trouvé" if project_id else "Aucun projet trouvé",
            details={"project_id": project_id, "user_id": user_id},
            **kwargs,
        )


class IntegrationException(LumieraException):
    """Raised when external integration fails."""

    def __init__(self, service: str, operation: str, **kwargs):
        super().__init__(
            message=f"{service} integration error during {operation}",
            error_code=ErrorCode.DATABASE_ERROR,  # Will be overridden by specific integrations
            user_message=f"Erreur de connexion avec {service}",
            details={"service": service, "operation": operation},
            **kwargs,
        )


class DatabaseException(IntegrationException):
    """Raised when database operation fails."""

    def __init__(self, operation: str, **kwargs):
        kwargs["error_code"] = ErrorCode.DATABASE_ERROR
        super().__init__(service="Database", operation=operation, **kwargs)


class PlanRadarException(IntegrationException):
    """Raised when PlanRadar API call fails."""

    def __init__(self, operation: str, **kwargs):
        kwargs["error_code"] = ErrorCode.PLANRADAR_API_ERROR
        super().__init__(service="PlanRadar", operation=operation, **kwargs)


class HandlerNotFoundException(LumieraException):
    """Raised when no handler is found for intent."""

    def __init__(self, intent: str, **kwargs):
        super().__init__(
            message=f"No handler found for intent: {intent}",
            error_code=ErrorCode.HANDLER_NOT_FOUND,
            user_message="Action non reconnue",
            details={"intent": intent},
            **kwargs,
        )


class ValidationException(LumieraException):
    """Raised when input validation fails."""

    def __init__(self, field: str, reason: str, **kwargs):
        super().__init__(
            message=f"Validation error for {field}: {reason}",
            error_code=ErrorCode.VALIDATION_ERROR,
            user_message=f"Données invalides: {field}",
            details={"field": field, "reason": reason},
            **kwargs,
        )


class AgentExecutionException(LumieraException):
    """Raised when agent execution fails."""

    def __init__(self, stage: str, **kwargs):
        super().__init__(
            message=f"Agent execution failed at stage: {stage}",
            error_code=ErrorCode.AGENT_ERROR,
            user_message="Erreur de traitement du message",
            details={"stage": stage},
            **kwargs,
        )
