from echolex.domain.models import RetrievedChunk
from echolex.retrieval.conversation import (
    EvidenceMemory,
    build_retrieval_query,
    should_reuse_evidence,
    source_announcement,
)


def _chunk(page: int) -> RetrievedChunk:
    return RetrievedChunk(
        text=f"evidence from page {page}",
        page=page,
        source="paper.pdf",
        score=0.9,
        chunk_id=f"chunk-{page}",
        chunk_index=0,
    )


def test_explicit_rephrase_reuses_previous_evidence() -> None:
    memory = EvidenceMemory(
        user_query="What is FID?",
        chunks=(_chunk(5),),
    )

    assert should_reuse_evidence(
        "Explain that in simpler terms",
        memory,
    )


def test_new_factual_followup_triggers_retrieval() -> None:
    memory = EvidenceMemory(
        user_query="What is FID?",
        chunks=(_chunk(5),),
    )

    assert not should_reuse_evidence(
        "What are its limitations?",
        memory,
    )


def test_referential_followup_is_contextualized_for_retrieval() -> None:
    memory = EvidenceMemory(
        user_query="What is FID?",
        chunks=(_chunk(5),),
    )

    query = build_retrieval_query(
        "What are its limitations?",
        memory,
    )

    assert "Previous topic: What is FID?" in query
    assert "Follow-up question: What are its limitations?" in query


def test_page_announcement_is_deduplicated_and_sorted() -> None:
    chunks = [
        _chunk(6),
        _chunk(5),
        _chunk(6),
    ]

    assert (
        source_announcement(chunks)
        == "Retrieved from pages 5 and 6."
    )


def test_no_evidence_has_explicit_source_announcement() -> None:
    assert (
        source_announcement([])
        == "Retrieved from no relevant page."
    )