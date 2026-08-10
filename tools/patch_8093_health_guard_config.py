"""Apply the 8093-only health-guard resilience contract to a service config.

OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


SERVICE_NAME = "BFV4PreviewProxy8093"
FAILURE_THRESHOLD = 3
SERVICE_DOWN_THRESHOLD = 1
PRE_RESTART_BACKOFF_SECONDS = 15
RESTART_COOLDOWN_SECONDS = 600


def patch_config(config: dict[str, Any]) -> bool:
    """Patch only the 8093 health section and report whether it changed."""

    if config.get("serviceName") != SERVICE_NAME:
        raise ValueError(f"unexpected serviceName: {config.get('serviceName')!r}")
    health = config.get("health")
    if not isinstance(health, dict):
        raise ValueError("health must be an object")
    tcp_checks = health.get("tcp") or []
    if not any(isinstance(item, dict) and int(item.get("port") or 0) == 8093 for item in tcp_checks):
        raise ValueError("8093 TCP health check is missing")

    desired = {
        "failureThreshold": FAILURE_THRESHOLD,
        "serviceNotRunningFailureThreshold": SERVICE_DOWN_THRESHOLD,
        "preRestartBackoffSeconds": PRE_RESTART_BACKOFF_SECONDS,
        "restartCooldownSeconds": RESTART_COOLDOWN_SECONDS,
    }
    changed = any(health.get(name) != value for name, value in desired.items())
    health.update(desired)
    return changed


def write_json_atomically(path: Path, config: dict[str, Any]) -> None:
    """Write UTF-8 JSON through a same-directory atomic replacement."""

    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch the 8093 health-guard resilience settings.")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    changed = patch_config(config)
    if changed:
        write_json_atomically(args.config, config)
    print(
        json.dumps(
            {
                "schema": "ops.8093.health-guard-config-patch.v1",
                "changed": changed,
                "service_name": config["serviceName"],
                "health": {
                    name: config["health"][name]
                    for name in (
                        "failureThreshold",
                        "serviceNotRunningFailureThreshold",
                        "preRestartBackoffSeconds",
                        "restartCooldownSeconds",
                    )
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
