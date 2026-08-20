Talk-To-Your-Document

A fully local, open-source voice RAG starter built with Pipecat, vLLM, Speaches, SentenceTransformers, and Qdrant.

Upload a PDF, index it locally, then ask questions by voice. The system transcribes the question, retrieves relevant document context, generates a grounded answer with a local LLM, and streams the response back as speech.

No proprietary inference APIs are required after model weights have been downloaded.

Use case

This repo is designed for building local voice assistants that can answer questions from private documents.

Typical use cases include:

Internal knowledge assistants

Policy and compliance document Q&A

Technical manual assistants

Private research or enterprise document search

Offline or air-gapped voice RAG prototypes

Runtime flow:

Microphone
  -> Pipecat + Silero VAD
  -> Faster-Whisper STT
  -> BGE query embedding
  -> Qdrant retrieval
  -> vLLM / Qwen2.5 response
  -> Kokoro TTS
  -> Browser audio

Document ingestion runs separately:

PDF -> PyMuPDF -> page-aware chunks -> BGE embeddings -> Qdrant

What is in this repo

.
├── docker-compose.yml          # Local vLLM + Speaches services
├── .env.example                # Runtime configuration
├── Makefile
├── pyproject.toml
├── data/
│   ├── documents/              # PDFs to index
│   └── qdrant/                 # Local persistent vector store
├── src/echolex/
│   ├── bot.py                  # Pipecat WebRTC voice pipeline
│   ├── chunking.py             # PDF extraction and chunking
│   ├── config.py               # Environment configuration
│   ├── healthcheck.py          # Service readiness checks
│   ├── ingestion.py            # PDF -> embeddings -> Qdrant
│   ├── rag.py                  # Retrieval layer
│   ├── processors/
│   │   └── rag_context.py      # Injects retrieved context per turn
│   └── services/
│       └── speaches_tts.py     # Local streaming TTS adapter
└── tests/
    └── test_chunking.py

Main components:

Pipecat for the real-time voice pipeline

Speaches for local Faster-Whisper STT and Kokoro TTS

vLLM for local OpenAI-compatible LLM inference

Qwen2.5-7B-Instruct-AWQ as the default LLM

BAAI/bge-small-en-v1.5 for embeddings

Qdrant embedded mode for local persistent retrieval

PyMuPDF for PDF parsing and page-aware chunking

Prerequisites

Recommended development environment:

Linux or WSL2

Docker Engine + Docker Compose

NVIDIA GPU with NVIDIA Container Toolkit for vLLM

Python 3.11+

uv

The supplied Qwen2.5-7B AWQ setup is best suited to a GPU with roughly 12 GB VRAM or more. Lower-memory GPUs may require reducing model context length or concurrency.

Setup

Create the local environment:

cp .env.example .env
uv sync --dev

Start the local inference services:

docker compose up -d

Verify that vLLM and Speaches are healthy:

uv run echolex-health

Useful endpoints:

vLLM:     http://127.0.0.1:8000/v1
Speaches: http://127.0.0.1:8001/v1

Index a PDF

Copy a PDF into the repository:

cp /path/to/manual.pdf data/documents/manual.pdf

Create the local vector index:

uv run echolex-ingest data/documents/manual.pdf --recreate

or:

make ingest PDF=data/documents/manual.pdf

The ingestion pipeline extracts page-aware text, creates BGE embeddings, and stores the resulting chunks and page metadata in Qdrant.

Run the voice app

Once the services are healthy and a PDF has been indexed:

uv run python -m echolex.bot -t webrtc

Open:

http://localhost:7860/client

Allow microphone access, connect, and ask a question whose answer is contained in the indexed PDF.

Example:

User: What does this document say about the retry policy?

Voice -> STT -> document retrieval -> local LLM -> TTS -> voice response

Retrieved document excerpts are injected only for the current LLM request, so RAG context does not accumulate permanently in conversation history.

If no relevant context is found, the assistant is instructed to say that the document does not provide enough information instead of falling back to unsupported model knowledge.

Development commands

# Run tests
uv run pytest -q

# Lint
uv run ruff check src tests

# Check services
docker compose ps
docker compose logs -f vllm
docker compose logs -f speaches

# Stop local services
docker compose down

Notes

The first run downloads model weights; once cached, inference is local.

Scanned/image-only PDFs require an OCR step before ingestion.

Embedded Qdrant is intended for local/single-process development. Move to a standalone Qdrant service before running multiple workers against the same index.

PyMuPDF is AGPL/commercial dual-licensed. Review LICENSE_NOTES.md if that license is not suitable for your deployment.