README
Talk-To-Your-Document: fully local Pipecat + vLLM
A reusable, fully open-source voice RAG starter. After model weights have been downloaded, the runtime does not require proprietary APIs or cloud inference.
1. System architecture
OFFLINE / INGESTION PATH

  PDF
   |
   v
+-------------------+      page-aware blocks      +---------------------+
| PyMuPDF           | --------------------------> | Paragraph/sentence  |
| get_text(blocks)  |                             | aware chunker       |
+-------------------+                             +----------+----------+
                                                             |
                                                             v
                                                  +---------------------+
                                                  | BAAI/bge-small-en-  |
                                                  | v1.5 embeddings     |
                                                  | SentenceTransformers|
                                                  +----------+----------+
                                                             |
                                                             v
                                                  +---------------------+
                                                  | Qdrant              |
                                                  | embedded persistent |
                                                  | data/qdrant         |
                                                  +---------------------+

REAL-TIME VOICE PATH

Browser microphone
       |
       | WebRTC
       v
+-----------------------+
| SmallWebRTCTransport  |
| Pipecat Audio In      |
+-----------+-----------+
            |
            v
+-----------------------+       local turn state / interruption detection
| Pipecat speech input  |<-----------------------------------------------+
| + Silero VAD          |                                                |
+-----------+-----------+                                                |
            |                                                            |
            v                                                            |
+-----------------------+       HTTP /v1/audio/transcriptions            |
| OpenAISTTService      | ------------------------------------+           |
| protocol adapter only |                                     |           |
+-----------+-----------+                                     v           |
            |                                      +-------------------+  |
            | final transcript                     | Speaches          |  |
            |                                      | Faster-Whisper    |  |
            v                                      +-------------------+  |
+-----------------------+
| User context          |
| aggregator            |
+-----------+-----------+
            |
            | LLMContextFrame
            v
+-----------------------+     query embedding     +-------------------+
| RAGContextProcessor   | ----------------------> | Qdrant            |
| transient injection   | <---------------------- | top-k excerpts    |
+-----------+-----------+                         +-------------------+
            |
            | grounded transient LLM request
            v
+-----------------------+       OpenAI-compatible /v1/chat/completions
| OpenAILLMService      | ----------------------------------------------+
| protocol adapter only |                                               |
+-----------+-----------+                                               v
            | tokens                                          +-------------------+
            |                                                 | vLLM              |
            |                                                 | Qwen2.5 7B AWQ    |
            |                                                 +-------------------+
            v
+-----------------------+
| SpeachesTTSService    |       HTTP streaming PCM
| sentence aggregation  | ----------------------------------------------+
+-----------+-----------+                                               |
            ^                                                           v
            |                                                 +-------------------+
            |                                                 | Speaches          |
            |                                                 | Kokoro-82M ONNX   |
            |                                                 +-------------------+
            |
            | TTSAudioRawFrame (24 kHz PCM)
            v
+-----------------------+
| Pipecat Audio Out     |
| SmallWebRTCTransport  |
+-----------+-----------+
            |
            | WebRTC
            v
Browser speakers
​
The actual Pipecat processor order is:
transport.input()
  -> OpenAISTTService (pointed at local Speaches)
  -> user_aggregator (Silero VAD + turn management)
  -> RAGContextProcessor
  -> OpenAILLMService (pointed at local vLLM)
  -> SpeachesTTSService
  -> transport.output()
  -> assistant_aggregator
