"""Build a hash-locked deployment archive for recommendation audit persistence."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "runtime/自动诊断服务/recommendation_adapter.py": ROOT / "自动诊断服务" / "recommendation_adapter.py",
    "runtime/自动诊断服务/local_pg_ws_bridge.py": ROOT / "自动诊断服务" / "local_pg_ws_bridge.py",
    "runtime/自动诊断服务/recommendation_audit_store.py": ROOT / "自动诊断服务" / "recommendation_audit_store.py",
    "runtime/自动诊断服务/recommendation_audit_schema.sql": ROOT / "自动诊断服务" / "recommendation_audit_schema.sql",
    "tools/migrate_recommendation_audit.py": ROOT / "tools" / "migrate_recommendation_audit.py",
    "tools/verify_recommendation_audit_runtime.py": ROOT / "tools" / "verify_recommendation_audit_runtime.py",
}
POLICY = ROOT / "调控结论生成引擎" / "policy" / "three_rules_two_systems.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".tmp_deploy" / "recommendation_audit_deploy.zip",
    )
    args = parser.parse_args()
    for path in (*FILES.values(), POLICY):
        if not path.is_file():
            raise SystemExit(f"required deployment file is missing: {path}")

    manifest = {
        "schema_version": "recommendation_audit_deploy_manifest.v1",
        "operation": "REQ-RECOMMENDATION-FULL-AUDIT-20260806",
        "engine_version": "v5-three-rules-two-systems",
        "policy_sha256": sha256(POLICY),
        "files": {
            relative: {"sha256": sha256(path), "size": path.stat().st_size}
            for relative, path in FILES.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in FILES.items():
            archive.write(path, relative)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output.resolve()),
                "archive_sha256": sha256(args.output),
                "file_count": len(FILES),
                "policy_sha256": manifest["policy_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
