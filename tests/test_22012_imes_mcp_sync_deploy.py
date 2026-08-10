from __future__ import annotations

import json
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "tools" / "remote_guarded_deploy_8093_imes_mcp_sync.ps1"
PROBE = ROOT / "tools" / "remote_probe_8093_imes_mcp_sync_result.ps1"
SSE_VERIFIER = ROOT / "tools" / "verify_8093_assistant_sse_once.py"
MCP = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_relay_mcp_server.py"
CATALOG = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "imes_full_variable_catalog.json"
PRODUCTION_REGISTRY = ROOT / "tools" / "service_configs" / "22012_mcp_server_registry.json"
PATCHER_PATH = ROOT / "tools" / "patch_22012_8093_mcp_service_config.py"
SPEC = importlib.util.spec_from_file_location("patch_22012_8093_mcp_service_config", PATCHER_PATH)
assert SPEC and SPEC.loader
PATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCHER)


def test_deploy_is_scoped_to_imes_mcp_and_protects_other_services() -> None:
    text = DEPLOY.read_text(encoding="utf-8")

    assert "REQ-22012-IMES-MCP-SYNC-20260805" in text
    assert "BFV4PreviewProxy8093" in text
    assert "imes_relay_mcp_server.py" in text
    assert "imes_full_variable_catalog.json" in text
    assert "$protectedPorts = @(8768, 8094, 8770)" in text
    assert "IMES_MCP_CONNECTION_MODE -ne 'direct_22012'" in text
    assert "IMES_RELAY_DB_HOST -ne '10.10.181.195'" in text
    assert "BFV4PreviewWs8768" not in text
    assert "22012_BFV4PreviewProxy8093.json.before" in text


def test_local_imes_mcp_contains_current_heat_freshness_fix_and_full_catalog() -> None:
    mcp_text = MCP.read_text(encoding="utf-8")
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    assert 'os.getenv("IMES_ACTIVE_HEAT_MAX_AGE_HOURS", "72")' in mcp_text
    assert "def get_current_previous_heat_si_summary" in mcp_text
    assert len(catalog["entries"]) == 315


def test_production_registry_registers_local_services_with_remote_endpoints() -> None:
    registry = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
    servers = {item["server_id"]: item for item in registry["servers"]}

    assert list(servers) == ["gl02-data", "gl02-extended", "imes-readonly", "imes-web-readonly"]
    assert servers["imes-readonly"]["env_defaults"] == {
        "IMES_MCP_CONNECTION_MODE": "direct_22012",
        "IMES_RELAY_DB_HOST": "10.10.181.195",
        "IMES_RELAY_DB_PORT": "5432",
    }
    assert servers["imes-web-readonly"]["env_defaults"]["IMES_WEB_URL"].startswith(
        "http://10.10.181.209:8080/"
    )


def test_service_config_patcher_is_idempotent_and_writes_no_secret_values() -> None:
    source = {
        "serviceName": "BFV4PreviewProxy8093",
        "envMachine": ["GL02_PGPASSWORD"],
        "env": {"BF_PROXY_PORT": "8093"},
    }

    first, first_changed = PATCHER.patch_service_config(source)
    second, second_changed = PATCHER.patch_service_config(first)

    assert first_changed is True
    assert second_changed is False
    assert "IMES_DB_PASSWORD" in second["envMachine"]
    assert "IMES_WEB_PASSWORD" in second["envMachine"]
    assert second["env"]["IMES_MCP_CONNECTION_MODE"] == "direct_22012"
    serialized = json.dumps(second, ensure_ascii=False)
    assert "IMES_DB_PASSWORD=" not in serialized
    assert "IMES_WEB_PASSWORD=" not in serialized


def test_service_config_patcher_adds_readonly_cross_source_mcp_health_probe() -> None:
    source = {
        "serviceName": "BFV4PreviewProxy8093",
        "envMachine": [],
        "env": {},
        "health": {"tcp": [{"port": 8093}], "http": []},
    }
    patched, changed = PATCHER.patch_service_config(source)
    assert changed is True
    probes = [item for item in patched["health"]["http"] if item["url"].endswith("/api/qa/mcp/health")]
    assert probes == [{"url": "http://127.0.0.1:8093/api/qa/mcp/health", "timeoutSeconds": 5}]
    second, second_changed = PATCHER.patch_service_config(patched)
    assert second_changed is False
    assert second["health"]["http"] == probes


def test_runtime_probe_avoids_slow_cim_listener_queries() -> None:
    text = PROBE.read_text(encoding="utf-8")

    assert "netstat.exe" in text
    assert "schtasks.exe" in text
    assert "Get-NetTCPConnection" not in text
    assert "Get-ScheduledTask" not in text
    assert "deployment_result.json" in text


def test_assistant_sse_verifier_supports_forced_and_automatic_mcp_modes() -> None:
    text = SSE_VERIFIER.read_text(encoding="utf-8")

    assert '"--use-mcp-tools"' in text
    assert '"--auto-mcp-tools"' in text
    assert "tool_mode = None if args.auto_mcp_tools else args.use_mcp_tools" in text
