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
const OUTPUT_ROOT = path.join(
  ROOT,
  "logs",
  "bf3d_structural_review_v3_20260719",
);
const REVIEW_FILE = "gl02_blast_furnace_review.v3.glb";
const REVIEW_ASSET_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  REVIEW_FILE,
);
const MATERIAL_REVIEW_ASSET_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  "gl02_blast_furnace_material_review.v3.glb",
);
const STRUCTURAL_REVIEW_ASSET_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  "gl02_blast_furnace_structural_review.v3.glb",
);
const MAX_WEB_GLB_BYTES = 25_000_000;
const REVIEW_ASSET_URL = `models/${REVIEW_FILE}`;
const OPERATIONAL_ASSET_URL =
  "models/gl02_blast_furnace_structural_review.v1.glb";
const LOOKDEV_PRESET_URL = "web/presets/lookdev_camera_v1.json";
const LOOKDEV_PRESET_SOURCE_PATH = path.join(
  ROOT,
  "PT",
  "高炉3D模型",
  "web",
  "presets",
  "lookdev_camera_v1.json",
);
const LOOKDEV_PRESET_RUNTIME_PATH = path.join(
  FRONTEND_ROOT,
  "web",
  "presets",
  "lookdev_camera_v1.json",
);
const LOOKDEV_PRESET_SHA256 =
  "78131335b87eb7b00b5f803b9b6936eecf4a74aa06b908b76c9f681260a7f9c6";
const DETAIL_NORMAL_FILE =
  "INT30_R2H_DetailNormal_1K_OpenGL_plusY_low_strength_0_25.png";
const DETAIL_NORMAL_PATH = path.join(
  FRONTEND_ROOT,
  "models",
  "textures",
  DETAIL_NORMAL_FILE,
);
const RUN_MATRIX = process.argv.includes("--matrix");
const RUN_EDGE_SMOKE = process.argv.includes("--edge-smoke");
const CHROMIUM_VIEWPORTS = [
  [1280, 720],
  [1366, 768],
  [1440, 900],
  [1546, 864],
  [1920, 1080],
  [1024, 768],
  [768, 1024],
  [390, 844],
  [375, 667],
];
const REPRESENTATIVE_VIEWPORTS = [
  [1920, 1080],
  [1366, 768],
  [768, 1024],
  [390, 844],
];
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".bin": "application/octet-stream",
  ".hdr": "application/octet-stream",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function assert(condition, message, detail = null) {
  if (!condition) {
    throw new Error(`${message}: ${JSON.stringify(detail)}`);
  }
}

function sha256(filePath) {
  return crypto
    .createHash("sha256")
    .update(fs.readFileSync(filePath))
    .digest("hex");
}

function startServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((request, response) => {
      let pathname;
      try {
        pathname = decodeURIComponent(
          new URL(request.url, "http://127.0.0.1").pathname,
        );
      } catch {
        response.writeHead(400).end("bad request");
        return;
      }
      if (pathname === "/") pathname = "/frontend_dashboard_v3.server.html";
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

function isKnownOffline(value) {
  const text = String(value || "");
  return (
    text.includes("127.0.0.1:8767") ||
    text.includes("ws://127.0.0.1:8767") ||
    text.includes("/api/") ||
    text.includes("/favicon.ico") ||
    text.includes("[BABEL] Note:")
  );
}

function isReviewResponse(response) {
  try {
    return new URL(response.url()).pathname.endsWith(`/${REVIEW_FILE}`);
  } catch {
    return false;
  }
}

function attachDiagnostics(page) {
  const diagnostics = {
    pageErrors: [],
    consoleErrors: [],
    httpErrors: [],
    reviewResponses: [],
    reviewRequestFailures: [],
  };
  page.on("pageerror", (error) =>
    diagnostics.pageErrors.push(String(error)),
  );
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const location = message.location()?.url || "";
    if (!isKnownOffline(message.text()) && !isKnownOffline(location)) {
      diagnostics.consoleErrors.push({
        text: message.text(),
        location,
      });
    }
  });
  page.on("response", (response) => {
    if (isReviewResponse(response)) {
      diagnostics.reviewResponses.push({
        status: response.status(),
        url: response.url(),
      });
    }
    if (
      response.status() >= 400 &&
      !isKnownOffline(response.url()) &&
      !isReviewResponse(response)
    ) {
      diagnostics.httpErrors.push({
        status: response.status(),
        url: response.url(),
      });
    }
  });
  page.on("requestfailed", (request) => {
    if (request.url().includes(REVIEW_FILE)) {
      diagnostics.reviewRequestFailures.push({
        url: request.url(),
        error: request.failure()?.errorText || "unknown",
      });
    }
  });
  return diagnostics;
}

