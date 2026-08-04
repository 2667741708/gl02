/**
 * GL02 furnace-body billboard adapter for the 8094 preview route.
 *
 * The standalone furnace-body asset deliberately removes the old SENSOR_*
 * marker meshes from the GLB.  This module restores the runtime contract by
 * loading the exported point manifest, drawing camera-facing labels, and
 * adding transparent hit objects to the viewer's existing arrays.  The
 * measured values remain owned by the page buffer; this adapter only reads
 * that buffer through the viewer getter exposed by the page patch.
 */
import * as THREE from "../libs/three/three.module.js";

const MANIFEST_URL = "models/gl02_furnace_body_billboards.v1.json";
const FORMAL_COLOR = "#67e1d5";
const PRESSURE_COLOR = "#edbd51";
const SELECTED_COLOR = "#fff1a8";
const LIVE_STALE_MS = 15_000;
const BACKGROUND_STORAGE_KEY = "bf3d.billboard.background.v1";
const BACKGROUND_PRESETS = Object.freeze({
  "soft-light": "#eef2f1",
  white: "#ffffff",
  steel: "#889596",
  dark: "#0d1516",
});
const VIEWPORT_STYLE_ID = "bf3d-billboard-full-viewport";

let activeViewer = null;
let mountingViewer = null;
let liveTimer = 0;
let liveSocket = null;
let reconnectTimer = 0;
let nextMountAttemptAt = 0;
let mountRetryDelayMs = 1000;
const liveState = {
  schema: "bf3d.billboard.pspace.live.v1",
  status: "idle",
  url: "",
  connectedAt: null,
  lastFrameAt: null,
  pointCount: 0,
  validPointCount: 0,
  lastError: "",
};
window.__BF3D_BILLBOARD_PSPACE_LIVE__ = liveState;

function installViewportLayoutStyle() {
  let style = document.getElementById(VIEWPORT_STYLE_ID);
  if (!style) {
    style = document.createElement("style");
    style.id = VIEWPORT_STYLE_ID;
    document.head.append(style);
  }
  style.textContent = `
    html body .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap
      .furnace-stage-3d.cad-stage.layered-cad-stage
      .cad-furnace-viewer {
        inset: 0 !important;
        left: 0 !important;
        right: 0 !important;
        top: 0 !important;
        bottom: 0 !important;
        width: auto !important;
        height: auto !important;
        overflow: hidden !important;
        border-color: transparent !important;
        box-shadow: none !important;
        pointer-events: auto !important;
        touch-action: none !important;
      }
    html body .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap
      .furnace-stage-3d.cad-stage.layered-cad-stage
      .cad-furnace-viewer canvas {
        display: block !important;
        width: 100% !important;
        height: 100% !important;
        pointer-events: auto !important;
        touch-action: none !important;
      }
    html body .furnace-layer-callouts.follow-model,
    html body .furnace-follow-lines {
      pointer-events: none !important;
    }
  `;
}

function viewportMetrics(viewer) {
  const host = viewer.renderer?.domElement?.parentElement;
  const stage = host?.closest(".layered-cad-stage");
  const hostRect = host?.getBoundingClientRect();
  const stageRect = stage?.getBoundingClientRect();
  const canvasRect = viewer.renderer?.domElement?.getBoundingClientRect();
  return {
    schema: "bf3d.billboard.viewport.v1",
    stageWidth: Number(stageRect?.width || 0),
    stageHeight: Number(stageRect?.height || 0),
    hostWidth: Number(hostRect?.width || 0),
    hostHeight: Number(hostRect?.height || 0),
    canvasWidth: Number(canvasRect?.width || 0),
    canvasHeight: Number(canvasRect?.height || 0),
    hostToStageWidthRatio: stageRect?.width ? hostRect.width / stageRect.width : null,
    canvasToHostWidthRatio: hostRect?.width ? canvasRect.width / hostRect.width : null,
  };
}

function resizeViewer(viewer) {
  const host = viewer.renderer?.domElement?.parentElement;
  const camera = viewer.camera;
  if (!host || !camera || !viewer.renderer) return viewportMetrics(viewer);
  for (const property of ["inset", "left", "right", "top", "bottom"]) {
    host.style.setProperty(property, "0px", "important");
  }
  const rect = host.getBoundingClientRect();
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  viewer.renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  return viewportMetrics(viewer);
}

