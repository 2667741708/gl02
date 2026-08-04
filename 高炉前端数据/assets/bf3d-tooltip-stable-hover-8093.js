/**
 * Stable, single-owner Billboard hover controller for the 8093 overview.
 *
 * BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802
 * REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802
 *
 * The legacy page contains multiple tooltip writers with different coordinate
 * systems.  The 8093 deployment pre-disables those compatibility writers;
 * this module then owns hit selection, content, visibility and positioning.
 */

const SCHEMA = "bf3d.tooltip.stable-hover.8093.v1";
const REQ_ID = "BUG-BF3D-8093-TOOLTIP-JITTER-SINGLE-OWNER-20260802";
const EMPHASIS_REQ_ID = "REQ-BF3D-8093-BILLBOARD-EMPHASIS-20260802";
const RUNTIME_KEY = "__BF3D_STABLE_TOOLTIP_HOVER_8093__";
const BILLBOARD_SCALE_MULTIPLIER = 1.22;
const BILLBOARD_SCALE_PATCH_KEY = "__bf3dBillboardEmphasis8093";
const CONFIG = Object.freeze({
  enterRadiusPx: 30,
  exitRadiusPx: 46,
  switchMarginPx: 12,
  switchDwellMs: 140,
  anchorGapPx: 16,
  viewportMarginPx: 10,
});

