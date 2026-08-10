#!/usr/bin/env python3
"""Read-only HTTP stability probe for the 8093 production page.

The probe deliberately uses a small browser-like burst so that a single
successful curl cannot hide listener backlog or connection-reset problems.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass


DEFAULT_PATHS = (
    "/",
    "/frontend_dashboard_v3.server.html?ws_port=8768",
    "/assets/bf-diagnosis-review-local.css?v=20260806-core19-r10-foreman-knowledge",
    "/assets/bf-diagnosis-manual-score-local.css?v=20260806-core19-r10-foreman-knowledge",
    "/assets/bf3d-furnace-body-billboard-adapter.js?v=20260806-local-133-r1",
    "/assets/bf3d-tooltip-stable-hover-8093.js",
    "/models/GL02_FURNACE_BODY_R1.glb",
    "/api/ollama/status",
    "/api/automation/status",
    "/api/qa/mcp/health",
)


@dataclass
class Result:
    round: int
    path: str
    ok: bool
    status: int | None
    bytes: int
    elapsed_ms: float
    sha256: str | None
    error: str | None


def fetch(opener: urllib.request.OpenerDirector, base_url: str, path: str, round_no: int, timeout: float) -> Result:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "bf-8093-stability-probe/1"})
        with opener.open(request, timeout=timeout) as response:
            data = response.read()
            status = int(response.status)
        return Result(
            round=round_no,
            path=path,
            ok=status == 200 and bool(data),
            status=status,
            bytes=len(data),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            sha256=hashlib.sha256(data).hexdigest().upper() if data else None,
            error=None if data else "EMPTY_BODY",
        )
    except Exception as exc:  # diagnostic boundary
        return Result(
            round=round_no,
            path=path,
            ok=False,
            status=getattr(exc, "code", None),
            bytes=0,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            sha256=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results: list[Result] = []
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        for round_no in range(1, max(1, args.rounds) + 1):
            futures = [
                pool.submit(fetch, opener, args.base_url, path, round_no, args.timeout)
                for path in DEFAULT_PATHS
            ]
            results.extend(future.result() for future in futures)

    successes = sum(item.ok for item in results)
    payload = {
        "schema": "ops.8093.http-stability-probe.v1",
        "base_url": args.base_url,
        "rounds": args.rounds,
        "concurrency": args.concurrency,
        "request_count": len(results),
        "success_count": successes,
        "failure_count": len(results) - successes,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "complete": successes == len(results),
        "results": [asdict(item) for item in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