function modelNdcBounds(viewer, box) {
  const points = [];
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) {
        points.push(new THREE.Vector3(x, y, z).project(viewer.camera));
      }
    }
  }
  return {
    minX: Math.min(...points.map((point) => point.x)),
    maxX: Math.max(...points.map((point) => point.x)),
    minY: Math.min(...points.map((point) => point.y)),
    maxY: Math.max(...points.map((point) => point.y)),
  };
}

function fitFullModel(viewer, reason = "manual") {
  if (!viewer.camera || !viewer.model) return null;
  resizeViewer(viewer);
  const box = new THREE.Box3().setFromObject(viewer.model);
  if (box.isEmpty()) return null;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const camera = viewer.camera;
  const verticalFov = THREE.MathUtils.degToRad(camera.fov);
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * Math.max(camera.aspect, 0.01));
  const limitingHalfFov = Math.max(THREE.MathUtils.degToRad(5), Math.min(verticalFov, horizontalFov) / 2);
  const distance = sphere.radius / Math.sin(limitingHalfFov) * 1.08;
  const direction = camera.position.clone().sub(sphere.center);
  if (direction.lengthSq() < 0.0001) direction.set(0.34, 0.3, 0.7);
  direction.normalize();
  camera.position.copy(sphere.center).addScaledVector(direction, distance);
  camera.near = Math.max(0.1, distance - sphere.radius * 1.8);
  camera.far = Math.max(260, distance + sphere.radius * 3);
  camera.lookAt(sphere.center);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  const ndcBounds = modelNdcBounds(viewer, box);
  const metrics = {
    ...viewportMetrics(viewer),
    reason,
    fittedAt: new Date().toISOString(),
    cameraDistance: distance,
    modelRadius: sphere.radius,
    modelNdcBounds: ndcBounds,
    modelInsideViewport:
      ndcBounds.minX >= -1 &&
      ndcBounds.maxX <= 1 &&
      ndcBounds.minY >= -1 &&
      ndcBounds.maxY <= 1,
  };
  viewer.billboardViewport = metrics;
  window.__BF3D_VIEWPORT_LAYOUT__ = metrics;
  return metrics;
}

function installViewportController(viewer) {
  installViewportLayoutStyle();
  viewer.__bf3dViewportObserver?.disconnect?.();
  const host = viewer.renderer?.domElement?.parentElement;
  if (!host) return;
  let lastWidth = 0;
  let lastHeight = 0;
  const apply = (reason) => {
    const rect = host.getBoundingClientRect();
    if (
      reason === "resize" &&
      Math.abs(rect.width - lastWidth) < 2 &&
      Math.abs(rect.height - lastHeight) < 2
    ) {
      return;
    }
    lastWidth = rect.width;
    lastHeight = rect.height;
    fitFullModel(viewer, reason);
  };
  const observer = new ResizeObserver(() => apply("resize"));
  observer.observe(host);
  viewer.__bf3dViewportObserver = observer;
  requestAnimationFrame(() => apply("mount"));
  window.setTimeout(() => apply("layout-settled"), 300);
}

installViewportLayoutStyle();

function installWheelZoomController(viewer) {
  const host = viewer.renderer?.domElement?.parentElement;
  if (!host || !viewer.camera || !viewer.model) return;
  if (viewer.__bf3dWheelZoomHandler) {
    host.removeEventListener("wheel", viewer.__bf3dWheelZoomHandler, true);
  }
  const box = new THREE.Box3().setFromObject(viewer.model);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const minDistance = Math.max(5, sphere.radius * 0.42);
  const maxDistance = Math.max(86, sphere.radius * 5);
  const onWheel = (event) => {
    if (event.target.closest?.(".bf3d-background-control")) return;
    event.preventDefault();
    event.stopPropagation();
    const camera = viewer.camera;
    const offset = camera.position.clone().sub(sphere.center);
    let currentDistance = offset.length();
    if (!Number.isFinite(currentDistance) || currentDistance < 0.001) {
      offset.set(0.34, 0.3, 0.7);
      currentDistance = offset.length();
    }
    const zoomFactor = Math.exp(THREE.MathUtils.clamp(event.deltaY, -240, 240) * 0.0018);
    const nextDistance = THREE.MathUtils.clamp(
      currentDistance * zoomFactor,
      minDistance,
      maxDistance,
    );
    camera.position.copy(sphere.center).addScaledVector(offset.normalize(), nextDistance);
    camera.lookAt(sphere.center);
    camera.updateMatrixWorld(true);
    host.dataset.lastWheelZoomAt = new Date().toISOString();
    host.dataset.cameraDistance = nextDistance.toFixed(3);
    if (window.__BF3D_VIEWPORT_LAYOUT__) {
      window.__BF3D_VIEWPORT_LAYOUT__.lastWheelZoomAt = host.dataset.lastWheelZoomAt;
      window.__BF3D_VIEWPORT_LAYOUT__.cameraDistance = nextDistance;
    }
  };
  host.addEventListener("wheel", onWheel, { capture: true, passive: false });
  host.dataset.wheelZoom = "enabled";
  viewer.__bf3dWheelZoomHandler = onWheel;
  viewer.billboardWheelZoom = {
    schema: "bf3d.billboard.wheel-zoom.v1",
    minDistance,
    maxDistance,
  };
}

