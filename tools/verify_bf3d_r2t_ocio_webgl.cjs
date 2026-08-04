#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");

const PLAYWRIGHT_FALLBACK =
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/playwright@1.61.1/node_modules/playwright";
let playwright;
let playwrightRoot;
try {
  playwright = require("playwright");
  playwrightRoot = path.dirname(require.resolve("playwright/package.json"));
} catch {
  playwright = require(PLAYWRIGHT_FALLBACK);
  playwrightRoot = PLAYWRIGHT_FALLBACK;
}

const ROOT = path.resolve(__dirname, "..");
const STAGE_ROOT = path.join(
  ROOT,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE",
);
const GENERATED_ROOT = path.join(STAGE_ROOT, "generated");
const ORACLE_ROOT = path.join(STAGE_ROOT, "webgl_oracle");
const REPORT_PATH = path.join(
  STAGE_ROOT,
  "reports",
  "ocio_webgl_oracle_report.json",
);
const CANDIDATE_PATH = path.join(
  STAGE_ROOT,
  "color_management_candidate.json",
);
const MANIFEST_PATH = path.join(
  GENERATED_ROOT,
  "ocio_assets_manifest.json",
);
const THREE_MODULE_PATH = path.join(
  ROOT,
  "高炉前端数据",
  "libs",
  "three",
  "three.module.js",
);
const VERIFIER_PATH = __filename;
const REQUIREMENT_ID =
  "REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720";
const STAGE_ID = "WEB-60_R2T";
const ENGINES = ["chromium", "firefox", "webkit"];
const WIDTH = 8;
const HEIGHT = 1;
const DPR = 1;
const REPEAT_COUNT = 2;
const FLOAT_MAX_ABS_ERROR = 2e-5;
const EIGHT_BIT_MAX_CODE_ERROR = 1;
const PAGE_PROMISE_TIMEOUT_MS = 120000;
const EXACT_VARIANT_ID = "exact_generated_shader";
const PORTABILITY_VARIANT_ID =
  "portability_nextafter_min_normal_candidate";
const UNIFORM_PORTABILITY_VARIANT_ID =
  "portability_uniform_nextafter_min_normal_candidate";
const EXACT_MIN_NORMAL_TOKEN = "1.17549435e-38";
const NEXTAFTER_MIN_NORMAL_TOKEN = "1.175494490952134e-38";
const PORTABILITY_UNIFORM_NAME = "ocio_portable_min_normal";
const EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES = 9;

const ORACLE_VECTOR_CONTRACT = Object.freeze([
  Object.freeze({
    id: "black",
    acceptanceLabel: "black",
    input: Object.freeze([0.0, 0.0, 0.0]),
  }),
  Object.freeze({
    id: "gray_18_percent",
    acceptanceLabel: "18-percent gray",
    input: Object.freeze([0.18, 0.18, 0.18]),
  }),
  Object.freeze({
    id: "white_1",
    acceptanceLabel: "linear white 1",
    input: Object.freeze([1.0, 1.0, 1.0]),
  }),
  Object.freeze({
    id: "gray_4",
    acceptanceLabel: "linear gray 4",
    input: Object.freeze([4.0, 4.0, 4.0]),
  }),
  Object.freeze({
    id: "red_18_percent",
    acceptanceLabel: "18-percent red",
    input: Object.freeze([0.18, 0.0, 0.0]),
  }),
  Object.freeze({
    id: "green_18_percent",
    acceptanceLabel: "18-percent green",
    input: Object.freeze([0.0, 0.18, 0.0]),
  }),
  Object.freeze({
    id: "blue_18_percent",
    acceptanceLabel: "18-percent blue",
    input: Object.freeze([0.0, 0.0, 0.18]),
  }),
  Object.freeze({
    id: "hdr_8_2_point5",
    acceptanceLabel: "HDR [8,2,0.5]",
    input: Object.freeze([8.0, 2.0, 0.5]),
  }),
]);

const MIME_TYPES = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glsl": "text/plain; charset=utf-8",
  ".bin": "application/octet-stream",
});

