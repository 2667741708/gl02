from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]


def default_file_url() -> str:
    return (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").resolve().as_uri()


def with_optimization_hash(url: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    extra = "optimization_polish_case=1"
    query = f"{query}&{extra}" if query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, "optimization"))


async def inspect_layout(url: str, screenshot_path: Path, viewport: dict[str, int], browser_engine: str = "chromium") -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    async with async_playwright() as playwright:
        browser_type = getattr(playwright, browser_engine)
        browser = await browser_type.launch(headless=True)
        page = await browser.new_page(viewport=viewport)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(with_optimization_hash(url), wait_until="domcontentloaded")
        await page.wait_for_selector(".optimization-workbench-v10", timeout=30_000)
        await page.wait_for_timeout(2_000)
        result = await page.evaluate(
            """
            () => {
              const viewportW = window.innerWidth;
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden';
              };
              const rect = el => {
                const r = el.getBoundingClientRect();
                return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
              };
              const overflowSamples = Array.from(document.querySelectorAll('.optimization-workbench-v10 *'))
                .filter(el => {
                  if (!visible(el)) return false;
                  const r = el.getBoundingClientRect();
                  return r.left < -8 || r.right > viewportW + 8;
                })
                .slice(0, 12)
                .map(el => ({tag: el.tagName.toLowerCase(), className: String(el.className || '').slice(0, 90), text: String(el.textContent || '').trim().slice(0, 70), ...rect(el)}));
              const important = Array.from(document.querySelectorAll('.optimization-workbench-v10 .workbench-state,.optimization-workbench-v10 .workbench-route,.optimization-workbench-v10 .workbench-variable-row,.optimization-workbench-v10 .workbench-risk-list,.optimization-workbench-v10 .workbench-action-card'));
              const clippedHidden = important.filter(el => {
                const s = getComputedStyle(el);
                return s.overflowY === 'hidden' && el.scrollHeight > el.clientHeight + 4;
              }).map(el => ({className: String(el.className || ''), text: String(el.textContent || '').trim().slice(0, 80), scrollHeight: el.scrollHeight, clientHeight: el.clientHeight}));
              const selectedDetailClipped = Array.from(document.querySelectorAll('.optimization-workbench-v10 .workbench-selected-grid > div'))
                .filter(el => el.scrollHeight > el.clientHeight + 2)
                .map(el => ({text: String(el.textContent || '').trim().slice(0, 100), scrollHeight: el.scrollHeight, clientHeight: el.clientHeight}));
              const fontNodes = Array.from(document.querySelectorAll('.optimization-workbench-v10 .workbench-state,.optimization-workbench-v10 .workbench-route,.optimization-workbench-v10 .workbench-signal,.optimization-workbench-v10 .workbench-variable-row,.optimization-workbench-v10 .workbench-risk-list,.optimization-workbench-v10 .workbench-action-card')).filter(visible);
              const fontSizes = fontNodes.map(el => Number.parseFloat(getComputedStyle(el).fontSize)).filter(Number.isFinite);
              const focusRows = Array.from(document.querySelectorAll('.optimization-workbench-v10 .workbench-variable-row')).filter(visible).length;
              const actionBodies = Array.from(document.querySelectorAll('.optimization-workbench-v10 .workbench-action-card')).filter(visible);
              const screen = document.querySelector('.optimization-workbench-v10');
              const fontSize = selector => {
                const node = document.querySelector(selector);
                return node ? Number.parseFloat(getComputedStyle(node).fontSize) : null;
              };
              return {
                screen_exists: !!screen,
                screen_rect: screen ? rect(screen) : null,
                viewport_document_width: document.documentElement.scrollWidth,
                app_min_width: getComputedStyle(document.querySelector('.app')).minWidth,
                app_width: getComputedStyle(document.querySelector('.app')).width,
                main_min_width: getComputedStyle(document.querySelector('.main')).minWidth,
                main_width: getComputedStyle(document.querySelector('.main')).width,
                main_tag: document.querySelector('.main')?.tagName || null,
                main_class: document.querySelector('.main')?.className || null,
                main_inline_style: document.querySelector('.main')?.getAttribute('style') || null,
                main_width_rules: Array.from(document.styleSheets).flatMap(sheet => {
                  try { return Array.from(sheet.cssRules || []).flatMap(rule => rule.cssRules ? Array.from(rule.cssRules) : [rule]); }
                  catch (_) { return []; }
                }).filter(rule => rule.selectorText && rule.style?.width && (() => { try { return document.querySelector('.main').matches(rule.selectorText); } catch (_) { return false; } })()).map(rule => ({selector:rule.selectorText,width:rule.style.width,priority:rule.style.getPropertyPriority('width')})),
                screen_min_width: screen ? getComputedStyle(screen).minWidth : null,
                screen_grid_columns: screen ? getComputedStyle(screen).gridTemplateColumns : null,
                visible_horizontal_overflow_count: overflowSamples.length,
                visible_horizontal_overflow_samples: overflowSamples,
                clipped_hidden_count: clippedHidden.length,
                clipped_hidden_samples: clippedHidden,
                selected_detail_clipped_count: selectedDetailClipped.length,
                selected_detail_clipped_samples: selectedDetailClipped,
                focus_row_count: focusRows,
                action_body_count: actionBodies.length,
                font_min: fontSizes.length ? Math.min(...fontSizes) : null,
                font_max: fontSizes.length ? Math.max(...fontSizes) : null,
                font_spread: fontSizes.length ? Math.max(...fontSizes) - Math.min(...fontSizes) : null,
                has_polish_style: !!document.getElementById('v3-optimization-workbench-v10-style'),
                has_typography_style: !!document.getElementById('v3-optimization-typography-v2'),
                typography: {
                  state_title: fontSize('.workbench-state-title'),
                  hero_title: fontSize('.workbench-hero h2'),
                  route_description: fontSize('.workbench-route div > span'),
                  variable_row: fontSize('.workbench-variable-row'),
                  action_title: fontSize('.workbench-action-title b'),
                  action_body: fontSize('.workbench-action-card p'),
                },
              };
            }
            """
        )
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=False)
        cards = page.locator(".optimization-workbench-v10 .workbench-action-card")
        selected_before = await cards.nth(0).get_attribute("aria-pressed")
        if await cards.count() > 1:
            await cards.nth(1).click()
            selected_after = await cards.nth(1).get_attribute("aria-pressed")
        else:
            selected_after = None
        result["action_selection_before"] = selected_before
        result["action_selection_after"] = selected_after
        await page.get_by_role("button", name="查看趋势").click()
        await page.wait_for_selector(".trend-grid", timeout=30_000)
        result["trend_route_reachable"] = await page.evaluate("() => window.location.hash === '#trend'")
        await browser.close()
    result["page_errors"] = page_errors
    result["console_errors"] = [
        e
        for e in console_errors
        if "Failed to fetch" not in e
        and 'URL scheme "file"' not in e
        and "WebSocket connection" not in e
    ]
    result["screenshot"] = str(screenshot_path)
    result["viewport"] = viewport
    result["browser_engine"] = browser_engine
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the optimization page typography and layout polish.")
    parser.add_argument("--url", default=default_file_url(), help="Base frontend URL or file URL.")
    parser.add_argument("--screenshot", default=str(ROOT / "logs" / "optimization_layout_polish.png"))
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()

    result = asyncio.run(inspect_layout(args.url, Path(args.screenshot), {"width": args.width, "height": args.height}, args.browser))
    failures = []
    if result["page_errors"] or result["console_errors"]:
        failures.append("page_or_console_errors")
    if not result["screen_exists"] or not result["has_polish_style"]:
        failures.append("optimization_screen_or_style_missing")
    if not result.get("has_typography_style"):
        failures.append("typography_style_missing")
    if result["visible_horizontal_overflow_count"]:
        failures.append("horizontal_overflow")
    if result["clipped_hidden_count"]:
        failures.append("hidden_clipping")
    if result.get("selected_detail_clipped_count"):
        failures.append("selected_detail_clipping")
    if result["focus_row_count"] < 5:
        failures.append("focus_rows_missing")
    if result["action_body_count"] < 5:
        failures.append("action_cards_missing")
    if result.get("action_selection_after") != "true":
        failures.append("action_selection_not_working")
    if result.get("trend_route_reachable") is not True:
        failures.append("trend_route_not_reachable")
    if result["font_spread"] is None or result["font_spread"] > 7:
        failures.append("font_spread_too_large")
    typography = result.get("typography") or {}
    minimum_sizes = {
        "state_title": 24,
        "hero_title": 23,
        "route_description": 13,
        "variable_row": 13,
        "action_title": 15,
        "action_body": 13,
    } if args.width <= 600 else {
        "state_title": 25,
        "hero_title": 25,
        "route_description": 13,
        "variable_row": 13,
        "action_title": 14,
        "action_body": 12,
    }
    if any(typography.get(name) is None or typography[name] < minimum for name, minimum in minimum_sizes.items()):
        failures.append("typography_too_small")

    payload = {"failed": len(failures), "failures": failures, "result": result}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
