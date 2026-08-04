#!/usr/bin/env python3
"""Serve the isolated GL02 V5 material/structure review page.

Requirement:
    REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720

Input:
    A fixed allow-list rooted at ``高炉前端数据`` and the SHA-locked
    ``models/gl02_blast_furnace_review.v5.glb``.

Output:
    A localhost-only, read-only HTTP server.  It does not expose the
    production dashboard, production 3D controller, formal GLB, APIs,
    directories, uploads, or write methods.

Exit codes:
    0: clean shutdown or ``--check-only`` passed.
    2: asset/hash/argument/startup contract failed.
    130: interrupted by Ctrl+C.
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


REQUIREMENT_ID = "REQ-BF3D-R2V-ISOLATED-WEB-REVIEW-20260720"
EXPECTED_REVIEW_SHA256 = (
    "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c"
)
EXPECTED_REVIEW_BYTES = 4_663_220
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = WORKSPACE_ROOT / "高炉前端数据"
REVIEW_ASSET = FRONTEND_ROOT / "models" / "gl02_blast_furnace_review.v5.glb"

ROUTES = {
    "/bf3d_review_v5.server.html": FRONTEND_ROOT / "bf3d_review_v5.server.html",
    "/assets/bf3d-review-renderer-v5.js": (
        FRONTEND_ROOT / "assets" / "bf3d-review-renderer-v5.js"
    ),
    "/assets/bf3d-review-renderer.css": (
        FRONTEND_ROOT / "assets" / "bf3d-review-renderer.css"
    ),
    "/models/gl02_blast_furnace_review.v5.glb": REVIEW_ASSET,
    "/libs/three/three.module.js": FRONTEND_ROOT / "libs" / "three" / "three.module.js",
    "/libs/three/controls/OrbitControls.js": (
        FRONTEND_ROOT / "libs" / "three" / "controls" / "OrbitControls.js"
    ),
    "/libs/three/loaders/GLTFLoader.js": (
        FRONTEND_ROOT / "libs" / "three" / "loaders" / "GLTFLoader.js"
    ),
    "/libs/three/lights/RectAreaLightUniformsLib.js": (
        FRONTEND_ROOT
        / "libs"
        / "three"
        / "lights"
        / "RectAreaLightUniformsLib.js"
    ),
    "/libs/three/utils/BufferGeometryUtils.js": (
        FRONTEND_ROOT / "libs" / "three" / "utils" / "BufferGeometryUtils.js"
    ),
}

MIME_OVERRIDES = {
    ".css": "text/css; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 for one file without modifying it."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_contract() -> dict[str, object]:
    """Validate every allow-listed source and the immutable review GLB."""

    missing = [
        str(path.relative_to(WORKSPACE_ROOT))
        for path in ROUTES.values()
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"审查服务器缺少允许资源：{missing}")

    actual_bytes = REVIEW_ASSET.stat().st_size
    actual_sha256 = sha256_file(REVIEW_ASSET)
    if (
        actual_bytes != EXPECTED_REVIEW_BYTES
        or actual_sha256 != EXPECTED_REVIEW_SHA256
    ):
        raise RuntimeError(
            "review.v5 资产合同不匹配："
            f"bytes={actual_bytes}/{EXPECTED_REVIEW_BYTES}, "
            f"sha256={actual_sha256}/{EXPECTED_REVIEW_SHA256}"
        )
    return {
        "ok": True,
        "schema_version": "bf3d.review_server_contract.v1",
        "requirement_id": REQUIREMENT_ID,
        "workspace_root": str(WORKSPACE_ROOT),
        "document": "高炉前端数据/bf3d_review_v5.server.html",
        "review_asset": {
            "path": "高炉前端数据/models/gl02_blast_furnace_review.v5.glb",
            "bytes": actual_bytes,
            "sha256": actual_sha256,
        },
        "allow_list_count": len(ROUTES),
        "production_page_exposed": False,
        "production_controller_exposed": False,
        "formal_glb_exposed": False,
        "write_methods_supported": False,
    }


class ReviewRequestHandler(BaseHTTPRequestHandler):
    """Serve only the explicit isolated-review allow-list."""

    protocol_version = "HTTP/1.1"
    server_version = "BF3DReview/1.0"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler contract
        self._serve(send_body=False)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler contract
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler contract
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler contract
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        payload = b"read-only review server"
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
            self.send_header("Location", "/bf3d_review_v5.server.html")
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
        self.send_header("Content-Type", content_type or "application/octet-stream")
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
            "script-src 'self' 'sha256-TcQPk9JehBWochQMEsoMOpCv/fzNPs4ICSJkRIUXGII='; "
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


class ReviewHttpServer(ThreadingHTTPServer):
    """Threaded localhost server whose worker threads never block shutdown."""

    daemon_threads = True
    allow_reuse_address = True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动 GL02 V5 独立、只读、SHA 锁定的材质/结构审查页。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python tools/serve_bf3d_review.py --check-only\n"
            "  python tools/serve_bf3d_review.py --port 8125\n"
            "  python tools/serve_bf3d_review.py --port 0 --quiet\n\n"
            "输出：启动时打印一行 JSON，包含实际 localhost URL 与资产 SHA。\n"
            "错误码：0=成功，2=合同/参数/启动失败，130=Ctrl+C。"
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址；为保持隔离只允许 127.0.0.1 或 localhost。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8125,
        help="监听端口，默认 8125；0 表示让操作系统分配空闲端口。",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不打印逐请求日志；启动 JSON 仍会输出。",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只核验 allow-list 与 review.v5 SHA，不启动服务。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host not in LOOPBACK_HOSTS:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "为保持生产隔离，--host 只允许 127.0.0.1 或 localhost",
                },
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
                {"ok": False, "error": str(error), "requirement_id": REQUIREMENT_ID},
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
        server = ReviewHttpServer((bind_host, args.port), ReviewRequestHandler)
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
        "event": "bf3d_review_server_ready",
        "host": actual_host,
        "port": actual_port,
        "url": f"http://{actual_host}:{actual_port}/bf3d_review_v5.server.html",
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
