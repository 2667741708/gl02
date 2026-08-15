/**
 * Keep physical and equipment-located measurements in the 8093 furnace scene.
 *
 * REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801
 *
 * The shared Billboard adapter deliberately retains the full 133-point data
 * contract for 8094.  This 8093-only post-adapter filter mutates the adapter's
 * live arrays in place so hover picking and realtime updates retain:
 *
 * - 80 furnace-body temperature sensors;
 * - 18 A-F static-pressure sensors at three elevations;
 * - 2 south/north taphole temperature sensors;
 * - 21 equipment/pipeline/top measurement tags with concrete semantics.
 *
 * Nine process calculations/set-points/aggregates and three legacy height
 * summaries remain available in the page's unchanged left-side variable
 * panels, but are not rendered or pickable on the furnace body.
 */

const REQ_ID = "REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801";
const RUNTIME_KEY = "__BF3D_PHYSICAL_POINT_FILTER_8093__";
const EXCLUDED_IDS = new Set([
  "DP_upper",
  "DP_lower",
  "DP_total",
  "PI",
  "GasUtil",
  "TFT",
  "PCI_set",
  "L",
  "P_top",
  "P_static_20m35",
  "P_static_23m49",
  "P_static_28m98",
]);
const EXPECTED_COUNTS = Object.freeze({
  bodyTemperature: 80,
  staticPressure: 18,
  tapholeTemperature: 2,
  equipmentMeasurement: 21,
  shellPhysical: 100,
  visible: 121,
  excluded: 12,
});

let mountedViewer = null;

function pointId(point) {
  return point?.canonical_id || point?.data_binding_key || point?.id || "";
}

function shouldKeepPoint(point) {
  return !EXCLUDED_IDS.has(pointId(point));
}

function isShellPhysicalPoint(point) {
  const id = pointId(point);
  return (
    point?.category === "body_temperature" ||
    point?.source_kind === "static_pressure_18" ||
    point?.category === "taphole_temperature" ||
    /^T_body_L(?:7|8|9|1[0-6])_[A-H]$/.test(id) ||
    /^P_static_(?:lower|middle|upper)_[A-F]$/.test(id) ||
    /^T_taphole_[12]$/.test(id)
  );
}

function pointCategory(point) {
  const id = pointId(point);
  if (point?.category === "body_temperature" || /^T_body_/.test(id)) {
    return "bodyTemperature";
  }
  if (point?.source_kind === "static_pressure_18" || /^P_static_(?:lower|middle|upper)_/.test(id)) {
    return "staticPressure";
  }
  if (point?.category === "taphole_temperature" || /^T_taphole_/.test(id)) {
    return "tapholeTemperature";
  }
  return "equipmentMeasurement";
}

function removeObject(object) {
  if (!object) return;
  object.visible = false;
  object.parent?.remove?.(object);
}

function disposeSprite(sprite) {
  if (!sprite?.isSprite) return;
  sprite.material?.map?.dispose?.();
  sprite.material?.dispose?.();
}

