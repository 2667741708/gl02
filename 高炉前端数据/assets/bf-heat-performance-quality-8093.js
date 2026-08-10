/* REQ-8093-HEAT-PERFORMANCE-QUALITY-20260806 */
(() => {
  'use strict';
  if (window.__BF_HEAT_PERFORMANCE_QUALITY_8093__) return;
  if (location.port && location.port !== '8093') return;
  window.__BF_HEAT_PERFORMANCE_QUALITY_8093__ = true;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
  const num = (value, digits = 2) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '--';
  const ts = value => value ? String(value).replace('T', ' ').slice(0, 16) : '--';
  const bandText = value => ({below_target: '低于目标带', target: '目标带内', above_target: '高于目标带'}[value] || '待化验');
  const tone = value => ({below_target: 'warn', target: 'good', above_target: 'bad'}[value] || 'muted');

  const style = document.createElement('style');
  style.id = 'bf-heat-performance-quality-8093-style';
  style.textContent = `
    .bf-heat-trigger{position:fixed;right:12px;top:78px;z-index:2147482000;height:36px;padding:0 14px;border:1px solid #3ba982;border-radius:6px;background:#0b322f;color:#dffbf0;font:900 14px/1 SimSun,"宋体",serif;box-shadow:0 6px 18px rgba(0,0,0,.35);cursor:pointer}
    .bf-heat-trigger:hover,.bf-heat-trigger:focus-visible{background:#125044;outline:2px solid #75d8b7;outline-offset:2px}
    .bf-heat-trigger small{display:block;margin-top:2px;color:#9bdac5;font-size:9px}
    .bf-heat-drawer{position:fixed;z-index:2147483000;right:12px;top:70px;width:min(1040px,calc(100vw - 24px));height:min(76vh,720px);display:none;grid-template-rows:48px minmax(0,1fr);border:1px solid #3c829b;border-radius:8px;background:#071722;color:#e8f4f8;box-shadow:0 20px 60px rgba(0,0,0,.62);font-family:SimSun,"宋体",serif;overflow:hidden}
    .bf-heat-drawer.open{display:grid}
    .bf-heat-head{display:flex;align-items:center;gap:10px;padding:0 12px;border-bottom:1px solid #25485b;background:#0a2433}
    .bf-heat-head h2{margin:0;font-size:17px}.bf-heat-head span{color:#9fc2cf;font-size:12px}.bf-heat-head .spacer{flex:1}
    .bf-heat-head button{height:28px;padding:0 10px;border:1px solid #386b7e;border-radius:4px;background:#0d3142;color:#edf9fb;font:700 12px SimSun,"宋体",serif;cursor:pointer}
    .bf-heat-body{overflow:auto;padding:10px;scrollbar-width:thin}
    .bf-heat-state{display:flex;min-height:120px;align-items:center;justify-content:center;border:1px dashed #36586a;color:#b6cbd4}
    .bf-heat-note{margin:0 0 8px;padding:7px 9px;border-left:3px solid #3ba982;background:#0a2730;color:#bfe0df;font-size:12px;line-height:1.45}
    .bf-heat-table-wrap{overflow:auto;border:1px solid #25485b}
    .bf-heat-table{width:100%;min-width:940px;border-collapse:collapse;font-size:12px}
    .bf-heat-table th{position:sticky;top:0;z-index:1;background:#103246;color:#d9eef6;text-align:left;padding:8px 7px;white-space:nowrap}
    .bf-heat-table td{border-top:1px solid #1d3a49;padding:7px;vertical-align:top;white-space:nowrap}
    .bf-heat-table tr[data-heat-row]{cursor:pointer}.bf-heat-table tr[data-heat-row]:hover{background:#0b2c39}
    .bf-heat-tag{display:inline-block;padding:2px 6px;border-radius:3px;border:1px solid #526b76}.bf-heat-tag.good{color:#8de4bb;border-color:#318a68}.bf-heat-tag.warn{color:#ffd27a;border-color:#a87a2d}.bf-heat-tag.bad{color:#ff9b93;border-color:#a84b45}.bf-heat-tag.muted{color:#aabdc5}
    .bf-heat-detail td{padding:0;background:#06131b}.bf-heat-samples{padding:10px;white-space:normal}.bf-heat-samples h3{margin:0 0 7px;font-size:13px;color:#bce8df}
    .bf-heat-sample-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:7px}.bf-heat-sample{border:1px solid #274958;padding:7px;background:#0a202b;line-height:1.5}
    .bf-heat-summary{white-space:normal;min-width:230px;line-height:1.45}
    @media(max-width:768px){.bf-heat-drawer{right:4px;top:54px;width:calc(100vw - 8px);height:calc(100vh - 60px)}.bf-heat-trigger{right:6px;top:58px}.bf-heat-head span{display:none}}
  `;
  document.head.appendChild(style);

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'bf-heat-trigger';
  trigger.innerHTML = '炉次实绩<small>加载中</small>';
  trigger.setAttribute('aria-expanded', 'false');
  trigger.setAttribute('aria-controls', 'bfHeatPerformanceDrawer');

  const drawer = document.createElement('aside');
  drawer.id = 'bfHeatPerformanceDrawer';
  drawer.className = 'bf-heat-drawer';
  drawer.setAttribute('aria-label', '炉次生产实绩与铁水质量分析');
  drawer.innerHTML = `<header class="bf-heat-head"><h2>炉次生产实绩与铁水质量</h2><span>正式 meltno · 一炉一行 · 原始试样可展开</span><div class="spacer"></div><button type="button" data-action="refresh">刷新</button><button type="button" data-action="close">关闭</button></header><div class="bf-heat-body"><div class="bf-heat-state">正在读取最近炉次…</div></div>`;
  document.body.append(trigger, drawer);
  const body = drawer.querySelector('.bf-heat-body');
  let items = [];
  let openMeltno = '';

  function sampleMarkup(item) {
    const samples = Array.isArray(item.sample_details) ? item.sample_details : [];
    if (!samples.length) return '<div class="bf-heat-samples">该炉次暂无有效铁水试样。</div>';
    return `<div class="bf-heat-samples"><h3>${esc(item.meltno)} · ${samples.length} 个原始试样（均值不会覆盖原始记录）</h3><div class="bf-heat-sample-grid">${samples.map((sample, index) => `<div class="bf-heat-sample"><b>试样${index + 1}：${esc(sample.sample_no || sample.batchno || '--')}</b><br>时间：${esc(ts(sample.sample_ts || sample.result_ts))}<br>C ${esc(num(sample.C, 3))}%　Si ${esc(num(sample.Si, 3))}%　Mn ${esc(num(sample.Mn, 3))}%<br>P ${esc(num(sample.P, 3))}%　S ${esc(num(sample.S, 3))}%</div>`).join('')}</div></div>`;
  }

  function render() {
    if (!items.length) {
      body.innerHTML = '<div class="bf-heat-state">暂时没有已聚合的炉次数据。请稍后刷新。</div>';
      return;
    }
    body.innerHTML = `<p class="bf-heat-note">质量分析仅描述 C/Si/Mn/P/S 数据完整性、Si 0.20%–0.40%目标带和样本实际波动，不替代正式质量判定。点击炉次可查看每个原始试样。</p><div class="bf-heat-table-wrap"><table class="bf-heat-table"><thead><tr><th>炉次 / 时间</th><th>实绩铁量</th><th>C均值</th><th>Si均值 / 范围</th><th>Mn均值</th><th>P均值</th><th>S均值</th><th>试样</th><th>铁水质量事实</th></tr></thead><tbody>${items.map(item => `<tr data-heat-row="${esc(item.meltno)}"><td><b>${esc(item.meltno)}</b><br>${esc(ts(item.open_ts))}</td><td>${esc(num(item.actual_iron_qty, 2))} t<br><small>理论 ${esc(num(item.theory_iron_qty, 2))} t</small></td><td>${esc(num(item.c_avg, 3))}%</td><td><b>${esc(num(item.si_avg, 3))}%</b><br>${esc(num(item.si_min, 3))}–${esc(num(item.si_max, 3))}%</td><td>${esc(num(item.mn_avg, 3))}%</td><td>${esc(num(item.p_avg, 3))}%</td><td>${esc(num(item.s_avg, 3))}%</td><td>${esc(item.hot_metal_sample_count)} 个</td><td class="bf-heat-summary"><span class="bf-heat-tag ${tone(item.si_band)}">${esc(bandText(item.si_band))}</span><br>${esc(item.quality_summary)}</td></tr>${openMeltno === item.meltno ? `<tr class="bf-heat-detail"><td colspan="9">${sampleMarkup(item)}</td></tr>` : ''}`).join('')}</tbody></table></div>`;
    body.querySelectorAll('[data-heat-row]').forEach(row => row.addEventListener('click', () => {
      openMeltno = openMeltno === row.dataset.heatRow ? '' : row.dataset.heatRow;
      render();
    }));
  }

  async function load() {
    body.innerHTML = '<div class="bf-heat-state">正在读取最近炉次…</div>';
    try {
      const response = await fetch('/api/heat-performance-quality?limit=12', {cache: 'no-store'});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || data.error_code || `HTTP ${response.status}`);
      items = Array.isArray(data.items) ? data.items : [];
      const latest = items[0];
      trigger.innerHTML = latest ? `炉次实绩<small>${esc(latest.meltno)} · Si ${esc(num(latest.si_avg, 3))}%</small>` : '炉次实绩<small>暂无数据</small>';
      render();
    } catch (error) {
      trigger.innerHTML = '炉次实绩<small>数据暂不可用</small>';
      body.innerHTML = `<div class="bf-heat-state">读取失败：${esc(error.message || error)}。请点击“刷新”重试。</div>`;
    }
  }

  function setOpen(open) {
    drawer.classList.toggle('open', open);
    trigger.setAttribute('aria-expanded', String(open));
    if (open && !items.length) load();
  }
  trigger.addEventListener('click', () => setOpen(!drawer.classList.contains('open')));
  drawer.querySelector('[data-action="close"]').addEventListener('click', () => setOpen(false));
  drawer.querySelector('[data-action="refresh"]').addEventListener('click', load);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
  load();
})();