function backgroundPreference() {
  const query = new URLSearchParams(window.location.search);
  const queryMode = query.get("background");
  if (queryMode && (BACKGROUND_PRESETS[queryMode] || queryMode === "custom")) {
    return { mode: queryMode, color: query.get("background_color") || "#eef2f1" };
  }
  try {
    const saved = JSON.parse(localStorage.getItem(BACKGROUND_STORAGE_KEY) || "{}");
    return {
      mode: BACKGROUND_PRESETS[saved.mode] || saved.mode === "custom" ? saved.mode : "soft-light",
      color: /^#[0-9a-f]{6}$/i.test(saved.color || "") ? saved.color : "#eef2f1",
    };
  } catch {
    return { mode: "soft-light", color: "#eef2f1" };
  }
}

function applyViewerBackground(viewer, mode, customColor = "#eef2f1") {
  const selectedMode = BACKGROUND_PRESETS[mode] || mode === "custom" ? mode : "soft-light";
  const selectedColor = selectedMode === "custom" && /^#[0-9a-f]{6}$/i.test(customColor)
    ? customColor
    : BACKGROUND_PRESETS[selectedMode] || BACKGROUND_PRESETS["soft-light"];
  viewer.scene.background = new THREE.Color(selectedColor);
  viewer.renderer.setClearColor(selectedColor, 1);
  viewer.backgroundMode = selectedMode;
  const host = viewer.renderer.domElement.parentElement;
  if (host) {
    host.dataset.backgroundMode = selectedMode;
    host.style.background = selectedColor;
  }
  try {
    localStorage.setItem(
      BACKGROUND_STORAGE_KEY,
      JSON.stringify({ mode: selectedMode, color: selectedColor }),
    );
  } catch {
    // Production kiosk policies can disable storage; the live selection still applies.
  }
  const colorInput = host?.querySelector(".bf3d-background-color");
  const select = host?.querySelector(".bf3d-background-select");
  if (select) select.value = selectedMode;
  if (colorInput) {
    colorInput.value = selectedColor;
    colorInput.disabled = selectedMode !== "custom";
  }
  return { mode: selectedMode, color: selectedColor };
}

