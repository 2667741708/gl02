#!/usr/bin/env python3
"""Build the exact local recommendation-engine payload for 8093 and 8094."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "logs" / "deployment" / "8093_8094_recommendation_sync_20260806_r3"
STAGE = OUTPUT / "payload"
ARCHIVE = OUTPUT / "recommendation_sync.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def copy_file(source: Path, relative: Path) -> None:
    destination = STAGE / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"output already exists: {OUTPUT}")
    STAGE.mkdir(parents=True)

    engine_source = ROOT / "调控结论生成引擎"
    for source in sorted(path for path in engine_source.rglob("*") if path.is_file()):
        if "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        copy_file(source, Path("runtime") / "调控结论生成引擎" / source.relative_to(engine_source))

    direct_files = {
        ROOT / "自动诊断服务" / "recommendation_adapter.py": Path("runtime/自动诊断服务/recommendation_adapter.py"),
        ROOT / "自动诊断服务" / "recommendation_adapter" / "__init__.py": Path("runtime/自动诊断服务/recommendation_adapter/__init__.py"),
        ROOT / "自动诊断服务" / "recommendation_adapter_full.py": Path("runtime/自动诊断服务/recommendation_adapter_full.py"),
        ROOT / "自动诊断服务" / "foreman_dual_control.py": Path("runtime/自动诊断服务/foreman_dual_control.py"),
        ROOT / "自动诊断服务" / "foreman_dual_control" / "__init__.py": Path("runtime/自动诊断服务/foreman_dual_control/__init__.py"),
        ROOT / "自动诊断服务" / "local_pg_ws_bridge.py": Path("runtime/自动诊断服务/local_pg_ws_bridge.py"),
        ROOT / "自动诊断服务" / "baseline_maintainer.py": Path("runtime/自动诊断服务/baseline_maintainer.py"),
        ROOT / "自动诊断服务" / "baseline_service.py": Path("runtime/自动诊断服务/baseline_service.py"),
        ROOT / "自动诊断服务" / "store.py": Path("runtime/自动诊断服务/store.py"),
        ROOT / "自动诊断服务" / "service_config.py": Path("runtime/自动诊断服务/service_config.py"),
        ROOT / "自动诊断服务" / "schema.sql": Path("runtime/自动诊断服务/schema.sql"),
        ROOT / "自动诊断服务" / "recommendation_audit_store.py": Path("runtime/自动诊断服务/recommendation_audit_store.py"),
        ROOT / "自动诊断服务" / "recommendation_audit_schema.sql": Path("runtime/自动诊断服务/recommendation_audit_schema.sql"),
        ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html": Path("source/frontend_dashboard_v3.server.html"),
        ROOT / "tools" / "patch_8094_multi_condition_review.py": Path("tools/patch_8094_multi_condition_review.py"),
        ROOT / "tools" / "verify_8094_multi_condition_runtime.py": Path("tools/verify_8094_multi_condition_runtime.py"),
        ROOT / "tools" / "verify_8094_multi_condition_package.py": Path("tools/verify_8094_multi_condition_package.py"),
        ROOT / "tools" / "verify_foreman_dual_control_runtime.py": Path("tools/verify_foreman_dual_control_runtime.py"),
        ROOT / "tools" / "migrate_recommendation_audit.py": Path("tools/migrate_recommendation_audit.py"),
        ROOT / "tools" / "migrate_foreman_pressure_quartiles.py": Path("tools/migrate_foreman_pressure_quartiles.py"),
        ROOT / "tools" / "restart_22012_8094_preview.ps1": Path("tools/restart_22012_8094_preview.ps1"),
        ROOT / "tools" / "sql" / "foreman_pressure_quartiles_20260806.sql": Path("tools/sql/foreman_pressure_quartiles_20260806.sql"),
    }
    for source, relative in direct_files.items():
        copy_file(source, relative)

    manifest_files: dict[str, dict[str, object]] = {}
    for path in sorted(item for item in STAGE.rglob("*") if item.is_file()):
        relative = path.relative_to(STAGE).as_posix()
        manifest_files[relative] = {"sha256": sha256(path), "size": path.stat().st_size}
    manifest = {
        "schema_version": "recommendation_sync_manifest.v2",
        "operation": "REQ-FOREMAN-COLD-BLAST-PRESSURE-20260806",
        "engine_version": "foreman-dual-control-v2",
        "shared_ws_port": 8768,
        "files": manifest_files,
    }
    (STAGE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(item for item in STAGE.rglob("*") if item.is_file()):
            bundle.write(path, path.relative_to(STAGE).as_posix())
    print(
        json.dumps(
            {
                "ok": True,
                "archive": str(ARCHIVE),
                "archive_sha256": sha256(ARCHIVE),
                "manifest_file_count": len(manifest_files),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
