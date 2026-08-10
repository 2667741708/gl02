const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, '高炉前端数据', 'frontend_dashboard_v3.server.html');
const babelPath = path.join(root, '高炉前端数据', 'libs', 'babel.min.js');
const html = fs.readFileSync(htmlPath, 'utf8');
const marker = '<script type="text/babel" data-presets="typescript,react">';
const start = html.indexOf(marker);
if (start < 0) throw new Error('text/babel application script was not found');
const bodyStart = start + marker.length;
const bodyEnd = html.indexOf('</script>', bodyStart);
if (bodyEnd < 0) throw new Error('text/babel application script is not closed');

const context = { console, setTimeout, clearTimeout, Date, Promise, performance };
context.window = context;
context.self = context;
context.globalThis = context;
vm.createContext(context);
try {
  vm.runInContext(fs.readFileSync(babelPath, 'utf8'), context, { filename: babelPath });
  context.Babel.transform(html.slice(bodyStart, bodyEnd), {
    filename: 'frontend_dashboard_v3.server.tsx',
    presets: ['typescript', 'react'],
    sourceType: 'script',
  });
  console.log(JSON.stringify({ ok: true, html: htmlPath, compiler: babelPath }));
} catch (error) {
  console.error(String(error && error.message ? error.message : error));
  process.exitCode = 1;
}
