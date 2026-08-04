"""Verify 8092 panel titles no longer render the cyan prefix icon.

对应需求：
- REQ-20260607-PANEL-TITLE-PREFIX-REMOVE：移除各页面面板标题前反复出现的装饰图标。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
DEFAULT_URL = "http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767"
DEFAULT_TABS = ["overview", "diagnosis", "optimization", "trend", "qa"]
REQUIRE_TITLE_TABS = {"overview", "diagnosis", "optimization", "trend"}
IGNORED_ERROR_PHRASES = ("Failed to fetch", 'URL scheme "file" is not supported')


def with_tab(url: str, tab: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    cache_bust = "cache_bust=panel_title_prefix_removed"
    query = f"{query}&{cache_bust}" if query else cache_bust
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, tab))


def verify_static() -> dict:
    text = HTML.read_text(encoding="utf-8")
    tokens = {
        "style_id": "v4-panel-title-prefix-remove" in text,
        "final_style_id": "v4-panel-title-prefix-final-remove" in text,
        "policy": "__BF_PANEL_TITLE_PREFIX_POLICY" in text,
        "content_none": ".panel-title:before,.panel-title::before{content:none!important" in text,
        "panel_chrome_none": ".panel:before,.panel::before,.panel:after,.panel::after{content:none!important" in text,
        "panel_head_chrome_none": ".panel-head:before,.panel-head::before,.panel-head:after,.panel-head::after" in text,
    }
    return tokens


async def inspect_tab(browser, base_url: str, tab: str, screenshot_dir: Path, timeout_ms: int) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    page = await browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    await page.goto(with_tab(base_url, tab), wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_selector(".app", timeout=timeout_ms)
    await page.wait_for_timeout(1200)

    result = await page.evaluate(
        """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return rect.width > 1 && rect.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
          };
          const titles = Array.from(document.querySelectorAll('.panel-title')).filter(visible);
          const heads = Array.from(document.querySelectorAll('.panel-head')).filter(visible);
          const panels = Array.from(document.querySelectorAll('.panel')).filter(visible);
          const samples = titles.slice(0, 12).map((el) => {
            const before = getComputedStyle(el, '::before');
            const rect = el.getBoundingClientRect();
            return {
              text: String(el.textContent || '').trim(),
              content: before.content,
              display: before.display,
              width: before.width,
              height: before.height,
              marginRight: before.marginRight,
              left: Math.round(rect.left * 10) / 10,
              top: Math.round(rect.top * 10) / 10
            };
          });
          const pseudoVisible = (style) => {
            const content = String(style.content || '').toLowerCase();
            const display = String(style.display || '').toLowerCase();
            if (content === 'none' || content === 'normal' || display === 'none') return false;
            const width = Number.parseFloat(style.width || '0') || 0;
            const height = Number.parseFloat(style.height || '0') || 0;
            const background = `${style.backgroundImage || ''} ${style.backgroundColor || ''}`.toLowerCase();
            const hasPaint = background.includes('gradient') ||
              (!background.includes('rgba(0, 0, 0, 0)') && !background.includes('transparent') && background.trim() !== 'none') ||
              (style.boxShadow && style.boxShadow !== 'none');
            return (width > 0.5 || height > 0.5 || hasPaint) && (content !== '""' || hasPaint || width > 0.5 || height > 0.5);
          };
          const hasVisiblePrefix = (el) => pseudoVisible(getComputedStyle(el, '::before'));
          const panelSamples = panels.slice(0, 12).map((el) => {
            const before = getComputedStyle(el, '::before');
            const after = getComputedStyle(el, '::after');
            const rect = el.getBoundingClientRect();
            return {
              text: String(el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80),
              beforeContent: before.content,
              beforeDisplay: before.display,
              beforeWidth: before.width,
              beforeHeight: before.height,
              beforeBackground: String(before.backgroundImage || before.backgroundColor || '').slice(0, 120),
              afterContent: after.content,
              afterDisplay: after.display,
              afterWidth: after.width,
              afterHeight: after.height,
              afterBackground: String(after.backgroundImage || after.backgroundColor || '').slice(0, 120),
              left: Math.round(rect.left * 10) / 10,
              top: Math.round(rect.top * 10) / 10
            };
          });
          const headSamples = heads.slice(0, 12).map((el) => {
            const before = getComputedStyle(el, '::before');
            const after = getComputedStyle(el, '::after');
            const rect = el.getBoundingClientRect();
            return {
              text: String(el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80),
              beforeContent: before.content,
              beforeDisplay: before.display,
              beforeWidth: before.width,
              beforeHeight: before.height,
              beforeBackground: String(before.backgroundImage || before.backgroundColor || '').slice(0, 120),
              afterContent: after.content,
              afterDisplay: after.display,
              afterWidth: after.width,
              afterHeight: after.height,
              afterBackground: String(after.backgroundImage || after.backgroundColor || '').slice(0, 120),
              left: Math.round(rect.left * 10) / 10,
              top: Math.round(rect.top * 10) / 10
            };
          });
          const panelChromeCount = panels.filter((el) =>
            pseudoVisible(getComputedStyle(el, '::before')) || pseudoVisible(getComputedStyle(el, '::after'))
          ).length;
          const headChromeCount = heads.filter((el) =>
            pseudoVisible(getComputedStyle(el, '::before')) || pseudoVisible(getComputedStyle(el, '::after'))
          ).length;
          return {
            stylePresent: !!document.getElementById('v4-panel-title-prefix-remove'),
            finalStylePresent: !!document.getElementById('v4-panel-title-prefix-final-remove'),
            policy: window.__BF_PANEL_TITLE_PREFIX_POLICY || null,
            titleCount: titles.length,
            headCount: heads.length,
            panelCount: panels.length,
            remainingPrefixCount: titles.filter(hasVisiblePrefix).length,
            remainingPanelChromeCount: panelChromeCount,
            remainingPanelHeadChromeCount: headChromeCount,
            samples,
            panelSamples,
            headSamples,
            horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
          };
        }
        """
    )

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshot_dir / f"{tab}_no_panel_prefix.png"
    await page.screenshot(path=str(screenshot), full_page=False)
    await page.close()

    result.update(
        {
            "tab": tab,
            "screenshot": str(screenshot),
            "page_errors": [e for e in page_errors if not any(p in e for p in IGNORED_ERROR_PHRASES)],
            "console_errors": [e for e in console_errors if not any(p in e for p in IGNORED_ERROR_PHRASES)],
        }
    )
    return result


async def verify_browser(base_url: str, tabs: list[str], screenshot_dir: Path, timeout_ms: int) -> list[dict]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        results = []
        for tab in tabs:
            results.append(await inspect_tab(browser, base_url, tab, screenshot_dir, timeout_ms))
        await browser.close()
        return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify panel-title prefix icons are removed across 8092 tabs.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--tabs", nargs="*", default=DEFAULT_TABS)
    parser.add_argument("--screenshot-dir", default=str(ROOT / "logs" / "panel_title_icon_remove"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    args = parser.parse_args()

    result = {
        "static": verify_static(),
        "browser": asyncio.run(
            verify_browser(args.url, args.tabs, Path(args.screenshot_dir), args.timeout_ms)
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failures: list[str] = []
    if not all(result["static"].values()):
        failures.append("missing_static_tokens")
    for item in result["browser"]:
        if item["page_errors"] or item["console_errors"]:
            failures.append(f"{item['tab']}:page_or_console_errors")
        if item["tab"] in REQUIRE_TITLE_TABS and item["titleCount"] < 1:
            failures.append(f"{item['tab']}:no_visible_panel_titles")
        if item["remainingPrefixCount"] != 0:
            failures.append(f"{item['tab']}:prefix_still_visible")
        if item["remainingPanelChromeCount"] != 0:
            failures.append(f"{item['tab']}:panel_chrome_still_visible")
        if item.get("remainingPanelHeadChromeCount", 0) != 0:
            failures.append(f"{item['tab']}:panel_head_chrome_still_visible")
        if item["policy"] not in {"panel-title-no-prefix-icon-v1", "panel-title-no-prefix-icon-v2"}:
            failures.append(f"{item['tab']}:runtime_policy_missing")
        if not item["stylePresent"] or not item.get("finalStylePresent"):
            failures.append(f"{item['tab']}:runtime_policy_missing")
        if item["horizontalOverflow"] > 8:
            failures.append(f"{item['tab']}:horizontal_overflow")
    if failures:
        print(json.dumps({"failed": failures}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
