"""Browser verification for the 8093 automatic-monitor drawer and Markdown rendering."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def verify(url: str, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 768})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(url, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(1_200)
        closed = await page.evaluate(
            """() => ({
              marker: !!window.__BF_AUTO_MONITOR_DOCK_MD_V9__,
              trigger: !!document.querySelector('#bf-auto-trigger'),
              triggerParent: document.querySelector('#bf-auto-trigger')?.parentElement?.className || null,
              monitorDisplay: getComputedStyle(document.querySelector('#bf-auto-monitor')).display,
              horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
            })"""
        )
        await page.screenshot(path=str(output_dir / "overview_1366x768_auto_monitor_v9_closed.png"), full_page=True)
        await page.locator("#bf-auto-trigger").click()
        await page.wait_for_timeout(250)
        opened = await page.evaluate(
            """() => {
              const element = document.querySelector('#bf-auto-monitor');
              const rect = element.getBoundingClientRect();
              return {
                display: getComputedStyle(element).display,
                rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
              };
            }"""
        )
        await page.screenshot(path=str(output_dir / "overview_1366x768_auto_monitor_v9_open.png"), full_page=True)
        markdown = await page.evaluate(
            """async () => {
              const element = document.createElement('div');
              element.className = 'bf-auto-summary';
              element.textContent = '**关键结论**\\n\\n- 第一项\\n- 第二项';
              document.querySelector('#bf-auto-monitor').appendChild(element);
              await new Promise(resolve => setTimeout(resolve, 450));
              return {
                html: element.innerHTML,
                hasStrong: !!element.querySelector('strong'),
                hasList: !!element.querySelector('ul > li'),
              };
            }"""
        )
        await page.locator("#bf-auto-monitor .bf-auto-close-v9").click()
        await page.wait_for_timeout(150)
        after_close = await page.evaluate(
            "() => ({display: getComputedStyle(document.querySelector('#bf-auto-monitor')).display})"
        )
        await browser.close()
    return {
        "url": url,
        "viewport": "1366x768",
        "closed": closed,
        "opened": opened,
        "markdown": markdown,
        "afterClose": after_close,
        "pageErrors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://10.30.220.12:8093/#overview")
    parser.add_argument("--output-dir", default="logs/8093_coregroups_playwright")
    args = parser.parse_args()
    result = asyncio.run(verify(args.url, Path(args.output_dir)))
    output = Path(args.output_dir) / "auto_monitor_v9_remote_result.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not (
        result["closed"]["marker"]
        and result["closed"]["trigger"]
        and result["closed"]["monitorDisplay"] == "none"
        and result["opened"]["display"] == "flex"
        and result["markdown"]["hasStrong"]
        and result["markdown"]["hasList"]
        and result["afterClose"]["display"] == "none"
        and not result["pageErrors"]
    ):
        raise SystemExit("Automatic monitor drawer verification failed")


if __name__ == "__main__":
    main()
