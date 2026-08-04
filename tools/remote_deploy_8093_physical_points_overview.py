#!/usr/bin/env python3
"""Deploy the 8093 physical-100-point and overview-only camera runtime.

REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801

Run this script on 10.30.220.12 after both JavaScript payloads have been
uploaded.  It discovers the V4 frontend directory from the page filename,
backs up every replaced 8093 file, writes atomically, and proves the 8094 page,
shared Billboard adapter and 8094 camera runtime were not changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801"
FILTER_ASSET = "assets/bf3d-physical-point-filter-8093.js"
FILTER_VERSION = "20260801-measured121-r2"
CAMERA_ASSET = "assets/bf3d-surface-camera-guard-8093.js"
CAMERA_VERSION = "20260802-overview-closer-r1"
FILTER_MARKER = "<!-- 8093-only measured 121-point runtime; 12 abstract/summary variables stay in side panels -->"
FILTER_TAG = (
    f'{FILTER_MARKER}\n'
    f'<script type="module" src="{FILTER_ASSET}?v={FILTER_VERSION}"></script>'
)
CAMERA_TAG = f'<script type="module" src="{CAMERA_ASSET}?v={CAMERA_VERSION}"></script>'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f"{path.name}.measured121.tmp")
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


def patch_page(text: str) -> str:
    adapter_pattern = re.compile(
        r'<script\s+type="module"\s+src="assets/bf3d-furnace-body-billboard-adapter\.js[^\"]*"\s*></script>'
    )
    adapter_match = adapter_pattern.search(text)
    if not adapter_match:
        raise RuntimeError("8093 shared Billboard adapter tag is missing")

    filter_pattern = re.compile(
        rf'(?:{re.escape(FILTER_MARKER)}\s*)?'
        rf'<script\s+type="module"\s+src="{re.escape(FILTER_ASSET)}[^\"]*"\s*></script>'
    )
    if filter_pattern.search(text):
        text = filter_pattern.sub(FILTER_TAG, text, count=1)
    else:
        text = text[: adapter_match.end()] + "\n  " + FILTER_TAG + text[adapter_match.end() :]

    camera_pattern = re.compile(
        rf'<script\s+type="module"\s+src="{re.escape(CAMERA_ASSET)}[^\"]*"\s*></script>'
    )
    text, camera_replacements = camera_pattern.subn(CAMERA_TAG, text, count=1)
    if camera_replacements != 1:
        raise RuntimeError("8093 camera runtime tag is missing or duplicated")

    if "bf3d-billboard-focus-guard-8095.js" in text:
        raise RuntimeError("8093 page unexpectedly loads the 8095 focus runtime")
    if text.count(FILTER_ASSET) != 1 or text.count(CAMERA_ASSET) != 1:
        raise RuntimeError("8093 point/camera runtime tags are duplicated")
    if text.index(FILTER_ASSET) > text.index(CAMERA_ASSET):
        raise RuntimeError("physical point filter must load before the camera guard")
    return text


def deploy(root: Path, filter_payload: Path, camera_payload: Path) -> dict[str, object]:
    frontend = locate_frontend(root)
    page_8093 = frontend / "frontend_dashboard_v3.server.html"
    page_8094 = frontend / "frontend_dashboard_v3.8094_preview.server.html"
    assets = frontend / "assets"
    target_filter = assets / "bf3d-physical-point-filter-8093.js"
    target_camera = assets / "bf3d-surface-camera-guard-8093.js"
    shared_adapter = assets / "bf3d-furnace-body-billboard-adapter.js"
    camera_8094 = assets / "bf3d-surface-camera-guard-8094.js"
    required = (
        page_8093,
        page_8094,
        shared_adapter,
        camera_8094,
        filter_payload,
        camera_payload,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required file missing: {missing}")

    filter_text = filter_payload.read_text(encoding="utf-8")
    camera_text = camera_payload.read_text(encoding="utf-8")
    for marker in (
        "bf3d.measured-point-filter.8093.v2",
        "visible: 121",
        "excluded: 12",
        "viewer.billboardEntries.splice",
    ):
        if marker not in filter_text:
            raise RuntimeError(f"physical-point payload marker missing: {marker}")
    for marker in (
        "bf3d.camera.overview-only.8093.v4",
        "pointFocusEnabled: false",
        "fullOrbitRadius",
        "OVERVIEW_FIT_MARGIN = 1.0",
        "OVERVIEW_ORBIT_MARGIN = 1.12",
        "viewer.controls.minAzimuthAngle = -Infinity",
        "viewer.controls.maxAzimuthAngle = Infinity",
    ):
        if marker not in camera_text:
            raise RuntimeError(f"overview camera payload marker missing: {marker}")
    for forbidden in ("focusById", "focusEntry", "Billboard focus mode"):
        if forbidden in camera_text:
            raise RuntimeError(f"overview camera payload still contains point focus: {forbidden}")

    hashes_before = {
        "page_8093": sha256(page_8093),
        "camera_8093": sha256(target_camera),
        "page_8094": sha256(page_8094),
        "shared_adapter": sha256(shared_adapter),
        "camera_8094": sha256(camera_8094),
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "8093_measured121_overview_20260801" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(page_8093, backup / f"{page_8093.name}.bak")
    shutil.copy2(target_camera, backup / f"{target_camera.name}.bak")
    if target_filter.is_file():
        shutil.copy2(target_filter, backup / f"{target_filter.name}.bak")

    patched_page = patch_page(page_8093.read_text(encoding="utf-8"))
    atomic_write(target_filter, filter_payload.read_bytes())
    atomic_write(target_camera, camera_payload.read_bytes())
    atomic_write(page_8093, patched_page.encode("utf-8"))

    deployed_page = page_8093.read_text(encoding="utf-8")
    deployed_filter = target_filter.read_text(encoding="utf-8")
    deployed_camera = target_camera.read_text(encoding="utf-8")
    if FILTER_TAG not in deployed_page or CAMERA_TAG not in deployed_page:
        raise RuntimeError("deployed 8093 page did not preserve exact cache markers")
    if "bf3d.measured-point-filter.8093.v2" not in deployed_filter:
        raise RuntimeError("deployed 8093 physical-point runtime contract failed")
    if "bf3d.camera.overview-only.8093.v4" not in deployed_camera:
        raise RuntimeError("deployed 8093 overview camera contract failed")

    hashes_after = {
        "page_8093": sha256(page_8093),
        "filter_8093": sha256(target_filter),
        "camera_8093": sha256(target_camera),
        "page_8094": sha256(page_8094),
        "shared_adapter": sha256(shared_adapter),
        "camera_8094": sha256(camera_8094),
    }
    for protected in ("page_8094", "shared_adapter", "camera_8094"):
        if hashes_before[protected] != hashes_after[protected]:
            raise RuntimeError(f"protected 8094 file changed: {protected}")

    return {
        "req_id": REQ_ID,
        "deployed": True,
        "root": str(root),
        "frontend": str(frontend),
        "backup": str(backup),
        "page_marker": FILTER_TAG,
        "camera_marker": CAMERA_TAG,
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "expected_visible_points": 121,
        "expected_excluded_points": 12,
        "point_focus_enabled": False,
        "8094_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    )
    parser.add_argument("--filter-payload", type=Path, required=True)
    parser.add_argument("--camera-payload", type=Path, required=True)
    args = parser.parse_args()
    result = deploy(
        args.root.resolve(),
        args.filter_payload.resolve(),
        args.camera_payload.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
