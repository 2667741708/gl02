const fs = require("fs");
const path = require("path");
const { chromium } = require(
  "C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
);

const outputDir = path.resolve("logs/8094_billboard_zoom_20260726");
fs.mkdirSync(outputDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
    args: ["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist"],
  });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  let result;
  try {
    await page.goto("http://10.30.220.12:8094/#overview", {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
    await page.waitForFunction(
      () =>
        window.__BF_CAD_FURNACE_VIEWER?.camera &&
        window.__BF_CAD_FURNACE_VIEWER?.billboardCenter &&
        document.querySelector(".cad-furnace-viewer")?.dataset.wheelZoom ===
          "enabled",
      null,
      { timeout: 90000 },
    );
    await page.waitForTimeout(2500);
    const before = await page.evaluate(() => {
      const host = document.querySelector(".cad-furnace-viewer");
      const stage = host.closest(".layered-cad-stage");
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const camera = viewer.camera;
      return {
        hostWidth: host.getBoundingClientRect().width,
        stageWidth: stage.getBoundingClientRect().width,
        widthRatio:
          host.getBoundingClientRect().width /
          stage.getBoundingClientRect().width,
        distance: camera.position.distanceTo(viewer.billboardCenter),
        wheelZoom: host.dataset.wheelZoom,
        scriptVersion: [...document.scripts]
          .map((script) => script.src)
          .find((src) =>
            src.includes("bf3d-furnace-body-billboard-adapter"),
          ),
      };
    });
    await page.evaluate(() => {
      const canvas = document.querySelector(".cad-furnace-viewer canvas");
      canvas.dispatchEvent(
        new WheelEvent("wheel", {
          deltaY: -220,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    await page.waitForTimeout(500);
    const after = await page.evaluate(() => {
      const host = document.querySelector(".cad-furnace-viewer");
      const viewer = window.__BF_CAD_FURNACE_VIEWER;
      const camera = viewer.camera;
      return {
        distance: camera.position.distanceTo(viewer.billboardCenter),
        lastWheelZoomAt: host.dataset.lastWheelZoomAt || "",
      };
    });
    await page.locator(".layered-cad-stage").screenshot({
      path: path.join(outputDir, "chromium_1366x768_furnace.png"),
    });
    result = {
      schema: "bf3d.billboard.zoom.acceptance.v1",
      checkedAt: new Date().toISOString(),
      before,
      after,
      errors,
      widthPassed: before.widthRatio >= 0.995,
      zoomPassed:
        Boolean(after.lastWheelZoomAt) && after.distance < before.distance * 0.98,
    };
    result.passed =
      result.widthPassed &&
      result.zoomPassed &&
      before.scriptVersion.includes("20260726-viewport-");
  } finally {
    await browser.close();
  }
  fs.writeFileSync(
    path.join(outputDir, "result.json"),
    JSON.stringify(result, null, 2),
    "utf8",
  );
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exitCode = result.passed ? 0 : 1;
})();
