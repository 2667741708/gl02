#!/usr/bin/env node
/** Cross-engine UI acceptance for REQ-HCZ-EXPERT-WEAK-LABEL-20260810. */

const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium, firefox, webkit } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, '高炉前端数据', 'soft_zone_replay');
const OUTPUT = path.join(ROOT, 'logs', 'hcz_expert_label_20260810', 'viewport_matrix');
const ALL = [[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]];
const REPRESENTATIVE = [[1920,1080],[1366,768],[768,1024],[390,844]];
const labels = [];

function replayPayload() {
  const start = new Date('2026-08-10T06:00:00');
  const timeline = Array.from({ length:73 }, (_, index) => new Date(start.getTime() + index * 300000).toISOString().slice(0,19));
  const points = [];
  for (let layer=7; layer<=16; layer+=1) {
    for (let sector=0; sector<8; sector+=1) {
      points.push({ id:`T_body_L${layer}_${'ABCDEFGH'[sector]}`, metric:'temperature', layer, height_m:16.86+(layer-7)*1.7, azimuth:'ABCDEFGH'[sector], angle_deg:sector*45, region:layer<9?'belly':layer===9?'waist':'stack_lower', unit:'℃', values:timeline.map((_, frame)=>120+layer*4+sector+20*Math.sin(frame/8)) });
    }
  }
  for (const [band,height] of [['lower',20.35],['middle',23.488],['upper',28.976]]) {
    for (let sector=0; sector<6; sector+=1) points.push({ id:`P_static_${band}_${'ABCDEF'[sector]}`, metric:'pressure', pressure_band:band, height_m:height, azimuth:'ABCDEF'[sector], angle_deg:sector*60, region:'stack_lower', unit:'kPa', values:timeline.map((_,frame)=>20+sector+Math.sin(frame/10)) });
  }
  return { ok:true, start_time:timeline[0], end_time:timeline.at(-1), timeline, points, scales:{temperature:{low:115,high:225}}, coverage:{temperature:1,pressure:1}, cohesive_zone:[], evidence:{temperature:'measured',cohesive_zone:'estimated',control_use:'prohibited'} };
}

function sendJson(response, status, payload) {
  const body = Buffer.from(JSON.stringify(payload));
  response.writeHead(status, {'Content-Type':'application/json; charset=utf-8','Content-Length':body.length,'Cache-Control':'no-store'});
  response.end(body);
}

function fixtureServer() {
  const replay = replayPayload();
  return http.createServer((request,response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname === '/favicon.ico') return response.writeHead(204).end();
    if (url.pathname === '/api/health') return sendJson(response,200,{ok:true,latest_sample_time:replay.end_time,cohesive_available:true,hcz_label_enabled:true,hcz_label_blind_to_model:true});
    if (url.pathname === '/api/replay') return sendJson(response,200,replay);
    if (url.pathname === '/api/hcz-label-config') return sendJson(response,200,{ok:true,blind_to_model:true,model_outputs_included:false,identity:{sub:'现场标注席',role:'blast_furnace_operator'}});
    if (url.pathname === '/api/hcz-label-context') return sendJson(response,200,{ok:true,context_mode:'contemporaneous_blind',primary_coverage:1,source_data_hash:'a'.repeat(64),blind_to_model:true,model_outputs_included:false});
    if (url.pathname === '/api/hcz-labels' && request.method === 'GET') return sendJson(response,200,{ok:true,count:labels.length,labels:[...labels].reverse()});
    if (url.pathname === '/api/hcz-labels' && request.method === 'POST') {
      let body=''; request.on('data', chunk => { body += chunk; }); request.on('end', () => {
        const payload = JSON.parse(body);
        const item = { id:labels.length+1, reference_id:`HCZ-fixture-${labels.length+1}`, available_at:new Date().toISOString(), context_mode:'contemporaneous_blind', blind_to_model:true, created:true, ...payload };
        labels.push(item); sendJson(response,201,{ok:true,label:item});
      }); return;
    }
    if (url.pathname === '/api/hcz-label-export') return response.writeHead(200,{'Content-Type':'text/csv'}).end('id,reference_id\n');
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html';
    const target = path.resolve(WEB_ROOT, relative);
    if (!target.startsWith(path.resolve(WEB_ROOT)+path.sep)) return response.writeHead(403).end();
    fs.readFile(target,(error,data)=>{
      if (error) return response.writeHead(404).end();
      const type = {'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[path.extname(target)] || 'application/octet-stream';
      response.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store'}); response.end(data);
    });
  });
}

