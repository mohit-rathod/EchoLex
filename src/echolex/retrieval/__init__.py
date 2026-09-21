"""Semantic retrieval feature with lazy infrastructure imports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from echolex.domain.models import RetrievedChunk

if TYPE_CHECKING:
    from echolex.retrieval.service import DocumentRetriever

__all__ = ["BGE_QUERY_PROMPT", "DocumentRetriever", "RetrievedChunk", "get_retriever"]


def __getattr__(name: str) -> Any:
    if name in {"BGE_QUERY_PROMPT", "DocumentRetriever", "get_retriever"}:
        from echolex.retrieval import service

        return getattr(service, name)
    raise AttributeError(name)
