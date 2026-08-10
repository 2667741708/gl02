const { chromium } = require('playwright');

const URL = 'http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768&pspace_ws_port=8770&minutes=90&inspect=ws-intervals-20260808';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const sockets = [];
  page.on('websocket', ws => {
    const item = { url: ws.url(), frames: [], raw: [], openedAt: Date.now() };
    sockets.push(item);
    ws.on('framereceived', data => {
      if (typeof data !== 'string') data = data?.toString?.() || '';
      if (item.raw.length < 2) item.raw.push({ type: typeof data, preview: String(data).slice(0, 200) });
      try {
        const message = JSON.parse(data);
        if (message.type === 'init' || message.type === 'tick') {
          item.frames.push({ type: message.type, timestamp: message.timestamp || '', receivedAt: Date.now(), keys: Object.keys(message.values || message.history || {}).length });
        }
      } catch (_) {}
    });
  });
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(15000);
  const report = sockets.map(item => {
    const timestamps = item.frames.map(frame => Date.parse(frame.timestamp)).filter(Number.isFinite);
    const deltas = timestamps.slice(1).map((ts, index) => ts - timestamps[index]);
    return {
      url: item.url,
      frameCount: item.frames.length,
      firstFrames: item.frames.slice(0, 3),
      lastFrames: item.frames.slice(-3),
      timestampDeltasMs: deltas,
      distinctDeltasMs: [...new Set(deltas)].sort((a, b) => a - b),
      initTimestamp: item.frames.find(frame => frame.type === 'init')?.timestamp || ''
      ,raw: item.raw
    };
  });
  console.log(JSON.stringify({ url: URL, sockets: report }, null, 2));
  await browser.close();
}

main().catch(error => { console.error(error); process.exitCode = 1; });
