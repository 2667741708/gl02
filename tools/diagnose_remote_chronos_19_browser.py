# -*- coding: utf-8 -*-
"""Observe the exact production WebSocket forecast frame through the 8093 page."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "acceptance" / "chronos19_browser_frame_20260807.json"
TARGET_IDS = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "Q_blast",
    "P_blast_cold", "P_blast", "T_blast", "PI", "DP_total", "DP_upper",
    "DP_lower", "GasUtil",
]


def summary(values: Any) -> dict[str, Any]:
    sequence = values if isinstance(values, list) else []
    numbers = []
    for value in sequence:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numbers.append(number)
    return {
        "length": len(sequence),
        "finite_count": len(numbers),
        "nonzero_count": sum(abs(value) > 1e-12 for value in numbers),
        "first": numbers[0] if numbers else None,
        "last": numbers[-1] if numbers else None,
        "min": min(numbers) if numbers else None,
        "max": max(numbers) if numbers else None,
    }


async def main() -> int:
    done = asyncio.Event()
    report: dict[str, Any] = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "url": "http://10.30.220.12:8093/frontend_dashboard_v3.server.html?ws_port=8768&chronos_diag=20260807#trend",
        "websockets": [],
        "history": {},
        "prediction": {},
        "status_messages": [],
        "console_errors": [],
        "page_errors": [],
    }

    def on_frame(payload: str | bytes) -> None:
        try:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            message = json.loads(text)
        except Exception:
            return
        message_type = message.get("type")
        if message_type == "init":
            history = message.get("history") or {}
            report["history"] = {target_id: summary(history.get(target_id)) for target_id in TARGET_IDS}
        elif message_type == "chronos_prediction_status":
            report["status_messages"].append({key: message.get(key) for key in ("type", "status", "engine", "chronos_base_url")})
        elif message_type in {"chronos_prediction", "chronos_prediction_batch"}:
            report["response_status"] = message.get("status")
            report["response_error"] = message.get("error") or message.get("message")
            forecast = message.get("forecast") if isinstance(message.get("forecast"), dict) else message
            predictions = forecast.get("predictions") if isinstance(forecast, dict) else []
            report["skipped"] = forecast.get("skipped") if isinstance(forecast, dict) else None
            for prediction in predictions if isinstance(predictions, list) else []:
                target_id = str(prediction.get("target_id") or prediction.get("target") or prediction.get("name") or "")
                values = prediction.get("p50") or prediction.get("mean") or prediction.get("forecast") or prediction.get("prediction")
                report["prediction"][target_id] = summary(values)
            done.set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("console", lambda msg: report["console_errors"].append(msg.text) if msg.type == "error" and not msg.text.startswith("[BABEL] Note:") else None)
        page.on("pageerror", lambda exc: report["page_errors"].append(str(exc)))

        def on_websocket(websocket) -> None:
            report["websockets"].append(websocket.url)
            websocket.on("framereceived", on_frame)

        page.on("websocket", on_websocket)
        await page.goto(report["url"], wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_selector(".app", timeout=90000)
        await page.wait_for_timeout(5000)
        button = page.get_by_role("button", name="生成全部未来曲线")
        try:
            await button.wait_for(state="visible", timeout=300000)
            if await button.is_enabled():
                await button.click()
        except Exception as exc:
            report["button_error"] = str(exc)
        try:
            await asyncio.wait_for(done.wait(), timeout=900)
        except TimeoutError:
            report["timeout"] = True
        await browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    zero_targets = [target_id for target_id, item in report["prediction"].items() if item["finite_count"] and item["nonzero_count"] == 0]
    print(json.dumps({
        "websockets": report["websockets"],
        "response_status": report.get("response_status"),
        "prediction_count": len(report["prediction"]),
        "zero_targets": zero_targets,
        "report": str(OUT),
    }, ensure_ascii=False))
    return 0 if report["prediction"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