function installBackgroundControl(viewer) {
  const host = viewer.renderer.domElement.parentElement;
  if (!host) return null;
  const existing = host.querySelector(".bf3d-background-control");
  if (existing) return existing;
  if (getComputedStyle(host).position === "static") host.style.position = "relative";
  const control = document.createElement("div");
  control.className = "bf3d-background-control";
  control.setAttribute("aria-label", "三维场景背景");
  control.style.cssText = [
    "position:absolute",
    "right:12px",
    "bottom:12px",
    "z-index:9",
    "display:grid",
    "grid-template-columns:auto minmax(88px,1fr) 34px auto",
    "align-items:center",
    "gap:7px",
    "padding:7px 8px",
    "border:1px solid rgba(74,96,96,.72)",
    "border-radius:6px",
    "background:rgba(20,29,30,.9)",
    "box-shadow:0 6px 18px rgba(0,0,0,.2)",
    "color:#f2f4f1",
    'font:13px SimSun,"宋体",serif',
  ].join(";");
  control.innerHTML = `
    <label for="bf3d-background-select">背景</label>
    <select id="bf3d-background-select" class="bf3d-background-select" aria-label="三维场景背景" style="min-height:30px;border:1px solid #607170;border-radius:4px;background:#f5f7f6;color:#182020;font:13px SimSun,'宋体',serif">
      <option value="soft-light">护眼浅灰</option>
      <option value="white">纯白</option>
      <option value="steel">钢灰</option>
      <option value="dark">深色</option>
      <option value="custom">自定义</option>
    </select>
    <input class="bf3d-background-color" type="color" value="#eef2f1" aria-label="自定义三维背景颜色" style="width:34px;height:30px;padding:2px;border:1px solid #607170;border-radius:4px;background:#f5f7f6">
    <button class="bf3d-fit-full-model" type="button" aria-label="完整显示三维模型" style="min-height:30px;padding:0 9px;border:1px solid #77908e;border-radius:4px;background:#344544;color:#f5f7f6;font:13px SimSun,'宋体',serif;cursor:pointer">全景</button>
  `;
  host.append(control);
  const select = control.querySelector(".bf3d-background-select");
  const colorInput = control.querySelector(".bf3d-background-color");
  const fitButton = control.querySelector(".bf3d-fit-full-model");
  select.addEventListener("change", () => {
    applyViewerBackground(viewer, select.value, colorInput.value);
  });
  colorInput.addEventListener("input", () => {
    select.value = "custom";
    applyViewerBackground(viewer, "custom", colorInput.value);
  });
  fitButton.addEventListener("click", () => fitFullModel(viewer, "control"));
  const preference = backgroundPreference();
  applyViewerBackground(viewer, preference.mode, preference.color);
  window.__BF3D_BACKGROUND_CONTROL__ = {
    schema: "bf3d.background-control.v1",
    presets: Object.keys(BACKGROUND_PRESETS),
    set(mode, color) {
      return applyViewerBackground(viewer, mode, color);
    },
    get() {
      return {
        mode: viewer.backgroundMode,
        color: `#${viewer.scene.background.getHexString()}`,
      };
    },
  };
  return control;
}

function finiteValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function latestFromBuffer(buffer, id) {
  const values = buffer?.[id];
  if (!Array.isArray(values)) return null;
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = finiteValue(values[index]);
    if (value !== null) return value;
  }
  return null;
}

function roundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

function bindingId(point) {
  return point.canonical_id || point.data_binding_key || point.id;
}

function labelText(point) {
  if (point.realtime_bad_quality) return `${point.short_label}  质量异常`;
  const value = point.realtime_value;
  if (value === null || value === undefined) return point.short_label;
  const formatted = Number.isFinite(Number(value))
    ? Number(value).toLocaleString("zh-CN", {
        maximumFractionDigits: 1,
        minimumFractionDigits: 1,
      })
    : String(value);
  const stale = point.realtime_stale ? "（中断）" : "";
  return `${point.short_label}  ${formatted}${point.display_unit || point.unit || ""}${stale}`;
}

function makeTexture(point, selected = false) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  const font = '26px SimSun, "宋体", serif';
  context.font = font;
  const text = labelText(point);
  const textWidth = Math.ceil(context.measureText(text).width);
  canvas.width = Math.max(150, Math.min(720, textWidth + 72));
  canvas.height = 62;
  context.font = font;
  context.textBaseline = "middle";
  const color = selected
    ? SELECTED_COLOR
    : point.source_kind === "static_pressure_18"
      ? PRESSURE_COLOR
      : FORMAL_COLOR;
  roundRect(context, 1, 1, canvas.width - 2, canvas.height - 2, 8);
  context.fillStyle = selected ? "rgba(42,36,17,.96)" : "rgba(10,20,21,.90)";
  context.fill();
  context.lineWidth = selected ? 3 : 2;
  context.strokeStyle = color;
  context.stroke();
  context.beginPath();
  context.arc(25, canvas.height / 2, selected ? 9 : 7, 0, Math.PI * 2);
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = 12;
  context.fill();
  context.shadowBlur = 0;
  context.fillStyle = selected ? "#fff8da" : "#f1eee5";
  context.fillText(text, 46, canvas.height / 2 + 1);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.userData = { canvasWidth: canvas.width, canvasHeight: canvas.height };
  return texture;
}

function deterministicDirection(id) {
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) >>> 0;
  }
  const angle = ((hash % 360) / 180) * Math.PI;
  return new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle));
}

