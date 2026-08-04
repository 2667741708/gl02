#!/usr/bin/env node
"use strict";

/**
 * Execute the frozen WEB-60 R2T Three.js r160 linear photometric fixture.
 *
 * Requirement:
 *   REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720
 *
 * The browser page uses NoToneMapping and an RGBA32F render target. This
 * runner serves an explicit allow-list, blocks external traffic, opens two
 * fresh pages in each browser engine, and writes raw linear sample statistics.
 * It performs no fitting and loads no production page/controller/GLB.
 */

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
const FIXTURE_ROOT = path.join(STAGE_ROOT, "photometric_fixture");
const WEB_ROOT = path.join(FIXTURE_ROOT, "web");
const INDEX_PATH = path.join(WEB_ROOT, "index.html");
const ORACLE_PATH = path.join(WEB_ROOT, "oracle.js");
const DEFINITION_PATH = path.join(FIXTURE_ROOT, "fixture_definition.json");
const OUTPUT_PATH = path.join(
  FIXTURE_ROOT,
  "three_linear_readback.json",
);
const THREE_PATH = path.join(
  ROOT,
  "高炉前端数据",
  "libs",
  "three",
  "three.module.js",
);
const LTC_ADDON_PATH = path.join(
  ROOT,
  "高炉前端数据",
  "libs",
  "three",
  "lights",
  "RectAreaLightUniformsLib.js",
);

const REQUIREMENT_ID =
  "REQ-BF3D-R2T-P40-PHOTOMETRIC-CALIBRATION-20260720";
const STAGE_ID = "WEB-60_R2T";
const ENGINES = Object.freeze(["chromium", "firefox", "webkit"]);
const RUNS_PER_ENGINE = 2;
const WIDTH = 32;
const HEIGHT = 32;
const DPR = 1;
const PAGE_TIMEOUT_MS = 300000;
const SOURCE_CONTRACT = Object.freeze({
  three_module: Object.freeze({
    path: THREE_PATH,
    bytes: 1272972,
    sha256:
      "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
  }),
  rect_area_ltc_addon: Object.freeze({
    path: LTC_ADDON_PATH,
    bytes: 313854,
    sha256:
      "08085bc942253cd54948bf936fecb66b54514a135872656e475a1cab09b55214",
  }),
});

const MIME_TYPES = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
});

function parseArgs() {
  const args = process.argv.slice(2);
  const index = args.indexOf("--definition-sha256");
  if (index < 0 || !args[index + 1]) {
    throw new Error("--definition-sha256 is required");
  }
  return { definitionSha256: args[index + 1] };
}

