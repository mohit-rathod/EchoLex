from __future__ import annotations

import sys

from loguru import logger

from echolex.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure one process-wide Loguru sink from validated settings."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        serialize=settings.log_json,
        backtrace=False,
        diagnose=False,
        enqueue=True,
    )
