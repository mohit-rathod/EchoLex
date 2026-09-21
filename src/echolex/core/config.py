from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    llm_base_url: str
    llm_model_name: str
    llm_temperature: float
    llm_max_completion_tokens: int

    stt_base_url: str
    stt_model: str
    stt_language: str | None
    stt_ttfs_p99_seconds: float

    tts_base_url: str
    tts_model: str
    tts_voice: str
    tts_language: str
    tts_speed: float
    tts_sample_rate: int

    embedding_model: str
    embedding_device: str

    qdrant_collection: str
    qdrant_url: str | None
    qdrant_path: Path

    rag_top_k: int
    rag_score_threshold: float
    rag_retrieval_timeout_seconds: float

    chunk_max_chars: int
    chunk_overlap_chars: int

    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        language = os.getenv("STT_LANGUAGE", "en").strip()
        qdrant_url = os.getenv("QDRANT_URL", "").strip() or None
        return cls(
            llm_base_url=_env("LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/"),
            llm_model_name=_env("LLM_MODEL_NAME", "qwen3-4b-awq"),
            llm_temperature=float(_env("LLM_TEMPERATURE", "0.15")),
            llm_max_completion_tokens=int(_env("LLM_MAX_COMPLETION_TOKENS", "320")),
            stt_base_url=_env(
                "STT_BASE_URL", "http://127.0.0.1:8001/v1"
            ).rstrip("/"),
            tts_base_url=_env(
                "TTS_BASE_URL", "http://127.0.0.1:8002/v1"
            ).rstrip("/"),
            stt_model=_env("STT_MODEL", "qwen3-asr-0.6b"),
            stt_language=language or None,
            stt_ttfs_p99_seconds=float(_env("STT_TTFS_P99_SECONDS", "0.8")),
            tts_model=_env("TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"),
            tts_voice=_env("TTS_VOICE", "vivian"),
            tts_language=_env("TTS_LANGUAGE", "English"),
            tts_speed=float(_env("TTS_SPEED", "1.0")),
            tts_sample_rate=int(_env("TTS_SAMPLE_RATE", "24000")),
            embedding_model=_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            embedding_device=_env("EMBEDDING_DEVICE", "cpu"),
            qdrant_collection=_env("QDRANT_COLLECTION", "echolex"),
            qdrant_url=qdrant_url,
            qdrant_path=Path(_env("QDRANT_PATH", "./data/qdrant")),
            rag_top_k=int(_env("RAG_TOP_K", "4")),
            rag_score_threshold=float(_env("RAG_SCORE_THRESHOLD", "0.55")),
            rag_retrieval_timeout_seconds=float(
                _env("RAG_RETRIEVAL_TIMEOUT_SECONDS", "1.5")
            ),
            chunk_max_chars=int(_env("CHUNK_MAX_CHARS", "1200")),
            chunk_overlap_chars=int(_env("CHUNK_OVERLAP_CHARS", "180")),
            log_level=_env("LOG_LEVEL", "INFO"),
        )

    def validate(self) -> None:
        if self.chunk_overlap_chars >= self.chunk_max_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS must be smaller than CHUNK_MAX_CHARS")
        if not 0.0 <= self.rag_score_threshold <= 1.0:
            raise ValueError("RAG_SCORE_THRESHOLD must be between 0 and 1")
        if not 0.0 <= self.llm_temperature <= 2.0:
            raise ValueError("LLM_TEMPERATURE must be between 0 and 2")
        if self.tts_sample_rate not in {8000, 24000}:
            raise ValueError(
                "Qwen3-TTS via vLLM-Omni supports "
                "TTS_SAMPLE_RATE=8000 or 24000. "
                "Use 24000 for the repository's default voice pipeline."
            )

        if self.tts_speed != 1.0:
            raise ValueError(
                "The current TTS adapter uses raw streaming audio, "
                "and vLLM-Omni requires TTS_SPEED=1.0 "
                "for streaming requests."
            )
