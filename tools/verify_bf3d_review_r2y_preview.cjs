#!/usr/bin/env node
"use strict";

/**
 * Chromium-only 1440x900 representative verifier for the R2Y material-signal
 * fixture.
 *
 * It captures exactly the 13 preregistered states, records a state JSON and
 * PNG hash for each, measures the fixed center ROI, checks single-variable
 * mutation boundaries, and classifies BaseColor/Normal/Roughness separately.
 * It never runs the full browser/viewport matrix.
 *
 * The isolated page intentionally loads only the locked V5 material GLB.
 * Consequently the R2X synthetic-black AO WebGL/float/8-bit probe is reported
 * as not_executed and the AO stage gate stays fail-closed.
 */

const childProcess = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");
const readline = require("readline");

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
const STAGE_ID =
  "WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC";
const STAGE = path.join(ROOT, "PT", "高炉3D模型", "work", STAGE_ID);
const CAPTURE_ROOT = path.join(STAGE, "preview", "captures");
const REPORT = path.join(
  STAGE,
  "reports",
  "bf3d_review_r2y_representative_report.json",
);
const BUILD_REPORT = path.join(
  STAGE,
  "reports",
  "r2y_material_signal_web_build_report.json",
);
const INPUT_LOCK = path.join(STAGE, "input_lock.json");
const CONTRACT = path.join(STAGE, "WEB-60_R2Y_阶段预注册合同.md");
const SERVER = path.join(ROOT, "tools", "serve_bf3d_review_r2y.py");
const BUILD = path.join(ROOT, "tools", "build_bf3d_review_r2y_web.py");
const REQUIREMENT_ID =
  "REQ-BF3D-R2Y-MATERIAL-SIGNAL-VISIBILITY-DIAGNOSTIC-20260720";
const EXPECTED_MODEL_SHA256 =
  "652be1b2c9147d5a7392497c7ae4964d19bdd7095b5435b87c105f9eb3fb66bc";
const EXPECTED_MODEL_BYTES = 994_372;
const VIEWPORT = Object.freeze({
  browserType: "chromium",
  width: 1440,
  height: 900,
  deviceScaleFactor: 1,
});
const CANVAS = Object.freeze({ width: 960, height: 540 });
const ROI = Object.freeze({ x: 224, y: 142, width: 512, height: 256 });
const PAGE_TIMEOUT_MS = 90_000;
const CAPTURE_IDS = Object.freeze([
  "00_contract",
  "01_p40_detail_ortho6p2",
  "02_macro_ortho3p1",
  "03_graze30",
  "04_graze75",
  "05_aniso1",
  "06_aniso8",
  "07_env0",
  "08_env1",
  "09_basecolor_raw",
  "10_normal_xy_fixed",
  "11_roughness_fixed",
  "12_contact_sheet",
]);
const BEAUTY_IDS = Object.freeze(CAPTURE_IDS.slice(1, 9));
const CHANNEL_IDS = Object.freeze([
  "09_basecolor_raw",
  "10_normal_xy_fixed",
  "11_roughness_fixed",
]);
const THRESHOLDS = Object.freeze({
  baseColorChannelSpanU8: 8,
  baseColorLumaStdU8: 1,
  normalXyStdNorm: 0.008,
  normalMeanZ: 0.98,
  normalScale: 0.45,
  roughnessSpan: 0.1,
  roughnessStd: 0.02,
  roughnessMinimum: 0.56,
  roughnessMaximum: 0.82,
  grazeBandPassRatio: 1.15,
  grazeChangedRatioOver1U8: 0.02,
  maximumBlackClipRatio: 0.001,
  maximumWhiteClipRatio: 0.001,
  macroMinimumBandPassRatio: 1,
  anisotropyBandPassRatio: 1.03,
  environmentChangedRatioOver1U8: 0.01,
  environmentMeanAbsDiffU8: 0.5,
});

