"""Build a versioned 8093 frontend release archive.

The archive is consumed by ``remote_guarded_deploy_8093_frontend_release.ps1``.
It contains the 8093 page, the 133-point GLB and 8093-only runtimes. Shared
8094-facing assets are declared as verify-only dependencies and are never
overwritten by this release.

Requirement: OPS-8093-FRONTEND-FAST-RELEASE-20260806.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"

DEPLOY_FILES = (
    "frontend_dashboard_v3.server.html",
    "models/GL02_FURNACE_BODY_R1.glb",
    "models/gl02_furnace_body_billboards.v1.json",
    "models/gl02_furnace_body_cn_label_mapping.v1.json",
    "assets/bf3d-physical-point-filter-8093.js",
    "assets/bf3d-surface-camera-guard-8093.js",
    "assets/bf3d-tooltip-stable-hover-8093.js",
    "assets/bf-core-metrics-pspace-live-8093.js",
    "assets/bf-heat-performance-quality-8093.js",
)

VERIFY_ONLY_FILES = (
    "assets/bf3d-furnace-body-billboard-adapter.js",
)

REQUIRED_MARKERS = (
    "REQ-BF3D-8093-REMOVE-SIMULATION-CONTROLS-20260806",
    "OPS-8093-QA-FETCH-RESILIENCE-20260806",
    "models/GL02_FURNACE_BODY_R1.glb",
    "bf3d-physical-point-filter-8093.js",
    "bf3d-tooltip-stable-hover-8093.js",
)

FORBIDDEN_PAGE_REFERENCES = (
    'src="assets/bf3d-internal-simulation.js',
    'src="assets/bf3d-structural-review.js',
    'href="assets/bf3d-internal-simulation.css',
    'href="assets/bf3d-structural-review.css',
    'id="gl02-layered-cad-controls-v1"',
)


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_source() -> None:
    """Validate the release source and the no-simulation page contract."""

    for relative in (*DEPLOY_FILES, *VERIFY_ONLY_FILES):
        source = FRONTEND / relative
        if not source.is_file():
            raise FileNotFoundError(f"release source is missing: {source}")

    page = (FRONTEND / "frontend_dashboard_v3.server.html").read_text(encoding="utf-8")
    for marker in REQUIRED_MARKERS:
        if marker not in page:
            raise ValueError(f"required page marker is missing: {marker}")
    for reference in FORBIDDEN_PAGE_REFERENCES:
        if reference in page:
            raise ValueError(f"forbidden page reference remains: {reference}")


def build_release(release_id: str, output: Path) -> dict[str, object]:
    """Create the archive and return its manifest."""

    validate_source()
    created_at = datetime.now(timezone.utc).isoformat()
    files: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="bf8093_release_") as temporary:
        staging = Path(temporary)
        for relative in DEPLOY_FILES:
            source = FRONTEND / relative
            destination = staging / "payload" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files.append(
                {
                    "relative_path": relative.replace("/", "\\"),
                    "archive_path": f"payload/{relative}",
                    "sha256": sha256(source),
                    "size": source.stat().st_size,
                    "mode": "deploy",
                }
            )

        for relative in VERIFY_ONLY_FILES:
            source = FRONTEND / relative
            files.append(
                {
                    "relative_path": relative.replace("/", "\\"),
                    "archive_path": None,
                    "sha256": sha256(source),
                    "size": source.stat().st_size,
                    "mode": "verify_only",
                }
            )

        manifest: dict[str, object] = {
            "schema": "ops.8093.frontend-release.v1",
            "requirement_id": "OPS-8093-FRONTEND-FAST-RELEASE-20260806",
            "release_id": release_id,
            "created_at": created_at,
            "deployment_mutex_required": False,
            "page_markers": list(REQUIRED_MARKERS),
            "forbidden_page_references": list(FORBIDDEN_PAGE_REFERENCES),
            "files": files,
        }
        (staging / "release-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(staging.rglob("*")):
                if source.is_file():
                    archive.write(source, source.relative_to(staging).as_posix())

    manifest["archive"] = str(output.resolve())
    manifest["archive_sha256"] = sha256(output)
    manifest["archive_size"] = output.stat().st_size
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the versioned 8093 frontend release archive.")
    parser.add_argument("--release-id", required=True, help="Sortable release id, for example 20260806_170000_no_sim_133_r1")
    parser.add_argument("--output", type=Path, required=True, help="Output ZIP path")
    args = parser.parse_args()
    result = build_release(args.release_id, args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
