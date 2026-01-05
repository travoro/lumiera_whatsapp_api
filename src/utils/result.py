"""Result wrapper for operations with structured error handling.

Provides a consistent way to return success/failure results with
proper error context throughout the application.
"""
from typing import Generic, TypeVar, Optional, Dict, Any, Union
from dataclasses import dataclass
from src.exceptions import LumieraException, ErrorCode

T = TypeVar('T')


@dataclass
class Result(Generic[T]):
    """Result wrapper for operations that can succeed or fail.

    Use this instead of returning None or raising exceptions directly
    to enable proper error propagation and handling.
    """

    success: bool
    data: Optional[T] = None
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    user_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    @staticmethod
    def ok(data: T) -> 'Result[T]':
        """Create a successful result.

        Args:
            data: The success data

        Returns:
            Result with success=True
        """
        return Result(success=True, data=data)

    @staticmethod
    def fail(
        error_code: ErrorCode,
        error_message: str,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> 'Result[T]':
        """Create a failed result.

        Args:
            error_code: Standard error code
            error_message: Technical error message
            user_message: User-friendly message
            details: Additional error context

        Returns:
            Result with success=False
        """
        return Result(
            success=False,
            data=None,
            error_code=error_code,
            error_message=error_message,
            user_message=user_message or "Une erreur s'est produite",
            details=details or {}
        )

    @staticmethod
    def from_exception(exc: Union[LumieraException, Exception]) -> 'Result[T]':
        """Create a failed result from an exception.

        Args:
            exc: Exception to convert

        Returns:
            Result with error information from exception
        """
        if isinstance(exc, LumieraException):
            return Result(
                success=False,
                data=None,
                error_code=exc.error_code,
                error_message=str(exc),
                user_message=exc.user_message,
                details=exc.details
            )
        else:
            return Result(
                success=False,
                data=None,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_message=str(exc),
                user_message="Une erreur interne s'est produite",
                details={"exception_type": type(exc).__name__}
            )

    def unwrap(self) -> T:
        """Get data or raise exception if failed.

        Returns:
            The data if successful

        Raises:
            ValueError: If result is a failure
        """
        if not self.success:
            raise ValueError(f"Cannot unwrap failed result: {self.error_message}")
        return self.data

    def unwrap_or(self, default: T) -> T:
        """Get data or return default if failed.

        Args:
            default: Default value to return on failure

        Returns:
            Data if successful, default otherwise
        """
        return self.data if self.success else default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses.

        Returns:
            Dictionary representation
        """
        if self.success:
            return {
                "success": True,
                "data": self.data
            }
        else:
            return {
                "success": False,
                "error_code": self.error_code.value if self.error_code else None,
                "error_message": self.error_message,
                "user_message": self.user_message,
                "details": self.details
            }
