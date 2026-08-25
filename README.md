# Talk-To-Your-Document

A fully local, open-source voice RAG application built with Pipecat, vLLM, Speaches, SentenceTransformers, Qdrant, and PyMuPDF.

This version keeps the existing runtime behavior intact while reorganizing the repository into explicit production-oriented module boundaries.

## Runtime flow

```text
Microphone
  -> Pipecat + Silero VAD
  -> Faster-Whisper STT via Speaches
  -> BGE query embedding
  -> Qdrant retrieval
  -> vLLM / Qwen2.5 response
  -> Kokoro TTS via Speaches
  -> Browser audio
```

Document ingestion remains a separate flow:

```text
PDF -> PyMuPDF -> page-aware chunks -> BGE embeddings -> Qdrant
```

## Repository structure

```text
.
├── .dockerignore
├── .env.example
├── .gitignore
├── ARCHITECTURE.md
├── Makefile
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
├── data/
│   ├── documents/
│   │   └── .gitkeep
│   └── qdrant/
│       └── .gitkeep
├── src/echolex/
│   ├── __init__.py
│   ├── bot.py                       # Stable Pipecat module entrypoint
│   ├── chunking.py                  # Compatibility import
│   ├── config.py                    # Compatibility import
│   ├── healthcheck.py               # Compatibility entrypoint
│   ├── rag.py                       # Compatibility import
│   ├── cli/
│   │   ├── health.py
│   │   └── ingest.py
│   ├── core/
│   │   ├── config.py
│   │   └── prompts.py
│   ├── domain/
│   │   └── models.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── chunking.py
│   │   └── service.py
│   ├── integrations/
│   │   └── speech/
│   │       └── speaches_tts.py
│   ├── retrieval/
│   │   └── service.py
│   ├── voice/
│   │   ├── pipeline.py
│   │   └── processors/
│   │       └── rag_context.py
│   ├── processors/                  # Compatibility imports
│   └── services/                    # Compatibility imports
└── tests/
    ├── test_chunking.py
    ├── test_config.py
    └── test_public_imports.py
```

See `ARCHITECTURE.md` for module ownership, dependency direction, and intentionally deferred runtime improvements.

## Design principles in this refactor

- Runtime/business behavior is intentionally unchanged.
- Domain data models are framework-independent.
- Configuration and prompt constants live under `core`.
- Ingestion and retrieval are separate features instead of root-level modules.
- Pipecat-specific code lives under the voice boundary.
- Speaches is treated as an integration adapter.
- CLI parsing is separated from application logic.
- Original import/entrypoint paths remain available through thin compatibility modules.
- Local secrets, vector-store state, PDFs, and Python bytecode are excluded from the repository.

## Prerequisites

Recommended development environment:

- Linux or WSL2
- Docker Engine + Docker Compose
- NVIDIA GPU with NVIDIA Container Toolkit for vLLM
- Python 3.11+
- `uv`

The supplied Qwen2.5-7B AWQ setup is best suited to a GPU with roughly 12 GB VRAM or more. Lower-memory GPUs may require reducing model context length or concurrency.

## Setup

Create the local environment:

```bash
cp .env.example .env
uv sync --dev
```

Start local inference services:

```bash
docker compose up -d
```

Verify vLLM and Speaches readiness:

```bash
uv run echolex-health
```

Default local endpoints:

- vLLM: `http://127.0.0.1:8000/v1`
- Speaches: `http://127.0.0.1:8001/v1`

## Index a PDF

Copy a PDF into the local document directory:

```bash
cp /path/to/manual.pdf data/documents/manual.pdf
```

Create the vector index:

```bash
uv run echolex-ingest data/documents/manual.pdf --recreate
```

or:

```bash
make ingest PDF=data/documents/manual.pdf
```

## Run the voice application

Once inference services are healthy and a PDF has been indexed:

```bash
uv run python -m echolex.bot -t webrtc
```

Open:

```text
http://localhost:7860/client
```

Retrieved excerpts are injected only into the current LLM request. They are not permanently appended to conversation history.

## Development commands

```bash
# Tests
uv run pytest -q

# Lint
uv run ruff check src tests

# Local service health
uv run echolex-health

# Infrastructure lifecycle
docker compose up -d
docker compose ps
docker compose logs -f vllm
docker compose logs -f speaches
docker compose down
```

## Repository hygiene

The refactored repository intentionally does not ship:

- `.env`
- indexed Qdrant data
- uploaded/source PDFs
- `__pycache__`
- local test/lint caches

Use `.env.example` as the checked-in configuration template and populate local runtime data under `data/`.

## Deferred engineering work

This pass is structural only. Runtime shortcomings such as standalone Qdrant deployment, retry/circuit-breaker policies, OCR, multi-document lifecycle, authentication, richer observability, retrieval tuning, and model/service lifecycle management are deliberately left for later changes so they can be implemented and benchmarked independently.