function sha256Buffer(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
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

function inspectFile(id, descriptor) {
  const payload = fs.readFileSync(descriptor.path);
  const actual = {
    bytes: payload.byteLength,
    sha256: sha256Buffer(payload),
  };
  return {
    id,
    path: relativePath(descriptor.path),
    expected_bytes: descriptor.bytes,
    actual_bytes: actual.bytes,
    expected_sha256: descriptor.sha256,
    actual_sha256: actual.sha256,
    passed:
      actual.bytes === descriptor.bytes &&
      actual.sha256 === descriptor.sha256,
  };
}

function buildSourceIntegrity(definitionSha256) {
  const resources = Object.entries(SOURCE_CONTRACT).map(
    ([id, descriptor]) => inspectFile(id, descriptor),
  );
  const definitionPayload = fs.readFileSync(DEFINITION_PATH);
  const definition = JSON.parse(definitionPayload.toString("utf8"));
  const definitionActualSha = sha256Buffer(definitionPayload);
  const definitionPassed =
    definitionActualSha === definitionSha256 &&
    definition.requirement_id === REQUIREMENT_ID &&
    definition.status === "frozen_before_render" &&
    definition.renderer_contract?.three?.revision === "160" &&
    definition.renderer_contract?.three?.tone_mapping ===
      "THREE.NoToneMapping" &&
    definition.renderer_contract?.three?.render_target === "RGBA32F" &&
    definition.renderer_contract?.three?.msaa === false &&
    definition.renderer_contract?.three?.samples === 0 &&
    definition.renderer_contract?.three?.dithering === false &&
    definition.renderer_contract?.three?.post_processing === false &&
    definition.renderer_contract?.three?.shadows === false &&
    definition.renderer_contract?.three?.ao === false &&
    definition.renderer_contract?.three?.extra_gi === false;
  const expectedSampleIds = Object.values(definition.families).flatMap(
    (family) => family.samples.map((sample) => sample.id),
  );
  const uniqueIds = new Set(expectedSampleIds);
  const sampleContractPassed =
    expectedSampleIds.length === uniqueIds.size &&
    expectedSampleIds.length > 0;
  return {
    resources,
    definition: {
      path: relativePath(DEFINITION_PATH),
      bytes: definitionPayload.byteLength,
      expected_sha256: definitionSha256,
      actual_sha256: definitionActualSha,
      passed: definitionPassed,
    },
    expected_sample_ids: expectedSampleIds,
    expected_sample_count: expectedSampleIds.length,
    sample_contract_passed: sampleContractPassed,
    passed:
      resources.every((item) => item.passed) &&
      definitionPassed &&
      sampleContractPassed,
  };
}

function makeServerAllowList() {
  const files = [
    INDEX_PATH,
    ORACLE_PATH,
    DEFINITION_PATH,
    THREE_PATH,
    LTC_ADDON_PATH,
  ];
  return new Map(
    files.map((filePath) => [
      `/${relativePath(filePath)}`,
      filePath,
    ]),
  );
}

function startServer() {
  const allowList = makeServerAllowList();
  const requests = [];
  const errors = [];
  const server = http.createServer((request, response) => {
    let decodedPath = null;
    try {
      const requestUrl = new URL(request.url, "http://127.0.0.1");
      decodedPath = decodeURIComponent(requestUrl.pathname);
    } catch (error) {
      response.writeHead(400);
      response.end("bad request");
      errors.push(serializeError(error, "decode_request"));
      return;
    }
    const filePath = allowList.get(decodedPath);
    if (!filePath) {
      requests.push({
        method: request.method,
        pathname: decodedPath,
        file: null,
        status: 404,
      });
      response.writeHead(404);
      response.end("not found");
      return;
    }
    try {
      const payload = fs.readFileSync(filePath);
      const mime =
        MIME_TYPES[path.extname(filePath).toLowerCase()] ||
        "application/octet-stream";
      response.writeHead(200, {
        "Content-Type": mime,
        "Content-Length": payload.byteLength,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      });
      response.end(payload);
      requests.push({
        method: request.method,
        pathname: decodedPath,
        file: relativePath(filePath),
        status: 200,
        bytes: payload.byteLength,
      });
    } catch (error) {
      errors.push(serializeError(error, "serve_file"));
      response.writeHead(500);
      response.end("server error");
    }
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({
        server,
        port: address.port,
        allowList: Array.from(allowList.keys()).sort(),
        requests,
        errors,
      });
    });
  });
}

