"""Browser acceptance for the 8093 single-owner Billboard hover controller.

BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802

The verifier launches an isolated installed Chrome, projects the live Three.js
Billboard entries into screen coordinates, selects a dense point cluster, and
then performs repeated two-pixel mouse movements.  The active sensor and the
viewport-fixed tooltip rectangle must remain stable throughout the sequence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SCHEMA = "bf3d.tooltip.stable-hover.8093.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://10.30.220.12:8093/?ws_port=8768#overview",
    )
    parser.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "logs" / "8093_tooltip_hover_acceptance_20260802.json",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=ROOT / "logs" / "8093_tooltip_hover_acceptance_20260802.png",
    )
    parser.add_argument("--ready-timeout-ms", type=int, default=60_000)
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


async def read_runtime(page) -> dict:
    return await page.evaluate(
        """() => {
          const viewer = window.__BF_CAD_FURNACE_VIEWER;
          const runtime = window.__BF3D_STABLE_TOOLTIP_HOVER_8093__;
          const canvas = viewer?.renderer?.domElement;
          const host = canvas?.parentElement;
          const tip = document.querySelector('.cad-furnace-tooltip');
          if (!viewer || !runtime || !canvas || !host || !tip) {
            return {
              ready: false,
              hasViewer: Boolean(viewer),
              hasRuntime: Boolean(runtime),
              hasCanvas: Boolean(canvas),
              hasTooltip: Boolean(tip),
            };
          }
          return {
            ready: true,
            schema: runtime.schema,
            singleWriter: runtime.singleWriter,
            coordinateSpace: runtime.coordinateSpace,
            selectionPolicy: runtime.selectionPolicy,
            pointFocusEnabled: runtime.pointFocusEnabled,
            legacyWritersDisabled: runtime.legacyWritersDisabled,
            billboardEmphasisScale: runtime.billboardEmphasisScale,
            billboardEmphasisReqId: runtime.billboardEmphasisReqId,
            owner: host.dataset.tooltipOwner || '',
            hostCoordinateSpace: host.dataset.tooltipCoordinateSpace || '',
            hostSelection: host.dataset.tooltipSelection || '',
            totalEntries: Array.isArray(viewer.billboardEntries)
              ? viewer.billboardEntries.length
              : -1,
            emphasizedEntries: Array.isArray(viewer.billboardEntries)
              ? viewer.billboardEntries.filter(entry =>
                  Number(entry?.sprite?.userData?.__bf3dBillboardEmphasis8093?.factor) === 1.22
                ).length
              : -1,
            viewerEmphasisScale: viewer.billboardEmphasisScale ?? null,
            hostEmphasisScale: host.dataset.billboardEmphasisScale || '',
            state: runtime.getState(),
            tooltip: {
              position: getComputedStyle(tip).position,
              display: getComputedStyle(tip).display,
            },
          };
        }"""
    )


async def dense_candidate(page) -> dict:
    return await page.evaluate(
        """() => {
          const viewer = window.__BF_CAD_FURNACE_VIEWER;
          const canvas = viewer.renderer.domElement;
          const rect = canvas.getBoundingClientRect();
          const world = viewer.camera.position.clone();
          const ndc = viewer.camera.position.clone();
          const points = [];
          for (const entry of viewer.billboardEntries || []) {
            const id = entry?.bindingId || entry?.point?.canonical_id ||
              entry?.point?.data_binding_key || entry?.point?.id ||
              entry?.sprite?.userData?.sensorId || '';
            if (!id || !entry?.sprite?.visible || !entry.sprite.parent) continue;
            entry.sprite.getWorldPosition(world);
            ndc.copy(world).project(viewer.camera);
            const x = rect.left + ((ndc.x + 1) * rect.width) / 2;
            const y = rect.top + ((1 - ndc.y) * rect.height) / 2;
            if (ndc.z < -1 || ndc.z > 1) continue;
            if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) continue;
            points.push({id, x, y, z: ndc.z});
          }
          let candidate = null;
          for (const point of points) {
            let nearest = Infinity;
            for (const other of points) {
              if (other === point) continue;
              nearest = Math.min(nearest, Math.hypot(point.x - other.x, point.y - other.y));
            }
            if (!candidate || nearest < candidate.nearest) {
              candidate = {...point, nearest};
            }
          }
          return {
            candidate,
            visibleProjected: points.length,
            canvasRect: {
              left: rect.left,
              top: rect.top,
              right: rect.right,
              bottom: rect.bottom,
              width: rect.width,
              height: rect.height,
            },
          };
        }"""
    )


async def sample_tooltip(page) -> dict:
    return await page.evaluate(
        """() => {
          const runtime = window.__BF3D_STABLE_TOOLTIP_HOVER_8093__;
          const tip = document.querySelector('.cad-furnace-tooltip');
          const host = window.__BF_CAD_FURNACE_VIEWER?.renderer?.domElement?.parentElement;
          const rect = tip?.getBoundingClientRect();
          return {
            state: runtime?.getState?.() || null,
            owner: host?.dataset?.tooltipOwner || '',
            display: tip ? getComputedStyle(tip).display : '',
            position: tip ? getComputedStyle(tip).position : '',
            left: rect?.left ?? null,
            top: rect?.top ?? null,
            width: rect?.width ?? null,
            height: rect?.height ?? null,
          };
        }"""
    )


async def run(args: argparse.Namespace) -> dict:
    if not args.chrome.is_file():
        raise FileNotFoundError(f"Chrome executable not found: {args.chrome}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)

    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []
    bad_responses: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not args.headed,
            executable_path=str(args.chrome),
            args=["--use-angle=swiftshader", "--enable-webgl"],
        )
        context = await browser.new_context(viewport={"width": 1546, "height": 864})
        page = await context.new_page()
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                f"{request.method} {request.url}: {request.failure}"
            ),
        )
        page.on(
            "response",
            lambda response: bad_responses.append(
                f"{response.status} {response.url}"
            )
            if response.status >= 400
            else None,
        )
        try:
            await page.goto(args.url, wait_until="domcontentloaded", timeout=20_000)
        except PlaywrightTimeoutError:
            # The dashboard holds long-lived connections. Runtime readiness is
            # the authoritative signal for this scoped acceptance.
            pass
        try:
            await page.wait_for_function(
                """() => Boolean(
                  window.__BF3D_STABLE_TOOLTIP_HOVER_8093__ &&
                  window.__BF_CAD_FURNACE_VIEWER?.renderer?.domElement &&
                  window.__BF_CAD_FURNACE_VIEWER?.billboardEntries?.length &&
                  window.__BF_CAD_FURNACE_VIEWER?.billboardEmphasisScale === 1.22
                )""",
                timeout=args.ready_timeout_ms,
            )
        except PlaywrightTimeoutError:
            await page.screenshot(path=str(args.screenshot), full_page=False)
            diagnostic = await page.evaluate(
                """() => ({
                  url: location.href,
                  title: document.title,
                  rootChildren: document.querySelector('#root')?.childElementCount ?? -1,
                  bodyChildren: document.body?.childElementCount ?? -1,
                  hasReact: Boolean(window.React),
                  hasBabel: Boolean(window.Babel),
                  hasViewer: Boolean(window.__BF_CAD_FURNACE_VIEWER),
                  hasStableRuntime: Boolean(window.__BF3D_STABLE_TOOLTIP_HOVER_8093__),
                  singleOwnerFlag: Boolean(window.__BF3D_HOVER_SINGLE_OWNER_8093__),
                  viewer: window.__BF_CAD_FURNACE_VIEWER ? {
                    keys: Object.keys(window.__BF_CAD_FURNACE_VIEWER).slice(0, 40),
                    hasModel: Boolean(window.__BF_CAD_FURNACE_VIEWER.model),
                    hasScene: Boolean(window.__BF_CAD_FURNACE_VIEWER.scene),
                    hasRenderer: Boolean(window.__BF_CAD_FURNACE_VIEWER.renderer),
                    hasControls: Boolean(window.__BF_CAD_FURNACE_VIEWER.controls),
                    furnaceBodyBillboards: Boolean(window.__BF_CAD_FURNACE_VIEWER.__bf3dFurnaceBodyBillboards),
                    billboardEntries: window.__BF_CAD_FURNACE_VIEWER.billboardEntries?.length ?? -1,
                    billboardEmphasisScale: window.__BF_CAD_FURNACE_VIEWER.billboardEmphasisScale ?? null,
                    sensorObjects: window.__BF_CAD_FURNACE_VIEWER.sensorObjects?.length ?? -1,
                  } : null,
                  viewerHostStatus: document.querySelector('.cad-furnace-viewer')?.dataset?.status || '',
                  canvasCount: document.querySelectorAll('canvas').length,
                  scripts: Array.from(document.scripts).slice(-8).map(script => script.src || script.type),
                })"""
            )
            await browser.close()
            report = {
                "requirement_id": "BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802",
                "url": args.url,
                "viewport": "1546x864",
                "passed": False,
                "checks": {"runtime_ready": False},
                "diagnostic": diagnostic,
                "page_errors": page_errors,
                "console_errors": console_errors[:30],
                "failed_requests": failed_requests[:30],
                "bad_responses": bad_responses[:30],
                "screenshot": str(args.screenshot),
            }
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return report

        runtime = await read_runtime(page)
        projection = await dense_candidate(page)
        candidate = projection.get("candidate")
        if not candidate:
            raise RuntimeError("no visible projected Billboard candidate")

        x = float(candidate["x"])
        y = float(candidate["y"])
        await page.mouse.move(x, y)
        await page.wait_for_timeout(220)
        initial = await sample_tooltip(page)

        offsets = [
            (-2, 0),
            (2, 0),
            (0, -2),
            (0, 2),
            (-1, -1),
            (1, 1),
        ] * 4
        samples = []
        for dx, dy in offsets:
            await page.mouse.move(x + dx, y + dy)
            await page.wait_for_timeout(35)
            samples.append(await sample_tooltip(page))

        await page.screenshot(path=str(args.screenshot), full_page=False)
        final_runtime = await read_runtime(page)
        await browser.close()

    all_samples = [initial, *samples]
    active_ids = [sample.get("state", {}).get("activeId", "") for sample in all_samples]
    active_ids = [item for item in active_ids if item]
    lefts = [float(sample["left"]) for sample in all_samples if sample.get("left") is not None]
    tops = [float(sample["top"]) for sample in all_samples if sample.get("top") is not None]
    switch_counts = [
        int(sample.get("state", {}).get("switches", 0)) for sample in all_samples
    ]
    unique_active_ids = sorted(set(active_ids))
    left_range = max(lefts) - min(lefts) if lefts else None
    top_range = max(tops) - min(tops) if tops else None
    switch_delta = max(switch_counts) - min(switch_counts) if switch_counts else None

    checks = {
        "runtime_schema": runtime.get("schema") == SCHEMA,
        "single_writer": runtime.get("singleWriter") is True
        and runtime.get("owner") == "stable-hover-8093",
        "viewport_fixed": runtime.get("coordinateSpace") == "viewport-fixed"
        and runtime.get("tooltip", {}).get("position") == "fixed",
        "hysteresis_policy": runtime.get("selectionPolicy") == "screen-space-hysteresis",
        "point_focus_disabled": runtime.get("pointFocusEnabled") is False,
        "physical_points_121": runtime.get("totalEntries") == 121,
        "billboard_emphasis_122": runtime.get("billboardEmphasisScale") == 1.22
        and runtime.get("viewerEmphasisScale") == 1.22
        and runtime.get("hostEmphasisScale") == "1.22",
        "all_visible_points_emphasized": runtime.get("emphasizedEntries") == 121,
        "dense_cluster_used": float(candidate.get("nearest", 9999)) <= 46,
        "tooltip_visible": all(sample.get("display") != "none" for sample in all_samples),
        "active_sensor_stable": len(unique_active_ids) == 1,
        "no_switches_during_jitter": switch_delta == 0,
        "horizontal_position_stable": left_range is not None and left_range <= 1.0,
        "vertical_position_stable": top_range is not None and top_range <= 1.0,
        "page_errors_zero": not page_errors,
    }
    report = {
        "requirement_id": "BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802",
        "url": args.url,
        "viewport": "1546x864",
        "runtime": runtime,
        "final_runtime": final_runtime,
        "projection": projection,
        "jitter": {
            "moves": len(offsets),
            "max_offset_px": 2,
            "active_ids": unique_active_ids,
            "switch_delta": switch_delta,
            "left_range_px": left_range,
            "top_range_px": top_range,
        },
        "checks": checks,
        "page_errors": page_errors,
        "console_errors": console_errors[:20],
        "failed_requests": failed_requests[:20],
        "bad_responses": bad_responses[:20],
        "screenshot": str(args.screenshot),
        "passed": all(checks.values()),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    args = parse_args()
    report = asyncio.run(run(args))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
