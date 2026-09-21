from dataclasses import replace

import pytest

from echolex.config import Settings


def test_default_settings_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = [
        "LLM_BASE_URL",
        "LLM_MODEL_NAME",
        "LLM_TEMPERATURE",
        "LLM_MAX_COMPLETION_TOKENS",

        "STT_BASE_URL",
        "STT_MODEL",
        "STT_LANGUAGE",
        "STT_TTFS_P99_SECONDS",

        "TTS_BASE_URL",
        "TTS_MODEL",
        "TTS_VOICE",
        "TTS_LANGUAGE",
        "TTS_SPEED",
        "TTS_SAMPLE_RATE",

        "EMBEDDING_MODEL",
        "EMBEDDING_DEVICE",

        "QDRANT_COLLECTION",
        "QDRANT_URL",
        "QDRANT_PATH",

        "RAG_TOP_K",
        "RAG_SCORE_THRESHOLD",
        "RAG_RETRIEVAL_TIMEOUT_SECONDS",

        "CHUNK_MAX_CHARS",
        "CHUNK_OVERLAP_CHARS",

        "LOG_LEVEL",
    ]

    for name in names:
        monkeypatch.delenv(
            name,
            raising=False,
        )

    settings = Settings.from_env()

    settings.validate()

    assert (
        settings.llm_model_name
        == "qwen3-4b-awq"
    )

    assert (
        settings.stt_model
        == "qwen3-asr-0.6b"
    )

    assert (
        settings.tts_model
        == (
            "Qwen/"
            "Qwen3-TTS-12Hz-"
            "0.6B-CustomVoice"
        )
    )

    assert (
        settings.tts_voice
        == "vivian"
    )

    assert (
        settings.embedding_device
        == "cpu"
    )

    assert (
        settings.tts_sample_rate
        == 24000
    )


def test_settings_reject_invalid_chunk_overlap() -> None:
    settings = Settings.from_env()

    invalid = replace(
        settings,
        chunk_max_chars=100,
        chunk_overlap_chars=100,
    )

    with pytest.raises(
        ValueError,
        match="CHUNK_OVERLAP_CHARS",
    ):
        invalid.validate()

def test_settings_reject_non_default_streaming_tts_speed() -> None:
    settings = Settings.from_env()

    invalid = replace(
        settings,
        tts_speed=1.25,
    )

    with pytest.raises(
        ValueError,
        match="TTS_SPEED=1.0",
    ):
        invalid.validate()