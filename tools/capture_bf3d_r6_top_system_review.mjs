import { mkdir } from "node:fs/promises";
import path from "node:path";

const playwrightModule = await import(
  process.env.BF_PLAYWRIGHT_CORE_URL || "playwright-core"
);
const { chromium } = playwrightModule;

const workspace = process.cwd();
const screenshotDir = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1",
  "screenshots",
);
const overviewOutput = path.join(screenshotDir, "r6_top_feed_gas_cleaning_overview.png");
const detailOutput = path.join(screenshotDir, "r6_top_feed_gas_cleaning_detail.png");
const url =
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/" +
  "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/preview/";
const executablePath =
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 120_000 });
  await page.waitForFunction(
    () => window.__BF3D_GLB_IMG2THREEJS_BRIDGE__?.passed === true,
    null,
    { timeout: 120_000 },
  );
  await page.locator("#mode-hybrid").click();
  await page.locator("#focus-top-system").click();
  await page.waitForTimeout(700);
  await page.locator("#viewport").screenshot({ path: overviewOutput });

  const canvas = page.locator("#scene");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("无法取得 R6 三维画布");
  await page.mouse.move(box.x + box.width * .48, box.y + box.height * .48);
  await page.mouse.wheel(0, -520);
  await page.mouse.move(box.x + box.width * .42, box.y + box.height * .46);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .56, box.y + box.height * .42, { steps: 16 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  await page.locator("#viewport").screenshot({ path: detailOutput });

  const contract = await page.evaluate(
    () => window.__BF3D_GLB_IMG2THREEJS_BRIDGE__,
  );
  const result = {
    overviewOutput,
    detailOutput,
    contract: {
      passed: contract?.passed,
      schema: contract?.schema,
      topFeedGasCleaningSchema: contract?.topFeedGasCleaningSchema,
      fittedConveyorSystemCount: contract?.fittedConveyorSystemCount,
      fittedConveyorBeltCount: contract?.fittedConveyorBeltCount,
      fittedConveyorRollerCount: contract?.fittedConveyorRollerCount,
      fittedConveyorTrestleCount: contract?.fittedConveyorTrestleCount,
      fittedTopGasUptakeCount: contract?.fittedTopGasUptakeCount,
      fittedGasDuctCount: contract?.fittedGasDuctCount,
      fittedGravityDustCatcherCount: contract?.fittedGravityDustCatcherCount,
      fittedFineDustCollectorCount: contract?.fittedFineDustCollectorCount,
      fittedDustHopperCount: contract?.fittedDustHopperCount,
      fittedExternalProcessSupportCount: contract?.fittedExternalProcessSupportCount,
      hybridSuppressedEquipmentCount: contract?.hybridSuppressedEquipmentCount,
    },
    consoleErrors,
    pageErrors,
  };
  result.passed =
    consoleErrors.length === 0 &&
    pageErrors.length === 0 &&
    result.contract.passed === true &&
    result.contract.schema === "bf3d.glb_img2threejs_bridge.runtime.v6" &&
    result.contract.topFeedGasCleaningSchema === "bf3d.external_top_feed_gas_cleaning.v1" &&
    result.contract.fittedConveyorSystemCount === 1 &&
    result.contract.fittedConveyorBeltCount === 1 &&
    result.contract.fittedConveyorRollerCount === 18 &&
    result.contract.fittedConveyorTrestleCount === 4 &&
    result.contract.fittedTopGasUptakeCount === 4 &&
    result.contract.fittedGasDuctCount === 3 &&
    result.contract.fittedGravityDustCatcherCount === 1 &&
    result.contract.fittedFineDustCollectorCount === 1 &&
    result.contract.fittedDustHopperCount === 5 &&
    result.contract.fittedExternalProcessSupportCount === 16 &&
    result.contract.hybridSuppressedEquipmentCount === 3;
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  if (!result.passed) process.exitCode = 1;
} finally {
  await browser.close();
}
