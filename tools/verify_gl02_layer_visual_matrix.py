"""Capture and validate the GL02 layer highlight across browser engines and viewports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


CHROMIUM_VIEWPORTS = [(1280, 720), (1366, 768), (1440, 900), (1546, 864), (1920, 1080), (1024, 768), (768, 1024), (390, 844), (375, 667)]
REPRESENTATIVE_VIEWPORTS = [(1920, 1080), (1366, 768), (768, 1024), (390, 844)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GL02 L10 highlight visual matrix.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8092")
    parser.add_argument("--ws-port", type=int, default=8767)
    parser.add_argument("--output", type=Path, default=Path("logs/gl02_layer_visual_matrix"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    url = f"{args.base_url.rstrip('/')}/?ws_port={args.ws_port}#overview"
    results: list[dict] = []
    with sync_playwright() as playwright:
        for engine_name, engine, viewports in (
            ("chromium", playwright.chromium, CHROMIUM_VIEWPORTS),
            ("firefox", playwright.firefox, REPRESENTATIVE_VIEWPORTS),
            ("webkit", playwright.webkit, REPRESENTATIVE_VIEWPORTS),
        ):
            try:
                browser = engine.launch(headless=True)
            except Exception as exc:
                results.append({"engine": engine_name, "skipped": True, "error": str(exc)})
                continue
            for width, height in viewports:
                errors: list[str] = []
                page = browser.new_page(viewport={"width": width, "height": height})
                page.on("pageerror", lambda error, target=errors: target.append(str(error)))
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_function("window.__BF_CAD_FURNACE_VIEWER?.highlightLayer", timeout=60_000)
                page.locator('button[data-kind="layer"][data-id="L10"]').click()
                page.wait_for_timeout(650)
                state = page.evaluate(
                    """() => ({
                      highlight: window.__BF_CAD_FURNACE_VIEWER.getLayerHighlightState(),
                      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                      controlsVisible: !!document.querySelector('.cad-layer-controls')?.getClientRects().length,
                      canvas: {width: document.querySelector('.cad-furnace-viewer canvas')?.clientWidth || 0, height: document.querySelector('.cad-furnace-viewer canvas')?.clientHeight || 0}
                    })"""
                )
                screenshot = args.output / f"{engine_name}_{width}x{height}_L10.png"
                page.screenshot(path=str(screenshot), full_page=False)
                ok = not errors and not state["horizontalOverflow"] and state["controlsVisible"] and state["highlight"]["layerId"] == "L10" and state["canvas"]["width"] > 0
                results.append({"engine": engine_name, "viewport": f"{width}x{height}", "ok": ok, "state": state, "errors": errors, "screenshot": str(screenshot.resolve())})
                page.close()
            browser.close()
    report = {"ok": all(item.get("ok", item.get("skipped", False)) for item in results), "url": url, "results": results}
    report_path = args.output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
