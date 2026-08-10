from __future__ import annotations

import asyncio
import json
import websockets


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, (dict, list)) and "recommend" in str(key).lower():
                yield child, value
            yield from walk(value, child)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk(value, f"{path}[{index}]")


def action_records(obj):
    found = []
    if isinstance(obj, dict):
        keys = set(obj)
        if "status" in keys and ("control_variable" in keys or "control_label" in keys or "recommended_target" in keys):
            found.append({
                "status": obj.get("status"),
                "control_variable": obj.get("control_variable"),
                "control_label": obj.get("control_label"),
                "current_value": obj.get("current_value"),
                "recommended_target": obj.get("recommended_target"),
                "recommended_change": obj.get("recommended_change", obj.get("delta")),
                "missing_inputs": obj.get("missing_inputs"),
                "blocking_reasons": obj.get("blocking_reasons"),
            })
        for value in obj.values():
            found.extend(action_records(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(action_records(value))
    return found


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8768", open_timeout=20, max_size=8_000_000) as ws:
        message = await asyncio.wait_for(ws.recv(), timeout=30)
    data = json.loads(message)
    diagnosis = data.get("diagnosis") or {}
    records = action_records(data)
    print(json.dumps({
        "type": data.get("type"),
        "timestamp": data.get("timestamp"),
        "top_keys": sorted(data.keys()),
        "diagnosis_keys": sorted(diagnosis.keys()) if isinstance(diagnosis, dict) else [],
        "recommendation_paths": [path for path, _ in walk(data)],
        "action_records": records,
        "eligible_pressure_actions": [r for r in records if r.get("control_variable") == "P_blast_cold" and r.get("status") == "eligible"],
        "pressure_needs_data": [r for r in records if r.get("control_variable") == "P_blast_cold" and r.get("status") == "needs_data"],
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
