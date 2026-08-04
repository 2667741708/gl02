"""Verify the 8092 overview variable-insight interaction.

对应需求：
- REQ-20260605-FOREMAN-VARIABLE-INSIGHT：首页核心指标、CAD 点位和趋势图可打开变量关联分析抽屉。

文档：
- docs/requirements_traceability.md#req-20260605-foreman-variable-insight-首页变量关联分析交互
- docs/test_reference.md#test-20260605-foreman-variable-insight-首页变量关联分析验收
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
DEFAULT_URL = "http://127.0.0.1:8092/frontend_dashboard_v3.server.html?ws_port=8767"


REQUIRED_TOKENS = [
    "VARIABLE_RELATION_GROUPS",
    "window.VARIABLE_RELATION_GROUPS",
    "VariableInsightDrawer",
    "BFInsightOverviewTab",
    "BFInsightMetricRows",
    "BFInsightCadFurnaceViewer",
    "BFInsightChartBox",
    "metric-row-button",
    "basis-action",
    "foreman-actions",
    "cad-insight-click-wrap",
    "onSeriesClick",
    "bf_pending_variable_insight",
    "bf_pending_variable_question",
    "带上下文追问",
    "传感器数据展览台",
    "__BF_CAD_SENSOR_EXHIBITION_STAGE__",
    "__BF_CAD_SENSOR_EXHIBITION_STATE__",
    "__BF_OVERVIEW_CAD_ROTATION_PAUSED__",
    "bf-cad-pin-card",
    "bf-cad-pin-lines",
    "clickHit",
    "rotationPaused",
    "prefers-reduced-motion",
]

CORE_IDS = [
    "GasUtil",
    "PI",
    "O2_rate",
    "Q_O2",
    "TFT",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "P_top",
    "DP_upper",
    "DP_lower",
    "DP_total",
    "L",
    "L_south",
    "L_north",
    "Q_blast",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "PCI_rate",
    "PCI_set",
    "T_taphole_1",
    "T_taphole_2",
]

RELATION_GROUP_TOKENS = [
    "pressure-permeability",
    "top-temperature-heatload",
    "top-pressure-oscillation",
    "stockline-lowline",
    "blast-system",
    "gas-efficiency",
]


def _extract_block(html: str) -> str:
    start = html.index("const VARIABLE_RELATION_GROUPS=")
    end = html.index("window.__BF_RENDER_APP__&&window.__BF_RENDER_APP__();", start)
    return html[start:end]


def verify_static() -> dict:
    html = FRONTEND_HTML.read_text(encoding="utf-8")
    missing = [token for token in REQUIRED_TOKENS if token not in html]
    if missing:
        raise AssertionError(f"frontend HTML is missing variable insight tokens: {missing}")

    block = _extract_block(html)
    late_render = html.index("window.__BF_RENDER_APP__&&window.__BF_RENDER_APP__();")
    patch_start = html.index("const VARIABLE_RELATION_GROUPS=")
    if patch_start > late_render:
        raise AssertionError("variable insight patch must execute before React render")

    missing_groups = [token for token in RELATION_GROUP_TOKENS if token not in block]
    if missing_groups:
        raise AssertionError(f"missing relation groups: {missing_groups}")

    missing_core_ids = [token for token in CORE_IDS if token not in block]
    if missing_core_ids:
        raise AssertionError(f"missing clickable core metric ids: {missing_core_ids}")

    metric_ids_match = re.search(r"MetricRows=function BFInsightMetricRows\([^)]*\)\{const ids=\[([^\]]+)\]", block)
    if not metric_ids_match:
        raise AssertionError("cannot locate BFInsightMetricRows id list")
    metric_ids = re.findall(r"'([^']+)'", metric_ids_match.group(1))
    if len(metric_ids) != 28:
        raise AssertionError(f"expected 28 clickable core metrics, got {len(metric_ids)}")
    if metric_ids != CORE_IDS:
        raise AssertionError(f"clickable core metric order changed unexpectedly: {metric_ids}")

    forbidden_in_new_block = ["pSpace", "GL02_PGPASSWORD", "生产写入", "控制写入", "执行控制", "下发控制"]
    leaked = [token for token in forbidden_in_new_block if token in block]
    if leaked:
        raise AssertionError(f"variable insight block contains forbidden operational wording: {leaked}")

    return {
        "static": "ok",
        "relation_groups": len(RELATION_GROUP_TOKENS),
        "clickable_core_metrics": len(metric_ids),
        "tokens_checked": len(REQUIRED_TOKENS),
    }


async def verify_browser(url: str, screenshot_dir: Path) -> dict:
    from playwright.async_api import async_playwright

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector(".app", timeout=30_000)
        await page.wait_for_selector(".compact-core-metrics", timeout=30_000)
        await page.wait_for_timeout(1_500)

        header_text = await page.locator(".topbar").inner_text(timeout=10_000)
        for token in ["高炉工艺大模型智能决策系统", "炽穹・高炉炼铁大模型"]:
            if token not in header_text:
                raise AssertionError(f"brand header is missing token: {token}")

        metric_count = await page.locator(".compact-core-metrics .metric-row-button").count()
        if metric_count != 28:
            raise AssertionError(f"expected 28 clickable metric buttons, got {metric_count}")

        async def open_metric(label: str) -> dict:
            await page.locator(f".metric-row-button:has-text('{label}')").first.click()
            await page.wait_for_selector(".var-insight-drawer", timeout=10_000)
            await page.wait_for_timeout(500)
            drawer_text = await page.locator(".var-insight-drawer").inner_text()
            for token in ["传感器数据展览台", "关联变量", "规则影响", "带上下文追问"]:
                if token not in drawer_text:
                    raise AssertionError(f"drawer for {label} missing visible token: {token}")
            chart_canvas = await page.locator(".var-insight-chart canvas").count()
            if chart_canvas < 1:
                raise AssertionError(f"drawer for {label} did not render an ECharts canvas")
            overflow = await page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if overflow > 8:
                raise AssertionError(f"visible horizontal overflow after opening {label}: {overflow}px")
            return {"label": label, "drawer_chars": len(drawer_text), "chart_canvas": chart_canvas}

        opened = [await open_metric(label) for label in ["总压差", "煤气利用率", "顶温A"]]
        await page.locator(".var-close").click()
        await page.wait_for_selector(".var-insight-drawer", state="detached", timeout=10_000)

        await page.wait_for_selector(".cad-insight-click-wrap .cad-furnace-viewer[data-status='loaded']", timeout=30_000)
        await page.wait_for_function(
            "() => window.__BF_CAD_FURNACE_VIEWER?.hitObjects?.length === 115 && window.__BF_CAD_SENSOR_EXHIBITION_STATE__",
            timeout=30_000,
        )

        blank = await page.evaluate(
            """() => {
                const host = document.querySelector('.cad-insight-click-wrap .cad-furnace-viewer');
                const wrap = document.querySelector('.cad-insight-click-wrap');
                const v = window.__BF_CAD_FURNACE_VIEWER;
                const rect = wrap.getBoundingClientRect();
                const canvasRect = v.renderer.domElement.getBoundingClientRect();
                const project = (obj) => {
                    const p = obj.position.clone().project(v.camera);
                    return {x: canvasRect.left + (p.x + 1) * canvasRect.width / 2, y: canvasRect.top + (1 - p.y) * canvasRect.height / 2};
                };
                const points = v.hitObjects.map(project);
                let best = {x: rect.left + rect.width * 0.08, y: rect.top + rect.height * 0.12, d: -1};
                for (let y = rect.top + 34; y < rect.bottom - 34; y += 22) {
                    for (let x = rect.left + 34; x < rect.right - 34; x += 22) {
                        const d = Math.min(...points.map(p => Math.hypot(x - p.x, y - p.y)));
                        if (d > best.d) best = {x, y, d};
                    }
                }
                return best;
            }"""
        )
        await page.mouse.click(blank["x"], blank["y"])
        await page.wait_for_timeout(450)
        miss_state = await page.evaluate(
            """() => ({
                drawerCount: document.querySelectorAll('.var-insight-drawer').length,
                clickHit: document.querySelector('.cad-insight-click-wrap .cad-furnace-viewer')?.dataset.clickHit,
                paused: window.__BF_OVERVIEW_CAD_ROTATION_PAUSED__,
                rotationY: Number(document.querySelector('.cad-insight-click-wrap .cad-furnace-viewer')?.dataset.rotationY || 0),
            })"""
        )
        if miss_state["drawerCount"] != 0 or miss_state["clickHit"] != "miss" or not miss_state["paused"]:
            raise AssertionError(f"CAD blank click should miss sensor and pause rotation, got {miss_state}")
        await page.wait_for_timeout(900)
        paused_delta = await page.evaluate(
            """(before) => Math.abs(Number(document.querySelector('.cad-insight-click-wrap .cad-furnace-viewer')?.dataset.rotationY || 0) - before)""",
            miss_state["rotationY"],
        )
        if paused_delta > 0.003:
            raise AssertionError(f"CAD rotation did not pause after blank click: delta={paused_delta}")

        sensor_points = await page.evaluate(
            """() => {
                const host = document.querySelector('.cad-insight-click-wrap .cad-furnace-viewer');
                const wrap = document.querySelector('.cad-insight-click-wrap');
                const v = window.__BF_CAD_FURNACE_VIEWER;
                const rect = wrap.getBoundingClientRect();
                const canvasRect = v.renderer.domElement.getBoundingClientRect();
                return v.hitObjects.map(obj => {
                    const p = obj.position.clone().project(v.camera);
                    return {
                        id: obj.userData.sensorId,
                        x: canvasRect.left + (p.x + 1) * canvasRect.width / 2,
                        y: canvasRect.top + (1 - p.y) * canvasRect.height / 2,
                    };
                }).filter(p => p.x > rect.left && p.x < rect.right && p.y > rect.top && p.y < rect.bottom);
            }"""
        )
        if len(sensor_points) < 2:
            raise AssertionError(f"expected at least two projected CAD sensors, got {sensor_points}")

        await page.mouse.click(sensor_points[0]["x"], sensor_points[0]["y"])
        await page.wait_for_selector(".var-insight-drawer", timeout=10_000)
        await page.wait_for_selector(".bf-cad-pin-card", timeout=10_000)
        first_drawer_text = await page.locator(".var-insight-drawer").inner_text()
        if "传感器数据展览台" not in first_drawer_text:
            raise AssertionError("CAD sensor click drawer title was not renamed")
        first_pin_state = await page.evaluate(
            """() => ({
                pinCount: document.querySelectorAll('.bf-cad-pin-card').length,
                lineCount: document.querySelectorAll('.bf-cad-pin-lines line').length,
                mode: document.querySelector('.bf-cad-pin-card')?.dataset.mode,
                clickHit: document.querySelector('.cad-insight-click-wrap .cad-furnace-viewer')?.dataset.clickHit,
            })"""
        )
        if first_pin_state["pinCount"] < 1 or first_pin_state["lineCount"] < 1 or first_pin_state["mode"] != "follow" or first_pin_state["clickHit"] != "sensor":
            raise AssertionError(f"CAD sensor click did not create follow pin with connector: {first_pin_state}")

        close_blank = await page.evaluate(
            """() => {
                const wrap = document.querySelector('.cad-insight-click-wrap');
                const drawer = document.querySelector('.var-insight-layer');
                const v = window.__BF_CAD_FURNACE_VIEWER;
                const rect = wrap.getBoundingClientRect();
                const canvasRect = v.renderer.domElement.getBoundingClientRect();
                const drawerRect = drawer?.getBoundingClientRect();
                const insideDrawer = (x, y) => drawerRect && x >= drawerRect.left - 4 && x <= drawerRect.right + 4 && y >= drawerRect.top - 4 && y <= drawerRect.bottom + 4;
                const project = (obj) => {
                    const p = obj.position.clone().project(v.camera);
                    return {x: canvasRect.left + (p.x + 1) * canvasRect.width / 2, y: canvasRect.top + (1 - p.y) * canvasRect.height / 2};
                };
                const points = v.hitObjects.map(project);
                let best = null;
                for (let y = rect.top + 28; y < rect.bottom - 28; y += 20) {
                    for (let x = rect.left + 28; x < rect.right - 28; x += 20) {
                        if (insideDrawer(x, y)) continue;
                        const d = Math.min(...points.map(p => Math.hypot(x - p.x, y - p.y)));
                        if (!best || d > best.d) best = {x, y, d};
                    }
                }
                return best || {x: rect.left + 24, y: rect.top + 24, d: 0};
            }"""
        )
        await page.mouse.click(close_blank["x"], close_blank["y"])
        await page.wait_for_selector(".var-insight-drawer", state="detached", timeout=10_000)
        still_pinned = await page.locator(".bf-cad-pin-card").count()
        if still_pinned < 1:
            raise AssertionError("empty click closed the drawer but should keep selected sensor callout pinned")

        second_sensor = await page.evaluate(
            """(firstId) => {
                const wrap = document.querySelector('.cad-insight-click-wrap');
                const v = window.__BF_CAD_FURNACE_VIEWER;
                const rect = wrap.getBoundingClientRect();
                const canvasRect = v.renderer.domElement.getBoundingClientRect();
                const blockers = Array.from(document.querySelectorAll('.bf-cad-pin-card,.var-insight-layer')).map(el => el.getBoundingClientRect());
                const insideBlocker = (x, y) => blockers.some(r => x >= r.left - 8 && x <= r.right + 8 && y >= r.top - 8 && y <= r.bottom + 8);
                const first = document.querySelector(`.bf-cad-pin-card[data-sensor-id="${firstId}"]`)?.getBoundingClientRect();
                const candidates = v.hitObjects.map(obj => {
                    const p = obj.position.clone().project(v.camera);
                    return {
                        id: obj.userData.sensorId,
                        x: canvasRect.left + (p.x + 1) * canvasRect.width / 2,
                        y: canvasRect.top + (1 - p.y) * canvasRect.height / 2,
                    };
                }).filter(p => p.id !== firstId && p.x > rect.left && p.x < rect.right && p.y > rect.top && p.y < rect.bottom && !insideBlocker(p.x, p.y));
                candidates.sort((a, b) => {
                    const da = first ? Math.hypot(a.x - first.left, a.y - first.top) : 0;
                    const db = first ? Math.hypot(b.x - first.left, b.y - first.top) : 0;
                    return db - da;
                });
                return candidates[0] || null;
            }""",
            sensor_points[0]["id"],
        )
        if not second_sensor:
            raise AssertionError("cannot find an uncovered second CAD sensor point for multi-select")
        await page.mouse.click(second_sensor["x"], second_sensor["y"])
        await page.wait_for_timeout(500)
        multi_pin_count = await page.locator(".bf-cad-pin-card").count()
        if multi_pin_count < 2:
            raise AssertionError(f"expected multiple CAD sensor callouts, got {multi_pin_count}")

        card_box = await page.locator(".bf-cad-pin-card").first.bounding_box()
        if not card_box:
            raise AssertionError("cannot measure first CAD pin card for drag test")
        before_transform = await page.locator(".bf-cad-pin-card").first.evaluate("el => getComputedStyle(el).transform")
        await page.mouse.move(card_box["x"] + 32, card_box["y"] + 16)
        await page.mouse.down()
        await page.mouse.move(card_box["x"] + 92, card_box["y"] + 58, steps=5)
        await page.mouse.up()
        await page.wait_for_timeout(300)
        drag_state = await page.locator(".bf-cad-pin-card").first.evaluate(
            """(el, before) => ({
                mode: el.dataset.mode,
                changed: getComputedStyle(el).transform !== before,
            })""",
            before_transform,
        )
        if drag_state["mode"] != "fixed" or not drag_state["changed"]:
            raise AssertionError(f"dragging CAD pin should switch it to fixed position, got {drag_state}")

        await page.screenshot(path=screenshot_dir / "variable_insight_overview_1440x900.png", full_page=True)
        await browser.close()

    serious_console = [msg for msg in console_errors if "Failed to fetch" not in msg]
    if page_errors:
        raise AssertionError(f"page errors during browser check: {page_errors}")
    if serious_console:
        raise AssertionError(f"console errors during browser check: {serious_console}")

    return {"browser": "ok", "url": url, "opened": opened, "screenshot_dir": str(screenshot_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify 8092 overview variable-insight interaction")
    parser.add_argument("--browser", action="store_true", help="Run Playwright click validation against a running 8092 frontend")
    parser.add_argument("--url", default=DEFAULT_URL, help="Frontend URL for browser validation")
    parser.add_argument("--screenshot-dir", default=str(ROOT / "logs" / "variable_insight_frontend"), help="Directory for browser screenshots")
    args = parser.parse_args()

    result = {"static": verify_static()}
    if args.browser:
        result["browser"] = asyncio.run(verify_browser(args.url, Path(args.screenshot_dir)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
