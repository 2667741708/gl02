/**
 * 8095-only Billboard focus and furnace-shell camera guard.
 *
 * The 8094 adapter keeps its original furnace-centred dolly behaviour.
 * This overlay is loaded only by the 8095 preview page. It:
 * - focuses a clicked Billboard from the local furnace-surface normal;
 * - replaces the furnace-centred wheel handler with target-centred dolly;
 * - raycasts the fitted furnace shell before every inward camera move;
 * - restores the pre-focus furnace-centred overview when focus exits.
 */
import * as THREE from "../libs/three/three.module.js";

const RUNTIME_KEY = "__BF3D_BILLBOARD_FOCUS_GUARD_8095__";
const SCHEMA = "bf3d.billboard.focus-shell-guard.8095.v1";
const SHELL_NAME = "IMG2THREEJS_FITTED_GL02_SHELL";
const HOST_CLASS = "bf3d-focus-guard-8095";
const MAX_PICK_DRAG_PX = 7;
const MAX_PICK_DURATION_MS = 650;
const CAMERA_TWEEN_MS = 360;

let mountedViewer = null;
let disposeMounted = () => {};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function easeOutCubic(value) {
  return 1 - Math.pow(1 - value, 3);
}

function displayName(entry) {
  return (
    entry?.point?.semantic_abbreviation_cn ||
    entry?.point?.short_label ||
    entry?.point?.semantic_name_cn ||
    entry?.point?.semantic_short_cn ||
    entry?.point?.display_name_cn ||
    entry?.point?.display_name ||
    entry?.point?.name_cn ||
    entry?.point?.id ||
    entry?.bindingId ||
    "点位"
  );
}

function installStyle() {
  if (document.getElementById("bf3d-focus-guard-8095-style")) return;
  const style = document.createElement("style");
  style.id = "bf3d-focus-guard-8095-style";
  style.textContent = `
    .${HOST_CLASS}{
      position:absolute;left:12px;bottom:12px;z-index:12;
      display:flex;align-items:center;gap:8px;max-width:min(460px,calc(100% - 250px));
      min-height:34px;padding:6px 8px;border:1px solid rgba(54,157,151,.72);
      border-radius:6px;background:rgba(15,28,29,.92);color:#eef8f5;
      box-shadow:0 6px 18px rgba(0,0,0,.2);font:13px SimSun,"宋体",serif;
      pointer-events:none;
    }
    .${HOST_CLASS}[data-mode="overview"]{opacity:.82}
    .${HOST_CLASS} .bf3d-focus-state{
      min-width:0;overflow-wrap:anywhere;line-height:1.35;
    }
    .${HOST_CLASS} .bf3d-focus-state strong{color:#75ece0}
    .${HOST_CLASS} .bf3d-focus-exit{
      display:none;min-height:28px;padding:0 10px;flex:0 0 auto;
      border:1px solid #7b9995;border-radius:4px;background:#304643;color:#fff;
      font:13px SimSun,"宋体",serif;cursor:pointer;pointer-events:auto;
    }
    .${HOST_CLASS}[data-mode="focus"] .bf3d-focus-exit{display:block}
    @media(max-width:768px){
      .${HOST_CLASS}{left:8px;bottom:54px;max-width:calc(100% - 16px)}
    }
  `;
  document.head.append(style);
}

