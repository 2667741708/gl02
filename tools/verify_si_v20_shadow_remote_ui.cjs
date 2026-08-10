const fs = require('fs');
const path = require('path');

function loadPlaywright() {
  const candidates = [
    process.env.CODEX_PLAYWRIGHT_PATH,
    'C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright',
  ].filter(Boolean);
  for (const candidate of candidates) {
    try { return require(candidate); } catch (_) {}
  }
  return require('playwright');
}

const { chromium } = loadPlaywright();
const outputDir = path.resolve('logs/si_v20_shadow_remote_20260808');
fs.mkdirSync(outputDir, { recursive: true });

async function verify(browser, port, viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const url = `http://10.30.220.12:${port}/?si_v20_remote_smoke=20260808`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.locator('.bf-si20-trigger').waitFor({ state: 'visible', timeout: 30000 });
  await page.locator('.bf-si20-trigger').click();
  await page.locator('#bfSiV20ShadowWorkbench.open').waitFor({ state: 'visible', timeout: 15000 });
  await page.locator('[data-role="model-state"]').waitFor({ state: 'visible', timeout: 15000 });
  const status = await page.request.get(`http://10.30.220.12:${port}/api/si-v20/status?limit=2`);
  const statusJson = await status.json();
  await page.locator('[data-tab="history"]').click();
  await page.locator('[data-panel="history"].active').waitFor({ state: 'visible', timeout: 15000 });
  const screenshot = path.join(outputDir, `port${port}_${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: screenshot, fullPage: false });
  const result = await page.evaluate(() => ({
    triggerVisible: !!document.querySelector('.bf-si20-trigger'),
    drawerOpen: document.querySelector('#bfSiV20ShadowWorkbench')?.classList.contains('open') || false,
    historyActive: document.querySelector('[data-panel="history"]')?.classList.contains('active') || false,
    targetInput: !!document.querySelector('#bfSi20Target'),
    replayButton: !!document.querySelector('[data-action="replay"]'),
    horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  }));
  await context.close();
  return {
    port,
    viewport,
    url,
    screenshot,
    statusCode: status.status(),
    statusOk: statusJson.ok === true,
    modelName: statusJson.model?.name,
    auditTableReady: statusJson.audit_table_ready === true,
    errors,
    ...result,
  };
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const port of [8093, 8094]) {
      for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
        results.push(await verify(browser, port, viewport));
      }
    }
  } finally {
    await browser.close();
  }
  const report = path.join(outputDir, 'remote_ui_smoke.json');
  fs.writeFileSync(report, JSON.stringify(results, null, 2), 'utf8');
  console.log(JSON.stringify({ report, results }, null, 2));
  if (results.some(item => !item.statusOk || !item.auditTableReady || !item.triggerVisible || !item.drawerOpen || !item.historyActive || item.horizontalOverflow > 0 || item.errors.length)) {
    process.exitCode = 1;
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
