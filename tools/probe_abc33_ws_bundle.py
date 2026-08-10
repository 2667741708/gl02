from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from typing import Any

import websockets


def find_bundle(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("schema_version") == "abc_rule_bundle.v1" and isinstance(value.get("rules"), list):
            return value
        for child in value.values():
            found = find_bundle(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_bundle(child)
            if found:
                return found
    return None


def collect_schema_versions(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        schema = value.get("schema_version")
        if schema:
            found.append(str(schema))
        for child in value.values():
            collect_schema_versions(child, found)
    elif isinstance(value, list):
        for child in value:
            collect_schema_versions(child, found)


async def inspect(url: str, timeout: float) -> dict[str, Any]:
    async with websockets.connect(url, open_timeout=timeout, max_size=64 * 1024 * 1024) as socket:
        message = await asyncio.wait_for(socket.recv(), timeout=timeout)
    payload = json.loads(message)
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    bundle = diagnosis.get("abc_rule_bundle") if isinstance(diagnosis.get("abc_rule_bundle"), dict) else None
    bundle = bundle or find_bundle(payload) or {}
    schema_versions: list[str] = []
    collect_schema_versions(payload, schema_versions)
    rules = bundle.get("rules") or []
    statuses = Counter(str(rule.get("status") or rule.get("state") or "unknown") for rule in rules)
    missing = Counter()
    missing_sensors = Counter()
    for rule in rules:
        for item in rule.get("missing_inputs") or rule.get("missing_data") or []:
            if isinstance(item, dict):
                key = item.get("variable") or item.get("key") or item.get("label")
            else:
                key = item
            if key:
                missing[str(key)] += 1
        for sensor in rule.get("missing_sensors") or []:
            missing_sensors[str(sensor)] += 1
    return {
        "url": url,
        "message_type": payload.get("type"),
        "timestamp": payload.get("timestamp"),
        "top_keys": sorted(payload.keys()),
        "diagnosis_keys": sorted(diagnosis.keys()),
        "diagnosis_error": diagnosis.get("error") or diagnosis.get("error_type"),
        "schema_versions": sorted(set(schema_versions)),
        "bundle_state": bundle.get("state"),
        "rule_count": len(rules),
        "status_counts": dict(sorted(statuses.items())),
        "confidence_nonzero": sum(float(rule.get("confidence") or 0) > 0 for rule in rules),
        "scores_nonnull": sum(rule.get("score") is not None for rule in rules),
        "score_available_count": sum(rule.get("score_available") is True for rule in rules),
        "release_states": dict(Counter(str(rule.get("release_state") or "unknown") for rule in rules)),
        "alert_count": len(bundle.get("alerts") or []),
        "valid_zero_rule_ids": [
            rule.get("rule_id")
            for rule in rules
            if rule.get("score_available") is True
            and rule.get("status") != "needs_data"
            and float(rule.get("score") or 0) == 0
        ],
        "data_complete_count": sum(rule.get("data_complete") is True for rule in rules),
        "incomplete_rule_ids": [rule.get("rule_id") for rule in rules if rule.get("data_complete") is not True],
        "rule_ids": [rule.get("rule_id") for rule in rules],
        "missing_inputs": dict(missing.most_common()),
        "missing_sensors": dict(missing_sensors.most_common()),
        "error_type": bundle.get("error_type"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8768")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    result = asyncio.run(inspect(args.url, args.timeout))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["rule_count"] == 33 else 2


if __name__ == "__main__":
    raise SystemExit(main())