async function inspect(browser, engine, base, width, height) {
  const context = await browser.newContext({viewport:{width,height}});
  const page = await context.newPage();
  const errors=[]; page.on('pageerror', error=>errors.push(String(error))); page.on('console', message=>{if(message.type()==='error') errors.push(message.text());});
  await page.goto(`${base}/hcz-labeling.html?qa=${engine}-${width}x${height}`,{waitUntil:'networkidle',timeout:60000});
  await page.waitForFunction(()=>document.querySelector('#serviceStatus')?.textContent.includes('就绪'));
  await page.waitForFunction(()=>document.querySelector('#contextState')?.classList.contains('ready'));
  const iframe = page.frames().find(frame=>frame.url().includes('labeling_blind=1'));
  if (!iframe) throw new Error('blind replay iframe missing');
  await iframe.waitForFunction(()=>document.body.dataset.hczLabelBlind==='true');
  const metrics = await page.evaluate(()=>({
    overflowX:Math.max(0,document.documentElement.scrollWidth-innerWidth),
    submitVisible:document.querySelector('#submitButton').getBoundingClientRect().height>0,
    status:document.querySelector('#serviceStatus').textContent.trim(),
    blindText:document.querySelector('.subtitle').textContent,
    bodyFont:getComputedStyle(document.body).fontFamily,
    context:document.querySelector('#contextState').textContent,
  }));
  const blind = await iframe.evaluate(()=>({toggleHidden:getComputedStyle(document.querySelector('#cohesiveToggle').closest('label')).display==='none',estimateHidden:getComputedStyle(document.querySelector('.estimate-card')).display==='none',includeChecked:document.querySelector('#cohesiveToggle').checked}));
  const screenshot=path.join(OUTPUT,`${engine}_${width}x${height}.png`); await page.screenshot({path:screenshot,fullPage:false});
  await context.close(); return {engine,viewport:`${width}x${height}`,errors,screenshot,...metrics,...blind};
}

async function submitAcceptance(browser, base) {
  const context=await browser.newContext({viewport:{width:1366,height:768}}); const page=await context.newPage();
  await page.goto(`${base}/hcz-labeling.html?qa=submit`,{waitUntil:'networkidle'});
  await page.waitForFunction(()=>document.querySelector('#contextState')?.classList.contains('ready'));
  await page.locator('label:has(input[name="root_level_label"][value="normal"]) span').click({force:true});
  await page.locator('label:has(input[name="movement_label"][value="stable"]) span').click({force:true});
  await page.locator('#confidenceGrade').selectOption('4'); await page.locator('#operatorName').fill('GL02-甲班');
  await page.locator('input[name="evidence"][value="temperature_pattern"]').check();
  await page.locator('#submitButton').click(); await page.waitForFunction(()=>!document.querySelector('#formSuccess').hidden);
  const result={success:await page.locator('#formSuccess').textContent(),count:await page.locator('#historyCount').textContent()};
  await context.close(); return result;
}

(async()=>{
  fs.mkdirSync(OUTPUT,{recursive:true}); const server=fixtureServer(); await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`; const results=[]; const launched=[];
  try {
    for (const [name,type,viewports] of [['chromium',chromium,ALL],['firefox',firefox,REPRESENTATIVE],['webkit',webkit,REPRESENTATIVE]]) {
      const browser=await type.launch({headless:true}); launched.push(browser);
      for (const [width,height] of viewports) results.push(await inspect(browser,name,base,width,height));
    }
    const submit=await submitAcceptance(launched[0],base);
    const failures=results.flatMap(item=>{
      const prefix=`${item.engine} ${item.viewport}`; const list=[];
      if(item.errors.length) list.push(`${prefix}: errors ${item.errors.join('|')}`);
      if(item.overflowX>1) list.push(`${prefix}: overflow ${item.overflowX}`);
      if(!item.submitVisible||!item.toggleHidden||!item.estimateHidden||item.includeChecked) list.push(`${prefix}: blind controls contract failed`);
      if(!item.blindText.includes('不加载、不展示HCZ模型结果')) list.push(`${prefix}: blind boundary text missing`);
      if(!item.bodyFont.includes('SimSun')&&!item.bodyFont.includes('宋体')) list.push(`${prefix}: font contract failed`);
      return list;
    });
    const report={ok:failures.length===0,base,results,submit,failures}; fs.writeFileSync(path.join(OUTPUT,'report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({ok:report.ok,cases:results.length,submit,failures},null,2)); if(failures.length) process.exitCode=1;
  } finally { for(const browser of launched) await browser.close(); await new Promise(resolve=>server.close(resolve)); }
})().catch(error=>{console.error(error);process.exit(1);});
