"""Retry logic and error handling with Tenacity."""

import asyncio
import logging
from typing import Any, Callable

import httpx
from anthropic import APIConnectionError, APIError, RateLimitError
from openai import APIError as OpenAIAPIError
from openai import RateLimitError as OpenAIRateLimitError
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.utils.logger import log

# === API Call Retry Decorators ===


def retry_on_api_error(max_attempts: int = 3):
    """Retry decorator for general API errors with exponential backoff.

    Use for: Claude API, OpenAI API, external service calls

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (
                APIError,
                APIConnectionError,
                OpenAIAPIError,
                httpx.HTTPError,
                httpx.TimeoutException,
            )
        ),
        before_sleep=before_sleep_log(log, logging.WARNING),
        after=after_log(log, logging.INFO),
        reraise=True,
    )


def retry_on_rate_limit(max_attempts: int = 5):
    """Retry decorator specifically for rate limit errors with longer backoff.

    Use for: Claude/OpenAI rate limits (429 errors)

    Args:
        max_attempts: Maximum number of retry attempts (default: 5)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(
            (
                RateLimitError,
                OpenAIRateLimitError,
            )
        ),
        before_sleep=before_sleep_log(log, logging.WARNING),
        after=after_log(log, logging.INFO),
        reraise=True,
    )


def retry_on_network_error(max_attempts: int = 3):
    """Retry decorator for network/connection errors.

    Use for: Database queries, HTTP requests, Twilio API

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (
                httpx.ConnectError,
                httpx.TimeoutException,
                ConnectionError,
                TimeoutError,
            )
        ),
        before_sleep=before_sleep_log(log, logging.WARNING),
        after=after_log(log, logging.INFO),
        reraise=True,
    )


# === Graceful Degradation Helpers ===


async def with_fallback(
    primary_fn: Callable,
    fallback_fn: Callable,
    fallback_on: tuple = (Exception,),
    *args,
    **kwargs,
) -> Any:
    """Execute primary function, fall back to fallback function on error.

    Args:
        primary_fn: Primary function to try first
        fallback_fn: Fallback function if primary fails
        fallback_on: Tuple of exception types to catch
        *args, **kwargs: Arguments to pass to functions

    Returns:
        Result from primary or fallback function
    """
    try:
        if callable(primary_fn):
            return (
                await primary_fn(*args, **kwargs)
                if asyncio.iscoroutinefunction(primary_fn)
                else primary_fn(*args, **kwargs)
            )
        return primary_fn
    except fallback_on as e:
        log.warning(f"Primary function failed: {e}. Using fallback.")
        try:
            if callable(fallback_fn):
                return (
                    await fallback_fn(*args, **kwargs)
                    if asyncio.iscoroutinefunction(fallback_fn)
                    else fallback_fn(*args, **kwargs)
                )
            return fallback_fn
        except Exception as fallback_error:
            log.error(f"Fallback also failed: {fallback_error}")
            raise


async def with_default(fn: Callable, default: Any, *args, **kwargs) -> Any:
    """Execute function, return default value on any error.

    Args:
        fn: Function to execute
        default: Default value to return on error
        *args, **kwargs: Arguments to pass to function

    Returns:
        Function result or default value
    """
    try:
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return fn(*args, **kwargs)
    except Exception as e:
        log.warning(f"Function failed, returning default: {e}")
        return default


# === Error Context Manager ===


class ErrorContext:
    """Context manager for standardized error handling and logging."""

    def __init__(self, operation: str, user_id: str = None, critical: bool = False):
        """Initialize error context.

        Args:
            operation: Description of operation being performed
            user_id: Optional user ID for context
            critical: If True, re-raise errors. If False, suppress and log.
        """
        self.operation = operation
        self.user_id = user_id
        self.critical = critical

    async def __aenter__(self):
        log.info(
            f"Starting: {self.operation}"
            + (f" (user: {self.user_id})" if self.user_id else "")
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            log.info(f"Completed: {self.operation}")
            return True

        # Log error with context
        error_msg = f"Error in {self.operation}: {exc_val}"
        if self.user_id:
            error_msg += f" (user: {self.user_id})"

        if self.critical:
            log.error(error_msg)
            return False  # Re-raise
        else:
            log.warning(error_msg)
            return True  # Suppress


# Import asyncio for coroutine checks
