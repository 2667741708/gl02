from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Browser, Page, async_playwright


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ("overview", "diagnosis", "optimization", "trend", "qa")
ALL_VIEWPORTS = (
    ("desktop_1280x720", 1280, 720),
    ("desktop_1366x768", 1366, 768),
    ("desktop_1440x900", 1440, 900),
    ("desktop_1546x864", 1546, 864),
    ("desktop_1920x1080", 1920, 1080),
    ("tablet_1024x768", 1024, 768),
    ("tablet_768x1024", 768, 1024),
    ("mobile_390x844", 390, 844),
    ("mobile_375x667", 375, 667),
)
REPRESENTATIVE_VIEWPORTS = tuple(
    item
    for item in ALL_VIEWPORTS
    if item[0] in {"desktop_1920x1080", "desktop_1366x768", "tablet_768x1024", "mobile_390x844"}
)
EDGE_VIEWPORTS = tuple(item for item in ALL_VIEWPORTS if item[0] == "desktop_1366x768")
EXPECTED_CONSOLE = (
    "WebSocket connection",
    "can’t establish a connection to the server at ws://",
    "Failed to fetch",
    "Failed to load resource: the server responded with a status of 404",
    "favicon.ico",
    "ERR_CONNECTION_REFUSED",
    "ERR_FAILED",
    "[BABEL] Note:",
)
EXPECTED_PAGE_ERRORS = ("Failed to fetch", "HTTP 404", "接口 HTTP 404")
ROUTE_SELECTORS = {
    "overview": ".overview-three-column-v12",
    "diagnosis": ".diagnosis-grid",
    "optimization": ".optimization-cockpit",
    "trend": ".trend-grid",
    "qa": ".qa-server-shell.qa-project-shell",
}
PAGE_READY_TIMEOUT_MS = 120_000


def with_route(url: str, route: str, case_name: str) -> str:
    parts = urlsplit(url)
    query = f"{parts.query}&adaptive_case={case_name}" if parts.query else f"adaptive_case={case_name}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, route))


def static_check() -> dict:
    source = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
    text = source.read_text(encoding="utf-8")
    checks = {
        "bug_marker": "BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716" in text,
        "final_style": 'id="v3-overview-adaptive-final"' in text,
        "desktop_fluid_columns": "minmax(320px, 27fr) minmax(0, 45fr) minmax(320px, 28fr)" in text,
        "mobile_single_column": "grid-template-columns: minmax(0, 1fr) !important" in text,
        "core_container_query": "@container overview-core-panel (min-width: 430px)" in text,
        "short_height_boundary": "@media(max-height:820px) and (min-width:1280px)" in text,
    }
    return {"passed": all(checks.values()), "checks": checks}


async def inspect_general(page: Page, width: int, route: str) -> dict:
    return await page.evaluate(
        """
        ({width,selector}) => {
          const rect = el => {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
          };
          const shown = el => {
            const r = el.getBoundingClientRect(), s = getComputedStyle(el);
            return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const app = document.querySelector('.app');
          const header = document.querySelector('.topbar');
          const main = document.querySelector('.main');
          const nav = document.querySelector('.bottom-nav');
          const screen = document.querySelector(selector);
          const overflow = screen ? Array.from(screen.querySelectorAll('*')).filter(el => {
            if (!shown(el) || el.closest('.echarts-tooltip') || el.closest('#bf-auto-monitor') || el.closest('.furnace-follow-lines')) return false;
            const r = el.getBoundingClientRect();
            return r.left < -1 || r.right > innerWidth + 1;
          }).slice(0, 10).map(el => ({
            tag:el.tagName.toLowerCase(),
            className:String(el.className || '').slice(0,100),
            text:String(el.textContent || '').trim().slice(0,60),
            box:rect(el)
          })) : [];
          return {
            viewport:{width:innerWidth,height:innerHeight},
            app:rect(app),header:rect(header),main:rect(main),nav:rect(nav),screen:rect(screen),
            document_overflow_x:document.documentElement.scrollWidth-document.documentElement.clientWidth,
            main_overflow_x:main ? main.scrollWidth-main.clientWidth : null,
            main_scrollable_y:main ? main.scrollHeight>main.clientHeight+1 : false,
            header_in_view:!!header && header.getBoundingClientRect().top>=-1 && header.getBoundingClientRect().bottom<=innerHeight+1,
            nav_in_view:!!nav && nav.getBoundingClientRect().top>=-1 && nav.getBoundingClientRect().bottom<=innerHeight+1,
            main_above_nav:!!main && !!nav && main.getBoundingClientRect().bottom<=nav.getBoundingClientRect().top+1,
            active_screen_inside_main:!!screen && !!main && screen.getBoundingClientRect().left>=main.getBoundingClientRect().left-1 && screen.getBoundingClientRect().right<=main.getBoundingClientRect().right+1,
            mobile_expected:width<1280,
            overflow_samples:overflow
          };
        }
        """,
        {"width": width, "selector": ROUTE_SELECTORS[route]},
    )


