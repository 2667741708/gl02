#!/usr/bin/env python3
"""Verify the live 8768 recommendation stream uses the v2 dual-control contract."""

from __future__ import annotations

import argparse
import asyncio
import json

import websockets


ALLOWED = {"P_blast_cold", "PCI_set"}


async def verify(uri: str, timeout_seconds: float) -> dict[str, object]:
    async with websockets.connect(uri, open_timeout=timeout_seconds, max_size=32 * 1024 * 1024) as socket:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        payload = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = max(0.1, deadline - asyncio.get_running_loop().time())
            raw = await asyncio.wait_for(socket.recv(), timeout=remaining)
            candidate = json.loads(raw)
            if candidate.get("type") == "init":
                payload = candidate
                break
        if payload is None:
            raise RuntimeError("8768 did not deliver an init frame before timeout")
    if payload.get("type") != "init":
        raise RuntimeError(f"first WebSocket frame is {payload.get('type')!r}, expected 'init'")
    diagnosis = payload.get("diagnosis") or {}
    bundle = diagnosis.get("recommendation_bundle") or {}
    conditions = bundle.get("conditions") or []
    if len(conditions) != 8:
        raise RuntimeError(f"expected eight condition plans, got {len(conditions)}")
    control_scope = bundle.get("control_scope") or {}
    if control_scope.get("schema_version") != "foreman_dual_control.v2":
        raise RuntimeError("live bundle is missing foreman_dual_control.v2")
    if set(control_scope.get("adjustable_variables") or []) != ALLOWED:
        raise RuntimeError("live adjustable variables are not exactly P_blast_cold and PCI_set")
    if control_scope.get("evidence_only_variables") != ["Q_blast"]:
        raise RuntimeError("Q_blast evidence-only contract is missing")
    status_counts: dict[str, int] = {}
    action_count = 0
    for condition in conditions:
        recommendation = condition.get("recommendation") or {}
        actions = recommendation.get("actions") or []
        if not actions:
            raise RuntimeError(f"condition {condition.get('label')} has no dual-control actions")
        for action in actions:
            action_count += 1
            variable = action.get("control_variable")
            if variable not in ALLOWED:
                raise RuntimeError(f"unexpected control variable: {variable!r}")
            if variable == "Q_blast":
                raise RuntimeError("Q_blast must never be an executable control variable")
            for field in (
                "control_label", "current_value", "recommended_change", "recommended_target",
                "unit", "step_tier", "effective_at", "limit_snapshot", "approval",
                "source_document", "trigger_evidence", "preconditions", "blocking_reasons",
                "missing_inputs", "observation_window", "sequence",
            ):
                if field not in action:
                    raise RuntimeError(f"action {action.get('action_id')} missing {field}")
            status = str(action.get("status") or "")
            status_counts[status] = status_counts.get(status, 0) + 1
            if not action.get("approval", {}).get("required", False):
                raise RuntimeError("all live actions must require foreman approval")
    return {
        "ok": True,
        "type": payload.get("type"),
        "timestamp": payload.get("timestamp"),
        "condition_count": len(conditions),
        "action_count": action_count,
        "status_counts": status_counts,
        "control_scope": control_scope,
        "engine_version": bundle.get("engine_meta", {}).get("version"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default="ws://127.0.0.1:8768")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.uri, args.timeout)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
