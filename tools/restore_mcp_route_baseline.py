"""Verify or restore the preserved MCP colloquial-routing baseline.

This command only changes local workspace files when --restore is explicitly
provided. It never deploys to 220.12 or restarts services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "backups" / "mcp_route_baseline_20260726_1552"
MANIFEST_PATH = BASELINE_DIR / "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verify_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results = []
    for item in manifest["files"]:
        snapshot = BASELINE_DIR / item["snapshot"]
        actual = sha256(snapshot)
        results.append(
            {
                "snapshot": str(snapshot),
                "expected_sha256": item["sha256"],
                "actual_sha256": actual,
                "ok": actual == item["sha256"],
            }
        )
    return {"ok": all(item["ok"] for item in results), "baseline_id": manifest["baseline_id"], "files": results}


def restore() -> dict:
    verification = verify_manifest()
    if not verification["ok"]:
        raise RuntimeError("基线快照哈希校验失败，拒绝恢复")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    restored = []
    for item in manifest["files"]:
        source = BASELINE_DIR / item["snapshot"]
        target = ROOT / item["source"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored.append({"target": str(target), "sha256": sha256(target)})
    return {"ok": True, "baseline_id": manifest["baseline_id"], "restored": restored}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验或恢复MCP口语意图路由基线。")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--verify", action="store_true", help="只校验基线文件SHA-256，不修改工作区。")
    action.add_argument("--restore", action="store_true", help="校验成功后覆盖恢复本地三个基线文件。")
    args = parser.parse_args()
    result = restore() if args.restore else verify_manifest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
