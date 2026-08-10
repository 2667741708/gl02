/* REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808 */
(() => {
  'use strict';
  if (window.__BF_SI_V20_SHADOW_WORKBENCH__) return;
  if (location.port && !['8093', '8094'].includes(location.port)) return;
  window.__BF_SI_V20_SHADOW_WORKBENCH__ = true;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
  const hasNumber = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  const number = (value, digits = 3) => hasNumber(value) ? Number(value).toFixed(digits) : '--';
  const percent = value => hasNumber(value) ? `${(Number(value) * 100).toFixed(2)}%` : '--';
  const ts = value => value ? String(value).replace('T', ' ').replace(/[+Z].*$/, '').slice(0, 19) : '--';
  const dateText = value => value ? String(value).slice(0, 10) : '';
  const localInput = value => value ? String(value).replace(' ', 'T').slice(0, 16) : '';
  const today = new Date();
  const dateIso = date => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };
  const sevenDaysAgo = new Date(today.getTime() - 6 * 86400000);

  const style = document.createElement('style');
  style.id = 'bf-si-v20-shadow-workbench-style';
  style.textContent = `
    .bf-si20-trigger{position:fixed;right:12px;top:122px;z-index:2147482000;min-width:126px;height:38px;padding:0 13px;border:1px solid #b38b42;border-radius:6px;background:#332913;color:#fff0c9;box-shadow:0 6px 18px rgba(0,0,0,.35);font:900 14px/1 SimSun,"宋体",serif;cursor:pointer}
    .bf-si20-trigger small{display:block;margin-top:2px;color:#d9bd82;font-size:9px}.bf-si20-trigger:hover,.bf-si20-trigger:focus-visible{background:#4b3917;outline:2px solid #e3bd70;outline-offset:2px}
    .bf-si20-drawer{position:fixed;z-index:2147483500;inset:54px 12px 12px 12px;display:none;grid-template-rows:auto minmax(0,1fr);border:1px solid #5b7e8e;border-radius:8px;background:#07151d;color:#e9f3f5;box-shadow:0 22px 70px rgba(0,0,0,.68);font-family:SimSun,"宋体",serif;overflow:hidden}
    .bf-si20-drawer.open{display:grid}.bf-si20-head{display:flex;align-items:center;gap:9px;min-height:48px;padding:8px 12px;border-bottom:1px solid #294956;background:#0b2631;flex-wrap:wrap}.bf-si20-head h2{margin:0;font-size:17px}.bf-si20-head .badge{padding:3px 7px;border:1px solid #a77c35;border-radius:3px;color:#f1cf8b;font-size:11px}.bf-si20-head .spacer{flex:1}.bf-si20-btn{height:30px;padding:0 11px;border:1px solid #467184;border-radius:4px;background:#103342;color:#effaff;font:700 12px SimSun,"宋体",serif;cursor:pointer}.bf-si20-btn:hover,.bf-si20-btn:focus-visible{background:#185064;outline:1px solid #81c0d0}.bf-si20-btn.primary{border-color:#3d9d78;background:#14513f}.bf-si20-btn.warn{border-color:#b58a3b;background:#4a3817}.bf-si20-btn:disabled{opacity:.55;cursor:wait}
    .bf-si20-body{overflow:auto;padding:10px;scrollbar-width:thin}.bf-si20-state{min-height:110px;display:flex;align-items:center;justify-content:center;border:1px dashed #395965;color:#b6cad0;padding:12px;text-align:center;line-height:1.6}.bf-si20-note{margin:0 0 9px;padding:8px 10px;border-left:3px solid #b58a3b;background:#29230f;color:#ebd59b;font-size:12px;line-height:1.55}
    .bf-si20-tabs{display:flex;gap:6px;margin-bottom:9px}.bf-si20-tab{height:31px;padding:0 13px;border:1px solid #365c6b;background:#0b2632;color:#bad3da;font:700 12px SimSun,"宋体",serif;cursor:pointer}.bf-si20-tab.active{border-color:#4ca981;background:#12483a;color:#e8fff6}
    .bf-si20-panel{display:none}.bf-si20-panel.active{display:block}.bf-si20-form{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:8px;padding:10px;border:1px solid #294a58;background:#0a202a}.bf-si20-field{display:flex;flex-direction:column;gap:5px;min-width:0}.bf-si20-field label{color:#bcd2d8;font-size:12px}.bf-si20-field input,.bf-si20-field select{width:100%;height:32px;box-sizing:border-box;border:1px solid #3b6879;border-radius:3px;background:#061821;color:#f0f9fb;padding:0 7px;font:12px SimSun,"宋体",serif}.bf-si20-actions{display:flex;align-items:end;gap:7px;flex-wrap:wrap}
    .bf-si20-result{margin-top:9px;display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:8px}.bf-si20-card{border:1px solid #315362;background:#0a202a;padding:9px;min-height:66px}.bf-si20-card span{display:block;color:#9fb8c0;font-size:11px}.bf-si20-card strong{display:block;margin-top:7px;font-size:20px;color:#f2f9fa}.bf-si20-card.good strong{color:#7ee0af}.bf-si20-card.warn strong{color:#f3c86f}.bf-si20-warning{grid-column:1/-1;padding:8px 10px;border-left:3px solid #c69039;background:#2a230f;color:#f0d494;font-size:12px;line-height:1.55}
    .bf-si20-candidates{display:flex;align-items:stretch;gap:7px;flex-wrap:wrap;margin-top:8px;padding:8px;border:1px solid #294a58;background:#091d26}.bf-si20-candidates>span{align-self:center;color:#b9ced4;font-size:12px}.bf-si20-candidate{min-width:190px;padding:7px 9px;border:1px solid #4c7280;border-radius:4px;background:#102f3a;color:#edf8fa;text-align:left;font:12px SimSun,"宋体",serif;cursor:pointer}.bf-si20-candidate strong,.bf-si20-candidate small{display:block}.bf-si20-candidate small{margin-top:4px;color:#c3d5da;white-space:normal}.bf-si20-candidate.estimated{border-color:#a77c35;background:#302711}.bf-si20-candidate:hover,.bf-si20-candidate:focus-visible{outline:1px solid #80c2d1}
    .bf-si20-history-tools{display:flex;align-items:end;gap:8px;flex-wrap:wrap;padding:9px;border:1px solid #294a58;background:#0a202a}.bf-si20-history-tools .bf-si20-field{width:150px}.bf-si20-metrics{margin:9px 0;display:flex;gap:8px;flex-wrap:wrap}.bf-si20-metric{padding:6px 9px;border:1px solid #315362;background:#0b2530;color:#cce0e5;font-size:12px}
    .bf-si20-chart-wrap{position:relative;height:310px;border:1px solid #315362;background:#081b24;padding:8px}.bf-si20-chart{width:100%;height:100%;display:block}.bf-si20-legend{display:flex;gap:14px;margin:7px 0;color:#c5d7dc;font-size:12px}.bf-si20-key{display:inline-flex;align-items:center;gap:5px}.bf-si20-key::before{content:"";width:16px;height:3px;background:var(--key)}
    .bf-si20-table-wrap{margin-top:8px;overflow:auto;border:1px solid #315362}.bf-si20-table{width:100%;min-width:1080px;border-collapse:collapse;font-size:12px}.bf-si20-table th{position:sticky;top:0;background:#123342;color:#d9edf1;padding:7px;text-align:left;white-space:nowrap}.bf-si20-table td{border-top:1px solid #233f4b;padding:7px;white-space:nowrap}.bf-si20-hit{color:#78dca9}.bf-si20-miss{color:#ff9d91}.bf-si20-wait{color:#d9bc7a}
    @media(max-width:1024px){.bf-si20-form{grid-template-columns:repeat(2,minmax(150px,1fr))}.bf-si20-result{grid-template-columns:repeat(2,minmax(130px,1fr))}.bf-si20-drawer{inset:48px 5px 5px}}
    @media(max-width:600px){.bf-si20-trigger{right:6px;top:100px}.bf-si20-form{grid-template-columns:1fr}.bf-si20-result{grid-template-columns:1fr}.bf-si20-chart-wrap{height:250px}.bf-si20-head .badge{display:none}}
  `;
  document.head.appendChild(style);

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'bf-si20-trigger';
  trigger.innerHTML = '平均Si预测<small>V20影子模式</small>';
  trigger.setAttribute('aria-expanded', 'false');

  const drawer = document.createElement('aside');
  drawer.className = 'bf-si20-drawer';
  drawer.id = 'bfSiV20ShadowWorkbench';
  drawer.setAttribute('aria-label', 'V20平均硅含量预测与历史回放');
  drawer.innerHTML = `
    <header class="bf-si20-head"><h2>平均 Si 预测与历史回放</h2><span class="badge">V20 历史Si · experimental shadow</span><span data-role="model-state">正在检查模型…</span><div class="spacer"></div><button type="button" class="bf-si20-btn" data-action="refresh">刷新</button><button type="button" class="bf-si20-btn" data-action="close">关闭</button></header>
    <div class="bf-si20-body">
      <p class="bf-si20-note">该功能只写预测审计记录，不调整高炉设定值。实际 Si 来自每炉全部有效铁水试样的算术平均；当前炉自身化验不会进入预测输入。任意时刻点击可预测，但模型正式训练口径是开口前 60 分钟，偏离时会明确提示。</p>
      <div class="bf-si20-tabs"><button type="button" class="bf-si20-tab active" data-tab="predict">当前预测</button><button type="button" class="bf-si20-tab" data-tab="history">历史曲线与回放</button></div>
      <section class="bf-si20-panel active" data-panel="predict">
        <div class="bf-si20-form">
          <div class="bf-si20-field"><label for="bfSi20Target">目标炉次</label><input id="bfSi20Target" list="bfSi20TargetList" placeholder="2#YYYYMMDD-NNN"><datalist id="bfSi20TargetList"></datalist></div>
          <div class="bf-si20-field"><label for="bfSi20Open">目标/预计开口时间</label><input id="bfSi20Open" type="datetime-local"></div>
          <div class="bf-si20-field"><label for="bfSi20CutoffMode">预测截止口径</label><select id="bfSi20CutoffMode"><option value="now">服务器当前时刻</option><option value="open_minus_60">开口前60分钟回放</option><option value="explicit">指定历史时刻</option></select></div>
          <div class="bf-si20-field"><label for="bfSi20Cutoff">指定截止时间</label><input id="bfSi20Cutoff" type="datetime-local" disabled></div>
          <div class="bf-si20-actions"><button type="button" class="bf-si20-btn primary" data-action="predict">开始预测平均Si</button></div>
        </div>
        <div data-role="candidate-state" class="bf-si20-candidates"><span>正在读取220.12本地候选炉次…</span></div>
        <div data-role="predict-state" class="bf-si20-state">请选择目标炉次，然后点击“开始预测平均Si”。</div>
      </section>
      <section class="bf-si20-panel" data-panel="history">
        <div class="bf-si20-history-tools">
          <div class="bf-si20-field"><label for="bfSi20From">开始日期</label><input id="bfSi20From" type="date" value="${dateIso(sevenDaysAgo)}"></div>
          <div class="bf-si20-field"><label for="bfSi20To">结束日期</label><input id="bfSi20To" type="date" value="${dateIso(today)}"></div>
          <button type="button" class="bf-si20-btn" data-action="history">查询实际与预测曲线</button>
          <button type="button" class="bf-si20-btn warn" data-action="replay">按开口前60分钟回放所选日期</button>
        </div>
        <div data-role="history-state" class="bf-si20-state">正在读取预测与实际平均Si…</div>
      </section>
    </div>`;
  document.body.append(trigger, drawer);

  const targetInput = drawer.querySelector('#bfSi20Target');
  const targetList = drawer.querySelector('#bfSi20TargetList');
  const openInput = drawer.querySelector('#bfSi20Open');
  const cutoffMode = drawer.querySelector('#bfSi20CutoffMode');
  const cutoffInput = drawer.querySelector('#bfSi20Cutoff');
  const fromInput = drawer.querySelector('#bfSi20From');
  const toInput = drawer.querySelector('#bfSi20To');
  const predictState = drawer.querySelector('[data-role="predict-state"]');
  const candidateState = drawer.querySelector('[data-role="candidate-state"]');
  const historyState = drawer.querySelector('[data-role="history-state"]');
  const modelState = drawer.querySelector('[data-role="model-state"]');
  const targetMap = new Map();
  let historyItems = [];
  let loadingStatus = false;

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, {cache: 'no-store', credentials: 'same-origin', ...options});
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.ok === false) {
      const error = new Error(data.error || data.message || data.error_code || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function loadStatus() {
    if (loadingStatus) return;
    loadingStatus = true;
    try {
      const data = await jsonFetch(`/api/si-v20/status?limit=180&_ts=${Date.now()}`);
      targetMap.clear();
      const targets = Array.isArray(data.targets) ? data.targets : [];
      const candidates = Array.isArray(data.candidate_targets) ? data.candidate_targets : [];
      [...candidates, ...targets].forEach(item => targetMap.set(String(item.meltno), item));
      targetList.innerHTML = [
        ...candidates.map(item => `<option value="${esc(item.meltno)}">候选 · ${esc(ts(item.open_ts))} · ${esc(item.candidate_status_text)}</option>`),
        ...targets.map(item => `<option value="${esc(item.meltno)}">${esc(ts(item.open_ts))} · ${item.si_avg == null ? '待化验' : `实际Si ${number(item.si_avg)}%`}</option>`)
      ].join('');
      candidateState.innerHTML = candidates.length
        ? `<span>候选炉次（点击选择）</span>${candidates.map(item => `<button type="button" class="bf-si20-candidate ${item.candidate_time_is_estimated ? 'estimated' : ''}" data-candidate-meltno="${esc(item.meltno)}"><strong>${esc(item.meltno)} · ${esc(item.candidate_status_text)}</strong><small>${item.candidate_time_is_estimated ? '估计开口' : '正式开口'}：${esc(ts(item.open_ts))}；来源：${esc(item.source_type)}</small></button>`).join('')}`
        : '<span>220.12本地IMES镜像暂时没有候选炉次；系统只会显示明确标记的推测候选，不会把上一炉当成下一炉。</span>';
      const recommended = data.recommended_target;
      if (!targetInput.value && recommended) {
        targetInput.value = recommended.meltno;
        openInput.value = localInput(recommended.open_ts);
      }
      modelState.textContent = `模型：${data.model?.name || '--'} · 14项历史特征 · 审计表${data.audit_table_ready ? '已就绪' : '未迁移'}`;
      trigger.innerHTML = `平均Si预测<small>${recommended ? `候选 ${esc(recommended.meltno)}` : 'V20影子模式'}</small>`;
    } catch (error) {
      modelState.textContent = `模型状态不可用：${error.message}`;
      trigger.innerHTML = '平均Si预测<small>服务暂不可用</small>';
    } finally {
      loadingStatus = false;
    }
  }

  function setBusy(button, busy, text) {
    if (!button) return;
    if (busy) button.dataset.originalText = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? text : (button.dataset.originalText || button.textContent);
  }

  function renderPrediction(item) {
    const actualClass = item.actual_ready ? (item.hit_abs_le_005 ? 'good' : 'warn') : '';
    const warning = (item.warnings || []).length
      ? `<div class="bf-si20-warning">${item.warnings.map(esc).join('<br>')}</div>`
      : '';
    predictState.className = '';
    predictState.innerHTML = `<div class="bf-si20-result">
      <div class="bf-si20-card good"><span>预测平均Si（最大概率代理值）</span><strong>${number(item.si_mean)}%</strong></div>
      <div class="bf-si20-card"><span>P10–P90经验区间</span><strong>${number(item.p10)}–${number(item.p90)}%</strong></div>
      <div class="bf-si20-card"><span>预测截止 / 距开口</span><strong>${number(item.lead_minutes, 1)} min</strong><span>${esc(ts(item.prediction_cutoff_ts))}</span></div>
      <div class="bf-si20-card ${actualClass}"><span>随后获得的实际平均Si</span><strong>${item.actual_ready ? `${number(item.actual_si_mean)}%` : '等待化验'}</strong></div>
      <div class="bf-si20-card ${actualClass}"><span>绝对误差 / ±0.05</span><strong>${item.absolute_error == null ? '--' : `${number(item.absolute_error)} / ${item.hit_abs_le_005 ? '命中' : '未命中'}`}</strong></div>
      ${warning}
    </div>`;
  }

  async function predict() {
    const button = drawer.querySelector('[data-action="predict"]');
    const target = targetInput.value.trim();
    if (!target) { predictState.className = 'bf-si20-state'; predictState.textContent = '请先选择或填写目标炉次。'; return; }
    const body = {
      target_meltno: target,
      target_open_ts: openInput.value || null,
      cutoff_mode: cutoffMode.value,
      cutoff_ts: cutoffInput.value || null
    };
    setBusy(button, true, '预测中…');
    predictState.className = 'bf-si20-state';
    predictState.textContent = '正在读取截止时刻前已发布的历史Si并执行V20影子预测…';
    try {
      const data = await jsonFetch('/api/si-v20/predict', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
      });
      renderPrediction(data.prediction);
      await loadHistory();
    } catch (error) {
      predictState.className = 'bf-si20-state';
      predictState.textContent = `预测失败：${error.message}`;
    } finally { setBusy(button, false); }
  }

  function drawChart(canvas, items) {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(300, Math.floor(rect.width * ratio));
    canvas.height = Math.max(180, Math.floor(rect.height * ratio));
    const ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    const width = rect.width, height = rect.height;
    ctx.clearRect(0, 0, width, height);
    const ordered = [...items].sort((a, b) => String(a.target_open_ts).localeCompare(String(b.target_open_ts)));
    const values = ordered.flatMap(item => [item.prediction_si_mean, item.actual_si_mean]).filter(hasNumber).map(Number);
    if (!ordered.length || !values.length) {
      ctx.fillStyle = '#a9bec5'; ctx.font = '13px SimSun'; ctx.fillText('暂无可绘制的预测记录，请先查询或执行历史回放。', 20, 35); return;
    }
    let yMin = Math.min(...values, 0.15), yMax = Math.max(...values, 0.45);
    const pad = Math.max(0.025, (yMax - yMin) * 0.12); yMin -= pad; yMax += pad;
    const margin = {left: 50, right: 18, top: 18, bottom: 46};
    const xAt = index => margin.left + (ordered.length === 1 ? (width - margin.left - margin.right) / 2 : index * (width - margin.left - margin.right) / (ordered.length - 1));
    const yAt = value => margin.top + (yMax - value) * (height - margin.top - margin.bottom) / (yMax - yMin);
    ctx.strokeStyle = '#294653'; ctx.fillStyle = '#9eb7bf'; ctx.font = '11px SimSun'; ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const value = yMin + (yMax - yMin) * i / 5, y = yAt(value);
      ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(width - margin.right, y); ctx.stroke();
      ctx.fillText(value.toFixed(2), 6, y + 4);
    }
    const draw = (key, color) => {
      ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 2; ctx.beginPath(); let started = false;
      ordered.forEach((item, index) => {
        if (!hasNumber(item[key])) { started = false; return; }
        const value = Number(item[key]);
        const x = xAt(index), y = yAt(value); if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ordered.forEach((item, index) => { if (!hasNumber(item[key])) return; const value = Number(item[key]); const x = xAt(index), y = yAt(value); ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); });
    };
    draw('actual_si_mean', '#4aa8e8'); draw('prediction_si_mean', '#56c58b');
    const step = Math.max(1, Math.ceil(ordered.length / 12));
    ctx.fillStyle = '#a9bec5'; ctx.textAlign = 'center';
    ordered.forEach((item, index) => { if (index % step && index !== ordered.length - 1) return; const label = String(item.target_meltno).split('-').pop(); ctx.fillText(label, xAt(index), height - 20); });
    ctx.textAlign = 'start';
  }

  function renderHistory(data) {
    historyItems = Array.isArray(data.items) ? data.items : [];
    if (!historyItems.length) {
      historyState.className = 'bf-si20-state';
      historyState.textContent = '所选日期没有炉次实际Si或预测记录。可以刷新实绩同步，或按开口前60分钟生成回放预测。';
      return;
    }
    const m = data.metrics || {};
    historyState.className = '';
    historyState.innerHTML = `<div class="bf-si20-metrics"><span class="bf-si20-metric">曲线炉次 ${historyItems.length}</span><span class="bf-si20-metric">实际Si ${m.actual_count || 0}</span><span class="bf-si20-metric">已预测 ${m.prediction_count || 0}</span><span class="bf-si20-metric">已完成对比 ${m.evaluated_count || 0}</span><span class="bf-si20-metric">MAE ${number(m.mae, 4)}</span><span class="bf-si20-metric">±0.05命中率 ${percent(m.hit_rate_abs_le_005)}</span></div><div class="bf-si20-legend"><span class="bf-si20-key" style="--key:#4aa8e8">实际平均Si</span><span class="bf-si20-key" style="--key:#56c58b">V20预测平均Si</span></div><div class="bf-si20-chart-wrap"><canvas class="bf-si20-chart"></canvas></div><div class="bf-si20-table-wrap"><table class="bf-si20-table"><thead><tr><th>炉次 / 开口</th><th>预测时刻</th><th>提前量</th><th>预测Si</th><th>P10–P90</th><th>实际平均Si</th><th>绝对误差</th><th>±0.05</th><th>记录状态</th></tr></thead><tbody>${historyItems.map(item => { const compared = item.has_prediction && item.actual_ready; return `<tr><td><b>${esc(item.target_meltno)}</b><br>${esc(ts(item.target_open_ts))}</td><td>${esc(ts(item.prediction_cutoff_ts))}</td><td>${item.has_prediction ? `${number(item.lead_minutes, 1)} min` : '--'}</td><td><b>${item.has_prediction ? `${number(item.prediction_si_mean)}%` : '--'}</b></td><td>${item.has_prediction ? `${number(item.prediction_p10)}–${number(item.prediction_p90)}%` : '--'}</td><td>${item.actual_ready ? `${number(item.actual_si_mean)}%` : '<span class="bf-si20-wait">等待化验</span>'}</td><td>${compared ? number(item.absolute_error) : '--'}</td><td class="${compared ? (item.hit_abs_le_005 ? 'bf-si20-hit' : 'bf-si20-miss') : 'bf-si20-wait'}">${compared ? (item.hit_abs_le_005 ? '命中' : '未命中') : (item.has_prediction ? '待对比' : '未预测')}</td><td>${item.has_prediction ? `${esc(item.requested_by || '页面用户')}<br>${esc(item.request_mode || 'shadow')}` : '仅实际实绩'}</td></tr>`; }).join('')}</tbody></table></div>`;
    const canvas = historyState.querySelector('canvas');
    requestAnimationFrame(() => drawChart(canvas, historyItems));
  }

  async function loadHistory() {
    historyState.className = 'bf-si20-state'; historyState.textContent = '正在读取历史炉次实际平均Si、已保存预测和随后对比结果…';
    const params = new URLSearchParams({date_from: fromInput.value, date_to: toInput.value, latest_per_heat: '1', limit: '1200', _ts: String(Date.now())});
    try { renderHistory(await jsonFetch(`/api/si-v20/history?${params}`)); }
    catch (error) { historyState.className = 'bf-si20-state'; historyState.textContent = `读取历史失败：${error.message}`; }
  }

  async function replay() {
    const button = drawer.querySelector('[data-action="replay"]');
    setBusy(button, true, '回放中…');
    historyState.className = 'bf-si20-state'; historyState.textContent = '正在逐炉按开口前60分钟构建历史Si特征并保存影子预测…';
    try {
      const data = await jsonFetch('/api/si-v20/replay', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({date_from: fromInput.value, date_to: toInput.value, limit: 200})});
      await loadHistory();
      const metric = historyState.querySelector('.bf-si20-metrics');
      if (metric) metric.insertAdjacentHTML('afterbegin', `<span class="bf-si20-metric">本次回放 ${data.predicted_count} 炉，失败 ${data.failed_count}</span>`);
    } catch (error) {
      historyState.className = 'bf-si20-state';
      historyState.textContent = `历史回放失败：${error.message}`;
    } finally { setBusy(button, false); }
  }

  function selectTab(name) {
    drawer.querySelectorAll('[data-tab]').forEach(item => item.classList.toggle('active', item.dataset.tab === name));
    drawer.querySelectorAll('[data-panel]').forEach(item => item.classList.toggle('active', item.dataset.panel === name));
    if (name === 'history') loadHistory();
  }
  drawer.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => selectTab(button.dataset.tab)));
  targetInput.addEventListener('change', () => { const item = targetMap.get(targetInput.value.trim()); if (item) openInput.value = localInput(item.open_ts); });
  candidateState.addEventListener('click', event => {
    const button = event.target.closest('[data-candidate-meltno]');
    if (!button) return;
    const item = targetMap.get(button.dataset.candidateMeltno);
    if (!item) return;
    targetInput.value = item.meltno;
    openInput.value = localInput(item.open_ts);
    targetInput.focus();
  });
  cutoffMode.addEventListener('change', () => { cutoffInput.disabled = cutoffMode.value !== 'explicit'; });
  drawer.querySelector('[data-action="predict"]').addEventListener('click', predict);
  drawer.querySelector('[data-action="history"]').addEventListener('click', loadHistory);
  drawer.querySelector('[data-action="replay"]').addEventListener('click', replay);
  drawer.querySelector('[data-action="refresh"]').addEventListener('click', async () => { await loadStatus(); const active = drawer.querySelector('[data-panel="history"].active'); if (active) await loadHistory(); });
  function setOpen(open) { drawer.classList.toggle('open', open); trigger.setAttribute('aria-expanded', String(open)); if (open) loadStatus(); }
  trigger.addEventListener('click', () => setOpen(!drawer.classList.contains('open')));
  drawer.querySelector('[data-action="close"]').addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
  window.addEventListener('resize', () => { const canvas = historyState.querySelector('canvas'); if (canvas && historyItems.length) drawChart(canvas, historyItems); });
  loadStatus();
})();
