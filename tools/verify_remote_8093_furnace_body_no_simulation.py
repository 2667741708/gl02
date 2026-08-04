#!/usr/bin/env python3
"""Chrome/CDP acceptance for the 8093 furnace-body sync without simulation UI."""

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
ROUTES = ("overview", "diagnosis", "optimization", "trend", "qa")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://127.0.0.1:9225")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8093/?ws_port=8768&bf3d_8093_sync_acceptance=1#overview",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--ready-timeout", type=float, default=50.0)
    parser.add_argument("--skip-page-screenshots", action="store_true")
    parser.add_argument("--skip-canvas-screenshots", action="store_true")
    parser.add_argument("--skip-viewport-matrix", action="store_true")
    return parser.parse_args()


class CDP:
    def __init__(self, websocket_url: str) -> None:
        self.ws = websocket.create_connection(
            websocket_url, timeout=5, origin="http://127.0.0.1"
        )
        self.seq = 0
        self.events: list[dict[str, Any]] = []

    def close(self) -> None:
        self.ws.close()

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.seq += 1
        message_id = self.seq
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.time() + 5
        while time.time() < deadline:
            payload = json.loads(self.ws.recv())
            if payload.get("id") == message_id:
                if "error" in payload:
                    raise RuntimeError(f"{method}: {payload['error']}")
                return payload.get("result", {})
            if payload.get("method"):
                self.events.append(payload)
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

    def canvas_screenshot(self, target: Path) -> None:
        data_url = self.evaluate(
            "window.__BF_CAD_FURNACE_VIEWER.renderer.domElement.toDataURL('image/png')"
        )
        if not isinstance(data_url, str) or "," not in data_url:
            raise RuntimeError("Three.js canvas screenshot returned no PNG data")
        target.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))


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


