# Echolex local observability

This overlay adds a local Grafana/Prometheus/Tempo/Loki stack plus host and NVIDIA GPU telemetry around the vLLM LLM/STT services, vLLM-Omni TTS service, and Qdrant.

The dashboard is intentionally reliability-first. It distinguishes metrics that are exact at scrape time from latency/request-shape metrics that are aggregated by Prometheus histograms.

## What is collected

### Host / system

Collected by `node_exporter`:

- total, used, and available system RAM;
- RAM used/available percentages;
- CPU utilization percentage;
- effective busy CPU cores and total logical cores;
- Linux load average;
- CPU/hardware temperature sensors when Linux exposes them through `/sys`.

### NVIDIA GPU

Collected by `dcgm-exporter` using `observability/dcgm-counters.csv`:

- VRAM used, free, reserved, total, and utilization percentage;
- GPU utilization;
- compute-engine, tensor-pipe, and DRAM activity when DCGM profiling fields are supported;
- GPU and GPU-memory temperature;
- PCIe RX/TX bandwidth when profiling fields are supported;
- GPU power draw and clocks;
- thermal, power, and reliability throttling counters;
- XID, PCIe replay, ECC, and retired-page health signals when supported.

NVIDIA documents that metric availability depends on the GPU, driver, DCGM version, permissions, and deployment configuration. An `N/A` panel is therefore preferable to inventing a value for an unsupported field.

### Model / inference

Collected from each model server `/metrics` endpoint:

- running and waiting requests;
- request throughput;
- TTFT;
- end-to-end request latency;
- TPOT;
- inter-token latency;
- queue time;
- prefill time;
- decode time;
- inference/RUNNING-phase time;
- prompt and generation token throughput;
- prompt and generation token distributions;
- total prompt and generated tokens;
- KV-cache utilization;
- scheduler preemptions;
- prefix-cache hit ratio;
- waiting reason where the installed vLLM version exports it;
- request finish reasons;
- corrupted/NaN request signals where enabled by vLLM;
- vLLM-Omni TTS audio TTFP, real-time factor, audio duration, underrun, frame throughput, failures, and skipped audio.

## Important: "last served request" semantics

Stock vLLM Prometheus latency and request-shape metrics are histograms/counters. A Prometheus histogram stores cumulative bucket counts, a cumulative sum, and a cumulative count; it does **not** retain the exact value of the last completed request.

For reliability, this dashboard does not fake a last-request value. It uses:

- **recent mean (1 minute)** as the closest stable operational view;
- **rolling mean (5 minutes)** for trend stability;
- **p95/p99** for tail latency;
- exact scrape-time gauges for running requests, waiting requests, KV-cache usage, CPU/GPU utilization, memory, temperatures, and similar gauges.

If literal last-request TTFT/E2E/TPOT/prefill/decode/token count is required, instrument the request path (or a request-aware proxy) to emit request-level events with a request ID, timestamps, model name, prompt/output token counts, and phase durations. Logs/traces are usually a better fit than a long-lived Prometheus gauge for this diagnostic use case.

## Dashboard layout

The provisioned dashboard is **Echolex · Inference & GPU Reliability** and is separated into:

1. Reliability summary
2. Host CPU and memory
3. NVIDIA GPU / VRAM / thermal / PCIe
4. All models combined
5. Per-model latency
6. Per-model queue / prefill / decode
7. Per-model tokens / KV cache / request shape
8. Model reliability / outcomes
9. TTS audio quality

Resource-saturation panels use green / yellow / red semantic thresholds. Latency panels intentionally avoid arbitrary red SLO thresholds because an acceptable TTFT/E2E value is model- and product-specific; set those after the service SLO is agreed.

## Start

Prerequisites:

- Linux or WSL2 with Docker Engine / Docker Compose;
- NVIDIA driver and NVIDIA Container Toolkit for `dcgm-exporter` and the model containers;
- a GPU supported by the chosen DCGM image;
- the existing model and Grafana variables in `.env`.

Run:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.observability.yml \
  up -d
```

Local endpoints:

- Grafana: `http://127.0.0.1:3000`
- Prometheus: `http://127.0.0.1:9090`

The overlay intentionally binds Grafana/Prometheus/OTLP ports to localhost.

## Verify targets

```bash
curl -fsS http://127.0.0.1:8000/metrics >/dev/null
curl -fsS http://127.0.0.1:8001/metrics >/dev/null
curl -fsS http://127.0.0.1:8002/metrics >/dev/null
curl -fsS http://127.0.0.1:6333/metrics >/dev/null
curl -fsS http://127.0.0.1:9090/api/v1/targets
```

From Prometheus, verify these additional targets are `UP`:

```text
node-exporter
dcgm-exporter
```

Useful metric checks:

```text
node_memory_MemTotal_bytes
node_cpu_seconds_total
node_hwmon_temp_celsius
DCGM_FI_DEV_GPU_UTIL
DCGM_FI_DEV_FB_USED
DCGM_FI_DEV_GPU_TEMP
DCGM_FI_PROF_PCIE_RX_BYTES
DCGM_FI_PROF_PCIE_TX_BYTES
vllm:num_requests_running
vllm:kv_cache_usage_perc
vllm:time_to_first_token_seconds_bucket
vllm:e2e_request_latency_seconds_bucket
```

## Platform caveats

- On WSL2 or Docker Desktop, `node_exporter` observes the Linux VM/WSL environment visible to Docker, not necessarily every Windows-host hardware sensor.
- CPU thermal panels can be empty when `/sys/class/hwmon` or `/sys/class/thermal` does not expose CPU sensors to the container.
- PCIe profiling metrics can be empty on unsupported GPU/driver/DCGM combinations.
- Some vLLM metrics are version-dependent. The dashboard uses compatibility queries for counters whose public naming has changed, but panels still show `N/A` when a metric genuinely does not exist in the installed version.

## Additional metrics worth adding at application level

The model dashboard cannot answer the entire user-perceived voice/RAG latency story. For production, add application telemetry for:

- complete voice-turn latency: user stops speaking → first synthesized audio packet;
- STT request latency and audio-duration-normalized RTF;
- retrieval latency, Qdrant query latency, embedding latency, and number of retrieved chunks;
- prompt construction/tokenization time;
- LLM cancellation/timeouts and upstream HTTP error class;
- TTS first-audio and playback-underrun events observed by the client;
- end-to-end request correlation IDs spanning STT → retrieval → LLM → TTS;
- process/container restarts, OOM kills, and model-load/startup duration;
- explicit SLO burn-rate alerts after latency/error SLOs are defined.

## Production note

`grafana/otel-lgtm:latest` is a development convenience bundle, not a pinned HA production observability deployment. For production, pin approved images/digests and use persistent/managed Prometheus or Mimir, Grafana, Loki, Tempo, alert routing, retention policy, backups, and access control appropriate to the platform.
