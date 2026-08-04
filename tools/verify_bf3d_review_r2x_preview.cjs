#!/usr/bin/env node
"use strict";

/**
 * Chromium-only 1440x900 representative verifier for the R2X 1K AO candidate.
 *
 * Requirement:
 *   REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720
 *
 * This verifier never runs a browser matrix. It captures exactly four raw
 * canvas PNGs at two locked cameras and computes paired AO off/on pixel
 * differences without changing thresholds, material parameters, lights,
 * exposure, environment, tone mapping, or camera values.
 */

const childProcess = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const readline = require("readline");
const zlib = require("zlib");

const PLAYWRIGHT_FALLBACK =
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright";
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require(PLAYWRIGHT_FALLBACK);
}

const ROOT = path.resolve(__dirname, "..");
const FRONTEND = path.join(ROOT, "高炉前端数据");
const STAGE_ID = "WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE";
const STAGE = path.join(ROOT, "PT", "高炉3D模型", "work", STAGE_ID);
const PREVIEW = path.join(STAGE, "preview");
const SCREENSHOTS = path.join(PREVIEW, "screenshots");
const REPORT = path.join(
  STAGE,
  "reports",
  "bf3d_review_r2x_representative_report.json",
);
const HTML = path.join(FRONTEND, "bf3d_review_r2x.server.html");
const RENDERER = path.join(
  FRONTEND,
  "assets",
  "bf3d-review-renderer-r2x.js",
);
const CSS = path.join(FRONTEND, "assets", "bf3d-review-renderer.css");
const SERVER = path.join(ROOT, "tools", "serve_bf3d_review_r2x.py");
const BUILD_REPORT = path.join(
  STAGE,
  "reports",
  "r2x_web_candidate_build_report.json",
);
const CANDIDATE = path.join(
  STAGE,
  "glb",
  "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb",
);
const CONTRACT = path.join(STAGE, "WEB-60_R2X_阶段预注册合同.md");
const EXPECTED_CANDIDATE_SHA256 =
  "bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00";
const EXPECTED_CANDIDATE_BYTES = 1_115_216;
const REQUIREMENT_ID =
  "REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720";
const VIEWPORT = Object.freeze({
  browserType: "chromium",
  width: 1440,
  height: 900,
});
const PAGE_TIMEOUT_MS = 90_000;

// Predeclared automated visual thresholds. These are fixed before capture and
// must not be relaxed to obtain a passing result.
const PIXEL_THRESHOLDS = Object.freeze({
  minimumChangedPixels: 64,
  minimumChangedRatio: 0.00005,
  minimumMeanAbsDiffChangedRgbU8: 0.25,
  maximumFullFrameMeanLumaDropFraction: 0.02,
  maximumForegroundMeanLumaDropFraction: 0.03,
  maximumBrightenedShareOfChanged: 0.02,
  falseRingRowForegroundDarkShare: 0.72,
  falseRingMinimumConsecutiveRows: 2,
  falseRingMinimumForegroundPixelsPerRow: 8,
  backgroundRgbToleranceU8: 5,
  darkPixelMinimumLumaDropU8: 0.75,
});

const PROTECTED = Object.freeze({
  candidate_glb: {
    path: CANDIDATE,
    bytes: EXPECTED_CANDIDATE_BYTES,
    sha256: EXPECTED_CANDIDATE_SHA256,
  },
  v5_blend: {
    path: path.join(
      FRONTEND,
      "models",
      "gl02_blast_furnace_review.v5.blend",
    ),
    sha256:
      "3e6df5fb02d3734d14923d4432739a5918ac8249d6a3c8ad1415395429b27e3a",
  },
  v5_unified_glb: {
    path: path.join(
      FRONTEND,
      "models",
      "gl02_blast_furnace_review.v5.glb",
    ),
    sha256:
      "0ac031e626c9eaa0b0cdd8192cf9fda712324af174a4285f563a97309451ed3c",
  },
  v5_material_glb: {
    path: path.join(
      FRONTEND,
      "models",
      "gl02_blast_furnace_material_review.v5.glb",
    ),
    sha256:
      "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc",
  },
  v5_structural_glb: {
    path: path.join(
      FRONTEND,
      "models",
      "gl02_blast_furnace_structural_review.v5.glb",
    ),
    sha256:
      "e5c77d3834c631e2513209a690f6328d1c63dba2c8d489b2d2dbe17645465f71",
  },
  formal_glb: {
    path: path.join(FRONTEND, "models", "gl02_blast_furnace.glb"),
    sha256:
      "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6",
  },
  production_html: {
    path: path.join(FRONTEND, "frontend_dashboard_v3.server.html"),
  },
  production_controller: {
    path: path.join(FRONTEND, "assets", "bf3d-structural-review.js"),
  },
  r2x_contract: {
    path: CONTRACT,
  },
  r2w_html: {
    path: path.join(FRONTEND, "bf3d_review_r2w.server.html"),
  },
  r2w_renderer: {
    path: path.join(
      FRONTEND,
      "assets",
      "bf3d-review-renderer-r2w.js",
    ),
  },
});

function sha256Buffer(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

function relativePath(filePath) {
  return path.relative(ROOT, filePath).split(path.sep).join("/");
}

function inspectFile(filePath, expected = {}) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`受控文件不存在：${relativePath(filePath)}`);
  }
  const stats = fs.statSync(filePath);
  const actual = {
    path: relativePath(filePath),
    bytes: stats.size,
    sha256: sha256File(filePath),
  };
  if (
    (expected.bytes !== undefined && actual.bytes !== expected.bytes) ||
    (expected.sha256 !== undefined && actual.sha256 !== expected.sha256)
  ) {
    throw new Error(
      `受控文件锁不匹配：${JSON.stringify({ actual, expected })}`,
    );
  }
  return actual;
}

