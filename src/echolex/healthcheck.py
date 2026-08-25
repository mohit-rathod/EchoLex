"""Backward-compatible healthcheck entrypoint."""

from echolex.cli.health import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
