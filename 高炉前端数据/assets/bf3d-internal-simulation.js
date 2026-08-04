/**
 * GL02 furnace internal simulation overlay.
 *
 * Requirement:
 * - REQ-BF3D-INTERNAL-RUNTIME-6X-20260719
 *
 * Contract:
 * - Adds runtime-only Three.js process objects without replacing the formal GLB.
 * - Keeps measured/interpolated/estimated/simulated/illustrative states explicit.
 * - Exposes a deterministic API at window.__BF3D_INTERNAL_SIMULATION__.
 */

import * as THREE from "../libs/three/three.module.js";

const CONFIG_URL = "../config/bf3d_internal_simulation.v1.json";
const PROFILE = [
  [0, 2.05],
  [4.8, 2.35],
  [8.8, 2.95],
  [13.8, 4.15],
  [18.6, 4.46],
  [24.5, 4.05],
  [30.6, 3.36],
  [35.2, 2.78],
  [37.2, 2.42],
  [40, 2.18],
];
const LEGACY_INTERNAL_PREFIXES = [
  "internal_burden_reference",
  "burden_column_layered_charge_coke",
  "burden_column_layered_charge_ore",
  "cohesive_zone_softening_melting_band",
  "countercurrent_gas_flow_streamlines",
  "hot_blast_raceway_plumes",
  "hot_metal_dripping_",
  "hearth_molten_iron_pool",
  "hearth_slag_layer",
  "cold_blast_supply_flow",
];
const EVIDENCE_LABELS = {
  measured: "实测",
  interpolated: "有界插值",
  estimated: "估计",
  simulated: "仿真",
  illustrative: "教学示意",
  stale: "数据陈旧",
  "no-data": "无数据",
  blocked: "门禁未通过",
};
const DEFAULT_CONFIG = {
  schema_version: "bf3d_internal_simulation_config.v1",
  furnace_id: "GL02",
  coordinate_frame: "GL02_LOCAL_YUP_M",
  asset_version: "web-runtime-2026.07.19",
  tuyere_count: 26,
  stockline_gate: {
    enabled: false,
    zero_datum_m: null,
    positive_direction: null,
    valid_range_m: null,
    south_north_tilt_enabled: false,
    status: "blocked_pending_field_confirmation",
  },
  freshness: {
    sensor_warn_after_ms: 180000,
    sensor_hard_expire_after_ms: 600000,
    status: "candidate_runtime_thresholds_pending_source_freeze",
  },
  pressure: {
    height_m: [20.35, 23.488, 28.976],
    azimuth_labels: ["A", "B", "C", "D", "E", "F"],
    orientation_status: "relative_only",
    legend_mode: "baseline_deviation_kpa",
    legend_min: -12,
    legend_max: 12,
  },
  performance: {
    desktop_surface_segments: 64,
    mobile_surface_segments: 36,
    desktop_surface_particle_count: 320,
    mobile_surface_particle_count: 144,
    pci_points_per_tuyere_max: 12,
    droplet_point_count: 96,
  },
  burden_fx: {
    enabled: true,
    evidence: "illustrative",
    random_seed: 20260719,
    chute_height_m: 35.2,
    chute_length_m: 2.45,
    cycle_duration_ms: 14000,
    discharge_start_ratio: 0.12,
    discharge_end_ratio: 0.7,
    settle_end_ratio: 0.9,
    high_particle_capacity_per_type: 180,
    medium_particle_capacity_per_type: 108,
    low_particle_capacity_per_type: 56,
    high_dust_capacity: 180,
    medium_dust_capacity: 96,
    low_dust_capacity: 48,
    what_if_default_enabled: false,
    live_motion_gate: {
      enabled: false,
      require_event_time: true,
      require_motion_parameters: true,
      require_mass_balance: true,
      status: "blocked_pending_chute_program_and_event_semantics",
    },
  },
  illustrative_scenario: {
    scenario_version: "GL02-TEACHING-2026.07",
    random_seed: 20260719,
    cohesive_shape: "inverted_v",
    charge_interval_ms: 14000,
  },
};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const lerp = (from, to, amount) => from + (to - from) * amount;
const smoothstep = (value) => {
  const x = clamp(value, 0, 1);
  return x * x * (3 - 2 * x);
};
const normalizeName = (name) =>
  String(name || "")
    .toLowerCase()
    .replace(/^approx_gl02_/, "");
const seededRandom = (initialSeed) => {
  let seed = Number(initialSeed) >>> 0;
  return () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
};
const finite = (value) =>
  Number.isFinite(Number(value)) ? Number(value) : null;
const ratio = (value) => {
  const numeric = finite(value);
  if (numeric === null) return null;
  return clamp(numeric > 1 ? numeric / 100 : numeric, 0, 1);
};
const snapshotObject = (value) =>
  value &&
  typeof value === "object" &&
  value.schema_version === "bf3d_snapshot.v1";
const cachedLiveSnapshot = () => {
  const value = window.__BF3D_LATEST_SNAPSHOT__;
  return snapshotObject(value) && value.mode !== "illustrative"
    ? value
    : null;
};
const snapshotMillis = (snapshot) => {
  const cohesiveTime =
    snapshot?.estimated?.cohesive_zone?.sample_time;
  const value =
    cohesiveTime || snapshot?.knowledge_time || snapshot?.render_time;
  const millis = new Date(value || "").getTime();
  return Number.isFinite(millis) ? millis : Number.NEGATIVE_INFINITY;
};
const validateLiveCohesiveEstimate = (estimate, knowledgeTime) => {
  const issues = [];
  const boundedNumber = (name, lower, upper) => {
    const value = estimate?.[name];
    const numeric =
      typeof value === "boolean" ? null : finite(value);
    if (numeric === null) {
      issues.push(`${name}:not_finite`);
      return null;
    }
    if (numeric < lower || numeric > upper) {
      issues.push(`${name}:out_of_range`);
      return null;
    }
    return numeric;
  };
  if (!estimate || typeof estimate !== "object") {
    return { valid: false, issues: ["estimate:missing"] };
  }
  if (estimate.status !== "available") issues.push("status:not_available");
  if (estimate.evidence !== "estimated") issues.push("evidence:not_estimated");
  if (estimate.calibration_status !== "uncalibrated") {
    issues.push("calibration_status:not_uncalibrated");
  }
  if (estimate.control_use !== "prohibited") {
    issues.push("control_use:not_prohibited");
  }
  if (estimate.root_definition !== "wall_thermal_activity_centroid") {
    issues.push("root_definition:invalid");
  }
  if (estimate.azimuth_reference !== "sensor_relative_A_zero") {
    issues.push("azimuth_reference:invalid");
  }
  if (estimate.absolute_azimuth_status !== "unconfirmed") {
    issues.push("absolute_azimuth_status:invalid");
  }
  if (
    typeof estimate.model_version !== "string" ||
    !estimate.model_version.trim()
  ) {
    issues.push("model_version:missing");
  }
  const centerHeight = boundedNumber("centerHeight", 0, 50);
  const thickness = boundedNumber("thickness", 0.1, 10);
  const innerRadius = boundedNumber("innerRadius", 0, 10);
  const outerRadius = boundedNumber("outerRadius", 0.1, 10);
  boundedNumber("eccentricity", 0, 5);
  boundedNumber("eccentricAngle", -Math.PI * 2, Math.PI * 2);
  boundedNumber("amplitude", 0, 10);
  boundedNumber("uncertainty", 0, 10);
  boundedNumber("confidence", 0, 0.45);
  if (
    innerRadius !== null &&
    outerRadius !== null &&
    outerRadius <= innerRadius
  ) {
    issues.push("radii:outer_not_greater_than_inner");
  }
  if (
    centerHeight !== null &&
    thickness !== null &&
    (centerHeight - thickness / 2 < 0 ||
      centerHeight + thickness / 2 > 50)
  ) {
    issues.push("thickness:outside_furnace_bounds");
  }
  if (
    !["flat", "inverted_v", "w", "eccentric"].includes(estimate.shape)
  ) {
    issues.push("shape:invalid");
  }
  const sampleMillis = new Date(estimate.sample_time || "").getTime();
  const knowledgeMillis = new Date(knowledgeTime || "").getTime();
  if (!Number.isFinite(sampleMillis)) {
    issues.push("sample_time:invalid");
  }
  if (!Number.isFinite(knowledgeMillis)) {
    issues.push("knowledge_time:invalid");
  } else if (
    Number.isFinite(sampleMillis) &&
    sampleMillis > knowledgeMillis
  ) {
    issues.push("sample_time:after_knowledge_time");
  }
  const movement = estimate.movement;
  if (!movement || typeof movement !== "object") {
    issues.push("movement:missing");
  } else {
    if (!["up", "down", "stable"].includes(movement.direction)) {
      issues.push("movement.direction:invalid");
    }
    const velocity =
      typeof movement.velocity_m_per_h === "boolean"
        ? null
        : finite(movement.velocity_m_per_h);
    if (velocity === null || Math.abs(velocity) > 5) {
      issues.push("movement.velocity_m_per_h:invalid");
    }
    const horizon =
      typeof movement.forecast_horizon_minutes === "boolean"
        ? null
        : finite(movement.forecast_horizon_minutes);
    if (horizon === null || horizon <= 0 || horizon > 240) {
      issues.push("movement.forecast_horizon_minutes:invalid");
    }
    const forecast =
      typeof movement.forecast_height_m === "boolean"
        ? null
        : finite(movement.forecast_height_m);
    if (forecast === null || forecast < 0 || forecast > 50) {
      issues.push("movement.forecast_height_m:invalid");
    }
    if (
      movement.forecast_assumption !==
      "constant_velocity_uncalibrated"
    ) {
      issues.push("movement.forecast_assumption:invalid");
    }
  }
  return {
    valid: issues.length === 0,
    issues: [...new Set(issues)],
  };
};
const latestValue = (buffer, id) => {
  const values = buffer?.[id];
  if (!Array.isArray(values)) return null;
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = finite(values[index]);
    if (value !== null) return value;
  }
  return null;
};
const latestTimestamp = (buffer) => {
  const values = Array.isArray(buffer?.timestamps) ? buffer.timestamps : [];
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const millis = new Date(values[index]).getTime();
    if (Number.isFinite(millis)) return new Date(millis).toISOString();
  }
  return null;
};
const worldY = (heightM) => Number(heightM) - 20;
const radiusAt = (heightM) => {
  for (let index = 1; index < PROFILE.length; index += 1) {
    const [lowerHeight, lowerRadius] = PROFILE[index - 1];
    const [upperHeight, upperRadius] = PROFILE[index];
    if (heightM <= upperHeight) {
      const amount = clamp(
        (heightM - lowerHeight) / (upperHeight - lowerHeight),
        0,
        1,
      );
      return lerp(lowerRadius, upperRadius, amount);
    }
  }
  return PROFILE[PROFILE.length - 1][1];
};
const disposeMaterial = (material) => {
  if (!material) return;
  const materials = Array.isArray(material) ? material : [material];
  materials.forEach((item) => item?.dispose?.());
};
const disposeObject = (object) => {
  object.traverse((child) => {
    if (!child.isMesh && !child.isPoints && !child.isLine) return;
    if (child.isInstancedMesh) child.dispose?.();
    child.geometry?.dispose?.();
    disposeMaterial(child.material);
  });
};

