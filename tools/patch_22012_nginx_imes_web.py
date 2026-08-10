"""Patch the existing 220.12 Nginx 18080 server for direct IMES Web access.

Requirement: OPS-22012-DIRECT-SOURCE-RELAYS-20260805.
The patch keeps the existing g13 static site available at ``/g13.html`` while
making the port root redirect to ``/imes.web/`` and proxying that path to the
fixed IMES Web upstream.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


MARKER = "OPS-22012-IMES-WEB-PROXY-20260805"
LISTEN_TOKEN = "listen 18080;"
UPSTREAM = "http://10.10.181.209:8080"


def _server_block_bounds(text: str, token_index: int) -> tuple[int, int]:
    """Return the enclosing ``server { ... }`` bounds for a listen token."""

    start = text.rfind("server {", 0, token_index)
    if start < 0:
        raise ValueError("找不到 listen 18080 所属的 server 块")
    brace = text.find("{", start)
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise ValueError("listen 18080 的 server 块括号不完整")


def patch_nginx_config(text: str) -> tuple[str, bool]:
    """Add the bounded IMES locations and return ``(text, changed)``."""

    if text.count(LISTEN_TOKEN) != 1:
        raise ValueError("nginx.conf 必须且只能包含一个 listen 18080;")
    if MARKER in text:
        required = (
            "location = /imes.web",
            "location ^~ /imes.web/",
            f"proxy_pass {UPSTREAM};",
            "return 302 /imes.web/;",
        )
        missing = [item for item in required if item not in text]
        if missing:
            raise ValueError(f"已有标记但配置不完整：{missing}")
        return text, False

    newline = "\r\n" if "\r\n" in text else "\n"
    listen_index = text.index(LISTEN_TOKEN)
    server_start, server_end = _server_block_bounds(text, listen_index)
    server_text = text[server_start:server_end]
    location_token = "        location / {"
    location_index = server_text.find(location_token)
    if location_index < 0:
        raise ValueError("18080 server 块中找不到既有 location /，拒绝盲目修改")

    block_lines = [
        f"        # {MARKER}",
        "        location = / {",
        "            return 302 /imes.web/;",
        "        }",
        "",
        "        location = /imes.web {",
        "            return 302 /imes.web/;",
        "        }",
        "",
        "        location ^~ /imes.web/ {",
        f"            proxy_pass {UPSTREAM};",
        "            proxy_http_version 1.1;",
        "            proxy_set_header Host $http_host;",
        "            proxy_set_header X-Real-IP $remote_addr;",
        "            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "            proxy_set_header X-Forwarded-Proto $scheme;",
        "            proxy_set_header X-Forwarded-Host $http_host;",
        "            proxy_set_header X-Forwarded-Port $server_port;",
        "            proxy_connect_timeout 15s;",
        "            proxy_read_timeout 120s;",
        "            proxy_send_timeout 120s;",
        "            proxy_redirect default;",
        "        }",
        "",
    ]
    block = newline.join(block_lines)
    absolute_insert = server_start + location_index
    patched = text[:absolute_insert] + block + text[absolute_insert:]
    return patched, True


def main() -> int:
    """Patch one explicit Nginx config and emit a non-secret JSON result."""

    parser = argparse.ArgumentParser(description="为220.12 Nginx 18080增加IMES Web受控反向代理。")
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
                "upstream": UPSTREAM,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