{
  let installedViewer = null;
  let disposeInstalled = () => {};
  let bootTimer = 0;

  const clamp = (value, minimum, maximum) => {
    if (maximum < minimum) return minimum;
    return Math.max(minimum, Math.min(maximum, value));
  };

  const finiteNumber = (value) => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  function entryId(entry) {
    return (
      entry?.bindingId ||
      entry?.point?.canonical_id ||
      entry?.point?.data_binding_key ||
      entry?.point?.id ||
      entry?.sprite?.userData?.sensorId ||
      ""
    );
  }

  function installBillboardEmphasis(viewer, host) {
    const patchedSprites = [];
    for (const entry of viewer.billboardEntries || []) {
      const sprite = entry?.sprite;
      const scale = sprite?.scale;
      if (!sprite || !scale || typeof scale.set !== "function") continue;
      if (sprite.userData?.[BILLBOARD_SCALE_PATCH_KEY]) {
        patchedSprites.push(sprite);
        continue;
      }
      const originalSet = scale.set;
      scale.set = function setEmphasizedBillboardScale(x, y, z) {
        return originalSet.call(
          this,
          Number(x) * BILLBOARD_SCALE_MULTIPLIER,
          Number(y) * BILLBOARD_SCALE_MULTIPLIER,
          z,
        );
      };
      originalSet.call(
        scale,
        scale.x * BILLBOARD_SCALE_MULTIPLIER,
        scale.y * BILLBOARD_SCALE_MULTIPLIER,
        scale.z,
      );
      sprite.userData[BILLBOARD_SCALE_PATCH_KEY] = {
        factor: BILLBOARD_SCALE_MULTIPLIER,
        originalSet,
      };
      patchedSprites.push(sprite);
    }

    viewer.billboardEmphasisScale = BILLBOARD_SCALE_MULTIPLIER;
    viewer.billboardEmphasisReqId = EMPHASIS_REQ_ID;
    host.dataset.billboardEmphasisScale = String(BILLBOARD_SCALE_MULTIPLIER);
    host.dataset.billboardEmphasis = "moderate-8093";

    return () => {
      for (const sprite of patchedSprites) {
        const marker = sprite?.userData?.[BILLBOARD_SCALE_PATCH_KEY];
        const scale = sprite?.scale;
        if (!marker || !scale || typeof marker.originalSet !== "function") {
          continue;
        }
        const currentX = scale.x;
        const currentY = scale.y;
        const currentZ = scale.z;
        scale.set = marker.originalSet;
        marker.originalSet.call(
          scale,
          currentX / marker.factor,
          currentY / marker.factor,
          currentZ,
        );
        delete sprite.userData[BILLBOARD_SCALE_PATCH_KEY];
      }
      delete viewer.billboardEmphasisScale;
      delete viewer.billboardEmphasisReqId;
      delete host.dataset.billboardEmphasisScale;
      delete host.dataset.billboardEmphasis;
    };
  }

  function fallbackTooltip(entry, sensorId) {
    const point = entry?.point || {};
    const value = finiteNumber(point.realtime_value);
    const label =
      point.semantic_name_cn ||
      point.short_label ||
      point.chinese_name ||
      sensorId;
    const unit = point.display_unit || point.unit || "";
    const valueText = value === null ? "--" : value.toFixed(1);
    const height = finiteNumber(point.elevation_m ?? point.position?.[1]);
    return (
      `<strong>${escapeHtml(label)}</strong>` +
      `<div class="value">${escapeHtml(valueText)} ${escapeHtml(unit)}</div>` +
      `<div>点位：<b>${escapeHtml(sensorId)}</b></div>` +
      (height === null ? "" : `<div>标高：${height.toFixed(3)} m</div>`) +
      `<div class="muted">CAD GLB 节点：SENSOR_${escapeHtml(sensorId)}</div>`
    );
  }

  function tooltipContent(viewer, entry, sensorId) {
    const formatter = window.__BF3D_CAD_SENSOR_TOOLTIP_8093__;
    const buffer = viewer.getBuffer?.();
    if (typeof formatter === "function" && buffer) {
      try {
        return formatter(buffer, sensorId);
      } catch (error) {
        console.warn("8093 tooltip formatter fallback", error);
      }
    }
    return fallbackTooltip(entry, sensorId);
  }

  function install(viewer) {
    const canvas = viewer?.renderer?.domElement;
    const host = canvas?.parentElement;
    const tip = document.querySelector(".cad-furnace-tooltip");
    const entries = viewer?.billboardEntries;
    if (!canvas?.isConnected || !host || !tip || !Array.isArray(entries)) return false;

    const state = {
      activeId: "",
      activeEntry: null,
      candidateId: "",
      candidateSince: 0,
      candidateTimer: 0,
      side: "right",
      pointerX: 0,
      pointerY: 0,
      pointerInside: false,
      dragging: false,
      frame: 0,
      disposed: false,
      switches: 0,
      lastReason: "installed",
      lastHtml: "",
      lastContentAt: 0,
    };
    const projected = new Map();
    // The deployed 8093 viewer does not expose its imported THREE namespace.
    // Reuse the camera's Vector3 type instead of requiring viewer.THREE.
    const worldPosition = viewer.camera.position.clone();
    const ndc = viewer.camera.position.clone();

    tip.style.setProperty("position", "fixed", "important");
    tip.style.setProperty("transform", "none", "important");
    tip.style.setProperty("pointer-events", "none", "important");
    tip.style.setProperty("z-index", "2147483647", "important");
    tip.style.setProperty("will-change", "left, top", "important");
    host.dataset.tooltipOwner = "stable-hover-8093";
    host.dataset.tooltipCoordinateSpace = "viewport-fixed";
    host.dataset.tooltipSelection = "screen-space-hysteresis";
    const releaseBillboardEmphasis = installBillboardEmphasis(viewer, host);

    function entriesNow() {
      return Array.isArray(viewer.billboardEntries) ? viewer.billboardEntries : [];
    }

    function projectEntries() {
      projected.clear();
      const rect = canvas.getBoundingClientRect();
      for (const entry of entriesNow()) {
        const id = entryId(entry);
        const object = entry?.sprite;
        if (!id || !object?.visible || !object.parent) continue;
        object.getWorldPosition(worldPosition);
        ndc.copy(worldPosition).project(viewer.camera);
        if (!Number.isFinite(ndc.x) || !Number.isFinite(ndc.y) || ndc.z < -1 || ndc.z > 1) {
          continue;
        }
        projected.set(id, {
          id,
          entry,
          x: rect.left + ((ndc.x + 1) * rect.width) / 2,
          y: rect.top + ((1 - ndc.y) * rect.height) / 2,
          z: ndc.z,
        });
      }
      return rect;
    }

    function distanceTo(item) {
      return item ? Math.hypot(state.pointerX - item.x, state.pointerY - item.y) : Infinity;
    }

    function nearestProjected() {
      let best = null;
      let bestDistance = Infinity;
      for (const item of projected.values()) {
        const distance = distanceTo(item);
        if (
          distance < bestDistance - 0.25 ||
          (Math.abs(distance - bestDistance) <= 0.25 && item.z < (best?.z ?? Infinity))
        ) {
          best = item;
          bestDistance = distance;
        }
      }
      return { item: best, distance: bestDistance };
    }

    function chooseSide(item) {
      const rect = canvas.getBoundingClientRect();
      const width = tip.getBoundingClientRect().width || 330;
      const roomRight = rect.right - item.x;
      const roomLeft = item.x - rect.left;
      return roomRight >= width + CONFIG.anchorGapPx || roomRight >= roomLeft ? "right" : "left";
    }

    function setActive(item, reason) {
      const nextId = item?.id || "";
      if (nextId === state.activeId) return;
      if (state.activeId && nextId) state.switches += 1;
      state.activeId = nextId;
      state.activeEntry = item?.entry || null;
      window.clearTimeout(state.candidateTimer);
      state.candidateTimer = 0;
      state.candidateId = "";
      state.candidateSince = 0;
      state.lastReason = reason;
      host.dataset.hoverSensor = nextId;
      host.dataset.tooltipSwitches = String(state.switches);
      if (!item) {
        state.lastHtml = "";
        state.lastContentAt = 0;
        tip.style.display = "none";
        return;
      }
      state.lastHtml = tooltipContent(viewer, item.entry, item.id);
      state.lastContentAt = performance.now();
      tip.innerHTML = state.lastHtml;
      tip.style.display = "block";
      state.side = chooseSide(item);
      host.dataset.tooltipSide = state.side;
    }

    function clear(reason) {
      setActive(null, reason);
    }

    function resolveSelection(now) {
      if (!state.pointerInside || state.dragging) {
        clear(state.dragging ? "camera-drag" : "pointer-leave");
        return;
      }
      const activeItem = projected.get(state.activeId);
      const activeDistance = distanceTo(activeItem);
      const nearest = nearestProjected();

      if (!activeItem || activeDistance > CONFIG.exitRadiusPx) {
        if (nearest.item && nearest.distance <= CONFIG.enterRadiusPx) {
          setActive(nearest.item, activeItem ? "active-exit" : "enter-radius");
        } else {
          clear("outside-enter-radius");
        }
        return;
      }

      if (
        !nearest.item ||
        nearest.item.id === activeItem.id ||
        nearest.distance + CONFIG.switchMarginPx >= activeDistance
      ) {
        window.clearTimeout(state.candidateTimer);
        state.candidateTimer = 0;
        state.candidateId = "";
        state.candidateSince = 0;
        return;
      }

      if (state.candidateId !== nearest.item.id) {
        window.clearTimeout(state.candidateTimer);
        state.candidateId = nearest.item.id;
        state.candidateSince = now;
        state.candidateTimer = window.setTimeout(schedule, CONFIG.switchDwellMs + 1);
        return;
      }
      if (now - state.candidateSince >= CONFIG.switchDwellMs) {
        setActive(nearest.item, "switch-dwell");
      }
    }

    function placeTip() {
      const item = projected.get(state.activeId);
      if (!item || tip.style.display === "none") return;
      const canvasRect = canvas.getBoundingClientRect();
      const tipRect = tip.getBoundingClientRect();
      const width = tipRect.width || 330;
      const height = tipRect.height || 150;
      const margin = CONFIG.viewportMarginPx;
      const minimumLeft = Math.max(margin, canvasRect.left + margin);
      const maximumLeft = Math.min(window.innerWidth - width - margin, canvasRect.right - width - margin);
      const minimumTop = Math.max(margin, canvasRect.top + margin);
      const maximumTop = Math.min(window.innerHeight - height - margin, canvasRect.bottom - height - margin);
      const desiredLeft =
        state.side === "left"
          ? item.x - width - CONFIG.anchorGapPx
          : item.x + CONFIG.anchorGapPx;
      const left = clamp(desiredLeft, minimumLeft, maximumLeft);
      const top = clamp(item.y - height / 2, minimumTop, maximumTop);
      tip.style.setProperty("left", `${Math.round(left)}px`, "important");
      tip.style.setProperty("top", `${Math.round(top)}px`, "important");
    }

    function update(now = performance.now()) {
      state.frame = 0;
      if (state.disposed || !canvas.isConnected) return;
      projectEntries();
      resolveSelection(now);
      if (state.activeId) {
        if (now - state.lastContentAt >= 1000) {
          const html = tooltipContent(viewer, state.activeEntry, state.activeId);
          if (html !== state.lastHtml) {
            state.lastHtml = html;
            tip.innerHTML = html;
          }
          state.lastContentAt = now;
        }
        placeTip();
      }
    }

    function schedule() {
      if (!state.frame) state.frame = requestAnimationFrame(update);
    }

    function onPointerMoveCapture(event) {
      if (event.buttons) {
        state.dragging = true;
        state.pointerInside = false;
        requestAnimationFrame(() => clear("camera-drag"));
        return;
      }
      // The legacy mouse-follow writer is a bubble listener on this canvas.
      // Stop only hover moves; pointerdown/drag remains owned by OrbitControls.
      event.stopImmediatePropagation();
      state.dragging = false;
      state.pointerInside = true;
      state.pointerX = event.clientX;
      state.pointerY = event.clientY;
      schedule();
    }

    function onPointerMoveAfterDrag(event) {
      if (event.buttons) requestAnimationFrame(() => clear("camera-drag"));
    }

    function onPointerLeave() {
      state.pointerInside = false;
      window.clearTimeout(state.candidateTimer);
      state.candidateTimer = 0;
      state.candidateId = "";
      state.candidateSince = 0;
      clear("pointer-leave");
    }

    function onControlStart() {
      state.dragging = true;
      clear("camera-drag");
    }

    function onControlChange() {
      if (!state.dragging && state.activeId) schedule();
    }

    function onControlEnd() {
      state.dragging = false;
      state.pointerInside = false;
      clear("camera-end-await-pointer");
    }

    function onResize() {
      if (state.activeId) {
        const item = projected.get(state.activeId);
        if (item) state.side = chooseSide(item);
      }
      schedule();
    }

    canvas.addEventListener("pointermove", onPointerMoveCapture, { capture: true });
    canvas.addEventListener("pointermove", onPointerMoveAfterDrag);
    canvas.addEventListener("pointerleave", onPointerLeave, { capture: true });
    viewer.controls?.addEventListener?.("start", onControlStart);
    viewer.controls?.addEventListener?.("change", onControlChange);
    viewer.controls?.addEventListener?.("end", onControlEnd);
    window.addEventListener("resize", onResize);
    window.addEventListener("blur", onPointerLeave);

    const runtime = {
      schema: SCHEMA,
      reqId: REQ_ID,
      config: CONFIG,
      singleWriter: true,
      coordinateSpace: "viewport-fixed",
      selectionPolicy: "screen-space-hysteresis",
      pointFocusEnabled: false,
      legacyWritersDisabled: true,
      billboardEmphasisScale: BILLBOARD_SCALE_MULTIPLIER,
      billboardEmphasisReqId: EMPHASIS_REQ_ID,
      getState: () => ({
        activeId: state.activeId,
        candidateId: state.candidateId,
        side: state.side,
        switches: state.switches,
        lastReason: state.lastReason,
        dragging: state.dragging,
      }),
      hide: () => clear("api-hide"),
      dispose: () => dispose(),
    };
    window[RUNTIME_KEY] = runtime;

    function dispose() {
      if (state.disposed) return;
      state.disposed = true;
      cancelAnimationFrame(state.frame);
      window.clearTimeout(state.candidateTimer);
      canvas.removeEventListener("pointermove", onPointerMoveCapture, { capture: true });
      canvas.removeEventListener("pointermove", onPointerMoveAfterDrag);
      canvas.removeEventListener("pointerleave", onPointerLeave, { capture: true });
      viewer.controls?.removeEventListener?.("start", onControlStart);
      viewer.controls?.removeEventListener?.("change", onControlChange);
      viewer.controls?.removeEventListener?.("end", onControlEnd);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("blur", onPointerLeave);
      clear("dispose");
      releaseBillboardEmphasis();
      delete host.dataset.tooltipOwner;
    }

    return dispose;
  }

  function boot() {
    const viewer = window.__BF_CAD_FURNACE_VIEWER;
    if (
      window.__BF3D_HOVER_SINGLE_OWNER_8093__ &&
      viewer &&
      viewer !== installedViewer &&
      viewer.__bf3dFurnaceBodyBillboards &&
      Array.isArray(viewer.billboardEntries)
    ) {
      const nextDispose = install(viewer);
      // The adapter and React viewer become ready in separate tasks.  A
      // failed early install must remain retryable; otherwise this viewer is
      // permanently skipped even after its canvas/tooltip enters the DOM.
      if (typeof nextDispose === "function") {
        disposeInstalled();
        disposeInstalled = nextDispose;
        installedViewer = viewer;
      }
    }
    bootTimer = window.setTimeout(boot, 120);
  }

  boot();
  window.addEventListener(
    "beforeunload",
    () => {
      window.clearTimeout(bootTimer);
      disposeInstalled();
    },
    { once: true },
  );
}