function mount(viewer) {
  if (!viewer?.camera || !viewer?.controls || !viewer?.renderer || !viewer?.model) {
    return false;
  }
  if (!viewer.__bf3dFurnaceBodyBillboards || !viewer.billboardEntries?.length) {
    return false;
  }

  const host = viewer.renderer.domElement.parentElement;
  const canvas = viewer.renderer.domElement;
  if (!host || !canvas) return false;

  installStyle();
  if (getComputedStyle(host).position === "static") host.style.position = "relative";

  const shellMeshes = [];
  viewer.model.traverse((object) => {
    if (!object?.isMesh) return;
    if (
      object.name === SHELL_NAME ||
      object.userData?.kind === "fitted_programmatic_shell" ||
      /FITTED.*SHELL|FURNACE.*SHELL|炉壳/i.test(object.name || "")
    ) {
      shellMeshes.push(object);
    }
  });
  if (!shellMeshes.length) {
    viewer.model.traverse((object) => {
      if (object?.isMesh && !/^SENSOR_|^HIT_/i.test(object.name || "")) {
        shellMeshes.push(object);
      }
    });
  }

  const bodyBox = new THREE.Box3().setFromObject(viewer.model);
  const bodySphere = bodyBox.getBoundingSphere(new THREE.Sphere());
  const bodyCenter = viewer.billboardCenter?.clone?.() || bodySphere.center.clone();
  const safetyGap = clamp(bodySphere.radius * 0.042, 1.2, 2.1);
  const observationDistance = clamp(bodySphere.radius * 0.16, 4.8, 8.2);
  const minOverviewDistance = Math.max(5, bodySphere.radius * 0.42);
  const maxDistance = Math.max(86, bodySphere.radius * 5);
  const shellRaycaster = new THREE.Raycaster();
  const pickRaycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const normalMatrix = new THREE.Matrix3();
  const entriesByObject = new Map();
  const entriesById = new Map();
  const state = {
    schema: SCHEMA,
    mode: "overview",
    selectedId: "",
    selectedName: "",
    collisionBlocked: false,
    collisionCount: 0,
    shellMeshCount: shellMeshes.length,
    safetyGap,
    observationDistance,
    overviewPosition: null,
    overviewTarget: null,
    overviewNear: null,
    overviewFar: null,
    overviewMinDistance: viewer.controls.minDistance,
    overviewPanEnabled: viewer.controls.enablePan,
    entry: null,
    surfacePoint: null,
    surfaceNormal: null,
    lastSafePosition: viewer.camera.position.clone(),
    tweenFrame: 0,
  };

  for (const entry of viewer.billboardEntries) {
    entriesByObject.set(entry.sprite, entry);
    entriesById.set(entry.point.id, entry);
    entriesById.set(entry.bindingId, entry);
  }
  for (const hit of viewer.hitObjects || []) {
    const id =
      hit.userData?.manifestPointId ||
      hit.userData?.canonicalId ||
      hit.userData?.sensorId;
    const entry = entriesById.get(id);
    if (entry) entriesByObject.set(hit, entry);
  }

  const panel = document.createElement("div");
  panel.className = HOST_CLASS;
  panel.dataset.mode = "overview";
  panel.setAttribute("role", "status");
  panel.setAttribute("aria-live", "polite");
  panel.innerHTML = `
    <span class="bf3d-focus-state">点击数据牌可进入<strong>点位聚焦</strong>；滚轮受炉壳安全距离约束</span>
    <button class="bf3d-focus-exit" type="button">退出聚焦</button>
  `;
  host.append(panel);
  const panelText = panel.querySelector(".bf3d-focus-state");
  const exitButton = panel.querySelector(".bf3d-focus-exit");

  function exposeState() {
    host.dataset.focusGuard8095 = "ready";
    host.dataset.cameraMode = state.mode;
    host.dataset.focusSensor = state.selectedId;
    host.dataset.shellMeshCount = String(state.shellMeshCount);
    host.dataset.shellSafetyGap = state.safetyGap.toFixed(3);
    host.dataset.collisionBlocked = String(state.collisionBlocked);
    host.dataset.collisionCount = String(state.collisionCount);
  }

  function markCollision(blocked) {
    state.collisionBlocked = blocked;
    if (blocked) state.collisionCount += 1;
    exposeState();
  }

  function firstShellHit(origin, direction, far) {
    if (!shellMeshes.length || far <= 0) return null;
    shellRaycaster.set(origin, direction);
    shellRaycaster.near = 0;
    shellRaycaster.far = far;
    return shellRaycaster.intersectObjects(shellMeshes, false)[0] || null;
  }

  function surfaceInfo(entry) {
    const anchor = new THREE.Vector3(...entry.point.position);
    const radial = anchor.clone().sub(bodyCenter);
    radial.y = 0;
    if (radial.lengthSq() < 0.0001) {
      radial.copy(viewer.camera.position).sub(bodyCenter);
      radial.y = 0;
    }
    radial.normalize();
    const castDistance = Math.max(12, bodySphere.radius * 1.2);
    const origin = anchor.clone().addScaledVector(radial, castDistance * 0.5);
    const hit = firstShellHit(origin, radial.clone().negate(), castDistance);
    const surfacePoint = hit?.point?.clone?.() || anchor.clone();
    let surfaceNormal = radial.clone();
    if (hit?.face?.normal && hit.object?.matrixWorld) {
      normalMatrix.getNormalMatrix(hit.object.matrixWorld);
      surfaceNormal = hit.face.normal.clone().applyMatrix3(normalMatrix).normalize();
      if (surfaceNormal.dot(radial) < 0) surfaceNormal.negate();
    }
    return { anchor, surfacePoint, surfaceNormal };
  }

  function saveOverviewPose() {
    if (state.overviewPosition) return;
    state.overviewPosition = viewer.camera.position.clone();
    state.overviewTarget = viewer.controls.target.clone();
    state.overviewNear = viewer.camera.near;
    state.overviewFar = viewer.camera.far;
    state.overviewMinDistance = viewer.controls.minDistance;
    state.overviewPanEnabled = viewer.controls.enablePan;
  }

  function resetSelectedVisual() {
    if (!state.entry?.sprite) return;
    if (state.entry.sprite.userData.__focusScale) {
      state.entry.sprite.scale.copy(state.entry.sprite.userData.__focusScale);
      delete state.entry.sprite.userData.__focusScale;
    }
    state.entry.sprite.material?.color?.set?.(0xffffff);
    state.entry.sprite.renderOrder = 10;
  }

  function setSelectedVisual(entry) {
    resetSelectedVisual();
    entry.sprite.userData.__focusScale = entry.sprite.scale.clone();
    entry.sprite.scale.multiplyScalar(1.12);
    entry.sprite.material?.color?.set?.(0xfff1a8);
    entry.sprite.renderOrder = 30;
  }

  function tweenCamera(position, target, onDone) {
    cancelAnimationFrame(state.tweenFrame);
    const startPosition = viewer.camera.position.clone();
    const startTarget = viewer.controls.target.clone();
    const startedAt = performance.now();
    viewer.controls.enabled = false;
    const step = (now) => {
      const progress = clamp((now - startedAt) / CAMERA_TWEEN_MS, 0, 1);
      const eased = easeOutCubic(progress);
      viewer.camera.position.lerpVectors(startPosition, position, eased);
      viewer.controls.target.lerpVectors(startTarget, target, eased);
      viewer.camera.lookAt(viewer.controls.target);
      viewer.camera.updateMatrixWorld(true);
      if (progress < 1) {
        state.tweenFrame = requestAnimationFrame(step);
        return;
      }
      viewer.controls.enabled = true;
      viewer.controls.update();
      state.lastSafePosition.copy(viewer.camera.position);
      onDone?.();
    };
    state.tweenFrame = requestAnimationFrame(step);
  }

  function fitOverview(reason = "full-view") {
    const camera = viewer.camera;
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const horizontalFov =
      2 * Math.atan(Math.tan(verticalFov / 2) * Math.max(camera.aspect, 0.01));
    const limitingHalfFov = Math.max(
      THREE.MathUtils.degToRad(5),
      Math.min(verticalFov, horizontalFov) / 2,
    );
    const distance = bodySphere.radius / Math.sin(limitingHalfFov) * 1.08;
    const direction = camera.position.clone().sub(bodyCenter);
    if (direction.lengthSq() < 0.0001) direction.set(0.34, 0.3, 0.7);
    direction.normalize();
    cancelAnimationFrame(state.tweenFrame);
    viewer.controls.enabled = true;
    viewer.controls.target.copy(bodyCenter);
    camera.position.copy(bodyCenter).addScaledVector(direction, distance);
    camera.near = 0.08;
    camera.far = Math.max(260, distance + bodySphere.radius * 4);
    camera.lookAt(bodyCenter);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    viewer.controls.minDistance = minOverviewDistance;
    viewer.controls.maxDistance = maxDistance;
    viewer.controls.enablePan = state.overviewPanEnabled ?? true;
    viewer.controls.update();
    state.mode = "overview";
    state.overviewPosition = null;
    state.overviewTarget = null;
    state.lastSafePosition.copy(camera.position);
    host.dataset.focusExitReason = reason;
    host.dataset.cameraDistance = distance.toFixed(3);
    host.dataset.wheelZoomMode = "furnace-center";
    panel.dataset.mode = "overview";
    panelText.innerHTML =
      "点击数据牌可进入<strong>点位聚焦</strong>；当前为炉心全景旋转";
    exposeState();
    return distance;
  }

  function focusEntry(entry, reason = "pointer") {
    if (!entry) return false;
    saveOverviewPose();
    const surface = surfaceInfo(entry);
    const focusTarget = surface.anchor.clone().addScaledVector(surface.surfaceNormal, 0.12);
    const focusPosition = surface.surfacePoint
      .clone()
      .addScaledVector(surface.surfaceNormal, observationDistance);
    state.mode = "focus";
    state.entry = entry;
    state.selectedId = entry.bindingId || entry.point.id;
    state.selectedName = displayName(entry);
    state.surfacePoint = surface.surfacePoint;
    state.surfaceNormal = surface.surfaceNormal;
    state.collisionBlocked = false;
    viewer.selectedBillboardId = entry.point.id;
    viewer.camera.near = 0.08;
    viewer.camera.far = Math.max(viewer.camera.far, bodySphere.radius * 8);
    viewer.camera.updateProjectionMatrix();
    viewer.controls.minDistance = safetyGap;
    viewer.controls.maxDistance = maxDistance;
    viewer.controls.enablePan = false;
    setSelectedVisual(entry);
    panel.dataset.mode = "focus";
    panelText.innerHTML = `已聚焦：<strong>${state.selectedName}</strong>；滚轮沿点位推进，炉壳前 ${safetyGap.toFixed(1)} m 停止`;
    host.dataset.focusReason = reason;
    exposeState();
    tweenCamera(focusPosition, focusTarget, () => {
      state.lastSafePosition.copy(viewer.camera.position);
      exposeState();
    });
    return true;
  }

  function exitFocus({ animate = true, reason = "control" } = {}) {
    if (state.mode !== "focus") return false;
    resetSelectedVisual();
    viewer.selectedBillboardId = "";
    state.mode = "overview";
    state.entry = null;
    state.selectedId = "";
    state.selectedName = "";
    state.surfacePoint = null;
    state.surfaceNormal = null;
    state.collisionBlocked = false;
    viewer.controls.minDistance = state.overviewMinDistance ?? minOverviewDistance;
    viewer.controls.maxDistance = maxDistance;
    viewer.controls.enablePan = state.overviewPanEnabled ?? true;
    viewer.camera.near = state.overviewNear ?? 0.1;
    viewer.camera.far = state.overviewFar ?? Math.max(260, bodySphere.radius * 8);
    viewer.camera.updateProjectionMatrix();
    panel.dataset.mode = "overview";
    panelText.innerHTML = "点击数据牌可进入<strong>点位聚焦</strong>；已恢复以炉心为中心的全景旋转";
    host.dataset.focusExitReason = reason;
    const position =
      state.overviewPosition?.clone?.() ||
      bodyCenter.clone().add(new THREE.Vector3(0.34, 0.3, 0.7).normalize().multiplyScalar(bodySphere.radius * 2.6));
    const target = state.overviewTarget?.clone?.() || bodyCenter.clone();
    exposeState();
    if (animate) {
      tweenCamera(position, target, exposeState);
    } else {
      cancelAnimationFrame(state.tweenFrame);
      viewer.camera.position.copy(position);
      viewer.controls.target.copy(target);
      viewer.camera.lookAt(target);
      viewer.camera.updateMatrixWorld(true);
      viewer.controls.enabled = true;
      viewer.controls.update();
      state.lastSafePosition.copy(viewer.camera.position);
    }
    state.overviewPosition = null;
    state.overviewTarget = null;
    return true;
  }

  function visibleEntryHit(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    pickRaycaster.setFromCamera(pointer, viewer.camera);
    const pickObjects = [
      ...viewer.billboardEntries.map((entry) => entry.sprite),
      ...Array.from(entriesByObject.keys()).filter((object) => object?.isMesh),
    ];
    const hits = pickRaycaster.intersectObjects(pickObjects, false);
    for (const hit of hits) {
      const entry = entriesByObject.get(hit.object);
      if (!entry) continue;
      const shellHit = firstShellHit(
        viewer.camera.position,
        hit.point.clone().sub(viewer.camera.position).normalize(),
        hit.distance,
      );
      if (shellHit && shellHit.distance + 0.1 < hit.distance) continue;
      return entry;
    }
    return null;
  }

  function constrainCameraMove(from, requested) {
    const movement = requested.clone().sub(from);
    const distance = movement.length();
    if (distance < 0.0001) return requested;
    const direction = movement.normalize();
    const hit = firstShellHit(from, direction, distance + safetyGap);
    if (!hit || hit.distance > distance + safetyGap) {
      markCollision(false);
      return requested;
    }
    const allowedDistance = Math.max(0, hit.distance - safetyGap);
    markCollision(true);
    return from.clone().addScaledVector(direction, allowedDistance);
  }

  function onWheel(event) {
    if (event.target.closest?.(".bf3d-background-control, .bf3d-focus-guard-8095")) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    const target = state.mode === "focus"
      ? viewer.controls.target
      : bodyCenter;
    const offset = viewer.camera.position.clone().sub(target);
    let currentDistance = offset.length();
    if (!Number.isFinite(currentDistance) || currentDistance < 0.001) {
      offset.set(0.34, 0.3, 0.7);
      currentDistance = offset.length();
    }
    const zoomFactor = Math.exp(clamp(event.deltaY, -240, 240) * 0.0018);
    const minimum = state.mode === "focus" ? safetyGap : minOverviewDistance;
    const rawNextDistance = currentDistance * zoomFactor;
    const nextDistance = clamp(rawNextDistance, minimum, maxDistance);
    const requested = target.clone().addScaledVector(offset.normalize(), nextDistance);
    const inward = nextDistance < currentDistance;
    const blockedByMinimum =
      state.mode === "focus" &&
      event.deltaY < 0 &&
      rawNextDistance <= minimum + 0.0001;
    const safePosition = inward
      ? constrainCameraMove(viewer.camera.position, requested)
      : requested;
    viewer.camera.position.copy(safePosition);
    viewer.camera.lookAt(target);
    viewer.camera.updateMatrixWorld(true);
    viewer.controls.update();
    state.lastSafePosition.copy(viewer.camera.position);
    host.dataset.lastWheelZoomAt = new Date().toISOString();
    host.dataset.cameraDistance = viewer.camera.position.distanceTo(target).toFixed(3);
    host.dataset.wheelZoomMode = state.mode === "focus" ? "billboard-target" : "furnace-center";
    if (blockedByMinimum) markCollision(true);
    exposeState();
  }

  function guardFocusedCamera() {
    if (
      state.mode !== "focus" ||
      !state.surfacePoint ||
      !state.surfaceNormal ||
      !viewer.controls.enabled
    ) {
      state.lastSafePosition.copy(viewer.camera.position);
      return;
    }
    const signedGap = viewer.camera.position
      .clone()
      .sub(state.surfacePoint)
      .dot(state.surfaceNormal);
    if (signedGap < safetyGap) {
      viewer.camera.position.addScaledVector(state.surfaceNormal, safetyGap - signedGap);
      viewer.camera.lookAt(viewer.controls.target);
      viewer.camera.updateMatrixWorld(true);
      viewer.controls.update();
      markCollision(true);
    }
    state.lastSafePosition.copy(viewer.camera.position);
  }

  let pointerDown = null;
  function onPointerDown(event) {
    if (event.button !== 0) return;
    pointerDown = {
      x: event.clientX,
      y: event.clientY,
      at: performance.now(),
    };
  }

  function onPointerUp(event) {
    if (!pointerDown || event.button !== 0) return;
    const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
    const duration = performance.now() - pointerDown.at;
    pointerDown = null;
    if (moved > MAX_PICK_DRAG_PX || duration > MAX_PICK_DURATION_MS) return;
    const entry = visibleEntryHit(event);
    if (entry) {
      event.preventDefault();
      event.stopPropagation();
      focusEntry(entry, "pointer");
    }
  }

  function onKeyDown(event) {
    if (event.key === "Escape" && state.mode === "focus") {
      event.preventDefault();
      exitFocus({ reason: "escape" });
    }
  }

  function onHostClickCapture(event) {
    if (!event.target.closest?.(".bf3d-fit-full-model")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (state.mode === "focus") {
      exitFocus({ animate: false, reason: "full-view" });
    }
    fitOverview("full-view");
  }

  if (viewer.__bf3dWheelZoomHandler) {
    host.removeEventListener("wheel", viewer.__bf3dWheelZoomHandler, true);
    viewer.__bf3dWheelZoomHandler = null;
  }
  host.addEventListener("wheel", onWheel, { capture: true, passive: false });
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointerup", onPointerUp);
  host.addEventListener("click", onHostClickCapture, true);
  exitButton.addEventListener("click", () => exitFocus({ reason: "button" }));
  window.addEventListener("keydown", onKeyDown);
  const guardTimer = window.setInterval(guardFocusedCamera, 40);

  viewer.billboardFocusGuard8095 = {
    schema: SCHEMA,
    shellMeshCount: shellMeshes.length,
    safetyGap,
    observationDistance,
    focusById(id) {
      return focusEntry(entriesById.get(id), "api");
    },
    exitFocus,
    fitOverview,
    getState() {
      return {
        schema: state.schema,
        mode: state.mode,
        selectedId: state.selectedId,
        selectedName: state.selectedName,
        collisionBlocked: state.collisionBlocked,
        collisionCount: state.collisionCount,
        shellMeshCount: state.shellMeshCount,
        safetyGap: state.safetyGap,
        observationDistance: state.observationDistance,
        cameraDistance: viewer.camera.position.distanceTo(viewer.controls.target),
        target: viewer.controls.target.toArray(),
        cameraPosition: viewer.camera.position.toArray(),
      };
    },
  };
  window[RUNTIME_KEY] = viewer.billboardFocusGuard8095;
  host.dataset.wheelZoom = "focus-shell-guard-8095";
  exposeState();

  disposeMounted = () => {
    cancelAnimationFrame(state.tweenFrame);
    clearInterval(guardTimer);
    host.removeEventListener("wheel", onWheel, true);
    canvas.removeEventListener("pointerdown", onPointerDown);
    canvas.removeEventListener("pointerup", onPointerUp);
    host.removeEventListener("click", onHostClickCapture, true);
    window.removeEventListener("keydown", onKeyDown);
    panel.remove();
    if (window[RUNTIME_KEY] === viewer.billboardFocusGuard8095) {
      delete window[RUNTIME_KEY];
    }
    delete viewer.billboardFocusGuard8095;
  };
  return true;
}

const mountTimer = window.setInterval(() => {
  const viewer = window.__BF_CAD_FURNACE_VIEWER;
  if (viewer === mountedViewer) return;
  if (!viewer?.__bf3dFurnaceBodyBillboards) return;
  disposeMounted();
  if (mount(viewer)) mountedViewer = viewer;
}, 150);

window.addEventListener(
  "beforeunload",
  () => {
    clearInterval(mountTimer);
    disposeMounted();
  },
  { once: true },
);
