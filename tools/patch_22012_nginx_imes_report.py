"""Add the controlled 220.12 reverse proxy for the IMES report application.

Requirement: REQ-IMES-REPORT-22012-PROXY-20260808.

The report application lives at 10.10.181.205:8080 and emits absolute URLs
back to that host.  The dedicated 18084 server therefore proxies the full
application and rewrites those absolute URLs to the VPN-facing endpoint.
The existing 18080 IMES server is intentionally left untouched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


MARKER = "OPS-22012-IMES-REPORT-PROXY-20260808"
LISTEN_TOKEN = "listen 18084;"
UPSTREAM = "http://10.10.181.205:8080"
PUBLIC_BASE = "http://10.30.220.12:18084"


def _block_end(text: str, opening_index: int) -> int:
    brace = text.find("{", opening_index)
    if brace < 0:
        raise ValueError("找不到 http 块的开始括号")
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("http 块括号不完整")


def _http_block_bounds(text: str) -> tuple[int, int]:
    token = "http {"
    start = text.find(token)
    if start < 0:
        raise ValueError("找不到 nginx http 块")
    return start, _block_end(text, start)


def _required_tokens() -> tuple[str, ...]:
    return (
        MARKER,
        LISTEN_TOKEN,
        f"proxy_pass {UPSTREAM};",
        "sub_filter_once off;",
        f"sub_filter '{UPSTREAM}' '{PUBLIC_BASE}';",
        "proxy_set_header Accept-Encoding \"\";",
    )


def patch_nginx_config(text: str) -> tuple[str, bool]:
    """Add the idempotent 18084 report server to an explicit nginx config."""

    if MARKER in text:
        missing = [token for token in _required_tokens() if token not in text]
        if missing:
            raise ValueError(f"已有报表代理标记但配置不完整：{missing}")
        return text, False
    if LISTEN_TOKEN in text:
        raise ValueError("listen 18084 已存在其他配置，拒绝覆盖")

    newline = "\r\n" if "\r\n" in text else "\n"
    _, http_end = _http_block_bounds(text)
    block_lines = [
        f"    # {MARKER}",
        "    server {",
        "        listen 18084;",
        "        server_name 0.0.0.0;",
        "",
        "        # The report emits absolute URLs to the source host; rewrite them",
        "        # so every browser request stays on the VPN-facing relay.",
        "        location / {",
        f"            proxy_pass {UPSTREAM};",
        "            proxy_http_version 1.1;",
        "            proxy_set_header Host 10.10.181.205:8080;",
        "            proxy_set_header X-Real-IP $remote_addr;",
        "            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "            proxy_set_header X-Forwarded-Proto $scheme;",
        "            proxy_set_header X-Forwarded-Host $http_host;",
        "            proxy_set_header X-Forwarded-Port $server_port;",
        "            proxy_set_header Accept-Encoding \"\";",
        "            proxy_connect_timeout 15s;",
        "            proxy_read_timeout 120s;",
        "            proxy_send_timeout 120s;",
        f"            proxy_redirect {UPSTREAM}/ {PUBLIC_BASE}/;",
        "            sub_filter_once off;",
        f"            sub_filter 'http://10.10.181.205:8080' 'http://10.30.220.12:18084';",
        "            sub_filter_types text/css application/javascript application/x-javascript application/json;",
        "        }",
        "    }",
        "",
    ]
    block = newline.join(block_lines)
    patched = text[:http_end] + newline + block + text[http_end:]
    return patched, True


def main() -> int:
    parser = argparse.ArgumentParser(description="为220.12 Nginx增加IMES报表受控反向代理。")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    original = args.config.read_text(encoding="utf-8")
    patched, changed = patch_nginx_config(original)
    if changed:
        args.config.write_text(patched, encoding="utf-8", newline="")
    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "config": str(args.config),
                "marker": MARKER,
                "listen": "10.30.220.12:18084",
                "upstream": "10.10.181.205:8080",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
