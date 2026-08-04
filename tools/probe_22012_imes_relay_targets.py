"""Read-only reachability probe intended to run on 10.30.220.12."""
from __future__ import annotations

import json
import socket
import time
from datetime import datetime
from urllib.request import Request, urlopen


TARGETS = (
    ("imes_web", "10.10.181.209", 8080),
    ("imes_vastbase", "10.10.181.195", 5432),
    ("pspace", "10.22.181.243", 8889),
)


def tcp_probe(name: str, host: str, port: int, timeout: float = 5.0) -> dict:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok, error = True, None
    except OSError as exc:
        ok, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "name": name,
        "host": host,
        "port": port,
        "tcp_ok": ok,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "error": error,
    }


def main() -> int:
    results = [tcp_probe(*target) for target in TARGETS]
    web = next(item for item in results if item["name"] == "imes_web")
    if web["tcp_ok"]:
        try:
            request = Request("http://10.10.181.209:8080/imes.web/", method="GET")
            with urlopen(request, timeout=8) as response:
                web["http_status"] = response.status
                web["http_url"] = response.geturl()
        except Exception as exc:  # HTTP reachability is supplemental to TCP
            web["http_error"] = f"{type(exc).__name__}: {exc}"
    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "all_tcp_ok": all(item["tcp_ok"] for item in results),
        "targets": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["all_tcp_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
