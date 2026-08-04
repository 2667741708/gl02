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
  "bf3d_c2_cross_engine_20260719",
);
const VIEWPORTS = [
  [1920, 1080],
  [1366, 768],
  [768, 1024],
  [390, 844],
];
const ENGINES = ["chromium", "firefox", "webkit"];
const REPRESENTATIVE_SCREENSHOT_VIEWPORT = "1366x768";
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
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
              history: {
                timestamps: ["2026-07-19T00:00:00.000Z"],
              },
              data_quality: { state: "test" },
              source: "bf3d-c2-cross-engine-contract",
              server: "local",
              interval_seconds: 60,
              aggregate: "mean",
            }),
          );
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

function isExpectedOffline(text) {
  return (
    text.includes("127.0.0.1:8767") ||
    text.includes("/api/automation/") ||
    text.includes("/api/short-window/") ||
    text.includes("/api/qa/") ||
    text.includes("/api/ollama/") ||
    text.includes("ERR_CONNECTION_REFUSED") ||
    text.includes("Failed to fetch") ||
    text.includes("[BABEL] Note:")
  );
}

function isExpectedOfflineResponse(entry) {
  const pathname = new URL(entry.url).pathname;
  return (
    pathname.startsWith("/api/automation/") ||
    pathname.startsWith("/api/short-window/") ||
    pathname.startsWith("/api/qa/") ||
    pathname.startsWith("/api/ollama/") ||
    pathname.endsWith("/favicon.ico")
  );
}

async function installWebSocketContractStub(page) {
  await page.addInitScript(() => {
    class C2ContractWebSocket extends EventTarget {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      constructor(url, protocols) {
        super();
        this.url = String(url || "");
        this.protocols = protocols;
        this.readyState = C2ContractWebSocket.CONNECTING;
        this.sent = [];
        this.binaryType = "blob";
        this.bufferedAmount = 0;
        this.extensions = "";
        this.protocol = "";
        window.__BF3D_C2_TEST_WEBSOCKETS__ =
          window.__BF3D_C2_TEST_WEBSOCKETS__ || [];
        window.__BF3D_C2_TEST_WEBSOCKETS__.push(this);
        setTimeout(() => {
          if (this.readyState !== C2ContractWebSocket.CONNECTING) return;
          this.readyState = C2ContractWebSocket.OPEN;
          const event = new Event("open");
          this.dispatchEvent(event);
          if (typeof this.onopen === "function") this.onopen(event);
        }, 0);
      }

      send(value) {
        this.sent.push(value);
      }

      close() {
        if (this.readyState === C2ContractWebSocket.CLOSED) return;
        this.readyState = C2ContractWebSocket.CLOSED;
        const event = new CloseEvent("close");
        this.dispatchEvent(event);
        if (typeof this.onclose === "function") this.onclose(event);
      }

      emitMessage(value) {
        const event = new MessageEvent("message", {
          data:
            typeof value === "string" ? value : JSON.stringify(value),
        });
        this.dispatchEvent(event);
        if (typeof this.onmessage === "function") this.onmessage(event);
      }
    }
    window.WebSocket = C2ContractWebSocket;
  });
}

async function ensureSimulationPanelExpanded(page) {
  const body = page.locator(".bf3d-sim-body");
  if (!(await body.isVisible())) {
    await page.locator(".bf3d-sim-collapse").click();
    await body.waitFor({ state: "visible", timeout: 10_000 });
  }
}

