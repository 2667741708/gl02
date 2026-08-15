#!/usr/bin/env python3
"""Targeted production Chromium smoke for the 8093 throat-variable removal."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "logs" / f"8093_remove_throat_smoke_{datetime.now():%Y%m%d_%H%M%S}"
URL = "http://10.30.220.12:8093/?cb=remove-throat-production-20260811#diagnosis"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    failed_responses: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on(
            "response",
            lambda response: failed_responses.append(
                f"HTTP {response.status} {response.url}"
            )
            if response.status >= 400
            else None,
        )
        response = page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        if response is None or response.status != 200:
            raise RuntimeError("8093 page did not return HTTP 200")
        contract = page.locator(
            '.diag-vars-wrap[data-core-variable-contract="no-throat-temperature-20260811"]'
        )
        contract.wait_for(state="visible", timeout=20000)
        cards = contract.locator(".diag-var-card[data-core-variable-id]")
        ids = set(
            cards.evaluate_all("nodes => nodes.map(node => node.dataset.coreVariableId)")
        )
        throat = {"T_throat_A", "T_throat_B", "T_throat_C", "T_throat_D"}
        tops = {"T_top_A", "T_top_B", "T_top_C", "T_top_D"}
        heat = page.request.get(
            "http://10.30.220.12:8093/assets/bf-heat-performance-quality-8093-query-v2.js?v=20260807-query-v2"
        )
        screenshot = OUTPUT / "diagnosis-1366x768.png"
        page.screenshot(path=str(screenshot), full_page=True)
        result = {
            "ok": (
                cards.count() == 32
                and not (ids & throat)
                and tops.issubset(ids)
                and heat.status == 200
                and not failed_responses
                and not console_errors
            ),
            "url": URL,
            "viewport": "1366x768",
            "core_variable_count": cards.count(),
            "throat_ids_present": sorted(ids & throat),
            "top_ids_present": sorted(ids & tops),
            "heat_query_http": heat.status,
            "failed_responses": failed_responses,
            "console_errors": console_errors,
            "screenshot": str(screenshot),
        }
        browser.close()
    report = OUTPUT / "report.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["report"] = str(report)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
