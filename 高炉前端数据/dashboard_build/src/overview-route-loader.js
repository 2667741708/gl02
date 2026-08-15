/**
 * REQ-8093-FRONTEND-PERF-R1: load the Three.js overview runtime only when the
 * overview route is active. This entry intentionally has no static Three.js
 * import, so diagnosis/optimization/trend/QA cold loads remain lightweight.
 */

const RUNTIME_MODULES = Object.freeze([
  "/assets/bf-shared-runtime-scheduler.js?v=20260810-perf-r1",
  "/assets/bf-core-metrics-pspace-live-8093.js?v=20260810-perf-r1",
  "/assets/bf3d-furnace-body-billboard-adapter.js?v=20260810-perf-r1",
  "/assets/bf3d-physical-point-filter-8093.js?v=20260810-perf-r1",
  "/assets/bf3d-surface-camera-guard-8093.js?v=20260810-perf-r1",
  "/assets/bf3d-tooltip-stable-hover-8093.js?v=20260806-local-133-r1",
]);

const state = {
  schema: "bf.overview.route-loader.v1",
  status: "idle",
  loadedAt: "",
  error: "",
  modules: [...RUNTIME_MODULES],
};

let loadPromise = null;

function activeRoute() {
  return (window.location.hash || "#overview").slice(1) || "overview";
}

function publish() {
  document.documentElement.dataset.overviewRuntimeStatus = state.status;
  window.__BF_OVERVIEW_ROUTE_LOADER__ = {
    ...state,
    load: loadOverviewRuntime,
  };
}

async function importRuntime(url) {
  return import(/* @vite-ignore */ url);
}

function loadOverviewRuntime() {
  if (loadPromise) return loadPromise;
  state.status = "loading";
  state.error = "";
  publish();
  loadPromise = (async () => {
    // The scheduler and the shared 8770 transport must exist before the 3D
    // consumers mount, otherwise each consumer would create its own timer or
    // WebSocket during the same navigation.
    await importRuntime(RUNTIME_MODULES[0]);
    await importRuntime(RUNTIME_MODULES[1]);
    // Preserve the source-page adapter -> filter -> camera -> tooltip order.
    // These modules all attach to the same viewer, so parallel evaluation can
    // make their initial layout race even though the final feature set matches.
    for (const moduleUrl of RUNTIME_MODULES.slice(2)) {
      await importRuntime(moduleUrl);
    }
    state.status = "loaded";
    state.loadedAt = new Date().toISOString();
    publish();
  })().catch((error) => {
    state.status = "error";
    state.error = String(error?.message || error);
    loadPromise = null;
    publish();
    throw error;
  });
  return loadPromise;
}

function activateForRoute() {
  if (activeRoute() !== "overview") return;
  void loadOverviewRuntime();
}

window.addEventListener("hashchange", activateForRoute);
publish();
queueMicrotask(activateForRoute);