​
The assistant aggregator deliberately stays after audio output so interruption-aware conversation history tracks spoken output rather than merely generated output.
2. Design decisions
Why Speaches for speech
Speaches provides a local OpenAI-compatible speech server, Faster-Whisper STT, and Kokoro/Piper TTS. This starter runs it on CPU so the NVIDIA GPU is reserved for vLLM. The Pipecat STT integration can use the local OpenAI-compatible endpoint directly.
For TTS, this repo contains talkdoc.services.speaches_tts.SpeachesTTSService. Do not replace it blindly with Pipecat's OpenAITTSService: that service validates OpenAI's fixed voice IDs, while Kokoro uses IDs such as af_heart.
Why Qdrant embedded first
For a single local Pipecat process, embedded persistent Qdrant avoids another server and another network hop. Set QDRANT_URL later to move retrieval to a Qdrant server without changing ingestion or processor code. Do that before running multiple bot processes against the same index.
Why transient RAG injection
Retrieved excerpts are not written permanently into conversation history. RAGContextProcessor creates a one-request LLMContext, replaces only the latest user message with a grounded query payload, and sends that copy to the LLM. This prevents the same document chunks from accumulating in every later turn.
Why cascaded STT -> LLM -> TTS
Document QA needs explicit text retrieval between transcription and generation. A cascaded pipeline gives you deterministic control over retrieval, prompts, citations/page provenance, model swapping, and latency instrumentation.
3. Prerequisites
Recommended baseline:
Linux or WSL2
Docker Engine + Docker Compose plugin
NVIDIA GPU + current NVIDIA driver + NVIDIA Container Toolkit for vLLM
Python 3.11-3.14
uv
A 12 GB-class NVIDIA GPU is the safer baseline for the supplied Qwen2.5-7B AWQ configuration. An 8 GB card may work only after reducing context length and concurrency; benchmark rather than assuming it will fit.
Enough RAM for SentenceTransformers + CPU speech inference
The first run downloads model weights. Once caches are populated, inference itself is local. For an air-gapped deployment, pre-populate the Hugging Face caches or bake model weights into internal images/volumes.
Licensing note
The runtime stack is open source/open weight, but licenses are not all equally permissive. Pipecat is BSD-2-Clause, vLLM and Qwen2.5 are Apache-2.0, Speaches is MIT, Qdrant is Apache-2.0, BGE-small-en-v1.5 is MIT, Faster-Distil-Whisper small.en is MIT, and Kokoro-82M is Apache-2.0. PyMuPDF is AGPL-3.0/commercial dual-licensed; if your product cannot accept AGPL obligations, swap the parser for pypdf (BSD-3-Clause) or another parser after reviewing its license. This is an engineering heads-up, not legal advice. See LICENSE_NOTES.md.
4. Project structure
.
├── docker-compose.yml
├── .env.example
├── Makefile
├── pyproject.toml
├── data/
│   ├── documents/
│   └── qdrant/
├── src/talkdoc/
│   ├── bot.py                    # Pipecat worker + WebRTC pipeline
│   ├── chunking.py               # page-aware PDF extraction/chunking
│   ├── config.py                 # typed environment configuration
│   ├── healthcheck.py            # local service readiness checks
│   ├── ingestion.py              # PDF -> embedding -> Qdrant
│   ├── rag.py                    # retriever / Qdrant adapter
│   ├── processors/
│   │   └── rag_context.py        # transient RAG LLM-context injection
│   └── services/
│       └── speaches_tts.py       # streaming Kokoro/Piper PCM adapter
└── tests/
    └── test_chunking.py
​
5. Docker and environment setup
Copy the environment file and install Python dependencies:
cp .env.example .env
uv sync --dev
​
Start local inference:
docker compose up -d
​
Inspect service startup:
docker compose ps
docker compose logs -f vllm
docker compose logs -f speaches
​
Run the included health check:
uv run talkdoc-health
​
Expected endpoints:
vLLM health:      <http://127.0.0.1:8000/health>
vLLM API:         <http://127.0.0.1:8000/v1>
Speaches health:  <http://127.0.0.1:8001/health>
Speaches API:     <http://127.0.0.1:8001/v1>
​
The supplied vLLM configuration uses:
Qwen/Qwen2.5-7B-Instruct-AWQ
--gpu-memory-utilization 0.80
--max-model-len 8192
--max-num-seqs 8
--enable-prefix-caching
​
These are starter values, not universal optimum values. Reduce VLLM_MAX_MODEL_LEN to 4096 and/or VLLM_GPU_MEMORY_UTILIZATION if your GPU is tight. Raise them only after measuring memory headroom. Keep the conversational response cap small (LLM_MAX_COMPLETION_TOKENS=320) because spoken answers should generally be concise.
If the supplied AWQ model is unsuitable for your GPU, change only these two values together:
VLLM_MODEL=<Hugging-Face-model-id>
LLM_MODEL_NAME=<the-served-name-you-want-Pipecat-to-send>
​
If you choose a non-quantized 7B/8B model, expect significantly more VRAM usage.
6. PDF ingestion and indexing
Place a document in data/documents/, for example:
cp /path/to/manual.pdf data/documents/manual.pdf
​
Index it:
uv run talkdoc-ingest data/documents/manual.pdf --recreate
​
Or:
make ingest PDF=data/documents/manual.pdf
​
-recreate is recommended for this one-document starter. Without it, deterministic point IDs make re-ingesting the exact same PDF idempotent, but an edited PDF with the same filename can leave old points in a shared collection. For a multi-document product, add document IDs/tenants and delete-by-document filters rather than recreating the whole collection.
Ingestion does the following:
PyMuPDF reads page blocks using reading-oriented sorting.
Text is normalized while preserving paragraphs.
Chunks stay inside page boundaries so page provenance is reliable.
Oversized paragraphs are split at sentence boundaries when possible.
BAAI/bge-small-en-v1.5 generates normalized document embeddings.
Qdrant stores cosine vectors plus text, page, source, chunk number, and document SHA-256.
For scanned/image-only PDFs, PyMuPDF text extraction will return little or no useful text. Add an open-source OCR stage such as OCRmyPDF/Tesseract before this ingestion path instead of pretending the parser can recover pixels as text.
7. Run the Pipecat voice application
After both Docker services are healthy and the PDF is indexed:
uv run python -m talkdoc.bot -t webrtc
​
Pipecat's development runner defaults to WebRTC and port 7860. Open:
<http://localhost:7860/client>
​
Allow microphone permission, connect, and ask a question whose answer exists in the PDF.
Example:
User: What does this document say about the retry policy?

