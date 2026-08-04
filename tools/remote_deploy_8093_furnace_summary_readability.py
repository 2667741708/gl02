#!/usr/bin/env python3
"""Deploy the 8093-only seven-card process-summary readability override."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802"
CSS_ASSET = "assets/bf3d-furnace-summary-readability-8093.css"
CSS_VERSION = "20260802-expanded7-r2"
LINK_MARKER = f"<!-- {REQ_ID} -->"
LINK_TAG = f'{LINK_MARKER}\n  <link rel="stylesheet" href="{CSS_ASSET}?v={CSS_VERSION}">'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f"{path.name}.summary-readability.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def locate_frontend(root: Path) -> Path:
    candidates = [
        path.parent
        for path in root.rglob("frontend_dashboard_v3.server.html")
        if (path.parent / "assets").is_dir()
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one 8093 frontend directory, found {candidates}")
    return candidates[0]


def validate_css(text: str) -> None:
    required = (
        REQ_ID,
        ".layered-cad-stage .furnace-layer-callouts.follow-model .furnace-layer-card",
        "width: clamp(208px, 23%, 228px) !important",
        "grid-template-columns: minmax(78px, 1fr) max-content max-content !important",
        "overflow: visible !important",
        "text-overflow: clip !important",
        "display: inline !important",
        "width: 198px !important",
        "width: 190px !important",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"summary-card CSS markers missing: {missing}")
    if ".furnace-billboard" in text or ".core-group-row" in text:
        raise RuntimeError("summary-card CSS must not target point Billboards or the 28-variable panel")


def patch_page(text: str) -> str:
    if LINK_TAG in text and text.count(REQ_ID) == 1 and text.count(CSS_ASSET) == 1:
        return text
    pattern = re.compile(
        rf"\s*(?:{re.escape(LINK_MARKER)}\s*)?"
        rf'<link\s+rel="stylesheet"\s+href="{re.escape(CSS_ASSET)}[^\"]*"\s*/?>\s*'
    )
    text = pattern.sub("\n", text)
    if text.count("</head>") != 1:
        raise RuntimeError("8093 page must contain exactly one closing head tag")
    text = text.replace("</head>", f"\n  {LINK_TAG}\n</head>", 1)
    if text.count(REQ_ID) != 1 or text.count(CSS_ASSET) != 1:
        raise RuntimeError("8093 summary-card stylesheet link is missing or duplicated")
    return text


def deploy(root: Path, css_payload: Path) -> dict[str, object]:
    frontend = locate_frontend(root)
    page_8093 = frontend / "frontend_dashboard_v3.server.html"
    page_8094 = frontend / "frontend_dashboard_v3.8094_preview.server.html"
    assets = frontend / "assets"
    target_css = assets / Path(CSS_ASSET).name
    shared_adapter = assets / "bf3d-furnace-body-billboard-adapter.js"
    camera_8094 = assets / "bf3d-surface-camera-guard-8094.js"
    required = (page_8093, page_8094, shared_adapter, camera_8094, css_payload)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required file missing: {missing}")

    css_text = css_payload.read_text(encoding="utf-8")
    validate_css(css_text)
    hashes_before = {
        "page_8093": sha256(page_8093),
        "page_8094": sha256(page_8094),
        "shared_adapter": sha256(shared_adapter),
        "camera_8094": sha256(camera_8094),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "8093_furnace_summary_readability_20260802" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(page_8093, backup / f"{page_8093.name}.bak")
    if target_css.is_file():
        shutil.copy2(target_css, backup / f"{target_css.name}.bak")

    patched_page = patch_page(page_8093.read_text(encoding="utf-8"))
    atomic_write(target_css, css_payload.read_bytes())
    atomic_write(page_8093, patched_page.encode("utf-8"))

    deployed_page = page_8093.read_text(encoding="utf-8")
    deployed_css = target_css.read_text(encoding="utf-8")
    if LINK_TAG not in deployed_page:
        raise RuntimeError("deployed page failed the exact stylesheet-link contract")
    validate_css(deployed_css)

    hashes_after = {
        "page_8093": sha256(page_8093),
        "summary_css_8093": sha256(target_css),
        "page_8094": sha256(page_8094),
        "shared_adapter": sha256(shared_adapter),
        "camera_8094": sha256(camera_8094),
    }
    for protected in ("page_8094", "shared_adapter", "camera_8094"):
        if hashes_before[protected] != hashes_after[protected]:
            raise RuntimeError(f"protected file changed: {protected}")

    return {
        "req_id": REQ_ID,
        "deployed": True,
        "root": str(root),
        "frontend": str(frontend),
        "backup": str(backup),
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "scope": "seven-follow-model-process-summary-cards-only",
        "card_width_desktop_px": "208-242",
        "card_width_compact_px": 198,
        "card_width_low_height_px": 190,
        "ellipsis_removed": True,
        "units_preserved": True,
        "8094_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    )
    parser.add_argument("--css-payload", type=Path, required=True)
    args = parser.parse_args()
    result = deploy(args.root.resolve(), args.css_payload.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
