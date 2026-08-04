#!/usr/bin/env python3
"""Serve the GL02 dashboard with an isolated blast-furnace GLB candidate.

The dashboard source and all normal assets are served from ``高炉前端数据``.
Only ``/models/gl02_blast_furnace.glb`` is replaced at request time, so the
production model file is never copied over or modified.
"""

from __future__ import annotations

import argparse
import mimetypes
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRONTEND_ROOT = ROOT / "高炉前端数据"
DEFAULT_MODEL = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / "P60_PREFLIGHT_4K_20260717_R1"
    / "P60_PREFLIGHT_4K_UNCOMPRESSED.glb"
)
MODEL_ROUTE = "/models/gl02_blast_furnace.glb"

mimetypes.add_type("model/gltf-binary", ".glb")


class PreviewHandler(SimpleHTTPRequestHandler):
    """Static handler that aliases only the dashboard furnace-model route."""

    candidate_model: Path

    def _request_path(self) -> str:
        return unquote(urlparse(self.path).path).replace("\\", "/")

    def _send_candidate(self, include_body: bool) -> None:
        size = self.candidate_model.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-BF3D-Preview-Model", self.candidate_model.name)
        self.end_headers()
        if include_body:
            with self.candidate_model.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    self.wfile.write(chunk)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self._request_path() == MODEL_ROUTE:
            self._send_candidate(include_body=True)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if self._request_path() == MODEL_ROUTE:
            self._send_candidate(include_body=False)
            return
        super().do_HEAD()

    def end_headers(self) -> None:
        if self._request_path() != MODEL_ROUTE:
            self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve the dashboard while safely aliasing its furnace GLB."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8094)
    parser.add_argument(
        "--frontend-root",
        type=Path,
        default=DEFAULT_FRONTEND_ROOT,
        help="Directory containing frontend_dashboard_v3.server.html.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help="Isolated GLB candidate served at the production model URL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frontend_root = args.frontend_root.resolve()
    candidate_model = args.model.resolve()
    dashboard = frontend_root / "frontend_dashboard_v3.server.html"
    if not dashboard.is_file():
        raise FileNotFoundError(f"Dashboard not found: {dashboard}")
    if not candidate_model.is_file():
        raise FileNotFoundError(f"Candidate GLB not found: {candidate_model}")

    class BoundPreviewHandler(PreviewHandler):
        pass

    BoundPreviewHandler.candidate_model = candidate_model
    bound_handler = partial(BoundPreviewHandler, directory=str(frontend_root))
    server = ThreadingHTTPServer((args.host, args.port), bound_handler)
    print(
        f"BF3D preview: http://{args.host}:{args.port}/"
        "frontend_dashboard_v3.server.html?ws_port=8767#overview",
        flush=True,
    )
    print(f"Aliased model: {candidate_model}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
