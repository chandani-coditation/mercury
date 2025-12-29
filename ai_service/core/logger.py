"""Standardized logging configuration for NOC Agent AI."""

import logging
import sys
import os
from datetime import datetime
from typing import Optional
from logging.handlers import TimedRotatingFileHandler


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    log_dir: Optional[str] = None,
    service_name: str = "ai_service",
) -> logging.Logger:
    """
    Set up standardized logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file (if None, auto-generates daily log file in log_dir)
        log_format: Optional custom format string
        log_dir: Directory for log files (default: ./logs)
        service_name: Service name for log file naming (default: ai_service)

    Returns:
        Configured logger instance
    """
    # Default format: timestamp, level, module, message
    if log_format is None:
        log_format = (
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
        )

    # Create formatter
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler - daily rotation
    if log_file is None:
        # Auto-generate log file path with date
        if log_dir is None:
            log_dir = os.path.join(os.getcwd(), "logs")

        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)

        # Generate log file name with date: ai_service_2025-11-12.log
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"{service_name}_{date_str}.log")

    # Use TimedRotatingFileHandler for daily rotation
    # Rotates at midnight, keeps 30 days of logs
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,  # Keep 30 days of logs
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"  # Suffix format for rotated files
    logger.addHandler(file_handler)

    # Set levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
