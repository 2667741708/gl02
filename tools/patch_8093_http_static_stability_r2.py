#!/usr/bin/env python3
"""Complete and verify the R1 patch after validating both GLB call sites."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def atomic_replace(path: Path, old: str, new: str, expected: int) -> bool:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0 and text.count(new) == expected:
        return False
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} old blocks, found {count}")
    temporary = path.with_name(path.name + ".http_stability_r2.tmp")
    temporary.write_text(text.replace(old, new), encoding="utf-8", newline="")
    os.replace(temporary, path)
    return True


def main() -> int:
    backend = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
    page = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
    probe = ROOT / "tools" / "probe_8093_http_stability.py"
    backend_text = backend.read_text(encoding="utf-8")
    required = (
        "OPS-8093-HTTP-STATIC-STABILITY-20260806-R1",
        "class BlastFurnaceThreadingHTTPServer",
        "request_queue_size = max(32",
        "self.serve_static(parsed.path, parsed.query)",
    )
    missing = [marker for marker in required if marker not in backend_text]
    if missing:
        raise RuntimeError(f"backend patch incomplete: {missing}")
    page_changed = atomic_replace(
        page,
        "models/GL02_FURNACE_BODY_R1.glb?t=${Date.now()}",
        "models/GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1",
        2,
    )
    probe_changed = atomic_replace(
        probe,
        '    "/assets/bf3d-billboard-adapter.js",',
        '    "/assets/bf3d-furnace-body-billboard-adapter.js?v=20260806-local-133-r1",',
        1,
    )
    print(json.dumps({
        "schema": "ops.8093.http-static-stability-patch.v2",
        "backend_verified": True,
        "page_changed": page_changed,
        "probe_changed": probe_changed,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
