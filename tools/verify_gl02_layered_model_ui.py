"""Verify the GL02 layered model controls against a running 8092 page."""

from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GL02 process-zone and enabled L7-L16 browser controls.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8092")
    parser.add_argument(
        "--page-path",
        default="/",
        help="Page path served below base-url; use /frontend_dashboard_v3.server.html for a plain static server.",
    )
    parser.add_argument(
        "--allow-offline-data-source",
        action="store_true",
        help="Ignore the known 8092 API/WebSocket network errors when validating a plain static page.",
    )
    parser.add_argument("--ws-port", type=int, default=8767)
    args = parser.parse_args()
    page_path = "/" + args.page_path.strip("/")
    if args.page_path.rstrip("/") == "":
        page_path = "/"
    url = f"{args.base_url.rstrip('/')}{page_path}?ws_port={args.ws_port}#overview"
    page_errors: list[str] = []
    console_errors: list[str] = []
    http_errors: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on(
            "response",
            lambda response: http_errors.append(
                {"status": response.status, "url": response.url}
            )
            if response.status >= 400
            else None,
        )
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_function(
            "window.__BF_CAD_FURNACE_VIEWER && window.__BF_CAD_FURNACE_VIEWER.sensorCount===115",
            timeout=60_000,
        )
        page.wait_for_selector(".cad-layer-controls", timeout=15_000)
        enabled_layers = page.locator('button[data-kind="layer"]').evaluate_all(
            "buttons => buttons.map(button => button.dataset.id)"
        )
        cutaway_buttons = page.locator("button[data-cutaway-action]").evaluate_all(
            "buttons => buttons.map(button => ({action:button.dataset.cutawayAction,label:button.textContent,disabled:button.disabled}))"
        )
        exterior_before = page.evaluate(
            """() => {
              const viewer=window.__BF_CAD_FURNACE_VIEWER,state=viewer.getCutawayState();
              return {
                state,
                host:{
                  mode:document.querySelector('.cad-furnace-viewer')?.dataset.cutawayMode,
                  phase:document.querySelector('.cad-furnace-viewer')?.dataset.cutawayPhase,
                  internalCount:Number(document.querySelector('.cad-furnace-viewer')?.dataset.internalCount||-1)
                },
                visibleInternal:state.internalPrefixes.reduce((count,prefix)=>{
                  viewer.model.traverse(object=>{const name=String(object.name||'').toLowerCase().replace(/^approx_gl02_/,'');if(object.isMesh&&name.startsWith(prefix)&&object.visible)count++});
                  return count;
                },0)
              };
            }"""
        )
        page.locator('button[data-cutaway-action="cutaway"]').click()
        page.wait_for_timeout(220)
        cutaway_enter = page.evaluate(
            """() => ({
              state:window.__BF_CAD_FURNACE_VIEWER.getCutawayState(),
              status:document.querySelector('.cad-cutaway-status')?.textContent || '',
              active:document.querySelector('button[data-cutaway-action="cutaway"]')?.classList.contains('active')
            })"""
        )
        page.wait_for_timeout(1450)
        cutaway_playing = page.evaluate(
            "() => window.__BF_CAD_FURNACE_VIEWER.getCutawayState()"
        )
        page.locator('button[data-cutaway-action="play"]').click()
        page.wait_for_timeout(80)
        cutaway_paused = page.evaluate(
            """() => ({
              state:window.__BF_CAD_FURNACE_VIEWER.getCutawayState(),
              label:document.querySelector('button[data-cutaway-action="play"]')?.textContent,
              pressed:document.querySelector('button[data-cutaway-action="play"]')?.getAttribute('aria-pressed')
            })"""
        )
        cutaway_reuse = page.evaluate(
            """() => {
              const viewer=window.__BF_CAD_FURNACE_VIEWER,before=viewer.getCutawayState();
              for(let index=0;index<20;index++){viewer.setCutawayMode('exterior');viewer.setCutawayMode('cutaway')}
              viewer.setCutawayMode('exterior');
              return {before,after:viewer.getCutawayState()};
            }"""
        )
        page.locator('button[data-cutaway-action="cutaway"]').click()
        page.wait_for_timeout(40)
        page.locator('button[data-cutaway-action="reset"]').click()
        page.wait_for_timeout(80)
        cutaway_reset = page.evaluate(
            """() => ({
              state:window.__BF_CAD_FURNACE_VIEWER.getCutawayState(),
              exteriorActive:document.querySelector('button[data-cutaway-action="exterior"]')?.classList.contains('active'),
              visibleInternal:Number(document.querySelector('.cad-furnace-viewer')?.dataset.internalVisibleCount||-1)
            })"""
        )
        page.locator('button[data-kind="layer"][data-id="L9"]').click()
        page.wait_for_timeout(180)
        l9_enter = page.evaluate("() => window.__BF_CAD_FURNACE_VIEWER.getLayerHighlightState()")
        layer_cases: dict[str, dict] = {}
        for layer_number in range(7, 17):
            layer_id = f"L{layer_number}"
            page.locator(
                f'button[data-kind="layer"][data-id="{layer_id}"]'
            ).click()
            page.wait_for_timeout(30)
            layer_cases[layer_id] = page.evaluate(
                """layerId => ({
                  status: document.querySelector('.cad-layer-selection-status')?.textContent || '',
                  visible: Number(document.querySelector('.cad-furnace-viewer')?.dataset.visibleSensors || -1),
                  names: window.__BF_CAD_FURNACE_VIEWER.sensorObjects
                    .filter(object => object.visible && object.name.startsWith('SENSOR_T_body_'))
                    .map(object => object.name),
                  highlight: window.__BF_CAD_FURNACE_VIEWER.getLayerHighlightState(),
                  sourceAttr: document.querySelector('.cad-furnace-viewer')?.dataset.highlightSource || '',
                  requested: layerId
                })""",
                layer_id,
            )
        page.wait_for_timeout(1800)
        l16_highlight = page.evaluate("() => window.__BF_CAD_FURNACE_VIEWER.getLayerHighlightState()")
        source_contract = page.evaluate(
            """() => {
              const viewer=window.__BF_CAD_FURNACE_VIEWER,state=viewer.getLayerHighlightState();
              return {
                source:state.source,
                sourceAttr:document.querySelector('.cad-furnace-viewer')?.dataset.highlightSource || '',
                embeddedBandCount:state.embeddedBandCount,
                exposedBandCount:viewer.layerBandObjects?.length || 0,
                cachedGeometryCount:state.cachedGeometryCount,
                visibleSlotCount:state.visibleSlotCount,
                objectCount:state.objectCount
              };
            }"""
        )
        page.locator('button[data-kind="zone"][data-id="SHAFT"]').click()
        page.wait_for_timeout(300)
        shaft = page.evaluate(
            """() => {
              const viewer=window.__BF_CAD_FURNACE_VIEWER;
              let root=viewer.sensorObjects[0]; while(root.parent) root=root.parent;
              return {
                status: document.querySelector('.cad-layer-selection-status')?.textContent || '',
                visible: Number(document.querySelector('.cad-furnace-viewer')?.dataset.visibleSensors || -1),
                shaft: root.getObjectByName('APPROX_GL02_FURNACE_SHAFT')?.visible,
                hearth: root.getObjectByName('APPROX_GL02_FURNACE_HEARTH')?.visible
              };
            }"""
        )
        material = page.evaluate(
            """() => {
              const v=window.__BF_CAD_FURNACE_VIEWER;
              let root=v.sensorObjects[0]; while(root.parent && root.parent.type!=='Scene') root=root.parent;
              let sample=null; root.traverse(o=>{if(!sample && o.isMesh && /^APPROX_GL02_FURNACE_/.test(o.name) && o.material) sample=o.material});
              const contract=v.getCutawayState().shellMaterialContract;
              return sample ? {roughness:sample.roughness,metalness:sample.metalness,opacity:sample.opacity,transparent:sample.transparent,depthWrite:sample.depthWrite,hasMap:!!sample.map,hasRoughnessMap:!!sample.roughnessMap,hasMetalnessMap:!!sample.metalnessMap,hasAoMap:!!sample.aoMap,hasNormalMap:!!sample.normalMap,hasBumpMap:!!sample.bumpMap,contract} : null;
            }"""
        )
        tone_cases = page.evaluate(
            """() => {
              const oldBuf=window.__BF_CAD_TOOLTIP_BUF__,oldBase=window.__BF_CORE_BASELINE_30D__;
              const ids='ABCDEFGH'.split('').map(s=>`T_body_L7_${s}`),make=(value,z=0)=>{
                const buf={},base={}; ids.forEach(id=>{buf[id]=[value];base[id]={median:value-z*10,iqr:10}});
                window.__BF_CAD_TOOLTIP_BUF__=buf;window.__BF_CORE_BASELINE_30D__=base;
                return window.__BF_CAD_LAYER_VISUALS.visualState('L7').tone;
              };
              const result={normal:make(100,0),warn:make(106,.6),bad:make(116,1.6)};
              window.__BF_CAD_TOOLTIP_BUF__={};window.__BF_CORE_BASELINE_30D__={};result.nodata=window.__BF_CAD_LAYER_VISUALS.visualState('L7').tone;
              window.__BF_CAD_TOOLTIP_BUF__=oldBuf;window.__BF_CORE_BASELINE_30D__=oldBase;return result;
            }"""
        )
        reuse = page.evaluate(
            """() => {
              const v=window.__BF_CAD_FURNACE_VIEWER,before=v.getLayerHighlightState();
              for(let i=0;i<100;i++)v.highlightLayer(`L${7+i%10}`);
              return {before,immediate:v.getLayerHighlightState()};
            }"""
        )
        page.wait_for_timeout(180)
        reuse["settled"] = page.evaluate(
            "() => window.__BF_CAD_FURNACE_VIEWER.getLayerHighlightState()"
        )
        idempotent = page.evaluate(
            """() => {
              const v=window.__BF_CAD_FURNACE_VIEWER,before=v.getLayerHighlightState();
              v.highlightLayer(before.layerId);
              return {before,after:v.getLayerHighlightState()};
            }"""
        )
        page.locator('button[data-kind="all"][data-id="all"]').click()
        page.wait_for_timeout(180)
        cleared = page.evaluate("() => window.__BF_CAD_FURNACE_VIEWER.getLayerHighlightState()")
        browser.close()
    if enabled_layers != [f"L{i}" for i in range(7, 17)]:
        raise AssertionError(f"enabled layer range failed: {enabled_layers}")
    if [button["action"] for button in cutaway_buttons] != [
        "exterior",
        "cutaway",
        "play",
        "reset",
    ]:
        raise AssertionError(f"cutaway controls failed: {cutaway_buttons}")
    if (
        exterior_before["state"]["mode"] != "exterior"
        or exterior_before["state"]["phase"] != "off"
        or exterior_before["state"]["playing"]
        or exterior_before["state"]["internalCount"] != 45
        or "hot_metal_dripping_"
        not in exterior_before["state"]["internalPrefixes"]
        or exterior_before["state"]["clippedMaterialCount"]
        < exterior_before["state"]["shellMaterialCount"]
        or not all(
            exterior_before["state"]["shellMaterialContract"].get(field)
            for field in (
                "preservedBaseColorMaps",
                "preservedRoughnessMaps",
                "preservedMetalnessMaps",
                "preservedAoMaps",
                "preservedNormalMaps",
                "factorPolicyApplied",
            )
        )
        or exterior_before["visibleInternal"] != 0
        or exterior_before["host"]["mode"] != "exterior"
        or exterior_before["host"]["internalCount"]
        != exterior_before["state"]["internalCount"]
    ):
        raise AssertionError(f"default exterior contract failed: {exterior_before}")
    if (
        cutaway_enter["state"]["mode"] != "cutaway"
        or cutaway_enter["state"]["phase"] != "cutting"
        or not cutaway_enter["state"]["playing"]
        or not 0 < cutaway_enter["state"]["cutProgress"] < 1
        or "工艺示意，非实时断面测量" not in cutaway_enter["status"]
        or not cutaway_enter["active"]
    ):
        raise AssertionError(f"cutaway enter animation failed: {cutaway_enter}")
    if (
        cutaway_playing["mode"] != "cutaway"
        or cutaway_playing["phase"] != "playing"
        or not cutaway_playing["playing"]
        or cutaway_playing["cutProgress"] != 1
        or cutaway_playing["revealProgress"] != 1
        or cutaway_playing["visibleInternalCount"]
        != cutaway_playing["internalCount"]
    ):
        raise AssertionError(f"cutaway reveal sequence failed: {cutaway_playing}")
    if (
        cutaway_paused["state"]["phase"] != "paused"
        or cutaway_paused["state"]["playing"]
        or cutaway_paused["label"] != "播放"
        or cutaway_paused["pressed"] != "false"
    ):
        raise AssertionError(f"cutaway pause failed: {cutaway_paused}")
    for field in (
        "objectCount",
        "materialCount",
        "internalCount",
        "shellMaterialCount",
        "clippedMaterialCount",
    ):
        if cutaway_reuse["before"][field] != cutaway_reuse["after"][field]:
            raise AssertionError(
                f"cutaway resource reuse failed for {field}: {cutaway_reuse}"
            )
    if (
        cutaway_reset["state"]["mode"] != "exterior"
        or cutaway_reset["state"]["phase"] != "off"
        or cutaway_reset["state"]["playing"]
        or cutaway_reset["visibleInternal"] != 0
        or not cutaway_reset["exteriorActive"]
    ):
        raise AssertionError(f"cutaway reset failed: {cutaway_reset}")
    expected_heights = {
        "L7": 16.860,
        "L8": 18.335,
        "L9": 20.125,
        "L10": 21.860,
        "L11": 23.711,
        "L12": 25.441,
        "L13": 27.171,
        "L14": 28.901,
        "L15": 30.631,
        "L16": 32.361,
    }
    for layer_id, height in expected_heights.items():
        case = layer_cases[layer_id]
        expected_names = [
            f"SENSOR_T_body_{layer_id}_{sector}" for sector in "ABCDEFGH"
        ]
        if case["visible"] != 8 or case["names"] != expected_names:
            raise AssertionError(f"{layer_id} filter failed: {case}")
        if case["highlight"]["layerId"] != layer_id or abs(
            case["highlight"]["y"] - (height - 20)
        ) > 1e-6:
            raise AssertionError(f"{layer_id} highlight height failed: {case}")
        if case["sourceAttr"] != case["highlight"]["source"]:
            raise AssertionError(f"{layer_id} highlight source attribute failed: {case}")
    if l9_enter["phase"] != "enter" or not 1.0 < l9_enter["scale"] <= 1.12:
        raise AssertionError(f"L9 enter animation failed: {l9_enter}")
    if l16_highlight["phase"] != "pulse" or not 1.02 <= l16_highlight["scale"] <= 1.06:
        raise AssertionError(f"L16 pulse animation failed: {l16_highlight}")
    if abs(l16_highlight["y"] - 12.361) > 1e-6:
        raise AssertionError(f"highlight geometry contract failed: {l16_highlight}")
    if (
        abs(l16_highlight["bounds"]["lower"] - 31.496) > 1e-6
        or abs(l16_highlight["bounds"]["upper"] - 33.226) > 1e-6
    ):
        raise AssertionError(f"L16 band boundary contract failed: {l16_highlight}")
    if source_contract["source"] not in {"embedded", "procedural"}:
        raise AssertionError(f"invalid highlight source: {source_contract}")
    if source_contract["sourceAttr"] != source_contract["source"]:
        raise AssertionError(f"highlight source dataset failed: {source_contract}")
    if source_contract["source"] == "embedded":
        if (
            source_contract["embeddedBandCount"] != 10
            or source_contract["exposedBandCount"] != 10
            or source_contract["cachedGeometryCount"] != 0
        ):
            raise AssertionError(f"embedded P36 contract failed: {source_contract}")
    elif (
        source_contract["embeddedBandCount"] >= 10
        or source_contract["cachedGeometryCount"] != 10
    ):
        raise AssertionError(f"procedural fallback cache failed: {source_contract}")
    if source_contract["visibleSlotCount"] != 1:
        raise AssertionError(f"settled slot visibility failed: {source_contract}")
    if not material or not (
        (.72 <= material["roughness"] <= .80 or abs(material["roughness"] - 1) < .001)
        and (.32 <= material["metalness"] <= .42 or abs(material["metalness"] - 1) < .001)
        and abs(material["opacity"] - 1) < .001
        and material["transparent"] is False
        and material["depthWrite"] is True
        and material["hasRoughnessMap"]
        and (material["hasNormalMap"] or material["hasBumpMap"])
        and material["contract"]["preservedBaseColorMaps"]
        and material["contract"]["preservedRoughnessMaps"]
        and material["contract"]["preservedMetalnessMaps"]
        and material["contract"]["preservedAoMaps"]
        and material["contract"]["preservedNormalMaps"]
        and material["contract"]["factorPolicyApplied"]
    ):
        raise AssertionError(f"matte shell material failed: {material}")
    if tone_cases != {"normal": "normal", "warn": "warn", "bad": "bad", "nodata": "nodata"}:
        raise AssertionError(f"layer tone mapping failed: {tone_cases}")
    for field in ("objectCount", "cachedGeometryCount", "embeddedBandCount", "source"):
        if reuse["before"][field] != reuse["settled"][field]:
            raise AssertionError(f"highlight resource reuse failed for {field}: {reuse}")
    if reuse["settled"]["transitionId"] - reuse["before"]["transitionId"] != 100:
        raise AssertionError(f"highlight object reuse failed: {reuse}")
    if reuse["settled"]["visibleSlotCount"] != 1:
        raise AssertionError(f"highlight slot cleanup failed: {reuse}")
    if idempotent["before"]["transitionId"] != idempotent["after"]["transitionId"]:
        raise AssertionError(f"same-layer idempotency failed: {idempotent}")
    if (
        cleared["phase"] != "off"
        or cleared["layerId"]
        or cleared["visibleSlotCount"] != 0
    ):
        raise AssertionError(f"clear highlight failed: {cleared}")
    if shaft["shaft"] is not True or shaft["hearth"] is not False or shaft["visible"] <= 0:
        raise AssertionError(f"shaft isolation failed: {shaft}")
    benign_console_errors = {
        "[BABEL] Note: The code generator has deoptimised the styling of /Inline Babel script as it exceeds the max of 500KB."
    }
    known_offline_api_paths = {
        "/api/automation/status",
        "/api/short-window/summaries",
        "/api/short-window/conversations",
    }
    unexpected_http_errors = [
        item
        for item in http_errors
        if not (
            args.allow_offline_data_source
            and any(
                urlparse_path in str(item["url"])
                for urlparse_path in known_offline_api_paths
            )
        )
    ]
    unexpected_console_errors = [
        message
        for message in console_errors
        if message not in benign_console_errors
        and not (
            args.allow_offline_data_source
            and (
                message.startswith("Failed to load resource:")
                or (
                    message.startswith("WebSocket connection to ")
                    and f"127.0.0.1:{args.ws_port}" in message
                )
            )
        )
    ]
    if page_errors:
        raise AssertionError(f"browser page errors: {page_errors}")
    if unexpected_console_errors:
        raise AssertionError(
            f"browser console errors: {unexpected_console_errors}; http_errors={http_errors}"
        )
    if unexpected_http_errors:
        raise AssertionError(f"browser HTTP errors: {unexpected_http_errors}")
    print(json.dumps({"ok": True, "url": url, "offline_data_source": args.allow_offline_data_source, "enabled_layers": enabled_layers, "cutaway_buttons": cutaway_buttons, "exterior_before": exterior_before, "cutaway_enter": cutaway_enter, "cutaway_playing": cutaway_playing, "cutaway_paused": cutaway_paused, "cutaway_reuse": cutaway_reuse, "cutaway_reset": cutaway_reset, "layer_cases": layer_cases, "l9_enter": l9_enter, "l16_highlight": l16_highlight, "source_contract": source_contract, "material": material, "tone_cases": tone_cases, "reuse_after_100_switches": reuse, "idempotent": idempotent, "cleared": cleared, "shaft": shaft, "page_errors": page_errors, "console_errors": unexpected_console_errors, "http_errors": unexpected_http_errors, "ignored_offline_console_errors": console_errors, "ignored_offline_http_errors": http_errors}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