function snapshotProtectedFiles() {
  return Object.fromEntries(
    Object.entries(PROTECTED).map(([key, value]) => [
      key,
      inspectFile(value.path, value),
    ]),
  );
}

function protectedSnapshotsMatch(before, after) {
  return Object.keys(before).every(
    (key) =>
      before[key].bytes === after[key].bytes &&
      before[key].sha256 === after[key].sha256,
  );
}

function serializeError(error, phase = undefined) {
  return {
    phase: phase || null,
    name: error?.name || "Error",
    message: String(error?.message || error),
    stack: error?.stack || null,
  };
}

function assert(condition, message, detail = undefined) {
  if (condition) return;
  const error = new Error(message);
  if (detail !== undefined) error.detail = detail;
  throw error;
}

function parseGlbJson(filePath) {
  const buffer = fs.readFileSync(filePath);
  assert(buffer.length >= 20, "GLB 太小");
  assert(buffer.toString("ascii", 0, 4) === "glTF", "GLB magic 不匹配");
  assert(buffer.readUInt32LE(4) === 2, "GLB version 不是 2");
  assert(buffer.readUInt32LE(8) === buffer.length, "GLB length 不匹配");
  const jsonLength = buffer.readUInt32LE(12);
  assert(buffer.toString("ascii", 16, 20) === "JSON", "首 chunk 不是 JSON");
  return JSON.parse(
    buffer
      .subarray(20, 20 + jsonLength)
      .toString("utf8")
      .replace(/[\u0000\u0020]+$/u, ""),
  );
}

function buildGlbContract() {
  const document = parseGlbJson(CANDIDATE);
  const nodes = document.nodes || [];
  const meshes = document.meshes || [];
  const materials = document.materials || [];
  const targets = nodes.filter(
    (node) =>
      String(node.name || "").startsWith("R2J_ASM_GL02_FURNACE_") &&
      String(node.name || "").includes("_SHELL_"),
  );
  const primitives = [];
  for (const node of targets) {
    const mesh = meshes[node.mesh];
    for (const primitive of mesh?.primitives || []) {
      const material = materials[primitive.material] || {};
      const pbr = material.pbrMetallicRoughness || {};
      const attributes = Object.keys(primitive.attributes || {});
      primitives.push({
        node: node.name,
        material: material.name,
        attributes,
        baseColorTexCoord: pbr.baseColorTexture?.texCoord ?? 0,
        metallicRoughnessTexCoord:
          pbr.metallicRoughnessTexture?.texCoord ?? 0,
        normalTexCoord: material.normalTexture?.texCoord ?? 0,
        occlusionTexCoord: material.occlusionTexture?.texCoord ?? null,
        occlusionStrength: material.occlusionTexture?.strength ?? 1,
      });
    }
  }
  const passed =
    targets.length === 5 &&
    meshes.length === 5 &&
    materials.length === 2 &&
    materials[0]?.name === "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL" &&
    materials[1]?.name === "INT30_R2G_R1_LOCK_BAKED_PBR_STEEL.001" &&
    primitives.length === 5 &&
    primitives.every(
      (primitive) =>
        ["TEXCOORD_0", "TEXCOORD_1", "TEXCOORD_2"].every((attribute) =>
          primitive.attributes.includes(attribute),
        ) &&
        primitive.baseColorTexCoord === 0 &&
        primitive.metallicRoughnessTexCoord === 0 &&
        primitive.normalTexCoord === 0 &&
        primitive.occlusionTexCoord === 2 &&
        primitive.occlusionStrength === 1,
    );
  return {
    passed,
    node_count: nodes.length,
    mesh_count: meshes.length,
    material_count: materials.length,
    material_names: materials.map((material) => material.name),
    target_count: targets.length,
    primitives,
  };
}

function buildStaticContract() {
  const html = fs.readFileSync(HTML, "utf8");
  const renderer = fs.readFileSync(RENDERER, "utf8");
  const server = fs.readFileSync(SERVER, "utf8");
  const buildReport = JSON.parse(fs.readFileSync(BUILD_REPORT, "utf8"));
  const checks = {
    build_report_passed: buildReport.passed === true,
    exact_candidate_url:
      renderer.includes(
        "gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb",
      ) && !renderer.includes('r2x-ao-smoke1k.glb"'),
    scope_labels: [
      "1K smoke",
      "E/illustrative",
      "not P50",
      "not production",
    ].every((token) => html.includes(token)),
    exactly_two_views:
      html.includes('data-view-button="global"') &&
      html.includes('data-view-button="detail"'),
    exactly_two_ao_states:
      html.includes('data-ao-button="off"') &&
      html.includes('data-ao-button="on"'),
    ao_only_runtime_change:
      renderer.includes("entry.material.aoMapIntensity = value") &&
      renderer.includes("onlyIntensityChangesAtRuntime"),
    p40_locked:
      renderer.includes("const FIXED_EXPOSURE = 1.0") &&
      renderer.includes("[0.0864, 0.0864, 0.0864]") &&
      renderer.includes("THREE.ACESFilmicToneMapping") &&
      renderer.includes("[0.78, 0.18, 0.62]") &&
      renderer.includes("intensityAtK1: 1.3275510357953"),
    isolated_server:
      server.includes('"formal_glb_exposed": False') &&
      server.includes('"v5_glb_exposed": False') &&
      server.includes('"old_r2x_candidate_exposed": False'),
  };
  return {
    checks,
    passed: Object.values(checks).every(Boolean),
    build_report: {
      path: relativePath(BUILD_REPORT),
      sha256: sha256File(BUILD_REPORT),
    },
  };
}

