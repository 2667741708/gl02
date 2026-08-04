from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def verify_static() -> dict:
    text = HTML.read_text(encoding="utf-8")
    required = [
        "MiniCadFurnaceIcon",
        "MiniRotatingCadFurnaceIcon",
        "v4-mini-cad-furnace-icon",
        "models/gl02_blast_furnace.glb",
        "__BF_MINI_CAD_FURNACE_VIEWER",
    ]
    return {token: token in text for token in required}


async def verify_browser(url: str, screenshot: Path, timeout_ms: int) -> dict:
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page_errors: list[str] = []
    console_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_selector(".mini-cad-furnace", timeout=timeout_ms)
        await page.wait_for_function(
            "() => document.querySelector('.mini-cad-furnace')?.dataset.status === 'loaded'",
            timeout=timeout_ms,
        )
        await page.wait_for_timeout(900)
        before = await page.evaluate(
            """
            () => {
              const el = document.querySelector('.mini-cad-furnace');
              const canvas = el?.querySelector('canvas');
              return {
                status: el?.dataset.status || null,
                model_url: el?.dataset.modelUrl || null,
                mesh_count: Number(el?.dataset.modelMeshCount || 0),
                has_canvas: !!canvas,
                canvas_size: canvas ? [canvas.width, canvas.height] : null,
                rotation_y: Number(el?.dataset.rotationY || 0),
                svg_count: document.querySelectorAll('svg.diag-mini-furnace').length,
                body_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                visible_text: el?.innerText || '',
              };
            }
            """
        )
        await page.wait_for_timeout(1000)
        after = await page.evaluate(
            "() => Number(document.querySelector('.mini-cad-furnace')?.dataset.rotationY || 0)"
        )
        await page.locator(".mini-cad-furnace").screenshot(path=str(screenshot))
        await browser.close()
    before["rotation_y_after"] = after
    before["rotation_delta"] = after - before["rotation_y"]
    before["screenshot"] = str(screenshot)
    before["page_errors"] = page_errors
    before["console_errors"] = console_errors
    return before


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the small diagnosis furnace uses the local rotating GLB model.")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767#diagnosis",
    )
    parser.add_argument(
        "--screenshot",
        default=str(ROOT / "logs" / "diagnosis_page_iteration" / "mini_cad_furnace_verify.png"),
    )
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    args = parser.parse_args()

    result = {
        "static": verify_static(),
        "browser": asyncio.run(verify_browser(args.url, Path(args.screenshot), args.timeout_ms)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failures: list[str] = []
    if not all(result["static"].values()):
        failures.append("missing_static_tokens")
    browser = result["browser"]
    if browser["page_errors"] or browser["console_errors"]:
        failures.append("page_or_console_errors")
    if browser["status"] != "loaded" or browser["model_url"] != "models/gl02_blast_furnace.glb":
        failures.append("mini_glb_not_loaded")
    if not browser["has_canvas"] or browser["mesh_count"] < 10:
        failures.append("mini_glb_canvas_or_mesh_missing")
    if browser["svg_count"] != 0:
        failures.append("legacy_svg_still_rendered")
    if abs(browser["rotation_delta"]) < 0.05:
        failures.append("mini_glb_not_rotating")
    if browser["body_overflow"] != 0:
        failures.append("layout_overflow")
    if failures:
        print(json.dumps({"failed": failures}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
