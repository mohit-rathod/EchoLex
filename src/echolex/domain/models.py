from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """A bounded segment of extracted document text with page provenance."""

    text: str
    page: int
    chunk_index: int
    source: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A document segment returned by semantic retrieval."""

    text: str
    page: int
    source: str
    score: float
