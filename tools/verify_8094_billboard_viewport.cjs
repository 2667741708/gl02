const fs = require("fs");
const path = require("path");

const playwright = require(
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
);

const URL = process.env.BF_8094_URL || "http://10.30.220.12:8094/#overview";
const OUTPUT_DIR = path.resolve(
  process.env.BF_8094_VIEWPORT_OUTPUT ||
    "logs/8094_billboard_viewport_20260726",
);
const VIEWPORTS = {
  desktop_1280x720: { width: 1280, height: 720 },
  desktop_1366x768: { width: 1366, height: 768 },
  desktop_1440x900: { width: 1440, height: 900 },
  desktop_1546x864: { width: 1546, height: 864 },
  desktop_1920x1080: { width: 1920, height: 1080 },
  tablet_1024x768: { width: 1024, height: 768 },
  tablet_768x1024: { width: 768, height: 1024 },
  mobile_390x844: { width: 390, height: 844 },
  mobile_375x667: { width: 375, height: 667 },
};
const REPRESENTATIVE = [
  "desktop_1920x1080",
  "desktop_1366x768",
  "tablet_768x1024",
  "mobile_390x844",
];
const ENGINES = [
  {
    name: "chromium",
    launcher: playwright.chromium,
    executablePath:
      "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
    viewportNames: Object.keys(VIEWPORTS),
  },
  {
    name: "firefox",
    launcher: playwright.firefox,
    executablePath:
      "C:/Users/hmw20/AppData/Local/ms-playwright/firefox-1532/firefox/firefox.exe",
    viewportNames: REPRESENTATIVE,
  },
  {
    name: "webkit",
    launcher: playwright.webkit,
    executablePath:
      "C:/Users/hmw20/AppData/Local/ms-playwright/webkit-2311/Playwright.exe",
    viewportNames: REPRESENTATIVE,
  },
];

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function inspect(page) {
  return page.evaluate(() => {
    const host = document.querySelector(".cad-furnace-viewer");
    const stage = host?.closest(".layered-cad-stage");
    const canvas = host?.querySelector("canvas");
    const hostRect = host?.getBoundingClientRect();
    const stageRect = stage?.getBoundingClientRect();
    const canvasRect = canvas?.getBoundingClientRect();
    const runtime = window.__BF3D_VIEWPORT_LAYOUT__ || null;
    const scriptVersion = [...document.scripts]
      .map((script) => script.src)
      .find((src) => src.includes("bf3d-furnace-body-billboard-adapter"));
    return {
      scriptVersion: scriptVersion || "",
      styleInstalled: Boolean(document.getElementById("bf3d-billboard-full-viewport")),
      billboardStatus: host?.dataset.billboardStatus || "",
      backgroundMode: host?.dataset.backgroundMode || "",
      hasFitButton: Boolean(host?.querySelector(".bf3d-fit-full-model")),
      stage: stageRect
        ? { width: stageRect.width, height: stageRect.height }
        : null,
      host: hostRect ? { width: hostRect.width, height: hostRect.height } : null,
      canvas: canvasRect
        ? { width: canvasRect.width, height: canvasRect.height }
        : null,
      hostToStageWidthRatio:
        stageRect?.width > 0 ? hostRect.width / stageRect.width : null,
      canvasToHostWidthRatio:
        hostRect?.width > 0 && canvasRect
          ? canvasRect.width / hostRect.width
          : null,
      modelInsideViewport: runtime?.modelInsideViewport ?? null,
      modelNdcBounds: runtime?.modelNdcBounds || null,
      fitReason: runtime?.reason || "",
      billboardCount:
        window.__BF_FURNACE_BODY_BILLBOARDS__?.totalBillboardCount ?? null,
      pspaceStatus: window.__BF3D_BILLBOARD_PSPACE_LIVE__?.status || "",
      pspaceValidPointCount:
        window.__BF3D_BILLBOARD_PSPACE_LIVE__?.validPointCount ?? null,
      horizontalOverflow:
        Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) -
        window.innerWidth,
    };
  });
}

async function verifyEngine(config) {
  const launchOptions = {
    headless: true,
    executablePath: config.executablePath,
  };
  if (config.name === "chromium") {
    launchOptions.args = [
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--ignore-gpu-blocklist",
    ];
  }
  const browser = await config.launcher.launch(launchOptions);
  const context = await browser.newContext({
    viewport: VIEWPORTS.desktop_1920x1080,
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const engineResult = {
    engine: config.name,
    browserVersion: browser.version(),
    url: URL,
    runtimeReady: false,
    viewports: [],
    pageErrors,
    consoleErrors,
  };
  try {
    await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForSelector(".cad-furnace-viewer", {
      state: "visible",
      timeout: 45000,
    });
    await page.waitForFunction(
      () => Boolean(document.getElementById("bf3d-billboard-full-viewport")),
      null,
      { timeout: 30000 },
    );
    try {
      await page.waitForFunction(
        () =>
          window.__BF3D_VIEWPORT_LAYOUT__?.modelInsideViewport === true &&
          window.__BF_FURNACE_BODY_BILLBOARDS__?.totalBillboardCount === 133,
        null,
        { timeout: 60000 },
      );
      engineResult.runtimeReady = true;
    } catch (error) {
      engineResult.runtimeWaitError = String(error);
    }

    for (const viewportName of config.viewportNames) {
      const viewport = VIEWPORTS[viewportName];
      await page.setViewportSize(viewport);
      await page.waitForTimeout(700);
      const audit = await inspect(page);
      const layoutPassed =
        audit.styleInstalled &&
        audit.hostToStageWidthRatio >= 0.995 &&
        (audit.canvasToHostWidthRatio === null ||
          audit.canvasToHostWidthRatio >= 0.995);
      const modelPassed =
        !engineResult.runtimeReady || audit.modelInsideViewport === true;
      engineResult.viewports.push({
        name: viewportName,
        viewport,
        ...audit,
        layoutPassed,
        modelPassed,
        passed: layoutPassed && modelPassed,
      });
      if (
        config.name === "chromium" &&
        ["desktop_1366x768", "desktop_1920x1080"].includes(viewportName)
      ) {
        await page
          .locator(".layered-cad-stage")
          .screenshot({
            path: path.join(
              OUTPUT_DIR,
              `${config.name}_${viewportName}_furnace.png`,
            ),
          });
      }
    }
  } finally {
    await context.close();
    await browser.close();
  }
  engineResult.passed =
    engineResult.viewports.length === config.viewportNames.length &&
    engineResult.viewports.every((item) => item.passed) &&
    (config.name !== "chromium" || engineResult.runtimeReady);
  return engineResult;
}

(async () => {
  const results = [];
  for (const engine of ENGINES) {
    try {
      results.push(await verifyEngine(engine));
    } catch (error) {
      results.push({
        engine: engine.name,
        passed: false,
        fatalError: String(error?.stack || error),
      });
    }
  }
  const report = {
    schema: "bf3d.billboard.viewport.acceptance.v1",
    generatedAt: new Date().toISOString(),
    url: URL,
    expectedCacheVersion: "20260726-viewport-wheel-r6",
    engines: results,
    passed: results.length === ENGINES.length && results.every((item) => item.passed),
  };
  const reportPath = path.join(OUTPUT_DIR, "result.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exitCode = report.passed ? 0 : 1;
})();
