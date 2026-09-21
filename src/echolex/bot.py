from __future__ import annotations

import sys

from echolex.core.config import Settings
from echolex.core.logging import configure_logging
from echolex.voice.pipeline import bot, run_bot

__all__ = ["bot", "main", "run_bot"]


def _register_bot_on_main_module() -> None:
    """Expose bot where Pipecat's runner expects to find it."""
    main_module = sys.modules.get("__main__")

    if main_module is None:
        raise RuntimeError("Python __main__ module is unavailable")

    setattr(main_module, "bot", bot)


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings)

    # Pipecat discovers bot() from __main__.
    _register_bot_on_main_module()

    from pipecat.runner.run import main as pipecat_main

    pipecat_main()


if __name__ == "__main__":
    main()