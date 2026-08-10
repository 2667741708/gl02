#!/usr/bin/env node
/**
 * Read-only live smoke check for the standalone foreman trend page.
 * The local 8092/8767 stack must already be running with --db-profile 22012.
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const OUTPUT_DIR = path.join(ROOT, 'logs', 'foreman_trend_preview_20260805');
const URL = 'http://127.0.0.1:8092/foreman_trend_preview.html?ws_port=8767&minutes=90';

async function launchBrowser() {
  try {
    return await chromium.launch({ channel: 'msedge', headless: true });
  } catch (error) {
    return chromium.launch({
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      headless: true
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
    const metricRows = [...document.querySelectorAll('.metric-cell')].map(cell => ({
      label: cell.querySelector('.metric-label')?.textContent.trim() || '',
      value: cell.querySelector('.metric-value')?.textContent.trim() || '',
      state: cell.dataset.state || ''
    }));
    const metricValues = metricRows.filter(item => item.state === 'value').map(item => item.value);
    return {
      sourceText: document.querySelector('#source-state').textContent.trim(),
      historyStatus: document.documentElement.dataset.foremanHistoryStatus || '',
      pspaceStatus: document.documentElement.dataset.foremanPspaceStatus || '',
      pspaceLastFrame: document.documentElement.dataset.foremanPspaceLastFrame || '',
      dataClock: document.querySelector('#data-clock').textContent.trim(),
      metricValueCount: document.querySelectorAll('.metric-cell[data-state="value"]').length,
      metricMissingCount: document.querySelectorAll('.metric-cell[data-state="missing"]').length,
      metricRows,
      sampleMetricValues: metricValues.slice(0, 8),
      mainSeries: main.getOption().series.length,
      mainDataSeries: main.getOption().series.filter(series => series.data.some(point => point?.[1] !== null)).length,
      lowerSeries: lower.getOption().series.length,
      lowerDataSeries: lower.getOption().series.filter(series => series.data.some(point => point?.[1] !== null)).length,
      requirement: document.documentElement.dataset.requirement
    };
  });

  const screenshot = path.join(OUTPUT_DIR, 'foreman_trend_live_22012_1280x1024.png');
  await page.screenshot({ path: screenshot, fullPage: false });
  result.url = URL;
  result.screenshot = screenshot;
  result.pageErrors = pageErrors;
  result.consoleErrors = consoleErrors;
  const report = path.join(OUTPUT_DIR, 'live_22012_report.json');
  fs.writeFileSync(report, JSON.stringify(result, null, 2), 'utf8');
  await browser.close();

  const failures = [];
  if (result.historyStatus !== 'live') failures.push('8767 WebSocket did not connect');
  if (!result.dataClock || result.dataClock.endsWith('--')) failures.push('live data timestamp missing');
  if (result.metricValueCount < 1 || result.metricValueCount >= 49) failures.push('live metric coverage is unexpected');
  if (result.mainSeries !== 12 || result.mainDataSeries !== 12) failures.push('main chart live data incomplete');
  if (result.lowerSeries !== 5 || result.lowerDataSeries < 2) failures.push('lower chart live data incomplete');
  if (result.requirement !== 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805') failures.push('requirement marker missing');
  if (result.pageErrors.length || result.consoleErrors.length) failures.push('browser errors detected');
  if (failures.length) {
    console.error(JSON.stringify({ status: 'FAIL', failures, report, result }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ status: 'PASS', report, result }, null, 2));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
