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
  "matrix",
);
const ROUTES = ["overview", "diagnosis", "optimization", "trend", "qa"];
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
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function assert(condition, message, detail) {
  if (!condition) throw new Error(`${message}: ${JSON.stringify(detail)}`);
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

async function inspectRoute(page, route, routeIndex) {
  if (routeIndex > 0) {
    await page.locator(".bottom-nav .nav-btn").nth(routeIndex).click();
    await page.waitForTimeout(120);
  }
  await page.waitForFunction(
    (expected) => window.location.hash.replace(/^#/, "") === expected,
    route,
    { timeout: 15_000 },
  );
  if (route === "overview") {
    await page.waitForFunction(
      () => window.__BF3D_INTERNAL_SIMULATION__?.getState?.().ready === true,
      null,
      { timeout: 90_000 },
    );
  }
  return page.evaluate((expected) => {
    const root = document.documentElement;
    const body = document.body;
    const navButtons = [...document.querySelectorAll(".bottom-nav .nav-btn")];
    const active = navButtons.findIndex(
      (button) =>
        button.classList.contains("active") ||
        button.getAttribute("aria-current") === "page",
    );
    const visibleButtons = navButtons.filter((button) => {
      const rect = button.getBoundingClientRect();
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        rect.right > 0 &&
        rect.left < window.innerWidth
      );
    }).length;
    const headerText =
      document.querySelector(".branded-topbar")?.textContent || "";
    return {
      route: expected,
      hash: window.location.hash,
      active,
      navCount: navButtons.length,
      visibleButtons,
      viewportWidth: root.clientWidth,
      rootScrollWidth: root.scrollWidth,
      bodyScrollWidth: body.scrollWidth,
      horizontalOverflow:
        root.scrollWidth > root.clientWidth + 1 ||
        body.scrollWidth > root.clientWidth + 1,
      headerReachable:
        headerText.includes("高炉工艺大模型智能决策系统") &&
        headerText.includes("炽穹"),
    };
  }, route);
}

async function runViewport(browser, engine, baseUrl, width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
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
    await page.goto(`${baseUrl}#overview`, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    const routes = [];
    for (let index = 0; index < ROUTES.length; index += 1) {
      routes.push(await inspectRoute(page, ROUTES[index], index));
    }
    await page.locator(".bottom-nav .nav-btn").nth(0).click();
    await page.waitForFunction(
      () => window.__BF3D_INTERNAL_SIMULATION__?.getState?.().ready === true,
      null,
      { timeout: 90_000 },
    );
    await page.locator('button[data-cutaway-action="cutaway"]').click();
    if (
      !(await page
        .locator('button[data-sim-action="illustrative"]')
        .isVisible())
    ) {
      await page.locator(".bf3d-sim-collapse").click();
    }
    await page.locator('button[data-sim-action="illustrative"]').click();
    await page.waitForTimeout(240);
    await page.locator(".bf3d-sim-panel").scrollIntoViewIfNeeded();
    await page.waitForTimeout(80);
    const overview = await page.evaluate(() => {
      const state = window.__BF3D_INTERNAL_SIMULATION__.getState();
      const panel = document
        .querySelector(".bf3d-sim-panel")
        ?.getBoundingClientRect();
      const cutawayButton = document
        .querySelector('button[data-cutaway-action="cutaway"]')
        ?.getBoundingClientRect();
      return {
        state: {
          mode: state.mode,
          pressurePoints: state.pressure.visibleMeasuredCount,
          tuyereCount: state.tuyere.tuyereCount,
          legacyVisible: state.resources.legacyDecorativeVisibleCount,
          deliveryImplementation:
            state.stock.delivery.implementation.ore,
          deliveryCapacity:
            state.resources.burdenDeliveryParticleCapacity,
          deliveryQuality: state.stock.delivery.quality.current,
          liveMotionGate: state.stock.delivery.liveMotionGate.enabled,
          cohesiveWhatIfDefault: state.cohesive.whatIf.enabled,
        },
        panel: panel
          ? {
              left: panel.left,
              right: panel.right,
              top: panel.top,
              bottom: panel.bottom,
            }
          : null,
        cutawayButton: cutawayButton
          ? {
              left: cutawayButton.left,
              right: cutawayButton.right,
              top: cutawayButton.top,
              bottom: cutawayButton.bottom,
            }
          : null,
        viewport: { width: innerWidth, height: innerHeight },
      };
    });
    const screenshot =
      engine === "chromium" &&
      [[1280, 720], [390, 844]].some(
        ([w, h]) => w === width && h === height,
      )
        ? path.join(OUTPUT_ROOT, `${engine}_${width}x${height}.png`)
        : null;
    if (screenshot) await page.screenshot({ path: screenshot });
    const hasExpectedOfflineResponse = httpErrors.some((entry) => {
      const pathname = new URL(entry.url).pathname;
      return (
        pathname.startsWith("/api/automation/") ||
        pathname.startsWith("/api/short-window/") ||
        pathname.startsWith("/api/qa/") ||
        pathname.startsWith("/api/ollama/")
      );
    });
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) =>
        !isExpectedOffline(message) &&
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
        !pathname.startsWith("/api/qa/") &&
        !pathname.startsWith("/api/ollama/") &&
        !pathname.endsWith("/favicon.ico")
      );
    });
    const result = {
      engine,
      viewport: `${width}x${height}`,
      routes,
      overview,
      screenshot,
      pageErrors: pageErrors.filter(
        (message) =>
          !(
            hasExpectedOfflineResponse &&
            message.includes("接口 HTTP 404")
          ),
      ),
      ignoredOfflinePageErrors: pageErrors.filter(
        (message) =>
          hasExpectedOfflineResponse && message.includes("接口 HTTP 404"),
      ),
      consoleErrors: unexpectedConsoleErrors,
      httpErrors: unexpectedHttpErrors,
    };
    assert(
      routes.length === 5 &&
        routes.every(
          (item) =>
            item.hash === `#${item.route}` &&
            item.navCount === 5 &&
            item.visibleButtons >= 1 &&
            item.horizontalOverflow === false &&
            item.headerReachable,
        ),
      "five route and overflow matrix",
      result,
    );
    assert(
      overview.state.mode === "illustrative" &&
        overview.state.pressurePoints === 18 &&
        overview.state.tuyereCount === 26 &&
        overview.state.legacyVisible === 0 &&
        overview.state.deliveryImplementation === "InstancedMesh" &&
        overview.state.deliveryCapacity > 0 &&
        ["high", "medium", "low"].includes(
          overview.state.deliveryQuality,
        ) &&
        overview.state.liveMotionGate === false &&
        overview.state.cohesiveWhatIfDefault === false,
      "internal simulation overview state",
      result,
    );
    assert(
      overview.panel &&
        overview.panel.left >= -1 &&
        overview.panel.right <= overview.viewport.width + 1 &&
        overview.panel.top >= -1 &&
        overview.panel.bottom <= overview.viewport.height + 1,
      "simulation panel viewport bounds",
      result,
    );
    assert(
      overview.cutawayButton &&
        overview.cutawayButton.left >= -1 &&
        overview.cutawayButton.right <= overview.viewport.width + 1 &&
        overview.cutawayButton.right > overview.cutawayButton.left &&
        overview.cutawayButton.bottom > overview.cutawayButton.top,
      "cutaway button viewport bounds",
      result,
    );
    assert(result.pageErrors.length === 0, "page errors", result);
    assert(
      unexpectedConsoleErrors.length === 0,
      "console errors",
      result,
    );
    assert(unexpectedHttpErrors.length === 0, "HTTP errors", result);
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
    for (const [engine, viewports] of [
      ["chromium", CHROMIUM_VIEWPORTS],
      ["firefox", REPRESENTATIVE_VIEWPORTS],
      ["webkit", REPRESENTATIVE_VIEWPORTS],
    ]) {
      const browser = await playwright[engine].launch({ headless: true });
      try {
        for (const [width, height] of viewports) {
          matrix.push(
            await runViewport(
              browser,
              engine,
              baseUrl,
              width,
              height,
            ),
          );
        }
      } finally {
        await browser.close();
      }
    }
    const report = {
      ok: true,
      requirement: "REQ-BF3D-INTERNAL-RUNTIME-6X-20260719",
      baseUrl,
      generatedAt: new Date().toISOString(),
      coverage: {
        viewportRuns: matrix.length,
        routeCombinations: matrix.length * ROUTES.length,
        chromium: CHROMIUM_VIEWPORTS.map(([w, h]) => `${w}x${h}`),
        firefox: REPRESENTATIVE_VIEWPORTS.map(([w, h]) => `${w}x${h}`),
        webkit: REPRESENTATIVE_VIEWPORTS.map(([w, h]) => `${w}x${h}`),
      },
      matrix,
    };
    fs.writeFileSync(
      path.join(OUTPUT_ROOT, "cross_engine_viewport_report.json"),
      JSON.stringify(report, null, 2),
      "utf8",
    );
    process.stdout.write(
      `${JSON.stringify(
        {
          ok: true,
          viewportRuns: report.coverage.viewportRuns,
          routeCombinations: report.coverage.routeCombinations,
          engines: {
            chromium: CHROMIUM_VIEWPORTS.length,
            firefox: REPRESENTATIVE_VIEWPORTS.length,
            webkit: REPRESENTATIVE_VIEWPORTS.length,
          },
        },
        null,
        2,
      )}\n`,
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
