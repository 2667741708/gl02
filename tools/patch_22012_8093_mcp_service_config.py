"""Add non-secret multi-MCP runtime settings to the 220.12 8093 service config.

Requirement: REQ-22012-IMES-MCP-SYNC-20260805.
Credential values remain in Machine environment variables and are never written
to the managed-service JSON document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_MACHINE_ENV = (
    "IMES_DB_USER",
    "IMES_DB_PASSWORD",
    "IMES_OPS_DB_USER",
    "IMES_OPS_DB_PASSWORD",
    "IMES_LAB_DB_USER",
    "IMES_LAB_DB_PASSWORD",
    "IMES_WEB_USER",
    "IMES_WEB_PASSWORD",
    "IMES_WEB_SESSION_COOKIE",
)

REQUIRED_ENV = {
    "BF_QA_MCP_SERVER_REGISTRY": (
        "F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/"
        "高炉前端数据/智能助手/backend/mcp_host/server_registry.json"
    ),
    "IMES_MCP_CONNECTION_MODE": "direct_22012",
    "IMES_RELAY_DB_HOST": "10.10.181.195",
    "IMES_RELAY_DB_PORT": "5432",
    "IMES_ACTIVE_HEAT_MAX_AGE_HOURS": "72",
    "IMES_WEB_URL": "http://10.10.181.209:8080/imes.web/",
}

MCP_HEALTH_URL = "http://127.0.0.1:8093/api/qa/mcp/health"


def ensure_mcp_health_probe(payload: dict) -> bool:
    """Add one cheap MCP Host probe to the existing 8093 guard contract."""

    health = dict(payload.get("health") or {})
    checks = [dict(item) for item in (health.get("http") or []) if isinstance(item, dict)]
    desired = {"url": MCP_HEALTH_URL, "timeoutSeconds": 5}
    for item in checks:
        if str(item.get("url") or "") == MCP_HEALTH_URL:
            changed = item.get("timeoutSeconds") != desired["timeoutSeconds"]
            item.update(desired)
            health["http"] = checks
            payload["health"] = health
            return changed
    checks.append(desired)
    health["http"] = checks
    payload["health"] = health
    return True


def patch_service_config(payload: dict) -> tuple[dict, bool]:
    """Return an idempotently patched 8093 service config and change flag."""

    if payload.get("serviceName") != "BFV4PreviewProxy8093":
        raise ValueError("service config is not BFV4PreviewProxy8093")
    changed = False
    machine_env = list(payload.get("envMachine") or [])
    for name in REQUIRED_MACHINE_ENV:
        if name not in machine_env:
            machine_env.append(name)
            changed = True
    payload["envMachine"] = machine_env

    env = dict(payload.get("env") or {})
    for name, value in REQUIRED_ENV.items():
        if env.get(name) != value:
            env[name] = value
            changed = True
    payload["env"] = env
    if ensure_mcp_health_probe(payload):
        changed = True
    return payload, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐220.12 8093生产服务的多MCP非敏感配置。")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.config.read_text(encoding="utf-8-sig"))
    patched, changed = patch_service_config(payload)
    if changed:
        args.config.write_text(
            json.dumps(patched, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "service": patched["serviceName"],
                "machine_env_names": list(REQUIRED_MACHINE_ENV),
                "runtime_env": REQUIRED_ENV,
                "health_probe": MCP_HEALTH_URL,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
