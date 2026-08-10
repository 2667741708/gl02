"""Contracts and simulations for the one-click 8093 assistant recovery tool.

TEST-8093-ASSISTANT-AUTO-RECOVERY-20260805
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "assistant_8093_auto_recovery.py"
DIAGNOSE_PS1 = ROOT / "tools" / "remote_8093_assistant_diagnose.ps1"
KEYWORD_DEPLOYER = ROOT / "tools" / "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1"
SERVICE_RECOVERY = ROOT / "tools" / "remote_guarded_recover_8093_service.ps1"
FETCH_RESILIENCE_DEPLOYER = ROOT / "tools" / "remote_hot_deploy_8093_fetch_resilience.ps1"
ACCEPTANCE_PS1 = ROOT / "tools" / "remote_verify_8093_keyword_knowledge_sse_once.ps1"
PS1_SYNTAX_CHECKER = ROOT / "tools" / "check_ps1_syntax.ps1"

SPEC = importlib.util.spec_from_file_location("assistant_8093_auto_recovery", TOOL_PATH)
assert SPEC and SPEC.loader
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def powershell_51_copy(source: Path, destination: Path) -> Path:
    """Mirror the BOM-normalized bytes used by the remote package builder."""

    payload = source.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    destination.write_bytes(b"\xef\xbb\xbf" + payload)
    return destination


def healthy_diagnostic() -> dict:
    return {
        "schema": "ops.8093.assistant-auto-diagnose.v1",
        "services": [
            {"name": "BFV4PreviewProxy8093", "status": "Running"},
            {"name": "BFOllama11434", "status": "Running"},
            {"name": "BFV4PreviewWs8768", "status": "Running"},
        ],
        "listeners": [
            {"port": 5432, "listening": True, "pid": 10},
            {"port": 8093, "listening": True, "pid": 11},
            {"port": 8094, "listening": True, "pid": 14},
            {"port": 8768, "listening": True, "pid": 12},
            {"port": 8770, "listening": True, "pid": 15},
            {"port": 11434, "listening": True, "pid": 13},
        ],
        "endpoints": [
            {
                "name": "assistant_status",
                "ok": True,
                "content": {"ok": True, "proxy_ok": True, "model_ok": True},
            },
            {
                "name": "ollama_processes",
                "ok": True,
                "content": {"models": [{"name": tool.APPROVED_MODEL}]},
            },
            {
                "name": "default_knowledge_search",
                "ok": True,
                "content": {"enabled": True, "retrieval_mode": "keyword", "evidence": [{"title": "e1"}]},
            },
        ],
        "runtime": {
            "assistant_8093": {"knowledge_search_mode": "keyword"},
            "ollama_11434": {"max_loaded_models": "1"},
        },
        "files": {
            "proxy_sha256": tool.PG_POOL_ACTIVE_PROXY_HASH,
            "rag_sha256": tool.PG_POOL_FINAL_RAG_HASH,
            "assistant_pg_sha256": tool.PG_POOL_FINAL_ASSISTANT_PG_HASH,
            "frontend_sha256": "1" * 64,
            "frontend_fetch_resilience": True,
        },
        "config": {
            "sha256": tool.CURRENT_CONFIG_HASH,
            "knowledge_search_mode": "keyword",
            "health": {
                "failure_threshold": 3,
                "service_down_threshold": 1,
                "pre_restart_backoff_seconds": 15,
                "restart_cooldown_seconds": 600,
            },
            "ollama_max_loaded_models": "1",
        },
        "guard": {
            "script_sha256": tool.CURRENT_GUARD_HASH,
            "task_state": "Ready",
            "last_task_result": 0,
            "state": {"consecutiveFailures": 0},
        },
        "logs": {"qa_requests": [], "error_matches": [], "guard_restarts": []},
    }


def test_package_is_immutable_and_powershell_payloads_have_bom() -> None:
    package_id, manifest, payloads = tool.build_package()
    package_id_again, manifest_again, payloads_again = tool.build_package()

    assert package_id == package_id_again
    assert manifest == manifest_again
    assert payloads == payloads_again
    assert package_id.startswith(tool.PACKAGE_VERSION + "_")
    for name, payload in payloads.items():
        if name.endswith(".ps1"):
            assert payload.startswith(b"\xef\xbb\xbf")


def test_healthy_runtime_classifies_without_repair() -> None:
    result = tool.classify_diagnostic(healthy_diagnostic())

    assert result["classification"] == "healthy"
    assert result["healthy"] is True
    assert result["repair_actions"] == []
    assert result["evidence"]["default_retrieval_mode"] == "keyword"


def test_keyword_drift_maps_directly_to_existing_deployer() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["config"]["sha256"] = tool.PRE_KEYWORD_CONFIG_HASH
    diagnostic["config"]["knowledge_search_mode"] = ""
    diagnostic["runtime"]["assistant_8093"]["knowledge_search_mode"] = "hybrid"
    diagnostic["endpoints"][2]["content"]["retrieval_mode"] = "hybrid"

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "keyword_mode"
    assert result["repair_actions"] == ["keyword_mode"]
    assert result["manual_blockers"] == []


def test_old_guard_and_keyword_drift_are_repaired_in_order() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["config"]["sha256"] = tool.OLD_GUARD_CONFIG_HASH
    diagnostic["config"]["knowledge_search_mode"] = ""
    diagnostic["config"]["health"] = {
        "failure_threshold": 1,
        "service_down_threshold": 1,
        "pre_restart_backoff_seconds": 0,
        "restart_cooldown_seconds": 0,
    }
    diagnostic["guard"]["script_sha256"] = tool.OLD_GUARD_HASH
    diagnostic["runtime"]["assistant_8093"]["knowledge_search_mode"] = "hybrid"
    diagnostic["endpoints"][2]["content"]["retrieval_mode"] = "hybrid"

    result = tool.classify_diagnostic(diagnostic)

    assert result["repair_actions"] == ["guard_contract", "keyword_mode"]
    assert result["manual_blockers"] == []


def test_unknown_hash_refuses_automatic_repair() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["config"]["sha256"] = "0" * 64

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "unknown_config_hash"
    assert result["repair_actions"] == []
    assert "unknown_config_hash" in result["manual_blockers"]


def test_known_nested_pool_timeout_maps_to_pool_reuse_deployer() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["files"] = {
        "proxy_sha256": tool.PG_POOL_PRE_PROXY_HASH,
        "rag_sha256": tool.PG_POOL_PRE_RAG_HASH,
    }
    knowledge = diagnostic["endpoints"][2]["content"]
    knowledge["enabled"] = False
    knowledge["evidence"] = []
    knowledge["message"] = "PostgreSQL 知识索引不可用：couldn't get a connection after 10.00 sec"

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "pg_pool_reuse"
    assert result["repair_actions"] == ["pg_pool_reuse"]
    assert result["manual_blockers"] == []


def test_known_vulnerable_pool_hashes_repair_even_during_healthy_probe() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["files"] = {
        "proxy_sha256": tool.PG_POOL_PRE_PROXY_HASH,
        "rag_sha256": tool.PG_POOL_PRE_RAG_HASH,
    }

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "pg_pool_reuse"
    assert result["repair_actions"] == ["pg_pool_reuse"]
    assert result["manual_blockers"] == []


def test_known_pool_hashes_are_not_misclassified_when_search_times_out() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["files"] = {
        "proxy_sha256": tool.PG_POOL_PRE_PROXY_HASH,
        "rag_sha256": tool.PG_POOL_PRE_RAG_HASH,
    }
    diagnostic["endpoints"][2] = {
        "name": "default_knowledge_search",
        "ok": False,
        "content": None,
        "error": "The operation has timed out.",
    }

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "pg_pool_reuse"
    assert result["repair_actions"] == ["pg_pool_reuse"]


def test_connectivity_allows_8093_to_be_the_failed_component() -> None:
    snapshot = {
        "targets": {
            "ssh": {"ok": True},
            "postgresql": {"ok": True},
            "assistant_8093": {"ok": False},
            "ollama_11434": {"ok": True},
        }
    }

    assert tool.infrastructure_connectivity_ok(snapshot) is True


def test_known_final_runtime_with_only_8093_down_maps_to_service_recovery() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["services"][0]["status"] = "Stopped"
    diagnostic["listeners"][1] = {"port": 8093, "listening": False, "pid": None}
    diagnostic["endpoints"][0] = {
        "name": "assistant_status",
        "ok": False,
        "content": None,
        "error": "TCP 8093 is not listening",
    }
    diagnostic["endpoints"][2] = {
        "name": "default_knowledge_search",
        "ok": False,
        "content": None,
        "error": "TCP 8093 is not listening",
    }

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "service_recover"
    assert result["repair_actions"] == ["service_recover"]
    assert result["manual_blockers"] == []


def test_unknown_backend_hash_refuses_service_recovery() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["services"][0]["status"] = "Stopped"
    diagnostic["listeners"][1] = {"port": 8093, "listening": False, "pid": None}
    diagnostic["endpoints"][0] = {"name": "assistant_status", "ok": False, "error": "down"}
    diagnostic["files"]["proxy_sha256"] = "0" * 64

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "service_unavailable"
    assert result["repair_actions"] == []


def test_known_frontend_without_fetch_resilience_maps_to_hot_patch() -> None:
    diagnostic = healthy_diagnostic()
    diagnostic["files"]["frontend_sha256"] = tool.FETCH_RESILIENCE_PRE_FRONTEND_HASH
    diagnostic["files"]["frontend_fetch_resilience"] = False

    result = tool.classify_diagnostic(diagnostic)

    assert result["classification"] == "frontend_fetch_resilience"
    assert result["repair_actions"] == ["frontend_fetch_resilience"]
    assert result["manual_blockers"] == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 serialization test")
def test_powershell_51_diagnostic_serializes_numeric_ports_as_array(tmp_path: Path) -> None:
    fixture = {
        "listeners": {
            "8093": {"listening": True, "pid": 101},
            "11434": {"listening": True, "pid": 202},
        },
        "services": [{"name": "BFV4PreviewProxy8093", "status": "Running"}],
        "endpoints": [],
        "config": {"knowledge_search_mode": "keyword"},
        "guard": {"task_state": "Ready"},
        "logs": {},
    }
    path = tmp_path / "diagnostic-simulation.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    script_path = powershell_51_copy(DIAGNOSE_PS1, tmp_path / DIAGNOSE_PS1.name)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-SimulationInputPath",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.lstrip("\ufeff"))
    assert result["listeners"] == [
        {"port": 8093, "listening": True, "pid": 101},
        {"port": 11434, "listening": True, "pid": 202},
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 serialization test")
def test_powershell_51_deployer_simulation_catches_numeric_key_regression(tmp_path: Path) -> None:
    fixture = {
        "listeners": {
            "8093": {"before": 101, "after": 102},
            "8768": {"before": 201, "after": 201},
            "11434": {"before": 301, "after": 301},
        },
        "rollback_applied": False,
        "process_mode_keyword": True,
        "default_keyword_search_ok": True,
    }
    path = tmp_path / "deployer-simulation.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    script_path = powershell_51_copy(KEYWORD_DEPLOYER, tmp_path / KEYWORD_DEPLOYER.name)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-SimulationInputPath",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.lstrip("\ufeff"))
    assert isinstance(result["pids"], list)
    assert result["pids"][0] == {"port": 8093, "before": 101, "after": 102}
    assert result["checks"]["process_mode_keyword"] is True


def test_recover_pipeline_uses_short_phases_and_exactly_one_sse(monkeypatch, tmp_path: Path) -> None:
    before = healthy_diagnostic()
    before["config"]["sha256"] = tool.PRE_KEYWORD_CONFIG_HASH
    before["config"]["knowledge_search_mode"] = ""
    before["runtime"]["assistant_8093"]["knowledge_search_mode"] = "hybrid"
    before["endpoints"][2]["content"]["retrieval_mode"] = "hybrid"
    after = healthy_diagnostic()
    calls: list[str] = []
    diagnose_count = 0

    class FakeRemote:
        def __init__(self, args) -> None:
            self.args = args

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def run_ps1(self, path: str, timeout: int):
            nonlocal diagnose_count
            name = Path(path).name
            calls.append(name)
            if name == "remote_8093_assistant_diagnose.ps1":
                value = before if diagnose_count == 0 else after
                diagnose_count += 1
            elif name == "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1":
                value = {"schema": "deploy", "rollback_applied": False}
            else:
                value = {
                    "schema": "acceptance",
                    "request_count": 1,
                    "report_path": "remote-report.json",
                    "timing_ms": {"total": 1000},
                }
            return tool.RemoteCommandResult(path, 0, json.dumps(value), "", 0.1)

    monkeypatch.setattr(tool, "ensure_connectivity", lambda args: {"elapsed_seconds": 0.1, "ready_at": tool.now_iso()})
    monkeypatch.setattr(tool, "SshRemote", FakeRemote)
    monkeypatch.setattr(
        tool,
        "ensure_remote_package",
        lambda remote, allow_upload: {"package_id": "test", "remote_directory": r"C:\pkg"},
    )
    monkeypatch.setattr(tool, "write_json_report", lambda report, suffix: tmp_path / f"{suffix}.json")
    args = SimpleNamespace(
        no_auto_prestage=False,
        diagnostic_timeout=120,
        repair_timeout=600,
        acceptance_timeout=420,
    )

    assert tool.run_recover(args) == 0
    assert calls == [
        "remote_8093_assistant_diagnose.ps1",
        "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1",
        "remote_8093_assistant_diagnose.ps1",
        "remote_verify_8093_keyword_knowledge_sse_once.ps1",
    ]
    assert calls.count("remote_verify_8093_keyword_knowledge_sse_once.ps1") == 1


def test_remote_execution_contract_uses_only_short_file_commands() -> None:
    source = TOOL_PATH.read_text(encoding="utf-8")

    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File" in source
    assert "-EncodedCommand" not in source
    assert "ScriptBlock::Create" not in source
    assert "remote.run_ps1" in source
    assert "request_count" in source


def test_diagnostic_preserves_unsigned_task_result_range() -> None:
    source = DIAGNOSE_PS1.read_text(encoding="utf-8")

    assert "[long]$taskInfo.LastTaskResult" in source
    assert "[int]$taskInfo.LastTaskResult" not in source


def test_diagnostic_uses_one_listener_snapshot_and_skips_dead_8093_http_waits() -> None:
    source = DIAGNOSE_PS1.read_text(encoding="utf-8")

    assert "Get-NetTCPConnection -State Listen" in source
    assert "Get-NetTCPConnection -LocalPort $Port" not in source
    assert "Get-UnavailableEndpointRow" in source
    assert "-MaxEvents 500" in source


def test_acceptance_uses_two_listener_snapshots_instead_of_ten_port_queries() -> None:
    source = ACCEPTANCE_PS1.read_text(encoding="utf-8")

    assert source.count("Get-ListenerSnapshot") == 3
    assert "Get-NetTCPConnection -LocalPort $Port" not in source


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 parser test")
@pytest.mark.parametrize(
    "source",
    [DIAGNOSE_PS1, SERVICE_RECOVERY, FETCH_RESILIENCE_DEPLOYER, ACCEPTANCE_PS1],
)
def test_remote_powershell_scripts_parse_with_51(source: Path, tmp_path: Path) -> None:
    script_path = powershell_51_copy(source, tmp_path / source.name)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1_SYNTAX_CHECKER),
            "-Path",
            str(script_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_cli_help_documents_examples_and_exit_codes() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    assert "diagnose" in completed.stdout
    assert "recover" in completed.stdout
    assert "prestage" in completed.stdout
    assert "退出码" in completed.stdout
