"""
Centralized logging configuration with file rotation.

Logs are written to:
- Console: INFO level
- File: DEBUG level with 10-day retention
- Separate error log for errors only
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from config import config


def setup_logging(log_dir: Path | None = None) -> None:
    """
    Configure application logging with rotation.

    Args:
        log_dir: Directory for log files (defaults to data_dir/logs)
    """
    if log_dir is None:
        log_dir = config.data_dir / "logs"

    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Format: timestamp, logger name, level, message
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)

    # ========== Console Handler ==========
    # INFO level, only to stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ========== Main File Handler ==========
    # DEBUG level, rotates daily, keeps 10 days
    main_log_file = log_dir / "megpt.log"
    main_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(main_log_file),
        when="midnight",  # Rotate at midnight
        interval=1,  # Every day
        backupCount=10,  # Keep 10 days of logs
        encoding="utf-8",
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(formatter)
    main_handler.suffix = "%Y-%m-%d"  # Date suffix for rotated files
    root_logger.addHandler(main_handler)

    # ========== Error File Handler ==========
    # ERROR level only, rotates daily, keeps 10 days
    error_log_file = log_dir / "error.log"
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(error_log_file),
        when="midnight",
        interval=1,
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.suffix = "%Y-%m-%d"
    root_logger.addHandler(error_handler)

    # Silence noisy third-party loggers
    _configure_third_party_loggers()

    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Logs: {main_log_file}")
    logger.info(f"Error log: {error_log_file}")
    logger.info(f"Retention: 10 days")


def _configure_third_party_loggers() -> None:
    """Set appropriate log levels for noisy third-party packages."""
    # These are too noisy
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)


# Auto-setup on import
setup_logging()
