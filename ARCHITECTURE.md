# Echolex Architecture

This repository is intentionally structured around runtime responsibilities while preserving the existing application behavior.

## Dependency direction

```text
CLI / Voice entrypoints
        |
        v
Feature modules (ingestion, retrieval, voice processors)
        |
        +--------------------+
        v                    v
      domain               core
        ^
        |
integrations / third-party adapters
```

The current implementation is still a local single-process starter. The refactor changes module ownership and repository hygiene only; it does not change the retrieval, chunking, prompting, inference, or audio behavior.

## Package ownership

- `echolex.core`: environment-backed settings and prompt constants.
- `echolex.domain`: shared immutable data models with no framework dependencies.
- `echolex.ingestion`: PDF chunking and PDF-to-Qdrant indexing.
- `echolex.retrieval`: BGE query embedding and Qdrant retrieval.
- `echolex.voice`: Pipecat pipeline orchestration and request-scoped RAG injection.
- `echolex.integrations`: adapters for external/local services such as Speaches.
- `echolex.cli`: command-line entrypoints.

## Compatibility surface

The original import paths remain available as thin compatibility modules where possible:

- `echolex.config`
- `echolex.chunking`
- `echolex.rag`
- `echolex.bot`
- `echolex.healthcheck`
- `echolex.processors.rag_context`
- `echolex.services.speaches_tts`

`echolex.ingestion` remains the public ingestion package and still exposes `ingest_pdf` and `main`.

## Intentionally deferred engineering work

The following are not changed in this pass because they can alter runtime semantics and should be addressed independently with benchmarks/tests:

- embedded Qdrant concurrency and migration to a standalone vector service;
- retriever lifecycle/cleanup and model process management;
- retries, circuit breakers, and richer external-service failure policy;
- observability/exporters beyond Pipecat's current metrics;
- OCR for scanned PDFs;
- document lifecycle, multi-document tenancy, and collection partitioning;
- configuration schema migration to a typed settings library;
- dependency/version upgrades;
- authentication, authorization, and deployment hardening;
- retrieval-quality and latency tuning.

## Old-to-new ownership map

| Original path | Canonical path | Responsibility |
| --- | --- | --- |
| `echolex/config.py` | `echolex/core/config.py` | Runtime configuration |
| `echolex/chunking.py` | `echolex/ingestion/chunking.py` | PDF text normalization/chunking |
| `echolex/ingestion.py` | `echolex/ingestion/service.py` | Indexing use case |
| `echolex/rag.py` | `echolex/retrieval/service.py` | Semantic retrieval |
| `echolex/processors/rag_context.py` | `echolex/voice/processors/rag_context.py` | Turn-scoped RAG injection |
| `echolex/services/speaches_tts.py` | `echolex/integrations/speech/speaches_tts.py` | Speaches adapter |
| `echolex/bot.py` orchestration | `echolex/voice/pipeline.py` | Voice pipeline assembly |
| `echolex/healthcheck.py` | `echolex/cli/health.py` | Operational health CLI |
| ingestion CLI parsing | `echolex/cli/ingest.py` | Ingestion CLI |
| chunk/retrieval dataclasses | `echolex/domain/models.py` | Shared domain models |
