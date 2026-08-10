from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools" / "check_managed_nssm_service_health.ps1"
PATCHER = ROOT / "tools" / "patch_8093_health_guard_config.py"
DEPLOY = ROOT / "tools" / "remote_guarded_deploy_8093_health_guard.ps1"
RUNTIME_PROBE = ROOT / "tools" / "probe_8093_health_guard_runtime.ps1"
SSE_VERIFY = ROOT / "tools" / "verify_8093_assistant_sse_once.py"
REMOTE_SSE_VERIFY = ROOT / "tools" / "remote_verify_8093_assistant_sse_once.ps1"


def base_config(tmp_path: Path) -> dict:
    return {
        "serviceName": "BFV4PreviewProxy8093",
        "root": str(tmp_path),
        "logDir": str(tmp_path),
        "logPrefix": "proxy_8093",
        "health": {
            "tcpTimeoutMilliseconds": 50,
            "tcp": [{"host": "127.0.0.1", "port": 8093}],
            "http": [],
        },
    }


def test_config_patcher_is_exact_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "8093.json"
    path.write_text(json.dumps(base_config(tmp_path), ensure_ascii=False), encoding="utf-8")

    first = subprocess.run(
        [sys.executable, str(PATCHER), "--config", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    second = subprocess.run(
        [sys.executable, str(PATCHER), "--config", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    config = json.loads(path.read_text(encoding="utf-8"))

    assert json.loads(first.stdout)["changed"] is True
    assert json.loads(second.stdout)["changed"] is False
    assert config["health"] | {
        "failureThreshold": 3,
        "serviceNotRunningFailureThreshold": 1,
        "preRestartBackoffSeconds": 15,
        "restartCooldownSeconds": 600,
    } == config["health"]


def test_config_patcher_rejects_other_services(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["serviceName"] = "BFOllama11434"
    path = tmp_path / "other.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PATCHER), "--config", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0
    assert "unexpected serviceName" in result.stderr


def test_guard_and_deployer_encode_resilience_and_isolation_contract() -> None:
    guard = GUARD.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    probe = RUNTIME_PROBE.read_text(encoding="utf-8")

    for marker in (
        "consecutiveFailures",
        "failureThreshold",
        "preRestartBackoffSeconds",
        "restartCooldownSeconds",
        "restart_deferred",
        "restart_suppressed_cooldown",
        "recovered_during_backoff",
    ):
        assert marker in guard
    for marker in (
        "BFV4PreviewProxy8093HealthCheck",
        "service_8093_pid_unchanged",
        "ws_8768_pid_unchanged",
        "preview_8094_pid_unchanged",
        "ollama_11434_pid_unchanged",
        "only_approved_27b_loaded",
        "rolled back",
    ):
        assert marker in deploy
    assert "ops.8093.health-guard-runtime.readonly.v2" in probe


def test_sse_acceptance_is_single_request_and_requires_complete_event_chain() -> None:
    verifier = SSE_VERIFY.read_text(encoding="utf-8")
    wrapper = REMOTE_SSE_VERIFY.read_text(encoding="utf-8")

    assert verifier.count('"POST",') == 1
    assert '"request_count": 1' in verifier
    assert 'required_events = {"start", "delta", "final", "done"}' in verifier
    assert '"use_mcp_tools": False' in verifier
    assert "no_guard_restart_during_acceptance" in wrapper
    assert "service_8093_pid_unchanged" in wrapper
    assert "ollama_11434_pid_unchanged" in wrapper


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell service-state contract is Windows-only")
def test_two_transient_failures_are_deferred_and_success_resets_state(tmp_path: Path) -> None:
    service_check = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "(Get-Service -Name EventLog).Status.ToString()"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if service_check.returncode != 0 or "Running" not in service_check.stdout:
        pytest.skip("Windows EventLog service is not available and running")

    config = {
        "serviceName": "EventLog",
        "root": str(tmp_path),
        "logDir": str(tmp_path),
        "logPrefix": "guard_contract",
        "health": {
            "tcpTimeoutMilliseconds": 30,
            "tcp": [{"host": "127.0.0.1", "port": 1}],
            "failureThreshold": 3,
            "serviceNotRunningFailureThreshold": 1,
            "preRestartBackoffSeconds": 0,
            "restartCooldownSeconds": 600,
        },
    }
    path = tmp_path / "guard.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(GUARD),
        "-ConfigPath",
        str(path),
    ]

    first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert first.returncode == 1
    assert second.returncode == 1

    state_path = tmp_path / "guard_contract.health.state.json"
    log_path = tmp_path / "guard_contract.health.log"
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    log = log_path.read_text(encoding="utf-8-sig")
    assert state["consecutiveFailures"] == 2
    assert "consecutive_failures=1 threshold=3" in log
    assert "consecutive_failures=2 threshold=3" in log
    assert "restart_deferred" in log
    assert "restart_service reason=" not in log

    config["health"]["tcp"] = []
    path.write_text(json.dumps(config), encoding="utf-8")
    recovered = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert recovered.returncode == 0
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    log = log_path.read_text(encoding="utf-8-sig")
    assert state["consecutiveFailures"] == 0
    assert "recovered previous_failures=2" in log