async function injectC2Snapshot(page) {
  return page.evaluate(() => {
    const now = new Date().toISOString();
    const snapshot = {
      schema_version: "bf3d_snapshot.v1",
      furnace_id: "GL02",
      mode: "live",
      render_time: now,
      knowledge_time: now,
      measured: {
        stockline: {
          L: null,
          L_south: null,
          L_north: null,
          sample_time: now,
          evidence: "measured",
        },
        static_pressure: [],
        blast: {
          Q_blast: null,
          O2_rate: null,
          PCI_rate: null,
          sample_time: now,
          evidence: "measured",
        },
        active_tap: null,
      },
      estimated: {
        burden_state: null,
        cohesive_zone: {
          status: "available",
          centerHeight: 18.35,
          rootHeight: 18.35,
          thickness: 2.3,
          innerRadius: 0.9,
          outerRadius: 3.82,
          eccentricity: 0.28,
          eccentricAngle: 0.52,
          amplitude: 2.15,
          uncertainty: 0.58,
          shape: "inverted_v",
          evidence: "estimated",
          model_version: "C2-ROOT-BASELINE-2026.07",
          scene_version: "BF3D-C2-CROSS-ENGINE-20260719",
          movement: {
            direction: "up",
            velocity_m_per_h: 0.36,
            forecast_horizon_minutes: 15,
            forecast_height_m: 18.44,
            forecast_assumption: "constant_velocity_uncalibrated",
          },
          confidence: 0.42,
          input_coverage: 0.88,
          calibration_status: "uncalibrated",
          control_use: "prohibited",
          root_definition: "wall_thermal_activity_centroid",
          azimuth_reference: "sensor_relative_A_zero",
          absolute_azimuth_status: "unconfirmed",
          sample_time: now,
          quality: {
            state: "good",
            warnings: [
              "未通过炉内直接测量标定，仅用于可视化和工艺研判。",
            ],
          },
        },
        hearth_inventory: null,
      },
      quality: {
        state: "good",
        missing: [],
        stale: [],
        bad: [],
        warnings: [],
      },
    };
    window.__BF3D_LATEST_SNAPSHOT__ = snapshot;
    window.dispatchEvent(
      new CustomEvent("bf3d:snapshot", { detail: snapshot }),
    );
    return snapshot;
  });
}

async function inspectC2(page) {
  return page.evaluate(() => {
    const api = window.__BF3D_INTERNAL_SIMULATION__;
    const state = api.getState();
    const host =
      document.querySelector(".cad-furnace-viewer") ||
      api.viewer.renderer.domElement.parentElement;
    const panel = document.querySelector(".bf3d-sim-panel");
    const panelBody = document.querySelector(".bf3d-sim-body");
    const cohesiveRow = document.querySelector(
      '.bf3d-sim-object-row[data-object="cohesive"]',
    );
    const cohesiveStatus = cohesiveRow?.querySelector(
      ".bf3d-sim-object-status",
    );
    const cutawayButton = document.querySelector(
      'button[data-cutaway-action="cutaway"]',
    );
    const shell = api.viewer.scene.getObjectByName(
      "BF3D_EST_COHESIVE_ZONE_SHELL",
    );
    const cohesiveGroup = api.viewer.scene.getObjectByName(
      "BF3D_EST_COHESIVE_ZONE",
    );
    const whatIf = api.viewer.scene.getObjectByName(
      "BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF",
    );
    const rect = (element) => {
      if (!element) return null;
      const value = element.getBoundingClientRect();
      return {
        left: value.left,
        right: value.right,
        top: value.top,
        bottom: value.bottom,
        width: value.width,
        height: value.height,
      };
    };
    const isTopHit = (element) => {
      if (!element) return false;
      const value = element.getBoundingClientRect();
      const x = Math.max(
        0,
        Math.min(innerWidth - 1, value.left + value.width / 2),
      );
      const y = Math.max(
        0,
        Math.min(innerHeight - 1, value.top + value.height / 2),
      );
      const hit = document.elementFromPoint(x, y);
      return Boolean(hit && (hit === element || element.contains(hit)));
    };
    const isEffectivelyVisible = (object) => {
      if (!object || object.visible !== true) return false;
      let current = object.parent;
      while (current) {
        if (current.visible === false) return false;
        current = current.parent;
      }
      return true;
    };
    const root = document.documentElement;
    const body = document.body;
    return {
      state: {
        mode: state.mode,
        cutawayMode: state.cutawayMode,
        visible: state.visible,
        cohesive: state.cohesive,
      },
      status: cohesiveStatus?.textContent?.trim() || "",
      evidenceLabel:
        cohesiveRow
          ?.querySelector(".bf3d-sim-evidence")
          ?.textContent?.trim() || "",
      attributes: {
        cohesiveWhatIf: host?.dataset.cohesiveWhatIf || "",
        cohesiveVisible: host?.dataset.cohesiveVisible || "",
        cohesiveEvidence: host?.dataset.cohesiveEvidence || "",
        cohesiveDirection: host?.dataset.cohesiveDirection || "",
        cohesiveVelocityMPerH:
          host?.dataset.cohesiveVelocityMPerH || "",
        cohesiveRootHeightM:
          host?.dataset.cohesiveRootHeightM || "",
        cohesiveThicknessM:
          host?.dataset.cohesiveThicknessM || "",
        cohesiveEccentricityM:
          host?.dataset.cohesiveEccentricityM || "",
        cohesiveConfidence:
          host?.dataset.cohesiveConfidence || "",
        cohesiveInputCoverage:
          host?.dataset.cohesiveInputCoverage || "",
        cohesiveCalibrationStatus:
          host?.dataset.cohesiveCalibrationStatus || "",
        cohesiveControlUse:
          host?.dataset.cohesiveControlUse || "",
        cohesiveRootDefinition:
          host?.dataset.cohesiveRootDefinition || "",
        cohesiveAzimuthReference:
          host?.dataset.cohesiveAzimuthReference || "",
        cohesiveAbsoluteAzimuthStatus:
          host?.dataset.cohesiveAbsoluteAzimuthStatus || "",
        cohesiveQuality:
          host?.dataset.cohesiveQuality || "",
        cohesiveFreshness:
          host?.dataset.cohesiveFreshness || "",
        cohesiveModelVersion:
          host?.dataset.cohesiveModelVersion || "",
        cohesiveContractState:
          host?.dataset.cohesiveContractState || "",
        cohesiveContractIssues:
          host?.dataset.cohesiveContractIssues || "",
      },
      geometry: {
        shellExists: Boolean(shell),
        shellVisible: isEffectivelyVisible(shell),
        shellColor:
          shell?.material?.color?.getHexString?.() || null,
        shellOpacity: shell?.material?.opacity ?? null,
        groupVisible: isEffectivelyVisible(cohesiveGroup),
        whatIfVisible: isEffectivelyVisible(whatIf),
      },
      layout: {
        viewport: { width: innerWidth, height: innerHeight },
        rootScrollWidth: root.scrollWidth,
        rootClientWidth: root.clientWidth,
        bodyScrollWidth: body.scrollWidth,
        horizontalOverflow:
          root.scrollWidth > root.clientWidth + 1 ||
          body.scrollWidth > root.clientWidth + 1,
        panel: rect(panel),
        panelBodyVisible:
          panelBody && getComputedStyle(panelBody).display !== "none",
        cohesiveRow: rect(cohesiveRow),
        cohesiveRowTopHit: isTopHit(cohesiveRow),
        cutawayButton: rect(cutawayButton),
        cutawayButtonTopHit: isTopHit(cutawayButton),
      },
    };
  });
}

