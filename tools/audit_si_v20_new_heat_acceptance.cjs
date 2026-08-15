/*
 * Read-only hourly acceptance probe for the 220.12 V20 Si workbench.
 *
 * REQ-SI-V20-NEW-HEAT-HOURLY-ACCEPTANCE-20260810
 * - captures API snapshots, UI state, screenshots and all three page CSV exports;
 * - freezes the first observed latest actual heat as the baseline;
 * - passes only after a newer heat with actual Si is visible in both status and
 *   history, is no longer advertised as an unopened candidate, and has a saved
 *   prediction association.
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawnSync } = require('child_process');
let playwright;
try {
  playwright = require('playwright');
} catch (_) {
  playwright = require('C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
}
const { chromium } = playwright;

function argument(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function heatKey(meltno) {
  const match = String(meltno || '').match(/(\d{8})-(\d+)$/);
  return match ? Number(`${match[1]}${String(match[2]).padStart(4, '0')}`) : -1;
}

function hasNumber(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
}

function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function writeCsv(filePath, rows) {
  const keys = [...new Set(rows.flatMap(row => Object.keys(row || {})))];
  const lines = [keys.map(csvCell).join(',')];
  for (const row of rows) lines.push(keys.map(key => csvCell(row?.[key])).join(','));
  fs.writeFileSync(filePath, `\uFEFF${lines.join('\r\n')}\r\n`, 'utf8');
}

function predictionMetrics(items) {
  const evaluated = items.filter(item => hasNumber(item?.absolute_error));
  const signed = evaluated.filter(item => hasNumber(item?.signed_error)).map(item => Number(item.signed_error));
  const absolute = evaluated.map(item => Number(item.absolute_error));
  return {
    prediction_count: items.length,
    matched_heat_count: items.filter(item => item?.matched_actual_meltno).length,
    evaluated_count: evaluated.length,
    mae: absolute.length ? absolute.reduce((sum, value) => sum + value, 0) / absolute.length : null,
    rmse: signed.length ? Math.sqrt(signed.reduce((sum, value) => sum + value * value, 0) / signed.length) : null,
    bias: signed.length ? signed.reduce((sum, value) => sum + value, 0) / signed.length : null,
    hit_rate_abs_le_002: absolute.length ? absolute.filter(value => value <= 0.02).length / absolute.length : null,
    hit_rate_abs_le_005: evaluated.length ? evaluated.filter(item => item.hit_abs_le_005 === true).length / evaluated.length : null,
    pending_match_count: items.filter(item => !item?.matched_actual_meltno).length,
    waiting_si_count: items.filter(item => item?.matched_actual_meltno && !item?.actual_ready).length,
  };
}

function htmlEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

function parseEmbeddedJson(value) {
  const text = String(value || '');
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  try { return JSON.parse(text.slice(start, end + 1)); } catch { return null; }
}

function apiJson(_request, baseUrl, endpoint) {
  return new Promise(resolve => {
    let settled = false;
    let hardTimeout;
    let responseStatus = null;
    const finish = result => {
      if (settled) return;
      settled = true;
      if (hardTimeout) clearTimeout(hardTimeout);
      resolve(result);
    };
    const request = http.get(`${baseUrl}${endpoint}`, {
      agent: false,
      headers: { Connection: 'close' },
    }, response => {
      responseStatus = response.statusCode ?? null;
      const chunks = [];
      let byteCount = 0;
      response.on('data', chunk => {
        byteCount += chunk.length;
        if (byteCount > 25 * 1024 * 1024) {
          request.destroy(new Error(`${endpoint} response exceeds 25 MiB`));
          return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        let body;
        try { body = JSON.parse(text); } catch { body = { raw_text: text }; }
        finish({
          endpoint,
          http_status: responseStatus,
          ok: responseStatus >= 200 && responseStatus < 300,
          body,
        });
      });
      response.on('error', error => finish({
        endpoint,
        http_status: responseStatus,
        ok: false,
        body: null,
        error: error?.message || String(error),
      }));
    });
    request.on('error', error => finish({
      endpoint,
      http_status: responseStatus,
      ok: false,
      body: null,
      error: error?.message || String(error),
    }));
    request.setTimeout(6000, () => request.destroy(new Error(`${endpoint} socket timeout`)));
    hardTimeout = setTimeout(() => request.destroy(new Error(`${endpoint} hard timeout`)), 8000);
  });
}

async function withTimeout(promise, timeoutMs, label) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function savePageDownloads(page, exportDir, stamp) {
  const outputs = [];
  const errors = [];
  for (const [selector, kind] of [
    ['#downloadPredictionBtn', 'prediction_curve'],
    ['#downloadActualBtn', 'actual_si_curve'],
    ['#downloadHourlyTableBtn', 'hourly_si_table'],
  ]) {
    let download;
    try {
      [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 15000 }),
        page.click(selector, { timeout: 15000 }),
      ]);
      const suggested = download.suggestedFilename();
      const target = path.join(exportDir, `${stamp}_${kind}_${suggested}`);
      await withTimeout(download.saveAs(target), 20000, `${kind} download.saveAs`);
      outputs.push(target);
    } catch (error) {
      errors.push(`${kind}: ${error?.message || String(error)}`);
      if (download) await withTimeout(download.cancel(), 5000, `${kind} download.cancel`).catch(() => {});
    }
  }
  return { outputs, errors };
}

async function run() {
  const baseUrl = argument('--base-url', 'http://10.30.220.12:8093').replace(/\/$/, '');
  const outputDir = path.resolve(argument('--output-dir', 'reports/acceptance/SI_V20_NEW_HEAT_20260810'));
  const now = new Date();
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const apiDir = path.join(outputDir, 'evidence', 'api');
  const screenshotDir = path.join(outputDir, 'evidence', 'screenshots');
  const exportDir = path.join(outputDir, 'exports');
  fs.mkdirSync(apiDir, { recursive: true });
  fs.mkdirSync(screenshotDir, { recursive: true });
  fs.mkdirSync(exportDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    acceptDownloads: true,
    locale: 'zh-CN',
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  const targetUrl = `${baseUrl}/si_v20_workbench.html?acceptance=${encodeURIComponent(stamp)}`;
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('#strictHourlyStatus', { timeout: 30000 });
  await page.waitForTimeout(2500);

  const statusEndpoint = '/api/si-v20/status?limit=50';
  const apiResults = {};
  apiResults[statusEndpoint] = await apiJson(context.request, baseUrl, statusEndpoint);
  const status = apiResults[statusEndpoint].body || {};
  const targets = Array.isArray(status.targets) ? status.targets : [];
  const actualTargets = targets.filter(item => Number.isFinite(Number(item.si_avg)));
  actualTargets.sort((a, b) => heatKey(b.meltno) - heatKey(a.meltno));
  const latestActual = actualTargets[0] || null;
  const historyEndpoint = latestActual?.meltno
    ? `/api/si-v20/history?limit=10&latest_per_heat=1&meltno=${encodeURIComponent(latestActual.meltno)}`
    : '/api/si-v20/history?limit=10&latest_per_heat=1';
  const endpoints = [
    '/api/si-v20/strict-hourly/status',
    '/api/si-v20/strict-hourly/history?limit=1',
    historyEndpoint,
    '/api/si-v20/schedule',
    '/api/si-v20/hourly-table?limit=72',
  ];
  for (const endpoint of endpoints) {
    apiResults[endpoint] = await apiJson(context.request, baseUrl, endpoint);
  }
  fs.writeFileSync(path.join(apiDir, `${stamp}_api_snapshot.json`), JSON.stringify(apiResults, null, 2), 'utf8');

  const strictStatus = apiResults['/api/si-v20/strict-hourly/status'].body || {};
  const strictHistoryProbe = apiResults['/api/si-v20/strict-hourly/history?limit=1'].body || {};
  const history = apiResults[historyEndpoint].body || {};
  const schedule = apiResults['/api/si-v20/schedule'].body || {};
  const hourlyTable = apiResults['/api/si-v20/hourly-table?limit=72'].body || {};

  const baselinePath = path.join(outputDir, 'baseline.json');
  let baseline;
  if (fs.existsSync(baselinePath)) {
    baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));
  } else {
    baseline = {
      schema: 'ops.si-v20.new-heat-acceptance-baseline.v1',
      captured_at: now.toISOString(),
      meltno: latestActual?.meltno || null,
      open_ts: latestActual?.open_ts || null,
      si_avg: latestActual?.si_avg ?? null,
    };
    fs.writeFileSync(baselinePath, JSON.stringify(baseline, null, 2), 'utf8');
  }

  const newerActual = actualTargets.find(item => heatKey(item.meltno) > heatKey(baseline.meltno));
  const historyItems = Array.isArray(history.items) ? history.items : [];
  const hourlyItems = Array.isArray(hourlyTable.items) ? hourlyTable.items : [];
  const strictItems = hourlyItems.filter(item =>
    item?.request_mode === 'strict_hourly' || item?.prediction_source === 'strict_hourly'
  );
  const scheduledItems = hourlyItems.filter(item =>
    item?.request_mode === 'scheduled_interval' || item?.prediction_source === 'scheduled_interval'
  );
  const integrationRow = newerActual
    ? historyItems.find(item => item.target_meltno === newerActual.meltno && item.actual_ready !== false)
    : null;
  const unopenedCandidate = newerActual
    ? (status.candidate_targets || []).find(item => item.meltno === newerActual.meltno)
    : null;
  const associatedPrediction = newerActual
    ? [...historyItems, ...strictItems, ...scheduledItems].find(item =>
        (item.target_meltno === newerActual.meltno || item.matched_actual_meltno === newerActual.meltno) &&
        (item.has_prediction === true || hasNumber(item.prediction_si_mean))
      )
    : null;

  await page.waitForFunction(() => {
    const hourlyRows = document.querySelectorAll('#hourlyTableRows tr').length;
    return hourlyRows > 0;
  }, { timeout: 30000 });
  const uiState = await page.evaluate(() => ({
    title: document.querySelector('h1')?.textContent?.trim() || '',
    statusLine: document.querySelector('#statusLine')?.textContent?.trim() || '',
    strictStatus: document.querySelector('#strictHourlyStatus')?.textContent?.trim() || '',
    scheduleStatus: document.querySelector('#scheduleStatus')?.textContent?.trim() || '',
    historyRows: document.querySelectorAll('#historyRows tr').length,
    candidateCards: document.querySelectorAll('.candidate').length,
    chartPresent: !!document.querySelector('#chart'),
    horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    hourlyRows: document.querySelectorAll('#hourlyTableRows tr').length,
  }));
  const screenshotPath = path.join(screenshotDir, `${stamp}_8093_workbench_1920x1080.png`);
  await page.screenshot({ path: screenshotPath, fullPage: false, timeout: 30000 });
  const hourlyScreenshotPath = path.join(screenshotDir, `${stamp}_8093_hourly_table.png`);
  await page.locator('.hourly-panel').screenshot({ path: hourlyScreenshotPath, timeout: 30000 });
  const downloadResult = await savePageDownloads(page, exportDir, stamp);
  const downloadedFiles = downloadResult.outputs;

  writeCsv(path.join(exportDir, `${stamp}_history_union.csv`), historyItems);
  writeCsv(path.join(exportDir, `${stamp}_strict_hourly.csv`), strictItems);
  writeCsv(path.join(exportDir, `${stamp}_scheduled_interval.csv`), scheduledItems);
  writeCsv(path.join(exportDir, `${stamp}_hourly_table.csv`), Array.isArray(hourlyTable.items) ? hourlyTable.items : []);

  const python = process.env.PYTHON || 'python';
  const remoteProbe = spawnSync(python, [
    '-B', path.join(process.cwd(), 'tools', 'remote_22012_session.py'), 'run', '--',
    '--allow-agents-password', '--no-profile', '--timeout', '180',
    '--workdir', 'F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    '--script', path.join(process.cwd(), 'tools', 'remote_probe_si_v20_acceptance.ps1'),
  ], {
    cwd: process.cwd(),
    encoding: 'utf8',
    timeout: 120000,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
  });
  const remoteProbePath = path.join(apiDir, `${stamp}_remote_runtime_probe.txt`);
  fs.writeFileSync(remoteProbePath, `${remoteProbe.stdout || ''}${remoteProbe.stderr || ''}`, 'utf8');
  const remoteProbeResult = parseEmbeddedJson(remoteProbe.stdout);
  const databaseProbe = spawnSync(python, [
    '-B', path.join(process.cwd(), 'tools', 'verify_si_v20_strict_hourly_production.py'),
  ], { cwd: process.cwd(), encoding: 'utf8', timeout: 60000 });
  const databaseProbePath = path.join(apiDir, `${stamp}_strict_hourly_database_probe.json`);
  fs.writeFileSync(databaseProbePath, `${databaseProbe.stdout || ''}${databaseProbe.stderr || ''}`, 'utf8');

  const apiHealthy = Object.values(apiResults).every(item => item.ok && item.body?.ok !== false);
  const strictSlot = strictStatus.current_slot || {};
  const strictSlotHealthy = ['succeeded', 'success', 'pending', 'running'].includes(String(strictSlot.slot_status || strictSlot.status || '').toLowerCase());
  const uiHealthy = pageErrors.length === 0 && downloadResult.errors.length === 0 && downloadedFiles.length === 3 &&
    uiState.horizontalOverflow <= 1 && uiState.chartPresent && uiState.hourlyRows > 0;
  const remoteRuntimeHealthy = remoteProbe.status === 0 && remoteProbeResult?.ok === true;
  const strictDatabaseHealthy = databaseProbe.status === 0;
  const newHeatIntegrated = Boolean(newerActual && integrationRow && !unopenedCandidate);
  const predictionLinked = Boolean(associatedPrediction);
  const passed = apiHealthy && strictSlotHealthy && uiHealthy && remoteRuntimeHealthy &&
    strictDatabaseHealthy && newHeatIntegrated && predictionLinked;

  const result = {
    schema: 'ops.si-v20.new-heat-hourly-acceptance.v1',
    checked_at: now.toISOString(),
    base_url: baseUrl,
    baseline,
    latest_actual: latestActual,
    newer_actual: newerActual || null,
    api_healthy: apiHealthy,
    ui_healthy: uiHealthy,
    remote_runtime_healthy: remoteRuntimeHealthy,
    remote_runtime_probe_result: remoteProbeResult,
    strict_database_healthy: strictDatabaseHealthy,
    strict_slot_healthy: strictSlotHealthy,
    strict_slot: strictSlot,
    new_heat_integrated: newHeatIntegrated,
    prediction_linked: predictionLinked,
    prediction_association: associatedPrediction || null,
    page_errors: pageErrors,
    download_errors: downloadResult.errors,
    ui_state: uiState,
    schedule_status: schedule,
    metrics: {
      history: history.metrics || null,
      strict_hourly: predictionMetrics(strictItems),
      strict_hourly_api_probe: {
        count: strictHistoryProbe.count ?? null,
        limit: 1,
        schema: strictHistoryProbe.schema || null,
      },
      scheduled_interval: predictionMetrics(scheduledItems),
      hourly_table: hourlyTable.metrics || null,
    },
    artifacts: {
      screenshot: path.relative(outputDir, screenshotPath).replaceAll('\\', '/'),
      hourly_table_screenshot: path.relative(outputDir, hourlyScreenshotPath).replaceAll('\\', '/'),
      api_snapshot: `evidence/api/${stamp}_api_snapshot.json`,
      remote_runtime_probe: `evidence/api/${stamp}_remote_runtime_probe.txt`,
      strict_database_probe: `evidence/api/${stamp}_strict_hourly_database_probe.json`,
      downloads: downloadedFiles.map(file => path.relative(outputDir, file).replaceAll('\\', '/')),
      history_csv: `exports/${stamp}_history_union.csv`,
      strict_hourly_csv: `exports/${stamp}_strict_hourly.csv`,
      scheduled_interval_csv: `exports/${stamp}_scheduled_interval.csv`,
      hourly_table_csv: `exports/${stamp}_hourly_table.csv`,
    },
    passed,
    state: passed ? 'accepted_new_heat_closed_loop' : newerActual ? 'new_heat_waiting_full_closed_loop' : 'waiting_new_heat',
  };
  const resultPath = path.join(outputDir, `${stamp}_check.json`);
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2), 'utf8');
  fs.appendFileSync(path.join(outputDir, 'hourly_checks.jsonl'), `${JSON.stringify(result)}\n`, 'utf8');

  const report = `# V20 新炉次实时接入持续验收报告\n\n` +
    `- 验收状态：**${passed ? '通过' : '持续监控中'}**\n` +
    `- 基线炉次：${baseline.meltno || '无'}（${baseline.open_ts || '无开口时间'}，Si=${baseline.si_avg ?? '无'}%）\n` +
    `- 本次最新实际炉次：${latestActual?.meltno || '无'}（Si=${latestActual?.si_avg ?? '无'}%）\n` +
    `- 新炉次已接入：${newHeatIntegrated ? '是' : '否'}\n` +
    `- 新炉次已有预测关联：${predictionLinked ? '是' : '否'}\n` +
    `- API / 页面 / 远端运行时 / 严格整点槽 / 整点数据库：${apiHealthy ? '正常' : '异常'} / ${uiHealthy ? '正常' : '异常'} / ${remoteRuntimeHealthy ? '正常' : '异常'} / ${strictSlotHealthy ? '正常' : '异常'} / ${strictDatabaseHealthy ? '正常' : '异常'}\n` +
    `- 最近检查：${now.toISOString()}\n\n` +
    `## 最近截图\n\n![8093 V20工作台](${result.artifacts.screenshot})\n\n![每小时Si预测与炉次化验汇总](${result.artifacts.hourly_table_screenshot})\n\n` +
    `## 可导出证据\n\n` +
    result.artifacts.downloads.map(file => `- [页面导出 ${path.basename(file)}](${file})`).join('\n') + '\n' +
    `- [历史实际与预测并集 CSV](${result.artifacts.history_csv})\n` +
    `- [严格整点预测 CSV](${result.artifacts.strict_hourly_csv})\n` +
    `- [可调定时预测 CSV](${result.artifacts.scheduled_interval_csv})\n` +
    `- [每小时预测与炉次化验汇总 CSV](${result.artifacts.hourly_table_csv})\n` +
    `- [API原始快照](${result.artifacts.api_snapshot})\n` +
    `- [220.12运行时探针](${result.artifacts.remote_runtime_probe})\n` +
    `- [严格整点数据库探针](${result.artifacts.strict_database_probe})\n` +
    `- [本次结构化结论](${path.basename(resultPath)})\n\n` +
    `## 判定规则\n\n只有比基线更新的炉次携带实际平均Si进入status与history、从未开口候选中移除、存在预测关联，同时API、页面和严格整点槽健康，才结束监控。\n`;
  fs.writeFileSync(path.join(outputDir, 'acceptance_report.md'), report, 'utf8');
  const html = `<!doctype html><meta charset="utf-8"><title>V20新炉次验收报告</title>` +
    `<style>body{font-family:SimSun,serif;max-width:1200px;margin:24px auto;line-height:1.6;color:#17242d}img{max-width:100%;border:1px solid #789}code{background:#eef;padding:2px 4px}</style>` +
    `<h1>V20 新炉次实时接入持续验收报告</h1><p><b>状态：${passed ? '通过' : '持续监控中'}</b></p>` +
    `<ul><li>基线炉次：${htmlEscape(baseline.meltno)}</li><li>最新实际炉次：${htmlEscape(latestActual?.meltno)}</li>` +
    `<li>新炉次已接入：${newHeatIntegrated ? '是' : '否'}</li><li>预测关联：${predictionLinked ? '是' : '否'}</li>` +
    `<li>API / 页面 / 远端运行时 / 严格整点槽 / 整点数据库：${apiHealthy ? '正常' : '异常'} / ${uiHealthy ? '正常' : '异常'} / ${remoteRuntimeHealthy ? '正常' : '异常'} / ${strictSlotHealthy ? '正常' : '异常'} / ${strictDatabaseHealthy ? '正常' : '异常'}</li></ul>` +
    `<h2>最近截图</h2><img src="${htmlEscape(result.artifacts.screenshot)}"><h3>每小时Si预测与炉次化验汇总</h3><img src="${htmlEscape(result.artifacts.hourly_table_screenshot)}">` +
    `<h2>可导出证据</h2><ul>` +
    [...result.artifacts.downloads, result.artifacts.history_csv, result.artifacts.strict_hourly_csv, result.artifacts.scheduled_interval_csv, result.artifacts.hourly_table_csv, result.artifacts.api_snapshot, result.artifacts.remote_runtime_probe, result.artifacts.strict_database_probe]
      .map(file => `<li><a href="${htmlEscape(file)}">${htmlEscape(path.basename(file))}</a></li>`).join('') +
    `</ul><p>最近检查：${htmlEscape(now.toISOString())}</p>`;
  fs.writeFileSync(path.join(outputDir, 'acceptance_report.html'), html, 'utf8');

  await context.close();
  await browser.close();
  console.log(JSON.stringify({ ...result, result_file: resultPath }, null, 2));
  process.exitCode = passed ? 0 : 2;
}

run().catch(error => {
  console.error(error?.stack || String(error));
  // Playwright may keep browser transports alive after a mid-run exception.
  // This CLI is an hourly one-shot acceptance probe, so fail deterministically
  // instead of leaving the scheduler blocked until an outer timeout kills it.
  process.exit(1);
});
