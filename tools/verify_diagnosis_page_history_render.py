from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def verify(url: str, screenshot: Path | None, timeout_ms: int) -> dict:
    console_errors: list[str] = []
    page_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 2048, "height": 1152})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector(".diag-table", timeout=timeout_ms)
        await page.wait_for_timeout(2500)
        result = await page.evaluate(
            """
            () => {
              const table = document.querySelector('.diag-table');
              const headers = Array.from(document.querySelectorAll('.diag-table thead th')).map(th => th.textContent.trim());
              const rows = Array.from(document.querySelectorAll('.diag-table tbody tr'));
              const valueCells = rows.flatMap(row => Array.from(row.querySelectorAll('td')).slice(1, -1).map(td => td.textContent.trim()));
              const canvases = Array.from(document.querySelectorAll('canvas')).map(c => {
                const ctx = c.getContext('2d');
                let nonBlank = false;
                if (ctx && c.width && c.height) {
                  const data = ctx.getImageData(0, 0, Math.min(c.width, 80), Math.min(c.height, 80)).data;
                  for (let i = 3; i < data.length; i += 4) {
                    if (data[i] !== 0) { nonBlank = true; break; }
                  }
                }
                return { width: c.width, height: c.height, nonBlank };
              });
              return {
                title_found: document.body.innerText.includes('诊断演化趋势'),
                diag_bottom_text: document.querySelector('.diag-bottom')?.innerText || '',
                old_trend_copy_visible: (() => {
                  const text = document.querySelector('.diag-bottom')?.innerText || '';
                  return text.includes('诊断演化趋势（') || text.includes('近1小时12次') || text.includes('近6次');
                })(),
                table_found: !!table,
                headers,
                value_cells: valueCells.length,
                dash_cells: valueCells.filter(text => text === '--').length,
                numeric_cells: valueCells.filter(text => /^-?\\d/.test(text)).length,
                canvas_count: canvases.length,
                nonblank_canvas_count: canvases.filter(c => c.nonBlank).length,
                body_has_raw_scores: document.body.innerText.includes('raw_scores'),
                history_header_count: document.querySelectorAll('.diag-history-12 thead th').length,
                history_has_horizontal_scroll: (() => {
                  const wrap = document.querySelector('.diag-history-scroll');
                  return wrap ? wrap.scrollWidth > wrap.clientWidth + 1 : false;
                })(),
              };
            }
            """
        )
        if screenshot:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot), full_page=True)
            result["screenshot"] = str(screenshot)
        await browser.close()
    result["console_errors"] = console_errors
    result["page_errors"] = page_errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the 8092 diagnosis page renders database-backed diagnosis history.")
    parser.add_argument("--url", default="http://127.0.0.1:8092/#diagnosis")
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--screenshot", default="logs/diagnosis_history_page_verify.png")
    args = parser.parse_args()

    screenshot = Path(args.screenshot) if args.screenshot else None
    result = asyncio.run(verify(args.url, screenshot, args.timeout_ms))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["page_errors"] or result["console_errors"]:
        return 2
    if not result["title_found"] or not result["table_found"]:
        return 3
    if result["old_trend_copy_visible"] or result["history_has_horizontal_scroll"]:
        return 7
    if result["history_header_count"] != 14:
        return 8
    if result["dash_cells"] != 0 or result["numeric_cells"] <= 0:
        return 4
    if result["canvas_count"] <= 0 or result["nonblank_canvas_count"] <= 0:
        return 5
    if result["body_has_raw_scores"]:
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