async function inspectCutawayControlReachability(page) {
  const button = page.locator('button[data-cutaway-action="cutaway"]');
  await button.scrollIntoViewIfNeeded();
  await page.waitForTimeout(80);
  return button.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const x = Math.max(
      0,
      Math.min(innerWidth - 1, rect.left + rect.width / 2),
    );
    const y = Math.max(
      0,
      Math.min(innerHeight - 1, rect.top + rect.height / 2),
    );
    const hit = document.elementFromPoint(x, y);
    return {
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
      topHit: Boolean(
        hit && (hit === element || element.contains(hit)),
      ),
      active:
        element.classList.contains("active") ||
        element.getAttribute("aria-pressed") === "true",
    };
  });
}

function assertC2Contract(result, cutawayControl) {
  const { state, status, attributes, geometry, layout } = result;
  const cohesive = state.cohesive;
  assert(
    state.mode === "live" &&
      state.cutawayMode === "cutaway" &&
      state.visible === true,
    "live cutaway state",
    state,
  );
  assert(
    cohesive.visible === true &&
      cohesive.evidence === "estimated" &&
      cohesive.movement.direction === "up" &&
      cohesive.movement.forecast_height_m === 18.44 &&
      cohesive.confidence === 0.42 &&
      cohesive.inputCoverage === 0.88 &&
      cohesive.calibrationStatus === "uncalibrated" &&
      cohesive.controlUse === "prohibited" &&
      cohesive.contract.state === "valid" &&
      cohesive.contract.issues.length === 0,
    "C2 live estimate state",
    cohesive,
  );
  assert(
    cohesive.whatIf.enabled === false &&
      cohesive.whatIf.visible === false,
    "production what-if remains disabled",
    cohesive.whatIf,
  );
  [
    "未标定估计",
    "禁止控制",
    "上移",
    "根部",
    "厚度",
    "置信度 42%",
  ].forEach((label) => {
    assert(status.includes(label), `status includes ${label}`, status);
  });
  assert(
    attributes.cohesiveWhatIf === "false" &&
      attributes.cohesiveVisible === "true" &&
      attributes.cohesiveEvidence === "estimated" &&
      attributes.cohesiveDirection === "up" &&
      Math.abs(Number(attributes.cohesiveVelocityMPerH) - 0.36) <=
        0.001 &&
      Math.abs(Number(attributes.cohesiveRootHeightM) - 18.35) <=
        0.001 &&
      Math.abs(Number(attributes.cohesiveThicknessM) - 2.3) <= 0.02 &&
      Math.abs(Number(attributes.cohesiveEccentricityM) - 0.28) <=
        0.02 &&
      attributes.cohesiveConfidence === "0.420" &&
      attributes.cohesiveInputCoverage === "0.880" &&
      attributes.cohesiveCalibrationStatus === "uncalibrated" &&
      attributes.cohesiveControlUse === "prohibited" &&
      attributes.cohesiveRootDefinition ===
        "wall_thermal_activity_centroid" &&
      attributes.cohesiveAzimuthReference ===
        "sensor_relative_A_zero" &&
      attributes.cohesiveAbsoluteAzimuthStatus === "unconfirmed" &&
      attributes.cohesiveQuality === "good" &&
      attributes.cohesiveFreshness === "good" &&
      attributes.cohesiveModelVersion ===
        "C2-ROOT-BASELINE-2026.07" &&
      attributes.cohesiveContractState === "valid" &&
      attributes.cohesiveContractIssues === "",
    "data-cohesive observable contract",
    attributes,
  );
  assert(
    geometry.shellExists &&
      geometry.shellVisible &&
      geometry.groupVisible &&
      geometry.whatIfVisible === false &&
      geometry.shellColor === "c97138" &&
      geometry.shellOpacity >= 0.68,
    "orange cohesive shell render contract",
    geometry,
  );
  assert(
    layout.horizontalOverflow === false,
    "no horizontal overflow",
    layout,
  );
  assert(
    layout.panel &&
      layout.panel.left >= -1 &&
      layout.panel.right <= layout.viewport.width + 1 &&
      layout.panelBodyVisible,
    "simulation panel remains reachable",
    layout,
  );
  assert(
    layout.cohesiveRow &&
      layout.cohesiveRow.width > 40 &&
      layout.cohesiveRow.height > 10 &&
      layout.cohesiveRow.left >= -1 &&
      layout.cohesiveRow.right <= layout.viewport.width + 1 &&
      layout.cohesiveRowTopHit,
    "C2 status row is visible and unobscured",
    layout,
  );
  assert(
    cutawayControl &&
      cutawayControl.width > 10 &&
      cutawayControl.height > 10 &&
      cutawayControl.left >= -1 &&
      cutawayControl.right <= layout.viewport.width + 1 &&
      cutawayControl.top >= -1 &&
      cutawayControl.bottom <= layout.viewport.height + 1 &&
      cutawayControl.topHit,
    "cutaway control is independently reachable and unobscured",
    cutawayControl,
  );
}