def page_state(cdp: CDP) -> dict[str, Any]:
    return cdp.evaluate(
        """
        (() => {
          const root=document.documentElement;
          const host=document.querySelector('.cad-furnace-viewer');
          const canvas=host?.querySelector('canvas');
          const formalTitle=(document.body?.innerText||'').includes('高炉工艺大模型智能决策系统');
          return {
            route:location.hash,
            viewport:[innerWidth,innerHeight],
            horizontalOverflow:root.scrollWidth>innerWidth+1,
            bodyVisible:Boolean(document.body&&document.body.getBoundingClientRect().height>40),
            formalTitle,
            viewerVisible:Boolean(canvas&&canvas.getBoundingClientRect().width>40&&canvas.getBoundingClientRect().height>40),
            guardReady:host?.dataset.surfaceCameraGuard8093==='ready',
            targetMode:host?.dataset.cameraTargetMode||'',
            billboardCount:Number(host?.dataset.billboardCount||host?.dataset.sensorCount||0),
            modelAsset:host?.dataset.modelAsset||'',
            simulationPanelCount:document.querySelectorAll('.bf3d-sim-panel').length,
            simulationRuntimePresent:Boolean(window.__BF3D_INTERNAL_SIMULATION__)
          };
        })()
        """
    )


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
        "schema": "bf3d.8093-furnace-body-no-simulation.acceptance.v1",
        "url": args.url,
        "started_at_epoch": time.time(),
    }
    try:
        cdp.send("Runtime.enable")
        cdp.send("Log.enable")
        cdp.send("Page.enable")
        wait_value(
            cdp,
            "Boolean(window.__BF3D_SURFACE_CAMERA_GUARD_8093__"
            " && window.__BF_CAD_FURNACE_VIEWER?.billboardEntries?.length===133)",
            args.ready_timeout,
        )
        runtime = "window.__BF3D_SURFACE_CAMERA_GUARD_8093__"
        report["initial_guard"] = cdp.evaluate(f"{runtime}.getState()")
        report["initial_page"] = page_state(cdp)
        if not args.skip_canvas_screenshots:
            cdp.canvas_screenshot(out_dir / "8093_furnace_canvas_before_wheel.png")

        report["overview_360_rotation"] = cdp.evaluate(
            """
            (()=>{const v=window.__BF_CAD_FURNACE_VIEWER;
            const g=window.__BF3D_SURFACE_CAMERA_GUARD_8093__;
            const t=v.controls.target.clone(),start=v.camera.position.clone();
            const offset=start.clone().sub(t),horizontal=Math.hypot(offset.x,offset.z);
            const startAngle=Math.atan2(offset.z,offset.x),samples=[];
            for(let i=0;i<=24;i+=1){const a=startAngle+Math.PI*2*i/24;
              v.camera.position.set(t.x+Math.cos(a)*horizontal,t.y+offset.y,t.z+Math.sin(a)*horizontal);
              v.camera.lookAt(t);v.camera.updateMatrixWorld(true);v.controls.update();
              const s=g.getState();samples.push({i,d:s.cameraDistance,targetOffset:s.targetDistanceFromBodyCenter});}
            return {samples,state:g.getState()};})()
            """
        )

        report["focus_requested"] = cdp.evaluate(f"{runtime}.focusById('T_body_L9_H')")
        time.sleep(0.45)
        report["focus_initial"] = cdp.evaluate(f"{runtime}.getState()")
        report["focus_dynamic_rotation"] = cdp.evaluate(
            """
            (()=>{const v=window.__BF_CAD_FURNACE_VIEWER;
            const g=window.__BF3D_SURFACE_CAMERA_GUARD_8093__;
            const t=v.controls.target.clone(),offset=v.camera.position.clone().sub(t);
            const horizontal=Math.max(0.1,Math.hypot(offset.x,offset.z));
            const startAngle=Math.atan2(offset.z,offset.x),before=g.getState().dynamicSurfaceUpdateCount;
            const samples=[];
            for(let i=0;i<=16;i+=1){const a=startAngle+Math.PI*2*i/16;
              v.camera.position.set(t.x+Math.cos(a)*horizontal,t.y+offset.y,t.z+Math.sin(a)*horizontal);
              v.camera.lookAt(t);v.camera.updateMatrixWorld(true);v.controls.update();
              const s=g.getState();samples.push({i,source:s.surfaceTargetSource,gap:s.currentSignedGap});}
            const state=g.getState();return {before,after:state.dynamicSurfaceUpdateCount,samples,state};})()
            """
        )

        wheel_result = cdp.evaluate(
            """
            (()=>{const canvas=window.__BF_CAD_FURNACE_VIEWER.renderer.domElement;
            let dispatched=0;
            for(let i=0;i<54;i+=1){
              canvas.dispatchEvent(new WheelEvent('wheel',{
                deltaY:-720,bubbles:true,cancelable:true,view:window
              }));
              dispatched+=1;
              if(window.__BF3D_SURFACE_CAMERA_GUARD_8093__.getState().collisionBlocked)break;
            }
            return {dispatched,state:window.__BF3D_SURFACE_CAMERA_GUARD_8093__.getState()};})()
            """
        )
        wheel_state = wheel_result["state"]
        report["wheel_events_dispatched"] = wheel_result["dispatched"]
        report["after_wheel"] = wheel_state
        report["projection_after_wheel"] = {
            "camera_near": wheel_state.get("cameraNear"),
            "safe_near_plane": wheel_state.get("safeNearPlane"),
            "near_plane_locked": wheel_state.get("nearPlaneLocked"),
            "correction_count": wheel_state.get("nearPlaneCorrectionCount"),
            "correction_reason": wheel_state.get("nearPlaneCorrectionReason"),
        }
        report["signed_shell_gap"] = cdp.evaluate(
            """
            (()=>{const s=window.__BF3D_SURFACE_CAMERA_GUARD_8093__.getState();
            if(!s.surfacePoint||!s.surfaceNormal)return null;
            const a=s.cameraPosition.map((v,i)=>v-s.surfacePoint[i]);
            return a.reduce((sum,v,i)=>sum+v*s.surfaceNormal[i],0);})()
            """
        )
        report["exit_focus"] = cdp.evaluate(
            f"{runtime}.exitFocus({{animate:false,reason:'acceptance'}})"
        )
        report["after_exit"] = cdp.evaluate(f"{runtime}.getState()")
        if not args.skip_canvas_screenshots:
            cdp.canvas_screenshot(out_dir / "8093_furnace_canvas_after_guard.png")

        matrix: list[dict[str, Any]] = []
        if not args.skip_viewport_matrix:
            for width, height in VIEWPORTS:
                cdp.send(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                for route in ROUTES:
                    cdp.evaluate(f"location.hash='#{route}'")
                    time.sleep(0.09)
                    item = page_state(cdp)
                    item["requested"] = [width, height]
                    item["requestedRoute"] = f"#{route}"
                    matrix.append(item)
                    if not args.skip_page_screenshots and route == "overview":
                        cdp.screenshot(out_dir / f"8093_overview_{width}x{height}.png")
                    elif not args.skip_page_screenshots and width == 1366 and height == 768:
                        cdp.screenshot(out_dir / f"8093_{route}_1366x768.png")
            cdp.send("Emulation.clearDeviceMetricsOverride")
        else:
            report["viewport_matrix_skipped"] = (
                "near-plane regression only; reuse 20260801_r1 45/45 layout baseline"
            )
        report["chromium_matrix"] = matrix

        console_errors = []
        for event in cdp.events:
            method = event.get("method")
            params = event.get("params", {})
            if method == "Runtime.exceptionThrown":
                console_errors.append(params.get("exceptionDetails", {}).get("text", "exception"))
            elif method == "Log.entryAdded" and params.get("entry", {}).get("level") == "error":
                console_errors.append(params.get("entry", {}).get("text", "log error"))
        report["browser_errors"] = console_errors

        overview_items = [item for item in matrix if item["requestedRoute"] == "#overview"]
        report["checks"] = {
            "shared_furnace_body_loaded": report["initial_page"]["modelAsset"]
            == "GL02_FURNACE_BODY_R1.glb",
            "all_133_billboards": report["initial_page"]["billboardCount"] == 133,
            "dual_camera_runtime_scoped_to_8093": report["initial_guard"].get("schema")
            == "bf3d.camera.dual-mode.8093.v2",
            "overview_targets_furnace_center": report["initial_guard"].get("mode")
            == "overview"
            and report["initial_guard"].get("targetDistanceFromBodyCenter", 1) < 0.001,
            "overview_360_rotation_unclamped": len(
                report["overview_360_rotation"].get("samples", [])
            )
            == 25
            and all(
                sample.get("d", 0)
                >= report["initial_guard"].get("fullOrbitRadius", 0) - 0.03
                and sample.get("targetOffset", 1) < 0.001
                for sample in report["overview_360_rotation"].get("samples", [])
            ),
            "billboard_focus_entered": report["focus_requested"] is True
            and report["focus_initial"].get("mode") == "focus"
            and str(report["focus_initial"].get("selectedId", "")).endswith(
                "T_body_L9_H"
            ),
            "focus_surface_reprojects_dynamically": report["focus_dynamic_rotation"].get(
                "after", 0
            )
            > report["focus_dynamic_rotation"].get("before", 0)
            and any(
                str(sample.get("source", "")).startswith("dynamic-")
                for sample in report["focus_dynamic_rotation"].get("samples", [])
            ),
            "collision_guard_triggered": wheel_state.get("collisionBlocked") is True,
            "camera_stopped_outside_shell": report["signed_shell_gap"]
            is not None
            and report["signed_shell_gap"]
            >= wheel_state.get("safetyGap", 0) - 0.03,
            "near_plane_locked_for_8093": wheel_state.get("nearPlaneLocked") is True
            and wheel_state.get("safeNearPlane") == 0.05,
            "near_plane_not_clipping_shell": wheel_state.get("cameraNear", 1)
            <= 0.051
            and wheel_state.get("cameraNear", 1) < report["signed_shell_gap"],
            "simulation_panel_absent": report["initial_page"]["simulationPanelCount"] == 0
            and all(item["simulationPanelCount"] == 0 for item in matrix),
            "simulation_runtime_absent": not report["initial_page"]["simulationRuntimePresent"]
            and all(not item["simulationRuntimePresent"] for item in matrix),
            "exit_restores_furnace_overview": report["exit_focus"] is True
            and report["after_exit"].get("mode") == "overview"
            and report["after_exit"].get("targetDistanceFromBodyCenter", 1) < 0.001,
            "browser_error_count_zero": not console_errors,
        }
        if not args.skip_viewport_matrix:
            report["checks"].update(
                {
                    "chromium_45_route_viewports": len(matrix) == 45
                    and all(
                        item["viewport"] == item["requested"]
                        and item["route"] == item["requestedRoute"]
                        and not item["horizontalOverflow"]
                        and item["bodyVisible"]
                        and item["formalTitle"]
                        for item in matrix
                    ),
                    "overview_viewer_and_guard_visible": len(overview_items) == 9
                    and all(
                        item["viewerVisible"]
                        and item["guardReady"]
                        and item["targetMode"] == "furnace-center"
                        and item["billboardCount"] == 133
                        for item in overview_items
                    ),
                }
            )
        report["passed"] = all(report["checks"].values())
    finally:
        report["finished_at_epoch"] = time.time()
        (out_dir / "8093_furnace_body_no_simulation_acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        cdp.close()
    print(json.dumps({"passed": report.get("passed"), "checks": report.get("checks")}))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
