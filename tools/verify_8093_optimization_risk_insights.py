"""验证8093参数优化页去重后的诊断证据与风险洞察布局。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


def optimization_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "optimization"))


async def verify(url: str, screenshot: Path, width: int, height: int) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    http_errors: list[dict[str, object]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on(
            "response",
            lambda response: http_errors.append({"status": response.status, "url": response.url})
            if response.status >= 400
            else None,
        )
        await page.goto(optimization_url(url), wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector('.bf-engine-cockpit[data-recommendation-state="ready"]', timeout=45_000)
        await page.wait_for_selector(".bf-risk-insight-grid", timeout=45_000)
        await page.wait_for_timeout(1_500)
        result = await page.evaluate(
            """
            () => {
              const root = document.querySelector('.bf-engine-cockpit');
              const evidence = Array.from(root?.querySelectorAll('.bf-decision-evidence-grid .cockpit-evidence-card') || []);
              const monitor = Array.from(root?.querySelectorAll('.opt-monitor-column .cockpit-metric-row') || []);
              const insights = Array.from(root?.querySelectorAll('.bf-risk-insight-grid .cockpit-trend-card') || []);
              const doc = document.documentElement;
              return {
                state: root?.dataset.recommendationState || null,
                evidence_count: evidence.length,
                evidence_sparks: root?.querySelectorAll('.bf-decision-evidence-grid .cockpit-spark').length || 0,
                evidence_baselines: evidence.map(card => card.querySelector('small')?.textContent?.trim() || ''),
                monitor_count: monitor.length,
                insight_titles: insights.map(card => card.querySelector('b')?.textContent?.trim() || ''),
                insight_count: insights.length,
                horizontal_overflow: doc.scrollWidth > doc.clientWidth + 1,
                clipped_insights: insights.filter(card => card.scrollHeight > card.clientHeight + 2).length,
              };
            }
            """
        )
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)
        await browser.close()

    ignored_console = ("favicon.ico", "Failed to fetch", "status of 502", "code generator has deoptimised")
    filtered_console = [
        item for item in console_errors if not any(marker in item for marker in ignored_console)
    ]
    filtered_http = [
        item for item in http_errors if "/api/trend/history" not in str(item["url"])
    ]
    failures: list[str] = []
    if result["state"] != "ready":
        failures.append("recommendation_engine_not_ready")
    if result["evidence_count"] != 4 or result["evidence_sparks"] != 0:
        failures.append("decision_evidence_still_duplicates_short_trends")
    if result["monitor_count"] != 5:
        failures.append("fixed_realtime_monitor_missing")
    expected_titles = {"主炉况 / 次炉况得分演化", "关键变量相对历史基线偏离"}
    if result["insight_count"] != 2 or set(result["insight_titles"]) != expected_titles:
        failures.append("risk_insights_not_replaced")
    if any(not value for value in result["evidence_baselines"]):
        failures.append("evidence_baseline_copy_missing")
    if result["horizontal_overflow"] or result["clipped_insights"]:
        failures.append("layout_overflow_or_clipping")
    if page_errors or filtered_console or filtered_http:
        failures.append("page_or_console_errors")
    return {
        "ok": not failures,
        "failures": failures,
        "viewport": {"width": width, "height": height},
        "result": result,
        "page_errors": page_errors,
        "console_errors": filtered_console,
        "http_errors": filtered_http,
        "screenshot": str(screenshot),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--screenshot", default="logs/8093_optimization_risk_insights.png")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    result = asyncio.run(verify(args.url, Path(args.screenshot), args.width, args.height))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