function startReviewServer() {
  return new Promise((resolve, reject) => {
    const python = process.env.PYTHON || "python";
    const child = childProcess.spawn(
      python,
      [SERVER, "--port", "0", "--quiet"],
      {
        cwd: ROOT,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const stderr = [];
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    const reader = readline.createInterface({ input: child.stdout });
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      reject(new Error(`R2X server ready timeout: ${stderr.join("")}`));
    }, 30_000);
    reader.on("line", (line) => {
      if (settled) return;
      try {
        const value = JSON.parse(line);
        if (value.event !== "bf3d_r2x_review_server_ready") return;
        settled = true;
        clearTimeout(timer);
        resolve({ child, ready: value, stderr, reader });
      } catch {
        // Ignore non-JSON startup noise.
      }
    });
    child.on("exit", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(
        new Error(
          `R2X server exited before ready: code=${code}, stderr=${stderr.join(
            "",
          )}`,
        ),
      );
    });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    });
  });
}

async function stopReviewServer(server) {
  if (!server?.child || server.child.exitCode !== null) return;
  server.reader?.close();
  server.child.kill();
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (server.child.exitCode === null) server.child.kill("SIGKILL");
      resolve();
    }, 5_000);
    server.child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

function attachDiagnostics(page, origin) {
  const diagnostics = {
    console: [],
    page: [],
    http: [],
    external: [],
    request_failed: [],
    requests: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") {
      diagnostics.console.push({
        text: message.text(),
        location: message.location(),
      });
    }
  });
  page.on("pageerror", (error) => {
    diagnostics.page.push(serializeError(error, "page"));
  });
  page.on("request", (request) => {
    const url = request.url();
    diagnostics.requests.push({
      method: request.method(),
      url,
      resource_type: request.resourceType(),
    });
    try {
      if (new URL(url).origin !== origin && !url.startsWith("data:")) {
        diagnostics.external.push({ method: request.method(), url });
      }
    } catch {
      diagnostics.external.push({ method: request.method(), url });
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      diagnostics.http.push({
        status: response.status(),
        url: response.url(),
      });
    }
  });
  page.on("requestfailed", (request) => {
    diagnostics.request_failed.push({
      url: request.url(),
      failure: request.failure(),
    });
  });
  return diagnostics;
}

function errorTotals(diagnostics) {
  return {
    console: diagnostics.console.length,
    page: diagnostics.page.length,
    http: diagnostics.http.length,
    external: diagnostics.external.length,
    request_failed: diagnostics.request_failed.length,
  };
}

function cameraSignature(state) {
  return JSON.stringify({
    view: state.composition.view,
    direction: state.composition.cameraDirection,
    distanceScale: state.composition.cameraDistanceScale,
    position: state.composition.cameraPosition,
    quaternion: state.composition.cameraQuaternion,
    projectionMatrix: state.composition.projectionMatrix,
  });
}

function materialSignatureWithoutAoIntensity(snapshot) {
  const copy = structuredClone(snapshot);
  delete copy.aoMapIntensity;
  return JSON.stringify(copy);
}

function compareRuntimeSnapshots(offState, onState) {
  const offMaterials = offState.pbr.materialSnapshots;
  const onMaterials = onState.pbr.materialSnapshots;
  const bindingKey = (entry) => `${entry.mesh}|${entry.uuid}`;
  const byBinding = new Map(
    onMaterials.map((entry) => [bindingKey(entry), entry]),
  );
  const materialChecks = offMaterials.map((off) => {
    const on = byBinding.get(bindingKey(off));
    return {
      mesh: off.mesh,
      material: off.name,
      material_uuid: off.uuid,
      present_in_both: Boolean(on),
      off_intensity: off.aoMapIntensity,
      on_intensity: on?.aoMapIntensity ?? null,
      only_intensity_changed:
        Boolean(on) &&
        materialSignatureWithoutAoIntensity(off) ===
          materialSignatureWithoutAoIntensity(on) &&
        off.aoMapIntensity === 0 &&
        on.aoMapIntensity === 1,
    };
  });
  const lightingEqual =
    JSON.stringify(offState.lighting) === JSON.stringify(onState.lighting);
  const rendererEqual =
    JSON.stringify({
      revision: offState.renderer.revision,
      outputColorSpace: offState.renderer.outputColorSpace,
      toneMapping: offState.renderer.toneMapping,
      exposure: offState.renderer.exposure,
    }) ===
    JSON.stringify({
      revision: onState.renderer.revision,
      outputColorSpace: onState.renderer.outputColorSpace,
      toneMapping: onState.renderer.toneMapping,
      exposure: onState.renderer.exposure,
    });
  return {
    material_checks: materialChecks,
    all_materials_only_intensity_changed:
      materialChecks.length === 5 &&
      materialChecks.every((entry) => entry.only_intensity_changed),
    camera_unchanged: cameraSignature(offState) === cameraSignature(onState),
    lighting_unchanged: lightingEqual,
    renderer_color_path_unchanged: rendererEqual,
    passed:
      materialChecks.length === 5 &&
      materialChecks.every((entry) => entry.only_intensity_changed) &&
      cameraSignature(offState) === cameraSignature(onState) &&
      lightingEqual &&
      rendererEqual,
  };
}