async function waitForController(page) {
  await page.waitForFunction(
    () => {
      const state = window.__BF3D_STRUCTURAL_REVIEW__?.getState?.();
      return (
        state?.status === "ready" &&
        state?.mode === "operational" &&
        state?.sensor_count === 115 &&
        state?.callout_present_count >= 1 &&
        state?.yellow_profile_present_count === 1 &&
        state?.process_runtime_present_count === 1
      );
    },
    null,
    { timeout: 90_000 },
  );
  await page.waitForSelector(
    '[data-integrated-review-mode="material"]',
    { state: "visible" },
  );
}

async function openOverview(page, baseUrl) {
  await page.goto(`${baseUrl}?ws_port=8767#overview`, {
    waitUntil: "domcontentloaded",
    timeout: 90_000,
  });
  await waitForController(page);
}

async function stateOf(page) {
  return page.evaluate(() =>
    window.__BF3D_STRUCTURAL_REVIEW__.getState(),
  );
}

async function setMode(page, mode) {
  await page.evaluate(async (nextMode) => {
    await window.__BF3D_STRUCTURAL_REVIEW__.setMode(nextMode);
  }, mode);
  await page.waitForFunction(
    (expectedMode) => {
      const state = window.__BF3D_STRUCTURAL_REVIEW__?.getState?.();
      return state?.mode === expectedMode && state?.asset_status !== "loading";
    },
    mode,
    { timeout: 90_000 },
  );
  return stateOf(page);
}

function assertOperational(state, label) {
  assert(
    state.mode === "operational" &&
      state.operational_asset_url === OPERATIONAL_ASSET_URL &&
      state.review_asset_url === REVIEW_ASSET_URL &&
      state.sensor_count === 115 &&
      state.hit_count === 115 &&
      state.sensor_visible_count === 115 &&
      state.hit_visible_count === 115 &&
      state.base_model_visible === true &&
      state.material_visible_count === 0 &&
      state.section_visible_count === 0,
    label,
    state,
  );
}

function assertReviewContract(state, mode, label) {
  const materialMode = mode === "material";
  assert(
    state.mode === mode &&
      state.asset_status === "ready" &&
      state.operational_asset_url === OPERATIONAL_ASSET_URL &&
      state.review_asset_url === REVIEW_ASSET_URL &&
      state.material_group_count === 1 &&
      state.section_group_count === 1 &&
      state.material_renderable_count === 5 &&
      state.section_renderable_count === 10 &&
      state.material_primitive_renderable_count === 5 &&
      state.section_primitive_renderable_count === 20 &&
      state.material_visible_count === 0 &&
      state.section_visible_count === 10 &&
      state.material_review_layout ===
        (materialMode ? "section_material_audit" : "stacked") &&
      state.physical_section_count === 10 &&
      state.unexpected_top_level_count === 0 &&
      state.forbidden_review_object_count === 0 &&
      state.review_material_clipping_count === 0 &&
      state.review_double_side_count === 0 &&
      state.review_pbr_mutation_count === 0 &&
      state.sensor_visible_count === 0 &&
      state.hit_visible_count === 0 &&
      state.base_model_visible === false &&
      state.callouts_hidden &&
      state.callout_present_count >= 1 &&
      state.callout_visible_count === 0 &&
      state.yellow_profile_present_count === 1 &&
      state.yellow_profile_visible_count === 0 &&
      state.yellow_profile_hidden &&
      state.process_runtime_present_count === 1 &&
      state.process_runtime_visible_count === 0 &&
      state.process_runtime_hidden &&
      state.lookdev_mode === "neutral_direct" &&
      state.lookdev_preset_url === LOOKDEV_PRESET_URL &&
      state.lookdev_preset_schema === "bf3d.lookdev_camera.v1" &&
      state.pmrem_enabled === false &&
      state.pmrem_reason === "no_approved_neutral_environment" &&
      state.not_for_construction === true,
    label,
    state,
  );
}

