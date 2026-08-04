"""Render the optimization workbench against live 8093/8768 data without deployment.

REQ-OPT-20260710-WORKBENCH.  The browser intercepts the 8093 HTML document
and appends the local workbench override in memory before the page's existing
render call.  No remote file, service, database record, or WebSocket payload
is changed.  This validates the workbench against the actual bridge payload
under the bridge's accepted same-origin policy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import Route, async_playwright


ROOT = Path(__file__).resolve().parents[1]
LOCAL_HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
START_MARKER = "/* REQ-OPT-20260710-WORKBENCH: parameters-optimization operational workbench */"
RENDER_MARKER = "window.__BF_RENDER_APP__&&window.__BF_RENDER_APP__();"
DEFAULT_URL = "http://10.30.220.12:8093/?ws_port=8768#optimization"


def local_override() -> str:
    """Extract the tested workbench override from the local frontend source."""
    source = LOCAL_HTML.read_text(encoding="utf-8")
    start = source.index(START_MARKER)
    end = source.index(RENDER_MARKER, start)
    return source[start:end]


async def run_overlay(url: str, screenshot: Path) -> dict:
    """Load remote 8093 with the local workbench override only in browser memory."""
    override = local_override()
    page_errors: list[str] = []
    console_errors: list[str] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-web-security",
                "--disable-features=BlockInsecurePrivateNetworkRequests",
            ],
        )
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        async def inject_workbench(route: Route) -> None:
            request = route.request
            if not request.is_navigation_request():
                await route.continue_()
                return
            response = await route.fetch()
            body = await response.text()
            if RENDER_MARKER not in body:
                await route.fulfill(response=response)
                return
            headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() != "content-length"
            }
            headers["cache-control"] = "no-store"
            await route.fulfill(
                response=response,
                body=body.replace(RENDER_MARKER, f"{override}\n{RENDER_MARKER}", 1),
                headers=headers,
            )

        await page.route("**/*", inject_workbench)
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_selector(".optimization-workbench-v10", timeout=45_000)
        except Exception as exc:
            debug = await page.evaluate(
                """() => ({
                  marker_present: document.documentElement.innerHTML.includes('REQ-OPT-20260710-WORKBENCH'),
                  root_text: (document.querySelector('#root')?.textContent || '').slice(0, 240),
                  rendered_optimization: !!document.querySelector('.optimization-screen'),
                })"""
            )
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot), full_page=False)
            await browser.close()
            return {"overlay_error": str(exc), "debug": debug, "page_errors": page_errors, "console_errors": console_errors}
        await page.wait_for_function(
            """() => {
                const state = document.querySelector('.workbench-state-title');
                const variables = Array.from(document.querySelectorAll('.workbench-variable-row b'));
                return state && state.textContent.trim() !== '等待实时数据' &&
                  variables.some(node => !['--', '0.0', '0.00'].includes(node.textContent.trim()));
            }""",
            timeout=45_000,
        )

        result = await page.evaluate(
            """() => {
                const visible = el => {
                  const rect = el.getBoundingClientRect();
                  const style = getComputedStyle(el);
                  return rect.width > 1 && rect.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
                };
                const cards = Array.from(document.querySelectorAll('.workbench-action-card')).filter(visible);
                const variables = Array.from(document.querySelectorAll('.workbench-variable-row')).filter(visible);
                const overflow = Array.from(document.querySelectorAll('.optimization-workbench-v10 *')).filter(el => {
                  if (!visible(el)) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.left < -8 || rect.right > window.innerWidth + 8;
                }).length;
                return {
                  state: document.querySelector('.workbench-state-title')?.textContent.trim() || '',
                  diagnosis: document.querySelector('.workbench-hero-top span:nth-child(2)')?.textContent.trim() || '',
                  variable_count: variables.length,
                  variable_values: variables.map(row => row.querySelector('b')?.textContent.trim() || ''),
                  action_count: cards.length,
                  selected_before: cards[0]?.getAttribute('aria-pressed') || null,
                  horizontal_overflow_count: overflow,
                };
            }"""
        )
        cards = page.locator(".workbench-action-card")
        if await cards.count() > 1:
            await cards.nth(1).click()
            result["selected_after"] = await cards.nth(1).get_attribute("aria-pressed")
        else:
            result["selected_after"] = None

        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)
        await browser.close()

    result["page_errors"] = page_errors
    result["console_errors"] = console_errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="In-memory 8093 workbench compatibility verification.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--screenshot", default=str(ROOT / "logs" / "optimization_workbench_remote_8093_live.png"))
    parser.add_argument("--out", default=str(ROOT / "logs" / "optimization_workbench_remote_8093_live.json"))
    args = parser.parse_args()

    result = asyncio.run(run_overlay(args.url, Path(args.screenshot)))
    failures: list[str] = []
    if result.get("overlay_error"):
        failures.append("overlay_not_rendered")
    else:
        if result["state"] == "等待实时数据":
            failures.append("live_data_not_rendered")
        if result["variable_count"] < 5:
            failures.append("variable_rows_missing")
        if result["action_count"] < 3:
            failures.append("action_cards_missing")
        if result["selected_after"] != "true":
            failures.append("action_selection_not_working")
        if result["horizontal_overflow_count"]:
            failures.append("horizontal_overflow")
    if result["page_errors"] or result["console_errors"]:
        failures.append("browser_errors")

    payload = {"ok": not failures, "failures": failures, "result": result}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
