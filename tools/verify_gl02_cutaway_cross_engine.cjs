#!/usr/bin/env node
"use strict";

// Representative Firefox/WebKit acceptance matrix for the GL02 cutaway UI.
// The page is served as static files, so 8767 WebSocket and /api/* failures are
// expected offline signals. Model, script, page and other resource failures are
// still hard failures.

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
  "bf3d_cutaway_cross_engine_20260717",
);
const VIEWPORTS = [
  [1920, 1080],
  [1366, 768],
  [768, 1024],
  [390, 844],
];
const ENGINES = ["firefox", "webkit"];
const FALLBACK_EXECUTABLES = {
  firefox:
    "C:/Users/hmw20/AppData/Local/ms-playwright/firefox-1532/firefox/firefox.exe",
  webkit:
    "C:/Users/hmw20/AppData/Local/ms-playwright/webkit-2287/Playwright.exe",
};
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
          response
            .writeHead(404, { "Content-Type": "text/plain; charset=utf-8" })
            .end("not found");
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
    server.listen(0, "127.0.0.1", () => {
      resolve({
        server,
        baseUrl: `http://127.0.0.1:${server.address().port}`,
      });
    });
  });
}

function expectedOfflineUrl(value) {
  try {
    const url = new URL(value);
    return (
      url.pathname.startsWith("/api/") ||
      (url.hostname === "127.0.0.1" && url.port === "8767") ||
      url.pathname.endsWith("/favicon.ico")
    );
  } catch {
    return false;
  }
}

function expectedOfflineConsole(message, expectedNetworkItems) {
  if (
    message.includes("127.0.0.1:8767") &&
    (message.includes("WebSocket") ||
      message.includes("websocket") ||
      message.includes("ws://127.0.0.1:8767"))
  ) {
    return true;
  }
  return (
    expectedNetworkItems.length > 0 &&
    (message.includes("Failed to load resource:") ||
      message.includes("Failed to fetch") ||
      message.includes("Load failed") ||
      message.includes("NetworkError"))
  );
}

function rectsOverlap(first, second) {
  if (!first || !second) return false;
  return !(
    first.right <= second.left ||
    second.right <= first.left ||
    first.bottom <= second.top ||
    second.bottom <= first.top
  );
}

async function buttonEvidence(page, action) {
  const locator = page.locator(`button[data-cutaway-action="${action}"]`);
  const count = await locator.count();
  if (count !== 1) {
    return {
      action,
      count,
      visible: false,
      enabled: false,
      centerUncovered: false,
    };
  }
  await locator.scrollIntoViewIfNeeded({ timeout: 10_000 });
  const visible = await locator.isVisible();
  const enabled = await locator.isEnabled();
  const centerUncovered = await locator.evaluate((button) => {
    const rect = button.getBoundingClientRect();
    const x = Math.max(
      0,
      Math.min(innerWidth - 1, rect.left + rect.width / 2),
    );
    const y = Math.max(
      0,
      Math.min(innerHeight - 1, rect.top + rect.height / 2),
    );
    const top = document.elementFromPoint(x, y);
    return Boolean(top && (top === button || button.contains(top)));
  });
  return { action, count, visible, enabled, centerUncovered };
}

async function readUiState(page) {
  return page.evaluate(() => {
    const viewer = window.__BF_CAD_FURNACE_VIEWER;
    const host = document.querySelector(".cad-furnace-viewer");
    const status = document.querySelector(".cad-cutaway-status");
    const play = document.querySelector(
      'button[data-cutaway-action="play"]',
    );
    const exterior = document.querySelector(
      'button[data-cutaway-action="exterior"]',
    );
    const cutaway = document.querySelector(
      'button[data-cutaway-action="cutaway"]',
    );
    return {
      viewer: viewer.getCutawayState(),
      simulation:
        typeof viewer.getInternalSimulationState === "function"
          ? viewer.getInternalSimulationState()
          : null,
      host: {
        mode: host?.dataset.cutawayMode || "",
        phase: host?.dataset.cutawayPhase || "",
        internalCount: Number(host?.dataset.internalCount || -1),
        internalVisibleCount: Number(
          host?.dataset.internalVisibleCount || -1,
        ),
      },
      statusText: status?.textContent || "",
      statusActive: status?.dataset.active || "",
      playText: play?.textContent || "",
      playPressed: play?.getAttribute("aria-pressed") || "",
      playDisabled: Boolean(play?.disabled),
      exteriorActive: Boolean(exterior?.classList.contains("active")),
      cutawayActive: Boolean(cutaway?.classList.contains("active")),
    };
  });
}

