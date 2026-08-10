#!/usr/bin/env node
/** Cross-engine acceptance for REQ-BODY-TEMP-INFRARED-REPLAY-20260808. */

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium, firefox, webkit } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, '高炉前端数据', 'soft_zone_replay');
const REMOTE_BASE_URL = String(process.env.SOFT_ZONE_REPLAY_BASE_URL || '').replace(/\/+$/, '');
const REMOTE_SMOKE = process.env.SOFT_ZONE_REPLAY_REMOTE_SMOKE === '1';
const REMOTE_EDGE_ONLY = process.env.SOFT_ZONE_REPLAY_REMOTE_EDGE_ONLY === '1';
const OUTPUT_DIR = path.join(ROOT, 'logs', 'soft_zone_replay_20260808', REMOTE_BASE_URL ? 'remote_22012_matrix' : 'viewport_matrix');
const ALL_VIEWPORTS = [[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]];
const REPRESENTATIVE = [[1920,1080],[1366,768],[768,1024],[390,844]];
const LAYERS = [
  [7,16.860,'belly'],[8,18.335,'belly'],[9,20.125,'waist'],[10,21.860,'stack_lower'],
  [11,23.711,'stack_lower'],[12,25.441,'stack_lower'],[13,27.171,'stack_lower'],
  [14,28.901,'stack_middle'],[15,30.631,'stack_upper'],[16,32.361,'stack_upper']
];
const SECTORS = 'ABCDEFGH'.split('');
let server = null;
const browsers = new Set();

function fixturePayload() {
  const start = new Date('2026-08-08T06:00:00');
  const timeline = Array.from({ length: 73 }, (_, index) => new Date(start.getTime() + index * 5 * 60000).toISOString().slice(0, 19));
  const points = [];
  for (const [layer, height, region] of LAYERS) {
    for (let sectorIndex = 0; sectorIndex < SECTORS.length; sectorIndex += 1) {
      const values = timeline.map((_, frame) => {
        const hotLayer = 10.8 + 2.2 * Math.sin(frame / 11);
        const layerHeat = 130 * Math.exp(-Math.pow(layer - hotLayer, 2) / 3.4);
        const angular = 0.72 + 0.28 * Math.cos(sectorIndex * Math.PI / 4 - frame / 8);
        return Number((78 + layer * 2.4 + layerHeat * angular + 5 * Math.sin(frame / 3 + sectorIndex)).toFixed(3));
      });
      points.push({ id:`T_body_L${layer}_${SECTORS[sectorIndex]}`, metric:'temperature', layer, height_m:height, azimuth:SECTORS[sectorIndex], angle_deg:sectorIndex*45, region, unit:'℃', values, available_count:values.length });
    }
  }
  for (const [band, height, region] of [['lower',20.350,'waist'],['middle',23.488,'stack_lower'],['upper',28.976,'stack_middle']]) {
    for (let sectorIndex = 0; sectorIndex < 6; sectorIndex += 1) {
      const values = timeline.map((_, frame) => Number((18 + height * 0.18 + sectorIndex * 0.16 + 0.8 * Math.sin(frame / 9 + sectorIndex)).toFixed(4)));
      points.push({ id:`P_static_${band}_${SECTORS[sectorIndex]}`, metric:'pressure', pressure_band:band, height_m:height, azimuth:SECTORS[sectorIndex], angle_deg:sectorIndex*60, region, unit:'kPa', values, available_count:values.length });
    }
  }
  const cohesive_zone = timeline.map((time, frame) => ({
    time, status:'available', center_height_m:22.1 + 1.4 * Math.sin(frame / 11),
    thickness_m:2.2, direction:Math.cos(frame / 11) > 0.12 ? 'up' : Math.cos(frame / 11) < -0.12 ? 'down' : 'stable',
    velocity_m_per_h:0.5 * Math.cos(frame / 11), confidence:0.42
  }));
  return {
    ok:true, schema_version:'gl02.body-temperature-replay.v1', source:'bf_sensor.one_minute_values',
    timeline, points, scales:{ temperature:{ low:92, high:228, unit:'℃', method:'p05_p95_fixed_window' } },
    coverage:{ temperature:1, pressure:0 }, cohesive_zone,
    evidence:{ temperature:'measured', cohesive_zone:'estimated', control_use:'prohibited' }
  };
}

function contentType(filename) {
  return { '.html':'text/html; charset=utf-8', '.js':'application/javascript; charset=utf-8', '.css':'text/css; charset=utf-8' }[path.extname(filename)] || 'application/octet-stream';
}

