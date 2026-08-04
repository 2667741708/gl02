from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
ASSET = ROOT / "高炉前端数据" / "assets" / "bf-heat-dashboard-link.js"
HEAT_PAGE = ROOT / "db_dashboard" / "heat.html"
DEFAULT_URL = "http://127.0.0.1:8095/?ws_port=8768#overview"
EXPECTED_DASHBOARD_URL = "http://127.0.0.1:8890/heat"
ROUTES = (
    ("overview", "总览"),
    ("diagnosis", "炉况诊断"),
    ("optimization", "参数优化建议"),
    ("trend", "趋势分析"),
    ("qa", "智能问答/知识助手"),
)
ALL_VIEWPORTS = (
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1546, 864),
    (1920, 1080),
    (1024, 768),
    (768, 1024),
    (390, 844),
    (375, 667),
)
REPRESENTATIVE_VIEWPORTS = (
    (1920, 1080),
    (1366, 768),
    (768, 1024),
    (390, 844),
)


def static_check(expect_enabled: bool = False) -> dict:
    source = SOURCE.read_text(encoding="utf-8")
    asset = ASSET.read_text(encoding="utf-8")
    heat_page = HEAT_PAGE.read_text(encoding="utf-8")
    source_loads_asset = (
        'src="assets/bf-heat-dashboard-link.js?v=20260726-r1"' in source
    )
    checks = {
        "requirement": "REQ-8094-HEAT-DASHBOARD-LINK-20260726" in asset,
        "source_enable_state": source_loads_asset is expect_enabled,
        "workstation_target": (
            'data-url="http://127.0.0.1:8890/heat"' in source
        )
        is expect_enabled,
        "stable_test_id": 'dataset.testid = "heat-dashboard-link"' in asset,
        "new_tab_isolated": 'link.rel = "noopener noreferrer"' in asset,
        "configurable_target": "window.__BF_HEAT_DASHBOARD_URL__" in asset,
        "six_column_nav": "grid-template-columns:repeat(6" in asset,
        "mobile_contract": "@media(max-width:600px)" in asset,
        "dashboard_back_link_disabled": "返回高炉工作台" not in heat_page,
    }
    return {"passed": all(checks.values()), "checks": checks}


async def verify_viewport(
    browser,
    base_url: str,
    browser_name: str,
    width: int,
    height: int,
    output: Path,
) -> list[dict]:
    page = await browser.new_page(viewport={"width": width, "height": height})
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    await page.goto(base_url, wait_until="domcontentloaded", timeout=120_000)
    await page.locator('[data-testid="heat-dashboard-link"]').wait_for(
        state="visible", timeout=120_000
    )

    rows: list[dict] = []
    for route, label in ROUTES:
        if route != "overview":
            button = page.locator(".bottom-nav button").filter(has_text=label)
            count = await button.count()
            if count != 1:
                raise RuntimeError(f"{route} navigation count={count}")
            await button.click()
            await page.wait_for_url(f"**#{route}", timeout=10_000)

        screenshot = output / f"{browser_name}_{width}x{height}_{route}.png"
        state = await page.evaluate(
            """
            () => {
              const link = document.querySelector('[data-testid="heat-dashboard-link"]');
              const rect = link?.getBoundingClientRect();
              const style = link ? getComputedStyle(link) : null;
              return {
                route: location.hash.replace(/^#/, ''),
                formal_header: !!document.querySelector('.topbar.branded-topbar'),
                nav_count: document.querySelectorAll('.bottom-nav .nav-btn').length,
                link_count: document.querySelectorAll('[data-testid="heat-dashboard-link"]').length,
                link_href: link?.href || '',
                link_target: link?.target || '',
                link_visible: !!link && rect.width > 1 && rect.height > 1 &&
                  style.display !== 'none' && style.visibility !== 'hidden',
                link_inside_viewport: !!rect && rect.left >= -1 && rect.right <= innerWidth + 1,
                horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 1,
                document_width: document.documentElement.scrollWidth,
                viewport_width: innerWidth,
              };
            }
            """
        )
        await page.screenshot(path=str(screenshot), full_page=False)
        filtered_console = [
            text
            for text in console_errors
            if not any(
                expected in text
                for expected in (
                    "favicon.ico",
                    "WebSocket connection",
                    "can’t establish a connection",
                    "can't establish a connection",
                    "Failed to fetch",
                    "[BABEL] Note:",
                )
            )
        ]
        failures: list[str] = []
        expected = {
            "route": route,
            "formal_header": True,
            "nav_count": 6,
            "link_count": 1,
            "link_href": EXPECTED_DASHBOARD_URL,
            "link_target": "_blank",
            "link_visible": True,
            "link_inside_viewport": True,
            "horizontal_overflow": False,
        }
        for key, expected_value in expected.items():
            if state.get(key) != expected_value:
                failures.append(f"{key}={state.get(key)!r}")
        if page_errors or filtered_console:
            failures.append("page_or_console_errors")
        rows.append(
            {
                "browser": browser_name,
                "viewport": f"{width}x{height}",
                "url": page.url,
                "route": route,
                "data_state": "live_or_explicit_waiting",
                "screenshot": str(screenshot),
                "failures": failures,
                "state": state,
                "page_errors": list(page_errors),
                "console_errors": filtered_console,
            }
        )
        page_errors.clear()
        console_errors.clear()

    await page.close()
    return rows


async def browser_matrix(args: argparse.Namespace) -> dict:
    viewports = (
        ALL_VIEWPORTS if args.matrix == "all" else REPRESENTATIVE_VIEWPORTS
    )
    if args.browser == "msedge":
        viewports = ((1366, 768),)
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    async with async_playwright() as playwright:
        if args.browser == "msedge":
            browser = await playwright.chromium.launch(headless=True, channel="msedge")
        else:
            browser = await getattr(playwright, args.browser).launch(headless=True)
        for width, height in viewports:
            rows.extend(
                await verify_viewport(
                    browser,
                    args.url,
                    args.browser,
                    width,
                    height,
                    output,
                )
            )
        await browser.close()
    return {
        "browser": args.browser,
        "matrix": args.matrix,
        "passed": not any(row["failures"] for row in rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the 8094-to-8890 heat dashboard navigation entry."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--browser",
        choices=("chromium", "firefox", "webkit", "msedge"),
        default="chromium",
    )
    parser.add_argument(
        "--matrix", choices=("all", "representative"), default="all"
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "logs" / "8094_heat_dashboard_link_qa"),
    )
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument(
        "--expect-enabled",
        action="store_true",
        help="Use only while testing an explicitly staged page with the link enabled.",
    )
    args = parser.parse_args()

    payload: dict = {"static": static_check(args.expect_enabled)}
    if not args.static_only:
        if not args.expect_enabled:
            parser.error("browser matrix requires --expect-enabled")
        payload["browser"] = asyncio.run(browser_matrix(args))
    payload["passed"] = payload["static"]["passed"] and payload.get(
        "browser", {"passed": True}
    )["passed"]

    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / f"manifest_{args.browser}_{args.matrix}.json"
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": payload["passed"],
                "manifest": str(manifest),
                "rows": len(payload.get("browser", {}).get("rows", [])),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
