const { chromium } = require('playwright');

const URL = 'http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768&pspace_ws_port=8770&minutes=90&inspect=20260808';

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true }).catch(() => chromium.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: true,
  }));
  const page = await browser.newPage({ viewport: { width: 1280, height: 1024 } });
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForFunction(() => document.documentElement.dataset.foremanHistoryStatus === 'live' && document.documentElement.dataset.foremanPspaceStatus === 'live', null, { timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll('.metric-cell[data-state="value"]').length > 0, null, { timeout: 30000 });
  await page.waitForTimeout(2000);
  const result = await page.evaluate(() => ({
    source: document.querySelector('#source-state')?.textContent.trim(),
    rows: [...document.querySelectorAll('.metric-cell')].map(cell => ({
      id: cell.dataset.metric,
      label: cell.querySelector('.metric-label')?.textContent.trim(),
      value: cell.querySelector('.metric-value')?.textContent.trim(),
      state: cell.dataset.state,
      source: cell.dataset.source,
      title: cell.title,
    })),
  }));
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
