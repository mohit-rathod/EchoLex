# Local LGTM observability overlay

This Compose overlay adds a local Grafana/Prometheus/Tempo/Loki stack around the inference services and Qdrant. It is intended for development, benchmarking, and single-host operational testing; use your organization's managed/persistent observability platform for a real production environment.

## Collected metrics

- vLLM LLM/STT/TTS request and model-runtime metrics exposed by each service.
- Qdrant service metrics.
- OTLP ports `4317` and `4318` are exposed on localhost for application telemetry you add later.

## Start

Set a non-default Grafana password in `.env`, then run:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.observability.yml \
  up -d
```

Local endpoints:

- Grafana: `http://127.0.0.1:3000`
- Prometheus: `http://127.0.0.1:9090`

The overlay intentionally binds these ports to localhost.

## Verify

```bash
curl -fsS http://127.0.0.1:8000/metrics >/dev/null
curl -fsS http://127.0.0.1:8001/metrics >/dev/null
curl -fsS http://127.0.0.1:8002/metrics >/dev/null
curl -fsS http://127.0.0.1:6333/metrics >/dev/null
curl -fsS http://127.0.0.1:9090/api/v1/targets
```

## Production note

The supplied `grafana/otel-lgtm:latest` image is a convenience development bundle, not a pinned HA production observability deployment. For production, pin approved images/digests and deploy Grafana, Prometheus/Mimir, Loki, and Tempo with persistent storage, authentication, retention policy, backups, and alert routing appropriate to your platform.