function paethPredictor(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function decodePng(filePath) {
  const payload = fs.readFileSync(filePath);
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  assert(payload.subarray(0, 8).equals(signature), "截图不是 PNG");
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  const idat = [];
  while (offset + 12 <= payload.length) {
    const length = payload.readUInt32BE(offset);
    const type = payload.toString("ascii", offset + 4, offset + 8);
    const data = payload.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === "IDAT") {
      idat.push(data);
    } else if (type === "IEND") {
      break;
    }
    offset += 12 + length;
  }
  assert(bitDepth === 8, `仅支持 8-bit PNG，实际 ${bitDepth}`);
  assert(interlace === 0, "不支持 interlaced PNG");
  const channelsByType = { 0: 1, 2: 3, 4: 2, 6: 4 };
  const channels = channelsByType[colorType];
  assert(channels, `不支持 PNG color type ${colorType}`);
  const rowBytes = width * channels;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  assert(
    raw.length === height * (rowBytes + 1),
    `PNG inflate length 不匹配：${raw.length}`,
  );
  const decoded = Buffer.alloc(height * rowBytes);
  let sourceOffset = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = raw[sourceOffset];
    sourceOffset += 1;
    const rowOffset = y * rowBytes;
    const previousOffset = (y - 1) * rowBytes;
    for (let x = 0; x < rowBytes; x += 1) {
      const value = raw[sourceOffset + x];
      const left = x >= channels ? decoded[rowOffset + x - channels] : 0;
      const up = y > 0 ? decoded[previousOffset + x] : 0;
      const upperLeft =
        y > 0 && x >= channels
          ? decoded[previousOffset + x - channels]
          : 0;
      let reconstructed;
      if (filter === 0) reconstructed = value;
      else if (filter === 1) reconstructed = (value + left) & 0xff;
      else if (filter === 2) reconstructed = (value + up) & 0xff;
      else if (filter === 3)
        reconstructed = (value + Math.floor((left + up) / 2)) & 0xff;
      else if (filter === 4)
        reconstructed =
          (value + paethPredictor(left, up, upperLeft)) & 0xff;
      else throw new Error(`未知 PNG filter ${filter}`);
      decoded[rowOffset + x] = reconstructed;
    }
    sourceOffset += rowBytes;
  }
  const rgba = Buffer.alloc(width * height * 4);
  for (let index = 0; index < width * height; index += 1) {
    const source = index * channels;
    const target = index * 4;
    if (colorType === 6) {
      rgba[target] = decoded[source];
      rgba[target + 1] = decoded[source + 1];
      rgba[target + 2] = decoded[source + 2];
      rgba[target + 3] = decoded[source + 3];
    } else if (colorType === 2) {
      rgba[target] = decoded[source];
      rgba[target + 1] = decoded[source + 1];
      rgba[target + 2] = decoded[source + 2];
      rgba[target + 3] = 255;
    } else if (colorType === 4) {
      rgba[target] = decoded[source];
      rgba[target + 1] = decoded[source];
      rgba[target + 2] = decoded[source];
      rgba[target + 3] = decoded[source + 1];
    } else {
      rgba[target] = decoded[source];
      rgba[target + 1] = decoded[source];
      rgba[target + 2] = decoded[source];
      rgba[target + 3] = 255;
    }
  }
  return { width, height, rgba, colorType, bitDepth };
}

