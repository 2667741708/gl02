#!/usr/bin/env node
/** Read-only production Edge smoke for REQ-HCZ-RULE-SENSITIVITY-20260811. */

const fs = require('fs');
const path = require('path');
const playwrightPackage = process.env.PLAYWRIGHT_NODE_PACKAGE || 'playwright';
const { chromium } = require(playwrightPackage);

const base = String(process.env.HCZ_UPWARD_RULE_BASE_URL || 'http://10.30.220.12:8093').replace(/\/+$/, '');
const output = path.resolve(__dirname, '..', 'logs', 'hcz_rule_sensitivity_20260811', 'remote_22012');
const viewports = [[1366, 768], [390, 844]];

async function runCase(browser, width, height) {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const errors = [];
  const badResponses = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('response', response => {
    if (response.status() >= 400) badResponses.push({ status: response.status(), url: response.url() });
  });

  const url = `${base}/hcz_upward_rule.html?qa=sensitivity-${Date.now()}-${width}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 120000 });
  await page.waitForFunction(() => document.querySelector('#serviceState')?.textContent.includes('就绪'), null, { timeout: 120000 });
  await page.fill('#trialTopTemperature', '10');
  await page.click('#runSensitivityButton');
  await page.waitForFunction(() => document.querySelector('#sensitivityState')?.textContent.includes('试算完成'), null, { timeout: 360000 });

  const metrics = await page.evaluate(() => {
    const gasCells = Array.from(document.querySelectorAll('#metricBody tr'))
      .find(row => row.cells[0]?.textContent.includes('煤气利用率'))?.querySelectorAll('td');
    return {
      status: document.querySelector('#decisionBadge')?.textContent.trim(),
      metricRows: document.querySelectorAll('#metricBody tr').length,
      layerCards: document.querySelectorAll('#layerGrid .layer').length,
      gateCards: document.querySelectorAll('#gateGrid .gate').length,
      gasCurrent: gasCells?.[1]?.textContent.trim(),
      gasBaseline: gasCells?.[2]?.textContent.trim(),
      gasDelta: gasCells?.[3]?.textContent.trim(),
      gasThreshold: gasCells?.[4]?.textContent.trim(),
      sensitivitySummary: document.querySelector('#sensitivitySummary')?.textContent.trim(),
      sensitivityState: document.querySelector('#sensitivityState')?.textContent.trim(),
      resultVisible: !document.querySelector('#sensitivityResult')?.hidden,
      overflowX: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      errorVisible: getComputedStyle(document.querySelector('#errorState')).display !== 'none',
    };
  });
  const api = await page.evaluate(() => Promise.all([
    fetch('/api/hcz-upward-rule', { cache: 'no-store' }).then(response => response.json()),
    fetch('/api/hcz-rule-sensitivity?days=90&top_temperature_delta_c=10', { cache: 'no-store' }).then(response => response.json()),
  ]));
  const [current, trial] = api;
  const screenshot = path.join(output, `edge_${width}x${height}.png`);
  await page.screenshot({ path: screenshot, fullPage: false });

  const ok = errors.length === 0
    && badResponses.length === 0
    && metrics.metricRows === 5
    && metrics.layerCards === 7
    && metrics.gateCards === 3
    && metrics.overflowX <= 1
    && !metrics.errorVisible
    && metrics.resultVisible
    && metrics.gasCurrent?.endsWith('%')
    && metrics.gasBaseline?.endsWith('%')
    && metrics.gasDelta?.includes('百分点')
    && metrics.gasThreshold?.includes('百分点')
    && metrics.sensitivitySummary?.includes('上移事件 0→0')
    && current.ok === true
    && current.source?.gas_utilisation_normalised === true
    && current.metrics?.blast_pressure?.label === '冷风风压'
    && trial.ok === true
    && trial.read_only_trial === true
    && trial.production_defaults_changed === false
    && trial.parameters?.baseline?.top_temperature_delta_c === 15
    && trial.parameters?.scenario?.top_temperature_delta_c === 10
    && trial.safety?.downward_definition === 'symmetric_mirror_candidate_only';

  await context.close();
  return {
    ok,
    viewport: `${width}x${height}`,
    url,
    metrics,
    api: {
      current_status: current.status,
      gas_utilisation_delta_pp: current.metrics?.gas_utilisation?.delta,
      baseline_up_episodes: trial.baseline?.up?.episode_count,
      scenario_up_episodes: trial.scenario?.up?.episode_count,
      baseline_down_episodes: trial.baseline?.down?.episode_count,
      scenario_down_episodes: trial.scenario?.down?.episode_count,
    },
    errors,
    badResponses,
    screenshot,
  };
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  let browser;
  try {
    try {
      browser = await chromium.launch({ channel: 'msedge', headless: true });
    } catch (_error) {
      browser = await chromium.launch({ headless: true });
    }
    const cases = [];
    for (const [width, height] of viewports) cases.push(await runCase(browser, width, height));
    const report = { ok: cases.every(item => item.ok), cases };
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
    if (!report.ok) process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