async function runViewport(browser, engine, baseUrl, width, height) {
  const viewport = `${width}x${height}`;
  const page = await browser.newPage({ viewport: { width, height } });
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
      httpErrors.push({
        status: response.status(),
        url: response.url(),
      });
    }
  });
  await installWebSocketContractStub(page);
  try {
    await page.goto(`${baseUrl}#overview`, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    await page.waitForFunction(
      () =>
        window.__BF_CAD_FURNACE_VIEWER?.sensorCount === 115 &&
        window.__BF3D_INTERNAL_SIMULATION__?.getState?.().ready ===
          true,
      null,
      { timeout: 90_000 },
    );
    await page.locator('button[data-cutaway-action="cutaway"]').click();
    await ensureSimulationPanelExpanded(page);
    await page.locator('button[data-sim-action="live"]').click();
    await injectC2Snapshot(page);
    await page.waitForFunction(
      () => {
        const state =
          window.__BF3D_INTERNAL_SIMULATION__?.getState?.();
        const host = document.querySelector(".cad-furnace-viewer");
        return (
          state?.mode === "live" &&
          state?.cutawayMode === "cutaway" &&
          state?.cohesive?.visible === true &&
          state?.cohesive?.movement?.direction === "up" &&
          host?.dataset?.cohesiveEvidence === "estimated" &&
          host?.dataset?.cohesiveCalibrationStatus ===
            "uncalibrated" &&
          Math.abs(
            Number(host?.dataset?.cohesiveThicknessM) - 2.3,
          ) <= 0.02 &&
          Math.abs(
            Number(host?.dataset?.cohesiveEccentricityM) - 0.28,
          ) <= 0.02
        );
      },
      null,
      { timeout: 15_000 },
    );
    await page
      .locator('.bf3d-sim-object-row[data-object="cohesive"]')
      .scrollIntoViewIfNeeded();
    await page.waitForTimeout(220);
    const inspection = await inspectC2(page);
    const cutawayControl =
      await inspectCutawayControlReachability(page);

    const hasExpectedOfflineResponse = httpErrors.some(
      isExpectedOfflineResponse,
    );
    const unexpectedPageErrors = pageErrors.filter(
      (message) =>
        !(
          hasExpectedOfflineResponse &&
          message.includes("接口 HTTP 404")
        ) && !isExpectedOffline(message),
    );
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) =>
        !isExpectedOffline(message) &&
        !(
          hasExpectedOfflineResponse &&
          message.includes("Failed to load resource:")
        ),
    );
    const unexpectedHttpErrors = httpErrors.filter(
      (entry) => !isExpectedOfflineResponse(entry),
    );
    const screenshot =
      viewport === REPRESENTATIVE_SCREENSHOT_VIEWPORT
        ? path.join(OUTPUT_ROOT, `${engine}_${viewport}_c2_live.png`)
        : null;
    if (screenshot) {
      await page
        .locator('.bf3d-sim-object-row[data-object="cohesive"]')
        .scrollIntoViewIfNeeded();
      await page.waitForTimeout(80);
      await page.screenshot({ path: screenshot, fullPage: false });
    }

    const result = {
      ok: true,
      engine,
      viewport,
      url: page.url(),
      screenshot,
      inspection,
      cutawayControl,
      pageErrors: unexpectedPageErrors,
      consoleErrors: unexpectedConsoleErrors,
      httpErrors: unexpectedHttpErrors,
      ignoredOffline: {
        pageErrors: pageErrors.length - unexpectedPageErrors.length,
        consoleErrors:
          consoleErrors.length - unexpectedConsoleErrors.length,
        httpErrors: httpErrors.length - unexpectedHttpErrors.length,
      },
    };
    assertC2Contract(inspection, cutawayControl);
    assert(
      unexpectedPageErrors.length === 0,
      "unexpected page errors",
      result,
    );
    assert(
      unexpectedConsoleErrors.length === 0,
      "unexpected console errors",
      result,
    );
    assert(
      unexpectedHttpErrors.length === 0,
      "unexpected HTTP errors",
      result,
    );
    return result;
  } finally {
    await page.close();
  }
}

