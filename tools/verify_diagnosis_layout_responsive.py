from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]


def default_file_url() -> str:
    return (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").resolve().as_uri() + "#diagnosis"


async def inspect_layout(url: str, viewport: dict[str, int], name: str, screenshot_dir: Path) -> dict:
    errors: list[str] = []
    console_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport=viewport)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector(".diagnosis-grid", timeout=30_000)
        await page.wait_for_timeout(4000)
        await page.evaluate(
            """
            () => {
              const main = document.querySelector('.main');
              if (main) main.scrollTop = main.scrollHeight;
            }
            """
        )
        await page.wait_for_timeout(500)
        result = await page.evaluate(
            """
            () => {
              const main = document.querySelector('.main');
              const nav = document.querySelector('.bottom-nav');
              const bottom = document.querySelector('.diag-bottom');
              const table = document.querySelector('.diag-table');
              const rect = el => {
                const r = el.getBoundingClientRect();
                return { y: r.y, height: r.height, bottom: r.bottom, width: r.width, right: r.right };
              };
              const navRect = rect(nav);
              const bottomRect = rect(bottom);
              const tableCells = Array.from(document.querySelectorAll('.diag-table td,.diag-table th')).map(td => ({
                text: td.textContent.trim(),
                scrollWidth: td.scrollWidth,
                clientWidth: td.clientWidth,
              }));
              const baseRowOverflowCount = Array.from(document.querySelectorAll('.base-row')).filter(row => {
                const rowRect = row.getBoundingClientRect();
                return Array.from(row.children).some(child => child.getBoundingClientRect().right > rowRect.right + 1);
              }).length;
              return {
                main_client_height: main.clientHeight,
                main_scroll_height: main.scrollHeight,
                main_scroll_top: main.scrollTop,
                bottom_above_nav: bottomRect.bottom <= navRect.y + 1,
                visible_bottom_height: Math.max(0, Math.min(bottomRect.bottom, navRect.y) - Math.max(bottomRect.y, 0)),
                table_exists: !!table,
                table_cell_overflow_count: tableCells.filter(cell => cell.scrollWidth > cell.clientWidth + 1).length,
                base_row_overflow_count: baseRowOverflowCount,
                body_has_raw_scores: document.body.innerText.includes('raw_scores'),
              };
            }
            """
        )
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot = screenshot_dir / f"diagnosis_layout_{name}.png"
        await page.screenshot(path=str(screenshot), full_page=False)
        await browser.close()
    result["viewport"] = viewport
    result["screenshot"] = str(screenshot)
    result["page_errors"] = errors
    result["console_errors"] = console_errors
    return result


async def run_checks(url: str, screenshot_dir: Path) -> list[dict]:
    viewports = [
        ("short_2048x420", {"width": 2048, "height": 420}),
        ("desktop_2048x1152", {"width": 2048, "height": 1152}),
    ]
    results = []
    for name, viewport in viewports:
        results.append(await inspect_layout(url, viewport, name, screenshot_dir))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify diagnosis page layout does not clip bottom panels or table text.")
    parser.add_argument("--url", default=default_file_url())
    parser.add_argument("--screenshot-dir", default=str(ROOT / "logs"))
    args = parser.parse_args()

    results = asyncio.run(run_checks(args.url, Path(args.screenshot_dir)))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(item["page_errors"] or item["console_errors"] for item in results):
        return 2
    if any(not item["table_exists"] for item in results):
        return 3
    if any(item["table_cell_overflow_count"] or item["base_row_overflow_count"] for item in results):
        return 4
    if not all(item["bottom_above_nav"] for item in results):
        return 5
    short = next(item for item in results if item["viewport"]["height"] == 420)
    if short["visible_bottom_height"] < 250:
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
