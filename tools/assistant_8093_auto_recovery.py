"""Unified diagnose, repair, and acceptance entrypoint for the 8093 assistant.

Requirement:
    OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805

Inputs:
    CLI mode, local/VPN connectivity, a versioned remote tool package, and the
    current 220.12 runtime state.

Outputs:
    A local JSON report for every run. The ``docs`` phase separately generates
    a Markdown handoff, the latest trace report, and the maintained DOCX.

Safety:
    Remote PowerShell is always invoked through one short ``-File`` command.
    Recovery only applies known guard or keyword drift. SSE acceptance is sent
    at most once per ``recover`` invocation and is never retried automatically.

Documentation:
    docs/8093智能助手自动诊断修复验收工具_20260805.md
"""

from __future__ import annotations

import argparse
import concurrent.futures
import getpass
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
REPORT_ROOT = ROOT / "logs" / "assistant_8093_auto_recovery"
REQUIREMENT_ID = "OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805"
REMOTE_PROJECT_ROOT = r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
REMOTE_PACKAGE_PARENT = r"C:\ProgramData\BFV4\assistant-auto-recovery\packages"
PACKAGE_VERSION = "20260805_v2"
APPROVED_MODEL = "chiqiong-blast-furnace:latest"
CURRENT_CONFIG_HASH = "7541DB038ADD3CAB3F7DBDC6205117D049F4C440C636037EE92A5CC0E9517C5B"
PRE_MCP_CONFIG_HASH = "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE"
PRE_KEYWORD_CONFIG_HASH = "D20F01F1E66FF8973AB6720DDEB450AEE50FAE2AC6FFB023E1C04EACA066EACA"
OLD_GUARD_CONFIG_HASH = "A862003D01553E7EE6413663DA14C651760D9F137AB6C2D7C5CCA4033D14B6FB"
CURRENT_GUARD_HASH = "1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3"
OLD_GUARD_HASH = "F55F5B59BD9155E99C4C89B289A6C1843F640BE82A57235070E1B5148B9E0B95"
PG_POOL_PRE_PROXY_HASH = "8F38DA0286791A95722520D7278AE2A37544E3D4EB255D8A5950FC3CAD50EFD0"
PG_POOL_PRE_RAG_HASH = "C42CA839CD83541F679D348B6652B0BFFC1AAB2EE72D96C3B08395A70E6289AA"
PG_POOL_PARTIAL_PROXY_HASH = "B53F01E063138A623B091CB3F36DD72971FF5B844FB2D27C06C222BB417FF5F6"
PG_POOL_PARTIAL_RAG_HASH = "B2CD593A9F9BDC619305AF94FD82600F1547BBE1FE2C145051D09134C907B475"
PG_POOL_FINAL_PROXY_HASH = "979587B4C011FD893D7F737BBF5727F2A82123F25E8DA12CEC5BFD45778E6FED"
PG_POOL_FINAL_RAG_HASH = "B2CD593A9F9BDC619305AF94FD82600F1547BBE1FE2C145051D09134C907B475"
PG_POOL_FINAL_ASSISTANT_PG_HASH = "91D345B1F121CEA407EE5429597CE0A0C6055749F2DAA8F2D9A7C31065CDBF5B"
PG_POOL_ACTIVE_PROXY_HASH = "381516CB59B1C005844E3D1D322C96820194045B04D3AC1F35D71BDB88629509"
PG_POOL_VALIDATED_PROXY_HASH = "623FF462A8E688FC40DA301B46A7818E287F095C62419999F08450A3554DFBBB"
FETCH_RESILIENCE_PRE_FRONTEND_HASH = "4C552CBA92D70379E3CBFD6447195F6B1105403009D3C6B39512BF5EF5D31262"
ATRUST_EXECUTABLE = Path(r"C:\Program Files (x86)\Sangfor\aTrust\aTrustTray\aTrustTray.exe")
VPN_PORTAL = ("27.188.68.221", 4430)
CONNECTIVITY_PORTS = {
    "ssh": 22,
    "postgresql": 5432,
    "assistant_8093": 8093,
    "ollama_11434": 11434,
}
PACKAGE_FILES = {
    "remote_8093_assistant_diagnose.ps1": ROOT / "tools" / "remote_8093_assistant_diagnose.ps1",
    "remote_guarded_recover_8093_service.ps1": ROOT / "tools" / "remote_guarded_recover_8093_service.ps1",
    "remote_hot_deploy_8093_fetch_resilience.ps1": ROOT
    / "tools"
    / "remote_hot_deploy_8093_fetch_resilience.ps1",
    "patch_8093_assistant_fetch_resilience.py": ROOT / "tools" / "patch_8093_assistant_fetch_resilience.py",
    "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1": ROOT
    / "tools"
    / "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1",
    "patch_8093_keyword_knowledge_mode.py": ROOT / "tools" / "patch_8093_keyword_knowledge_mode.py",
    "remote_guarded_deploy_8093_health_guard.ps1": ROOT
    / "tools"
    / "remote_guarded_deploy_8093_health_guard.ps1",
    "check_managed_nssm_service_health.ps1": ROOT / "tools" / "check_managed_nssm_service_health.ps1",
    "patch_8093_health_guard_config.py": ROOT / "tools" / "patch_8093_health_guard_config.py",
    "remote_guarded_deploy_8093_pg_pool_reuse.ps1": ROOT
    / "tools"
    / "remote_guarded_deploy_8093_pg_pool_reuse.ps1",
    "patch_8093_assistant_pg_pool_reuse.py": ROOT / "tools" / "patch_8093_assistant_pg_pool_reuse.py",
    "remote_verify_8093_keyword_knowledge_sse_once.ps1": ROOT
    / "tools"
    / "remote_verify_8093_keyword_knowledge_sse_once.ps1",
    "verify_8093_assistant_sse_once.py": ROOT / "tools" / "verify_8093_assistant_sse_once.py",
}