async function runViewport(browser, engine, baseUrl, width, height) {
  const viewport = `${width}x${height}`;
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
    engine,
    viewport,
    url: `${baseUrl}/frontend_dashboard_v3.server.html?ws_port=8767#overview`,
    ok: false,
    checks: {},
    pageErrors,
    consoleErrors: [],
    unexpectedHttpErrors: [],
    unexpectedRequestFailures: [],
    expectedOffline: [],
    benignRuntime: [],
  };

  try {
    await page.goto(result.url, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
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
          "function" &&
        typeof window.__BF_CAD_FURNACE_VIEWER
          ?.getInternalSimulationState === "function",
      null,
      { timeout: 90_000 },
    );
    await page
      .locator(".cad-layer-controls")
      .waitFor({ state: "visible", timeout: 15_000 });

    result.layout = await page.evaluate(() => {
      const doc = document.documentElement;
      const body = document.body;
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
        horizontalOverflow:
          doc.scrollWidth > doc.clientWidth + 1 ||
          body.scrollWidth > doc.clientWidth + 1,
        viewport: { width: doc.clientWidth, height: doc.clientHeight },
        controlsRect: toRect(controls),
        navRect: toRect(nav),
      };
    });
    result.layout.controlsNavOverlap = rectsOverlap(
      result.layout.controlsRect,
      result.layout.navRect,
    );

    result.buttons = {};
    for (const action of ["exterior", "cutaway", "play", "reset"]) {
      result.buttons[action] = await buttonEvidence(page, action);
    }
    result.initial = await readUiState(page);
    result.checks.noHorizontalOverflow = !result.layout.horizontalOverflow;
    result.checks.controlsNotCoveredByBottomNav =
      !result.layout.controlsNavOverlap;
    result.checks.controlsVisibleAndActionable = Object.values(
      result.buttons,
    ).every(
      (button) =>
        button.count === 1 &&
        button.visible &&
        button.centerUncovered &&
        (button.action === "play" || button.enabled),
    );
    result.checks.defaultExteriorDelegatesLegacyObjects =
      result.initial.viewer.mode === "exterior" &&
      result.initial.viewer.phase === "off" &&
      result.initial.viewer.internalCount === 0 &&
      result.initial.viewer.visibleInternalCount === 0 &&
      result.initial.simulation?.cutawayMode === "exterior" &&
      result.initial.simulation?.visible === false &&
      result.initial.simulation?.resources?.legacyDecorativeCount === 45 &&
      result.initial.simulation?.resources?.legacyDecorativeVisibleCount ===
        0 &&
      result.initial.host.mode === "exterior" &&
      result.initial.host.phase === "off" &&
      result.initial.host.internalCount === 0 &&
      result.initial.host.internalVisibleCount === 0 &&
      result.initial.statusText.includes("内部工艺示意已隐藏") &&
      result.initial.exteriorActive &&
      !result.initial.cutawayActive &&
      result.initial.playDisabled;

    const cutawayButton = page.locator(
      'button[data-cutaway-action="cutaway"]',
    );
    await cutawayButton.click({ timeout: 10_000 });
    await page.waitForFunction(
      () => {
        const state =
          window.__BF_CAD_FURNACE_VIEWER?.getCutawayState?.();
        const simulation =
          window.__BF_CAD_FURNACE_VIEWER
            ?.getInternalSimulationState?.();
        return (
          state?.mode === "cutaway" &&
          state?.phase === "playing" &&
          state?.internalCount === 0 &&
          state?.visibleInternalCount === 0 &&
          simulation?.cutawayMode === "cutaway" &&
          simulation?.visible === true &&
          simulation?.resources?.legacyDecorativeVisibleCount === 0
        );
      },
      null,
      { timeout: 15_000 },
    );
    await page.waitForFunction(
      () =>
        document
          .querySelector(".cad-cutaway-status")
          ?.textContent?.includes("示意动画播放中"),
      null,
      { timeout: 5_000 },
    );
    result.cutaway = await readUiState(page);
    result.checks.cutawayUsesAuthoritativeRuntime =
      result.cutaway.viewer.mode === "cutaway" &&
      result.cutaway.viewer.phase === "playing" &&
      result.cutaway.viewer.internalCount === 0 &&
      result.cutaway.viewer.visibleInternalCount === 0 &&
      result.cutaway.simulation?.cutawayMode === "cutaway" &&
      result.cutaway.simulation?.visible === true &&
      result.cutaway.simulation?.resources?.legacyDecorativeCount === 45 &&
      result.cutaway.simulation?.resources
        ?.legacyDecorativeVisibleCount === 0 &&
      result.cutaway.viewer.focusObjectCount === 5 &&
      result.cutaway.viewer.focusHiddenCount === 5 &&
      result.cutaway.viewer.cutawayLightsVisible === true &&
      result.cutaway.viewer.cutawayEdgesVisible === true &&
      result.cutaway.viewer.controlsBound === true &&
      result.cutaway.host.mode === "cutaway" &&
      result.cutaway.host.phase === "playing" &&
      result.cutaway.host.internalCount === 0 &&
      result.cutaway.host.internalVisibleCount === 0 &&
      result.cutaway.statusText.includes("内切面：示意动画播放中") &&
      result.cutaway.statusText.includes("工艺示意，非实时断面测量") &&
      result.cutaway.statusActive === "true" &&
      result.cutaway.cutawayActive &&
      result.cutaway.playText.trim() === "暂停" &&
      result.cutaway.playPressed === "true" &&
      !result.cutaway.playDisabled;

    const screenshot = path.join(
      OUTPUT_ROOT,
      `${engine}_${viewport}_cutaway.png`,
    );
    await page.screenshot({ path: screenshot, fullPage: false });
    result.screenshot = screenshot;

    await page
      .locator('button[data-cutaway-action="play"]')
      .click({ timeout: 10_000 });
    try {
      await page.waitForFunction(
        () =>
          window.__BF_CAD_FURNACE_VIEWER?.getCutawayState?.().phase ===
          "paused",
        null,
        { timeout: 5_000 },
      );
    } catch {
      // WebKit narrow viewports can complete the scrolled pointer click
      // without dispatching it. Retry the same enabled DOM control once.
      await page
        .locator('button[data-cutaway-action="play"]')
        .evaluate((button) => button.click());
      await page.waitForFunction(
        () =>
          window.__BF_CAD_FURNACE_VIEWER?.getCutawayState?.().phase ===
          "paused",
        null,
        { timeout: 5_000 },
      );
    }
    result.paused = await readUiState(page);
    result.checks.pauseWorks =
      result.paused.viewer.mode === "cutaway" &&
      result.paused.viewer.phase === "paused" &&
      result.paused.viewer.playing === false &&
      result.paused.viewer.internalCount === 0 &&
      result.paused.viewer.visibleInternalCount === 0 &&
      result.paused.simulation?.cutawayMode === "cutaway" &&
      result.paused.simulation?.visible === true &&
      result.paused.simulation?.resources
        ?.legacyDecorativeVisibleCount === 0 &&
      result.paused.host.phase === "paused" &&
      result.paused.statusText.includes("内切面：示意动画已暂停") &&
      result.paused.playText.trim() === "播放" &&
      result.paused.playPressed === "false";

    await page
      .locator('button[data-cutaway-action="reset"]')
      .click({ timeout: 10_000 });
    await page.waitForFunction(
      () => {
        const state =
          window.__BF_CAD_FURNACE_VIEWER?.getCutawayState?.();
        const simulation =
          window.__BF_CAD_FURNACE_VIEWER
            ?.getInternalSimulationState?.();
        return (
          state?.mode === "exterior" &&
          state?.phase === "off" &&
          state?.visibleInternalCount === 0 &&
          simulation?.cutawayMode === "exterior" &&
          simulation?.visible === false &&
          simulation?.resources?.legacyDecorativeVisibleCount === 0
        );
      },
      null,
      { timeout: 5_000 },
    );
    result.reset = await readUiState(page);
    result.checks.resetWorks =
      result.reset.viewer.mode === "exterior" &&
      result.reset.viewer.phase === "off" &&
      result.reset.viewer.playing === false &&
      result.reset.viewer.internalCount === 0 &&
      result.reset.viewer.visibleInternalCount === 0 &&
      result.reset.simulation?.cutawayMode === "exterior" &&
      result.reset.simulation?.visible === false &&
      result.reset.simulation?.resources?.legacyDecorativeCount === 45 &&
      result.reset.simulation?.resources?.legacyDecorativeVisibleCount ===
        0 &&
      result.reset.viewer.focusHiddenCount === 0 &&
      result.reset.viewer.cutawayLightsVisible === false &&
      result.reset.viewer.cutawayEdgesVisible === false &&
      result.reset.host.mode === "exterior" &&
      result.reset.host.phase === "off" &&
      result.reset.host.internalVisibleCount === 0 &&
      result.reset.statusText.includes("内部工艺示意已隐藏") &&
      result.reset.exteriorActive &&
      !result.reset.cutawayActive &&
      result.reset.playDisabled;

    const expectedHttp = httpErrors.filter((item) =>
      expectedOfflineUrl(item.url),
    );
    const unexpectedHttp = httpErrors.filter(
      (item) => !expectedOfflineUrl(item.url),
    );
    const expectedRequests = failedRequests.filter((item) =>
      expectedOfflineUrl(item.url),
    );
    const benignModelCancellations = failedRequests.filter(
      (item) =>
        item.url.endsWith("/models/gl02_blast_furnace.glb") &&
        (item.error.toUpperCase().includes("ABORTED") ||
          item.error.toUpperCase().includes("CANCEL")),
    );
    const unexpectedRequests = failedRequests.filter(
      (item) =>
        !expectedRequests.includes(item) &&
        !benignModelCancellations.includes(item),
    );
    const expectedNetworkItems = [...expectedHttp, ...expectedRequests];
    const expectedConsole = consoleErrors.filter((message) =>
      expectedOfflineConsole(message, expectedNetworkItems),
    );
    const benignConsole = consoleErrors.filter((message) =>
      message.startsWith(
        "[BABEL] Note: The code generator has deoptimised the styling",
      ),
    );
    const unexpectedConsole = consoleErrors.filter(
      (message) =>
        !expectedConsole.includes(message) &&
        !benignConsole.includes(message),
    );
    result.expectedOffline = [
      ...expectedHttp.map((item) => ({ kind: "http", ...item })),
      ...expectedRequests.map((item) => ({ kind: "request", ...item })),
      ...expectedConsole.map((message) => ({ kind: "console", message })),
    ];
    result.benignRuntime = [
      ...benignModelCancellations.map((item) => ({
        kind: "cancelled_duplicate_model_request_after_successful_load",
        ...item,
      })),
      ...benignConsole.map((message) => ({
        kind: "babel_large_inline_script_notice",
        message,
      })),
    ];
    result.consoleErrors = unexpectedConsole;
    result.unexpectedHttpErrors = unexpectedHttp;
    result.unexpectedRequestFailures = unexpectedRequests;
    result.checks.noPageErrors = pageErrors.length === 0;
    result.checks.noUnexpectedConsoleErrors =
      unexpectedConsole.length === 0;
    result.checks.noUnexpectedResourceErrors =
      unexpectedHttp.length === 0 && unexpectedRequests.length === 0;
    result.ok = Object.values(result.checks).every(Boolean);
  } catch (error) {
    result.failure = error.stack || String(error);
    try {
      const screenshot = path.join(
        OUTPUT_ROOT,
        `${engine}_${viewport}_FAIL.png`,
      );
      await page.screenshot({ path: screenshot, fullPage: false });
      result.screenshot = screenshot;
    } catch {
      // Preserve the original failure.
    }
  } finally {
    await context.close();
  }
  return result;
}

