from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]

VIEWPORTS: list[tuple[str, dict[str, int]]] = [
    ("desktop_1920x1080", {"width": 1920, "height": 1080}),
    ("laptop_1366x768", {"width": 1366, "height": 768}),
    ("tablet_1024x768", {"width": 1024, "height": 768}),
    ("portrait_768x1024", {"width": 768, "height": 1024}),
    ("mobile_390x844", {"width": 390, "height": 844}),
    ("short_1280x560", {"width": 1280, "height": 560}),
]

TABS = ["overview", "diagnosis", "optimization", "trend", "qa"]
IGNORED_PAGE_ERROR_PHRASES = ("Failed to fetch", 'URL scheme "file" is not supported')
IGNORED_FILE_CONSOLE_ERROR_PHRASES = (
    "has been blocked by CORS policy",
    "Failed to load resource: net::ERR_FAILED",
)


def default_file_url() -> str:
    return (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").resolve().as_uri()


def with_tab(url: str, tab: str, case_name: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    extra = f"responsive_case={case_name}"
    query = f"{query}&{extra}" if query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, tab))


async def inspect_page(browser, base_url: str, tab: str, viewport_name: str, viewport: dict[str, int], screenshot_dir: Path) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    page = await browser.new_page(viewport=viewport)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    case_name = f"{viewport_name}_{tab}"
    await page.goto(with_tab(base_url, tab, case_name), wait_until="domcontentloaded")
    await page.wait_for_selector(".app", timeout=30_000)
    await page.wait_for_timeout(1_500)

    result = await page.evaluate(
        """
        () => {
          const viewportW = window.innerWidth;
          const viewportH = window.innerHeight;
          const app = document.querySelector('.app');
          const header = document.querySelector('.topbar');
          const main = document.querySelector('.main');
          const nav = document.querySelector('.bottom-nav');
          const activeScreen = document.querySelector('.screen[style*="display: grid"], .screen:not([style*="display: none"])');
          const rect = (el) => {
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height};
          };
          const visible = (el) => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const tolerance = 8;
          const overflowSamples = Array.from(document.body.querySelectorAll('*'))
            .filter(el => {
              if (!visible(el)) return false;
              if (el.closest('.bottom-nav')) return false;
              if (el.closest('.echarts-tooltip')) return false;
              const r = el.getBoundingClientRect();
              return r.left < -tolerance || r.right > viewportW + tolerance;
            })
            .slice(0, 12)
            .map(el => {
              const r = el.getBoundingClientRect();
              return {
                tag: el.tagName.toLowerCase(),
                className: String(el.className || '').slice(0, 120),
                text: String(el.textContent || '').trim().slice(0, 80),
                left: Math.round(r.left * 10) / 10,
                right: Math.round(r.right * 10) / 10,
                width: Math.round(r.width * 10) / 10
              };
            });
          const baseRowOverflowCount = Array.from(document.querySelectorAll('.base-row')).filter(row => {
            if (!visible(row)) return false;
            const rowRect = row.getBoundingClientRect();
            return Array.from(row.children).some(child => visible(child) && child.getBoundingClientRect().right > rowRect.right + 2);
          }).length;
          return {
            viewport: {width: viewportW, height: viewportH},
            app: rect(app),
            header: rect(header),
            main: rect(main),
            nav: rect(nav),
            active_screen: rect(activeScreen),
            body_scroll_width: document.documentElement.scrollWidth,
            body_client_width: document.documentElement.clientWidth,
            main_scroll_width: main ? main.scrollWidth : null,
            main_client_width: main ? main.clientWidth : null,
            app_fits_height: app ? app.getBoundingClientRect().height <= viewportH + 1 : false,
            nav_in_view: nav ? nav.getBoundingClientRect().bottom <= viewportH + 1 && nav.getBoundingClientRect().top >= -1 : false,
            header_in_view: header ? header.getBoundingClientRect().top >= -1 && header.getBoundingClientRect().bottom <= viewportH + 1 : false,
            main_above_nav: main && nav ? main.getBoundingClientRect().bottom <= nav.getBoundingClientRect().top + 1 : false,
            visible_horizontal_overflow_count: overflowSamples.length,
            visible_horizontal_overflow_samples: overflowSamples,
            base_row_overflow_count: baseRowOverflowCount,
          };
        }
        """
    )

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / f"{case_name}.png"
    await page.screenshot(path=str(screenshot_path), full_page=False)
    await page.close()

    ignored_console_phrases = list(IGNORED_PAGE_ERROR_PHRASES)
    if urlsplit(base_url).scheme == "file":
        ignored_console_phrases.extend(IGNORED_FILE_CONSOLE_ERROR_PHRASES)
    page_errors = [e for e in page_errors if not any(phrase in e for phrase in IGNORED_PAGE_ERROR_PHRASES)]
    console_errors = [e for e in console_errors if not any(phrase in e for phrase in ignored_console_phrases)]
    result.update(
        {
            "tab": tab,
            "viewport_name": viewport_name,
            "screenshot": str(screenshot_path),
            "page_errors": page_errors,
            "console_errors": console_errors,
        }
    )
    return result


async def run_checks(base_url: str, screenshot_dir: Path, tabs: list[str], viewports: list[tuple[str, dict[str, int]]]) -> list[dict]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            results = []
            for viewport_name, viewport in viewports:
                for tab in tabs:
                    results.append(await inspect_page(browser, base_url, tab, viewport_name, viewport, screenshot_dir))
            return results
        finally:
            await browser.close()


def has_failure(item: dict) -> bool:
    main_overflow = 0
    if item["main_scroll_width"] is not None and item["main_client_width"] is not None:
        main_overflow = item["main_scroll_width"] - item["main_client_width"]
    return any(
        [
            item["page_errors"],
            item["console_errors"],
            not item["app_fits_height"],
            not item["header_in_view"],
            not item["nav_in_view"],
            not item["main_above_nav"],
            main_overflow > 12,
            item["visible_horizontal_overflow_count"] > 0,
            item["base_row_overflow_count"] > 0,
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify V3 frontend responsive layout across main tabs and screen sizes.")
    parser.add_argument("--url", default=default_file_url(), help="Base frontend URL or file URL.")
    parser.add_argument("--screenshot-dir", default=str(ROOT / "logs" / "responsive_layout"), help="Directory for viewport screenshots.")
    parser.add_argument("--tabs", default=",".join(TABS), help="Comma-separated tab hashes to check.")
    args = parser.parse_args()

    tabs = [item.strip().lstrip("#") for item in args.tabs.split(",") if item.strip()]
    results = asyncio.run(run_checks(args.url, Path(args.screenshot_dir), tabs, VIEWPORTS))
    failures = [item for item in results if has_failure(item)]
    summary = {
        "url": args.url,
        "checked": len(results),
        "failed": len(failures),
        "failures": failures,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
