from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location(
    "remote_22012_session_under_test",
    TOOLS / "remote_22012_session.py",
)
assert SPEC and SPEC.loader
SESSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SESSION)


class FakeTransport:
    def __init__(self) -> None:
        self.keepalive = None

    def is_active(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return True

    def set_keepalive(self, seconds: int) -> None:
        self.keepalive = seconds


class FakeClient:
    def __init__(self) -> None:
        self.transport = FakeTransport()
        self.closed = False

    def get_transport(self) -> FakeTransport:
        return self.transport

    def close(self) -> None:
        self.closed = True


def connection_args() -> argparse.Namespace:
    return argparse.Namespace(
        host="10.30.220.12",
        user="administrator",
        workdir=SESSION.DEFAULT_REMOTE_ROOT,
        password_env="BF_22012_SSH_PASSWORD",
        password_file=str(SESSION.remote_exec.DEFAULT_PASSWORD_FILE),
        allow_agents_password=False,
        prompt_password=False,
        timeout=30,
    )


def test_session_state_is_outside_repository() -> None:
    assert ROOT not in SESSION.DEFAULT_STATE.parents
    assert SESSION.DEFAULT_STATE.name == "22012.json"


def test_ensure_reuses_one_authenticated_transport(monkeypatch) -> None:
    fake = FakeClient()
    calls = []
    monkeypatch.setattr(SESSION.remote_exec, "connect", lambda args: calls.append(args) or fake)
    manager = SESSION.SessionManager(connection_args(), "session-a")

    first_client, first_reused = manager.ensure()
    second_client, second_reused = manager.ensure()

    assert first_client is second_client is fake
    assert first_reused is False
    assert second_reused is True
    assert len(calls) == 1
    assert fake.transport.keepalive == SESSION.KEEPALIVE_SECONDS


def test_transport_failure_is_not_replayed(monkeypatch) -> None:
    fake = FakeClient()
    connect_calls = []
    execute_calls = []
    monkeypatch.setattr(SESSION.remote_exec, "connect", lambda args: connect_calls.append(args) or fake)
    parsed = argparse.Namespace(
        host="10.30.220.12",
        user="administrator",
        upload_only=False,
    )
    monkeypatch.setattr(SESSION.remote_exec, "parse_args", lambda argv: parsed)

    fake_sftp = object()
    monkeypatch.setattr(manager := SESSION.SessionManager(connection_args(), "session-b"), "ensure_sftp", lambda client: fake_sftp)

    def fail_once(args, client, sftp, timings):
        execute_calls.append((args, client, sftp))
        raise paramiko.SSHException("transport lost")

    monkeypatch.setattr(SESSION.remote_exec, "execute", fail_once)
    result = manager.execute({"argv": ["--command", "Write-Output ok"]})

    assert result["ok"] is False
    assert result["uncertain_execution"] is True
    assert result["automatic_replay"] is False
    assert "phase_duration_ms" in result
    assert len(connect_calls) == 1
    assert len(execute_calls) == 1


def test_run_parser_preserves_remote_arguments() -> None:
    args = SESSION.parse_args(["run", "--", "--timeout", "60", "--command", "Write-Output ok"])
    assert args.action == "run"
    assert args.remote_args == ["--", "--timeout", "60", "--command", "Write-Output ok"]


def test_remote_exec_supports_caller_owned_client() -> None:
    source = (TOOLS / "remote_22012_exec.py").read_text(encoding="utf-8")
    assert "def execute(" in source
    assert "sftp: paramiko.SFTPClient | None = None" in source
    assert '"--emit-timing-json"' in source
    assert '"bf.remote-exec.timing.v1"' in source
    assert "if owns_client:" in source


def test_remote_exec_supports_protected_password_file(monkeypatch, tmp_path: Path) -> None:
    password_file = tmp_path / "22012.pw"
    password_file.write_text("secret-from-file\n", encoding="utf-8")
    args = argparse.Namespace(
        password_env="BF_22012_TEST_PASSWORD",
        password_file=str(password_file),
        allow_agents_password=False,
        prompt_password=False,
    )
    monkeypatch.delenv("BF_22012_TEST_PASSWORD", raising=False)
    monkeypatch.delenv("BF_22012_SSH_PASSWORD", raising=False)

    assert SESSION.remote_exec.resolve_password(args) == "secret-from-file"


def test_keepalive_and_latency_benchmark_contracts() -> None:
    benchmark = (TOOLS / "benchmark_22012_ssh_command_latency.ps1").read_text(encoding="utf-8")
    assert SESSION.KEEPALIVE_SECONDS == 30
    assert "ValidateRange(5, 50)" in benchmark
    assert "alternating_cold_and_reused" in benchmark
    assert "cold_p90_ms" in benchmark and "reused_p90_ms" in benchmark
    assert "break_even_command_count" in benchmark
    assert "production_write_performed = $false" in benchmark


def test_stop_removes_only_a_dead_broker_stale_state(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "22012.json"
    state_path.write_text(json.dumps({"pid": 999999, "broker_port": 1}), encoding="utf-8")
    monkeypatch.setattr(SESSION, "_request", lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(SESSION, "_pid_is_running", lambda pid: False)
    result = SESSION._stop_daemon(state_path)
    assert result["ok"] is True
    assert result["stale_state_removed"] is True
    assert not state_path.exists()
