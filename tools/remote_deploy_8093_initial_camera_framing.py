#!/usr/bin/env python3
"""Deploy the closer whole-furnace initial framing to the 8093 preview only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8093-INITIAL-FRAME-CLOSER-20260802"
CAMERA_ASSET = "assets/bf3d-surface-camera-guard-8093.js"
CAMERA_VERSION = "20260802-overview-closer-r1"
CAMERA_TAG = f'<script type="module" src="{CAMERA_ASSET}?v={CAMERA_VERSION}"></script>'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f"{path.name}.camera-framing.tmp")
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
    pattern = re.compile(
        rf'<script\s+type="module"\s+src="{re.escape(CAMERA_ASSET)}[^\"]*"\s*></script>'
    )
    patched, replacements = pattern.subn(CAMERA_TAG, text, count=1)
    if replacements != 1 or patched.count(CAMERA_ASSET) != 1:
        raise RuntimeError("8093 camera runtime tag is missing or duplicated")
    return patched


def deploy(root: Path, camera_payload: Path) -> dict[str, object]:
    frontend = locate_frontend(root)
    assets = frontend / "assets"
    page_8093 = frontend / "frontend_dashboard_v3.server.html"
    target_camera = assets / "bf3d-surface-camera-guard-8093.js"
    protected = {
        "page_8094": frontend / "frontend_dashboard_v3.8094_preview.server.html",
        "shared_adapter": assets / "bf3d-furnace-body-billboard-adapter.js",
        "physical_filter_8093": assets / "bf3d-physical-point-filter-8093.js",
        "stable_hover_8093": assets / "bf3d-tooltip-stable-hover-8093.js",
        "summary_css_8093": assets / "bf3d-furnace-summary-readability-8093.css",
        "camera_8094": assets / "bf3d-surface-camera-guard-8094.js",
        "model_8093": frontend / "models" / "gl02_blast_furnace.glb",
    }
    required = [page_8093, target_camera, camera_payload, *protected.values()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required file missing: {missing}")

    payload_text = camera_payload.read_text(encoding="utf-8")
    for marker in (
        'SCHEMA = "bf3d.camera.overview-only.8093.v4"',
        "OVERVIEW_FIT_MARGIN = 1.0",
        "OVERVIEW_ORBIT_MARGIN = 1.12",
        "viewer.controls.minDistance = fullOrbitRadius",
        'host.dataset.initialFraming = "closer-whole-furnace-r1"',
        "pointFocusEnabled: false",
    ):
        if marker not in payload_text:
            raise RuntimeError(f"camera payload marker missing: {marker}")

    protected_before = {name: sha256(path) for name, path in protected.items()}
    page_before = sha256(page_8093)
    camera_before = sha256(target_camera)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "8093_initial_camera_framing_20260802" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(page_8093, backup / f"{page_8093.name}.bak")
    shutil.copy2(target_camera, backup / f"{target_camera.name}.bak")

    patched_page = patch_page(page_8093.read_text(encoding="utf-8"))
    atomic_write(target_camera, camera_payload.read_bytes())
    atomic_write(page_8093, patched_page.encode("utf-8"))

    if CAMERA_TAG not in page_8093.read_text(encoding="utf-8"):
        raise RuntimeError("deployed page does not contain the exact camera cache marker")
    deployed_camera = target_camera.read_text(encoding="utf-8")
    if "bf3d.camera.overview-only.8093.v4" not in deployed_camera:
        raise RuntimeError("deployed camera schema is not v4")

    protected_after = {name: sha256(path) for name, path in protected.items()}
    changed_protected = [
        name for name in protected if protected_before[name] != protected_after[name]
    ]
    if changed_protected:
        raise RuntimeError(f"protected files changed: {changed_protected}")

    return {
        "schema": "deploy.8093.initial-camera-framing.v1",
        "requirement_id": REQ_ID,
        "deployed": True,
        "root": str(root),
        "frontend": str(frontend),
        "backup": str(backup),
        "camera_tag": CAMERA_TAG,
        "page_sha256_before": page_before,
        "page_sha256_after": sha256(page_8093),
        "camera_sha256_before": camera_before,
        "camera_sha256_after": sha256(target_camera),
        "protected_sha256": protected_after,
        "protected_unchanged": True,
        "overview_fit_margin": 1.0,
        "legacy_overview_fit_margin": 1.08,
        "expected_linear_scale_gain_percent": round((1.08 / 1.0 - 1) * 100, 1),
        "min_distance_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    )
    parser.add_argument("--camera-payload", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            deploy(args.root.resolve(), args.camera_payload.resolve()),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
