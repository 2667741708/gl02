#!/usr/bin/env node
/**
 * Browser acceptance for REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805.
 *
 * Starts a read-only static server, opens fixture=1, validates the 49-cell
 * matrix, full-width charts, real toolbar actions, navigation, overflow, and
 * captures the comparison screenshot.
 */

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, '高炉前端数据');
const OUTPUT_DIR = path.join(ROOT, 'logs', 'foreman_trend_preview_20260805');
let activeServer = null;
let activeBrowser = null;

function contentType(filename) {
  const extension = path.extname(filename).toLowerCase();
  return {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml'
  }[extension] || 'application/octet-stream';
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
    if (!target.startsWith(path.resolve(WEB_ROOT) + path.sep) && target !== path.resolve(WEB_ROOT)) {
      response.writeHead(403).end('Forbidden');
      return;
    }
    fs.readFile(target, (error, data) => {
      if (error) {
        response.writeHead(404).end('Not found');
        return;
      }
      response.writeHead(200, { 'Content-Type': contentType(target), 'Cache-Control': 'no-store' });
      response.end(data);
    });
  });
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const server = createServer();
  activeServer = server;
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
  } catch (error) {
    const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
    browser = await chromium.launch({ executablePath: edgePath, headless: true });
  }
  activeBrowser = browser;
  const pageErrors = [];
  const consoleErrors = [];
  const page = await browser.newPage({ viewport: { width: 1280, height: 1024 }, deviceScaleFactor: 1 });
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const url = `http://127.0.0.1:${port}/foreman_trend_preview.html?fixture=1&minutes=90`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForSelector('.metric-cell[data-state="value"]');
  await page.waitForFunction(() => document.querySelectorAll('.metric-cell').length === 49);
  await page.waitForTimeout(700);

  const beforeZoom = await page.evaluate(() => {
    const chart = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const zoom = chart.getOption().dataZoom[0];
    return { start: zoom.start, end: zoom.end };
  });
  await page.locator('[data-chart-toolbar="main"] [data-action="zoom-in"]').click();
  await page.waitForTimeout(150);
  const afterZoom = await page.evaluate(() => {
    const chart = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const zoom = chart.getOption().dataZoom[0];
    return { start: zoom.start, end: zoom.end };
  });
  await page.locator('[data-chart-toolbar="main"] [data-action="reset"]').click();
  await page.locator('[data-chart-toolbar="main"] [data-action="legend"]').click();

  const legendInteractionWorked = await page.evaluate(() => !document.querySelector('#series-key').hidden);
  await page.locator('[data-chart-toolbar="main"] [data-action="series-picker"]').click();
  await page.locator('#series-picker [data-series-select="P_top_gas_A"]').check();
  await page.waitForTimeout(120);
  const pickerInteractionWorked = await page.evaluate(() => {
    const chart = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const metric = document.querySelector('.metric-cell[data-metric="P_top_gas_A"] .metric-value');
    return {
      selected: Boolean(document.querySelector('#series-picker [data-series-select="P_top_gas_A"]')?.checked),
      pickerVisible: !document.querySelector('#series-picker').hidden,
      seriesCount: chart.getOption().series.length,
      metricColor: metric?.style.color || ''
    };
  });

  const result = await page.evaluate(() => {
    const rect = selector => {
      const element = document.querySelector(selector);
      const box = element.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    };
    const main = echarts.getInstanceByDom(document.querySelector('#main-trend-chart'));
    const lower = echarts.getInstanceByDom(document.querySelector('#lower-trend-chart'));
    return {
      requirement: document.documentElement.dataset.requirement,
      metricCount: document.querySelectorAll('.metric-cell').length,
      metricValueCount: document.querySelectorAll('.metric-cell[data-state="value"]').length,
      columnCount: document.querySelectorAll('.metric-column').length,
      rowsPerColumn: [...document.querySelectorAll('.metric-column')].map(item => item.children.length),
      sourceText: document.querySelector('#source-state').textContent.trim(),
      stage: rect('.foreman-stage'),
      matrix: rect('.metric-matrix'),
      mainChart: rect('.main-chart-shell'),
      lowerChart: rect('.lower-chart-shell'),
      navigation: rect('.legacy-tabs'),
      mainSeries: main.getOption().series.length,
      lowerSeries: lower.getOption().series.length,
      mainHasData: main.getOption().series.every(series => series.data.length > 0),
      lowerHasData: lower.getOption().series.every(series => series.data.length > 0),
      linkTargets: [...document.querySelectorAll('.legacy-tabs a')].map(item => item.getAttribute('href')),
      overflowX: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      overflowY: Math.max(0, document.documentElement.scrollHeight - innerHeight)
    };
  });
  result.zoomChanged = (afterZoom.end - afterZoom.start) < (beforeZoom.end - beforeZoom.start);
  result.legendInteractionWorked = legendInteractionWorked;
  result.pickerInteractionWorked = pickerInteractionWorked;
  result.pageErrors = pageErrors;
  result.consoleErrors = consoleErrors;
  result.url = url;

  await page.locator('[data-chart-toolbar="main"] [data-action="legend"]').click();
  const screenshot = path.join(OUTPUT_DIR, 'foreman_trend_1280x1024.png');
  await page.screenshot({ path: screenshot, fullPage: false });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'report.json'), JSON.stringify(result, null, 2), 'utf8');
  await browser.close();
  activeBrowser = null;
  await new Promise(resolve => server.close(resolve));
  activeServer = null;

  const failures = [];
  if (result.requirement !== 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805') failures.push('requirement marker missing');
  if (result.metricCount !== 49 || result.metricValueCount !== 49) failures.push('49 metric values are not all visible in fixture mode');
  if (result.columnCount !== 7 || result.rowsPerColumn.some(value => value !== 7)) failures.push('matrix is not 7x7');
  if (result.sourceText !== '布局校验数据 · 非生产') failures.push('fixture boundary is not visible');
  if (result.mainSeries < 12 || !result.mainHasData) failures.push('main trend series incomplete');
  if (result.lowerSeries !== 5 || !result.lowerHasData) failures.push('lower trend series incomplete');
  if (!result.zoomChanged || !result.legendInteractionWorked) failures.push('toolbar interaction failed');
  if (!result.pickerInteractionWorked.selected || !result.pickerInteractionWorked.pickerVisible || result.pickerInteractionWorked.seriesCount !== 13 || !result.pickerInteractionWorked.metricColor) failures.push('variable curve picker failed');
  if (result.overflowX !== 0 || result.overflowY !== 0) failures.push('1280x1024 viewport overflows');
  if (result.pageErrors.length || result.consoleErrors.length) failures.push('browser errors detected');
  if (result.linkTargets.length !== 6 || !result.linkTargets.some(item => item.includes('#trend'))) failures.push('comparison navigation incomplete');
  if (failures.length) {
    console.error(JSON.stringify({ failures, result }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ status: 'PASS', screenshot, report: path.join(OUTPUT_DIR, 'report.json'), result }, null, 2));
}

main().catch(async error => {
  if (activeBrowser) await activeBrowser.close().catch(() => {});
  if (activeServer) await new Promise(resolve => activeServer.close(resolve));
  console.error(error);
  process.exitCode = 1;
});
