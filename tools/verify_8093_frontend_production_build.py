"""Compare the source dashboard with the Vite/esbuild production build.

This verifier is local-only. It serves the same static tree through two
ephemeral localhost ports, stubs WebSocket transport, and checks route loading,
the 3D billboard contract, and a deterministic overview-panel pixel diff.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import threading
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageChops, ImageStat
from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError, async_playwright


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
SOURCE_HTML = FRONTEND / "frontend_dashboard_v3.server.html"
PRODUCTION_HTML = FRONTEND / "frontend_dashboard_v3.production.html"
HEAVY_RESOURCE_MARKERS = (
    "/libs/three/",
    "GL02_FURNACE_BODY_R1.glb",
    "bf3d-furnace-body-billboard-adapter.js",
    "bf3d-surface-camera-guard-8093.js",
    "bf3d-tooltip-stable-hover-8093.js",
)
ROUTES = ("overview", "diagnosis", "optimization", "trend", "qa")
CHROMIUM_VIEWPORTS = (
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1546, 864),
    (1920, 1080),
    (1024, 768),
    (768, 1024),
    (390, 844),
    (375, 667),
)
REPRESENTATIVE_VIEWPORTS = ((1920, 1080), (1366, 768), (768, 1024), (390, 844))


FAKE_WEBSOCKET = r"""
(() => {
  class FakeWebSocket {
    static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
    constructor(url) {
      this.url = String(url); this.readyState = FakeWebSocket.CONNECTING;
      this.listeners = new Map();
      window.__FAKE_WEBSOCKET_URLS__ = window.__FAKE_WEBSOCKET_URLS__ || [];
      window.__FAKE_WEBSOCKET_URLS__.push(this.url);
      queueMicrotask(() => { this.readyState = FakeWebSocket.OPEN; this.emit('open', {}); });
    }
    addEventListener(name, callback) {
      const list = this.listeners.get(name) || []; list.push(callback); this.listeners.set(name, list);
    }
    removeEventListener(name, callback) {
      this.listeners.set(name, (this.listeners.get(name) || []).filter(item => item !== callback));
    }
    emit(name, event) {
      for (const callback of this.listeners.get(name) || []) callback.call(this, event);
      const handler = this[`on${name}`]; if (typeof handler === 'function') handler.call(this, event);
    }
    send() {}
    close() { this.readyState = FakeWebSocket.CLOSED; this.emit('close', {}); }
  }
  window.WebSocket = FakeWebSocket;
})();
"""


def handler_for(index_file: Path):
    primary_root = index_file.parent.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def send_json_fixture(self) -> None:
            body = json.dumps(
                {"ok": True, "state": "needs_data", "items": [], "events": [], "rules": []},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError):
                return

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                if content_length:
                    self.rfile.read(content_length)
                self.send_json_fixture()
                return
            self.send_error(404)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.send_json_fixture()
                return
            relative = unquote(parsed.path).lstrip("/")
            if not relative or relative in {
                "frontend_dashboard_v3.server.html",
                "frontend_dashboard_v3.production.html",
            }:
                target = index_file
            else:
                primary_target = (primary_root / relative).resolve()
                fallback_target = (FRONTEND / relative).resolve()
                target = primary_target if primary_target.is_file() else fallback_target
            allowed_roots = (primary_root, FRONTEND)
            if not any(target == root or root in target.parents for root in allowed_roots):
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix.lower() in {".html", ".js", ".css", ".json"}:
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionAbortedError):
                return

    return Handler


class LocalServer:
    def __init__(self, index_file: Path):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(index_file))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


async def new_page(browser: Browser) -> Page:
    page = await browser.new_page(viewport={"width": 1366, "height": 768}, device_scale_factor=1)
    await page.add_init_script(FAKE_WEBSOCKET)
    return page


async def resource_snapshot(page: Page) -> dict:
    return await page.evaluate(
        """() => {
          const resources = performance.getEntriesByType('resource').map(item => ({
            name: item.name,
            transferSize: item.transferSize || 0,
            encodedBodySize: item.encodedBodySize || 0,
            duration: item.duration || 0,
          }));
          const navigation = performance.getEntriesByType('navigation')[0];
          return {
            resources,
            totalTransferSize: resources.reduce((sum, item) => sum + item.transferSize, 0),
            totalEncodedBodySize: resources.reduce((sum, item) => sum + item.encodedBodySize, 0),
            domContentLoadedMs: navigation ? navigation.domContentLoadedEventEnd : 0,
            loadMs: navigation ? navigation.loadEventEnd : 0,
          };
        }"""
    )


async def diagnosis_probe(browser: Browser, base_url: str) -> dict:
    page = await new_page(browser)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    await page.goto(
        f"{base_url}/frontend_dashboard_v3.server.html?verify=perf-r1#diagnosis",
        wait_until="networkidle",
        timeout=60_000,
    )
    await page.wait_for_selector(".screen.diagnosis-grid", timeout=30_000)
    snapshot = await resource_snapshot(page)
    await page.close()
    heavy = [
        item["name"]
        for item in snapshot["resources"]
        if any(marker in item["name"] for marker in HEAVY_RESOURCE_MARKERS)
    ]
    return {**snapshot, "heavyResources": heavy, "pageErrors": errors}


async def overview_probe(browser: Browser, base_url: str, screenshot: Path, production: bool) -> dict:
    page = await new_page(browser)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    await page.goto(
        f"{base_url}/frontend_dashboard_v3.server.html?verify=perf-r1#overview",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    try:
        await page.wait_for_function(
            "document.querySelector('.cad-furnace-viewer')?.dataset.status === 'loaded'",
            timeout=20_000,
        )
    except PlaywrightTimeoutError as error:
        debug = await page.evaluate(
            """() => ({
              status: document.querySelector('.cad-furnace-viewer')?.dataset.status || 'missing',
              route: location.hash,
              overviewRuntimeStatus: document.documentElement.dataset.overviewRuntimeStatus || '',
              resources: performance.getEntriesByType('resource').map(item => item.name),
            })"""
        )
        raise RuntimeError(
            json.dumps({"message": str(error), "pageErrors": errors, "debug": debug}, ensure_ascii=False)
        ) from error
    try:
        await page.wait_for_function(
            "document.querySelector('.cad-furnace-viewer')?.dataset.billboardCount === '121'",
            timeout=20_000,
        )
    except PlaywrightTimeoutError as error:
        debug = await page.evaluate(
            """() => ({
              billboardStatus: document.querySelector('.cad-furnace-viewer')?.dataset.billboardStatus || '',
              sensorCount: window.__BF_CAD_FURNACE_VIEWER?.sensorObjects?.length || 0,
              billboardCount: window.__BF_CAD_FURNACE_VIEWER?.billboardEntries?.length || 0,
              hasAdapter: Boolean(window.BF3D_BILLBOARD_ADAPTER),
              resources: performance.getEntriesByType('resource').map(item => item.name),
            })"""
        )
        raise RuntimeError(
            json.dumps({"message": str(error), "pageErrors": errors, "debug": debug}, ensure_ascii=False)
        ) from error
    if production:
        await page.wait_for_function(
            "document.documentElement.dataset.overviewRuntimeStatus === 'loaded'",
            timeout=30_000,
        )
    detail_trigger = page.locator(
        '.core-spark-button[aria-label="查看综合顶压趋势与相关性"]'
    )
    await detail_trigger.wait_for(timeout=30_000)
    await detail_trigger.click()
    await page.locator(
        '.core-detail-dialog[role="dialog"][aria-label="综合顶压趋势与变量关联"]'
    ).wait_for(timeout=10_000)
    detail_overlay = await page.evaluate(
        """() => {
          const backdrop = document.querySelector('.core-detail-backdrop');
          const dialog = document.querySelector('[role=dialog].core-detail-dialog');
          if (!backdrop || !dialog) return { ok: false, reason: 'missing' };
          const rect = dialog.getBoundingClientRect();
          const top = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + Math.min(80, rect.height / 2)
          );
          const portalParentIsBody = backdrop.parentElement === document.body;
          const topmost = top === dialog || dialog.contains(top);
          const zIndex = Number(getComputedStyle(backdrop).zIndex);
          return {
            ok: portalParentIsBody && topmost && zIndex === 2147483647,
            portalParentIsBody,
            topmost,
            zIndex,
            topClass: top?.className || top?.tagName || '',
          };
        }"""
    )
    await page.locator('.core-detail-close[aria-label="关闭变量详情"]').click()
    await page.wait_for_timeout(2_000)
    await page.mouse.move(1, 1)
    await page.evaluate(
        """() => {
          const host = document.querySelector('.cad-furnace-viewer');
          const canvas = host?.querySelector('canvas');
          const viewer = canvas?.__bf3dViewer || window.__BF_CAD_FURNACE_VIEWER;
          if (viewer) window.__BF_CAD_FURNACE_VIEWER = viewer;
          canvas?.dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }));
          document.querySelectorAll('.cad-furnace-tooltip').forEach((tooltip) => {
            tooltip.style.display = 'none';
          });
          viewer?.surfaceCameraGuard8093?.resetOverview?.('visual-verification');
          viewer?.controls?.update?.();
          viewer?.renderer?.render?.(viewer.scene, viewer.camera);
          window.__BF_FURNACE_FOLLOW_ANCHORS_SYNC__?.();
        }"""
    )
    await page.evaluate(
        """() => new Promise((resolve) => requestAnimationFrame(
          () => requestAnimationFrame(resolve)
        ))"""
    )
    contract = await page.evaluate(
        """() => {
          const host = document.querySelector('.cad-furnace-viewer');
          const viewer = host?.querySelector('canvas')?.__bf3dViewer
            || window.__BF_CAD_FURNACE_VIEWER;
          const first = viewer?.billboardEntries?.[0]?.sprite;
          const fnv1a = (values) => {
            let hash = 2166136261;
            for (const value of values) {
              hash ^= value;
              hash = Math.imul(hash, 16777619);
            }
            return (hash >>> 0).toString(16).padStart(8, '0');
          };
          const textureSignatures = (viewer?.billboardEntries || []).map((entry) => {
            const canvas = entry.sprite?.material?.map?.image;
            if (!canvas?.getContext) return '';
            const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
            return fnv1a(pixels);
          });
          const geometryBytes = new TextEncoder().encode(
            (viewer?.billboardEntries || []).map((entry) => {
              const sprite = entry.sprite;
              return [
                entry.bindingId || entry.point?.id || '',
                ...sprite.position.toArray().map((value) => value.toFixed(5)),
                ...sprite.scale.toArray().map((value) => value.toFixed(5)),
              ].join(':');
            }).sort().join('|')
          );
          const calloutStyles = [...document.querySelectorAll('.furnace-layer-card')].map((card) => {
            const style = getComputedStyle(card);
            return {
              layer: card.dataset.layer || '',
              className: card.className,
              text: card.textContent,
              fontFamily: style.fontFamily,
              fontSize: style.fontSize,
              color: style.color,
              backgroundImage: style.backgroundImage,
              borderLeft: style.borderLeft,
              padding: style.padding,
              width: style.width,
              height: style.height,
            };
          });
          return {
            status: host?.dataset.status || '',
            sensorCount: Number(host?.dataset.sensorCount || 0),
            billboardCount: Number(host?.dataset.billboardCount || 0),
            pointPolicy: host?.dataset.pointPolicy || '',
            billboardScale: host?.dataset.billboardEmphasisScale || '',
            billboardPrimitive: first?.userData?.billboardPrimitive || '',
            textureColorSpace: first?.material?.map?.colorSpace || '',
            textureWidth: first?.material?.map?.userData?.canvasWidth || 0,
            textureHeight: first?.material?.map?.userData?.canvasHeight || 0,
            billboardTextureSignatures: textureSignatures,
            billboardGeometrySignature: fnv1a(geometryBytes),
            calloutStyleSignature: fnv1a(
              new TextEncoder().encode(JSON.stringify(calloutStyles))
            ),
            modelUrl: viewer?.modelUrl || '',
            rendererColorSpace: viewer?.renderer?.outputColorSpace || '',
            sharedSocketAttached: Boolean(window.__BF_CORE_PSPACE_LIVE__),
            schedulerTasks: window.__BF_SHARED_SCHEDULER__?.snapshot?.().keys || [],
            websocketUrls: window.__FAKE_WEBSOCKET_URLS__ || [],
          };
        }"""
    )
    panel = page.locator(".overview-furnace-panel-v12")
    await panel.screenshot(path=str(screenshot), animations="disabled")
    structure_screenshot = screenshot.with_name(f"{screenshot.stem}-structure{screenshot.suffix}")
    await page.evaluate(
        """() => {
          const host = document.querySelector('.cad-furnace-viewer');
          const viewer = host?.querySelector('canvas')?.__bf3dViewer
            || window.__BF_CAD_FURNACE_VIEWER;
          for (const entry of viewer?.billboardEntries || []) entry.sprite.visible = false;
          const callouts = document.querySelector('.furnace-layer-callouts');
          if (callouts) callouts.style.visibility = 'hidden';
          viewer?.renderer?.render?.(viewer.scene, viewer.camera);
        }"""
    )
    await panel.screenshot(path=str(structure_screenshot), animations="disabled")
    await page.evaluate(
        """() => {
          const host = document.querySelector('.cad-furnace-viewer');
          const viewer = host?.querySelector('canvas')?.__bf3dViewer
            || window.__BF_CAD_FURNACE_VIEWER;
          for (const entry of viewer?.billboardEntries || []) entry.sprite.visible = true;
          const callouts = document.querySelector('.furnace-layer-callouts');
          if (callouts) callouts.style.visibility = '';
          viewer?.renderer?.render?.(viewer.scene, viewer.camera);
        }"""
    )
    snapshot = await resource_snapshot(page)
    await page.close()
    return {
        "contract": contract,
        "detailOverlay": detail_overlay,
        "network": snapshot,
        "pageErrors": errors,
        "structureScreenshot": str(structure_screenshot),
    }


def pixel_diff(source: Path, production: Path, output: Path) -> dict:
    left = Image.open(source).convert("RGBA")
    right = Image.open(production).convert("RGBA")
    if left.size != right.size:
        return {"sameSize": False, "sourceSize": left.size, "productionSize": right.size}
    diff = ImageChops.difference(left, right)
    diff.save(output)
    stat = ImageStat.Stat(diff)
    mean = sum(stat.mean[:3]) / 3
    pixels = list(diff.getdata())
    changed = sum(1 for pixel in pixels if max(pixel[:3]) > 4)
    changed_ratio = changed / max(1, len(pixels))
    return {
        "sameSize": True,
        "width": left.width,
        "height": left.height,
        "meanAbsoluteDifference": mean,
        "changedPixelRatioOver4": changed_ratio,
    }


async def verify(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_shot = output_dir / "overview-source.png"
    production_shot = output_dir / "overview-production.png"
    diff_shot = output_dir / "overview-diff.png"
    structure_diff_shot = output_dir / "overview-structure-diff.png"
    with ExitStack() as stack:
        source_url = stack.enter_context(LocalServer(SOURCE_HTML))
        production_url = stack.enter_context(LocalServer(PRODUCTION_HTML))
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                source_diagnosis = await diagnosis_probe(browser, source_url)
                production_diagnosis = await diagnosis_probe(browser, production_url)
                source_overview = await overview_probe(browser, source_url, source_shot, False)
                production_overview = await overview_probe(
                    browser, production_url, production_shot, True
                )
            finally:
                await browser.close()
    appearance_visual = pixel_diff(source_shot, production_shot, diff_shot)
    visual = pixel_diff(
        Path(source_overview["structureScreenshot"]),
        Path(production_overview["structureScreenshot"]),
        structure_diff_shot,
    )
    source_contract = source_overview["contract"]
    production_contract = production_overview["contract"]
    comparable_keys = (
        "status",
        "sensorCount",
        "billboardCount",
        "pointPolicy",
        "billboardScale",
        "billboardPrimitive",
        "textureColorSpace",
        "textureWidth",
        "textureHeight",
        "billboardTextureSignatures",
        "billboardGeometrySignature",
        "calloutStyleSignature",
        "modelUrl",
        "rendererColorSpace",
    )
    contract_match = all(source_contract.get(key) == production_contract.get(key) for key in comparable_keys)
    result = {
        "ok": (
            not production_diagnosis["heavyResources"]
            and contract_match
            and visual.get("sameSize")
            and visual.get("changedPixelRatioOver4", 1) <= 0.01
            and not production_overview["pageErrors"]
            and production_overview["detailOverlay"]["ok"]
        ),
        "requirement": "REQ-8093-FRONTEND-PERF-R1",
        "diagnosis": {"source": source_diagnosis, "production": production_diagnosis},
        "overview": {"source": source_overview, "production": production_overview},
        "contractMatch": contract_match,
        "visual": visual,
        "appearanceVisual": appearance_visual,
        "artifacts": {
            "source": str(source_shot),
            "production": str(production_shot),
            "diff": str(diff_shot),
            "sourceStructure": source_overview["structureScreenshot"],
            "productionStructure": production_overview["structureScreenshot"],
            "structureDiff": str(structure_diff_shot),
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


async def verify_full_matrix(output_dir: Path) -> dict:
    """Run the required 85 production-build route/engine/viewport cases."""

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with LocalServer(PRODUCTION_HTML) as production_url:
        async with async_playwright() as playwright:
            for engine_name in ("chromium", "firefox", "webkit"):
                browser_type = getattr(playwright, engine_name)
                browser = await browser_type.launch(headless=True)
                viewports = (
                    CHROMIUM_VIEWPORTS
                    if engine_name == "chromium"
                    else REPRESENTATIVE_VIEWPORTS
                )
                context = await browser.new_context(
                    viewport={"width": viewports[0][0], "height": viewports[0][1]},
                    device_scale_factor=1,
                )
                await context.add_init_script(FAKE_WEBSOCKET)
                try:
                    for route_index, route in enumerate(ROUTES):
                        for width, height in viewports:
                            page = await context.new_page()
                            await page.set_viewport_size({"width": width, "height": height})
                            console_errors: list[str] = []
                            page_errors: list[str] = []
                            page.on(
                                "console",
                                lambda message, target=console_errors: target.append(message.text)
                                if message.type == "error"
                                else None,
                            )
                            page.on("pageerror", lambda error, target=page_errors: target.append(str(error)))
                            record = {
                                "engine": engine_name,
                                "route": route,
                                "viewport": f"{width}x{height}",
                                "failures": [],
                            }
                            try:
                                await page.goto(
                                    f"{production_url}/frontend_dashboard_v3.server.html?matrix={engine_name}-{route}-{width}x{height}#{route}",
                                    wait_until="domcontentloaded",
                                    timeout=30_000,
                                )
                                await page.wait_for_selector(".app", timeout=15_000)
                                await page.wait_for_function(
                                    """(index) => {
                                      const buttons = document.querySelectorAll('.bottom-nav .nav-btn');
                                      return buttons[index]?.classList.contains('active');
                                    }""",
                                    arg=route_index,
                                    timeout=10_000,
                                )
                                if route == "overview":
                                    await page.wait_for_function(
                                        "document.documentElement.dataset.overviewRuntimeStatus === 'loaded'",
                                        timeout=30_000,
                                    )
                                    await page.wait_for_function(
                                        "document.querySelector('.cad-furnace-viewer')?.dataset.billboardCount === '121'",
                                        timeout=30_000,
                                    )
                                else:
                                    await page.wait_for_timeout(250)
                                state = await page.evaluate(
                                    """() => {
                                      const resources = performance.getEntriesByType('resource').map(item => item.name);
                                      return {
                                        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                                        mainChildren: document.querySelector('.main')?.children.length || 0,
                                        resources,
                                      };
                                    }"""
                                )
                                if state["overflow"]:
                                    record["failures"].append("horizontal_overflow")
                                if state["mainChildren"] != 1:
                                    record["failures"].append("route_root_missing")
                                if route != "overview" and any(
                                    marker in resource
                                    for resource in state["resources"]
                                    for marker in HEAVY_RESOURCE_MARKERS
                                ):
                                    record["failures"].append("non_overview_loaded_3d")
                                if console_errors:
                                    record["failures"].append(
                                        "console:" + " | ".join(console_errors[:3])
                                    )
                                if page_errors:
                                    record["failures"].append(
                                        "page:" + " | ".join(page_errors[:3])
                                    )
                            except Exception as error:  # noqa: BLE001
                                record["failures"].append(str(error))
                            if record["failures"]:
                                screenshot = output_dir / (
                                    f"FAIL-{engine_name}-{route}-{width}x{height}.png"
                                )
                                await page.screenshot(path=str(screenshot), full_page=True)
                                record["screenshot"] = str(screenshot)
                            results.append(record)
                            await page.close()
                finally:
                    await context.close()
                    await browser.close()
    failures = [record for record in results if record["failures"]]
    report = {
        "ok": not failures and len(results) == 85,
        "requirement": "REQ-8093-FRONTEND-PERF-R1",
        "caseCount": len(results),
        "failureCount": len(failures),
        "failures": failures,
        "results": results,
    }
    (output_dir / "full-matrix.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    global SOURCE_HTML, PRODUCTION_HTML
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".tmp" / "8093-frontend-production-build",
    )
    parser.add_argument("--source-html", type=Path, default=SOURCE_HTML)
    parser.add_argument("--production-html", type=Path, default=PRODUCTION_HTML)
    parser.add_argument("--full-matrix", action="store_true")
    args = parser.parse_args()
    SOURCE_HTML = args.source_html.resolve()
    PRODUCTION_HTML = args.production_html.resolve()
    if not SOURCE_HTML.is_file() or not PRODUCTION_HTML.is_file():
        parser.error("source and production HTML files must exist")
    result = asyncio.run(verify(args.output.resolve()))
    full = asyncio.run(verify_full_matrix(args.output.resolve())) if args.full_matrix else None
    summary = {
        "ok": result["ok"] and (full is None or full["ok"]),
        "diagnosisSourceTransfer": result["diagnosis"]["source"]["totalTransferSize"],
        "diagnosisProductionTransfer": result["diagnosis"]["production"]["totalTransferSize"],
        "diagnosisProductionHeavyResources": result["diagnosis"]["production"]["heavyResources"],
        "contractMatch": result["contractMatch"],
        "visual": result["visual"],
        "fullMatrix": None
        if full is None
        else {"ok": full["ok"], "caseCount": full["caseCount"], "failureCount": full["failureCount"]},
        "report": str(args.output.resolve() / "report.json"),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
