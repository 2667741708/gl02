# -*- coding: utf-8 -*-
"""Lightweight HTTP server for the foreman trend preview page.

Serves static files from a configured frontend directory on a dedicated port.
The page connects to the existing 8768 WebSocket bridge for live sensor data.
"""
from __future__ import annotations

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class ForemanTrendHandler(SimpleHTTPRequestHandler):
    """Serve static files with CORS-friendly headers for the foreman trend page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=300")
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[foreman-trend] {self.client_address[0]} - {format % args}", flush=True)


def main() -> int:
    host = os.environ.get("BF_FOREMAN_HOST", "0.0.0.0")
    port = int(os.environ.get("BF_FOREMAN_PORT", "8892"))
    server = HTTPServer((host, port), ForemanTrendHandler)
    print(f"[foreman-trend] serving {FRONTEND_DIR} on {host}:{port}", flush=True)
    server.serve_forever()
    return 0


FRONTEND_DIR = Path(os.environ.get(
    "BF_FRONTEND_DIR",
    Path(__file__).resolve().parents[1] / "高炉前端数据",
))

if __name__ == "__main__":
    raise SystemExit(main())
