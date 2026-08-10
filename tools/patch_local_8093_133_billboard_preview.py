#!/usr/bin/env python3
"""Patch the local V3 page to use the validated 133-point furnace asset.

This is intentionally local-only.  It does not contact, stop, or deploy to
10.30.220.12.  The patch is idempotent and preserves the rest of the page.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path


OLD_MODEL_URL = "models/gl02_blast_furnace_structural_review.v1.glb"
MODEL_URL = "models/GL02_FURNACE_BODY_R1.glb"
MARKER = "REQ-BF3D-LOCAL-133-BILLBOARD-PREVIEW-20260806"
RUNTIME_TAGS = f"""  <!-- {MARKER}: validated 115 + 18 point furnace runtime -->
  <script type="module" src="assets/bf3d-furnace-body-billboard-adapter.js?v=20260806-local-133-r1"></script>
  <!-- 8093 measured-point display policy; 133-point catalog remains available to the runtime -->
  <script type="module" src="assets/bf3d-physical-point-filter-8093.js?v=20260806-local-133-r1"></script>
  <script type="module" src="assets/bf3d-surface-camera-guard-8093.js?v=20260806-local-133-r1"></script>
  <script type="module" src="assets/bf3d-tooltip-stable-hover-8093.js?v=20260806-local-133-r1"></script>
"""
ANCHOR = '  <script type="module" src="assets/bf-core-metrics-pspace-live-8093.js?v=20260804-r1"></script>'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def patch_text(text: str) -> tuple[str, int]:
    old_count = text.count(OLD_MODEL_URL)
    current_count = text.count(MODEL_URL)
    if old_count:
        text = text.replace(OLD_MODEL_URL, MODEL_URL)
    elif current_count < 2:
        raise RuntimeError("active CAD viewer model URL was not found")

    if MARKER not in text:
        if ANCHOR not in text:
            raise RuntimeError("local runtime insertion anchor was not found")
        text = text.replace(ANCHOR, RUNTIME_TAGS + ANCHOR, 1)

    if text.count("bf3d-furnace-body-billboard-adapter.js") != 1:
        raise RuntimeError("Billboard adapter must be linked exactly once")
    if text.count("bf3d-physical-point-filter-8093.js") != 1:
        raise RuntimeError("physical-point filter must be linked exactly once")
    if text.count("bf3d-surface-camera-guard-8093.js") != 1:
        raise RuntimeError("camera runtime must be linked exactly once")
    if text.count("bf3d-tooltip-stable-hover-8093.js") != 1:
        raise RuntimeError("tooltip runtime must be linked exactly once")
    if OLD_MODEL_URL in text:
        raise RuntimeError("legacy structural-review model URL remains")
    if "bf-heat-performance-quality-8093.js" not in text:
        raise RuntimeError("heat-performance runtime must be preserved")
    return text, old_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()

    page = args.page.resolve()
    backup_dir = args.backup_dir.resolve()
    if not page.is_file():
        raise FileNotFoundError(page)
    before = sha256(page)
    updated, replacements = patch_text(page.read_text(encoding="utf-8"))

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{page.name}.{stamp}.bak"
    shutil.copy2(page, backup)
    temporary = page.with_name(f"{page.name}.local133.tmp")
    temporary.write_text(updated, encoding="utf-8", newline="\n")
    os.replace(temporary, page)

    print(f"page={page}")
    print(f"backup={backup}")
    print(f"sha256_before={before}")
    print(f"sha256_after={sha256(page)}")
    print(f"model_url_replacements={replacements}")
    print("production_deployed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
