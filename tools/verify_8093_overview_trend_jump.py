"""验证8093首页趋势跳转位于标题栏且不遮挡图表信息。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


def with_overview_hash(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "overview"))


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
            lambda response: http_errors.append(
                {"status": response.status, "url": response.url}
            )
            if response.status >= 400
            else None,
        )
        await page.goto(with_overview_hash(url), wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector(".overview-trend-jump-v14", timeout=45_000)
        await page.wait_for_timeout(2_000)
        layout = await page.evaluate(
            """
            () => {
              const button = document.querySelector('.overview-trend-jump-v14');
              const head = button?.closest('.panel-head');
              const action = button?.closest('.panel-head-action');
              const chart = document.querySelector('.overview-large-trend-panel .overview-large-chart-v8');
              const rect = element => {
                const value = element.getBoundingClientRect();
                return {left:value.left,right:value.right,top:value.top,bottom:value.bottom,width:value.width,height:value.height};
              };
              const buttonRect = button ? rect(button) : null;
              const headRect = head ? rect(head) : null;
              const chartRect = chart ? rect(chart) : null;
              return {
                button_text: button?.innerText?.trim() || '',
                in_header_action: Boolean(action),
                button_rect: buttonRect,
                head_rect: headRect,
                chart_rect: chartRect,
                inside_header: Boolean(buttonRect && headRect && buttonRect.left >= headRect.left - 1 && buttonRect.right <= headRect.right + 1 && buttonRect.top >= headRect.top - 1 && buttonRect.bottom <= headRect.bottom + 1),
                overlaps_chart: Boolean(buttonRect && chartRect && buttonRect.left < chartRect.right && buttonRect.right > chartRect.left && buttonRect.top < chartRect.bottom && buttonRect.bottom > chartRect.top),
                horizontal_overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
              };
            }
            """
        )
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)
        await page.evaluate("window.__overviewTrendJumpSentinel = 'same-document'")
        await page.locator(".overview-trend-jump-v14").click()
        await page.wait_for_function("location.hash === '#trend'", timeout=10_000)
        navigation = await page.evaluate(
            """() => ({
              hash: location.hash,
              same_document: window.__overviewTrendJumpSentinel === 'same-document',
              trend_visible: Boolean(document.querySelector('.trend-grid')),
            })"""
        )
        await browser.close()

    ignored_console = ("favicon.ico", "Failed to fetch", "status of 502")
    filtered_console = [
        item for item in console_errors
        if not any(marker in item for marker in ignored_console)
    ]
    filtered_http = [
        item for item in http_errors
        if "/api/trend/history" not in str(item["url"])
    ]
    failures: list[str] = []
    if layout["button_text"].replace("\n", "") != "进入趋势分析›":
        failures.append("trend_jump_text_missing")
    if not layout["in_header_action"] or not layout["inside_header"]:
        failures.append("trend_jump_not_inside_panel_header")
    if layout["overlaps_chart"]:
        failures.append("trend_jump_overlaps_chart")
    if layout["horizontal_overflow"]:
        failures.append("horizontal_overflow")
    if navigation != {
        "hash": "#trend",
        "same_document": True,
        "trend_visible": True,
    }:
        failures.append("trend_jump_did_not_use_in_app_navigation")
    if page_errors or filtered_console or filtered_http:
        failures.append("page_or_console_errors")
    return {
        "ok": not failures,
        "failures": failures,
        "viewport": {"width": width, "height": height},
        "layout": layout,
        "navigation": navigation,
        "page_errors": page_errors,
        "console_errors": filtered_console,
        "http_errors": filtered_http,
        "screenshot": str(screenshot),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--screenshot", default="logs/8093_overview_trend_jump.png")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    result = asyncio.run(verify(args.url, Path(args.screenshot), args.width, args.height))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
