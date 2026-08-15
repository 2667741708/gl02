const fs = require('fs');
let playwright;
try { playwright = require('playwright'); }
catch (_) { playwright = require('C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }

const url = process.argv[2] || 'http://10.30.220.12:8093/?cb=abc33-20260811-overview-entry-r1#overview';
const screenshot = 'logs/abc33_overview_entry_standard/production-8093-overview-entry.png';

(async () => {
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('.overview-furnace-panel-v12 .abc33-entry-overview', { timeout: 20000 });
  const before = await page.evaluate(() => {
    const entry = document.querySelector('.abc33-entry-overview');
    return {
      inHeader: Boolean(entry?.closest('.overview-furnace-panel-v12 > .panel-head')),
      position: entry ? getComputedStyle(entry).position : null,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    };
  });
  await page.click('.abc33-entry-overview', { timeout: 5000 });
  await page.waitForSelector('#abc-furnace-rules-production', { state: 'visible', timeout: 10000 });
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => ({
    cards: document.querySelectorAll('#abc-furnace-rules-production .abc33-card').length,
    title: document.querySelector('#abc-furnace-rules-production .abc33-head h2')?.textContent?.trim() || '',
    closeText: document.querySelector('#abc-furnace-rules-production .abc33-close')?.textContent?.trim() || '',
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }));
  await page.screenshot({ path: screenshot, fullPage: false });
  await browser.close();
  const ok = before.inHeader && before.position !== 'fixed' && before.overflow === 0 && after.cards === 33 && after.closeText === '关闭总览' && after.overflow === 0 && errors.length === 0;
  process.stdout.write(JSON.stringify({ ok, url, before, after, errors, screenshot }, null, 2));
  process.exit(ok ? 0 : 1);
})().catch(error => { console.error(error); process.exit(1); });
