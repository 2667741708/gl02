#!/usr/bin/env python3
"""Serve the R2X 1K AO representative from a strict localhost allow-list.

Requirement:
    REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720

The server exposes only the isolated R2X page, its owned renderer, the shared
review CSS, the SHA-locked v5payload candidate, and the exact Three r160
modules required by GLTFLoader. It supports GET/HEAD only.

Exit codes:
    0: check-only passed or server stopped cleanly.
    2: contract, argument, or bind failure.
    130: interrupted with Ctrl+C.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIREMENT_ID = "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720"
STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE"
EXPECTED_CANDIDATE_SHA256 = (
    "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00"
)
EXPECTED_CANDIDATE_BYTES = 1_115_216
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = WORKSPACE_ROOT / "高炉前端数据"
STAGE_ROOT = (
    WORKSPACE_ROOT
    / "PT"
    / "高炉3D模型"
    / "work"
    / STAGE_ID
)
CANDIDATE = (
    STAGE_ROOT
    / "glb"
    / "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
)

ROUTES = {
    "/bf3d_review_r2x.server.html": FRONTEND_ROOT
    / "bf3d_review_r2x.server.html",
    "/assets/bf3d-review-renderer-r2x.js": FRONTEND_ROOT
    / "assets"
    / "bf3d-review-renderer-r2x.js",
    "/assets/bf3d-review-renderer.css": FRONTEND_ROOT
    / "assets"
    / "bf3d-review-renderer.css",
    (
        "/r2x/"
        "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb"
    ): CANDIDATE,
    "/libs/three/three.module.js": FRONTEND_ROOT
    / "libs"
    / "three"
    / "three.module.js",
    "/libs/three/controls/OrbitControls.js": FRONTEND_ROOT
    / "libs"
    / "three"
    / "controls"
    / "OrbitControls.js",
    "/libs/three/loaders/GLTFLoader.js": FRONTEND_ROOT
    / "libs"
    / "three"
    / "loaders"
    / "GLTFLoader.js",
    "/libs/three/lights/RectAreaLightUniformsLib.js": FRONTEND_ROOT
    / "libs"
    / "three"
    / "lights"
    / "RectAreaLightUniformsLib.js",
    "/libs/three/utils/BufferGeometryUtils.js": FRONTEND_ROOT
    / "libs"
    / "three"
    / "utils"
    / "BufferGeometryUtils.js",
}

MIME_OVERRIDES = {
    ".css": "text/css; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 without modifying the file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_contract() -> dict[str, object]:
    """Validate the allow-list and immutable candidate lock."""

    missing = [
        str(path.relative_to(WORKSPACE_ROOT))
        for path in ROUTES.values()
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"R2X server allow-list files missing: {missing}")
    actual_bytes = CANDIDATE.stat().st_size
    actual_sha256 = sha256_file(CANDIDATE)
    if (
        actual_bytes != EXPECTED_CANDIDATE_BYTES
        or actual_sha256 != EXPECTED_CANDIDATE_SHA256
    ):
        raise RuntimeError(
            "R2X v5payload contract mismatch: "
            f"bytes={actual_bytes}/{EXPECTED_CANDIDATE_BYTES}, "
            f"sha256={actual_sha256}/{EXPECTED_CANDIDATE_SHA256}"
        )
    return {
        "ok": True,
        "schema_version": "bf3d.r2x.review_server_contract.v1",
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "workspace_root": str(WORKSPACE_ROOT),
        "document": "高炉前端数据/bf3d_review_r2x.server.html",
        "candidate": {
            "path": (
                "PT/高炉3D模型/work/"
                f"{STAGE_ID}/glb/"
                "gl02_blast_furnace_material_review."
                "r2x-ao-smoke1k.v5payload.glb"
            ),
            "bytes": actual_bytes,
            "sha256": actual_sha256,
        },
        "allow_list_count": len(ROUTES),
        "production_page_exposed": False,
        "production_controller_exposed": False,
        "formal_glb_exposed": False,
        "v5_glb_exposed": False,
        "old_r2x_candidate_exposed": False,
        "write_methods_supported": False,
        "representative_only": True,
    }


class R2XRequestHandler(BaseHTTPRequestHandler):
    """Serve only explicit R2X isolated-review resources."""

    protocol_version = "HTTP/1.1"
    server_version = "BF3DR2XReview/1.0"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(send_body=False)

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        payload = b"read-only R2X review server"
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _serve(self, *, send_body: bool) -> None:
        try:
            pathname = unquote(urlsplit(self.path).path)
        except (UnicodeDecodeError, ValueError):
            self.send_error(HTTPStatus.BAD_REQUEST, "bad request")
            return
        if pathname == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/bf3d_review_r2x.server.html")
            self.send_header("Content-Length", "0")
            self._security_headers()
            self.end_headers()
            return
        target = ROUTES.get(pathname)
        if target is None:
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            payload = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "read failed")
            return
        content_type = MIME_OVERRIDES.get(target.suffix.lower())
        if not content_type:
            content_type = mimetypes.guess_type(target.name)[0]
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", content_type or "application/octet-stream"
        )
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Accept-Ranges", "none")
        self._security_headers()
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' "
            "'sha256-TcQPk9JehBWochQMEsoMOpCv/fzNPs4ICSJkRIUXGII='; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' blob:; "
            "font-src 'self'; "
            "worker-src 'none'; "
            "object-src 'none'; "
            "frame-src 'none'; "
            "base-uri 'self'; "
            "form-action 'none'",
        )

    def log_message(self, format_string: str, *args: object) -> None:
        if not getattr(self.server, "quiet", False):
            super().log_message(format_string, *args)


class R2XHttpServer(ThreadingHTTPServer):
    """Threaded localhost server with daemon request workers."""

    daemon_threads = True
    allow_reuse_address = True


def build_parser() -> argparse.ArgumentParser:
    """Build the documented R2X server CLI."""

    parser = argparse.ArgumentParser(
        description="启动 GL02 R2X 1K AO 隔离代表审查页。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python tools/serve_bf3d_review_r2x.py --check-only\n"
            "  python tools/serve_bf3d_review_r2x.py --port 8126\n"
            "  python tools/serve_bf3d_review_r2x.py --port 0 --quiet\n\n"
            "只允许 localhost；只暴露新 v5payload 候选。\n"
            "错误码：0=成功，2=合同/参数/启动失败，130=Ctrl+C。"
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="只允许 127.0.0.1 或 localhost。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8126,
        help="监听端口，默认 8126；0 表示分配空闲端口。",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="关闭逐请求日志；启动合同仍输出。",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只核验 allow-list 和 v5payload SHA，不启动服务。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate arguments, then check or serve the R2X allow-list."""

    args = build_parser().parse_args(argv)
    if args.host not in LOOPBACK_HOSTS:
        print(
            json.dumps(
                {"ok": False, "error": "--host 只允许 localhost"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    if not 0 <= args.port <= 65535:
        print(
            json.dumps(
                {"ok": False, "error": "--port 必须在 0..65535"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        contract = validate_contract()
    except (OSError, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "requirement_id": REQUIREMENT_ID,
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    if args.check_only:
        print(json.dumps(contract, ensure_ascii=False))
        return 0
    bind_host = "127.0.0.1" if args.host == "localhost" else args.host
    try:
        server = R2XHttpServer((bind_host, args.port), R2XRequestHandler)
    except OSError as error:
        print(
            json.dumps(
                {"ok": False, "error": f"监听失败：{error}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    server.quiet = args.quiet
    actual_host, actual_port = server.server_address
    ready = {
        **contract,
        "event": "bf3d_r2x_review_server_ready",
        "host": actual_host,
        "port": actual_port,
        "url": f"http://{actual_host}:{actual_port}/bf3d_review_r2x.server.html",
    }
    print(json.dumps(ready, ensure_ascii=False), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
