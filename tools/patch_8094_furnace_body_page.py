"""Prepare the remote 8094 preview HTML for the standalone furnace-body asset.

This is intentionally a deterministic, hash-guarded patch.  The remote page
is downloaded as evidence first, transformed locally, then uploaded only after
the new GLB and manifest have been validated.  It does not touch the 8093
production page.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


EXPECTED_SOURCE_SHA256 = (
    "4F0D80F45218565ABA5F8A0EB28C30882E10067745F88690B288039366C3CCEE"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def patch_page(source: Path, target: Path) -> None:
    source_hash = sha256(source)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit(
            f"source hash mismatch: {source_hash}; expected {EXPECTED_SOURCE_SHA256}"
        )
    text = source.read_text(encoding="utf-8")

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
    if text.count(old_static_rows) != 1:
        raise SystemExit("expected one legacy static-pressure row block")
    text = text.replace(old_static_rows, new_static_rows, 1)

    old_viewer = (
        "window.__BF_CAD_FURNACE_VIEWER = { sensorObjects, hitObjects, camera, "
        "renderer, modelUrl: 'models/gl02_blast_furnace.glb', sensorCount: "
        "sensorObjects.length, hitCount: hitObjects.length, mappedCount }"
    )
    old_viewer_with_hover_radius = (
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
    viewer_count = text.count(old_viewer) + text.count(old_viewer_with_hover_radius)
    if viewer_count != 2:
        raise SystemExit(f"expected two CAD viewer contracts, found {viewer_count}")
    text = text.replace(old_viewer, new_viewer)
    text = text.replace(old_viewer_with_hover_radius, new_viewer[:-2] + ", hoverRadiusPx: 42 }")

    head_marker = '<link rel="bf3d-8094-furnace-body-assets"'
    if head_marker not in text:
        head_assets = """  <!-- bf3d-8094-furnace-body-assets: GL02 body + runtime flow contract -->
  <link rel="stylesheet" href="assets/bf3d-internal-simulation.css">
  <link rel="bf3d-8094-furnace-body-assets" href="assets/bf3d-internal-simulation.css">
"""
        if "</head>" not in text:
            raise SystemExit("HTML head closing tag not found")
        text = text.replace("</head>", head_assets + "</head>", 1)

    body_marker = 'assets/bf3d-furnace-body-billboard-adapter.js'
    if body_marker not in text:
        body_assets = """  <!-- 8094-only runtime: 133 billboards and internal gas/charge flow -->
  <script type="module" src="assets/bf3d-furnace-body-billboard-adapter.js?v=20260725-r2"></script>
  <script type="module" src="assets/bf3d-internal-simulation.js"></script>
"""
        if "</body>" not in text:
            raise SystemExit("HTML body closing tag not found")
        text = text.replace("</body>", body_assets + "</body>", 1)

    target.write_text(text, encoding="utf-8", newline="\n")
    target_hash = sha256(target)
    print(f"source_sha256={source_hash}")
    print(f"target_sha256={target_hash}")
    print(f"viewer_contract_replacements={viewer_count}")
    print("static_pressure_rows=21")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} SOURCE_HTML TARGET_HTML", file=sys.stderr)
        return 2
    patch_page(Path(argv[1]), Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
