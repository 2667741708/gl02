/**
 * Port-scoped furnace-surface camera target and shell collision guard.
 *
 * REQ-BF3D-8094-SURFACE-CAMERA-GUARD-20260801
 * The default scope remains 8094.  The 8093 compatibility entry sets
 * __BF3D_SURFACE_CAMERA_GUARD_SCOPE__ before importing this module so both
 * ports share the same collision algorithm without sharing runtime keys.
 *
 * The 133-point adapter originally performs wheel dolly towards the model
 * bounding-sphere centre.  That target is inside the furnace, so repeated
 * wheel input can move the camera through the shell.  This overlay keeps the
 * OrbitControls target on the first visible fitted-shell surface and clamps
 * every inward camera move before the shell safety gap.
 */
import * as THREE from "../libs/three/three.module.js";

const PORT_SCOPE = String(window.__BF3D_SURFACE_CAMERA_GUARD_SCOPE__ || "8094");
const RUNTIME_KEY = `__BF3D_SURFACE_CAMERA_GUARD_${PORT_SCOPE}__`;
const VIEWER_PROPERTY = `surfaceCameraGuard${PORT_SCOPE}`;
const SCHEMA = `bf3d.surface-camera-shell-guard.${PORT_SCOPE}.v1`;
const SHELL_NAME = "IMG2THREEJS_FITTED_GL02_SHELL";
const SAFE_NEAR_PLANE = PORT_SCOPE === "8093" ? 0.05 : null;

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

  const host = viewer.renderer.domElement.parentElement;
  if (!host) return false;

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
  if (bodyBox.isEmpty()) return false;
  const bodySphere = bodyBox.getBoundingSphere(new THREE.Sphere());
  const bodyCenter = viewer.billboardCenter?.clone?.() || bodySphere.center.clone();
  const safetyGap = clamp(bodySphere.radius * 0.042, 1.2, 2.1);
  const targetOffset = clamp(safetyGap * 0.05, 0.06, 0.1);
  const maxDistance = Math.max(86, bodySphere.radius * 5);
  const shellRaycaster = new THREE.Raycaster();
  const normalMatrix = new THREE.Matrix3();
  const state = {
    schema: SCHEMA,
    mode: "furnace-surface",
    shellMeshCount: shellMeshes.length,
    safetyGap,
    targetOffset,
    collisionBlocked: false,
    collisionCount: 0,
    surfacePoint: null,
    surfaceNormal: null,
    surfaceTarget: null,
    surfaceTargetSource: "",
    lastSafePosition: viewer.camera.position.clone(),
    adjusting: false,
    resetReason: "mount",
    nearPlaneLocked: SAFE_NEAR_PLANE !== null,
    safeNearPlane: SAFE_NEAR_PLANE,
    nearPlaneCorrectionCount: 0,
    nearPlaneCorrectionReason: "",
  };

  function exposeState() {
    host.dataset[`surfaceCameraGuard${PORT_SCOPE}`] = "ready";
    host.dataset.cameraTargetMode = state.mode;
    host.dataset.shellMeshCount = String(state.shellMeshCount);
    host.dataset.shellSafetyGap = state.safetyGap.toFixed(3);
    host.dataset.collisionBlocked = String(state.collisionBlocked);
    host.dataset.collisionCount = String(state.collisionCount);
    host.dataset.wheelZoomMode = "furnace-surface";
    host.dataset.cameraNear = viewer.camera.near.toFixed(3);
    host.dataset.nearPlaneLocked = String(state.nearPlaneLocked);
    if (state.safeNearPlane !== null) {
      host.dataset.safeNearPlane = state.safeNearPlane.toFixed(3);
    }
    host.dataset.cameraDistance = viewer.camera.position
      .distanceTo(viewer.controls.target)
      .toFixed(3);
  }

  function enforceSafeNearPlane(reason = "guard") {
    if (!state.nearPlaneLocked || state.safeNearPlane === null) return false;
    const camera = viewer.camera;
    if (
      Number.isFinite(camera.near) &&
      Math.abs(camera.near - state.safeNearPlane) <= 0.0005
    ) {
      return false;
    }
    camera.near = state.safeNearPlane;
    camera.updateProjectionMatrix();
    state.nearPlaneCorrectionCount += 1;
    state.nearPlaneCorrectionReason = reason;
    return true;
  }

  function markCollision(blocked) {
    state.collisionBlocked = blocked;
    if (blocked) state.collisionCount += 1;
    exposeState();
  }

  function firstShellHit(origin, direction, far) {
    if (!shellMeshes.length || !Number.isFinite(far) || far <= 0) return null;
    shellRaycaster.set(origin, direction);
    shellRaycaster.near = 0;
    shellRaycaster.far = far;
    return shellRaycaster.intersectObjects(shellMeshes, false)[0] || null;
  }

  function outwardNormal(hit, radial) {
    let normal = radial.clone();
    if (hit?.face?.normal && hit.object?.matrixWorld) {
      normalMatrix.getNormalMatrix(hit.object.matrixWorld);
      normal = hit.face.normal.clone().applyMatrix3(normalMatrix).normalize();
      if (normal.dot(radial) < 0) normal.negate();
    }
    return normal;
  }

  function findVisibleSurface(cameraPosition = viewer.camera.position) {
    const toCenter = bodyCenter.clone().sub(cameraPosition);
    const far = toCenter.length() + bodySphere.radius * 1.5;
    if (far < 0.001) return null;
    const direction = toCenter.normalize();
    const hit = firstShellHit(cameraPosition, direction, far);
    if (hit) {
      const radial = hit.point.clone().sub(bodyCenter).normalize();
      const normal = outwardNormal(hit, radial);
      return {
        point: hit.point.clone(),
        normal,
        target: hit.point.clone().addScaledVector(normal, targetOffset),
        source: "shell-raycast",
      };
    }

    const radial = cameraPosition.clone().sub(bodyCenter);
    if (radial.lengthSq() < 0.0001) radial.set(0.34, 0.3, 0.7);
    radial.normalize();
    const point = bodyCenter.clone().addScaledVector(radial, bodySphere.radius * 0.48);
    return {
      point,
      normal: radial,
      target: point.clone().addScaledVector(radial, targetOffset),
      source: "bounding-sphere-fallback",
    };
  }

  function applySurfaceTarget(surface, reason = "reset") {
    if (!surface) return false;
    state.surfacePoint = surface.point;
    state.surfaceNormal = surface.normal;
    state.surfaceTarget = surface.target;
    state.surfaceTargetSource = surface.source;
    state.resetReason = reason;
    state.collisionBlocked = false;
    viewer.controls.target.copy(surface.target);
    viewer.controls.minDistance = safetyGap;
    viewer.controls.maxDistance = maxDistance;
    viewer.controls.enablePan = false;
    enforceSafeNearPlane(`surface-target:${reason}`);
    viewer.camera.lookAt(surface.target);
    viewer.camera.updateMatrixWorld(true);
    viewer.controls.update();
    state.lastSafePosition.copy(viewer.camera.position);
    host.dataset.surfaceTargetSource = surface.source;
    host.dataset.surfaceResetReason = reason;
    exposeState();
    return true;
  }

  function resetSurfaceFocus(reason = "api") {
    return applySurfaceTarget(findVisibleSurface(viewer.camera.position), reason);
  }

  function fitSurfaceOverview(reason = "full-view") {
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
    state.adjusting = true;
    camera.position.copy(bodyCenter).addScaledVector(direction, distance);
    camera.near = state.nearPlaneLocked ? state.safeNearPlane : 0.08;
    camera.far = Math.max(260, distance + bodySphere.radius * 4);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
    state.adjusting = false;
    resetSurfaceFocus(reason);
    return distance;
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
    if (event.target.closest?.(".bf3d-background-control")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    enforceSafeNearPlane("wheel");
    const target = viewer.controls.target;
    const offset = viewer.camera.position.clone().sub(target);
    let currentDistance = offset.length();
    if (!Number.isFinite(currentDistance) || currentDistance < 0.001) {
      offset.copy(state.surfaceNormal || new THREE.Vector3(0.34, 0.3, 0.7));
      currentDistance = offset.length();
    }
    const zoomFactor = Math.exp(clamp(event.deltaY, -240, 240) * 0.0018);
    const rawNextDistance = currentDistance * zoomFactor;
    const nextDistance = clamp(rawNextDistance, safetyGap, maxDistance);
    const requested = target.clone().addScaledVector(offset.normalize(), nextDistance);
    const inward = nextDistance < currentDistance;
    const safePosition = inward
      ? constrainCameraMove(viewer.camera.position, requested)
      : requested;
    if (event.deltaY < 0 && rawNextDistance <= safetyGap + 0.0001) {
      markCollision(true);
    }
    state.adjusting = true;
    viewer.camera.position.copy(safePosition);
    viewer.camera.lookAt(target);
    viewer.camera.updateMatrixWorld(true);
    viewer.controls.update();
    state.adjusting = false;
    guardCamera();
    state.lastSafePosition.copy(viewer.camera.position);
    host.dataset.lastWheelZoomAt = new Date().toISOString();
    exposeState();
  }

  function guardCamera() {
    const nearCorrected = enforceSafeNearPlane("periodic-guard");
    if (nearCorrected) exposeState();
    if (state.adjusting || !state.surfacePoint || !state.surfaceNormal) return;
    const camera = viewer.camera;
    const signedGap = camera.position
      .clone()
      .sub(state.surfacePoint)
      .dot(state.surfaceNormal);
    const targetDistance = camera.position.distanceTo(viewer.controls.target);
    if (signedGap >= safetyGap && targetDistance >= safetyGap) {
      state.lastSafePosition.copy(camera.position);
      exposeState();
      return;
    }

    state.adjusting = true;
    if (signedGap < safetyGap) {
      camera.position.addScaledVector(state.surfaceNormal, safetyGap - signedGap);
    }
    const offset = camera.position.clone().sub(viewer.controls.target);
    if (offset.length() < safetyGap) {
      if (offset.lengthSq() < 0.0001) offset.copy(state.surfaceNormal);
      camera.position
        .copy(viewer.controls.target)
        .addScaledVector(offset.normalize(), safetyGap);
    }
    camera.lookAt(viewer.controls.target);
    camera.updateMatrixWorld(true);
    viewer.controls.update();
    state.adjusting = false;
    state.lastSafePosition.copy(camera.position);
    markCollision(true);
  }

  function onHostClickCapture(event) {
    if (!event.target.closest?.(".bf3d-fit-full-model")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    fitSurfaceOverview("full-view");
  }

  if (viewer.__bf3dWheelZoomHandler) {
    host.removeEventListener("wheel", viewer.__bf3dWheelZoomHandler, true);
    viewer.__bf3dWheelZoomHandler = null;
  }
  host.addEventListener("wheel", onWheel, { capture: true, passive: false });
  host.addEventListener("click", onHostClickCapture, true);
  viewer.controls.addEventListener?.("change", guardCamera);
  const guardTimer = window.setInterval(guardCamera, 80);

  viewer[VIEWER_PROPERTY] = {
    schema: SCHEMA,
    shellMeshCount: shellMeshes.length,
    safetyGap,
    resetSurfaceFocus,
    fitSurfaceOverview,
    getState() {
      return {
        schema: state.schema,
        mode: state.mode,
        collisionBlocked: state.collisionBlocked,
        collisionCount: state.collisionCount,
        shellMeshCount: state.shellMeshCount,
        safetyGap: state.safetyGap,
        surfacePoint: state.surfacePoint?.toArray?.() || null,
        surfaceNormal: state.surfaceNormal?.toArray?.() || null,
        target: viewer.controls.target.toArray(),
        cameraPosition: viewer.camera.position.toArray(),
        cameraDistance: viewer.camera.position.distanceTo(viewer.controls.target),
        targetDistanceFromBodyCenter: viewer.controls.target.distanceTo(bodyCenter),
        targetDistanceFromSurface: state.surfacePoint
          ? viewer.controls.target.distanceTo(state.surfacePoint)
          : null,
        surfaceTargetSource: state.surfaceTargetSource,
        bodyRadius: bodySphere.radius,
        resetReason: state.resetReason,
        cameraNear: viewer.camera.near,
        cameraFar: viewer.camera.far,
        nearPlaneLocked: state.nearPlaneLocked,
        safeNearPlane: state.safeNearPlane,
        nearPlaneCorrectionCount: state.nearPlaneCorrectionCount,
        nearPlaneCorrectionReason: state.nearPlaneCorrectionReason,
      };
    },
  };
  window[RUNTIME_KEY] = viewer[VIEWER_PROPERTY];
  host.dataset.wheelZoom = `surface-shell-guard-${PORT_SCOPE}`;
  resetSurfaceFocus("mount");

  disposeMounted = () => {
    clearInterval(guardTimer);
    host.removeEventListener("wheel", onWheel, true);
    host.removeEventListener("click", onHostClickCapture, true);
    viewer.controls.removeEventListener?.("change", guardCamera);
    if (window[RUNTIME_KEY] === viewer[VIEWER_PROPERTY]) {
      delete window[RUNTIME_KEY];
    }
    delete viewer[VIEWER_PROPERTY];
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