function assertCleanDiagnostics(diagnostics, label) {
  assert(
    diagnostics.pageErrors.length === 0 &&
      diagnostics.consoleErrors.length === 0 &&
      diagnostics.httpErrors.length === 0,
    label,
    diagnostics,
  );
}

async function runPrimary(baseUrl, browser) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });
  const diagnostics = attachDiagnostics(page);
  const states = {};
  try {
    await openOverview(page, baseUrl);
    states.operationalBefore = await stateOf(page);
    assertOperational(states.operationalBefore, "initial V1 operational contract");
    assert(
      states.operationalBefore.asset_status === "idle" &&
        states.operationalBefore.asset_request_count === 0 &&
        diagnostics.reviewResponses.length === 0,
      "V3 must remain lazy before review mode",
      { state: states.operationalBefore, diagnostics },
    );

    await page
      .locator('[data-integrated-review-mode="material"]')
      .click();
    try {
      await page.waitForFunction(
        () => {
          const state = window.__BF3D_STRUCTURAL_REVIEW__?.getState?.();
          return state?.mode === "material" && state?.asset_status === "ready";
        },
        null,
        { timeout: 90_000 },
      );
    } catch (error) {
      const state = await stateOf(page);
      throw new Error(
        `material review did not become ready: ${JSON.stringify({
          state,
          diagnostics,
          cause: error.message,
        })}`,
      );
    }
    states.material = await stateOf(page);
    assertReviewContract(states.material, "material", "material isolation");
    assert(
      diagnostics.reviewResponses.filter((item) => item.status === 200)
        .length === 1 &&
        states.material.asset_request_count === 1,
      "first material review loads V3 exactly once",
      { state: states.material, diagnostics },
    );
    await page.locator(".layered-cad-stage").screenshot({
      path: path.join(OUTPUT_ROOT, "material_review_1440x900.png"),
    });
    await page.locator('[data-review-camera="global"]').click();
    await page.waitForFunction(
      () =>
        window.__BF3D_STRUCTURAL_REVIEW__?.getState?.()
          .structural_camera === "global",
    );
    states.materialGlobal = await stateOf(page);
    assertReviewContract(
      states.materialGlobal,
      "material",
      "material full-section camera",
    );
    await page.locator('[data-review-camera="layer-detail"]').click();
    await page.waitForFunction(
      () =>
        window.__BF3D_STRUCTURAL_REVIEW__?.getState?.()
          .structural_camera === "layer-detail",
    );

    states.structural = await setMode(page, "structural");
    assertReviewContract(
      states.structural,
      "structural",
      "physical structural section isolation",
    );
    assert(
      await page.locator("[data-review-legend]").isVisible(),
      "structural legend visible",
      states.structural,
    );
    await page.locator(".layered-cad-stage").screenshot({
      path: path.join(OUTPUT_ROOT, "structural_section_1440x900.png"),
    });
    await page.locator('[data-review-camera="layer-detail"]').click();
    await page.waitForFunction(
      () =>
        window.__BF3D_STRUCTURAL_REVIEW__?.getState?.()
          .structural_camera === "layer-detail",
    );
    states.structuralLayerDetail = await stateOf(page);
    assertReviewContract(
      states.structuralLayerDetail,
      "structural",
      "structural layer-detail camera",
    );
    await page.locator(".layered-cad-stage").screenshot({
      path: path.join(
        OUTPUT_ROOT,
        "structural_layer_detail_1440x900.png",
      ),
    });
    await page.locator('[data-review-camera="global"]').click();

    const resourceBaseline = states.structural.owned_resources;
    states.afterThirtyTransitions = await page.evaluate(async () => {
      const controller = window.__BF3D_STRUCTURAL_REVIEW__;
      for (let index = 0; index < 30; index += 1) {
        await controller.setMode(index % 2 ? "material" : "structural");
      }
      return controller.getState();
    });
    assert(
      states.afterThirtyTransitions.asset_request_count === 1 &&
        JSON.stringify(states.afterThirtyTransitions.owned_resources) ===
          JSON.stringify(resourceBaseline),
      "30 transitions reuse one V3 asset and stable owned resources",
      { resourceBaseline, state: states.afterThirtyTransitions },
    );

    states.operationalAfter = await setMode(page, "operational");
    assertOperational(
      states.operationalAfter,
      "operational state restored after review",
    );
    assert(
      states.operationalAfter.asset_request_count === 1,
      "operational return does not reload V3",
      states.operationalAfter,
    );

    states.disposeRemount = await page.evaluate(async () => {
      const oldController = window.__BF3D_STRUCTURAL_REVIEW__;
      window.__BF3D_OLD_REVIEW_CONTROLLER__ = oldController;
      oldController.dispose();
      const started = performance.now();
      while (
        (!window.__BF3D_STRUCTURAL_REVIEW__ ||
          window.__BF3D_STRUCTURAL_REVIEW__ === oldController) &&
        performance.now() - started < 10_000
      ) {
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      return {
        stale: oldController.getState(),
        current: window.__BF3D_STRUCTURAL_REVIEW__?.getState?.() || null,
        panelCount: document.querySelectorAll(".bf3d-review-panel").length,
        reviewRootCount:
          window.__BF_CAD_FURNACE_VIEWER?.scene?.children?.filter?.(
            (object) => object.name === "BF3D_V3_CONTROLLED_REVIEW_ROOT",
          )?.length || 0,
      };
    });
    assert(
      states.disposeRemount.stale.status === "disposed" &&
        states.disposeRemount.stale.owned_resources.geometries === 0 &&
        states.disposeRemount.stale.owned_resources.materials === 0 &&
        states.disposeRemount.stale.owned_resources.textures === 0 &&
        states.disposeRemount.current?.mode === "operational" &&
        states.disposeRemount.current?.asset_status === "idle" &&
        states.disposeRemount.current?.sensor_visible_count === 115 &&
        states.disposeRemount.panelCount === 1 &&
        states.disposeRemount.reviewRootCount === 0,
      "dispose removes V3 resources and remounts one clean controller",
      states.disposeRemount,
    );

    assertCleanDiagnostics(diagnostics, "primary browser diagnostics");
    return {
      states,
      diagnostics,
      screenshots: [
        "material_review_1440x900.png",
        "structural_section_1440x900.png",
      ],
    };
  } finally {
    await page.close();
  }
}