function sha256Buffer(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function sameArray(actual, expected) {
  return (
    Array.isArray(actual) &&
    Array.isArray(expected) &&
    actual.length === expected.length &&
    actual.every((value, index) => Object.is(value, expected[index]))
  );
}

function clamp01(value) {
  return Math.min(1, Math.max(0, value));
}

function expectedByte(value) {
  return Math.round(clamp01(value) * 255);
}

function float32Bits(value) {
  const buffer = Buffer.allocUnsafe(4);
  buffer.writeFloatLE(value, 0);
  return {
    value: buffer.readFloatLE(0),
    bits_hex: `0x${buffer.readUInt32LE(0).toString(16).padStart(8, "0")}`,
  };
}

function relativePath(filePath) {
  return path.relative(ROOT, filePath).replaceAll(path.sep, "/");
}

function serializeError(error, phase = undefined) {
  return {
    ...(phase ? { phase } : {}),
    name: error?.name || "Error",
    message: String(error?.message || error),
    stack: String(error?.stack || ""),
  };
}

function makeCheck(id, passed, detail = undefined) {
  return {
    id,
    passed: Boolean(passed),
    ...(detail === undefined ? {} : { detail }),
  };
}

function inspectFile(id, filePath, expected) {
  const bytes = fs.readFileSync(filePath);
  const actual = {
    bytes: bytes.byteLength,
    sha256: sha256Buffer(bytes),
  };
  const checks = expected.map((item) => ({
    source: item.source,
    expected_bytes: item.bytes,
    expected_sha256: item.sha256,
    bytes_match: actual.bytes === item.bytes,
    sha256_match: actual.sha256 === item.sha256,
  }));
  return {
    id,
    path: relativePath(filePath),
    ...actual,
    expected: checks,
    passed: checks.every(
      (item) => item.bytes_match && item.sha256_match,
    ),
  };
}

function buildResourceIntegrity() {
  const candidate = readJson(CANDIDATE_PATH);
  const manifest = readJson(MANIFEST_PATH);
  const exactShaderBuffer = fs.readFileSync(
    path.join(GENERATED_ROOT, manifest.shader.file),
  );
  const exactShaderSource = exactShaderBuffer.toString("utf8");
  const exactMinNormalTokenOccurrences =
    exactShaderSource.split(EXACT_MIN_NORMAL_TOKEN).length - 1;
  const portabilityShaderSource = exactShaderSource.replaceAll(
    EXACT_MIN_NORMAL_TOKEN,
    NEXTAFTER_MIN_NORMAL_TOKEN,
  );
  const portabilityShaderBuffer = Buffer.from(
    portabilityShaderSource,
    "utf8",
  );
  const uniformPortabilityShaderSource = exactShaderSource.replaceAll(
    EXACT_MIN_NORMAL_TOKEN,
    PORTABILITY_UNIFORM_NAME,
  );
  const uniformPortabilityShaderBuffer = Buffer.from(
    uniformPortabilityShaderSource,
    "utf8",
  );
  const exactTokenFloat32 = float32Bits(Number(EXACT_MIN_NORMAL_TOKEN));
  const portabilityTokenFloat32 = float32Bits(
    Number(NEXTAFTER_MIN_NORMAL_TOKEN),
  );
  const orderedTextures = [...manifest.textures].sort(
    (left, right) => left.ocio_order_index - right.ocio_order_index,
  );
  const manifestThree = manifest.sources.find(
    (source) => source.id === "three_r160_module",
  );
  const candidateAssets = candidate.generated_assets;
  const resources = [
    inspectFile("ocio_assets_manifest", MANIFEST_PATH, [
      {
        source: "color_management_candidate.generated_assets.manifest",
        bytes: candidateAssets.manifest.bytes,
        sha256: candidateAssets.manifest.sha256,
      },
    ]),
    inspectFile(
      "Blender52_AgX_MediumLow_sRGB.glsl",
      path.join(GENERATED_ROOT, manifest.shader.file),
      [
        {
          source: "color_management_candidate.generated_assets.shader",
          bytes: candidateAssets.shader.bytes,
          sha256: candidateAssets.shader.sha256,
        },
        {
          source: "ocio_assets_manifest.shader",
          bytes: manifest.shader.bytes,
          sha256: manifest.shader.sha256,
        },
      ],
    ),
    inspectFile(
      "ocio_lut3d_0_37_rgb32f_le.bin",
      path.join(GENERATED_ROOT, orderedTextures[0].rgb32f.file),
      [
        {
          source:
            "color_management_candidate.generated_assets.lut_37_rgb32f",
          bytes: candidateAssets.lut_37_rgb32f.bytes,
          sha256: candidateAssets.lut_37_rgb32f.sha256,
        },
        {
          source: "ocio_assets_manifest.textures[0].rgb32f",
          bytes: orderedTextures[0].rgb32f.bytes,
          sha256: orderedTextures[0].rgb32f.sha256,
        },
      ],
    ),
    inspectFile(
      "ocio_lut3d_0_37_rgba32f_le.bin",
      path.join(GENERATED_ROOT, orderedTextures[0].rgba32f.file),
      [
        {
          source:
            "color_management_candidate.generated_assets.lut_37_rgba32f",
          bytes: candidateAssets.lut_37_rgba32f.bytes,
          sha256: candidateAssets.lut_37_rgba32f.sha256,
        },
        {
          source: "ocio_assets_manifest.textures[0].rgba32f",
          bytes: orderedTextures[0].rgba32f.bytes,
          sha256: orderedTextures[0].rgba32f.sha256,
        },
      ],
    ),
    inspectFile(
      "ocio_lut3d_1_57_rgb32f_le.bin",
      path.join(GENERATED_ROOT, orderedTextures[1].rgb32f.file),
      [
        {
          source:
            "color_management_candidate.generated_assets.lut_57_rgb32f",
          bytes: candidateAssets.lut_57_rgb32f.bytes,
          sha256: candidateAssets.lut_57_rgb32f.sha256,
        },
        {
          source: "ocio_assets_manifest.textures[1].rgb32f",
          bytes: orderedTextures[1].rgb32f.bytes,
          sha256: orderedTextures[1].rgb32f.sha256,
        },
      ],
    ),
    inspectFile(
      "ocio_lut3d_1_57_rgba32f_le.bin",
      path.join(GENERATED_ROOT, orderedTextures[1].rgba32f.file),
      [
        {
          source:
            "color_management_candidate.generated_assets.lut_57_rgba32f",
          bytes: candidateAssets.lut_57_rgba32f.bytes,
          sha256: candidateAssets.lut_57_rgba32f.sha256,
        },
        {
          source: "ocio_assets_manifest.textures[1].rgba32f",
          bytes: orderedTextures[1].rgba32f.bytes,
          sha256: orderedTextures[1].rgba32f.sha256,
        },
      ],
    ),
    inspectFile("three_r160_module", THREE_MODULE_PATH, [
      {
        source: "color_management_candidate.source_contract.three_module",
        bytes: candidate.source_contract.three_module.bytes,
        sha256: candidate.source_contract.three_module.sha256,
      },
      {
        source: "ocio_assets_manifest.sources.three_r160_module",
        bytes: manifestThree?.bytes,
        sha256: manifestThree?.sha256,
      },
    ]),
  ];

  const points = manifest.cpu_oracle.points.map((point, index) => {
    const fixed = ORACLE_VECTOR_CONTRACT[index];
    return {
      index,
      id: point.id,
      input_scene_linear_rgb: point.input_scene_linear_rgb,
      expected_display_encoded_srgb:
        point.expected_display_encoded_srgb,
      expected_default_framebuffer_rgb8:
        point.expected_display_encoded_srgb.map(expectedByte),
      fixed_id_match: point.id === fixed?.id,
      fixed_input_match: sameArray(
        point.input_scene_linear_rgb,
        fixed?.input,
      ),
      candidate_label_match:
        candidate.webgl_acceptance.test_vectors[index] ===
        fixed?.acceptanceLabel,
    };
  });

  const semanticChecks = [
    makeCheck(
      "candidate_requirement",
      candidate.requirement_id === REQUIREMENT_ID,
      candidate.requirement_id,
    ),
    makeCheck(
      "candidate_stage",
      candidate.stage_id === STAGE_ID,
      candidate.stage_id,
    ),
    makeCheck(
      "manifest_requirement",
      manifest.requirement_id === REQUIREMENT_ID,
      manifest.requirement_id,
    ),
    makeCheck(
      "manifest_stage",
      manifest.stage_id === STAGE_ID,
      manifest.stage_id,
    ),
    makeCheck(
      "exact_transform_selected",
      candidate.selected_option ===
        "exact_blender_5_2_ocio_gpu_transform",
      candidate.selected_option,
    ),
    makeCheck(
      "rgba32f_threshold",
      candidate.webgl_acceptance.rgba32f_max_abs_error ===
        FLOAT_MAX_ABS_ERROR,
      candidate.webgl_acceptance.rgba32f_max_abs_error,
    ),
    makeCheck(
      "eight_bit_threshold",
      candidate.webgl_acceptance
        .eight_bit_framebuffer_max_error_code_values_per_channel ===
        EIGHT_BIT_MAX_CODE_ERROR,
      candidate.webgl_acceptance
        .eight_bit_framebuffer_max_error_code_values_per_channel,
    ),
    makeCheck(
      "not_evaluated_blocks",
      candidate.webgl_acceptance.not_evaluated_blocks_capture === true,
    ),
    makeCheck(
      "raw_shader_material",
      manifest.threejs_integration_contract.material ===
        "THREE.RawShaderMaterial",
      manifest.threejs_integration_contract.material,
    ),
    makeCheck(
      "no_tone_mapping",
      manifest.threejs_integration_contract.renderer_tone_mapping ===
        "THREE.NoToneMapping",
      manifest.threejs_integration_contract.renderer_tone_mapping,
    ),
    makeCheck(
      "direct_display_encoded_output",
      manifest.transform.output_is_display_encoded === true &&
        manifest.threejs_integration_contract.post_shader_oetf ===
          "FORBIDDEN" &&
        manifest.threejs_integration_contract.second_srgb_oetf_allowed ===
          false,
      manifest.transform,
    ),
    makeCheck(
      "two_luts_in_ocio_order",
      orderedTextures.length === 2 &&
        orderedTextures[0].ocio_order_index === 0 &&
        orderedTextures[1].ocio_order_index === 1 &&
        sameArray(manifest.shader.samplers_in_ocio_order, [
          "ocio_lut3d_0Sampler",
          "ocio_lut3d_1Sampler",
        ]),
      manifest.shader.samplers_in_ocio_order,
    ),
    makeCheck(
      "eight_fixed_oracle_points",
      points.length === WIDTH &&
        points.every(
          (point) =>
            point.fixed_id_match &&
            point.fixed_input_match &&
            point.candidate_label_match &&
            point.expected_display_encoded_srgb.length === 3 &&
            point.expected_display_encoded_srgb.every(Number.isFinite),
        ),
      points,
    ),
    makeCheck(
      "portability_candidate_one_literal_nine_token_diff",
      exactMinNormalTokenOccurrences ===
        EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES &&
        exactShaderSource !== portabilityShaderSource &&
        exactShaderSource.replaceAll(
          EXACT_MIN_NORMAL_TOKEN,
          NEXTAFTER_MIN_NORMAL_TOKEN,
        ) === portabilityShaderSource,
      {
        exact_token_occurrences: exactMinNormalTokenOccurrences,
        expected_token_occurrences:
          EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES,
        changed_unique_numeric_literals: 1,
        vec3_clamp_count: 3,
        original_token: EXACT_MIN_NORMAL_TOKEN,
        replacement_token: NEXTAFTER_MIN_NORMAL_TOKEN,
      },
    ),
    makeCheck(
      "portability_candidate_float32_nextafter",
      exactTokenFloat32.bits_hex === "0x00800000" &&
        portabilityTokenFloat32.bits_hex === "0x00800001",
      {
        original: exactTokenFloat32,
        replacement: portabilityTokenFloat32,
      },
    ),
    makeCheck(
      "uniform_portability_candidate_nine_token_diff",
      exactMinNormalTokenOccurrences ===
        EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES &&
        uniformPortabilityShaderSource !== exactShaderSource &&
        exactShaderSource.replaceAll(
          EXACT_MIN_NORMAL_TOKEN,
          PORTABILITY_UNIFORM_NAME,
        ) === uniformPortabilityShaderSource,
      {
        diff_token_count: EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES,
        original_token: EXACT_MIN_NORMAL_TOKEN,
        replacement_token: PORTABILITY_UNIFORM_NAME,
        uniform_value: portabilityTokenFloat32,
      },
    ),
  ];

  const implementationFiles = [
    path.join(ORACLE_ROOT, "index.html"),
    path.join(ORACLE_ROOT, "oracle.js"),
    path.join(ORACLE_ROOT, "README.md"),
    VERIFIER_PATH,
  ].map((filePath) => {
    const bytes = fs.readFileSync(filePath);
    return {
      path: relativePath(filePath),
      bytes: bytes.byteLength,
      sha256: sha256Buffer(bytes),
    };
  });

  return {
    candidate,
    manifest,
    points,
    report: {
      passed:
        resources.every((resource) => resource.passed) &&
        semanticChecks.every((check) => check.passed),
      candidate: {
        path: relativePath(CANDIDATE_PATH),
        bytes: fs.statSync(CANDIDATE_PATH).size,
        sha256: sha256File(CANDIDATE_PATH),
      },
      manifest: {
        path: relativePath(MANIFEST_PATH),
        bytes: fs.statSync(MANIFEST_PATH).size,
        sha256: sha256File(MANIFEST_PATH),
      },
      resources,
      semantic_checks: semanticChecks,
      implementation_files: implementationFiles,
      portability_candidate: {
        id: PORTABILITY_VARIANT_ID,
        approval_status: "candidate_not_approved",
        generated_asset_mutated_on_disk: false,
        generated_candidate_asset_written: false,
        changed_unique_numeric_literals: 1,
        diff_token_count:
          exactMinNormalTokenOccurrences ===
          EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES
            ? EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES
            : null,
        vec3_clamp_count: 3,
        original_token: EXACT_MIN_NORMAL_TOKEN,
        original_token_float32: exactTokenFloat32,
        replacement_token: NEXTAFTER_MIN_NORMAL_TOKEN,
        replacement_token_float32: portabilityTokenFloat32,
        exact_generated_shader: {
          bytes: exactShaderBuffer.byteLength,
          sha256: sha256Buffer(exactShaderBuffer),
        },
        in_memory_compiled_ocio_function: {
          bytes: portabilityShaderBuffer.byteLength,
          sha256: sha256Buffer(portabilityShaderBuffer),
        },
        passed_preflight:
          exactMinNormalTokenOccurrences ===
            EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES &&
          exactTokenFloat32.bits_hex === "0x00800000" &&
          portabilityTokenFloat32.bits_hex === "0x00800001",
      },
      uniform_portability_candidate: {
        id: UNIFORM_PORTABILITY_VARIANT_ID,
        approval_status: "candidate_not_approved",
        generated_asset_mutated_on_disk: false,
        generated_candidate_asset_written: false,
        changed_unique_numeric_literals: 1,
        diff_token_count: EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES,
        vec3_clamp_count: 3,
        original_token: EXACT_MIN_NORMAL_TOKEN,
        replacement_token: PORTABILITY_UNIFORM_NAME,
        uniform_value_decimal: NEXTAFTER_MIN_NORMAL_TOKEN,
        uniform_value_float32: portabilityTokenFloat32,
        exact_generated_shader: {
          bytes: exactShaderBuffer.byteLength,
          sha256: sha256Buffer(exactShaderBuffer),
        },
        in_memory_compiled_ocio_function: {
          bytes: uniformPortabilityShaderBuffer.byteLength,
          sha256: sha256Buffer(uniformPortabilityShaderBuffer),
        },
        passed_preflight:
          exactMinNormalTokenOccurrences ===
            EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES &&
          portabilityTokenFloat32.bits_hex === "0x00800001",
      },
    },
    variantExpectations: {
      [EXACT_VARIANT_ID]: {
        id: EXACT_VARIANT_ID,
        approval_status: "authoritative_exact_generated_asset",
        exact_generated_asset_sha256: sha256Buffer(exactShaderBuffer),
        compiled_ocio_function_bytes: exactShaderBuffer.byteLength,
        compiled_ocio_function_sha256: sha256Buffer(exactShaderBuffer),
        compiled_source_is_byte_exact_generated_asset: true,
        portability_token_diff: null,
      },
      [PORTABILITY_VARIANT_ID]: {
        id: PORTABILITY_VARIANT_ID,
        approval_status: "candidate_not_approved",
        exact_generated_asset_sha256: sha256Buffer(exactShaderBuffer),
        compiled_ocio_function_bytes:
          portabilityShaderBuffer.byteLength,
        compiled_ocio_function_sha256:
          sha256Buffer(portabilityShaderBuffer),
        compiled_source_is_byte_exact_generated_asset: false,
        portability_token_diff: {
          changed_unique_numeric_literals: 1,
          diff_token_count: EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES,
          vec3_clamp_count: 3,
          original_token: EXACT_MIN_NORMAL_TOKEN,
          replacement_token: NEXTAFTER_MIN_NORMAL_TOKEN,
          rationale:
            "float32 minimum normal nextafter toward positive infinity",
        },
      },
      [UNIFORM_PORTABILITY_VARIANT_ID]: {
        id: UNIFORM_PORTABILITY_VARIANT_ID,
        approval_status: "candidate_not_approved",
        exact_generated_asset_sha256: sha256Buffer(exactShaderBuffer),
        compiled_ocio_function_bytes:
          uniformPortabilityShaderBuffer.byteLength,
        compiled_ocio_function_sha256:
          sha256Buffer(uniformPortabilityShaderBuffer),
        compiled_source_is_byte_exact_generated_asset: false,
        portability_token_diff: {
          changed_unique_numeric_literals: 1,
          diff_token_count: EXPECTED_MIN_NORMAL_TOKEN_OCCURRENCES,
          vec3_clamp_count: 3,
          original_token: EXACT_MIN_NORMAL_TOKEN,
          replacement_token: PORTABILITY_UNIFORM_NAME,
          uniform_value_decimal: NEXTAFTER_MIN_NORMAL_TOKEN,
          uniform_value_float32_bits: "0x00800001",
          rationale:
            "avoid driver constant folding while preserving one shared highp float value",
        },
      },
    },
  };
}

function allowedFiles() {
  return [
    path.join(ORACLE_ROOT, "index.html"),
    path.join(ORACLE_ROOT, "oracle.js"),
    CANDIDATE_PATH,
    MANIFEST_PATH,
    path.join(GENERATED_ROOT, "Blender52_AgX_MediumLow_sRGB.glsl"),
    path.join(GENERATED_ROOT, "ocio_lut3d_0_37_rgba32f_le.bin"),
    path.join(GENERATED_ROOT, "ocio_lut3d_1_57_rgba32f_le.bin"),
    THREE_MODULE_PATH,
  ].map((filePath) => path.resolve(filePath));
}

function startIsolatedServer() {
  const allowList = new Set(allowedFiles());
  const requests = [];
  const serverErrors = [];
  const clientDisconnects = [];
  return new Promise((resolve, reject) => {
    const server = http.createServer((request, response) => {
      const record = {
        method: request.method,
        raw_url: request.url,
        pathname: null,
        file: null,
        status: null,
      };
      requests.push(record);
      response.on("finish", () => {
        record.status = response.statusCode;
      });

      if (request.method !== "GET" && request.method !== "HEAD") {
        response.writeHead(405, {
          "Content-Type": "text/plain; charset=utf-8",
          Allow: "GET, HEAD",
        });
        response.end("method not allowed");
        return;
      }

      let decodedPath;
      try {
        const url = new URL(request.url, "http://127.0.0.1");
        decodedPath = decodeURIComponent(url.pathname);
      } catch (error) {
        serverErrors.push(serializeError(error, "request_url_decode"));
        response.writeHead(400, {
          "Content-Type": "text/plain; charset=utf-8",
        });
        response.end("bad request");
        return;
      }
      record.pathname = decodedPath;
      const target = path.resolve(
        ROOT,
        decodedPath.replace(/^[/\\]+/, ""),
      );
      record.file = relativePath(target);
      if (!allowList.has(target)) {
        response.writeHead(403, {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
        });
        response.end("isolated oracle allow-list rejection");
        return;
      }

      try {
        const payload = fs.readFileSync(target);
        response.writeHead(200, {
          "Content-Type":
            MIME_TYPES[path.extname(target).toLowerCase()] ||
            "application/octet-stream",
          "Content-Length": payload.byteLength,
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        });
        response.end(request.method === "HEAD" ? undefined : payload);
      } catch (error) {
        serverErrors.push(serializeError(error, "static_file_read"));
        response.writeHead(500, {
          "Content-Type": "text/plain; charset=utf-8",
        });
        response.end("server error");
      }
    });

    server.on("clientError", (error, socket) => {
      if (error?.code === "ECONNRESET") {
        clientDisconnects.push({
          phase: "client_disconnect_after_browser_close",
          code: error.code,
          message: String(error.message || error),
          treated_as_http_failure: false,
        });
      } else {
        serverErrors.push(serializeError(error, "client_error"));
      }
      if (socket.writable) {
        socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
      }
    });
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      resolve({
        server,
        port: server.address().port,
        requests,
        serverErrors,
        clientDisconnects,
        allowList: [...allowList].map(relativePath),
      });
    });
  });
}

