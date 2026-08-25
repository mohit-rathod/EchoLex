"""Document ingestion feature.

The public facade intentionally avoids importing heavyweight embedding/vector dependencies
until ingestion is actually invoked. This keeps document chunking independently importable.
"""

from __future__ import annotations

from pathlib import Path


def ingest_pdf(pdf_path: str | Path, *, recreate: bool = False) -> int:
    """Delegate to the ingestion service without eager infrastructure imports."""
    from echolex.ingestion.service import ingest_pdf as _ingest_pdf

    return _ingest_pdf(pdf_path, recreate=recreate)


def main() -> None:
    """Backward-compatible CLI entrypoint."""
    from echolex.cli.ingest import main as cli_main

    cli_main()


__all__ = ["ingest_pdf", "main"]
