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
const ORACLE_ROOT = path.join(STAGE_ROOT, "ltc_runtime_oracle");
const REPORT_PATH = path.join(
  STAGE_ROOT,
  "reports",
  "ltc_runtime_oracle_report.json",
);
const THREE_ROOT = path.join(ROOT, "高炉前端数据", "libs", "three");
const THREE_MODULE_PATH = path.join(THREE_ROOT, "three.module.js");
const ADDON_PATH = path.join(
  THREE_ROOT,
  "lights",
  "RectAreaLightUniformsLib.js",
);
const VENDOR_LOCK_PATH = path.join(THREE_ROOT, "vendor.lock.json");
const THREE_LICENSE_PATH = path.join(
  THREE_ROOT,
  "LICENSE-three-r160.txt",
);
const LTC_LICENSE_PATH = path.join(
  THREE_ROOT,
  "LICENSE-ltc_code-5c0770b.txt",
);
const INDEX_PATH = path.join(ORACLE_ROOT, "index.html");
const ORACLE_PATH = path.join(ORACLE_ROOT, "oracle.js");
const README_PATH = path.join(ORACLE_ROOT, "README.md");
const VERIFIER_PATH = __filename;

const REQUIREMENT_ID =
  "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720";
const STAGE_ID = "WEB-60_R2T";
const ENGINES = Object.freeze(["chromium", "firefox", "webkit"]);
const RUNS_PER_ENGINE = 2;
const READBACK_REPEAT_COUNT = 2;
const WIDTH = 64;
const HEIGHT = 64;
const DPR = 1;
const PAGE_TIMEOUT_MS = 120000;

const FILE_CONTRACT = Object.freeze({
  three_module: Object.freeze({
    path: THREE_MODULE_PATH,
    bytes: 1272972,
    sha256:
      "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
  }),
  rect_area_ltc_addon: Object.freeze({
    path: ADDON_PATH,
    bytes: 313854,
    sha256:
      "08085bc942253cd54948bf936fecb66b54514a135872656e475a1cab09b55214",
  }),
  three_license: Object.freeze({
    path: THREE_LICENSE_PATH,
    bytes: 1081,
    sha256:
      "852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d",
  }),
  ltc_license: Object.freeze({
    path: LTC_LICENSE_PATH,
    bytes: 1718,
    sha256:
      "692a54e97fcadd0f04b14027386e53809c1dcf96de3e15b15af15731b15c1e94",
  }),
});

const TEXTURE_CONTRACT = Object.freeze([
  Object.freeze({
    id: "LTC_FLOAT_1",
    data_constructor: "Float32Array",
    scalar_count: 16384,
    data_bytes: 65536,
    data_sha256:
      "cf5cf21e5c112d2095c7e2418cb0a1ac54636e275d73e42f3453646c67f26814",
    expected_type_key: "FloatType",
  }),
  Object.freeze({
    id: "LTC_FLOAT_2",
    data_constructor: "Float32Array",
    scalar_count: 16384,
    data_bytes: 65536,
    data_sha256:
      "3b1b09080b26104498db277c14fc1733786465c6958e7a8403d688b1e24c2ff5",
    expected_type_key: "FloatType",
  }),
  Object.freeze({
    id: "LTC_HALF_1",
    data_constructor: "Uint16Array",
    scalar_count: 16384,
    data_bytes: 32768,
    data_sha256:
      "a391de32f868fd4aa8774917b793174b7be804c08e2fb8924c30f31d7aa8dcd7",
    expected_type_key: "HalfFloatType",
  }),
  Object.freeze({
    id: "LTC_HALF_2",
    data_constructor: "Uint16Array",
    scalar_count: 16384,
    data_bytes: 32768,
    data_sha256:
      "fa1ecbc6deb3c85ddf603cdf1e98e30279444f905eb1cebb849d761b570dd696",
    expected_type_key: "HalfFloatType",
  }),
]);

const MIME_TYPES = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
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

function relativePath(filePath) {
  return path.relative(ROOT, filePath).replaceAll(path.sep, "/");
}

