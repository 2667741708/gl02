#!/usr/bin/env node
"use strict";

// Independent viewport matrix for the GL02 L7-L16 layer UI. This intentionally
// serves the frontend as static files, so the 8767 WebSocket and /api/* calls are
// expected to be offline; model/script/asset failures are still hard failures.

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
const OUTPUT_ROOT = path.join(ROOT, "logs", "bf3d_layer_matrix_20260717");
const VIEWPORTS = [
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
const LAYERS_TO_CLICK = ["L7", "L10", "L13", "L16"];
const EXPECTED_LAYER_IDS = Array.from({ length: 10 }, (_, index) => `L${index + 7}`);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function startStaticServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((request, response) => {
      let pathname;
      try {
        pathname = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
      } catch {
        response.writeHead(400).end("bad request");
        return;
      }
      if (pathname === "/") pathname = "/frontend_dashboard_v3.server.html";
      const relative = pathname.replace(/^\/+/, "");
      const target = path.resolve(FRONTEND_ROOT, relative);
      if (target !== FRONTEND_ROOT && !target.startsWith(FRONTEND_ROOT + path.sep)) {
        response.writeHead(403).end("forbidden");
        return;
      }
      fs.stat(target, (statError, stat) => {
        if (statError || !stat.isFile()) {
          response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
          response.end("not found");
          return;
        }
        response.writeHead(200, {
          "Content-Type": MIME[path.extname(target).toLowerCase()] || "application/octet-stream",
          "Cache-Control": "no-store",
        });
        fs.createReadStream(target).pipe(response);
      });
    });
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, baseUrl: `http://127.0.0.1:${address.port}` });
    });
  });
}

function isExpectedOfflineResponse(item) {
  try {
    const url = new URL(item.url);
    return (
      url.pathname.startsWith("/api/") ||
      (url.hostname === "127.0.0.1" && url.port === "8767")
    );
  } catch {
    return false;
  }
}

function isExpectedOfflineConsole(message, expectedOfflineResponses) {
  if (
    message.includes("WebSocket connection to") &&
    message.includes("127.0.0.1:8767")
  ) {
    return true;
  }
  if (
    (message.startsWith("Failed to load resource:") ||
      message.includes("Failed to fetch")) &&
    expectedOfflineResponses.length > 0
  ) {
    return true;
  }
  return false;
}

function rectsOverlap(a, b) {
  if (!a || !b) return false;
  return !(
    a.right <= b.left ||
    b.right <= a.left ||
    a.bottom <= b.top ||
    b.bottom <= a.top
  );
}

