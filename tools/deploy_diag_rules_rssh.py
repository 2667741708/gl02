#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""One-command 8093/8094 diagnosis deployment over local reliable_ssh.

This entrypoint packages the allow-listed diagnosis feature bundle locally,
then delegates host verification, transfer, remote execution, timeout handling,
and audit logging to ``reliable_ssh_22012_cli.mjs``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TMP_DEPLOY = ROOT / ".tmp_deploy"
NODE_CLI = TOOLS / "reliable_ssh_22012_cli.mjs"
PROXY_BUILDER = TOOLS / "build_diag_proxy_payload.py"
PROXY_BLOCK_BUILDER = TOOLS / "build_8093_diag_single_payload.py"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import deploy_diag_rules as common  # noqa: E402


def run_transport(arguments: list[str], timeout: int) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise common.DeployError("Node.js is required to run the reliable_ssh transport")
    completed = subprocess.run(
        [node, str(NODE_CLI), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if completed.returncode:
        raise common.DeployError(
            "reliable_ssh transport failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}")
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise common.DeployError("reliable_ssh transport returned no JSON receipt")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise common.DeployError(f"Invalid reliable_ssh receipt: {lines[-1][:500]}") from exc


def build_package(
    temp: Path,
    version: str,
    deployment_id: str,
    remote_stage: str,
) -> tuple[Path, dict[str, Any]]:
    local_proxy = ROOT / common.PROXY_RELATIVE
    manifest, _ = common.make_manifest(deployment_id, version, remote_stage, local_proxy)
    local_files = [local_proxy]
    local_files.extend(ROOT / relative for relative in common.BUNDLE_FILES)
    if len(local_files) != len(manifest["files"]):
        raise common.DeployError("Package file list does not match the deployment manifest")

    package = temp / f"{deployment_id}.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for local, entry in zip(local_files, manifest["files"], strict=True):
            archive.write(local, arcname=entry["stagedName"])
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr(
            "remote_deploy_diag_rules.ps1",
            common.REMOTE_SCRIPT.read_text(encoding="utf-8-sig").encode("utf-8-sig"),
        )
        archive.write(PROXY_BUILDER, arcname=PROXY_BUILDER.name)
        archive.write(PROXY_BLOCK_BUILDER, arcname=PROXY_BLOCK_BUILDER.name)
    if package.stat().st_size > 2_000_000:
        raise common.DeployError(f"Deployment package unexpectedly exceeds 2 MB: {package.stat().st_size}")
    return package, manifest

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guarded one-command diagnosis deployment using local reliable_ssh."
    )
    parser.add_argument("--apply", action="store_true", help="Deploy to 220.12; otherwise run local dry-run gates only.")
    parser.add_argument("--verify", choices=("fast", "full"), default="fast")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--timeout", type=int, default=240)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    version = common.deployment_version()
    deployment_id = version.replace("diag-", "diag_rules_")
    local_check = common.validate_local_sources()
    if not args.skip_tests:
        common.run_quick_tests()

    report: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if args.apply else "dry_run",
        "transport": "reliable_ssh_10_30_220_12",
        "deployment_id": deployment_id,
        "asset_version": version,
        "targets": [8093, 8094],
        "protected_ports": [8768, 8770, 11434],
        "restart_scope": ["BFV4PreviewProxy8093", "V3AutoPreviewProxy8094"],
        "bundle_files": [
            str(path).replace("\\", "/") for path in (common.PROXY_RELATIVE, *common.BUNDLE_FILES)
        ],
        "local_check": local_check,
        "verification": args.verify,
    }
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("Dry-run only. Add --apply to deploy through reliable_ssh.")
        return 0

    TMP_DEPLOY.mkdir(parents=True, exist_ok=True)
    remote_stage = common.REMOTE_TEMP_ROOT + "\\" + deployment_id
    remote_package = remote_stage + ".zip"
    report["ok"] = False
    report["started_at"] = datetime.now().isoformat(timespec="seconds")
    return_code = 1
    try:
        with tempfile.TemporaryDirectory(prefix="diag_rules_rssh_", dir=TMP_DEPLOY) as temp_name:
            temp = Path(temp_name)
            package, manifest = build_package(
                temp,
                version,
                deployment_id,
                remote_stage,
            )
            report["package"] = {
                "bytes": package.stat().st_size,
                "files": len(manifest["files"]),
                "transport_files": len(manifest["files"]) + 4,
                "proxy_merge": "remote_current_base",
            }
            report["remote_apply"] = run_transport(
                [
                    "apply-package",
                    "--package",
                    str(package),
                    "--remote-package",
                    remote_package,
                    "--stage-root",
                    remote_stage,
                    "--timeout",
                    str(args.timeout),
                ],
                timeout=args.timeout + 45,
            )

        report["fast_verification"] = common.verify_fast(common.DEFAULT_HOST, version)
        if args.verify == "full":
            report["full_verification"] = common.verify_full(common.DEFAULT_HOST)
        report["ok"] = True
        return_code = 0
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(report["error"], file=sys.stderr)
    finally:
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report_path = common.write_report(report)
        print(f"report={report_path}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
