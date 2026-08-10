#!/usr/bin/env python3
"""Build a frontend-only, hash-bound payload for the 8093/8094 recommendation page."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "logs" / "deployment" / "8093_8094_recommendation_visual_20260806_r2"
)
VISUAL_MARKER = "REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806"
CONFIDENCE_REMOVAL_MARKER = "REQ-UI-REMOVE-JUDGMENT-CONFIDENCE-20260806"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for a payload file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def build(output: Path) -> dict[str, object]:
    """Build the immutable frontend payload without changing a running service."""
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    payload = output / "payload"
    payload.mkdir(parents=True)
    sources = {
        ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html": Path(
            "source/frontend_dashboard_v3.server.html"
        ),
        ROOT / "tools" / "patch_8094_multi_condition_review.py": Path(
            "tools/patch_8094_multi_condition_review.py"
        ),
        ROOT / "tools" / "patch_remove_judgment_confidence.py": Path(
            "tools/patch_remove_judgment_confidence.py"
        ),
    }
    for source, relative in sources.items():
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    source_page = payload / "source" / "frontend_dashboard_v3.server.html"
    page_text = source_page.read_text(encoding="utf-8")
    if page_text.count(VISUAL_MARKER) != 2:
        raise ValueError("visual requirement marker count is not exactly two")
    if "OptimizationTab = OptimizationVisualWorkbenchLayout;" not in page_text:
        raise ValueError("visual recommendation workbench is not active")
    if CONFIDENCE_REMOVAL_MARKER not in page_text:
        raise ValueError("judgment-confidence removal marker is missing")
    if "判断把握" in page_text:
        raise ValueError("judgment-confidence copy remains in the source page")

    files: dict[str, dict[str, object]] = {}
    for path in sorted(item for item in payload.rglob("*") if item.is_file()):
        relative = path.relative_to(payload).as_posix()
        files[relative] = {"sha256": sha256(path), "size": path.stat().st_size}
    manifest = {
        "schema_version": "recommendation_visual_frontend_manifest.v1",
        "operation": "OPS-8093-8094-RECOMMENDATION-VISUAL-20260806-R2",
        "requirement": VISUAL_MARKER,
        "shared_ws_port": 8768,
        "service_restart_required": False,
        "core_evidence_count": 19,
        "judgment_confidence_visible": False,
        "files": files,
    }
    manifest_path = payload / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archive = output / "recommendation_visual_frontend.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(item for item in payload.rglob("*") if item.is_file()):
            bundle.write(path, path.relative_to(payload).as_posix())
    return {
        "ok": True,
        "archive": str(archive),
        "archive_sha256": sha256(archive),
        "source_page_sha256": sha256(source_page),
        "manifest_file_count": len(files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
