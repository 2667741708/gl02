#!/usr/bin/env python3
"""Idempotently apply the 8093 HTTP/static-resource stability patch."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


MARKER = "OPS-8093-HTTP-STATIC-STABILITY-20260806-R1"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one old block, found {count}")
    return text.replace(old, new, 1)


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".http_stability.tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    os.replace(temporary, path)


def patch_backend(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    text = replace_once(
        text,
        "class Handler(BaseHTTPRequestHandler):",
        f'''# {MARKER}\nclass BlastFurnaceThreadingHTTPServer(ThreadingHTTPServer):\n'''
        '''    """Threaded server sized for browser cold-start resource bursts."""\n\n'''
        '''    request_queue_size = max(32, int(os.environ.get("BF_8093_HTTP_REQUEST_QUEUE_SIZE", "128")))\n'''
        '''    daemon_threads = True\n'''
        '''    block_on_close = False\n'''
        '''    allow_reuse_address = True\n\n\n'''
        '''class Handler(BaseHTTPRequestHandler):''',
        "server class",
    )
    text = replace_once(
        text,
        "        self.serve_static(parsed.path)\n",
        "        self.serve_static(parsed.path, parsed.query)\n",
        "static query routing",
    )
    text = replace_once(
        text,
        "    def serve_static(self, request_path: str) -> None:\n",
        "    def serve_static(self, request_path: str, request_query: str = \"\") -> None:\n",
        "static signature",
    )
    old_headers = '''        self.send_response(200)\n        self.add_cors()\n        self.send_header("Content-Type", content_type)\n        self.send_header("Cache-Control", "no-store")\n        self.send_header("Content-Length", str(len(data)))\n'''
    new_headers = '''        is_html = target.suffix.lower() == ".html"\n        etag = None\n        if not is_html:\n            stat = target.stat()\n            etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'\n            if self.headers.get("If-None-Match") == etag:\n                self.send_response(304)\n                self.add_cors()\n                self.send_header("ETag", etag)\n                self.send_header("Cache-Control", "public, max-age=300")\n                self.end_headers()\n                return\n        self.send_response(200)\n        self.add_cors()\n        self.send_header("Content-Type", content_type)\n        if is_html:\n            self.send_header("Cache-Control", "no-store")\n        elif any(key in parse_qs(request_query) for key in ("v", "release")):\n            self.send_header("Cache-Control", "public, max-age=31536000, immutable")\n        else:\n            self.send_header("Cache-Control", "public, max-age=300")\n        if etag:\n            self.send_header("ETag", etag)\n        self.send_header("Content-Length", str(len(data)))\n'''
    text = replace_once(text, old_headers, new_headers, "static cache headers")
    text = replace_once(
        text,
        "    server = ThreadingHTTPServer((HOST, PORT), Handler)\n",
        "    server = BlastFurnaceThreadingHTTPServer((HOST, PORT), Handler)\n",
        "server construction",
    )
    atomic_write(path, text)
    return True


def patch_page(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    old = "models/GL02_FURNACE_BODY_R1.glb?t=${Date.now()}"
    new = "models/GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1"
    if old not in text and new in text:
        return False
    text = replace_once(text, old, new, "stable GLB URL")
    atomic_write(path, text)
    return True


def patch_probe(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    old = '    "/assets/bf3d-billboard-adapter.js",'
    new = '    "/assets/bf3d-furnace-body-billboard-adapter.js?v=20260806-local-133-r1",'
    if old not in text and new in text:
        return False
    text = replace_once(text, old, new, "probe adapter path")
    atomic_write(path, text)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    backend = root / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
    page = root / "高炉前端数据" / "frontend_dashboard_v3.server.html"
    probe = root / "tools" / "probe_8093_http_stability.py"
    for required in (backend, page, probe):
        if not required.is_file():
            raise FileNotFoundError(required)
    result = {
        "schema": "ops.8093.http-static-stability-patch.v1",
        "backend_changed": patch_backend(backend),
        "page_changed": patch_page(page),
        "probe_changed": patch_probe(probe),
        "marker": MARKER,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
