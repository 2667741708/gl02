#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""One-command deployer for the shared 8093/8094 diagnosis feature bundle.

The deployed bundle is the read-only diagnosis evidence/model-review layer and
the manual scoring UI.  It intentionally does not restart 8768 and therefore
does not deploy the production diagnosis scheduler or change persisted scores.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TMP_LIBS = ROOT / ".tmp_pylibs"
TMP_DEPLOY = ROOT / ".tmp_deploy"
LOG_ROOT = ROOT / "logs" / "deploy_diag_rules"

DEFAULT_HOST = "10.30.220.12"
DEFAULT_USER = "administrator"
REMOTE_ROOT = r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
REMOTE_PROXY = REMOTE_ROOT + r"\高炉前端数据\智能助手\backend\ollama_proxy_server.py"
REMOTE_TEMP_ROOT = r"C:\Users\Administrator\AppData\Local\Temp"

PROXY_RELATIVE = Path("高炉前端数据/智能助手/backend/ollama_proxy_server.py")
REMOTE_SCRIPT = TOOLS / "remote_deploy_diag_rules.ps1"

# Exact allow-listed production bundle.  The proxy is built on top of the
# currently deployed remote proxy so unrelated local proxy edits do not leak.
BUNDLE_FILES: tuple[Path, ...] = (
    Path("高炉前端数据/智能助手/backend/diag_ai_evidence.py"),
    Path("高炉前端数据/智能助手/backend/diagnosis_model_review.py"),
    Path("高炉前端数据/智能助手/backend/diagnosis_ai_analysis_api.py"),
    Path("高炉前端数据/智能助手/backend/diagnosis_review.py"),
    Path("高炉前端数据/assets/bf-diagnosis-manual-score-local.js"),
    Path("高炉前端数据/assets/bf-diagnosis-manual-score-local.css"),
    Path("高炉前端数据/assets/bf-diagnosis-review-local.js"),
    Path("高炉前端数据/assets/bf-diagnosis-review-local.css"),
)

QUICK_TESTS: tuple[str, ...] = (
    r"tests\test_diagnosis_ai_analysis.py",
    r"tests\test_diagnosis_review_api.py",
    r"tests\test_diagnosis_review_contract.py",
    r"tests\test_diag_rules_deployer.py",
    r"tests\test_diag_rules_reliable_deployer.py",
)

ASSET_NAMES: tuple[str, ...] = (
    "bf-diagnosis-review-local.css",
    "bf-diagnosis-manual-score-local.css",
    "bf-diagnosis-review-local.js",
    "bf-diagnosis-manual-score-local.js",
)


