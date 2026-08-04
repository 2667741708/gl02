#!/usr/bin/env python3
"""Sync the 8094 furnace-body viewer contract into 8093 without simulation UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8093-FURNACE-BODY-NO-SIM-20260801"
EXPECTED_SOURCE_SHA256 = "4F0D80F45218565ABA5F8A0EB28C30882E10067745F88690B288039366C3CCEE"
ADAPTER_ASSET = "assets/bf3d-furnace-body-billboard-adapter.js"
CAMERA_ASSET = "assets/bf3d-surface-camera-guard-8093.js"
CAMERA_ASSET_VERSION = "20260801-8093-dual-camera-r5"
NO_SIM_STYLE_ID = "bf3d-8093-no-internal-simulation-panel"
FAVICON_MARKER = '<link rel="icon" href="data:,">'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def patch_text(text: str) -> tuple[str, dict[str, int]]:
    if "assets/bf3d-internal-simulation.js" in text:
        raise RuntimeError("8093 source unexpectedly loads the internal simulation runtime")

    old_static_rows = (
        "['P_static_20m35', '20.35米静压', 'kPa'], ['P_static_23m49', "
        "'23.49米静压', 'kPa'], ['P_static_28m98', '28.98米静压', 'kPa']"
    )
    new_static_rows = ", ".join(
        [
            "['P_static_20m35', '20.35米静压（兼容）', 'kPa']",
            "['P_static_23m49', '23.49米静压（兼容）', 'kPa']",
            "['P_static_28m98', '28.98米静压（兼容）', 'kPa']",
            *[
                f"['P_static_{level}_{orientation}', '{height}米静压{orientation}', 'kPa']"
                for level, height in (
                    ("lower", "20.350"),
                    ("middle", "23.488"),
                    ("upper", "28.976"),
                )
                for orientation in "ABCDEF"
            ],
        ]
    )
    old_static_count = text.count(old_static_rows)
    if old_static_count == 1:
        text = text.replace(old_static_rows, new_static_rows, 1)
    elif old_static_count == 0 and "P_static_upper_F" in text:
        pass
    else:
        raise RuntimeError("expected legacy or already-expanded static-pressure rows")

    old_viewer = (
        "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects, hitObjects, camera, "
        "renderer, modelUrl: 'models/gl02_blast_furnace.glb', sensorCount: "
        "sensorObjects.length, hitCount: hitObjects.length, mappedCount }"
    )
    old_viewer_hover = (
        "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects, hitObjects, camera, "
        "renderer, modelUrl: 'models/gl02_blast_furnace.glb', sensorCount: "
        "sensorObjects.length, hitCount: hitObjects.length, mappedCount, "
        "hoverRadiusPx: 42 }"
    )
    new_viewer = (
        "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects, hitObjects, camera, "
        "renderer, scene, model, baseModel: model, controls, getBuffer: () => "
        "bufRef.current, modelUrl: 'models/gl02_blast_furnace.glb', sensorCount: "
        "sensorObjects.length, hitCount: hitObjects.length, mappedCount }"
    )
    viewer_count = text.count(old_viewer) + text.count(old_viewer_hover)
    if viewer_count == 2:
        text = text.replace(old_viewer, new_viewer)
        text = text.replace(old_viewer_hover, new_viewer[:-2] + ", hoverRadiusPx: 42 }")
    elif viewer_count == 0 and text.count("scene, model, baseModel: model, controls") == 2:
        pass
    else:
        raise RuntimeError(f"expected two legacy or expanded CAD viewer contracts, found {viewer_count}")

    no_sim_style = f"""  <!-- {REQ_ID}: panel suppressed; runtime intentionally not loaded -->
  <style id="{NO_SIM_STYLE_ID}">.bf3d-sim-panel{{display:none!important}}</style>
"""
    if NO_SIM_STYLE_ID not in text:
        if "</head>" not in text:
            raise RuntimeError("HTML head closing tag not found")
        text = text.replace("</head>", no_sim_style + "</head>", 1)
    if FAVICON_MARKER not in text:
        if "</head>" not in text:
            raise RuntimeError("HTML head closing tag not found for favicon")
        text = text.replace("</head>", f"  {FAVICON_MARKER}\n</head>", 1)

    runtime_tags = f"""  <!-- {REQ_ID}: 8094 furnace body + 133 billboards; no internal simulation -->
  <script type="module" src="{ADAPTER_ASSET}?v=20260801-8093-sync-r1"></script>
  <script type="module" src="{CAMERA_ASSET}?v={CAMERA_ASSET_VERSION}"></script>
"""
    if ADAPTER_ASSET not in text:
        if "</body>" not in text:
            raise RuntimeError("HTML body closing tag not found")
        text = text.replace("</body>", runtime_tags + "</body>", 1)

    for previous_version in (
        "20260801-8093-sync-r1",
        "20260801-8093-near-plane-r4",
    ):
        text = text.replace(
            f"{CAMERA_ASSET}?v={previous_version}",
            f"{CAMERA_ASSET}?v={CAMERA_ASSET_VERSION}",
        )

    if "assets/bf3d-internal-simulation.js" in text:
        raise RuntimeError("patched 8093 page must not load internal simulation JavaScript")
    if "assets/bf3d-internal-simulation.css" in text:
        raise RuntimeError("patched 8093 page must not load internal simulation CSS")
    return text, {"viewer_contract_replacements": viewer_count, "static_pressure_rows": 21}


def patch_page(
    page: Path,
    backup_dir: Path | None,
    expected_sha256: str = EXPECTED_SOURCE_SHA256,
) -> dict[str, object]:
    if not page.is_file():
        raise FileNotFoundError(page)
    before_hash = sha256(page)
    if before_hash != expected_sha256.upper():
        raise RuntimeError(
            f"source hash mismatch: {before_hash}; expected {expected_sha256.upper()}"
        )
    updated, counts = patch_text(page.read_text(encoding="utf-8"))
    backup_path = None
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{page.name}.{stamp}.bak"
        shutil.copy2(page, backup_path)
    page.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "req_id": REQ_ID,
        "page": str(page),
        "sha256_before": before_hash,
        "sha256_after": sha256(page),
        "backup": str(backup_path) if backup_path else None,
        **counts,
        "internal_simulation_runtime_loaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--expected-sha256", default=EXPECTED_SOURCE_SHA256)
    args = parser.parse_args()
    result = patch_page(
        args.page.resolve(),
        args.backup_dir.resolve() if args.backup_dir else None,
        args.expected_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
