#!/usr/bin/env python3
"""Read-only HTTP audit of 8093 remote assets against local workspace files."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ASSETS = {
    "page": ("", "高炉前端数据/frontend_dashboard_v3.server.html"),
    "camera_8093": (
        "assets/bf3d-surface-camera-guard-8093.js",
        "高炉前端数据/assets/bf3d-surface-camera-guard-8093.js",
    ),
    "physical_filter_8093": (
        "assets/bf3d-physical-point-filter-8093.js",
        "高炉前端数据/assets/bf3d-physical-point-filter-8093.js",
    ),
    "stable_hover_8093": (
        "assets/bf3d-tooltip-stable-hover-8093.js",
        "高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js",
    ),
    "summary_css_8093": (
        "assets/bf3d-furnace-summary-readability-8093.css",
        "高炉前端数据/assets/bf3d-furnace-summary-readability-8093.css",
    ),
    "shared_adapter": (
        "assets/bf3d-furnace-body-billboard-adapter.js",
        "高炉前端数据/assets/bf3d-furnace-body-billboard-adapter.js",
    ),
    "model_web_alias": (
        "models/gl02_blast_furnace.glb",
        "高炉前端数据/models/gl02_blast_furnace.glb",
    ),
    "model_controlled_master": (
        "models/gl02_blast_furnace.glb",
        "PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/GL02_FURNACE_BODY_R1.glb",
    ),
}

PAGE_MARKERS = (
    "bf3d-furnace-body-billboard-adapter.js",
    "bf3d-physical-point-filter-8093.js",
    "bf3d-surface-camera-guard-8093.js",
    "bf3d-tooltip-stable-hover-8093.js",
    "bf3d-furnace-summary-readability-8093.css",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://10.30.220.12:8093/")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    remote_paths = sorted({remote for remote, _ in ASSETS.values()})
    remote_data: dict[str, bytes] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(remote_paths)) as pool:
        futures = {
            pool.submit(fetch, args.base_url.rstrip("/") + "/" + remote, args.timeout): remote
            for remote in remote_paths
        }
        for future in as_completed(futures):
            remote = futures[future]
            try:
                remote_data[remote] = future.result()
            except Exception as error:  # pragma: no cover - network evidence
                errors[remote] = f"{type(error).__name__}: {error}"

    rows: dict[str, dict[str, object]] = {}
    for name, (remote_path, local_relative) in ASSETS.items():
        local_path = workspace / local_relative
        local_bytes = local_path.read_bytes() if local_path.is_file() else None
        remote_bytes = remote_data.get(remote_path)
        rows[name] = {
            "remote_path": remote_path or "/",
            "local_path": local_relative,
            "local_exists": local_bytes is not None,
            "local_bytes": len(local_bytes) if local_bytes is not None else None,
            "remote_bytes": len(remote_bytes) if remote_bytes is not None else None,
            "local_sha256": digest(local_bytes) if local_bytes is not None else None,
            "remote_sha256": digest(remote_bytes) if remote_bytes is not None else None,
            "identical": local_bytes is not None and remote_bytes is not None and local_bytes == remote_bytes,
            "remote_error": errors.get(remote_path),
        }

    remote_page = remote_data.get("")
    local_page_path = workspace / ASSETS["page"][1]
    local_page = local_page_path.read_bytes() if local_page_path.is_file() else b""
    remote_page_text = remote_page.decode("utf-8", errors="replace") if remote_page else ""
    local_page_text = local_page.decode("utf-8", errors="replace")
    result = {
        "schema": "audit.8093.remote-local-parity.v1",
        "base_url": args.base_url,
        "all_remote_reads_ok": not errors,
        "all_code_identical": all(
            rows[name]["identical"]
            for name in (
                "camera_8093",
                "physical_filter_8093",
                "stable_hover_8093",
                "summary_css_8093",
                "shared_adapter",
            )
        ),
        "page_identical": rows["page"]["identical"],
        "controlled_model_identical": rows["model_controlled_master"]["identical"],
        "web_alias_model_identical": rows["model_web_alias"]["identical"],
        "page_markers": {
            marker: {
                "local": marker in local_page_text,
                "remote": marker in remote_page_text,
            }
            for marker in PAGE_MARKERS
        },
        "assets": rows,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
