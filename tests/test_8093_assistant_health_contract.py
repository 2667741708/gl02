from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
AGENTS = ROOT / "AGENTS.md"
PROBE = ROOT / "tools" / "probe_8093_assistant_health.ps1"
LOG_PROBE = ROOT / "tools" / "probe_8093_assistant_log_tail.ps1"
DEPLOY = ROOT / "tools" / "remote_patch_8093_assistant_name.ps1"


def test_8093_navigation_uses_short_assistant_name() -> None:
    text = PAGE.read_text(encoding="utf-8")

    assert "['qa', '智能助手', '☻']" in text
    assert "智能问答/知识助手" not in text


def test_agents_contains_layered_8093_assistant_check_flow() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    required = (
        "OPS-8093-ASSISTANT-HEALTH-CHECK-20260804",
        "tools/probe_8093_assistant_health.ps1",
        "/api/ollama/status",
        "/api/qa/chat",
        "audit_22012_proxy_model_env.ps1",
        "proxy_8093.service.err.log",
        "OLLAMA_MAX_LOADED_MODELS=1",
        "BF_QA_KNOWLEDGE_SEARCH_MODE",
        "start -> delta -> final",
    )
    for marker in required:
        assert marker in text


def test_readonly_probe_has_no_service_or_file_mutation() -> None:
    text = PROBE.read_text(encoding="utf-8") + LOG_PROBE.read_text(encoding="utf-8")

    assert "ops.8093.assistant-health.readonly.v1" in text
    assert "ops.8093.assistant-log-tail.readonly.v1" in text
    for forbidden in (
        "Restart-Service",
        "Stop-Service",
        "Start-Service",
        "taskkill",
        "Remove-Item",
        "Move-Item",
        "Set-Content",
    ):
        assert forbidden not in text


def test_name_deploy_is_exact_idempotent_and_protects_8094() -> None:
    text = DEPLOY.read_text(encoding="utf-8")

    assert "Unexpected 8093 navigation title counts" in text
    assert "8094 preview page changed unexpectedly" in text
    assert "http_new_count" in text
    assert "[IO.File]::Replace" in text