async def inspect_core_page(page: Page) -> dict:
    return await page.evaluate(
        """
        () => {
          const body=document.querySelector('.overview-grid>section:nth-child(1) .panel-body');
          const content=document.querySelector('.core-page-v7-content');
          const bodyRect=body?.getBoundingClientRect(), contentRect=content?.getBoundingClientRect();
          const rows=Array.from(document.querySelectorAll('.core-page-v7-content .core-group-row'));
          const tabs=Array.from(document.querySelectorAll('.core-metric-tabs-v7 button'));
          const clippedText=Array.from(document.querySelectorAll('.core-page-v7-content .metric-name,.core-page-v7-content .metric-value')).filter(el => el.scrollWidth>el.clientWidth+1 || el.scrollHeight>el.clientHeight+1).map(el => el.getAttribute('title') || el.textContent.trim());
          const clippedRows=rows.filter(el => {
            const r=el.getBoundingClientRect();
            return !bodyRect || !contentRect || r.left<bodyRect.left-1 || r.right>bodyRect.right+1 || r.top<contentRect.top-1 || r.bottom>contentRect.bottom+1;
          });
          return {
            row_count:rows.length,
            clipped_row_count:clippedRows.length,
            clipped_text:clippedText,
            clipped_tab_count:tabs.filter(el => el.scrollWidth>el.clientWidth+1 || el.scrollHeight>el.clientHeight+1).length,
            core_body_overflow_x:body ? body.scrollWidth-body.clientWidth : null,
            core_content_overflow_y:content ? content.scrollHeight-content.clientHeight : null,
          };
        }
        """
    )


async def inspect_overview(page: Page, width: int) -> dict:
    first_tab = page.get_by_role("button", name="顶压 / 送风 / 喷煤 / 出铁口", exact=True)
    second_tab = page.get_by_role("button", name="热制度 / 料线 / 压差", exact=True)
    if await first_tab.count() != 1 or await second_tab.count() != 1:
        raise RuntimeError("core metric tabs are not unique")
    await first_tab.click()
    page1 = await inspect_core_page(page)

    trigger = page.get_by_role("button", name="查看综合顶压趋势与相关性", exact=True)
    if await trigger.count() != 1:
        raise RuntimeError("core metric detail trigger is not unique")
    await trigger.click()
    dialog = page.get_by_role("dialog", name="综合顶压趋势与变量关联", exact=True)
    await dialog.wait_for(state="visible", timeout=10_000)
    close = page.get_by_role("button", name="关闭变量详情", exact=True)
    if await close.count() != 1:
        raise RuntimeError("core metric detail close button is not unique")
    await close.click()
    await dialog.wait_for(state="hidden", timeout=10_000)

    await second_tab.click()
    page2 = await inspect_core_page(page)
    layout = await page.evaluate(
        """
        (width) => {
          const grid=document.querySelector('.overview-three-column-v12');
          const main=document.querySelector('.main');
          const children=grid ? Array.from(grid.children).map(el => {
            const r=el.getBoundingClientRect();
            return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
          }) : [];
          const desktop=width>=1280;
          const horizontalOrder=children.length===3 && children[0].left<children[1].left && children[1].left<children[2].left;
          const verticalOrder=children.length===3 && children[0].bottom<=children[1].top+1 && children[1].bottom<=children[2].top+1;
          const withinMain=!!main && children.every(r => r.left>=main.getBoundingClientRect().left-1 && r.right<=main.getBoundingClientRect().right+1);
          const lastReachable=!!main && children.length===3 && children[2].bottom-main.getBoundingClientRect().top<=main.scrollHeight+1;
          return {desktop,children,horizontalOrder,verticalOrder,withinMain,lastReachable,mainScrollable:!!main&&main.scrollHeight>main.clientHeight+1};
        }
        """,
        width,
    )
    failures: list[str] = []
    for name, state in (("page1", page1), ("page2", page2)):
        if state["row_count"] != 14:
            failures.append(f"{name}_row_count")
        if state["clipped_row_count"] or state["clipped_text"] or state["clipped_tab_count"]:
            failures.append(f"{name}_clipped")
        if (state["core_body_overflow_x"] or 0) > 1 or (state["core_content_overflow_y"] or 0) > 1:
            failures.append(f"{name}_overflow")
    if layout["desktop"]:
        if not layout["horizontalOrder"] or not layout["withinMain"]:
            failures.append("desktop_three_column")
    elif not (layout["verticalOrder"] and layout["withinMain"] and layout["lastReachable"] and layout["mainScrollable"]):
        failures.append("mobile_single_column")
    return {"passed": not failures, "failures": failures, "page1": page1, "page2": page2, "layout": layout}