async function loadConfig() {
  try {
    const response = await fetch(CONFIG_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const config = await response.json();
    return {
      ...DEFAULT_CONFIG,
      ...config,
      stockline_gate: {
        ...DEFAULT_CONFIG.stockline_gate,
        ...(config.stockline_gate || {}),
      },
      freshness: {
        ...DEFAULT_CONFIG.freshness,
        ...(config.freshness || {}),
      },
      pressure: {
        ...DEFAULT_CONFIG.pressure,
        ...(config.pressure || {}),
      },
      performance: {
        ...DEFAULT_CONFIG.performance,
        ...(config.performance || {}),
      },
      burden_fx: {
        ...DEFAULT_CONFIG.burden_fx,
        ...(config.burden_fx || {}),
        live_motion_gate: {
          ...DEFAULT_CONFIG.burden_fx.live_motion_gate,
          ...(config.burden_fx?.live_motion_gate || {}),
        },
      },
      illustrative_scenario: {
        ...DEFAULT_CONFIG.illustrative_scenario,
        ...(config.illustrative_scenario || {}),
      },
      __source: "config",
    };
  } catch (error) {
    console.warn("BF3D internal simulation config fallback", error);
    return { ...DEFAULT_CONFIG, __source: "fallback" };
  }
}

function createPanel(host) {
  const panel = document.createElement("section");
  panel.className = "bf3d-sim-panel";
  panel.dataset.collapsed = "false";
  panel.dataset.autoCompact = String(window.innerWidth <= 1024);
  panel.setAttribute("aria-label", "高炉内部仿真状态");
  panel.innerHTML = `
    <div class="bf3d-sim-head">
      <strong class="bf3d-sim-title">炉内仿真与工艺对象</strong>
      <span class="bf3d-sim-mode" data-mode="live">数据态</span>
      <button type="button" class="bf3d-sim-collapse" aria-label="折叠炉内仿真状态" aria-expanded="true">−</button>
    </div>
    <div class="bf3d-sim-body">
      <div class="bf3d-sim-toolbar">
        <button type="button" data-sim-action="live" class="active">数据态</button>
        <button type="button" data-sim-action="illustrative">教学演示</button>
        <button type="button" data-sim-action="charging-focus">布料聚焦</button>
        <button type="button" data-sim-action="cohesive-preview">软熔响应</button>
        <button type="button" data-sim-action="pause">暂停</button>
        <button type="button" data-sim-action="reset">复位</button>
      </div>
      <div class="bf3d-sim-object-list" aria-live="polite">
        ${[
          ["stock", "料面料柱"],
          ["charging", "溜槽布料"],
          ["cohesive", "软熔带"],
          ["tuyere", "风口回旋"],
          ["pressure", "静压力场"],
          ["hearth", "滴落炉缸"],
        ]
          .map(
            ([id, label]) => `
              <div class="bf3d-sim-object-row" data-object="${id}" data-state="no-data">
                <span class="bf3d-sim-object-name">${label}</span>
                <span class="bf3d-sim-object-status">等待状态</span>
                <span class="bf3d-sim-evidence">无数据</span>
              </div>`,
          )
          .join("")}
      </div>
      <div class="bf3d-sim-legend">
        <span>压力偏离</span><span>−12</span><i></i><span>+12 kPa</span>
      </div>
      <div class="bf3d-sim-detail">外观模式下内部对象冻结；打开“内切面”后显示。</div>
    </div>`;
  host.appendChild(panel);
  const collapse = panel.querySelector(".bf3d-sim-collapse");
  collapse.addEventListener("click", () => {
    const currentlyHidden =
      panel.dataset.collapsed === "true" ||
      panel.dataset.autoCompact === "true";
    const collapsed = !currentlyHidden;
    panel.dataset.collapsed = String(collapsed);
    panel.dataset.autoCompact = "false";
    collapse.textContent = collapsed ? "+" : "−";
    collapse.setAttribute("aria-expanded", String(!collapsed));
  });
  const onResize = () => {
    if (panel.dataset.collapsed !== "true") {
      panel.dataset.autoCompact = String(window.innerWidth <= 1024);
    }
  };
  window.addEventListener("resize", onResize);
  panel.__bfDispose = () => window.removeEventListener("resize", onResize);
  return panel;
}

function createStockSurfaceGeometry(segments, rings) {
  const vertices = [];
  const indices = [];
  const uvs = [];
  for (let ring = 0; ring <= rings; ring += 1) {
    const radial = ring / rings;
    for (let sector = 0; sector <= segments; sector += 1) {
      const angle = (sector / segments) * Math.PI * 2;
      vertices.push(Math.cos(angle) * radial, 0, Math.sin(angle) * radial);
      uvs.push(sector / segments, radial);
    }
  }
  for (let ring = 0; ring < rings; ring += 1) {
    for (let sector = 0; sector < segments; sector += 1) {
      const a = ring * (segments + 1) + sector;
      const b = a + segments + 1;
      indices.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(vertices, 3),
  );
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function updateStockSurface(
  geometry,
  segments,
  rings,
  radius,
  centerY,
  craterDepth,
  eccentricX,
  eccentricZ,
) {
  const positions = geometry.attributes.position;
  let offset = 0;
  for (let ring = 0; ring <= rings; ring += 1) {
    const radial = ring / rings;
    const bowl = -craterDepth * Math.pow(1 - radial, 2);
    const edgeRoll = -0.08 * Math.pow(radial, 5);
    for (let sector = 0; sector <= segments; sector += 1) {
      const angle = (sector / segments) * Math.PI * 2;
      const localRadius = radius * radial;
      const tilt =
        eccentricX * Math.cos(angle) * radial +
        eccentricZ * Math.sin(angle) * radial;
      positions.setXYZ(
        offset,
        Math.cos(angle) * localRadius,
        centerY + bowl + edgeRoll + tilt,
        Math.sin(angle) * localRadius,
      );
      offset += 1;
    }
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
}

function chooseBurdenFxQuality(config) {
  const memory = Number(navigator.deviceMemory || 4);
  const cores = Number(navigator.hardwareConcurrency || 4);
  const dpr = Number(window.devicePixelRatio || 1);
  const compact = window.innerWidth <= 768;
  let level = "high";
  if (compact || memory <= 4 || cores <= 4) level = "low";
  else if (memory < 8 || cores < 8 || dpr > 2.25) level = "medium";
  const presets = {
    high: {
      particleCapacity: config.burden_fx.high_particle_capacity_per_type,
      dustCapacity: config.burden_fx.high_dust_capacity,
      emissionRate: 42,
      dustBurst: 7,
      chuteSegments: 36,
    },
    medium: {
      particleCapacity: config.burden_fx.medium_particle_capacity_per_type,
      dustCapacity: config.burden_fx.medium_dust_capacity,
      emissionRate: 28,
      dustBurst: 5,
      chuteSegments: 28,
    },
    low: {
      particleCapacity: config.burden_fx.low_particle_capacity_per_type,
      dustCapacity: config.burden_fx.low_dust_capacity,
      emissionRate: 16,
      dustBurst: 3,
      chuteSegments: 20,
    },
  };
  return {
    level,
    initialLevel: level,
    memory,
    cores,
    dpr,
    ...presets[level],
    presets,
  };
}

function createBurdenDeliveryFx(config, center) {
  const settings = config.burden_fx;
  const quality = chooseBurdenFxQuality(config);
  const reducedMotion = window.matchMedia?.(
    "(prefers-reduced-motion: reduce)",
  )?.matches;
  const random = seededRandom(settings.random_seed);
  const group = new THREE.Group();
  group.name = "BF3D_ILL_BURDEN_DELIVERY_FX";
  group.userData = {
    semantic_id: "BF3D_ILL_BURDEN_DELIVERY_FX",
    evidence_level: "illustrative",
    runtime_only: true,
    production_default_hidden: true,
  };

  const chuteSteel = new THREE.MeshStandardMaterial({
    color: 0x4d5654,
    roughness: 0.84,
    metalness: 0.3,
    flatShading: false,
  });
  const chuteLiner = new THREE.MeshStandardMaterial({
    color: 0x2b302f,
    roughness: 0.96,
    metalness: 0.08,
  });
  const oreMaterial = new THREE.MeshStandardMaterial({
    color: 0x75462f,
    roughness: 0.96,
    metalness: 0,
    flatShading: true,
  });
  const cokeMaterial = new THREE.MeshStandardMaterial({
    color: 0x242728,
    roughness: 0.98,
    metalness: 0,
    flatShading: true,
  });
  const poreMaterial = new THREE.MeshStandardMaterial({
    color: 0x090b0b,
    roughness: 1,
    metalness: 0,
  });

  const chuteAzimuth = new THREE.Group();
  chuteAzimuth.name = "BF3D_ILL_CHUTE_AZIMUTH_PIVOT";
  chuteAzimuth.position.set(
    center.x,
    worldY(settings.chute_height_m),
    center.z,
  );
  const upperHead = new THREE.Mesh(
    new THREE.CylinderGeometry(
      0.58,
      0.42,
      0.7,
      quality.chuteSegments,
      1,
      false,
    ),
    chuteSteel,
  );
  upperHead.name = "BF3D_ILL_CHUTE_ROTATING_HEAD";
  upperHead.position.y = 0.38;
  const tiltPivot = new THREE.Group();
  tiltPivot.name = "BF3D_ILL_CHUTE_TILT_PIVOT";
  const chuteLength = settings.chute_length_m;
  const chuteFloor = new THREE.Mesh(
    new THREE.BoxGeometry(0.68, 0.11, chuteLength),
    chuteLiner,
  );
  chuteFloor.name = "BF3D_ILL_CHUTE_LINER";
  chuteFloor.position.z = chuteLength * 0.5;
  const leftWall = new THREE.Mesh(
    new THREE.BoxGeometry(0.1, 0.36, chuteLength),
    chuteSteel,
  );
  leftWall.name = "BF3D_ILL_CHUTE_LEFT_WALL";
  leftWall.position.set(-0.36, 0.12, chuteLength * 0.5);
  const rightWall = leftWall.clone();
  rightWall.name = "BF3D_ILL_CHUTE_RIGHT_WALL";
  rightWall.position.x = 0.36;
  const emitter = new THREE.Object3D();
  emitter.name = "BF3D_ILL_CHUTE_EMITTER";
  emitter.position.set(0, 0, chuteLength);
  tiltPivot.add(chuteFloor, leftWall, rightWall, emitter);
  chuteAzimuth.add(upperHead, tiltPivot);
  group.add(chuteAzimuth);

  const oreGeometry = new THREE.DodecahedronGeometry(0.17, 0);
  const cokeGeometry = new THREE.IcosahedronGeometry(0.19, 1);
  const poreGeometry = new THREE.SphereGeometry(0.033, 5, 4);
  const dummy = new THREE.Object3D();
  const hiddenMatrix = new THREE.Matrix4().makeScale(0, 0, 0);

  const createPool = (name, geometry, material, capacity, type) => {
    const mesh = new THREE.InstancedMesh(geometry, material, capacity);
    mesh.name = name;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    const active = new Uint8Array(capacity);
    const phase = new Uint8Array(capacity);
    const position = new Float32Array(capacity * 3);
    const velocity = new Float32Array(capacity * 3);
    const rotation = new Float32Array(capacity * 3);
    const spin = new Float32Array(capacity * 3);
    const scale = new Float32Array(capacity * 3);
    const age = new Float32Array(capacity);
    const lifetime = new Float32Array(capacity);
    let cursor = 0;
    let activeLimit = capacity;
    let currentActiveCount = 0;
    let spawned = 0;
    let impacts = 0;
    let rolled = 0;
    for (let index = 0; index < capacity; index += 1) {
      mesh.setMatrixAt(index, hiddenMatrix);
      const color =
        type === "ore"
          ? new THREE.Color().setHSL(
              0.045 + random() * 0.025,
              0.32 + random() * 0.16,
              0.25 + random() * 0.08,
            )
          : new THREE.Color().setHSL(
              0.5 + random() * 0.04,
              0.035,
              0.115 + random() * 0.045,
            );
      mesh.setColorAt(index, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;

    const deactivate = (index) => {
      active[index] = 0;
      phase[index] = 0;
      mesh.setMatrixAt(index, hiddenMatrix);
    };
    const spawn = (origin, direction) => {
      let index = -1;
      for (let offset = 0; offset < activeLimit; offset += 1) {
        const candidate = (cursor + offset) % activeLimit;
        if (!active[candidate]) {
          index = candidate;
          break;
        }
      }
      if (index < 0) index = cursor % activeLimit;
      cursor = (index + 1) % activeLimit;
      active[index] = 1;
      phase[index] = 0;
      age[index] = 0;
      lifetime[index] = 3.4 + random() * 1.6;
      const p = index * 3;
      position[p] = origin.x + (random() - 0.5) * 0.14;
      position[p + 1] = origin.y + (random() - 0.5) * 0.08;
      position[p + 2] = origin.z + (random() - 0.5) * 0.14;
      const speed = type === "coke" ? 5.15 : 5.65;
      velocity[p] = direction.x * speed + (random() - 0.5) * 0.75;
      velocity[p + 1] =
        direction.y * speed + 0.15 + (random() - 0.5) * 0.35;
      velocity[p + 2] =
        direction.z * speed + (random() - 0.5) * 0.75;
      rotation[p] = random() * Math.PI * 2;
      rotation[p + 1] = random() * Math.PI * 2;
      rotation[p + 2] = random() * Math.PI * 2;
      spin[p] = (random() - 0.5) * 6;
      spin[p + 1] = (random() - 0.5) * 7;
      spin[p + 2] = (random() - 0.5) * 6;
      const base = type === "coke" ? 1 : 0.9;
      scale[p] = base * lerp(0.62, 1.38, random());
      scale[p + 1] = base * lerp(0.58, 1.2, random());
      scale[p + 2] = base * lerp(0.66, 1.32, random());
      spawned += 1;
      return true;
    };
    const update = (deltaSeconds, stockState, impactCallback) => {
      let activeCount = 0;
      const stockY = Number.isFinite(stockState.currentY)
        ? stockState.currentY
        : worldY(32.8);
      const stockRadius = Math.max(
        2.15,
        radiusAt(stockY + 20) - 0.18,
      );
      const craterDepth = stockState.craterDepth ?? 0.3;
      for (let index = 0; index < capacity; index += 1) {
        if (!active[index] || index >= activeLimit) {
          if (active[index]) deactivate(index);
          continue;
        }
        activeCount += 1;
        const p = index * 3;
        age[index] += deltaSeconds;
        rotation[p] += spin[p] * deltaSeconds;
        rotation[p + 1] += spin[p + 1] * deltaSeconds;
        rotation[p + 2] += spin[p + 2] * deltaSeconds;
        const dx = position[p] - center.x;
        const dz = position[p + 2] - center.z;
        const radial = Math.hypot(dx, dz);
        const normalizedRadius = clamp(radial / stockRadius, 0, 1);
        const surfaceY =
          stockY -
          craterDepth * Math.pow(1 - normalizedRadius, 2) -
          0.035 * normalizedRadius;
        if (phase[index] === 0) {
          velocity[p + 1] -= 9.81 * deltaSeconds;
          position[p] += velocity[p] * deltaSeconds;
          position[p + 1] += velocity[p + 1] * deltaSeconds;
          position[p + 2] += velocity[p + 2] * deltaSeconds;
          if (
            position[p + 1] <= surfaceY + 0.055 &&
            velocity[p + 1] < 0
          ) {
            position[p + 1] = surfaceY + 0.055;
            phase[index] = 1;
            impacts += 1;
            const safeRadial = Math.max(0.001, radial);
            const outwardX = dx / safeRadial;
            const outwardZ = dz / safeRadial;
            velocity[p] =
              velocity[p] * 0.2 + outwardX * lerp(0.4, 1.15, random());
            velocity[p + 1] = Math.abs(velocity[p + 1]) * 0.11;
            velocity[p + 2] =
              velocity[p + 2] * 0.2 + outwardZ * lerp(0.4, 1.15, random());
            impactCallback(position[p], position[p + 1], position[p + 2]);
          }
        } else {
          const friction = Math.exp(-2.3 * deltaSeconds);
          velocity[p] *= friction;
          velocity[p + 2] *= friction;
          position[p] += velocity[p] * deltaSeconds;
          position[p + 2] += velocity[p + 2] * deltaSeconds;
          const rollDx = position[p] - center.x;
          const rollDz = position[p + 2] - center.z;
          const rollRadial = Math.hypot(rollDx, rollDz);
          const rollNormalized = clamp(rollRadial / stockRadius, 0, 1);
          position[p + 1] =
            stockY -
            craterDepth * Math.pow(1 - rollNormalized, 2) +
            0.055;
          rolled += 1;
        }
        if (
          age[index] >= lifetime[index] ||
          position[p + 1] < worldY(24.5) ||
          radial > stockRadius * 1.16
        ) {
          deactivate(index);
          activeCount -= 1;
          continue;
        }
        dummy.position.set(position[p], position[p + 1], position[p + 2]);
        dummy.rotation.set(
          rotation[p],
          rotation[p + 1],
          rotation[p + 2],
        );
        dummy.scale.set(scale[p], scale[p + 1], scale[p + 2]);
        dummy.updateMatrix();
        mesh.setMatrixAt(index, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
      mesh.visible = activeCount > 0;
      currentActiveCount = activeCount;
      return activeCount;
    };
    const reset = () => {
      active.fill(0);
      phase.fill(0);
      age.fill(0);
      cursor = 0;
      for (let index = 0; index < capacity; index += 1) {
        mesh.setMatrixAt(index, hiddenMatrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
      mesh.visible = false;
      currentActiveCount = 0;
    };
    return {
      mesh,
      type,
      capacity,
      active,
      position,
      rotation,
      scale,
      spawn,
      update,
      reset,
      getActiveCount: () => currentActiveCount,
      getActiveLimit: () => activeLimit,
      getImpactCount: () => impacts,
      setActiveLimit: (nextLimit) => {
        activeLimit = clamp(Math.round(nextLimit), 1, capacity);
      },
      getState: () => ({
        type,
        capacity,
        activeLimit,
        activeCount: currentActiveCount,
        spawned,
        impacts,
        rollIntegrationSteps: rolled,
      }),
    };
  };

  const orePool = createPool(
    "BF3D_ILL_FALLING_ORE_INSTANCES",
    oreGeometry,
    oreMaterial,
    quality.particleCapacity,
    "ore",
  );
  const cokePool = createPool(
    "BF3D_ILL_FALLING_COKE_INSTANCES",
    cokeGeometry,
    cokeMaterial,
    quality.particleCapacity,
    "coke",
  );
  group.add(orePool.mesh, cokePool.mesh);

  const poreCount = cokePool.capacity * 2;
  const cokePores = new THREE.InstancedMesh(
    poreGeometry,
    poreMaterial,
    poreCount,
  );
  cokePores.name = "BF3D_ILL_COKE_PORE_DARK_DETAILS";
  cokePores.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  cokePores.frustumCulled = false;
  for (let index = 0; index < poreCount; index += 1) {
    cokePores.setMatrixAt(index, hiddenMatrix);
  }
  cokePores.instanceMatrix.needsUpdate = true;
  group.add(cokePores);
  const updateCokePores = () => {
    let visible = 0;
    const activeLimit = cokePool.getActiveLimit();
    for (let index = 0; index < cokePool.capacity; index += 1) {
      const p = index * 3;
      const active =
        cokePool.active[index] &&
        index < activeLimit;
      for (let detail = 0; detail < 2; detail += 1) {
        const target = index * 2 + detail;
        if (!active) {
          cokePores.setMatrixAt(target, hiddenMatrix);
          continue;
        }
        const angle =
          cokePool.rotation[p + 1] + detail * Math.PI * 0.83;
        const offset = 0.105 * cokePool.scale[p];
        dummy.position.set(
          cokePool.position[p] + Math.cos(angle) * offset,
          cokePool.position[p + 1] +
            (detail === 0 ? 0.035 : -0.025),
          cokePool.position[p + 2] + Math.sin(angle) * offset,
        );
        dummy.rotation.set(0, angle, 0);
        dummy.scale.setScalar(0.65 + detail * 0.18);
        dummy.updateMatrix();
        cokePores.setMatrixAt(target, dummy.matrix);
        visible += 1;
      }
    }
    cokePores.instanceMatrix.needsUpdate = true;
    cokePores.visible = visible > 0;
    return visible;
  };

  const dustCapacity = quality.dustCapacity;
  const dustPositions = new Float32Array(dustCapacity * 3);
  const dustColors = new Float32Array(dustCapacity * 3);
  const dustVelocity = new Float32Array(dustCapacity * 3);
  const dustAge = new Float32Array(dustCapacity);
  const dustLife = new Float32Array(dustCapacity);
  const dustActive = new Uint8Array(dustCapacity);
  const dustGeometry = new THREE.BufferGeometry();
  for (let index = 0; index < dustCapacity; index += 1) {
    dustPositions[index * 3 + 1] = -9999;
  }
  dustGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(dustPositions, 3),
  );
  dustGeometry.setAttribute(
    "color",
    new THREE.BufferAttribute(dustColors, 3),
  );
  const dustMaterial = new THREE.PointsMaterial({
    size: quality.level === "low" ? 0.13 : 0.16,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.36,
    depthWrite: false,
    vertexColors: true,
  });
  const dust = new THREE.Points(dustGeometry, dustMaterial);
  dust.name = "BF3D_ILL_IMPACT_DUST_POINTS";
  dust.frustumCulled = false;
  dust.visible = false;
  group.add(dust);
  let dustCursor = 0;
  let dustBursts = 0;
  const spawnDust = (x, y, z) => {
    const burst = quality.dustBurst;
    for (let offset = 0; offset < burst; offset += 1) {
      const index = dustCursor % dustCapacity;
      dustCursor += 1;
      const p = index * 3;
      dustActive[index] = 1;
      dustAge[index] = 0;
      dustLife[index] = 0.55 + random() * 0.8;
      dustPositions[p] = x + (random() - 0.5) * 0.24;
      dustPositions[p + 1] = y + random() * 0.1;
      dustPositions[p + 2] = z + (random() - 0.5) * 0.24;
      dustVelocity[p] = (random() - 0.5) * 0.42;
      dustVelocity[p + 1] = 0.18 + random() * 0.46;
      dustVelocity[p + 2] = (random() - 0.5) * 0.42;
      dustColors[p] = 0.31 + random() * 0.1;
      dustColors[p + 1] = 0.25 + random() * 0.08;
      dustColors[p + 2] = 0.19 + random() * 0.06;
    }
    dustBursts += 1;
  };
  const updateDust = (deltaSeconds) => {
    let activeCount = 0;
    for (let index = 0; index < dustCapacity; index += 1) {
      if (!dustActive[index]) continue;
      const p = index * 3;
      dustAge[index] += deltaSeconds;
      if (dustAge[index] >= dustLife[index]) {
        dustActive[index] = 0;
        dustPositions[p + 1] = -9999;
        continue;
      }
      activeCount += 1;
      const drag = Math.exp(-1.4 * deltaSeconds);
      dustVelocity[p] *= drag;
      dustVelocity[p + 2] *= drag;
      dustPositions[p] += dustVelocity[p] * deltaSeconds;
      dustPositions[p + 1] += dustVelocity[p + 1] * deltaSeconds;
      dustPositions[p + 2] += dustVelocity[p + 2] * deltaSeconds;
      const fade = 1 - dustAge[index] / dustLife[index];
      dustColors[p] *= 0.985 + fade * 0.015;
      dustColors[p + 1] *= 0.985 + fade * 0.015;
      dustColors[p + 2] *= 0.985 + fade * 0.015;
    }
    dustGeometry.attributes.position.needsUpdate = true;
    dustGeometry.attributes.color.needsUpdate = true;
    dust.visible = activeCount > 0;
    return activeCount;
  };

  const emitterPosition = new THREE.Vector3();
  const chuteOrigin = new THREE.Vector3();
  const dischargeDirection = new THREE.Vector3();
  let active = false;
  let phase = "off";
  let evidence = "blocked";
  let burdenType = null;
  let eventId = null;
  let timelineMs = 0;
  let azimuthDeg = 25;
  let targetAzimuthDeg = 25;
  let tiltDeg = 34;
  let targetTiltDeg = 34;
  let emissionAccumulator = 0;
  let acceptedPrograms = 0;
  let rejectedPrograms = 0;
  let impactCount = 0;
  let activeOre = 0;
  let activeCoke = 0;
  let activeDust = 0;
  let visiblePoreDetails = 0;
  let fpsFrames = 0;
  let fpsSeconds = 0;
  let sampledFps = null;
  let autoDowngradeCount = 0;
  let lastGateReason = "等待教学演示或有效运动参数";
  let previousImpactTotal = 0;
  let lowQualityStepAccumulator = 0;

  const applyQualityLevel = (nextLevel) => {
    if (!quality.presets[nextLevel]) return false;
    quality.level = nextLevel;
    quality.emissionRate = quality.presets[nextLevel].emissionRate;
    quality.dustBurst = quality.presets[nextLevel].dustBurst;
    const nextLimit = Math.min(
      quality.particleCapacity,
      quality.presets[nextLevel].particleCapacity,
    );
    orePool.setActiveLimit(nextLimit);
    cokePool.setActiveLimit(nextLimit);
    return true;
  };
  const downgrade = () => {
    const next =
      quality.level === "high"
        ? "medium"
        : quality.level === "medium"
          ? "low"
          : null;
    if (!next) return false;
    applyQualityLevel(next);
    autoDowngradeCount += 1;
    return true;
  };
  const start = (event) => {
    if (
      !settings.enabled ||
      event?.type !== "BURDEN_CHARGE_STARTED" ||
      event?.visualize_motion !== true
    ) {
      return false;
    }
    const isIllustrative = event.evidence === "illustrative";
    const liveGate = settings.live_motion_gate;
    const eventMillis = new Date(event.event_time || "").getTime();
    const liveAzimuth = Number(event.chute_azimuth_deg);
    const liveTilt = Number(event.chute_tilt_deg);
    const timeValid =
      Number.isFinite(eventMillis) &&
      Math.abs(Date.now() - eventMillis) <= 600000;
    const motionValid =
      event.motion_parameters_valid === true &&
      Number.isFinite(liveAzimuth) &&
      liveAzimuth >= 0 &&
      liveAzimuth <= 360 &&
      Number.isFinite(liveTilt) &&
      liveTilt >= 15 &&
      liveTilt <= 55;
    const validLive =
      liveGate.enabled === true &&
      (!liveGate.require_event_time || timeValid) &&
      (!liveGate.require_motion_parameters || motionValid) &&
      (!liveGate.require_mass_balance ||
        event.mass_balance_valid === true);
    if (!isIllustrative && !validLive) {
      rejectedPrograms += 1;
      lastGateReason =
        "数据态缺少经审计的溜槽角度/事件时刻，运动保持隐藏";
      return false;
    }
    if (!["ore", "coke"].includes(event.burden_type)) {
      rejectedPrograms += 1;
      lastGateReason = "炉料类型无效";
      return false;
    }
    active = true;
    phase = "rotate";
    evidence = isIllustrative ? "illustrative" : "measured";
    burdenType = event.burden_type;
    eventId = event.event_id || null;
    timelineMs = 0;
    emissionAccumulator = 0;
    targetAzimuthDeg = isIllustrative
      ? 25 + (acceptedPrograms % 4) * 82
      : liveAzimuth;
    targetTiltDeg = isIllustrative
      ? 29 + (acceptedPrograms % 3) * 5.5
      : liveTilt;
    acceptedPrograms += 1;
    lastGateReason = isIllustrative
      ? "教学示意运动已启动"
      : "经审计的运动参数已接受";
    return true;
  };
  const update = (deltaSeconds, stockState) => {
    const illustrative = stockState.evidence === "illustrative";
    group.visible =
      settings.enabled &&
      (illustrative ||
        active ||
        orePool.getActiveCount() > 0 ||
        cokePool.getActiveCount() > 0);
    chuteAzimuth.visible = illustrative || active;
    if (quality.level === "low") {
      lowQualityStepAccumulator += deltaSeconds;
      if (lowQualityStepAccumulator < 1 / 30) return;
      deltaSeconds = Math.min(lowQualityStepAccumulator, 0.1);
      lowQualityStepAccumulator = 0;
    }
    if (active && reducedMotion) {
      azimuthDeg = targetAzimuthDeg;
      tiltDeg = targetTiltDeg;
      timelineMs = settings.cycle_duration_ms;
      phase = "settled";
      active = false;
    } else if (active) {
      timelineMs += deltaSeconds * 1000;
      const cycle = Math.max(1000, settings.cycle_duration_ms);
      const ratio = clamp(timelineMs / cycle, 0, 1);
      const dischargeStart = settings.discharge_start_ratio;
      const dischargeEnd = settings.discharge_end_ratio;
      if (ratio < dischargeStart) phase = "rotate";
      else if (ratio < dischargeEnd) phase = "discharge";
      else if (ratio < settings.settle_end_ratio) phase = "deposit";
      else phase = "settle";
      const azimuthBlend = smoothstep(
        clamp(ratio / Math.max(0.01, dischargeStart), 0, 1),
      );
      azimuthDeg = lerp(azimuthDeg, targetAzimuthDeg, azimuthBlend * 0.12);
      tiltDeg = lerp(tiltDeg, targetTiltDeg, 0.085);
      if (phase === "discharge" && !reducedMotion) {
        emissionAccumulator += deltaSeconds * quality.emissionRate;
        while (emissionAccumulator >= 1) {
          group.updateMatrixWorld(true);
          emitter.getWorldPosition(emitterPosition);
          chuteAzimuth.getWorldPosition(chuteOrigin);
          dischargeDirection
            .copy(emitterPosition)
            .sub(chuteOrigin)
            .normalize();
          dischargeDirection.x *= 0.32;
          dischargeDirection.z *= 0.32;
          dischargeDirection.y = -Math.max(
            0.78,
            Math.abs(dischargeDirection.y),
          );
          dischargeDirection.normalize();
          const pool = burdenType === "coke" ? cokePool : orePool;
          pool.spawn(emitterPosition, dischargeDirection);
          emissionAccumulator -= 1;
        }
      }
      if (ratio >= 1) {
        active = false;
        phase = "settled";
      }
    } else if (!illustrative) {
      phase = "off";
      evidence = "blocked";
    }
    chuteAzimuth.rotation.y = THREE.MathUtils.degToRad(azimuthDeg);
    tiltPivot.rotation.x = THREE.MathUtils.degToRad(tiltDeg);
    activeOre = orePool.update(deltaSeconds, stockState, spawnDust);
    activeCoke = cokePool.update(deltaSeconds, stockState, spawnDust);
    visiblePoreDetails = updateCokePores();
    activeDust = reducedMotion ? 0 : updateDust(deltaSeconds);
    const newImpactTotal =
      orePool.getImpactCount() + cokePool.getImpactCount();
    impactCount += Math.max(0, newImpactTotal - previousImpactTotal);
    previousImpactTotal = newImpactTotal;
    fpsFrames += 1;
    fpsSeconds += deltaSeconds;
    if (fpsSeconds >= 5) {
      sampledFps = fpsFrames / fpsSeconds;
      if (sampledFps < 35) downgrade();
      fpsFrames = 0;
      fpsSeconds = 0;
    }
  };
  const reset = () => {
    active = false;
    phase = "off";
    evidence = "blocked";
    burdenType = null;
    eventId = null;
    timelineMs = 0;
    emissionAccumulator = 0;
    orePool.reset();
    cokePool.reset();
    dustActive.fill(0);
    for (let index = 0; index < dustCapacity; index += 1) {
      dustPositions[index * 3 + 1] = -9999;
    }
    dustGeometry.attributes.position.needsUpdate = true;
    dust.visible = false;
    cokePores.visible = false;
    previousImpactTotal =
      orePool.getImpactCount() + cokePool.getImpactCount();
    activeOre = 0;
    activeCoke = 0;
    activeDust = 0;
    visiblePoreDetails = 0;
    lowQualityStepAccumulator = 0;
    group.visible = false;
    chuteAzimuth.visible = false;
  };
  reset();
  return {
    group,
    start,
    update,
    reset,
    downgrade,
    getState: () => ({
      enabled: settings.enabled,
      visible: group.visible,
      active,
      phase,
      evidence,
      burdenType,
      eventId,
      timelineMs,
      azimuthDeg,
      tiltDeg,
      reducedMotion: Boolean(reducedMotion),
      acceptedPrograms,
      rejectedPrograms,
      lastGateReason,
      implementation: {
        chute: "pooled_hierarchy",
        ore: "InstancedMesh",
        coke: "InstancedMesh",
        cokePores: "InstancedMesh_dark_detail",
        dust: "Points",
        collision: "bounded_analytical_surface_contact",
        roll: "bounded_radial_friction",
      },
      particles: {
        ore: orePool.getState(),
        coke: cokePool.getState(),
        activeOre,
        activeCoke,
        visiblePoreDetails,
      },
      dust: {
        capacity: dustCapacity,
        activeCount: activeDust,
        burstCount: dustBursts,
      },
      impactCount,
      quality: {
        initial: quality.initialLevel,
        current: quality.level,
        sampledFps,
        autoDowngradeCount,
        memory: quality.memory,
        cores: quality.cores,
        dpr: quality.dpr,
      },
      liveMotionGate: { ...settings.live_motion_gate },
      truthBoundary: {
        illustrativeByDefault: true,
        noMeasuredMotionWithoutParameters: true,
        noDemClaim: true,
        noRealParticleSizeClaim: true,
      },
    }),
  };
}

function createBurdenSystem(config, center) {
  const mobile = window.innerWidth <= 768;
  const segments = mobile
    ? config.performance.mobile_surface_segments
    : config.performance.desktop_surface_segments;
  const particleCount = mobile
    ? config.performance.mobile_surface_particle_count
    : config.performance.desktop_surface_particle_count;
  const rings = 9;
  const group = new THREE.Group();
  group.name = "BF3D_EST_BURDEN_SYSTEM";
  const delivery = createBurdenDeliveryFx(config, center);
  group.add(delivery.group);
  const surfaceGeometry = createStockSurfaceGeometry(segments, rings);
  const surfaceMaterial = new THREE.MeshStandardMaterial({
    color: 0x4d4437,
    roughness: 0.92,
    metalness: 0,
    side: THREE.DoubleSide,
  });
  const surface = new THREE.Mesh(surfaceGeometry, surfaceMaterial);
  surface.name = "BF3D_MEAS_STOCK_SURFACE";
  surface.receiveShadow = true;
  group.add(surface);

  const oreMaterial = new THREE.MeshStandardMaterial({
    color: 0x6f4633,
    roughness: 0.88,
    metalness: 0,
  });
  const cokeMaterial = new THREE.MeshStandardMaterial({
    color: 0x242728,
    roughness: 0.82,
    metalness: 0.02,
  });
  const layers = [];
  for (let index = 0; index < 12; index += 1) {
    const ore = index % 2 === 0;
    const heightM = 25.4 + index * 0.58;
    const thickness = ore ? 0.42 : 0.32;
    const radius = Math.max(2.5, radiusAt(heightM) - 0.22);
    const geometry = new THREE.CylinderGeometry(
      radius * 0.96,
      radius,
      thickness,
      Math.max(28, Math.round(segments * 0.75)),
      1,
      false,
    );
    const mesh = new THREE.Mesh(
      geometry,
      ore ? oreMaterial : cokeMaterial,
    );
    mesh.name = `BF3D_EST_BURDEN_LAYER_${ore ? "ORE" : "COKE"}_${String(
      index + 1,
    ).padStart(2, "0")}`;
    mesh.position.set(center.x, worldY(heightM), center.z);
    mesh.userData = {
      semantic_id: "BF3D_EST_BURDEN_LAYERS",
      burden_type: ore ? "ore" : "coke",
      evidence_level: "illustrative",
      pooled: true,
    };
    mesh.visible = false;
    group.add(mesh);
    layers.push(mesh);
  }

  const particleGeometry = new THREE.DodecahedronGeometry(0.085, 0);
  const oreParticles = new THREE.InstancedMesh(
    particleGeometry,
    oreMaterial.clone(),
    Math.ceil(particleCount / 2),
  );
  const cokeParticles = new THREE.InstancedMesh(
    particleGeometry,
    cokeMaterial.clone(),
    Math.floor(particleCount / 2),
  );
  oreParticles.name = "BF3D_EST_NEAR_SURFACE_ORE_INSTANCES";
  cokeParticles.name = "BF3D_EST_NEAR_SURFACE_COKE_INSTANCES";
  oreParticles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  cokeParticles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  group.add(oreParticles, cokeParticles);
  const random = seededRandom(config.illustrative_scenario.random_seed);
  const particleSeeds = Array.from({ length: particleCount }, (_, index) => ({
    angle: random() * Math.PI * 2,
    radial: Math.sqrt(random()) * 0.96,
    scale: lerp(0.52, 1.42, random()),
    rotation: random() * Math.PI * 2,
    type: index % 2,
  }));
  const dummy = new THREE.Object3D();
  let currentY = worldY(32.8);
  let targetY = currentY;
  let velocity = 0;
  let craterDepth = 0.3;
  let visibleLayerCount = 0;
  let chargeSequence = 0;

  const updateParticles = () => {
    const radius = Math.max(2.15, radiusAt(currentY + 20) - 0.18);
    let oreIndex = 0;
    let cokeIndex = 0;
    particleSeeds.forEach((seed) => {
      const localRadius = radius * seed.radial;
      const y =
        currentY -
        craterDepth * Math.pow(1 - seed.radial, 2) -
        0.04 * seed.radial +
        0.03 * Math.sin(seed.angle * 3);
      dummy.position.set(
        center.x + Math.cos(seed.angle) * localRadius,
        y,
        center.z + Math.sin(seed.angle) * localRadius,
      );
      dummy.rotation.set(
        seed.rotation * 0.37,
        seed.rotation,
        seed.rotation * 0.19,
      );
      dummy.scale.setScalar(seed.scale);
      dummy.updateMatrix();
      if (seed.type === 0) {
        oreParticles.setMatrixAt(oreIndex, dummy.matrix);
        oreIndex += 1;
      } else {
        cokeParticles.setMatrixAt(cokeIndex, dummy.matrix);
        cokeIndex += 1;
      }
    });
    oreParticles.instanceMatrix.needsUpdate = true;
    cokeParticles.instanceMatrix.needsUpdate = true;
  };

  const addCharge = (event) => {
    if (event?.type === "BURDEN_CHARGE_STARTED") {
      return delivery.start(event);
    }
    const massBalanceRequired =
      event?.evidence !== "measured" ||
      config.burden_fx.live_motion_gate.require_mass_balance !== false;
    if (
      !event ||
      event.type !== "BURDEN_CHARGE_COMPLETED" ||
      (massBalanceRequired && event.mass_balance_valid !== true) ||
      !["ore", "coke"].includes(event.burden_type)
    ) {
      return false;
    }
    layers.forEach((layer) => {
      if (!layer.visible) return;
      layer.position.y -= 0.42;
      if (layer.position.y < worldY(13.8)) layer.visible = false;
    });
    const matching = layers.filter(
      (layer) => layer.userData.burden_type === event.burden_type,
    );
    const mesh =
      matching.find((layer) => !layer.visible) ||
      matching.reduce((oldest, layer) =>
        Number(layer.userData.charge_sequence || 0) <
        Number(oldest.userData.charge_sequence || 0)
          ? layer
          : oldest,
      );
    chargeSequence += 1;
    mesh.position.y = currentY - 0.5;
    mesh.visible = true;
    mesh.userData.evidence_level = event.evidence || "measured";
    mesh.userData.event_id = event.event_id || null;
    mesh.userData.charge_sequence = chargeSequence;
    visibleLayerCount = layers.filter((layer) => layer.visible).length;
    return true;
  };

  const update = (deltaSeconds, state) => {
    const desired =
      Number.isFinite(state.targetY) && state.deformationVisible
        ? state.targetY
        : currentY;
    targetY = desired;
    const spring = 2.8;
    const damping = 3.6;
    velocity += (targetY - currentY) * spring * deltaSeconds;
    velocity *= Math.exp(-damping * deltaSeconds);
    velocity = clamp(velocity, -0.12, 0.12);
    currentY += velocity * deltaSeconds;
    craterDepth = lerp(craterDepth, state.craterDepth ?? 0.3, 0.035);
    const radius = Math.max(2.15, radiusAt(currentY + 20) - 0.18);
    updateStockSurface(
      surfaceGeometry,
      segments,
      rings,
      radius,
      currentY,
      craterDepth,
      state.eccentricX || 0,
      state.eccentricZ || 0,
    );
    updateParticles();
    const descent = Math.max(0, Number(state.descentMps) || 0);
    layers.forEach((layer) => {
      if (!layer.visible || descent <= 0) return;
      layer.position.y -= descent * deltaSeconds;
      if (layer.position.y < worldY(13.8)) layer.visible = false;
    });
    surface.visible = state.deformationVisible;
    oreParticles.visible = state.deformationVisible;
    cokeParticles.visible = state.deformationVisible;
    state.currentY = currentY;
    state.craterDepth = craterDepth;
    delivery.update(deltaSeconds, state);
  };

  const reset = () => {
    currentY = worldY(32.8);
    targetY = currentY;
    velocity = 0;
    craterDepth = 0.3;
    visibleLayerCount = 0;
    chargeSequence = 0;
    layers.forEach((layer) => {
      layer.visible = false;
      layer.position.y = worldY(25.4);
      layer.userData.charge_sequence = 0;
      layer.userData.event_id = null;
    });
    delivery.reset();
  };
  updateParticles();
  return {
    group,
    surface,
    layers,
    oreParticles,
    cokeParticles,
    delivery,
    update,
    reset,
    addCharge,
    getState: () => ({
      targetY,
      currentY,
      velocity,
      visibleLayerCount: layers.filter((layer) => layer.visible).length,
      pooledLayerCount: layers.length,
      surfaceParticleCount: particleCount,
      particleImplementation: "InstancedMesh",
      delivery: delivery.getState(),
    }),
  };
}

function createCohesiveShellGeometry(radialSteps, segments) {
  const vertices = [];
  const indices = [];
  for (let side = 0; side < 2; side += 1) {
    for (let radial = 0; radial <= radialSteps; radial += 1) {
      for (let sector = 0; sector <= segments; sector += 1) {
        vertices.push(0, 0, 0);
      }
    }
  }
  const stride = (radialSteps + 1) * (segments + 1);
  for (let side = 0; side < 2; side += 1) {
    const reverse = side === 1;
    for (let radial = 0; radial < radialSteps; radial += 1) {
      for (let sector = 0; sector < segments; sector += 1) {
        const a = side * stride + radial * (segments + 1) + sector;
        const b = a + segments + 1;
        if (reverse) indices.push(a, a + 1, b, b, a + 1, b + 1);
        else indices.push(a, b, a + 1, b, b + 1, a + 1);
      }
    }
  }
  for (let radialEdge = 0; radialEdge <= radialSteps; radialEdge += radialSteps) {
    for (let sector = 0; sector < segments; sector += 1) {
      const topA = radialEdge * (segments + 1) + sector;
      const topB = topA + 1;
      const bottomA = stride + topA;
      const bottomB = bottomA + 1;
      indices.push(topA, bottomA, topB, topB, bottomA, bottomB);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(vertices, 3),
  );
  geometry.setIndex(indices);
  return geometry;
}

function cohesiveHeightOffset(shape, radial, amplitude) {
  if (shape === "flat") return 0;
  if (shape === "w") return amplitude * Math.cos(radial * Math.PI * 2);
  if (shape === "eccentric") return amplitude * (1 - radial);
  return amplitude * (1 - radial);
}

function writeCohesiveShell(geometry, radialSteps, segments, parameters) {
  const {
    centerHeight,
    thickness,
    innerRadius,
    outerRadius,
    eccentricity,
    eccentricAngle,
    amplitude,
    shape,
  } = parameters;
  const positions = geometry.attributes.position;
  let index = 0;
  for (let side = 0; side < 2; side += 1) {
    const sideOffset = side === 0 ? thickness / 2 : -thickness / 2;
    for (let radialIndex = 0; radialIndex <= radialSteps; radialIndex += 1) {
      const radial = radialIndex / radialSteps;
      const radius = lerp(innerRadius, outerRadius, radial);
      const shapeOffset = cohesiveHeightOffset(shape, radial, amplitude);
      for (let sector = 0; sector <= segments; sector += 1) {
        const angle = (sector / segments) * Math.PI * 2;
        const directional =
          eccentricity * Math.cos(angle - eccentricAngle) * radial;
        positions.setXYZ(
          index,
          Math.cos(angle) * radius +
            Math.cos(eccentricAngle) * eccentricity * 0.35,
          worldY(centerHeight + shapeOffset + directional) + sideOffset,
          Math.sin(angle) * radius +
            Math.sin(eccentricAngle) * eccentricity * 0.35,
        );
        index += 1;
      }
    }
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
}

function createCohesiveSystem(config, center) {
  const mobile = window.innerWidth <= 768;
  const segments = mobile ? 36 : 64;
  const radialSteps = 8;
  const group = new THREE.Group();
  group.name = "BF3D_EST_COHESIVE_ZONE";
  group.position.set(center.x, 0, center.z);
  const geometry = createCohesiveShellGeometry(radialSteps, segments);
  const material = new THREE.MeshStandardMaterial({
    color: 0xc97138,
    emissive: 0x84351f,
    emissiveIntensity: 0.46,
    roughness: 0.64,
    metalness: 0,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const shell = new THREE.Mesh(geometry, material);
  shell.name = "BF3D_EST_COHESIVE_ZONE_SHELL";
  shell.renderOrder = 18;
  group.add(shell);
  const confidenceGeometry = createCohesiveShellGeometry(
    radialSteps,
    segments,
  );
  const confidenceMaterial = new THREE.MeshBasicMaterial({
    color: 0xe0a06a,
    transparent: true,
    opacity: 0.16,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const confidence = new THREE.Mesh(
    confidenceGeometry,
    confidenceMaterial,
  );
  confidence.name = "BF3D_EST_COHESIVE_ZONE_CONFIDENCE";
  confidence.renderOrder = 17;
  group.add(confidence);
  const whatIfMaterial = new THREE.MeshStandardMaterial({
    color: 0xf18a45,
    emissive: 0x9f361b,
    emissiveIntensity: 0.72,
    roughness: 0.68,
    metalness: 0,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const whatIfEdgeMaterial = new THREE.MeshBasicMaterial({
    color: 0xffaa68,
    transparent: true,
    opacity: 0.42,
    depthWrite: false,
  });
  const whatIfGroup = new THREE.Group();
  whatIfGroup.name = "BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF";
  whatIfGroup.userData = {
    semantic_id: "BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF",
    evidence_level: "illustrative",
    causal: false,
    production_default_hidden: true,
  };
  const whatIfShell = new THREE.Mesh(
    new THREE.CylinderGeometry(3.35, 3.35, 0.56, segments, 1, true),
    whatIfMaterial,
  );
  whatIfShell.name = "BF3D_ILL_COHESIVE_RESPONSE_SHELL";
  whatIfShell.position.y = worldY(16.2);
  const whatIfUpperEdge = new THREE.Mesh(
    new THREE.TorusGeometry(3.35, 0.045, 6, segments),
    whatIfEdgeMaterial,
  );
  whatIfUpperEdge.name = "BF3D_ILL_COHESIVE_RESPONSE_UPPER_EDGE";
  whatIfUpperEdge.rotation.x = Math.PI / 2;
  whatIfUpperEdge.position.y = worldY(16.48);
  const whatIfLowerEdge = whatIfUpperEdge.clone();
  whatIfLowerEdge.name = "BF3D_ILL_COHESIVE_RESPONSE_LOWER_EDGE";
  whatIfLowerEdge.position.y = worldY(15.92);
  whatIfGroup.add(whatIfShell, whatIfUpperEdge, whatIfLowerEdge);
  whatIfGroup.visible = false;
  group.add(whatIfGroup);
  const current = {
    centerHeight: 15.7,
    thickness: 2.1,
    innerRadius: 0.9,
    outerRadius: 3.8,
    eccentricity: 0,
    eccentricAngle: 0,
    amplitude: 2.2,
    uncertainty: 0.6,
    shape: config.illustrative_scenario.cohesive_shape,
  };
  const target = { ...current };
  let evidence = "no-data";
  let modelVersion = null;
  let sceneVersion = null;
  let rootHeight = current.centerHeight;
  let movement = {
    direction: "unknown",
    velocity_m_per_h: null,
    forecast_height_m: null,
    forecast_15m_height_m: null,
  };
  let confidenceValue = null;
  let inputCoverage = null;
  let calibrationStatus = null;
  let controlUse = null;
  let rootDefinition = null;
  let azimuthReference = null;
  let absoluteAzimuthStatus = null;
  let sampleTime = null;
  let quality = { state: "no-data", warnings: [] };
  let freshnessState = "no-data";
  let whatIfEnabled = Boolean(config.burden_fx.what_if_default_enabled);
  let whatIfPulse = 0;
  let whatIfTriggerCount = 0;
  const syncGroupVisibility = () => {
    group.visible = shell.visible || whatIfGroup.visible;
  };

  const setParameters = (next) => {
    if (!next) {
      evidence = "no-data";
      modelVersion = null;
      sceneVersion = null;
      rootHeight = current.centerHeight;
      movement = {
        direction: "unknown",
        velocity_m_per_h: null,
        forecast_height_m: null,
        forecast_15m_height_m: null,
      };
      confidenceValue = null;
      inputCoverage = null;
      calibrationStatus = null;
      controlUse = null;
      rootDefinition = null;
      azimuthReference = null;
      absoluteAzimuthStatus = null;
      sampleTime = null;
      quality = { state: "no-data", warnings: [] };
      freshnessState = "no-data";
      shell.visible = false;
      confidence.visible = false;
      syncGroupVisibility();
      return;
    }
    [
      ["centerHeight", "center_height"],
      ["thickness", "thickness_m"],
      ["innerRadius", "inner_radius"],
      ["outerRadius", "outer_radius"],
      ["eccentricity", "eccentricity_m"],
      ["eccentricAngle", "eccentric_angle"],
      ["amplitude", "amplitude_m"],
      ["uncertainty", "uncertainty_m"],
    ].forEach(([key, alias]) => {
      const value = finite(next[key] ?? next[alias]);
      if (value !== null) target[key] = value;
    });
    if (["flat", "inverted_v", "w", "eccentric"].includes(next.shape)) {
      target.shape = next.shape;
    }
    evidence = ["estimated", "simulated"].includes(next.evidence)
      ? next.evidence
      : "no-data";
    modelVersion = next.model_version || null;
    sceneVersion = next.scene_version || null;
    rootHeight =
      finite(next.rootHeight ?? next.root_height_m) ??
      finite(next.centerHeight ?? next.center_height) ??
      target.centerHeight;
    const nextMovement =
      next.movement && typeof next.movement === "object"
        ? next.movement
        : {};
    const direction =
      nextMovement.direction ||
      next.movement_direction ||
      next.direction ||
      "unknown";
    const forecastHeight = finite(
      nextMovement.forecast_height_m ??
        nextMovement.forecast_15m_height_m ??
        next.forecast_height_m ??
        next.forecast_15m_height_m,
    );
    movement = {
      direction: ["up", "down", "stable"].includes(direction)
        ? direction
        : "unknown",
      velocity_m_per_h: finite(
        nextMovement.velocity_m_per_h ??
          next.movement_rate_m_per_h ??
          next.velocity_m_per_h,
      ),
      forecast_height_m: forecastHeight,
      forecast_15m_height_m: forecastHeight,
    };
    confidenceValue = ratio(
      next.confidence?.value ??
        next.confidence?.score ??
        next.confidence,
    );
    inputCoverage = ratio(
      next.input_coverage?.ratio ??
        next.input_coverage?.value ??
        next.input_coverage,
    );
    calibrationStatus =
      next.calibration_status ||
      next.calibration?.status ||
      null;
    controlUse = next.control_use || null;
    rootDefinition = next.root_definition || null;
    azimuthReference = next.azimuth_reference || null;
    absoluteAzimuthStatus =
      next.absolute_azimuth_status || null;
    sampleTime = next.sample_time || null;
    const suppliedQuality =
      next.quality && typeof next.quality === "object"
        ? next.quality
        : { state: next.quality };
    freshnessState =
      next.runtime_freshness ||
      suppliedQuality.runtime_freshness ||
      suppliedQuality.state ||
      "good";
    quality = {
      ...suppliedQuality,
      state:
        freshnessState === "stale"
          ? "stale"
          : suppliedQuality.state || "good",
      warnings: Array.isArray(suppliedQuality.warnings)
        ? [...suppliedQuality.warnings]
        : [],
    };
    shell.visible = evidence !== "no-data";
    confidence.visible = shell.visible && evidence === "estimated";
    syncGroupVisibility();
  };
  const setWhatIfEnabled = (enabled) => {
    whatIfEnabled = Boolean(enabled);
    if (!whatIfEnabled) {
      whatIfPulse = 0;
      whatIfGroup.visible = false;
    }
    syncGroupVisibility();
    return whatIfEnabled;
  };
  const triggerWhatIf = () => {
    if (!whatIfEnabled) return false;
    whatIfPulse = 1;
    whatIfTriggerCount += 1;
    whatIfGroup.visible = true;
    syncGroupVisibility();
    return true;
  };
  const update = (deltaSeconds) => {
    const amount = 1 - Math.exp(-1.9 * deltaSeconds);
    [
      "centerHeight",
      "thickness",
      "innerRadius",
      "outerRadius",
      "eccentricity",
      "eccentricAngle",
      "amplitude",
      "uncertainty",
    ].forEach((key) => {
      current[key] = lerp(current[key], target[key], amount);
    });
    current.shape = target.shape;
    if (shell.visible) {
      writeCohesiveShell(geometry, radialSteps, segments, current);
      writeCohesiveShell(confidenceGeometry, radialSteps, segments, {
        ...current,
        thickness: current.thickness + current.uncertainty * 2,
        innerRadius: Math.max(
          0.3,
          current.innerRadius - current.uncertainty * 0.2,
        ),
        outerRadius:
          current.outerRadius + current.uncertainty * 0.2,
      });
      confidence.visible = evidence === "estimated";
    }
    if (whatIfEnabled && whatIfPulse > 0.012) {
      whatIfPulse *= Math.exp(-0.72 * deltaSeconds);
      const pulse =
        1 +
        whatIfPulse *
          (0.035 + Math.sin(performance.now() * 0.009) * 0.012);
      whatIfGroup.scale.set(pulse, 1 + whatIfPulse * 0.018, pulse);
      whatIfMaterial.opacity = 0.1 + whatIfPulse * 0.24;
      whatIfMaterial.emissiveIntensity = 0.42 + whatIfPulse * 0.82;
      whatIfEdgeMaterial.opacity = 0.18 + whatIfPulse * 0.5;
      whatIfGroup.visible = true;
    } else if (!whatIfEnabled || whatIfPulse <= 0.012) {
      whatIfGroup.visible = false;
    }
    syncGroupVisibility();
  };
  shell.visible = false;
  confidence.visible = false;
  group.visible = false;
  return {
    group,
    setParameters,
    setWhatIfEnabled,
    triggerWhatIf,
    update,
    reset: () => {
      setParameters(null);
      setWhatIfEnabled(config.burden_fx.what_if_default_enabled);
    },
    getState: () => ({
      evidence,
      shape: current.shape,
      centerHeight: current.centerHeight,
      thickness: current.thickness,
      innerRadius: current.innerRadius,
      outerRadius: current.outerRadius,
      eccentricity: current.eccentricity,
      uncertainty: current.uncertainty,
      rootHeight,
      movement: { ...movement },
      confidence: confidenceValue,
      inputCoverage,
      input_coverage: inputCoverage,
      calibrationStatus,
      calibration_status: calibrationStatus,
      controlUse,
      control_use: controlUse,
      rootDefinition,
      root_definition: rootDefinition,
      azimuthReference,
      azimuth_reference: azimuthReference,
      absoluteAzimuthStatus,
      absolute_azimuth_status: absoluteAzimuthStatus,
      sampleTime,
      sample_time: sampleTime,
      quality: {
        ...quality,
        warnings: [...quality.warnings],
      },
      freshness: freshnessState,
      modelVersion,
      model_version: modelVersion,
      sceneVersion,
      confidenceVisible: confidence.visible,
      visible: shell.visible,
      implementation: "closed_parametric_volume_shell",
      whatIf: {
        enabled: whatIfEnabled,
        visible: whatIfGroup.visible,
        evidence: "illustrative",
        causal: false,
        triggerCount: whatIfTriggerCount,
        productionDefaultHidden: true,
        label: "软熔带响应开关演示；非本批次实时因果结果",
      },
    }),
  };
}

function pressureColor(value, config, target = new THREE.Color()) {
  const min = config.pressure.legend_min;
  const max = config.pressure.legend_max;
  const amount = clamp((Number(value) - min) / (max - min), 0, 1);
  const stops = [
    [0, new THREE.Color(0x3869a9)],
    [0.25, new THREE.Color(0x6a9bc0)],
    [0.5, new THREE.Color(0x8a8f83)],
    [0.75, new THREE.Color(0xd2a64c)],
    [1, new THREE.Color(0xd25c3c)],
  ];
  for (let index = 1; index < stops.length; index += 1) {
    if (amount <= stops[index][0]) {
      const [lowerStop, lowerColor] = stops[index - 1];
      const [upperStop, upperColor] = stops[index];
      return target
        .copy(lowerColor)
        .lerp(
          upperColor,
          (amount - lowerStop) / (upperStop - lowerStop),
        );
    }
  }
  return target.copy(stops[stops.length - 1][1]);
}

function circularInterpolate(values, normalizedAngle) {
  const scaled = ((normalizedAngle % 1) + 1) % 1 * values.length;
  const lower = Math.floor(scaled) % values.length;
  const upper = (lower + 1) % values.length;
  const amount = scaled - Math.floor(scaled);
  return lerp(values[lower], values[upper], smoothstep(amount));
}

function createPressureSystem(config, center) {
  const operationalGroup = new THREE.Group();
  operationalGroup.name = "BF3D_MEAS_STATIC_PRESSURE";
  operationalGroup.userData = {
    semantic_id: "BF3D_OPERATIONAL_STATIC_PRESSURE_OVERLAY",
    evidence_role: "measured",
    bf3d_operational_overlay: true,
    bf3d_review_visibility: "hidden",
  };
  const fieldGroup = new THREE.Group();
  fieldGroup.name = "BF3D_DERIVED_STATIC_PRESSURE_FIELD";
  fieldGroup.userData = {
    semantic_id: "BF3D_DERIVED_STATIC_PRESSURE_FIELD",
    evidence_role: "interpolated_and_estimated",
    bf3d_operational_overlay: false,
    bf3d_review_visibility: "hidden",
  };
  const markers = [];
  const markerGeometry = new THREE.SphereGeometry(0.105, 12, 8);
  const markerMaterial = new THREE.MeshBasicMaterial({
    color: 0xf2c94c,
    transparent: true,
    opacity: 0.96,
  });
  const bandMaterial = new THREE.MeshBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.36,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const bands = [];
  const arrows = [];
  const lastGoodRows = new Map();
  const markerIdentityColor = new THREE.Color(0xf2c94c);
  const staleMarkerColor = new THREE.Color(0x8f7728);
  config.pressure.height_m.forEach((heightM, heightIndex) => {
    const heightLabel = ["lower", "middle", "upper"][heightIndex];
    const radius = radiusAt(heightM) - 0.14;
    const geometry = new THREE.CylinderGeometry(
      radius,
      radius,
      0.42,
      72,
      1,
      true,
    );
    const colors = new Float32Array(geometry.attributes.position.count * 3);
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const band = new THREE.Mesh(geometry, bandMaterial.clone());
    band.name = `BF3D_INTERP_STATIC_PRESSURE_BAND_${heightIndex + 1}`;
    band.position.set(center.x, worldY(heightM), center.z);
    band.renderOrder = 14;
    band.visible = false;
    band.userData = {
      semantic_id: `P_static_${heightLabel}_periodic_band`,
      evidence_role: "interpolated",
      evidence_level: "no-data",
      derivation: "periodic_interpolation",
      quality_state: "missing",
      height_m: heightM,
      source_point_count: 0,
    };
    fieldGroup.add(band);
    bands.push(band);
    config.pressure.azimuth_labels.forEach((label, sectorIndex) => {
      const angle =
        -Math.PI / 2 +
        (sectorIndex / config.pressure.azimuth_labels.length) * Math.PI * 2;
      const marker = new THREE.Mesh(markerGeometry, markerMaterial.clone());
      marker.name = `BF3D_MEAS_STATIC_PRESSURE_${heightIndex + 1}_${label}`;
      const markerRadius = radius + 0.26;
      marker.position.set(
        center.x + Math.cos(angle) * markerRadius,
        worldY(heightM),
        center.z + Math.sin(angle) * markerRadius,
      );
      marker.userData = {
        semantic_id: `P_static_${heightLabel}_${label}`,
        evidence_role: "measured",
        evidence_level: "no-data",
        derivation: "raw",
        orientation_status: config.pressure.orientation_status,
        height_m: heightM,
        radial_offset_from_shell_m: 0.12,
        azimuth: label,
        value: null,
        deviation_kpa: null,
        unit: "kPa",
        quality_state: "missing",
        sample_time: null,
      };
      marker.visible = false;
      operationalGroup.add(marker);
      markers.push(marker);
    });
    const arrow = new THREE.ArrowHelper(
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(center.x, worldY(heightM), center.z),
      1.15,
      0xd6a958,
      0.26,
      0.14,
    );
    arrow.name = `BF3D_EST_PRESSURE_BIAS_ARROW_${heightIndex + 1}`;
    arrow.visible = false;
    arrow.userData = {
      semantic_id: `P_static_${heightLabel}_bias_arrow`,
      evidence_role: "estimated",
      evidence_level: "no-data",
      derivation: "first_circular_moment",
      quality_state: "missing",
      height_m: heightM,
      source_point_count: 0,
    };
    fieldGroup.add(arrow);
    arrows.push(arrow);
  });

  let rows = [];
  const pressureRowQuality = (row, illustrative) => {
    const value = finite(row?.value);
    if (value === null) return "missing";
    if (illustrative) return "illustrative";
    const declared = String(row?.quality_state || "")
      .trim()
      .toLowerCase();
    if (["missing", "bad", "maintenance", "no-data"].includes(declared)) {
      return "missing";
    }
    const sampleMillis = new Date(row?.sample_time || "").getTime();
    if (!Number.isFinite(sampleMillis)) return "missing";
    const ageMillis = Math.max(0, Date.now() - sampleMillis);
    if (ageMillis > config.freshness.sensor_hard_expire_after_ms) {
      return "hard-expired";
    }
    if (
      declared === "stale" ||
      ageMillis > config.freshness.sensor_warn_after_ms
    ) {
      return "stale";
    }
    return "good";
  };
  const setRows = (nextRows, { illustrative = false } = {}) => {
    rows = Array.isArray(nextRows) ? nextRows : [];
    const byId = new Map(rows.map((row) => [row.semantic_id, row]));
    config.pressure.height_m.forEach((heightM, heightIndex) => {
      const labelPrefix = ["lower", "middle", "upper"][heightIndex];
      const points = config.pressure.azimuth_labels.map((label) => {
        const semanticId = `P_static_${labelPrefix}_${label}`;
        const row = byId.get(semanticId);
        const qualityState = pressureRowQuality(row, illustrative);
        const value = finite(row?.value);
        const deviationKpa = finite(row?.deviation_kpa);
        if (qualityState === "good") {
          lastGoodRows.set(semanticId, {
            value,
            deviation_kpa: deviationKpa,
            sample_time: row?.sample_time || null,
          });
        }
        const frozen = qualityState === "stale" ? lastGoodRows.get(semanticId) : null;
        return {
          semanticId,
          row,
          qualityState,
          value: frozen?.value ?? value,
          deviationKpa: frozen?.deviation_kpa ?? deviationKpa,
          sampleTime: frozen?.sample_time ?? row?.sample_time ?? null,
        };
      });
      const derivationReady = points.every(
        (point) =>
          ["good", "illustrative"].includes(point.qualityState) &&
          point.deviationKpa !== null,
      );
      const band = bands[heightIndex];
      band.visible = derivationReady;
      band.userData.evidence_level = derivationReady
        ? illustrative
          ? "illustrative"
          : "interpolated"
        : "no-data";
      band.userData.quality_state = derivationReady
        ? illustrative
          ? "illustrative"
          : "good"
        : "missing";
      band.userData.source_point_count = derivationReady ? 6 : 0;
      if (derivationReady) {
        const deviations = points.map((point) => point.deviationKpa);
        const position = band.geometry.attributes.position;
        const colors = band.geometry.attributes.color;
        const color = new THREE.Color();
        for (let vertex = 0; vertex < position.count; vertex += 1) {
          const angle = Math.atan2(position.getZ(vertex), position.getX(vertex));
          const normalized = (angle + Math.PI / 2) / (Math.PI * 2);
          pressureColor(
            circularInterpolate(deviations, normalized),
            config,
            color,
          );
          colors.setXYZ(vertex, color.r, color.g, color.b);
        }
        colors.needsUpdate = true;
      }
      const sliceMarkers = markers.slice(heightIndex * 6, heightIndex * 6 + 6);
      sliceMarkers.forEach((marker, sectorIndex) => {
        const point = points[sectorIndex];
        const visible =
          point.value !== null &&
          ["good", "stale", "illustrative"].includes(point.qualityState);
        marker.visible = visible;
        marker.userData.value = visible ? point.value : null;
        marker.userData.deviation_kpa = visible ? point.deviationKpa : null;
        marker.userData.evidence_level = !visible
          ? "no-data"
          : point.qualityState === "illustrative"
            ? "illustrative"
            : point.qualityState === "stale"
              ? "stale"
              : "measured";
        marker.userData.quality_state =
          point.qualityState === "hard-expired"
            ? "missing"
            : point.qualityState;
        marker.userData.freshness_state = point.qualityState;
        marker.userData.sample_time = point.sampleTime;
        marker.userData.source_sample_time = point.row?.sample_time || null;
        marker.material.opacity = point.qualityState === "stale" ? 0.72 : 0.96;
        if (point.qualityState === "stale") {
          marker.material.color.copy(staleMarkerColor);
        } else {
          marker.material.color.copy(markerIdentityColor);
        }
      });
      const arrow = arrows[heightIndex];
      arrow.visible = derivationReady;
      arrow.userData.evidence_level = derivationReady
        ? illustrative
          ? "illustrative"
          : "estimated"
        : "no-data";
      arrow.userData.quality_state = derivationReady
        ? illustrative
          ? "illustrative"
          : "good"
        : "missing";
      arrow.userData.source_point_count = derivationReady ? 6 : 0;
      if (derivationReady) {
        const deviations = points.map((point) => point.deviationKpa);
        let x = 0;
        let z = 0;
        deviations.forEach((value, sectorIndex) => {
          const angle =
            -Math.PI / 2 + (sectorIndex / deviations.length) * Math.PI * 2;
          x += Math.cos(angle) * value;
          z += Math.sin(angle) * value;
        });
        const direction = new THREE.Vector3(-x, 2.8, -z).normalize();
        arrow.setDirection(direction);
        arrow.setLength(
          clamp(Math.hypot(x, z) / deviations.length / 3, 0.65, 1.7),
          0.26,
          0.14,
        );
      }
    });
  };
  return {
    group: operationalGroup,
    operationalGroup,
    fieldGroup,
    markers,
    bands,
    arrows,
    setRows,
    reset: () => {
      lastGoodRows.clear();
      setRows([]);
    },
    getState: () => {
      const visibleMarkers = markers.filter((marker) => marker.visible);
      const visibleStaleCount = visibleMarkers.filter(
        (marker) => marker.userData.evidence_level === "stale",
      ).length;
      const visibleIllustrativeCount = visibleMarkers.filter(
        (marker) => marker.userData.evidence_level === "illustrative",
      ).length;
      return {
        evidence: !visibleMarkers.length
          ? "no-data"
          : visibleIllustrativeCount === visibleMarkers.length
            ? "illustrative"
            : visibleStaleCount > 0
              ? "stale"
              : "measured",
        markerCount: markers.length,
        visibleMeasuredCount: visibleMarkers.length,
        visiblePointCount: visibleMarkers.length,
        visibleGoodCount: visibleMarkers.filter(
          (marker) => marker.userData.quality_state === "good",
        ).length,
        visibleStaleCount,
        rawWithoutDeviationCount: visibleMarkers.filter(
          (marker) => marker.userData.deviation_kpa === null,
        ).length,
        interpolatedBandCount: bands.filter((band) => band.visible).length,
        biasArrowCount: arrows.filter((arrow) => arrow.visible).length,
        operationalOverlayVisible: operationalGroup.visible,
        fieldOverlayVisible: fieldGroup.visible,
        orientationStatus: config.pressure.orientation_status,
        legendMode: config.pressure.legend_mode,
        legendRange: [
          config.pressure.legend_min,
          config.pressure.legend_max,
        ],
        fieldLabel: "压力偏流指示（非煤气真实流线）",
      };
    },
  };
}

function createTuyereSystem(config, center) {
  const group = new THREE.Group();
  group.name = "BF3D_SIM_TUYERE_RACEWAY";
  const tuyereCount = config.tuyere_count;
  const heightM = 8.2;
  const radius = radiusAt(heightM) - 0.22;
  const racewayGeometry = new THREE.SphereGeometry(1, 9, 6);
  const racewayMaterial = new THREE.MeshStandardMaterial({
    color: 0x7a3e25,
    emissive: 0xe25c25,
    emissiveIntensity: 0.65,
    roughness: 0.5,
    metalness: 0,
    transparent: true,
    opacity: 0.56,
    depthWrite: false,
  });
  const raceways = new THREE.InstancedMesh(
    racewayGeometry,
    racewayMaterial,
    tuyereCount,
  );
  raceways.name = "BF3D_SIM_RACEWAY_INSTANCES_26";
  raceways.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  group.add(raceways);
  const maxPerTuyere = config.performance.pci_points_per_tuyere_max;
  const maxPoints = maxPerTuyere * tuyereCount;
  const positions = new Float32Array(maxPoints * 3);
  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(positions, 3),
  );
  const particleMaterial = new THREE.PointsMaterial({
    color: 0xdfa15e,
    size: 0.075,
    transparent: true,
    opacity: 0.82,
    depthWrite: false,
    sizeAttenuation: true,
    blending: THREE.AdditiveBlending,
  });
  const particles = new THREE.Points(particleGeometry, particleMaterial);
  particles.name = "BF3D_SIM_PCI_POINTS";
  group.add(particles);
  const random = seededRandom(config.illustrative_scenario.random_seed + 26);
  const seeds = Array.from({ length: maxPoints }, () => ({
    phase: random(),
    jitter: (random() - 0.5) * 0.13,
    vertical: (random() - 0.5) * 0.11,
  }));
  const dummy = new THREE.Object3D();
  const quaternion = new THREE.Quaternion();
  const xAxis = new THREE.Vector3(1, 0, 0);
  let intensity = 0;
  let evidence = "no-data";
  let perTuyere = 0;
  let source = null;

  const setTotals = (totals) => {
    const qBlast = finite(totals?.Q_blast);
    const oxygen = finite(totals?.O2_rate);
    const pci = finite(totals?.PCI_rate);
    evidence = totals?.evidence || (qBlast !== null ? "measured" : "no-data");
    source = totals || null;
    if (qBlast === null && pci === null && oxygen === null) {
      intensity = 0;
      perTuyere = 0;
      return;
    }
    const blastFactor = qBlast === null ? 0.5 : clamp((qBlast - 3200) / 1800, 0, 1);
    const oxygenFactor =
      oxygen === null ? 0.5 : clamp((oxygen - 1.5) / 5.5, 0, 1);
    const pciFactor = pci === null ? 0.5 : clamp((pci - 28) / 32, 0, 1);
    intensity = clamp(
      blastFactor * 0.5 + oxygenFactor * 0.2 + pciFactor * 0.3,
      0.12,
      1,
    );
    perTuyere = Math.max(2, Math.round(maxPerTuyere * intensity));
  };

  const update = (elapsedSeconds) => {
    racewayMaterial.emissiveIntensity = 0.35 + intensity * 1.15;
    racewayMaterial.opacity = intensity > 0 ? 0.3 + intensity * 0.42 : 0;
    raceways.visible = intensity > 0;
    particles.visible = intensity > 0;
    for (let tuyereIndex = 0; tuyereIndex < tuyereCount; tuyereIndex += 1) {
      const angle = (tuyereIndex / tuyereCount) * Math.PI * 2;
      const radialDirection = new THREE.Vector3(
        -Math.cos(angle),
        0,
        -Math.sin(angle),
      );
      dummy.position.set(
        center.x + Math.cos(angle) * radius,
        worldY(heightM),
        center.z + Math.sin(angle) * radius,
      );
      quaternion.setFromUnitVectors(xAxis, radialDirection);
      dummy.quaternion.copy(quaternion);
      dummy.scale.set(
        0.34 + intensity * 0.72,
        0.18 + intensity * 0.2,
        0.18 + intensity * 0.2,
      );
      dummy.updateMatrix();
      raceways.setMatrixAt(tuyereIndex, dummy.matrix);
      for (let pointIndex = 0; pointIndex < maxPerTuyere; pointIndex += 1) {
        const globalIndex = tuyereIndex * maxPerTuyere + pointIndex;
        if (pointIndex >= perTuyere) {
          positions[globalIndex * 3] = 1e5;
          positions[globalIndex * 3 + 1] = 1e5;
          positions[globalIndex * 3 + 2] = 1e5;
          continue;
        }
        const seed = seeds[globalIndex];
        const progress =
          (seed.phase + elapsedSeconds * (0.42 + intensity * 0.72)) % 1;
        const travel = 0.18 + progress * (0.8 + intensity * 1.25);
        const tangentX = -Math.sin(angle);
        const tangentZ = Math.cos(angle);
        positions[globalIndex * 3] =
          center.x +
          Math.cos(angle) * radius +
          radialDirection.x * travel +
          tangentX * seed.jitter * progress;
        positions[globalIndex * 3 + 1] =
          worldY(heightM) + seed.vertical * progress;
        positions[globalIndex * 3 + 2] =
          center.z +
          Math.sin(angle) * radius +
          radialDirection.z * travel +
          tangentZ * seed.jitter * progress;
      }
    }
    raceways.instanceMatrix.needsUpdate = true;
    particleGeometry.attributes.position.needsUpdate = true;
    particleGeometry.setDrawRange(0, maxPoints);
  };
  setTotals(null);
  return {
    group,
    raceways,
    particles,
    setTotals,
    update,
    reset: () => setTotals(null),
    getState: () => ({
      evidence,
      tuyereCount,
      racewayInstanceCount: tuyereCount,
      particleImplementation: "Points",
      particleCapacity: maxPoints,
      activePointsPerTuyere: perTuyere,
      uniformIntensity: true,
      minTuyereIntensity: intensity,
      maxTuyereIntensity: intensity,
      intensity,
      source,
    }),
  };
}

function createHearthSystem(config, center) {
  const group = new THREE.Group();
  group.name = "BF3D_EST_HEARTH_SYSTEM";
  const ironMaterial = new THREE.MeshStandardMaterial({
    color: 0x5f2417,
    emissive: 0xff5a24,
    emissiveIntensity: 1.35,
    roughness: 0.28,
    metalness: 0.18,
    transparent: true,
    opacity: 0.9,
    depthWrite: true,
  });
  const slagMaterial = new THREE.MeshStandardMaterial({
    color: 0x6e4823,
    emissive: 0xd08a36,
    emissiveIntensity: 0.72,
    roughness: 0.62,
    metalness: 0,
    transparent: true,
    opacity: 0.82,
    depthWrite: false,
  });
  const iron = new THREE.Mesh(
    new THREE.CylinderGeometry(1.82, 1.88, 0.72, 48, 1, false),
    ironMaterial,
  );
  iron.name = "BF3D_EST_HEARTH_HOT_METAL";
  iron.position.set(center.x, worldY(2.25), center.z);
  iron.renderOrder = 20;
  const slag = new THREE.Mesh(
    new THREE.CylinderGeometry(1.86, 1.9, 0.36, 48, 1, false),
    slagMaterial,
  );
  slag.name = "BF3D_EST_HEARTH_SLAG";
  slag.position.set(center.x, worldY(2.8), center.z);
  slag.renderOrder = 21;
  const streamMaterial = new THREE.MeshStandardMaterial({
    color: 0x8d3318,
    emissive: 0xff6b27,
    emissiveIntensity: 1.7,
    roughness: 0.34,
    metalness: 0.08,
  });
  const stream = new THREE.Mesh(
    new THREE.CylinderGeometry(0.095, 0.095, 4.6, 14, 1, false),
    streamMaterial,
  );
  stream.name = "BF3D_EST_TAP_STREAM_UNIFORM";
  stream.rotation.z = Math.PI / 2;
  stream.position.set(center.x + 3.7, worldY(2.45), center.z);
  stream.renderOrder = 24;
  const dropletCount = config.performance.droplet_point_count;
  const dropletPositions = new Float32Array(dropletCount * 3);
  const dropletGeometry = new THREE.BufferGeometry();
  dropletGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(dropletPositions, 3),
  );
  const droplets = new THREE.Points(
    dropletGeometry,
    new THREE.PointsMaterial({
      color: 0xff7a36,
      size: 0.11,
      transparent: true,
      opacity: 0.78,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  droplets.name = "BF3D_SIM_DROPLETS_POINTS";
  droplets.renderOrder = 19;
  group.add(iron, slag, stream, droplets);
  const random = seededRandom(config.illustrative_scenario.random_seed + 66);
  const dropletSeeds = Array.from({ length: dropletCount }, () => ({
    angle: random() * Math.PI * 2,
    radial: 0.4 + random() * 2.7,
    phase: random(),
    speed: 0.42 + random() * 0.7,
  }));
  let evidence = "no-data";
  let dropletEvidence = "no-data";
  let tapActive = false;
  let liquidVisible = false;
  let ironLevel = 2.25;
  let slagLevel = 2.8;
  let tapEventId = null;

  const setState = (next) => {
    if (!next) {
      evidence = "no-data";
      dropletEvidence = "no-data";
      tapActive = false;
      liquidVisible = false;
      tapEventId = null;
      return;
    }
    evidence = ["estimated", "illustrative", "simulated"].includes(next.evidence)
      ? next.evidence
      : "no-data";
    dropletEvidence = ["estimated", "simulated"].includes(
      next.droplet_evidence,
    )
      ? next.droplet_evidence
      : "no-data";
    liquidVisible = evidence !== "no-data";
    tapActive = next.tap_active === true;
    ironLevel = finite(next.iron_level_m) ?? ironLevel;
    slagLevel = finite(next.slag_level_m) ?? slagLevel;
    tapEventId = next.tap_event_id || null;
  };
  const dispatchEvent = (event) => {
    if (event?.type === "TAP_OPENED") {
      tapActive = true;
      tapEventId = event.event_id || null;
      return true;
    }
    if (event?.type === "TAP_CLOSED") {
      tapActive = false;
      tapEventId = event.event_id || null;
      return true;
    }
    return false;
  };
  const update = (elapsedSeconds) => {
    iron.visible = liquidVisible;
    slag.visible = liquidVisible;
    stream.visible = liquidVisible && tapActive;
    droplets.visible =
      liquidVisible &&
      ["estimated", "simulated"].includes(dropletEvidence);
    iron.position.y = worldY(ironLevel);
    slag.position.y = worldY(Math.max(slagLevel, ironLevel + 0.42));
    const ripple = 1 + Math.sin(elapsedSeconds * 1.25) * 0.006;
    iron.scale.set(ripple, 1, ripple);
    slag.scale.set(2 - ripple, 1, 2 - ripple);
    dropletSeeds.forEach((seed, index) => {
      const progress = (seed.phase + elapsedSeconds * seed.speed * 0.12) % 1;
      const y = worldY(13.2) - progress * 9.9;
      const inward = 1 - progress * 0.42;
      dropletPositions[index * 3] =
        center.x + Math.cos(seed.angle) * seed.radial * inward;
      dropletPositions[index * 3 + 1] = y;
      dropletPositions[index * 3 + 2] =
        center.z + Math.sin(seed.angle) * seed.radial * inward;
    });
    dropletGeometry.attributes.position.needsUpdate = true;
  };
  setState(null);
  return {
    group,
    iron,
    slag,
    stream,
    droplets,
    setState,
    dispatchEvent,
    update,
    reset: () => setState(null),
    getState: () => ({
      evidence,
      dropletEvidence,
      liquidVisible,
      ironVisible: iron.visible,
      slagVisible: slag.visible,
      separateLiquidSurfaces: true,
      ironLevel,
      slagLevel,
      tapActive,
      tapEventId,
      streamWidthPolicy: "uniform_without_instantaneous_flow",
      dropletImplementation: "Points",
      dropletCount,
    }),
  };
}

function createDemoSnapshot(config) {
  const now = new Date().toISOString();
  const pressureRows = [];
  const bases = [184, 162, 128];
  ["lower", "middle", "upper"].forEach((height, heightIndex) => {
    config.pressure.azimuth_labels.forEach((label, sectorIndex) => {
      const deviation =
        Math.sin((sectorIndex / 6) * Math.PI * 2 + heightIndex * 0.7) *
          (5.6 - heightIndex * 0.7) +
        0.8 * heightIndex;
      pressureRows.push({
        semantic_id: `P_static_${height}_${label}`,
        value: bases[heightIndex] + deviation,
        deviation_kpa: deviation,
        unit: "kPa",
        evidence: "illustrative",
        sample_time: now,
      });
    });
  });
  return {
    schema_version: "bf3d_snapshot.v1",
    furnace_id: "GL02",
    mode: "illustrative",
    render_time: now,
    knowledge_time: now,
    measured: {
      stockline: {
        L: 2.18,
        sample_time: now,
        evidence: "illustrative",
      },
      static_pressure: pressureRows,
      blast: {
        Q_blast: 4215,
        O2_rate: 4.3,
        PCI_rate: 43.5,
        evidence: "illustrative",
        sample_time: now,
      },
      active_tap: {
        tap_active: true,
        event_id: "DEMO-TAP-OPEN",
        evidence: "illustrative",
      },
    },
    estimated: {
      burden_state: {
        target_height_m: 32.7,
        descent_mps: 0.035,
        crater_depth_m: 0.34,
        evidence: "illustrative",
        mass_balance_valid: true,
      },
      cohesive_zone: {
        centerHeight: 15.8,
        thickness: 2.15,
        innerRadius: 0.9,
        outerRadius: 3.85,
        eccentricity: 0.16,
        eccentricAngle: 0.4,
        amplitude: 2.25,
        uncertainty: 0.62,
        shape: config.illustrative_scenario.cohesive_shape,
        evidence: "estimated",
        model_version: "C2-DEMO-2026.07",
        movement: {
          direction: "stable",
          velocity_m_per_h: 0.02,
          forecast_15m_height_m: 15.81,
        },
        confidence: 0.78,
        input_coverage: 0.86,
        calibration_status: "teaching_only",
        sample_time: now,
        quality: {
          state: "illustrative",
          warnings: ["教学参数，不代表当前生产炉况"],
        },
      },
      hearth_inventory: {
        evidence: "illustrative",
        droplet_evidence: "estimated",
        iron_level_m: 2.22,
        slag_level_m: 2.78,
        tap_active: true,
        tap_event_id: "DEMO-TAP-OPEN",
      },
    },
    quality: {
      state: "illustrative",
      missing: [],
      stale: [],
      bad: [],
      warnings: ["教学演示数据，不代表 GL02 当前生产状态"],
    },
  };
}

function buildLiveSnapshot(config) {
  const buffer = window.__BF_CAD_TOOLTIP_BUF__ || {};
  const sampleTime = latestTimestamp(buffer);
  const blast = {
    Q_blast: latestValue(buffer, "Q_blast"),
    O2_rate: latestValue(buffer, "O2_rate"),
    PCI_rate: latestValue(buffer, "PCI_rate"),
    sample_time: sampleTime,
    evidence: "measured",
  };
  const stockline = {
    L: latestValue(buffer, "L"),
    L_south: latestValue(buffer, "L_south"),
    L_north: latestValue(buffer, "L_north"),
    sample_time: sampleTime,
    evidence: "measured",
  };
  return {
    schema_version: "bf3d_snapshot.v1",
    furnace_id: config.furnace_id,
    mode: "live",
    render_time: new Date().toISOString(),
    knowledge_time: sampleTime,
    measured: {
      stockline,
      static_pressure: [],
      blast,
      active_tap: null,
    },
    estimated: {
      burden_state: null,
      cohesive_zone: null,
      hearth_inventory: null,
    },
    quality: {
      state: sampleTime ? "good" : "missing",
      missing: sampleTime ? [] : ["sensor_sample_time"],
      stale: [],
      bad: [],
      warnings: [],
    },
  };
}

function createController(viewer, config) {
  const scene = viewer.scene;
  const model = viewer.model;
  const host = viewer.renderer?.domElement?.parentElement;
  if (!scene || !model || !host) return null;
  delete viewer.__bf3dInternalSimulationDisposed;
  const modelBox = new THREE.Box3().setFromObject(model);
  const center = modelBox.getCenter(new THREE.Vector3());
  const root = new THREE.Group();
  root.name = "BF3D_INTERNAL_SIMULATION_RUNTIME";
  root.userData = {
    semantic_id: "BF3D_INTERNAL_SIMULATION_RUNTIME",
    asset_version: config.asset_version,
    coordinate_frame: config.coordinate_frame,
    evidence_level: "mixed",
  };
  scene.add(root);
  const burden = createBurdenSystem(config, center);
  const cohesive = createCohesiveSystem(config, center);
  const tuyere = createTuyereSystem(config, center);
  const pressure = createPressureSystem(config, center);
  const hearth = createHearthSystem(config, center);
  root.add(
    burden.group,
    cohesive.group,
    tuyere.group,
    pressure.fieldGroup,
    hearth.group,
  );
  scene.add(pressure.operationalGroup);
  const legacyObjects = [];
  model.traverse((object) => {
    const name = normalizeName(object.name);
    if (LEGACY_INTERNAL_PREFIXES.some((prefix) => name.startsWith(prefix))) {
      legacyObjects.push(object);
    }
  });
  const panelHost =
    host.closest(".furnace-stage-3d.cad-stage") || host.parentElement;
  const focusShell =
    panelHost?.closest(".furnace-wrap.furnace-layer-wrap") ||
    panelHost?.parentElement ||
    panelHost;
  const panel = createPanel(panelHost);
  const modeBadge = panel.querySelector(".bf3d-sim-mode");
  const detail = panel.querySelector(".bf3d-sim-detail");
  const modeButtons = {
    live: panel.querySelector('[data-sim-action="live"]'),
    illustrative: panel.querySelector(
      '[data-sim-action="illustrative"]',
    ),
    cohesivePreview: panel.querySelector(
      '[data-sim-action="cohesive-preview"]',
    ),
    chargingFocus: panel.querySelector(
      '[data-sim-action="charging-focus"]',
    ),
    pause: panel.querySelector('[data-sim-action="pause"]'),
  };
  let mode = "live";
  let playing = true;
  let backgroundPaused = document.hidden;
  let chargingFocus = false;
  let focusCameraPosition = null;
  let focusTarget = null;
  const focusVisibilityRecords = [];
  let disposed = false;
  const initialCachedSnapshot = cachedLiveSnapshot();
  let snapshot = initialCachedSnapshot || buildLiveSnapshot(config);
  let injectedSnapshot = initialCachedSnapshot;
  let lastFrame = performance.now();
  let animationFrame = 0;
  let lastLiveRead = 0;
  let lastUiWrite = 0;
  let lastDemoCharge = 0;
  let elapsedSeconds = 0;
  let eventSequence = 0;
  let pendingDemoCharge = null;
  const seenEventIds = new Set();
  const seenEventOrder = [];
  const eventGateState = {
    validated: 0,
    applied: 0,
    rejected: 0,
    duplicates: 0,
    lastReason: "等待事件",
  };
  let lastBurdenImpactCount = 0;
  let stockState = {
    evidence: "blocked",
    status: "主料线零点/方向门禁未确认",
    deformationVisible: false,
    targetY: worldY(32.8),
    craterDepth: 0.3,
    eccentricX: 0,
    eccentricZ: 0,
    descentMps: 0,
    quality: "blocked",
  };
  let cohesiveContract = {
    state: "not-evaluated",
    issues: [],
  };
  let lastSnapshotApplied = null;

  const freshness = (sampleTime) => {
    const millis = new Date(sampleTime || "").getTime();
    if (!Number.isFinite(millis)) return "no-data";
    const age = Math.max(0, Date.now() - millis);
    if (age > config.freshness.sensor_hard_expire_after_ms) return "no-data";
    if (age > config.freshness.sensor_warn_after_ms) return "stale";
    return "good";
  };

  const applySnapshot = (nextSnapshot) => {
    if (!nextSnapshot) return false;
    snapshot = nextSnapshot;
    lastSnapshotApplied = nextSnapshot;
    const isIllustrative = mode === "illustrative";
    const stock = nextSnapshot.measured?.stockline || {};
    const stockQuality = isIllustrative
      ? "illustrative"
      : freshness(stock.sample_time || nextSnapshot.knowledge_time);
    if (isIllustrative) {
      const estimated = nextSnapshot.estimated?.burden_state || {};
      stockState = {
        evidence: "illustrative",
        status: "中性径向分布；教学回放",
        deformationVisible: true,
        targetY: worldY(estimated.target_height_m ?? 32.8),
        craterDepth: estimated.crater_depth_m ?? 0.32,
        eccentricX: 0,
        eccentricZ: 0,
        descentMps: estimated.descent_mps ?? 0.035,
        quality: "illustrative",
      };
    } else if (!config.stockline_gate.enabled) {
      stockState = {
        evidence: "blocked",
        status: "主料线零点/方向门禁未确认",
        deformationVisible: false,
        targetY: burden.getState().currentY,
        craterDepth: 0.3,
        eccentricX: 0,
        eccentricZ: 0,
        descentMps: 0,
        quality: "blocked",
      };
    } else if (stockQuality === "good" || stockQuality === "stale") {
      const line = finite(stock.L);
      const [minLine, maxLine] = config.stockline_gate.valid_range_m || [
        null,
        null,
      ];
      const valid =
        line !== null &&
        Number.isFinite(minLine) &&
        Number.isFinite(maxLine) &&
        line >= minLine &&
        line <= maxLine;
      stockState = {
        evidence: stockQuality === "stale" ? "stale" : "measured",
        status: valid
          ? stockQuality === "stale"
            ? "冻结上一有效料面"
            : "主料线有限速率驱动"
          : "主料线越界，形变已隐藏",
        deformationVisible: valid,
        targetY: valid
          ? worldY(config.stockline_gate.zero_datum_m - line)
          : burden.getState().currentY,
        craterDepth: 0.3,
        eccentricX: 0,
        eccentricZ: 0,
        descentMps: finite(nextSnapshot.estimated?.burden_state?.descent_mps) || 0,
        quality: valid ? stockQuality : "no-data",
      };
    } else {
      stockState = {
        evidence: stockQuality,
        status:
          stockQuality === "stale"
            ? "数据陈旧，冻结料面"
            : "数据硬失联，料面形变已隐藏",
        deformationVisible: false,
        targetY: burden.getState().currentY,
        craterDepth: 0.3,
        eccentricX: 0,
        eccentricZ: 0,
        descentMps: 0,
        quality: stockQuality,
      };
    }
    const cohesiveEstimate =
      nextSnapshot.estimated?.cohesive_zone || null;
    const contractResult =
      isIllustrative || !cohesiveEstimate
        ? { valid: true, issues: [] }
        : validateLiveCohesiveEstimate(
            cohesiveEstimate,
            nextSnapshot.knowledge_time,
          );
    cohesiveContract = {
      state: !cohesiveEstimate
        ? "missing"
        : isIllustrative
          ? "illustrative-bypass"
          : contractResult.valid
            ? "valid"
            : "invalid",
      issues: [...contractResult.issues],
    };
    const cohesiveQuality = isIllustrative
      ? "illustrative"
      : freshness(
          cohesiveEstimate?.sample_time ||
            nextSnapshot.knowledge_time,
        );
    cohesive.setParameters(
      cohesiveEstimate &&
        contractResult.valid &&
        cohesiveQuality !== "no-data"
        ? {
            ...cohesiveEstimate,
            sample_time:
              cohesiveEstimate.sample_time ||
              nextSnapshot.knowledge_time ||
              null,
            runtime_freshness: cohesiveQuality,
          }
        : null,
    );
    const blast = nextSnapshot.measured?.blast || {};
    const blastQuality = isIllustrative
      ? "illustrative"
      : freshness(blast.sample_time || nextSnapshot.knowledge_time);
    tuyere.setTotals(
      ["good", "illustrative"].includes(blastQuality)
        ? {
            ...blast,
            evidence: isIllustrative ? "illustrative" : "measured",
          }
        : null,
    );
    pressure.setRows(nextSnapshot.measured?.static_pressure || [], {
      illustrative: isIllustrative,
    });
    hearth.setState(nextSnapshot.estimated?.hearth_inventory || null);
    return true;
  };

  const clearEventHistory = () => {
    seenEventIds.clear();
    seenEventOrder.length = 0;
    pendingDemoCharge = null;
  };
  const rememberEvent = (eventId) => {
    seenEventIds.add(eventId);
    seenEventOrder.push(eventId);
    if (seenEventOrder.length > 256) {
      const oldest = seenEventOrder.shift();
      seenEventIds.delete(oldest);
    }
  };
  const validateEvent = (event) => {
    if (!event || event.schema_version !== "bf3d_event.v1") {
      return "事件版本缺失或不受支持";
    }
    if (event.furnace_id !== config.furnace_id) {
      return "高炉编号不匹配";
    }
    if (
      typeof event.event_id !== "string" ||
      event.event_id.trim().length < 3
    ) {
      return "事件编号缺失";
    }
    if (seenEventIds.has(event.event_id)) return "duplicate";
    if (!Number.isFinite(new Date(event.event_time || "").getTime())) {
      return "事件时间无效";
    }
    const allowedEvidence =
      mode === "illustrative"
        ? event.evidence === "illustrative"
        : event.evidence === "measured";
    if (!allowedEvidence) return "事件证据等级与当前模式不匹配";
    if (
      ![
        "BURDEN_CHARGE_STARTED",
        "BURDEN_CHARGE_COMPLETED",
        "TAP_OPENED",
        "TAP_CLOSED",
      ].includes(event.type)
    ) {
      return "事件类型不受支持";
    }
    if (event.type.startsWith("BURDEN_CHARGE_")) {
      if (!["ore", "coke"].includes(event.burden_type)) {
        return "炉料类型无效";
      }
      const massBalanceRequired =
        mode !== "live" ||
        config.burden_fx.live_motion_gate.require_mass_balance !==
          false;
      if (massBalanceRequired && event.mass_balance_valid !== true) {
        return "质量平衡门禁未通过";
      }
      if (
        mode === "live" &&
        config.burden_fx.live_motion_gate.enabled !== true
      ) {
        return "数据态上料事件/溜槽程序门禁未通过";
      }
    }
    return null;
  };
  const dispatchEvent = (event) => {
    const rejection = validateEvent(event);
    if (rejection) {
      eventGateState.rejected += 1;
      if (rejection === "duplicate") eventGateState.duplicates += 1;
      eventGateState.lastReason =
        rejection === "duplicate" ? "重复事件已忽略" : rejection;
      return false;
    }
    rememberEvent(event.event_id);
    eventGateState.validated += 1;
    const burdenAccepted = burden.addCharge(event);
    const hearthAccepted = hearth.dispatchEvent(event);
    const applied = burdenAccepted || hearthAccepted;
    if (applied) {
      eventGateState.applied += 1;
      eventGateState.lastReason = "事件已应用";
    } else {
      eventGateState.rejected += 1;
      eventGateState.lastReason =
        event.type === "BURDEN_CHARGE_STARTED"
          ? burden.getState().delivery.lastGateReason
          : "事件未被任何工艺对象接受";
    }
    return applied;
  };

  const setChargingFocus = (enabled) => {
    const next = Boolean(enabled) && mode === "illustrative";
    if (next === chargingFocus) return chargingFocus;
    chargingFocus = next;
    if (chargingFocus) {
      focusCameraPosition = viewer.camera?.position?.clone?.() || null;
      focusTarget = viewer.controls?.target?.clone?.() || null;
      focusVisibilityRecords.length = 0;
      const focusObjects = [
        ...(viewer.sensorObjects || []),
        ...(viewer.hitObjects || []),
        pressure.operationalGroup,
        pressure.fieldGroup,
        tuyere.group,
        hearth.group,
        scene.getObjectByName("GL02_CUTAWAY_PROFILE_EDGES"),
        model.getObjectByName("APPROX_GL02_cooling_bands_and_seams"),
        model.getObjectByName("APPROX_GL02_shell_stiffener_rings"),
        model.getObjectByName("APPROX_GL02_FURNACE_SHAFT"),
        model.getObjectByName("APPROX_GL02_FURNACE_THROAT"),
        model.getObjectByName("APPROX_GL02_bell_less_top_and_bleeders"),
      ];
      [...new Set(focusObjects.filter(Boolean))].forEach((object) => {
        focusVisibilityRecords.push({
          object,
          visible: object.visible,
        });
        object.visible = false;
      });
      if (viewer.camera && viewer.controls?.target) {
        const focusDirection = focusCameraPosition
          .clone()
          .sub(new THREE.Vector3(center.x, focusCameraPosition.y, center.z));
        focusDirection.y = 0;
        if (focusDirection.lengthSq() < 1e-6) {
          focusDirection.set(0.44, 0, 0.9);
        } else {
          focusDirection.normalize();
        }
        viewer.controls.target.set(center.x, 13.6, center.z);
        viewer.camera.position.set(
          center.x + focusDirection.x * 12.8,
          18.4,
          center.z + focusDirection.z * 12.8,
        );
        viewer.controls.update?.();
      }
      panelHost?.classList.add("bf3d-charging-focus");
      focusShell?.classList.add("bf3d-charging-focus");
      requestAnimationFrame(() => {
        window.dispatchEvent(new Event("resize"));
      });
    } else {
      focusVisibilityRecords.forEach(({ object, visible }) => {
        if (object) object.visible = visible;
      });
      focusVisibilityRecords.length = 0;
      if (focusCameraPosition && viewer.camera) {
        viewer.camera.position.copy(focusCameraPosition);
      }
      if (focusTarget && viewer.controls?.target) {
        viewer.controls.target.copy(focusTarget);
        viewer.controls.update?.();
      }
      focusCameraPosition = null;
      focusTarget = null;
      panelHost?.classList.remove("bf3d-charging-focus");
      focusShell?.classList.remove("bf3d-charging-focus");
      requestAnimationFrame(() => {
        window.dispatchEvent(new Event("resize"));
      });
    }
    panel.dataset.chargingFocus = String(chargingFocus);
    host.dataset.burdenChargingFocus = String(chargingFocus);
    return chargingFocus;
  };

  const setMode = (nextMode) => {
    setChargingFocus(false);
    mode = nextMode === "illustrative" ? "illustrative" : "live";
    clearEventHistory();
    eventSequence = 0;
    if (mode === "illustrative") {
      injectedSnapshot = null;
      burden.reset();
      cohesive.setWhatIfEnabled(config.burden_fx.what_if_default_enabled);
      snapshot = createDemoSnapshot(config);
      applySnapshot(snapshot);
      dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "DEMO-CHARGE-ORE-001",
        event_time: snapshot.render_time,
        type: "BURDEN_CHARGE_COMPLETED",
        furnace_id: config.furnace_id,
        burden_type: "ore",
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: false,
      });
      dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "DEMO-CHARGE-COKE-001",
        event_time: snapshot.render_time,
        type: "BURDEN_CHARGE_COMPLETED",
        furnace_id: config.furnace_id,
        burden_type: "coke",
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: false,
      });
      lastDemoCharge =
        performance.now() -
        config.illustrative_scenario.charge_interval_ms +
        1500;
    } else {
      burden.reset();
      cohesive.reset();
      pressure.reset();
      hearth.reset();
      tuyere.reset();
      injectedSnapshot = cachedLiveSnapshot();
      snapshot = injectedSnapshot || buildLiveSnapshot(config);
      applySnapshot(snapshot);
    }
    playing = true;
    syncUi(true);
    return mode;
  };

  const injectSnapshot = (nextSnapshot) => {
    injectedSnapshot = nextSnapshot;
    const nextMode =
      nextSnapshot?.mode === "illustrative" ? "illustrative" : "live";
    if (nextMode !== mode) {
      setChargingFocus(false);
      clearEventHistory();
      burden.reset();
      cohesive.reset();
      pressure.reset();
      hearth.reset();
      tuyere.reset();
      lastBurdenImpactCount = 0;
    }
    mode = nextMode;
    applySnapshot(nextSnapshot);
    syncUi(true);
    return true;
  };

  const reset = () => {
    burden.reset();
    cohesive.reset();
    pressure.reset();
    hearth.reset();
    tuyere.reset();
    eventSequence = 0;
    lastBurdenImpactCount = 0;
    elapsedSeconds = 0;
    return setMode(mode);
  };

  const objectUiState = () => {
    const burdenState = burden.getState();
    const deliveryState = burdenState.delivery;
    const cohesiveState = cohesive.getState();
    const tuyereState = tuyere.getState();
    const pressureState = pressure.getState();
    const hearthState = hearth.getState();
    const directionLabel = {
      up: "↑上移",
      down: "↓下移",
      stable: "→稳定",
      unknown: "趋势未知",
    }[cohesiveState.movement.direction] || "趋势未知";
    const confidenceLabel =
      cohesiveState.confidence === null
        ? "置信度待定"
        : `置信度 ${(cohesiveState.confidence * 100).toFixed(0)}%`;
    const liveSafetyLabels =
      mode === "live"
        ? [
            String(cohesiveState.calibrationStatus || "")
              .toLowerCase()
              .includes("uncalibrated")
              ? "未标定估计"
              : null,
            String(cohesiveState.controlUse || "")
              .toLowerCase()
              .includes("prohibited")
              ? "禁止控制"
              : null,
          ].filter(Boolean)
        : [];
    const liveSafetyPrefix = liveSafetyLabels.length
      ? `${liveSafetyLabels.join(" · ")} · `
      : "";
    return {
      stock: {
        evidence: stockState.evidence,
        text:
          mode === "illustrative"
            ? `${burden.getState().visibleLayerCount} 层 · 中性径向分布`
            : stockState.status,
      },
      charging: {
        evidence:
          deliveryState.active || deliveryState.visible
            ? deliveryState.evidence
            : "blocked",
        text: deliveryState.active
          ? `${deliveryState.burdenType === "coke" ? "焦批" : "矿批"} · ${deliveryState.phase} · ${deliveryState.particles.activeOre + deliveryState.particles.activeCoke} 粒`
          : mode === "illustrative"
            ? `教学待机 · ${deliveryState.quality.current}档`
            : "真实溜槽参数门禁未通过，运动隐藏",
      },
      cohesive: {
        evidence:
          cohesiveContract.state === "invalid"
            ? "blocked"
            : cohesiveState.visible
          ? cohesiveState.freshness === "stale"
            ? "stale"
            : mode === "illustrative"
            ? "illustrative"
            : cohesiveState.evidence
          : "no-data",
        text:
          cohesiveContract.state === "invalid"
            ? "C2 输出合同无效，几何已隐藏"
            : cohesiveState.visible
          ? `${mode === "illustrative" ? "教学估计 · " : ""}${liveSafetyPrefix}${directionLabel} · 根部 ${cohesiveState.rootHeight.toFixed(2)}m · 厚度 ${cohesiveState.thickness.toFixed(2)}m · ${confidenceLabel}`
          : "无可靠 C2/C3 输出，已隐藏",
      },
      tuyere: {
        evidence: tuyereState.evidence,
        text: tuyereState.intensity
          ? `26 个统一响应 · ${tuyereState.activePointsPerTuyere} 点/风口`
          : "总风/氧/煤数据不可用",
      },
      pressure: {
        evidence:
          pressureState.visiblePointCount > 0
            ? pressureState.evidence
            : "no-data",
        text: pressureState.visiblePointCount
          ? `${pressureState.visiblePointCount}/18 点${
              pressureState.evidence === "illustrative"
                ? "教学示意"
                : pressureState.visibleStaleCount
                  ? `可见（${pressureState.visibleStaleCount} 点陈旧冻结）`
                  : "实测"
            } · ${
              pressureState.interpolatedBandCount
                ? `${pressureState.interpolatedBandCount}/3 层有界插值`
                : "无合格基线偏差，不生成色带"
            }`
          : "0/18 点可见 · 当前快照无有效静压力",
      },
      hearth: {
        evidence: hearthState.liquidVisible
          ? hearthState.evidence
          : "no-data",
        text: hearthState.liquidVisible
          ? `铁渣分层 · 铁口${hearthState.tapActive ? "开启" : "关闭"}`
          : "无液位/滴落估计，已隐藏",
      },
    };
  };

  function syncUi(force = false) {
    const now = performance.now();
    if (!force && now - lastUiWrite < 180) return;
    lastUiWrite = now;
    modeBadge.dataset.mode = mode;
    modeBadge.textContent = mode === "illustrative" ? "教学回放" : "数据态";
    modeButtons.live.classList.toggle("active", mode === "live");
    modeButtons.illustrative.classList.toggle(
      "active",
      mode === "illustrative",
    );
    modeButtons.pause.classList.toggle("active", !playing);
    modeButtons.pause.textContent = playing ? "暂停" : "继续";
    const cohesiveState = cohesive.getState();
    modeButtons.cohesivePreview.classList.toggle(
      "active",
      cohesiveState.whatIf.enabled,
    );
    modeButtons.cohesivePreview.disabled = mode !== "illustrative";
    modeButtons.cohesivePreview.title =
      mode === "illustrative"
        ? "仅教学演示；非本批次实时因果结果"
        : "数据态禁止启用无实测依据的软熔带响应";
    modeButtons.chargingFocus.classList.toggle(
      "active",
      chargingFocus,
    );
    modeButtons.chargingFocus.disabled = mode !== "illustrative";
    modeButtons.chargingFocus.textContent = chargingFocus
      ? "退出聚焦"
      : "布料聚焦";
    modeButtons.chargingFocus.title =
      mode === "illustrative"
        ? "临时隐藏传感器与辅助标注并聚焦炉顶；退出后完整恢复"
        : "只允许在教学演示中使用";
    const ui = objectUiState();
    Object.entries(ui).forEach(([id, item]) => {
      const row = panel.querySelector(`[data-object="${id}"]`);
      if (!row) return;
      row.dataset.state = item.evidence;
      row.querySelector(".bf3d-sim-object-status").textContent = item.text;
      row.querySelector(".bf3d-sim-evidence").textContent =
        EVIDENCE_LABELS[item.evidence] || item.evidence;
    });
    const deliveryState = burden.getState().delivery;
    host.dataset.burdenChargingMode = mode;
    host.dataset.burdenChargingPhase = deliveryState.phase;
    host.dataset.burdenChargingEvidence = deliveryState.evidence;
    host.dataset.burdenChargingQuality =
      deliveryState.quality.current;
    host.dataset.cohesiveWhatIf = String(
      cohesiveState.whatIf.enabled,
    );
    host.dataset.cohesiveVisible = String(cohesiveState.visible);
    host.dataset.cohesiveEvidence = cohesiveState.evidence;
    host.dataset.cohesiveDirection =
      cohesiveState.movement.direction;
    host.dataset.cohesiveVelocityMPerH =
      cohesiveState.movement.velocity_m_per_h === null
        ? ""
        : cohesiveState.movement.velocity_m_per_h.toFixed(3);
    host.dataset.cohesiveRootHeightM =
      cohesiveState.rootHeight.toFixed(3);
    host.dataset.cohesiveThicknessM =
      cohesiveState.thickness.toFixed(3);
    host.dataset.cohesiveEccentricityM =
      cohesiveState.eccentricity.toFixed(3);
    host.dataset.cohesiveConfidence =
      cohesiveState.confidence === null
        ? ""
        : cohesiveState.confidence.toFixed(3);
    host.dataset.cohesiveInputCoverage =
      cohesiveState.inputCoverage === null
        ? ""
        : cohesiveState.inputCoverage.toFixed(3);
    host.dataset.cohesiveCalibrationStatus =
      cohesiveState.calibrationStatus || "";
    host.dataset.cohesiveControlUse =
      cohesiveState.controlUse || "";
    host.dataset.cohesiveRootDefinition =
      cohesiveState.rootDefinition || "";
    host.dataset.cohesiveAzimuthReference =
      cohesiveState.azimuthReference || "";
    host.dataset.cohesiveAbsoluteAzimuthStatus =
      cohesiveState.absoluteAzimuthStatus || "";
    host.dataset.cohesiveSampleTime =
      cohesiveState.sampleTime || "";
    host.dataset.cohesiveQuality =
      cohesiveState.quality?.state || "no-data";
    host.dataset.cohesiveFreshness =
      cohesiveState.freshness || "no-data";
    host.dataset.cohesiveModelVersion =
      cohesiveState.modelVersion || "";
    host.dataset.cohesiveContractState = cohesiveContract.state;
    host.dataset.cohesiveContractIssues =
      cohesiveContract.issues.join(",");
    const cutawayMode = viewer.getCutawayState?.().mode || "exterior";
      detail.textContent =
      cutawayMode !== "cutaway"
        ? "外观模式：内部对象已冻结并隐藏。打开“内切面”后显示。"
        : mode === "illustrative"
          ? `教学回放 · ${config.illustrative_scenario.scenario_version} · 固定随机种子 ${config.illustrative_scenario.random_seed}；不代表 GL02 当前状态。`
          : `数据态 · ${config.asset_version} · 料线门禁 ${config.stockline_gate.enabled ? "已启用" : "未通过"}；无可靠输入的对象保持隐藏。`;
  }

  panel.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-sim-action]");
    if (!button) return;
    const action = button.dataset.simAction;
    if (action === "live") setMode("live");
    if (action === "illustrative") setMode("illustrative");
    if (action === "pause") {
      playing = !playing;
      syncUi(true);
    }
    if (action === "cohesive-preview" && mode === "illustrative") {
      const enabled = !cohesive.getState().whatIf.enabled;
      cohesive.setWhatIfEnabled(enabled);
      if (enabled) cohesive.triggerWhatIf();
      syncUi(true);
    }
    if (action === "charging-focus" && mode === "illustrative") {
      setChargingFocus(!chargingFocus);
      syncUi(true);
    }
    if (action === "reset") reset();
  });
  const onSnapshotEvent = (event) => {
    if (event?.detail) injectSnapshot(event.detail);
  };
  const onProcessEvent = (event) => {
    if (event?.detail) dispatchEvent(event.detail);
  };
  const onVisibilityChange = () => {
    backgroundPaused = document.hidden;
    if (!backgroundPaused) lastFrame = performance.now();
  };
  window.addEventListener("bf3d:snapshot", onSnapshotEvent);
  window.addEventListener("bf3d:event", onProcessEvent);
  document.addEventListener("visibilitychange", onVisibilityChange);

  const getState = () => {
    const cutawayMode = viewer.getCutawayState?.().mode || "exterior";
    return {
      schemaVersion: "bf3d_internal_simulation_state.v1",
      ready: !disposed,
      mode,
      playing,
      backgroundPaused,
      chargingFocus,
      cutawayMode,
      visible: root.visible,
      configSource: config.__source,
      configVersion: config.schema_version,
      assetVersion: config.asset_version,
      coordinateFrame: config.coordinate_frame,
      stocklineGate: { ...config.stockline_gate },
      freshness: { ...config.freshness },
      snapshotMode: snapshot?.mode || null,
      knowledgeTime: snapshot?.knowledge_time || null,
      eventGate: {
        ...eventGateState,
        seenCount: seenEventIds.size,
        maxRemembered: 256,
      },
      stock: { ...stockState, ...burden.getState() },
      cohesive: {
        ...cohesive.getState(),
        contract: {
          state: cohesiveContract.state,
          issues: [...cohesiveContract.issues],
        },
      },
      tuyere: tuyere.getState(),
      pressure: pressure.getState(),
      hearth: hearth.getState(),
      resources: {
        rootChildren: root.children.length,
        legacyDecorativeCount: legacyObjects.length,
        legacyDecorativeVisibleCount: legacyObjects.filter(
          (object) => object.visible,
        ).length,
        burdenLayerPool: burden.layers.length,
        burdenSurfaceParticleCount:
          burden.getState().surfaceParticleCount,
        burdenDeliveryParticleCapacity:
          burden.getState().delivery.particles.ore.capacity +
          burden.getState().delivery.particles.coke.capacity,
        burdenDeliveryDustCapacity:
          burden.getState().delivery.dust.capacity,
        tuyereInstances: tuyere.getState().racewayInstanceCount,
        pciPointCapacity: tuyere.getState().particleCapacity,
        pressureMarkers: pressure.markers.length,
        pressureBands: pressure.bands.length,
        dropletPointCount: hearth.getState().dropletCount,
      },
      truthBoundary: {
        noSouthNorthTiltBeforeGate: true,
        noRandomCohesiveShape: true,
        noPerTuyereDifferenceFromTotals: true,
        noPressureAsRealGasStreamline: true,
        noChemistryPoolColoring: true,
        noFlowWidthWithoutInstantaneousFlow: true,
        noMeasuredBurdenMotionWithoutChuteProgram: true,
        noDemOrRealParticleSizeClaim: true,
        schemaFurnaceModeAndIdempotencyGate: true,
        startedAndCompletedEventsSeparated: true,
      },
    };
  };

  const tick = (now) => {
    if (
      disposed ||
      window.__BF_CAD_FURNACE_VIEWER !== viewer ||
      !host.isConnected
    ) {
      dispose();
      return;
    }
    animationFrame = requestAnimationFrame(tick);
    if (backgroundPaused) {
      syncUi();
      return;
    }
    const deltaSeconds = clamp((now - lastFrame) / 1000, 0, 0.1);
    lastFrame = now;
    const cutawayMode = viewer.getCutawayState?.().mode || "exterior";
    root.visible = cutawayMode === "cutaway";
    const materialReviewActive =
      document.body?.dataset?.reviewMode === "material";
    pressure.operationalGroup.visible =
      !materialReviewActive && !chargingFocus;
    pressure.fieldGroup.visible = !materialReviewActive && !chargingFocus;
    panel.hidden = false;
    legacyObjects.forEach((object) => {
      object.visible = false;
    });
    if (mode === "live" && now - lastLiveRead >= 1000) {
      lastLiveRead = now;
      const cached = cachedLiveSnapshot();
      if (
        cached &&
        (!injectedSnapshot ||
          snapshotMillis(cached) >= snapshotMillis(injectedSnapshot))
      ) {
        injectedSnapshot = cached;
      }
      applySnapshot(
        injectedSnapshot || cached || buildLiveSnapshot(config),
      );
    }
    if (
      mode === "illustrative" &&
      playing &&
      root.visible &&
      !pendingDemoCharge &&
      now - lastDemoCharge >=
        config.illustrative_scenario.charge_interval_ms
    ) {
      lastDemoCharge = now;
      const burdenType = eventSequence % 2 === 0 ? "ore" : "coke";
      eventSequence += 1;
      const correlationId = `DEMO-CHARGE-${String(
        eventSequence,
      ).padStart(3, "0")}`;
      const started = dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: `${correlationId}-START`,
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_STARTED",
        furnace_id: config.furnace_id,
        burden_type: burdenType,
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: true,
        correlation_id: correlationId,
      });
      if (started) {
        pendingDemoCharge = {
          correlationId,
          burdenType,
          remainingMs:
            config.burden_fx.cycle_duration_ms *
            config.burden_fx.settle_end_ratio,
        };
      }
    }
    if (playing && root.visible && pendingDemoCharge) {
      pendingDemoCharge.remainingMs -= deltaSeconds * 1000;
      if (pendingDemoCharge.remainingMs <= 0) {
        const completed = pendingDemoCharge;
        pendingDemoCharge = null;
        dispatchEvent({
          schema_version: "bf3d_event.v1",
          event_id: `${completed.correlationId}-COMPLETE`,
          event_time: new Date().toISOString(),
          type: "BURDEN_CHARGE_COMPLETED",
          furnace_id: config.furnace_id,
          burden_type: completed.burdenType,
          evidence: "illustrative",
          mass_balance_valid: true,
          visualize_motion: false,
          correlation_id: completed.correlationId,
        });
      }
    }
    if (playing && root.visible) elapsedSeconds += deltaSeconds;
    if (playing && root.visible) {
      burden.update(deltaSeconds, stockState);
      const burdenImpactCount = burden.getState().delivery.impactCount;
      if (
        mode === "illustrative" &&
        burdenImpactCount > lastBurdenImpactCount &&
        cohesive.getState().whatIf.enabled
      ) {
        cohesive.triggerWhatIf();
      }
      lastBurdenImpactCount = burdenImpactCount;
      cohesive.update(deltaSeconds);
      tuyere.update(elapsedSeconds);
      hearth.update(elapsedSeconds);
    }
    syncUi();
  };

  function dispose() {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(animationFrame);
    panel.__bfDispose?.();
    setChargingFocus(false);
    window.removeEventListener("bf3d:snapshot", onSnapshotEvent);
    window.removeEventListener("bf3d:event", onProcessEvent);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    panel.remove();
    scene.remove(root);
    scene.remove(pressure.operationalGroup);
    disposeObject(root);
    disposeObject(pressure.operationalGroup);
    delete host.dataset.burdenChargingMode;
    delete host.dataset.burdenChargingPhase;
    delete host.dataset.burdenChargingEvidence;
    delete host.dataset.burdenChargingQuality;
    delete host.dataset.cohesiveWhatIf;
    delete host.dataset.cohesiveVisible;
    delete host.dataset.cohesiveEvidence;
    delete host.dataset.cohesiveDirection;
    delete host.dataset.cohesiveVelocityMPerH;
    delete host.dataset.cohesiveRootHeightM;
    delete host.dataset.cohesiveThicknessM;
    delete host.dataset.cohesiveEccentricityM;
    delete host.dataset.cohesiveConfidence;
    delete host.dataset.cohesiveInputCoverage;
    delete host.dataset.cohesiveCalibrationStatus;
    delete host.dataset.cohesiveControlUse;
    delete host.dataset.cohesiveRootDefinition;
    delete host.dataset.cohesiveAzimuthReference;
    delete host.dataset.cohesiveAbsoluteAzimuthStatus;
    delete host.dataset.cohesiveSampleTime;
    delete host.dataset.cohesiveQuality;
    delete host.dataset.cohesiveFreshness;
    delete host.dataset.cohesiveModelVersion;
    delete host.dataset.cohesiveContractState;
    delete host.dataset.cohesiveContractIssues;
    delete host.dataset.burdenChargingFocus;
    if (window.__BF3D_INTERNAL_SIMULATION__?.viewer === viewer) {
      delete window.__BF3D_INTERNAL_SIMULATION__;
    }
    if (viewer.__bf3dInternalSimulation === api) {
      delete viewer.getInternalSimulationState;
      delete viewer.setInternalSimulationMode;
      delete viewer.injectInternalSimulationSnapshot;
      delete viewer.dispatchInternalSimulationEvent;
      delete viewer.setIllustrativeCohesiveWhatIf;
      delete viewer.__bf3dInternalSimulation;
    }
    viewer.__bf3dInternalSimulationDisposed = true;
  }

  const api = {
    viewer,
    config,
    setMode,
    injectSnapshot,
    dispatchEvent,
    play: () => {
      playing = true;
      syncUi(true);
      return true;
    },
    pause: () => {
      playing = false;
      syncUi(true);
      return true;
    },
    reset,
    setCohesiveWhatIf: (enabled) => {
      if (mode !== "illustrative") return false;
      const result = cohesive.setWhatIfEnabled(enabled);
      if (result) cohesive.triggerWhatIf();
      syncUi(true);
      return result;
    },
    setChargingFocus: (enabled) => {
      const result = setChargingFocus(enabled);
      syncUi(true);
      return result;
    },
    triggerIllustrativeCohesiveResponse: () => {
      if (mode !== "illustrative") return false;
      return cohesive.triggerWhatIf();
    },
    getState,
    dispose,
    makeIllustrativeSnapshot: () => createDemoSnapshot(config),
    getLastSnapshot: () => lastSnapshotApplied,
    inputEvents: {
      snapshot: "bf3d:snapshot",
      processEvent: "bf3d:event",
    },
  };
  viewer.getInternalSimulationState = getState;
  viewer.setInternalSimulationMode = setMode;
  viewer.injectInternalSimulationSnapshot = injectSnapshot;
  viewer.dispatchInternalSimulationEvent = dispatchEvent;
  viewer.setIllustrativeCohesiveWhatIf = api.setCohesiveWhatIf;
  viewer.__bf3dInternalSimulation = api;
  window.__BF3D_INTERNAL_SIMULATION__ = api;
  applySnapshot(snapshot);
  syncUi(true);
  animationFrame = requestAnimationFrame(tick);
  return api;
}

const config = await loadConfig();
let activeViewer = null;
let activeController = null;
const mountTimer = window.setInterval(() => {
  const viewer = window.__BF_CAD_FURNACE_VIEWER;
  if (
    !viewer ||
    !viewer.scene ||
    !viewer.model ||
    !viewer.renderer ||
    !viewer.renderer.domElement?.isConnected
  ) {
    return;
  }
  if (
    viewer === activeViewer &&
    activeController?.getState?.().ready === true
  ) {
    return;
  }
  activeController?.dispose?.();
  activeViewer = viewer;
  activeController = createController(viewer, config);
}, 120);

window.addEventListener(
  "beforeunload",
  () => {
    window.clearInterval(mountTimer);
    activeController?.dispose?.();
  },
  { once: true },
);