async function runRaceRecovery(baseUrl, browser) {
  const page = await browser.newPage({
    viewport: { width: 1366, height: 768 },
  });
  const diagnostics = attachDiagnostics(page);
  let delayedRequests = 0;
  const routePattern = `**/models/${REVIEW_FILE}*`;
  await page.route(routePattern, async (route) => {
    delayedRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 750));
    try {
      await route.fulfill({
        status: 200,
        contentType: "model/gltf-binary",
        path: REVIEW_ASSET_PATH,
      });
    } catch {
      // An AbortController cancellation is the expected race outcome.
    }
  });
  try {
    await openOverview(page, baseUrl);
    await page.evaluate(() => {
      void window.__BF3D_STRUCTURAL_REVIEW__.setMode("material");
    });
    await page.waitForFunction(
      () =>
        window.__BF3D_STRUCTURAL_REVIEW__?.getState?.().asset_status ===
        "loading",
    );
    await page.evaluate(() => {
      void window.__BF3D_STRUCTURAL_REVIEW__.setMode("structural");
      void window.__BF3D_STRUCTURAL_REVIEW__.setMode("operational");
    });
    await page.waitForTimeout(1000);
    const cancelled = await page.evaluate(() => {
      const controller = window.__BF3D_STRUCTURAL_REVIEW__;
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      return {
        state: controller.getState(),
        reviewRootCount: viewer.scene.children.filter(
          (object) => object.name === "BF3D_V3_CONTROLLED_REVIEW_ROOT",
        ).length,
      };
    });
    assertOperational(cancelled.state, "race returns to V1 operational mode");
    assert(
      cancelled.state.asset_status === "idle" &&
        cancelled.state.abort_count >= 1 &&
        cancelled.reviewRootCount === 0 &&
        delayedRequests === 1,
      "aborted V3 request cannot commit stale review state",
      { cancelled, delayedRequests, diagnostics },
    );

    await page.unroute(routePattern);
    await page.evaluate(() => {
      const controller = window.__BF3D_STRUCTURAL_REVIEW__;
      void controller.setMode("material");
      void controller.setMode("operational");
      void controller.setMode("structural");
    });
    await page.waitForFunction(
      () => {
        const state = window.__BF3D_STRUCTURAL_REVIEW__?.getState?.();
        return state?.mode === "structural" && state?.asset_status === "ready";
      },
      null,
      { timeout: 90_000 },
    );
    const recovered = await stateOf(page);
    assertReviewContract(
      recovered,
      "structural",
      "controller survives immediate material-operational-structural re-entry",
    );
    assert(
      recovered.asset_request_count === 3 &&
        recovered.abort_count >= 2,
      "immediate re-entry starts a fresh generation without stale commit",
      recovered,
    );
    assert(
      diagnostics.pageErrors.length === 0 &&
        diagnostics.httpErrors.length === 0,
      "race recovery browser diagnostics",
      diagnostics,
    );
    return { cancelled, recovered, delayedRequests, diagnostics };
  } finally {
    await page.close();
  }
}

