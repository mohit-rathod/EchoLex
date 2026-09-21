from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from echolex.core.config import Settings
from echolex.core.logging import configure_logging


@dataclass(frozen=True, slots=True)
class HealthResult:
    name: str
    ok: bool
    status: int
    target: str
    detail: str = ""


def _get(
    name: str,
    url: str,
    timeout: float,
    *,
    headers: dict[str, str] | None = None,
) -> HealthResult:
    try:
        request = urllib.request.Request(url, method="GET", headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(300).decode("utf-8", errors="replace")
            return HealthResult(name, 200 <= response.status < 300, response.status, url, body)
    except urllib.error.HTTPError as exc:
        body = exc.read(300).decode("utf-8", errors="replace")
        return HealthResult(name, False, exc.code, url, body)
    except Exception as exc:
        return HealthResult(name, False, 0, url, f"{type(exc).__name__}: {exc}")


def _embedded_qdrant_health(settings: Settings) -> HealthResult:
    path = Path(settings.qdrant_path)
    parent = path if path.exists() else path.parent
    ok = parent.exists() and parent.is_dir()
    return HealthResult(
        "Qdrant",
        ok,
        200 if ok else 0,
        str(path),
        "embedded storage path available" if ok else "embedded storage parent does not exist",
    )


def _checks(settings: Settings) -> list[HealthResult]:
    timeout = settings.health_timeout_seconds
    results = [
        _get("LLM", settings.llm_base_url.removesuffix("/v1") + "/health", timeout),
        _get("STT", settings.stt_base_url.removesuffix("/v1") + "/health", timeout),
        _get("TTS", settings.tts_base_url.removesuffix("/v1") + "/health", timeout),
    ]
    if settings.qdrant_url:
        qdrant_headers = (
            {"api-key": settings.qdrant_api_key}
            if settings.qdrant_api_key
            else None
        )
        results.append(
            _get(
                "Qdrant",
                settings.qdrant_url.rstrip("/") + "/readyz",
                timeout,
                headers=qdrant_headers,
            )
        )
    else:
        results.append(_embedded_qdrant_health(settings))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Echolex runtime dependencies.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    settings = Settings.from_env()
    configure_logging(settings)
    results = _checks(settings)

    if args.json:
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False))
    else:
        for result in results:
            state = "OK" if result.ok else "FAIL"
            print(f"{result.name:10} {state:4} HTTP {result.status:<3} {result.target}")
            if not result.ok and result.detail:
                print(f"  {result.detail[:300]}")

    if not all(result.ok for result in results):
        raise SystemExit(1)
