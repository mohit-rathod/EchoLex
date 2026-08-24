from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class TextChunk:
    """Immutable data structure representing a processed, bounded segment of extracted PDF text.

    Attributes:
        text: The normalized text content of the chunk.
        page: The 1-based page number where the text originates.
        chunk_index: The sequential index of this chunk within its parent page.
        source: The file name of the source document.
    """
    text: str
    page: int
    chunk_index: int
    source: str


# Regex to identify sentence boundaries, looking for punctuation followed by space and capital/number/quote
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def normalize_text(text: str) -> str:
    """Normalize extraction noise while preserving paragraph boundaries.

    Cleans up soft hyphens, non-breaking spaces, excessive inline whitespace,
    and multiple blank lines.
    """
    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph into smaller sub-pieces based on sentence boundaries.

    If sentences are too long or absent, falls back to hard character slicing up to max_chars.
    """
    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
    if len(sentences) <= 1:
        return [paragraph[i : i + max_chars].strip() for i in range(0, len(paragraph), max_chars)]

    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        if len(sentence) <= max_chars:
            current = sentence
        else:
            pieces.extend(
                sentence[i : i + max_chars].strip()
                for i in range(0, len(sentence), max_chars)
                if sentence[i : i + max_chars].strip()
            )
            current = ""
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
    """Paragraph-aware chunking with a small textual overlap.

    Chunks never cross page boundaries. That slightly sacrifices packing efficiency,
    but preserves trustworthy page provenance for spoken/document answers.
    """
    clean = normalize_text(text)
    if not clean:
        return []

    # Break text into paragraphs and split any paragraphs that exceed the character ceiling
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n\s*\n", clean):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
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
            tail = current[-overlap_chars:].strip() if overlap_chars else ""
            current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph
            if len(current) > max_chars:
                raw_chunks.append(current[:max_chars].strip())
                current = current[max(0, max_chars - overlap_chars) :].strip()
        else:
            raw_chunks.append(paragraph[:max_chars].strip())
            current = paragraph[max(0, max_chars - overlap_chars) :].strip()

    if current:
        raw_chunks.append(current.strip())

    return [
        TextChunk(text=chunk, page=page, chunk_index=i, source=source)
        for i, chunk in enumerate(raw_chunks)
        if chunk
    ]


def extract_pdf_chunks(
    pdf_path: str | Path,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 180,
) -> list[TextChunk]:
    """Extract text in reading-oriented block order and chunk it page-by-page.

    Args:
        pdf_path: File system path pointing to the target PDF document.
        max_chars: Maximum character limit allowed per individual chunk.
        overlap_chars: Number of overlapping characters carried over between sequential chunks.

    Returns:
        A list of populated TextChunk instances ready for downstream vector indexing.

    Raises:
        FileNotFoundError: If the specified PDF file path does not exist.
        ValueError: If the file is not a PDF, contains zero pages, or lacks extractable text.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path}")

    chunks: list[TextChunk] = []
    # Open document securely via PyMuPDF (fitz) and iterate through pages
    with pymupdf.open(path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"PDF has no pages: {path}")
        for page_number, page in enumerate(doc, start=1):
            # Extract text blocks sorted in natural reading order
            blocks = page.get_text("blocks", sort=True)
            text = "\n\n".join(str(block[4]).strip() for block in blocks if str(block[4]).strip())
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
            "add an OCR stage before ingestion for that document."
        )
    return chunks