async function closeServer(server) {
  if (!server) {
    return;
  }
  if (typeof server.closeIdleConnections === "function") {
    server.closeIdleConnections();
  }
  if (typeof server.closeAllConnections === "function") {
    server.closeAllConnections();
  }
  await new Promise((resolve, reject) => {
    server.close((error) => {
      if (error && error.code !== "ERR_SERVER_NOT_RUNNING") {
        reject(error);
      } else {
        resolve();
      }
    });
  });
}

function independentOracleEvaluation(
  pageResult,
  oraclePoints,
  variantExpectation,
) {
  const checks = [];
  const add = (id, passed, detail = undefined) => {
    checks.push(makeCheck(id, passed, detail));
  };
  add(
    "page_result_present",
    pageResult !== null && typeof pageResult === "object",
  );
  if (!pageResult || typeof pageResult !== "object") {
    return {
      passed: false,
      checks,
      float_max_abs_error: null,
      eight_bit_max_code_error: null,
      float_repeat_max_abs_delta: null,
      eight_bit_repeat_byte_exact: false,
    };
  }

  add(
    "page_schema",
    pageResult.schema_version ===
      "bf3d.r2t.ocio_webgl_page_result.v1",
    pageResult.schema_version,
  );
  add(
    "page_requirement",
    pageResult.requirement_id === REQUIREMENT_ID,
    pageResult.requirement_id,
  );
  add("page_stage", pageResult.stage_id === STAGE_ID, pageResult.stage_id);
  add(
    "transform_variant_identity",
    pageResult.transform_variant?.id === variantExpectation.id &&
      pageResult.transform_variant?.approval_status ===
        variantExpectation.approval_status,
    {
      actual: pageResult.transform_variant,
      expected: variantExpectation,
    },
  );
  add(
    "exact_generated_shader_still_loaded",
    pageResult.transform_variant
      ?.exact_generated_asset_loaded_and_sha_verified === true &&
      pageResult.transform_variant?.exact_generated_asset_sha256 ===
        variantExpectation.exact_generated_asset_sha256 &&
      pageResult.transform_variant?.generated_asset_mutated_on_disk ===
        false,
    pageResult.transform_variant,
  );
  add(
    "compiled_ocio_variant_identity",
    pageResult.transform_variant?.compiled_ocio_function_bytes ===
      variantExpectation.compiled_ocio_function_bytes &&
      pageResult.transform_variant?.compiled_ocio_function_sha256 ===
        variantExpectation.compiled_ocio_function_sha256 &&
      pageResult.transform_variant
        ?.compiled_source_is_byte_exact_generated_asset ===
        variantExpectation.compiled_source_is_byte_exact_generated_asset &&
      JSON.stringify(
        pageResult.transform_variant?.portability_token_diff ?? null,
      ) ===
        JSON.stringify(
          variantExpectation.portability_token_diff ?? null,
        ),
    {
      actual: pageResult.transform_variant,
      expected: variantExpectation,
    },
  );
  add(
    "page_completed",
    pageResult.status === "completed" && pageResult.passed === true,
    {
      status: pageResult.status,
      passed: pageResult.passed,
      errors: pageResult.errors,
    },
  );
  add(
    "viewport_8x1_dpr1",
    pageResult.viewport?.css_width === WIDTH &&
      pageResult.viewport?.css_height === HEIGHT &&
      pageResult.viewport?.canvas_width === WIDTH &&
      pageResult.viewport?.canvas_height === HEIGHT &&
      pageResult.viewport?.device_pixel_ratio === DPR &&
      pageResult.viewport?.renderer_pixel_ratio === DPR,
    pageResult.viewport,
  );
  add(
    "page_thresholds_frozen",
    pageResult.thresholds?.rgba32f_max_abs_error ===
      FLOAT_MAX_ABS_ERROR &&
      pageResult.thresholds
        ?.eight_bit_framebuffer_max_error_code_values_per_channel ===
        EIGHT_BIT_MAX_CODE_ERROR &&
      pageResult.thresholds?.repeat_count === REPEAT_COUNT,
    pageResult.thresholds,
  );
  add(
    "resource_integrity_page",
    pageResult.resources?.passed === true &&
      Array.isArray(pageResult.resources?.checks) &&
      pageResult.resources.checks.every((item) => item.passed === true),
    pageResult.resources,
  );
  add(
    "webgl2_hard_gate",
    pageResult.support?.webgl2 === true &&
      pageResult.support?.three_renderer_webgl2 === true &&
      pageResult.webgl?.is_webgl2 === true,
    pageResult.support,
  );
  add(
    "float_rt_hard_gate",
    pageResult.support?.float_render_target === true &&
      pageResult.support?.ext_color_buffer_float === true &&
      pageResult.support?.float_framebuffer_status?.name ===
        "FRAMEBUFFER_COMPLETE",
    pageResult.support,
  );
  add(
    "texture_3d_hard_gate",
    pageResult.support?.texture_3d === true &&
      pageResult.webgl?.max_3d_texture_size >= 57,
    {
      texture_3d: pageResult.support?.texture_3d,
      max_3d_texture_size: pageResult.webgl?.max_3d_texture_size,
    },
  );
  add(
    "renderer_identity_complete",
    [
      pageResult.webgl?.vendor,
      pageResult.webgl?.renderer,
      pageResult.webgl?.version,
      pageResult.webgl?.shading_language_version,
    ].every((value) => typeof value === "string" && value.length > 0) &&
      Array.isArray(pageResult.webgl?.extensions),
    pageResult.webgl,
  );
  add(
    "context_msaa_disabled",
    pageResult.webgl?.context_attributes?.antialias === false,
    pageResult.webgl?.context_attributes,
  );
  add(
    "raw_shader_no_extra_transfer",
    pageResult.shader_contract?.is_raw_shader_material === true &&
      pageResult.shader_contract?.material_type ===
        "RawShaderMaterial" &&
      pageResult.shader_contract?.renderer_tone_mapping ===
        pageResult.shader_contract?.expected_no_tone_mapping &&
      pageResult.shader_contract?.material_tone_mapped === false &&
      pageResult.shader_contract?.colorspace_fragment_present === false &&
      pageResult.shader_contract?.linear_to_output_texel_present ===
        false &&
      pageResult.shader_contract?.shader_chunk_include_present === false &&
      pageResult.shader_contract?.precision_qualifiers?.float === "highp" &&
      pageResult.shader_contract?.precision_qualifiers?.int === "highp" &&
      pageResult.shader_contract?.precision_qualifiers?.sampler3D ===
        "highp" &&
      pageResult.shader_contract?.portability_uniform?.name ===
        PORTABILITY_UNIFORM_NAME &&
      pageResult.shader_contract?.portability_uniform
        ?.value_float32_bits === "0x00800001" &&
      pageResult.shader_contract?.subsequent_oetf ===
        "forbidden_and_absent",
    pageResult.shader_contract,
  );
  add(
    "dithering_disabled",
    pageResult.shader_contract?.dithering === false &&
      pageResult.shader_contract?.gl_dither_enabled_after_render === false,
    pageResult.shader_contract,
  );
  add(
    "data3dtexture_contract",
    Array.isArray(pageResult.texture_contract) &&
      pageResult.texture_contract.length === 2 &&
      pageResult.texture_contract.every(
        (texture, index) =>
          texture.ocio_order_index === index &&
          texture.sampler_name ===
            `ocio_lut3d_${index}Sampler` &&
          texture.edge_length === (index === 0 ? 37 : 57) &&
          texture.is_data_3d_texture === true &&
          texture.format === texture.expected_format &&
          texture.type === texture.expected_type &&
          texture.internal_format === "RGBA32F" &&
          texture.color_space === "" &&
          texture.min_filter === texture.mag_filter &&
          texture.generate_mipmaps === false,
      ),
    pageResult.texture_contract,
  );

  const repeats = Array.isArray(pageResult.repeats)
    ? pageResult.repeats
    : [];
  add("repeat_count", repeats.length === REPEAT_COUNT, repeats.length);
  let floatMaxAbsError = 0;
  let eightBitMaxCodeError = 0;
  let pointStructurePass = repeats.length === REPEAT_COUNT;
  let floatThresholdPass = repeats.length === REPEAT_COUNT;
  let byteThresholdPass = repeats.length === REPEAT_COUNT;

  for (let repeatIndex = 0; repeatIndex < repeats.length; repeatIndex += 1) {
    const repeat = repeats[repeatIndex];
    if (
      repeat.repeat_index !== repeatIndex ||
      !Array.isArray(repeat.points) ||
      repeat.points.length !== oraclePoints.length
    ) {
      pointStructurePass = false;
      floatThresholdPass = false;
      byteThresholdPass = false;
      continue;
    }
    for (
      let pointIndex = 0;
      pointIndex < oraclePoints.length;
      pointIndex += 1
    ) {
      const expected = oraclePoints[pointIndex];
      const actual = repeat.points[pointIndex];
      if (
        actual.id !== expected.id ||
        actual.index !== expected.index ||
        !sameArray(
          actual.input_scene_linear_rgb,
          expected.input_scene_linear_rgb,
        ) ||
        !sameArray(
          actual.expected_display_encoded_srgb,
          expected.expected_display_encoded_srgb,
        ) ||
        !sameArray(
          actual.expected_default_framebuffer_rgb8,
          expected.expected_default_framebuffer_rgb8,
        ) ||
        !Array.isArray(actual.actual_rgba32f) ||
        actual.actual_rgba32f.length !== 4 ||
        !Array.isArray(actual.actual_default_framebuffer_rgba8) ||
        actual.actual_default_framebuffer_rgba8.length !== 4
      ) {
        pointStructurePass = false;
        floatThresholdPass = false;
        byteThresholdPass = false;
        continue;
      }

      for (let channel = 0; channel < 3; channel += 1) {
        const floatValue = actual.actual_rgba32f[channel];
        const byteValue =
          actual.actual_default_framebuffer_rgba8[channel];
        const floatError = Math.abs(
          floatValue - expected.expected_display_encoded_srgb[channel],
        );
        const byteError = Math.abs(
          byteValue - expected.expected_default_framebuffer_rgb8[channel],
        );
        floatMaxAbsError = Math.max(floatMaxAbsError, floatError);
        eightBitMaxCodeError = Math.max(
          eightBitMaxCodeError,
          byteError,
        );
        if (
          !Number.isFinite(floatValue) ||
          floatError > FLOAT_MAX_ABS_ERROR
        ) {
          floatThresholdPass = false;
        }
        if (
          !Number.isInteger(byteValue) ||
          byteValue < 0 ||
          byteValue > 255 ||
          byteError > EIGHT_BIT_MAX_CODE_ERROR
        ) {
          byteThresholdPass = false;
        }
      }
      if (
        !Number.isFinite(actual.actual_rgba32f[3]) ||
        Math.abs(actual.actual_rgba32f[3] - 1) >
          FLOAT_MAX_ABS_ERROR
      ) {
        floatThresholdPass = false;
      }
      if (actual.actual_default_framebuffer_rgba8[3] !== 255) {
        byteThresholdPass = false;
      }
    }
  }
  add("eight_points_each_repeat", pointStructurePass);
  add(
    "rgba32f_all_channels_within_threshold",
    floatThresholdPass && floatMaxAbsError <= FLOAT_MAX_ABS_ERROR,
    {
      actual_max_abs_error: floatMaxAbsError,
      threshold: FLOAT_MAX_ABS_ERROR,
    },
  );
  add(
    "default_framebuffer_all_channels_within_one_code",
    byteThresholdPass &&
      eightBitMaxCodeError <= EIGHT_BIT_MAX_CODE_ERROR,
    {
      actual_max_code_error: eightBitMaxCodeError,
      threshold: EIGHT_BIT_MAX_CODE_ERROR,
    },
  );

  let floatRepeatMaxAbsDelta = null;
  let eightBitRepeatByteExact = false;
  if (
    repeats.length === REPEAT_COUNT &&
    repeats.every(
      (repeat) =>
        Array.isArray(repeat.float_rgba32f_flat) &&
        repeat.float_rgba32f_flat.length === WIDTH * 4 &&
        Array.isArray(repeat.default_framebuffer_rgba8_flat) &&
        repeat.default_framebuffer_rgba8_flat.length === WIDTH * 4,
    )
  ) {
    floatRepeatMaxAbsDelta = 0;
    for (
      let index = 0;
      index < repeats[0].float_rgba32f_flat.length;
      index += 1
    ) {
      floatRepeatMaxAbsDelta = Math.max(
        floatRepeatMaxAbsDelta,
        Math.abs(
          repeats[0].float_rgba32f_flat[index] -
            repeats[1].float_rgba32f_flat[index],
        ),
      );
    }
    eightBitRepeatByteExact = sameArray(
      repeats[0].default_framebuffer_rgba8_flat,
      repeats[1].default_framebuffer_rgba8_flat,
    );
  }
  add(
    "float_repeat_delta_within_threshold",
    floatRepeatMaxAbsDelta !== null &&
      floatRepeatMaxAbsDelta <= FLOAT_MAX_ABS_ERROR,
    {
      actual_max_abs_delta: floatRepeatMaxAbsDelta,
      threshold: FLOAT_MAX_ABS_ERROR,
    },
  );
  add(
    "eight_bit_repeats_byte_exact",
    eightBitRepeatByteExact,
  );
  add(
    "page_error_array_empty",
    Array.isArray(pageResult.errors) && pageResult.errors.length === 0,
    pageResult.errors,
  );

  return {
    passed: checks.every((check) => check.passed),
    checks,
    float_max_abs_error: floatMaxAbsError,
    eight_bit_max_code_error: eightBitMaxCodeError,
    float_repeat_max_abs_delta: floatRepeatMaxAbsDelta,
    eight_bit_repeat_byte_exact: eightBitRepeatByteExact,
  };
}

