#!/usr/bin/env python3
"""Deploy the 8093 dual camera runtime without changing 8094 assets.

Requirement: REQ-BF3D-8093-DUAL-CAMERA-MODES-20260801.
This script is intended to run on 10.30.220.12 after the runtime payload has
been uploaded to a temporary path. It performs exact-marker checks, creates a
recoverable backup, atomically replaces the 8093 files, and proves the 8094
page/shared runtime hashes did not change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


REQ_ID = "REQ-BF3D-8093-DUAL-CAMERA-MODES-20260801"
OLD_MARKER = "assets/bf3d-surface-camera-guard-8093.js?v=20260801-8093-near-plane-r4"
NEW_MARKER = "assets/bf3d-surface-camera-guard-8093.js?v=20260801-8093-dual-camera-r5"
SCHEMA_MARKER = 'bf3d.camera.dual-mode.8093.v2'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f"{path.name}.dual-camera.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def deploy(root: Path, payload: Path) -> dict[str, object]:
    page = root / "高炉前端数据" / "frontend_dashboard_v3.server.html"
    asset_root = root / "高炉前端数据" / "assets"
    runtime = asset_root / "bf3d-surface-camera-guard-8093.js"
    shared_8094 = asset_root / "bf3d-surface-camera-guard-8094.js"
    page_8094 = root / "高炉前端数据" / "frontend_dashboard_v3.8094_preview.server.html"
    required = (page, runtime, shared_8094, page_8094, payload)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"required file missing: {missing}")

    payload_text = payload.read_text(encoding="utf-8")
    required_payload_markers = (
        SCHEMA_MARKER,
        "fullOrbitRadius",
        "surfaceAtCameraAzimuth",
        "dynamic-azimuth-shell-raycast",
        "focusById(id)",
        "exitFocus",
    )
    absent = [marker for marker in required_payload_markers if marker not in payload_text]
    if absent:
        raise RuntimeError(f"payload contract markers missing: {absent}")
    if "bf3d-surface-camera-guard-8094.js" in payload_text:
        raise RuntimeError("8093 payload must not import the 8094 runtime")

    page_text = page.read_text(encoding="utf-8")
    old_count = page_text.count(OLD_MARKER)
    new_count = page_text.count(NEW_MARKER)
    if (old_count, new_count) not in ((1, 0), (0, 1)):
        raise RuntimeError(
            f"unexpected 8093 page marker counts: old={old_count}, new={new_count}"
        )

    hashes_before = {
        "page_8093": sha256(page),
        "runtime_8093": sha256(runtime),
        "page_8094": sha256(page_8094),
        "shared_runtime_8094": sha256(shared_8094),
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = root / "backups" / "8093_dual_camera_modes_20260801" / stamp
    backup_root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(page, backup_root / f"{page.name}.bak")
    shutil.copy2(runtime, backup_root / f"{runtime.name}.bak")

    atomic_write(runtime, payload.read_bytes())
    if old_count == 1:
        page_text = page_text.replace(OLD_MARKER, NEW_MARKER, 1)
        atomic_write(page, page_text.encode("utf-8"))

    written_page = page.read_text(encoding="utf-8")
    written_runtime = runtime.read_text(encoding="utf-8")
    if written_page.count(NEW_MARKER) != 1:
        raise RuntimeError("8093 page cache marker verification failed")
    if SCHEMA_MARKER not in written_runtime:
        raise RuntimeError("8093 runtime schema verification failed")

    hashes_after = {
        "page_8093": sha256(page),
        "runtime_8093": sha256(runtime),
        "page_8094": sha256(page_8094),
        "shared_runtime_8094": sha256(shared_8094),
    }
    if hashes_before["page_8094"] != hashes_after["page_8094"]:
        raise RuntimeError("8094 page changed during the isolated 8093 deployment")
    if hashes_before["shared_runtime_8094"] != hashes_after["shared_runtime_8094"]:
        raise RuntimeError("8094 shared camera runtime changed during deployment")

    return {
        "req_id": REQ_ID,
        "deployed": True,
        "root": str(root),
        "backup": str(backup_root),
        "marker": NEW_MARKER,
        "schema": SCHEMA_MARKER,
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "8094_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"),
    )
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    result = deploy(args.root.resolve(), args.payload.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
