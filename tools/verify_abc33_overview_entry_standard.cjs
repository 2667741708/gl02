const path = require('path');
const fs = require('fs');
let playwright;
try { playwright = require('playwright'); }
catch (_) { playwright = require('C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }

const fixture = 'file:///' + path.resolve('tests/fixtures/abc33_overview_entry_fixture.html').replaceAll('\\','/');
const outputDir = path.resolve('logs/abc33_overview_entry_standard');
fs.mkdirSync(outputDir,{recursive:true});
const matrix = {
  chromium:[[1280,720],[1366,768],[1440,900],[1546,864],[1920,1080],[1024,768],[768,1024],[390,844],[375,667]],
  firefox:[[1920,1080],[1366,768],[768,1024],[390,844]],
  webkit:[[1920,1080],[1366,768],[768,1024],[390,844]],
};

(async()=>{
  const results=[];
  for(const [engine,viewports] of Object.entries(matrix)){
    const browser=await playwright[engine].launch({headless:true});
    for(const [width,height] of viewports){
      const page=await browser.newPage({viewport:{width,height}});
      const errors=[];
      page.on('pageerror',error=>errors.push(String(error)));
      page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
      await page.goto(fixture,{waitUntil:'load'});
      await page.waitForSelector('.overview-furnace-panel-v12 .abc33-entry-overview');
      const before=await page.evaluate(()=>({
        entryParent:document.querySelector('.abc33-entry-overview')?.parentElement?.className||'',
        fixedFallback:!!document.querySelector('.abc33-entry-fallback'),
        overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,
      }));
      await page.click('.abc33-entry-overview');
      await page.waitForTimeout(80);
      const after=await page.evaluate(()=>({
        visible:getComputedStyle(document.querySelector('#abc-furnace-rules-production')).display!=='none',
        cards:document.querySelectorAll('.abc33-card').length,
        title:document.querySelector('#abc-furnace-rules-production .abc33-head h2')?.textContent||'',
        closeText:document.querySelector('#abc-furnace-rules-production .abc33-close')?.textContent||'',
        overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,
      }));
      const ok=before.entryParent.includes('panel-head')&&!before.fixedFallback&&!before.overflow&&after.visible&&after.cards===33&&after.title.includes('33项炉况研判')&&after.closeText==='关闭总览'&&!after.overflow&&errors.length===0;
      results.push({engine,width,height,ok,before,after,errors});
      if(engine==='chromium'&&width===1366&&height===768)await page.screenshot({path:path.join(outputDir,'overview-entry-1366x768.png'),fullPage:true});
      await page.close();
    }
    await browser.close();
  }
  const report={schema:'abc33.overview-entry.standard.v1',fixture,checks:results.length,passed:results.filter(x=>x.ok).length,failed:results.filter(x=>!x.ok),results};
  fs.writeFileSync(path.join(outputDir,'report.json'),JSON.stringify(report,null,2));
  process.stdout.write(JSON.stringify({checks:report.checks,passed:report.passed,failed:report.failed.length,report:path.join(outputDir,'report.json')},null,2));
  process.exit(report.failed.length?1:0);
})().catch(error=>{console.error(error);process.exit(1)});
