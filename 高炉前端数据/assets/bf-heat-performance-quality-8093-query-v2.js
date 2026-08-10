/* REQ-8093-HEAT-PERFORMANCE-QUALITY-QUERY-20260807 */
(() => {
  'use strict';
  if (window.__BF_HEAT_PERFORMANCE_QUERY_8093__) return;
  if (location.port && location.port !== '8093') return;
  window.__BF_HEAT_PERFORMANCE_QUERY_8093__ = true;

  const REFRESH_MS = 5000;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
  const num = (value, digits = 2) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '--';
  const ts = value => value ? String(value).replace('T', ' ').slice(0, 19) : '--';
  const tankList = item => {
    const tanks = [...new Set((item.sample_details || []).map(sample => String(sample.tank_no || '').trim()).filter(Boolean))];
    return tanks.length ? tanks.join(', ') : '\u7F50\u53F7\u672A\u63D0\u4F9B';
  };  const bandText = value => ({ below_target: '低于目标带', target: '目标带内', above_target: '高于目标带' }[value] || '待化验');
  const tone = value => ({ below_target: 'warn', target: 'good', above_target: 'bad' }[value] || 'muted');
  const first = (obj, keys) => keys.map(key => obj?.[key]).find(value => value !== undefined && value !== null && value !== '') ?? '';

  const style = document.createElement('style');
  style.id = 'bf-heat-performance-quality-query-8093-style';
  style.textContent = `
    .bf-heat-query-trigger{position:fixed;right:12px;top:78px;z-index:2147482000;height:36px;padding:0 14px;border:1px solid #3ba982;border-radius:6px;background:#0b322f;color:#dffbf0;font:900 14px/1 SimSun,"宋体",serif;box-shadow:0 6px 18px rgba(0,0,0,.35);cursor:pointer}
    .bf-heat-query-trigger:hover,.bf-heat-query-trigger:focus-visible{background:#125044;outline:2px solid #75d8b7;outline-offset:2px}
    .bf-heat-query-trigger small{display:block;margin-top:2px;color:#9bdac5;font-size:9px}
    .bf-heat-query-drawer{position:fixed;z-index:2147483000;right:12px;top:70px;width:min(1220px,calc(100vw - 24px));height:min(82vh,790px);display:none;grid-template-rows:auto minmax(0,1fr);border:1px solid #3c829b;border-radius:8px;background:#071722;color:#e8f4f8;box-shadow:0 20px 60px rgba(0,0,0,.62);font-family:SimSun,"宋体",serif;overflow:hidden}
    .bf-heat-query-drawer.open{display:grid}
    .bf-heat-query-head{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid #25485b;background:#0a2433;flex-wrap:wrap}
    .bf-heat-query-head h2{margin:0;font-size:17px}.bf-heat-query-head span{color:#9fc2cf;font-size:12px}.bf-heat-query-head .spacer{flex:1}
    .bf-heat-query-head button{height:28px;padding:0 10px;border:1px solid #386b7e;border-radius:4px;background:#0d3142;color:#edf9fb;font:700 12px SimSun,"宋体",serif;cursor:pointer}
    .bf-heat-query-tools{display:flex;gap:6px;align-items:center;width:100%;padding-top:3px;flex-wrap:wrap}
    .bf-heat-query-tools input{height:28px;box-sizing:border-box;border:1px solid #386b7e;border-radius:4px;background:#061923;color:#effcff;padding:0 7px;font:12px SimSun,"宋体",serif}
    .bf-heat-query-tools input[type=text]{width:min(260px,38vw)}.bf-heat-query-tools input[type=date]{width:132px}
    .bf-heat-query-tools label{color:#bcd5dd;font-size:12px;display:flex;align-items:center;gap:4px;white-space:nowrap}
    .bf-heat-query-body{overflow:auto;padding:10px;scrollbar-width:thin}
    .bf-heat-query-state{display:flex;min-height:120px;align-items:center;justify-content:center;border:1px dashed #36586a;color:#b6cbd4}
    .bf-heat-query-note{margin:0 0 8px;padding:7px 9px;border-left:3px solid #3ba982;background:#0a2730;color:#bfe0df;font-size:12px;line-height:1.45}
    .bf-heat-query-table-wrap{overflow:auto;border:1px solid #25485b}
    .bf-heat-query-table{width:100%;min-width:1080px;border-collapse:collapse;font-size:12px}
    .bf-heat-query-table th{position:sticky;top:0;z-index:1;background:#103246;color:#d9eef6;text-align:left;padding:8px 7px;white-space:nowrap}
    .bf-heat-query-table td{border-top:1px solid #1d3a49;padding:7px;vertical-align:top;white-space:nowrap}
    .bf-heat-query-table tr[data-heat-row]{cursor:pointer}.bf-heat-query-table tr[data-heat-row]:hover{background:#0b2c39}
    .bf-heat-tag{display:inline-block;padding:2px 6px;border-radius:3px;border:1px solid #526b76}.bf-heat-tag.good{color:#8de4bb;border-color:#318a68}.bf-heat-tag.warn{color:#ffd27a;border-color:#a87a2d}.bf-heat-tag.bad{color:#ff9b93;border-color:#a84b45}.bf-heat-tag.muted{color:#aabdc5}
    .bf-heat-query-detail td{padding:0;background:#06131b}.bf-heat-query-detail-inner{padding:10px;white-space:normal}.bf-heat-query-detail-inner h3{margin:10px 0 7px;font-size:13px;color:#bce8df}.bf-heat-query-detail-inner h3:first-child{margin-top:0}
    .bf-heat-detail-table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px}.bf-heat-detail-table th,.bf-heat-detail-table td{border:1px solid #274958;padding:5px;text-align:left;white-space:nowrap}.bf-heat-detail-table th{background:#0d2b38;color:#cde8eb}
    .bf-heat-query-warning{padding:7px 9px;background:#2b2410;border-left:3px solid #c59a35;color:#f1d58e;line-height:1.5}
    @media(max-width:768px){.bf-heat-query-drawer{right:4px;top:54px;width:calc(100vw - 8px);height:calc(100vh - 60px)}.bf-heat-query-trigger{right:6px;top:58px}.bf-heat-query-head span{display:none}.bf-heat-query-tools input[type=text]{width:100%}}
  `;
  document.head.appendChild(style);

  const trigger = document.createElement('button');
  trigger.type = 'button'; trigger.className = 'bf-heat-query-trigger';
  trigger.innerHTML = '炉次实绩<small>加载中</small>';
  trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-controls', 'bfHeatPerformanceQueryDrawer');

  const drawer = document.createElement('aside');
  drawer.id = 'bfHeatPerformanceQueryDrawer'; drawer.className = 'bf-heat-query-drawer';
  drawer.setAttribute('aria-label', '炉次生产实绩与各样本铁水质量查询');
  drawer.innerHTML = `<header class="bf-heat-query-head"><h2>炉次生产实绩与铁水质量</h2><span>只读 IMES 镜像 · 炉次汇总 + 出铁段 + 化验样本（原始试样）</span><div class="spacer"></div><button type="button" data-action="refresh">刷新</button><button type="button" data-action="close">关闭</button><div class="bf-heat-query-tools"><input type="text" data-filter="q" placeholder="查询炉次、试样号、罐号"><input type="date" data-filter="from" aria-label="开始日期"><span>至</span><input type="date" data-filter="to" aria-label="结束日期"><label><input type="checkbox" data-filter="hasSamples" checked>仅显示已有化验</label><button type="button" data-action="query">查询</button><button type="button" data-action="clear">清除条件</button></div></header><div class="bf-heat-query-body"><div class="bf-heat-query-state">正在读取最近炉次…</div></div>`;
  document.body.append(trigger, drawer);
  const body = drawer.querySelector('.bf-heat-query-body');
  const filterQ = drawer.querySelector('[data-filter="q"]');
  const filterFrom = drawer.querySelector('[data-filter="from"]');
  const filterTo = drawer.querySelector('[data-filter="to"]');
  const filterSamples = drawer.querySelector('[data-filter="hasSamples"]');
  let items = [], openMeltno = '', timer = 0, loading = false;

  function currentFilters() {
    return { q: filterQ.value.trim(), date_from: filterFrom.value, date_to: filterTo.value, has_samples: filterSamples.checked };
  }
  function apiUrl() {
    const params = new URLSearchParams({ limit: '100' });
    const f = currentFilters();
    if (f.q) params.set('q', f.q);
    if (f.date_from) params.set('date_from', f.date_from);
    if (f.date_to) params.set('date_to', f.date_to);
    if (f.has_samples) params.set('has_samples', '1');
    params.set('_ts', String(Date.now()));
    return `/api/heat-performance-quality?${params.toString()}`;
  }
  function sampleRows(item) {
    const samples = Array.isArray(item.sample_details) ? item.sample_details : [];
    if (!samples.length) return '<tr><td colspan="9">该炉次暂无有效铁水化验样本（原始试样）。</td></tr>';
    return samples.map((sample, index) => {
      const tank = first(sample, ['tank_no', 'tankNo', 'thankno']);
      return `<tr><td>${esc(tank || `样本${index + 1}（罐号未提供）`)}</td><td>${esc(sample.sample_no || sample.batchno || '--')}</td><td>${esc(ts(sample.sample_ts || sample.result_ts))}</td><td>${esc(num(sample.C, 3))}%</td><td>${esc(num(sample.Si, 3))}%</td><td>${esc(num(sample.Mn, 3))}%</td><td>${esc(num(sample.P, 3))}%</td><td>${esc(num(sample.S, 3))}%</td><td>${esc(sample.sample_class || '--')}</td></tr>`;
    }).join('');
  }
  function outputRows(item) {
    const outputs = Array.isArray(item.output_details) ? item.output_details : [];
    if (!outputs.length) return '<tr><td colspan="6">该炉次暂无出铁段/称量明细。</td></tr>';
    return outputs.map((output, index) => {
      const tank = first(output, ['tank_no', 'tankNo', 'thankno', 'outPutNo', 'output_no']);
      return `<tr><td>${esc(tank || `出铁段${index + 1}（罐号未提供）`)}</td><td>${esc(num(output.iron_qty, 2))} t</td><td>${esc(ts(output.workdate))}</td><td>${esc(ts(output.weight_time))}</td><td>${esc(num(output.gross_weight, 2))} t</td><td>${esc(num(output.tare_weight, 2))} t</td></tr>`;
    }).join('');
  }
  function detailMarkup(item) {
    const samples = Array.isArray(item.sample_details) ? item.sample_details : [];
    const outputs = Array.isArray(item.output_details) ? item.output_details : [];
    const mapped = samples.some(s => first(s, ['tank_no', 'tankNo', 'thankno'])) || outputs.some(o => first(o, ['tank_no', 'tankNo', 'thankno', 'outPutNo', 'output_no']));
    return `<div class="bf-heat-query-detail-inner"><h3>${esc(item.meltno)} · 出铁段/罐次明细（${outputs.length} 条）</h3><div class="bf-heat-query-tanks">\u5DF2\u6D3E\u7F50\u53F7\uFF1A${esc(tankList(item))}</div><table class="bf-heat-detail-table"><thead><tr><th>罐号/段次</th><th>铁量</th><th>记录时间</th><th>称重时间</th><th>毛重</th><th>皮重</th></tr></thead><tbody>${outputRows(item)}</tbody></table><h3>${esc(item.meltno)} · 铁水化验样本（原始试样）（${samples.length} 条）</h3><table class="bf-heat-detail-table"><thead><tr><th>罐号/样本归属</th><th>试样号/批号</th><th>结果时间</th><th>C</th><th>Si</th><th>Mn</th><th>P</th><th>S</th><th>样本类别</th></tr></thead><tbody>${sampleRows(item)}</tbody></table>${mapped ? '' : '<div class="bf-heat-query-warning">当前 IMES 镜像没有返回铁水罐号字段。页面会完整展示各出铁段和各化验样本（原始试样），但不会把样本强行一一绑定到某个罐；待源端补齐罐号后可直接显示。</div>'}</div>`;
  }
  function render() {
    if (!items.length) { body.innerHTML = '<div class="bf-heat-query-state">暂时没有已聚合的炉次数据，或没有匹配的炉次/化验记录。请调整日期、炉次号或试样号。</div>'; return; }
    const f = currentFilters();
    body.innerHTML = `<p class="bf-heat-query-note">查询条件：${esc(f.q || '全部炉次')}；日期：${esc(f.date_from || '不限')}–${esc(f.date_to || '不限')}。共 ${items.length} 条。点击炉次可查看每个出铁段和每个化验样本（原始试样）；Si 目标带和完整性仅作事实描述，不替代正式质量判定。</p><div class="bf-heat-query-table-wrap"><table class="bf-heat-query-table"><thead><tr><th>炉次 / 开口—结束</th><th>实绩铁量</th><th>C均值</th><th>Si均值 / 范围</th><th>Mn均值</th><th>P均值</th><th>S均值</th><th>化验样本（原始试样）</th><th>出铁段</th><th>质量事实</th></tr></thead><tbody>${items.map(item => `<tr data-heat-row="${esc(item.meltno)}"><td><b>${esc(item.meltno)}</b><br>${esc(ts(item.open_ts))} — ${esc(ts(item.close_ts))}</td><td>${esc(num(item.actual_iron_qty, 2))} t</td><td>${esc(num(item.c_avg, 3))}%</td><td><b>${esc(num(item.si_avg, 3))}%</b><br>${esc(num(item.si_min, 3))}–${esc(num(item.si_max, 3))}%</td><td>${esc(num(item.mn_avg, 3))}%</td><td>${esc(num(item.p_avg, 3))}%</td><td>${esc(num(item.s_avg, 3))}%</td><td>${esc(item.hot_metal_sample_count)} 条</td><td>${esc(item.output_count)} 条</td><td><span class="bf-heat-tag ${tone(item.si_band)}">${esc(bandText(item.si_band))}</span><br>${esc(item.quality_summary)}</td></tr>${openMeltno === item.meltno ? `<tr class="bf-heat-query-detail"><td colspan="10">${detailMarkup(item)}</td></tr>` : ''}`).join('')}</tbody></table></div>`;
    body.querySelectorAll('[data-heat-row]').forEach(row => row.addEventListener('click', () => { openMeltno = openMeltno === row.dataset.heatRow ? '' : row.dataset.heatRow; render(); }));
  }
  async function load() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch(apiUrl(), { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || data.error_code || `HTTP ${response.status}`);
      items = Array.isArray(data.items) ? data.items : [];
      const latest = items[0];
      trigger.innerHTML = latest ? `炉次实绩<small>${esc(latest.meltno)} · ${esc(latest.hot_metal_sample_count)}条样本</small>` : '炉次实绩<small>暂无匹配</small>';
      render();
    } catch (error) {
      trigger.innerHTML = '炉次实绩<small>数据暂不可用</small>';
      body.innerHTML = `<div class="bf-heat-query-state">读取失败：${esc(error.message || error)}。请点击“刷新”重试。</div>`;
    } finally {
      loading = false;
      clearTimeout(timer); timer = setTimeout(load, REFRESH_MS);
    }
  }
  function setOpen(open) { drawer.classList.toggle('open', open); trigger.setAttribute('aria-expanded', String(open)); if (open && !items.length) load(); }
  drawer.querySelector('[data-action="query"]').addEventListener('click', () => { openMeltno = ''; load(); });
  drawer.querySelector('[data-action="clear"]').addEventListener('click', () => { filterQ.value = ''; filterFrom.value = ''; filterTo.value = ''; filterSamples.checked = true; openMeltno = ''; load(); });
  trigger.addEventListener('click', () => setOpen(!drawer.classList.contains('open')));
  drawer.querySelector('[data-action="close"]').addEventListener('click', () => setOpen(false));
  drawer.querySelector('[data-action="refresh"]').addEventListener('click', load);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
  load();
})();