function luma(r, g, b) {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function analyzePixelPair(offPath, onPath, pairName) {
  const off = decodePng(offPath);
  const on = decodePng(onPath);
  assert(
    off.width === on.width && off.height === on.height,
    `${pairName} PNG 尺寸不一致`,
  );
  const pixelCount = off.width * off.height;
  const background = [
    off.rgba[0],
    off.rgba[1],
    off.rgba[2],
  ];
  let changedPixels = 0;
  let darkenedPixels = 0;
  let brightenedPixels = 0;
  let sumAbsAllRgb = 0;
  let sumAbsChangedRgb = 0;
  let maxAbsDiff = 0;
  let sumLumaOff = 0;
  let sumLumaOn = 0;
  let foregroundPixels = 0;
  let foregroundLumaOff = 0;
  let foregroundLumaOn = 0;
  const rowForeground = new Array(off.height).fill(0);
  const rowDarkChanged = new Array(off.height).fill(0);
  const rowDarkLumaDrop = new Array(off.height).fill(0);

  for (let pixel = 0; pixel < pixelCount; pixel += 1) {
    const offset = pixel * 4;
    const offRgb = [
      off.rgba[offset],
      off.rgba[offset + 1],
      off.rgba[offset + 2],
    ];
    const onRgb = [
      on.rgba[offset],
      on.rgba[offset + 1],
      on.rgba[offset + 2],
    ];
    const diffs = offRgb.map((value, channel) =>
      Math.abs(value - onRgb[channel]),
    );
    const changed = diffs.some((value) => value > 0);
    const abs = diffs[0] + diffs[1] + diffs[2];
    sumAbsAllRgb += abs;
    maxAbsDiff = Math.max(maxAbsDiff, ...diffs);
    if (changed) {
      changedPixels += 1;
      sumAbsChangedRgb += abs;
    }
    const offLuma = luma(...offRgb);
    const onLuma = luma(...onRgb);
    sumLumaOff += offLuma;
    sumLumaOn += onLuma;
    if (offLuma - onLuma >= PIXEL_THRESHOLDS.darkPixelMinimumLumaDropU8) {
      darkenedPixels += 1;
    } else if (
      onLuma - offLuma >= PIXEL_THRESHOLDS.darkPixelMinimumLumaDropU8
    ) {
      brightenedPixels += 1;
    }
    const isForeground = offRgb.some(
      (value, channel) =>
        Math.abs(value - background[channel]) >
        PIXEL_THRESHOLDS.backgroundRgbToleranceU8,
    );
    if (isForeground) {
      foregroundPixels += 1;
      foregroundLumaOff += offLuma;
      foregroundLumaOn += onLuma;
      const row = Math.floor(pixel / off.width);
      rowForeground[row] += 1;
      if (
        offLuma - onLuma >= PIXEL_THRESHOLDS.darkPixelMinimumLumaDropU8
      ) {
        rowDarkChanged[row] += 1;
        rowDarkLumaDrop[row] += offLuma - onLuma;
      }
    }
  }

  const meanLumaOff = sumLumaOff / pixelCount;
  const meanLumaOn = sumLumaOn / pixelCount;
  const foregroundMeanLumaOff =
    foregroundPixels > 0 ? foregroundLumaOff / foregroundPixels : 0;
  const foregroundMeanLumaOn =
    foregroundPixels > 0 ? foregroundLumaOn / foregroundPixels : 0;
  const fullFrameMeanLumaDropFraction =
    meanLumaOff > 0 ? Math.max(0, (meanLumaOff - meanLumaOn) / meanLumaOff) : 0;
  const foregroundMeanLumaDropFraction =
    foregroundMeanLumaOff > 0
      ? Math.max(
          0,
          (foregroundMeanLumaOff - foregroundMeanLumaOn) /
            foregroundMeanLumaOff,
        )
      : 0;

  const ringRows = [];
  for (let row = 0; row < off.height; row += 1) {
    const foreground = rowForeground[row];
    const dark = rowDarkChanged[row];
    const share = foreground > 0 ? dark / foreground : 0;
    const meanDrop = dark > 0 ? rowDarkLumaDrop[row] / dark : 0;
    if (
      foreground >=
        PIXEL_THRESHOLDS.falseRingMinimumForegroundPixelsPerRow &&
      share >= PIXEL_THRESHOLDS.falseRingRowForegroundDarkShare &&
      meanDrop >= PIXEL_THRESHOLDS.darkPixelMinimumLumaDropU8
    ) {
      ringRows.push({ row, foreground, dark, share, mean_luma_drop: meanDrop });
    }
  }
  const ringRuns = [];
  let current = [];
  for (const entry of ringRows) {
    if (
      current.length === 0 ||
      entry.row === current[current.length - 1].row + 1
    ) {
      current.push(entry);
    } else {
      if (
        current.length >= PIXEL_THRESHOLDS.falseRingMinimumConsecutiveRows
      ) {
        ringRuns.push(current);
      }
      current = [entry];
    }
  }
  if (current.length >= PIXEL_THRESHOLDS.falseRingMinimumConsecutiveRows) {
    ringRuns.push(current);
  }

  const changedRatio = changedPixels / pixelCount;
  const meanAbsDiffAllRgbU8 = sumAbsAllRgb / (pixelCount * 3);
  const meanAbsDiffChangedRgbU8 =
    changedPixels > 0 ? sumAbsChangedRgb / (changedPixels * 3) : 0;
  const brightenedShareOfChanged =
    changedPixels > 0 ? brightenedPixels / changedPixels : 0;
  const minimumChangedPixels = Math.max(
    PIXEL_THRESHOLDS.minimumChangedPixels,
    Math.ceil(pixelCount * PIXEL_THRESHOLDS.minimumChangedRatio),
  );
  const aoDifferenceTooWeak =
    changedPixels < minimumChangedPixels ||
    meanAbsDiffChangedRgbU8 <
      PIXEL_THRESHOLDS.minimumMeanAbsDiffChangedRgbU8 ||
    maxAbsDiff === 0;
  const overallDarkeningDetected =
    fullFrameMeanLumaDropFraction >
      PIXEL_THRESHOLDS.maximumFullFrameMeanLumaDropFraction ||
    foregroundMeanLumaDropFraction >
      PIXEL_THRESHOLDS.maximumForegroundMeanLumaDropFraction;
  const unexpectedBrighteningDetected =
    brightenedShareOfChanged >
    PIXEL_THRESHOLDS.maximumBrightenedShareOfChanged;
  const falseRingDetected = ringRuns.length > 0;
  return {
    pair: pairName,
    width: off.width,
    height: off.height,
    pixel_count: pixelCount,
    changed_pixels: changedPixels,
    changed_ratio: changedRatio,
    minimum_changed_pixels: minimumChangedPixels,
    darkened_pixels: darkenedPixels,
    brightened_pixels: brightenedPixels,
    brightened_share_of_changed: brightenedShareOfChanged,
    mean_abs_diff_all_rgb_u8: meanAbsDiffAllRgbU8,
    mean_abs_diff_changed_rgb_u8: meanAbsDiffChangedRgbU8,
    max_abs_diff_u8: maxAbsDiff,
    mean_luma_off_u8: meanLumaOff,
    mean_luma_on_u8: meanLumaOn,
    full_frame_mean_luma_drop_fraction: fullFrameMeanLumaDropFraction,
    foreground_pixels: foregroundPixels,
    foreground_mean_luma_off_u8: foregroundMeanLumaOff,
    foreground_mean_luma_on_u8: foregroundMeanLumaOn,
    foreground_mean_luma_drop_fraction: foregroundMeanLumaDropFraction,
    background_reference_rgb_u8: background,
    ao_difference_too_weak: aoDifferenceTooWeak,
    overall_darkening_detected: overallDarkeningDetected,
    unexpected_brightening_detected: unexpectedBrighteningDetected,
    false_ring_detected: falseRingDetected,
    false_ring_candidates: ringRuns.map((run) => ({
      start_row: run[0].row,
      end_row: run[run.length - 1].row,
      row_count: run.length,
      maximum_dark_foreground_share: Math.max(
        ...run.map((entry) => entry.share),
      ),
      rows: run,
    })),
    thresholds: PIXEL_THRESHOLDS,
    passed:
      !aoDifferenceTooWeak &&
      !overallDarkeningDetected &&
      !unexpectedBrighteningDetected &&
      !falseRingDetected,
  };
}

async function capture(
  page,
  view,
  aoEnabled,
  diagnostics,
) {
  await page.evaluate(
    ({ targetView, enabled }) => {
      window.BF3D_R2X_REVIEW.setView(targetView);
      window.BF3D_R2X_REVIEW.setAoEnabled(enabled);
      window.BF3D_R2X_REVIEW.resetCamera();
      window.BF3D_R2X_REVIEW.renderOnce();
    },
    { targetView: view, enabled: aoEnabled },
  );
  await page.waitForTimeout(350);
  const state = await page.evaluate(() =>
    window.BF3D_R2X_REVIEW.getAuditSnapshot(),
  );
  const label = `${view}-${aoEnabled ? "on" : "off"}`;
  const filePath = path.join(
    SCREENSHOTS,
    `r2x_chromium_1440x900_${label}.png`,
  );
  const canvas = page.locator("#bf3d-review-canvas");
  await canvas.screenshot({ path: filePath, type: "png", animations: "disabled" });
  return {
    id: label,
    view,
    ao_enabled: aoEnabled,
    path: relativePath(filePath),
    bytes: fs.statSync(filePath).size,
    sha256: sha256File(filePath),
    state,
    error_totals_after_capture: errorTotals(diagnostics),
  };
}

async function runRepresentative(baseUrl) {
  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: VIEWPORT.width, height: VIEWPORT.height },
    deviceScaleFactor: 1,
    colorScheme: "dark",
    locale: "zh-CN",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(PAGE_TIMEOUT_MS);
  const origin = new URL(baseUrl).origin;
  const diagnostics = attachDiagnostics(page, origin);
  const captures = [];
  try {
    await page.goto(baseUrl, {
      waitUntil: "domcontentloaded",
      timeout: PAGE_TIMEOUT_MS,
    });
    await page.waitForFunction(
      () =>
        ["ready", "error"].includes(
          window.BF3D_R2X_REVIEW?.getState?.().loadState,
        ) &&
        ["ready", "error"].includes(document.body.dataset.loadState),
      null,
      { timeout: PAGE_TIMEOUT_MS },
    );
    const readiness = await page.evaluate(() => ({
      bodyLoadState: document.body.dataset.loadState || null,
      reviewState: window.BF3D_R2X_REVIEW?.getState?.() || null,
      visibleMessage:
        document.querySelector("#load-message")?.textContent || null,
    }));
    assert(
      readiness.bodyLoadState === "ready" &&
        readiness.reviewState?.loadState === "ready",
      "R2X 页面进入 error 状态",
      readiness,
    );
    const layout = await page.evaluate(() => ({
      viewport: [innerWidth, innerHeight],
      document_scroll_width: document.documentElement.scrollWidth,
      body_scroll_width: document.body.scrollWidth,
      horizontal_overflow:
        document.documentElement.scrollWidth > innerWidth + 1 ||
        document.body.scrollWidth > innerWidth + 1,
      labels: document.body.innerText,
      canvas_rect: (() => {
        const rect = document
          .querySelector("#bf3d-review-canvas")
          .getBoundingClientRect();
        return {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
        };
      })(),
    }));
    assert(!layout.horizontal_overflow, "1440x900 页面存在横向溢出", layout);
    for (const label of [
      "1K smoke",
      "E/illustrative",
      "not P50",
      "not production",
    ]) {
      assert(layout.labels.includes(label), `页面缺少边界标签：${label}`);
    }

    captures.push(await capture(page, "global", false, diagnostics));
    captures.push(await capture(page, "global", true, diagnostics));
    captures.push(await capture(page, "detail", false, diagnostics));
    captures.push(await capture(page, "detail", true, diagnostics));

    const finalState = await page.evaluate(() =>
      window.BF3D_R2X_REVIEW.getAuditSnapshot(),
    );
    return { captures, diagnostics, layout, finalState };
  } finally {
    await context.close();
    await browser.close();
  }
}

