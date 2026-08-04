"""Verify the CAD GLB furnace model wiring used by the 8092 overview page.

对应需求：
- REQ-20260517-CAD-FURNACE-GLB：总览页使用 CAD 生成的 GL02 高炉 GLB 模型。

文档：
- docs/requirements_traceability.md#req-20260517-cad-furnace-glb-总览页cad高炉模型替换
- docs/test_reference.md#test-20260517-cad-furnace-glb-cad高炉模型前端验收
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import struct
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
GLB_PATH = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"
REALTIME_PREVIEW = ROOT / "高炉前端数据" / "models" / "sensor_realtime_preview.json"
INDUSTRIAL_TEXTURE_DIR = ROOT / "高炉前端数据" / "textures" / "industrial"
INDUSTRIAL_SCENE_CONFIG = ROOT / "高炉前端数据" / "config" / "industrial_furnace_scene.json"
INDUSTRIAL_TEXTURE_PROFILES = [
    "oxidized_coated_steel",
    "dark_aged_steel",
    "worn_galvanized_pipe",
    "refractory_brick",
    "concrete_floor",
    "steel_grating",
    "ash_dust",
    "heat_stained_metal",
    "slag_molten",
]
INDUSTRIAL_TEXTURE_SLOTS = ["basecolor", "normal", "roughness", "metalness", "ao"]
THREE_FILES = [
    ROOT / "高炉前端数据" / "libs" / "three" / "three.module.js",
    ROOT / "高炉前端数据" / "libs" / "three" / "controls" / "OrbitControls.js",
    ROOT / "高炉前端数据" / "libs" / "three" / "loaders" / "GLTFLoader.js",
    ROOT / "高炉前端数据" / "libs" / "three" / "utils" / "BufferGeometryUtils.js",
]


def read_glb_json(path: Path) -> dict:
    """Read the JSON chunk from a binary GLB file."""

    blob = path.read_bytes()
    magic, version, _length = struct.unpack("<4sII", blob[:12])
    if magic != b"glTF" or version != 2:
        raise AssertionError(f"{path} is not a glTF 2.0 GLB file")
    json_length, chunk_type = struct.unpack("<II", blob[12:20])
    if chunk_type != 0x4E4F534A:
        raise AssertionError(f"{path} first GLB chunk is not JSON")
    return json.loads(blob[20 : 20 + json_length].decode("utf-8"))


def verify_static_files() -> dict:
    """Check the static HTML, Three.js modules, GLB, ordered metrics, and preview payload."""

    html = FRONTEND_HTML.read_text(encoding="utf-8")
    required_html_tokens = [
        "function CadFurnaceViewer",
        "models/gl02_blast_furnace.glb",
        "cad-furnace-viewer",
        "hitObjects",
        "mappedCount",
        "overview-cad-grid",
        "v4-overview-right-fit",
        "compact-core-metrics",
        "legacy-furnace-scene",
        "three.module.js",
        "GLTFLoader.js",
        "bfCadTextureKit",
        "bfCadApplyMaterial",
        "roughnessMap",
        "aoMap",
        "metalnessMap",
        "texturedMeshCount",
        "materialProfiles",
        "v4-industrial-texture-polish",
        "bfPolishChartOption",
        "BF_INDUSTRIAL_PBR",
        "BF_INDUSTRIAL_SCENE_CONFIG_URL",
        "bfLoadIndustrialSceneConfig",
        "bfIndustrialTextureKit",
        "bfIndustrialMeshProfile",
        "BFIndustrialCadFurnaceViewer",
        "industrialPbr",
        "shadowMap.enabled=bfCfgBool",
        "cameraConstrained",
        "cad-industrial-toolbar",
        "cad-industrial-label",
        "furnaceFront",
        "stockline",
    ]
    missing = [token for token in required_html_tokens if token not in html]
    if missing:
        raise AssertionError(f"frontend HTML is missing CAD viewer tokens: {missing}")

    for path in [GLB_PATH, REALTIME_PREVIEW, INDUSTRIAL_SCENE_CONFIG, *THREE_FILES]:
        if not path.exists():
            raise AssertionError(f"required frontend asset missing: {path}")
    scene_config = json.loads(INDUSTRIAL_SCENE_CONFIG.read_text(encoding="utf-8"))
    for required_path in [
        ("renderer", "toneMappingExposure"),
        ("lights", "hemisphere", "intensity"),
        ("lights", "top", "intensity"),
        ("lights", "side", "intensity"),
        ("canvas", "filter"),
        ("camera", "fov"),
        ("labels", "backgroundOpacity"),
    ]:
        cur = scene_config
        for key in required_path:
            cur = cur.get(key, {})
        if not isinstance(cur, dict) or "value" not in cur or "comment" not in cur:
            raise AssertionError(f"scene config parameter is missing value/comment: {'.'.join(required_path)}")

    texture_missing = []
    for profile in INDUSTRIAL_TEXTURE_PROFILES:
        for slot in INDUSTRIAL_TEXTURE_SLOTS:
            texture_path = INDUSTRIAL_TEXTURE_DIR / f"{profile}_{slot}.png"
            if not texture_path.exists():
                texture_missing.append(str(texture_path.relative_to(ROOT)))
        if profile == "slag_molten" and not (INDUSTRIAL_TEXTURE_DIR / "slag_molten_emissive.png").exists():
            texture_missing.append(str((INDUSTRIAL_TEXTURE_DIR / "slag_molten_emissive.png").relative_to(ROOT)))
    manifest_path = INDUSTRIAL_TEXTURE_DIR / "industrial_pbr_manifest.json"
    if not manifest_path.exists():
        texture_missing.append(str(manifest_path.relative_to(ROOT)))
    if texture_missing:
        raise AssertionError(f"industrial PBR texture assets are missing: {texture_missing[:12]}")

    gltf = read_glb_json(GLB_PATH)
    node_names = [node.get("name", "") for node in gltf.get("nodes", [])]
    sensor_nodes = [node for node in gltf.get("nodes", []) if node.get("name", "").startswith("SENSOR_")]
    required_nodes = [
        "APPROX_GL02_furnace_shell",
        "APPROX_GL02_FURNACE_HEARTH",
        "APPROX_GL02_FURNACE_BOSH",
        "APPROX_GL02_FURNACE_BELLY",
        "APPROX_GL02_FURNACE_SHAFT",
        "APPROX_GL02_FURNACE_THROAT",
        "APPROX_GL02_bustle_pipe_and_tuyere_stocks",
        "APPROX_GL02_two_physical_tapholes",
        "APPROX_GL02_TAPHole_1_prominent_outlet",
        "APPROX_GL02_TAPHole_2_prominent_outlet",
    ]
    missing_nodes = [name for name in required_nodes if name not in node_names]
    if missing_nodes:
        raise AssertionError(f"GLB is missing expected CAD nodes: {missing_nodes}")
    forbidden_nodes = [name for name in node_names if "TAPHole_3" in name]
    if forbidden_nodes:
        raise AssertionError(f"GLB must not contain removed third taphole nodes: {forbidden_nodes}")
    if len(sensor_nodes) != 115:
        raise AssertionError(f"expected 115 SENSOR_ nodes, got {len(sensor_nodes)}")
    layer_groups = [node for node in gltf.get("nodes", []) if node.get("name", "").startswith("GL02_SENSOR_LAYER_L")]
    if len(layer_groups) != 10 or any(len(node.get("children", [])) != 8 for node in layer_groups):
        raise AssertionError("expected L7-L16 sensor layer groups with exactly 8 child sensors each")
    bad_scale = [node.get("name") for node in sensor_nodes if node.get("scale") != [0.115, 0.115, 0.115]]
    if bad_scale:
        raise AssertionError(f"sensor node scale is not 0.115 for: {bad_scale[:8]}")

    sensor_ids = sorted(node["name"][len("SENSOR_") :] for node in sensor_nodes)
    frontend_rows = set(
        match.group(1)
        for match in re.finditer(r"\['([^']+)','[^']*','[^']*'\]", html.split("const ALL_ROWS=", 1)[0])
    )
    missing_rows = sorted(set(sensor_ids) - frontend_rows)
    if missing_rows:
        raise AssertionError(f"GLB sensor ids are not registered in frontend CATS: {missing_rows[:12]}")

    core_match = re.search(r"const CORE_METRIC_ITEMS=\[(.*?)\];", html)
    if not core_match:
        raise AssertionError("CORE_METRIC_ITEMS ordered core metric list not found")
    core_block = core_match.group(1)
    required_core_tokens = [
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
    missing_core = [token for token in required_core_tokens if token not in core_block]
    if missing_core:
        raise AssertionError(f"core metrics must include requested ordered tokens; missing={missing_core}")

    nav_match = re.search(r"const NAVS=\[(.*?)\];", html)
    if not nav_match or "reports" in nav_match.group(1) or "报表预览" in nav_match.group(1):
        raise AssertionError("report preview must be removed from bottom navigation")
    if "window.location.hash='reports'" in html or "window.location.hash=\"reports\"" in html:
        raise AssertionError("report preview hash entry must not remain in active UI wiring")
    if "QaSourcesPanel=function BFQaSourcesPanelRemoved(){return null};" not in html:
        raise AssertionError("QA source/report list panel must be disabled")
    if "v4-qa-remove-source-panel" not in html:
        raise AssertionError("QA two-column layout override is missing")

    preview = json.loads(REALTIME_PREVIEW.read_text(encoding="utf-8"))
    if len(preview.get("values", {})) != 115:
        raise AssertionError("sensor realtime preview payload must contain 115 values")

    return {
        "glb": str(GLB_PATH.relative_to(ROOT)),
        "sensor_nodes": len(sensor_nodes),
        "sensor_layer_groups": len(layer_groups),
        "furnace_process_zones": 5,
        "frontend_sensor_rows": len(set(sensor_ids) & frontend_rows),
        "core_metrics": len(required_core_tokens),
        "sensor_scale": 0.115,
        "preview_values": len(preview.get("values", {})),
        "three_modules": len(THREE_FILES),
        "industrial_texture_profiles": len(INDUSTRIAL_TEXTURE_PROFILES),
        "industrial_texture_slots": len(INDUSTRIAL_TEXTURE_SLOTS),
        "scene_config": str(INDUSTRIAL_SCENE_CONFIG.relative_to(ROOT)),
    }


def verify_http(base_url: str) -> dict:
    """Optionally verify that the running 8092 server exposes the CAD assets."""

    checks = {
        "html": f"{base_url.rstrip('/')}/frontend_dashboard_v3.server.html?ws_port=8767",
        "glb": f"{base_url.rstrip('/')}/models/gl02_blast_furnace.glb",
        "three": f"{base_url.rstrip('/')}/libs/three/three.module.js",
    }
    result: dict[str, int] = {}
    for key, url in checks.items():
        with urllib.request.urlopen(url, timeout=8) as response:
            if response.status != 200:
                raise AssertionError(f"{url} returned HTTP {response.status}")
            result[key] = int(response.headers.get("Content-Length") or 0)
    return result


async def verify_browser(base_url: str, screenshot: str = "") -> dict:
    """Verify the live 8092 page renders CAD layout, ordered metrics, and hover values."""

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on local dev environment.
        raise AssertionError("playwright is required for --browser validation") from exc

    url = f"{base_url.rstrip('/')}/frontend_dashboard_v3.server.html?ws_port=8767"
    page_errors: list[str] = []
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1365, "height": 768})
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_selector(".overview-cad-grid", timeout=60_000)
        await page.wait_for_function(
            "window.__BF_CAD_FURNACE_VIEWER && window.__BF_CAD_FURNACE_VIEWER.sensorCount===115",
            timeout=60_000,
        )
        await page.wait_for_timeout(1500)
        info = await page.evaluate(
            """() => {
              const v=window.__BF_CAD_FURNACE_VIEWER||{};
              const right=document.querySelector('.overview-right.rebalanced');
              const panels=[...document.querySelectorAll('.overview-right.rebalanced > .panel')].map(panel => {
                const body=panel.querySelector('.panel-body');
                const title=panel.querySelector('.panel-title')?.textContent?.trim() || '';
                return {
                  title,
                  panelClientHeight: panel.clientHeight,
                  panelScrollHeight: panel.scrollHeight,
                  bodyClientHeight: body ? body.clientHeight : 0,
                  bodyScrollHeight: body ? body.scrollHeight : 0,
                  fits: panel.scrollHeight <= panel.clientHeight + 3 && (!body || body.scrollHeight <= body.clientHeight + 3)
                };
              });
              return {
                hash: location.hash,
                active: document.querySelector('.nav-btn.active')?.innerText || '',
                nav: [...document.querySelectorAll('.bottom-nav .nav-btn')].map(e=>e.innerText.replace(/\\s+/g,' ').trim()),
                status: getComputedStyle(document.querySelector('.cad-furnace-status')).display,
                sensorCount: v.sensorCount,
                hitCount: v.hitCount,
                mappedCount: v.mappedCount,
                texturedMeshCount: v.texturedMeshCount || 0,
                materialProfiles: v.materialProfiles || {},
                industrialPbr: !!v.industrialPbr || document.querySelector('.cad-furnace-viewer')?.dataset.industrialPbr === 'true',
                textureBase: v.textureBase || '',
                sceneConfigUrl: v.sceneConfigUrl || document.querySelector('.cad-furnace-viewer')?.dataset.sceneConfig || '',
                configuredExposure: v.renderer?.toneMappingExposure || 0,
                shadowEnabled: !!v.shadowEnabled || document.querySelector('.cad-furnace-viewer')?.dataset.shadowEnabled === 'true',
                cameraConstrained: !!v.cameraConstrained || document.querySelector('.cad-furnace-viewer')?.dataset.cameraConstrained === 'true',
                labelCount: v.labelCount || document.querySelectorAll('.cad-industrial-label').length,
                viewLabels: [...document.querySelectorAll('.cad-industrial-toolbar button')].map(e => e.textContent.trim()),
                currentView: document.querySelector('.cad-furnace-viewer')?.dataset.currentView || '',
                rendererShadowEnabled: !!v.renderer?.shadowMap?.enabled,
                controls: v.controls ? {
                  enablePan: v.controls.enablePan,
                  minDistance: v.controls.minDistance,
                  maxDistance: v.controls.maxDistance,
                  minPolarAngle: v.controls.minPolarAngle,
                  maxPolarAngle: v.controls.maxPolarAngle
                } : null,
                whiteMaterialPolicy: v.whiteMaterialPolicy || document.querySelector('.cad-furnace-viewer')?.dataset.whiteMaterialPolicy || '',
                shellMaterialPolicy: v.shellMaterialPolicy || document.querySelector('.cad-furnace-viewer')?.dataset.shellMaterialPolicy || '',
                realisticTexturePolicy: window.__BF_CAD_REALISTIC_TEXTURE_POLICY || '',
                realisticTextureMaps: window.__BF_CAD_REALISTIC_TEXTURE_MAPS || [],
                realisticTexturedMeshes: window.__BF_CAD_REALISTIC_TEXTURED_MESHES || 0,
                realisticProfileCounts: window.__BF_CAD_REALISTIC_PROFILE_COUNTS || {},
                opaqueShellPolicy: window.__BF_CAD_OPAQUE_SHELL_POLICY || '',
                opaqueShellMeshes: window.__BF_CAD_OPAQUE_SHELL_MESHES || 0,
                opaqueShellMaterials: window.__BF_CAD_OPAQUE_SHELL_MATERIALS || [],
                coreCount: document.querySelectorAll('.core-metric-board .core-metric-cell,.compact-core-metrics .metric-row').length,
                coreNames: [...document.querySelectorAll('.core-metric-board .core-cell-name,.compact-core-metrics .metric-name')].map(e => e.textContent.trim()),
                industrialTextureStyle: !!document.getElementById('v4-industrial-texture-polish'),
                industrialPbrStyle: !!document.getElementById('v4-industrial-pbr-furnace-scene'),
                sparkBackground: document.querySelector('.compact-core-metrics .spark') ? getComputedStyle(document.querySelector('.compact-core-metrics .spark')).backgroundImage : '',
                canvasFilter: getComputedStyle(document.querySelector('.cad-furnace-viewer canvas')).filter,
                hasRightTrend: !!document.querySelector('.overview-right.rebalanced .right-trend-panel'),
                rightPanelFits: !!right && right.scrollHeight <= right.clientHeight + 3 && panels.every(panel => panel.fits),
                rightPanelOverflow: panels.filter(panel => !panel.fits),
                rightPanelCount: panels.length
              };
            }"""
        )
        if screenshot:
            Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=screenshot, full_page=True)
        coord = await page.evaluate(
            """() => {
              const v=window.__BF_CAD_FURNACE_VIEWER;
              const obj=v.hitObjects.find(o=>o.userData.sensorId==='TFT') || v.hitObjects[0];
              const p=obj.position.clone().project(v.camera);
              const r=v.renderer.domElement.getBoundingClientRect();
              return {id: obj.userData.sensorId, x: r.left + (p.x+1)*r.width/2, y: r.top + (1-p.y)*r.height/2};
            }"""
        )
        await page.mouse.move(coord["x"], coord["y"])
        await page.wait_for_timeout(600)
        tooltip = await page.evaluate(
            """() => {
              const el=document.querySelector('.cad-furnace-tooltip');
              return {display:getComputedStyle(el).display, text:el.innerText};
            }"""
        )
        qa_page = await browser.new_page(viewport={"width": 1280, "height": 720})
        qa_page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        await qa_page.goto(f"{base_url.rstrip('/')}/frontend_dashboard_v3.server.html?ws_port=8767#qa", wait_until="domcontentloaded", timeout=60_000)
        await qa_page.wait_for_selector(".qa-project-shell", timeout=60_000)
        qa_info = await qa_page.evaluate(
            """() => {
              const shell=document.querySelector('.qa-project-shell');
              const styles=shell ? getComputedStyle(shell) : null;
              const exactTexts=[...document.querySelectorAll('*')].map(el=>(el.textContent||'').trim()).filter(Boolean);
              return {
                sourcePanelCount: document.querySelectorAll('.qa-source-panel').length,
                hasSourceTitle: exactTexts.includes('来源'),
                hasLibraryTitle: exactTexts.includes('资料库'),
                hasShortQueueTab: [...document.querySelectorAll('button')].some(el=>(el.textContent||'').includes('短时队列')),
                hasChat: !!document.querySelector('.qa-server-chat'),
                gridTemplateColumns: styles ? styles.gridTemplateColumns : ''
              };
            }"""
        )
        await browser.close()

    if page_errors:
        raise AssertionError(f"browser page errors: {page_errors[:3]}")
    if info["sensorCount"] != 115 or info["hitCount"] != 115 or info["mappedCount"] != 115:
        raise AssertionError(f"CAD viewer sensor/hit/mapping counts are wrong: {info}")
    if info["texturedMeshCount"] < 20:
        raise AssertionError(f"CAD non-sensor meshes were not textured enough: {info}")
    if not info["industrialPbr"] or info["textureBase"] != "textures/industrial/":
        raise AssertionError(f"industrial PBR texture kit did not apply: {info}")
    if info["sceneConfigUrl"] != "config/industrial_furnace_scene.json":
        raise AssertionError(f"industrial scene config was not loaded: {info}")
    required_profiles = {
        "oxidized_coated_steel",
        "dark_aged_steel",
        "worn_galvanized_pipe",
        "steel_grating",
        "slag_molten",
    }
    missing_profiles = sorted(required_profiles - set(info["materialProfiles"]))
    if missing_profiles:
        raise AssertionError(f"CAD industrial material profiles are missing: {missing_profiles}; info={info}")
    if not info["shadowEnabled"] or not info["rendererShadowEnabled"]:
        raise AssertionError(f"CAD shadow map is not enabled: {info}")
    if not info["cameraConstrained"] or not info["controls"] or info["controls"]["enablePan"]:
        raise AssertionError(f"CAD camera constraints did not apply: {info}")
    if info["controls"]["minPolarAngle"] < 0.4 or info["controls"]["maxPolarAngle"] > 1.5:
        raise AssertionError(f"CAD camera polar angle limits are too loose: {info}")
    expected_views = ["总览", "炉前", "平台", "围管", "出铁口", "料线"]
    if info["viewLabels"] != expected_views or info["currentView"] != "overview":
        raise AssertionError(f"CAD controlled view presets are wrong: {info}")
    if info["labelCount"] < 8:
        raise AssertionError(f"CAD anchored industrial labels did not render: {info}")
    if (
        not info["industrialTextureStyle"]
        or not info["industrialPbrStyle"]
        or "drop-shadow" not in info["canvasFilter"]
    ):
        raise AssertionError(f"industrial micro-chart texture style did not apply: {info}")
    expected_core_names = [
        "综合顶压",
        "顶压A",
        "顶压B",
        "顶压C",
        "顶压D",
        "煤气利用率",
        "理论燃烧温度",
        "热风温度",
        "顶温A",
        "顶温B",
        "顶温C",
        "顶温D",
        "冷风流量",
        "冷风压力",
        "热风压力",
        "富氧率",
        "富氧流量",
        "透气性指数",
        "上部压差",
        "下部压差",
        "总压差",
        "雷达探尺",
        "南尺",
        "北尺",
        "喷煤率",
        "喷煤设定",
        "1#铁口温度参考",
        "2#铁口温度参考",
    ]
    if info["coreCount"] != len(expected_core_names) or info["coreNames"] != expected_core_names:
        raise AssertionError(f"core metric order is wrong: {info.get('coreNames')}")
    if "报表预览" in "".join(info["nav"]):
        raise AssertionError("report preview is still visible in bottom navigation")
    if info["status"] == "none":
        raise AssertionError("CAD industrial status bar should be visible")
    if not info["hasRightTrend"]:
        raise AssertionError("trend/timeline panel was not moved into the right column")
    if not info["rightPanelFits"] or info["rightPanelCount"] != 4:
        raise AssertionError(f"overview right column panels overflow or are incomplete: {info}")
    if tooltip["display"] == "none" or "暂无实时值" in tooltip["text"]:
        raise AssertionError(f"CAD hover tooltip did not show a live value: {tooltip}")
    if qa_info["sourcePanelCount"] or qa_info["hasSourceTitle"] or qa_info["hasLibraryTitle"]:
        raise AssertionError(f"QA source/report list panel is still visible: {qa_info}")
    if not qa_info["hasShortQueueTab"] or not qa_info["hasChat"]:
        raise AssertionError(f"QA core chat UI did not render after removing source panel: {qa_info}")
    return {"page": info, "qa": qa_info, "hover_target": coord, "tooltip": tooltip}


def main() -> int:
    """CLI entrypoint for reproducible CAD frontend validation."""

    parser = argparse.ArgumentParser(description="Validate the 8092 CAD GLB furnace frontend wiring.")
    parser.add_argument("--base-url", default="", help="Optional running 8092 base URL, for example http://127.0.0.1:8092")
    parser.add_argument("--browser", action="store_true", help="Also validate the live overview page with Playwright.")
    parser.add_argument("--screenshot", default="", help="Optional screenshot path when --browser is enabled.")
    args = parser.parse_args()
    result = {"static": verify_static_files()}
    if args.base_url:
        result["http"] = verify_http(args.base_url)
        if args.browser:
            result["browser"] = asyncio.run(verify_browser(args.base_url, args.screenshot))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("CAD furnace frontend validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
