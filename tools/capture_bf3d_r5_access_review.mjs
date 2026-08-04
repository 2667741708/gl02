import { mkdir } from "node:fs/promises";
import path from "node:path";

const playwrightModule = await import(
  process.env.BF_PLAYWRIGHT_CORE_URL || "playwright-core"
);
const { chromium } = playwrightModule;

const workspace = process.cwd();
const output = path.join(
  workspace,
  "PT",
  "高炉3D模型",
  "work",
  "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1",
  "screenshots",
  "r5_access_closeup.png",
);
const ladderOutput = path.join(
  path.dirname(output),
  "r5_access_ladder_closeup.png",
);
const url =
  "http://127.0.0.1:8096/PT/%E9%AB%98%E7%82%893D%E6%A8%A1%E5%9E%8B/work/" +
  "WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/preview/";
const executablePath =
  "C:/Users/hmw20/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

await mkdir(path.dirname(output), { recursive: true });
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
  await page.locator("#focus-layers").click();
  const canvas = page.locator("#scene");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("无法取得 R5 三维画布");
  await page.mouse.move(box.x + box.width * .48, box.y + box.height * .5);
  await page.mouse.wheel(0, -720);
  await page.mouse.move(box.x + box.width * .42, box.y + box.height * .46);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .58, box.y + box.height * .43, { steps: 18 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  await page.locator("#viewport").screenshot({ path: output });
  await page.mouse.move(box.x + box.width * .3, box.y + box.height * .46);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .78, box.y + box.height * .46, { steps: 28 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  await page.locator("#viewport").screenshot({ path: ladderOutput });
  const contract = await page.evaluate(() => window.__BF3D_GLB_IMG2THREEJS_BRIDGE__);
  const result = {
    output,
    ladderOutput,
    passed:
      consoleErrors.length === 0 &&
      pageErrors.length === 0 &&
      contract?.passed === true &&
      contract?.fittedMaintenancePlatformCount === 7 &&
      contract?.fittedAccessLadderCount === 6,
    consoleErrors,
    pageErrors,
  };
  process.stdout.write(`${JSON.stringify(result)}\n`);
  if (!result.passed) process.exitCode = 1;
} finally {
  await browser.close();
}
