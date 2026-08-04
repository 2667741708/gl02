#!/usr/bin/env python3
"""Chrome/CDP acceptance for the 8094 furnace-surface camera guard."""

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


VIEWPORTS = [
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1546, 864),
    (1920, 1080),
    (1024, 768),
    (768, 1024),
    (390, 844),
    (375, 667),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://127.0.0.1:9225")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8094/?surface_camera_guard_acceptance=1#overview",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--ready-timeout", type=float, default=50.0)
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
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
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
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", expression))
        return remote.get("value")

    def wheel(self, x: float, y: float, delta_y: float) -> None:
        self.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": delta_y},
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
    raise TimeoutError(f"Timed out waiting for {expression}; last={last!r}")


def distance(left: list[float], right: list[float]) -> float:
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)) ** 0.5


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    response = requests.put(
        f"{args.cdp}/json/new?{urllib.parse.quote(args.url, safe='')}", timeout=2
    )
    response.raise_for_status()
    target = response.json()
    cdp = CDP(target["webSocketDebuggerUrl"])
    report: dict[str, Any] = {
        "schema": "bf3d.surface-camera-guard-8094.acceptance.v1",
        "url": args.url,
        "started_at_epoch": time.time(),
    }
    try:
        cdp.send("Runtime.enable")
        cdp.send("Page.enable")
        wait_value(
            cdp,
            "Boolean(window.__BF3D_SURFACE_CAMERA_GUARD_8094__"
            " && window.__BF_CAD_FURNACE_VIEWER?.renderer?.domElement)",
            args.ready_timeout,
        )
        runtime = "window.__BF3D_SURFACE_CAMERA_GUARD_8094__"
        report["initial"] = cdp.evaluate(f"{runtime}.getState()")
        report["billboard_count"] = cdp.evaluate(
            "window.__BF_CAD_FURNACE_VIEWER.billboardEntries?.length || 0"
        )
        canvas = cdp.evaluate(
            """
            (() => {
              const rect = window.__BF_CAD_FURNACE_VIEWER.renderer.domElement.getBoundingClientRect();
              return {x:rect.left+rect.width/2,y:rect.top+rect.height/2,width:rect.width,height:rect.height};
            })()
            """
        )
        cdp.screenshot(out_dir / "8094_surface_target_before_wheel.png")

        wheel_state = report["initial"]
        for _ in range(54):
            cdp.wheel(canvas["x"], canvas["y"], -720)
            time.sleep(0.045)
            wheel_state = cdp.evaluate(f"{runtime}.getState()")
            if wheel_state.get("collisionBlocked"):
                break
        report["after_continuous_wheel"] = wheel_state
        report["signed_shell_gap"] = cdp.evaluate(
            """
            (() => {
              const s=window.__BF3D_SURFACE_CAMERA_GUARD_8094__.getState();
              const a=s.cameraPosition.map((v,i)=>v-s.surfacePoint[i]);
              return a.reduce((sum,v,i)=>sum+v*s.surfaceNormal[i],0);
            })()
            """
        )
        report["viewer_dataset"] = cdp.evaluate(
            "(() => { const h=document.querySelector('.cad-furnace-viewer'); return h ? {...h.dataset} : null; })()"
        )
        cdp.screenshot(out_dir / "8094_surface_target_after_wheel_guard.png")

        report["full_view_result"] = cdp.evaluate(
            """
            (() => {
              const b=document.querySelector('.bf3d-fit-full-model');
              if(!b)return {clicked:false};
              b.click();
              return {clicked:true};
            })()
            """
        )
        time.sleep(0.25)
        report["after_full_view"] = cdp.evaluate(f"{runtime}.getState()")

        viewport_results = []
        for width, height in VIEWPORTS:
            cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
            )
            time.sleep(0.08)
            layout = cdp.evaluate(
                """
                (() => {
                  const root=document.documentElement;
                  const host=document.querySelector('.cad-furnace-viewer');
                  const rect=host?.getBoundingClientRect();
                  return {
                    viewport:[innerWidth,innerHeight],
                    horizontalOverflow:root.scrollWidth>innerWidth+1,
                    viewerVisible:Boolean(rect&&rect.width>40&&rect.height>40),
                    guardReady:host?.dataset.surfaceCameraGuard8094==='ready',
                    targetMode:host?.dataset.cameraTargetMode||''
                  };
                })()
                """
            )
            layout["requested"] = [width, height]
            viewport_results.append(layout)
        cdp.send("Emulation.clearDeviceMetricsOverride")
        report["chromium_viewports"] = viewport_results

        initial = report["initial"]
        after_full = report["after_full_view"]
        report["checks"] = {
            "surface_runtime_ready": initial.get("mode") == "furnace-surface",
            "fitted_shell_raycast_available": initial.get("shellMeshCount", 0) > 0,
            "all_133_billboards_preserved": report["billboard_count"] == 133,
            "target_is_real_shell_surface": initial.get("surfaceTargetSource")
            == "shell-raycast"
            and initial.get("targetDistanceFromBodyCenter", 0) > 0.5
            and initial.get("targetDistanceFromSurface", 1) <= 0.11,
            "wheel_target_stayed_on_surface": distance(initial["target"], wheel_state["target"])
            < 0.01,
            "collision_guard_triggered": wheel_state.get("collisionBlocked") is True
            and wheel_state.get("collisionCount", 0) > 0,
            "camera_stopped_outside_shell": report["signed_shell_gap"]
            >= wheel_state.get("safetyGap", 0) - 0.03,
            "full_view_keeps_surface_target": after_full.get("mode") == "furnace-surface"
            and after_full.get("surfaceTargetSource") == "shell-raycast"
            and after_full.get("targetDistanceFromBodyCenter", 0) > 0.5
            and after_full.get("targetDistanceFromSurface", 1) <= 0.11,
            "chromium_required_viewports": all(
                item["viewport"] == item["requested"]
                and not item["horizontalOverflow"]
                and item["viewerVisible"]
                and item["guardReady"]
                and item["targetMode"] == "furnace-surface"
                for item in viewport_results
            ),
        }
        report["passed"] = all(report["checks"].values())
    finally:
        report["finished_at_epoch"] = time.time()
        (out_dir / "8094_surface_camera_guard_acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        cdp.close()
    print(json.dumps({"passed": report.get("passed"), "checks": report.get("checks")}))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
