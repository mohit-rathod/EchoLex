from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from loguru import logger
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from echolex.core.config import Settings
from echolex.domain.models import TextChunk
from echolex.ingestion.chunking import extract_pdf_chunks


def _client(settings: Settings) -> QdrantClient:
    """Initialize Qdrant from a remote URL or embedded local storage."""
    if settings.qdrant_url:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=settings.qdrant_timeout_seconds,
        )
    settings.qdrant_path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(settings.qdrant_path))


def _document_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _point_id(document_hash: str, chunk: TextChunk) -> str:
    key = f"{document_hash}:{chunk.page}:{chunk.chunk_index}:{chunk.text}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _validate_pdf(path: Path, settings: Settings) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"PDF is empty: {path}")
    if size > settings.max_pdf_bytes:
        raise ValueError(
            f"PDF is {size} bytes; configured MAX_PDF_BYTES is {settings.max_pdf_bytes}"
        )


def ingest_pdf(pdf_path: str | Path, *, recreate: bool = False) -> int:
    """Extract, embed, and idempotently index one PDF into Qdrant."""
    settings = Settings.from_env()
    path = Path(pdf_path).expanduser().resolve()
    _validate_pdf(path, settings)

    if recreate and settings.app_env == "production" and not settings.allow_collection_recreate:
        raise ValueError(
            "Collection recreation is disabled in production. "
            "Set ALLOW_COLLECTION_RECREATE=true only for an intentional destructive reset."
        )

    started = time.perf_counter()
    logger.info("ingestion_started path={} collection={}", path, settings.qdrant_collection)
    chunks = extract_pdf_chunks(
        path,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
        max_pages=settings.max_pdf_pages,
    )

    logger.info("embedding_model_loading model={} device={}", settings.embedding_model, settings.embedding_device)
    encoder = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
    dimension = int(encoder.get_embedding_dimension())
    client = _client(settings)

    try:
        exists = client.collection_exists(settings.qdrant_collection)
        if recreate and exists:
            logger.warning("qdrant_collection_recreate collection={}", settings.qdrant_collection)
            client.delete_collection(settings.qdrant_collection)
            exists = False

        if not exists:
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )

        document_hash = _document_hash(path)
        batch_size = settings.ingest_batch_size

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = encoder.encode_document(
                [item.text for item in batch],
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            points = [
                models.PointStruct(
                    id=_point_id(document_hash, chunk),
                    vector=vector.tolist(),
                    payload={
                        "text": chunk.text,
                        "page": chunk.page,
                        "chunk_index": chunk.chunk_index,
                        "source": chunk.source,
                        "document_sha256": document_hash,
                    },
                )
                for chunk, vector in zip(batch, vectors, strict=True)
            ]
            client.upsert(
                collection_name=settings.qdrant_collection,
                points=points,
                wait=True,
            )
            logger.info(
                "ingestion_batch_complete indexed={} total={}",
                min(start + len(batch), len(chunks)),
                len(chunks),
            )
    finally:
        client.close()

    logger.success(
        "ingestion_complete source={} chunks={} elapsed_ms={:.1f}",
        path.name,
        len(chunks),
        (time.perf_counter() - started) * 1000,
    )
    return len(chunks)