async function main() {
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const server = await startServer();
  const port = server.address().port;
  const baseUrl = `http://127.0.0.1:${port}/frontend_dashboard_v3.server.html?ws_port=8767`;
  const matrix = [];
  try {
    for (const engine of ENGINES) {
      const browser = await playwright[engine].launch({ headless: true });
      try {
        for (const [width, height] of VIEWPORTS) {
          try {
            matrix.push(
              await runViewport(
                browser,
                engine,
                baseUrl,
                width,
                height,
              ),
            );
          } catch (error) {
            matrix.push({
              ok: false,
              engine,
              viewport: `${width}x${height}`,
              error: String(error?.stack || error),
            });
          }
        }
      } finally {
        await browser.close();
      }
    }
    const passed = matrix.filter((item) => item.ok).length;
    const report = {
      ok: passed === ENGINES.length * VIEWPORTS.length,
      requirement: "REQ-BF3D-C2-ROOT-MOTION-20260719",
      generatedAt: new Date().toISOString(),
      baseUrl,
      contract: {
        schema_version: "bf3d_snapshot.v1",
        evidence: "estimated",
        calibration_status: "uncalibrated",
        control_use: "prohibited",
        direction: "up",
        root_height_m: 18.35,
        thickness_m: 2.3,
        eccentricity_m: 0.28,
        confidence: 0.42,
        forecast_height_m: 18.44,
      },
      coverage: {
        expectedRuns: ENGINES.length * VIEWPORTS.length,
        passedRuns: passed,
        failedRuns: matrix.length - passed,
        engines: ENGINES,
        viewports: VIEWPORTS.map(([w, h]) => `${w}x${h}`),
        representativeScreenshots: ENGINES.map((engine) =>
          path.join(
            OUTPUT_ROOT,
            `${engine}_${REPRESENTATIVE_SCREENSHOT_VIEWPORT}_c2_live.png`,
          ),
        ),
      },
      matrix,
    };
    const reportPath = path.join(OUTPUT_ROOT, "report.json");
    fs.writeFileSync(
      reportPath,
      JSON.stringify(report, null, 2),
      "utf8",
    );
    process.stdout.write(
      `${JSON.stringify(
        {
          ok: report.ok,
          passed: `${passed}/${report.coverage.expectedRuns}`,
          report: reportPath,
          screenshots: report.coverage.representativeScreenshots,
        },
        null,
        2,
      )}\n`,
    );
    assert(
      report.ok,
      "C2 cross-engine matrix did not pass 12/12",
      matrix.filter((item) => !item.ok),
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
