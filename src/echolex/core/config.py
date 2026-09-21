from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

Environment = Literal["development", "test", "production"]


class ConfigurationError(ValueError):
    """Raised when runtime configuration is invalid or unsafe."""


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _int_env(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer; got {raw!r}") from exc


def _float_env(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number; got {raw!r}") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean; got {raw!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime configuration loaded from environment variables."""

    app_env: Environment
    log_level: str
    log_json: bool

    llm_base_url: str
    llm_api_key: str
    llm_model_name: str
    llm_temperature: float
    llm_max_completion_tokens: int

    stt_base_url: str
    stt_api_key: str
    stt_model: str
    stt_language: str | None
    stt_ttfs_p99_seconds: float

    tts_base_url: str
    tts_api_key: str | None
    tts_model: str
    tts_voice: str
    tts_language: str
    tts_speed: float
    tts_sample_rate: int
    tts_request_timeout_seconds: float

    embedding_model: str
    embedding_device: str

    qdrant_collection: str
    qdrant_url: str | None
    qdrant_api_key: str | None
    qdrant_path: Path
    qdrant_timeout_seconds: float

    rag_top_k: int
    rag_score_threshold: float
    rag_retrieval_timeout_seconds: float
    rag_max_context_chars: int

    chunk_max_chars: int
    chunk_overlap_chars: int
    ingest_batch_size: int
    allow_collection_recreate: bool
    max_pdf_bytes: int
    max_pdf_pages: int

    health_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        language = _env("STT_LANGUAGE", "en")
        app_env = _env("APP_ENV", "development").lower()

        settings = cls(
            app_env=app_env,  # type: ignore[arg-type]
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            log_json=_bool_env("LOG_JSON", False),
            llm_base_url=_env("LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/"),
            llm_api_key=_env("LLM_API_KEY", "local-not-a-secret"),
            llm_model_name=_env("LLM_MODEL_NAME", "qwen3-4b-awq"),
            llm_temperature=_float_env("LLM_TEMPERATURE", 0.15),
            llm_max_completion_tokens=_int_env("LLM_MAX_COMPLETION_TOKENS", 320),
            stt_base_url=_env("STT_BASE_URL", "http://127.0.0.1:8001/v1").rstrip("/"),
            stt_api_key=_env("STT_API_KEY", "local-not-a-secret"),
            stt_model=_env("STT_MODEL", "qwen3-asr-0.6b"),
            stt_language=language or None,
            stt_ttfs_p99_seconds=_float_env("STT_TTFS_P99_SECONDS", 0.8),
            tts_base_url=_env("TTS_BASE_URL", "http://127.0.0.1:8002/v1").rstrip("/"),
            tts_api_key=_optional_env("TTS_API_KEY"),
            tts_model=_env("TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"),
            tts_voice=_env("TTS_VOICE", "vivian"),
            tts_language=_env("TTS_LANGUAGE", "English"),
            tts_speed=_float_env("TTS_SPEED", 1.0),
            tts_sample_rate=_int_env("TTS_SAMPLE_RATE", 24000),
            tts_request_timeout_seconds=_float_env("TTS_REQUEST_TIMEOUT_SECONDS", 60.0),
            embedding_model=_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            embedding_device=_env("EMBEDDING_DEVICE", "cpu"),
            qdrant_collection=_env("QDRANT_COLLECTION", "echolex"),
            qdrant_url=_optional_env("QDRANT_URL"),
            qdrant_api_key=_optional_env("QDRANT_API_KEY"),
            qdrant_path=Path(_env("QDRANT_PATH", "./data/qdrant")),
            qdrant_timeout_seconds=_float_env("QDRANT_TIMEOUT_SECONDS", 5.0),
            rag_top_k=_int_env("RAG_TOP_K", 4),
            rag_score_threshold=_float_env("RAG_SCORE_THRESHOLD", 0.55),
            rag_retrieval_timeout_seconds=_float_env("RAG_RETRIEVAL_TIMEOUT_SECONDS", 1.5),
            rag_max_context_chars=_int_env("RAG_MAX_CONTEXT_CHARS", 6000),
            chunk_max_chars=_int_env("CHUNK_MAX_CHARS", 1200),
            chunk_overlap_chars=_int_env("CHUNK_OVERLAP_CHARS", 180),
            ingest_batch_size=_int_env("INGEST_BATCH_SIZE", 64),
            allow_collection_recreate=_bool_env("ALLOW_COLLECTION_RECREATE", False),
            max_pdf_bytes=_int_env("MAX_PDF_BYTES", 100 * 1024 * 1024),
            max_pdf_pages=_int_env("MAX_PDF_PAGES", 2000),
            health_timeout_seconds=_float_env("HEALTH_TIMEOUT_SECONDS", 3.0),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.app_env not in {"development", "test", "production"}:
            raise ConfigurationError("APP_ENV must be development, test, or production")
        if self.log_level not in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError(f"Unsupported LOG_LEVEL: {self.log_level}")
        if self.chunk_max_chars <= 0:
            raise ConfigurationError("CHUNK_MAX_CHARS must be greater than 0")
        if self.chunk_overlap_chars < 0 or self.chunk_overlap_chars >= self.chunk_max_chars:
            raise ConfigurationError("CHUNK_OVERLAP_CHARS must be >= 0 and smaller than CHUNK_MAX_CHARS")
        if self.rag_top_k <= 0:
            raise ConfigurationError("RAG_TOP_K must be greater than 0")
        if not 0.0 <= self.rag_score_threshold <= 1.0:
            raise ConfigurationError("RAG_SCORE_THRESHOLD must be between 0 and 1")
        if self.rag_retrieval_timeout_seconds <= 0:
            raise ConfigurationError("RAG_RETRIEVAL_TIMEOUT_SECONDS must be greater than 0")
        if self.rag_max_context_chars <= 0:
            raise ConfigurationError("RAG_MAX_CONTEXT_CHARS must be greater than 0")
        if not 0.0 <= self.llm_temperature <= 2.0:
            raise ConfigurationError("LLM_TEMPERATURE must be between 0 and 2")
        if self.llm_max_completion_tokens <= 0:
            raise ConfigurationError("LLM_MAX_COMPLETION_TOKENS must be greater than 0")
        if self.stt_ttfs_p99_seconds <= 0:
            raise ConfigurationError("STT_TTFS_P99_SECONDS must be greater than 0")
        if self.tts_sample_rate not in {8000, 24000}:
            raise ConfigurationError(
                "Qwen3-TTS via vLLM-Omni supports TTS_SAMPLE_RATE=8000 or 24000"
            )
        if self.tts_speed != 1.0:
            raise ConfigurationError(
                "The streaming vLLM-Omni adapter requires TTS_SPEED=1.0"
            )
        if self.tts_request_timeout_seconds <= 0:
            raise ConfigurationError("TTS_REQUEST_TIMEOUT_SECONDS must be greater than 0")
        if self.qdrant_timeout_seconds <= 0:
            raise ConfigurationError("QDRANT_TIMEOUT_SECONDS must be greater than 0")
        if self.ingest_batch_size <= 0:
            raise ConfigurationError("INGEST_BATCH_SIZE must be greater than 0")
        if self.max_pdf_bytes <= 0:
            raise ConfigurationError("MAX_PDF_BYTES must be greater than 0")
        if self.max_pdf_pages <= 0:
            raise ConfigurationError("MAX_PDF_PAGES must be greater than 0")
        if self.health_timeout_seconds <= 0:
            raise ConfigurationError("HEALTH_TIMEOUT_SECONDS must be greater than 0")
        if self.app_env == "production" and not self.qdrant_url:
            raise ConfigurationError(
                "QDRANT_URL is required when APP_ENV=production; embedded Qdrant is for local development only"
            )
