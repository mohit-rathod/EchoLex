# Echolex / Talk-To-Your-Document

A local-first voice RAG application built around Pipecat, vLLM, vLLM-Omni, Qdrant, SentenceTransformers, and PyMuPDF.

This revision keeps the existing product flow while hardening the codebase for repeatable deployment and operations: validated configuration, standalone Qdrant support, bounded RAG context, explicit resource cleanup, safer TTS error handling, health checks, structured logging support, CI, and repository/deployment hygiene.

## Runtime flow

```text
Browser microphone
  -> Pipecat + Silero VAD
  -> Qwen3-ASR through an OpenAI-compatible vLLM endpoint
  -> BGE query embedding
  -> Qdrant semantic retrieval
  -> request-scoped grounded context
  -> Qwen3 LLM through vLLM
  -> Qwen3-TTS through vLLM-Omni
  -> browser audio
```

Document ingestion is separate:

```text
PDF
  -> file/page safety checks
  -> PyMuPDF ordered text extraction
  -> bounded overlapping chunks
  -> SentenceTransformer embeddings
  -> deterministic IDs + provenance
  -> Qdrant
```

## Repository layout

```text
src/echolex/
├── core/                  # validated settings, logging, prompt/text utilities
├── domain/                # framework-independent immutable models
├── ingestion/             # PDF extraction, chunking, embedding and indexing
├── retrieval/             # Qdrant retrieval + conversational evidence policy
├── integrations/speech/   # vLLM-Omni and legacy speech adapters
├── voice/                 # Pipecat orchestration and RAG processor
├── cli/                   # operational entrypoints
└── compatibility modules  # preserved legacy import paths
```

See `ARCHITECTURE.md` for dependency rules and deployment notes.

## Prerequisites

- Linux or WSL2
- Docker Engine + Docker Compose
- NVIDIA Container Toolkit for GPU inference
- Python 3.11+
- `uv`

The supplied inference settings are deliberately low-concurrency and tuned for a constrained single-GPU local environment. Benchmark and resize model context, concurrency, and GPU memory reservations for the actual deployment GPU before raising traffic.

## Setup

```bash
cp .env.example .env
uv sync --frozen --dev
docker compose up -d
uv run echolex-health
```

The default local endpoints are:

- LLM: `http://127.0.0.1:8000/v1`
- STT: `http://127.0.0.1:8001/v1`
- TTS: `http://127.0.0.1:8002/v1`
- Qdrant: `http://127.0.0.1:6333`

## Index a PDF

```bash
cp /path/to/manual.pdf data/documents/manual.pdf
uv run echolex-ingest data/documents/manual.pdf --recreate
```

`--recreate` is convenient for a single-document environment because it resets the collection first. Without it, deterministic point IDs make re-ingesting the same unchanged PDF idempotent.

## Run the voice application

```bash
uv run echolex-bot -t webrtc
```

Then open the Pipecat client URL printed by the runner (commonly `http://localhost:7860/client`).

## Configuration

`.env.example` documents all supported settings. Important production controls include:

```text
APP_ENV=production
LOG_JSON=true
QDRANT_URL=http://qdrant.internal:6333
QDRANT_API_KEY=...
LLM_API_KEY=...
STT_API_KEY=...
TTS_API_KEY=...
RAG_RETRIEVAL_TIMEOUT_SECONDS=1.5
RAG_MAX_CONTEXT_CHARS=6000
MAX_PDF_BYTES=104857600
MAX_PDF_PAGES=2000
```

## Observability

Start the local LGTM overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```
