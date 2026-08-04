"""验证8093参数优化页的决策依据展示与版本注释移除。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def verify(url: str, screenshot: Path, width: int, height: int) -> dict:
    page_errors: list[str] = []
    console_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector('.bf-engine-cockpit[data-recommendation-state="ready"]', timeout=45_000)
        await page.wait_for_timeout(2_000)
        result = await page.evaluate(
            """
            () => {
              const root = document.querySelector('.bf-engine-cockpit');
              const basis = root?.querySelector('.bf-decision-basis-summary');
              const cards = Array.from(root?.querySelectorAll('.cockpit-evidence-card') || []);
              const doc = document.documentElement;
              const rect = element => {
                const r = element.getBoundingClientRect();
                return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
              };
              return {
                state: root?.dataset.recommendationState || null,
                version_visible: (root?.innerText || '').includes('版本：'),
                basis_text: basis?.innerText || '',
                evidence_titles: cards.map(card => card.querySelector('div')?.textContent?.trim() || ''),
                evidence_count: cards.length,
                horizontal_overflow: doc.scrollWidth > doc.clientWidth + 1,
                basis_clipped: basis ? basis.scrollHeight > basis.clientHeight + 2 : true,
                root_rect: root ? rect(root) : null,
              };
            }
            """
        )
        basis_before = result["basis_text"]
        candidates = page.locator('.bf-engine-candidates .cockpit-candidate')
        candidate_count = await candidates.count()
        if candidate_count > 1:
            await candidates.nth(1).click()
            await page.wait_for_timeout(300)
        result["candidate_count"] = candidate_count
        result["basis_stable_after_candidate_click"] = (
            await page.locator('.bf-decision-basis-summary').inner_text()
        ) == basis_before
        result["basis_lines"] = [
            line.strip() for line in basis_before.splitlines() if line.strip()
        ]
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=False)
        await browser.close()
    result["page_errors"] = page_errors
    result["console_errors"] = [
        item for item in console_errors
        if "favicon.ico" not in item
        and "Failed to fetch" not in item
        and "code generator has deoptimised" not in item
        and "status of 502" not in item
    ]
    result["screenshot"] = str(screenshot)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the 8093 decision basis presentation.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--screenshot", default="logs/8093_decision_basis.png")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    result = asyncio.run(verify(args.url, Path(args.screenshot), args.width, args.height))
    failures: list[str] = []
    if result["state"] != "ready":
        failures.append("recommendation_not_ready")
    if result["version_visible"]:
        failures.append("version_comment_still_visible")
    if "规则判据" in result["basis_text"] or "处置逻辑" in result["basis_text"]:
        failures.append("internal_rule_labels_still_visible")
    if len(result["basis_lines"]) < 3:
        failures.append("decision_basis_content_missing")
    if result["evidence_count"] != 4:
        failures.append("condition_evidence_cards_missing")
    if not result["basis_stable_after_candidate_click"]:
        failures.append("decision_basis_changes_with_action_selection")
    if result["horizontal_overflow"] or result["basis_clipped"]:
        failures.append("layout_overflow_or_clipping")
    if result["page_errors"] or result["console_errors"]:
        failures.append("page_or_console_errors")
    payload = {"ok": not failures, "failures": failures, "result": result}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
