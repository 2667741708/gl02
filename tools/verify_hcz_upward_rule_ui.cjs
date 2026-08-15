#!/usr/bin/env node
/** Cross-engine UI acceptance for REQ-HCZ-RULE-SENSITIVITY-20260811. */

const fs = require('fs');
const http = require('http');
const path = require('path');
const playwrightPackage = process.env.PLAYWRIGHT_NODE_PACKAGE || 'playwright';
const { chromium, firefox, webkit } = require(playwrightPackage);

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, '高炉前端数据');
const OUTPUT = path.join(ROOT, 'logs', 'hcz_rule_sensitivity_20260811', 'viewport_matrix');
const ALL = [[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]];
const REP = [[1920,1080],[1366,768],[768,1024],[390,844]];

function currentPayload() {
  const metrics = {};
  for (const [key,label,unit,current,baseline,delta,direction,threshold] of [
    ['top_temperature','平均顶温','℃',198,180,18,'increase',15],
    ['total_pressure_drop','全压差','kPa',157,150,7,'increase',5],
    ['permeability_index','透气性指数','m³/(min·kPa)',7.3,8,-0.7,'decrease',0.5],
    ['gas_utilisation','煤气利用率','percentage_point',46.6,48,-1.4,'decrease',1],
    ['blast_pressure','冷风风压','kPa',357,350,7,'increase',5],
  ]) metrics[key] = {label,unit,current_24h_mean:current,baseline_5d_mean:baseline,delta,direction,threshold,current_valid_hours:24,baseline_valid_hours:120,coverage_pass:true,threshold_pass:true};
  const layers = Array.from({length:7},(_,i)=>({layer:i+7,current_24h_mean:130+i,baseline_5d_mean:112+i,delta_c:i<3?18-i*2:4,current_valid_hours:24,baseline_valid_hours:120,coverage_pass:true,rise_10c_pass:i<3,rise_20c_pass:false}));
  const defaults = {
    top_temperature_delta_c: 15,
    total_pressure_drop_kpa: 5,
    permeability_drop: 0.5,
    gas_utilisation_drop_pp: 1,
    cold_blast_pressure_rise_kpa: 5,
    body_temperature_delta_c: 10,
    min_directional_layers: 2,
    required_consecutive_hours: 12,
  };
  return {ok:true,status:'triggered',triggered:true,decision:'up',conclusion:'软熔带上移综合趋势规则已触发',evaluation_time:'2026-08-10T13:00:00+08:00',missing_reasons:[],cache:'miss',windows:{current_start:'2026-08-09T14:00:00+08:00',current_end:'2026-08-10T13:00:00+08:00'},metrics,body_temperature:{rising_layers:[7,8,9],strong_rising_layers:[],layers,gate_pass:true},sustained_trend:{required_consecutive_hours:12,max_consecutive_hours:14,qualified_hour_count:16,gate_pass:true},gates:{data_sufficient:true,core_all_pass:true,body_layers_pass:true,duration_pass:true},source:{latest_sample_time:'2026-08-10T13:01:00+08:00',query_elapsed_ms:142,read_only:true},sensitivity:{read_only_trial:true,parameters:Object.fromEntries(Object.entries(defaults).map(([key,value])=>[key,{default:value}]))}};
}

function sensitivityPayload(topThreshold) {
  const changed = topThreshold <= 10;
  const empty = {evaluation_hours:2160,data_sufficient_hours:2110,triggered_evaluation_hours:0,episode_count:0,episodes:[]};
  const trialUp = changed ? {...empty,triggered_evaluation_hours:14,episode_count:2,episodes:[{start:'2026-08-09T22:00:00+08:00',end:'2026-08-10T04:00:00+08:00'}]} : empty;
  return {
    ok:true,history_days:90,evaluation_start:'2026-05-13T14:00:00+08:00',evaluation_end:'2026-08-11T13:00:00+08:00',
    baseline:{up:empty,down:empty},scenario:{up:trialUp,down:empty},
    comparison:{up:{added_triggered_hour_count:changed?14:0,removed_triggered_hour_count:0,added_triggered_hours:changed?['2026-08-09T22:00:00+08:00']:[]},down:{added_triggered_hour_count:0,removed_triggered_hour_count:0,added_triggered_hours:[]}},
    source:{hourly_record_count:145000,history_cache:'hit',query_elapsed_ms:0,evaluation_elapsed_ms:210,read_only:true},
  };
}

function createServer() {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname === '/api/hcz-upward-rule') {
      response.writeHead(200, {'Content-Type':'application/json','Cache-Control':'no-store'});
      return response.end(JSON.stringify(currentPayload()));
    }
    if (url.pathname === '/api/hcz-rule-sensitivity') {
      response.writeHead(200, {'Content-Type':'application/json','Cache-Control':'no-store'});
      return response.end(JSON.stringify(sensitivityPayload(Number(url.searchParams.get('top_temperature_delta_c')))));
    }
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'hcz_upward_rule.html';
    const target = path.resolve(WEB, relative);
    if (!target.startsWith(path.resolve(WEB) + path.sep)) return response.writeHead(403).end();
    fs.readFile(target, (error, data) => {
      if (error) return response.writeHead(404).end();
      const type = {'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[path.extname(target)] || 'application/octet-stream';
      response.writeHead(200, {'Content-Type':type});
      response.end(data);
    });
  });
}

