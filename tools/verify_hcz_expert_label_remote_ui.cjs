#!/usr/bin/env node
/** Read-only production smoke for REQ-HCZ-EXPERT-WEAK-LABEL-20260810. */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const base = String(process.env.HCZ_LABEL_BASE_URL || 'http://10.30.220.12:8892').replace(/\/+$/, '');
const output = path.resolve(__dirname, '..', 'logs', 'hcz_expert_label_20260810', 'remote_22012');

(async()=>{
  fs.mkdirSync(output,{recursive:true});
  let browser;
  try {
    try { browser=await chromium.launch({channel:'msedge',headless:true}); }
    catch (_error) { browser=await chromium.launch({headless:true}); }
    const context=await browser.newContext({viewport:{width:1366,height:768}});
    const page=await context.newPage(); const errors=[]; const badResponses=[];
    page.on('pageerror',error=>errors.push(String(error)));
    page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
    page.on('response',response=>{if(response.status()>=400)badResponses.push({status:response.status(),url:response.url()});});
    const url=`${base}/hcz-labeling.html?qa=remote-${Date.now()}`;
    await page.goto(url,{waitUntil:'networkidle',timeout:90000});
    await page.waitForFunction(()=>document.querySelector('#serviceStatus')?.textContent.includes('就绪'),null,{timeout:60000});
    await page.waitForFunction(()=>document.querySelector('#contextState')?.classList.contains('ready'),null,{timeout:90000});
    const iframe=page.frames().find(frame=>frame.url().includes('labeling_blind=1'));
    if(!iframe)throw new Error('blind replay iframe missing');
    await iframe.waitForFunction(()=>document.body.dataset.hczLabelBlind==='true');
    const main=await page.evaluate(()=>({
      status:document.querySelector('#serviceStatus').textContent.trim(),
      context:document.querySelector('#contextState').textContent.trim(),
      count:document.querySelector('#historyCount').textContent.trim(),
      overflowX:Math.max(0,document.documentElement.scrollWidth-innerWidth),
      submitDisabled:document.querySelector('#submitButton').disabled,
      title:document.title,
    }));
    const blind=await iframe.evaluate(()=>({
      mode:document.body.dataset.hczLabelBlind,
      toggleDisplay:getComputedStyle(document.querySelector('#cohesiveToggle').closest('label')).display,
      estimateDisplay:getComputedStyle(document.querySelector('.estimate-card')).display,
      checked:document.querySelector('#cohesiveToggle').checked,
      frame:document.querySelector('#frameCounter').textContent.trim(),
    }));
    const screenshot=path.join(output,'edge_1366x768.png'); await page.screenshot({path:screenshot,fullPage:false});
    const ok=errors.length===0&&badResponses.length===0&&main.overflowX<=1&&!main.submitDisabled&&blind.mode==='true'&&blind.toggleDisplay==='none'&&blind.estimateDisplay==='none'&&!blind.checked;
    const report={ok,url,main,blind,errors,badResponses,screenshot};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
    await context.close(); if(!ok)process.exitCode=1;
  } finally { if(browser)await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
