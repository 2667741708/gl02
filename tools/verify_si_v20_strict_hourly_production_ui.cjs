/* Read-only cross-engine smoke against the deployed V20 strict-hourly page. */
const { chromium, firefox, webkit } = require('playwright');

const target = process.env.SI_V20_WORKBENCH_URL || 'http://10.30.220.12:8093/si_v20_workbench.html?cb=20260810-hourly-table-r2';
const chromiumViews = [[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]];
const representative = [[1920,1080],[1366,768],[768,1024],[390,844]];

async function run() {
  const results = [];
  const plans = process.env.SI_V20_SMOKE_COMPACT === '1' ? [
    ['chromium', chromium, [[1366,768]]],
  ] : [
    ['chromium', chromium, chromiumViews],
    ['firefox', firefox, representative],
    ['webkit', webkit, representative],
  ];
  for (const [engine, launcher, views] of plans) {
    const browser = await launcher.launch({headless:true});
    for (const [width,height] of views) {
      const page = await browser.newPage({viewport:{width,height}});
      const errors = [];
      page.on('pageerror', error => errors.push(String(error)));
      await page.goto(target, {waitUntil:'domcontentloaded', timeout:15000});
      await page.waitForTimeout(1200);
      const state = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        strictText: document.querySelector('#strictHourlyStatus')?.textContent?.trim() || '',
        strictButton: !!document.querySelector('#strictHourlyHistoryBtn'),
        strictPredictEnabled: !document.querySelector('#strictHourlyBtn')?.disabled,
        chart: !!document.querySelector('#chart'),
        table: !!document.querySelector('#historyRows'),
        hourlyTable: !!document.querySelector('#hourlyTableRows'),
        hourlyRows: document.querySelectorAll('#hourlyTableRows tr').length,
        hourlyDownload: !!document.querySelector('#downloadHourlyTableBtn'),
      }));
      results.push({engine,viewport:`${width}x${height}`,errors,...state});
      await page.close();
    }
    await browser.close();
  }
  const passed = results.every(item =>
    item.errors.length === 0 && item.overflow <= 1 && item.strictText.includes('独立常开') &&
    item.strictButton && item.strictPredictEnabled && item.chart && item.table &&
    item.hourlyTable && item.hourlyRows > 0 && item.hourlyDownload
  );
  console.log(JSON.stringify({schema:'bf.si.v20.strict-hourly.production-ui.hourly-table.v2',target,passed,results},null,2));
  if (!passed) process.exitCode = 1;
}

run().catch(error => { console.error(error); process.exitCode = 1; });