function placeSprite(entry, center) {
  const anchor = new THREE.Vector3(...entry.point.position);
  const radial = new THREE.Vector3(anchor.x - center.x, 0, anchor.z - center.z);
  if (radial.lengthSq() < 0.2) radial.copy(deterministicDirection(entry.point.id));
  radial.normalize();
  entry.sprite.position.copy(anchor).addScaledVector(radial, 0.34);
  const width = entry.sprite.material.map.userData.canvasWidth;
  const height = entry.point.source_kind === "static_pressure_18" ? 0.62 : 0.5;
  entry.sprite.scale.set((height * width) / 62, height, 1);
  entry.sprite.center.set(0.05, 0.5);
}

function refreshEntry(entry, center) {
  const selected = entry.point.id === activeViewer?.selectedBillboardId;
  const previous = entry.sprite.material.map;
  entry.sprite.material.map = makeTexture(entry.point, selected);
  entry.sprite.material.needsUpdate = true;
  if (previous && previous !== entry.sprite.material.map) previous.dispose();
  placeSprite(entry, center);
  entry.sprite.renderOrder = selected ? 20 : 10;
}

function updateLiveLabels() {
  if (!activeViewer?.billboardEntries) return;
  const buffer = activeViewer.getBuffer?.();
  if (!buffer) return;
  const now = Date.now();
  for (const entry of activeViewer.billboardEntries) {
    if (entry.point.realtime_source === "pspace") {
      const fresh = now - Number(entry.point.realtime_received_at || 0) <= LIVE_STALE_MS;
      if (fresh) {
        if (entry.point.realtime_stale) {
          entry.point.realtime_stale = false;
          refreshEntry(entry, activeViewer.billboardCenter);
        }
        continue;
      }
      if (!entry.point.realtime_stale) {
        entry.point.realtime_stale = true;
        refreshEntry(entry, activeViewer.billboardCenter);
      }
    }
    const value = latestFromBuffer(buffer, entry.bindingId);
    if (value === null && entry.point.realtime_source === "pspace") continue;
    if (value === entry.point.realtime_value) continue;
    entry.point.realtime_value = value;
    entry.point.realtime_source = "page_buffer";
    entry.point.realtime_received_at = now;
    entry.point.realtime_stale = false;
    entry.point.realtime_bad_quality = false;
    refreshEntry(entry, activeViewer.billboardCenter);
  }
}

function qualityIsBad(quality, error = "") {
  const text = `${quality ?? ""} ${error ?? ""}`.trim().toLowerCase();
  return Boolean(text && /(bad|uncertain|invalid|error|失败|异常|无效)/i.test(text));
}

function setLiveStatus(status, error = "") {
  liveState.status = status;
  liveState.lastError = error ? String(error) : "";
  const host = activeViewer?.renderer?.domElement?.parentElement;
  if (host) {
    host.dataset.billboardLiveStatus = status;
    host.dataset.billboardLivePoints = String(liveState.validPointCount || 0);
    host.dataset.billboardLiveTimestamp = liveState.lastFrameAt || "";
  }
}

function websocketUrl() {
  const query = new URLSearchParams(window.location.search);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host =
    query.get("billboard_ws_host") ||
    window.BF_PSPACE_WS_HOST ||
    window.location.hostname ||
    "10.30.220.12";
  const port =
    query.get("billboard_ws_port") ||
    window.BF_PSPACE_WS_PORT ||
    "8770";
  return `${protocol}://${host}:${port}`;
}

function latestHistoryValue(history, id) {
  return latestFromBuffer(history, id);
}

function applyLivePayload(payload) {
  if (!activeViewer?.billboardEntries || !payload) return;
  const values = payload.type === "init" ? payload.history : payload.values;
  if (!values || typeof values !== "object") return;
  const pointMeta = payload.point_meta || {};
  const records = [];
  for (const entry of activeViewer.billboardEntries) {
    const id = entry.bindingId;
    if (!Object.prototype.hasOwnProperty.call(values, id)) continue;
    const value = payload.type === "init" ? latestHistoryValue(values, id) : values[id];
    const meta = pointMeta[id] || {};
    records.push({
      canonical_id: id,
      value,
      unit: entry.point.display_unit || entry.point.unit || "",
      timestamp: meta.timestamp || payload.timestamp || "",
      quality: meta.quality ?? "",
      error: meta.error || "",
      source: "pspace",
    });
  }
  if (!records.length) return;
  window.BF3D_BILLBOARD_ADAPTER?.updateValues(records);
  liveState.lastFrameAt = payload.timestamp || new Date().toISOString();
  liveState.pointCount = records.length;
  liveState.validPointCount = records.filter(
    (record) => finiteValue(record.value) !== null && !qualityIsBad(record.quality, record.error),
  ).length;
  setLiveStatus("connected");
}

