from __future__ import annotations

import argparse

from echolex.ingestion.service import ingest_pdf


def main() -> None:
    """Parse ingestion CLI arguments and index the requested PDF."""
    parser = argparse.ArgumentParser(description="Index a PDF into local Qdrant.")
    parser.add_argument("pdf", help="Path to a PDF file")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help=(
            "Delete and recreate the collection first. "
            "Recommended for the single-document starter."
        ),
    )
    args = parser.parse_args()
    ingest_pdf(args.pdf, recreate=args.recreate)