async function runViewport(browser, baseUrl, width, height) {
  const id = `${width}x${height}`;
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
    reducedMotion: "no-preference",
  });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  const failedRequests = [];
  const httpErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      error: request.failure()?.errorText || "request failed",
    });
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      httpErrors.push({ status: response.status(), url: response.url() });
    }
  });

  const result = {
    engine: "chromium",
    viewport: id,
    url: `${baseUrl}/frontend_dashboard_v3.server.html?ws_port=8767#overview`,
    ok: false,
    checks: {},
    layers: {},
    page_errors: pageErrors,
    console_errors: [],
    expected_offline: [],
    benign_runtime: [],
    unexpected_http_errors: [],
    unexpected_request_failures: [],
  };

  try {
    await page.goto(result.url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForFunction(
      () =>
        window.__BF_CAD_FURNACE_VIEWER?.sensorCount === 115 &&
        typeof window.__BF_CAD_FURNACE_VIEWER?.highlightLayer === "function",
      null,
      { timeout: 60000 }
    );
    await page.locator(".cad-layer-controls").waitFor({ state: "visible", timeout: 15000 });

    const staticState = await page.evaluate(() => {
      const doc = document.documentElement;
      const host = document.querySelector(".cad-furnace-viewer");
      const controls = document.querySelector(".cad-layer-controls");
      const nav = document.querySelector(".bottom-nav");
      const toRect = (element) => {
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        return {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
      };
      return {
        status: host?.dataset.status || "",
        sensorCount: Number(host?.dataset.sensorCount || 0),
        mappedCount: Number(host?.dataset.mappedCount || 0),
        canvas: {
          width: host?.querySelector("canvas")?.clientWidth || 0,
          height: host?.querySelector("canvas")?.clientHeight || 0,
        },
        layerIds: Array.from(
          document.querySelectorAll('button[data-kind="layer"]'),
          (button) => button.dataset.id
        ),
        horizontalOverflow: doc.scrollWidth > doc.clientWidth + 1,
        viewport: { width: doc.clientWidth, height: doc.clientHeight },
        controlsRect: toRect(controls),
        navRect: toRect(nav),
      };
    });
    staticState.controlsNavOverlap = rectsOverlap(
      staticState.controlsRect,
      staticState.navRect
    );
    result.static = staticState;
    result.checks.model_loaded =
      staticState.status === "loaded" &&
      staticState.sensorCount === 115 &&
      staticState.mappedCount === 115 &&
      staticState.canvas.width > 0 &&
      staticState.canvas.height > 0;
    result.checks.ten_layer_buttons =
      JSON.stringify(staticState.layerIds) === JSON.stringify(EXPECTED_LAYER_IDS);
    result.checks.no_horizontal_overflow = !staticState.horizontalOverflow;
    result.checks.controls_not_covered_by_bottom_nav = !staticState.controlsNavOverlap;

    for (const layerId of LAYERS_TO_CLICK) {
      const button = page.locator(
        `button[data-kind="layer"][data-id="${layerId}"]`
      );
      const count = await button.count();
      const visibleBefore = count === 1 && (await button.isVisible());
      if (count === 1) {
        await button.click();
        await page.waitForTimeout(80);
      }
      const layerState = await page.evaluate((requested) => {
        const viewer = window.__BF_CAD_FURNACE_VIEWER;
        const visibleNames = viewer.sensorObjects
          .filter(
            (object) =>
              object.visible && object.name.startsWith("SENSOR_T_body_")
          )
          .map((object) => object.name);
        return {
          requested,
          active:
            document.querySelector(".cad-layer-controls button.active")?.dataset
              .id || "",
          visibleSensors: Number(
            document.querySelector(".cad-furnace-viewer")?.dataset
              .visibleSensors || -1
          ),
          visibleNames,
          highlight: viewer.getLayerHighlightState(),
        };
      }, layerId);
      layerState.buttonCount = count;
      layerState.buttonVisible = visibleBefore;
      layerState.ok =
        count === 1 &&
        visibleBefore &&
        layerState.active === layerId &&
        layerState.visibleSensors === 8 &&
        layerState.visibleNames.length === 8 &&
        layerState.visibleNames.every((name) =>
          name.startsWith(`SENSOR_T_body_${layerId}_`)
        ) &&
        layerState.highlight.layerId === layerId;
      result.layers[layerId] = layerState;
    }
    result.checks.four_layer_clicks = LAYERS_TO_CLICK.every(
      (layerId) => result.layers[layerId]?.ok
    );

    const screenshotPath = path.join(OUTPUT_ROOT, `chromium_${id}_L16.png`);
    await page.screenshot({ path: screenshotPath, fullPage: false });
    result.screenshot = screenshotPath;

    const expectedOfflineResponses = httpErrors.filter(isExpectedOfflineResponse);
    const unexpectedHttpErrors = httpErrors.filter(
      (item) => !isExpectedOfflineResponse(item)
    );
    const expectedOfflineRequests = failedRequests.filter((item) => {
      try {
        const url = new URL(item.url);
        return (
          url.pathname.startsWith("/api/") ||
          (url.hostname === "127.0.0.1" && url.port === "8767")
        );
      } catch {
        return false;
      }
    });
    const benignCancelledModelRequests = failedRequests.filter((item) => {
      try {
        const url = new URL(item.url);
        return (
          result.checks.model_loaded &&
          url.pathname === "/models/gl02_blast_furnace.glb" &&
          item.error.includes("ERR_ABORTED")
        );
      } catch {
        return false;
      }
    });
    const unexpectedRequestFailures = failedRequests.filter(
      (item) =>
        !expectedOfflineRequests.includes(item) &&
        !benignCancelledModelRequests.includes(item)
    );
    const expectedOfflineConsole = consoleErrors.filter((message) =>
      isExpectedOfflineConsole(message, expectedOfflineResponses)
    );
    const benignConsole = consoleErrors.filter((message) =>
      message.startsWith(
        "[BABEL] Note: The code generator has deoptimised the styling"
      )
    );
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) =>
        !expectedOfflineConsole.includes(message) &&
        !benignConsole.includes(message)
    );
    result.expected_offline = [
      ...expectedOfflineResponses.map((item) => ({
        kind: "http",
        ...item,
      })),
      ...expectedOfflineRequests.map((item) => ({
        kind: "request",
        ...item,
      })),
      ...expectedOfflineConsole.map((message) => ({
        kind: "console",
        message,
      })),
    ];
    result.benign_runtime = [
      ...benignCancelledModelRequests.map((item) => ({
        kind: "cancelled_duplicate_model_request_after_successful_load",
        ...item,
      })),
      ...benignConsole.map((message) => ({
        kind: "babel_large_inline_script_notice",
        message,
      })),
    ];
    result.unexpected_http_errors = unexpectedHttpErrors;
    result.unexpected_request_failures = unexpectedRequestFailures;
    result.console_errors = unexpectedConsoleErrors;
    result.checks.no_page_errors = pageErrors.length === 0;
    result.checks.no_unexpected_console_errors =
      unexpectedConsoleErrors.length === 0;
    result.checks.no_unexpected_resource_errors =
      unexpectedHttpErrors.length === 0 &&
      unexpectedRequestFailures.length === 0;
    result.ok = Object.values(result.checks).every(Boolean);
  } catch (error) {
    result.failure = error?.stack || String(error);
    try {
      const screenshotPath = path.join(OUTPUT_ROOT, `chromium_${id}_FAIL.png`);
      await page.screenshot({ path: screenshotPath, fullPage: false });
      result.screenshot = screenshotPath;
    } catch {
      // Preserve the original failure.
    }
  } finally {
    await context.close();
  }
  return result;
}