function createServer() {
  const replay = fixturePayload();
  return http.createServer((request, response) => {
    const parsed = new URL(request.url, 'http://127.0.0.1');
    if (parsed.pathname === '/favicon.ico') return response.writeHead(204).end();
    if (parsed.pathname === '/api/health') {
      response.writeHead(200, { 'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store' });
      return response.end(JSON.stringify({ ok:true, latest_sample_time:'2026-08-08T12:00:00', schema_version:'gl02.body-temperature-replay.v1' }));
    }
    if (parsed.pathname === '/api/replay') {
      const include = parsed.searchParams.get('include_cohesive') === '1';
      response.writeHead(200, { 'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store' });
      return response.end(JSON.stringify({ ...replay, cohesive_zone:include ? replay.cohesive_zone : [] }));
    }
    const relative = decodeURIComponent(parsed.pathname).replace(/^\/+/, '') || 'index.html';
    const target = path.resolve(WEB_ROOT, relative);
    if (!target.startsWith(path.resolve(WEB_ROOT) + path.sep) && target !== path.resolve(WEB_ROOT)) return response.writeHead(403).end('Forbidden');
    fs.readFile(target, (error, data) => {
      if (error) return response.writeHead(404).end('Not found');
      response.writeHead(200, { 'Content-Type':contentType(target), 'Cache-Control':'no-store' });
      response.end(data);
    });
  });
}