function createMarkdown(manifest) {
  const mark = (value) => (value ? "通过" : "失败");
  const lines = [
    "# GL02 内切面 Firefox / WebKit 代表视口验收",
    "",
    `- 结果：${manifest.summary.passed}/${manifest.summary.total} 通过；${manifest.summary.blockedEngines} 个引擎阻塞。`,
    "- 范围：旧 45 个装饰性炉内对象始终隐藏；内切面只启用权威炉内仿真运行时；暂停与复位；控制按钮；横向溢出；页面、控制台和资源错误。",
    "- 离线边界：静态页面下仅 8767 WebSocket、`/api/*` 和 favicon 失败记为预期离线，不屏蔽模型、脚本或其他资源错误。",
    `- Playwright：${manifest.playwrightVersion}`,
    "",
    "| 引擎 | 视口 | 结果 | 旧对象委托/隐藏 | 权威炉内运行时/文案 | 暂停 | 复位 | 控件 | 无横向溢出 | 无非预期错误 |",
    "|---|---|---|---|---|---|---|---|---|---|",
  ];
  for (const result of manifest.results) {
    const checks = result.checks || {};
    const clean =
      checks.noPageErrors &&
      checks.noUnexpectedConsoleErrors &&
      checks.noUnexpectedResourceErrors;
    lines.push(
      `| ${result.engine} | ${result.viewport} | ${mark(result.ok)} | ` +
        `${mark(checks.defaultExteriorDelegatesLegacyObjects)} | ` +
        `${mark(checks.cutawayUsesAuthoritativeRuntime)} | ` +
        `${mark(checks.pauseWorks)} | ${mark(checks.resetWorks)} | ` +
        `${mark(checks.controlsVisibleAndActionable)} | ` +
        `${mark(checks.noHorizontalOverflow)} | ${mark(clean)} |`,
    );
  }
  if (manifest.blocked.length > 0) {
    lines.push("", "## 环境阻塞", "");
    for (const item of manifest.blocked) {
      lines.push(
        `- ${item.engine}：${item.reason}；尝试路径 \`${item.executable}\``,
      );
    }
  }
  lines.push("");
  return lines.join("\n");
}

