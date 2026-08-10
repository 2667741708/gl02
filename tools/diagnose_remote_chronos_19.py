# -*- coding: utf-8 -*-
"""Capture one production 19-target Chronos response without changing plant state."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import websockets


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "acceptance" / "chronos19_zero_diagnosis_20260807.json"
TARGET_IDS = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "Q_blast",
    "P_blast_cold", "P_blast", "T_blast", "PI", "DP_total", "DP_upper",
    "DP_lower", "GasUtil",
]


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def series_summary(values: Any) -> dict[str, Any]:
    sequence = values if isinstance(values, list) else []
    cleaned = [finite(value) for value in sequence]
    numbers = [value for value in cleaned if value is not None]
    return {
        "length": len(sequence),
        "finite_count": len(numbers),
        "nonzero_count": sum(abs(value) > 1e-12 for value in numbers),
        "first": numbers[0] if numbers else None,
        "last": numbers[-1] if numbers else None,
        "min": min(numbers) if numbers else None,
        "max": max(numbers) if numbers else None,
    }


def extract_predictions(message: dict[str, Any]) -> list[dict[str, Any]]:
    forecast = message.get("forecast") if isinstance(message.get("forecast"), dict) else message
    predictions = forecast.get("predictions") if isinstance(forecast, dict) else None
    return predictions if isinstance(predictions, list) else []


async def main() -> int:
    report: dict[str, Any] = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "websocket": "ws://10.30.220.12:8768",
        "target_ids": TARGET_IDS,
        "history": {},
        "prediction": {},
        "status_messages": [],
    }
    async with websockets.connect("ws://10.30.220.12:8768", open_timeout=30, max_size=64 * 1024 * 1024) as websocket:
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=60))
            if message.get("type") == "init":
                history = message.get("history") or {}
                for target_id in TARGET_IDS:
                    report["history"][target_id] = series_summary(history.get(target_id))
                break
        await websocket.send(json.dumps({
            "type": "chronos_predict_recommended_batch",
            "prediction_minutes": 120,
            "context_minutes": 480,
            "target_ids": TARGET_IDS,
            "data_source": "production_zero_diagnosis",
        }, ensure_ascii=False))
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=900))
            message_type = message.get("type")
            if message_type == "chronos_prediction_status":
                report["status_messages"].append(message)
                continue
            if message_type not in {"chronos_prediction", "chronos_prediction_batch"}:
                continue
            report["response_status"] = message.get("status")
            report["response_error"] = message.get("error") or message.get("message")
            forecast = message.get("forecast") if isinstance(message.get("forecast"), dict) else message
            report["skipped"] = forecast.get("skipped") if isinstance(forecast, dict) else None
            for prediction in extract_predictions(message):
                target_id = str(prediction.get("target_id") or prediction.get("target") or prediction.get("name") or "")
                values = prediction.get("p50") or prediction.get("mean") or prediction.get("forecast") or prediction.get("prediction")
                report["prediction"][target_id] = series_summary(values)
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    zero_targets = [target_id for target_id, item in report["prediction"].items() if item["finite_count"] and item["nonzero_count"] == 0]
    print(json.dumps({
        "response_status": report.get("response_status"),
        "prediction_count": len(report["prediction"]),
        "zero_targets": zero_targets,
        "report": str(OUT),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