Runtime:
Microphone -> Silero/turn detection -> Faster-Whisper -> transcript
-> BGE query embedding -> Qdrant top-k
-> transient grounded context -> vLLM token stream
-> sentence buffer -> Kokoro PCM stream -> WebRTC audio
​
8. Pipecat pipeline implementation
The important part of bot.py is intentionally short:
pipeline = Pipeline(
    [
        transport.input(),
        stt,
        user_aggregator,
        rag,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ]
)
​
Current Pipecat uses PipelineWorker and WorkerRunner in this starter, not old PipelineTask examples.
Silero is configured on LLMUserAggregatorParams. This is intentional in current Pipecat: VAD participates in user-turn management and interruption handling rather than being treated as a random audio filter.
The STT object is:
stt = OpenAISTTService(
    api_key="local-not-a-secret",
    base_url=settings.speaches_base_url,
    settings=OpenAISTTService.Settings(
        model=settings.stt_model,
        language=settings.stt_language,
    ),
    ttfs_p99_latency=settings.stt_ttfs_p99_seconds,
)
​
Despite the class name, this configuration does not call OpenAI. It uses the OpenAI-compatible protocol against 127.0.0.1:8001.
The local vLLM client is analogous:
llm = OpenAILLMService(
    api_key="local-not-a-secret",
    base_url=settings.vllm_base_url,
    settings=OpenAILLMService.Settings(
        model=settings.llm_model_name,
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=settings.llm_temperature,
        max_completion_tokens=settings.llm_max_completion_tokens,
    ),
)
​
vLLM emits OpenAI-compatible streaming chat completions. Pipecat converts streamed output into LLM text frames. Pipecat TTS sentence aggregation then sends a completed sentence to the local TTS adapter instead of waiting for the entire LLM answer.
9. RAG request lifecycle
RAGContextProcessor runs after user aggregation and before the LLM.
For each completed user turn:
final transcript
   -> embedding query
   -> Qdrant query_points(top_k)
   -> score threshold
   -> page-labelled excerpts
   -> transient replacement of latest user message
   -> LLMContextFrame to vLLM
