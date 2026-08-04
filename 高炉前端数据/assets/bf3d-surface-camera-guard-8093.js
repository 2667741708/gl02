/**
 * 8093-only furnace-centred overview camera guard.
 *
 * REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801
 *
 * Billboard points remain hover-pickable, but no point can change the camera
 * target. OrbitControls always targets the furnace centre, supports unlimited
 * azimuth rotation, and clamps wheel dolly outside the complete model sphere.
 */
import * as THREE from "../libs/three/three.module.js";

const RUNTIME_KEY = "__BF3D_SURFACE_CAMERA_GUARD_8093__";
const VIEWER_PROPERTY = "surfaceCameraGuard8093";
const SCHEMA = "bf3d.camera.overview-only.8093.v4";
const SAFE_NEAR_PLANE = 0.05;
// Keep the whole furnace inside the viewport without the former extra 8% fit
// padding.  This makes the initial overview about 7.4% larger while the
// collision-safe minimum orbit radius below remains unchanged.
const OVERVIEW_FIT_MARGIN = 1.0;
const OVERVIEW_ORBIT_MARGIN = 1.12;

let mountedViewer = null;
let disposeMounted = () => {};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function mount(viewer) {
  if (!viewer?.camera || !viewer?.controls || !viewer?.renderer || !viewer?.model) {
    return false;
  }
  if (!viewer.__bf3dFurnaceBodyBillboards) return false;
  if (!viewer.__BF3D_PHYSICAL_POINT_FILTER_8093__) return false;

  const host = viewer.renderer.domElement.parentElement;
  if (!host) return false;

  const bodyBox = new THREE.Box3().setFromObject(viewer.model);
  if (bodyBox.isEmpty()) return false;
  const bodySphere = bodyBox.getBoundingSphere(new THREE.Sphere());
  const bodyCenter = viewer.billboardCenter?.clone?.() || bodySphere.center.clone();
  const safetyGap = clamp(bodySphere.radius * 0.025, 0.55, 1.2);
  const fullOrbitRadius =
    bodySphere.radius + bodySphere.center.distanceTo(bodyCenter) + safetyGap;
  const maxDistance = Math.max(100, fullOrbitRadius * 5);
  const state = {
    schema: SCHEMA,
    mode: "overview",
    pointFocusEnabled: false,
    safetyGap,
    fullOrbitRadius,
    overviewFitMargin: OVERVIEW_FIT_MARGIN,
    overviewOrbitMargin: OVERVIEW_ORBIT_MARGIN,
    correctionCount: 0,
    lastResetReason: "mount",
    adjusting: false,
  };

  function exposeState() {
    host.dataset.surfaceCameraGuard8093 = "ready";
    host.dataset.cameraTargetMode = "furnace-center";
    host.dataset.cameraMode = "overview";
    host.dataset.pointFocusEnabled = "false";
    host.dataset.wheelZoomMode = "full-model-radius";
    host.dataset.fullOrbitRadius = fullOrbitRadius.toFixed(3);
    host.dataset.overviewFitMargin = OVERVIEW_FIT_MARGIN.toFixed(2);
    host.dataset.overviewOrbitMargin = OVERVIEW_ORBIT_MARGIN.toFixed(2);
    host.dataset.initialFraming = "closer-whole-furnace-r1";
    host.dataset.cameraNear = viewer.camera.near.toFixed(3);
    host.dataset.cameraDistance = viewer.camera.position.distanceTo(bodyCenter).toFixed(3);
  }

  function enforceNearPlane() {
    if (Math.abs(Number(viewer.camera.near) - SAFE_NEAR_PLANE) <= 0.0005) return;
    viewer.camera.near = SAFE_NEAR_PLANE;
    viewer.camera.updateProjectionMatrix();
    state.correctionCount += 1;
  }

  function applyOverviewControls() {
    viewer.controls.target.copy(bodyCenter);
    viewer.controls.minDistance = fullOrbitRadius;
    viewer.controls.maxDistance = maxDistance;
    viewer.controls.minAzimuthAngle = -Infinity;
    viewer.controls.maxAzimuthAngle = Infinity;
    viewer.controls.enablePan = false;
  }

  function clampOutsideModel() {
    if (state.adjusting) return;
    enforceNearPlane();
    applyOverviewControls();
    const offset = viewer.camera.position.clone().sub(bodyCenter);
    const distance = offset.length();
    if (distance < fullOrbitRadius) {
      state.adjusting = true;
      if (offset.lengthSq() < 0.0001) offset.set(0.34, 0.3, 0.7);
      viewer.camera.position
        .copy(bodyCenter)
        .addScaledVector(offset.normalize(), fullOrbitRadius);
      viewer.camera.lookAt(bodyCenter);
      viewer.camera.updateMatrixWorld(true);
      viewer.controls.update();
      state.adjusting = false;
      state.correctionCount += 1;
    }
    exposeState();
  }

  function fitOverview(reason = "api") {
    const camera = viewer.camera;
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const horizontalFov =
      2 * Math.atan(Math.tan(verticalFov / 2) * Math.max(camera.aspect, 0.01));
    const limitingHalfFov = Math.max(
      THREE.MathUtils.degToRad(5),
      Math.min(verticalFov, horizontalFov) / 2,
    );
    const distance = Math.max(
      fullOrbitRadius * OVERVIEW_ORBIT_MARGIN,
      bodySphere.radius / Math.sin(limitingHalfFov) * OVERVIEW_FIT_MARGIN,
    );
    const direction = camera.position.clone().sub(bodyCenter);
    if (direction.lengthSq() < 0.0001) direction.set(0.34, 0.3, 0.7);
    state.adjusting = true;
    applyOverviewControls();
    camera.position.copy(bodyCenter).addScaledVector(direction.normalize(), distance);
    camera.near = SAFE_NEAR_PLANE;
    camera.far = Math.max(260, distance + bodySphere.radius * 4);
    camera.updateProjectionMatrix();
    camera.lookAt(bodyCenter);
    camera.updateMatrixWorld(true);
    viewer.controls.update();
    state.adjusting = false;
    state.lastResetReason = reason;
    exposeState();
    return distance;
  }

  function onWheel(event) {
    if (event.target.closest?.(".bf3d-background-control")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    applyOverviewControls();
    enforceNearPlane();
    const offset = viewer.camera.position.clone().sub(bodyCenter);
    let currentDistance = offset.length();
    if (!Number.isFinite(currentDistance) || currentDistance < 0.001) {
      offset.set(0.34, 0.3, 0.7);
      currentDistance = offset.length();
    }
    const zoomFactor = Math.exp(clamp(event.deltaY, -240, 240) * 0.0018);
    const nextDistance = clamp(
      currentDistance * zoomFactor,
      fullOrbitRadius,
      maxDistance,
    );
    state.adjusting = true;
    viewer.camera.position
      .copy(bodyCenter)
      .addScaledVector(offset.normalize(), nextDistance);
    viewer.camera.lookAt(bodyCenter);
    viewer.camera.updateMatrixWorld(true);
    viewer.controls.update();
    state.adjusting = false;
    host.dataset.lastWheelZoomAt = new Date().toISOString();
    exposeState();
  }

  function onHostClickCapture(event) {
    if (!event.target.closest?.(".bf3d-fit-full-model")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    fitOverview("full-view");
  }

  if (viewer.__bf3dWheelZoomHandler) {
    host.removeEventListener("wheel", viewer.__bf3dWheelZoomHandler, true);
    viewer.__bf3dWheelZoomHandler = null;
  }
  host.addEventListener("wheel", onWheel, { capture: true, passive: false });
  host.addEventListener("click", onHostClickCapture, true);
  viewer.controls.addEventListener?.("change", clampOutsideModel);
  const guardTimer = window.setInterval(clampOutsideModel, 100);

  viewer[VIEWER_PROPERTY] = {
    schema: SCHEMA,
    pointFocusEnabled: false,
    fitOverview,
    resetOverview(reason = "api") {
      return fitOverview(reason);
    },
    getState() {
      return {
        schema: state.schema,
        mode: state.mode,
        pointFocusEnabled: false,
        target: viewer.controls.target.toArray(),
        bodyCenter: bodyCenter.toArray(),
        cameraPosition: viewer.camera.position.toArray(),
        cameraDistance: viewer.camera.position.distanceTo(bodyCenter),
        fullOrbitRadius,
        safetyGap,
        overviewFitMargin: OVERVIEW_FIT_MARGIN,
        overviewOrbitMargin: OVERVIEW_ORBIT_MARGIN,
        correctionCount: state.correctionCount,
        lastResetReason: state.lastResetReason,
        minAzimuthAngle: viewer.controls.minAzimuthAngle,
        maxAzimuthAngle: viewer.controls.maxAzimuthAngle,
        cameraNear: viewer.camera.near,
        cameraFar: viewer.camera.far,
        visibleBillboardCount: viewer.billboardEntries?.length || 0,
      };
    },
  };
  window[RUNTIME_KEY] = viewer[VIEWER_PROPERTY];
  host.dataset.wheelZoom = "full-model-radius-8093";
  fitOverview("mount");

  disposeMounted = () => {
    window.clearInterval(guardTimer);
    host.removeEventListener("wheel", onWheel, true);
    host.removeEventListener("click", onHostClickCapture, true);
    viewer.controls.removeEventListener?.("change", clampOutsideModel);
    if (window[RUNTIME_KEY] === viewer[VIEWER_PROPERTY]) delete window[RUNTIME_KEY];
    delete viewer[VIEWER_PROPERTY];
  };
  return true;
}

const mountTimer = window.setInterval(() => {
  const viewer = window.__BF_CAD_FURNACE_VIEWER;
  if (viewer === mountedViewer) return;
  if (!viewer?.__BF3D_PHYSICAL_POINT_FILTER_8093__) return;
  disposeMounted();
  if (mount(viewer)) mountedViewer = viewer;
}, 120);

window.addEventListener(
  "beforeunload",
  () => {
    window.clearInterval(mountTimer);
    disposeMounted();
  },
  { once: true },
);
