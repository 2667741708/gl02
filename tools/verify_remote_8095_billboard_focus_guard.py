#!/usr/bin/env python3
"""Remote/CDP acceptance test for the 8095 Billboard focus guard.

The script expects a Chrome instance with remote debugging enabled.  It opens
the 8095 page, clicks a real Three.js Billboard through CDP coordinates,
pushes the wheel inward until the shell collision guard engages, exits focus,
and records screenshots plus a machine-readable report.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
import websocket


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://127.0.0.1:9225")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8095/?focus_guard_validation=remote#overview",
    )
    parser.add_argument("--sensor-id", default="T_body_L9_H")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--ready-timeout", type=float, default=45.0)
    return parser.parse_args()


class CDP:
    def __init__(self, websocket_url: str) -> None:
        self.ws = websocket.create_connection(
            websocket_url,
            timeout=2,
            origin="http://127.0.0.1",
        )
        self.seq = 0

    def close(self) -> None:
        self.ws.close()

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.seq += 1
        message_id = self.seq
        self.ws.send(
            json.dumps(
                {"id": message_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            )
        )
        deadline = time.time() + 3
        while time.time() < deadline:
            payload = json.loads(self.ws.recv())
            if payload.get("id") == message_id:
                if "error" in payload:
                    raise RuntimeError(f"{method}: {payload['error']}")
                return payload.get("result", {})
        raise TimeoutError(method)

    def evaluate(self, expression: str) -> Any:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", expression))
        return remote.get("value")

    def click(self, x: float, y: float) -> None:
        common = {"x": x, "y": y, "button": "left", "clickCount": 1}
        self.send("Input.dispatchMouseEvent", {**common, "type": "mousePressed"})
        self.send("Input.dispatchMouseEvent", {**common, "type": "mouseReleased"})

    def wheel(self, x: float, y: float, delta_y: float) -> None:
        self.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": x,
                "y": y,
                "deltaX": 0,
                "deltaY": delta_y,
            },
        )

    def screenshot(self, target: Path) -> None:
        result = self.send("Page.captureScreenshot", {"format": "png"})
        target.write_bytes(base64.b64decode(result["data"]))


def wait_value(cdp: CDP, expression: str, timeout: float) -> Any:
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        try:
            last = cdp.evaluate(expression)
            if last:
                return last
        except (TimeoutError, RuntimeError, websocket.WebSocketTimeoutException):
            pass
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for: {expression}; last={last!r}")


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    response = requests.put(
        f"{args.cdp}/json/new?{urllib.parse.quote(args.url, safe='')}",
        timeout=2,
    )
    response.raise_for_status()
    target = response.json()
    cdp = CDP(target["webSocketDebuggerUrl"])
    report: dict[str, Any] = {
        "schema": "bf3d.focus-guard-8095.acceptance.v1",
        "url": args.url,
        "sensor_id": args.sensor_id,
        "started_at_epoch": time.time(),
    }
    try:
        cdp.send("Runtime.enable")
        cdp.send("Page.enable")
        wait_value(
            cdp,
            "Boolean(window.__BF3D_BILLBOARD_FOCUS_GUARD_8095__"
            " && window.__BF_CAD_FURNACE_VIEWER"
            " && window.__BF_CAD_FURNACE_VIEWER.billboardEntries?.length)",
            args.ready_timeout,
        )
        report["initial"] = cdp.evaluate(
            "window.__BF3D_BILLBOARD_FOCUS_GUARD_8095__.getState()"
        )
        report["route"] = cdp.evaluate("window.__BF3D_8095_MODEL_ROUTE__")
        report["billboard_count"] = cdp.evaluate(
            "window.__BF_CAD_FURNACE_VIEWER.billboardEntries.length"
        )

        sensor_literal = json.dumps(args.sensor_id)
        cdp.evaluate(
            "window.__BF3D_BILLBOARD_FOCUS_GUARD_8095__.fitOverview('acceptance')"
        )
        time.sleep(0.35)
        projected = wait_value(
            cdp,
            """
            (() => {
              const viewer = window.__BF_CAD_FURNACE_VIEWER;
              const entry = viewer.billboardEntries.find(
                item => item.bindingId === SENSOR_ID
              );
              if (!entry || !entry.sprite?.visible) return null;
              const rect = viewer.renderer.domElement.getBoundingClientRect();
              const point = entry.sprite.position.clone().project(viewer.camera);
              return {
                x: rect.left + (point.x + 1) * rect.width / 2,
                y: rect.top + (1 - point.y) * rect.height / 2,
                z: point.z,
                semantic: entry.point?.semantic_abbreviation_cn
                  || entry.point?.short_label
                  || entry.point?.semantic_name_cn
                  || ""
              };
            })()
            """.replace("SENSOR_ID", sensor_literal),
            4,
        )
        report["projected"] = projected
        cdp.click(projected["x"], projected["y"])
        time.sleep(0.6)
        report["after_real_click"] = cdp.evaluate(
            "window.__BF3D_BILLBOARD_FOCUS_GUARD_8095__.getState()"
        )
        report["focus_panel_text"] = cdp.evaluate(
            "document.querySelector('.bf3d-focus-panel')?.innerText || ''"
        )
        cdp.screenshot(out_dir / "8095_focus_after_real_billboard_click.png")

        for _ in range(36):
            cdp.wheel(projected["x"], projected["y"], -720)
            time.sleep(0.06)
            state = cdp.evaluate(
                "window.__BF3D_BILLBOARD_FOCUS_GUARD_8095__.getState()"
            )
            if state.get("collisionBlocked"):
                break
        report["after_continuous_wheel"] = state
        report["viewer_dataset_after_wheel"] = cdp.evaluate(
            """
            (() => {
              const host = document.querySelector('.cad-furnace-viewer');
              return host ? {...host.dataset} : null;
            })()
            """
        )
        cdp.screenshot(out_dir / "8095_focus_after_collision_guard.png")

        exit_result = cdp.evaluate(
            """
            (() => {
              const button = [...document.querySelectorAll('button')]
                .find(item => item.textContent.trim() === '退出聚焦');
              if (!button) return {clicked:false};
              button.click();
              return {clicked:true, disabled:Boolean(button.disabled)};
            })()
            """
        )
        report["exit_button"] = exit_result
        time.sleep(0.65)
        report["after_exit"] = cdp.evaluate(
            "window.__BF3D_BILLBOARD_FOCUS_GUARD_8095__.getState()"
        )
        cdp.screenshot(out_dir / "8095_overview_after_exit.png")

        click_state = report["after_real_click"]
        wheel_state = report["after_continuous_wheel"]
        exit_state = report["after_exit"]
        report["checks"] = {
            "route_alias_active": report["route"].get("resolved", "").endswith(
                "gl02_blast_furnace.glb"
            ),
            "all_133_billboards": report["billboard_count"] == 133,
            "real_click_selected_sensor": (
                click_state.get("mode") == "focus"
                and click_state.get("selectedId") == args.sensor_id
            ),
            "chinese_semantic_name": (
                projected.get("semantic") == click_state.get("selectedName")
                and bool(projected.get("semantic"))
            ),
            "shell_raycast_available": click_state.get("shellMeshCount", 0) > 0,
            "collision_guard_triggered": (
                wheel_state.get("collisionBlocked") is True
                and wheel_state.get("collisionCount", 0) > 0
            ),
            "exit_restored_overview": (
                exit_result.get("clicked") is True
                and exit_state.get("mode") == "overview"
                and not exit_state.get("selectedId")
            ),
        }
        report["passed"] = all(report["checks"].values())
    finally:
        report["finished_at_epoch"] = time.time()
        (out_dir / "8095_focus_guard_acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cdp.close()
    print(json.dumps({"passed": report.get("passed"), "checks": report.get("checks")}))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
