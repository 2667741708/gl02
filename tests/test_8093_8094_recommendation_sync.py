from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_builder_packages_full_engine_and_shared_runtime() -> None:
    source = (ROOT / "tools" / "build_8093_8094_recommendation_sync.py").read_text(encoding="utf-8")
    assert 'ROOT / "调控结论生成引擎"' in source
    assert '"recommendation_adapter.py"' in source
    assert '"local_pg_ws_bridge.py"' in source
    assert '"frontend_dashboard_v3.server.html"' in source
    assert '"recommendation_sync_manifest.v1"' in source


def test_remote_deployer_updates_only_shared_engine_runtime_and_pages() -> None:
    source = (ROOT / "tools" / "remote_deploy_8093_8094_recommendation_sync.ps1").read_text(encoding="utf-8")
    assert 'BFV4PreviewWs8768' in source
    assert 'Stop-Service -Name $service8768' in source
    assert 'REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805' in source
    assert '--ws-port 8768' in source
    assert 'BFV4PreviewProxy8093' not in source
    assert 'Stop-ScheduledTask' not in source
    assert 'ollama_proxy_server.py' not in source


def test_remote_deployer_verifies_exact_runtime_hashes_and_rolls_back() -> None:
    source = (ROOT / "tools" / "remote_deploy_8093_8094_recommendation_sync.ps1").read_text(encoding="utf-8")
    assert 'Installed hash mismatch' in source
    assert '8093 page does not match the latest local source' in source
    assert 'Copy-Item -LiteralPath (Join-Path $backup $engineName)' in source
    assert 'verify_8094_multi_condition_runtime.py' in source
