from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "patch_8093_keyword_knowledge_mode.py"
DEPLOYER = ROOT / "tools" / "remote_guarded_deploy_8093_keyword_knowledge_mode.ps1"
SSE_WRAPPER = ROOT / "tools" / "remote_verify_8093_keyword_knowledge_sse_once.ps1"


def base_config() -> dict[str, object]:
    return {
        "serviceName": "BFV4PreviewProxy8093",
        "env": {"BF_PROXY_PORT": "8093"},
        "health": {
            "tcp": [{"host": "127.0.0.1", "port": 8093}],
            "failureThreshold": 3,
            "serviceNotRunningFailureThreshold": 1,
            "preRestartBackoffSeconds": 15,
            "restartCooldownSeconds": 600,
        },
    }


def run_patcher(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PATCHER), "--config", str(path)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def test_patcher_sets_keyword_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "22012_BFV4PreviewProxy8093.json"
    path.write_text(json.dumps(base_config(), ensure_ascii=False), encoding="utf-8")

    first = run_patcher(path)
    second = run_patcher(path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout)["changed"] is True
    assert json.loads(second.stdout)["changed"] is False
    patched = json.loads(path.read_text(encoding="utf-8"))
    assert patched["env"]["BF_QA_KNOWLEDGE_SEARCH_MODE"] == "keyword"
    assert patched["health"] | {
        "failureThreshold": 3,
        "serviceNotRunningFailureThreshold": 1,
        "preRestartBackoffSeconds": 15,
        "restartCooldownSeconds": 600,
    } == patched["health"]


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.update(serviceName="BFV4PreviewProxy8094"), "unexpected serviceName"),
        (lambda value: value["env"].update(BF_PROXY_PORT="8094"), "BF_PROXY_PORT must be 8093"),
        (lambda value: value["health"].update(failureThreshold=1), "health contract drifted"),
        (
            lambda value: value["env"].update(BF_QA_KNOWLEDGE_SEARCH_MODE="vector"),
            "unexpected existing BF_QA_KNOWLEDGE_SEARCH_MODE",
        ),
    ],
)
def test_patcher_rejects_wrong_scope_or_drift(tmp_path: Path, mutator, message: str) -> None:
    config = base_config()
    mutator(config)
    path = tmp_path / "service.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    result = run_patcher(path)

    assert result.returncode != 0
    assert message in result.stderr


def test_guarded_deployer_contract() -> None:
    source = DEPLOYER.read_text(encoding="utf-8")
    for marker in (
        "BFV4PreviewProxy8093",
        "BFV4PreviewProxy8093HealthCheck",
        "patch_8093_keyword_knowledge_mode.py",
        "BF_QA_KNOWLEDGE_SEARCH_MODE",
        'knowledge_search_mode = "keyword"',
        "failureThreshold",
        "serviceNotRunningFailureThreshold",
        "preRestartBackoffSeconds",
        "restartCooldownSeconds",
        "service_8093_pid_changed",
        "ws_8768_pid_unchanged",
        "preview_8094_pid_unchanged",
        "db_bridge_8770_pid_unchanged",
        "ollama_11434_pid_unchanged",
        "only_approved_27b_loaded",
        "default_keyword_search_ok",
        "rollback_applied",
    ):
        assert marker in source
    assert "OLLAMA_MAX_LOADED_MODELS=2" not in source
    assert "Stop-Service -Name BFOllama11434" not in source
    assert "Stop-Service -Name BFV4PreviewWs8768" not in source


def test_keyword_sse_acceptance_contract() -> None:
    source = SSE_WRAPPER.read_text(encoding="utf-8")
    for marker in (
        "request_count",
        "--require-knowledge",
        "prepared_knowledge",
        "BF_QA_KNOWLEDGE_SEARCH_MODE",
        "retrieval_mode",
        "exactly_one_request",
        "no_guard_restart_during_acceptance",
        "only_approved_27b_loaded",
        "ws_8768_pid_unchanged",
        "preview_8094_pid_unchanged",
        "db_bridge_8770_pid_unchanged",
        "ollama_11434_pid_unchanged",
        "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE",
    ):
        assert marker in source
    assert source.count("$output = & $python -X utf8 $payload --timeout") == 1