​
If retrieval times out or fails, the processor injects an explicit no_relevant_document_context marker. The system prompt then forces the model to say the document does not provide enough information rather than silently falling back to model memory.
The default BGE query instruction is:
Represent this sentence for searching relevant passages:
​
Tune RAG_TOP_K and RAG_SCORE_THRESHOLD with a real evaluation set; do not treat the supplied 0.55 threshold as universally correct. BGE v1.5 similarity scores are not calibrated probabilities, so ranking quality matters more than the absolute number.
10. Latency optimization order
Optimize based on measured stage latency, not intuition.
Recommended order:
Measure end-of-user-speech -> final STT transcript.
Measure retrieval time.
Measure vLLM time-to-first-token.
Measure first completed sentence time.
Measure TTS time-to-first-audio.
Measure browser playback start.
Practical knobs:
STT
Use faster-distil-whisper-small.en for English-first low latency.
Keep Speaches model TTL at 1 so the model remains warm.
If CPU STT is too slow, move Speaches to its CUDA image only if you have enough VRAM or a second GPU.
Benchmark STT_TTFS_P99_SECONDS on your own machine; Pipecat uses this value in turn timing.
Retrieval
Keep BGE-small on CPU initially.
Keep top_k small, normally 3-6.
Never put synchronous SentenceTransformer inference directly on the asyncio event loop; this repo uses asyncio.to_thread.
For large corpora, add metadata filtering and a reranker rather than increasing top-k indefinitely.
vLLM
Prefer a quantized 7B/8B instruction model for the first local build.
Keep context length only as large as your use case needs.
Keep spoken completions bounded.
Prefix caching helps repeated common prompt prefixes.
Tune GPU-memory utilization with headroom rather than forcing 100% VRAM allocation.
Measure TTFT and decode throughput separately.
TTS
Sentence aggregation is the quality/latency default.
Token-level TTS can lower latency but is usually worse for an HTTP Kokoro endpoint because tiny requests destroy natural phrasing and create request overhead.
The adapter streams each sentence's PCM bytes as they arrive; it does not wait for the complete audio file before sending Pipecat frames.
11. Error handling included
The starter handles or surfaces:
missing/non-PDF paths
PDFs with no extractable text
invalid chunk settings
Qdrant collection creation/recreation
deterministic point IDs
RAG timeouts
RAG exceptions
no relevant RAG results
Speaches TTS non-2xx responses
TTS HTTP timeouts/network errors
arbitrary HTTP chunk boundaries for 16-bit PCM
WebRTC disconnect cancellation
infrastructure health checks
Production systems should additionally add structured metrics/exporters, request IDs, durable session metadata, authentication, authorization, rate limiting, and a privacy/retention policy for transcripts and audio.
12. Scaling path without rewriting the core
Stage A: local workstation
Pipecat process
  + embedded BGE model
  + embedded Qdrant
Docker:
  + vLLM GPU
  + Speaches CPU
​
This is the supplied configuration.
Stage B: multiple Pipecat sessions on one host
Move Qdrant to a standalone server and set:
QDRANT_URL=http://127.0.0.1:6333
​
Keep a process-level embedding model singleton instead of loading one per voice session. The included get_retriever() already caches the retriever once per Python process.
Stage C: multi-host
Separate these responsibilities:
Web/API/session router
       |
       +--> Pipecat worker pool
       |
       +--> shared Qdrant
       |
       +--> vLLM inference replicas
       |
       +--> STT/TTS inference replicas
​
At that point add load-aware routing, model warm pools, health-aware failover, central tracing, and explicit per-session lifecycle management. Do not share embedded Qdrant files between multiple concurrently writing processes.
For browser users over the public internet, replace direct local SmallWebRTC assumptions with production WebRTC signaling/TURN infrastructure or another production-capable transport. The Pipecat development runner is for development, not your production session scheduler.
13. Recommended next upgrades
Implement these in roughly this order:
Add a REST upload endpoint and background ingestion job.
Introduce document_id and filter every Qdrant retrieval by document/user/tenant.
Add hybrid dense + BM25/sparse retrieval.
Add a local cross-encoder reranker for high-value documents.
Add Pipecat eval scenarios for grounded QA, interruption recovery, and latency budgets.
Export Pipecat metrics/OpenTelemetry traces.
Add a custom React/Pipecat client instead of relying on the development /client UI.
Move Qdrant into its own service before multiple bot workers.
Add authentication and per-document ACLs.
Add OCR and layout/table-aware parsing if your PDFs require it.
14. Commands cheat sheet
# One-time
cp .env.example .env
uv sync --dev

# Start local inference
docker compose up -d
uv run talkdoc-health

# Index one PDF
cp /path/to/file.pdf data/documents/file.pdf
uv run talkdoc-ingest data/documents/file.pdf --recreate

# Tests
uv run pytest -q
uv run ruff check src tests

# Run voice app
uv run python -m talkdoc.bot -t webrtc

# Browser UI
# <http://localhost:7860/client>

# Stop inference
docker compose down
​
15. Known trade-offs
Faster-Whisper through the HTTP transcription endpoint is segment-based, not true token-by-token ASR. It is a good first local architecture, but if sub-turn live captions become a requirement, replace only the STT adapter with a realtime local transcription path.
Kokoro HTTP TTS streams bytes, but each request starts at a sentence boundary. This is intentional for intelligibility and simple interruption behavior.
Embedded Qdrant is excellent for the local starter; a shared server is the correct boundary once you scale concurrent processes.
Character-based page-aware chunking is transparent and robust, but a complex legal/scientific PDF may benefit from structure-aware section/table chunking.
An AWQ model lowers VRAM use, but the best quantization/model combination depends on GPU architecture and your accuracy target. Benchmark your actual workload.
