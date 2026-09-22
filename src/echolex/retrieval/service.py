from __future__ import annotations

import atexit
from pathlib import Path
from threading import Lock, RLock

from loguru import logger
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from echolex.core.config import Settings
from echolex.domain.models import RetrievedChunk

BGE_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "


class DocumentRetriever:
    """Thread-safe synchronous semantic retriever for the async voice pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings
        logger.info(
            "embedding_model_loading model={} device={}",
            settings.embedding_model,
            settings.embedding_device,
        )
        self.encoder = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        self.client = self._build_client(settings)
        self._query_lock = RLock()
        self._closed = False

    @staticmethod
    def _build_client(settings: Settings) -> QdrantClient:
        if settings.qdrant_url:
            logger.info("qdrant_remote url={}", settings.qdrant_url)
            return QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=settings.qdrant_timeout_seconds,
            )

        path = Path(settings.qdrant_path)
        path.mkdir(parents=True, exist_ok=True)
        logger.warning("qdrant_embedded path={} intended_for=development", path)
        return QdrantClient(path=str(path))

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        if self._closed:
            raise RuntimeError("DocumentRetriever is closed")

        query = " ".join(query.split())
        if not query:
            return []

        limit = self.settings.rag_top_k if top_k is None else top_k
        if limit <= 0:
            raise ValueError("top_k must be greater than 0")

        with self._query_lock:
            vector = self.encoder.encode_query(
                query,
                prompt="Represent this sentence for searching relevant passages:",
                normalize_embeddings=True,
            ).tolist()
            result = self.client.query_points(
                collection_name=self.settings.qdrant_collection,
                query=vector,
                limit=limit,
                with_payload=True,
            )

        chunks: list[RetrievedChunk] = []
        for point in result.points:
            score = float(point.score)
            if score < self.settings.rag_score_threshold:
                continue
            payload = point.payload or {}
            text = str(payload.get("text", "")).strip()
            if not text:
                continue
            chunks.append(
                RetrievedChunk(
                    text=text,
                    page=int(payload.get("page", 0) or 0),
                    source=str(payload.get("source", "document")),
                    score=score,
                    chunk_id=str(point.id),
                    chunk_index=int(payload.get("chunk_index", 0) or 0),
                    document_sha256=str(payload.get("document_sha256", "")),
                )
            )
        return chunks

    def close(self) -> None:
        if not self._closed:
            self.client.close()
            self._closed = True

    def __enter__(self) -> "DocumentRetriever":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


_RETRIEVER: DocumentRetriever | None = None
_RETRIEVER_LOCK = Lock()


def get_retriever() -> DocumentRetriever:
    """Return the process-local retriever, initialized exactly once."""
    global _RETRIEVER
    if _RETRIEVER is not None:
        return _RETRIEVER

    with _RETRIEVER_LOCK:
        if _RETRIEVER is None:
            _RETRIEVER = DocumentRetriever(Settings.from_env())
        return _RETRIEVER


def close_retriever() -> None:
    """Close and clear the cached retriever, primarily for shutdown and tests."""
    global _RETRIEVER
    with _RETRIEVER_LOCK:
        if _RETRIEVER is not None:
            _RETRIEVER.close()
            _RETRIEVER = None


atexit.register(close_retriever)