async function runErrorRetry(baseUrl, browser) {
  const page = await browser.newPage({
    viewport: { width: 1366, height: 768 },
  });
  const diagnostics = attachDiagnostics(page);
  let routedRequests = 0;
  const routePattern = `**/models/${REVIEW_FILE}*`;
  await page.route(routePattern, async (route) => {
    routedRequests += 1;
    if (routedRequests === 1) {
      await route.fulfill({
        status: 503,
        contentType: "text/plain; charset=utf-8",
        body: "deliberate verification fault",
      });
      return;
    }
    await route.continue();
  });
  try {
    await openOverview(page, baseUrl);
    await page
      .locator('[data-integrated-review-mode="material"]')
      .click();
    await page.waitForFunction(
      () =>
        window.__BF3D_STRUCTURAL_REVIEW__?.getState?.().asset_status ===
        "error",
      null,
      { timeout: 90_000 },
    );
    const failed = await stateOf(page);
    assert(
      failed.mode === "operational" &&
        failed.sensor_visible_count === 115 &&
        failed.hit_visible_count === 115 &&
        failed.base_model_visible === true &&
        failed.asset_status === "error" &&
        failed.load_attempt === 1 &&
        failed.asset_request_count === 1 &&
        (await page.locator("[data-review-retry]").isVisible()),
      "V3 failure restores V1 and exposes retry",
      { failed, diagnostics },
    );

    await page.locator("[data-review-retry]").click();
    await page.waitForFunction(
      () => {
        const state = window.__BF3D_STRUCTURAL_REVIEW__?.getState?.();
        return state?.mode === "material" && state?.asset_status === "ready";
      },
      null,
      { timeout: 90_000 },
    );
    const recovered = await stateOf(page);
    assertReviewContract(
      recovered,
      "material",
      "retry recovers material review",
    );
    assert(
      recovered.load_attempt === 2 &&
        recovered.asset_request_count === 2 &&
        routedRequests === 2,
      "retry performs exactly one additional request",
      { recovered, routedRequests, diagnostics },
    );
    const unexpectedConsole = diagnostics.consoleErrors.filter(
      (entry) =>
        !entry.location.includes(REVIEW_FILE) &&
        !entry.text.includes("503"),
    );
    assert(
      diagnostics.pageErrors.length === 0 &&
        diagnostics.httpErrors.length === 0 &&
        unexpectedConsole.length === 0,
      "retry browser diagnostics",
      { diagnostics, unexpectedConsole },
    );
    return { failed, recovered, routedRequests, diagnostics };
  } finally {
    await page.close();
  }
}