function serializeError(error, phase = undefined) {
  return {
    ...(phase ? { phase } : {}),
    name: error?.name || "Error",
    message: String(error?.message || error),
    detail: error?.detail ?? null,
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

function inspectFile(id, descriptor, vendorEntry = undefined) {
  const payload = fs.readFileSync(descriptor.path);
  const actual = {
    bytes: payload.byteLength,
    sha256: sha256Buffer(payload),
  };
  const hardcodedMatch =
    actual.bytes === descriptor.bytes &&
    actual.sha256 === descriptor.sha256;
  const vendorLockMatch =
    vendorEntry === undefined ||
    (vendorEntry.bytes === actual.bytes &&
      vendorEntry.sha256 === actual.sha256 &&
      path.resolve(ROOT, vendorEntry.path) ===
        path.resolve(descriptor.path));
  return {
    id,
    path: relativePath(descriptor.path),
    expected_bytes: descriptor.bytes,
    actual_bytes: actual.bytes,
    expected_sha256: descriptor.sha256,
    actual_sha256: actual.sha256,
    hardcoded_contract_match: hardcodedMatch,
    vendor_lock_match: vendorLockMatch,
    passed: hardcodedMatch && vendorLockMatch,
  };
}

function inspectEvidenceFile(id, filePath) {
  const payload = fs.readFileSync(filePath);
  return {
    id,
    path: relativePath(filePath),
    bytes: payload.byteLength,
    sha256: sha256Buffer(payload),
  };
}

function buildSourceIntegrity() {
  const vendorLock = readJson(VENDOR_LOCK_PATH);
  const vendorEntries = new Map(
    vendorLock.vendored_files.map((entry) => [entry.id, entry]),
  );
  const resources = [
    inspectFile(
      "three_module",
      FILE_CONTRACT.three_module,
      vendorLock.three?.core,
    ),
    inspectFile(
      "rect_area_ltc_addon",
      FILE_CONTRACT.rect_area_ltc_addon,
      vendorEntries.get("three_r160_rect_area_light_uniforms_lib"),
    ),
    inspectFile(
      "three_license",
      FILE_CONTRACT.three_license,
      vendorEntries.get("three_r160_license"),
    ),
    inspectFile(
      "ltc_license",
      FILE_CONTRACT.ltc_license,
      vendorEntries.get("selfshadow_ltc_code_license"),
    ),
  ];

  const addonSource = fs.readFileSync(ADDON_PATH, "utf8");
  const indexSource = fs.readFileSync(INDEX_PATH, "utf8");
  const oracleSource = fs.readFileSync(ORACLE_PATH, "utf8");
  const runtimeContract = vendorLock.runtime_contract || {};
  const semanticChecks = [
    makeCheck(
      "vendor_lock_schema",
      vendorLock.schema_version ===
        "bf3d.three_r160.rect_area_ltc_vendor_lock.v1",
      vendorLock.schema_version,
    ),
    makeCheck(
      "vendor_lock_requirement",
      vendorLock.requirement_id === REQUIREMENT_ID,
      vendorLock.requirement_id,
    ),
    makeCheck(
      "vendor_lock_status",
      vendorLock.status === "vendor_sources_locked",
      vendorLock.status,
    ),
    makeCheck(
      "three_revision_lock",
      vendorLock.three?.revision === "160" &&
        vendorLock.three?.core?.revision === "160",
      vendorLock.three,
    ),
    makeCheck(
      "three_commit_lock",
      vendorLock.three?.peeled_commit ===
        "d04539a76736ff500cae883d6a38b3dd8643c548" &&
        vendorLock.three?.npm_git_head ===
          "d04539a76736ff500cae883d6a38b3dd8643c548",
      {
        peeled_commit: vendorLock.three?.peeled_commit,
        npm_git_head: vendorLock.three?.npm_git_head,
      },
    ),
    makeCheck(
      "runtime_same_instance_required",
      runtimeContract.same_three_esm_instance_required === true,
      runtimeContract.same_three_esm_instance_required,
    ),
    makeCheck(
      "runtime_init_once_required",
      runtimeContract.init_exactly_once_per_three_module_instance ===
        true,
      runtimeContract.init_exactly_once_per_three_module_instance,
    ),
    makeCheck(
      "runtime_texture_names",
      JSON.stringify(runtimeContract.expected_ltc_textures) ===
        JSON.stringify(TEXTURE_CONTRACT.map((item) => item.id)),
      runtimeContract.expected_ltc_textures,
    ),
    makeCheck(
      "runtime_texture_size",
      JSON.stringify(runtimeContract.expected_texture_size) ===
        JSON.stringify([64, 64]),
      runtimeContract.expected_texture_size,
    ),
    makeCheck(
      "runtime_extension_fail_closed",
      runtimeContract.webgl_extension_failure_policy === "fail_closed",
      runtimeContract.webgl_extension_failure_policy,
    ),
    makeCheck(
      "runtime_shadow_not_supported",
      runtimeContract.rect_area_shadow_supported === false,
      runtimeContract.rect_area_shadow_supported,
    ),
    makeCheck(
      "addon_bare_three_import",
      /}\s*from\s*['"]three['"]\s*;/.test(addonSource),
    ),
    makeCheck(
      "addon_exports_expected_class",
      addonSource.includes("class RectAreaLightUniformsLib") &&
        addonSource.includes("static init()") &&
        addonSource.includes("export { RectAreaLightUniformsLib };"),
    ),
    makeCheck(
      "addon_defines_all_four_uniforms",
      TEXTURE_CONTRACT.every((item) =>
        addonSource.includes(`UniformsLib.${item.id} = new DataTexture`),
      ),
    ),
    makeCheck(
      "addon_has_no_runtime_network_loader",
      !/\bfetch\s*\(|\bXMLHttpRequest\b|\bTextureLoader\b/.test(
        addonSource,
      ),
    ),
    makeCheck(
      "index_import_map_same_instance",
      indexSource.includes(
        '"three": "../../../../../高炉前端数据/libs/three/three.module.js"',
      ) &&
        indexSource.includes(
          '"three/addons/": "../../../../../高炉前端数据/libs/three/"',
        ),
    ),
    makeCheck(
      "oracle_imports_both_through_import_map",
      oracleSource.includes('import * as THREE from "three";') &&
        oracleSource.includes(
          'from "three/addons/lights/RectAreaLightUniformsLib.js";',
        ),
    ),
    makeCheck(
      "oracle_hardcodes_float_extension_fail_closed",
      oracleSource.includes(
        "fail_closed_no_half_branch_relaxation",
      ) &&
        oracleSource.includes("OES_texture_float_linear"),
    ),
  ];
  const evidenceFiles = [
    inspectEvidenceFile("oracle_index", INDEX_PATH),
    inspectEvidenceFile("oracle_runtime", ORACLE_PATH),
    inspectEvidenceFile("oracle_readme", README_PATH),
    inspectEvidenceFile("validator", VERIFIER_PATH),
    inspectEvidenceFile("vendor_lock", VENDOR_LOCK_PATH),
  ];
  return {
    vendor_lock: {
      path: relativePath(VENDOR_LOCK_PATH),
      bytes: fs.statSync(VENDOR_LOCK_PATH).size,
      sha256: sha256File(VENDOR_LOCK_PATH),
      schema_version: vendorLock.schema_version,
      requirement_id: vendorLock.requirement_id,
      status: vendorLock.status,
    },
    resources,
    semantic_checks: semanticChecks,
    texture_payload_contract: TEXTURE_CONTRACT,
    evidence_files: evidenceFiles,
    passed:
      resources.every((item) => item.passed) &&
      semanticChecks.every((item) => item.passed),
  };
}

function allowedFiles() {
  return [INDEX_PATH, ORACLE_PATH, THREE_MODULE_PATH, ADDON_PATH].map(
    (filePath) => path.resolve(filePath),
  );
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
        response.end("isolated LTC oracle allow-list rejection");
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
          "Content-Security-Policy":
            "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'self'",
          "Cross-Origin-Resource-Policy": "same-origin",
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

function independentlyEvaluatePage(pageResult) {
  const checks = [];
  const add = (id, passed, detail = undefined) => {
    checks.push(makeCheck(id, passed, detail));
  };
  add("page_result_present", pageResult !== null);
  add(
    "page_schema",
    pageResult?.schema_version ===
      "bf3d.r2t.ltc_runtime_page_result.v1",
    pageResult?.schema_version,
  );
  add(
    "page_requirement",
    pageResult?.requirement_id === REQUIREMENT_ID,
    pageResult?.requirement_id,
  );
  add("page_stage", pageResult?.stage_id === STAGE_ID, pageResult?.stage_id);
  add("page_completed", pageResult?.status === "completed", pageResult?.status);
  add("page_claimed_pass", pageResult?.passed === true, pageResult?.passed);
  add(
    "candidate_runtime_prerequisite_classification",
    pageResult?.classification?.artifact_role ===
      "isolated_candidate_runtime_prerequisite" &&
      pageResult?.classification?.runtime_prerequisite_only === true,
    pageResult?.classification,
  );
  add(
    "release_boundaries_remain_false",
    pageResult?.classification?.capture_eligible === false &&
      pageResult?.classification?.approval_granted === false &&
      pageResult?.classification?.production_integration_allowed ===
        false &&
      pageResult?.classification
        ?.blender_photometric_equivalence_claimed === false &&
      pageResult?.classification?.rect_area_light_shadow_claimed ===
        false,
    pageResult?.classification,
  );
  add(
    "same_esm_instance",
    pageResult?.import_contract?.passed === true &&
      pageResult?.import_contract?.oracle_three_specifier === "three" &&
      pageResult?.import_contract?.addon_internal_three_specifier ===
        "three" &&
      pageResult?.import_contract
        ?.uniforms_initialized_on_oracle_three_namespace === true &&
      pageResult?.import_contract
        ?.shader_selected_uniforms_lib_texture_identity === true,
    pageResult?.import_contract,
  );
  add(
    "source_integrity",
    pageResult?.source_integrity?.passed === true &&
      pageResult?.source_integrity?.checks?.length === 2 &&
      pageResult.source_integrity.checks.every(
        (item) =>
          item.passed === true &&
          item.actual_bytes === item.expected_bytes &&
          item.actual_sha256 === item.expected_sha256,
      ),
    pageResult?.source_integrity,
  );

  const init = pageResult?.init_once;
  add(
    "controller_effective_init_exactly_once",
    init?.controller_requested_calls === 1 &&
      init?.controller_effective_init_calls === 1 &&
      init?.addon_init_effective_calls === 1,
    init,
  );
  add(
    "duplicate_probe_rejected_before_addon",
    init?.duplicate_audit_attempts === 1 &&
      init?.duplicate_attempts_rejected_before_addon === 1 &&
      init?.duplicate_error?.code ===
        "DUPLICATE_LTC_INIT_REJECTED" &&
      init?.texture_identities_preserved_after_duplicate_probe ===
        true &&
      init?.exactly_once_passed === true,
    init,
  );
  const textures = init?.textures || [];
  for (const expected of TEXTURE_CONTRACT) {
    const actual = textures.find((item) => item.id === expected.id);
    add(
      `texture_${expected.id}`,
      actual?.passed === true &&
        actual?.width === 64 &&
        actual?.height === 64 &&
        actual?.data_constructor === expected.data_constructor &&
        actual?.scalar_count === expected.scalar_count &&
        actual?.data_bytes === expected.data_bytes &&
        actual?.data_sha256 === expected.data_sha256 &&
        actual?.expected_type_key === expected.expected_type_key &&
        actual?.format === actual?.expected_format &&
        actual?.type === actual?.expected_type &&
        actual?.mapping === actual?.expected_mapping &&
        actual?.wrap_s === actual?.expected_wrap &&
        actual?.wrap_t === actual?.expected_wrap &&
        actual?.mag_filter === actual?.expected_mag_filter &&
        actual?.min_filter === actual?.expected_min_filter &&
        actual?.anisotropy === 1 &&
        actual?.generate_mipmaps === false &&
        actual?.flip_y === false &&
        actual?.premultiply_alpha === false &&
        actual?.unpack_alignment === 1 &&
        actual?.color_space === actual?.expected_color_space &&
        actual?.internal_format === null &&
        actual?.mipmap_count === 0 &&
        actual?.version_after_init_before_upload === 1,
      actual,
    );
  }
  add(
    "exactly_four_textures",
    textures.length === TEXTURE_CONTRACT.length,
    textures.map((item) => item.id),
  );

  const runtime = pageResult?.runtime;
  add(
    "webgl2_float_branch_supported",
    runtime?.support?.webgl2_supported === true &&
      runtime?.support?.three_renderer_webgl2 === true &&
      runtime?.support?.required_extension ===
        "OES_texture_float_linear" &&
      runtime?.support?.required_float_texture_branch_supported ===
        true &&
      runtime?.support?.half_float_fallback_accepted_for_this_gate ===
        false,
    runtime?.support,
  );
  add(
    "r160_branch_texture_identity",
    runtime?.extension_branch?.native_extension_present === true &&
      runtime?.extension_branch?.expected_branch === "float" &&
      JSON.stringify(
        runtime?.extension_branch?.actual_selected_textures,
      ) === JSON.stringify(["LTC_FLOAT_1", "LTC_FLOAT_2"]) &&
      runtime?.extension_branch
        ?.selected_texture_identity_matches_uniforms_lib === true &&
      runtime?.extension_branch?.passed === true,
    runtime?.extension_branch,
  );
  add(
    "mesh_standard_shader_compiled",
    runtime?.shader?.is_mesh_standard_material === true &&
      runtime?.shader?.material_type === "MeshStandardMaterial" &&
      runtime?.shader?.on_before_compile_call_count >= 1 &&
      runtime?.shader?.ltc_uniforms_present === true &&
      runtime?.shader?.linked_program_count >= 1 &&
      runtime?.shader?.programs?.every(
        (program) =>
          program.linked === true && program.runnable === true,
      ) &&
      runtime?.shader?.passed === true,
    runtime?.shader,
  );
  add(
    "minimal_fixture",
    runtime?.fixture?.rect_area_light_count === 1 &&
      runtime?.fixture?.mesh_standard_material_count === 1 &&
      runtime?.fixture?.ambient_light_count === 0 &&
      runtime?.fixture?.environment_present === false &&
      runtime?.fixture?.mesh_standard_material?.metalness === 1 &&
      runtime?.fixture?.mesh_standard_material?.emissive_linear_rgb
        ?.every((channel) => channel === 0) &&
      runtime?.fixture?.rect_area_light?.cast_shadow === false &&
      runtime?.fixture?.rect_area_light?.shadow_property_present ===
        false &&
      runtime?.fixture?.renderer?.shadow_map_enabled === false,
    runtime?.fixture,
  );
  add(
    "claim_boundaries",
    runtime?.fixture?.claims
      ?.proves_shader_compiles_and_renders_non_black === true &&
      runtime?.fixture?.claims
        ?.proves_deterministic_rgba8_readback === true &&
      runtime?.fixture?.claims
        ?.lit_output_requires_rect_area_ltc_specular_path === true &&
      runtime?.fixture?.claims
        ?.proves_blender_photometric_equivalence === false &&
      runtime?.fixture?.claims?.proves_rect_area_light_shadows ===
        false,
    runtime?.fixture?.claims,
  );
  const readback = runtime?.readback;
  const litRepeats = readback?.lit_repeats || [];
  add(
    "readback_repeat_count",
    readback?.repeat_count === READBACK_REPEAT_COUNT &&
      litRepeats.length === READBACK_REPEAT_COUNT,
    {
      declared: readback?.repeat_count,
      actual: litRepeats.length,
    },
  );
  add(
    "lit_non_black",
    readback?.lit_non_black === true &&
      litRepeats.every(
        (item) =>
          item.rgb_nonzero_pixel_count > 0 &&
          item.rgb_sum > 0 &&
          item.center_rgba8
            ?.slice(0, 3)
            .some((channel) => channel > 0) &&
          item.min_alpha_code === 255 &&
          item.max_alpha_code === 255 &&
          item.webgl_errors?.length === 0,
      ),
    litRepeats,
  );
  add(
    "lit_readback_deterministic",
    readback?.repeat_byte_identical === true &&
      litRepeats.length === READBACK_REPEAT_COUNT &&
      litRepeats.every(
        (item) => item.sha256 === litRepeats[0]?.sha256,
      ),
    litRepeats.map((item) => item.sha256),
  );
  const control = readback?.zero_intensity_control;
  add(
    "zero_intensity_control_black",
    readback?.zero_intensity_control_black === true &&
      control?.rgb_nonzero_pixel_count === 0 &&
      control?.rgb_sum === 0 &&
      control?.center_rgba8
        ?.slice(0, 3)
        .every((channel) => channel === 0) &&
      control?.min_alpha_code === 255 &&
      control?.max_alpha_code === 255 &&
      control?.webgl_errors?.length === 0,
    control,
  );
  add(
    "page_webgl_errors_zero",
    Array.isArray(runtime?.webgl_errors) &&
      runtime.webgl_errors.length === 0,
    runtime?.webgl_errors,
  );
  add(
    "page_error_array_empty",
    Array.isArray(pageResult?.errors) &&
      pageResult.errors.length === 0,
    pageResult?.errors,
  );
  add(
    "viewport_contract",
    pageResult?.viewport?.css_width === WIDTH &&
      pageResult?.viewport?.css_height === HEIGHT &&
      pageResult?.viewport?.canvas_width === WIDTH &&
      pageResult?.viewport?.canvas_height === HEIGHT &&
      pageResult?.viewport?.device_pixel_ratio === DPR,
    pageResult?.viewport,
  );
  return {
    checks,
    passed: checks.every((check) => check.passed),
    lit_readback_sha256: litRepeats[0]?.sha256 ?? null,
    shader_fragment_sha256:
      runtime?.shader?.fragment_shader_sha256 ?? null,
    selected_branch:
      runtime?.extension_branch?.expected_branch ?? null,
  };
}

async function runEngineOnce({
  engine,
  browserType,
  runIndex,
  baseUrl,
  port,
  serverState,
}) {
  const startRequestIndex = serverState.requests.length;
  const result = {
    engine,
    run_index: runIndex,
    status: "not_evaluated",
    evaluated: false,
    passed: false,
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
    independent_evaluation: null,
    console_messages: [],
    console_errors: [],
    page_errors: [],
    http_errors: [],
    external_requests: [],
    cleanup_errors: [],
    errors: [],
    requests: [],
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
        : { headless: true };
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

    await page.goto(`${baseUrl}?engine=${engine}&run=${runIndex}`, {
      waitUntil: "load",
      timeout: PAGE_TIMEOUT_MS,
    });
    await page.waitForFunction(
      () =>
        Boolean(
          window.__BF3D_R2T_LTC_RUNTIME_ORACLE_PROMISE__,
        ),
      undefined,
      { timeout: PAGE_TIMEOUT_MS },
    );
    result.page_result = await page.evaluate(async () => {
      return window.__BF3D_R2T_LTC_RUNTIME_ORACLE_PROMISE__;
    });
    const browserEnvironment = await page.evaluate(() => ({
      user_agent: navigator.userAgent,
      navigator_platform: navigator.platform,
      device_pixel_ratio: window.devicePixelRatio,
      inner_width: window.innerWidth,
      inner_height: window.innerHeight,
      oracle_status:
        document.documentElement.dataset.oracleStatus || null,
    }));
    result.browser.user_agent = browserEnvironment.user_agent;
    result.browser.navigator_platform =
      browserEnvironment.navigator_platform;
    result.browser.page_environment = browserEnvironment;
    result.independent_evaluation = independentlyEvaluatePage(
      result.page_result,
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

  const protectedRequests = result.requests.filter((request) => {
    const resource = String(request.file || request.pathname || "");
    return (
      resource.endsWith(".glb") ||
      resource.includes("frontend_dashboard_v3.server.html") ||
      resource.includes("bf3d-structural-review.js")
    );
  });
  result.isolation = {
    localhost_only: result.external_requests.length === 0,
    allow_list_only:
      result.requests.length >= 4 &&
      result.requests.every((request) => request.status === 200),
    production_page_controller_glb_requests: protectedRequests,
    production_assets_not_loaded: protectedRequests.length === 0,
  };
  result.error_counts = {
    console: result.console_errors.length,
    page: result.page_errors.length,
    http: result.http_errors.length,
    external: result.external_requests.length,
    cleanup: result.cleanup_errors.length,
    harness: result.errors.length,
  };
  result.passed =
    result.evaluated === true &&
    result.status === "evaluated" &&
    result.independent_evaluation?.passed === true &&
    result.error_counts.console === 0 &&
    result.error_counts.page === 0 &&
    result.error_counts.http === 0 &&
    result.error_counts.external === 0 &&
    result.error_counts.cleanup === 0 &&
    result.error_counts.harness === 0 &&
    result.isolation.localhost_only === true &&
    result.isolation.allow_list_only === true &&
    result.isolation.production_assets_not_loaded === true;
  result.status = result.passed ? "passed" : result.status;
  return result;
}

function ensureRunEntries(runs) {
  for (const engine of ENGINES) {
    for (let runIndex = 0; runIndex < RUNS_PER_ENGINE; runIndex += 1) {
      if (
        !runs.some(
          (item) =>
            item.engine === engine && item.run_index === runIndex,
        )
      ) {
        runs.push({
          engine,
          run_index: runIndex,
          status: "not_evaluated",
          evaluated: false,
          passed: false,
          errors: [
            {
              phase: "hard_gate",
              name: "NotEvaluated",
              message:
                "required engine run was not evaluated; fail closed",
              detail: null,
              stack: "",
            },
          ],
          console_errors: [],
          page_errors: [],
          http_errors: [],
          external_requests: [],
          cleanup_errors: [],
        });
      }
    }
  }
}

function summarizeEngineGroups(runs) {
  return ENGINES.map((engine) => {
    const engineRuns = runs
      .filter((item) => item.engine === engine)
      .sort((left, right) => left.run_index - right.run_index);
    const litHashes = engineRuns.map(
      (item) =>
        item.independent_evaluation?.lit_readback_sha256 ?? null,
    );
    const shaderHashes = engineRuns.map(
      (item) =>
        item.independent_evaluation?.shader_fragment_sha256 ?? null,
    );
    const branches = engineRuns.map(
      (item) => item.independent_evaluation?.selected_branch ?? null,
    );
    const repeatOutputsByteIdentical =
      litHashes.length === RUNS_PER_ENGINE &&
      litHashes[0] !== null &&
      litHashes.every((hash) => hash === litHashes[0]);
    const shaderSourcesIdentical =
      shaderHashes.length === RUNS_PER_ENGINE &&
      shaderHashes[0] !== null &&
      shaderHashes.every((hash) => hash === shaderHashes[0]);
    const extensionBranchConsistent =
      branches.length === RUNS_PER_ENGINE &&
      branches.every((branch) => branch === "float");
    const passed =
      engineRuns.length === RUNS_PER_ENGINE &&
      engineRuns.every((item) => item.passed) &&
      repeatOutputsByteIdentical &&
      shaderSourcesIdentical &&
      extensionBranchConsistent;
    return {
      engine,
      expected_runs: RUNS_PER_ENGINE,
      evaluated_runs: engineRuns.filter((item) => item.evaluated).length,
      passed_runs: engineRuns.filter((item) => item.passed).length,
      browser_versions: [
        ...new Set(
          engineRuns
            .map((item) => item.browser?.playwright_browser_version)
            .filter(Boolean),
        ),
      ],
      renderer:
        engineRuns[0]?.page_result?.webgl?.unmasked_renderer ||
        engineRuns[0]?.page_result?.webgl?.renderer ||
        null,
      vendor:
        engineRuns[0]?.page_result?.webgl?.unmasked_vendor ||
        engineRuns[0]?.page_result?.webgl?.vendor ||
        null,
      required_float_branch_supported: engineRuns.every(
        (item) =>
          item.page_result?.runtime?.support
            ?.required_float_texture_branch_supported === true,
      ),
      selected_branches: branches,
      extension_branch_consistent: extensionBranchConsistent,
      lit_readback_sha256: litHashes,
      independent_run_outputs_byte_identical:
        repeatOutputsByteIdentical,
      shader_fragment_sha256: shaderHashes,
      shader_sources_identical: shaderSourcesIdentical,
      error_counts: {
        console: engineRuns.reduce(
          (sum, item) => sum + (item.console_errors?.length || 0),
          0,
        ),
        page: engineRuns.reduce(
          (sum, item) => sum + (item.page_errors?.length || 0),
          0,
        ),
        http: engineRuns.reduce(
          (sum, item) => sum + (item.http_errors?.length || 0),
          0,
        ),
        external: engineRuns.reduce(
          (sum, item) => sum + (item.external_requests?.length || 0),
          0,
        ),
      },
      passed,
    };
  });
}

function makeInitialReport(playwrightVersion) {
  return {
    schema_version: "bf3d.r2t.ltc_runtime_oracle_report.v1",
    requirement_id: REQUIREMENT_ID,
    stage_id: STAGE_ID,
    generated_at: new Date().toISOString(),
    status: "running",
    passed: false,
    classification: {
      artifact_role: "candidate_runtime_prerequisite",
      runtime_prerequisite_verified: false,
      capture_eligible: false,
      approval_granted: false,
      production_integration_allowed: false,
      next_stage_automatically_allowed: false,
      blender_photometric_equivalence_claimed: false,
      rect_area_light_shadow_claimed: false,
    },
    contract: {
      isolation: "localhost_explicit_file_allow_list_no_external_network",
      browser_engines_hard_gate: [...ENGINES],
      fresh_runs_per_engine: RUNS_PER_ENGINE,
      readbacks_per_page_run: READBACK_REPEAT_COUNT,
      unsupported_or_not_evaluated_is_failure: true,
      webgl2_required: true,
      float_texture_extension_required:
        "OES_texture_float_linear",
      half_float_fallback_satisfies_this_gate: false,
      same_three_esm_instance_required: true,
      effective_addon_init_calls_required: 1,
      duplicate_attempt_policy:
        "one explicit audit attempt must be rejected before addon invocation",
      required_textures: TEXTURE_CONTRACT,
      required_fixture:
        "one RectAreaLight plus one MeshStandardMaterial plane",
      required_readback:
        "non-black lit RGBA8, black zero-intensity control, byte-identical repeats",
      production_page_loaded: false,
      production_controller_loaded: false,
      formal_glb_loaded: false,
      production_mutation_performed: false,
      capture_approval_effect: "none",
      production_approval_effect: "none",
    },
    environment: {
      node: process.version,
      platform: process.platform,
      arch: process.arch,
      playwright_version: playwrightVersion,
      playwright_root: playwrightRoot.replaceAll("\\", "/"),
    },
    source_integrity: null,
    server: {
      address: "127.0.0.1",
      port: null,
      allow_list: [],
      errors: [],
      client_disconnects: [],
    },
    runs: [],
    engine_groups: [],
    summary: {
      expected_engines: ENGINES.length,
      expected_runs: ENGINES.length * RUNS_PER_ENGINE,
      evaluated_runs: 0,
      passed_runs: 0,
      failed_runs: ENGINES.length * RUNS_PER_ENGINE,
      not_evaluated_runs: ENGINES.flatMap((engine) =>
        Array.from(
          { length: RUNS_PER_ENGINE },
          (_, runIndex) => `${engine}#${runIndex}`,
        ),
      ),
      engines_passed: 0,
      error_counts: {
        console: 0,
        page: 0,
        http: 0,
        external: 0,
      },
    },
    errors: [],
  };
}

function buildSummary(report) {
  const notEvaluatedRuns = report.runs
    .filter((item) => !item.evaluated)
    .map((item) => `${item.engine}#${item.run_index}`);
  return {
    expected_engines: ENGINES.length,
    expected_runs: ENGINES.length * RUNS_PER_ENGINE,
    evaluated_runs: report.runs.filter((item) => item.evaluated).length,
    passed_runs: report.runs.filter((item) => item.passed).length,
    failed_runs: report.runs.filter((item) => !item.passed).length,
    not_evaluated_runs: notEvaluatedRuns,
    engines_passed: report.engine_groups.filter((item) => item.passed)
      .length,
    error_counts: {
      console: report.runs.reduce(
        (sum, item) => sum + (item.console_errors?.length || 0),
        0,
      ),
      page: report.runs.reduce(
        (sum, item) => sum + (item.page_errors?.length || 0),
        0,
      ),
      http: report.runs.reduce(
        (sum, item) => sum + (item.http_errors?.length || 0),
        0,
      ),
      external: report.runs.reduce(
        (sum, item) => sum + (item.external_requests?.length || 0),
        0,
      ),
    },
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
    report.source_integrity = buildSourceIntegrity();
    if (!report.source_integrity.passed) {
      throw new Error(
        "source integrity or runtime semantic contract failed before browser evaluation",
      );
    }
    serverState = await startIsolatedServer();
    report.server.port = serverState.port;
    report.server.allow_list = serverState.allowList;
    const oracleUrlPath = relativePath(INDEX_PATH)
      .split("/")
      .map(encodeURIComponent)
      .join("/");
    const baseUrl =
      `http://127.0.0.1:${serverState.port}/` + oracleUrlPath;
    for (const engine of ENGINES) {
      for (
        let runIndex = 0;
        runIndex < RUNS_PER_ENGINE;
        runIndex += 1
      ) {
        report.runs.push(
          await runEngineOnce({
            engine,
            browserType: playwright[engine],
            runIndex,
            baseUrl,
            port: serverState.port,
            serverState,
          }),
        );
      }
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

  ensureRunEntries(report.runs);
  report.runs.sort(
    (left, right) =>
      ENGINES.indexOf(left.engine) - ENGINES.indexOf(right.engine) ||
      left.run_index - right.run_index,
  );
  report.engine_groups = summarizeEngineGroups(report.runs);
  report.summary = buildSummary(report);
  const allErrorCountsZero = Object.values(
    report.summary.error_counts,
  ).every((count) => count === 0);
  const runtimePassed =
    report.source_integrity?.passed === true &&
    report.server.errors.length === 0 &&
    report.errors.length === 0 &&
    report.summary.evaluated_runs ===
      ENGINES.length * RUNS_PER_ENGINE &&
    report.summary.passed_runs ===
      ENGINES.length * RUNS_PER_ENGINE &&
    report.summary.not_evaluated_runs.length === 0 &&
    report.summary.engines_passed === ENGINES.length &&
    allErrorCountsZero;
  report.passed = runtimePassed;
  report.status = runtimePassed
    ? "runtime_prerequisite_verified_candidate_not_approved"
    : "runtime_prerequisite_failed_closed";
  report.classification.runtime_prerequisite_verified =
    runtimePassed;
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
        summary: report.summary,
        engine_groups: report.engine_groups.map((item) => ({
          engine: item.engine,
          passed: item.passed,
          evaluated_runs: item.evaluated_runs,
          passed_runs: item.passed_runs,
          required_float_branch_supported:
            item.required_float_branch_supported,
          independent_run_outputs_byte_identical:
            item.independent_run_outputs_byte_identical,
          error_counts: item.error_counts,
        })),
        classification: report.classification,
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
          schema_version: "bf3d.r2t.ltc_runtime_oracle_report.v1",
          requirement_id: REQUIREMENT_ID,
          stage_id: STAGE_ID,
          generated_at: new Date().toISOString(),
          status: "fatal",
          passed: false,
          classification: {
            artifact_role: "candidate_runtime_prerequisite",
            runtime_prerequisite_verified: false,
            capture_eligible: false,
            approval_granted: false,
            production_integration_allowed: false,
            next_stage_automatically_allowed: false,
            blender_photometric_equivalence_claimed: false,
            rect_area_light_shadow_claimed: false,
          },
          errors: [serializeError(error, "unhandled_main")],
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } catch {
    // Preserve the original failure if even fail-closed reporting fails.
  }
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