async function runEngine({
  engine,
  browserType,
  baseUrl,
  port,
  serverState,
  oraclePoints,
  variantExpectation,
}) {
  const startRequestIndex = serverState.requests.length;
  const result = {
    engine,
    transform_variant: {
      id: variantExpectation.id,
      approval_status: variantExpectation.approval_status,
    },
    status: "not_evaluated",
    evaluated: false,
    browser: {
      playwright_browser_version: null,
      executable_path: null,
      user_agent: null,
      navigator_platform: null,
    },
    viewport: {
      width: WIDTH,
      height: HEIGHT,
      device_scale_factor: DPR,
    },
    page_result: null,
    oracle_evaluation: null,
    console_messages: [],
    console_errors: [],
    page_errors: [],
    http_errors: [],
    external_requests: [],
    cleanup_errors: [],
    errors: [],
    requests: [],
    passed: false,
  };

  let browser = null;
  let context = null;
  let page = null;
  try {
    const launchOptions =
      engine === "firefox"
        ? {
            headless: true,
            firefoxUserPrefs: {
              "webgl.disable-angle": true,
              "webgl.force-enabled": true,
            },
          }
        : {
            headless: true,
          };
    result.browser.launch_options = launchOptions;
    result.browser.executable_path = browserType.executablePath();
    browser = await browserType.launch(launchOptions);
    result.browser.playwright_browser_version = browser.version();
    context = await browser.newContext({
      viewport: { width: WIDTH, height: HEIGHT },
      screen: { width: WIDTH, height: HEIGHT },
      deviceScaleFactor: DPR,
      colorScheme: "dark",
      serviceWorkers: "block",
    });
    await context.route("**/*", async (route) => {
      const requestUrl = route.request().url();
      let allowed = false;
      try {
        const parsed = new URL(requestUrl);
        allowed =
          parsed.protocol === "http:" &&
          parsed.hostname === "127.0.0.1" &&
          Number(parsed.port) === port;
      } catch {
        allowed = false;
      }
      if (!allowed) {
        result.external_requests.push({
          url: requestUrl,
          resource_type: route.request().resourceType(),
          method: route.request().method(),
          blocked: true,
        });
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    page = await context.newPage();
    page.on("console", (message) => {
      const item = {
        type: message.type(),
        text: message.text(),
        location: message.location(),
      };
      result.console_messages.push(item);
      if (message.type() === "error") {
        result.console_errors.push(item);
      }
    });
    page.on("pageerror", (error) => {
      result.page_errors.push(serializeError(error, "pageerror"));
    });
    page.on("response", (response) => {
      if (response.status() >= 400) {
        result.http_errors.push({
          kind: "http_response",
          url: response.url(),
          status: response.status(),
          status_text: response.statusText(),
        });
      }
    });
    page.on("requestfailed", (request) => {
      result.http_errors.push({
        kind: "request_failed",
        url: request.url(),
        method: request.method(),
        resource_type: request.resourceType(),
        failure: request.failure(),
      });
    });

    await page.goto(baseUrl, {
      waitUntil: "load",
      timeout: PAGE_PROMISE_TIMEOUT_MS,
    });
    await page.waitForFunction(
      () => Boolean(window.__OCIO_WEBGL_ORACLE_PROMISE__),
      undefined,
      { timeout: PAGE_PROMISE_TIMEOUT_MS },
    );
    result.page_result = await page.evaluate(async () => {
      return window.__OCIO_WEBGL_ORACLE_PROMISE__;
    });
    const browserEnvironment = await page.evaluate(() => ({
      user_agent: navigator.userAgent,
      navigator_platform: navigator.platform,
      device_pixel_ratio: window.devicePixelRatio,
      inner_width: window.innerWidth,
      inner_height: window.innerHeight,
      oracle_status: document.documentElement.dataset.oracleStatus || null,
    }));
    result.browser.user_agent = browserEnvironment.user_agent;
    result.browser.navigator_platform =
      browserEnvironment.navigator_platform;
    result.browser.page_environment = browserEnvironment;
    result.oracle_evaluation = independentOracleEvaluation(
      result.page_result,
      oraclePoints,
      variantExpectation,
    );
    result.evaluated = true;
    result.status =
      result.page_result?.status === "completed"
        ? "evaluated"
        : "page_failed";
  } catch (error) {
    result.status = browser
      ? "evaluation_failed"
      : "browser_launch_failed";
    result.errors.push(serializeError(error, result.status));
  } finally {
    if (page) {
      try {
        await page.close();
      } catch (error) {
        result.cleanup_errors.push(serializeError(error, "page_close"));
      }
    }
    if (context) {
      try {
        await context.close();
      } catch (error) {
        result.cleanup_errors.push(
          serializeError(error, "context_close"),
        );
      }
    }
    if (browser) {
      try {
        await browser.close();
      } catch (error) {
        result.cleanup_errors.push(
          serializeError(error, "browser_close"),
        );
      }
    }
    result.requests = serverState.requests.slice(startRequestIndex);
  }

  const protectedResourceRequests = result.requests.filter((request) => {
    const resource = String(request.file || request.pathname || "");
    return (
      resource.endsWith(".glb") ||
      resource.includes("frontend_dashboard_v3.server.html") ||
      resource.includes("bf3d-structural-review.js")
    );
  });
  result.isolation = {
    localhost_only: result.external_requests.length === 0,
    allow_list_only: result.requests.every(
      (request) => request.status === 200,
    ),
    production_page_controller_glb_requests: protectedResourceRequests,
    production_assets_not_loaded: protectedResourceRequests.length === 0,
  };
  result.passed =
    result.evaluated === true &&
    result.status === "evaluated" &&
    result.oracle_evaluation?.passed === true &&
    result.console_errors.length === 0 &&
    result.page_errors.length === 0 &&
    result.http_errors.length === 0 &&
    result.external_requests.length === 0 &&
    result.cleanup_errors.length === 0 &&
    result.errors.length === 0 &&
    result.isolation.allow_list_only === true &&
    result.isolation.production_assets_not_loaded === true;
  result.status = result.passed ? "passed" : result.status;
  return result;
}

function ensureHardGateEntries(results, variantExpectation) {
  for (const engine of ENGINES) {
    if (!results.some((item) => item.engine === engine)) {
      results.push({
        engine,
        transform_variant: {
          id: variantExpectation.id,
          approval_status: variantExpectation.approval_status,
        },
        status: "not_evaluated",
        evaluated: false,
        passed: false,
        errors: [
          {
            phase: "hard_gate",
            name: "NotEvaluated",
            message:
              "engine was not evaluated; not_evaluated is a hard failure",
            stack: "",
          },
        ],
      });
    }
  }
}

function summarizeEngines(results) {
  const evaluated = results.filter((item) => item.evaluated);
  const passed = results.filter((item) => item.passed);
  const notEvaluated = results
    .filter((item) => !item.evaluated)
    .map((item) => item.engine);
  return {
    expected_engines: ENGINES.length,
    evaluated_engines: evaluated.length,
    passed_engines: passed.length,
    failed_engines: results.length - passed.length,
    not_evaluated_engines: notEvaluated,
    per_engine: Object.fromEntries(
      results.map((item) => [
        item.engine,
        {
          status: item.status,
          evaluated: item.evaluated,
          passed: item.passed,
          renderer:
            item.page_result?.webgl?.unmasked_renderer ||
            item.page_result?.webgl?.renderer ||
            null,
          vendor:
            item.page_result?.webgl?.unmasked_vendor ||
            item.page_result?.webgl?.vendor ||
            null,
          version: item.page_result?.webgl?.version ?? null,
          float_max_abs_error:
            item.oracle_evaluation?.float_max_abs_error ?? null,
          eight_bit_max_code_error:
            item.oracle_evaluation?.eight_bit_max_code_error ?? null,
          float_repeat_max_abs_delta:
            item.oracle_evaluation?.float_repeat_max_abs_delta ?? null,
          eight_bit_repeat_byte_exact:
            item.oracle_evaluation?.eight_bit_repeat_byte_exact ?? false,
          console_error_count: item.console_errors?.length ?? null,
          page_error_count: item.page_errors?.length ?? null,
          http_error_count: item.http_errors?.length ?? null,
          external_request_count:
            item.external_requests?.length ?? null,
        },
      ]),
    ),
  };
}

function compareExactAndPortability(
  exactResults,
  portabilityResults,
  oraclePoints,
) {
  const perEngine = [];
  for (const engine of ENGINES) {
    const exact = exactResults.find((item) => item.engine === engine);
    const portability = portabilityResults.find(
      (item) => item.engine === engine,
    );
    const comparison = {
      engine,
      evaluated:
        exact?.evaluated === true && portability?.evaluated === true,
      non_black_observation_count: 0,
      non_black_float_max_abs_delta: null,
      non_black_eight_bit_max_code_delta: null,
      black: {
        exact_float_max_abs_error_to_cpu: null,
        portability_float_max_abs_error_to_cpu: null,
        exact_eight_bit_max_code_error_to_cpu: null,
        portability_eight_bit_max_code_error_to_cpu: null,
      },
      non_black_passed: false,
      portability_black_passed: false,
      repeats: [],
      passed: false,
    };
    if (
      !comparison.evaluated ||
      exact.page_result?.repeats?.length !== REPEAT_COUNT ||
      portability.page_result?.repeats?.length !== REPEAT_COUNT
    ) {
      perEngine.push(comparison);
      continue;
    }

    let nonBlackFloatMaxDelta = 0;
    let nonBlackByteMaxDelta = 0;
    let exactBlackFloatError = 0;
    let portabilityBlackFloatError = 0;
    let exactBlackByteError = 0;
    let portabilityBlackByteError = 0;
    let structurePass = true;
    for (
      let repeatIndex = 0;
      repeatIndex < REPEAT_COUNT;
      repeatIndex += 1
    ) {
      const exactRepeat = exact.page_result.repeats[repeatIndex];
      const portabilityRepeat =
        portability.page_result.repeats[repeatIndex];
      const repeatComparison = {
        repeat_index: repeatIndex,
        points: [],
      };
      for (
        let pointIndex = 0;
        pointIndex < oraclePoints.length;
        pointIndex += 1
      ) {
        const expected = oraclePoints[pointIndex];
        const exactPoint = exactRepeat.points?.[pointIndex];
        const portabilityPoint =
          portabilityRepeat.points?.[pointIndex];
        if (
          exactPoint?.id !== expected.id ||
          portabilityPoint?.id !== expected.id
        ) {
          structurePass = false;
          continue;
        }
        const floatAbsDeltaRgb = [0, 1, 2].map((channel) =>
          Math.abs(
            portabilityPoint.actual_rgba32f[channel] -
              exactPoint.actual_rgba32f[channel],
          ),
        );
        const byteAbsDeltaRgb = [0, 1, 2].map((channel) =>
          Math.abs(
            portabilityPoint.actual_default_framebuffer_rgba8[channel] -
              exactPoint.actual_default_framebuffer_rgba8[channel],
          ),
        );
        repeatComparison.points.push({
          id: expected.id,
          exact_rgba32f: exactPoint.actual_rgba32f,
          portability_rgba32f: portabilityPoint.actual_rgba32f,
          float_abs_delta_rgb: floatAbsDeltaRgb,
          exact_default_framebuffer_rgba8:
            exactPoint.actual_default_framebuffer_rgba8,
          portability_default_framebuffer_rgba8:
            portabilityPoint.actual_default_framebuffer_rgba8,
          eight_bit_abs_delta_rgb: byteAbsDeltaRgb,
        });
        if (expected.id === "black") {
          for (let channel = 0; channel < 3; channel += 1) {
            exactBlackFloatError = Math.max(
              exactBlackFloatError,
              Math.abs(
                exactPoint.actual_rgba32f[channel] -
                  expected.expected_display_encoded_srgb[channel],
              ),
            );
            portabilityBlackFloatError = Math.max(
              portabilityBlackFloatError,
              Math.abs(
                portabilityPoint.actual_rgba32f[channel] -
                  expected.expected_display_encoded_srgb[channel],
              ),
            );
            exactBlackByteError = Math.max(
              exactBlackByteError,
              Math.abs(
                exactPoint.actual_default_framebuffer_rgba8[channel] -
                  expected.expected_default_framebuffer_rgb8[channel],
              ),
            );
            portabilityBlackByteError = Math.max(
              portabilityBlackByteError,
              Math.abs(
                portabilityPoint.actual_default_framebuffer_rgba8[
                  channel
                ] -
                  expected.expected_default_framebuffer_rgb8[channel],
              ),
            );
          }
        } else {
          comparison.non_black_observation_count += 1;
          nonBlackFloatMaxDelta = Math.max(
            nonBlackFloatMaxDelta,
            ...floatAbsDeltaRgb,
          );
          nonBlackByteMaxDelta = Math.max(
            nonBlackByteMaxDelta,
            ...byteAbsDeltaRgb,
          );
        }
      }
      comparison.repeats.push(repeatComparison);
    }
    comparison.non_black_float_max_abs_delta =
      nonBlackFloatMaxDelta;
    comparison.non_black_eight_bit_max_code_delta =
      nonBlackByteMaxDelta;
    comparison.black = {
      exact_float_max_abs_error_to_cpu: exactBlackFloatError,
      portability_float_max_abs_error_to_cpu:
        portabilityBlackFloatError,
      exact_eight_bit_max_code_error_to_cpu: exactBlackByteError,
      portability_eight_bit_max_code_error_to_cpu:
        portabilityBlackByteError,
    };
    comparison.non_black_passed =
      structurePass &&
      comparison.non_black_observation_count === 7 * REPEAT_COUNT &&
      nonBlackFloatMaxDelta <= FLOAT_MAX_ABS_ERROR &&
      nonBlackByteMaxDelta === 0;
    comparison.portability_black_passed =
      portabilityBlackFloatError <= FLOAT_MAX_ABS_ERROR &&
      portabilityBlackByteError <= EIGHT_BIT_MAX_CODE_ERROR;
    comparison.passed =
      comparison.non_black_passed &&
      comparison.portability_black_passed;
    perEngine.push(comparison);
  }
  return {
    requirement:
      "all seven non-black points remain within the frozen float tolerance versus exact and byte-identical in RGBA8; portability black must meet the CPU oracle",
    non_black_float_delta_threshold: FLOAT_MAX_ABS_ERROR,
    non_black_eight_bit_code_delta_threshold: 0,
    portability_black_float_error_threshold: FLOAT_MAX_ABS_ERROR,
    portability_black_eight_bit_code_error_threshold:
      EIGHT_BIT_MAX_CODE_ERROR,
    per_engine: perEngine,
    all_engines_non_black_passed:
      perEngine.length === ENGINES.length &&
      perEngine.every((item) => item.non_black_passed),
    all_engines_portability_black_passed:
      perEngine.length === ENGINES.length &&
      perEngine.every((item) => item.portability_black_passed),
    passed:
      perEngine.length === ENGINES.length &&
      perEngine.every((item) => item.passed),
  };
}

function makeInitialReport(playwrightVersion) {
  return {
    schema_version: "bf3d.r2t.ocio_webgl_oracle_report.v1",
    requirement_id: REQUIREMENT_ID,
    stage_id: STAGE_ID,
    generated_at: new Date().toISOString(),
    passed: false,
    status: "running",
    contract: {
      isolation: "localhost_allow_list_only_no_external_network",
      production_page_loaded: false,
      production_controller_loaded: false,
      formal_glb_loaded: false,
      production_mutation_performed: false,
      browser_engines_hard_gate: [...ENGINES],
      unsupported_or_not_evaluated_is_failure: true,
      exact_generated_shader_is_release_hard_gate: true,
      portability_candidate_cannot_satisfy_exact_hard_gate: true,
      viewport: {
        css_width: WIDTH,
        css_height: HEIGHT,
        device_pixel_ratio: DPR,
      },
      repeat_count: REPEAT_COUNT,
      thresholds: {
        rgba32f_max_abs_error: FLOAT_MAX_ABS_ERROR,
        default_framebuffer_max_error_code_values_per_rgb_channel:
          EIGHT_BIT_MAX_CODE_ERROR,
        eight_bit_repeats_must_be_byte_identical: true,
        float_repeat_max_abs_delta: FLOAT_MAX_ABS_ERROR,
      },
      required_texture_contract: {
        class: "THREE.Data3DTexture",
        format: "THREE.RGBAFormat",
        type: "THREE.FloatType",
        internal_format: "RGBA32F",
        color_space: "THREE.NoColorSpace",
        filters: "THREE.NearestFilter",
        wrapping: "THREE.ClampToEdgeWrapping",
        mipmaps: false,
        ocio_order: [
          "ocio_lut3d_0Sampler",
          "ocio_lut3d_1Sampler",
        ],
      },
      required_final_pass: {
        material: "THREE.RawShaderMaterial",
        tone_mapping: "THREE.NoToneMapping",
        antialias: false,
        dithering: false,
        colorspace_fragment: false,
        linearToOutputTexel: false,
        subsequent_srgb_oetf: false,
        output:
          "OCIO display-encoded sRGB written directly to default RGBA8 framebuffer",
      },
    },
    environment: {
      node: process.version,
      platform: process.platform,
      arch: process.arch,
      playwright_version: playwrightVersion,
      playwright_root: playwrightRoot.replaceAll("\\", "/"),
    },
    resource_integrity: null,
    oracle_points: [],
    server: {
      address: "127.0.0.1",
      port: null,
      allow_list: [],
      errors: [],
      client_disconnects: [],
    },
    engines: [],
    exact_variant: {
      id: EXACT_VARIANT_ID,
      approval_status: "authoritative_exact_generated_asset",
      passed: false,
      status: "not_evaluated",
    },
    summary: {
      expected_engines: ENGINES.length,
      evaluated_engines: 0,
      passed_engines: 0,
      failed_engines: ENGINES.length,
      not_evaluated_engines: [...ENGINES],
    },
    portability_candidate: {
      id: PORTABILITY_VARIANT_ID,
      approval_status: "candidate_not_approved",
      passed: false,
      status: "not_evaluated",
      engines: [],
      summary: {
        expected_engines: ENGINES.length,
        evaluated_engines: 0,
        passed_engines: 0,
        failed_engines: ENGINES.length,
        not_evaluated_engines: [...ENGINES],
      },
      side_effect_comparison_to_exact: null,
    },
    uniform_portability_candidate: {
      id: UNIFORM_PORTABILITY_VARIANT_ID,
      approval_status: "candidate_not_approved",
      passed: false,
      status: "not_evaluated",
      engines: [],
      summary: {
        expected_engines: ENGINES.length,
        evaluated_engines: 0,
        passed_engines: 0,
        failed_engines: ENGINES.length,
        not_evaluated_engines: [...ENGINES],
      },
      side_effect_comparison_to_exact: null,
    },
    errors: [],
  };
}

async function main() {
  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  let playwrightVersion = null;
  try {
    playwrightVersion = readJson(
      path.join(playwrightRoot, "package.json"),
    ).version;
  } catch (error) {
    playwrightVersion = `unreadable: ${error.message}`;
  }
  const report = makeInitialReport(playwrightVersion);
  let serverState = null;

  try {
    const integrity = buildResourceIntegrity();
    report.resource_integrity = integrity.report;
    report.oracle_points = integrity.points;
    if (!integrity.report.passed) {
      throw new Error(
        "resource integrity or semantic contract failed before browser evaluation",
      );
    }

    serverState = await startIsolatedServer();
    report.server.port = serverState.port;
    report.server.allow_list = serverState.allowList;
    const oracleUrlPath = relativePath(
      path.join(ORACLE_ROOT, "index.html"),
    )
      .split("/")
      .map(encodeURIComponent)
      .join("/");
    const baseUrl =
      `http://127.0.0.1:${serverState.port}/` + oracleUrlPath;

    for (const engine of ENGINES) {
      const engineResult = await runEngine({
        engine,
        browserType: playwright[engine],
        baseUrl:
          `${baseUrl}?variant=` + encodeURIComponent(EXACT_VARIANT_ID),
        port: serverState.port,
        serverState,
        oraclePoints: integrity.points,
        variantExpectation:
          integrity.variantExpectations[EXACT_VARIANT_ID],
      });
      report.engines.push(engineResult);
    }
    for (const engine of ENGINES) {
      const engineResult = await runEngine({
        engine,
        browserType: playwright[engine],
        baseUrl:
          `${baseUrl}?variant=` +
          encodeURIComponent(PORTABILITY_VARIANT_ID),
        port: serverState.port,
        serverState,
        oraclePoints: integrity.points,
        variantExpectation:
          integrity.variantExpectations[PORTABILITY_VARIANT_ID],
      });
      report.portability_candidate.engines.push(engineResult);
    }
    for (const engine of ENGINES) {
      const engineResult = await runEngine({
        engine,
        browserType: playwright[engine],
        baseUrl:
          `${baseUrl}?variant=` +
          encodeURIComponent(UNIFORM_PORTABILITY_VARIANT_ID),
        port: serverState.port,
        serverState,
        oraclePoints: integrity.points,
        variantExpectation:
          integrity.variantExpectations[
            UNIFORM_PORTABILITY_VARIANT_ID
          ],
      });
      report.uniform_portability_candidate.engines.push(engineResult);
    }
    report.server.errors = [...serverState.serverErrors];
    report.server.client_disconnects = [
      ...serverState.clientDisconnects,
    ];
  } catch (error) {
    report.errors.push(serializeError(error, "main"));
  } finally {
    if (serverState?.server) {
      try {
        await closeServer(serverState.server);
      } catch (error) {
        report.errors.push(serializeError(error, "server_close"));
      }
    }
  }

  ensureHardGateEntries(report.engines, {
    id: EXACT_VARIANT_ID,
    approval_status: "authoritative_exact_generated_asset",
  });
  ensureHardGateEntries(report.portability_candidate.engines, {
    id: PORTABILITY_VARIANT_ID,
    approval_status: "candidate_not_approved",
  });
  ensureHardGateEntries(report.uniform_portability_candidate.engines, {
    id: UNIFORM_PORTABILITY_VARIANT_ID,
    approval_status: "candidate_not_approved",
  });
  report.summary = summarizeEngines(report.engines);
  report.portability_candidate.summary = summarizeEngines(
    report.portability_candidate.engines,
  );
  report.portability_candidate.side_effect_comparison_to_exact =
    compareExactAndPortability(
      report.engines,
      report.portability_candidate.engines,
      report.oracle_points,
    );
  report.uniform_portability_candidate.summary = summarizeEngines(
    report.uniform_portability_candidate.engines,
  );
  report.uniform_portability_candidate.side_effect_comparison_to_exact =
    compareExactAndPortability(
      report.engines,
      report.uniform_portability_candidate.engines,
      report.oracle_points,
    );

  const commonInfrastructurePassed =
    report.resource_integrity?.passed === true &&
    report.server.errors.length === 0 &&
    report.errors.length === 0;
  const exactPassed =
    commonInfrastructurePassed &&
    report.summary.evaluated_engines === ENGINES.length &&
    report.summary.passed_engines === ENGINES.length &&
    report.summary.not_evaluated_engines.length === 0;
  const portabilityPassed =
    commonInfrastructurePassed &&
    report.portability_candidate.summary.evaluated_engines ===
      ENGINES.length &&
    report.portability_candidate.summary.passed_engines ===
      ENGINES.length &&
    report.portability_candidate.summary.not_evaluated_engines.length ===
      0 &&
    report.portability_candidate.side_effect_comparison_to_exact
      .passed === true;
  const uniformPortabilityPassed =
    commonInfrastructurePassed &&
    report.uniform_portability_candidate.summary.evaluated_engines ===
      ENGINES.length &&
    report.uniform_portability_candidate.summary.passed_engines ===
      ENGINES.length &&
    report.uniform_portability_candidate.summary.not_evaluated_engines
      .length === 0 &&
    report.uniform_portability_candidate
      .side_effect_comparison_to_exact.passed === true;

  report.exact_variant.passed = exactPassed;
  report.exact_variant.status = exactPassed
    ? "passed"
    : "failed_hard_gate";
  report.portability_candidate.passed = portabilityPassed;
  report.portability_candidate.status = portabilityPassed
    ? "passed_candidate_not_approved"
    : "failed_candidate_not_approved";
  report.uniform_portability_candidate.passed =
    uniformPortabilityPassed;
  report.uniform_portability_candidate.status =
    uniformPortabilityPassed
      ? "passed_candidate_not_approved"
      : "failed_candidate_not_approved";
  report.passed = exactPassed;
  report.status = exactPassed
    ? "passed"
    : uniformPortabilityPassed
      ? "failed_exact_hard_gate_uniform_portability_candidate_passed_not_approved"
      : portabilityPassed
        ? "failed_exact_hard_gate_portability_candidate_passed_not_approved"
      : "failed";
  report.generated_at = new Date().toISOString();

  fs.writeFileSync(
    REPORT_PATH,
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
  process.stdout.write(
    `${JSON.stringify(
      {
        passed: report.passed,
        status: report.status,
        report: relativePath(REPORT_PATH),
        exact_summary: report.summary,
        portability_candidate: {
          approval_status:
            report.portability_candidate.approval_status,
          passed: report.portability_candidate.passed,
          status: report.portability_candidate.status,
          summary: report.portability_candidate.summary,
          side_effect_comparison_passed:
            report.portability_candidate
              .side_effect_comparison_to_exact?.passed ?? false,
        },
        uniform_portability_candidate: {
          approval_status:
            report.uniform_portability_candidate.approval_status,
          passed: report.uniform_portability_candidate.passed,
          status: report.uniform_portability_candidate.status,
          summary: report.uniform_portability_candidate.summary,
          side_effect_comparison_passed:
            report.uniform_portability_candidate
              .side_effect_comparison_to_exact?.passed ?? false,
        },
      },
      null,
      2,
    )}\n`,
  );
  if (!report.passed) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  try {
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(
      REPORT_PATH,
      `${JSON.stringify(
        {
          schema_version: "bf3d.r2t.ocio_webgl_oracle_report.v1",
          requirement_id: REQUIREMENT_ID,
          stage_id: STAGE_ID,
          generated_at: new Date().toISOString(),
          passed: false,
          status: "fatal",
          errors: [serializeError(error, "unhandled_main")],
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } catch {
    // Preserve the original failure if even the fail-closed report cannot write.
  }
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
