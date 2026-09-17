"""
utils/logging_config.py
------------------------
Configures application-wide logging. Writes to both console and a
rotating log file under logs/. Never logs secrets: callers are
responsible for not passing API keys, passwords, or full connection
strings into log messages (see helpers.mask_secret for redaction).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from config import settings

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotently configure the root logger for the application."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    os.makedirs(_LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.app.log_level.upper())
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
