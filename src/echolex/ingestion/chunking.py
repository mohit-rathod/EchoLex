from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from echolex.domain.models import TextChunk

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def normalize_text(text: str) -> str:
    """Normalize extraction noise while preserving paragraph boundaries."""
    text = text.replace("\u00ad", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _validate_chunking(max_chars: int, overlap_chars: int) -> None:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be >= 0 and smaller than max_chars")


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [
        text[start : start + max_chars].strip()
        for start in range(0, len(text), max_chars)
        if text[start : start + max_chars].strip()
    ]


def _split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph at sentence boundaries when possible."""
    if len(paragraph) <= max_chars:
        return [paragraph]

    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
    if len(sentences) <= 1:
        return _hard_split(paragraph, max_chars)

    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_hard_split(sentence, max_chars))
            continue

        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence

    if current:
        pieces.append(current)
    return pieces


def chunk_page_text(
    text: str,
    *,
    page: int,
    source: str,
    max_chars: int = 1200,
    overlap_chars: int = 180,
) -> list[TextChunk]:
    """Chunk one page while preserving paragraph boundaries and bounded overlap."""
    _validate_chunking(max_chars, overlap_chars)
    if page <= 0:
        raise ValueError("page must be greater than 0")
    if not source.strip():
        raise ValueError("source must not be blank")

    clean = normalize_text(text)
    if not clean:
        return []

    paragraphs: list[str] = []
    for paragraph in re.split(r"\n\s*\n", clean):
        paragraph = paragraph.strip()
        if paragraph:
            paragraphs.extend(_split_oversized_paragraph(paragraph, max_chars))

    raw_chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            raw_chunks.append(current.strip())
            overlap = current[-overlap_chars:].strip() if overlap_chars else ""
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
        else:
            current = paragraph

        while len(current) > max_chars:
            raw_chunks.append(current[:max_chars].strip())
            next_start = max_chars - overlap_chars
            current = current[next_start:].strip()

    if current:
        raw_chunks.append(current.strip())

    return [
        TextChunk(text=chunk, page=page, chunk_index=index, source=source)
        for index, chunk in enumerate(raw_chunks)
        if chunk
    ]


def extract_pdf_chunks(
    pdf_path: str | Path,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 180,
    max_pages: int | None = None,
) -> list[TextChunk]:
    """Extract reading-ordered text and chunk it page by page."""
    _validate_chunking(max_chars, overlap_chars)
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path}")

    chunks: list[TextChunk] = []
    with pymupdf.open(path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"PDF has no pages: {path}")
        if max_pages is not None and doc.page_count > max_pages:
            raise ValueError(
                f"PDF has {doc.page_count} pages; configured limit is {max_pages}"
            )

        for page_number, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks", sort=True)
            text = "\n\n".join(
                str(block[4]).strip() for block in blocks if str(block[4]).strip()
            )
            chunks.extend(
                chunk_page_text(
                    text,
                    page=page_number,
                    source=path.name,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )

    if not chunks:
        raise ValueError(
            "No extractable text was found. The PDF may be scanned/image-only; "
            "run OCR before ingestion."
        )
    return chunks
