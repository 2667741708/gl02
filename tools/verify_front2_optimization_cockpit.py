from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://127.0.0.1:8094/?ws_port=8767#optimization"
ALL_VIEWPORTS = [
    (1280, 720), (1366, 768), (1440, 900), (1546, 864), (1920, 1080),
    (1024, 768), (768, 1024), (390, 844), (375, 667),
]
REPRESENTATIVE_VIEWPORTS = [(1920, 1080), (1366, 768), (768, 1024), (390, 844)]


async def inspect(page, url: str, out_file: Path) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        # Some remote reverse proxies keep the response stream open after the
        # document has committed. Continue only if the rendered cockpit itself
        # becomes available below; this does not hide a missing page.
        await page.goto(url, wait_until="commit", timeout=15_000)
    await page.wait_for_selector(".optimization-cockpit", timeout=30_000)
    result = await page.evaluate(
        """
        () => {
          const root = document.querySelector('.optimization-cockpit');
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const rect = el => { const r = el.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; };
          const viewportW = window.innerWidth;
          const overflow = Array.from(root.querySelectorAll('*')).filter(el => {
            if (!visible(el)) return false;
            const r = el.getBoundingClientRect();
            return r.left < -2 || r.right > viewportW + 2;
          }).slice(0, 8).map(el => ({className:String(el.className || ''), text:String(el.textContent || '').trim().slice(0, 50), ...rect(el)}));
          return {
            cockpit: !!root,
            formal_header: !!document.querySelector('.topbar.branded-topbar'),
            left_state: !!document.querySelector('.opt-state-column'),
            decision: !!document.querySelector('.cockpit-decision'),
            monitor: !!document.querySelector('.cockpit-metric-table'),
            risk: !!document.querySelector('.cockpit-risk-list'),
            candidate_count: document.querySelectorAll('.cockpit-candidate').length,
            document_width: document.documentElement.scrollWidth,
            viewport_width: viewportW,
            shell: ['.app', '.main', '.screen', '.optimization-cockpit'].map(selector => {
              const el = document.querySelector(selector), style = el && getComputedStyle(el), r = el && el.getBoundingClientRect();
              return {selector, width:r?.width, minWidth:style?.minWidth, display:style?.display};
            }),
            overflow,
            waiting_state: document.body.innerText.includes('等待实时数据'),
          };
        }
        """
    )
    candidates = page.locator(".cockpit-candidate")
    candidate_count = await candidates.count()
    if candidate_count > 1:
        second = candidates.nth(1)
        await second.click()
        result["candidate_selection"] = await second.get_attribute("aria-pressed")
    else:
        result["candidate_selection"] = None
    await page.screenshot(path=str(out_file), full_page=False)
    result["page_errors"] = page_errors
    result["console_errors"] = [
        text for text in console_errors
        if "WebSocket connection" not in text and "Failed to fetch" not in text
    ]
    return result


async def main_async(args: argparse.Namespace) -> dict:
    viewports = ALL_VIEWPORTS if args.matrix == "all" else REPRESENTATIVE_VIEWPORTS
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    async with async_playwright() as playwright:
        browser_type = getattr(playwright, args.browser)
        browser = await browser_type.launch(headless=True)
        for width, height in viewports:
            page = await browser.new_page(viewport={"width": width, "height": height})
            file = output / f"optimization_{args.browser}_{width}x{height}.png"
            result = await inspect(page, args.url, file)
            failures = []
            for key in ("cockpit", "formal_header", "left_state", "decision", "monitor", "risk"):
                if not result[key]:
                    failures.append(key)
            if result["candidate_count"] < 1:
                failures.append("candidate_missing")
            if result["candidate_count"] > 1 and result["candidate_selection"] != "true":
                failures.append("candidate_selection")
            if result["document_width"] > result["viewport_width"] + 1 or result["overflow"]:
                failures.append("horizontal_overflow")
            if result["page_errors"] or result["console_errors"]:
                failures.append("page_or_console_errors")
            rows.append({"browser": args.browser, "viewport": f"{width}x{height}", "url": args.url, "waiting_state": result["waiting_state"], "screenshot": str(file), "failures": failures, "result": result})
            await page.close()
        await browser.close()
    return {"browser": args.browser, "matrix": args.matrix, "passed": not any(row["failures"] for row in rows), "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify front2 parameter optimization cockpit layout.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    parser.add_argument("--matrix", choices=("all", "representative"), default="all")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "front2_optimization_cockpit_qa"))
    args = parser.parse_args()
    payload = asyncio.run(main_async(args))
    out = Path(args.out_dir).resolve() / f"manifest_{args.browser}_{args.matrix}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "manifest": str(out), "rows": len(payload["rows"])}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
