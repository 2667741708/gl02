from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


SIZES = ((1920, 1080), (1546, 864), (1440, 900), (1366, 768), (1280, 720))
PAGES = (
    ("overview", "总览"),
    ("diagnosis", "炉况诊断"),
    ("optimization", "参数优化建议"),
    ("trend", "趋势分析"),
    ("qa", "智能问答/知识助手"),
)


async def capture(base_url: str, output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        for width, height in SIZES:
            context = await browser.new_context(viewport={"width": width, "height": height})
            page = await context.new_page()
            start_url = f"{base_url.rstrip('/')}?ws_port=8768&optimization_polish_case=1#optimization"
            await page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_selector(".bf-engine-cockpit, .optimization-workbench-v10", timeout=45_000)
            for nav_index, (route, title) in enumerate(PAGES):
                page_errors: list[str] = []
                console_errors: list[str] = []
                page.on("pageerror", lambda exc, bucket=page_errors: bucket.append(str(exc)))
                page.on(
                    "console",
                    lambda msg, bucket=console_errors: bucket.append(msg.text) if msg.type == "error" else None,
                )
                status = "ok"
                error = ""
                try:
                    nav = page.locator(".bottom-nav .nav-btn").nth(nav_index)
                    await nav.evaluate("element => element.click()")
                    await page.wait_for_function("target => location.hash === '#' + target", arg=route, timeout=15_000)
                    await page.wait_for_function(
                        "label => document.querySelector('.bottom-nav .nav-btn.active')?.innerText.includes(label)",
                        arg=title,
                        timeout=15_000,
                    )
                    await page.wait_for_timeout(5_000 if route in {"overview", "trend", "qa"} else 3_000)
                except Exception as exc:  # screenshot the failure state for auditability
                    status = "failed"
                    error = str(exc)
                filename = f"{width}x{height}_{route}.png"
                screenshot = output_dir / filename
                await page.screenshot(path=str(screenshot), full_page=False)
                metrics = await page.evaluate(
                    """
                    () => ({
                      hash: location.hash,
                      viewportWidth: innerWidth,
                      documentWidth: document.documentElement.scrollWidth,
                      documentHeight: document.documentElement.scrollHeight,
                      bodyTextLength: (document.body?.innerText || '').length
                    })
                    """
                )
                results.append(
                    {
                        "size": f"{width}x{height}",
                        "route": route,
                        "title": title,
                        "status": status,
                        "error": error,
                        "screenshot": str(screenshot),
                        "horizontal_overflow": metrics["documentWidth"] > width + 1,
                        "metrics": metrics,
                        "page_errors": page_errors,
                        "console_errors": [
                            item
                            for item in console_errors
                            if "Failed to fetch" not in item and "WebSocket connection" not in item
                        ],
                    }
                )
            await page.close()
            await context.close()
        await browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the five 8093 pages at five desktop viewport sizes.")
    parser.add_argument("--url", default="http://10.30.220.12:8093/")
    parser.add_argument("--output-dir", default="logs/8093_five_pages_matrix_20260711")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    results = asyncio.run(capture(args.url, output_dir))
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [item for item in results if item["status"] != "ok" or item["horizontal_overflow"] or item["page_errors"] or item["console_errors"]]
    print(json.dumps({"count": len(results), "failed": len(failures), "manifest": str(manifest)}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