function mount(viewer) {
  if (!viewer?.__bf3dFurnaceBodyBillboards || !Array.isArray(viewer.billboardEntries)) {
    return false;
  }
  if (viewer[RUNTIME_KEY]) return true;

  const allEntries = [...viewer.billboardEntries];
  const visibleEntries = allEntries.filter((entry) => shouldKeepPoint(entry.point));
  const excludedEntries = allEntries.filter((entry) => !shouldKeepPoint(entry.point));
  const visibleIds = new Set(visibleEntries.map((entry) => entry.bindingId));
  const counts = visibleEntries.reduce(
    (result, entry) => {
      result[pointCategory(entry.point)] += 1;
      return result;
    },
    {
      bodyTemperature: 0,
      staticPressure: 0,
      tapholeTemperature: 0,
      equipmentMeasurement: 0,
    },
  );
  const excludedIds = new Set(excludedEntries.map((entry) => entry.bindingId));

  if (
    allEntries.length !== EXPECTED_COUNTS.visible + EXPECTED_COUNTS.excluded ||
    visibleEntries.length !== EXPECTED_COUNTS.visible ||
    excludedEntries.length !== EXPECTED_COUNTS.excluded ||
    counts.bodyTemperature !== EXPECTED_COUNTS.bodyTemperature ||
    counts.staticPressure !== EXPECTED_COUNTS.staticPressure ||
    counts.tapholeTemperature !== EXPECTED_COUNTS.tapholeTemperature ||
    counts.equipmentMeasurement !== EXPECTED_COUNTS.equipmentMeasurement ||
    [...EXCLUDED_IDS].some((id) => !excludedIds.has(id))
  ) {
    throw new Error(
      `8093 physical-point contract mismatch: total=${allEntries.length}, ` +
        `visible=${visibleEntries.length}, excluded=${excludedEntries.length}, ` +
        `body=${counts.bodyTemperature}, pressure=${counts.staticPressure}, ` +
        `taphole=${counts.tapholeTemperature}, equipment=${counts.equipmentMeasurement}`,
    );
  }

  const excludedSprites = new Set(excludedEntries.map((entry) => entry.sprite));
  const visibleHits = viewer.hitObjects.filter((object) =>
    visibleIds.has(object?.userData?.sensorId || object?.userData?.canonicalId),
  );
  const excludedHits = viewer.hitObjects.filter((object) => !visibleHits.includes(object));

  excludedEntries.forEach((entry) => {
    removeObject(entry.sprite);
    disposeSprite(entry.sprite);
  });
  excludedHits.forEach(removeObject);

  // Mutate rather than replace: the viewer and the shared adapter keep these
  // array references inside their hover/realtime closures.
  viewer.billboardEntries.splice(0, viewer.billboardEntries.length, ...visibleEntries);
  viewer.hitObjects.splice(0, viewer.hitObjects.length, ...visibleHits);
  viewer.sensorObjects.splice(
    0,
    viewer.sensorObjects.length,
    ...viewer.sensorObjects.filter((object) => !excludedSprites.has(object)),
  );

  viewer.sensorCount = viewer.sensorObjects.length;
  viewer.hitCount = viewer.hitObjects.length;
  viewer.mappedCount = visibleEntries.length;
  viewer.billboardCount = visibleEntries.length;
  viewer.physicalPointCount = EXPECTED_COUNTS.shellPhysical;
  viewer.equipmentMeasurementPointCount = counts.equipmentMeasurement;
  viewer.abstractPointCount = 0;

  const host = viewer.renderer?.domElement?.parentElement;
  if (host) {
    host.dataset.pointPolicy = "measured-121-8093";
    host.dataset.sensorCount = String(viewer.sensorCount);
    host.dataset.hitCount = String(viewer.hitCount);
    host.dataset.mappedCount = String(viewer.mappedCount);
    host.dataset.billboardCount = String(viewer.billboardCount);
    host.dataset.physicalPointCount = String(EXPECTED_COUNTS.shellPhysical);
    host.dataset.equipmentMeasurementPointCount = String(counts.equipmentMeasurement);
    host.dataset.abstractPointCount = "0";
    host.dataset.excludedAbstractPointCount = String(excludedEntries.length);
  }

  const runtime = {
    schema: "bf3d.measured-point-filter.8093.v2",
    reqId: REQ_ID,
    policy: "physical-and-equipment-measurements",
    expectedCounts: EXPECTED_COUNTS,
    counts: {
      ...counts,
      shellPhysical: EXPECTED_COUNTS.shellPhysical,
      visible: visibleEntries.length,
      excluded: excludedEntries.length,
    },
    visibleIds: visibleEntries.map((entry) => entry.bindingId),
    excludedIds: excludedEntries.map((entry) => entry.bindingId),
    passed: true,
  };
  viewer[RUNTIME_KEY] = runtime;
  window[RUNTIME_KEY] = runtime;

  if (window.__BF_FURNACE_BODY_BILLBOARDS__) {
    Object.assign(window.__BF_FURNACE_BODY_BILLBOARDS__, {
      displayPolicy: "measured-121-8093",
      totalBillboardCount: visibleEntries.length,
      spriteCount: visibleEntries.length,
      hitCount: visibleHits.length,
      excludedAbstractPointCount: excludedEntries.length,
      passed: visibleEntries.length === EXPECTED_COUNTS.visible,
    });
  }
  return true;
}

const poll = () => {
  const viewer = window.__BF_CAD_FURNACE_VIEWER;
  if (!viewer || viewer === mountedViewer) return;
  try {
    if (mount(viewer)) mountedViewer = viewer;
  } catch (error) {
    const host = viewer?.renderer?.domElement?.parentElement;
    if (host) host.dataset.pointPolicy = "error";
    console.error("8093 物理测点过滤失败", error);
  }
};
const scheduler = window.__BF_SHARED_SCHEDULER__;
const stopPolling = scheduler?.subscribe
  ? scheduler.subscribe("bf3d-physical-point-filter", 120, poll)
  : (() => {
      const timer = window.setInterval(() => {
        if (!document.hidden) poll();
      }, 120);
      return () => window.clearInterval(timer);
    })();

window.addEventListener("beforeunload", stopPolling, { once: true });
