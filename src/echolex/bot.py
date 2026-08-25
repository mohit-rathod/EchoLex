from __future__ import annotations

import sys

from loguru import logger

from echolex.core.config import Settings
from echolex.voice.pipeline import bot, run_bot

__all__ = ["bot", "main", "run_bot"]


def main() -> None:
    """Delegate execution to Pipecat's runner CLI."""
    from pipecat.runner.run import main as pipecat_main

    pipecat_main()


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level=Settings.from_env().log_level)
    main()
