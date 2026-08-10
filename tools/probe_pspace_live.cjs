const { chromium } = require('playwright');

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const consoleErrors = [];
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  await page.goto('http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768&pspace_ws_port=8770&verify=pspace-debug', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(12000);
  const snapshot = await page.evaluate(() => ({
    source: document.querySelector('#source-state')?.textContent || '',
    historyStatus: document.documentElement.dataset.foremanHistoryStatus || '',
    pspaceStatus: document.documentElement.dataset.foremanPspaceStatus || '',
    pspaceLastFrame: document.documentElement.dataset.foremanPspaceLastFrame || '',
    values: document.querySelectorAll('.metric-cell[data-state="value"]').length,
    missing: document.querySelectorAll('.metric-cell[data-state="missing"]').length,
  }));
  console.log(JSON.stringify({ snapshot, errors, consoleErrors }, null, 2));
  await browser.close();
}

main().catch(error => { console.error(error); process.exitCode = 1; });
