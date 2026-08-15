/* REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811
 * Shared, read-only curve inspection for every production page that renders
 * sensor time series.  The page owns the data source; this helper only reads
 * the ECharts option and shows the nearest raw point after a right click.
 */
(() => {
  'use strict';

  const POPUP_CLASS = 'bf-curve-inspector-popup';
  const POPUP_STYLE_ID = 'bf-curve-inspector-style';
  const NAME_TO_ID = {
    '综合顶压': 'P_top', '综合顶温': 'T_top', '荒煤气温度': 'T_top',
    '冷风压力': 'P_blast_cold', '热风压力': 'P_blast', '热风温度': 'T_blast', '冷风流量': 'Q_blast',
    '喷煤率': 'PCI_rate', '喷煤实际速率': 'PCI_rate', '富氧流量': 'Q_O2', '富氧率': 'O2_rate',
    '透气性指数': 'PI', '煤气利用率': 'GasUtil', '全炉压差': 'DP_total', '总压差': 'DP_total',
    '上部压差': 'DP_upper', '下部压差': 'DP_lower', '雷达探尺': 'L', '罐重': 'Hopper_weight',
    '罐重设定': 'Hopper_weight_set', '顶温A': 'T_top_A', '顶温B': 'T_top_B', '顶温C': 'T_top_C', '顶温D': 'T_top_D',
    '南尺': 'L_south', '北尺': 'L_north', '一氧化碳': 'CO_top', '二氧化碳': 'CO2_top', '氢气': 'H2_top'
  };

  function installStyle() {
    if (document.getElementById(POPUP_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = POPUP_STYLE_ID;
    style.textContent = `
      .${POPUP_CLASS}{position:fixed;z-index:2147483000;min-width:230px;max-width:360px;padding:10px 12px;
        border:1px solid #35b8ff;border-radius:7px;background:rgba(3,15,31,.97);box-shadow:0 8px 28px rgba(0,0,0,.42);
        color:#eaf6ff;font:12px/1.55 Consolas,"Microsoft YaHei",sans-serif;pointer-events:none;white-space:normal}
      .${POPUP_CLASS} b{color:#fff}.${POPUP_CLASS} .bf-curve-inspector-label{color:#8fc8eb;margin-right:6px}
      .bf-curve-range-controls{display:inline-flex;align-items:center;gap:4px;margin-left:8px;color:#9ec8e8;font:11px/1.2 Consolas,"Microsoft YaHei",sans-serif;white-space:nowrap}
      .bf-curve-range-controls input{height:24px;min-width:148px;padding:1px 4px;border:1px solid #287fb7;border-radius:3px;background:#071d35;color:#eaf6ff;font:11px Consolas,sans-serif}
      .bf-curve-range-controls button{height:24px;padding:0 6px;border:1px solid #287fb7;border-radius:3px;background:#0a3760;color:#eaf6ff;cursor:pointer}
      .bf-curve-range-controls button:hover{background:#0e5e91}
    `;
    document.head.appendChild(style);
  }

  function hide() {
    document.querySelectorAll(`.${POPUP_CLASS}`).forEach((node) => node.remove());
  }

  function formatTime(value) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return String(value ?? '--');
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  function finite(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function show(event, point) {
    if (!point) return;
    installStyle();
    hide();
    const popup = document.createElement('div');
    popup.className = POPUP_CLASS;
    popup.innerHTML = [
      `<div><span class="bf-curve-inspector-label">点位ID</span><b>${escapeHtml(point.id)}</b></div>`,
      `<div><span class="bf-curve-inspector-label">曲线</span>${escapeHtml(point.name || point.id)}</div>`,
      `<div><span class="bf-curve-inspector-label">数据</span><b>${escapeHtml(point.valueText)}</b>${escapeHtml(point.unit || '')}</div>`,
      `<div><span class="bf-curve-inspector-label">时间戳</span>${escapeHtml(formatTime(point.timestamp))}</div>`,
    ].join('');
    document.body.appendChild(popup);
    const gap = 12;
    const rect = popup.getBoundingClientRect();
    const left = Math.min(Math.max(gap, event.clientX + gap), Math.max(gap, window.innerWidth - rect.width - gap));
    const top = Math.min(Math.max(gap, event.clientY + gap), Math.max(gap, window.innerHeight - rect.height - gap));
    popup.style.left = `${left}px`;
    popup.style.top = `${top}px`;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }

  function pointFromOption(chart, event) {
    const option = chart.getOption?.() || {};
    const seriesList = Array.isArray(option.series) ? option.series : [];
    const dom = chart.getDom();
    const rect = dom.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let best = null;
    seriesList.forEach((series, seriesIndex) => {
      const data = Array.isArray(series.data) ? series.data : [];
      data.forEach((rawPoint) => {
        const tuple = Array.isArray(rawPoint) ? rawPoint : [rawPoint?.value?.[0], rawPoint?.value?.[1]];
        const timestamp = tuple[0];
        const value = finite(tuple[2] ?? tuple[1]);
        if (timestamp === undefined || value === null) return;
        let pixel;
        try { pixel = chart.convertToPixel({ seriesIndex }, [timestamp, tuple[1]]); } catch (_error) { pixel = null; }
        if (!Array.isArray(pixel) || pixel.length < 2 || !Number.isFinite(pixel[0])) return;
        const dx = pixel[0] - x;
        const dy = pixel[1] - y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const candidate = { distance, timestamp, value, series, seriesIndex };
        if (!best || distance < best.distance) best = candidate;
      });
    });
    if (!best || best.distance > 48) return null;
    const id = best.series.id || best.series.pointId || NAME_TO_ID[best.series.name] || best.series.name || `series-${best.seriesIndex + 1}`;
    const unit = best.series.unit || '';
    const displayValue = id === 'GasUtil' && Math.abs(best.value) <= 1.5 ? best.value * 100 : best.value;
    return {
      id,
      name: best.series.name || id,
      unit,
      timestamp: best.timestamp,
      valueText: displayValue.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    };
  }

  function installEcharts(chart) {
    if (!chart || chart.__bfCurveInspectorInstalled) return chart;
    const dom = chart.getDom?.();
    if (!dom) return chart;
    chart.__bfCurveInspectorInstalled = true;
    installStyle();
    dom.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      show(event, pointFromOption(chart, event));
    });
    dom.addEventListener('mouseleave', hide);
    applySavedRange(chart);
    return chart;
  }

  function dateInputValue(value) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:00`;
  }

  function applySavedRange(chart) {
    const range = window.__BF_CURVE_RANGE__;
    if (!range || !chart) return;
    try { chart.dispatchAction({ type: 'dataZoom', startValue: range.start, endValue: range.end }); } catch (_error) { /* chart may have no time axis */ }
  }

  function applyRange(startValue, endValue) {
    const start = new Date(startValue).getTime();
    const end = new Date(endValue).getTime();
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
    window.__BF_CURVE_RANGE__ = { start, end };
    document.querySelectorAll('[data-bf-curve-range-start]').forEach((input) => { input.value = dateInputValue(start); });
    document.querySelectorAll('[data-bf-curve-range-end]').forEach((input) => { input.value = dateInputValue(end); });
    const echartsApi = window.echarts;
    if (!echartsApi?.getInstanceByDom) return;
    document.querySelectorAll('[_echarts_instance_]').forEach((dom) => applySavedRange(echartsApi.getInstanceByDom(dom)));
  }

  function installRangeControls(toolbar) {
    if (!toolbar || toolbar.dataset.bfCurveRangeInstalled === '1') return;
    toolbar.dataset.bfCurveRangeInstalled = '1';
    const wrapper = document.createElement('span');
    wrapper.className = 'bf-curve-range-controls';
    wrapper.innerHTML = '<span>时间范围</span><input type="datetime-local" step="3600" data-bf-curve-range-start aria-label="曲线开始时间"><span>至</span><input type="datetime-local" step="3600" data-bf-curve-range-end aria-label="曲线结束时间"><button type="button" data-bf-curve-range-shift="-1">−1h</button><button type="button" data-bf-curve-range-shift="1">+1h</button><button type="button" data-bf-curve-range-apply>应用</button>';
    toolbar.appendChild(wrapper);
    const startInput = wrapper.querySelector('[data-bf-curve-range-start]');
    const endInput = wrapper.querySelector('[data-bf-curve-range-end]');
    const latest = Date.now();
    startInput.value = dateInputValue(latest - 2 * 3600000);
    endInput.value = dateInputValue(latest);
    wrapper.addEventListener('click', (event) => {
      const shift = Number(event.target.closest('[data-bf-curve-range-shift]')?.dataset.bfCurveRangeShift);
      if (Number.isFinite(shift) && shift !== 0) {
        const start = new Date(startInput.value); const end = new Date(endInput.value);
        start.setHours(start.getHours() + shift); end.setHours(end.getHours() + shift);
        startInput.value = dateInputValue(start); endInput.value = dateInputValue(end); applyRange(startInput.value, endInput.value);
      }
      if (event.target.closest('[data-bf-curve-range-apply]')) applyRange(startInput.value, endInput.value);
    });
  }

  function observeRangeToolbars() {
    const scan = () => document.querySelectorAll('.trend-toolbar').forEach(installRangeControls);
    scan();
    new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observeRangeToolbars, { once: true });
  else observeRangeToolbars();

  window.BFCurveInspector = { installEcharts, hide };
})();
