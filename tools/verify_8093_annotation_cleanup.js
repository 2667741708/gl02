/* Verify 8093 annotation cleanup in source and a Chromium browser. */
const fs = require('fs');
const path = require('path');
let chromium = null;

const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, '高炉前端数据', 'frontend_dashboard_v3.server.html');
const baseUrl = process.argv[2] || 'http://10.30.220.12:8093/';
const outputDir = path.join(root, 'logs', '8093_annotation_cleanup_20260714');
const routes = ['overview', 'diagnosis', 'optimization', 'trend', 'qa'];

function verifyStatic() {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const start = html.lastIndexOf('function FurnaceLayerFollowCard');
  const end = html.indexOf('FurnaceLayerCallouts=', start);
  const follow = html.slice(start, end);
  const required = [
    "function Panel({title,children,className=''})",
    'v3-annotation-cleanup',
    '.furnace-layer-callouts .furnace-layer-unit{font-weight:900!important}',
  ];
  const missing = required.filter(token => !html.includes(token));
  if (missing.length) throw new Error(`missing cleanup markers: ${missing.join(', ')}`);
  if (/items\.length}项|text-bad|text-warn/.test(follow)) {
    throw new Error('active furnace callout renderer still emits a count badge or status color');
  }
  return { html: htmlPath, activeFollowRendererChecked: true };
}

async function verifyBrowser() {
  if (process.argv.includes('--static-only')) return { skipped: 'static-only' };
  try {
    ({ chromium } = require('playwright'));
  } catch (error) {
    return { skipped: `playwright unavailable: ${error.message}` };
  }
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  await page.goto(`${baseUrl.replace(/\/$/, '')}/?annotation_cleanup=20260714#overview`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.locator('.furnace-layer-callouts.follow-model .furnace-layer-card').first().waitFor({ timeout: 45000 });
  const results = [];
  for (let index = 0; index < routes.length; index += 1) {
    const route = routes[index];
    if (index) {
      await page.locator('.bottom-nav .nav-btn').nth(index).click();
      await page.waitForFunction(target => location.hash === `#${target}`, route, { timeout: 15000 });
    }
    await page.waitForTimeout(700);
    const state = await page.evaluate(() => {
      const visible = selector => [...document.querySelectorAll(selector)].filter(node => {
        const style = getComputedStyle(node);
        return style.display !== 'none' && style.visibility !== 'hidden';
      });
      const cards = [...document.querySelectorAll('.furnace-layer-callouts.follow-model .furnace-layer-card')];
      return {
        route: location.hash,
        panelNotes: visible('.panel-note').length,
        coreNotes: visible('.core-metric-note').length,
        passiveForecastBadges: visible('.forecast-badge:not(label)').length,
        furnaceCards: cards.length,
        furnaceCountBadges: cards.reduce((count, card) => count + card.querySelectorAll('.furnace-layer-head b').length, 0),
        furnaceHeadColors: cards.map(card => getComputedStyle(card.querySelector('.furnace-layer-head span')).color),
        furnaceUnitColors: cards.flatMap(card => [...card.querySelectorAll('.furnace-layer-unit')].map(node => getComputedStyle(node).color)),
        furnaceUnitWeights: cards.flatMap(card => [...card.querySelectorAll('.furnace-layer-unit')].map(node => getComputedStyle(node).fontWeight)),
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      };
    });
    if (state.panelNotes || state.coreNotes || state.passiveForecastBadges || state.horizontalOverflow) {
      throw new Error(`visible explanatory label or overflow: ${JSON.stringify(state)}`);
    }
    if (route === 'overview') {
      if (state.furnaceCards !== 7 || state.furnaceCountBadges !== 0) throw new Error(`unexpected furnace count state: ${JSON.stringify(state)}`);
      if ([...state.furnaceHeadColors, ...state.furnaceUnitColors].some(color => color !== 'rgb(255, 255, 255)')) throw new Error(`furnace title or unit text is not white: ${JSON.stringify(state)}`);
      if (state.furnaceUnitWeights.some(weight => Number(weight) < 700)) throw new Error(`furnace unit text is not bold: ${JSON.stringify(state)}`);
    }
    await page.screenshot({ path: path.join(outputDir, `${route}.png`), fullPage: false });
    results.push(state);
  }
  await browser.close();
  if (errors.length) throw new Error(`browser errors: ${errors.join('; ')}`);
  return { viewport: '1366x768', routes: results, screenshots: outputDir };
}

(async () => {
  console.log(JSON.stringify({ static: verifyStatic(), browser: await verifyBrowser() }, null, 2));
})().catch(error => { console.error(error.stack || error.message); process.exit(1); });
