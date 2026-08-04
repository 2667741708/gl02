#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");

const PLAYWRIGHT_PATH =
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright";
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require(PLAYWRIGHT_PATH);
}

const ROOT = path.resolve(__dirname, "..");
const FRONTEND_ROOT = path.join(ROOT, "高炉前端数据");
const CONTROLLER_PATH = path.join(
  FRONTEND_ROOT,
  "assets",
  "bf3d-structural-review.js",
);
const PRODUCTION_HTML_PATH = path.join(
  FRONTEND_ROOT,
  "frontend_dashboard_v3.server.html",
);
const FORMAL_GLB_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  "gl02_blast_furnace.glb",
);
const R2R_ROOT = path.join(
  ROOT,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE",
);
const R2R_CONTRACT_PATH = path.join(R2R_ROOT, "capture_contract.json");
const R2R_MANIFEST_PATH = path.join(R2R_ROOT, "capture_manifest.json");
const R2S_ROOT = path.join(
  ROOT,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT",
);
const INPUT_LOCK_PATH = path.join(R2S_ROOT, "input_lock.json");
const IMPLEMENTATION_DELTA_PATH = path.join(
  R2S_ROOT,
  "implementation_delta_manifest.json",
);
const COLOR_DECISION_PATH = path.join(
  R2S_ROOT,
  "color_management_decision.json",
);
const PHOTOMETRIC_DECISION_PATH = path.join(
  R2S_ROOT,
  "photometric_mapping_decision.json",
);
const PIPELINE_STATUS_PATH = path.join(
  R2S_ROOT,
  "pipeline_status.json",
);
const GATE_QUERY_NAME = "bf3d_test_capture";
const GATE_VALUE = "WEB-60_R2S";
const WINDOW_TOKEN_NAME = "__BF3D_TEST_CAPTURE_TOKEN__";
const REQUIREMENT_ID =
  "REQ-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720";
const EXPECTED_INPUT_LOCK_BYTES = 9132;
const EXPECTED_INPUT_LOCK_SHA256 =
  "3dc8caf07dd328d1ea69535cfc6fac61e504a1dc8b9351f7ad816ce8e0dd27d9";
const EXPECTED_R2R_CONTRACT_BYTES = 6836;
const EXPECTED_R2R_CONTRACT_SHA256 =
  "7c47ddf9d0b6867afd360f6d7e47da9303b9f1b2576f262686f642e3679303e4";
const EXPECTED_R2R_MANIFEST_BYTES = 352847;
const EXPECTED_R2R_MANIFEST_SHA256 =
  "c1afc04c4fd0ce3023aeaf0626b9b0fe21dc523183990f8b7c27a734e517972b";
const EXPECTED_CONTROLLER_POST_BYTES = 66839;
const EXPECTED_CONTROLLER_POST_SHA256 =
  "d99b6d8fc419d2c0d61f713af2343fe15b212f2c89f6f905ca27555dcb90b206";
const FORMAL_GLB_BYTES = 4314736;
const FORMAL_GLB_SHA256 =
  "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6";
const FROZEN_SECTION_BOUNDS = Object.freeze({
  minimum: Object.freeze([
    -4.460000038146973,
    -4.450119495391846,
    -20.0,
  ]),
  maximum: Object.freeze([
    -0.28433388471603394,
    4.450119495391846,
    20.0,
  ]),
});
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".png": "image/png",
  ".webp": "image/webp",
};

function assert(condition, message, detail = null) {
  if (!condition) {
    throw new Error(`${message}: ${JSON.stringify(detail)}`);
  }
}

function assertDeepEqual(actual, expected, message) {
  assert(
    JSON.stringify(actual) === JSON.stringify(expected),
    message,
    { actual, expected },
  );
}

function assertNear(actual, expected, epsilon, message) {
  assert(
    Number.isFinite(actual) &&
      Number.isFinite(expected) &&
      Math.abs(actual - expected) <= epsilon,
    message,
    { actual, expected, epsilon },
  );
}

function assertVectorNear(actual, expected, epsilon, message) {
  assert(
    Array.isArray(actual) &&
      Array.isArray(expected) &&
      actual.length === expected.length,
    `${message} shape`,
    { actual, expected },
  );
  actual.forEach((value, index) =>
    assertNear(
      Number(value),
      Number(expected[index]),
      epsilon,
      `${message}[${index}]`,
    ),
  );
}

function assertExactKeys(actual, expected, message) {
  assert(
    actual && typeof actual === "object" && !Array.isArray(actual),
    `${message} object`,
    actual,
  );
  assertDeepEqual(
    Object.keys(actual).sort(),
    expected.slice().sort(),
    `${message} keys`,
  );
}

function collectDifferencePaths(
  actual,
  expected,
  limit = 40,
  currentPath = "$",
  output = [],
) {
  if (output.length >= limit) return output;
  if (Object.is(actual, expected)) return output;
  if (
    actual === null ||
    expected === null ||
    typeof actual !== "object" ||
    typeof expected !== "object"
  ) {
    output.push({ path: currentPath, actual, expected });
    return output;
  }
  const actualKeys = Object.keys(actual);
  const expectedKeys = Object.keys(expected);
  const keys = Array.from(
    new Set([...actualKeys, ...expectedKeys]),
  ).sort();
  for (const key of keys) {
    if (output.length >= limit) break;
    if (
      !Object.prototype.hasOwnProperty.call(actual, key) ||
      !Object.prototype.hasOwnProperty.call(expected, key)
    ) {
      output.push({
        path: `${currentPath}.${key}`,
        actual: actual[key],
        expected: expected[key],
      });
      continue;
    }
    collectDifferencePaths(
      actual[key],
      expected[key],
      limit,
      `${currentPath}.${key}`,
      output,
    );
  }
  return output;
}

