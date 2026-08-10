"""Atomically deploy the prominent ABC33 decision-centre workbench to 8094."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".abc33-decision.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--asset", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    frontend = root / "高炉前端数据"
    page = frontend / "frontend_dashboard_v3.8094_preview.server.html"
    asset = frontend / "assets" / "abc-furnace-rules-production.js"
    source = Path(args.asset).resolve()
    for target in (page, asset, source):
        if not target.is_file():
            raise FileNotFoundError(target)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / "abc33_decision_center_8094" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(page, backup / page.name)
    shutil.copy2(asset, backup / asset.name)

    page_text = page.read_text(encoding="utf-8")
    old = 'assets/abc-furnace-rules-production.js?v=abc33-20260808-r2'
    new = 'assets/abc-furnace-rules-production.js?v=abc33-20260808-r3-decision-center'
    if old in page_text:
        page_text = page_text.replace(old, new, 1)
    elif new not in page_text:
        raise RuntimeError("ABC33 runtime marker is missing from 8094 page")

    atomic_bytes(asset, source.read_bytes())
    atomic_bytes(page, page_text.encode("utf-8"))
    print(json.dumps({
        "ok": True,
        "backup": str(backup),
        "page_sha256": sha256(page),
        "asset_sha256": sha256(asset),
        "asset_bytes": asset.stat().st_size,
        "version": "abc33-20260808-r3-decision-center",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
