from __future__ import annotations

import logging
from logging.config import dictConfig

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {
                "level": settings.app_log_level.upper(),
                "handlers": ["console"],
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