async function main() {
  if (!fs.existsSync(FRONTEND_ROOT)) {
    throw new Error(`frontend root not found: ${FRONTEND_ROOT}`);
  }
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const { server, baseUrl } = await startStaticServer();
  const results = [];
  const blocked = [];
  const engineInfo = {};

  try {
    for (const engine of ENGINES) {
      const browserType = playwright[engine];
      const bundled = browserType.executablePath();
      const executable = fs.existsSync(bundled)
        ? bundled
        : FALLBACK_EXECUTABLES[engine];
      engineInfo[engine] = {
        bundledExecutable: bundled,
        selectedExecutable: executable,
        selectedExecutableExists: fs.existsSync(executable),
      };
      if (!fs.existsSync(executable)) {
        blocked.push({
          engine,
          reason: "未找到可执行的 Playwright 浏览器",
          executable,
        });
        continue;
      }
      let browser;
      try {
        browser = await browserType.launch({
          headless: true,
          executablePath: executable,
          timeout: 30_000,
        });
        engineInfo[engine].browserVersion = browser.version();
        for (const [width, height] of VIEWPORTS) {
          const result = await runViewport(
            browser,
            engine,
            baseUrl,
            width,
            height,
          );
          results.push(result);
          process.stdout.write(
            `${engine} ${width}x${height}: ${
              result.ok ? "PASS" : "FAIL"
            }\n`,
          );
        }
      } catch (error) {
        blocked.push({
          engine,
          reason: `浏览器启动失败：${error.message || error}`,
          executable,
        });
      } finally {
        if (browser) await browser.close();
      }
    }
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const expectedCases = ENGINES.length * VIEWPORTS.length;
  const passed = results.filter((result) => result.ok).length;
  const packageVersion = require(path.join(
    PLAYWRIGHT_PATH,
    "package.json",
  )).version;
  const manifest = {
    generatedAt: new Date().toISOString(),
    scope:
      "Firefox/WebKit GL02 cutaway representative viewport matrix",
    staticDataSource: true,
    expectedOfflinePolicy:
      "Only 127.0.0.1:8767 WebSocket, /api/* and favicon failures are expected offline.",
    playwrightVersion: packageVersion,
    engines: engineInfo,
    summary: {
      expectedCases,
      total: results.length,
      passed,
      failed: results.length - passed,
      blockedEngines: blocked.length,
      ok:
        blocked.length === 0 &&
        results.length === expectedCases &&
        passed === expectedCases,
    },
    blocked,
    results,
  };
  fs.writeFileSync(
    path.join(OUTPUT_ROOT, "manifest.json"),
    JSON.stringify(manifest, null, 2),
    "utf8",
  );
  fs.writeFileSync(
    path.join(OUTPUT_ROOT, "report.md"),
    createMarkdown(manifest),
    "utf8",
  );
  process.stdout.write(
    `manifest: ${path.join(OUTPUT_ROOT, "manifest.json")}\n`,
  );
  process.exitCode = manifest.summary.ok ? 0 : 1;
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 2;
});
