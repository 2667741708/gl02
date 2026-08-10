#!/usr/bin/env node
/**
 * Read-only production smoke check for the standalone foreman trend page.
 *
 * Verifies the page served by 220.12:8093 and its existing 8768 minute-data
 * WebSocket. It never writes to the page, database, or remote services.
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const OUTPUT_DIR = path.join(ROOT, 'logs', 'foreman_trend_preview_20260805');
const URL = 'http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768&pspace_ws_port=8770&minutes=90&verify=20260805';

async function launchBrowser() {
  try {
    return await chromium.launch({ channel: 'msedge', headless: true });
  } catch (_) {
    return chromium.launch({
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      headless: true,
    });
  }
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await launchBrowser();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1024 }, deviceScaleFactor: 1 });
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForFunction(() => ['is-live', 'is-degraded'].some(className => document.querySelector('#source-state')?.classList.contains(className)), null, { timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll('.metric-cell[data-state="value"]').length > 0, null, { timeout: 30000 });
  await page.waitForTimeout(1200);

  const result = await page.evaluate(() => {
    const main = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const lower = echarts.getInstanceByDom(document.querySelector('#lower-trend-chart'));
    const countDataSeries = chart => chart.getOption().series.filter(series =>
      series.data.some(point => point?.[1] !== null)).length;
    return {
      sourceText: document.querySelector('#source-state')?.textContent.trim(),
      historyStatus: document.documentElement.dataset.foremanHistoryStatus || '',
      pspaceStatus: document.documentElement.dataset.foremanPspaceStatus || '',
      pspaceLastFrame: document.documentElement.dataset.foremanPspaceLastFrame || '',
      dataClock: document.querySelector('#data-clock')?.textContent.trim(),
      metricValueCount: document.querySelectorAll('.metric-cell[data-state="value"]').length,
      metricMissingCount: document.querySelectorAll('.metric-cell[data-state="missing"]').length,
      mainSeries: main.getOption().series.length,
      mainDataSeries: countDataSeries(main),
      lowerSeries: lower.getOption().series.length,
      lowerDataSeries: countDataSeries(lower),
      requirement: document.documentElement.dataset.requirement,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
  result.url = URL;
  result.pageErrors = pageErrors;
  result.consoleErrors = consoleErrors;
  const screenshot = path.join(OUTPUT_DIR, 'foreman_trend_remote_8093_1280x1024.png');
  await page.screenshot({ path: screenshot, fullPage: false });
  result.screenshot = screenshot;
  await browser.close();

  const failures = [];
  if (result.historyStatus !== 'live') failures.push('8768 history WebSocket did not connect');
  if (result.metricValueCount < 1 || result.metricValueCount >= 49) failures.push('unexpected live metric coverage');
  if (result.mainSeries !== 12 || result.mainDataSeries !== 12) failures.push('main trend data is incomplete');
  if (result.lowerSeries !== 5 || result.lowerDataSeries !== 5) failures.push('lower trend data is incomplete');
  if (result.requirement !== 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805') failures.push('requirement marker missing');
  if (result.horizontalOverflow) failures.push('horizontal overflow detected');
  if (pageErrors.length || consoleErrors.length) failures.push('browser errors detected');
  const report = path.join(OUTPUT_DIR, 'remote_8093_live_report.json');
  fs.writeFileSync(report, JSON.stringify({ status: failures.length ? 'FAIL' : 'PASS', failures, result }, null, 2), 'utf8');
  if (failures.length) throw new Error(`${failures.join('; ')}; report: ${report}`);
  console.log(JSON.stringify({ status: 'PASS', report, result }, null, 2));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
