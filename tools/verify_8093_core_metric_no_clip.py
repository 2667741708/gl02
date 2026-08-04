from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://127.0.0.1:8093/?ws_port=8768#overview"
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
PAGES = (
    (
        "顶压 / 送风 / 喷煤 / 出铁口",
        {
            "煤气顶压": (5, "顶压D"),
            "送风供氧": (5, "富氧流量"),
            "喷煤": (2, "喷煤设定"),
            "出铁口温度": (2, "2#铁口温度参考"),
        },
    ),
    (
        "热制度 / 料线 / 压差",
        {
            "热制度": (7, "顶温D"),
            "料线": (3, "北尺"),
            "压差透气": (4, "总压差"),
        },
    ),
)


def verify_source(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    checks = {
        "bug_marker": "BUG-8093-CORE-METRIC-GROUP-CLIP-20260715" in text,
        "title_weight_included": "flex:calc(var(--rows) + 1) 1 0!important" in text,
        "compact_rows": "repeat(var(--rows),minmax(22px,1fr))" in text,
        "short_rows": "repeat(var(--rows),minmax(20px,1fr))" in text,
        "first_missing_row_restored": "顶压D" in text,
        "last_missing_row_restored": "2#铁口温度参考" in text,
    }
    return {"path": str(path), "checks": checks, "passed": all(checks.values())}


async def goto_overview(page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeoutError:
        await page.goto(url, wait_until="commit", timeout=20_000)
    await page.wait_for_selector(".core-page-v7-content", state="visible", timeout=45_000)


async def inspect_active_page(page) -> list[dict]:
    return await page.evaluate(
        """
        () => [...document.querySelectorAll('.core-page-v7-content .core-metric-group')].map(group => {
          const groupRect = group.getBoundingClientRect();
          const rows = [...group.querySelectorAll('.core-group-row')];
          const rowResults = rows.map(row => {
            const rect = row.getBoundingClientRect();
            const style = getComputedStyle(row);
            const name = row.querySelector('.metric-name')?.textContent?.trim() || '';
            return {
              name,
              top: Number(rect.top.toFixed(2)),
              bottom: Number(rect.bottom.toFixed(2)),
              visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.height > 0,
              clipped: rect.top < groupRect.top - 0.5 || rect.bottom > groupRect.bottom + 0.5,
            };
          });
          return {
            title: group.querySelector('.core-group-title span')?.textContent?.trim() || '',
            rowCount: rows.length,
            lastRow: rowResults.at(-1)?.name || '',
            groupTop: Number(groupRect.top.toFixed(2)),
            groupBottom: Number(groupRect.bottom.toFixed(2)),
            hiddenRows: rowResults.filter(row => !row.visible).map(row => row.name),
            clippedRows: rowResults.filter(row => row.clipped).map(row => row.name),
          };
        })
        """
    )


async def inspect_viewport(page, url: str, screenshot: Path) -> dict:
    page_errors: list[str] = []
    console_errors: list[dict[str, str]] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: console_errors.append(
            {"text": msg.text, "url": str(msg.location.get("url", ""))}
        )
        if msg.type == "error"
        else None,
    )
    await goto_overview(page, url)

    page_results: list[dict] = []
    failures: list[str] = []
    for button_name, expected in PAGES:
        button = page.get_by_role("button", name=button_name, exact=True)
        if await button.count() != 1:
            page_results.append({"page": button_name, "passed": False, "error": "tab_button_missing"})
            failures.append(f"tab_button:{button_name}")
            continue
        await button.click()
        groups = await inspect_active_page(page)
        group_by_title = {group["title"]: group for group in groups}
        page_failures: list[str] = []
        if set(group_by_title) != set(expected):
            page_failures.append("group_titles")
        for title, (row_count, last_row) in expected.items():
            group = group_by_title.get(title)
            if not group:
                continue
            if group["rowCount"] != row_count:
                page_failures.append(f"{title}:row_count")
            if group["lastRow"] != last_row:
                page_failures.append(f"{title}:last_row")
            if group["hiddenRows"]:
                page_failures.append(f"{title}:hidden")
            if group["clippedRows"]:
                page_failures.append(f"{title}:clipped")
        page_results.append(
            {
                "page": button_name,
                "passed": not page_failures,
                "failures": page_failures,
                "groups": groups,
            }
        )
        failures.extend(f"{button_name}:{item}" for item in page_failures)

    shell = await page.evaluate(
        """
        () => ({
          formalHeader: !!document.querySelector('.topbar.branded-topbar'),
          viewportWidth: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          corePanelVisible: !!document.querySelector('.core-page-v7')?.getBoundingClientRect().height,
        })
        """
    )
    if not shell["formalHeader"]:
        failures.append("formal_header")
    if not shell["corePanelVisible"]:
        failures.append("core_panel")
    if shell["documentWidth"] > shell["viewportWidth"] + 1:
        failures.append("horizontal_overflow")

    filtered_console_errors = [
        item
        for item in console_errors
        if "favicon.ico" not in item["url"]
        and "WebSocket connection" not in item["text"]
        and "Failed to fetch" not in item["text"]
    ]
    if page_errors or filtered_console_errors:
        failures.append("page_or_console_errors")
    await page.screenshot(path=str(screenshot), full_page=False)
    return {
        "passed": not failures,
        "failures": failures,
        "shell": shell,
        "pages": page_results,
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
        if args.browser == "msedge":
            browser = await playwright.chromium.launch(headless=True, channel="msedge")
        else:
            browser = await getattr(playwright, args.browser).launch(headless=True)
        for width, height in viewports:
            page = await browser.new_page(viewport={"width": width, "height": height})
            screenshot = output / f"core_metric_no_clip_{args.browser}_{width}x{height}.png"
            try:
                result = await inspect_viewport(page, args.url, screenshot)
            except Exception as exc:
                result = {
                    "passed": False,
                    "failures": ["unhandled_error"],
                    "error": str(exc),
                    "screenshot": str(screenshot),
                }
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
    parser = argparse.ArgumentParser(description="Verify that all 28 overview core metrics remain visible and unclipped.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit", "msedge"), default="chromium")
    parser.add_argument("--matrix", choices=("all", "representative"), default="all")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "8093_core_metric_no_clip_qa"))
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