async def inspect_case(
    browser: Browser,
    base_url: str,
    engine: str,
    viewport: tuple[str, int, int],
    route: str,
    out_dir: Path,
) -> dict:
    viewport_name, width, height = viewport
    case_name = f"{engine}_{viewport_name}_{route}"
    page = await browser.new_page(viewport={"width": width, "height": height})
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    try:
        for attempt in range(3):
            try:
                await page.goto(with_route(base_url, route, case_name), wait_until="domcontentloaded", timeout=PAGE_READY_TIMEOUT_MS)
                await page.locator(".app").wait_for(state="visible", timeout=PAGE_READY_TIMEOUT_MS)
                await page.locator(ROUTE_SELECTORS[route]).wait_for(state="visible", timeout=PAGE_READY_TIMEOUT_MS)
                break
            except Exception as exc:
                transient = any(
                    marker in str(exc)
                    for marker in ("ERR_EMPTY_RESPONSE", "ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "Timeout")
                )
                if not transient or attempt == 2:
                    raise
                await page.wait_for_timeout(1_500 * (attempt + 1))
        await page.wait_for_timeout(300)
        general = await inspect_general(page, width, route)
        overview = await inspect_overview(page, width) if route == "overview" else None
        screenshot = out_dir / engine / f"{viewport_name}_{route}.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)
    finally:
        await page.close()

    filtered_page_errors = [item for item in page_errors if not any(phrase in item for phrase in EXPECTED_PAGE_ERRORS)]
    filtered_console = [item for item in console_errors if not any(phrase in item for phrase in EXPECTED_CONSOLE)]
    failures: list[str] = []
    if filtered_page_errors:
        failures.append("page_errors")
    if filtered_console:
        failures.append("console_errors")
    if general["document_overflow_x"] > 1 or (general["main_overflow_x"] or 0) > 1 or general["overflow_samples"]:
        failures.append("horizontal_overflow")
    if not (general["header_in_view"] and general["nav_in_view"] and general["main_above_nav"] and general["active_screen_inside_main"]):
        failures.append("shell_clip")
    if overview and not overview["passed"]:
        failures.extend(overview["failures"])
    return {
        "passed": not failures,
        "engine": engine,
        "viewport": {"name": viewport_name, "width": width, "height": height},
        "route": route,
        "url": with_route(base_url, route, case_name),
        "screenshot": str(screenshot),
        "failures": sorted(set(failures)),
        "page_errors": filtered_page_errors,
        "console_errors": filtered_console,
        "general": general,
        "overview": overview,
    }


async def run_engine(playwright, engine: str, base_url: str, out_dir: Path, matrix: str) -> list[dict]:
    if engine == "msedge":
        browser = await playwright.chromium.launch(headless=True, channel="msedge")
        viewports = EDGE_VIEWPORTS
    else:
        browser = await getattr(playwright, engine).launch(headless=True)
        if matrix == "edge":
            viewports = EDGE_VIEWPORTS
        elif matrix == "representative":
            viewports = REPRESENTATIVE_VIEWPORTS
        else:
            viewports = ALL_VIEWPORTS if engine == "chromium" else REPRESENTATIVE_VIEWPORTS
    try:
        results: list[dict] = []
        for viewport in viewports:
            for route in ROUTES:
                results.append(await inspect_case(browser, base_url, engine, viewport, route, out_dir))
                await asyncio.sleep(0.8)
        return results
    finally:
        await browser.close()


async def run(base_url: str, engines: list[str], out_dir: Path, matrix: str) -> list[dict]:
    async with async_playwright() as playwright:
        results: list[dict] = []
        for engine in engines:
            results.extend(await run_engine(playwright, engine, base_url, out_dir, matrix))
        return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the V3 overview adaptive layout and the required cross-browser viewport matrix.")
    parser.add_argument("--url", default="http://127.0.0.1:8093/?ws_port=8768#overview")
    parser.add_argument("--engines", default="chromium", help="Comma-separated: chromium,firefox,webkit,msedge")
    parser.add_argument("--matrix", choices=("all", "representative", "edge"), default="all")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "overview_adaptive_qa_20260716"))
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    engines = [item.strip() for item in args.engines.split(",") if item.strip()]
    invalid = sorted(set(engines) - {"chromium", "firefox", "webkit", "msedge"})
    if invalid:
        parser.error(f"unsupported engines: {', '.join(invalid)}")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {"url": args.url, "static": static_check(), "results": []}
    if not args.static_only:
        payload["results"] = asyncio.run(run(args.url, engines, out_dir, args.matrix))
    payload["checked"] = len(payload["results"])
    payload["failures"] = [item for item in payload["results"] if not item["passed"]]
    payload["passed"] = payload["static"]["passed"] and not payload["failures"]
    manifest = out_dir / ("manifest_static.json" if args.static_only else "manifest.json")
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "checked": payload["checked"], "failed": len(payload["failures"]), "manifest": str(manifest)}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
