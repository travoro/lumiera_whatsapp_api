"""Logging configuration using loguru.

Best Practices:
- Single source of truth: All logs go to `logs/app.log` with automatic rotation
- Size-based rotation: 50 MB max per file (prevents huge files)
- Time-based backup: Keep 30 days of logs
- Separate error logs: Errors also go to dedicated file for easy debugging
- Compression: Old logs are compressed to save space
"""

import sys
from pathlib import Path

from loguru import logger

from src.config import settings


def setup_logger():
    """Configure logger with best practices for production use.

    Log Files:
    - logs/app.log: Main application log (rotates at 50MB, keeps 30 days)
    - logs/errors.log: Error-only log (rotates at 10MB, keeps 90 days)
    - Console: Colored output for development
    """
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    # Remove default handler
    logger.remove()

    # Custom format with timestamp, level, location, and message
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console handler - Always enabled for monitoring
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )

    # Main application log file - Single source of truth
    # Rotates when file reaches 50MB OR at midnight (whichever comes first)
    logger.add(
        "logs/app.log",
        format=log_format,
        level="INFO",
        rotation="50 MB",  # Rotate when file reaches 50MB
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress rotated logs to save space
        enqueue=True,  # Async logging for better performance
        backtrace=True,  # Include full backtrace on errors
        diagnose=True,  # Add diagnosis info to exceptions
    )

    # Error-only log file - For quick debugging
    logger.add(
        "logs/errors.log",
        format=log_format,
        level="ERROR",
        rotation="10 MB",  # Smaller rotation for errors
        retention="90 days",  # Keep errors longer
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    return logger


# Initialize logger
log = setup_logger()
