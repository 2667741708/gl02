"""Verify the 8092 trend analysis side panels fit without vertical clipping.

对应需求：
- REQ-20260517-TREND-ANALYSIS-FIT：趋势页预测分析、关键指标变化和趋势解读完整显示。

文档：
- docs/requirements_traceability.md#req-20260517-trend-analysis-fit-趋势页右侧分析完整显示
- docs/test_reference.md#test-20260517-trend-analysis-fit-趋势页右侧分析完整显示验收
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


async def verify_trend_layout(url: str, screenshot: str, width: int, height: int) -> dict:
    """Open the trend tab and verify the right analysis stack is not clipped."""

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on local dev environment.
        raise AssertionError("playwright is required for trend layout validation") from exc

    page_errors: list[str] = []
    console_errors: list[str] = []
    target = url.rstrip("/") if url.endswith(".html") else url.rstrip("/")
    if "#" in target:
        target = target.split("#", 1)[0]
    target = f"{target}#trend"

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(target, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector(".trend-grid.vertical-analysis", timeout=60_000)
        await page.wait_for_timeout(1500)
        result = await page.evaluate(
            """() => {
              const fit = (el, tolerance = 8) => !!el && el.scrollHeight <= el.clientHeight + tolerance && el.scrollWidth <= el.clientWidth + tolerance;
              const panels = [...document.querySelectorAll('.trend-analysis-stack > .panel')].map(panel => {
                const title = panel.querySelector('.panel-title')?.textContent?.trim() || '';
                const body = panel.querySelector('.panel-body');
                return {
                  title,
                  panelClientHeight: panel.clientHeight,
                  panelScrollHeight: panel.scrollHeight,
                  bodyClientHeight: body ? body.clientHeight : 0,
                  bodyScrollHeight: body ? body.scrollHeight : 0,
                  bodyClientWidth: body ? body.clientWidth : 0,
                  bodyScrollWidth: body ? body.scrollWidth : 0,
                  fits: fit(panel) && fit(body)
                };
              });
              const chronosList = document.querySelector('.trend-analysis-stack .chronos-list');
              const chronosRows = [...document.querySelectorAll('.trend-analysis-stack .chronos-row')];
              const tableRows = [...document.querySelectorAll('.trend-analysis-stack .trend-table tbody tr')];
              const insights = [...document.querySelectorAll('.trend-analysis-stack .trend-insights .evidence-item')];
              const chartEl = document.querySelector('.trend-chart-stack .chart');
              const chart = chartEl && window.echarts ? window.echarts.getInstanceByDom(chartEl) : null;
              const option = chart ? chart.getOption() : null;
              const firstSeries = option?.series?.[0]?.data || [];
              const firstPoint = firstSeries.find(p => p && Number.isFinite(Number(p[1])));
              const axisMin = option?.xAxis?.[0]?.min;
              const axisStartMs = axisMin ? new Date(axisMin).getTime() : NaN;
              const firstPointMs = firstPoint ? new Date(firstPoint[0]).getTime() : NaN;
              const leftGapMinutes = Number.isFinite(axisStartMs) && Number.isFinite(firstPointMs)
                ? Math.round((firstPointMs - axisStartMs) / 60000)
                : null;
              const yAxisSplitNumbers = (option?.yAxis || []).map(y => y.splitNumber);
              return {
                url: location.href,
                panelCount: panels.length,
                panels,
                allPanelsFit: panels.length === 3 && panels.every(panel => panel.fits),
                chronosRows: chronosRows.length,
                chronosListFits: fit(chronosList),
                tableRows: tableRows.length,
                insights: insights.length,
                chronosOverflowY: chronosList ? getComputedStyle(chronosList).overflowY : '',
                trendChartHasData: firstSeries.length > 0,
                leftGapMinutes,
                yAxisSplitNumbers
              };
            }"""
        )
        if screenshot:
            Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=screenshot, full_page=False)
        await browser.close()

    result["page_errors"] = page_errors
    result["console_errors"] = [
        item
        for item in console_errors
        if "Failed to fetch" not in item and "Failed to load resource" not in item
    ]
    if result["page_errors"] or result["console_errors"]:
        raise AssertionError(f"browser errors: {result}")
    if not result["allPanelsFit"]:
        raise AssertionError(f"trend analysis panels overflow: {result}")
    if result["chronosRows"] != 10 or not result["chronosListFits"]:
        raise AssertionError(f"chronos variable rows are not fully visible: {result}")
    if result["tableRows"] != 10 or result["insights"] != 4:
        raise AssertionError(f"trend table or insight counts are incomplete: {result}")
    if not result["trendChartHasData"] or result["leftGapMinutes"] is None or abs(result["leftGapMinutes"]) > 1:
        raise AssertionError(f"trend chart x-axis must start at the first valid database point: {result}")
    if any(value != 3 for value in result["yAxisSplitNumbers"]):
        raise AssertionError(f"trend chart y-axis must use compact 3-split labels: {result}")
    return result


def main() -> int:
    """CLI entrypoint for reproducible trend layout validation."""

    parser = argparse.ArgumentParser(description="Validate trend page right analysis layout.")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767",
        help="Frontend URL without hash.",
    )
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--screenshot", default=str(ROOT / "logs" / "trend_analysis_fit_20260517.png"))
    args = parser.parse_args()

    result = asyncio.run(verify_trend_layout(args.url, args.screenshot, args.width, args.height))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Trend analysis layout validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
