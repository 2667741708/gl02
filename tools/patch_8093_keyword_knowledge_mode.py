"""Set the 8093 assistant knowledge retrieval mode to keyword only.

OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


SERVICE_NAME = "BFV4PreviewProxy8093"
SEARCH_MODE_ENV = "BF_QA_KNOWLEDGE_SEARCH_MODE"
SEARCH_MODE = "keyword"
HEALTH_CONTRACT = {
    "failureThreshold": 3,
    "serviceNotRunningFailureThreshold": 1,
    "preRestartBackoffSeconds": 15,
    "restartCooldownSeconds": 600,
}


def patch_config(config: dict[str, Any]) -> bool:
    """Apply the 8093-only keyword mode after validating isolation contracts."""

    if config.get("serviceName") != SERVICE_NAME:
        raise ValueError(f"unexpected serviceName: {config.get('serviceName')!r}")

    environment = config.get("env")
    if not isinstance(environment, dict):
        raise ValueError("env must be an object")
    if str(environment.get("BF_PROXY_PORT") or "") != "8093":
        raise ValueError("BF_PROXY_PORT must be 8093")

    health = config.get("health")
    if not isinstance(health, dict):
        raise ValueError("health must be an object")
    tcp_checks = health.get("tcp") or []
    if not any(isinstance(item, dict) and int(item.get("port") or 0) == 8093 for item in tcp_checks):
        raise ValueError("8093 TCP health check is missing")
    actual_health = {name: health.get(name) for name in HEALTH_CONTRACT}
    if actual_health != HEALTH_CONTRACT:
        raise ValueError(f"8093 health contract drifted: {actual_health!r}")

    previous = str(environment.get(SEARCH_MODE_ENV) or "").strip().lower()
    if previous not in {"", "hybrid", SEARCH_MODE}:
        raise ValueError(f"unexpected existing {SEARCH_MODE_ENV}: {previous!r}")
    if previous == SEARCH_MODE and environment.get(SEARCH_MODE_ENV) == SEARCH_MODE:
        return False

    environment[SEARCH_MODE_ENV] = SEARCH_MODE
    return True


def write_json_atomically(path: Path, config: dict[str, Any]) -> None:
    """Write UTF-8 JSON through a same-directory atomic replacement."""

    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set BFV4PreviewProxy8093 knowledge retrieval to keyword mode."
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    changed = patch_config(config)
    if changed:
        write_json_atomically(args.config, config)
    print(
        json.dumps(
            {
                "schema": "ops.8093.knowledge-keyword-config-patch.v1",
                "requirement_id": "OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805",
                "changed": changed,
                "service_name": config["serviceName"],
                "search_mode": config["env"][SEARCH_MODE_ENV],
                "health_contract": {
                    name: config["health"][name] for name in HEALTH_CONTRACT
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
