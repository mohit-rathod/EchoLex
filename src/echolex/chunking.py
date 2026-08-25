"""Backward-compatible chunking import path."""

from echolex.domain.models import TextChunk
from echolex.ingestion.chunking import chunk_page_text, extract_pdf_chunks, normalize_text

__all__ = ["TextChunk", "chunk_page_text", "extract_pdf_chunks", "normalize_text"]
