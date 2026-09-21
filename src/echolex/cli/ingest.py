from __future__ import annotations

import argparse

from echolex.core.config import Settings
from echolex.core.logging import configure_logging
from echolex.ingestion.service import ingest_pdf


def main() -> None:
    """Parse ingestion CLI arguments and index the requested PDF."""
    settings = Settings.from_env()
    configure_logging(settings)

    parser = argparse.ArgumentParser(description="Index a PDF into Qdrant.")
    parser.add_argument("pdf", help="Path to a PDF file")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the collection before indexing.",
    )
    args = parser.parse_args()
    ingest_pdf(args.pdf, recreate=args.recreate)