async function main() {
  fs.mkdirSync(SCREENSHOTS, { recursive: true });
  const report = {
    schema_version: "bf3d.r2x.representative_preview.v1",
    requirement_id: REQUIREMENT_ID,
    stage_id: STAGE_ID,
    started_at: new Date().toISOString(),
    execution_scope: "chromium_1440x900_representative_only",
    browser: VIEWPORT,
    full_matrix_executed: false,
    candidate_glb_sha256: EXPECTED_CANDIDATE_SHA256,
    candidate_glb_bytes: EXPECTED_CANDIDATE_BYTES,
    thresholds: PIXEL_THRESHOLDS,
    overall_status: "running",
    machine_three_passed: false,
    visual_gate_passed: false,
    ao_difference_too_weak: true,
    false_ring_detected: false,
    overall_darkening_detected: false,
    unexpected_brightening_detected: false,
    runtime_failed: true,
    representative_visual_conclusion: "not_run",
    error_totals: {
      console: 0,
      page: 0,
      http: 0,
      external: 0,
      request_failed: 0,
    },
    source_contract: null,
    glb_contract: null,
    server_contract: null,
    runtime_contract: null,
    captures: [],
    pairs: {},
    protected_files_before: null,
    protected_files_after: null,
    protected_files_unchanged: false,
    hard_failures: [],
    attempt_history: [
      {
        attempt: 1,
        outcome: "failed_before_browser",
        cause:
          "Verifier GLB gate incorrectly expected five independent materials instead of the exact V5 two-shared-material baseline.",
        correction:
          "Locked material_count=2 and the two exact V5 material names while retaining five target primitives.",
        captures_written: 0,
        visual_inference_allowed: false,
      },
      {
        attempt: 2,
        outcome: "failed_before_page_ready",
        cause:
          "Renderer validation incorrectly expected five unique Three.js material objects; GLTFLoader correctly reused the two V5 shared materials.",
        correction:
          "Locked EXPECTED_MATERIAL_COUNT=2 and exact V5 shared material names; AO/PBR runtime counts remain five primitive bindings.",
        captures_written: 0,
        visual_inference_allowed: false,
      },
      {
        attempt: 3,
        outcome: "four_captures_created_adapter_machine_false",
        cause:
          "Runtime comparator keyed five primitive-binding snapshots only by shared material UUID, so repeated bindings were paired with the last mesh snapshot.",
        correction:
          "Pair off/on material snapshots by the composite mesh|material-UUID binding key; pixel thresholds and captured pixels remain unchanged.",
        captures_written: 4,
        visual_inference_allowed: true,
      },
    ],
    limitations: [
      "1K smoke / E illustrative / not P50 / not production.",
      "Only Chromium 1440x900 representative was executed; full matrix was not run.",
      "Automated paired-pixel gates do not replace root visual review.",
      "Two pre-capture implementation-gate failures and one shared-material comparator failure are retained in attempt_history; no pixel threshold was relaxed.",
      "This result cannot approve 2K, P50, P60, P70, QA-70, production, or photometric equivalence.",
    ],
    approval_stop_lines: {
      approval_granted: false,
      ao_2k_approved: false,
      p50_approved: false,
      p60_approved: false,
      production_integration_allowed: false,
      next_release_stage_allowed: false,
    },
  };
  let server = null;
  try {
    report.protected_files_before = snapshotProtectedFiles();
    report.source_contract = buildStaticContract();
    report.glb_contract = buildGlbContract();
    assert(report.source_contract.passed, "R2X 静态源合同失败");
    assert(report.glb_contract.passed, "R2X GLB JSON 合同失败");
    server = await startReviewServer();
    report.server_contract = server.ready;
    const result = await runRepresentative(server.ready.url);
    report.captures = result.captures.map((capture) => ({
      id: capture.id,
      view: capture.view,
      ao_enabled: capture.ao_enabled,
      path: capture.path,
      bytes: capture.bytes,
      sha256: capture.sha256,
      error_totals_after_capture: capture.error_totals_after_capture,
    }));
    report.error_totals = errorTotals(result.diagnostics);
    report.diagnostics = result.diagnostics;
    report.layout = result.layout;

    const byId = new Map(result.captures.map((entry) => [entry.id, entry]));
    const globalOff = byId.get("global-off");
    const globalOn = byId.get("global-on");
    const detailOff = byId.get("detail-off");
    const detailOn = byId.get("detail-on");
    assert(globalOff && globalOn && detailOff && detailOn, "四张截图不完整");

    const globalRuntime = compareRuntimeSnapshots(
      globalOff.state,
      globalOn.state,
    );
    const detailRuntime = compareRuntimeSnapshots(
      detailOff.state,
      detailOn.state,
    );
    const allStates = result.captures.map((capture) => capture.state);
    const stateMachineChecks = {
      five_shells: allStates.every(
        (state) =>
          state.objects.shellCount === 5 &&
          state.objects.materialCount === 2,
      ),
      ao_map_5_of_5: allStates.every(
        (state) => state.aoContract.aoMapCount === 5,
      ),
      ao_channel_2_5_of_5: allStates.every(
        (state) => state.aoContract.aoMapChannel2Count === 5,
      ),
      uv2_present_finite_5_of_5: allStates.every(
        (state) =>
          state.aoContract.uv2Count === 5 &&
          state.aoContract.uv2FiniteCount === 5,
      ),
      non_ao_texture_channel_0_5_of_5: allStates.every(
        (state) => state.aoContract.nonAoTextureChannel0Count === 5,
      ),
      non_ao_pbr_mutation_zero: allStates.every(
        (state) => state.pbr.nonAoMutation.mutationCount === 0,
      ),
      forbidden_yellow_zero: allStates.every(
        (state) =>
          state.objects.forbiddenObjectCount === 0 &&
          state.objects.yellowOutlineCount === 0,
      ),
      model_sha_verified: allStates.every(
        (state) =>
          state.model.shaVerified === true &&
          state.model.actualSha256 === EXPECTED_CANDIDATE_SHA256,
      ),
      ao_state_intensities_correct: allStates.every(
        (state) => state.aoContract.state.passed === true,
      ),
      global_projection_passed:
        globalOff.state.composition.projectionAudit.passed === true &&
        globalOn.state.composition.projectionAudit.passed === true,
      detail_projection_passed:
        detailOff.state.composition.projectionAudit.passed === true &&
        detailOn.state.composition.projectionAudit.passed === true,
      global_off_on_only_intensity: globalRuntime.passed,
      detail_off_on_only_intensity: detailRuntime.passed,
      five_error_classes_zero: Object.values(report.error_totals).every(
        (value) => value === 0,
      ),
    };
    report.runtime_contract = {
      state_machine_checks: stateMachineChecks,
      global_off_on: globalRuntime,
      detail_off_on: detailRuntime,
      states: Object.fromEntries(
        result.captures.map((capture) => [capture.id, capture.state]),
      ),
      passed: Object.values(stateMachineChecks).every(Boolean),
    };
    report.machine_three_passed = report.runtime_contract.passed;

    report.pairs.global = analyzePixelPair(
      path.join(ROOT, globalOff.path),
      path.join(ROOT, globalOn.path),
      "global",
    );
    report.pairs.detail = analyzePixelPair(
      path.join(ROOT, detailOff.path),
      path.join(ROOT, detailOn.path),
      "detail",
    );
    report.ao_difference_too_weak =
      report.pairs.global.ao_difference_too_weak ||
      report.pairs.detail.ao_difference_too_weak;
    report.false_ring_detected =
      report.pairs.global.false_ring_detected ||
      report.pairs.detail.false_ring_detected;
    report.overall_darkening_detected =
      report.pairs.global.overall_darkening_detected ||
      report.pairs.detail.overall_darkening_detected;
    report.unexpected_brightening_detected =
      report.pairs.global.unexpected_brightening_detected ||
      report.pairs.detail.unexpected_brightening_detected;
    report.visual_gate_passed =
      report.pairs.global.passed && report.pairs.detail.passed;
    report.runtime_failed =
      !report.machine_three_passed ||
      !Object.values(report.error_totals).every((value) => value === 0);
    const representativePassed =
      report.machine_three_passed &&
      report.visual_gate_passed &&
      !report.ao_difference_too_weak &&
      !report.false_ring_detected &&
      !report.overall_darkening_detected &&
      !report.unexpected_brightening_detected &&
      !report.runtime_failed;
    report.overall_status = representativePassed
      ? "representative_passed_pending_root_visual_review"
      : "representative_fail_closed";
    report.representative_visual_conclusion = representativePassed
      ? "automated_pairwise_gate_passed_pending_root_visual_review"
      : "automated_pairwise_gate_failed_closed";
  } catch (error) {
    report.hard_failures.push({
      ...serializeError(error, "representative_verification"),
      detail: error?.detail || null,
    });
    report.overall_status = "representative_fail_closed";
    report.runtime_failed = true;
    report.representative_visual_conclusion =
      "automated_pairwise_gate_failed_closed";
  } finally {
    await stopReviewServer(server);
    try {
      report.protected_files_after = snapshotProtectedFiles();
      report.protected_files_unchanged = protectedSnapshotsMatch(
        report.protected_files_before,
        report.protected_files_after,
      );
      if (!report.protected_files_unchanged) {
        report.hard_failures.push({
          phase: "protected_files",
          name: "IntegrityError",
          message: "候选/V5/正式/生产/R2W 受保护文件发生变化",
        });
        report.overall_status = "representative_fail_closed";
        report.runtime_failed = true;
      }
    } catch (error) {
      report.hard_failures.push(
        serializeError(error, "protected_files_after"),
      );
      report.overall_status = "representative_fail_closed";
      report.runtime_failed = true;
      report.protected_files_unchanged = false;
    }
    report.completed_at = new Date().toISOString();
    // Enforce final consistency after integrity checks.
    const finalPass =
      report.overall_status ===
        "representative_passed_pending_root_visual_review" &&
      report.machine_three_passed === true &&
      report.visual_gate_passed === true &&
      report.ao_difference_too_weak === false &&
      report.false_ring_detected === false &&
      report.overall_darkening_detected === false &&
      report.unexpected_brightening_detected === false &&
      report.runtime_failed === false &&
      Object.values(report.error_totals).every((value) => value === 0) &&
      report.protected_files_unchanged === true &&
      report.hard_failures.length === 0;
    if (!finalPass) report.overall_status = "representative_fail_closed";
    fs.mkdirSync(path.dirname(REPORT), { recursive: true });
    fs.writeFileSync(REPORT, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    process.stdout.write(
      `${JSON.stringify(
        {
          passed: finalPass,
          overall_status: report.overall_status,
          machine_three_passed: report.machine_three_passed,
          visual_gate_passed: report.visual_gate_passed,
          ao_difference_too_weak: report.ao_difference_too_weak,
          false_ring_detected: report.false_ring_detected,
          overall_darkening_detected: report.overall_darkening_detected,
          runtime_failed: report.runtime_failed,
          error_totals: report.error_totals,
          captures: report.captures.map((entry) => entry.path),
          report: relativePath(REPORT),
        },
        null,
        2,
      )}\n`,
    );
    if (!finalPass) process.exitCode = 1;
  }
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify(serializeError(error, "main"))}\n`);
  process.exitCode = 1;
});
