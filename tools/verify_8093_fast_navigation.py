from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://10.30.220.12:8093/?ws_port=8768#overview"
DEFAULT_SOURCE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
ALL_VIEWPORTS = [
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1546, 864),
    (1920, 1080),
    (1024, 768),
    (768, 1024),
    (390, 844),
    (375, 667),
]
REPRESENTATIVE_VIEWPORTS = [(1920, 1080), (1366, 768), (768, 1024), (390, 844)]
TARGETS = (
    ("diagnosis", "进入炉况诊断", ".diagnosis-grid, .diagnosis-screen"),
    ("optimization", "查看参数优化建议：优化送风制度", ".optimization-cockpit"),
    ("trend", "进入趋势分析", ".trend-grid"),
)


def verify_source(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    checks = {
        "requirement_marker": "REQ-8093-FAST-IN-APP-NAV-20260715" in text,
        "trend_button": 'aria-label="进入趋势分析"' in text,
        "trend_route": "overviewDecisionNavigateV11('trend')" in text,
        "internal_nav_click": "buttons=document.querySelectorAll('.bottom-nav .nav-btn')" in text,
        "overview_reload_removed": "window.location.hash=hash;window.location.reload()" not in text,
        "workbench_reload_removed": (
            "function optWorkbenchNavigate(hash){\n  if(!hash)return;\n  overviewDecisionNavigateV11(hash);\n}"
            in text
        ),
    }
    return {"path": str(path), "checks": checks, "passed": all(checks.values())}


async def goto_overview(page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeoutError:
        await page.goto(url, wait_until="commit", timeout=20_000)
    await page.wait_for_selector('[aria-label="进入炉况诊断"]', timeout=45_000)
    await page.wait_for_selector('[aria-label="进入趋势分析"]', timeout=45_000)


async def click_target(
    page,
    route: str,
    aria_label: str,
    target_selector: str,
    *,
    max_latency_ms: int,
    timeout_ms: int,
) -> dict:
    locator = (
        page.locator(".overview-suggestion-v11, .overview-suggestion-empty-v13")
        if route == "optimization"
        else page.get_by_role("button", name=aria_label, exact=True)
    )
    count = await locator.count()
    if (route == "optimization" and count < 1) or (route != "optimization" and count != 1):
        return {"route": route, "passed": False, "error": f"button_count={count}"}
    if route == "optimization":
        locator = locator.nth(0)
    before_token = await page.evaluate("window.__bfNavigationTestToken")
    started = perf_counter()
    await locator.click()
    await page.wait_for_function("route => location.hash === '#' + route", arg=route, timeout=timeout_ms)
    await page.wait_for_function(
        "index => document.querySelectorAll('.bottom-nav .nav-btn')[index]?.classList.contains('active')",
        arg={"diagnosis": 1, "optimization": 2, "trend": 3}[route],
        timeout=timeout_ms,
    )
    await page.wait_for_selector(target_selector, timeout=timeout_ms)
    elapsed_ms = round((perf_counter() - started) * 1000, 1)
    after_token = await page.evaluate("window.__bfNavigationTestToken")
    return {
        "route": route,
        "passed": before_token == after_token and elapsed_ms <= max_latency_ms,
        "elapsed_ms": elapsed_ms,
        "document_reloaded": before_token != after_token,
        "hash": await page.evaluate("location.hash"),
        "error": "" if before_token == after_token else "document_reloaded",
    }


async def inspect_viewport(page, url: str, screenshot: Path) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    await page.add_init_script(
        "window.__bfNavigationTestToken = `${Date.now()}-${Math.random()}`;"
    )
    await goto_overview(page, url)
    initial = await page.evaluate(
        """
        () => ({
          formalHeader: !!document.querySelector('.topbar.branded-topbar'),
          viewportWidth: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
        })
        """
    )
    initial["trendButtonVisible"] = await page.get_by_role(
        "button", name="进入趋势分析", exact=True
    ).is_visible()
    routes: list[dict] = []
    local_static = "127.0.0.1" in url or "localhost" in url
    for route, aria_label, selector in TARGETS:
        if route != "diagnosis":
            if "127.0.0.1" in url or "localhost" in url:
                target_url = url.replace("#overview", f"&navigation_target={route}#overview")
                await goto_overview(page, target_url)
            else:
                overview = page.get_by_role("button", name="▣ 总览", exact=True)
                if await overview.count() != 1:
                    routes.append({"route": route, "passed": False, "error": "overview_button_missing"})
                    continue
                # Force only the unrelated return trip because the 1024px
                # legacy shell can overlap the bottom nav.  Requirement entry
                # buttons themselves are always exercised with normal clicks.
                await overview.click(force=True)
                await page.wait_for_function("() => location.hash === '#overview'", timeout=8_000)
                await page.wait_for_selector('[aria-label="进入炉况诊断"]', timeout=8_000)
        routes.append(
            await click_target(
                page,
                route,
                aria_label,
                selector,
                max_latency_ms=6_000 if local_static else 1_500,
                timeout_ms=15_000 if local_static else 5_000,
            )
        )
    await page.screenshot(path=str(screenshot), full_page=False)
    filtered_console_errors = [
        item
        for item in console_errors
        if "favicon.ico" not in item
        and "WebSocket connection" not in item
        and "Failed to fetch" not in item
        and not (("127.0.0.1" in url or "localhost" in url) and "status of 404" in item)
    ]
    failures: list[str] = []
    if not initial["formalHeader"]:
        failures.append("formal_header")
    if initial["documentWidth"] > initial["viewportWidth"] + 1:
        failures.append("horizontal_overflow")
    if any(not item.get("passed") for item in routes):
        failures.append("route_navigation")
    if page_errors or filtered_console_errors:
        failures.append("page_or_console_errors")
    return {
        "passed": not failures,
        "failures": failures,
        "initial": initial,
        "routes": routes,
        "page_errors": page_errors,
        "console_errors": filtered_console_errors,
        "screenshot": str(screenshot),
    }


async def verify_browser(args: argparse.Namespace) -> dict:
    viewports = ALL_VIEWPORTS if args.matrix == "all" else REPRESENTATIVE_VIEWPORTS
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    async with async_playwright() as playwright:
        browser = await getattr(playwright, args.browser).launch(headless=True)
        for width, height in viewports:
            page = await browser.new_page(viewport={"width": width, "height": height})
            screenshot = output / f"fast_navigation_{args.browser}_{width}x{height}.png"
            try:
                result = await inspect_viewport(page, args.url, screenshot)
            except Exception as exc:
                result = {
                    "passed": False,
                    "failures": ["unhandled_error"],
                    "error": str(exc),
                    "screenshot": str(screenshot),
                }
                try:
                    await page.screenshot(path=str(screenshot), full_page=False)
                except Exception:
                    pass
            rows.append(
                {
                    "browser": args.browser,
                    "viewport": f"{width}x{height}",
                    "url": args.url,
                    **result,
                }
            )
            await page.close()
        await browser.close()
    return {
        "browser": args.browser,
        "matrix": args.matrix,
        "passed": all(row["passed"] for row in rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify 8093 overview cards use fast in-app navigation and expose the trend-page entry."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    parser.add_argument("--matrix", choices=("all", "representative"), default="all")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "8093_fast_navigation_qa"))
    args = parser.parse_args()

    static_result = verify_source(args.source.resolve())
    payload: dict = {"static": static_result, "passed": static_result["passed"]}
    if not args.static_only:
        browser_result = asyncio.run(verify_browser(args))
        payload["browser"] = browser_result
        payload["passed"] = payload["passed"] and browser_result["passed"]

    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    suffix = "static" if args.static_only else f"{args.browser}_{args.matrix}"
    manifest = output / f"manifest_{suffix}.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "manifest": str(manifest)}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
