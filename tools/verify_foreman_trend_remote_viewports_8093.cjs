#!/usr/bin/env node
/**
 * Cross-engine/viewport acceptance for the deployed 8093 foreman trend page.
 */

const fs = require('fs');
const path = require('path');
const { chromium, firefox, webkit } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const OUTPUT_DIR = path.join(ROOT, 'logs', 'foreman_trend_preview_20260805', 'remote_8093_viewports');
const URL = 'http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768&deploy=20260805_142812';
const DESKTOP = [[1280, 720], [1366, 768], [1440, 900], [1546, 864], [1920, 1080]];
const NARROW = [[1024, 768], [768, 1024], [390, 844], [375, 667]];
const REPRESENTATIVE = [[1920, 1080], [1366, 768], [768, 1024], [390, 844]];
const browsers = new Set();

async function launchEdge() {
  try {
    return await chromium.launch({ channel: 'msedge', headless: true });
  } catch (error) {
    return chromium.launch({
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      headless: true
    });
  }
}

async function verify(browser, engine, width, height) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForFunction(() => document.querySelector('#source-state')?.textContent.includes('实时流已连接'), null, { timeout: 60000 });
  await page.waitForFunction(() => document.querySelectorAll('.metric-cell[data-state="value"]').length > 0, null, { timeout: 60000 });
  await page.waitForTimeout(400);
  const result = await page.evaluate(() => {
    const stage = document.querySelector('.foreman-stage').getBoundingClientRect();
    const main = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const lower = echarts.getInstanceByDom(document.querySelector('#lower-trend-chart'));
    return {
      requirement: document.documentElement.dataset.requirement,
      source: document.querySelector('#source-state').textContent.trim(),
      dataClock: document.querySelector('#data-clock').textContent.trim(),
      stageWidth: Math.round(stage.width),
      metricValues: document.querySelectorAll('.metric-cell[data-state="value"]').length,
      mainSeries: main.getOption().series.length,
      mainDataSeries: main.getOption().series.filter(series => series.data.some(point => point?.[1] !== null)).length,
      lowerSeries: lower.getOption().series.length,
      lowerDataSeries: lower.getOption().series.filter(series => series.data.some(point => point?.[1] !== null)).length,
      overflowX: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      overflowY: Math.max(0, document.documentElement.scrollHeight - innerHeight)
    };
  });
  const screenshot = path.join(OUTPUT_DIR, engine + '_' + width + 'x' + height + '.png');
  await page.screenshot({ path: screenshot, fullPage: false });
  await context.close();
  return { engine, viewport: width + 'x' + height, ...result, screenshot, pageErrors, consoleErrors };
}

function failuresFor(results) {
  const failures = [];
  for (const item of results) {
    const [width, height] = item.viewport.split('x').map(Number);
    const prefix = item.engine + ' ' + item.viewport;
    if (item.requirement !== 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805') failures.push(prefix + ': marker');
    if (item.source !== '实时流已连接' || !item.dataClock || item.dataClock.endsWith('--')) failures.push(prefix + ': live state');
    if (item.metricValues < 1 || item.mainSeries !== 12 || item.mainDataSeries !== 12 || item.lowerSeries !== 5 || item.lowerDataSeries !== 5) failures.push(prefix + ': chart/data contract');
    if (item.pageErrors.length || item.consoleErrors.length) failures.push(prefix + ': browser errors');
    if (width >= 1280 && (item.overflowX !== 0 || item.overflowY !== 0)) failures.push(prefix + ': desktop overflow');
    if (width < 1280 && (item.stageWidth !== 1180 || item.overflowX <= 0)) failures.push(prefix + ': narrow canvas not scrollable');
    if (height < 720 && item.overflowY <= 0) failures.push(prefix + ': short canvas not scrollable');
  }
  return failures;
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const results = [];
  const targets = [
    ['edge-chromium', launchEdge, DESKTOP.concat(NARROW)],
    ['firefox', () => firefox.launch({ headless: true }), REPRESENTATIVE],
    ['webkit', () => webkit.launch({ headless: true }), REPRESENTATIVE]
  ];
  for (const target of targets) {
    const browser = await target[1]();
    browsers.add(browser);
    for (const viewport of target[2]) results.push(await verify(browser, target[0], viewport[0], viewport[1]));
    await browser.close();
    browsers.delete(browser);
  }
  const failures = failuresFor(results);
  const report = path.join(OUTPUT_DIR, 'report.json');
  fs.writeFileSync(report, JSON.stringify({ requirement: 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805', failures, results }, null, 2), 'utf8');
  if (failures.length) {
    console.error(JSON.stringify({ status: 'FAIL', report, failures }, null, 2));
    process.exit(1);
    return;
  }
  console.log(JSON.stringify({ status: 'PASS', report, checks: results.length }, null, 2));
  process.exit(0);
}

main().catch(async error => {
  for (const browser of browsers) await browser.close().catch(() => {});
  console.error(error);
  process.exitCode = 1;
});