function closeServer(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

function independentlyEvaluatePage(
  pageResult,
  expectedDefinitionSha,
  expectedSampleIds,
  definition,
) {
  const sampleIds = Array.isArray(pageResult?.samples)
    ? pageResult.samples.map((sample) => sample.id)
    : [];
  const uniqueIds = new Set(sampleIds);
  const expectedSet = new Set(expectedSampleIds);
  const sampleSetMatches =
    sampleIds.length === expectedSampleIds.length &&
    uniqueIds.size === sampleIds.length &&
    sampleIds.every((id) => expectedSet.has(id));
  const sampleContractsPass =
    Array.isArray(pageResult?.samples) &&
    pageResult.samples.every((sample) => {
      const renderer = sample.renderer || {};
      const statistics = sample.statistics || {};
      return (
        sample.status === "evaluated" &&
        sample.other_light_family_count === 0 &&
        renderer.tone_mapping === renderer.expected_tone_mapping &&
        renderer.tone_mapping_exposure === 1 &&
        renderer.output_color_space === "srgb-linear" &&
        renderer.render_target_type === "FloatType" &&
        renderer.render_target_samples === 0 &&
        renderer.shadows === false &&
        renderer.antialias === false &&
        renderer.dithering === false &&
        renderer.post_processing === false &&
        renderer.ao === false &&
        renderer.extra_gi === false &&
        statistics.finite === true &&
        Number.isFinite(statistics.linear_rec709_luminance)
      );
    });
  const samplesById = new Map(
    (pageResult?.samples || []).map((sample) => [sample.id, sample]),
  );
  const denominatorEpsilon =
    definition.fit_contract.denominator_epsilon;
  const familySignalSummary = Object.fromEntries(
    Object.entries(definition.families).map(([family, descriptor]) => {
      const fitRows = descriptor.samples.filter(
        (sample) => sample.partition === "fit",
      );
      const values = fitRows.map((row) => {
        const sample = samplesById.get(row.id);
        return {
          id: row.id,
          weight: row.weight,
          value: sample?.statistics?.linear_rec709_luminance,
        };
      });
      const allFinite = values.every((row) =>
        Number.isFinite(row.value),
      );
      const finiteValues = values
        .map((row) => row.value)
        .filter(Number.isFinite);
      const denominator = allFinite
        ? values.reduce(
            (sum, row) =>
              sum + row.weight * row.value * row.value,
            0,
          )
        : null;
      const passed =
        values.length === fitRows.length &&
        values.length > 0 &&
        allFinite &&
        Number.isFinite(denominator) &&
        denominator > denominatorEpsilon;
      return [
        family,
        {
          partition: "fit",
          sample_count: values.length,
          finite_sample_count: finiteValues.length,
          positive_sample_count: finiteValues.filter(
            (value) => value > 0,
          ).length,
          min_three_k1:
            finiteValues.length > 0 ? Math.min(...finiteValues) : null,
          max_three_k1:
            finiteValues.length > 0 ? Math.max(...finiteValues) : null,
          mean_three_k1:
            finiteValues.length > 0
              ? finiteValues.reduce((sum, value) => sum + value, 0) /
                finiteValues.length
              : null,
          weighted_wls_denominator: denominator,
          denominator_epsilon: denominatorEpsilon,
          zero_denominator_policy: "fail_closed",
          passed,
        },
      ];
    }),
  );
  const familySignalsPass = Object.values(familySignalSummary).every(
    (summary) => summary.passed,
  );
  const worldPmrem = pageResult?.diagnostics?.world_pmrem;
  const worldPmremPass =
    worldPmrem?.implementation ===
      "constant Linear-sRGB Float32 equirectangular texture through PMREM" &&
    worldPmrem?.source_type === "FloatType" &&
    worldPmrem?.source_color_space === "srgb-linear" &&
    JSON.stringify(worldPmrem?.source_resolution) ===
      JSON.stringify([64, 32]) &&
    JSON.stringify(worldPmrem?.radiance_linear_rgb) ===
      JSON.stringify(
        definition.families.world.radiance_linear_rgb,
      ) &&
    worldPmrem?.cube_size === 16 &&
    worldPmrem?.three_r160_lod_min === 4 &&
    worldPmrem?.minimum_cube_size === 16 &&
    worldPmrem?.ambient_light_substitution === false;
  const passed =
    pageResult?.schema_version ===
      "bf3d.r2t.three_linear_page_result.v1" &&
    pageResult?.requirement_id === REQUIREMENT_ID &&
    pageResult?.status === "completed" &&
    pageResult?.evaluated === true &&
    pageResult?.passed === true &&
    pageResult?.definition?.sha256 === expectedDefinitionSha &&
    pageResult?.runtime?.three_revision === "160" &&
    pageResult?.runtime?.webgl2 === true &&
    pageResult?.runtime?.ext_color_buffer_float === true &&
    pageResult?.runtime?.ltc_float_texture_ready === true &&
    pageResult?.contract?.tone_mapping === "NoToneMapping" &&
    pageResult?.contract?.exposure === 1 &&
    pageResult?.contract?.linear_float_readback === true &&
    pageResult?.contract?.msaa === false &&
    pageResult?.contract?.dithering === false &&
    pageResult?.contract?.post_processing === false &&
    pageResult?.contract?.shadows === false &&
    pageResult?.contract?.ao === false &&
    pageResult?.contract?.extra_gi === false &&
    pageResult?.contract?.one_family_per_render === true &&
    pageResult?.contract?.beauty_capture === false &&
    pageResult?.contract?.mask_capture === false &&
    Array.isArray(pageResult?.not_evaluated) &&
    pageResult.not_evaluated.length === 0 &&
    Array.isArray(pageResult?.errors) &&
    pageResult.errors.length === 0 &&
    sampleSetMatches &&
    sampleContractsPass &&
    familySignalsPass &&
    worldPmremPass;
  return {
    passed,
    sample_set_matches: sampleSetMatches,
    sample_contracts_pass: sampleContractsPass,
    family_signal_contracts_pass: familySignalsPass,
    family_signal_summary: familySignalSummary,
    world_pmrem_contract_pass: worldPmremPass,
    world_pmrem: worldPmrem ?? null,
    evaluated_sample_count: sampleIds.length,
    sample_scalar_sha256: sha256Buffer(
      Buffer.from(
        JSON.stringify(
          pageResult?.samples?.map((sample) => ({
            id: sample.id,
            value: sample.statistics.linear_rec709_luminance,
          })) || [],
        ),
        "utf8",
      ),
    ),
  };
}

async function runEngineOnce({
  engine,
  browserType,
  runIndex,
  baseUrl,
  port,
  serverState,
  definitionSha256,
  expectedSampleIds,
  definition,
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
      if (message.type() === "error") result.console_errors.push(item);
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
        Boolean(window.__BF3D_R2T_PHOTOMETRIC_FIXTURE_PROMISE__),
      undefined,
      { timeout: PAGE_TIMEOUT_MS },
    );
    result.page_result = await page.evaluate(async () => {
      return window.__BF3D_R2T_PHOTOMETRIC_FIXTURE_PROMISE__;
    });
    const pageEnvironment = await page.evaluate(() => ({
      user_agent: navigator.userAgent,
      navigator_platform: navigator.platform,
      device_pixel_ratio: window.devicePixelRatio,
      inner_width: window.innerWidth,
      inner_height: window.innerHeight,
      oracle_status:
        document.documentElement.dataset.oracleStatus || null,
    }));
    result.browser.user_agent = pageEnvironment.user_agent;
    result.browser.navigator_platform =
      pageEnvironment.navigator_platform;
    result.browser.page_environment = pageEnvironment;
    result.independent_evaluation = independentlyEvaluatePage(
      result.page_result,
      definitionSha256,
      expectedSampleIds,
      definition,
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
      result.requests.length >= 5 &&
      result.requests.every((request) => request.status === 200),
    production_page_controller_glb_requests: protectedRequests,
    production_assets_not_loaded: protectedRequests.length === 0,
    production_mutation_performed: false,
  };
  result.passed =
    result.evaluated &&
    result.status === "evaluated" &&
    result.independent_evaluation?.passed === true &&
    result.console_errors.length === 0 &&
    result.page_errors.length === 0 &&
    result.http_errors.length === 0 &&
    result.external_requests.length === 0 &&
    result.cleanup_errors.length === 0 &&
    result.errors.length === 0 &&
    result.isolation.localhost_only &&
    result.isolation.allow_list_only &&
    result.isolation.production_assets_not_loaded;
  return result;
}

function summarize(report) {
  const expectedRuns = ENGINES.length * RUNS_PER_ENGINE;
  const groups = ENGINES.map((engine) => {
    const runs = report.runs.filter((run) => run.engine === engine);
    const hashes = runs.map(
      (run) => run.independent_evaluation?.sample_scalar_sha256 ?? null,
    );
    return {
      engine,
      expected_runs: RUNS_PER_ENGINE,
      evaluated_runs: runs.filter((run) => run.evaluated).length,
      passed_runs: runs.filter((run) => run.passed).length,
      sample_scalar_sha256: hashes,
      fresh_runs_byte_identical:
        hashes.length === RUNS_PER_ENGINE &&
        hashes[0] !== null &&
        hashes.every((hash) => hash === hashes[0]),
      refit_performed: false,
      passed:
        runs.length === RUNS_PER_ENGINE &&
        runs.every((run) => run.passed),
    };
  });
  return {
    expected_engines: ENGINES.length,
    expected_runs: expectedRuns,
    evaluated_runs: report.runs.filter((run) => run.evaluated).length,
    passed_runs: report.runs.filter((run) => run.passed).length,
    failed_runs: report.runs.filter((run) => !run.passed).length,
    not_evaluated_runs: report.runs
      .filter((run) => !run.evaluated)
      .map((run) => `${run.engine}#${run.run_index}`),
    engines_passed: groups.filter((group) => group.passed).length,
    error_counts: {
      console: report.runs.reduce(
        (sum, run) => sum + run.console_errors.length,
        0,
      ),
      page: report.runs.reduce(
        (sum, run) => sum + run.page_errors.length,
        0,
      ),
      http: report.runs.reduce(
        (sum, run) => sum + run.http_errors.length,
        0,
      ),
      external: report.runs.reduce(
        (sum, run) => sum + run.external_requests.length,
        0,
      ),
    },
    engine_groups: groups,
  };
}

async function main() {
  fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
  const { definitionSha256 } = parseArgs();
  const definition = readJson(DEFINITION_PATH);
  const sourceIntegrity = buildSourceIntegrity(definitionSha256);
  const report = {
    schema_version: "bf3d.r2t.three_linear_readback.v1",
    requirement_id: REQUIREMENT_ID,
    stage_id: STAGE_ID,
    generated_at: new Date().toISOString(),
    status: "running",
    evaluated: false,
    passed: false,
    definition: {
      path: relativePath(DEFINITION_PATH),
      sha256: definitionSha256,
      frozen_before_browser_start: true,
    },
    classification: {
      artifact_role: "isolated_scene_linear_readback",
      fitting_performed_in_browser: false,
      capture_eligible: false,
      approval_granted: false,
      production_integration_allowed: false,
      beauty_capture_performed: false,
      mask_capture_performed: false,
    },
    environment: {
      node: process.version,
      platform: process.platform,
      arch: process.arch,
      playwright_root: playwrightRoot.replaceAll("\\", "/"),
      playwright_version: readJson(
        path.join(playwrightRoot, "package.json"),
      ).version,
    },
    contract: {
      engines: [...ENGINES],
      fresh_runs_per_engine: RUNS_PER_ENGINE,
      fit_engine: "chromium",
      fit_run_index: 0,
      per_browser_refit: false,
      tone_mapping: "NoToneMapping",
      exposure: 1.0,
      render_target: "RGBA32F",
      msaa: false,
      dithering: false,
      post_processing: false,
      shadows: false,
      ao: false,
      extra_gi: false,
      one_family_per_render: true,
      localhost_allow_list_only: true,
    },
    source_integrity: sourceIntegrity,
    server: {
      address: "127.0.0.1",
      port: null,
      allow_list: [],
      errors: [],
    },
    runs: [],
    summary: null,
    not_evaluated: ENGINES.flatMap((engine) =>
      Array.from(
        { length: RUNS_PER_ENGINE },
        (_, index) => `${engine}#${index}`,
      ),
    ),
    errors: [],
  };
  let serverState = null;
  try {
    if (!sourceIntegrity.passed) {
      throw new Error("source or frozen definition integrity failed");
    }
    serverState = await startServer();
    report.server.port = serverState.port;
    report.server.allow_list = serverState.allowList;
    const encodedPath = relativePath(INDEX_PATH)
      .split("/")
      .map(encodeURIComponent)
      .join("/");
    const baseUrl =
      `http://127.0.0.1:${serverState.port}/` + encodedPath;
    for (const engine of ENGINES) {
      for (
        let runIndex = 0;
        runIndex < RUNS_PER_ENGINE;
        runIndex += 1
      ) {
        const result = await runEngineOnce({
          engine,
          browserType: playwright[engine],
          runIndex,
          baseUrl,
          port: serverState.port,
          serverState,
          definitionSha256,
          expectedSampleIds: sourceIntegrity.expected_sample_ids,
          definition,
        });
        report.runs.push(result);
        const key = `${engine}#${runIndex}`;
        report.not_evaluated = report.not_evaluated.filter(
          (item) => item !== key || !result.evaluated,
        );
      }
    }
    report.server.errors = [...serverState.errors];
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
  report.summary = summarize(report);
  const allErrorsZero = Object.values(
    report.summary.error_counts,
  ).every((count) => count === 0);
  report.evaluated =
    report.summary.evaluated_runs ===
      ENGINES.length * RUNS_PER_ENGINE &&
    report.summary.not_evaluated_runs.length === 0;
  report.passed =
    sourceIntegrity.passed &&
    report.evaluated &&
    report.summary.passed_runs ===
      ENGINES.length * RUNS_PER_ENGINE &&
    report.summary.engines_passed === ENGINES.length &&
    allErrorsZero &&
    report.server.errors.length === 0 &&
    report.errors.length === 0;
  report.status = report.passed
    ? "linear_readback_evaluated"
    : "linear_readback_failed_closed";
  report.not_evaluated = report.summary.not_evaluated_runs;
  report.generated_at = new Date().toISOString();
  fs.writeFileSync(
    OUTPUT_PATH,
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
  process.stdout.write(
    `${JSON.stringify(
      {
        status: report.status,
        evaluated: report.evaluated,
        passed: report.passed,
        summary: report.summary,
        output: relativePath(OUTPUT_PATH),
      },
      null,
      2,
    )}\n`,
  );
  if (!report.passed) process.exitCode = 1;
}

main().catch((error) => {
  try {
    fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
    fs.writeFileSync(
      OUTPUT_PATH,
      `${JSON.stringify(
        {
          schema_version: "bf3d.r2t.three_linear_readback.v1",
          requirement_id: REQUIREMENT_ID,
          stage_id: STAGE_ID,
          generated_at: new Date().toISOString(),
          status: "fatal",
          evaluated: false,
          passed: false,
          definition: {
            path: relativePath(DEFINITION_PATH),
            sha256: null,
          },
          runs: [],
          not_evaluated: ["all_browser_runs"],
          errors: [serializeError(error, "unhandled_main")],
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } catch {
    // Preserve the original failure.
  }
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
