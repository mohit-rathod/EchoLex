from __future__ import annotations

import argparse
import hashlib
import uuid
from pathlib import Path

from loguru import logger
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from echolex.chunking import TextChunk, extract_pdf_chunks
from echolex.config import Settings


def _client(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url)
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


def ingest_pdf(pdf_path: str | Path, *, recreate: bool = False) -> int:
    settings = Settings.from_env()
    settings.validate()
    path = Path(pdf_path).resolve()

    logger.info("Extracting and chunking {}", path)
    chunks = extract_pdf_chunks(
        path,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    logger.info("Created {} chunks", len(chunks))

    logger.info("Loading embedding model {}", settings.embedding_model)
    encoder = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
    dimension = int(encoder.get_sentence_embedding_dimension())
    client = _client(settings)

    exists = client.collection_exists(settings.qdrant_collection)
    if recreate and exists:
        logger.warning("Recreating collection {}", settings.qdrant_collection)
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
    batch_size = 64
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [item.text for item in batch]
        vectors = encoder.encode_document(
            texts,
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
        logger.info("Indexed {}/{} chunks", min(start + len(batch), len(chunks)), len(chunks))

    client.close()
    logger.success("Indexed {} chunks from {}", len(chunks), path.name)
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a PDF into local Qdrant.")
    parser.add_argument("pdf", help="Path to a PDF file")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the collection first. Recommended for the single-document starter.",
    )
    args = parser.parse_args()
    ingest_pdf(args.pdf, recreate=args.recreate)


if __name__ == "__main__":
    main()
