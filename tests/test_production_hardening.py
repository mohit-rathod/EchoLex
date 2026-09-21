from __future__ import annotations

from dataclasses import replace

import pytest

from echolex.core.config import ConfigurationError, Settings
from echolex.core.speech_text import prepare_text_for_speech
from echolex.ingestion.chunking import chunk_page_text


def test_production_requires_remote_qdrant() -> None:
    settings = replace(Settings.from_env(), app_env="production", qdrant_url=None)

    with pytest.raises(ConfigurationError, match="QDRANT_URL"):
        settings.validate()


def test_chunking_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_chars"):
        chunk_page_text(
            "content",
            page=1,
            source="doc.pdf",
            max_chars=100,
            overlap_chars=100,
        )


def test_spoken_text_preserves_hyphenated_prose() -> None:
    text = "This is a state-of-the-art method."

    assert prepare_text_for_speech(text) == text


def test_spoken_text_converts_spaced_math_operator() -> None:
    assert prepare_text_for_speech("x + y = 4") == "x plus y equals 4"