async function runDetailRestoreRace(baseUrl, browser) {
  const page = await browser.newPage({
    viewport: { width: 1366, height: 768 },
  });
  const diagnostics = attachDiagnostics(page);
  let detailRequests = 0;
  let releaseDetailRequest;
  const detailRequestGate = new Promise((resolve) => {
    releaseDetailRequest = resolve;
  });
  await page.route(`**/${DETAIL_NORMAL_FILE}*`, async (route) => {
    detailRequests += 1;
    await detailRequestGate;
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      path: DETAIL_NORMAL_PATH,
    });
  });
  try {
    await openOverview(page, baseUrl);
    const beforeReview = await stateOf(page);
    assert(
      beforeReview.r2h_detail_normal === null,
      "detail restore race requires a pending detail texture",
      beforeReview,
    );
    const material = await setMode(page, "material");
    assertReviewContract(
      material,
      "material",
      "detail restore race material mode",
    );
    releaseDetailRequest();
    await page.waitForFunction(
      () =>
        window.__BF3D_STRUCTURAL_REVIEW__?.getState?.()
          .r2h_detail_normal !== null,
      null,
      { timeout: 90_000 },
    );
    const disabledDuringReview = await stateOf(page);
    assert(
      disabledDuringReview.r2h_detail_normal.status === "disabled" &&
        disabledDuringReview.r2h_detail_normal.detail_normal.active ===
          false,
      "late R2H detail completion remains disabled during review",
      disabledDuringReview.r2h_detail_normal,
    );
    const restored = await setMode(page, "operational");
    assertOperational(restored, "detail restore race operational mode");
    assert(
      restored.r2h_detail_normal?.status !== "disabled" &&
        restored.r2h_detail_normal?.detail_normal?.active === true &&
        detailRequests === 1,
      "late R2H detail is re-enabled on operational restore",
      { detail: restored.r2h_detail_normal, detailRequests },
    );
    assertCleanDiagnostics(diagnostics, "detail restore diagnostics");
    return {
      beforeReview,
      disabledDuringReview,
      restored,
      detailRequests,
      diagnostics,
    };
  } finally {
    releaseDetailRequest?.();
    await page.close();
  }
}

