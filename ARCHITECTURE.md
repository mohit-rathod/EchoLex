# Echolex Architecture

## Dependency direction

```text
CLI / voice entrypoints
        |
        v
application features (ingestion, retrieval, voice processors)
        |
        +---------------------------+
        v                           v
      domain                       core
        ^                           |
        |                           v
        +---------- integrations / third-party adapters
```

Canonical modules must not import the legacy compatibility paths under `echolex.config`, `echolex.chunking`, `echolex.rag`, `echolex.processors`, or `echolex.services`.

## Ownership

- `echolex.core`: configuration validation, logging policy, prompts, spoken-text normalization.
- `echolex.domain`: immutable framework-independent value objects.
- `echolex.ingestion`: file validation, PDF extraction/chunking, embedding, Qdrant indexing.
- `echolex.retrieval`: embedding/query execution and conversational evidence rules.
- `echolex.integrations`: adapters for external/local model services.
- `echolex.voice`: Pipecat pipeline construction and per-turn RAG augmentation.
- `echolex.cli`: operational commands.

## Runtime lifecycle

### Startup

1. `Settings.from_env()` loads `.env` without overriding already-injected environment variables.
2. Settings are parsed and validated before model/network clients are created.
3. Logging is configured once by the CLI entrypoint.
4. The voice pipeline creates STT/LLM/TTS adapters and obtains the process-local retriever.
5. The retriever lazily loads the embedding model and Qdrant client once per process.

### Request/turn

1. Pipecat converts speech to the latest user message.
2. `RAGContextProcessor` resolves whether the turn is an explicit rephrasing or a new factual question.
3. Retrieval runs in a worker thread with an application-level timeout.
4. Retrieved evidence is capped by a character budget and injected only into a transient LLM context.
5. The LLM response is converted to spoken-safe text and streamed from vLLM-Omni TTS.
6. The original conversation context remains free of embedded document excerpts.

### Shutdown

Pipecat owns service cleanup for the voice pipeline. The process-local retriever additionally registers an `atexit` cleanup that closes Qdrant. Ingestion closes Qdrant with `finally`, including failure paths.

## Data/provenance model

Every indexed Qdrant point includes:

- deterministic UUID5 point ID;
- document SHA-256;
- source filename;
- 1-based page number;
- page-local chunk index;
- extracted chunk text.

The deterministic ID makes re-ingestion of the same unchanged document idempotent.

## Security boundaries

Document text is untrusted data. Retrieved excerpts are wrapped as reference material and the system prompt explicitly forbids following instructions found inside the document. This reduces prompt-injection risk but does not replace tenant authorization or document-level access control.

The local Docker stack binds service ports to `127.0.0.1`. For non-local deployment, expose services through authenticated/private networking rather than changing these binds directly on an internet host.

## Production mode

`APP_ENV=production` requires `QDRANT_URL`; embedded Qdrant is intentionally treated as a development mode because it is not an appropriate shared concurrent service boundary.

Environment-specific production concerns that remain outside this repository include ingress/TLS, secrets management, autoscaling, Qdrant backups, multi-tenant authorization, SLO-based alerting, and rollout strategy.

## Compatibility surface

Legacy imports remain as thin wrappers:

- `echolex.config`
- `echolex.chunking`
- `echolex.rag`
- `echolex.bot`
- `echolex.healthcheck`
- `echolex.processors.rag_context`
- `echolex.services.speaches_tts`
- `echolex.services.speech_text`