function assertArrayNear(actual, expected, epsilon, message) {
  assert(
    Array.isArray(actual) &&
      Array.isArray(expected) &&
      actual.length === expected.length,
    `${message} shape`,
    {
      actualLength: Array.isArray(actual) ? actual.length : null,
      expectedLength: Array.isArray(expected) ? expected.length : null,
    },
  );
  actual.forEach((value, index) =>
    assertNear(
      Number(value),
      Number(expected[index]),
      epsilon,
      `${message}[${index}]`,
    ),
  );
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function fileFingerprint(filePath) {
  const stat = fs.statSync(filePath);
  return {
    bytes: stat.size,
    sha256: sha256(filePath),
  };
}

function sha256(filePath) {
  return crypto
    .createHash("sha256")
    .update(fs.readFileSync(filePath))
    .digest("hex");
}

function normalizeLockedPath(relativePath) {
  const normalized = String(relativePath).replace(/[\\/]+/g, path.sep);
  const absolute = path.resolve(ROOT, normalized);
  assert(
    absolute === ROOT || absolute.startsWith(ROOT + path.sep),
    "locked path must stay inside the workspace",
    { relativePath, absolute },
  );
  return absolute;
}

function blenderToThree(vector) {
  const mappedZ = -Number(vector[1]);
  return [
    Number(vector[0]),
    Number(vector[2]),
    Object.is(mappedZ, -0) ? 0 : mappedZ,
  ];
}

function vectorAdd(a, b) {
  return a.map((value, index) => Number(value) + Number(b[index]));
}

function vectorSubtract(a, b) {
  return a.map((value, index) => Number(value) - Number(b[index]));
}

function vectorScale(vector, scale) {
  return vector.map((value) => Number(value) * Number(scale));
}

function vectorDot(a, b) {
  return a.reduce(
    (sum, value, index) => sum + Number(value) * Number(b[index]),
    0,
  );
}

function vectorCross(a, b) {
  return [
    Number(a[1]) * Number(b[2]) - Number(a[2]) * Number(b[1]),
    Number(a[2]) * Number(b[0]) - Number(a[0]) * Number(b[2]),
    Number(a[0]) * Number(b[1]) - Number(a[1]) * Number(b[0]),
  ];
}

function vectorNormalize(vector, message) {
  const length = Math.hypot(...vector.map(Number));
  assert(length > 1e-12, `${message} non-zero length`, {
    vector,
    length,
  });
  return vectorScale(vector, 1 / length);
}

function matrixTranspose3(matrix) {
  return [
    [matrix[0][0], matrix[1][0], matrix[2][0]],
    [matrix[0][1], matrix[1][1], matrix[2][1]],
    [matrix[0][2], matrix[1][2], matrix[2][2]],
  ];
}

function quaternionFromRotationMatrix(matrix) {
  const m00 = matrix[0][0];
  const m01 = matrix[0][1];
  const m02 = matrix[0][2];
  const m10 = matrix[1][0];
  const m11 = matrix[1][1];
  const m12 = matrix[1][2];
  const m20 = matrix[2][0];
  const m21 = matrix[2][1];
  const m22 = matrix[2][2];
  const trace = m00 + m11 + m22;
  let w;
  let x;
  let y;
  let z;
  if (trace > 0) {
    const s = Math.sqrt(trace + 1) * 2;
    w = 0.25 * s;
    x = (m21 - m12) / s;
    y = (m02 - m20) / s;
    z = (m10 - m01) / s;
  } else if (m00 > m11 && m00 > m22) {
    const s = Math.sqrt(1 + m00 - m11 - m22) * 2;
    w = (m21 - m12) / s;
    x = 0.25 * s;
    y = (m01 + m10) / s;
    z = (m02 + m20) / s;
  } else if (m11 > m22) {
    const s = Math.sqrt(1 + m11 - m00 - m22) * 2;
    w = (m02 - m20) / s;
    x = (m01 + m10) / s;
    y = 0.25 * s;
    z = (m12 + m21) / s;
  } else {
    const s = Math.sqrt(1 + m22 - m00 - m11) * 2;
    w = (m10 - m01) / s;
    x = (m02 + m20) / s;
    y = (m12 + m21) / s;
    z = 0.25 * s;
  }
  return vectorNormalize([w, x, y, z], "camera quaternion");
}

function independentBlenderCamera(location, target, scale, near, far) {
  const forward = vectorNormalize(
    vectorSubtract(target, location),
    "camera direction",
  );
  const localZ = vectorScale(forward, -1);
  const worldUp = [0, 0, 1];
  const localX = vectorNormalize(
    vectorCross(worldUp, localZ),
    "camera local X",
  );
  const localY = vectorNormalize(
    vectorCross(localZ, localX),
    "camera local Y",
  );
  const rotation = [
    [localX[0], localY[0], localZ[0]],
    [localX[1], localY[1], localZ[1]],
    [localX[2], localY[2], localZ[2]],
  ];
  const rotationInverse = matrixTranspose3(rotation);
  const viewTranslation = rotationInverse.map(
    (row) => -vectorDot(row, location),
  );
  const matrixWorld = [
    rotation[0][0],
    rotation[0][1],
    rotation[0][2],
    location[0],
    rotation[1][0],
    rotation[1][1],
    rotation[1][2],
    location[1],
    rotation[2][0],
    rotation[2][1],
    rotation[2][2],
    location[2],
    0,
    0,
    0,
    1,
  ];
  const viewMatrix = [
    rotationInverse[0][0],
    rotationInverse[0][1],
    rotationInverse[0][2],
    viewTranslation[0],
    rotationInverse[1][0],
    rotationInverse[1][1],
    rotationInverse[1][2],
    viewTranslation[1],
    rotationInverse[2][0],
    rotationInverse[2][1],
    rotationInverse[2][2],
    viewTranslation[2],
    0,
    0,
    0,
    1,
  ];
  const aspect = 1920 / 1080;
  const verticalScale = scale / aspect;
  const projectionMatrix = [
    2 / scale,
    0,
    0,
    0,
    0,
    2 / verticalScale,
    0,
    0,
    0,
    0,
    -2 / (far - near),
    -(far + near) / (far - near),
    0,
    0,
    0,
    1,
  ];
  return {
    quaternion: quaternionFromRotationMatrix(rotation),
    matrixWorld,
    viewMatrix,
    projectionMatrix,
  };
}

function invertRigidMatrix4(matrix) {
  assert(
    Array.isArray(matrix) && matrix.length === 16,
    "rigid matrix shape",
    matrix,
  );
  const rotation = [
    [matrix[0], matrix[1], matrix[2]],
    [matrix[4], matrix[5], matrix[6]],
    [matrix[8], matrix[9], matrix[10]],
  ];
  const inverseRotation = matrixTranspose3(rotation);
  const translation = [matrix[3], matrix[7], matrix[11]];
  const inverseTranslation = inverseRotation.map(
    (row) => Math.fround(-vectorDot(row, translation)),
  );
  return [
    inverseRotation[0][0],
    inverseRotation[0][1],
    inverseRotation[0][2],
    inverseTranslation[0],
    inverseRotation[1][0],
    inverseRotation[1][1],
    inverseRotation[1][2],
    inverseTranslation[1],
    inverseRotation[2][0],
    inverseRotation[2][1],
    inverseRotation[2][2],
    inverseTranslation[2],
    0,
    0,
    0,
    1,
  ];
}

function assertQuaternionNear(actual, expected, epsilon, message) {
  const direct = actual.map(
    (value, index) => Number(value) - Number(expected[index]),
  );
  const negated = actual.map(
    (value, index) => Number(value) + Number(expected[index]),
  );
  const directMax = Math.max(...direct.map(Math.abs));
  const negatedMax = Math.max(...negated.map(Math.abs));
  assert(
    Math.min(directMax, negatedMax) <= epsilon,
    message,
    { actual, expected, epsilon, directMax, negatedMax },
  );
}

function verifyInputLockFile() {
  const fingerprint = fileFingerprint(INPUT_LOCK_PATH);
  assertDeepEqual(
    fingerprint,
    {
      bytes: EXPECTED_INPUT_LOCK_BYTES,
      sha256: EXPECTED_INPUT_LOCK_SHA256,
    },
    "input_lock.json root bytes and SHA-256",
  );
  const inputLock = readJson(INPUT_LOCK_PATH);
  assert(
    inputLock.schema_version === "bf3d.r2s.input_lock.v1" &&
      inputLock.requirement_id === REQUIREMENT_ID &&
      inputLock.stage_id === GATE_VALUE &&
      inputLock.status === "locked" &&
      inputLock.hash_algorithm === "SHA-256" &&
      inputLock.entry_count === 22 &&
      inputLock.entries.length === 22 &&
      inputLock.all_required_inputs_present === true &&
      inputLock.all_hashes_computed_from_current_bytes === true,
    "fixed R2S input lock contract",
    inputLock,
  );
  assert(
    new Set(inputLock.entries.map((entry) => entry.id)).size === 22 &&
      new Set(inputLock.entries.map((entry) => entry.path)).size === 22 &&
      inputLock.entries.every(
        (entry) =>
          entry.required === true &&
          Number.isInteger(entry.bytes) &&
          entry.bytes > 0 &&
          /^[a-f0-9]{64}$/.test(entry.sha256),
      ),
    "all 22 lock entries must be unique, required, and hashed",
    inputLock.entries,
  );
  const r2rContractEntry = inputLock.entries.find(
    (entry) => entry.id === "r2r_pre_registered_capture_contract",
  );
  const r2rManifestEntry = inputLock.entries.find(
    (entry) => entry.id === "r2r_blender_capture_manifest",
  );
  assertDeepEqual(
    {
      path: r2rContractEntry?.path,
      bytes: r2rContractEntry?.bytes,
      sha256: r2rContractEntry?.sha256,
    },
    {
      path:
        "PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/capture_contract.json",
      bytes: EXPECTED_R2R_CONTRACT_BYTES,
      sha256: EXPECTED_R2R_CONTRACT_SHA256,
    },
    "R2R contract lock entry",
  );
  assertDeepEqual(
    {
      path: r2rManifestEntry?.path,
      bytes: r2rManifestEntry?.bytes,
      sha256: r2rManifestEntry?.sha256,
    },
    {
      path:
        "PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/capture_manifest.json",
      bytes: EXPECTED_R2R_MANIFEST_BYTES,
      sha256: EXPECTED_R2R_MANIFEST_SHA256,
    },
    "R2R manifest lock entry",
  );
  const controllerEntry = inputLock.entries.find(
    (entry) => entry.id === "three_structural_review_controller",
  );
  assertDeepEqual(
    {
      path: controllerEntry?.path,
      bytes: controllerEntry?.bytes,
      sha256: controllerEntry?.sha256,
    },
    {
      path: "高炉前端数据/assets/bf3d-structural-review.js",
      bytes: 49180,
      sha256:
        "4b9e686700ee3be32e20f31a03ca79a0910779262510b849fe52d8e2bafb3aa6",
    },
    "controller pre-state lock entry",
  );
  const delta = readJson(IMPLEMENTATION_DELTA_PATH);
  const controllerDelta = delta.changed_files?.find(
    (entry) =>
      entry.path ===
      "高炉前端数据/assets/bf3d-structural-review.js",
  );
  assert(
    delta.schema_version ===
      "bf3d.r2s.implementation_delta_manifest.v1" &&
      delta.requirement_id === REQUIREMENT_ID &&
      delta.stage_id === GATE_VALUE &&
      delta.input_lock?.status === "preserved_pre_state" &&
      delta.input_lock?.entry_count === 22,
    "implementation delta must identify the preserved pre-state lock",
    delta,
  );
  assertDeepEqual(
    controllerDelta?.before,
    {
      bytes: controllerEntry.bytes,
      sha256: controllerEntry.sha256,
    },
    "controller delta before state must match the fixed lock",
  );
  assertDeepEqual(
    controllerDelta?.after,
    {
      bytes: EXPECTED_CONTROLLER_POST_BYTES,
      sha256: EXPECTED_CONTROLLER_POST_SHA256,
    },
    "controller authorized post-state must be fixed",
  );
  return { inputLock, fingerprint };
}

function verifyLockedInputsSnapshot(inputLock, label) {
  const rootFingerprint = fileFingerprint(INPUT_LOCK_PATH);
  assertDeepEqual(
    rootFingerprint,
    {
      bytes: EXPECTED_INPUT_LOCK_BYTES,
      sha256: EXPECTED_INPUT_LOCK_SHA256,
    },
    `${label} input lock root`,
  );
  const entries = inputLock.entries.map((entry) => {
    const filePath = normalizeLockedPath(entry.path);
    assert(fs.existsSync(filePath), `${label} locked input exists`, {
      id: entry.id,
      filePath,
    });
    const actual = fileFingerprint(filePath);
    const locked = {
      bytes: entry.bytes,
      sha256: entry.sha256,
    };
    const isControllerPostState =
      entry.id === "three_structural_review_controller";
    const authoritativeCurrent = isControllerPostState
      ? {
          bytes: EXPECTED_CONTROLLER_POST_BYTES,
          sha256: EXPECTED_CONTROLLER_POST_SHA256,
        }
      : locked;
    assertDeepEqual(
      actual,
      authoritativeCurrent,
      `${label} authoritative locked input ${entry.id}`,
    );
    return {
      id: entry.id,
      path: entry.path,
      locked,
      actual,
      status: isControllerPostState
        ? "authorized_post_delta_matches"
        : "locked_bytes_match",
    };
  });
  assert(
    entries.length === 22 &&
      entries.filter(
        (entry) => entry.status === "locked_bytes_match",
      ).length === 21 &&
      entries.filter(
        (entry) =>
          entry.status === "authorized_post_delta_matches",
      ).length === 1,
    `${label} all 22 locked entries classified`,
    entries,
  );
  return { label, rootFingerprint, entries };
}

function assertLockedSnapshotsEqual(before, after) {
  assertDeepEqual(
    after.rootFingerprint,
    before.rootFingerprint,
    "input_lock.json must remain byte-identical during verification",
  );
  assertDeepEqual(
    after.entries.map(({ id, path: entryPath, actual, status }) => ({
      id,
      path: entryPath,
      actual,
      status,
    })),
    before.entries.map(
      ({ id, path: entryPath, actual, status }) => ({
        id,
        path: entryPath,
        actual,
        status,
      }),
    ),
    "all 22 locked inputs must remain byte-identical before and after browser verification",
  );
}

function verifyDecisionFiles() {
  const color = readJson(COLOR_DECISION_PATH);
  const photometry = readJson(PHOTOMETRIC_DECISION_PATH);
  const pipeline = readJson(PIPELINE_STATUS_PATH);
  assert(
    color.schema_version ===
      "bf3d.r2s.color_management_decision.v1" &&
      color.status === "pending_preapproval" &&
      color.approved === false &&
      color.capture_eligible === false &&
      color.production_runtime?.tone_mapping ===
        "THREE.ACESFilmicToneMapping" &&
      color.production_runtime?.output_color_space ===
        "THREE.SRGBColorSpace" &&
      color.production_runtime?.exposure === 1.05 &&
      color.production_runtime?.mutation_authorized === false &&
      color.threejs_audit_candidate
        ?.medium_low_equivalence_implemented === false &&
      color.threejs_audit_candidate
        ?.medium_low_equivalence_approved === false &&
      color.decision_needed?.selected_option === null,
    "color decision must remain exact, sRGB, and pending",
    color,
  );
  assert(
    Object.values(color.guardrails || {}).every(
      (value) => value === false,
    ),
    "all color decision capture/change guardrails must remain false",
    color.guardrails,
  );
  assert(
    photometry.schema_version ===
      "bf3d.r2s.photometric_mapping_decision.v1" &&
      photometry.status === "pending_preapproval" &&
      photometry.approved === false &&
      photometry.capture_eligible === false &&
      photometry.coordinate_basis?.formula ===
        "Blender (x,y,z) -> Three.js (x,z,-y)" &&
      photometry.coordinate_basis
        ?.approved_for_position_and_direction_mapping === true &&
      photometry.topology_mapping?.length === 4 &&
      photometry.world_mapping?.three_environment_mapping_approved ===
        false &&
      photometry.world_mapping?.ambient_light_substitution_approved ===
        false,
    "photometric decision must remain pending and fail closed",
    photometry,
  );
  assert(
    Object.values(photometry.guardrails || {}).every(
      (value) => value === false,
    ),
    "all photometric implementation/capture guardrails must remain false",
    photometry.guardrails,
  );
  assert(
    pipeline.schema_version ===
      "bf3d.r2s.renderer_contract_alignment.v1" &&
      pipeline.stage_id === GATE_VALUE &&
      pipeline.status ===
        "audit_numeric_contract_verified_hardened_capture_blocked" &&
      pipeline.approval_granted === false &&
      pipeline.next_stage_allowed === false &&
      pipeline.implementation?.numeric_contract_implemented === true &&
      pipeline.implementation?.audit_only_camera_implemented ===
        false &&
      pipeline.implementation?.p40_four_light_mapping_implemented ===
        false &&
      pipeline.implementation?.threejs_capture_eligible === false &&
      pipeline.implementation?.beauty_mask_capture_implemented ===
        false &&
      pipeline.release_gates?.r2s_numeric_contract_verifier ===
        "passed_hardened_real_production_no_side_effects" &&
      pipeline.release_gates?.threejs_vs_eevee_numeric_ab ===
        "pending",
    "pipeline status must describe numeric-only capture-blocked state",
    pipeline,
  );
  return {
    colorStatus: color.status,
    colorOutputColorSpace:
      color.production_runtime.output_color_space,
    photometryStatus: photometry.status,
    pipelineStatus: pipeline.status,
    actualAuditCameraObjectsImplemented:
      pipeline.implementation.audit_only_camera_implemented,
    actualAuditLightObjectsImplemented:
      pipeline.implementation.p40_four_light_mapping_implemented,
  };
}

function harnessHtml() {
  return `<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>R2S audit contract harness</title></head>
<body>
<script type="module">
  import {
    buildR2SAuditShotManifest,
    getR2SAuditCaptureCapability
  } from "/assets/bf3d-structural-review.js";
  const capability = getR2SAuditCaptureCapability();
  const manifest = buildR2SAuditShotManifest();
  const capabilityAgain = getR2SAuditCaptureCapability();
  const manifestAgain = buildR2SAuditShotManifest();
  function inspectDeepFreeze(root, rootName) {
    const seen = new WeakSet();
    const notFrozen = [];
    let objectCount = 0;
    function visit(value, valuePath) {
      if (!value || typeof value !== "object" || seen.has(value)) return;
      seen.add(value);
      objectCount += 1;
      if (!Object.isFrozen(value)) notFrozen.push(valuePath);
      for (const key of Reflect.ownKeys(value)) {
        visit(value[key], valuePath + "." + String(key));
      }
    }
    visit(root, rootName);
    return { objectCount, notFrozen, allFrozen: notFrozen.length === 0 };
  }
  function attemptMutations(capabilityValue, manifestValue) {
    const before = JSON.stringify({ capabilityValue, manifestValue });
    const attempts = [];
    const attempt = (label, mutation) => {
      try {
        mutation();
        attempts.push({ label, threw: false, errorName: null });
      } catch (error) {
        attempts.push({
          label,
          threw: true,
          errorName: error?.name || typeof error
        });
      }
    };
    attempt("capability.captureEligible", () => {
      capabilityValue.captureEligible = true;
    });
    attempt("capability.gates.enabled", () => {
      capabilityValue.gates.enabled = !capabilityValue.gates.enabled;
    });
    attempt("capability.blockers.push", () => {
      capabilityValue.blockers.push("mutation");
    });
    attempt("manifest.shots.push", () => {
      manifestValue.shots.push({ id: "mutation" });
    });
    attempt("manifest.imageCapture.blocker", () => {
      manifestValue.imageCapture.blocker = "mutation";
    });
    attempt("delete manifest.colorState", () => {
      delete manifestValue.colorState;
    });
    attempt("define capability.captureEligible", () => {
      Object.defineProperty(capabilityValue, "captureEligible", {
        value: true
      });
    });
    attempt("set capability prototype", () => {
      Object.setPrototypeOf(capabilityValue, {});
    });
    if (capabilityValue.auditContract) {
      attempt("contract threshold", () => {
        capabilityValue.auditContract.comparisonThresholds
          .silhouette_iou_min = 0;
      });
      attempt("contract lights push", () => {
        capabilityValue.auditContract.lights.items.push({});
      });
      attempt("contract light target", () => {
        capabilityValue.auditContract.lights.items[0].three.target[0] = 0;
      });
      attempt("shot frustum", () => {
        manifestValue.shots[0].camera.three.frustum.left = 0;
      });
    }
    return {
      attempts,
      allThrewTypeError: attempts.every(
        (item) => item.threw && item.errorName === "TypeError"
      ),
      unchanged:
        before === JSON.stringify({ capabilityValue, manifestValue })
    };
  }
  window.__BF3D_R2S_HARNESS_API__ = Object.freeze({
    getCapability: getR2SAuditCaptureCapability,
    getManifest: buildR2SAuditShotManifest
  });
  window.__BF3D_R2S_HARNESS_RESULT__ = {
    capability,
    manifest,
    deterministic:
      JSON.stringify(capability) === JSON.stringify(capabilityAgain) &&
      JSON.stringify(manifest) === JSON.stringify(manifestAgain),
    frozen: {
      capability: Object.isFrozen(capability),
      gates: Object.isFrozen(capability.gates),
      auditContract:
        capability.auditContract === null ||
        Object.isFrozen(capability.auditContract),
      shotManifest:
        capability.shotManifest === null ||
        Object.isFrozen(capability.shotManifest),
      manifest: Object.isFrozen(manifest),
      shots: Object.isFrozen(manifest.shots)
    },
    deepFreeze: {
      capability: inspectDeepFreeze(capability, "capability"),
      manifest: inspectDeepFreeze(manifest, "manifest")
    },
    mutation: attemptMutations(capability, manifest)
  };
</script>
</body>
</html>`;
}

function startServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((request, response) => {
      let url;
      try {
        url = new URL(request.url, "http://127.0.0.1");
      } catch {
        response.writeHead(400).end("bad request");
        return;
      }
      if (url.pathname === "/__bf3d_r2s_audit_harness__.html") {
        response.writeHead(200, {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store",
        });
        response.end(harnessHtml());
        return;
      }
      let pathname;
      try {
        pathname = decodeURIComponent(url.pathname);
      } catch {
        response.writeHead(400).end("bad request");
        return;
      }
      if (pathname === "/") {
        pathname = "/frontend_dashboard_v3.server.html";
      }
      const target = path.resolve(
        FRONTEND_ROOT,
        pathname.replace(/^\/+/, ""),
      );
      if (
        target !== FRONTEND_ROOT &&
        !target.startsWith(FRONTEND_ROOT + path.sep)
      ) {
        response.writeHead(403).end("forbidden");
        return;
      }
      fs.stat(target, (error, stat) => {
        if (error || !stat.isFile()) {
          response.writeHead(404).end("not found");
          return;
        }
        response.writeHead(200, {
          "Content-Type":
            MIME[path.extname(target).toLowerCase()] ||
            "application/octet-stream",
          "Cache-Control": "no-store",
        });
        fs.createReadStream(target).pipe(response);
      });
    });
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

const NEGATIVE_GATE_CASES = [
  {
    label: "default gate",
    queryValues: [],
    tokenMode: "none",
    expected: {
      queryMatches: false,
      queryValueCount: 0,
      tokenMatches: false,
      tokenWasPresent: false,
    },
  },
  {
    label: "query-only gate",
    queryValues: [GATE_VALUE],
    tokenMode: "none",
    expected: {
      queryMatches: true,
      queryValueCount: 1,
      tokenMatches: false,
      tokenWasPresent: false,
    },
  },
  {
    label: "token-only gate",
    queryValues: [],
    tokenMode: "own",
    tokenValue: GATE_VALUE,
    expected: {
      queryMatches: false,
      queryValueCount: 0,
      tokenMatches: true,
      tokenWasPresent: true,
    },
  },
  {
    label: "wrong-query correct-token gate",
    queryValues: [`${GATE_VALUE}_WRONG`],
    tokenMode: "own",
    tokenValue: GATE_VALUE,
    expected: {
      queryMatches: false,
      queryValueCount: 1,
      tokenMatches: true,
      tokenWasPresent: true,
    },
  },
  {
    label: "correct-query wrong-token gate",
    queryValues: [GATE_VALUE],
    tokenMode: "own",
    tokenValue: `${GATE_VALUE}_WRONG`,
    expected: {
      queryMatches: true,
      queryValueCount: 1,
      tokenMatches: false,
      tokenWasPresent: true,
    },
  },
  {
    label: "duplicate-correct-query gate",
    queryValues: [GATE_VALUE, GATE_VALUE],
    tokenMode: "own",
    tokenValue: GATE_VALUE,
    expected: {
      queryMatches: false,
      queryValueCount: 2,
      tokenMatches: true,
      tokenWasPresent: true,
    },
  },
  {
    label: "mixed-query-values gate",
    queryValues: [GATE_VALUE, `${GATE_VALUE}_WRONG`],
    tokenMode: "own",
    tokenValue: GATE_VALUE,
    expected: {
      queryMatches: false,
      queryValueCount: 2,
      tokenMatches: true,
      tokenWasPresent: true,
    },
  },
  {
    label: "inherited-prototype-token gate",
    queryValues: [GATE_VALUE],
    tokenMode: "inherited",
    tokenValue: GATE_VALUE,
    expected: {
      queryMatches: true,
      queryValueCount: 1,
      tokenMatches: false,
      tokenWasPresent: false,
    },
  },
  {
    label: "late-token gate",
    queryValues: [GATE_VALUE],
    tokenMode: "none",
    lateTokenValue: GATE_VALUE,
    expected: {
      queryMatches: true,
      queryValueCount: 1,
      tokenMatches: false,
      tokenWasPresent: false,
    },
  },
];

const ENABLED_GATE_CASE = {
  label: "exact dual gate",
  queryValues: [GATE_VALUE],
  tokenMode: "own",
  tokenValue: GATE_VALUE,
};

function buildQuery(queryValues, includeWsPort = false) {
  const query = new URLSearchParams();
  if (includeWsPort) query.set("ws_port", "8767");
  for (const value of queryValues || []) {
    query.append(GATE_QUERY_NAME, value);
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

async function installGateInitScript(context, gateCase) {
  await context.addInitScript(
    ({ name, mode, value }) => {
      if (mode === "own") {
        Object.defineProperty(window, name, {
          value,
          configurable: true,
          writable: true,
        });
      } else if (mode === "inherited") {
        Object.defineProperty(Object.getPrototypeOf(window), name, {
          value,
          configurable: true,
          writable: true,
        });
      }
    },
    {
      name: WINDOW_TOKEN_NAME,
      mode: gateCase.tokenMode || "none",
      value: gateCase.tokenValue ?? null,
    },
  );
}

async function runHarnessCase(browser, baseUrl, gateCase) {
  const context = await browser.newContext();
  await installGateInitScript(context, gateCase);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  try {
    await page.goto(
      `${baseUrl}/__bf3d_r2s_audit_harness__.html${buildQuery(
        gateCase.queryValues,
      )}`,
      {
        waitUntil: "domcontentloaded",
        timeout: 30_000,
      },
    );
    await page.waitForFunction(
      () => Boolean(window.__BF3D_R2S_HARNESS_RESULT__),
      null,
      { timeout: 30_000 },
    );
    const result = await page.evaluate(
      () => window.__BF3D_R2S_HARNESS_RESULT__,
    );
    let lateResult = null;
    if (gateCase.lateTokenValue !== undefined) {
      lateResult = await page.evaluate(
        ({ name, value }) => {
          window[name] = value;
          return {
            capability:
              window.__BF3D_R2S_HARNESS_API__.getCapability(),
            manifest:
              window.__BF3D_R2S_HARNESS_API__.getManifest(),
          };
        },
        {
          name: WINDOW_TOKEN_NAME,
          value: gateCase.lateTokenValue,
        },
      );
    }
    return { result, lateResult, pageErrors };
  } finally {
    await context.close();
  }
}

function assertDisabledCase(caseResult, expected, label) {
  const { capability, manifest, deterministic, frozen } =
    caseResult.result;
  assert(caseResult.pageErrors.length === 0, `${label} page errors`, {
    pageErrors: caseResult.pageErrors,
  });
  assert(
    capability.auditMode === false &&
      capability.captureEligible === false &&
      capability.colorState === "pending_preapproval" &&
      capability.numericManifestAvailable === false &&
      capability.imageCaptureAvailable === false &&
      capability.auditContract === null &&
      capability.shotManifest === null,
    `${label} capability must fail closed`,
    capability,
  );
  assert(
    capability.gates.query.matches === expected.queryMatches &&
      capability.gates.query.valueCount ===
        expected.queryValueCount &&
      capability.gates.preInjectedWindowToken.matches ===
        expected.tokenMatches &&
      capability.gates.preInjectedWindowToken.wasPresent ===
        expected.tokenWasPresent &&
      capability.gates.enabled === false,
    `${label} dual gate state`,
    capability.gates,
  );
  assert(
    manifest.auditMode === false &&
      manifest.captureEligible === false &&
      manifest.shots.length === 0 &&
      manifest.imageCapture.captureAttempted === false &&
      manifest.imageCapture.beautyFiles.length === 0 &&
      manifest.imageCapture.maskFiles.length === 0,
    `${label} blocked manifest`,
    manifest,
  );
  assertDeepEqual(
    capability.blockers,
    [
      "dual_test_gate_not_satisfied",
      "color_management_preapproval_required",
      "light_photometry_preapproval_required",
    ],
    `${label} exact capability blockers`,
  );
  assert(
    manifest.imageCapture.blocker ===
      "dual_test_gate_not_satisfied",
    `${label} exact manifest blocker`,
    manifest.imageCapture,
  );
  assert(
    deterministic &&
      Object.values(frozen).every(Boolean) &&
      caseResult.result.deepFreeze.capability.allFrozen &&
      caseResult.result.deepFreeze.manifest.allFrozen &&
      caseResult.result.mutation.allThrewTypeError &&
      caseResult.result.mutation.unchanged,
    `${label} results are deterministic and frozen`,
    {
      deterministic,
      frozen,
      deepFreeze: caseResult.result.deepFreeze,
      mutation: caseResult.result.mutation,
    },
  );
  if (caseResult.lateResult) {
    assert(
      caseResult.lateResult.capability.auditMode === false &&
        caseResult.lateResult.capability.gates
          .preInjectedWindowToken.matches === false &&
        caseResult.lateResult.manifest.auditMode === false &&
        caseResult.lateResult.manifest.shots.length === 0,
      `${label} token added after module load must remain disabled`,
      caseResult.lateResult,
    );
  }
}

async function installProductionInstrumentation(context, gateCase) {
  await context.addInitScript(
    ({ tokenName, tokenMode, tokenValue }) => {
      if (tokenMode === "own") {
        Object.defineProperty(window, tokenName, {
          value: tokenValue,
          configurable: true,
          writable: true,
        });
      } else if (tokenMode === "inherited") {
        Object.defineProperty(
          Object.getPrototypeOf(window),
          tokenName,
          {
            value: tokenValue,
            configurable: true,
            writable: true,
          },
        );
      }

      const counterNames = [
        "canvasCreated",
        "offscreenCanvasCreated",
        "canvasAttachOps",
        "canvasGetContext",
        "webglContextRequests",
        "webglContextsCreated",
        "webglDrawCalls",
        "readPixels",
        "toDataURL",
        "toBlob",
        "captureStream",
        "objectUrlCreated",
        "objectUrlRevoked",
        "downloadClicks",
        "createImageBitmap",
        "rafRequested",
        "rafCallbacks",
        "rafCancelled",
      ];
      const counters = Object.fromEntries(
        counterNames.map((name) => [name, 0]),
      );
      const duringAudit = Object.fromEntries(
        counterNames.map((name) => [name, 0]),
      );
      const objectUrls = new Set();
      const webglContexts = new WeakSet();
      const pendingRaf = new Set();
      let auditDepth = 0;

      const bump = (name, amount = 1) => {
        counters[name] += amount;
        if (auditDepth > 0) duringAudit[name] += amount;
      };
      const wrapMethod = (
        owner,
        methodName,
        counterName,
        after = null,
      ) => {
        const original = owner?.[methodName];
        if (typeof original !== "function") return;
        Object.defineProperty(owner, methodName, {
          configurable: true,
          writable: true,
          value: function (...args) {
            bump(counterName);
            const result = Reflect.apply(original, this, args);
            if (after) after(result, args, this);
            return result;
          },
        });
      };
      const canvasCountIn = (node) => {
        if (!node) return 0;
        let count =
          typeof HTMLCanvasElement !== "undefined" &&
          node instanceof HTMLCanvasElement
            ? 1
            : 0;
        if (typeof node.querySelectorAll === "function") {
          count += node.querySelectorAll("canvas").length;
        }
        return count;
      };

      const originalCreateElement = Document.prototype.createElement;
      Document.prototype.createElement = function (...args) {
        const element = Reflect.apply(
          originalCreateElement,
          this,
          args,
        );
        if (
          String(args[0] || "").toLowerCase() === "canvas"
        ) {
          bump("canvasCreated");
        }
        return element;
      };
      const originalCreateElementNS =
        Document.prototype.createElementNS;
      Document.prototype.createElementNS = function (...args) {
        const element = Reflect.apply(
          originalCreateElementNS,
          this,
          args,
        );
        if (
          String(args[1] || "").toLowerCase() === "canvas"
        ) {
          bump("canvasCreated");
        }
        return element;
      };
      for (const methodName of [
        "appendChild",
        "insertBefore",
        "replaceChild",
      ]) {
        const original = Node.prototype[methodName];
        Node.prototype[methodName] = function (...args) {
          const count = canvasCountIn(args[0]);
          if (count > 0) bump("canvasAttachOps", count);
          return Reflect.apply(original, this, args);
        };
      }

      const canvasGetContext =
        HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (
        type,
        ...args
      ) {
        bump("canvasGetContext");
        const webgl =
          /^(?:webgl|webgl2|experimental-webgl)$/i.test(
            String(type),
          );
        if (webgl) bump("webglContextRequests");
        const result = Reflect.apply(canvasGetContext, this, [
          type,
          ...args,
        ]);
        if (webgl && result && !webglContexts.has(result)) {
          webglContexts.add(result);
          bump("webglContextsCreated");
        }
        return result;
      };
      wrapMethod(
        HTMLCanvasElement.prototype,
        "toDataURL",
        "toDataURL",
      );
      wrapMethod(
        HTMLCanvasElement.prototype,
        "toBlob",
        "toBlob",
      );
      wrapMethod(
        HTMLCanvasElement.prototype,
        "captureStream",
        "captureStream",
      );

      if (typeof window.OffscreenCanvas === "function") {
        const NativeOffscreenCanvas = window.OffscreenCanvas;
        window.OffscreenCanvas = new Proxy(NativeOffscreenCanvas, {
          construct(target, args, newTarget) {
            bump("offscreenCanvasCreated");
            return Reflect.construct(target, args, newTarget);
          },
        });
        const offscreenGetContext =
          NativeOffscreenCanvas.prototype.getContext;
        if (typeof offscreenGetContext === "function") {
          NativeOffscreenCanvas.prototype.getContext = function (
            type,
            ...args
          ) {
            bump("canvasGetContext");
            const webgl =
              /^(?:webgl|webgl2|experimental-webgl)$/i.test(
                String(type),
              );
            if (webgl) bump("webglContextRequests");
            const result = Reflect.apply(
              offscreenGetContext,
              this,
              [type, ...args],
            );
            if (
              webgl &&
              result &&
              !webglContexts.has(result)
            ) {
              webglContexts.add(result);
              bump("webglContextsCreated");
            }
            return result;
          };
        }
        wrapMethod(
          NativeOffscreenCanvas.prototype,
          "convertToBlob",
          "toBlob",
        );
      }

      for (const constructorName of [
        "WebGLRenderingContext",
        "WebGL2RenderingContext",
      ]) {
        const prototype = window[constructorName]?.prototype;
        wrapMethod(prototype, "readPixels", "readPixels");
        for (const drawMethod of [
          "drawArrays",
          "drawElements",
          "drawArraysInstanced",
          "drawElementsInstanced",
        ]) {
          wrapMethod(prototype, drawMethod, "webglDrawCalls");
        }
      }

      const originalCreateObjectURL = URL.createObjectURL;
      if (typeof originalCreateObjectURL === "function") {
        URL.createObjectURL = function (...args) {
          const value = Reflect.apply(
            originalCreateObjectURL,
            this,
            args,
          );
          objectUrls.add(value);
          bump("objectUrlCreated");
          return value;
        };
      }
      const originalRevokeObjectURL = URL.revokeObjectURL;
      if (typeof originalRevokeObjectURL === "function") {
        URL.revokeObjectURL = function (value) {
          objectUrls.delete(value);
          bump("objectUrlRevoked");
          return Reflect.apply(originalRevokeObjectURL, this, [
            value,
          ]);
        };
      }
      const originalAnchorClick =
        HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function (...args) {
        if (
          this.hasAttribute("download") ||
          String(this.href || "").startsWith("blob:")
        ) {
          bump("downloadClicks");
        }
        return Reflect.apply(originalAnchorClick, this, args);
      };
      if (typeof window.createImageBitmap === "function") {
        const originalCreateImageBitmap =
          window.createImageBitmap.bind(window);
        window.createImageBitmap = function (...args) {
          bump("createImageBitmap");
          return originalCreateImageBitmap(...args);
        };
      }

      const originalRaf =
        window.requestAnimationFrame.bind(window);
      const originalCancelRaf =
        window.cancelAnimationFrame.bind(window);
      window.requestAnimationFrame = function (callback) {
        bump("rafRequested");
        let id = 0;
        id = originalRaf((timestamp) => {
          pendingRaf.delete(id);
          bump("rafCallbacks");
          return callback(timestamp);
        });
        pendingRaf.add(id);
        return id;
      };
      window.cancelAnimationFrame = function (id) {
        if (pendingRaf.delete(id)) bump("rafCancelled");
        return originalCancelRaf(id);
      };

      const snapshot = () => ({
        counters: { ...counters },
        duringAudit: { ...duringAudit },
        auditDepth,
        liveObjectUrls: objectUrls.size,
        pendingRaf: pendingRaf.size,
        domCanvasCount: document.querySelectorAll("canvas").length,
      });
      const api = {
        beginAudit() {
          auditDepth += 1;
        },
        endAudit() {
          auditDepth = Math.max(0, auditDepth - 1);
        },
        snapshot,
      };
      Object.defineProperty(
        window,
        "__BF3D_R2S_TEST_INSTRUMENTATION__",
        {
          value: Object.freeze(api),
          configurable: false,
          writable: false,
        },
      );
      Object.defineProperty(
        window,
        "__BF3D_R2S_PRE_APP_SNAPSHOT__",
        {
          value: Object.freeze(snapshot()),
          configurable: false,
          writable: false,
        },
      );
    },
    {
      tokenName: WINDOW_TOKEN_NAME,
      tokenMode: gateCase.tokenMode || "none",
      tokenValue: gateCase.tokenValue ?? null,
    },
  );
}

async function runProductionGateCase(browser, baseUrl, gateCase) {
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
  });
  await installProductionInstrumentation(context, gateCase);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  try {
    await page.goto(
      `${baseUrl}/frontend_dashboard_v3.server.html${buildQuery(
        gateCase.queryValues,
        true,
      )}#overview`,
      {
        waitUntil: "domcontentloaded",
        timeout: 90_000,
      },
    );
    const result = await page.evaluate(
      async ({ tokenName, lateTokenValue }) => {
        const module = await import(
          "/assets/bf3d-structural-review.js"
        );
        if (lateTokenValue !== null) {
          window[tokenName] = lateTokenValue;
        }
        const inspectDeepFreeze = (root, rootName) => {
          const seen = new WeakSet();
          const notFrozen = [];
          let objectCount = 0;
          const visit = (value, valuePath) => {
            if (
              !value ||
              typeof value !== "object" ||
              seen.has(value)
            ) {
              return;
            }
            seen.add(value);
            objectCount += 1;
            if (!Object.isFrozen(value)) {
              notFrozen.push(valuePath);
            }
            for (const key of Reflect.ownKeys(value)) {
              visit(
                value[key],
                `${valuePath}.${String(key)}`,
              );
            }
          };
          visit(root, rootName);
          return {
            objectCount,
            notFrozen,
            allFrozen: notFrozen.length === 0,
          };
        };
        const instrument =
          window.__BF3D_R2S_TEST_INSTRUMENTATION__;
        const beforeInstrumentation = instrument.snapshot();
        instrument.beginAudit();
        let capability;
        let manifest;
        try {
          capability =
            module.getR2SAuditCaptureCapability();
          manifest = module.buildR2SAuditShotManifest();
        } finally {
          instrument.endAudit();
        }
        const afterInstrumentation = instrument.snapshot();
        return {
          capability,
          manifest,
          deterministic:
            JSON.stringify(capability) ===
              JSON.stringify(
                module.getR2SAuditCaptureCapability(),
              ) &&
            JSON.stringify(manifest) ===
              JSON.stringify(
                module.buildR2SAuditShotManifest(),
              ),
          frozen: {
            capability: Object.isFrozen(capability),
            gates: Object.isFrozen(capability.gates),
            auditContract:
              capability.auditContract === null ||
              Object.isFrozen(capability.auditContract),
            shotManifest:
              capability.shotManifest === null ||
              Object.isFrozen(capability.shotManifest),
            manifest: Object.isFrozen(manifest),
            shots: Object.isFrozen(manifest.shots),
          },
          deepFreeze: {
            capability: inspectDeepFreeze(
              capability,
              "capability",
            ),
            manifest: inspectDeepFreeze(manifest, "manifest"),
          },
          mutation: {
            allThrewTypeError: true,
            unchanged: true,
            attempts: [],
          },
          preApp:
            window.__BF3D_R2S_PRE_APP_SNAPSHOT__,
          beforeInstrumentation,
          afterInstrumentation,
        };
      },
      {
        tokenName: WINDOW_TOKEN_NAME,
        lateTokenValue:
          gateCase.lateTokenValue === undefined
            ? null
            : gateCase.lateTokenValue,
      },
    );
    assert(
      pageErrors.length === 0,
      `${gateCase.label} production page errors`,
      pageErrors,
    );
    const dangerousCounters = [
      "canvasCreated",
      "offscreenCanvasCreated",
      "canvasAttachOps",
      "canvasGetContext",
      "webglContextRequests",
      "webglContextsCreated",
      "webglDrawCalls",
      "readPixels",
      "toDataURL",
      "toBlob",
      "captureStream",
      "objectUrlCreated",
      "objectUrlRevoked",
      "downloadClicks",
      "createImageBitmap",
      "rafRequested",
      "rafCallbacks",
      "rafCancelled",
    ];
    assert(
      dangerousCounters.every(
        (name) =>
          result.afterInstrumentation.duringAudit[name] === 0 &&
          result.afterInstrumentation.counters[name] ===
            result.beforeInstrumentation.counters[name],
      ) &&
        result.afterInstrumentation.auditDepth === 0 &&
        result.afterInstrumentation.liveObjectUrls ===
          result.beforeInstrumentation.liveObjectUrls &&
        result.afterInstrumentation.domCanvasCount ===
          result.beforeInstrumentation.domCanvasCount,
      `${gateCase.label} production API must not capture or allocate browser resources`,
      {
        before: result.beforeInstrumentation,
        after: result.afterInstrumentation,
      },
    );
    return { result, pageErrors, lateResult: null };
  } finally {
    await context.close();
  }
}

function verifyStaticProductionContract() {
  const source = fs.readFileSync(CONTROLLER_PATH, "utf8");
  const html = fs.readFileSync(PRODUCTION_HTML_PATH, "utf8");
  assert(
    source.includes("getAuditCaptureCapability") &&
      source.includes("getAuditShotManifest") &&
      source.includes("getR2SAuditCaptureCapability") &&
      source.includes("buildR2SAuditShotManifest"),
    "controller must expose additive R2S read-only API",
  );
  const begin = source.indexOf("/* R2S_AUDIT_CONTRACT_BEGIN");
  const end = source.indexOf("/* R2S_AUDIT_CONTRACT_END */");
  assert(
    begin >= 0 && end > begin,
    "R2S audit contract block markers are required",
    { begin, end },
  );
  const auditBlock = source.slice(begin, end);
  const forbiddenAuditOperations = [
    /\bnew\s+THREE\.WebGLRenderer\b/,
    /\bnew\s+THREE\.(?:OrthographicCamera|DirectionalLight|RectAreaLight|Scene|WebGLRenderTarget)\b/,
    /\bnew\s+OffscreenCanvas\b/,
    /\brequestAnimationFrame\s*\(/,
    /\.setAnimationLoop\s*\(/,
    /\.render\s*\(/,
    /\breadRenderTargetPixels\b/,
    /\.readPixels\s*\(/,
    /\btoDataURL\b/,
    /\btoBlob\b/,
    /\bcaptureStream\b/,
    /\bgetImageData\b/,
    /\bURL\.createObjectURL\s*\(/,
    /\bdocument\.createElement(?:NS)?\s*\([^)]*canvas/i,
    /\.appendChild\s*\(/,
    /\.click\s*\(/,
    /\.download\s*=/,
    /\bviewer\.(?:camera|controls|renderer)\s*=/,
    /\bviewer\.renderer\.[A-Za-z_$][\w$]*\s*=/,
  ];
  for (const pattern of forbiddenAuditOperations) {
    assert(
      !pattern.test(auditBlock),
      "R2S numeric audit block must not render or mutate production",
      { pattern: String(pattern) },
    );
  }
  const productionPatterns = [
    /new THREE\.PerspectiveCamera\(42,\s*1,\s*\.1,\s*260\)/,
    /new THREE\.WebGLRenderer\(\{\s*antialias:\s*true,\s*alpha:\s*true\s*\}\)/,
    /new controlsMod\.OrbitControls\(camera,\s*renderer\.domElement\)/,
    /toneMapping\s*=\s*THREE\.ACESFilmicToneMapping/,
    /toneMappingExposure\s*=\s*1\.05/,
    /requestAnimationFrame\(animate\)/,
  ];
  for (const pattern of productionPatterns) {
    assert(
      pattern.test(html),
      "production viewer invariant is missing",
      { pattern: String(pattern) },
    );
  }
  assert(
    fs.statSync(FORMAL_GLB_PATH).size === FORMAL_GLB_BYTES &&
      sha256(FORMAL_GLB_PATH) === FORMAL_GLB_SHA256,
    "formal production GLB must remain byte-identical",
    {
      path: FORMAL_GLB_PATH,
      expectedBytes: FORMAL_GLB_BYTES,
      actualBytes: fs.statSync(FORMAL_GLB_PATH).size,
      expectedSha256: FORMAL_GLB_SHA256,
      actualSha256: sha256(FORMAL_GLB_PATH),
    },
  );
  return {
    productionViewerPatterns: productionPatterns.length,
    formalGlbBytes: FORMAL_GLB_BYTES,
    formalGlbSha256: FORMAL_GLB_SHA256,
  };
}

function recomputeExpectedShots() {
  const minimum = FROZEN_SECTION_BOUNDS.minimum;
  const maximum = FROZEN_SECTION_BOUNDS.maximum;
  const center = [
    Math.fround((minimum[0] + maximum[0]) / 2),
    Math.fround((minimum[1] + maximum[1]) / 2),
    Math.fround((minimum[2] + maximum[2]) / 2),
  ];
  const height = maximum[2] - minimum[2];
  const width = maximum[1] - minimum[1];
  const maximumSpan = Math.max(height, width);
  const standardLocation = [
    Math.fround(maximum[0] + 1.8 * maximumSpan),
    center[1],
    center[2],
  ];
  const standardScale = Math.max(
    1.05 * height,
    1.22 * width,
  );
  const localTarget = [
    maximum[0],
    Math.fround(
      maximum[1] - Math.max(0.035 * width, 0.35),
    ),
    Math.fround(minimum[2] + 0.58 * height),
  ];
  const localLocation = [
    standardLocation[0],
    center[1],
    localTarget[2],
  ];
  return {
    frozenBounds: {
      minimum: minimum.slice(),
      maximum: maximum.slice(),
      center,
      height,
      width,
    },
    shots: {
      standard_ortho_section_1x: {
        location: standardLocation,
        target: center,
        orthoScale: standardScale,
        actualAssetGeometry: true,
        diagnosticOnly: false,
        thicknessScale: 1,
      },
      local_layer_closeup_1x: {
        location: localLocation,
        target: localTarget,
        orthoScale: Math.max(3.6, 0.24 * width),
        actualAssetGeometry: true,
        diagnosticOnly: false,
        thicknessScale: 1,
      },
      six_family_material_board_with_midgray: {
        location: [12, 0, 0],
        target: [0, 0, 0],
        orthoScale: 9.6,
        actualAssetGeometry: false,
        diagnosticOnly: true,
        thicknessScale: null,
      },
    },
  };
}

function assertControlPoints(record, expectedCount, message) {
  const entries = Object.entries(record || {});
  assert(
    entries.length === expectedCount,
    `${message} count`,
    { expectedCount, actualCount: entries.length },
  );
  for (const [name, point] of entries) {
    assert(
      Array.isArray(point) &&
        point.length === 3 &&
        point.every(Number.isFinite),
      `${message} finite projected point`,
      { name, point },
    );
  }
}

function verifyAllR2RCaptureRecords(
  r2rContract,
  r2rManifest,
  recomputed,
) {
  assertDeepEqual(
    r2rContract.scene_contract.resolution,
    [1920, 1080],
    "R2R registered resolution",
  );
  assertDeepEqual(
    r2rManifest.scene_contract.resolution,
    [1920, 1080],
    "R2R captured resolution",
  );
  assert(
    r2rContract.scene_contract.resolution_percentage === 100 &&
      r2rManifest.scene_contract.resolution_percentage === 100 &&
      r2rContract.capture_contract.repeat_count === 2 &&
      r2rContract.capture_contract.fixed_seed === 20260719 &&
      r2rManifest.capture_count === 12 &&
      r2rManifest.captures.length === 12 &&
      r2rManifest.source_mutation_detected === false,
    "R2R resolution, repeat, seed, capture count, and source lock",
    {
      contractScene: r2rContract.scene_contract,
      captureContract: r2rContract.capture_contract,
      manifestCaptureCount: r2rManifest.capture_count,
      sourceMutationDetected:
        r2rManifest.source_mutation_detected,
    },
  );
  const shotIds = Object.keys(recomputed.shots);
  assertDeepEqual(
    r2rContract.capture_contract.shots.map((shot) => shot.id),
    shotIds,
    "R2R shot order",
  );
  const expectedCaptureIds = [];
  for (const engineId of ["eevee", "cycles"]) {
    for (const repeatIndex of [1, 2]) {
      for (const shotId of shotIds) {
        expectedCaptureIds.push(
          `${engineId}.repeat_${String(repeatIndex).padStart(
            2,
            "0",
          )}.${shotId}`,
        );
      }
    }
  }
  assertDeepEqual(
    r2rManifest.captures.map((capture) => capture.id),
    expectedCaptureIds,
    "all engine/repeat/shot capture records",
  );
  const referenceByShot = new Map();
  for (const capture of r2rManifest.captures) {
    const expected = recomputed.shots[capture.shot_id];
    assert(expected, "capture shot must be registered", capture);
    assert(
      capture.id ===
        `${capture.engine_id}.repeat_${String(
          capture.repeat_index,
        ).padStart(2, "0")}.${capture.shot_id}` &&
        ["eevee", "cycles"].includes(capture.engine_id) &&
        [1, 2].includes(capture.repeat_index) &&
        capture.engine_settings?.engine_id ===
          capture.engine_id &&
        capture.engine_settings?.fixed_seed === 20260719,
      `${capture.id} exact engine/repeat/seed record`,
      capture.engine_settings,
    );
    const engineContract =
      r2rContract.capture_contract.engines[capture.engine_id];
    assert(
      capture.engine_settings.blender_engine ===
        engineContract.blender_engine,
      `${capture.id} Blender engine`,
      capture.engine_settings,
    );
    if (capture.engine_id === "eevee") {
      assert(
        capture.engine_settings.taa_render_samples ===
          engineContract.taa_render_samples,
        `${capture.id} Eevee samples`,
        capture.engine_settings,
      );
    } else {
      assert(
        capture.engine_settings.samples ===
          engineContract.samples &&
          capture.engine_settings.adaptive_sampling ===
            engineContract.adaptive_sampling &&
          capture.engine_settings.denoise ===
            engineContract.denoise &&
          capture.engine_settings.denoiser ===
            engineContract.denoiser &&
          capture.engine_settings.requested_backend ===
            engineContract.device &&
          capture.engine_settings.strict_no_cpu_fallback ===
            engineContract.strict_no_cpu_fallback,
        `${capture.id} Cycles strict GPU contract`,
        capture.engine_settings,
      );
    }
    assert(
      capture.shot_formula.camera_formula_applied === true &&
        capture.shot_formula.actual_asset_geometry ===
          expected.actualAssetGeometry &&
        capture.shot_formula.thickness_scale ===
          expected.thicknessScale,
      `${capture.id} applied shot formula flags`,
      capture.shot_formula,
    );
    assertVectorNear(
      capture.shot_formula.bounds.minimum,
      recomputed.frozenBounds.minimum,
      0,
      `${capture.id} frozen minimum bounds`,
    );
    assertVectorNear(
      capture.shot_formula.bounds.maximum,
      recomputed.frozenBounds.maximum,
      0,
      `${capture.id} frozen maximum bounds`,
    );
    assertNear(
      capture.shot_formula.bounds.height,
      recomputed.frozenBounds.height,
      0,
      `${capture.id} frozen height`,
    );
    assertNear(
      capture.shot_formula.bounds.width,
      recomputed.frozenBounds.width,
      0,
      `${capture.id} frozen width`,
    );
    assertVectorNear(
      capture.shot_formula.location,
      expected.location,
      1e-6,
      `${capture.id} independently recomputed formula location`,
    );
    assertVectorNear(
      capture.shot_formula.target,
      expected.target,
      1e-6,
      `${capture.id} independently recomputed formula target`,
    );
    assertNear(
      capture.shot_formula.ortho_scale,
      expected.orthoScale,
      1e-6,
      `${capture.id} independently recomputed formula scale`,
    );
    assert(
      capture.camera.object ===
        "CAM_R2Q_SECTION_ORTHO_CANDIDATE" &&
        capture.camera.type === "ORTHO",
      `${capture.id} Blender orthographic camera identity`,
      capture.camera,
    );
    assertVectorNear(
      capture.camera.location,
      expected.location,
      1e-6,
      `${capture.id} camera location`,
    );
    assertNear(
      capture.camera.ortho_scale,
      expected.orthoScale,
      1e-6,
      `${capture.id} camera ortho scale`,
    );
    assertNear(
      capture.camera.clip_start,
      0.05,
      1e-6,
      `${capture.id} camera near`,
    );
    assertNear(
      capture.camera.clip_end,
      1000,
      1e-6,
      `${capture.id} camera far`,
    );
    const independentlyComputedCamera = independentBlenderCamera(
      expected.location,
      expected.target,
      capture.camera.ortho_scale,
      capture.camera.clip_start,
      capture.camera.clip_end,
    );
    assertQuaternionNear(
      capture.camera.rotation_quaternion,
      independentlyComputedCamera.quaternion,
      1e-6,
      `${capture.id} independently recomputed quaternion`,
    );
    assertArrayNear(
      capture.camera.matrix_world,
      independentlyComputedCamera.matrixWorld,
      1e-6,
      `${capture.id} independently recomputed matrix_world`,
    );
    assertArrayNear(
      capture.camera.view_matrix,
      invertRigidMatrix4(capture.camera.matrix_world),
      1e-6,
      `${capture.id} independently inverted view matrix`,
    );
    assertArrayNear(
      capture.camera.projection_matrix,
      independentlyComputedCamera.projectionMatrix,
      1e-6,
      `${capture.id} independently recomputed projection matrix`,
    );
    assertControlPoints(
      capture.camera.control_points_px,
      capture.shot_id ===
        "six_family_material_board_with_midgray"
        ? 63
        : 90,
      `${capture.id} control points`,
    );
    assert(
      capture.beauty?.width === 1920 &&
        capture.beauty?.height === 1080 &&
        capture.beauty?.color_mode === "RGBA" &&
        capture.beauty?.transparent_film === true &&
        capture.mask?.threshold === 0.5 &&
        capture.mask?.derived_from_beauty_alpha === true,
      `${capture.id} output resolution and mask contract`,
      { beauty: capture.beauty, mask: capture.mask },
    );
    const reference = referenceByShot.get(capture.shot_id);
    const cameraComparable = {
      location: capture.camera.location,
      rotation_quaternion:
        capture.camera.rotation_quaternion,
      ortho_scale: capture.camera.ortho_scale,
      clip_start: capture.camera.clip_start,
      clip_end: capture.camera.clip_end,
      matrix_world: capture.camera.matrix_world,
      view_matrix: capture.camera.view_matrix,
      projection_matrix: capture.camera.projection_matrix,
      control_points_px: capture.camera.control_points_px,
      material_rois_px: capture.camera.material_rois_px,
      midgray_roi_px: capture.camera.midgray_roi_px,
    };
    if (reference) {
      assertDeepEqual(
        cameraComparable,
        reference,
        `${capture.id} camera matrices/quaternion/control points must match every engine and repeat`,
      );
    } else {
      referenceByShot.set(capture.shot_id, cameraComparable);
    }
  }
  return {
    captureRecordCount: r2rManifest.captures.length,
    engineCount: 2,
    repeatCount: 2,
    shotCount: 3,
    independentlyRecomputedCameraRecords:
      r2rManifest.captures.length,
    crossEngineRepeatControlPointSets:
      referenceByShot.size,
  };
}

function verifyEnabledContract(capability, manifest) {
  assertDeepEqual(
    fileFingerprint(R2R_CONTRACT_PATH),
    {
      bytes: EXPECTED_R2R_CONTRACT_BYTES,
      sha256: EXPECTED_R2R_CONTRACT_SHA256,
    },
    "fixed R2R capture contract bytes",
  );
  assertDeepEqual(
    fileFingerprint(R2R_MANIFEST_PATH),
    {
      bytes: EXPECTED_R2R_MANIFEST_BYTES,
      sha256: EXPECTED_R2R_MANIFEST_SHA256,
    },
    "fixed R2R capture manifest bytes",
  );
  const r2rContract = readJson(R2R_CONTRACT_PATH);
  const r2rManifest = readJson(R2R_MANIFEST_PATH);
  const recomputed = recomputeExpectedShots();
  const captureRecords = verifyAllR2RCaptureRecords(
    r2rContract,
    r2rManifest,
    recomputed,
  );
  assert(
    capability.auditMode === true &&
      capability.captureEligible === false &&
      capability.colorState === "pending_preapproval" &&
      capability.numericManifestAvailable === true &&
      capability.imageCaptureAvailable === false &&
      capability.beautyCaptureAvailable === false &&
      capability.maskCaptureAvailable === false,
    "dual-gated capability must expose numeric preflight only",
    capability,
  );
  assertDeepEqual(
    capability.blockers,
    [
      "color_management_preapproval_required",
      "light_photometry_preapproval_required",
    ],
    "enabled capability exact blockers",
  );
  assert(
    capability.gates.query.matches === true &&
      capability.gates.query.valueCount === 1 &&
      capability.gates.preInjectedWindowToken.matches === true &&
      capability.gates.preInjectedWindowToken.wasPresent === true &&
      capability.gates.enabled === true &&
      capability.gates.evaluatedAtModuleLoad === true,
    "both exact gates are required",
    capability.gates,
  );
  const contract = capability.auditContract;
  assert(
    contract.auditMode === true &&
      contract.captureEligible === false &&
      contract.colorState === "pending_preapproval" &&
      contract.camera.threeImplementation ===
        "THREE.OrthographicCamera" &&
      contract.camera.independentFromProductionCamera === true &&
      contract.camera.productionCameraReferenceUsed === false &&
      contract.camera.runtimeBoundsUsed === false &&
      contract.resolutionCssPixels[0] === 1920 &&
      contract.resolutionCssPixels[1] === 1080 &&
      contract.devicePixelRatio === 1 &&
      contract.fileFormat === "PNG" &&
      contract.colorMode === "RGBA" &&
      contract.transparentFilm === true &&
      contract.fixedSeed === 20260719 &&
      contract.repeatCount === 2,
    "fixed independent numeric orthographic audit contract",
    contract,
  );
  assertDeepEqual(
    contract.camera.shotFormulas,
    Object.fromEntries(
      r2rContract.capture_contract.shots.map((shot) => [
        shot.id,
        shot.camera_formula,
      ]),
    ),
    "R2R three-shot formulas must remain authoritative",
  );
  assertDeepEqual(
    contract.comparisonThresholds,
    r2rContract.comparison_contract.thresholds,
    "all original R2R thresholds must remain byte-for-byte numeric equal",
  );
  assertDeepEqual(
    contract.comparisonContract,
    {
      maskThreshold:
        r2rContract.comparison_contract.mask_threshold,
      interiorErosionPixels:
        r2rContract.comparison_contract
          .interior_erosion_pixels,
      comparisonColorSpace:
        r2rContract.comparison_contract
          .comparison_color_space,
      thresholds: r2rContract.comparison_contract.thresholds,
      aggregation:
        r2rContract.comparison_contract.aggregation,
      notEvaluatedPolicy:
        r2rContract.comparison_contract.not_evaluated_policy,
      missingOrInvalidInputPolicy:
        r2rContract.comparison_contract
          .missing_or_invalid_input_policy,
      thresholdChangeAfterCaptureForbidden:
        r2rContract.comparison_contract
          .threshold_change_after_capture_forbidden,
    },
    "R2R mask, erosion, aggregation, and fail-closed policies must remain exact",
  );
  assert(
    contract.thresholdChangeAllowed === false &&
      contract.notEvaluatedPolicy.includes("prevents"),
    "threshold relaxation and not-evaluated PASS are forbidden",
    contract,
  );

  assert(
    contract.lights.requiredCount === 4 &&
      contract.lights.items.length === 4 &&
      contract.lights.dynamicBoundsFocusUsed === false &&
      contract.lights.productionLightsReplaced === false &&
      contract.lights.coordinateMapping === "(x,y,z)->(x,z,-y)",
    "P40 audit mapping must contain four fixed lights",
    contract.lights,
  );
  const expectedLights = r2rManifest.scene_contract.lights;
  assertDeepEqual(
    contract.lights.requiredNames,
    expectedLights.map((light) => light.name),
    "P40 light names and order",
  );
  for (const expected of expectedLights) {
    const actual = contract.lights.items.find(
      (light) => light.name === expected.name,
    );
    assert(actual, `missing ${expected.name}`);
    assert(
      actual.blender.type === expected.type &&
        actual.three.type ===
          (expected.type === "SUN"
            ? "DirectionalLight"
            : "RectAreaLight"),
      `${expected.name} type mapping`,
      actual,
    );
    assertDeepEqual(
      actual.blender.position,
      expected.location,
      `${expected.name} Blender position`,
    );
    assertDeepEqual(
      actual.blender.direction,
      expected.direction,
      `${expected.name} Blender direction`,
    );
    assertDeepEqual(
      actual.blender.colorLinearRgb,
      expected.color,
      `${expected.name} Blender color`,
    );
    assertDeepEqual(
      actual.three.colorLinearRgb,
      expected.color,
      `${expected.name} Three linear color`,
    );
    assertNear(
      actual.blender.energy,
      expected.energy,
      0,
      `${expected.name} source energy`,
    );
    assertVectorNear(
      actual.three.position,
      blenderToThree(expected.location),
      0,
      `${expected.name} Three position`,
    );
    assertVectorNear(
      actual.three.direction,
      blenderToThree(expected.direction),
      0,
      `${expected.name} Three direction`,
    );
    const expectedThreePosition = blenderToThree(
      expected.location,
    );
    const expectedThreeDirection = blenderToThree(
      expected.direction,
    );
    assertVectorNear(
      actual.three.target,
      vectorAdd(
        expectedThreePosition,
        expectedThreeDirection,
      ),
      0,
      `${expected.name} Three target equals position plus direction`,
    );
    assert(
      actual.three.intensity === null &&
        actual.three.intensityMappingState ===
          "pending_preapproval" &&
        actual.three.sunAngleMappingState ===
          (expected.type === "SUN"
            ? "pending_preapproval"
            : "not_applicable") &&
        actual.blender.sunAngleRad ===
          (expected.type === "SUN" ? expected.angle : null) &&
        actual.three.isLight !== true &&
        actual.three.isDirectionalLight !== true &&
        actual.three.isRectAreaLight !== true &&
        typeof actual.three.dispose !== "function",
      `${expected.name} photometry must fail closed`,
      actual.three,
    );
    assertDeepEqual(
      actual.coordinateMapping,
      {
        formula: "(x,y,z)->(x,z,-y)",
        sourcePosition: expected.location,
        mappedPosition: expectedThreePosition,
        sourceDirection: expected.direction,
        mappedDirection: expectedThreeDirection,
      },
      `${expected.name} exact coordinate mapping`,
    );
  }
  const top = contract.lights.items.find(
    (light) => light.name === "P40_NEUTRAL_TOP",
  );
  const expectedTop = expectedLights.find(
    (light) => light.name === "P40_NEUTRAL_TOP",
  );
  const expectedArea =
    Math.PI * Math.pow(expectedTop.size / 2, 2);
  const expectedSquareSide = Math.sqrt(expectedArea);
  assertDeepEqual(
    contract.lights.worldReference,
    {
      colorLinearRgba: [0.12, 0.12, 0.12, 1],
      strength: 0.72,
      threeMappingState: "pending_preapproval",
      ambientLightSubstitutionApproved: false,
    },
    "P40 exact world mapping remains pending",
  );
  assert(
    top.blender.shape === "DISK" &&
      top.blender.diskDiameterM === expectedTop.size &&
      top.blender.sunAngleRad === null &&
      top.three.type === "RectAreaLight" &&
      top.three.intensity === null &&
      top.three.intensityMappingState ===
        "pending_preapproval" &&
      top.three.sunAngleMappingState === "not_applicable" &&
      top.three.equalAreaSquareProxy.equalArea === true &&
      top.three.equalAreaSquareProxy.limitations.length === 3,
    "TOP must be an explicitly limited equal-area RectAreaLight proxy",
    top,
  );
  assertExactKeys(
    top.three.equalAreaSquareProxy,
    [
      "implementation",
      "sourceShape",
      "sourceDiskDiameterM",
      "sourceDiskAreaM2",
      "widthM",
      "heightM",
      "equalArea",
      "limitations",
    ],
    "TOP equal-area proxy",
  );
  assertDeepEqual(
    {
      implementation:
        top.three.equalAreaSquareProxy.implementation,
      sourceShape:
        top.three.equalAreaSquareProxy.sourceShape,
      sourceDiskDiameterM:
        top.three.equalAreaSquareProxy.sourceDiskDiameterM,
      equalArea: top.three.equalAreaSquareProxy.equalArea,
      limitations:
        top.three.equalAreaSquareProxy.limitations,
    },
    {
      implementation: "THREE.RectAreaLight",
      sourceShape: "DISK",
      sourceDiskDiameterM: expectedTop.size,
      equalArea: true,
      limitations: [
        "equal emitting area only; disk and square edge silhouettes differ",
        "angular emission and edge falloff equivalence is not approved",
        "Blender AREA power does not map directly to Three intensity",
      ],
    },
    "TOP exact proxy method and limitations",
  );
  assertNear(
    top.three.equalAreaSquareProxy.sourceDiskAreaM2,
    expectedArea,
    1e-12,
    "TOP disk area",
  );
  assertNear(
    top.three.equalAreaSquareProxy.widthM,
    expectedSquareSide,
    1e-12,
    "TOP square width",
  );
  assertNear(
    top.three.equalAreaSquareProxy.heightM,
    expectedSquareSide,
    1e-12,
    "TOP square height",
  );

  assert(
    manifest.auditMode === true &&
      manifest.captureEligible === false &&
      manifest.colorState === "pending_preapproval" &&
      manifest.deterministic === true &&
      manifest.resolutionCssPixels[0] === 1920 &&
      manifest.resolutionCssPixels[1] === 1080 &&
      manifest.devicePixelRatio === 1 &&
      manifest.shots.length === 3 &&
      manifest.imageCapture.apiExposed === false &&
      manifest.imageCapture.captureAttempted === false &&
      manifest.imageCapture.beautyFiles.length === 0 &&
      manifest.imageCapture.maskFiles.length === 0 &&
      manifest.imageCapture.blocker ===
        "color_management_preapproval_required",
    "numeric shot manifest must not fake image capture",
    manifest,
  );
  assertDeepEqual(
    manifest.frozenSectionBoundsBlender,
    recomputed.frozenBounds,
    "numeric manifest frozen bounds and derived dimensions",
  );
  const expectedShotIds = r2rContract.capture_contract.shots.map(
    (shot) => shot.id,
  );
  assertDeepEqual(
    manifest.shots.map((shot) => shot.id),
    expectedShotIds,
    "three R2R shot IDs",
  );
  for (const expectedShot of r2rContract.capture_contract.shots) {
    const actual = manifest.shots.find(
      (shot) => shot.id === expectedShot.id,
    );
    const independentlyExpected =
      recomputed.shots[expectedShot.id];
    assert(
      actual.formula === expectedShot.camera_formula &&
        actual.actualAssetGeometry ===
          independentlyExpected.actualAssetGeometry &&
        actual.diagnosticOnly ===
          independentlyExpected.diagnosticOnly &&
        actual.thicknessScale ===
          independentlyExpected.thicknessScale &&
        actual.camera.threeImplementation ===
          "THREE.OrthographicCamera" &&
        actual.camera.independentFromProductionCamera === true &&
        actual.camera.three.isCamera !== true &&
        actual.camera.three.isOrthographicCamera !== true &&
        typeof actual.camera.three.updateProjectionMatrix !==
          "function",
      `${expectedShot.id} numeric-only orthographic formula`,
      actual,
    );
    assertExactKeys(
      actual.camera.three,
      [
        "location",
        "target",
        "up",
        "horizontalOrthoScale",
        "frustum",
      ],
      `${expectedShot.id} numeric-only Three camera record`,
    );
    assertVectorNear(
      actual.camera.blender.location,
      independentlyExpected.location,
      0,
      `${expectedShot.id} independently recomputed Blender location`,
    );
    assertVectorNear(
      actual.camera.blender.target,
      independentlyExpected.target,
      0,
      `${expectedShot.id} independently recomputed Blender target`,
    );
    assertNear(
      actual.camera.blender.horizontalOrthoScale,
      independentlyExpected.orthoScale,
      0,
      `${expectedShot.id} independently recomputed horizontal ortho scale`,
    );
    assertVectorNear(
      actual.camera.three.location,
      blenderToThree(independentlyExpected.location),
      0,
      `${expectedShot.id} Three location`,
    );
    assertVectorNear(
      actual.camera.three.target,
      blenderToThree(independentlyExpected.target),
      0,
      `${expectedShot.id} Three target`,
    );
    assertVectorNear(
      actual.camera.three.up,
      [0, 1, 0],
      0,
      `${expectedShot.id} Three up`,
    );
    assertNear(
      actual.camera.three.horizontalOrthoScale,
      independentlyExpected.orthoScale,
      0,
      `${expectedShot.id} Three horizontal scale`,
    );
    const scale = independentlyExpected.orthoScale;
    const aspect = 1920 / 1080;
    const expectedFrustum = {
      left: -scale / 2,
      right: scale / 2,
      top: scale / (2 * aspect),
      bottom: -scale / (2 * aspect),
      near: 0.05,
      far: 1000,
    };
    assertDeepEqual(
      actual.camera.three.frustum,
      expectedFrustum,
      `${expectedShot.id} horizontal-scale Three frustum`,
    );
  }
  assert(
    contract.colorManagement.colorState ===
      "pending_preapproval" &&
      contract.colorManagement.captureEligible === false &&
      contract.colorManagement.approvedEquivalentCurveOrLut ===
        null &&
      contract.colorManagement
        .threeBuiltInAgxDefaultContrastIsApprovedEquivalent ===
        false &&
      contract.colorManagement.blocker ===
        "AgX Medium Low equivalent curve/LUT is not pre-approved" &&
      contract.colorManagement.productionRendererUnchanged
        .outputColorSpace === "THREE.SRGBColorSpace" &&
      contract.productionIsolation.mutationsPerformed === false &&
      contract.productionIsolation.mutableReferencesShared === false &&
      contract.productionIsolation.productionToneMapping ===
        "THREE.ACESFilmicToneMapping" &&
      contract.productionIsolation.productionToneMappingExposure ===
        1.05,
    "color approval blocker and production isolation",
    {
      color: contract.colorManagement,
      production: contract.productionIsolation,
    },
  );
  return {
    shotCount: manifest.shots.length,
    lightCount: contract.lights.items.length,
    thresholdCount: Object.keys(
      contract.comparisonThresholds,
    ).length,
    colorState: capability.colorState,
    captureEligible: capability.captureEligible,
    numericOnlyCameraImplementation: true,
    actualAuditCameraObjectsCreated: false,
    actualAuditLightObjectsCreated: false,
    resolutionCssPixels: manifest.resolutionCssPixels,
    devicePixelRatio: manifest.devicePixelRatio,
    captureRecords,
  };
}

async function flushAnimationFrames(page, count = 4) {
  await page.evaluate(
    (frameCount) =>
      new Promise((resolve) => {
        let remaining = frameCount;
        const next = () => {
          remaining -= 1;
          if (remaining <= 0) resolve();
          else requestAnimationFrame(next);
        };
        requestAnimationFrame(next);
      }),
    count,
  );
}

async function waitForProductionReady(page) {
  await page.waitForFunction(
    () => {
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const controller = window.__BF3D_STRUCTURAL_REVIEW__;
      const state = controller?.getState?.();
      return (
        viewer?.camera?.isPerspectiveCamera === true &&
        viewer?.controls &&
        viewer?.renderer &&
        viewer?.scene &&
        viewer?.THREE &&
        state?.status === "ready" &&
        state?.mode === "operational" &&
        state?.sensor_count === 115 &&
        viewer.renderer.toneMapping ===
          viewer.THREE.ACESFilmicToneMapping &&
        viewer.renderer.outputColorSpace ===
          viewer.THREE.SRGBColorSpace &&
        viewer.renderer.toneMappingExposure === 1.05
      );
    },
    null,
    { timeout: 90_000 },
  );
  await page.waitForTimeout(1200);
  await flushAnimationFrames(page, 6);
}

async function runProductionIsolationCase(
  browser,
  baseUrl,
  gateCase,
) {
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
  });
  await installProductionInstrumentation(context, gateCase);
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  try {
    await page.goto(
      `${baseUrl}/frontend_dashboard_v3.server.html${buildQuery(
        gateCase.queryValues,
        true,
      )}#overview`,
      {
        waitUntil: "domcontentloaded",
        timeout: 90_000,
      },
    );
    await waitForProductionReady(page);
    const initial = await page.evaluate(() => {
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const controller = window.__BF3D_STRUCTURAL_REVIEW__;
      const instrument =
        window.__BF3D_R2S_TEST_INSTRUMENTATION__;
      const collectScene = () => {
        const nodes = [];
        viewer.scene.traverse((object) => nodes.push(object));
        const nodeIndex = new WeakMap(
          nodes.map((object, index) => [object, index]),
        );
        const lights = nodes.filter(
          (object) => object.isLight === true,
        );
        const geometries = [];
        const materials = [];
        const textures = [];
        const geometrySet = new Set();
        const materialSet = new Set();
        const textureSet = new Set();
        for (const object of nodes) {
          if (
            object.geometry &&
            !geometrySet.has(object.geometry)
          ) {
            geometrySet.add(object.geometry);
            geometries.push(object.geometry);
          }
          const objectMaterials = (
            Array.isArray(object.material)
              ? object.material
              : [object.material]
          ).filter(Boolean);
          for (const material of objectMaterials) {
            if (!materialSet.has(material)) {
              materialSet.add(material);
              materials.push(material);
            }
            for (const value of Object.values(material)) {
              if (
                value?.isTexture &&
                !textureSet.has(value)
              ) {
                textureSet.add(value);
                textures.push(value);
              }
            }
          }
        }
        return {
          nodes,
          nodeIndex,
          lights,
          geometries,
          materials,
          textures,
        };
      };
      const describeSceneValue = (value) => {
        if (value === null || value === undefined) return null;
        if (value.isColor) {
          return {
            type: "Color",
            value: value.toArray(),
          };
        }
        if (value.isTexture) {
          return {
            type: value.type,
            name: value.name,
            colorSpace: value.colorSpace,
            mapping: value.mapping,
          };
        }
        if (value.isFog) {
          return {
            type: value.type,
            color: value.color?.toArray?.() || null,
            near: value.near,
            far: value.far,
            density: value.density ?? null,
          };
        }
        return {
          type: value.type || value.constructor?.name || null,
        };
      };
      const sceneAtBaseline = collectScene();
      const renderTargetAtBaseline =
        viewer.renderer.getRenderTarget();
      const refs = {
        viewer,
        camera: viewer.camera,
        controls: viewer.controls,
        renderer: viewer.renderer,
        rendererDomElement: viewer.renderer.domElement,
        rendererSetAnimationLoop:
          viewer.renderer.setAnimationLoop,
        rendererXr: viewer.renderer.xr,
        scene: viewer.scene,
        sceneBackground: viewer.scene.background,
        sceneEnvironment: viewer.scene.environment,
        sceneFog: viewer.scene.fog,
        renderTarget: renderTargetAtBaseline,
        sceneNodes: sceneAtBaseline.nodes,
        lights: sceneAtBaseline.lights,
        geometries: sceneAtBaseline.geometries,
        materials: sceneAtBaseline.materials,
        textures: sceneAtBaseline.textures,
      };
      const sameReferenceArray = (actual, expected) =>
        actual.length === expected.length &&
        actual.every(
          (value, index) => value === expected[index],
        );
      const identity = () => {
        const currentScene = collectScene();
        return {
          viewer: window.__BF_CAD_FURNACE_VIEWER ===
            refs.viewer,
          camera: viewer.camera === refs.camera,
          controls: viewer.controls === refs.controls,
          renderer: viewer.renderer === refs.renderer,
          rendererDomElement:
            viewer.renderer.domElement ===
            refs.rendererDomElement,
          rendererSetAnimationLoop:
            viewer.renderer.setAnimationLoop ===
            refs.rendererSetAnimationLoop,
          rendererXr:
            viewer.renderer.xr === refs.rendererXr,
          rendererRenderTarget:
            viewer.renderer.getRenderTarget() ===
            refs.renderTarget,
          scene: viewer.scene === refs.scene,
          sceneBackground:
            viewer.scene.background === refs.sceneBackground,
          sceneEnvironment:
            viewer.scene.environment ===
            refs.sceneEnvironment,
          sceneFog: viewer.scene.fog === refs.sceneFog,
          sceneNodes: sameReferenceArray(
            currentScene.nodes,
            refs.sceneNodes,
          ),
          lights: sameReferenceArray(
            currentScene.lights,
            refs.lights,
          ),
          geometries: sameReferenceArray(
            currentScene.geometries,
            refs.geometries,
          ),
          materials: sameReferenceArray(
            currentScene.materials,
            refs.materials,
          ),
          textures: sameReferenceArray(
            currentScene.textures,
            refs.textures,
          ),
        };
      };
      const snapshot = () => {
        const THREE = viewer.THREE;
        const renderer = viewer.renderer;
        const sceneData = collectScene();
        const viewport = renderer.getViewport(
          new THREE.Vector4(),
        );
        const currentViewport =
          typeof renderer.getCurrentViewport === "function"
            ? renderer.getCurrentViewport(
                new THREE.Vector4(),
              )
            : viewport;
        const scissor = renderer.getScissor(
          new THREE.Vector4(),
        );
        const size = renderer.getSize(new THREE.Vector2());
        const drawingBufferSize = renderer.getDrawingBufferSize(
          new THREE.Vector2(),
        );
        const clearColor = new THREE.Color();
        renderer.getClearColor(clearColor);
        const renderTarget = renderer.getRenderTarget();
        const topology = sceneData.nodes.map(
          (object, index) => ({
            index,
            parentIndex:
              object.parent === null
                ? null
                : sceneData.nodeIndex.get(object.parent),
            name: object.name,
            type: object.type,
            isScene: object.isScene === true,
            isGroup: object.isGroup === true,
            isMesh: object.isMesh === true,
            isLight: object.isLight === true,
            childrenCount: object.children.length,
          }),
        );
        const lights = sceneData.lights.map((light) => ({
          name: light.name,
          type: light.type,
          visible: light.visible,
          intensity: light.intensity,
          color: light.color?.toArray?.() || null,
          position: light.position.toArray(),
          targetIndex: light.target
            ? sceneData.nodeIndex.get(light.target) ?? null
            : null,
          targetPosition:
            light.target?.position?.toArray?.() || null,
          castShadow: light.castShadow,
          angle: light.angle ?? null,
          distance: light.distance ?? null,
          decay: light.decay ?? null,
          width: light.width ?? null,
          height: light.height ?? null,
        }));
        const stable = {
          camera: {
            type: viewer.camera.type,
            isPerspectiveCamera:
              viewer.camera.isPerspectiveCamera === true,
            isOrthographicCamera:
              viewer.camera.isOrthographicCamera === true,
            position: viewer.camera.position.toArray(),
            quaternion: viewer.camera.quaternion.toArray(),
            scale: viewer.camera.scale.toArray(),
            up: viewer.camera.up.toArray(),
            near: viewer.camera.near,
            far: viewer.camera.far,
            fov: viewer.camera.fov,
            zoom: viewer.camera.zoom,
            aspect: viewer.camera.aspect,
            matrix: viewer.camera.matrix.toArray(),
            matrixWorld: viewer.camera.matrixWorld.toArray(),
            matrixWorldInverse:
              viewer.camera.matrixWorldInverse.toArray(),
            projectionMatrix:
              viewer.camera.projectionMatrix.toArray(),
            projectionMatrixInverse:
              viewer.camera.projectionMatrixInverse.toArray(),
            layersMask: viewer.camera.layers.mask,
          },
          controls: {
            type: viewer.controls.constructor.name,
            enabled: viewer.controls.enabled,
            target: viewer.controls.target.toArray(),
            enableDamping: viewer.controls.enableDamping,
            dampingFactor: viewer.controls.dampingFactor,
            enablePan: viewer.controls.enablePan,
            enableRotate: viewer.controls.enableRotate,
            enableZoom: viewer.controls.enableZoom,
            minDistance: viewer.controls.minDistance,
            maxDistance: viewer.controls.maxDistance,
            minPolarAngle: viewer.controls.minPolarAngle,
            maxPolarAngle: viewer.controls.maxPolarAngle,
            minAzimuthAngle: viewer.controls.minAzimuthAngle,
            maxAzimuthAngle: viewer.controls.maxAzimuthAngle,
            polarAngle:
              viewer.controls.getPolarAngle?.() ?? null,
            azimuthalAngle:
              viewer.controls.getAzimuthalAngle?.() ?? null,
          },
          renderer: {
            domElementIsConnected:
              renderer.domElement.isConnected,
            domElementTag: renderer.domElement.tagName,
            outputColorSpace: renderer.outputColorSpace,
            outputColorSpaceMatchesSrgb:
              renderer.outputColorSpace ===
              THREE.SRGBColorSpace,
            toneMapping: renderer.toneMapping,
            toneMappingMatchesAces:
              renderer.toneMapping ===
              THREE.ACESFilmicToneMapping,
            toneMappingExposure:
              renderer.toneMappingExposure,
            pixelRatio: renderer.getPixelRatio(),
            size: size.toArray(),
            drawingBufferSize: drawingBufferSize.toArray(),
            viewport: viewport.toArray(),
            currentViewport: currentViewport.toArray(),
            scissor: scissor.toArray(),
            scissorTest: renderer.getScissorTest(),
            renderTarget:
              renderTarget === null
                ? null
                : {
                    type:
                      renderTarget.type ||
                      renderTarget.constructor?.name ||
                      null,
                    width: renderTarget.width,
                    height: renderTarget.height,
                  },
            autoClear: renderer.autoClear,
            autoClearColor: renderer.autoClearColor,
            autoClearDepth: renderer.autoClearDepth,
            autoClearStencil: renderer.autoClearStencil,
            sortObjects: renderer.sortObjects,
            localClippingEnabled:
              renderer.localClippingEnabled,
            clearColor: clearColor.toArray(),
            clearAlpha: renderer.getClearAlpha(),
            xrEnabled: renderer.xr?.enabled ?? null,
            xrIsPresenting:
              renderer.xr?.isPresenting ?? null,
          },
          scene: {
            topology,
            lights,
            background: describeSceneValue(
              viewer.scene.background,
            ),
            environment: describeSceneValue(
              viewer.scene.environment,
            ),
            fog: describeSceneValue(viewer.scene.fog),
          },
          resources: {
            sceneNodes: sceneData.nodes.length,
            lights: sceneData.lights.length,
            geometries: sceneData.geometries.length,
            materials: sceneData.materials.length,
            textures: sceneData.textures.length,
            rendererGeometries:
              renderer.info.memory.geometries,
            rendererTextures: renderer.info.memory.textures,
            rendererPrograms:
              renderer.info.programs?.length ?? null,
          },
          domCanvases: Array.from(
            document.querySelectorAll("canvas"),
          ).map((canvas, index) => ({
            index,
            id: canvas.id,
            className: canvas.className,
            width: canvas.width,
            height: canvas.height,
            isConnected: canvas.isConnected,
            parentClassName:
              canvas.parentElement?.className || "",
          })),
          controllerState: {
            status: controller.getState().status,
            mode: controller.getState().mode,
            sensorCount:
              controller.getState().sensor_count,
          },
        };
        return {
          stable,
          identity: identity(),
          volatile: {
            rendererFrame: renderer.info.render.frame,
            rendererCalls: renderer.info.render.calls,
            rendererTriangles:
              renderer.info.render.triangles,
            instrumentation: instrument.snapshot(),
          },
        };
      };
      Object.defineProperty(
        window,
        "__BF3D_R2S_PRODUCTION_ISOLATION_TEST__",
        {
          value: Object.freeze({
            snapshot,
            identity,
          }),
          configurable: false,
          writable: false,
        },
      );
      const beforeApi = snapshot();
      const instrumentationBefore = instrument.snapshot();
      instrument.beginAudit();
      let capability;
      let manifest;
      try {
        capability =
          controller.getAuditCaptureCapability();
        manifest = controller.getAuditShotManifest();
      } finally {
        instrument.endAudit();
      }
      const immediate = snapshot();
      const instrumentationAfter = instrument.snapshot();
      return {
        preApp:
          window.__BF3D_R2S_PRE_APP_SNAPSHOT__,
        beforeApi,
        immediate,
        instrumentationBefore,
        instrumentationAfter,
        capability,
        manifest,
        methods: {
          getAuditCaptureCapability:
            typeof controller.getAuditCaptureCapability,
          getAuditShotManifest:
            typeof controller.getAuditShotManifest,
        },
        frozen: {
          capability: Object.isFrozen(capability),
          manifest: Object.isFrozen(manifest),
        },
      };
    });
    await flushAnimationFrames(page, 4);
    const afterRaf = await page.evaluate(
      () =>
        window.__BF3D_R2S_PRODUCTION_ISOLATION_TEST__.snapshot(),
    );
    await page.waitForTimeout(450);
    await flushAnimationFrames(page, 3);
    const delayed = await page.evaluate(
      () =>
        window.__BF3D_R2S_PRODUCTION_ISOLATION_TEST__.snapshot(),
    );
    assert(
      pageErrors.length === 0,
      `${gateCase.label} production isolation page errors`,
      pageErrors,
    );
    return {
      label: gateCase.label,
      ...initial,
      afterRaf,
      delayed,
      pageErrors,
    };
  } finally {
    await context.close();
  }
}

function assertAllIdentityTrue(identity, message) {
  assert(
    Object.values(identity).every(Boolean),
    message,
    identity,
  );
}

function assertProductionIsolationResult(result, enabled) {
  assert(
    result.methods.getAuditCaptureCapability === "function" &&
      result.methods.getAuditShotManifest === "function",
    `${result.label} controller audit API methods`,
    result.methods,
  );
  assert(
    result.preApp.domCanvasCount === 0 &&
      result.preApp.liveObjectUrls === 0 &&
      result.preApp.pendingRaf === 0 &&
      Object.values(result.preApp.counters).every(
        (value) => value === 0,
      ) &&
      Object.values(result.preApp.duringAudit).every(
        (value) => value === 0,
      ),
    `${result.label} instrumentation must start before any app resource`,
    result.preApp,
  );
  assert(
    result.beforeApi.stable.camera.type ===
      "PerspectiveCamera" &&
      result.beforeApi.stable.camera.isPerspectiveCamera ===
        true &&
      result.beforeApi.stable.camera.isOrthographicCamera ===
        false &&
      result.beforeApi.stable.controls.type ===
        "OrbitControls" &&
      result.beforeApi.stable.renderer.toneMappingMatchesAces ===
        true &&
      result.beforeApi.stable.renderer
        .outputColorSpaceMatchesSrgb === true &&
      result.beforeApi.stable.renderer
        .toneMappingExposure === 1.05 &&
      result.beforeApi.stable.renderer.renderTarget === null,
    `${result.label} production camera/controls/ACES/sRGB/render-target invariants`,
    result.beforeApi.stable,
  );
  assertDeepEqual(
    result.immediate.stable,
    result.beforeApi.stable,
    `${result.label} immediate API call must not mutate production runtime`,
  );
  assertDeepEqual(
    result.afterRaf.stable,
    result.beforeApi.stable,
    `${result.label} RAF flush must preserve production runtime`,
  );
  assertDeepEqual(
    result.delayed.stable,
    result.beforeApi.stable,
    `${result.label} delayed async check must preserve production runtime`,
  );
  assertAllIdentityTrue(
    result.beforeApi.identity,
    `${result.label} baseline reference identity`,
  );
  assertAllIdentityTrue(
    result.immediate.identity,
    `${result.label} immediate reference identity`,
  );
  assertAllIdentityTrue(
    result.afterRaf.identity,
    `${result.label} RAF reference identity`,
  );
  assertAllIdentityTrue(
    result.delayed.identity,
    `${result.label} delayed reference identity`,
  );
  const counterNames = Object.keys(
    result.instrumentationBefore.counters,
  );
  assert(
    counterNames.every(
      (name) =>
        result.instrumentationAfter.counters[name] ===
          result.instrumentationBefore.counters[name] &&
        result.instrumentationAfter.duringAudit[name] === 0,
    ) &&
      result.instrumentationAfter.auditDepth === 0 &&
      result.instrumentationAfter.liveObjectUrls ===
        result.instrumentationBefore.liveObjectUrls &&
      result.instrumentationAfter.domCanvasCount ===
        result.instrumentationBefore.domCanvasCount &&
      result.immediate.volatile.rendererFrame ===
        result.beforeApi.volatile.rendererFrame,
    `${result.label} audit calls must not render, capture pixels, create canvases/resources, schedule RAF, create URLs, or download`,
    {
      before: result.instrumentationBefore,
      after: result.instrumentationAfter,
      rendererFrameBefore:
        result.beforeApi.volatile.rendererFrame,
      rendererFrameAfter:
        result.immediate.volatile.rendererFrame,
    },
  );
  assert(
    result.afterRaf.volatile.rendererFrame >
      result.beforeApi.volatile.rendererFrame &&
      result.delayed.volatile.rendererFrame >
        result.afterRaf.volatile.rendererFrame,
    `${result.label} original production RAF/render loop must continue`,
    {
      before: result.beforeApi.volatile.rendererFrame,
      afterRaf: result.afterRaf.volatile.rendererFrame,
      delayed: result.delayed.volatile.rendererFrame,
    },
  );
  assert(
    result.frozen.capability &&
      result.frozen.manifest &&
      result.capability.captureEligible === false &&
      result.manifest.captureEligible === false &&
      result.capability.auditMode === enabled &&
      result.manifest.auditMode === enabled,
    `${result.label} audit mode and capture blocker`,
    {
      capability: result.capability,
      manifest: result.manifest,
      frozen: result.frozen,
    },
  );
  if (enabled) {
    assert(
      result.capability.numericManifestAvailable === true &&
        result.capability.auditContract !== null &&
        result.manifest.shots.length === 3,
      `${result.label} gated numeric-only manifest`,
      result,
    );
  } else {
    assert(
      result.capability.numericManifestAvailable === false &&
        result.capability.auditContract === null &&
        result.manifest.shots.length === 0,
      `${result.label} ungated fail-closed manifest`,
      result,
    );
  }
  return {
    cameraType: result.beforeApi.stable.camera.type,
    controlsType: result.beforeApi.stable.controls.type,
    toneMapping: "THREE.ACESFilmicToneMapping",
    outputColorSpace: "THREE.SRGBColorSpace",
    toneMappingExposure:
      result.beforeApi.stable.renderer.toneMappingExposure,
    sceneNodeCount:
      result.beforeApi.stable.resources.sceneNodes,
    sceneLightCount:
      result.beforeApi.stable.resources.lights,
    geometryCount:
      result.beforeApi.stable.resources.geometries,
    materialCount:
      result.beforeApi.stable.resources.materials,
    textureCount:
      result.beforeApi.stable.resources.textures,
    domCanvasCount:
      result.beforeApi.stable.domCanvases.length,
    referencesUnchanged: true,
    runtimeStateUnchangedAfterRafAndDelay: true,
    auditCaptureSideEffects: 0,
  };
}

function canonicalizeIndependentProductionSnapshot(stable) {
  const normalized = JSON.parse(JSON.stringify(stable));
  const topology = stable.scene.topology;
  normalized.scene.topology = topology
    .map((node) => {
      const parent =
        node.parentIndex === null
          ? null
          : topology[node.parentIndex];
      return {
        name: node.name,
        type: node.type,
        isScene: node.isScene,
        isGroup: node.isGroup,
        isMesh: node.isMesh,
        isLight: node.isLight,
        childrenCount: node.childrenCount,
        parent:
          parent === null
            ? null
            : {
                name: parent.name,
                type: parent.type,
              },
      };
    })
    .sort((a, b) =>
      JSON.stringify(a).localeCompare(JSON.stringify(b)),
    );
  normalized.scene.lights = stable.scene.lights
    .map((light) => {
      const { targetIndex, ...rest } = light;
      return rest;
    })
    .sort((a, b) =>
      JSON.stringify(a).localeCompare(JSON.stringify(b)),
    );
  normalized.domCanvases = stable.domCanvases
    .map(({ index, ...canvas }) => canvas)
    .sort((a, b) =>
      JSON.stringify(a).localeCompare(JSON.stringify(b)),
    );
  return normalized;
}

function compareIndependentProductionCases(ungated, gated) {
  assertDeepEqual(
    gated.preApp,
    ungated.preApp,
    "independent ungated/gated pages must share the same pre-app zero baseline",
  );
  const differences = collectDifferencePaths(
    canonicalizeIndependentProductionSnapshot(
      gated.beforeApi.stable,
    ),
    canonicalizeIndependentProductionSnapshot(
      ungated.beforeApi.stable,
    ),
  );
  assert(
    differences.length === 0,
    "independent ungated/gated production pages must have identical runtime state before audit calls",
    differences,
  );
  return {
    independentContextsCompared: 2,
    preAppBaselinesEqual: true,
    readyRuntimeStatesEqual: true,
  };
}

async function main() {
  let server = null;
  let browser = null;
  let primaryError = null;
  let lockAfterError = null;
  let lockBefore = null;
  let lockAfter = null;
  let output = null;
  try {
    for (const filePath of [
      CONTROLLER_PATH,
      PRODUCTION_HTML_PATH,
      FORMAL_GLB_PATH,
      R2R_CONTRACT_PATH,
      R2R_MANIFEST_PATH,
      INPUT_LOCK_PATH,
      IMPLEMENTATION_DELTA_PATH,
      COLOR_DECISION_PATH,
      PHOTOMETRIC_DECISION_PATH,
      PIPELINE_STATUS_PATH,
    ]) {
      assert(
        fs.existsSync(filePath),
        "required input is missing",
        { filePath },
      );
    }
    const lock = verifyInputLockFile();
    lockBefore = verifyLockedInputsSnapshot(
      lock.inputLock,
      "before browser verification",
    );
    const decisions = verifyDecisionFiles();
    const staticProduction = verifyStaticProductionContract();
    server = await startServer();
    const baseUrl = `http://127.0.0.1:${server.address().port}`;
    browser = await playwright.chromium.launch({
      headless: true,
    });

    const harnessNegativeResults = [];
    for (const gateCase of NEGATIVE_GATE_CASES) {
      const caseResult = await runHarnessCase(
        browser,
        baseUrl,
        gateCase,
      );
      assertDisabledCase(
        caseResult,
        gateCase.expected,
        `harness ${gateCase.label}`,
      );
      harnessNegativeResults.push(gateCase.label);
    }

    const productionNegativeResults = [];
    for (const gateCase of NEGATIVE_GATE_CASES) {
      const caseResult = await runProductionGateCase(
        browser,
        baseUrl,
        gateCase,
      );
      assertDisabledCase(
        caseResult,
        gateCase.expected,
        `production HTML ${gateCase.label}`,
      );
      productionNegativeResults.push(gateCase.label);
    }

    const enabledCase = await runHarnessCase(
      browser,
      baseUrl,
      ENABLED_GATE_CASE,
    );
    assert(
      enabledCase.pageErrors.length === 0 &&
        enabledCase.result.deterministic &&
        Object.values(enabledCase.result.frozen).every(Boolean) &&
        enabledCase.result.deepFreeze.capability.allFrozen &&
        enabledCase.result.deepFreeze.manifest.allFrozen &&
        enabledCase.result.mutation.allThrewTypeError &&
        enabledCase.result.mutation.unchanged &&
        enabledCase.result.mutation.attempts.length === 12,
      "enabled contract must be deterministic, recursively frozen, mutation-resistant, and error-free",
      enabledCase.result,
    );
    const contract = verifyEnabledContract(
      enabledCase.result.capability,
      enabledCase.result.manifest,
    );

    const ungatedProduction = await runProductionIsolationCase(
      browser,
      baseUrl,
      {
        ...NEGATIVE_GATE_CASES[0],
        label: "independent ungated production page",
      },
    );
    const gatedProduction = await runProductionIsolationCase(
      browser,
      baseUrl,
      {
        ...ENABLED_GATE_CASE,
        label: "independent gated production page",
      },
    );
    const ungatedProductionSummary =
      assertProductionIsolationResult(
        ungatedProduction,
        false,
      );
    const gatedProductionSummary =
      assertProductionIsolationResult(gatedProduction, true);
    const independentProductionComparison =
      compareIndependentProductionCases(
        ungatedProduction,
        gatedProduction,
      );
    assertDeepEqual(
      gatedProduction.capability,
      enabledCase.result.capability,
      "real production controller capability must equal the enabled module harness",
    );
    assertDeepEqual(
      gatedProduction.manifest,
      enabledCase.result.manifest,
      "real production controller manifest must equal the enabled module harness",
    );

    output = {
      requirementId: REQUIREMENT_ID,
      stageId: GATE_VALUE,
      passed: true,
      inputLock: {
        bytes: lock.fingerprint.bytes,
        sha256: lock.fingerprint.sha256,
        entryCount: lock.inputLock.entries.length,
        lockedBytesMatchCount: 21,
        authorizedPostDeltaMatchCount: 1,
        r2rContractSha256:
          EXPECTED_R2R_CONTRACT_SHA256,
        r2rManifestSha256:
          EXPECTED_R2R_MANIFEST_SHA256,
        beforeAfterIdentical: true,
      },
      gates: {
        harnessNegativeMatrix: harnessNegativeResults,
        productionHtmlNegativeMatrix:
          productionNegativeResults,
        negativeCaseCount: NEGATIVE_GATE_CASES.length,
        exactDualGateEnabledNumericOnly: true,
      },
      recursiveFreeze: {
        capabilityObjectCount:
          enabledCase.result.deepFreeze.capability
            .objectCount,
        manifestObjectCount:
          enabledCase.result.deepFreeze.manifest.objectCount,
        mutationAttempts:
          enabledCase.result.mutation.attempts.length,
        allMutationsRejectedWithTypeError: true,
      },
      decisions,
      contract,
      production: {
        ...staticProduction,
        ungated: ungatedProductionSummary,
        gated: gatedProductionSummary,
        independentComparison:
          independentProductionComparison,
        instrumentationStartedBeforeAppScripts: true,
        delayedAsyncCheckMilliseconds: 450,
      },
      limitations: {
        actualThreeAuditCameraObjectsExist: false,
        actualThreeAuditLightObjectsExist: false,
        captureEligible: false,
        imageCaptureAttempted: false,
        controlPointWorldCoordinatesAvailableInFrozenManifest:
          false,
        controlPointVerification:
          "all 12 finite pixel sets are checked for exact cross-engine/repeat equality; independent 3D reprojection is unavailable because the frozen manifest does not include the source world coordinates",
      },
    };
  } catch (error) {
    primaryError = error;
  } finally {
    if (lockBefore) {
      try {
        const lock = verifyInputLockFile();
        lockAfter = verifyLockedInputsSnapshot(
          lock.inputLock,
          "after browser verification",
        );
        assertLockedSnapshotsEqual(lockBefore, lockAfter);
      } catch (error) {
        lockAfterError = error;
      }
    }
    const cleanupTasks = [];
    if (browser) cleanupTasks.push(browser.close());
    if (server) {
      cleanupTasks.push(
        new Promise((resolve, reject) => {
          server.close((error) => {
            if (error) reject(error);
            else resolve();
          });
        }),
      );
    }
    const cleanupResults = await Promise.allSettled(cleanupTasks);
    const cleanupErrors = cleanupResults
      .filter((result) => result.status === "rejected")
      .map((result) => result.reason);
    const errors = [
      primaryError,
      lockAfterError,
      ...cleanupErrors,
    ].filter(Boolean);
    if (errors.length === 1) throw errors[0];
    if (errors.length > 1) {
      throw new AggregateError(
        errors,
        "R2S verifier and/or cleanup failed",
      );
    }
  }
  assert(
    lockAfter !== null,
    "after-verification lock snapshot is required",
  );
  process.stdout.write(
    `${JSON.stringify(output, null, 2)}\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