function parseArguments(argv) {
  const options = { headed: false, timeoutMs: PAGE_TIMEOUT_MS };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--headed") {
      options.headed = true;
    } else if (value === "--timeout-ms") {
      const parsed = Number(argv[index + 1]);
      if (!Number.isFinite(parsed) || parsed < 1_000) {
        throw new Error("--timeout-ms must be >= 1000");
      }
      options.timeoutMs = parsed;
      index += 1;
    } else if (value === "--help" || value === "-h") {
      console.log(
        [
          "Usage: node tools/verify_bf3d_review_r2y_preview.cjs [options]",
          "",
          "Options:",
          "  --headed               show the representative browser",
          "  --timeout-ms <number>   page timeout (default 90000)",
          "  --help                  show this help",
          "",
          "Examples:",
          "  node tools/verify_bf3d_review_r2y_preview.cjs",
          "  node tools/verify_bf3d_review_r2y_preview.cjs --headed",
          "  node tools/verify_bf3d_review_r2y_preview.cjs --timeout-ms 120000",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${value}`);
    }
  }
  return options;
}

function rel(filePath) {
  return path.relative(ROOT, filePath).split(path.sep).join("/");
}

function sha256File(filePath) {
  const digest = crypto.createHash("sha256");
  digest.update(fs.readFileSync(filePath));
  return digest.digest("hex");
}

function snapshotFile(filePath) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return { path: rel(filePath), exists: false, bytes: null, sha256: null };
  }
  return {
    path: rel(filePath),
    exists: true,
    bytes: fs.statSync(filePath).size,
    sha256: sha256File(filePath),
  };
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(
    filePath,
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
}

function loadProtectedPaths() {
  const paths = new Set([INPUT_LOCK, CONTRACT]);
  if (fs.existsSync(INPUT_LOCK)) {
    const lock = JSON.parse(fs.readFileSync(INPUT_LOCK, "utf8"));
    for (const groupName of ["diagnostic_inputs", "protected_assets"]) {
      for (const item of lock[groupName] || []) {
        paths.add(path.join(ROOT, ...item.path.split("/")));
      }
    }
  }
  return [...paths].sort();
}

function snapshotFiles(paths) {
  return paths.map(snapshotFile);
}

function runBuildGate() {
  const python = process.env.PYTHON || "python";
  const result = childProcess.spawnSync(python, [BUILD], {
    cwd: ROOT,
    windowsHide: true,
    encoding: "utf8",
    timeout: 120_000,
  });
  return {
    command: `${python} tools/build_bf3d_review_r2y_web.py`,
    exitCode: result.status,
    signal: result.signal,
    stdout: (result.stdout || "").trim(),
    stderr: (result.stderr || "").trim(),
    passed:
      result.status === 0 &&
      fs.existsSync(BUILD_REPORT) &&
      JSON.parse(fs.readFileSync(BUILD_REPORT, "utf8")).passed === true,
    report: fs.existsSync(BUILD_REPORT)
      ? { ...snapshotFile(BUILD_REPORT), value: rel(BUILD_REPORT) }
      : { ...snapshotFile(BUILD_REPORT), value: rel(BUILD_REPORT) },
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
      reject(new Error(`R2Y server ready timeout: ${stderr.join("")}`));
    }, 30_000);
    reader.on("line", (line) => {
      if (settled) return;
      try {
        const value = JSON.parse(line);
        if (value.event !== "bf3d_r2y_review_server_ready") return;
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
          `R2Y server exited before ready: code=${code}, stderr=${stderr.join(
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

function requestStatus(url, method = "GET") {
  return new Promise((resolve, reject) => {
    const request = http.request(url, { method }, (response) => {
      response.resume();
      response.on("end", () => {
        resolve({
          method,
          url,
          status: response.statusCode,
          allow: response.headers.allow || null,
          contentType: response.headers["content-type"] || null,
          csp: response.headers["content-security-policy"] || null,
        });
      });
    });
    request.on("error", reject);
    request.end();
  });
}

function attachDiagnostics(page, origin) {
  const diagnostics = {
    console: [],
    page: [],
    http: [],
    external: [],
    request_failed: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error") {
      diagnostics.console.push({
        type: message.type(),
        text: message.text(),
        location: message.location(),
      });
    }
  });
  page.on("pageerror", (error) => {
    diagnostics.page.push({
      name: error.name,
      message: error.message,
      stack: error.stack || null,
    });
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      diagnostics.http.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText(),
      });
    }
  });
  page.on("request", (request) => {
    const url = request.url();
    if (url.startsWith("data:") || url.startsWith("blob:")) return;
    try {
      if (new URL(url).origin !== origin) {
        diagnostics.external.push({
          url,
          method: request.method(),
          resourceType: request.resourceType(),
        });
      }
    } catch {
      diagnostics.external.push({
        url,
        method: request.method(),
        resourceType: request.resourceType(),
      });
    }
  });
  page.on("requestfailed", (request) => {
    diagnostics.request_failed.push({
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
      failure: request.failure(),
    });
  });
  return diagnostics;
}

function diagnosticCounts(diagnostics) {
  return {
    console: diagnostics.console.length,
    page: diagnostics.page.length,
    http: diagnostics.http.length,
    external: diagnostics.external.length,
    request_failed: diagnostics.request_failed.length,
  };
}

async function analyzeAndStoreFrame(page, captureId, roi) {
  return page.evaluate(
    ({ id, fixedRoi }) => {
      const canvas = document.querySelector("#r2y-output-canvas");
      if (!(canvas instanceof HTMLCanvasElement)) {
        throw new Error("R2Y output canvas missing");
      }
      const context = canvas.getContext("2d", {
        alpha: false,
        willReadFrequently: true,
      });
      const image = context.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = new Uint8ClampedArray(image.data);
      if (!window.__BF3D_R2Y_VERIFY_FRAMES) {
        window.__BF3D_R2Y_VERIFY_FRAMES = new Map();
      }

      const lumaAt = (x, y) => {
        const offset = (y * canvas.width + x) * 4;
        return (
          0.2126 * pixels[offset] +
          0.7152 * pixels[offset + 1] +
          0.0722 * pixels[offset + 2]
        );
      };
      let sum = 0;
      let sumSquared = 0;
      let minimum = Number.POSITIVE_INFINITY;
      let maximum = Number.NEGATIVE_INFINITY;
      let black = 0;
      let white = 0;
      let pixelCount = 0;
      for (
        let y = fixedRoi.y;
        y < fixedRoi.y + fixedRoi.height;
        y += 1
      ) {
        for (
          let x = fixedRoi.x;
          x < fixedRoi.x + fixedRoi.width;
          x += 1
        ) {
          const value = lumaAt(x, y);
          sum += value;
          sumSquared += value * value;
          minimum = Math.min(minimum, value);
          maximum = Math.max(maximum, value);
          if (value <= 1) black += 1;
          if (value >= 254) white += 1;
          pixelCount += 1;
        }
      }
      let bandSquared = 0;
      let bandCount = 0;
      for (
        let y = fixedRoi.y + 1;
        y < fixedRoi.y + fixedRoi.height - 1;
        y += 1
      ) {
        for (
          let x = fixedRoi.x + 1;
          x < fixedRoi.x + fixedRoi.width - 1;
          x += 1
        ) {
          const center = lumaAt(x, y);
          const neighbourMean =
            (lumaAt(x - 1, y) +
              lumaAt(x + 1, y) +
              lumaAt(x, y - 1) +
              lumaAt(x, y + 1)) /
            4;
          const residual = center - neighbourMean;
          bandSquared += residual * residual;
          bandCount += 1;
        }
      }
      const average = pixelCount ? sum / pixelCount : 0;
      const variance = pixelCount
        ? Math.max(0, sumSquared / pixelCount - average * average)
        : 0;
      const stats = {
        roi: { ...fixedRoi },
        pixelCount,
        lumaMinU8: minimum,
        lumaMaxU8: maximum,
        lumaMeanU8: average,
        lumaStdU8: Math.sqrt(variance),
        blackClipPixels: black,
        blackClipRatio: pixelCount ? black / pixelCount : 1,
        whiteClipPixels: white,
        whiteClipRatio: pixelCount ? white / pixelCount : 1,
        bandPassRmsU8: bandCount
          ? Math.sqrt(bandSquared / bandCount)
          : 0,
        bandPassSampleCount: bandCount,
      };
      window.__BF3D_R2Y_VERIFY_FRAMES.set(id, {
        width: canvas.width,
        height: canvas.height,
        pixels,
        roi: { ...fixedRoi },
        stats,
      });
      return {
        canvas: [canvas.width, canvas.height],
        stats,
      };
    },
    { id: captureId, fixedRoi: roi },
  );
}