async function inspect(browser, engine, base, width, height) {
  const context = await browser.newContext({viewport:{width,height}});
  const page = await context.newPage();
  const errors = [];
  const responses = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('response', response => { if (response.status() >= 400) responses.push({status:response.status(),url:response.url()}); });
  await page.goto(`${base}/hcz_upward_rule.html?qa=${engine}-${width}x${height}`, {waitUntil:'networkidle',timeout:60000});
  await page.waitForFunction(() => document.querySelector('#serviceState')?.textContent.includes('就绪'));
  await page.fill('#trialTopTemperature', '10');
  await page.click('#runSensitivityButton');
  await page.waitForFunction(() => !document.querySelector('#sensitivityResult')?.hidden);
  const state = await page.evaluate(() => ({
    overflowX: Math.max(0, document.documentElement.scrollWidth - innerWidth),
    metricRows: document.querySelectorAll('#metricBody tr').length,
    metricLabels: Array.from(document.querySelectorAll('#metricBody tr td:first-child')).map(node => node.textContent.trim()),
    gasCells: Array.from(document.querySelectorAll('#metricBody tr')).find(row => row.querySelector('td')?.textContent.trim() === '煤气利用率') ? Array.from(Array.from(document.querySelectorAll('#metricBody tr')).find(row => row.querySelector('td')?.textContent.trim() === '煤气利用率').querySelectorAll('td')).map(cell => cell.textContent.trim()) : [],
    layerCards: document.querySelectorAll('#layerGrid .layer').length,
    gateCards: document.querySelectorAll('#gateGrid .gate').length,
    thresholdInputs: document.querySelectorAll('#sensitivityForm input[type="number"]').length,
    summary: document.querySelector('#sensitivitySummary').textContent.trim(),
    scenarioUp: document.querySelector('#scenarioUpEpisodes').textContent.trim(),
    resultVisible: getComputedStyle(document.querySelector('#sensitivityResult')).display !== 'none',
    marker: document.querySelector('[data-feature="REQ-HCZ-RULE-SENSITIVITY-20260811"]') !== null,
    font: getComputedStyle(document.body).fontFamily,
  }));
  const screenshot = path.join(OUTPUT, `${engine}_${width}x${height}.png`);
  await page.screenshot({path:screenshot,fullPage:false});
  await context.close();
  return {engine,viewport:`${width}x${height}`,errors,responses,screenshot,...state};
}

(async () => {
  fs.mkdirSync(OUTPUT, {recursive:true});
  const app = createServer();
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${app.address().port}`;
  const browsers = [];
  const results = [];
  try {
    for (const [name,type,views] of [['chromium',chromium,ALL],['firefox',firefox,REP],['webkit',webkit,REP]]) {
      const browser = await type.launch({headless:true});
      browsers.push(browser);
      for (const [width,height] of views) results.push(await inspect(browser,name,base,width,height));
    }
    const failures = results.flatMap(item => {
      const prefix = `${item.engine} ${item.viewport}`;
      const issues = [];
      if (item.errors.length || item.responses.length) issues.push(`${prefix}: browser errors`);
      if (item.overflowX > 1) issues.push(`${prefix}: overflow ${item.overflowX}`);
      if (item.metricRows !== 5 || item.layerCards !== 7 || item.gateCards !== 3) issues.push(`${prefix}: current-rule rows missing`);
      if (!item.metricLabels.includes('冷风风压') || item.metricLabels.includes('热风压力')) issues.push(`${prefix}: cold-blast label contract failed`);
      if (!item.gasCells[1]?.endsWith('%') || !item.gasCells[2]?.endsWith('%') || !item.gasCells[3]?.includes('个百分点') || !item.gasCells[4]?.includes('个百分点')) issues.push(`${prefix}: gas-utilisation unit display failed`);
      if (item.thresholdInputs !== 8 || !item.marker || !item.resultVisible) issues.push(`${prefix}: sensitivity controls missing`);
      if (item.scenarioUp !== '2次' || !item.summary.includes('0→2')) issues.push(`${prefix}: sensitivity result not rendered`);
      if (!item.font.includes('SimSun') && !item.font.includes('宋体')) issues.push(`${prefix}: font contract failed`);
      return issues;
    });
    const report = {ok:failures.length===0,cases:results.length,results,failures};
    fs.writeFileSync(path.join(OUTPUT,'report.json'), JSON.stringify(report,null,2));
    console.log(JSON.stringify({ok:report.ok,cases:report.cases,failures},null,2));
    if (failures.length) process.exitCode = 1;
  } finally {
    for (const browser of browsers) await browser.close();
    await new Promise(resolve => app.close(resolve));
  }
})().catch(error => { console.error(error); process.exit(1); });
