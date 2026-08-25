from echolex.chunking import TextChunk, chunk_page_text, normalize_text


def test_normalize_text_preserves_paragraph_boundaries() -> None:
    raw = "First\u00ad  sentence.\n\n\n  Second\tparagraph.  "

    assert normalize_text(raw) == "First sentence.\n\nSecond paragraph."


def test_chunk_page_text_preserves_page_source_and_indices() -> None:
    text = "Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph."

    chunks = chunk_page_text(
        text,
        page=3,
        source="sample.pdf",
        max_chars=24,
        overlap_chars=4,
    )

    assert chunks
    assert all(isinstance(chunk, TextChunk) for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.page == 3 for chunk in chunks)
    assert all(chunk.source == "sample.pdf" for chunk in chunks)


def test_chunk_page_text_returns_empty_list_for_blank_text() -> None:
    assert chunk_page_text(" \n\t ", page=1, source="blank.pdf") == []
