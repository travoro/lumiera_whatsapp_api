"""Logging configuration using loguru."""
import sys
from loguru import logger
from src.config import settings


def setup_logger():
    """Configure logger with appropriate settings."""
    # Remove default handler
    logger.remove()

    # Add console handler with custom format
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )

    # Add file handler for production
    if settings.is_production:
        logger.add(
            "logs/lumiera_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            level="INFO",
            format=log_format,
        )

    # Add error file handler
    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="90 days",
        level="ERROR",
        format=log_format,
    )

    return logger


# Initialize logger
log = setup_logger()
