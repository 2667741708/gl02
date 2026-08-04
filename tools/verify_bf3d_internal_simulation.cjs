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
const OUTPUT_ROOT = path.join(
  ROOT,
  "logs",
  "bf3d_internal_simulation_20260719",
);
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function assert(condition, message, detail) {
  if (!condition) {
    throw new Error(`${message}: ${JSON.stringify(detail)}`);
  }
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
      if (pathname === "/api/trend/history") {
        response
          .writeHead(200, {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
          })
          .end(
            JSON.stringify({
              ok: true,
              history: { timestamps: ["2026-07-19T00:00:00.000Z"] },
              data_quality: { state: "test" },
              source: "runtime-contract-test",
              server: "local",
              interval_seconds: 60,
              aggregate: "mean",
            }),
          );
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

function expectedOffline(text) {
  return (
    text.includes("127.0.0.1:8767") ||
    text.includes("/api/automation/") ||
    text.includes("/api/short-window/") ||
    text.includes("Failed to fetch") ||
    text.includes("ERR_CONNECTION_REFUSED") ||
    text.includes("[BABEL] Note:")
  );
}

async function main() {
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const server = await startServer();
  const port = server.address().port;
  const url = `http://127.0.0.1:${port}/frontend_dashboard_v3.server.html?ws_port=8767#overview`;
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });
  await page.addInitScript(() => {
    class ContractTestWebSocket extends EventTarget {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      constructor(url, protocols) {
        super();
        this.url = String(url || "");
        this.protocols = protocols;
        this.readyState = ContractTestWebSocket.CONNECTING;
        this.sent = [];
        window.__BF3D_TEST_WEBSOCKETS__ =
          window.__BF3D_TEST_WEBSOCKETS__ || [];
        window.__BF3D_TEST_WEBSOCKETS__.push(this);
        setTimeout(() => {
          if (this.readyState !== ContractTestWebSocket.CONNECTING) return;
          this.readyState = ContractTestWebSocket.OPEN;
          const event = new Event("open");
          this.dispatchEvent(event);
          if (typeof this.onopen === "function") this.onopen(event);
        }, 0);
      }

      send(value) {
        this.sent.push(value);
      }

      close() {
        if (this.readyState === ContractTestWebSocket.CLOSED) return;
        this.readyState = ContractTestWebSocket.CLOSED;
        const event = new CloseEvent("close");
        this.dispatchEvent(event);
        if (typeof this.onclose === "function") this.onclose(event);
      }

      emitMessage(value) {
        this.dispatchEvent(
          new MessageEvent("message", {
            data:
              typeof value === "string"
                ? value
                : JSON.stringify(value),
          }),
        );
      }
    }
    window.WebSocket = ContractTestWebSocket;
  });
  const pageErrors = [];
  const consoleErrors = [];
  const httpErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      httpErrors.push({ status: response.status(), url: response.url() });
    }
  });

  try {
    await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    await page.waitForFunction(
      () =>
        window.__BF_CAD_FURNACE_VIEWER?.sensorCount === 115 &&
        window.__BF3D_INTERNAL_SIMULATION__?.getState?.().ready === true,
      null,
      { timeout: 90_000 },
    );

    const initial = await page.evaluate(() =>
      window.__BF3D_INTERNAL_SIMULATION__.getState(),
    );
    assert(initial.mode === "live", "default data mode", initial);
    assert(initial.cutawayMode === "exterior", "default exterior", initial);
    assert(initial.visible === false, "internal root hidden outside cutaway", initial);
    assert(
      initial.stock.evidence === "blocked" &&
        initial.stocklineGate.enabled === false &&
        initial.stocklineGate.south_north_tilt_enabled === false,
      "stockline and tilt gate",
      initial.stock,
    );
    assert(
      initial.cohesive.visible === false &&
        initial.pressure.visibleMeasuredCount === 0 &&
        initial.hearth.liquidVisible === false,
      "no reliable input stays hidden",
      initial,
    );
    assert(
      initial.resources.tuyereInstances === 26 &&
        initial.resources.pressureMarkers === 18 &&
        initial.resources.pressureBands === 3 &&
        initial.resources.burdenLayerPool === 12,
      "fixed runtime resource contract",
      initial.resources,
    );
    assert(
      Object.values(initial.truthBoundary).every(Boolean),
      "truth boundary contract",
      initial.truthBoundary,
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const next = api.makeIllustrativeSnapshot();
      const now = new Date().toISOString();
      next.mode = "live";
      next.knowledge_time = now;
      next.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.quality_state = "good";
        row.sample_time = now;
        delete row.deviation_kpa;
      });
      api.injectSnapshot(next);
    });
    await page.waitForTimeout(120);
    const exteriorRawPressure = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const scene = api.viewer.scene;
      const operational = scene.getObjectByName(
        "BF3D_MEAS_STATIC_PRESSURE",
      );
      const field = scene.getObjectByName(
        "BF3D_DERIVED_STATIC_PRESSURE_FIELD",
      );
      const markers = operational.children.filter((item) =>
        item.name.startsWith("BF3D_MEAS_STATIC_PRESSURE_"),
      );
      const bands = field.children.filter((item) =>
        item.name.startsWith("BF3D_INTERP_STATIC_PRESSURE_BAND_"),
      );
      const arrows = field.children.filter((item) =>
        item.name.startsWith("BF3D_EST_PRESSURE_BIAS_ARROW_"),
      );
      return {
        state: api.getState(),
        internalRootVisible: scene.getObjectByName(
          "BF3D_INTERNAL_SIMULATION_RUNTIME",
        )?.visible,
        operationalVisible: operational.visible,
        operationalReviewVisibility:
          operational.userData.bf3d_review_visibility,
        markerColors: markers
          .filter((marker) => marker.visible)
          .map((marker) => marker.material.color.getHex()),
        radialOffsetsFromBand: bands.map((band, heightIndex) => {
          const marker = markers[heightIndex * 6];
          const markerRadius = Math.hypot(
            marker.position.x - band.position.x,
            marker.position.z - band.position.z,
          );
          return markerRadius - band.geometry.parameters.radiusTop;
        }),
        radialOffsetsFromShell: [
          ...new Set(
            markers.map(
              (marker) => marker.userData.radial_offset_from_shell_m,
            ),
          ),
        ],
        markerRoles: [...new Set(
          markers.map(
            (marker) =>
              `${marker.userData.evidence_role}:${marker.userData.derivation}`,
          ),
        )],
        bandRoles: [...new Set(
          bands.map(
            (band) =>
              `${band.userData.evidence_role}:${band.userData.derivation}`,
          ),
        )],
        arrowRoles: [...new Set(
          arrows.map(
            (arrow) =>
              `${arrow.userData.evidence_role}:${arrow.userData.derivation}`,
          ),
        )],
        pressureText:
          document.querySelector(
            '[data-object="pressure"] .bf3d-sim-object-status',
          )?.textContent || "",
      };
    });
    assert(
      exteriorRawPressure.state.cutawayMode === "exterior" &&
        exteriorRawPressure.internalRootVisible === false &&
        exteriorRawPressure.operationalVisible === true &&
        exteriorRawPressure.state.pressure.visiblePointCount === 18,
      "18 measured pressure points remain visible in exterior mode",
      exteriorRawPressure,
    );
    assert(
      exteriorRawPressure.state.pressure.rawWithoutDeviationCount === 18 &&
        exteriorRawPressure.state.pressure.interpolatedBandCount === 0 &&
        exteriorRawPressure.state.pressure.biasArrowCount === 0 &&
        exteriorRawPressure.markerColors.length === 18 &&
        exteriorRawPressure.markerColors.every(
          (color) => color === 0xf2c94c,
        ) &&
        exteriorRawPressure.radialOffsetsFromBand.every(
          (offset) => Math.abs(offset - 0.26) < 1e-6,
        ) &&
        exteriorRawPressure.radialOffsetsFromShell.length === 1 &&
        exteriorRawPressure.radialOffsetsFromShell[0] === 0.12,
      "raw pressure uses the yellow marker identity while derived field stays hidden without deviation",
      exteriorRawPressure,
    );
    assert(
      exteriorRawPressure.operationalReviewVisibility === "hidden" &&
        exteriorRawPressure.markerRoles.join() === "measured:raw" &&
        exteriorRawPressure.bandRoles.join() ===
          "interpolated:periodic_interpolation" &&
        exteriorRawPressure.arrowRoles.join() ===
          "estimated:first_circular_moment" &&
        exteriorRawPressure.pressureText.includes("18/18") &&
        exteriorRawPressure.pressureText.includes("不生成色带"),
      "pressure evidence roles and point-count UI",
      exteriorRawPressure,
    );
    const pressureExteriorScreenshot = path.join(
      OUTPUT_ROOT,
      "chromium_1440x900_static_pressure_exterior.png",
    );
    await page
      .locator(".cad-furnace-viewer")
      .screenshot({ path: pressureExteriorScreenshot });

    await page.evaluate(() => {
      document.body.dataset.reviewMode = "material";
    });
    await page.waitForTimeout(120);
    const materialReviewPressure = await page.evaluate(() => ({
      visible: window.__BF3D_INTERNAL_SIMULATION__.viewer.scene.getObjectByName(
        "BF3D_MEAS_STATIC_PRESSURE",
      )?.visible,
      fieldVisible:
        window.__BF3D_INTERNAL_SIMULATION__.viewer.scene.getObjectByName(
          "BF3D_DERIVED_STATIC_PRESSURE_FIELD",
        )?.visible,
      state:
        window.__BF3D_INTERNAL_SIMULATION__.getState().pressure,
    }));
    assert(
      materialReviewPressure.visible === false &&
        materialReviewPressure.fieldVisible === false &&
        materialReviewPressure.state.operationalOverlayVisible === false &&
        materialReviewPressure.state.fieldOverlayVisible === false,
      "material review hides operational pressure overlay",
      materialReviewPressure,
    );
    await page.evaluate(() => {
      delete document.body.dataset.reviewMode;
    });
    await page.waitForTimeout(120);
    assert(
      await page.evaluate(
        () =>
          window.__BF3D_INTERNAL_SIMULATION__.viewer.scene.getObjectByName(
            "BF3D_MEAS_STATIC_PRESSURE",
          )?.visible === true,
      ),
      "leaving material review restores operational pressure overlay",
    );

    await page.locator('button[data-cutaway-action="cutaway"]').click();
    await page.locator('button[data-sim-action="illustrative"]').click();
    await page.waitForTimeout(900);
    const illustrative = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const state = api.getState();
      const scene = api.viewer.scene;
      return {
        state,
        pressureMarkerColors: scene
          .getObjectByName("BF3D_MEAS_STATIC_PRESSURE")
          .children.filter((item) => item.visible)
          .map((item) => item.material.color.getHex()),
        types: {
          burdenOre:
            scene.getObjectByName(
              "BF3D_EST_NEAR_SURFACE_ORE_INSTANCES",
            )?.isInstancedMesh === true,
          burdenCoke:
            scene.getObjectByName(
              "BF3D_EST_NEAR_SURFACE_COKE_INSTANCES",
            )?.isInstancedMesh === true,
          raceway:
            scene.getObjectByName(
              "BF3D_SIM_RACEWAY_INSTANCES_26",
            )?.isInstancedMesh === true,
          pci:
            scene.getObjectByName("BF3D_SIM_PCI_POINTS")?.isPoints === true,
          droplets:
            scene.getObjectByName("BF3D_SIM_DROPLETS_POINTS")?.isPoints ===
            true,
        },
        panel: {
          mode:
            document.querySelector(".bf3d-sim-mode")?.textContent || "",
          detail:
            document.querySelector(".bf3d-sim-detail")?.textContent || "",
        },
      };
    });
    const demo = illustrative.state;
    assert(
      demo.mode === "illustrative" &&
        demo.visible === true &&
        illustrative.panel.mode.includes("教学"),
      "illustrative mode visible",
      illustrative,
    );
    assert(
      demo.stock.evidence === "illustrative" &&
        demo.stock.visibleLayerCount >= 2 &&
        demo.stock.surfaceParticleCount > 100 &&
        illustrative.types.burdenOre &&
        illustrative.types.burdenCoke,
      "hybrid burden implementation",
      illustrative,
    );
    assert(
      demo.cohesive.visible === true &&
        demo.cohesive.evidence === "estimated" &&
        demo.cohesive.shape === "inverted_v" &&
        demo.cohesive.movement.forecast_height_m === 15.81 &&
        demo.cohesive.movement.forecast_15m_height_m === 15.81 &&
        demo.cohesive.confidenceVisible === true &&
        demo.cohesive.implementation === "closed_parametric_volume_shell",
      "cohesive shell contract",
      demo.cohesive,
    );
    assert(
      demo.tuyere.tuyereCount === 26 &&
        demo.tuyere.uniformIntensity === true &&
        demo.tuyere.minTuyereIntensity ===
          demo.tuyere.maxTuyereIntensity &&
        demo.tuyere.activePointsPerTuyere > 0 &&
        illustrative.types.raceway &&
        illustrative.types.pci,
      "uniform 26 tuyere response",
      demo.tuyere,
    );
    assert(
      demo.pressure.visibleMeasuredCount === 18 &&
        demo.pressure.interpolatedBandCount === 3 &&
        demo.pressure.evidence === "illustrative" &&
        illustrative.pressureMarkerColors.length === 18 &&
        illustrative.pressureMarkerColors.every(
          (color) => color === 0xf2c94c,
        ) &&
        demo.pressure.legendRange[0] === -12 &&
        demo.pressure.legendRange[1] === 12 &&
        demo.pressure.fieldLabel.includes("非煤气真实流线"),
      "illustrative pressure markers keep the yellow identity while derived field keeps its fixed legend",
      demo.pressure,
    );
    assert(
      demo.hearth.ironVisible === true &&
        demo.hearth.slagVisible === true &&
        demo.hearth.separateLiquidSurfaces === true &&
        demo.hearth.streamWidthPolicy ===
          "uniform_without_instantaneous_flow" &&
        illustrative.types.droplets,
      "hearth liquid and droplet contract",
      demo.hearth,
    );
    assert(
      demo.resources.legacyDecorativeVisibleCount === 0,
      "legacy decorative internals hidden",
      demo.resources,
    );
    assert(
      demo.stock.delivery.enabled === true &&
        demo.stock.delivery.liveMotionGate.enabled === false &&
        demo.stock.delivery.truthBoundary.illustrativeByDefault === true &&
        demo.stock.delivery.truthBoundary.noDemClaim === true &&
        demo.cohesive.whatIf.enabled === false &&
        demo.cohesive.whatIf.productionDefaultHidden === true,
      "R2N production-default gates",
      {
        delivery: demo.stock.delivery,
        cohesiveWhatIf: demo.cohesive.whatIf,
      },
    );

    await page.evaluate(() => {
      window.__BF3D_INTERNAL_SIMULATION__.dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "TEST-R2N-ILL-ORE-001",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_STARTED",
        furnace_id: "GL02",
        burden_type: "ore",
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: true,
      });
    });
    await page.waitForFunction(
      () => {
        const delivery =
          window.__BF3D_INTERNAL_SIMULATION__?.getState?.().stock
            ?.delivery;
        return (
          delivery?.active === true &&
          delivery?.particles?.activeOre > 0 &&
          delivery?.dust?.capacity > 0
        );
      },
      null,
      { timeout: 10_000 },
    );
    const r2n = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const state = api.getState();
      const scene = api.viewer.scene;
      const beforeWhatIf = state.cohesive.whatIf;
      const enabled = api.setCohesiveWhatIf(true);
      const afterWhatIf = api.getState().cohesive.whatIf;
      return {
        delivery: state.stock.delivery,
        beforeWhatIf,
        enabled,
        afterWhatIf,
        types: {
          deliveryRoot:
            scene.getObjectByName(
              "BF3D_ILL_BURDEN_DELIVERY_FX",
            )?.isGroup === true,
          chute:
            scene.getObjectByName(
              "BF3D_ILL_CHUTE_TILT_PIVOT",
            )?.isGroup === true,
          ore:
            scene.getObjectByName(
              "BF3D_ILL_FALLING_ORE_INSTANCES",
            )?.isInstancedMesh === true,
          coke:
            scene.getObjectByName(
              "BF3D_ILL_FALLING_COKE_INSTANCES",
            )?.isInstancedMesh === true,
          pores:
            scene.getObjectByName(
              "BF3D_ILL_COKE_PORE_DARK_DETAILS",
            )?.isInstancedMesh === true,
          dust:
            scene.getObjectByName(
              "BF3D_ILL_IMPACT_DUST_POINTS",
            )?.isPoints === true,
          response:
            scene.getObjectByName(
              "BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF",
            )?.isGroup === true,
        },
        hostData: {
          phase:
            api.viewer.renderer.domElement.parentElement.dataset
              .burdenChargingPhase,
          quality:
            api.viewer.renderer.domElement.parentElement.dataset
              .burdenChargingQuality,
          evidence:
            api.viewer.renderer.domElement.parentElement.dataset
              .burdenChargingEvidence,
        },
      };
    });
    assert(
      r2n.delivery.active === true &&
        r2n.delivery.evidence === "illustrative" &&
        r2n.delivery.implementation.ore === "InstancedMesh" &&
        r2n.delivery.implementation.dust === "Points" &&
        r2n.delivery.particles.activeOre > 0 &&
        Object.values(r2n.types).every(Boolean),
      "R2N chute, particles, coke pores, dust and response objects",
      r2n,
    );
    assert(
      r2n.beforeWhatIf.enabled === false &&
        r2n.enabled === true &&
        r2n.afterWhatIf.enabled === true &&
        r2n.afterWhatIf.visible === true &&
        r2n.afterWhatIf.evidence === "illustrative" &&
        r2n.afterWhatIf.causal === false,
      "R2N cohesive response is explicit non-causal what-if",
      r2n,
    );
    assert(
      ["high", "medium", "low"].includes(r2n.hostData.quality) &&
        r2n.hostData.evidence === "illustrative",
      "R2N observable host dataset",
      r2n.hostData,
    );
    await page.waitForTimeout(1800);

    const screenshot = path.join(
      OUTPUT_ROOT,
      "chromium_1440x900_r2n_burden_charging.png",
    );
    await page.screenshot({ path: screenshot, fullPage: false });
    await page.evaluate(() => {
      window.__BF3D_INTERNAL_SIMULATION__.dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "TEST-R2N-ILL-COKE-001",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_STARTED",
        furnace_id: "GL02",
        burden_type: "coke",
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: true,
      });
    });
    await page.waitForFunction(
      () =>
        window.__BF3D_INTERNAL_SIMULATION__.getState().stock.delivery
          .particles.activeCoke > 0,
      null,
      { timeout: 10_000 },
    );
    await page.waitForTimeout(1200);
    const effectsState = await page.evaluate(
      () =>
        window.__BF3D_INTERNAL_SIMULATION__.getState().stock.delivery,
    );
    assert(
      effectsState.impactCount > 0 &&
        effectsState.dust.burstCount > 0 &&
        effectsState.particles.ore.rollIntegrationSteps +
          effectsState.particles.coke.rollIntegrationSteps >
          0 &&
        effectsState.particles.visiblePoreDetails > 0,
      "R2N impact, rolling, dust and coke pore evidence",
      effectsState,
    );
    const closeupScreenshot = path.join(
      OUTPUT_ROOT,
      "chromium_1440x900_r2n_burden_closeup.png",
    );
    const focusState = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const enabled = api.setChargingFocus(true);
      return {
        enabled,
        state: api.getState(),
        visibleSensors: api.viewer.sensorObjects.filter(
          (object) => object.visible,
        ).length,
        visibleHits: api.viewer.hitObjects.filter(
          (object) => object.visible,
        ).length,
        panel:
          document.querySelector(".bf3d-sim-panel")?.dataset
            .chargingFocus || "",
        shellClass:
          document
            .querySelector(".furnace-wrap.furnace-layer-wrap")
            ?.classList.contains("bf3d-charging-focus") || false,
        calloutVisibility: getComputedStyle(
          document.querySelector(".furnace-layer-callouts"),
        ).visibility,
        controlsVisibility: getComputedStyle(
          document.querySelector(".cad-layer-controls"),
        ).visibility,
        viewerWidth:
          document
            .querySelector(".cad-furnace-viewer")
            ?.getBoundingClientRect().width || 0,
        stageWidth:
          document
            .querySelector(".furnace-stage-3d.cad-stage")
            ?.getBoundingClientRect().width || 0,
      };
    });
    assert(
      focusState.enabled === true &&
        focusState.state.chargingFocus === true &&
        focusState.visibleSensors === 0 &&
        focusState.visibleHits === 0 &&
        focusState.panel === "true" &&
        focusState.shellClass === true &&
        focusState.calloutVisibility === "hidden" &&
        focusState.controlsVisibility === "hidden" &&
        focusState.stageWidth > 0 &&
        focusState.viewerWidth / focusState.stageWidth >= 0.9,
      "R2N charging focus hides sensors and exposes state",
      focusState,
    );
    await page.waitForTimeout(240);
    await page
      .locator(".cad-furnace-viewer")
      .screenshot({ path: closeupScreenshot });
    const focusExitState = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      api.setMode("live");
      const afterLive = {
        chargingFocus: api.getState().chargingFocus,
        panel:
          document.querySelector(".bf3d-sim-panel")?.dataset
            .chargingFocus || "",
        shellClass:
          document
            .querySelector(".furnace-wrap.furnace-layer-wrap")
            ?.classList.contains("bf3d-charging-focus") || false,
      };
      api.setMode("illustrative");
      api.setChargingFocus(true);
      api.reset();
      const afterReset = {
        chargingFocus: api.getState().chargingFocus,
        panel:
          document.querySelector(".bf3d-sim-panel")?.dataset
            .chargingFocus || "",
        shellClass:
          document
            .querySelector(".furnace-wrap.furnace-layer-wrap")
            ?.classList.contains("bf3d-charging-focus") || false,
      };
      api.setMode("illustrative");
      return { afterLive, afterReset };
    });
    assert(
      focusExitState.afterLive.chargingFocus === false &&
        focusExitState.afterLive.panel === "false" &&
        focusExitState.afterLive.shellClass === false &&
        focusExitState.afterReset.chargingFocus === false &&
        focusExitState.afterReset.panel === "false" &&
        focusExitState.afterReset.shellClass === false,
      "R2N live/reset exits charging focus and restores shell UI",
      focusExitState,
    );

    const events = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const before = api.getState().stock.visibleLayerCount;
      const invalidAccepted = api.dispatchEvent({
        type: "BURDEN_CHARGE_COMPLETED",
        burden_type: "ore",
        mass_balance_valid: false,
      });
      const afterInvalid = api.getState().stock.visibleLayerCount;
      const validAccepted = api.dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "TEST-CHARGE-VALID",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_COMPLETED",
        furnace_id: "GL02",
        burden_type: "ore",
        evidence: "illustrative",
        mass_balance_valid: true,
      });
      const afterValid = api.getState().stock.visibleLayerCount;
      return {
        before,
        invalidAccepted,
        afterInvalid,
        validAccepted,
        afterValid,
      };
    });
    assert(
      events.invalidAccepted === false &&
        events.afterInvalid === events.before &&
        events.validAccepted === true &&
        events.afterValid === events.before + 1,
      "burden event and mass balance gate",
      events,
    );

    const strictEvents = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const before = api.getState().stock.visibleLayerCount;
      const event = {
        schema_version: "bf3d_event.v1",
        event_id: "TEST-R2N-IDEMPOTENT-COMPLETE",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_COMPLETED",
        furnace_id: "GL02",
        burden_type: "coke",
        evidence: "illustrative",
        mass_balance_valid: true,
      };
      const first = api.dispatchEvent(event);
      const afterFirst = api.getState().stock.visibleLayerCount;
      const duplicate = api.dispatchEvent(event);
      const afterDuplicate = api.getState().stock.visibleLayerCount;
      const wrongFurnace = api.dispatchEvent({
        ...event,
        event_id: "TEST-R2N-WRONG-FURNACE",
        furnace_id: "OTHER_FURNACE",
      });
      const afterWrongFurnace =
        api.getState().stock.visibleLayerCount;
      return {
        before,
        first,
        afterFirst,
        duplicate,
        afterDuplicate,
        wrongFurnace,
        afterWrongFurnace,
        eventGate: api.getState().eventGate,
      };
    });
    assert(
      strictEvents.first === true &&
        strictEvents.afterFirst === strictEvents.before + 1 &&
        strictEvents.duplicate === false &&
        strictEvents.afterDuplicate === strictEvents.afterFirst &&
        strictEvents.wrongFurnace === false &&
        strictEvents.afterWrongFurnace === strictEvents.afterFirst &&
        strictEvents.eventGate.duplicates >= 1,
      "strict schema, furnace and idempotency event gate",
      strictEvents,
    );

    const pooledLayers = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      for (let index = 0; index < 16; index += 1) {
        api.dispatchEvent({
          schema_version: "bf3d_event.v1",
          event_id: `TEST-R2N-POOL-${String(index).padStart(2, "0")}`,
          event_time: new Date(Date.now() + index).toISOString(),
          type: "BURDEN_CHARGE_COMPLETED",
          furnace_id: "GL02",
          burden_type: index % 2 === 0 ? "ore" : "coke",
          evidence: "illustrative",
          mass_balance_valid: true,
        });
      }
      const state = api.getState();
      const visible = [];
      api.viewer.scene.traverse((object) => {
        if (
          object.name?.startsWith("BF3D_EST_BURDEN_LAYER_") &&
          object.visible
        ) {
          visible.push({
            y: object.position.y,
            sequence: object.userData.charge_sequence,
          });
        }
      });
      return {
        currentY: state.stock.currentY,
        visibleCount: state.stock.visibleLayerCount,
        visible,
      };
    });
    const topLayerY = Math.max(
      ...pooledLayers.visible.map((item) => item.y),
    );
    assert(
      pooledLayers.visibleCount === 12 &&
        pooledLayers.visible.length === 12 &&
        Math.abs(topLayerY - (pooledLayers.currentY - 0.5)) < 0.2 &&
        new Set(
          pooledLayers.visible.map((item) => item.sequence),
        ).size === 12,
      "12-layer pool rotates and places newest charge at surface",
      pooledLayers,
    );

    const pausedFreeze = await page.evaluate(async () => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      api.dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "TEST-R2N-PAUSE-FREEZE",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_STARTED",
        furnace_id: "GL02",
        burden_type: "ore",
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: true,
      });
      api.pause();
      const before = api.getState();
      await new Promise((resolve) => setTimeout(resolve, 700));
      const after = api.getState();
      api.play();
      return {
        beforeTimeline: before.stock.delivery.timelineMs,
        afterTimeline: after.stock.delivery.timelineMs,
        beforeLayers: before.stock.visibleLayerCount,
        afterLayers: after.stock.visibleLayerCount,
        playing: after.playing,
      };
    });
    assert(
      pausedFreeze.beforeTimeline === pausedFreeze.afterTimeline &&
        pausedFreeze.beforeLayers === pausedFreeze.afterLayers &&
        pausedFreeze.playing === false,
      "pause freezes delivery clock and automatic deposition",
      pausedFreeze,
    );

    const measured = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const next = api.makeIllustrativeSnapshot();
      const now = new Date().toISOString();
      next.mode = "live";
      next.knowledge_time = now;
      next.measured.stockline.sample_time = now;
      next.measured.blast.sample_time = now;
      next.measured.blast.evidence = "measured";
      next.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.quality_state = "good";
        row.sample_time = now;
      });
      next.estimated.cohesive_zone = null;
      next.estimated.hearth_inventory = null;
      window.dispatchEvent(
        new CustomEvent("bf3d:snapshot", { detail: next }),
      );
      const state = api.getState();
      state.pressureMarkerColors = api.viewer.scene
        .getObjectByName("BF3D_MEAS_STATIC_PRESSURE")
        .children.filter((item) => item.visible)
        .map((item) => item.material.color.getHex());
      return state;
    });
    assert(
      measured.mode === "live" &&
        measured.stock.evidence === "blocked" &&
        measured.stock.delivery.active === false &&
        measured.stock.delivery.visible === false &&
        measured.cohesive.visible === false &&
        measured.cohesive.whatIf.visible === false &&
        measured.pressure.evidence === "measured" &&
        measured.pressure.visibleMeasuredCount === 18 &&
        measured.pressure.visibleGoodCount === 18 &&
        measured.pressure.interpolatedBandCount === 3 &&
        measured.pressure.biasArrowCount === 3 &&
        measured.pressureMarkerColors.length === 18 &&
        measured.pressureMarkerColors.every(
          (color) => color === 0xf2c94c,
        ) &&
        measured.tuyere.evidence === "measured" &&
        measured.hearth.liquidVisible === false,
      "measured snapshot evidence, yellow pressure-marker identity, and gates",
      measured,
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const next = api.makeIllustrativeSnapshot();
      const now = new Date().toISOString();
      next.mode = "live";
      next.knowledge_time = now;
      next.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.quality_state = "good";
        row.sample_time = now;
      });
      next.measured.static_pressure[0].quality_state = "missing";
      next.measured.static_pressure[0].value = null;
      api.injectSnapshot(next);
    });
    await page.waitForTimeout(220);
    const partialPressure = await page.evaluate(() => ({
      state: window.__BF3D_INTERNAL_SIMULATION__.getState().pressure,
      pressureText:
        document.querySelector(
          '[data-object="pressure"] .bf3d-sim-object-status',
        )?.textContent || "",
    }));
    assert(
      partialPressure.state.visiblePointCount === 17 &&
        partialPressure.state.visibleGoodCount === 17 &&
        partialPressure.state.interpolatedBandCount === 2 &&
        partialPressure.state.biasArrowCount === 2 &&
        partialPressure.pressureText.includes("17/18"),
      "a missing point hides only that point and blocks its six-point layer derivation",
      partialPressure,
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const good = api.makeIllustrativeSnapshot();
      const now = new Date().toISOString();
      good.mode = "live";
      good.knowledge_time = now;
      good.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.quality_state = "good";
        row.sample_time = now;
      });
      api.injectSnapshot(good);
      const marker = api.viewer.scene.getObjectByName(
        "BF3D_MEAS_STATIC_PRESSURE_1_A",
      );
      window.__BF3D_GOOD_PRESSURE_VALUE__ = marker.userData.value;

      const stale = api.makeIllustrativeSnapshot();
      stale.mode = "live";
      stale.knowledge_time = now;
      stale.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.quality_state = "stale";
        row.sample_time = now;
        row.value += 999;
        row.deviation_kpa += 999;
      });
      api.injectSnapshot(stale);
    });
    await page.waitForTimeout(220);
    const stalePressure = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const marker = api.viewer.scene.getObjectByName(
        "BF3D_MEAS_STATIC_PRESSURE_1_A",
      );
      return {
        state: api.getState().pressure,
        frozenValue: marker.userData.value,
        expectedValue: window.__BF3D_GOOD_PRESSURE_VALUE__,
        markerEvidenceRole: marker.userData.evidence_role,
        markerEvidenceLevel: marker.userData.evidence_level,
        markerQuality: marker.userData.quality_state,
        markerColor: marker.material.color.getHex(),
        pressureText:
          document.querySelector(
            '[data-object="pressure"] .bf3d-sim-object-status',
          )?.textContent || "",
      };
    });
    assert(
      stalePressure.state.visiblePointCount === 18 &&
        stalePressure.state.visibleGoodCount === 0 &&
        stalePressure.state.visibleStaleCount === 18 &&
        stalePressure.state.interpolatedBandCount === 0 &&
        stalePressure.state.biasArrowCount === 0 &&
        stalePressure.frozenValue === stalePressure.expectedValue &&
        stalePressure.markerEvidenceRole === "measured" &&
        stalePressure.markerEvidenceLevel === "stale" &&
        stalePressure.markerQuality === "stale" &&
        stalePressure.markerColor === 0x8f7728 &&
        stalePressure.pressureText.includes("陈旧冻结"),
      "stale pressure freezes the last good value, uses dark yellow, and suppresses derived fields",
      stalePressure,
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const socket = window.__BF3D_TEST_WEBSOCKETS__.find(
        (item) => item.readyState === 1,
      );
      const next = api.makeIllustrativeSnapshot();
      const now = new Date().toISOString();
      next.mode = "live";
      next.render_time = now;
      next.knowledge_time = now;
      next.measured.stockline.sample_time = now;
      next.measured.blast.sample_time = now;
      next.measured.blast.evidence = "measured";
      next.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.sample_time = now;
      });
      next.estimated.cohesive_zone = {
        status: "available",
        centerHeight: 18.35,
        thickness: 2.4,
        innerRadius: 0.82,
        outerRadius: 4.08,
        eccentricity: 0.31,
        eccentricAngle: 0.72,
        amplitude: 2.05,
        uncertainty: 0.48,
        shape: "eccentric",
        evidence: "estimated",
        movement: {
          direction: "up",
          velocity_m_per_h: 0.42,
          forecast_horizon_minutes: 15,
          forecast_height_m: 18.53,
          forecast_assumption: "constant_velocity_uncalibrated",
        },
        confidence: 0.42,
        input_coverage: 0.875,
        calibration_status: "uncalibrated",
        control_use: "prohibited",
        root_definition: "wall_thermal_activity_centroid",
        azimuth_reference: "sensor_relative_A_zero",
        absolute_azimuth_status: "unconfirmed",
        sample_time: now,
        quality: { state: "good", warnings: [] },
        model_version: "C2-ROOT-MOTION-V1",
      };
      next.estimated.hearth_inventory = null;
      window.__BF3D_TEST_SNAPSHOT_EVENT_COUNT__ = 0;
      window.addEventListener("bf3d:snapshot", () => {
        window.__BF3D_TEST_SNAPSHOT_EVENT_COUNT__ += 1;
      });
      socket.emitMessage({
        type: "init",
        timestamp: now,
        history: { timestamps: [now] },
        bf3d_snapshot: next,
      });
    });
    await page.waitForFunction(
      () =>
        window.__BF3D_LATEST_SNAPSHOT__?.estimated?.cohesive_zone
          ?.model_version === "C2-ROOT-MOTION-V1" &&
        window.__BF3D_INTERNAL_SIMULATION__?.getState?.().cohesive
          ?.visible === true,
      null,
      { timeout: 10_000 },
    );
    await page.waitForTimeout(450);
    const liveC2 = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const state = api.getState();
      const host = api.viewer.renderer.domElement.parentElement;
      return {
        state: state.cohesive,
        cacheModel:
          window.__BF3D_LATEST_SNAPSHOT__.estimated.cohesive_zone
            .model_version,
        cacheConfidence:
          window.__BF3D_LATEST_SNAPSHOT__.estimated.cohesive_zone
            .confidence,
        eventCount: window.__BF3D_TEST_SNAPSHOT_EVENT_COUNT__,
        status:
          document.querySelector(
            '[data-object="cohesive"] .bf3d-sim-object-status',
          )?.textContent || "",
        host: {
          visible: host.dataset.cohesiveVisible,
          direction: host.dataset.cohesiveDirection,
          velocity: host.dataset.cohesiveVelocityMPerH,
          rootHeight: host.dataset.cohesiveRootHeightM,
          thickness: host.dataset.cohesiveThicknessM,
          confidence: host.dataset.cohesiveConfidence,
          inputCoverage: host.dataset.cohesiveInputCoverage,
          calibration: host.dataset.cohesiveCalibrationStatus,
          controlUse: host.dataset.cohesiveControlUse,
          rootDefinition: host.dataset.cohesiveRootDefinition,
          azimuthReference: host.dataset.cohesiveAzimuthReference,
          absoluteAzimuthStatus:
            host.dataset.cohesiveAbsoluteAzimuthStatus,
          sampleTime: host.dataset.cohesiveSampleTime,
          quality: host.dataset.cohesiveQuality,
          freshness: host.dataset.cohesiveFreshness,
          modelVersion: host.dataset.cohesiveModelVersion,
          contractState: host.dataset.cohesiveContractState,
          contractIssues: host.dataset.cohesiveContractIssues,
        },
      };
    });
    assert(
      liveC2.cacheConfidence <= 0.45,
      "live C2 fixture respects uncalibrated confidence ceiling",
      liveC2.cacheConfidence,
    );
    assert(
      liveC2.cacheModel === "C2-ROOT-MOTION-V1" &&
        liveC2.eventCount === 1 &&
        liveC2.state.visible === true &&
        liveC2.state.evidence === "estimated" &&
        liveC2.state.movement.direction === "up" &&
        liveC2.state.movement.velocity_m_per_h === 0.42 &&
        liveC2.state.movement.forecast_height_m === 18.53 &&
        liveC2.state.movement.forecast_15m_height_m === 18.53 &&
        liveC2.state.confidence === 0.42 &&
        liveC2.state.inputCoverage === 0.875 &&
        liveC2.state.input_coverage === 0.875 &&
        liveC2.state.calibrationStatus === "uncalibrated" &&
        liveC2.state.calibration_status === "uncalibrated" &&
        liveC2.state.controlUse === "prohibited" &&
        liveC2.state.control_use === "prohibited" &&
        liveC2.state.rootDefinition ===
          "wall_thermal_activity_centroid" &&
        liveC2.state.root_definition ===
          "wall_thermal_activity_centroid" &&
        liveC2.state.azimuthReference ===
          "sensor_relative_A_zero" &&
        liveC2.state.azimuth_reference ===
          "sensor_relative_A_zero" &&
        liveC2.state.absoluteAzimuthStatus === "unconfirmed" &&
        liveC2.state.absolute_azimuth_status === "unconfirmed" &&
        liveC2.state.modelVersion === "C2-ROOT-MOTION-V1" &&
        liveC2.state.model_version === "C2-ROOT-MOTION-V1" &&
        liveC2.state.sample_time === liveC2.state.sampleTime &&
        liveC2.state.quality.state === "good" &&
        liveC2.state.freshness === "good" &&
        liveC2.state.contract.state === "valid" &&
        liveC2.state.whatIf.visible === false,
      "live C2 snapshot metadata and WebSocket cache publication",
      liveC2,
    );
    assert(
      liveC2.status.includes("↑上移") &&
        liveC2.status.includes("未标定估计") &&
        liveC2.status.includes("禁止控制") &&
        liveC2.status.includes("根部 18.35m") &&
        liveC2.status.includes("厚度 ") &&
        liveC2.status.includes("置信度 42%") &&
        liveC2.host.visible === "true" &&
        liveC2.host.direction === "up" &&
        liveC2.host.velocity === "0.420" &&
        liveC2.host.rootHeight === "18.350" &&
        Number(liveC2.host.thickness) > 2.2 &&
        Number(liveC2.host.thickness) <= 2.4 &&
        liveC2.host.confidence === "0.420" &&
        liveC2.host.inputCoverage === "0.875" &&
        liveC2.host.calibration === "uncalibrated" &&
        liveC2.host.controlUse === "prohibited" &&
        liveC2.host.rootDefinition ===
          "wall_thermal_activity_centroid" &&
        liveC2.host.azimuthReference ===
          "sensor_relative_A_zero" &&
        liveC2.host.absoluteAzimuthStatus === "unconfirmed" &&
        liveC2.host.quality === "good" &&
        liveC2.host.freshness === "good" &&
        liveC2.host.modelVersion === "C2-ROOT-MOTION-V1" &&
        liveC2.host.contractState === "valid" &&
        liveC2.host.contractIssues === "",
      "live C2 status line and stable host attributes",
      liveC2,
    );
    const c2Screenshot = path.join(
      OUTPUT_ROOT,
      "chromium_1440x900_c2_root_prediction.png",
    );
    await page.screenshot({
      path: c2Screenshot,
      fullPage: false,
    });

    await page.evaluate(() => {
      const socket = window.__BF3D_TEST_WEBSOCKETS__.find(
        (item) => item.readyState === 1,
      );
      const next = structuredClone(window.__BF3D_LATEST_SNAPSHOT__);
      const now = new Date().toISOString();
      next.render_time = now;
      next.knowledge_time = now;
      next.estimated.cohesive_zone.sample_time = now;
      next.estimated.cohesive_zone.confidence = 0.9;
      next.estimated.cohesive_zone.calibration_status = "calibrated";
      next.estimated.cohesive_zone.control_use = "allowed";
      socket.emitMessage({
        type: "tick",
        timestamp: now,
        values: {},
        bf3d_snapshot: next,
      });
    });
    await page.waitForFunction(
      () =>
        window.__BF3D_INTERNAL_SIMULATION__?.getState?.().cohesive
          ?.contract?.state === "invalid",
      null,
      { timeout: 10_000 },
    );
    const invalidC2 = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const state = api.getState().cohesive;
      const host = api.viewer.renderer.domElement.parentElement;
      return {
        state,
        status:
          document.querySelector(
            '[data-object="cohesive"] .bf3d-sim-object-status',
          )?.textContent || "",
        contractState: host.dataset.cohesiveContractState,
        contractIssues: host.dataset.cohesiveContractIssues,
      };
    });
    assert(
      invalidC2.state.visible === false &&
        invalidC2.state.contract.state === "invalid" &&
        invalidC2.state.contract.issues.includes(
          "confidence:out_of_range",
        ) &&
        invalidC2.state.contract.issues.includes(
          "calibration_status:not_uncalibrated",
        ) &&
        invalidC2.state.contract.issues.includes(
          "control_use:not_prohibited",
        ) &&
        invalidC2.status.includes("C2 输出合同无效") &&
        invalidC2.contractState === "invalid",
      "unsafe C2 snapshot is rejected independently by the frontend",
      invalidC2,
    );

    await page.evaluate(() => {
      const socket = window.__BF3D_TEST_WEBSOCKETS__.find(
        (item) => item.readyState === 1,
      );
      const next = structuredClone(window.__BF3D_LATEST_SNAPSHOT__);
      const now = new Date().toISOString();
      next.render_time = now;
      next.knowledge_time = now;
      next.estimated.cohesive_zone.sample_time = now;
      next.estimated.cohesive_zone.confidence = 0.42;
      next.estimated.cohesive_zone.calibration_status = "uncalibrated";
      next.estimated.cohesive_zone.control_use = "prohibited";
      socket.emitMessage({
        type: "tick",
        timestamp: now,
        values: {},
        bf3d_snapshot: next,
      });
    });
    await page.waitForFunction(
      () => {
        const state =
          window.__BF3D_INTERNAL_SIMULATION__?.getState?.().cohesive;
        return state?.visible === true && state?.contract?.state === "valid";
      },
      null,
      { timeout: 10_000 },
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const socket = window.__BF3D_TEST_WEBSOCKETS__.find(
        (item) => item.readyState === 1,
      );
      const next = structuredClone(window.__BF3D_LATEST_SNAPSHOT__);
      const staleTime = new Date(
        Date.now() - api.config.freshness.sensor_warn_after_ms - 1000,
      ).toISOString();
      next.render_time = new Date().toISOString();
      next.knowledge_time = staleTime;
      next.estimated.cohesive_zone.sample_time = staleTime;
      next.estimated.cohesive_zone.movement = {
        direction: "down",
        velocity_m_per_h: -0.28,
        forecast_horizon_minutes: 15,
        forecast_height_m: 18.28,
        forecast_assumption: "constant_velocity_uncalibrated",
      };
      socket.emitMessage({
        type: "tick",
        timestamp: staleTime,
        values: {},
        bf3d_snapshot: next,
      });
    });
    await page.waitForFunction(
      () => {
        const state =
          window.__BF3D_INTERNAL_SIMULATION__?.getState?.().cohesive;
        return (
          state?.visible === true &&
          state?.freshness === "stale" &&
          state?.movement?.direction === "down"
        );
      },
      null,
      { timeout: 10_000 },
    );
    const staleC2 = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const host = api.viewer.renderer.domElement.parentElement;
      return {
        state: api.getState().cohesive,
        status:
          document.querySelector(
            '[data-object="cohesive"] .bf3d-sim-object-status',
          )?.textContent || "",
        hostQuality: host.dataset.cohesiveQuality,
        hostFreshness: host.dataset.cohesiveFreshness,
      };
    });
    assert(
      staleC2.state.visible === true &&
        staleC2.state.quality.state === "stale" &&
        staleC2.state.freshness === "stale" &&
        staleC2.status.includes("↓下移") &&
        staleC2.hostQuality === "stale" &&
        staleC2.hostFreshness === "stale",
      "stale C2 snapshot remains visible and is labelled stale",
      staleC2,
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const socket = window.__BF3D_TEST_WEBSOCKETS__.find(
        (item) => item.readyState === 1,
      );
      window.__BF3D_TEST_ORIGINAL_FRESHNESS__ = {
        warn: api.config.freshness.sensor_warn_after_ms,
        hard: api.config.freshness.sensor_hard_expire_after_ms,
      };
      api.config.freshness.sensor_warn_after_ms = 80;
      api.config.freshness.sensor_hard_expire_after_ms = 220;
      const next = structuredClone(window.__BF3D_LATEST_SNAPSHOT__);
      const now = new Date().toISOString();
      next.render_time = now;
      next.knowledge_time = now;
      next.estimated.cohesive_zone.sample_time = now;
      next.estimated.cohesive_zone.movement = {
        direction: "stable",
        velocity_m_per_h: 0.01,
        forecast_horizon_minutes: 15,
        forecast_height_m: 18.35,
        forecast_assumption: "constant_velocity_uncalibrated",
      };
      socket.emitMessage({
        type: "tick",
        timestamp: now,
        values: {},
        bf3d_snapshot: next,
      });
    });
    await page.waitForFunction(
      () => {
        const api = window.__BF3D_INTERNAL_SIMULATION__;
        const host = api?.viewer?.renderer?.domElement?.parentElement;
        return (
          api?.getState?.().cohesive?.visible === false &&
          host?.dataset?.cohesiveVisible === "false" &&
          document
            .querySelector(
              '[data-object="cohesive"] .bf3d-sim-object-status',
            )
            ?.textContent?.includes("已隐藏")
        );
      },
      null,
      { timeout: 5_000 },
    );
    const autoHardExpiredC2 = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const host = api.viewer.renderer.domElement.parentElement;
      return {
        state: api.getState().cohesive,
        status:
          document.querySelector(
            '[data-object="cohesive"] .bf3d-sim-object-status',
          )?.textContent || "",
        hostVisible: host.dataset.cohesiveVisible,
        hostFreshness: host.dataset.cohesiveFreshness,
      };
    });
    assert(
      autoHardExpiredC2.state.visible === false &&
        autoHardExpiredC2.state.freshness === "no-data" &&
        autoHardExpiredC2.status.includes("已隐藏") &&
        autoHardExpiredC2.hostVisible === "false" &&
        autoHardExpiredC2.hostFreshness === "no-data",
      "injected C2 snapshot automatically hard-expires",
      autoHardExpiredC2,
    );

    await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const socket = window.__BF3D_TEST_WEBSOCKETS__.find(
        (item) => item.readyState === 1,
      );
      const original = window.__BF3D_TEST_ORIGINAL_FRESHNESS__;
      api.config.freshness.sensor_warn_after_ms = original.warn;
      api.config.freshness.sensor_hard_expire_after_ms = original.hard;
      const next = structuredClone(window.__BF3D_LATEST_SNAPSHOT__);
      const now = new Date().toISOString();
      next.render_time = now;
      next.knowledge_time = now;
      next.estimated.cohesive_zone.sample_time = now;
      next.estimated.cohesive_zone.movement = {
        direction: "stable",
        velocity_m_per_h: 0.01,
        forecast_horizon_minutes: 15,
        forecast_height_m: 18.35,
        forecast_assumption: "constant_velocity_uncalibrated",
      };
      socket.emitMessage({
        type: "tick",
        timestamp: now,
        values: {},
        bf3d_snapshot: next,
      });
    });
    await page.waitForFunction(
      () => {
        const state =
          window.__BF3D_INTERNAL_SIMULATION__?.getState?.().cohesive;
        return (
          state?.visible === true &&
          state?.freshness === "good" &&
          state?.movement?.direction === "stable"
        );
      },
      null,
      { timeout: 10_000 },
    );
    const recoveredC2 = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      return {
        state: api.getState().cohesive,
        status:
          document.querySelector(
            '[data-object="cohesive"] .bf3d-sim-object-status',
          )?.textContent || "",
      };
    });
    assert(
      recoveredC2.state.visible === true &&
        recoveredC2.state.freshness === "good" &&
        recoveredC2.state.modelVersion === "C2-ROOT-MOTION-V1" &&
        recoveredC2.status.includes("→稳定"),
      "fresh C2 snapshot recovers after hard expiry",
      recoveredC2,
    );

    const liveMotionGate = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const before = api.getState().stock.delivery;
      const measuredAccepted = api.dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "TEST-R2N-LIVE-BLOCKED-001",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_STARTED",
        furnace_id: "GL02",
        burden_type: "coke",
        evidence: "measured",
        mass_balance_valid: true,
        visualize_motion: true,
        motion_parameters_valid: true,
        chute_azimuth_deg: 90,
        chute_tilt_deg: 34,
      });
      const gateAfterMeasured = api.getState().eventGate;
      const illustrativeAccepted = api.dispatchEvent({
        schema_version: "bf3d_event.v1",
        event_id: "TEST-R2N-LIVE-ILLUSTRATIVE-BLOCKED",
        event_time: new Date().toISOString(),
        type: "BURDEN_CHARGE_STARTED",
        furnace_id: "GL02",
        burden_type: "ore",
        evidence: "illustrative",
        mass_balance_valid: true,
        visualize_motion: true,
      });
      const after = api.getState().stock.delivery;
      return {
        before,
        after,
        measuredAccepted,
        illustrativeAccepted,
        gateAfterMeasured,
        eventGate: api.getState().eventGate,
      };
    });
    assert(
      liveMotionGate.measuredAccepted === false &&
        liveMotionGate.illustrativeAccepted === false &&
        liveMotionGate.after.active === false &&
        liveMotionGate.after.rejectedPrograms ===
          liveMotionGate.before.rejectedPrograms &&
        liveMotionGate.gateAfterMeasured.lastReason.includes("门禁") &&
        liveMotionGate.eventGate.lastReason.includes("证据"),
      "live burden motion remains blocked without source freeze",
      liveMotionGate,
    );

    const hardExpired = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const next = api.makeIllustrativeSnapshot();
      const old = new Date(
        Date.now() - api.config.freshness.sensor_hard_expire_after_ms - 1000,
      ).toISOString();
      next.mode = "live";
      next.knowledge_time = old;
      next.measured.stockline.sample_time = old;
      next.measured.blast.sample_time = old;
      next.measured.static_pressure.forEach((row) => {
        row.evidence = "measured";
        row.quality_state = "good";
        row.sample_time = old;
      });
      next.estimated.cohesive_zone = null;
      next.estimated.hearth_inventory = null;
      api.injectSnapshot(next);
      return api.getState();
    });
    assert(
      hardExpired.tuyere.evidence === "no-data" &&
        hardExpired.pressure.visibleMeasuredCount === 0 &&
        hardExpired.pressure.interpolatedBandCount === 0 &&
        hardExpired.pressure.biasArrowCount === 0 &&
        hardExpired.cohesive.visible === false &&
        hardExpired.hearth.liquidVisible === false,
      "hard expiry hides static pressure points, inferred fields and effects",
      hardExpired,
    );

    const resourceReuse = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const before = api.getState().resources;
      for (let index = 0; index < 50; index += 1) {
        api.setMode(index % 2 === 0 ? "illustrative" : "live");
      }
      const after = api.getState().resources;
      const panelCount = document.querySelectorAll(".bf3d-sim-panel").length;
      const rootCount = api.viewer.scene.children.filter(
        (object) => object.name === "BF3D_INTERNAL_SIMULATION_RUNTIME",
      ).length;
      const pressureOverlayCount = api.viewer.scene.children.filter(
        (object) => object.name === "BF3D_MEAS_STATIC_PRESSURE",
      ).length;
      return {
        before,
        after,
        panelCount,
        rootCount,
        pressureOverlayCount,
      };
    });
    for (const field of [
      "rootChildren",
      "legacyDecorativeCount",
      "burdenLayerPool",
      "burdenDeliveryParticleCapacity",
      "burdenDeliveryDustCapacity",
      "tuyereInstances",
      "pciPointCapacity",
      "pressureMarkers",
      "pressureBands",
      "dropletPointCount",
    ]) {
      assert(
        resourceReuse.before[field] === resourceReuse.after[field],
        `resource reuse ${field}`,
        resourceReuse,
      );
    }
    assert(
      resourceReuse.panelCount === 1 &&
        resourceReuse.rootCount === 1 &&
        resourceReuse.pressureOverlayCount === 1,
      "single controller lifecycle",
      resourceReuse,
    );

    const disposedState = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      const viewer = api.viewer;
      api.dispose();
      return {
        globalPresent: Boolean(window.__BF3D_INTERNAL_SIMULATION__),
        viewerApiPresent: Boolean(viewer.__bf3dInternalSimulation),
        getterPresent:
          typeof viewer.getInternalSimulationState === "function",
        modeSetterPresent:
          typeof viewer.setInternalSimulationMode === "function",
        panelCount:
          document.querySelectorAll(".bf3d-sim-panel").length,
        rootCount: viewer.scene.children.filter(
          (object) =>
            object.name === "BF3D_INTERNAL_SIMULATION_RUNTIME",
        ).length,
        pressureOverlayCount: viewer.scene.children.filter(
          (object) => object.name === "BF3D_MEAS_STATIC_PRESSURE",
        ).length,
      };
    });
    assert(
      disposedState.globalPresent === false &&
        disposedState.viewerApiPresent === false &&
        disposedState.getterPresent === false &&
        disposedState.modeSetterPresent === false &&
        disposedState.panelCount === 0 &&
        disposedState.rootCount === 0 &&
        disposedState.pressureOverlayCount === 0,
      "dispose removes runtime, panel and viewer API closures",
      disposedState,
    );
    await page.waitForFunction(
      () =>
        window.__BF3D_INTERNAL_SIMULATION__?.getState?.().ready ===
        true,
      null,
      { timeout: 10_000 },
    );
    const remountedState = await page.evaluate(() => {
      const api = window.__BF3D_INTERNAL_SIMULATION__;
      return {
        panelCount:
          document.querySelectorAll(".bf3d-sim-panel").length,
        rootCount: api.viewer.scene.children.filter(
          (object) =>
            object.name === "BF3D_INTERNAL_SIMULATION_RUNTIME",
        ).length,
        pressureOverlayCount: api.viewer.scene.children.filter(
          (object) => object.name === "BF3D_MEAS_STATIC_PRESSURE",
        ).length,
        viewerApiPresent:
          api.viewer.__bf3dInternalSimulation === api,
        ready: api.getState().ready,
        cohesiveVisible: api.getState().cohesive.visible,
        cohesiveModelVersion:
          api.getState().cohesive.modelVersion,
      };
    });
    assert(
      remountedState.ready === true &&
        remountedState.panelCount === 1 &&
        remountedState.rootCount === 1 &&
        remountedState.pressureOverlayCount === 1 &&
        remountedState.viewerApiPresent === true &&
        remountedState.cohesiveVisible === true &&
        remountedState.cohesiveModelVersion ===
          "C2-ROOT-MOTION-V1",
      "same connected viewer remounts from latest cached C2 snapshot",
      remountedState,
    );

    const layout = await page.evaluate(() => {
      const panel = document
        .querySelector(".bf3d-sim-panel")
        ?.getBoundingClientRect();
      return {
        viewport: {
          width: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        },
        panel: panel
          ? {
              left: panel.left,
              right: panel.right,
              top: panel.top,
              bottom: panel.bottom,
            }
          : null,
      };
    });
    assert(
      layout.viewport.scrollWidth <= layout.viewport.width &&
        layout.panel &&
        layout.panel.left >= 0 &&
        layout.panel.right <= layout.viewport.width,
      "no horizontal overflow",
      layout,
    );

    const hasExpectedOfflineResponse = httpErrors.some((entry) => {
      const pathname = new URL(entry.url).pathname;
      return (
        pathname.startsWith("/api/automation/") ||
        pathname.startsWith("/api/short-window/")
      );
    });
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) =>
        !expectedOffline(message) &&
        !(
          hasExpectedOfflineResponse &&
          message.includes("Failed to load resource:")
        ),
    );
    const unexpectedHttpErrors = httpErrors.filter((entry) => {
      const pathname = new URL(entry.url).pathname;
      return (
        !pathname.startsWith("/api/automation/") &&
        !pathname.startsWith("/api/short-window/") &&
        !pathname.endsWith("/favicon.ico")
      );
    });
    assert(pageErrors.length === 0, "page errors", pageErrors);
    assert(
      unexpectedConsoleErrors.length === 0,
      "console errors",
      unexpectedConsoleErrors,
    );
    assert(
      unexpectedHttpErrors.length === 0,
      "HTTP errors",
      unexpectedHttpErrors,
    );

    const report = {
      ok: true,
      requirement: "REQ-BF3D-INTERNAL-RUNTIME-6X-20260719",
      url,
      initial,
      illustrative,
      events,
      measured,
      liveC2,
      invalidC2,
      staleC2,
      autoHardExpiredC2,
      recoveredC2,
      hardExpired,
      resourceReuse,
      layout,
      pressureExteriorScreenshot,
      screenshot,
      c2Screenshot,
      closeupScreenshot,
      pageErrors,
      consoleErrors: unexpectedConsoleErrors,
      httpErrors: unexpectedHttpErrors,
      ignoredOfflineConsoleErrors: consoleErrors.filter((message) =>
        expectedOffline(message),
      ),
    };
    fs.writeFileSync(
      path.join(OUTPUT_ROOT, "runtime_contract_report.json"),
      JSON.stringify(report, null, 2),
      "utf8",
    );
    process.stdout.write(
      `${JSON.stringify(
        {
          ok: report.ok,
          requirement: report.requirement,
          screenshot: report.screenshot,
          pressureExteriorScreenshot,
          initialMode: initial.mode,
          demoPressurePoints: demo.pressure.visibleMeasuredCount,
          demoTuyeres: demo.tuyere.tuyereCount,
          liveC2: {
            modelVersion: liveC2.state.modelVersion,
            direction: liveC2.state.movement.direction,
            confidence: liveC2.state.confidence,
            hardExpired: !autoHardExpiredC2.state.visible,
            recovered: recoveredC2.state.visible,
            screenshot: c2Screenshot,
          },
          eventGate: events,
          resourceReuse,
        },
        null,
        2,
      )}\n`,
    );
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
