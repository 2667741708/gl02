from __future__ import annotations

import argparse
import asyncio
import json

import websockets


async def check(url: str, timeout: float, max_size: int) -> dict:
    async with websockets.connect(url, open_timeout=timeout, max_size=max_size) as ws:
        message = await asyncio.wait_for(ws.recv(), timeout=timeout)
    data = json.loads(message)
    history = data.get("history") or {}
    diagnosis = data.get("diagnosis") or {}
    baseline = diagnosis.get("baseline_compare") or {}
    diagnosis_history = data.get("diagnosis_history") or diagnosis.get("history") or []
    latest_diagnosis_history = diagnosis_history[-1] if diagnosis_history else {}
    bf3d_snapshot = data.get("bf3d_snapshot") or {}
    bf3d_quality = bf3d_snapshot.get("quality") or {}
    cohesive_quality = bf3d_quality.get("cohesive_zone") or {}
    cohesive_zone = (bf3d_snapshot.get("estimated") or {}).get("cohesive_zone") or {}
    return {
        "type": data.get("type"),
        "timestamp": data.get("timestamp"),
        "history_points": len(history.get("timestamps") or []),
        "main_label": diagnosis.get("main_label"),
        "baseline_items": len(baseline.get("items") or []),
        "diagnosis_history_count": len(diagnosis_history),
        "diagnosis_history_first": diagnosis_history[0].get("timestamp") if diagnosis_history else None,
        "diagnosis_history_last": latest_diagnosis_history.get("timestamp"),
        "diagnosis_history_score_keys": sorted((latest_diagnosis_history.get("raw_scores") or {}).keys()),
        "bf3d_schema_version": bf3d_snapshot.get("schema_version"),
        "bf3d_knowledge_time": bf3d_snapshot.get("knowledge_time"),
        "bf3d_quality_state": bf3d_quality.get("state"),
        "cohesive_zone_status": cohesive_zone.get("status") or cohesive_quality.get("status"),
        "cohesive_zone_model_version": (
            cohesive_zone.get("model_version") or cohesive_quality.get("model_version")
        ),
        "cohesive_zone_calibration_status": (
            cohesive_zone.get("calibration_status")
            or cohesive_quality.get("calibration_status")
        ),
        "cohesive_zone_control_use": (
            cohesive_zone.get("control_use") or cohesive_quality.get("control_use")
        ),
        "cohesive_zone_direction": (cohesive_zone.get("movement") or {}).get("direction"),
        "cohesive_zone_center_height_m": cohesive_zone.get("centerHeight"),
        "cohesive_zone_thickness_m": cohesive_zone.get("thickness"),
        "cohesive_zone_eccentricity_m": cohesive_zone.get("eccentricity"),
        "cohesive_zone_confidence": cohesive_zone.get("confidence"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the V3 PostgreSQL WebSocket bridge.")
    parser.add_argument("--url", default="ws://127.0.0.1:8767")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--max-size", type=int, default=2_000_000)
    parser.add_argument("--min-diagnosis-history", type=int, default=0)
    parser.add_argument(
        "--require-bf3d-snapshot",
        action="store_true",
        help="Fail unless the first WebSocket message contains bf3d_snapshot.v1.",
    )
    parser.add_argument(
        "--require-cohesive-zone",
        action="store_true",
        help="Fail unless the uncalibrated C2 cohesive-zone estimate is available.",
    )
    args = parser.parse_args()

    result = asyncio.run(check(args.url, args.timeout, args.max_size))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["diagnosis_history_count"] < args.min_diagnosis_history:
        return 2
    if args.require_bf3d_snapshot and result["bf3d_schema_version"] != "bf3d_snapshot.v1":
        return 3
    if args.require_cohesive_zone:
        if result["cohesive_zone_status"] != "available":
            return 4
        if result["cohesive_zone_calibration_status"] != "uncalibrated":
            return 5
        if result["cohesive_zone_control_use"] != "prohibited":
            return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