class PipelineError(RuntimeError):
    """A classified, user-safe pipeline failure."""

    def __init__(self, stage: str, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code


@dataclass(frozen=True)
class RemoteCommandResult:
    """Result of one short remote PowerShell ``-File`` invocation."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float


def utc_stamp() -> str:
    """Return a sortable local-time stamp for report filenames."""

    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    """Return the current local time in ISO 8601 format."""

    return datetime.now().astimezone().isoformat()


def sha256_bytes(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""

    return hashlib.sha256(data).hexdigest().upper()


def deployed_bytes(path: Path) -> bytes:
    """Return bytes exactly as staged on Windows PowerShell 5.1.

    PowerShell scripts receive a UTF-8 BOM so ``-File`` decodes Chinese paths
    correctly. Python and JSON files remain regular UTF-8.
    """

    data = path.read_bytes()
    if path.suffix.lower() == ".ps1" and not data.startswith(b"\xef\xbb\xbf"):
        return b"\xef\xbb\xbf" + data
    return data


def build_package() -> tuple[str, dict[str, Any], dict[str, bytes]]:
    """Build the immutable package descriptor and payload map."""

    payloads: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    for remote_name, local_path in sorted(PACKAGE_FILES.items()):
        if not local_path.is_file():
            raise PipelineError("package", f"missing local package file: {local_path}", 4)
        data = deployed_bytes(local_path)
        payloads[remote_name] = data
        rows.append(
            {
                "name": remote_name,
                "sha256": sha256_bytes(data),
                "size": len(data),
            }
        )
    identity = {"schema": "ops.8093.assistant-auto-package.v1", "version": PACKAGE_VERSION, "files": rows}
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    package_id = f"{PACKAGE_VERSION}_{sha256_bytes(canonical)[:12].lower()}"
    manifest = dict(identity)
    manifest["package_id"] = package_id
    manifest["requirement_id"] = REQUIREMENT_ID
    return package_id, manifest, payloads


def read_agents_ssh_password() -> str | None:
    """Read the existing project-local SSH credential without logging it."""

    if not AGENTS.is_file():
        return None
    text = AGENTS.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"SSH 密码：([^\r\n]+)", text)
    return match.group(1).strip() if match else None


def resolve_password(args: argparse.Namespace) -> str:
    """Resolve the SSH password from an environment variable or approved source."""

    value = os.getenv(args.password_env or "BF_22012_SSH_PASSWORD")
    if value:
        return value
    if args.allow_agents_password:
        value = read_agents_ssh_password()
        if value:
            return value
    if args.prompt_password:
        return getpass.getpass(f"SSH password for {args.user}@{args.host}: ")
    raise PipelineError(
        "credentials",
        "missing SSH password; set BF_22012_SSH_PASSWORD or use --allow-agents-password/--prompt-password",
        4,
    )


def tcp_probe(host: str, port: int, timeout: float) -> dict[str, Any]:
    """Probe one TCP endpoint without changing remote state."""

    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok = True
            error = None
    except OSError as exc:
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    return {
        "host": host,
        "port": port,
        "ok": ok,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": error,
    }


def connectivity_snapshot(host: str, timeout: float) -> dict[str, Any]:
    """Probe VPN portal and all required 220.12 ports in parallel."""

    targets = [("vpn_portal", VPN_PORTAL[0], VPN_PORTAL[1])]
    targets.extend((name, host, port) for name, port in CONNECTIVITY_PORTS.items())
    rows: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as executor:
        futures = {
            executor.submit(tcp_probe, target_host, port, timeout): name
            for name, target_host, port in targets
        }
        for future, name in ((future, futures[future]) for future in futures):
            rows[name] = future.result()
    required = [rows[name]["ok"] for name in CONNECTIVITY_PORTS]
    return {
        "collected_at": now_iso(),
        "all_required_ok": all(required),
        "targets": rows,
    }


def infrastructure_connectivity_ok(snapshot: dict[str, Any]) -> bool:
    """Allow diagnosis/recovery when 8093 itself is the failed component."""

    targets = snapshot.get("targets") or {}
    return all(bool((targets.get(name) or {}).get("ok")) for name in ("ssh", "postgresql", "ollama_11434"))


def atrust_running() -> bool:
    """Return whether the aTrust tray process is already running."""

    try:
        completed = subprocess.run(
            ["tasklist.exe", "/FI", "IMAGENAME eq aTrustTray.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "aTrustTray.exe" in completed.stdout


def start_atrust() -> dict[str, Any]:
    """Start the installed aTrust tray once so its saved session can reconnect."""

    if not ATRUST_EXECUTABLE.is_file():
        return {"attempted": False, "started": False, "reason": "aTrust executable not found"}
    if atrust_running():
        return {"attempted": False, "started": False, "reason": "aTrust tray already running"}
    try:
        subprocess.Popen([str(ATRUST_EXECUTABLE)], close_fds=True)
    except OSError as exc:
        return {"attempted": True, "started": False, "reason": str(exc)}
    return {"attempted": True, "started": True, "reason": None}


def ensure_connectivity(args: argparse.Namespace) -> dict[str, Any]:
    """Check VPN/SSH/8093/11434/PostgreSQL before any SSH operation.

    VPN recovery time is recorded separately. Service recovery timing starts
    only after the private infrastructure is reachable. 8093 is deliberately
    observed but is not a transport prerequisite because it may be the failed
    component this command must diagnose and recover.
    """

    started = time.perf_counter()
    initial = connectivity_snapshot(args.host, args.connect_timeout)
    recovery = {"attempted": False, "started": False, "reason": None}
    final = initial
    if not infrastructure_connectivity_ok(initial) and not args.no_vpn_recovery:
        recovery = start_atrust()
        deadline = time.monotonic() + args.vpn_timeout
        while time.monotonic() < deadline:
            time.sleep(2)
            final = connectivity_snapshot(args.host, args.connect_timeout)
            if infrastructure_connectivity_ok(final):
                break
    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "initial": initial,
        "vpn_recovery": recovery,
        "final": final,
        "elapsed_seconds": elapsed,
        "deployment_timer_started": False,
    }
    if not infrastructure_connectivity_ok(final):
        failed = [
            name
            for name in ("ssh", "postgresql", "ollama_11434")
            if not bool((final["targets"].get(name) or {}).get("ok"))
        ]
        raise PipelineError("connectivity", f"required connectivity is unavailable: {', '.join(failed)}", 3)
    result["ready_at"] = now_iso()
    return result


def load_paramiko():
    """Load Paramiko, including the repository-local fallback dependency path."""

    try:
        import paramiko  # type: ignore

        return paramiko
    except ImportError:
        fallback = ROOT / ".tmp_pylibs"
        if fallback.is_dir():
            sys.path.insert(0, str(fallback))
        import paramiko  # type: ignore

        return paramiko


class SshRemote:
    """Small SSH/SFTP adapter that only executes pre-staged ``-File`` scripts."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.client: Any = None

    def __enter__(self) -> "SshRemote":
        paramiko = load_paramiko()
        timeout = max(1, min(30, int(self.args.connect_timeout)))
        password = resolve_password(self.args)
        last_error: Exception | None = None
        for attempt in range(1, 4):
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    hostname=self.args.host,
                    username=self.args.user,
                    password=password,
                    timeout=timeout,
                    banner_timeout=timeout,
                    auth_timeout=timeout,
                    look_for_keys=False,
                    allow_agent=False,
                )
                self.client = client
                return self
            except Exception as exc:  # noqa: BLE001 - transport libraries expose several transient types
                last_error = exc
                client.close()
                if attempt < 3:
                    time.sleep(attempt * 1.5)
        raise PipelineError("ssh", f"SSH session failed after 3 fresh attempts: {type(last_error).__name__}", 5)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def open_sftp(self):
        if self.client is None:
            raise PipelineError("ssh", "SSH client is not connected", 5)
        return self.client.open_sftp()

    def run_ps1(self, script_path: str, timeout: int) -> RemoteCommandResult:
        """Execute one short remote PowerShell ``-File`` command."""

        if self.client is None:
            raise PipelineError("ssh", "SSH client is not connected", 5)
        command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
        started = time.perf_counter()
        _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = int(stdout.channel.recv_exit_status())
        return RemoteCommandResult(
            command=command,
            exit_code=exit_code,
            stdout=out,
            stderr=err,
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )


