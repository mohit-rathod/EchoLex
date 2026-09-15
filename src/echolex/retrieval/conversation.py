from __future__ import annotations

import re
from dataclasses import dataclass

from echolex.domain.models import RetrievedChunk


_REUSE_PATTERNS = (
    re.compile(
        r"\b(explain|simplify|rephrase|paraphrase|summarize|summarise|clarify)"
        r"\s+(that|this|it)\b"
    ),
    re.compile(r"\b(say|repeat)\s+(that|this|it)\s+again\b"),
    re.compile(r"^(make it )?(shorter|simpler|more concise)$"),
    re.compile(r"^(in simple words|in simpler terms)$"),
    re.compile(r"\bwhat do you mean by (that|this)\b"),
)

_CONTEXTUAL_FOLLOW_UP_PATTERNS = (
    re.compile(r"^(and|also|then|so|but)\b"),
    re.compile(r"\b(it|its|that|this|those|these|they|them|former|latter)\b"),
    re.compile(r"^(what|why|how|which|when|where)\s+about\b"),
    re.compile(r"^(why|how so|which one|what else|anything else)\??$"),
)


@dataclass(frozen=True)
class EvidenceMemory:
    """Evidence retained from the most recent grounded document turn."""

    user_query: str = ""
    chunks: tuple[RetrievedChunk, ...] = ()

    @property
    def has_evidence(self) -> bool:
        return bool(self.chunks)


def should_reuse_evidence(query: str, memory: EvidenceMemory) -> bool:
    """Reuse prior evidence only for explicit transformations of the previous answer."""
    if not memory.has_evidence:
        return False

    normalized = " ".join(query.lower().split())
    return any(pattern.search(normalized) for pattern in _REUSE_PATTERNS)


def build_retrieval_query(query: str, memory: EvidenceMemory) -> str:
    """Resolve short/referential follow-ups by carrying forward the previous topic."""
    clean_query = " ".join(query.split())
    if not memory.user_query:
        return clean_query

    normalized = clean_query.lower()
    is_contextual = any(
        pattern.search(normalized)
        for pattern in _CONTEXTUAL_FOLLOW_UP_PATTERNS
    )

    if not is_contextual:
        return clean_query

    return (
        f"Previous topic: {memory.user_query}\n"
        f"Follow-up question: {clean_query}"
    )


def source_announcement(
    chunks: list[RetrievedChunk] | tuple[RetrievedChunk, ...],
) -> str:
    """Build the exact page announcement that the model must speak before its answer."""
    pages = sorted({chunk.page for chunk in chunks if chunk.page > 0})

    if not pages:
        return "Retrieved from no relevant page."

    if len(pages) == 1:
        return f"Retrieved from page {pages[0]}."

    if len(pages) == 2:
        return f"Retrieved from pages {pages[0]} and {pages[1]}."

    joined = ", ".join(str(page) for page in pages[:-1])
    return f"Retrieved from pages {joined}, and {pages[-1]}."