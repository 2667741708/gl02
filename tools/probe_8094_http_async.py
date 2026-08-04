from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


url = sys.argv[1] if len(sys.argv) > 1 else "http://10.30.220.12:8094/"
output = Path(sys.argv[2] if len(sys.argv) > 2 else "logs/8094_http_probe.json")
started = time.monotonic()
result: dict[str, object] = {
    "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "url": url,
    "status": None,
    "bytes": None,
    "seconds": None,
    "has_viewport_fit_r5": False,
    "error": "",
}
try:
    response = requests.get(url, timeout=60)
    result.update(
        {
            "status": response.status_code,
            "bytes": len(response.content),
            "seconds": round(time.monotonic() - started, 3),
            "has_viewport_fit_r5": b"20260726-viewport-fit-r5" in response.content,
        }
    )
except Exception as exc:
    result["seconds"] = round(time.monotonic() - started, 3)
    result["error"] = f"{type(exc).__name__}: {exc}"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
