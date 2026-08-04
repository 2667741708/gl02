"""验证8093首页前三条建议与参数优化页标准化结果一致。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


def with_hash(url: str, route: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, route))


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

        await page.goto(with_hash(url, "overview"), wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector(".overview-suggestion-list-v13 .overview-suggestion-v11", timeout=45_000)
        await page.wait_for_timeout(1_000)
        overview = await page.evaluate(
            """
            () => {
              const cards = Array.from(document.querySelectorAll('.overview-suggestion-list-v13 .overview-suggestion-v11'));
              const doc = document.documentElement;
              return {
                names: cards.map(card => card.querySelector('.overview-suggestion-copy-v11 b')?.textContent?.trim() || ''),
                summaries: cards.map(card => card.querySelector('.overview-suggestion-copy-v11 span')?.textContent?.trim() || ''),
                count: cards.length,
                note: document.querySelector('.overview-suggestions-panel-v12 .panel-note')?.textContent?.trim() || '',
                horizontal_overflow: doc.scrollWidth > doc.clientWidth + 1,
                clipped_cards: cards.filter(card => card.scrollHeight > card.clientHeight + 2 || card.scrollWidth > card.clientWidth + 2).length,
              };
            }
            """
        )
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)

        await page.locator(".bottom-nav .nav-btn", has_text="参数优化建议").click()
        await page.wait_for_selector(
            '.bf-engine-cockpit[data-recommendation-state="ready"]',
            state="attached",
            timeout=45_000,
        )
        await page.wait_for_selector(
            ".bf-engine-candidates .cockpit-candidate", state="attached", timeout=45_000
        )
        await page.wait_for_timeout(500)
        optimization = await page.evaluate(
            """
            () => {
              const cards = Array.from(document.querySelectorAll('.bf-engine-candidates .cockpit-candidate'));
              return {
                names: cards.slice(0, 3).map(card => card.querySelector('b')?.textContent?.trim() || ''),
                count: cards.length,
                state: document.querySelector('.bf-engine-cockpit')?.dataset.recommendationState || null,
              };
            }
            """
        )
        await browser.close()

    ignored = ("favicon.ico", "Failed to fetch", "status of 502")
    filtered_console_errors = [
        item for item in console_errors if not any(marker in item for marker in ignored)
    ]
    filtered_http_errors = [
        item for item in http_errors
        if "/api/trend/history" not in str(item["url"])
    ]
    failures: list[str] = []
    if overview["count"] != 3:
        failures.append("overview_does_not_show_three_actions")
    if overview["names"] != optimization["names"]:
        failures.append("overview_and_optimization_names_differ")
    if any(not item for item in overview["summaries"]):
        failures.append("overview_summary_text_missing")
    if overview["horizontal_overflow"] or overview["clipped_cards"]:
        failures.append("overview_layout_overflow_or_clipping")
    if optimization["state"] != "ready":
        failures.append("optimization_engine_not_ready")
    if page_errors or filtered_console_errors or filtered_http_errors:
        failures.append("page_or_console_errors")
    return {
        "ok": not failures,
        "failures": failures,
        "viewport": {"width": width, "height": height},
        "overview": overview,
        "optimization": optimization,
        "page_errors": page_errors,
        "console_errors": filtered_console_errors,
        "http_errors": filtered_http_errors,
        "screenshot": str(screenshot),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--screenshot", default="logs/8093_overview_shared_recommendations.png")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    result = asyncio.run(verify(args.url, Path(args.screenshot), args.width, args.height))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