async function main() {
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const { server, baseUrl } = await startStaticServer();
  let browser;
  const results = [];
  try {
    browser = await playwright.chromium.launch({ headless: true });
    for (const [width, height] of VIEWPORTS) {
      const result = await runViewport(browser, baseUrl, width, height);
      results.push(result);
      process.stdout.write(
        `${result.viewport}: ${result.ok ? "PASS" : "FAIL"}\n`
      );
    }
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  const passed = results.filter((result) => result.ok).length;
  const manifest = {
    generated_at: new Date().toISOString(),
    scope: "Chromium GL02 L7/L10/L13/L16 layer UI matrix",
    static_data_source: true,
    expected_offline_policy:
      "Only 127.0.0.1:8767 WebSocket and /api/* static-server failures are ignored.",
    browser: {
      engine: "chromium",
      executable: playwright.chromium.executablePath(),
    },
    summary: {
      total: results.length,
      passed,
      failed: results.length - passed,
      ok: passed === results.length,
    },
    results,
  };
  fs.writeFileSync(
    path.join(OUTPUT_ROOT, "manifest.json"),
    JSON.stringify(manifest, null, 2),
    "utf8"
  );
  const lines = [
    "# GL02 测温层 Chromium 视口验收",
    "",
    `- 结果：${passed}/${results.length} 通过`,
    `- 数据边界：静态页面，8767 WebSocket 与 /api/* 离线记录为 expected_offline`,
    `- 浏览器：${manifest.browser.executable}`,
    "",
    "| 视口 | 结果 | 模型/115点 | 十层按钮 | L7/L10/L13/L16 | 无横向溢出 | 控制栏未被底栏遮挡 | 页面/控制台/资源错误 |",
    "|---|---|---|---|---|---|---|---|",
    ...results.map((result) => {
      const c = result.checks || {};
      const mark = (value) => (value ? "通过" : "失败");
      return `| ${result.viewport} | ${mark(result.ok)} | ${mark(
        c.model_loaded
      )} | ${mark(c.ten_layer_buttons)} | ${mark(
        c.four_layer_clicks
      )} | ${mark(c.no_horizontal_overflow)} | ${mark(
        c.controls_not_covered_by_bottom_nav
      )} | ${mark(
        c.no_page_errors &&
          c.no_unexpected_console_errors &&
          c.no_unexpected_resource_errors
      )} |`;
    }),
    "",
  ];
  fs.writeFileSync(path.join(OUTPUT_ROOT, "report.md"), lines.join("\n"), "utf8");
  process.stdout.write(
    `manifest: ${path.join(OUTPUT_ROOT, "manifest.json")}\n`
  );
  process.exitCode = manifest.summary.ok ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});
