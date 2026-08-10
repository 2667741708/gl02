# -*- coding: utf-8 -*-
"""Cross-engine production smoke checks for the merged 8094 trend panel."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "acceptance" / "8094_trend_19_lane_production_20260807.json"
BASE_URL = "http://10.30.220.12:8094/?trend19_prod=20260807#trend"
MATRIX = {
    "chromium": [(1280, 720), (1366, 768), (1440, 900), (1546, 864), (1920, 1080), (1024, 768), (768, 1024), (390, 844), (375, 667)],
    "firefox": [(1920, 1080), (1366, 768), (768, 1024), (390, 844)],
    "webkit": [(1920, 1080), (1366, 768), (768, 1024), (390, 844)],
}


async def check_page(browser_type, engine: str, viewport: tuple[int, int]) -> dict:
    browser = await browser_type.launch(headless=True)
    page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" and not msg.text.startswith("[BABEL] Note:") else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_selector(".app", timeout=90000)
    await page.wait_for_timeout(5000)
    state = await page.evaluate(
        """() => ({
          overflow: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
          panels: document.querySelectorAll('.trend-chart-stack.trend-lane-single > .panel').length,
          canvases: document.querySelectorAll('.trend-chart-stack.trend-lane-single canvas').length,
          title: document.body.innerText.includes('19个核心变量趋势与预测'),
          controls: document.body.innerText.includes('生成全部未来曲线') && document.body.innerText.includes('1小时') && document.body.innerText.includes('8小时'),
          rightPanels: ['高炉大模型预测分析','关键指标变化','趋势解读'].every(t => document.body.innerText.includes(t))
        })"""
    )
    await browser.close()
    ok = state["overflow"] == 0 and state["panels"] == 1 and state["canvases"] >= 1 and state["title"] and state["controls"] and state["rightPanels"] and not errors
    return {"engine": engine, "viewport": list(viewport), "ok": ok, "state": state, "errors": errors}


async def main() -> int:
    results = []
    async with async_playwright() as playwright:
        for engine, viewports in MATRIX.items():
            browser_type = getattr(playwright, engine)
            for viewport in viewports:
                results.append(await check_page(browser_type, engine, viewport))
    payload = {
        "requirement": "REQ-TREND-19-LANE-MERGE-20260807",
        "url": BASE_URL,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "checks": len(results),
        "status": "PASS" if all(item["ok"] for item in results) else "FAIL",
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": payload["checks"], "status": payload["status"], "report": str(OUT)}, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
