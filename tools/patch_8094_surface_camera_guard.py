#!/usr/bin/env python3
"""Idempotently attach the 8094 furnace-surface camera guard to its preview page."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8094-SURFACE-CAMERA-GUARD-20260801"
GUARD_ASSET = "assets/bf3d-surface-camera-guard-8094.js"
GUARD_MARKER = "<!-- 8094-only furnace-surface camera target and shell collision guard -->"
GUARD_TAG = (
    f'{GUARD_MARKER}\n'
    f'<script type="module" src="{GUARD_ASSET}?v=20260801-surface-target-r2"></script>'
)
ADAPTER_ASSET = "assets/bf3d-furnace-body-billboard-adapter.js"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_page(page: Path, backup_dir: Path | None) -> dict[str, object]:
    if not page.is_file():
        raise FileNotFoundError(page)
    original = page.read_text(encoding="utf-8")
    if ADAPTER_ASSET not in original:
        raise RuntimeError(f"8094 adapter marker missing: {ADAPTER_ASSET}")

    before_hash = sha256(page)
    if GUARD_TAG in original:
        return {
            "req_id": REQ_ID,
            "changed": False,
            "page": str(page),
            "sha256_before": before_hash,
            "sha256_after": before_hash,
            "backup": None,
        }

    if GUARD_ASSET in original:
        pattern = re.compile(
            rf'(?:{re.escape(GUARD_MARKER)}\s*)?'
            rf'<script type="module" src="{re.escape(GUARD_ASSET)}[^\"]*"></script>'
        )
        updated, replacements = pattern.subn(GUARD_TAG, original, count=1)
        if replacements != 1:
            raise RuntimeError("cannot update existing 8094 guard script tag")
    else:
        insertion = "\n" + GUARD_TAG
        internal_tag = '<script type="module" src="assets/bf3d-internal-simulation.js"></script>'
        if internal_tag in original:
            updated = original.replace(internal_tag, insertion + "\n" + internal_tag, 1)
        elif "</body>" in original:
            updated = original.replace("</body>", insertion + "\n</body>", 1)
        else:
            raise RuntimeError("cannot find a safe script insertion point")

    backup_path = None
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{page.name}.{stamp}.bak"
        shutil.copy2(page, backup_path)

    page.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "req_id": REQ_ID,
        "changed": True,
        "page": str(page),
        "sha256_before": before_hash,
        "sha256_after": sha256(page),
        "backup": str(backup_path) if backup_path else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    result = patch_page(args.page.resolve(), args.backup_dir.resolve() if args.backup_dir else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