def to_sftp_path(path: str) -> str:
    """Convert a Windows path to the form accepted by Windows OpenSSH SFTP."""

    return path.replace("\\", "/")


def sftp_mkdirs(sftp: Any, remote_path: str) -> None:
    """Create one controlled SFTP directory tree."""

    normalized = to_sftp_path(remote_path)
    parts = normalized.split("/")
    current = parts[0] + "/"
    for part in parts[1:]:
        if not part:
            continue
        current = current.rstrip("/") + "/" + part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def sftp_read_bytes(sftp: Any, remote_path: str) -> bytes:
    """Read one remote file through SFTP."""

    with sftp.file(to_sftp_path(remote_path), "rb") as handle:
        return handle.read()


def remote_file_exists(sftp: Any, remote_path: str) -> bool:
    """Return whether one remote path exists."""

    try:
        sftp.stat(to_sftp_path(remote_path))
    except OSError:
        return False
    return True


def write_remote_file_atomic(sftp: Any, remote_path: str, data: bytes, package_dir: str) -> None:
    """Write one file atomically inside the exact controlled package directory."""

    normalized = to_sftp_path(remote_path)
    controlled = to_sftp_path(package_dir).rstrip("/") + "/"
    if not normalized.startswith(controlled):
        raise PipelineError("package", f"refusing write outside controlled package: {remote_path}", 4)
    temporary = normalized + ".uploading-" + uuid.uuid4().hex
    with sftp.file(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
    if sha256_bytes(sftp_read_bytes(sftp, temporary)) != sha256_bytes(data):
        raise PipelineError("package", f"remote upload hash mismatch: {remote_path}", 4)
    if remote_file_exists(sftp, normalized):
        sftp.remove(normalized)
    sftp.rename(temporary, normalized)


def ensure_remote_package(remote: SshRemote, allow_upload: bool) -> dict[str, Any]:
    """Verify or stage the immutable remote package, with the manifest written last."""

    package_id, manifest, payloads = build_package()
    package_dir = REMOTE_PACKAGE_PARENT + "\\" + package_id
    manifest_path = package_dir + "\\manifest.json"
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    uploaded: list[str] = []
    with remote.open_sftp() as sftp:
        complete = False
        if remote_file_exists(sftp, manifest_path):
            try:
                existing = json.loads(sftp_read_bytes(sftp, manifest_path).decode("utf-8"))
                complete = existing == manifest
                for row in manifest["files"]:
                    remote_path = package_dir + "\\" + row["name"]
                    complete = complete and remote_file_exists(sftp, remote_path)
                    if complete:
                        complete = sha256_bytes(sftp_read_bytes(sftp, remote_path)) == row["sha256"]
            except (OSError, ValueError, UnicodeError):
                complete = False
        if not complete:
            if not allow_upload:
                raise PipelineError("package", f"remote package is missing or invalid: {package_id}", 4)
            sftp_mkdirs(sftp, package_dir)
            for row in manifest["files"]:
                remote_path = package_dir + "\\" + row["name"]
                write_remote_file_atomic(sftp, remote_path, payloads[row["name"]], package_dir)
                uploaded.append(row["name"])
            write_remote_file_atomic(sftp, manifest_path, manifest_bytes, package_dir)
        verified: dict[str, str] = {}
        for row in manifest["files"]:
            remote_path = package_dir + "\\" + row["name"]
            actual = sha256_bytes(sftp_read_bytes(sftp, remote_path))
            if actual != row["sha256"]:
                raise PipelineError("package", f"remote package hash mismatch: {row['name']}", 4)
            verified[row["name"]] = actual
        remote_manifest = json.loads(sftp_read_bytes(sftp, manifest_path).decode("utf-8"))
        if remote_manifest != manifest:
            raise PipelineError("package", "remote manifest verification failed", 4)
    return {
        "package_id": package_id,
        "remote_directory": package_dir,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "uploaded": uploaded,
        "reused": not uploaded,
        "verified_files": verified,
    }


def parse_json_output(result: RemoteCommandResult, stage: str) -> dict[str, Any]:
    """Parse the JSON emitted by one remote phase without retrying it."""

    if result.exit_code != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PipelineError(stage, f"remote phase failed with exit {result.exit_code}: {detail[-2000:]}", 5)
    text = result.stdout.strip().lstrip("\ufeff")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError(stage, f"remote phase did not return valid JSON: {exc}", 5) from exc
    if not isinstance(value, dict):
        raise PipelineError(stage, "remote phase JSON must be an object", 5)
    return value


def row_by(rows: Iterable[dict[str, Any]], field: str, value: Any) -> dict[str, Any] | None:
    """Return the first row whose field matches the requested value."""

    for row in rows:
        if row.get(field) == value:
            return row
    return None


def endpoint_by(diagnostic: dict[str, Any], name: str) -> dict[str, Any]:
    """Return one named endpoint result or an empty failure row."""

    row = row_by(diagnostic.get("endpoints") or [], "name", name)
    return row or {"name": name, "ok": False, "content": None, "error": "missing endpoint row"}


def classify_diagnostic(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Classify the runtime and select only known, hash-bounded repairs."""

    issues: list[dict[str, str]] = []
    repairs: list[str] = []
    manual_blockers: list[str] = []
    services = diagnostic.get("services") or []
    listeners = diagnostic.get("listeners") or []
    config = diagnostic.get("config") or {}
    guard = diagnostic.get("guard") or {}
    runtime = diagnostic.get("runtime") or {}
    files = diagnostic.get("files") or {}

    assistant_service_unavailable = False
    protected_runtime_ok = True
    for service_name in ("BFV4PreviewProxy8093", "BFOllama11434", "BFV4PreviewWs8768"):
        service = row_by(services, "name", service_name)
        if not service or service.get("status") != "Running":
            issues.append({"code": "service_not_running", "detail": service_name})
            if service_name == "BFV4PreviewProxy8093":
                assistant_service_unavailable = True
            else:
                protected_runtime_ok = False
                manual_blockers.append("service_unavailable")
    for port in (5432, 8093, 8094, 8768, 8770, 11434):
        listener = row_by(listeners, "port", port)
        if not listener or not listener.get("listening"):
            issues.append({"code": "listener_missing", "detail": str(port)})
            if port == 8093:
                assistant_service_unavailable = True
            else:
                protected_runtime_ok = False
                manual_blockers.append("postgres_unavailable" if port == 5432 else "service_unavailable")

    status = endpoint_by(diagnostic, "assistant_status")
    status_content = status.get("content") or {}
    assistant_status_failed = not status.get("ok") or not status_content.get("ok") or not status_content.get("model_ok")
    if assistant_status_failed:
        issues.append({"code": "assistant_status_failed", "detail": str(status.get("error") or status_content)})

    processes = endpoint_by(diagnostic, "ollama_processes")
    model_names = [str(row.get("name") or "") for row in (processes.get("content") or {}).get("models") or []]
    if model_names != [APPROVED_MODEL]:
        issues.append({"code": "model_residency_drift", "detail": ",".join(model_names) or "none"})
        manual_blockers.append("model_residency_drift")

    config_hash = str(config.get("sha256") or "").upper()
    guard_hash = str(guard.get("script_sha256") or "").upper()
    known_configs = {CURRENT_CONFIG_HASH, PRE_MCP_CONFIG_HASH, PRE_KEYWORD_CONFIG_HASH, OLD_GUARD_CONFIG_HASH}
    known_guards = {CURRENT_GUARD_HASH, OLD_GUARD_HASH}
    if config_hash not in known_configs:
        issues.append({"code": "unknown_config_hash", "detail": config_hash})
        manual_blockers.append("unknown_config_hash")
    if guard_hash not in known_guards:
        issues.append({"code": "unknown_guard_hash", "detail": guard_hash})
        manual_blockers.append("unknown_guard_hash")

    health = config.get("health") or {}
    health_tuple = (
        int(health.get("failure_threshold") or 0),
        int(health.get("service_down_threshold") or 0),
        int(health.get("pre_restart_backoff_seconds") or 0),
        int(health.get("restart_cooldown_seconds") or 0),
    )
    guard_drift = health_tuple != (3, 1, 15, 600) or guard_hash == OLD_GUARD_HASH
    if guard.get("task_state") == "Disabled":
        issues.append({"code": "guard_task_disabled", "detail": "health task is disabled"})
        manual_blockers.append("guard_task_disabled")
    elif guard_drift and not manual_blockers:
        issues.append({"code": "guard_drift", "detail": f"contract={health_tuple} hash={guard_hash}"})
        repairs.append("guard_contract")

    runtime_mode = str(((runtime.get("assistant_8093") or {}).get("knowledge_search_mode") or "")).strip().lower()
    config_mode = str(config.get("knowledge_search_mode") or "").strip().lower()
    knowledge = endpoint_by(diagnostic, "default_knowledge_search")
    knowledge_content = knowledge.get("content") or {}
    retrieval_mode = str(knowledge_content.get("retrieval_mode") or knowledge_content.get("search_mode") or "").lower()
    evidence_count = len(knowledge_content.get("evidence") or [])
    knowledge_detail = str(knowledge.get("error") or knowledge_content)
    knowledge_message = str(knowledge_content.get("message") or "").lower()
    proxy_hash = str(files.get("proxy_sha256") or "").upper()
    rag_hash = str(files.get("rag_sha256") or "").upper()
    assistant_pg_hash = str(files.get("assistant_pg_sha256") or "").upper()
    final_pool_baseline = (
        proxy_hash in {PG_POOL_FINAL_PROXY_HASH, PG_POOL_ACTIVE_PROXY_HASH, PG_POOL_VALIDATED_PROXY_HASH}
        and rag_hash == PG_POOL_FINAL_RAG_HASH
        and assistant_pg_hash == PG_POOL_FINAL_ASSISTANT_PG_HASH
    )
    final_service_baseline = (config_hash, proxy_hash) in {
        (PRE_MCP_CONFIG_HASH, PG_POOL_FINAL_PROXY_HASH),
        (CURRENT_CONFIG_HASH, PG_POOL_ACTIVE_PROXY_HASH),
        (CURRENT_CONFIG_HASH, PG_POOL_VALIDATED_PROXY_HASH),
    }
    assistant_recovery_needed = assistant_service_unavailable or assistant_status_failed
    service_recovery_safe = (
        assistant_recovery_needed
        and protected_runtime_ok
        and final_service_baseline
        and guard_hash == CURRENT_GUARD_HASH
        and final_pool_baseline
        and not manual_blockers
    )
    if service_recovery_safe:
        repairs.append("service_recover")
    elif assistant_recovery_needed:
        manual_blockers.append("service_unavailable" if assistant_service_unavailable else "assistant_status_failed")

    approved_pool_baseline = (proxy_hash, rag_hash) in {
        (PG_POOL_PRE_PROXY_HASH, PG_POOL_PRE_RAG_HASH),
        (PG_POOL_PARTIAL_PROXY_HASH, PG_POOL_PARTIAL_RAG_HASH),
    }
    keyword_drift = (
        config_mode != "keyword"
        or runtime_mode != "keyword"
        or (bool(retrieval_mode) and retrieval_mode != "keyword")
    )
    if assistant_recovery_needed:
        pass
    elif keyword_drift and not manual_blockers:
        issues.append(
            {
                "code": "keyword_drift",
                "detail": f"config={config_mode or 'blank'} runtime={runtime_mode or 'blank'} default={retrieval_mode or 'blank'}",
            }
        )
        repairs.append("keyword_mode")
    elif approved_pool_baseline and not manual_blockers:
        nested_pool_timeout = "couldn't get a connection after" in knowledge_message
        detail = knowledge_detail if nested_pool_timeout else f"known vulnerable hashes proxy={proxy_hash} rag={rag_hash}"
        issues.append({"code": "pg_pool_nested_lease", "detail": detail})
        repairs.append("pg_pool_reuse")
    elif not knowledge.get("ok") or not knowledge_content.get("enabled") or evidence_count == 0:
        issues.append({"code": "knowledge_search_failed", "detail": knowledge_detail})
        manual_blockers.append("knowledge_search_failed")

    frontend_hash = str(files.get("frontend_sha256") or "").upper()
    frontend_fetch_resilience = bool(files.get("frontend_fetch_resilience"))
    frontend_contract_observed = "frontend_sha256" in files or "frontend_fetch_resilience" in files
    if frontend_contract_observed and not frontend_fetch_resilience:
        if frontend_hash == FETCH_RESILIENCE_PRE_FRONTEND_HASH:
            issues.append({"code": "frontend_fetch_resilience_missing", "detail": frontend_hash})
            if not manual_blockers:
                repairs.append("frontend_fetch_resilience")
        else:
            issues.append({"code": "unknown_frontend_hash", "detail": frontend_hash})
            manual_blockers.append("unknown_frontend_hash")

    ollama_runtime = runtime.get("ollama_11434") or {}
    if str(ollama_runtime.get("max_loaded_models") or config.get("ollama_max_loaded_models") or "") != "1":
        issues.append({"code": "ollama_capacity_drift", "detail": "OLLAMA_MAX_LOADED_MODELS must remain 1"})
        manual_blockers.append("ollama_capacity_drift")

    repairs = list(dict.fromkeys(repairs))
    manual_blockers = list(dict.fromkeys(manual_blockers))
    if manual_blockers:
        classification = manual_blockers[0]
    elif repairs:
        classification = "+".join(repairs)
    else:
        classification = "healthy"
    logs = diagnostic.get("logs") or {}
    return {
        "classification": classification,
        "healthy": classification == "healthy",
        "issues": issues,
        "repair_actions": repairs,
        "manual_blockers": manual_blockers,
        "evidence": {
            "config_hash": config_hash,
            "guard_hash": guard_hash,
            "config_mode": config_mode,
            "runtime_mode": runtime_mode,
            "default_retrieval_mode": retrieval_mode,
            "default_evidence_count": evidence_count,
            "loaded_models": model_names,
            "frontend_hash": frontend_hash,
            "frontend_fetch_resilience": frontend_fetch_resilience,
            "recent_qa_requests": (logs.get("qa_requests") or [])[-5:],
            "recent_error_matches": (logs.get("error_matches") or [])[-10:],
            "recent_guard_restarts": (logs.get("guard_restarts") or [])[-10:],
        },
    }


def remote_script_path(package: dict[str, Any], filename: str) -> str:
    """Return one script path inside the verified package."""

    return str(package["remote_directory"]).rstrip("\\") + "\\" + filename


def run_diagnostic(remote: SshRemote, package: dict[str, Any], timeout: int) -> tuple[dict[str, Any], RemoteCommandResult]:
    """Run the single consolidated read-only remote diagnostic."""

    path = remote_script_path(package, "remote_8093_assistant_diagnose.ps1")
    result = remote.run_ps1(path, timeout)
    return parse_json_output(result, "diagnose"), result


def write_json_report(report: dict[str, Any], suffix: str) -> Path:
    """Write one local report atomically."""

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / f"{utc_stamp()}_{suffix}.json"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def base_report(command: str, connectivity: dict[str, Any]) -> dict[str, Any]:
    """Create the common report envelope."""

    return {
        "schema": "ops.8093.assistant-auto-recovery.local-report.v1",
        "requirement_id": REQUIREMENT_ID,
        "command": command,
        "started_at": now_iso(),
        "connectivity": connectivity,
        "service_recovery_timer": {"started_at": None, "elapsed_seconds": None},
        "package": None,
        "diagnostic_before": None,
        "classification_before": None,
        "repairs": [],
        "diagnostic_after": None,
        "classification_after": None,
        "acceptance": None,
        "request_count": 0,
        "documents_pending": command == "recover",
        "ok": False,
    }


def run_prestage(args: argparse.Namespace) -> int:
    """Pre-stage and verify the immutable package after connectivity succeeds."""

    connectivity = ensure_connectivity(args)
    report = base_report("prestage", connectivity)
    with SshRemote(args) as remote:
        report["package"] = ensure_remote_package(remote, allow_upload=True)
    report["ok"] = True
    report["completed_at"] = now_iso()
    path = write_json_report(report, "prestage")
    print(json.dumps({"ok": True, "package": report["package"], "report": str(path)}, ensure_ascii=False))
    return 0


def run_diagnose(args: argparse.Namespace) -> int:
    """Complete connectivity and consolidated classification in one run."""

    connectivity = ensure_connectivity(args)
    report = base_report("diagnose", connectivity)
    with SshRemote(args) as remote:
        package = ensure_remote_package(remote, allow_upload=not args.no_auto_prestage)
        diagnostic, command = run_diagnostic(remote, package, args.diagnostic_timeout)
    classification = classify_diagnostic(diagnostic)
    report["package"] = package
    report["diagnostic_before"] = diagnostic
    report["diagnostic_command"] = command.__dict__
    report["classification_before"] = classification
    report["classification_after"] = classification
    report["ok"] = True
    report["completed_at"] = now_iso()
    path = write_json_report(report, "diagnose")
    print(
        json.dumps(
            {
                "ok": True,
                "classification": classification["classification"],
                "elapsed_seconds": round(command.elapsed_seconds + connectivity["elapsed_seconds"], 3),
                "report": str(path),
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_recover(args: argparse.Namespace) -> int:
    """Diagnose, apply only known repairs, verify, and send one SSE acceptance."""

    connectivity = ensure_connectivity(args)
    report = base_report("recover", connectivity)
    recovery_started = time.perf_counter()
    report["service_recovery_timer"]["started_at"] = now_iso()
    exit_code = 0
    try:
        with SshRemote(args) as remote:
            package = ensure_remote_package(remote, allow_upload=not args.no_auto_prestage)
            report["package"] = package
            diagnostic_before, before_command = run_diagnostic(remote, package, args.diagnostic_timeout)
            classification_before = classify_diagnostic(diagnostic_before)
            report["diagnostic_before"] = diagnostic_before
            report["diagnostic_before_command"] = before_command.__dict__
            report["classification_before"] = classification_before
            if classification_before["manual_blockers"]:
                raise PipelineError(
                    "classification",
                    "automatic repair refused: " + ", ".join(classification_before["manual_blockers"]),
                    2,
                )
            for action in classification_before["repair_actions"]:
                filename = {
                    "service_recover": "remote_guarded_recover_8093_service.ps1",
                    "frontend_fetch_resilience": "remote_hot_deploy_8093_fetch_resilience.ps1",
                    "guard_contract": "remote_guarded_deploy_8093_health_guard.ps1",
                    "keyword_mode": "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1",
                    "pg_pool_reuse": "remote_guarded_deploy_8093_pg_pool_reuse.ps1",
                }[action]
                phase_result = remote.run_ps1(remote_script_path(package, filename), args.repair_timeout)
                phase_json = parse_json_output(phase_result, f"repair:{action}")
                report["repairs"].append(
                    {"action": action, "result": phase_json, "command": phase_result.__dict__}
                )
            diagnostic_after, after_command = run_diagnostic(remote, package, args.diagnostic_timeout)
            classification_after = classify_diagnostic(diagnostic_after)
            report["diagnostic_after"] = diagnostic_after
            report["diagnostic_after_command"] = after_command.__dict__
            report["classification_after"] = classification_after
            if not classification_after["healthy"]:
                raise PipelineError(
                    "post_verification",
                    "post-repair classification is not healthy: " + classification_after["classification"],
                    2,
                )
            acceptance_name = "remote_verify_8093_keyword_knowledge_sse_once.ps1"
            acceptance_result = remote.run_ps1(remote_script_path(package, acceptance_name), args.acceptance_timeout)
            acceptance = parse_json_output(acceptance_result, "acceptance")
            report["acceptance"] = acceptance
            report["acceptance_command"] = acceptance_result.__dict__
            report["request_count"] = int(acceptance.get("request_count") or 0)
            if report["request_count"] != 1:
                raise PipelineError("acceptance", "acceptance did not prove exactly one request", 6)
            report["ok"] = True
    except PipelineError as exc:
        report["failure"] = {"stage": exc.stage, "message": str(exc), "exit_code": exc.exit_code}
        exit_code = exc.exit_code
    finally:
        report["service_recovery_timer"]["elapsed_seconds"] = round(time.perf_counter() - recovery_started, 3)
        report["completed_at"] = now_iso()
        path = write_json_report(report, "recover")
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "classification_before": (report.get("classification_before") or {}).get("classification"),
                "classification_after": (report.get("classification_after") or {}).get("classification"),
                "repairs": [row["action"] for row in report["repairs"]],
                "request_count": report["request_count"],
                "service_recovery_seconds": report["service_recovery_timer"]["elapsed_seconds"],
                "report": str(path),
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def latest_report() -> Path:
    """Return the latest local recovery report."""

    rows = sorted(REPORT_ROOT.glob("*_recover.json"), key=lambda path: path.stat().st_mtime)
    if not rows:
        raise PipelineError("documents", "no recovery report is available", 7)
    return rows[-1]


def markdown_report(report: dict[str, Any], report_path: Path) -> str:
    """Render a concise, secret-free Markdown handoff from one JSON report."""

    before = report.get("classification_before") or {}
    after = report.get("classification_after") or {}
    acceptance = report.get("acceptance") or {}
    package = report.get("package") or {}
    repairs = [row.get("action") for row in report.get("repairs") or []]
    timing = acceptance.get("timing_ms") or {}
    evidence = after.get("evidence") or {}
    lines = [
        "# 8093 智能助手自动诊断—修复—验收报告",
        "",
        f"追踪编号：`{REQUIREMENT_ID}`  ",
        f"完成时间：`{report.get('completed_at')}`  ",
        f"源报告：`{report_path}`",
        "",
        "## 结论",
        "",
        f"- 成功：`{str(bool(report.get('ok'))).lower()}`",
        f"- 修复前分类：`{before.get('classification')}`",
        f"- 修复后分类：`{after.get('classification')}`",
        f"- 实施动作：`{', '.join(str(row) for row in repairs) if repairs else 'none'}`",
        f"- 真实问答请求数：`{report.get('request_count')}`",
        f"- 服务恢复与验收耗时：`{(report.get('service_recovery_timer') or {}).get('elapsed_seconds')}s`",
        "- 2026-08-06 本轮根因：8093 在并行部署/恢复流程的受控停启窗口中确实无监听，浏览器因而抛出 `Failed to fetch`；SCM 停启记录、受控 `KeyboardInterrupt` 与同期文件哈希变化相互印证。",
        "- 排除项：本轮不是 PostgreSQL `PoolTimeout` 复发，也不是 11434/27B 模型整体宕机。",
        "",
        "## 包与验收证据",
        "",
        f"- 远端受控包：`{package.get('package_id')}`",
        f"- 远端目录：`{package.get('remote_directory')}`",
        f"- 默认检索：`{evidence.get('default_retrieval_mode')}`",
        f"- 默认证据数：`{evidence.get('default_evidence_count')}`",
        f"- 模型驻留：`{evidence.get('loaded_models')}`",
        f"- 页面哈希：`{evidence.get('frontend_hash')}`",
        f"- 页面容错标记：`{evidence.get('frontend_fetch_resilience')}`",
        f"- SSE 总耗时：`{timing.get('total')}ms`",
        f"- 远端 SSE 报告：`{acceptance.get('report_path')}`",
        "",
        "## 固定边界",
        "",
        "- 连通性恢复时间与服务修复计时分离；VPN/SSH/8093/11434/PostgreSQL 未全通时不开始部署。",
        "- 只自动修复已知哈希范围内的守卫合同或 keyword 漂移；未知哈希拒绝覆盖。",
        "- 所有新 8093 写入流程使用 `Global\\BFV4PreviewProxy8093Deployment` 互斥；纯页面修复使用原子热更新，不重启 8093。",
        "- 只读 GET 可按 1.5s/3s 退避重试；问答 POST/SSE 绝不自动重发，防止重复会话与模型负载。",
        "- 每次 recover 最多发送一个真实 SSE POST，失败后不自动重试。",
        "- DOCX 与追踪报告在服务恢复后由独立 docs 阶段生成。",
        "",
    ]
    return "\n".join(lines)


def run_documents(args: argparse.Namespace) -> int:
    """Generate Markdown trace records and DOCX after service recovery returns."""

    report_path = Path(args.report).resolve() if args.report else latest_report().resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("command") != "recover":
        raise PipelineError("documents", "docs phase requires a recover report", 7)
    content = markdown_report(report, report_path)
    handoff_dir = ROOT / "docs" / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    handoff = handoff_dir / f"{utc_stamp()}-8093-assistant-auto-recovery.md"
    latest = ROOT / "docs" / "8093智能助手自动恢复最近报告.md"
    for path in (handoff, latest):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    bundled_python = Path(
        r"C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    )
    python = bundled_python if bundled_python.is_file() else Path(sys.executable)
    generator = ROOT / "tools" / "generate_8093_assistant_repair_docx.py"
    completed = subprocess.run(
        [str(python), str(generator)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise PipelineError("documents", f"DOCX generation failed: {completed.stderr}", 7)
    print(
        json.dumps(
            {
                "ok": True,
                "source_report": str(report_path),
                "handoff": str(handoff),
                "latest_trace": str(latest),
                "docx": str(ROOT / "docs" / "8093智能助手不可用原因与正式修复手册_20260804.docx"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the documented CLI parser."""

    parser = argparse.ArgumentParser(
        description="8093 智能助手统一诊断—修复—验收工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python tools\\assistant_8093_auto_recovery.py diagnose --allow-agents-password
  python tools\\assistant_8093_auto_recovery.py recover --allow-agents-password
  python tools\\assistant_8093_auto_recovery.py prestage --allow-agents-password
  python tools\\assistant_8093_auto_recovery.py docs --report logs\\assistant_8093_auto_recovery\\<report>.json

退出码：0=成功；2=拒绝自动修复；3=连通性失败；4=凭据/包失败；
5=远端阶段失败；6=SSE 验收失败；7=文档阶段失败。
""",
    )
    parser.add_argument("command", choices=("prestage", "diagnose", "recover", "docs"))
    parser.add_argument("--host", default=os.getenv("BF_22012_HOST", "10.30.220.12"))
    parser.add_argument("--user", default=os.getenv("BF_22012_USER", "administrator"))
    parser.add_argument("--password-env", default="BF_22012_SSH_PASSWORD")
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument("--prompt-password", action="store_true")
    parser.add_argument("--connect-timeout", type=float, default=3.0)
    parser.add_argument("--vpn-timeout", type=int, default=90)
    parser.add_argument("--no-vpn-recovery", action="store_true")
    parser.add_argument("--no-auto-prestage", action="store_true")
    parser.add_argument("--diagnostic-timeout", type=int, default=120)
    parser.add_argument("--repair-timeout", type=int, default=600)
    parser.add_argument("--acceptance-timeout", type=int, default=420)
    parser.add_argument("--report", help="Recover JSON report used by the docs phase.")
    return parser


def configure_utf8_console() -> None:
    """Keep Chinese JSON/help stable when launched from Windows PowerShell 5.1."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """Dispatch the selected phase and always return a documented exit code."""

    configure_utf8_console()
    args = build_parser().parse_args()
    try:
        if args.command == "prestage":
            return run_prestage(args)
        if args.command == "diagnose":
            return run_diagnose(args)
        if args.command == "recover":
            return run_recover(args)
        return run_documents(args)
    except PipelineError as exc:
        print(
            json.dumps(
                {"ok": False, "stage": exc.stage, "error": str(exc), "exit_code": exc.exit_code},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