async function runMatrix(baseUrl, options = {}) {
  const edgeOnly = options.edgeOnly === true;
  const cases = [];
  const matrixRoot = path.join(
    OUTPUT_ROOT,
    edgeOnly ? "edge_smoke" : "matrix",
  );
  fs.mkdirSync(matrixRoot, { recursive: true });
  const engines = edgeOnly
    ? [
        [
          "msedge",
          playwright.chromium,
          REPRESENTATIVE_VIEWPORTS,
          { channel: "msedge" },
        ],
      ]
    : [
        ["chromium", playwright.chromium, CHROMIUM_VIEWPORTS, {}],
        ["firefox", playwright.firefox, REPRESENTATIVE_VIEWPORTS, {}],
        ["webkit", playwright.webkit, REPRESENTATIVE_VIEWPORTS, {}],
      ];

  for (const [engineName, launcher, viewports, launchOptions] of engines) {
    const browser = await launcher.launch({
      headless: true,
      ...launchOptions,
    });
    const browserVersion = browser.version();
    try {
      for (const [width, height] of viewports) {
        const page = await browser.newPage({
          viewport: { width, height },
        });
        const diagnostics = attachDiagnostics(page);
        try {
          await openOverview(page, baseUrl);
          const initial = await stateOf(page);
          assert(
            initial.asset_status === "idle" &&
              diagnostics.reviewResponses.length === 0,
            `${engineName} ${width}x${height} lazy V3`,
            { initial, diagnostics },
          );
          const material = await setMode(page, "material");
          assertReviewContract(
            material,
            "material",
            `${engineName} ${width}x${height} material`,
          );
          const structural = await setMode(page, "structural");
          assertReviewContract(
            structural,
            "structural",
            `${engineName} ${width}x${height} structural`,
          );
          const layout = await page.evaluate(() => {
            const root = document.documentElement;
            const body = document.body;
            const panel = document.querySelector(".bf3d-review-panel");
            const panelRect = panel?.getBoundingClientRect();
            const buttons = [
              ...document.querySelectorAll("[data-review-mode]"),
            ];
            return {
              horizontalOverflow:
                root.scrollWidth > root.clientWidth + 1 ||
                body.scrollWidth > root.clientWidth + 1,
              panelVisible:
                Boolean(panelRect) &&
                panelRect.width > 0 &&
                panelRect.height > 0,
              visibleButtons: buttons.filter((button) => {
                const rect = button.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
              }).length,
              headerPresent:
                document.body.textContent.includes(
                  "高炉工艺大模型智能决策系统",
                ) &&
                Boolean(document.querySelector(".topbar.branded-topbar")),
              browserIdentity: {
                userAgent: navigator.userAgent,
                brands: navigator.userAgentData?.brands || [],
              },
            };
          });
          assert(
            !layout.horizontalOverflow &&
              layout.panelVisible &&
              layout.visibleButtons === 3 &&
              layout.headerPresent,
            `${engineName} ${width}x${height} layout`,
            layout,
          );
          if (engineName === "msedge") {
            const identityText = JSON.stringify(
              layout.browserIdentity,
            );
            assert(
              identityText.includes("Edg/") ||
                identityText.includes("Microsoft Edge"),
              `${engineName} ${width}x${height} real Edge identity`,
              {
                browserVersion,
                browserIdentity: layout.browserIdentity,
              },
            );
          }
          assert(
            structural.asset_request_count === 1 &&
              diagnostics.reviewResponses.filter(
                (item) => item.status === 200,
              ).length === 1,
            `${engineName} ${width}x${height} one V3 request`,
            { structural, diagnostics },
          );
          const screenshot =
            `${engineName}_${width}x${height}_structural.png`;
          await page.locator(".layered-cad-stage").screenshot({
            path: path.join(matrixRoot, screenshot),
          });
          const restored = await setMode(page, "operational");
          assertOperational(
            restored,
            `${engineName} ${width}x${height} operational restore`,
          );
          assertCleanDiagnostics(
            diagnostics,
            `${engineName} ${width}x${height} diagnostics`,
          );
          cases.push({
            engine: engineName,
            browserVersion,
            viewport: `${width}x${height}`,
            initial,
            material,
            structural,
            restored,
            layout,
            diagnostics,
            screenshot,
            passed: true,
          });
        } finally {
          await page.close();
        }
      }
    } finally {
      await browser.close();
    }
  }

  const expectedCases = edgeOnly ? REPRESENTATIVE_VIEWPORTS.length : 17;
  const report = {
    requirement_id: edgeOnly
      ? "REQ-BF3D-R2R-LOCAL-EDGE-SMOKE-20260719"
      : "REQ-BF3D-STRUCTURAL-REVIEW-20260719",
    scope: edgeOnly
      ? "local Microsoft Edge stable smoke; not on-site Edge acceptance"
      : "cross-engine and viewport matrix",
    expected_cases: expectedCases,
    actual_cases: cases.length,
    passed:
      cases.length === expectedCases &&
      cases.every((item) => item.passed),
    cases,
  };
  fs.writeFileSync(
    path.join(
      OUTPUT_ROOT,
      edgeOnly ? "edge_smoke_report.json" : "matrix_report.json",
    ),
    JSON.stringify(report, null, 2) + "\n",
    "utf8",
  );
  return report;
}

