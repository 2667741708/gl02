import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const playwrightModule = await import(
  process.env.BF_PLAYWRIGHT_CORE_URL || "playwright-core"
);
const { chromium } = playwrightModule;

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const mockPspace = process.argv.includes("--mock-pspace");
const workspace = process.cwd();
const assetFolder = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "模型资产库",
  "09_高炉本体133点Billboard",
);
const url = argument(
  "--url",
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/" +
    "%E6%A8%A1%E5%9E%8B%E8%B5%84%E4%BA%A7%E5%BA%93/" +
    "09_%E9%AB%98%E7%82%89%E6%9C%AC%E4%BD%93133%E7%82%B9Billboard/preview/",
);
const output = path.resolve(
  argument("--output", path.join(assetFolder, "billboard_validation_report.json")),
);
const screenshot = path.resolve(
  argument("--screenshot", path.join(assetFolder, "网页预览.png")),
);
const mobileScreenshot = path.resolve(
  argument(
    "--mobile-screenshot",
    path.join(assetFolder, "reports", "chromium_390x844.png"),
  ),
);
const executablePath = argument(
  "--chromium",
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
);

await mkdir(path.dirname(output), { recursive: true });
await mkdir(path.dirname(screenshot), { recursive: true });
await mkdir(path.dirname(mobileScreenshot), { recursive: true });

const browser = await chromium.launch({ headless: true, executablePath });