async function launchEdge() {
  try { return await chromium.launch({ channel:'msedge', headless:true }); }
  catch (_error) { return chromium.launch({ executablePath:'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless:true }); }
}

async function verify(browser, engine, baseUrl, width, height) {
  const context = await browser.newContext({ viewport:{ width, height }, deviceScaleFactor:1, acceptDownloads:true });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  const responseErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push({ text:message.text(), location:message.location() });
  });
  page.on('response', response => {
    if (response.status() >= 400) responseErrors.push({ status:response.status(), url:response.url() });
  });
  const url = `${baseUrl}/?qa=${engine}-${width}x${height}`;
  await page.goto(url, { waitUntil:'networkidle', timeout:60000 });
  await page.waitForFunction(() => document.querySelector('.app-shell')?.dataset.appState === 'ready');
  await page.waitForFunction(() => Number(document.querySelector('#timelineInput')?.max) >= 1);
  await page.waitForTimeout(150);

  const before = Number(await page.locator('#timelineInput').inputValue());
  await page.locator('#playButton').click();
  await page.waitForTimeout(650);
  const after = Number(await page.locator('#timelineInput').inputValue());
  await page.locator('#playButton').click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(100);
  const metrics = await page.evaluate(() => {
    const canvas = document.querySelector('#thermalCanvas').getBoundingClientRect();
    const temperatureTrend = document.querySelector('#temperatureTrendCanvas').getBoundingClientRect();
    const pressureTrend = document.querySelector('#pressureTrendCanvas').getBoundingClientRect();
    const load = document.querySelector('#loadButton').getBoundingClientRect();
    const record = document.querySelector('#recordButton').getBoundingClientRect();
    return {
      appState:document.querySelector('.app-shell').dataset.appState,
      overflowX:Math.max(0, document.documentElement.scrollWidth - innerWidth),
      canvasWidth:Math.round(canvas.width), canvasHeight:Math.round(canvas.height),
      temperatureTrendWidth:Math.round(temperatureTrend.width),
      pressureTrendWidth:Math.round(pressureTrend.width),
      temperatureTrendSeries:Number(document.querySelector('#temperatureTrendCanvas').dataset.renderedSeries || 0),
      pressureTrendSeries:Number(document.querySelector('#pressureTrendCanvas').dataset.renderedSeries || 0),
      loadReachable:load.width > 0 && load.height > 0,
      recordReachable:record.width > 0 && record.height > 0,
      frameText:document.querySelector('#frameCounter').textContent.trim(),
      sourceText:document.querySelector('#sourceBadge').textContent.trim(),
      loadingHidden:document.querySelector('#loadingState').classList.contains('hidden'),
      errorHidden:document.querySelector('#errorState').classList.contains('hidden'),
      emptyHidden:document.querySelector('#emptyState').classList.contains('hidden'),
      bodyFont:getComputedStyle(document.body).fontFamily,
      mediaRecorderSupported:typeof MediaRecorder !== 'undefined',
      captureStreamSupported:typeof document.querySelector('#thermalCanvas').captureStream === 'function'
    };
  });
  const screenshot = path.join(OUTPUT_DIR, `${engine}_${width}x${height}.png`);
  await page.screenshot({ path:screenshot, fullPage:false });
  await page.locator('.trend-section').scrollIntoViewIfNeeded();
  await page.waitForTimeout(100);
  const trendScreenshot = path.join(OUTPUT_DIR, `${engine}_${width}x${height}_trends.png`);
  await page.screenshot({ path:trendScreenshot, fullPage:false });
  await context.close();
  return { engine, viewport:`${width}x${height}`, url, screenshot, trendScreenshot, before, after, pageErrors, consoleErrors, responseErrors, ...metrics };
}

async function verifyStates(browser, baseUrl) {
  const context = await browser.newContext({ viewport:{ width:1366, height:768 } });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/`, { waitUntil:'networkidle' });
  await page.waitForFunction(() => document.querySelector('.app-shell')?.dataset.appState === 'ready');

  await page.route('**/api/replay*', route => route.fulfill({ status:503, contentType:'application/json', body:JSON.stringify({ ok:false, message:'QA error' }) }));
  await page.locator('#loadButton').click();
  await page.waitForFunction(() => document.querySelector('.app-shell')?.dataset.appState === 'error');
  const errorVisible = await page.locator('#errorState').isVisible();
  await page.unroute('**/api/replay*');

  await page.route('**/api/replay*', route => route.fulfill({ status:200, contentType:'application/json', body:JSON.stringify({ ok:false, timeline:[] }) }));
  await page.locator('#retryButton').click();
  await page.waitForFunction(() => document.querySelector('.app-shell')?.dataset.appState === 'empty');
  const emptyVisible = await page.locator('#emptyState').isVisible();
  await context.close();
  return { errorVisible, emptyVisible };
}

function failuresFor(results, states) {
  const failures = [];
  for (const item of results) {
    const prefix = `${item.engine} ${item.viewport}`;
    if (item.appState !== 'ready' || item.sourceText !== '数据库就绪') failures.push(`${prefix}: ready state missing`);
    if (item.after <= item.before) failures.push(`${prefix}: playback did not advance`);
    if (item.overflowX !== 0) failures.push(`${prefix}: horizontal overflow ${item.overflowX}px`);
    if (item.canvasWidth < 280 || item.canvasHeight < 350) failures.push(`${prefix}: canvas too small`);
    if (item.temperatureTrendWidth < 280 || item.pressureTrendWidth < 280) failures.push(`${prefix}: trend canvas too small`);
    if (item.temperatureTrendSeries !== 8) failures.push(`${prefix}: expected 8 temperature trend series`);
    if (item.pressureTrendSeries !== 6) failures.push(`${prefix}: expected 6 pressure trend series`);
    if (!item.loadReachable || !item.recordReachable) failures.push(`${prefix}: controls unreachable`);
    if (!item.loadingHidden || !item.errorHidden || !item.emptyHidden) failures.push(`${prefix}: success state overlays incorrect`);
    if (!item.bodyFont.includes('SimSun')) failures.push(`${prefix}: SimSun stack missing`);
    if (item.pageErrors.length || item.consoleErrors.length) failures.push(`${prefix}: browser errors detected`);
  }
  if (!states.errorVisible) failures.push('error state is not visible');
  if (!states.emptyVisible) failures.push('empty state is not visible');
  return failures;
}

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive:true });
  let baseUrl = REMOTE_BASE_URL;
  if (!baseUrl) {
    server = createServer();
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    baseUrl = `http://127.0.0.1:${server.address().port}`;
  }
  const results = [];
  const targets = REMOTE_EDGE_ONLY ? [
    ['edge-chromium', launchEdge, [[1366,768]]]
  ] : REMOTE_SMOKE ? [
    ['edge-chromium', launchEdge, [[1366,768],[390,844]]],
    ['firefox', () => firefox.launch({ headless:true }), [[1366,768]]],
    ['webkit', () => webkit.launch({ headless:true }), [[390,844]]]
  ] : [
    ['edge-chromium', launchEdge, ALL_VIEWPORTS],
    ['firefox', () => firefox.launch({ headless:true }), REPRESENTATIVE],
    ['webkit', () => webkit.launch({ headless:true }), REPRESENTATIVE]
  ];
  for (const [engine, launch, viewports] of targets) {
    const browser = await launch();
    browsers.add(browser);
    for (const [width, height] of viewports) results.push(await verify(browser, engine, baseUrl, width, height));
    await browser.close();
    browsers.delete(browser);
  }
  const stateBrowser = await launchEdge();
  browsers.add(stateBrowser);
  const states = await verifyStates(stateBrowser, baseUrl);
  await stateBrowser.close();
  browsers.delete(stateBrowser);
  const failures = failuresFor(results, states);
  const report = path.join(OUTPUT_DIR, 'report.json');
  fs.writeFileSync(report, JSON.stringify({ requirement:'REQ-BODY-TEMP-INFRARED-REPLAY-20260808', failures, states, results }, null, 2), 'utf8');
  if (server) {
    await new Promise(resolve => server.close(resolve));
    server = null;
  }
  if (failures.length) {
    console.error(JSON.stringify({ status:'FAIL', report, failures }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({ status:'PASS', report, checks:results.length, states }, null, 2));
}

main().catch(async error => {
  for (const browser of browsers) await browser.close().catch(() => {});
  if (server) await new Promise(resolve => server.close(resolve));
  console.error(error);
  process.exitCode = 1;
});