async function main() {
  assert(
    fs.existsSync(LOOKDEV_PRESET_SOURCE_PATH) &&
      fs.existsSync(LOOKDEV_PRESET_RUNTIME_PATH),
    "controlled LookDev source and runtime copy are required",
    {
      source: LOOKDEV_PRESET_SOURCE_PATH,
      runtime: LOOKDEV_PRESET_RUNTIME_PATH,
    },
  );
  const sourcePresetSha256 = sha256(LOOKDEV_PRESET_SOURCE_PATH);
  const runtimePresetSha256 = sha256(LOOKDEV_PRESET_RUNTIME_PATH);
  assert(
    sourcePresetSha256 === LOOKDEV_PRESET_SHA256 &&
      runtimePresetSha256 === LOOKDEV_PRESET_SHA256,
    "runtime LookDev preset must be byte-identical to controlled PT source",
    {
      expected: LOOKDEV_PRESET_SHA256,
      source: sourcePresetSha256,
      runtime: runtimePresetSha256,
    },
  );
  assert(
    fs.existsSync(REVIEW_ASSET_PATH),
    "controlled V3 GLB is required before browser verification",
    REVIEW_ASSET_PATH,
  );
  const webGlbAssets = [
    REVIEW_ASSET_PATH,
    MATERIAL_REVIEW_ASSET_PATH,
    STRUCTURAL_REVIEW_ASSET_PATH,
  ].map((filePath) => ({
    path: filePath,
    bytes: fs.existsSync(filePath) ? fs.statSync(filePath).size : -1,
    sha256: fs.existsSync(filePath) ? sha256(filePath) : null,
  }));
  assert(
    webGlbAssets.every(
      (asset) =>
        asset.bytes > 0 &&
        asset.bytes <= MAX_WEB_GLB_BYTES,
    ),
    "all controlled V3 Web GLBs must stay within the 25 MB gate",
    { max_bytes: MAX_WEB_GLB_BYTES, assets: webGlbAssets },
  );
  assert(
    fs.existsSync(DETAIL_NORMAL_PATH),
    "R2H detail texture is required before browser verification",
    DETAIL_NORMAL_PATH,
  );
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const server = await startServer();
  const port = server.address().port;
  const baseUrl =
    `http://127.0.0.1:${port}/frontend_dashboard_v3.server.html`;
  const browser = await playwright.chromium.launch({ headless: true });
  try {
    const primary = await runPrimary(baseUrl, browser);
    const raceRecovery = await runRaceRecovery(baseUrl, browser);
    const errorRetry = await runErrorRetry(baseUrl, browser);
    const detailRestoreRace = await runDetailRestoreRace(
      baseUrl,
      browser,
    );
    const matrix = RUN_MATRIX ? await runMatrix(baseUrl) : null;
    const edgeSmoke = RUN_EDGE_SMOKE
      ? await runMatrix(baseUrl, { edgeOnly: true })
      : null;
    const report = {
      requirement_id: "REQ-BF3D-STRUCTURAL-REVIEW-20260719",
      schema_version: "bf3d.web.structural_review_verification.v3",
      url: `${baseUrl}?ws_port=8767#overview`,
      controlled_assets: {
        operational: OPERATIONAL_ASSET_URL,
        review: REVIEW_ASSET_URL,
        web_glbs: webGlbAssets.map((asset) => ({
          path: path.relative(ROOT, asset.path),
          bytes: asset.bytes,
          sha256: asset.sha256,
        })),
        lookdev: {
          url: LOOKDEV_PRESET_URL,
          source_path: path.relative(ROOT, LOOKDEV_PRESET_SOURCE_PATH),
          runtime_path: path.relative(ROOT, LOOKDEV_PRESET_RUNTIME_PATH),
          sha256: LOOKDEV_PRESET_SHA256,
        },
      },
      primary,
      raceRecovery,
      errorRetry,
      detailRestoreRace,
      matrix,
      edgeSmoke,
      passed:
        primary &&
        raceRecovery &&
        errorRetry &&
        detailRestoreRace &&
        (!RUN_MATRIX || matrix?.passed === true) &&
        (!RUN_EDGE_SMOKE || edgeSmoke?.passed === true),
    };
    fs.writeFileSync(
      path.join(OUTPUT_ROOT, "report.json"),
      JSON.stringify(report, null, 2) + "\n",
      "utf8",
    );
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