async function compareFrames(page, captureA, captureB) {
  return page.evaluate(
    ({ a, b }) => {
      const frames = window.__BF3D_R2Y_VERIFY_FRAMES;
      const first = frames?.get(a);
      const second = frames?.get(b);
      if (!first || !second) {
        throw new Error(`missing stored pair ${a}/${b}`);
      }
      if (
        first.width !== second.width ||
        first.height !== second.height
      ) {
        throw new Error(`pair dimensions differ ${a}/${b}`);
      }
      const roi = first.roi;
      let changedPixelsOver1U8 = 0;
      let changedPixelsAny = 0;
      let absoluteRgbSum = 0;
      let absoluteRgbChangedSum = 0;
      let changedChannelCount = 0;
      let maximumChannelDifferenceU8 = 0;
      let squaredRgbSum = 0;
      let pixelCount = 0;
      for (let y = roi.y; y < roi.y + roi.height; y += 1) {
        for (let x = roi.x; x < roi.x + roi.width; x += 1) {
          const offset = (y * first.width + x) * 4;
          let maximum = 0;
          let pixelAbsolute = 0;
          for (let channel = 0; channel < 3; channel += 1) {
            const difference =
              second.pixels[offset + channel] -
              first.pixels[offset + channel];
            const absolute = Math.abs(difference);
            maximum = Math.max(maximum, absolute);
            maximumChannelDifferenceU8 = Math.max(
              maximumChannelDifferenceU8,
              absolute,
            );
            pixelAbsolute += absolute;
            absoluteRgbSum += absolute;
            squaredRgbSum += difference * difference;
          }
          if (maximum > 0) {
            changedPixelsAny += 1;
            absoluteRgbChangedSum += pixelAbsolute;
            changedChannelCount += 3;
          }
          if (maximum > 1) changedPixelsOver1U8 += 1;
          pixelCount += 1;
        }
      }
      return {
        captureA: a,
        captureB: b,
        roi: { ...roi },
        pixelCount,
        changedPixelsAny,
        changedRatioAny: pixelCount
          ? changedPixelsAny / pixelCount
          : 0,
        changedPixelsOver1U8,
        changedRatioOver1U8: pixelCount
          ? changedPixelsOver1U8 / pixelCount
          : 0,
        meanAbsDiffRgbU8: pixelCount
          ? absoluteRgbSum / (pixelCount * 3)
          : 0,
        meanAbsDiffChangedRgbU8: changedChannelCount
          ? absoluteRgbChangedSum / changedChannelCount
          : 0,
        rmsDiffRgbU8: pixelCount
          ? Math.sqrt(squaredRgbSum / (pixelCount * 3))
          : 0,
        maximumChannelDifferenceU8,
      };
    },
    { a: captureA, b: captureB },
  );
}

function gate(gates, name, passed, actual, threshold) {
  gates.push({
    name,
    passed: Boolean(passed),
    actual,
    threshold,
  });
}

function equality(a, b, epsilon = 1e-9) {
  return (
    Number.isFinite(Number(a)) &&
    Number.isFinite(Number(b)) &&
    Math.abs(Number(a) - Number(b)) <= epsilon
  );
}

