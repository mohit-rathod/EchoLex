from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from loguru import logger
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from echolex.core.config import Settings
from echolex.domain.models import RetrievedChunk


BGE_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "


class DocumentRetriever:
    """Synchronous document retriever used from the async voice pipeline via a worker thread."""

    def __init__(self, settings: Settings):
        self.settings = settings
        logger.info("Loading embedding model {}", settings.embedding_model)
        self.encoder = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        self.client = self._build_client(settings)

    @staticmethod
    def _build_client(settings: Settings) -> QdrantClient:
        """Construct Qdrant from a configured server URL or embedded path."""
        if settings.qdrant_url:
            logger.info("Using Qdrant server at {}", settings.qdrant_url)
            return QdrantClient(url=settings.qdrant_url)

        path = Path(settings.qdrant_path)
        path.mkdir(parents=True, exist_ok=True)
        logger.info("Using embedded Qdrant at {}", path)
        return QdrantClient(path=str(path))

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        """Run the existing BGE + Qdrant semantic retrieval flow."""
        query = query.strip()
        if not query:
            return []

        vector = self.encoder.encode_query(
            query,
            prompt=BGE_QUERY_PROMPT,
            normalize_embeddings=True,
        ).tolist()
        result = self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=vector,
            limit=top_k or self.settings.rag_top_k,
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
                    page=int(payload.get("page", 0)),
                    source=str(payload.get("source", "document")),
                    score=score,
                )
            )
        return chunks


@lru_cache(maxsize=1)
def get_retriever() -> DocumentRetriever:
    """Return the process-local cached retriever instance."""
    settings = Settings.from_env()
    settings.validate()
    return DocumentRetriever(settings)
