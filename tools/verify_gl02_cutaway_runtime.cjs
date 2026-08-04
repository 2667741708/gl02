#!/usr/bin/env node
"use strict";

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
const OUTPUT_ROOT = path.join(ROOT, "logs", "bf3d_cutaway_runtime_20260717");
const modelArgument = process.argv.find((value) => value.startsWith("--model="));
const MODEL_OVERRIDE = modelArgument
  ? path.resolve(modelArgument.slice("--model=".length))
  : null;
const LABEL = MODEL_OVERRIDE ? "p60_4k" : "formal";
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

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
      let target;
      if (
        MODEL_OVERRIDE &&
        pathname === "/models/gl02_blast_furnace.glb"
      ) {
        target = MODEL_OVERRIDE;
      } else {
        if (pathname === "/") pathname = "/frontend_dashboard_v3.server.html";
        target = path.resolve(FRONTEND_ROOT, pathname.replace(/^\/+/, ""));
        if (
          target !== FRONTEND_ROOT &&
          !target.startsWith(FRONTEND_ROOT + path.sep)
        ) {
          response.writeHead(403).end("forbidden");
          return;
        }
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

function isExpectedOffline(message) {
  return (
    message.includes("127.0.0.1:8767") ||
    message.includes("/api/") ||
    message.includes("Failed to fetch") ||
    message.includes("ERR_CONNECTION_REFUSED")
  );
}

function assert(condition, message, detail) {
  if (!condition) {
    throw new Error(`${message}: ${JSON.stringify(detail)}`);
  }
}

async function main() {
  if (MODEL_OVERRIDE && !fs.existsSync(MODEL_OVERRIDE)) {
    throw new Error(`model override not found: ${MODEL_OVERRIDE}`);
  }
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const server = await startServer();
  const port = server.address().port;
  const url = `http://127.0.0.1:${port}/frontend_dashboard_v3.server.html?ws_port=8767#overview`;
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  const pageErrors = [];
  const consoleErrors = [];
  const httpErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      httpErrors.push({ status: response.status(), url: response.url() });
    }
  });

  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90_000 });
    try {
      await page.waitForFunction(
        () =>
          document.querySelector(".cad-furnace-viewer")?.dataset.status ===
          "loaded",
        null,
        { timeout: 90_000 },
      );
      await page.waitForFunction(
        () => window.__BF_CAD_FURNACE_VIEWER?.sensorCount === 115,
        null,
        { timeout: 90_000 },
      );
      await page.waitForFunction(
        () =>
          typeof window.__BF_CAD_FURNACE_VIEWER?.getCutawayState ===
          "function",
        null,
        { timeout: 90_000 },
      );
      await page.waitForFunction(
        () =>
          typeof window.__BF_CAD_FURNACE_VIEWER
            ?.getInternalSimulationState === "function",
        null,
        { timeout: 90_000 },
      );
    } catch (error) {
      const readiness = await page.evaluate(() => {
        const host = document.querySelector(".cad-furnace-viewer");
        const viewer = window.__BF_CAD_FURNACE_VIEWER;
        return {
          readyState: document.readyState,
          hostConnected: Boolean(host?.isConnected),
          hostDataset: host ? { ...host.dataset } : null,
          viewerExists: Boolean(viewer),
          viewerKeys: viewer ? Object.keys(viewer).sort() : [],
          sensorCount: viewer?.sensorCount ?? null,
          sensorObjectCount: viewer?.sensorObjects?.length ?? null,
          hasCutawayState: typeof viewer?.getCutawayState === "function",
          hasInternalSimulationState:
            typeof viewer?.getInternalSimulationState === "function",
          structuralReviewStatus:
            host?.dataset.bf3dStructuralReviewStatus || null,
          globalSimulationExists: Boolean(
            window.__BF3D_INTERNAL_SIMULATION__,
          ),
        };
      });
      const diagnostic = {
        ok: false,
        label: LABEL,
        url,
        error: error.stack || String(error),
        readiness,
        pageErrors,
        consoleErrors,
        httpErrors,
      };
      fs.writeFileSync(
        path.join(OUTPUT_ROOT, `${LABEL}_readiness_failure.json`),
        JSON.stringify(diagnostic, null, 2),
        "utf8",
      );
      throw new Error(
        `cutaway readiness failed: ${JSON.stringify(diagnostic)}`,
      );
    }
    const before = await page.evaluate(() => {
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const state = viewer.getCutawayState();
      const shell = [];
      viewer.model.traverse((object) => {
        if (!object.isMesh || !/^APPROX_GL02_FURNACE_/.test(object.name)) return;
        const materials = Array.isArray(object.material)
          ? object.material
          : [object.material];
        materials.forEach((material) =>
          shell.push({
            name: material.name,
            roughness: material.roughness,
            metalness: material.metalness,
            opacity: material.opacity,
            transparent: material.transparent,
            map: Boolean(material.map),
            roughnessMap: Boolean(material.roughnessMap),
            metalnessMap: Boolean(material.metalnessMap),
            normalMap: Boolean(material.normalMap),
            aoMap: Boolean(material.aoMap),
          }),
        );
      });
      return {
        state,
        simulation: viewer.getInternalSimulationState(),
        shell,
        highlight: viewer.getLayerHighlightState(),
        host: { ...document.querySelector(".cad-furnace-viewer").dataset },
      };
    });
    assert(before.state.mode === "exterior", "default mode", before);
    assert(
      before.state.internalCount === 0,
      "legacy internal objects delegated to authoritative runtime",
      before,
    );
    assert(before.state.visibleInternalCount === 0, "default hidden", before);
    assert(
      before.simulation.cutawayMode === "exterior" &&
        before.simulation.visible === false &&
        before.simulation.resources.legacyDecorativeCount === 45 &&
        before.simulation.resources.legacyDecorativeVisibleCount === 0,
      "legacy objects delegated to authoritative runtime",
      before.simulation,
    );
    assert(
      Object.values(before.state.shellMaterialContract).every(
        (value) => typeof value !== "boolean" || value,
      ),
      "shell material preservation contract",
      before.state.shellMaterialContract,
    );
    assert(
      before.state.clippedMaterialCount >= before.state.shellMaterialCount,
      "clipped material coverage",
      before.state,
    );
    assert(
      before.shell.every(
        (material) =>
          material.opacity === 1 &&
          material.transparent === false &&
          material.roughness >= 0.72 &&
          material.roughness <= 1 &&
          material.metalness >= 0.3 &&
          material.metalness <= 1,
      ),
      "opaque matte material factors",
      before.shell,
    );
    if (MODEL_OVERRIDE) {
      assert(
        before.highlight.source === "embedded" &&
          before.highlight.embeddedBandCount === 10,
        "P60 embedded L7-L16 bands",
        before.highlight,
      );
      assert(
        before.shell.every(
          (material) =>
            material.map &&
            material.roughnessMap &&
            material.metalnessMap &&
            material.normalMap &&
            material.aoMap,
        ),
        "P60 full PBR maps",
        before.shell,
      );
    }

    await page.locator('button[data-cutaway-action="cutaway"]').click();
    await page.waitForTimeout(220);
    const entering = await page.evaluate(() => ({
      state: window.__BF_CAD_FURNACE_VIEWER.getCutawayState(),
      simulation:
        window.__BF_CAD_FURNACE_VIEWER.getInternalSimulationState(),
      text: document.querySelector(".cad-cutaway-status")?.textContent || "",
    }));
    assert(
      ["cutting", "revealing", "playing"].includes(entering.state.phase) &&
        entering.state.cutProgress > 0 &&
        entering.state.cutProgress <= 1 &&
        entering.simulation.cutawayMode === "cutaway" &&
        entering.simulation.resources.legacyDecorativeVisibleCount === 0 &&
        entering.text.includes("非实时断面测量"),
      "cutaway enter animation",
      entering,
    );
    await page.waitForTimeout(1450);
    const playing = await page.evaluate(() => ({
      state: window.__BF_CAD_FURNACE_VIEWER.getCutawayState(),
      simulation:
        window.__BF_CAD_FURNACE_VIEWER.getInternalSimulationState(),
    }));
    assert(
      playing.state.phase === "playing" &&
        playing.state.visibleInternalCount === 0 &&
        playing.state.revealProgress === 0 &&
        playing.state.focusObjectCount === 5 &&
        playing.state.focusHiddenCount === 5 &&
        playing.state.cutawayLightsVisible === true &&
        playing.state.cutawayEdgesVisible === true &&
        playing.state.controlsBound === true &&
        playing.simulation.cutawayMode === "cutaway" &&
        playing.simulation.visible === true &&
        playing.simulation.resources.legacyDecorativeVisibleCount === 0,
      "cutaway staged reveal",
      playing,
    );
    await page.locator('button[data-cutaway-action="play"]').click();

    const layerCounts = {};
    for (let layer = 7; layer <= 16; layer += 1) {
      const layerId = `L${layer}`;
      await page
        .locator(`button[data-kind="layer"][data-id="${layerId}"]`)
        .click();
      await page.waitForTimeout(35);
      layerCounts[layerId] = await page.evaluate(
        () =>
          Number(
            document.querySelector(".cad-furnace-viewer")?.dataset
              .visibleSensors || 0,
          ),
      );
    }
    assert(
      Object.values(layerCounts).every((count) => count === 8),
      "L7-L16 point counts",
      layerCounts,
    );

    const reuse = await page.evaluate(() => {
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const beforeState = viewer.getCutawayState();
      for (let index = 0; index < 20; index += 1) {
        viewer.setCutawayMode("exterior");
        viewer.setCutawayMode("cutaway");
      }
      viewer.resetCutaway();
      return { before: beforeState, after: viewer.getCutawayState() };
    });
    for (const field of [
      "objectCount",
      "materialCount",
      "internalCount",
      "shellMaterialCount",
      "clippedMaterialCount",
    ]) {
      assert(
        reuse.before[field] === reuse.after[field],
        `resource reuse ${field}`,
        reuse,
      );
    }
    assert(
      reuse.after.mode === "exterior" &&
        reuse.after.visibleInternalCount === 0 &&
        reuse.after.focusHiddenCount === 0 &&
        reuse.after.cutawayLightsVisible === false &&
        reuse.after.cutawayEdgesVisible === false,
      "reset exterior",
      reuse.after,
    );

    const screenshot = path.join(OUTPUT_ROOT, `${LABEL}_cutaway_L16.png`);
    await page.locator('button[data-cutaway-action="cutaway"]').click();
    await page.waitForTimeout(1600);
    await page.screenshot({ path: screenshot, fullPage: false });
    await page.evaluate(() => {
      window.__BF_CUTAWAY_ROUTE_OLD_VIEWER__ =
        window.__BF_CAD_FURNACE_VIEWER;
    });
    await page.locator(".bottom-nav .nav-btn").nth(1).click();
    await page.waitForFunction(
      () => !document.querySelector(".cad-furnace-viewer"),
      null,
      { timeout: 15_000 },
    );
    await page.waitForFunction(
      () => window.__BF_CUTAWAY_ROUTE_OLD_VIEWER__?.__bfLayerVisualsV2Disposed,
      null,
      { timeout: 15_000 },
    );
    await page.locator(".bottom-nav .nav-btn").nth(0).click();
    await page.waitForFunction(
      () =>
        window.__BF_CAD_FURNACE_VIEWER !==
          window.__BF_CUTAWAY_ROUTE_OLD_VIEWER__ &&
        window.__BF_CAD_FURNACE_VIEWER?.sensorCount === 115 &&
        typeof window.__BF_CAD_FURNACE_VIEWER?.getCutawayState ===
          "function" &&
        typeof window.__BF_CAD_FURNACE_VIEWER
          ?.getInternalSimulationState === "function",
      null,
      { timeout: 90_000 },
    );
    const routeLifecycle = await page.evaluate(() => {
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const beforeState = viewer.getCutawayState();
      const beforeSimulation = viewer.getInternalSimulationState();
      viewer.setCutawayMode("cutaway");
      const cutawayState = viewer.getCutawayState();
      const cutawaySimulation = viewer.getInternalSimulationState();
      viewer.resetCutaway();
      const resetState = viewer.getCutawayState();
      const resetSimulation = viewer.getInternalSimulationState();
      const host = { ...document.querySelector(".cad-furnace-viewer").dataset };
      delete window.__BF_CUTAWAY_ROUTE_OLD_VIEWER__;
      return {
        beforeState,
        beforeSimulation,
        cutawayState,
        cutawaySimulation,
        resetState,
        resetSimulation,
        host,
      };
    });
    assert(
      routeLifecycle.beforeState.mode === "exterior" &&
        routeLifecycle.beforeState.internalCount === 0 &&
        routeLifecycle.beforeState.visibleInternalCount === 0 &&
        routeLifecycle.beforeSimulation.resources
          .legacyDecorativeVisibleCount === 0 &&
        routeLifecycle.beforeState.controlsBound === true &&
        routeLifecycle.cutawayState.mode === "cutaway" &&
        routeLifecycle.cutawaySimulation.resources
          .legacyDecorativeVisibleCount === 0 &&
        routeLifecycle.cutawayState.focusHiddenCount === 5 &&
        routeLifecycle.cutawayState.cutawayEdgesVisible === true &&
        routeLifecycle.resetState.mode === "exterior" &&
        routeLifecycle.resetSimulation.resources
          .legacyDecorativeVisibleCount === 0,
      "route remount lifecycle",
      routeLifecycle,
    );
    const unexpectedHttpErrors = httpErrors.filter(
      (entry) =>
        !isExpectedOffline(entry.url) &&
        !new URL(entry.url).pathname.endsWith("/favicon.ico"),
    );
    const hasExpectedOfflineResponse = httpErrors.some((entry) =>
      isExpectedOffline(entry.url),
    );
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) =>
        !isExpectedOffline(message) &&
        !message.includes("[BABEL] Note:") &&
        !(
          hasExpectedOfflineResponse &&
          message.includes("Failed to load resource:")
        ),
    );
    const result = {
      ok: true,
      label: LABEL,
      url,
      modelOverride: MODEL_OVERRIDE,
      before,
      entering,
      playing,
      layerCounts,
      reuse,
      routeLifecycle,
      screenshot,
      pageErrors,
      consoleErrors: unexpectedConsoleErrors,
      httpErrors: unexpectedHttpErrors,
      ignoredOfflineConsoleErrors: consoleErrors.filter(
        (message) => !unexpectedConsoleErrors.includes(message),
      ),
      ignoredOfflineHttpErrors: httpErrors.filter(
        (entry) => !unexpectedHttpErrors.includes(entry),
      ),
    };
    fs.writeFileSync(
      path.join(OUTPUT_ROOT, `${LABEL}_report.json`),
      JSON.stringify(result, null, 2),
      "utf8",
    );
    assert(pageErrors.length === 0, "page errors", pageErrors);
    assert(
      unexpectedConsoleErrors.length === 0,
      "console errors",
      unexpectedConsoleErrors,
    );
    assert(
      unexpectedHttpErrors.length === 0,
      "http errors",
      unexpectedHttpErrors,
    );
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
