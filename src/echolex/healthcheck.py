from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from echolex.config import Settings


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, response.read(500).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(500).decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def main() -> None:
    settings = Settings.from_env()
    checks = {
        "vLLM": settings.vllm_base_url.removesuffix("/v1") + "/health",
        "Speaches": settings.speaches_base_url.removesuffix("/v1") + "/health",
    }
    failed = False
    for name, url in checks.items():
        status, body = _get(url)
        ok = 200 <= status < 300
        print(f"{name:10} {'OK' if ok else 'FAIL':4} HTTP {status} {url}")
        if not ok:
            failed = True
            print(json.dumps({"response": body[:300]}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
