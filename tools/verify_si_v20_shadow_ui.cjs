/* Cross-engine/viewport UI verification for the V20 Si shadow workbench. */
const fs = require('fs');
const path = require('path');

const FALLBACK = 'C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
let playwright;
try { playwright = require('playwright'); } catch (_) { playwright = require(FALLBACK); }

const root = path.resolve(__dirname, '..');
const scriptPath = path.join(root, '高炉前端数据', 'assets', 'bf-si-v20-shadow-workbench.js');
const outputDir = path.join(root, 'logs', 'si_v20_shadow_ui_20260808');
fs.mkdirSync(outputDir, {recursive: true});

const chromiumViewports = [
  [1280, 720], [1366, 768], [1440, 900], [1546, 864], [1920, 1080],
  [1024, 768], [768, 1024], [390, 844], [375, 667], [844, 390]
];
const representative = [[1920, 1080], [1366, 768], [768, 1024], [390, 844]];

const targets = Array.from({length: 12}, (_, index) => ({
  meltno: `2#20260807-${String(95 - index).padStart(3, '0')}`,
  open_ts: `2026-08-07 ${String(Math.max(0, 7 - index)).padStart(2, '0')}:40:00`,
  si_avg: index < 2 ? null : 0.28 + (index % 4) * 0.02,
  hot_metal_sample_count: index < 2 ? 0 : 2
}));
const historyItems = Array.from({length: 12}, (_, index) => ({
  prediction_id: index + 1,
  target_meltno: `2#20260807-${String(84 + index).padStart(3, '0')}`,
  target_open_ts: `2026-08-07 ${String(index).padStart(2, '0')}:30:00`,
  prediction_cutoff_ts: `2026-08-07 ${String(Math.max(0, index - 1)).padStart(2, '0')}:30:00`,
  requested_at: '2026-08-07 08:00:00+08:00',
  requested_by: '高炉长', requested_role: '高炉长', request_mode: 'historical_range_replay',
  lead_minutes: 60, prediction_si_mean: 0.29 + (index % 5) * 0.015,
  prediction_p10: 0.23 + (index % 5) * 0.015, prediction_p90: 0.36 + (index % 5) * 0.015,
  actual_si_mean: 0.28 + (index % 4) * 0.02, actual_ready: true,
  absolute_error: Math.abs((0.29 + (index % 5) * 0.015) - (0.28 + (index % 4) * 0.02)),
  hit_abs_le_005: true
}));

function mockBody(url, options) {
  if (url.includes('/api/si-v20/status')) return {ok: true, status: 'experimental_shadow', audit_table_ready: true, require_login: true, model: {name: 'ablation_history'}, targets, recommended_target: targets[0]};
  if (url.includes('/api/si-v20/history')) return {ok: true, items: historyItems, count: historyItems.length, metrics: {evaluated_count: 12, mae: 0.0321, hit_rate_abs_le_005: 0.75}};
  if (url.includes('/api/si-v20/replay')) return {ok: true, predicted_count: 12, failed_count: 0};
  if (url.includes('/api/si-v20/predict')) return {ok: true, prediction: {target_meltno: targets[0].meltno, target_open_ts: targets[0].open_ts, prediction_cutoff_ts: '2026-08-07 06:40:00', lead_minutes: 60, si_mean: 0.318, p10: 0.255, p50: 0.318, p90: 0.381, actual_ready: false, actual_si_mean: null, absolute_error: null, hit_abs_le_005: null, warnings: []}};
  return {ok: false, error: `unmocked ${url}`};
}

async function runCase(browserType, engine, viewport) {
  const browser = await browserType.launch({headless: true});
  const page = await browser.newPage({viewport: {width: viewport[0], height: viewport[1]}});
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', error => errors.push(String(error)));
  await page.setContent('<!doctype html><html><head><meta charset="utf-8"><title>V20 Si</title><style>html,body{margin:0;min-height:100%;background:#102832;color:white}</style></head><body><main style="padding:20px">高炉工作台</main></body></html>');
  await page.exposeFunction('__mockSiV20', (url, options) => mockBody(String(url), options));
  await page.evaluate(() => {
    window.fetch = async (url, options = {}) => {
      const payload = await window.__mockSiV20(String(url), options);
      return new Response(JSON.stringify(payload), {status: payload.ok === false ? 500 : 200, headers: {'Content-Type': 'application/json'}});
    };
    Object.defineProperty(window.location, 'port', {value: '8093', configurable: true});
  }).catch(() => {});
  await page.addScriptTag({path: scriptPath});
  await page.waitForSelector('.bf-si20-trigger');
  await page.click('.bf-si20-trigger');
  await page.waitForSelector('.bf-si20-drawer.open');
  await page.click('[data-action="predict"]');
  await page.waitForSelector('.bf-si20-card');
  await page.click('[data-tab="history"]');
  await page.waitForSelector('.bf-si20-chart');
  await page.waitForTimeout(80);
  const state = await page.evaluate(() => {
    const drawer = document.querySelector('.bf-si20-drawer');
    const canvas = document.querySelector('.bf-si20-chart');
    return {
      bodyOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      drawerVisible: getComputedStyle(drawer).display !== 'none',
      drawerRight: drawer.getBoundingClientRect().right,
      viewportWidth: document.documentElement.clientWidth,
      canvasWidth: canvas.width,
      actualLabel: document.body.textContent.includes('实际平均Si'),
      predictButton: Boolean(document.querySelector('[data-action="predict"]')),
      replayButton: Boolean(document.querySelector('[data-action="replay"]'))
    };
  });
  const screenshot = path.join(outputDir, `${engine}_${viewport[0]}x${viewport[1]}.png`);
  await page.screenshot({path: screenshot, fullPage: true});
  await browser.close();
  const passed = errors.length === 0 && state.bodyOverflow <= 1 && state.drawerVisible && state.drawerRight <= state.viewportWidth + 1 && state.canvasWidth > 0 && state.actualLabel && state.predictButton && state.replayButton;
  return {engine, viewport: `${viewport[0]}x${viewport[1]}`, passed, errors, state, screenshot};
}

(async () => {
  const results = [];
  for (const viewport of chromiumViewports) results.push(await runCase(playwright.chromium, 'chromium', viewport));
  for (const engine of ['firefox', 'webkit']) {
    for (const viewport of representative) results.push(await runCase(playwright[engine], engine, viewport));
  }
  const report = {schema: 'bf.si.v20.shadow_ui_matrix.v1', generated_at: new Date().toISOString(), results, passed: results.every(item => item.passed)};
  fs.writeFileSync(path.join(outputDir, 'ui_matrix.json'), JSON.stringify(report, null, 2));
  process.stdout.write(JSON.stringify(report, null, 2));
  if (!report.passed) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
