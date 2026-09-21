# LGTM observability overlay for talk-to-doc-local

This overlay is designed to be merged with the existing project `docker-compose.yml`.

## What it collects

- vLLM: request concurrency, queueing, token throughput, TTFT, inter-token latency, KV-cache utilization and request success rate.
- GPU: utilization, VRAM usage, temperature, power and other `nvidia-smi` fields supported by the current driver/GPU.
- Host: CPU, RAM, filesystem, disk, network and load metrics from node-exporter.
- Containers: CPU, memory, filesystem and network metrics from cAdvisor.
- OTLP endpoint: ports 4317/4318 are ready for application traces/logs/metrics later.

## Start

From the project root:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.observability.yml \
  up -d
```

Grafana: http://localhost:3000

Prometheus: http://localhost:9090

Default Grafana credentials are `admin` / `admin` unless you set:

```bash
export GRAFANA_ADMIN_USER=admin
export GRAFANA_ADMIN_PASSWORD='change-me'
```

## Verify scrape targets

```bash
curl http://localhost:8000/metrics | head
curl http://localhost:8001/metrics | head
curl http://localhost:8002/metrics | head
curl http://localhost:9090/api/v1/targets
```

GPU exporter health:

```bash
docker exec talk-to-doc-gpu-exporter nvidia-smi
```

## WSL2 note

`node-exporter` reports the Linux/WSL environment visible to Docker. If you also need native Windows host counters, run `windows_exporter` on Windows and add it as another Prometheus scrape target.

## Optional vLLM traces

vLLM can send OpenTelemetry traces to the LGTM Tempo backend. Add these server flags only if you need traces, because detailed tracing adds overhead:

```text
--otlp-traces-endpoint http://lgtm:4317
--collect-detailed-traces model,worker
```

Add them to each vLLM service command only after the basic metrics stack is working.
