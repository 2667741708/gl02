#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a diagnosis-only proxy payload against the current remote proxy."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from build_8093_diag_single_payload import build


ASSETS = (
    "bf-diagnosis-review-local.css",
    "bf-diagnosis-manual-score-local.css",
    "bf-diagnosis-review-local.js",
    "bf-diagnosis-manual-score-local.js",
)


def apply_asset_version(path: Path, version: str) -> None:
    if not re.fullmatch(r"diag-[0-9]{8}-[0-9]{4}-[0-9a-f]{10}", version):
        raise RuntimeError("invalid diagnosis asset version")
    text = path.read_text(encoding="utf-8-sig")
    replacements = 0
    for asset in ASSETS:
        pattern = re.compile(rf"(/assets/{re.escape(asset)}\?v=)[A-Za-z0-9_.-]+")
        text, count = pattern.subn(rf"\g<1>{version}", text)
        replacements += count
    if replacements < len(ASSETS):
        raise RuntimeError(f"asset version anchors changed: {replacements}")
    ast.parse(text, filename=str(path))
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--local", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--asset-version", required=True)
    args = parser.parse_args()
    build(args.base, args.local, args.output)
    apply_asset_version(args.output, args.asset_version)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