function captureInvariantFailures(states) {
  const failures = [];
  for (const id of CAPTURE_IDS) {
    const state = states.get(id);
    if (!state) {
      failures.push({ id, reason: "state_missing" });
      continue;
    }
    const bad = [];
    if (state.captureId !== id) bad.push("capture_id");
    if (!state.captureReady || state.loadState !== "ready") {
      bad.push("capture_not_ready");
    }
    if (
      state.model?.actualSha256 !== EXPECTED_MODEL_SHA256 ||
      state.model?.expectedSha256 !== EXPECTED_MODEL_SHA256 ||
      state.model?.expectedBytes !== EXPECTED_MODEL_BYTES ||
      state.model?.shaVerified !== true
    ) {
      bad.push("model_lock");
    }
    if (
      state.objects?.shellCount !== 5 ||
      state.objects?.materialCount !== 2 ||
      state.objects?.forbiddenObjectCount !== 0 ||
      state.objects?.yellowOutlineCount !== 0 ||
      state.objects?.sensorCount !== 0 ||
      state.objects?.leaderCount !== 0 ||
      state.objects?.processParticleCount !== 0
    ) {
      bad.push("object_contract");
    }
    if (
      state.pbr?.pbrMutationCount !== 0 ||
      state.pbr?.mutationAudit?.mutationCount !== 0 ||
      state.pbr?.aoEnabled !== false ||
      state.pbr?.aoMapCount !== 0
    ) {
      bad.push("pbr_or_ao_contract");
    }
    if (
      state.mutationAudit?.passed !== true ||
      state.mutationAudit?.pbrMutationCount !== 0 ||
      (state.mutationAudit?.unexpectedCategories || []).length !== 0
    ) {
      bad.push("single_variable_mutation");
    }
    if (
      String(state.renderer?.revision) !== "160" ||
      state.renderer?.outputColorSpace !== "srgb" ||
      state.renderer?.toneMapping !== 4 ||
      !equality(state.renderer?.exposure, 1) ||
      JSON.stringify(state.renderer?.canvas) !== "[960,540]" ||
      !equality(state.renderer?.pixelRatio, 1)
    ) {
      bad.push("renderer_contract");
    }
    if (
      state.camera?.projection !== "orthographic" ||
      state.camera?.positionErrorMeters > 1e-6 ||
      state.camera?.landmarkTargetErrorMeters > 1e-6 ||
      state.camera?.quaternionAngularErrorRadians > 1e-6 ||
      state.camera?.roiMinimumSatisfied !== true ||
      state.camera?.roiContainsOuterOutline !== false ||
      state.camera?.roiContainsFiveZoneBoundary !== false
    ) {
      bad.push("camera_contract");
    }
    if (
      state.lighting?.directionalCount !== 3 ||
      state.lighting?.ambientLightCount !== 0 ||
      state.lighting?.effectiveLtcInitCalls !== 1
    ) {
      bad.push("lighting_contract");
    }
    if (
      state.evidence !== "E/diagnostic" ||
      state.beautyApproved !== false ||
      state.productionApproved !== false ||
      state.fullMatrixAllowed !== false
    ) {
      bad.push("approval_boundary");
    }
    if (CHANNEL_IDS.includes(id)) {
      if (
        state.diagnostic?.watermark !==
        "CHANNEL DIAGNOSTIC / NOT PBR"
      ) {
        bad.push("channel_watermark");
      }
    }
    if (bad.length) failures.push({ id, reasons: bad });
  }
  return failures;
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const protectedPaths = loadProtectedPaths();
  const protectedBefore = snapshotFiles(protectedPaths);
  const buildGate = runBuildGate();
  const generatedAt = new Date().toISOString();
  let server;
  let browser;
  let context;
  let page;
  let diagnostics = {
    console: [],
    page: [],
    http: [],
    external: [],
    request_failed: [],
  };
  const captures = [];
  const states = new Map();
  const pixelEvidence = new Map();
  const gates = [];
  const pairEvidence = {};
  let serverContract = null;
  let httpContract = null;
  let browserAudit = null;
  let layoutAudit = null;
  let fatalError = null;

  try {
    server = await startReviewServer();
    serverContract = server.ready;
    const pageUrl = server.ready.url;
    const origin = new URL(pageUrl).origin;
    const unknownUrl = `${origin}/not-on-r2y-allow-list`;
    httpContract = {
      pageHead: await requestStatus(pageUrl, "HEAD"),
      unknownGet: await requestStatus(unknownUrl, "GET"),
      pagePost: await requestStatus(pageUrl, "POST"),
    };

    browser = await playwright.chromium.launch({ headless: !options.headed });
    context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
      colorScheme: "dark",
      locale: "zh-CN",
    });
    page = await context.newPage();
    page.setDefaultTimeout(options.timeoutMs);
    diagnostics = attachDiagnostics(page, origin);
    await page.goto(pageUrl, {
      waitUntil: "networkidle",
      timeout: options.timeoutMs,
    });
    await page.waitForFunction(
      () =>
        window.BF3D_R2Y_FIXTURE &&
        window.BF3D_R2Y_FIXTURE.getState().loadState === "ready",
      null,
      { timeout: options.timeoutMs },
    );
    const userAgent = await page.evaluate(() => navigator.userAgent);
    browserAudit = {
      type: "Chromium",
      version: browser.version(),
      userAgent,
      viewportCss: [VIEWPORT.width, VIEWPORT.height],
      deviceScaleFactor: VIEWPORT.deviceScaleFactor,
      fullMatrixExecuted: false,
    };
    layoutAudit = await page.evaluate(() => {
      const canvas = document.querySelector("#r2y-output-canvas");
      const frame = document.querySelector("#r2y-output-frame");
      const canvasRect = canvas.getBoundingClientRect();
      const frameRect = frame.getBoundingClientRect();
      const clickable = [...document.querySelectorAll("[data-r2y-capture]")]
        .map((button) => ({
          id: button.dataset.r2yCapture,
          disabled: button.disabled,
          width: button.getBoundingClientRect().width,
          height: button.getBoundingClientRect().height,
        }));
      return {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        documentScrollWidth: document.documentElement.scrollWidth,
        documentScrollHeight: document.documentElement.scrollHeight,
        bodyScrollWidth: document.body.scrollWidth,
        horizontalOverflow:
          document.documentElement.scrollWidth > window.innerWidth,
        canvasRect: {
          x: canvasRect.x,
          y: canvasRect.y,
          width: canvasRect.width,
          height: canvasRect.height,
        },
        canvasBackingStore: [canvas.width, canvas.height],
        frameRect: {
          x: frameRect.x,
          y: frameRect.y,
          width: frameRect.width,
          height: frameRect.height,
        },
        captureButtons: clickable,
      };
    });

    fs.mkdirSync(CAPTURE_ROOT, { recursive: true });
    for (const id of CAPTURE_IDS) {
      const state = await page.evaluate(
        async (captureId) =>
          window.BF3D_R2Y_FIXTURE.setCaptureState(captureId),
        id,
      );
      await page.waitForFunction(
        (captureId) =>
          window.BF3D_R2Y_FIXTURE.getState().captureId === captureId,
        id,
      );
      const runtimeState = await page.evaluate(() =>
        window.BF3D_R2Y_FIXTURE.getAuditSnapshot(),
      );
      states.set(id, runtimeState);
      const pixel = await analyzeAndStoreFrame(page, id, ROI);
      pixelEvidence.set(id, pixel);
      const pngPath = path.join(CAPTURE_ROOT, `${id}.png`);
      await page.locator("#r2y-output-canvas").screenshot({
        path: pngPath,
        type: "png",
        animations: "disabled",
      });
      const pngSnapshot = snapshotFile(pngPath);
      const statePath = path.join(CAPTURE_ROOT, `${id}.state.json`);
      const stateDocument = {
        ...runtimeState,
        verification: {
          schemaVersion: "bf3d.r2y.capture_state_evidence.v1",
          generatedAt: new Date().toISOString(),
          browser: browserAudit,
          viewportCss: [VIEWPORT.width, VIEWPORT.height],
          outputCanvasCss: [CANVAS.width, CANVAS.height],
          outputCanvasBackingStore: pixel.canvas,
          screenshot: pngSnapshot,
          roiStatistics: pixel.stats,
          diagnosticErrorCountsAtCapture: diagnosticCounts(diagnostics),
          modelSha256: runtimeState.model?.actualSha256 || null,
          fullMatrixExecuted: false,
        },
      };
      writeJson(statePath, stateDocument);
      const stateSnapshot = snapshotFile(statePath);
      captures.push({
        id,
        kind: runtimeState.captureKind,
        label: runtimeState.captureLabel,
        png: pngSnapshot,
        state: stateSnapshot,
        roiStatistics: pixel.stats,
        modelSha256: runtimeState.model?.actualSha256 || null,
        gpu: runtimeState.renderer?.gpu || null,
        camera: runtimeState.camera,
        lighting: runtimeState.lighting,
        environment: runtimeState.environment,
        sampler: runtimeState.sampler,
        mutationAudit: runtimeState.mutationAudit,
      });
    }

    for (const [name, a, b] of [
      ["density", "01_p40_detail_ortho6p2", "02_macro_ortho3p1"],
      ["grazing", "03_graze30", "04_graze75"],
      ["anisotropy", "05_aniso1", "06_aniso8"],
      ["environment", "07_env0", "08_env1"],
    ]) {
      pairEvidence[name] = await compareFrames(page, a, b);
      pairEvidence[name].bandPassRmsA =
        pixelEvidence.get(a).stats.bandPassRmsU8;
      pairEvidence[name].bandPassRmsB =
        pixelEvidence.get(b).stats.bandPassRmsU8;
      pairEvidence[name].bandPassRatio =
        pairEvidence[name].bandPassRmsA > 0
          ? pairEvidence[name].bandPassRmsB /
            pairEvidence[name].bandPassRmsA
          : null;
    }
  } catch (error) {
    fatalError = {
      name: error.name || "Error",
      message: error.message || String(error),
      stack: error.stack || null,
    };
  } finally {
    if (context) await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
    await stopReviewServer(server);
  }

  gate(
    gates,
    "build_gate",
    buildGate.passed,
    { exitCode: buildGate.exitCode, report: buildGate.report },
    { exitCode: 0, reportPassed: true },
  );
  gate(
    gates,
    "no_fatal_runtime_error",
    fatalError === null,
    fatalError,
    null,
  );
  gate(
    gates,
    "server_strict_allow_list",
    serverContract?.r2x_candidate_exposed === false &&
      serverContract?.formal_glb_exposed === false &&
      serverContract?.write_methods_supported === false &&
      httpContract?.pageHead?.status === 200 &&
      httpContract?.unknownGet?.status === 404 &&
      httpContract?.pagePost?.status === 405,
    { serverContract, httpContract },
    {
      r2xCandidateExposed: false,
      formalGlbExposed: false,
      writeMethodsSupported: false,
      pageHead: 200,
      unknownGet: 404,
      pagePost: 405,
    },
  );
  gate(
    gates,
    "representative_viewport_only",
    browserAudit?.viewportCss?.[0] === 1440 &&
      browserAudit?.viewportCss?.[1] === 900 &&
      browserAudit?.fullMatrixExecuted === false,
    browserAudit,
    {
      browser: "Chromium",
      viewportCss: [1440, 900],
      fullMatrixExecuted: false,
    },
  );
  gate(
    gates,
    "layout_no_horizontal_overflow",
    layoutAudit?.horizontalOverflow === false,
    layoutAudit?.horizontalOverflow,
    false,
  );
  gate(
    gates,
    "fixed_output_canvas_960x540",
    layoutAudit?.canvasRect?.width === CANVAS.width &&
      layoutAudit?.canvasRect?.height === CANVAS.height &&
      JSON.stringify(layoutAudit?.canvasBackingStore) === "[960,540]" &&
      layoutAudit?.frameRect?.width === CANVAS.width &&
      layoutAudit?.frameRect?.height === CANVAS.height,
    layoutAudit,
    {
      canvasCss: [CANVAS.width, CANVAS.height],
      canvasBackingStore: [CANVAS.width, CANVAS.height],
      frameCss: [CANVAS.width, CANVAS.height],
    },
  );
  gate(
    gates,
    "all_13_capture_buttons_reachable",
    layoutAudit?.captureButtons?.length === 13 &&
      layoutAudit.captureButtons.every(
        (item) =>
          !item.disabled && item.width > 0 && item.height > 0,
      ),
    layoutAudit?.captureButtons || null,
    { count: 13, allEnabledAndSized: true },
  );
  gate(
    gates,
    "all_13_capture_artifacts",
    captures.length === 13 &&
      captures.every(
        (item) =>
          item.png.exists &&
          item.png.bytes > 0 &&
          item.png.sha256 &&
          item.state.exists &&
          item.state.bytes > 0 &&
          item.state.sha256,
      ),
    captures.map((item) => ({
      id: item.id,
      png: item.png,
      state: item.state,
    })),
    { count: 13, pngAndStateHashPerCapture: true },
  );
  const finalErrorCounts = diagnosticCounts(diagnostics);
  gate(
    gates,
    "five_error_classes_zero",
    Object.values(finalErrorCounts).every((value) => value === 0),
    finalErrorCounts,
    {
      console: 0,
      page: 0,
      http: 0,
      external: 0,
      request_failed: 0,
    },
  );
  const invariantFailures = captureInvariantFailures(states);
  gate(
    gates,
    "runtime_invariants_all_13_states",
    invariantFailures.length === 0,
    invariantFailures,
    [],
  );

  const beautyClipping = BEAUTY_IDS.map((id) => ({
    id,
    blackClipRatio:
      pixelEvidence.get(id)?.stats?.blackClipRatio ?? null,
    whiteClipRatio:
      pixelEvidence.get(id)?.stats?.whiteClipRatio ?? null,
  }));
  gate(
    gates,
    "beauty_roi_black_clip_below_0p1pct",
    beautyClipping.length === 8 &&
      beautyClipping.every(
        (item) =>
          item.blackClipRatio !== null &&
          item.blackClipRatio <
            THRESHOLDS.maximumBlackClipRatio,
      ),
    beautyClipping,
    `<${THRESHOLDS.maximumBlackClipRatio}`,
  );
  gate(
    gates,
    "beauty_roi_white_clip_below_0p1pct",
    beautyClipping.length === 8 &&
      beautyClipping.every(
        (item) =>
          item.whiteClipRatio !== null &&
          item.whiteClipRatio <
            THRESHOLDS.maximumWhiteClipRatio,
      ),
    beautyClipping,
    `<${THRESHOLDS.maximumWhiteClipRatio}`,
  );

  const channelStatistics =
    states.get("09_basecolor_raw")?.pbr?.channels || null;
  const baseColor = channelStatistics?.baseColor || null;
  const normal = channelStatistics?.normal || null;
  const roughness = channelStatistics?.roughness || null;
  const baseSpanPassed =
    baseColor?.channels?.length === 3 &&
    baseColor.channels.every(
      (item) => item.spanU8 >= THRESHOLDS.baseColorChannelSpanU8,
    );
  const baseLumaPassed =
    baseColor?.lumaStdU8 >= THRESHOLDS.baseColorLumaStdU8;
  const normalXyPassed =
    normal?.xyStdNorm >= THRESHOLDS.normalXyStdNorm;
  const normalZPassed = normal?.meanZ >= THRESHOLDS.normalMeanZ;
  const normalScalePassed = equality(
    normal?.normalScale,
    THRESHOLDS.normalScale,
    1e-6,
  );
  const roughSpanPassed =
    roughness?.span >= THRESHOLDS.roughnessSpan;
  const roughStdPassed =
    roughness?.std >= THRESHOLDS.roughnessStd;
  const roughRangePassed =
    roughness?.min >= THRESHOLDS.roughnessMinimum &&
    roughness?.max <= THRESHOLDS.roughnessMaximum;
  gate(
    gates,
    "basecolor_each_channel_span",
    baseSpanPassed,
    baseColor?.channels || null,
    `each >= ${THRESHOLDS.baseColorChannelSpanU8} u8`,
  );
  gate(
    gates,
    "basecolor_luma_std",
    baseLumaPassed,
    baseColor?.lumaStdU8 ?? null,
    `>= ${THRESHOLDS.baseColorLumaStdU8} u8`,
  );
  gate(
    gates,
    "normal_xy_std_norm",
    normalXyPassed,
    normal?.xyStdNorm ?? null,
    `>= ${THRESHOLDS.normalXyStdNorm}`,
  );
  gate(
    gates,
    "normal_mean_z",
    normalZPassed,
    normal?.meanZ ?? null,
    `>= ${THRESHOLDS.normalMeanZ}`,
  );
  gate(
    gates,
    "normal_scale_unchanged",
    normalScalePassed,
    normal?.normalScale ?? null,
    THRESHOLDS.normalScale,
  );
  gate(
    gates,
    "roughness_span",
    roughSpanPassed,
    roughness?.span ?? null,
    `>= ${THRESHOLDS.roughnessSpan}`,
  );
  gate(
    gates,
    "roughness_std",
    roughStdPassed,
    roughness?.std ?? null,
    `>= ${THRESHOLDS.roughnessStd}`,
  );
  gate(
    gates,
    "roughness_full_range",
    roughRangePassed,
    roughness
      ? { min: roughness.min, max: roughness.max }
      : null,
    [
      THRESHOLDS.roughnessMinimum,
      THRESHOLDS.roughnessMaximum,
    ],
  );

  const grazing = pairEvidence.grazing;
  const density = pairEvidence.density;
  const anisotropy = pairEvidence.anisotropy;
  const environment = pairEvidence.environment;
  const grazingRmsPassed =
    grazing?.bandPassRatio >= THRESHOLDS.grazeBandPassRatio;
  const grazingChangedPassed =
    grazing?.changedRatioOver1U8 >=
    THRESHOLDS.grazeChangedRatioOver1U8;
  const densityPassed =
    density?.bandPassRatio >= THRESHOLDS.macroMinimumBandPassRatio;
  const anisotropyPassed =
    anisotropy?.bandPassRatio >=
    THRESHOLDS.anisotropyBandPassRatio;
  const environmentPassed =
    environment?.changedRatioOver1U8 >=
      THRESHOLDS.environmentChangedRatioOver1U8 &&
    environment?.meanAbsDiffRgbU8 >=
      THRESHOLDS.environmentMeanAbsDiffU8;
  gate(
    gates,
    "grazing_band_pass_ratio_75_over_30",
    grazingRmsPassed,
    grazing || null,
    `>= ${THRESHOLDS.grazeBandPassRatio}`,
  );
  gate(
    gates,
    "grazing_changed_pixels_over_1u8",
    grazingChangedPassed,
    grazing || null,
    `>= ${THRESHOLDS.grazeChangedRatioOver1U8}`,
  );
  gate(
    gates,
    "macro_band_pass_not_lower_than_detail",
    densityPassed,
    density || null,
    `>= ${THRESHOLDS.macroMinimumBandPassRatio}`,
  );
  gate(
    gates,
    "anisotropy_contribution",
    anisotropyPassed,
    anisotropy || null,
    `>= ${THRESHOLDS.anisotropyBandPassRatio}`,
  );
  gate(
    gates,
    "environment_consumption",
    environmentPassed,
    environment || null,
    {
      changedRatioOver1U8: `>= ${THRESHOLDS.environmentChangedRatioOver1U8}`,
      meanAbsDiffRgbU8: `>= ${THRESHOLDS.environmentMeanAbsDiffU8}`,
    },
  );

  const invariantGatePassed =
    invariantFailures.length === 0 &&
    Object.values(finalErrorCounts).every((value) => value === 0);
  const channelInterpretationBoundary =
    "Texture data, CPU sampling and a Three.js material binding do not " +
    "independently prove shader consumption or final per-channel visual " +
    "visibility. No per-channel texture off/on shader differential was " +
    "executed in R2Y, so consumed remains null and visible fails closed.";
  const channelClassifications = {
    baseColor: {
      data_present: baseColor?.dataPresent === true,
      sampled: baseColor?.sampled === true,
      runtime_binding_present:
        baseColor?.runtimeBindingPresent === true,
      consumed: null,
      visible: false,
      consumption_classification: "not_independently_probed",
      visibility_classification:
        "fail_closed_not_independently_proven",
      raw_signal_thresholds_passed:
        baseSpanPassed && baseLumaPassed,
      evidence: {
        channels: baseColor?.channels || null,
        lumaStdU8: baseColor?.lumaStdU8 ?? null,
      },
      interpretation_boundary: channelInterpretationBoundary,
    },
    normal: {
      data_present: normal?.dataPresent === true,
      sampled: normal?.sampled === true,
      runtime_binding_present:
        normal?.runtimeBindingPresent === true,
      consumed: null,
      visible: false,
      consumption_classification: "not_independently_probed",
      visibility_classification:
        "fail_closed_not_independently_proven",
      raw_signal_thresholds_passed:
        normalXyPassed && normalZPassed && normalScalePassed,
      shared_grazing_response_passed:
        grazingRmsPassed && grazingChangedPassed,
      evidence: normal,
      interpretation_boundary: channelInterpretationBoundary,
    },
    roughness: {
      data_present: roughness?.dataPresent === true,
      sampled: roughness?.sampled === true,
      runtime_binding_present:
        roughness?.runtimeBindingPresent === true,
      consumed: null,
      visible: false,
      consumption_classification: "not_independently_probed",
      visibility_classification:
        "fail_closed_not_independently_proven",
      raw_signal_thresholds_passed:
        roughSpanPassed && roughStdPassed && roughRangePassed,
      shared_grazing_response_passed:
        grazingRmsPassed && grazingChangedPassed,
      evidence: roughness,
      interpretation_boundary:
        channelInterpretationBoundary +
        " " +
        "Anisotropy/environment only prove sampler or IBL consumption; " +
        "they do not independently prove roughness is visually obvious.",
    },
  };

  const aoWebglClassification = {
    execution_status: "not_executed",
    r2x_candidate_loaded: false,
    isolated_clone_canvas_created: false,
    synthetic_black_ao_webgl_liveness: {
      status: "not_executed",
      changed_pixels: null,
      threshold: ">=64",
    },
    float_linear_off_on: {
      status: "not_executed",
      maximum_absolute_difference: null,
      threshold: ">1e-5",
    },
    final_8bit_off_on: {
      status: "not_executed",
      changed_pixels: null,
      mean_absolute_rgb_difference_u8: null,
      thresholds: {
        changed_pixels: ">=64",
        mean_absolute_rgb_difference_u8: ">=0.25",
      },
    },
    shader_liveness_inferred: false,
    classification: "not_executed_fail_closed",
    gate_passed: false,
    reason:
      "The R2Y PBR fixture and strict server load only the locked V5 " +
      "material GLB. No independent R2X clone/canvas was executed, so " +
      "shader texture-consumption liveness and float-vs-8bit behavior " +
      "cannot be inferred from CPU or prior screenshots.",
  };

  const protectedAfter = snapshotFiles(protectedPaths);
  const protectedUnchanged =
    JSON.stringify(protectedBefore) === JSON.stringify(protectedAfter);
  gate(
    gates,
    "protected_inputs_unchanged",
    protectedUnchanged,
    protectedAfter,
    protectedBefore,
  );
  const requiredPbrGates = gates.filter(
    (item) =>
      ![
        "server_strict_allow_list",
        "representative_viewport_only",
      ].includes(item.name),
  );
  const pbrFixturePassed =
    requiredPbrGates.every((item) => item.passed) &&
    Object.values(channelClassifications).every(
      (item) =>
        item.data_present &&
        item.sampled &&
        item.runtime_binding_present &&
        item.consumed === true &&
        item.visible === true,
    );

  const report = {
    schema_version: "bf3d.r2y.representative_report.v2",
    requirement_id: REQUIREMENT_ID,
    stage_id: STAGE_ID,
    generated_at: generatedAt,
    evidence_class: "E/diagnostic",
    scope: {
      browser_engine: "Chromium",
      viewport_css: [1440, 900],
      output_canvas_css: [960, 540],
      output_canvas_dpr: 1,
      representative_only: true,
      full_matrix_executed: false,
      capture_count: CAPTURE_IDS.length,
      capture_ids: CAPTURE_IDS,
      beauty_approved: false,
      golden_approved: false,
      production_approved: false,
    },
    build_gate: buildGate,
    server_contract: serverContract,
    http_contract: httpContract,
    browser: browserAudit,
    layout: layoutAudit,
    errors: {
      classes: [
        "console",
        "page",
        "http",
        "external",
        "request_failed",
      ],
      counts: finalErrorCounts,
      details: diagnostics,
      passed: Object.values(finalErrorCounts).every(
        (value) => value === 0,
      ),
    },
    thresholds: THRESHOLDS,
    roi_definition: ROI,
    captures,
    pair_evidence: pairEvidence,
    channel_statistics: channelStatistics,
    pbr_channel_classifications: channelClassifications,
    channel_classification_boundary: channelInterpretationBoundary,
    pbr_fixture: {
      invariant_gate_passed: invariantGatePassed,
      representative_machine_and_visual_gate_passed: pbrFixturePassed,
      conclusion: pbrFixturePassed
        ? "pbr_signal_visible_under_controlled_fixture"
        : "pbr_signal_visibility_fail_closed",
    },
    ao_webgl_classification: aoWebglClassification,
    protected_inputs_before: protectedBefore,
    protected_inputs_after: protectedAfter,
    protected_inputs_unchanged: protectedUnchanged,
    gates,
    gate_summary: {
      total: gates.length,
      passed: gates.filter((item) => item.passed).length,
      failed: gates.filter((item) => !item.passed).length,
    },
    pbr_fixture_passed: pbrFixturePassed,
    ao_gate_passed: false,
    stage_complete: false,
    passed: false,
    conclusion:
      "r2y_stage_fail_closed_ao_webgl_liveness_not_executed",
    fatal_error: fatalError,
    stop_lines: {
      asset_mutation_allowed: false,
      full_matrix_allowed: false,
      full_matrix_executed: false,
      ao_rebake_allowed: false,
      ao_2k_approved: false,
      p50_approved: false,
      p60_approved: false,
      production_integration_allowed: false,
      next_release_stage_allowed: false,
    },
  };
  writeJson(REPORT, report);
  console.log(
    JSON.stringify({
      ok: false,
      report: rel(REPORT),
      reportSha256: sha256File(REPORT),
      pbrFixturePassed,
      pbrConclusion: report.pbr_fixture.conclusion,
      aoWebglLiveness: "not_executed",
      aoClassification: "not_executed_fail_closed",
      stageComplete: false,
      captures: captures.length,
      errors: finalErrorCounts,
      failedGates: gates
        .filter((item) => !item.passed)
        .map((item) => item.name),
      fullMatrixExecuted: false,
    }),
  );
  process.exitCode = 1;
}

main().catch((error) => {
  const fatal = {
    schema_version: "bf3d.r2y.representative_report.v2",
    requirement_id: REQUIREMENT_ID,
    stage_id: STAGE_ID,
    generated_at: new Date().toISOString(),
    evidence_class: "E/diagnostic",
    pbr_fixture_passed: false,
    ao_gate_passed: false,
    stage_complete: false,
    passed: false,
    conclusion: "r2y_representative_verifier_fatal_fail_closed",
    fatal_error: {
      name: error.name || "Error",
      message: error.message || String(error),
      stack: error.stack || null,
    },
    scope: {
      browser_engine: "Chromium",
      viewport_css: [1440, 900],
      full_matrix_executed: false,
    },
    ao_webgl_classification: {
      execution_status: "not_executed",
      classification: "not_executed_fail_closed",
      shader_liveness_inferred: false,
      gate_passed: false,
    },
  };
  try {
    writeJson(REPORT, fatal);
  } catch {
    // Preserve the original fatal error.
  }
  console.error(JSON.stringify(fatal));
  process.exitCode = 2;
});