class DeployError(RuntimeError):
    """A safe, user-facing deployment failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def bundle_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative in BUNDLE_FILES:
        path = ROOT / relative
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    digest.update((ROOT / PROXY_RELATIVE).read_bytes())
    return digest.hexdigest()[:10]


def deployment_version(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return f"diag-{moment:%Y%m%d-%H%M}-{bundle_fingerprint()}"


def validate_local_sources() -> dict[str, Any]:
    required = [ROOT / relative for relative in BUNDLE_FILES]
    required.extend((ROOT / PROXY_RELATIVE, REMOTE_SCRIPT, TOOLS / "build_8093_diag_single_payload.py"))
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise DeployError("Missing local deployment files: " + ", ".join(missing))

    python_files = [path for path in required if path.suffix == ".py"]
    for path in python_files:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

    manual = (ROOT / "高炉前端数据/assets/bf-diagnosis-manual-score-local.js").read_text(encoding="utf-8-sig")
    proxy = (ROOT / PROXY_RELATIVE).read_text(encoding="utf-8-sig")
    markers = (
        "bootWhenBodyReady",
        "bfdms-core-evidence",
        "/api/diagnosis-core-evidence?label=",
        "renderCoreChart",
    )
    absent = [marker for marker in markers if marker not in manual]
    if absent:
        raise DeployError("Manual score asset markers missing: " + ", ".join(absent))
    if 'parsed.path == "/api/diagnosis-core-evidence"' not in proxy:
        raise DeployError("Local proxy does not expose /api/diagnosis-core-evidence")

    node = shutil.which("node")
    if not node:
        raise DeployError("Node.js was not found; cannot run JavaScript syntax checks")
    for relative in BUNDLE_FILES:
        path = ROOT / relative
        if path.suffix == ".js":
            subprocess.run([node, "--check", str(path)], cwd=ROOT, check=True)

    return {
        "python_files": len(python_files),
        "javascript_files": sum(1 for path in required if path.suffix == ".js"),
        "bundle_files": len(BUNDLE_FILES) + 1,
    }


def run_quick_tests() -> None:
    command = [sys.executable, "-m", "pytest", *QUICK_TESTS, "-q", "--basetemp", ".tmp_pytest_diag_rules_deploy"]
    subprocess.run(command, cwd=ROOT, check=True)


def replace_asset_version(proxy_path: Path, version: str) -> None:
    text = proxy_path.read_text(encoding="utf-8-sig")
    replacements = 0
    for asset in ASSET_NAMES:
        pattern = re.compile(rf"(/assets/{re.escape(asset)}\?v=)[A-Za-z0-9_.-]+")
        text, count = pattern.subn(rf"\g<1>{version}", text)
        replacements += count
    if replacements < len(ASSET_NAMES):
        raise DeployError(
            f"Proxy asset-version anchors changed: expected at least {len(ASSET_NAMES)}, got {replacements}"
        )
    proxy_path.write_text(text, encoding="utf-8")


def build_proxy(remote_base: Path, output: Path, version: str) -> None:
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from build_8093_diag_single_payload import build  # noqa: PLC0415

    build(remote_base, ROOT / PROXY_RELATIVE, output)
    replace_asset_version(output, version)
    ast.parse(output.read_text(encoding="utf-8"), filename=str(output))
    if version not in output.read_text(encoding="utf-8"):
        raise DeployError("Generated proxy does not contain the deployment asset version")


def remote_module() -> Any:
    if TMP_LIBS.is_dir() and str(TMP_LIBS) not in sys.path:
        sys.path.insert(0, str(TMP_LIBS))
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    try:
        import remote_22012_exec  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise DeployError(
            "Paramiko is unavailable. Install it into .tmp_pylibs or the active Python environment."
        ) from exc
    return remote_22012_exec


def connection_args(args: argparse.Namespace) -> Namespace:
    return Namespace(
        host=args.host,
        user=args.user,
        password_env=args.password_env,
        allow_agents_password=args.allow_agents_password,
        prompt_password=args.prompt_password,
        timeout=args.timeout,
        workdir=REMOTE_ROOT,
        no_profile=True,
        upload=[],
        download=[],
        command=None,
        script=None,
        python_args=None,
        keep_remote_script=False,
    )


def check_tcp(host: str, port: int, timeout: float = 3.0) -> None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as exc:
        raise DeployError(f"VPN/private-network preflight failed: {host}:{port}: {exc}") from exc


def encode_remote_command(command: str) -> str:
    wrapper = "\n".join(
        (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
            "$OutputEncoding = [System.Text.Encoding]::UTF8",
            '$ProgressPreference = "SilentlyContinue"',
            f'Set-Location -LiteralPath "{REMOTE_ROOT}"',
            command,
            "exit $LASTEXITCODE",
        )
    )
    encoded = base64.b64encode(wrapper.encode("utf-16le")).decode("ascii")
    return f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"


def execute_remote(client: Any, command: str, timeout: int) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(encode_remote_command(command), timeout=timeout)
    stdout.channel.settimeout(timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = int(stdout.channel.recv_exit_status() or 0)
    return code, out, err


def stage_bom_copy(source: Path, destination: Path) -> None:
    destination.write_bytes(source.read_text(encoding="utf-8-sig").encode("utf-8-sig"))


def make_manifest(
    deployment_id: str,
    version: str,
    remote_stage: str,
    built_proxy: Path,
) -> tuple[dict[str, Any], list[tuple[Path, str]]]:
    files: list[tuple[Path, Path]] = [(built_proxy, PROXY_RELATIVE)]
    files.extend((ROOT / relative, relative) for relative in BUNDLE_FILES)
    entries: list[dict[str, Any]] = []
    uploads: list[tuple[Path, str]] = []
    for index, (local, target_relative) in enumerate(files, start=1):
        staged_name = f"{index:02d}_{local.name}"
        entries.append(
            {
                "stagedName": staged_name,
                "targetRelative": str(target_relative).replace("/", "\\"),
                "sha256": sha256_file(local),
            }
        )
        uploads.append((local, remote_stage + "\\" + staged_name))
    manifest = {
        "schema": "bf_diag_rules_deploy.v1",
        "deploymentId": deployment_id,
        "assetVersion": version,
        "projectRoot": REMOTE_ROOT,
        "stageRoot": remote_stage,
        "targets": [8093, 8094],
        "files": entries,
    }
    return manifest, uploads


def fetch_text(url: str, timeout: float = 15.0, attempts: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise DeployError(f"HTTP {response.status}: {url}")
                return response.read().decode("utf-8", errors="replace")
        except (OSError, urllib.error.URLError, DeployError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2)
    raise DeployError(f"HTTP verification failed for {url}: {last_error}")


def verify_fast(host: str, version: str) -> dict[str, Any]:
    result: dict[str, Any] = {"level": "fast", "ports": {}}
    cache_key = int(time.time())
    for port in (8093, 8094):
        page = fetch_text(f"http://{host}:{port}/?deploy={cache_key}")
        manual = fetch_text(
            f"http://{host}:{port}/assets/bf-diagnosis-manual-score-local.js?deploy={cache_key}"
        )
        checks = {
            "page_asset_version": version in page,
            "body_poll_boot": "bootWhenBodyReady" in manual,
            "core19_panel": "bfdms-core-evidence" in manual,
            "curve_renderer": "renderCoreChart" in manual,
        }
        if not all(checks.values()):
            raise DeployError(f"Fast verification failed on {port}: {checks}")
        result["ports"][str(port)] = checks
    return result


def verify_full(host: str) -> dict[str, Any]:
    result: dict[str, Any] = {"level": "full", "ports": {}}
    verifier = TOOLS / "verify_diagnosis_core19_remote.py"
    for port in (8093, 8094):
        completed = subprocess.run(
            [
                sys.executable,
                str(verifier),
                "--base-url",
                f"http://{host}:{port}",
                "--lightweight",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=90,
        )
        result["ports"][str(port)] = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
        if completed.returncode:
            raise DeployError(
                f"Full core19 verification failed on {port}: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
    return result


def write_report(report: dict[str, Any]) -> Path:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    path = LOG_ROOT / f"{report['deployment_id']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-command guarded deployment for the 8093/8094 diagnosis feature bundle."
    )
    parser.add_argument("--apply", action="store_true", help="Actually mutate 220.12; without it only a local dry-run is performed.")
    parser.add_argument("--verify", choices=("fast", "full"), default="fast")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the local pytest gate; intended only for emergency redeploys.")
    parser.add_argument("--host", default=os.getenv("BF_22012_HOST", DEFAULT_HOST))
    parser.add_argument("--user", default=os.getenv("BF_22012_USER", DEFAULT_USER))
    parser.add_argument("--password-env", default="BF_22012_SSH_PASSWORD")
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument("--prompt-password", action="store_true")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--keep-stage", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    version = deployment_version()
    deployment_id = version.replace("diag-", "diag_rules_")
    local_check = validate_local_sources()
    if not args.skip_tests:
        run_quick_tests()

    plan = {
        "ok": True,
        "mode": "apply" if args.apply else "dry_run",
        "deployment_id": deployment_id,
        "asset_version": version,
        "targets": [8093, 8094],
        "protected_ports": [8768, 8770, 11434],
        "restart_scope": ["BFV4PreviewProxy8093", "V3AutoPreviewProxy8094"],
        "bundle_files": [str(path).replace("\\", "/") for path in (PROXY_RELATIVE, *BUNDLE_FILES)],
        "local_check": local_check,
        "verification": args.verify,
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print("Dry-run only. Add --apply to deploy.")
        return 0

    for port in (22, 8093, 8094, 8768, 8770, 11434):
        check_tcp(args.host, port)

    TMP_DEPLOY.mkdir(parents=True, exist_ok=True)
    remote_stage = REMOTE_TEMP_ROOT + "\\" + deployment_id
    report: dict[str, Any] = {**plan, "ok": False, "started_at": datetime.now().isoformat(timespec="seconds")}
    remote = remote_module()
    connection = remote.connect(connection_args(args))
    try:
        with tempfile.TemporaryDirectory(prefix="diag_rules_", dir=TMP_DEPLOY) as temp_name:
            temp = Path(temp_name)
            remote_base = temp / "ollama_proxy_server.remote.py"
            built_proxy = temp / "ollama_proxy_server.py"
            manifest_path = temp / "manifest.json"
            remote_script_bom = temp / "remote_deploy_diag_rules.bom.ps1"

            sftp = connection.open_sftp()
            try:
                sftp.get(REMOTE_PROXY, str(remote_base))
            finally:
                sftp.close()
            build_proxy(remote_base, built_proxy, version)
            manifest, uploads = make_manifest(deployment_id, version, remote_stage, built_proxy)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            stage_bom_copy(REMOTE_SCRIPT, remote_script_bom)
            uploads.extend(
                (
                    (manifest_path, remote_stage + r"\manifest.json"),
                    (remote_script_bom, remote_stage + r"\remote_deploy_diag_rules.ps1"),
                )
            )
            sftp = connection.open_sftp()
            try:
                remote.upload_files(sftp, uploads)
            finally:
                sftp.close()

            command = (
                "& powershell.exe -NoProfile -ExecutionPolicy Bypass "
                f"-File '{remote_stage}\\remote_deploy_diag_rules.ps1' "
                f"-ManifestPath '{remote_stage}\\manifest.json'"
            )
            code, out, err = execute_remote(connection, command, args.timeout)
            print(out, end="" if out.endswith("\n") else "\n")
            if err:
                print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
            report["remote_exit_code"] = code
            report["remote_output_tail"] = out[-6000:]
            report["remote_error_tail"] = err[-3000:]
            if code:
                raise DeployError(f"Remote guarded deployment failed with exit code {code}")

        report["fast_verification"] = verify_fast(args.host, version)
        if args.verify == "full":
            report["full_verification"] = verify_full(args.host)
        report["ok"] = True
        return_code = 0
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"
        return_code = 1
        print(report["error"], file=sys.stderr)
    finally:
        connection.close()
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report_path = write_report(report)
        print(f"report={report_path}")

    if return_code == 0 and not args.keep_stage:
        # Remote cleanup is deliberately left to the server's routine temp cleanup;
        # deleting an uncertain stage after an SSH disconnect would harm forensics.
        pass
    return return_code


if __name__ == "__main__":
    reliable_entry = TOOLS / "deploy_diag_rules_rssh.py"
    raise SystemExit(subprocess.call([sys.executable, str(reliable_entry), *sys.argv[1:]], cwd=ROOT))
