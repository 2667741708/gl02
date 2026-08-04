from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def static_tokens() -> dict:
    text = HTML.read_text(encoding="utf-8")
    required = [
        "v4-diagnosis-foreman-polish",
        "BFDiagnosisForemanTab",
        "DIAG_FOREMAN_VARIABLE_IDS",
        "诊断证据清单",
        "点击进入变量关联",
        "VariableInsightDrawer",
    ]
    return {
        "required": {token: token in text for token in required},
        "forbidden_static_debug": any(token in text for token in ["raw_scores：", "pSpace 调试", "生产账号"]),
    }


async def verify_browser(url: str, screenshot_dir: Path, timeout_ms: int) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_selector(".foreman-diagnosis", timeout=timeout_ms)
        await page.wait_for_timeout(3000)
        desktop_shot = screenshot_dir / "diagnosis_foreman_polish_1440.png"
        await page.screenshot(path=str(desktop_shot), full_page=False)
        initial = await page.evaluate(
            """
            () => {
              const rect = el => {
                const r = el.getBoundingClientRect();
                return { top: r.top, bottom: r.bottom, width: r.width, height: r.height };
              };
              const nav = document.querySelector('.bottom-nav');
              const bottom = document.querySelector('.diag-analysis-band');
              const text = document.querySelector('.foreman-diagnosis')?.innerText || '';
              return {
                title: document.title,
                foreman_found: !!document.querySelector('.foreman-diagnosis'),
                panel_titles: Array.from(document.querySelectorAll('.foreman-diagnosis .panel-title')).map(x => x.textContent.trim()),
                variable_buttons: document.querySelectorAll('.diag-var-button').length,
                score_buttons: document.querySelectorAll('.diag-rank-button').length,
                evidence_buttons: document.querySelectorAll('.diag-rule-action').length,
                body_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                bottom_above_nav: bottom && nav ? rect(bottom).bottom <= rect(nav).top + 1 : false,
                forbidden_debug: /raw_scores|pSpace|GL02|生产账号|调试字段/.test(text),
                readonly_copy: text.includes('只读研判') && text.includes('不写入生产控制'),
              };
            }
            """
        )
        await page.locator(".diag-var-button").first.click()
        await page.wait_for_timeout(700)
        drawer_one = await page.evaluate(
            """
            () => ({
              drawer: !!document.querySelector('.var-insight-drawer'),
              title: document.querySelector('.var-drawer-head h3')?.textContent?.trim() || '',
              related_count: document.querySelectorAll('.var-related').length,
              qa_button: Array.from(document.querySelectorAll('button')).some(b => /带上下文追问/.test(b.textContent || '')),
              close_label: document.querySelector('.var-close')?.getAttribute('aria-label') || '',
            })
            """
        )
        drawer_shot = screenshot_dir / "diagnosis_foreman_drawer_1440.png"
        await page.screenshot(path=str(drawer_shot), full_page=False)
        await page.locator(".var-close").click()
        await page.wait_for_timeout(300)
        await page.locator(".diag-rank-button").first.click()
        await page.wait_for_timeout(500)
        drawer_two = await page.evaluate(
            """
            () => ({
              drawer: !!document.querySelector('.var-insight-drawer'),
              title: document.querySelector('.var-drawer-head h3')?.textContent?.trim() || '',
            })
            """
        )
        await page.locator(".var-close").click()
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(800)
        mobile_shot = screenshot_dir / "diagnosis_foreman_polish_mobile.png"
        await page.screenshot(path=str(mobile_shot), full_page=False)
        mobile = await page.evaluate(
            """
            () => ({
              overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
              variable_buttons: document.querySelectorAll('.diag-var-button').length,
              visible_title: document.body.innerText.includes('炉况诊断'),
            })
            """
        )
        await browser.close()
    return {
        "initial": initial,
        "drawer_variable": drawer_one,
        "drawer_score": drawer_two,
        "mobile": mobile,
        "screenshots": {
            "desktop": str(desktop_shot),
            "drawer": str(drawer_shot),
            "mobile": str(mobile_shot),
        },
        "page_errors": page_errors,
        "console_errors": console_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 8092 diagnosis foreman page polish and variable insight interactions.")
    parser.add_argument("--url", default="http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767#diagnosis")
    parser.add_argument("--screenshot-dir", default=str(ROOT / "logs" / "diagnosis_page_iteration"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    args = parser.parse_args()

    result = {
        "static": static_tokens(),
        "browser": asyncio.run(verify_browser(args.url, Path(args.screenshot_dir), args.timeout_ms)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failures: list[str] = []
    if not all(result["static"]["required"].values()):
        failures.append("missing_static_tokens")
    if result["static"]["forbidden_static_debug"]:
        failures.append("forbidden_static_debug")
    browser = result["browser"]
    if browser["page_errors"] or browser["console_errors"]:
        failures.append("page_or_console_errors")
    initial = browser["initial"]
    if not initial["foreman_found"]:
        failures.append("foreman_layout_missing")
    if initial["variable_buttons"] < 10 or initial["score_buttons"] != 8 or initial["evidence_buttons"] < 3:
        failures.append("clickable_entry_count_wrong")
    if initial["body_overflow"] != 0 or not initial["bottom_above_nav"]:
        failures.append("layout_overflow_or_nav_overlap")
    if initial["forbidden_debug"] or not initial["readonly_copy"]:
        failures.append("copy_or_debug_contract_failed")
    drawer_one = browser["drawer_variable"]
    if not drawer_one["drawer"] or not drawer_one["title"] or drawer_one["related_count"] < 2 or not drawer_one["qa_button"]:
        failures.append("variable_drawer_failed")
    drawer_two = browser["drawer_score"]
    if not drawer_two["drawer"] or not drawer_two["title"]:
        failures.append("score_drawer_failed")
    if browser["mobile"]["overflow"] != 0 or browser["mobile"]["variable_buttons"] < 10:
        failures.append("mobile_layout_failed")
    if failures:
        print(json.dumps({"failed": failures}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
