#!/usr/bin/env python3
"""Firefox/WebKit representative viewport checks for the GL02 L7-L16 UI.

The frontend is served as static files on an ephemeral local port. Therefore
the 8767 WebSocket and /api/* failures are expected offline signals; model,
script, page, console, and other resource failures remain hard failures.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, Error, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "高炉前端数据"
OUTPUT_ROOT = ROOT / "logs" / "bf3d_layer_cross_engine_20260717"
VIEWPORTS = ((1920, 1080), (1366, 768), (768, 1024), (390, 844))
ENGINES = ("firefox", "webkit")
LAYERS_TO_CLICK = ("L7", "L10", "L13", "L16")
EXPECTED_LAYER_IDS = tuple(f"L{layer}" for layer in range(7, 17))

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: Any) -> None:
        return


def start_static_server() -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    handler = lambda *args, **kwargs: QuietStaticHandler(  # noqa: E731
        *args, directory=str(FRONTEND_ROOT), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    return server, thread, f"http://127.0.0.1:{port}"


def expected_offline_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.path.startswith("/api/") or (
        parsed.hostname == "127.0.0.1" and parsed.port == 8767
    )


def expected_offline_console(message: str, offline_network_items: list[dict[str, Any]]) -> bool:
    if "127.0.0.1:8767" in message and any(
        marker in message
        for marker in ("WebSocket", "websocket", "ws://127.0.0.1:8767")
    ):
        return True
    offline_markers = (
        "Failed to load resource:",
        "Failed to fetch",
        "Load failed",
        "NetworkError",
    )
    return bool(offline_network_items) and any(marker in message for marker in offline_markers)


def rectangles_overlap(first: dict[str, float] | None, second: dict[str, float] | None) -> bool:
    if not first or not second:
        return False
    return not (
        first["right"] <= second["left"]
        or second["right"] <= first["left"]
        or first["bottom"] <= second["top"]
        or second["bottom"] <= first["top"]
    )


def collect_static_state(page: Page) -> dict[str, Any]:
    state = page.evaluate(
        """() => {
          const doc = document.documentElement;
          const body = document.body;
          const host = document.querySelector(".cad-furnace-viewer");
          const controls = document.querySelector(".cad-layer-controls");
          const nav = document.querySelector(".bottom-nav");
          const toRect = (element) => {
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            return {
              left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
              width: rect.width, height: rect.height
            };
          };
          return {
            status: host?.dataset.status || "",
            sensorCount: Number(host?.dataset.sensorCount || 0),
            mappedCount: Number(host?.dataset.mappedCount || 0),
            canvas: {
              width: host?.querySelector("canvas")?.clientWidth || 0,
              height: host?.querySelector("canvas")?.clientHeight || 0
            },
            layerIds: Array.from(
              document.querySelectorAll('button[data-kind="layer"]'),
              (button) => button.dataset.id
            ),
            horizontalOverflow:
              doc.scrollWidth > doc.clientWidth + 1 ||
              body.scrollWidth > doc.clientWidth + 1,
            viewport: { width: doc.clientWidth, height: doc.clientHeight },
            controlsRect: toRect(controls),
            navRect: toRect(nav)
          };
        }"""
    )
    state["controlsNavOverlap"] = rectangles_overlap(
        state.get("controlsRect"), state.get("navRect")
    )
    return state


def layer_state(page: Page, layer_id: str) -> dict[str, Any]:
    locator = page.locator(f'button[data-kind="layer"][data-id="{layer_id}"]')
    count = locator.count()
    visible = count == 1 and locator.is_visible()
    center_uncovered = False
    if count == 1:
        locator.scroll_into_view_if_needed(timeout=10_000)
        center_uncovered = bool(
            locator.evaluate(
                """(button) => {
                  const rect = button.getBoundingClientRect();
                  const x = Math.max(0, Math.min(innerWidth - 1, rect.left + rect.width / 2));
                  const y = Math.max(0, Math.min(innerHeight - 1, rect.top + rect.height / 2));
                  const top = document.elementFromPoint(x, y);
                  return !!top && (top === button || button.contains(top));
                }"""
            )
        )
        locator.click(timeout=10_000)
        page.wait_for_timeout(100)

    state = page.evaluate(
        """(requested) => {
          const viewer = window.__BF_CAD_FURNACE_VIEWER;
          const host = document.querySelector(".cad-furnace-viewer");
          const visibleNames = viewer.sensorObjects
            .filter((object) => object.visible && object.name.startsWith("SENSOR_T_body_"))
            .map((object) => object.name);
          return {
            requested,
            active:
              document.querySelector(".cad-layer-controls button.active")?.dataset.id || "",
            visibleSensors: Number(host?.dataset.visibleSensors || -1),
            visibleNames,
            highlight: viewer.getLayerHighlightState()
          };
        }""",
        layer_id,
    )
    state.update(
        {
            "buttonCount": count,
            "buttonVisible": visible,
            "buttonCenterUncovered": center_uncovered,
        }
    )
    state["ok"] = bool(
        count == 1
        and visible
        and center_uncovered
        and state["active"] == layer_id
        and state["visibleSensors"] == 8
        and len(state["visibleNames"]) == 8
        and all(
            name.startswith(f"SENSOR_T_body_{layer_id}_")
            for name in state["visibleNames"]
        )
        and state["highlight"].get("layerId") == layer_id
    )
    return state


def run_viewport(
    browser: Browser, engine: str, base_url: str, width: int, height: int
) -> dict[str, Any]:
    viewport_id = f"{width}x{height}"
    context = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=1,
        reduced_motion="no-preference",
    )
    page = context.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    http_errors: list[dict[str, Any]] = []

    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def on_console(message: Any) -> None:
        if message.type == "error":
            console_errors.append(message.text)

    def on_request_failed(request: Any) -> None:
        failed_requests.append(
            {
                "url": request.url,
                "error": request.failure or "request failed",
            }
        )

    def on_response(response: Any) -> None:
        if response.status >= 400:
            http_errors.append({"status": response.status, "url": response.url})

    page.on("console", on_console)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)

    result: dict[str, Any] = {
        "engine": engine,
        "viewport": viewport_id,
        "url": f"{base_url}/frontend_dashboard_v3.server.html?ws_port=8767#overview",
        "ok": False,
        "checks": {},
        "layers": {},
        "page_errors": page_errors,
        "console_errors": [],
        "expected_offline": [],
        "benign_runtime": [],
        "unexpected_http_errors": [],
        "unexpected_request_failures": [],
    }

    try:
        page.goto(result["url"], wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_function(
            """() =>
              window.__BF_CAD_FURNACE_VIEWER?.sensorCount === 115 &&
              typeof window.__BF_CAD_FURNACE_VIEWER?.highlightLayer === "function"
            """,
            timeout=60_000,
        )
        page.locator(".cad-layer-controls").wait_for(
            state="visible", timeout=15_000
        )

        static_state = collect_static_state(page)
        result["static"] = static_state
        result["checks"] = {
            "model_loaded": bool(
                static_state["status"] == "loaded"
                and static_state["sensorCount"] == 115
                and static_state["mappedCount"] == 115
                and static_state["canvas"]["width"] > 0
                and static_state["canvas"]["height"] > 0
            ),
            "ten_layer_buttons": static_state["layerIds"]
            == list(EXPECTED_LAYER_IDS),
            "no_horizontal_overflow": not static_state["horizontalOverflow"],
            "controls_not_covered_by_bottom_nav": not static_state[
                "controlsNavOverlap"
            ],
        }

        for requested_layer in LAYERS_TO_CLICK:
            result["layers"][requested_layer] = layer_state(page, requested_layer)
        result["checks"]["four_layer_clicks"] = all(
            result["layers"][requested_layer]["ok"]
            for requested_layer in LAYERS_TO_CLICK
        )

        screenshot = OUTPUT_ROOT / f"{engine}_{viewport_id}_L16.png"
        page.screenshot(path=str(screenshot), full_page=False)
        result["screenshot"] = str(screenshot)

        expected_http = [
            item for item in http_errors if expected_offline_url(item["url"])
        ]
        unexpected_http = [
            item for item in http_errors if not expected_offline_url(item["url"])
        ]
        expected_requests = [
            item for item in failed_requests if expected_offline_url(item["url"])
        ]
        benign_model_cancellations = [
            item
            for item in failed_requests
            if result["checks"]["model_loaded"]
            and urlparse(item["url"]).path == "/models/gl02_blast_furnace.glb"
            and ("ABORTED" in item["error"].upper() or "CANCEL" in item["error"].upper())
        ]
        unexpected_requests = [
            item
            for item in failed_requests
            if item not in expected_requests and item not in benign_model_cancellations
        ]
        offline_network_items = [*expected_http, *expected_requests]
        expected_console = [
            message
            for message in console_errors
            if expected_offline_console(message, offline_network_items)
        ]
        benign_console = [
            message
            for message in console_errors
            if message.startswith(
                "[BABEL] Note: The code generator has deoptimised the styling"
            )
        ]
        unexpected_console = [
            message
            for message in console_errors
            if message not in expected_console and message not in benign_console
        ]

        result["expected_offline"] = [
            *({"kind": "http", **item} for item in expected_http),
            *({"kind": "request", **item} for item in expected_requests),
            *({"kind": "console", "message": message} for message in expected_console),
        ]
        result["benign_runtime"] = [
            *(
                {
                    "kind": "cancelled_duplicate_model_request_after_successful_load",
                    **item,
                }
                for item in benign_model_cancellations
            ),
            *(
                {
                    "kind": "babel_large_inline_script_notice",
                    "message": message,
                }
                for message in benign_console
            ),
        ]
        result["unexpected_http_errors"] = unexpected_http
        result["unexpected_request_failures"] = unexpected_requests
        result["console_errors"] = unexpected_console
        result["checks"]["no_page_errors"] = len(page_errors) == 0
        result["checks"]["no_unexpected_console_errors"] = (
            len(unexpected_console) == 0
        )
        result["checks"]["no_unexpected_resource_errors"] = (
            len(unexpected_http) == 0 and len(unexpected_requests) == 0
        )
        result["ok"] = all(result["checks"].values())
    except Exception as error:  # Preserve all evidence for the manifest.
        result["failure"] = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        try:
            screenshot = OUTPUT_ROOT / f"{engine}_{viewport_id}_FAIL.png"
            page.screenshot(path=str(screenshot), full_page=False)
            result["screenshot"] = str(screenshot)
        except Error:
            pass
    finally:
        context.close()
    return result


def markdown_report(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "# GL02 测温层 Firefox / WebKit 代表视口验收",
        "",
        f"- 结果：{summary['passed']}/{summary['total']} 通过；"
        f"{summary['blocked_engines']} 个浏览器引擎因本机环境阻塞",
        "- 数据边界：静态页面，8767 WebSocket 与 `/api/*` 离线仅记为 "
        "`expected_offline`，未屏蔽模型、脚本或其他资源错误",
        f"- Playwright：{manifest['playwright_version']}",
        "",
        "| 引擎 | 视口 | 结果 | 模型/115点 | 十层按钮 | L7/L10/L13/L16 | "
        "无横向溢出 | 控制栏未被底栏遮挡 | 页面/控制台/资源错误 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    mark = lambda value: "通过" if value else "失败"  # noqa: E731
    for result in manifest["results"]:
        checks = result.get("checks", {})
        clean_runtime = bool(
            checks.get("no_page_errors")
            and checks.get("no_unexpected_console_errors")
            and checks.get("no_unexpected_resource_errors")
        )
        lines.append(
            f"| {result['engine']} | {result['viewport']} | {mark(result['ok'])} | "
            f"{mark(checks.get('model_loaded'))} | "
            f"{mark(checks.get('ten_layer_buttons'))} | "
            f"{mark(checks.get('four_layer_clicks'))} | "
            f"{mark(checks.get('no_horizontal_overflow'))} | "
            f"{mark(checks.get('controls_not_covered_by_bottom_nav'))} | "
            f"{mark(clean_runtime)} |"
        )
    if manifest["blocked"]:
        lines.extend(["", "## 环境阻塞", ""])
        for item in manifest["blocked"]:
            lines.append(
                f"- {item['engine']}：{item['reason']}；预期路径 "
                f"`{item.get('executable', '')}`"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not FRONTEND_ROOT.is_dir():
        raise FileNotFoundError(f"Frontend root not found: {FRONTEND_ROOT}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    server, server_thread, base_url = start_static_server()
    results: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    engine_info: dict[str, Any] = {}

    try:
        with sync_playwright() as playwright:
            package_version = "unknown"
            try:
                from importlib.metadata import version

                package_version = version("playwright")
            except Exception:
                pass

            for engine in ENGINES:
                browser_type = getattr(playwright, engine)
                executable = browser_type.executable_path
                engine_info[engine] = {
                    "executable": executable,
                    "executable_exists": Path(executable).is_file(),
                }
                if not Path(executable).is_file():
                    blocked.append(
                        {
                            "engine": engine,
                            "reason": "匹配当前 Playwright 的浏览器可执行文件未安装",
                            "executable": executable,
                        }
                    )
                    continue

                browser: Browser | None = None
                try:
                    browser = browser_type.launch(headless=True, timeout=30_000)
                    engine_info[engine]["browser_version"] = browser.version
                    for width, height in VIEWPORTS:
                        result = run_viewport(
                            browser, engine, base_url, width, height
                        )
                        results.append(result)
                        print(
                            f"{engine} {width}x{height}: "
                            f"{'PASS' if result['ok'] else 'FAIL'}",
                            flush=True,
                        )
                except Exception as error:
                    blocked.append(
                        {
                            "engine": engine,
                            "reason": f"浏览器启动失败：{error}",
                            "executable": executable,
                        }
                    )
                finally:
                    if browser:
                        browser.close()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    total_expected = len(ENGINES) * len(VIEWPORTS)
    passed = sum(1 for result in results if result["ok"])
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Firefox/WebKit GL02 L7/L10/L13/L16 representative viewport matrix",
        "static_data_source": True,
        "expected_offline_policy": (
            "Only 127.0.0.1:8767 WebSocket and /api/* static-server failures "
            "are expected offline."
        ),
        "playwright_version": package_version,
        "engines": engine_info,
        "summary": {
            "expected_cases": total_expected,
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "blocked_engines": len(blocked),
            "ok": (
                len(blocked) == 0
                and len(results) == total_expected
                and passed == total_expected
            ),
        },
        "blocked": blocked,
        "results": results,
    }
    manifest_path = OUTPUT_ROOT / "manifest.json"
    report_path = OUTPUT_ROOT / "report.md"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_path.write_text(markdown_report(manifest), encoding="utf-8")
    print(f"manifest: {manifest_path}", flush=True)
    return 0 if manifest["summary"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
