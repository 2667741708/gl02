from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
DEFAULT_URL = "http://127.0.0.1:8093/?ws_port=8768#overview"


def static_check() -> dict:
    text = SOURCE.read_text(encoding="utf-8")
    checks = {
        "requirement": "REQ-8093-CORE-SPARK-DETAIL-CORRELATION-20260715" in text,
        "clickable_spark": "查看${name}趋势与相关性" in text,
        "time_value_detail": "可缩放趋势与时间点数值" in text,
        "pearson": "corePearsonV1" in text,
        "scatter": "同分钟样本" in text,
        "non_causal_notice": "相关不等于因果" in text,
        "zoom": "type:'slider'" in text,
    }
    return {"passed": all(checks.values()), "checks": checks}


async def browser_check(url: str, browser_name: str, width: int, height: int, screenshot: Path) -> dict:
    async with async_playwright() as playwright:
        browser = await (
            playwright.chromium.launch(headless=True, channel="msedge")
            if browser_name == "msedge"
            else getattr(playwright, browser_name).launch(headless=True)
        )
        page = await browser.new_page(viewport={"width": width, "height": height})
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(f"{msg.text} [{msg.location.get('url', '')}]") if msg.type == "error" else None,
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        trigger = page.get_by_role("button", name="查看综合顶压趋势与相关性", exact=True)
        await trigger.wait_for(timeout=120_000)
        if await trigger.count() != 1:
            raise RuntimeError("core trend trigger is not unique")
        await trigger.click()
        dialog = page.get_by_role("dialog", name="综合顶压趋势与变量关联", exact=True)
        await dialog.wait_for(timeout=10_000)
        select = dialog.locator(".core-detail-select select")
        if await select.count() != 1:
            raise RuntimeError("comparison selector is not unique")
        await select.select_option("DP_total")
        await page.screenshot(path=str(screenshot), full_page=False)
        state = await page.evaluate(
            """() => ({
              dialog: !!document.querySelector('[role=dialog].core-detail-dialog'),
              triggerCount: document.querySelectorAll('.core-spark-button').length,
              detailChart: !!document.querySelector('.core-detail-chart'),
              scatter: !!document.querySelector('.core-detail-scatter'),
              selected: document.querySelector('.core-detail-select select')?.value,
              horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
            })"""
        )
        expected_console = ("favicon.ico", "WebSocket connection", "Failed to fetch", "[BABEL] Note: The code generator has deoptimised")
        filtered_console = [item for item in console_errors if not any(expected in item for expected in expected_console)]
        await browser.close()
    failures = []
    if not all((state["dialog"], state["detailChart"], state["scatter"], state["triggerCount"] == 14, state["selected"] == "DP_total")):
        failures.append("interaction_contract")
    if state["horizontalOverflow"]:
        failures.append("horizontal_overflow")
    if page_errors or filtered_console:
        failures.append("page_or_console_errors")
    return {"passed": not failures, "failures": failures, "state": state, "page_errors": page_errors, "console_errors": filtered_console, "screenshot": str(screenshot)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify clickable core mini trends open detail and correlation analysis.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit", "msedge"), default="chromium")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "8093_core_spark_detail_qa"))
    args = parser.parse_args()
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    payload = {"static": static_check()}
    if not args.static_only:
        payload["browser"] = asyncio.run(browser_check(args.url, args.browser, args.width, args.height, output / f"core_spark_detail_{args.browser}_{args.width}x{args.height}.png"))
    payload["passed"] = payload["static"]["passed"] and (payload.get("browser", {}).get("passed", True))
    manifest = output / f"manifest_{args.browser}_{args.width}x{args.height}.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "manifest": str(manifest)}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
