#!/usr/bin/env python3
"""Add the production-safe HTML rewrite without changing the active page manifest."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
MARKER = "OPS-8093-STABLE-GLB-URL-REWRITE-20260806-R1"


def main() -> int:
    text = BACKEND.read_text(encoding="utf-8")
    if MARKER in text:
        changed = False
    else:
        old = '    text = data.decode("utf-8", errors="replace")\n    injections = []\n'
        new = (
            '    text = data.decode("utf-8", errors="replace")\n'
            f'    # {MARKER}\n'
            '    text = text.replace(\n'
            '        "models/GL02_FURNACE_BODY_R1.glb?t=${Date.now()}",\n'
            '        "models/GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1",\n'
            '    )\n'
            '    injections = []\n'
        )
        if text.count(old) != 1:
            raise RuntimeError(f"expected one HTML decode block, found {text.count(old)}")
        temporary = BACKEND.with_name(BACKEND.name + ".http_stability_r3.tmp")
        temporary.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")
        os.replace(temporary, BACKEND)
        changed = True
    print(json.dumps({
        "schema": "ops.8093.http-static-stability-patch.v3",
        "backend_changed": changed,
        "marker": MARKER,
        "production_page_file_change_required": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
