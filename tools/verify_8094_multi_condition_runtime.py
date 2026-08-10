#!/usr/bin/env python3
"""Read one 8769 init frame and verify the eight-condition preview contract."""

from __future__ import annotations

import argparse
import asyncio
import json

import websockets


LABELS = {"normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"}


async def verify(uri: str, timeout_seconds: float) -> dict[str, object]:
    async with websockets.connect(uri, open_timeout=timeout_seconds, max_size=16 * 1024 * 1024) as socket:
        raw = await asyncio.wait_for(socket.recv(), timeout=timeout_seconds)
    payload = json.loads(raw)
    if payload.get("type") != "init":
        raise RuntimeError(f"first WebSocket frame is {payload.get('type')!r}, expected 'init'")
    diagnosis = payload.get("diagnosis") or {}
    bundle = diagnosis.get("recommendation_bundle") or {}
    conditions = bundle.get("conditions") or []
    condition_labels = {item.get("label") for item in conditions}
    if bundle.get("schema_version") != "multi_condition_recommendation.v1":
        raise RuntimeError("8769 diagnosis is missing multi_condition_recommendation.v1")
    if len(conditions) != 8 or condition_labels != LABELS:
        raise RuntimeError("8769 diagnosis does not contain all eight condition plans")
    active = [item for item in conditions if item.get("scope") == "active"]
    if len(active) != 1:
        raise RuntimeError("8769 diagnosis must contain exactly one active plan")
    if not all(item.get("read_only") for item in conditions):
        raise RuntimeError("8769 returned a non-read-only condition plan")
    return {
        "ok": True,
        "type": payload.get("type"),
        "timestamp": payload.get("timestamp"),
        "schema_version": bundle.get("schema_version"),
        "condition_count": len(conditions),
        "active_label": active[0].get("label"),
        "engine_version": bundle.get("engine_meta", {}).get("version"),
        "read_only": bundle.get("engine_meta", {}).get("read_only"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default="ws://127.0.0.1:8769")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.uri, args.timeout)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
