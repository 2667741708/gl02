#!/usr/bin/env python3
"""Remove local 8093 furnace review/layer controls and internal simulation UI.

The production-facing furnace body, Billboard points, camera guard, tooltip,
live data and process callouts are deliberately preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8093-REMOVE-SIMULATION-CONTROLS-20260806"
REMOVED_LINKS = (
    '<link rel="stylesheet" href="assets/bf3d-internal-simulation.css">',
    '<link rel="stylesheet" href="assets/bf3d-structural-review.css">',
)
REMOVED_SCRIPTS = (
    '<script type="module" src="assets/bf3d-internal-simulation.js"></script>',
    '<script type="module" src="assets/bf3d-structural-review.js"></script>',
)
BLOCK_IDS = (
    "gl02-layered-cad-controls-v1",
    "gl02-layered-cad-controls-script-v1",
    "gl02-layer-highlight-material-v1",
    "gl02-layer-highlight-material-v2",
)
PRESERVED_ASSETS = (
    "bf3d-furnace-body-billboard-adapter.js",
    "bf3d-physical-point-filter-8093.js",
    "bf3d-surface-camera-guard-8093.js",
    "bf3d-tooltip-stable-hover-8093.js",
    "bf-heat-performance-quality-8093.js",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def remove_element_by_id(text: str, element_id: str) -> tuple[str, int]:
    pattern = re.compile(
        rf"\n?[ \t]*<(style|script)\b[^>]*\bid=[\"']{re.escape(element_id)}[\"'][^>]*>.*?</\1>[ \t]*\n?",
        re.DOTALL,
    )
    return pattern.subn("\n", text, count=1)


def patch_text(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for literal in (*REMOVED_LINKS, *REMOVED_SCRIPTS):
        count = text.count(literal)
        counts[literal] = count
        text = text.replace(f"  {literal}\n", "", 1)
        text = text.replace(f"{literal}\n", "", 1)

    for element_id in BLOCK_IDS:
        text, count = remove_element_by_id(text, element_id)
        counts[element_id] = count

    marker = f"  <!-- {REQ_ID}: review controls and internal simulation intentionally removed -->\n"
    if REQ_ID not in text:
        anchor = "  <!-- REQ-BF3D-LOCAL-133-BILLBOARD-PREVIEW-20260806"
        if anchor not in text:
            raise RuntimeError("133-point runtime anchor is missing")
        text = text.replace(anchor, marker + anchor, 1)

    forbidden = (
        *REMOVED_LINKS,
        *REMOVED_SCRIPTS,
        *BLOCK_IDS,
        'className="bf3d-sim-panel"',
    )
    remaining = [item for item in forbidden if item in text]
    if remaining:
        raise RuntimeError(f"removed runtime markers remain: {remaining}")
    missing = [item for item in PRESERVED_ASSETS if item not in text]
    if missing:
        raise RuntimeError(f"required production runtime was removed: {missing}")
    return text, counts


def patch_page(page: Path, backup_dir: Path) -> dict[str, object]:
    source = page.read_text(encoding="utf-8")
    updated, counts = patch_text(source)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{page.name}.{stamp}.bak"
    shutil.copy2(page, backup)
    temporary = page.with_name(f"{page.name}.remove-sim.tmp")
    temporary.write_text(updated, encoding="utf-8", newline="\n")
    os.replace(temporary, page)
    return {
        "req_id": REQ_ID,
        "page": str(page),
        "backup": str(backup),
        "sha256_after": sha256(page),
        "removed": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    result = patch_page(args.page.resolve(), args.backup_dir.resolve())
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