async function runViewport(viewport, screenshotPath, exerciseInteractions) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  if (mockPspace) {
    await page.addInitScript(() => {
      class BillboardPspaceWebSocket extends EventTarget {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;

        constructor(url) {
          super();
          this.url = String(url);
          this.readyState = BillboardPspaceWebSocket.CONNECTING;
          setTimeout(async () => {
            this.readyState = BillboardPspaceWebSocket.OPEN;
            this.dispatchEvent(new Event("open"));
            const response = await fetch(
              new URL("../sensor_billboards.v1.json", window.location.href),
              { cache: "no-store" },
            );
            const manifest = await response.json();
            const values = {};
            const point_meta = {};
            manifest.points.forEach((point, index) => {
              const id = point.canonical_id || point.data_binding_key || point.id;
              values[id] = Number((100 + index / 10).toFixed(1));
              point_meta[id] = {
                timestamp: "2026/07/26 12:00:05.000",
                quality: "Good",
              };
            });
            this.dispatchEvent(
              new MessageEvent("message", {
                data: JSON.stringify({
                  type: "tick",
                  timestamp: "2026-07-26T12:00:05+08:00",
                  values,
                  point_meta,
                  data_quality: {
                    source: "pspace",
                    billboard_expected: 133,
                    billboard_mapped: 133,
                    billboard_missing: [],
                  },
                }),
              }),
            );
          }, 50);
        }

        send() {}

        close() {
          this.readyState = BillboardPspaceWebSocket.CLOSED;
          this.dispatchEvent(new CloseEvent("close"));
        }
      }
      window.WebSocket = BillboardPspaceWebSocket;
    });
  }
  const consoleErrors = [];
  const pageErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 120_000 });
    await page.waitForFunction(
      () =>
        document.body.dataset.loadState === "ready" &&
        window.__BF3D_FURNACE_BODY_BILLBOARD__?.passed === true,
      null,
      { timeout: 120_000 },
    );
    if (mockPspace) {
      await page.waitForFunction(
        () =>
          window.__BF3D_BILLBOARD_PSPACE_LIVE__?.status === "connected" &&
          window.__BF3D_BILLBOARD_PSPACE_LIVE__?.pointCount === 133 &&
          window.__BF3D_BILLBOARD_PSPACE_LIVE__?.validPointCount === 133,
        null,
        { timeout: 30_000 },
      );
    }
    const contract = await page.evaluate(() => window.__BF3D_FURNACE_BODY_BILLBOARD__);
    const pspaceLive = await page.evaluate(
      () => window.__BF3D_BILLBOARD_PSPACE_LIVE__ || null,
    );
    const layout = await page.evaluate(() => ({
      viewportWidth: document.documentElement.clientWidth,
      viewportHeight: document.documentElement.clientHeight,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      horizontalOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      canvasWidth: document.querySelector("#scene")?.getBoundingClientRect().width || 0,
      canvasHeight: document.querySelector("#scene")?.getBoundingClientRect().height || 0,
    }));
    const interactions = {
      exercised: exerciseInteractions,
      formalOnlyOffVisibleCount: null,
      bothOffVisibleCount: null,
      restoredVisibleCount: null,
      searchResultCount: null,
      selectedId: null,
      adapterUpdate: null,
      selectedValue: null,
      canonicalAdapterUpdate: null,
      canonicalSelectedValue: null,
    };
    if (exerciseInteractions) {
      await page.locator("#toggle-formal").uncheck();
      interactions.formalOnlyOffVisibleCount =
        await page.locator("#visible-count").textContent();
      await page.locator("#toggle-pressure").uncheck();
      interactions.bothOffVisibleCount = await page.locator("#visible-count").textContent();
      await page.locator("#toggle-formal").check();
      await page.locator("#toggle-pressure").check();
      interactions.restoredVisibleCount = await page.locator("#visible-count").textContent();
      await page.locator("#sensor-search").fill("DP_total");
      interactions.searchResultCount = await page.locator(".sensor-item").count();
      await page.locator(".sensor-item").first().click();
      interactions.selectedId = await page.locator("#selection-id").textContent();
      interactions.adapterUpdate = await page.evaluate(() =>
        window.BF3D_BILLBOARD_ADAPTER.updateValues([
          { id: "SENSOR_DP_total", value: 156.2, unit: "kPa" },
        ]),
      );
      interactions.selectedValue = await page.locator("#selection-value").textContent();
      if (contract.locale === "zh-CN") {
        interactions.canonicalAdapterUpdate = await page.evaluate(() =>
          window.BF3D_BILLBOARD_ADAPTER.updateValues([
            { canonical_id: "DP_total", value: 157.3, unit: "kPa" },
          ]),
        );
        interactions.canonicalSelectedValue =
          await page.locator("#selection-value").textContent();
      }
      await page.evaluate(() => window.BF3D_BILLBOARD_ADAPTER.clearValues());
      await page.locator("#sensor-search").fill("");
      await page.locator("#reset-view").click();
      // Capture the reusable asset screenshot from a clean default state after the
      // interaction assertions have already passed.
      await page.reload({ waitUntil: "networkidle", timeout: 120_000 });
      await page.waitForFunction(
        () =>
          document.body.dataset.loadState === "ready" &&
          window.__BF3D_FURNACE_BODY_BILLBOARD__?.passed === true,
        null,
        { timeout: 120_000 },
      );
    }
    await page.screenshot({ path: screenshotPath, fullPage: false });
    return {
      viewport,
      contract,
      pspaceLive,
      layout,
      interactions,
      consoleErrors,
      pageErrors,
      passed:
        contract.passed === true &&
        contract.formalBillboardCount === 115 &&
        contract.staticPressureBillboardCount === 18 &&
        contract.totalBillboardCount === 133 &&
        contract.spriteCount === 133 &&
        contract.allBillboardsUseThreeSprite === true &&
        contract.embeddedFormalSensorCount === 0 &&
        contract.embeddedStaticPressureCount === 0 &&
        contract.externalSystemNodeCount === 0 &&
        contract.nonPhysicalBandCount === 0 &&
        contract.realtimeAdapterInstalled === true &&
        (!mockPspace ||
          (pspaceLive?.status === "connected" &&
            pspaceLive?.pointCount === 133 &&
            pspaceLive?.validPointCount === 133)) &&
        layout.horizontalOverflow === false &&
        layout.canvasWidth > 0 &&
        layout.canvasHeight > 0 &&
        (!exerciseInteractions ||
          (interactions.formalOnlyOffVisibleCount?.trim() === "18 / 133" &&
            interactions.bothOffVisibleCount?.trim() === "0 / 133" &&
            interactions.restoredVisibleCount?.trim() === "133 / 133" &&
            interactions.searchResultCount === 1 &&
            interactions.selectedId?.trim() === "SENSOR_DP_total" &&
            interactions.adapterUpdate?.updated === 1 &&
            interactions.selectedValue?.trim() === "156.2kPa" &&
            (contract.locale !== "zh-CN" ||
              (interactions.canonicalAdapterUpdate?.updated === 1 &&
                interactions.canonicalSelectedValue?.trim() === "157.3kPa")))) &&
        consoleErrors.length === 0 &&
        pageErrors.length === 0,
    };
  } finally {
    await context.close();
  }
}

try {
  const desktop = await runViewport({ width: 1440, height: 900 }, screenshot, true);
  const mobile = await runViewport({ width: 390, height: 844 }, mobileScreenshot, false);
  const report = {
    schema: "bf3d.furnace_body_billboard_validation.v1",
    generatedAt: new Date().toISOString(),
    url,
    screenshot,
    mobileScreenshot,
    desktop,
    mobile,
    passed: desktop.passed && mobile.passed,
  };
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify({
    output,
    desktopPassed: desktop.passed,
    mobilePassed: mobile.passed,
    modelNodes: desktop.contract.modelNodeCount,
    modelMeshes: desktop.contract.modelMeshCount,
    billboards: desktop.contract.totalBillboardCount,
    allUseThreeSprite: desktop.contract.allBillboardsUseThreeSprite,
    passed: report.passed,
  })}\n`);
  if (!report.passed) process.exitCode = 1;
} finally {
  await browser.close();
}