function connectBillboardRealtime() {
  if (
    liveSocket &&
    (liveSocket.readyState === WebSocket.OPEN ||
      liveSocket.readyState === WebSocket.CONNECTING)
  ) {
    return;
  }
  window.clearTimeout(reconnectTimer);
  const url = websocketUrl();
  liveState.url = url;
  setLiveStatus("connecting");
  try {
    liveSocket = new WebSocket(url);
  } catch (error) {
    setLiveStatus("error", error?.message || error);
    reconnectTimer = window.setTimeout(connectBillboardRealtime, 3000);
    return;
  }
  liveSocket.addEventListener("open", () => {
    liveState.connectedAt = new Date().toISOString();
    setLiveStatus("connected");
  });
  liveSocket.addEventListener("message", (event) => {
    try {
      applyLivePayload(JSON.parse(event.data));
    } catch (error) {
      setLiveStatus("error", error?.message || error);
    }
  });
  liveSocket.addEventListener("error", () => setLiveStatus("error", "WebSocket error"));
  liveSocket.addEventListener("close", () => {
    liveSocket = null;
    setLiveStatus("disconnected");
    reconnectTimer = window.setTimeout(connectBillboardRealtime, 3000);
  });
}

async function mount(viewer) {
  if (activeViewer === viewer && viewer.__bf3dFurnaceBodyBillboards) return;
  const response = await fetch(MANIFEST_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`炉体传感器清单 HTTP ${response.status}`);
  const manifest = await response.json();
  if (
    manifest?.schema !== "bf3d.sensor_billboards.v1" ||
    manifest?.counts?.total !== 133 ||
    !Array.isArray(manifest.points) ||
    manifest.points.length !== 133
  ) {
    throw new Error("炉体传感器清单未通过 133 点位合同");
  }
  if (!viewer.scene || !viewer.model || !viewer.renderer) {
    throw new Error("CAD viewer 未暴露场景句柄");
  }

  const center = new THREE.Box3()
    .setFromObject(viewer.model)
    .getCenter(new THREE.Vector3());
  const hitGeometry = new THREE.SphereGeometry(0.95, 16, 10);
  const hitMaterial = new THREE.MeshBasicMaterial({
    color: 0x12b8ff,
    transparent: true,
    opacity: 0.02,
    depthWrite: false,
  });
  const entries = [];
  for (const point of manifest.points) {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: makeTexture(point),
        transparent: true,
        depthTest: true,
        depthWrite: false,
        toneMapped: false,
      }),
    );
    const id = bindingId(point);
    sprite.name = `BILLBOARD_${point.id}`;
    sprite.userData = {
      schema: "bf3d.sensor_billboard.runtime.v1",
      sensorId: id,
      canonicalId: id,
      manifestPointId: point.id,
      sourceKind: point.source_kind,
      layer_id: point.layer_id || null,
      height_m: point.elevation_m ?? point.position?.[1] ?? null,
      billboardPrimitive: "THREE.Sprite",
      cameraFacing: true,
    };
    viewer.scene.add(sprite);
    const entry = { point, bindingId: id, sprite };
    placeSprite(entry, center);
    entries.push(entry);
    viewer.sensorObjects.push(sprite);

    const hit = new THREE.Mesh(hitGeometry, hitMaterial);
    hit.name = `HIT_${id}`;
    hit.position.set(...point.position);
    hit.userData = {
      sensorId: id,
      canonicalId: id,
      manifestPointId: point.id,
      sourceKind: point.source_kind,
      layer_id: point.layer_id || null,
      height_m: point.elevation_m ?? point.position?.[1] ?? null,
    };
    viewer.scene.add(hit);
    viewer.hitObjects.push(hit);
  }

  activeViewer = viewer;
  activeViewer.billboardCenter = center;
  activeViewer.billboardEntries = entries;
  activeViewer.billboardManifest = manifest;
  activeViewer.__bf3dFurnaceBodyBillboards = true;
  activeViewer.sensorCount = activeViewer.sensorObjects.length;
  activeViewer.hitCount = activeViewer.hitObjects.length;
  activeViewer.mappedCount = manifest.points.length;
  activeViewer.billboardCount = entries.length;
  activeViewer.modelAsset = "GL02_FURNACE_BODY_R1.glb";
  installViewportController(viewer);
  installWheelZoomController(viewer);
  installBackgroundControl(viewer);
  const host = viewer.renderer.domElement.parentElement;
  if (host) {
    host.dataset.sensorCount = String(activeViewer.sensorCount);
    host.dataset.hitCount = String(activeViewer.hitCount);
    host.dataset.mappedCount = String(activeViewer.mappedCount);
    host.dataset.billboardCount = String(entries.length);
    host.dataset.billboardStatus = "ready";
    host.dataset.modelAsset = activeViewer.modelAsset;
  }
  window.__BF_FURNACE_BODY_BILLBOARDS__ = {
    schema: "bf3d.furnace_body_billboard.runtime.v1",
    modelAsset: activeViewer.modelAsset,
    manifestUrl: MANIFEST_URL,
    formalSensorCount: manifest.counts.formal_sensor_115,
    staticPressureCount: manifest.counts.static_pressure_18,
    totalBillboardCount: entries.length,
    spriteCount: entries.filter((entry) => entry.sprite.isSprite).length,
    hitCount: activeViewer.hitObjects.length,
    liveBufferAdapter: typeof activeViewer.getBuffer === "function",
    pspaceRealtimeContract: liveState.schema,
    pspaceRealtimeUrl: websocketUrl(),
    passed: entries.length === 133 && entries.every((entry) => entry.sprite.isSprite),
  };
  window.BF3D_BILLBOARD_ADAPTER = {
    fitFullModel() {
      return fitFullModel(viewer, "api");
    },
    viewport() {
      return viewportMetrics(viewer);
    },
    setBackground(mode, color) {
      return applyViewerBackground(viewer, mode, color);
    },
    updateValues(records) {
      const list = Array.isArray(records)
        ? records
        : Object.entries(records || {}).map(([id, value]) => ({ id, value }));
      let updated = 0;
      for (const record of list) {
        const id = record.canonical_id || record.data_binding_key || record.id;
        const entry = entries.find((item) => item.bindingId === id);
        if (!entry) continue;
        entry.point.realtime_value = record.value;
        if (record.unit !== undefined) entry.point.display_unit = record.unit;
        entry.point.realtime_timestamp = record.timestamp || "";
        entry.point.realtime_quality = record.quality ?? "";
        entry.point.realtime_source = record.source || "adapter";
        entry.point.realtime_received_at = Date.now();
        entry.point.realtime_stale = false;
        entry.point.realtime_bad_quality = qualityIsBad(record.quality, record.error);
        refreshEntry(entry, center);
        updated += 1;
      }
      return { requested: list.length, updated };
    },
    clearValues() {
      for (const entry of entries) {
        entry.point.realtime_value = null;
        entry.point.realtime_timestamp = "";
        entry.point.realtime_quality = "";
        entry.point.realtime_source = "";
        entry.point.realtime_received_at = 0;
        entry.point.realtime_stale = false;
        entry.point.realtime_bad_quality = false;
        refreshEntry(entry, center);
      }
    },
    manifest,
  };
  if (!liveTimer) liveTimer = window.setInterval(updateLiveLabels, 1000);
  connectBillboardRealtime();
  nextMountAttemptAt = 0;
  mountRetryDelayMs = 1000;
}

function tryMount() {
  const viewer = window.__BF_CAD_FURNACE_VIEWER;
  if (Date.now() < nextMountAttemptAt) return;
  if (
    !viewer ||
    !viewer.scene ||
    !viewer.model ||
    !viewer.renderer ||
    viewer.__bf3dFurnaceBodyBillboards ||
    mountingViewer === viewer
  ) {
    return;
  }
  mountingViewer = viewer;
  mount(viewer)
    .catch((error) => {
      const host = viewer.renderer?.domElement?.parentElement;
      if (host) host.dataset.billboardStatus = "error";
      nextMountAttemptAt = Date.now() + mountRetryDelayMs;
      mountRetryDelayMs = Math.min(15_000, mountRetryDelayMs * 2);
      console.error("炉体 Billboard 适配失败", error);
    })
    .finally(() => {
      if (mountingViewer === viewer) mountingViewer = null;
    });
}

window.setInterval(tryMount, 250);
tryMount();
