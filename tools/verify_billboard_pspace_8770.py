# -*- coding: utf-8 -*-
"""Verify the dedicated Billboard pSpace WebSocket without exposing tag names."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from typing import Any


REQUIRED = (
    "DP_total",
    "T_throat_A",
    "P_static_lower_A",
    "P_static_middle_C",
    "P_static_upper_F",
)
REQUIRED_FOREMAN = (
    "CO_top",
    "CO2_top",
    "H2_top",
    "PCI_previous_hour",
    "BlastEnergy",
    "BlastSpeedStd",
    "BlastSpeedActual",
    "Q_soft_water",
    "P_soft_water",
    "Q_high_pressure_water",
    "P_high_pressure_water",
    "P_medium_pressure_water",
    "ExpansionTankLevel",
    "Q_N2",
    "P_N2",
    "P_O2_valve_in",
    "P_O2_valve_out",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://10.30.220.12:8770")
    parser.add_argument("--open-timeout", type=float, default=90)
    parser.add_argument("--frame-timeout", type=float, default=90)
    parser.add_argument("--require-numeric", type=int, default=100)
    return parser.parse_args()


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    values = payload.get("values") or {}
    meta = payload.get("point_meta") or {}
    quality = payload.get("data_quality") or {}
    numeric = [
        sensor_id
        for sensor_id in meta
        if isinstance(values.get(sensor_id), (int, float)) and math.isfinite(values[sensor_id])
    ]
    return {
        "type": payload.get("type"),
        "timestamp": payload.get("timestamp"),
        "replay_mode": (payload.get("replay") or {}).get("mode"),
        "stream_value_count": len(values),
        "billboard_meta_count": len(meta),
        "billboard_expected": quality.get("billboard_expected"),
        "billboard_mapped": quality.get("billboard_mapped"),
        "billboard_missing_count": len(quality.get("billboard_missing") or []),
        "numeric_billboard_values": len(numeric),
        "quality_metadata_count": sum(
            1 for sensor_id in meta if meta[sensor_id].get("quality") not in (None, "")
        ),
        "required_keys_present": all(sensor_id in values and sensor_id in meta for sensor_id in REQUIRED),
        "required_numeric_count": sum(
            1
            for sensor_id in REQUIRED
            if isinstance(values.get(sensor_id), (int, float)) and math.isfinite(values[sensor_id])
        ),
        "foreman_keys_present": all(sensor_id in values for sensor_id in REQUIRED_FOREMAN),
        "foreman_numeric_count": sum(
            1
            for sensor_id in REQUIRED_FOREMAN
            if isinstance(values.get(sensor_id), (int, float)) and math.isfinite(values[sensor_id])
        ),
        "foreman_values": {sensor_id: values.get(sensor_id) for sensor_id in REQUIRED_FOREMAN},
    }


def passed(result: dict[str, Any], require_numeric: int) -> bool:
    return bool(
        result["type"] == "tick"
        and result["replay_mode"] == "pspace_realtime"
        and result["stream_value_count"] == 157
        and result["billboard_meta_count"] == 133
        and result["billboard_expected"] == 133
        and result["billboard_mapped"] == 133
        and result["billboard_missing_count"] == 0
        and result["numeric_billboard_values"] >= require_numeric
        and result["required_keys_present"]
        and result["foreman_keys_present"]
        and result["foreman_numeric_count"] == len(REQUIRED_FOREMAN)
    )


async def verify(args: argparse.Namespace) -> dict[str, Any]:
    import websockets

    async with websockets.connect(
        args.url,
        open_timeout=args.open_timeout,
        max_size=25_000_000,
    ) as websocket:
        for _ in range(12):
            payload = json.loads(
                await asyncio.wait_for(websocket.recv(), timeout=args.frame_timeout)
            )
            if payload.get("type") != "tick":
                continue
            result = summarize(payload)
            result["passed"] = passed(result, args.require_numeric)
            return result
    raise RuntimeError("No pSpace tick was received")


def verify_with_websocket_client(args: argparse.Namespace) -> dict[str, Any]:
    import websocket

    connection = websocket.create_connection(args.url, timeout=args.open_timeout)
    try:
        connection.settimeout(args.frame_timeout)
        for _ in range(12):
            payload = json.loads(connection.recv())
            if payload.get("type") != "tick":
                continue
            result = summarize(payload)
            result["passed"] = passed(result, args.require_numeric)
            return result
    finally:
        connection.close()
    raise RuntimeError("No pSpace tick was received")


def main() -> int:
    args = parse_args()
    try:
        import websockets  # noqa: F401
    except ModuleNotFoundError:
        result = verify_with_websocket_client(args)
    else:
        result = asyncio.run(verify(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
