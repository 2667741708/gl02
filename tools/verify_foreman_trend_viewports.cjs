#!/usr/bin/env node
/**
 * Cross-engine and viewport acceptance for
 * REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805.
 *
 * Desktop viewports must fit without page overflow. Narrow viewports retain
 * the fixed industrial workstation canvas and must expose it through normal
 * two-axis page scrolling as a read-only workflow.
 */

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium, firefox, webkit } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, '高炉前端数据');
const OUTPUT_DIR = path.join(ROOT, 'logs', 'foreman_trend_preview_20260805', 'viewport_matrix');
const DESKTOP_VIEWPORTS = [
  [1280, 720],
  [1366, 768],
  [1440, 900],
  [1546, 864],
  [1920, 1080]
];
const NARROW_VIEWPORTS = [
  [1024, 768],
  [768, 1024],
  [390, 844],
  [375, 667]
];
const REPRESENTATIVE_VIEWPORTS = [
  [1920, 1080],
  [1366, 768],
  [768, 1024],
  [390, 844]
];

let activeServer = null;
const activeBrowsers = new Set();

function contentType(filename) {
  return {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8'
  }[path.extname(filename).toLowerCase()] || 'application/octet-stream';
}

function createServer() {
  return http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    if (pathname === '/favicon.ico') {
      response.writeHead(204).end();
      return;
    }
    const relative = pathname.replace(/^\/+/, '') || 'foreman_trend_preview.html';
    const target = path.resolve(WEB_ROOT, relative);
    const root = path.resolve(WEB_ROOT);
    if (!target.startsWith(root + path.sep) && target !== root) {
      response.writeHead(403).end('Forbidden');
      return;
    }
    fs.readFile(target, (error, data) => {
      if (error) {
        response.writeHead(404).end('Not found');
        return;
      }
      response.writeHead(200, {
        'Content-Type': contentType(target),
        'Cache-Control': 'no-store'
      });
      response.end(data);
    });
  });
}

async function launchChromium() {
  try {
    return await chromium.launch({ channel: 'msedge', headless: true });
  } catch (error) {
    return chromium.launch({
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      headless: true
    });
  }
}

async function verifyViewport(browser, engine, port, width, height) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  const url = `http://127.0.0.1:${port}/foreman_trend_preview.html?fixture=1&minutes=90`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForFunction(() => document.querySelectorAll('.metric-cell[data-state="value"]').length === 49);
  await page.waitForTimeout(250);

  const initial = await page.evaluate(() => {
    const stage = document.querySelector('.foreman-stage').getBoundingClientRect();
    const main = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const lower = echarts.getInstanceByDom(document.querySelector('#lower-trend-chart'));
    return {
      requirement: document.documentElement.dataset.requirement,
      metricCount: document.querySelectorAll('.metric-cell').length,
      stageWidth: Math.round(stage.width),
      stageHeight: Math.round(stage.height),
      documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight,
      overflowX: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      overflowY: Math.max(0, document.documentElement.scrollHeight - innerHeight),
      mainSeries: main && main.getOption().series.length,
      lowerSeries: lower && lower.getOption().series.length,
      activeTab: document.querySelector('.legacy-tabs a[aria-current="page"]')?.textContent.trim() || '',
      sourceText: document.querySelector('#source-state').textContent.trim()
    };
  });

  const screenshot = path.join(OUTPUT_DIR, `${engine}_${width}x${height}.png`);
  await page.screenshot({ path: screenshot, fullPage: false });

  const reachability = await page.evaluate(() => {
    window.scrollTo(document.documentElement.scrollWidth, document.documentElement.scrollHeight);
    const lastTab = document.querySelector('.legacy-tabs a:last-child').getBoundingClientRect();
    const navigation = document.querySelector('.legacy-tabs').getBoundingClientRect();
    return {
      scrollX: Math.round(window.scrollX),
      scrollY: Math.round(window.scrollY),
      maxScrollX: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      maxScrollY: Math.max(0, document.documentElement.scrollHeight - innerHeight),
      lastTabVisible: lastTab.left >= 0 && lastTab.right <= innerWidth + 1,
      navigationVisible: navigation.top < innerHeight && navigation.bottom > 0
    };
  });

  await context.close();
  return {
    engine,
    viewport: `${width}x${height}`,
    url,
    screenshot,
    ...initial,
    ...reachability,
    pageErrors,
    consoleErrors
  };
}

function collectFailures(results) {
  const failures = [];
  for (const item of results) {
    const prefix = `${item.engine} ${item.viewport}`;
    const [width, height] = item.viewport.split('x').map(Number);
    if (item.requirement !== 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805') failures.push(`${prefix}: requirement marker missing`);
    if (item.metricCount !== 49 || item.mainSeries !== 12 || item.lowerSeries !== 5) failures.push(`${prefix}: content contract incomplete`);
    if (item.activeTab !== '工长趋势1' || item.sourceText !== '布局校验数据 · 非生产') failures.push(`${prefix}: visible state boundary incomplete`);
    if (item.pageErrors.length || item.consoleErrors.length) failures.push(`${prefix}: browser errors detected`);
    if (width >= 1280 && (item.overflowX !== 0 || item.overflowY !== 0)) failures.push(`${prefix}: desktop viewport overflows`);
    if (width < 1280 && (item.stageWidth !== 1180 || item.overflowX <= 0 || item.scrollX !== item.maxScrollX || !item.lastTabVisible)) failures.push(`${prefix}: narrow horizontal workflow is not reachable`);
    if (height < 720 && (item.overflowY <= 0 || item.scrollY !== item.maxScrollY || !item.navigationVisible)) failures.push(`${prefix}: short viewport bottom workflow is not reachable`);
  }
  return failures;
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  activeServer = createServer();
  await new Promise(resolve => activeServer.listen(0, '127.0.0.1', resolve));
  const port = activeServer.address().port;
  const results = [];

  const targets = [
    ['edge-chromium', launchChromium, [...DESKTOP_VIEWPORTS, ...NARROW_VIEWPORTS]],
    ['firefox', () => firefox.launch({ headless: true }), REPRESENTATIVE_VIEWPORTS],
    ['webkit', () => webkit.launch({ headless: true }), REPRESENTATIVE_VIEWPORTS]
  ];

  for (const [engine, launch, viewports] of targets) {
    const browser = await launch();
    activeBrowsers.add(browser);
    for (const [width, height] of viewports) {
      results.push(await verifyViewport(browser, engine, port, width, height));
    }
    await browser.close();
    activeBrowsers.delete(browser);
  }

  const failures = collectFailures(results);
  const report = path.join(OUTPUT_DIR, 'report.json');
  fs.writeFileSync(report, JSON.stringify({ requirement: 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805', failures, results }, null, 2), 'utf8');
  await new Promise(resolve => activeServer.close(resolve));
  activeServer = null;

  if (failures.length) {
    console.error(JSON.stringify({ status: 'FAIL', report, failures }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ status: 'PASS', report, checks: results.length }, null, 2));
}

main().catch(async error => {
  for (const browser of activeBrowsers) await browser.close().catch(() => {});
  if (activeServer) await new Promise(resolve => activeServer.close(resolve));
  console.error(error);
  process.exitCode = 1;
});
