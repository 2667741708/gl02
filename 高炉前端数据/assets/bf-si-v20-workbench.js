/* REQ-SI-V20-INDEPENDENT-WORKBENCH-20260808 */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const hasNumber = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  const num = (value, digits = 3) => hasNumber(value) ? Number(value).toFixed(digits) : '--';
  const pct = value => hasNumber(value) ? `${(Number(value) * 100).toFixed(1)}%` : '--';
  const isoText = value => value ? String(value).replace('T',' ').replace(/[+Z].*$/,'').slice(0,19) : '--';
  const localInput = value => value ? String(value).replace(' ','T').slice(0,16) : '';
  const dateIso = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const today = new Date();
  const defaultFrom = new Date(today.getTime() - 6 * 86400000);
  const state = {status:null, schedule:null, strictHourly:null, history:[], hourlyRows:[], selected:null, readiness:null, refreshInFlight:false, historyMode:'heat', autoDateFrom:dateIso(defaultFrom), autoDateTo:dateIso(today)};

  async function api(url, options = {}) {
    const response = await fetch(url, {cache:'no-store', credentials:'same-origin', ...options});
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || data.ok === false) throw new Error(data.error || data.message || `HTTP ${response.status}`);
    return data;
  }
  function setError(target, error) { target.innerHTML = `<div class="error">${esc(error.message || error)}</div>`; }
  function candidateLabel(item) {
    const timeKind = item.candidate_time_is_estimated ? '估计开口' : '正式开口';
    return `${timeKind} ${isoText(item.open_ts)} · ${item.candidate_status_text || '候选炉次'}`;
  }
  function chooseCandidate(item) {
    state.selected = item;
    $('#target').value = item.meltno || '';
    $('#openTs').value = localInput(item.open_ts);
    document.querySelectorAll('.candidate').forEach(node => node.classList.toggle('selected', node.dataset.meltno === item.meltno));
    checkReadiness();
  }
  function renderCandidates(data) {
    const candidates = Array.isArray(data.candidate_targets) ? data.candidate_targets : [];
    const root = $('#candidates');
    if (!candidates.length) {
      root.innerHTML = '<div class="empty">本地镜像暂无候选炉次。系统不会把上一炉已完成实绩当作下一炉候选。</div>';
      return;
    }
    root.innerHTML = candidates.map(item => `<button type="button" class="candidate ${item.candidate_time_is_estimated ? 'estimated' : ''}" data-meltno="${esc(item.meltno)}"><strong>${esc(item.meltno)} · ${esc(item.candidate_status_text || '')}</strong><small>${esc(candidateLabel(item))}</small><small>来源：${esc(item.source_type || '--')}；镜像时间：${esc(isoText(item.mirrored_at))}</small></button>`).join('');
    root.querySelectorAll('.candidate').forEach(button => button.addEventListener('click', () => {
      const item = candidates.find(candidate => candidate.meltno === button.dataset.meltno);
      if (item) chooseCandidate(item);
    }));
    const recommended = data.recommended_target || candidates[0];
    if (recommended && !$('#target').value) chooseCandidate(recommended);
  }
  function renderStatus(data) {
    state.status = data;
    const latestActual = (data.targets || []).find(item => hasNumber(item.si_avg));
    const freshness = latestActual ? `最新实际 ${latestActual.meltno} / ${isoText(latestActual.source_updated_at)}` : '暂无实际Si';
    $('#modelMeta').textContent = `模型 ${data.model?.name || '--'} · ${data.model?.feature_count || 0}项特征 · ${freshness} · ${data.audit_table_ready ? '审计表已就绪' : '审计表未迁移'}`;
    renderCandidates(data);
    const options = [...(data.candidate_targets || []), ...(data.targets || [])];
    $('#targetList').innerHTML = options.map(item => `<option value="${esc(item.meltno)}">${esc(isoText(item.open_ts))} · ${item.candidate_status_text || (item.si_avg == null ? '待化验' : `实际Si ${num(item.si_avg)}%`)}</option>`).join('');
  }
  function renderPrediction(data) {
    const p = data.prediction || data;
    const actualReady = p.actual_ready;
    const errClass = actualReady ? (p.hit_abs_le_005 ? 'good' : 'warn') : '';
    $('#prediction').innerHTML = `<div class="result-grid"><div class="result"><span>P50/最大概率代理值</span><strong>${num(p.si_mean)}%</strong><small>${esc(p.target_meltno || '')}</small></div><div class="result"><span>P10–P90经验区间</span><strong>${num(p.p10)}–${num(p.p90)}%</strong><small>训练提前量 ${num(data.model?.trained_lead_minutes || 60,1)} min</small></div><div class="result"><span>截止时刻 / 提前量</span><strong>${num(p.lead_minutes,1)} min</strong><small>${esc(isoText(p.prediction_cutoff_ts))}</small></div><div class="result ${errClass}"><span>随后实际平均Si</span><strong>${actualReady ? `${num(p.actual_si_mean)}%` : '等待化验'}</strong><small>${actualReady ? `误差 ${num(p.absolute_error)} · ${p.hit_abs_le_005 ? '±0.05命中' : '±0.05未命中'}` : '实际值到库后自动对比'}</small></div></div>${(p.warnings || []).length ? `<div class="notice" style="margin-top:8px">${p.warnings.map(esc).join('<br>')}</div>` : ''}`;
  }
  function renderReadiness(data) {
    state.readiness = data;
    const h = data.history || {};
    const items = [
      ['目标炉次', data.target_meltno], ['截止时刻', isoText(data.prediction_cutoff_ts)], ['提前量', `${num(data.lead_minutes,1)} min`],
      ['可用特征', `${data.available_feature_count}/${data.feature_count}`], ['缺失特征', data.missing_feature_count],
      ['前1炉平均Si', `${num(h.history_mean__Si_lag_1)}%`], ['前2炉平均Si', `${num(h.history_mean__Si_lag_2)}%`], ['前3炉平均Si', `${num(h.history_mean__Si_lag_3)}%`],
      ['前4炉平均Si', `${num(h.history_mean__Si_lag_4)}%`], ['前5炉平均Si', `${num(h.history_mean__Si_lag_5)}%`],
      ['近3炉均值', `${num(h.history_mean__Si_mean_3)}%`], ['近5炉斜率', num(h.history_mean__Si_slope_5,5)],
      ['可见已发布炉数', h.v20_history__visible_label_count], ['未化验炉间隔', h.v20_history__unlabeled_heat_gap]
    ];
    $('#readiness').innerHTML = items.map(([label,value]) => `<div class="readiness-item"><span>${esc(label)}</span><b>${esc(String(value ?? '--'))}</b></div>`).join('');
    const details = Object.entries(data.features || {}).sort((a,b) => a[0].localeCompare(b[0])).map(([key,value]) => `<div><span>${esc(key)}</span><br>${esc(String(value ?? '缺失'))}</div>`).join('');
    $('#featureDetails').innerHTML = details || '<div>没有特征快照</div>';
    if ((data.warnings || []).length) $('#globalNotice').innerHTML = data.warnings.map(esc).join('<br>');
  }
  async function loadStatus() {
    try { renderStatus(await api(`/api/si-v20/status?limit=180&_ts=${Date.now()}`)); }
    catch (error) { setError($('#candidates'), error); $('#modelMeta').textContent = `状态读取失败：${error.message}`; }
  }
  function renderSchedule(data) {
    const schedule=data.schedule||{}; state.schedule=schedule;
    if(schedule.cadence_minutes) $('#scheduleCadence').value=String(schedule.cadence_minutes);
    if(schedule.enabled!==undefined) $('#scheduleEnabled').value=String(Boolean(schedule.enabled));
    const dailyPoints=schedule.cadence_minutes?Math.ceil(1440/Number(schedule.cadence_minutes)):null;
    $('#scheduleStatus').textContent=schedule.schedule_id?`数据库配置 #${schedule.schedule_id} · ${schedule.enabled?'运行中':'已暂停'} · 每${schedule.cadence_minutes}分钟（约${dailyPoints}点/天） · 下一时间槽 ${isoText(schedule.next_slot_ts)} · 最近结果 ${schedule.last_run_status||'尚未执行'}`:'尚无定时配置，保存后创建。';
  }
  async function loadSchedule(){try{renderSchedule(await api(`/api/si-v20/schedule?_ts=${Date.now()}`))}catch(error){$('#scheduleStatus').textContent=`定时配置读取失败：${error.message}`}}
  function renderStrictHourlyStatus(data){state.strictHourly=data;const slot=data.current_slot||{};const model=data.model||{};$('#strictHourlyStatus').textContent=`独立常开 · 当前槽 ${isoText(slot.schedule_slot_ts)} · ${slot.slot_status||'待创建'} · 尝试 ${slot.attempt_count??0} 次 · 模型 ${model.name||'--'} / ${model.feature_count||0}项 · ${data.contracts?.local_database_only?'仅220.12本地库':'数据源待核对'}`;}
  async function loadStrictHourlyStatus(){try{renderStrictHourlyStatus(await api(`/api/si-v20/strict-hourly/status?_ts=${Date.now()}`))}catch(error){$('#strictHourlyStatus').textContent=`严格整点状态读取失败：${error.message}`}}
  async function saveSchedule(){const button=$('#saveScheduleBtn');button.disabled=true;button.textContent='保存中…';try{const data=await api('/api/si-v20/schedule/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cadence_minutes:Number($('#scheduleCadence').value),enabled:$('#scheduleEnabled').value==='true',furnace_no:'2'})});renderSchedule(data);$('#scheduleStatus').textContent+=` · 保存成功 ${new Date().toLocaleTimeString('zh-CN',{hour12:false})}`}catch(error){$('#scheduleStatus').textContent=`保存失败：${error.message}`}finally{button.disabled=false;button.textContent='保存自动预测周期'}}
  function readinessPayload() {
    return {target_meltno:$('#target').value.trim(), target_open_ts:$('#openTs').value || null, cutoff_mode:$('#cutoffMode').value, cutoff_ts:$('#cutoffTs').value || null};
  }
  async function checkReadiness() {
    if (!$('#target').value.trim()) return;
    $('#readiness').innerHTML = '<div class="empty">正在检查截止时刻前的数据覆盖与泄漏合同…</div>';
    try {
      const query = new URLSearchParams(readinessPayload());
      renderReadiness(await api(`/api/si-v20/data-readiness?${query}`));
    } catch (error) { setError($('#readiness'), error); }
  }
  async function predict() {
    const button = $('#predictBtn');
    if (!$('#target').value.trim()) { setError($('#prediction'), new Error('请先选择候选炉次')); return; }
    button.disabled = true; button.textContent = '预测中…';
    try {
      const data = await api('/api/si-v20/predict', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readinessPayload())});
      renderPrediction(data); renderReadiness({...(state.readiness || {}), ...(data.features ? {features:data.features} : {}), target_meltno:data.prediction.target_meltno, prediction_cutoff_ts:data.prediction.prediction_cutoff_ts, lead_minutes:data.prediction.lead_minutes, history: state.readiness?.history || {}, feature_count:Object.keys(data.features || {}).length, available_feature_count:Object.values(data.features || {}).filter(hasNumber).length, missing_feature_count:Object.values(data.features || {}).filter(value => value == null).length, warnings:data.prediction.warnings || []});
      await loadActiveHistory();
    } catch (error) { setError($('#prediction'), error); }
    finally { button.disabled = false; button.textContent = '开始预测平均 Si'; }
  }
  async function strictHourlyPredict() {
    const button = $('#strictHourlyBtn');
    button.disabled = true; button.textContent = '严格整点补跑中…';
    try {
      const data = await api('/api/si-v20/strict-hourly/predict', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      const row=data.slot||{};
      $('#strictHourlyStatus').textContent=`严格整点 ${isoText(row.schedule_slot_ts)} · ${row.slot_status||'已提交'} · 预测 #${row.prediction_id||'--'} · 发起 ${isoText(row.requested_at)} · 完成 ${isoText(row.completed_at)}`;
      await loadStrictHourlyHistory();
    } catch (error) { $('#strictHourlyStatus').textContent=`严格整点补跑失败：${error.message}`; }
    finally { button.disabled = false; button.textContent = '补跑当前严格整点'; }
  }
  function visibleHistory() {
    const filter = $('#filter').value;
    return state.history.filter(item => {
      if (!meltWithinRange(item)) return false;
      if (filter === 'actual_only') return item.history_status === 'actual_only';
      if (filter === 'predicted') return item.has_prediction;
      if (filter === 'compared') return item.history_status === 'compared';
      if (filter === 'hit') return item.hit_abs_le_005 === true;
      if (filter === 'miss') return item.hit_abs_le_005 === false;
      return true;
    });
  }
  function rowMeltno(item) {
    return item.matched_actual_meltno || item.actual_meltno || item.target_meltno || item.predicted_target_meltno || '';
  }
  function meltParts(value) {
    const text = String(value || '').trim();
    const full = text.match(/(\d{8})-(\d+)$/);
    if (full) return {date:Number(full[1]), sequence:Number(full[2]), full:true};
    const sequence = text.match(/(\d+)$/);
    return sequence ? {date:null, sequence:Number(sequence[1]), full:false} : null;
  }
  function compareMelt(value, bound, lower) {
    if (!String(bound || '').trim()) return true;
    const current=meltParts(value), edge=meltParts(bound);
    if (!current || !edge) return true;
    if (edge.full && current.full) {
      const left=current.date*1000+current.sequence, right=edge.date*1000+edge.sequence;
      return lower ? left>=right : left<=right;
    }
    return lower ? current.sequence>=edge.sequence : current.sequence<=edge.sequence;
  }
  function meltWithinRange(item) {
    const meltno=rowMeltno(item);
    return compareMelt(meltno,$('#meltFrom').value,true) && compareMelt(meltno,$('#meltTo').value,false);
  }
  function csvCell(value) {
    if (value === null || value === undefined) return '';
    let text=String(value);
    if (/^[=+\-@]/.test(text)) text=`'${text}`;
    return `"${text.replace(/"/g,'""')}"`;
  }
  function downloadCsv(filename, headers, rows) {
    const body=[headers,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n');
    const blob=new Blob([`\ufeff${body}`],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);const link=document.createElement('a');
    link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),0);
  }
  function exportPredictionCurve() {
    const items=visibleHistory().filter(item=>item.has_prediction);
    if(!items.length){$('#exportStatus').textContent='当前范围没有预测记录，无法导出。';return;}
    const headers=['预测ID','预测模式','预测发起时间','预测完成时间','预测时间槽','特征截止时间','数据最大时间','预测候选炉次','匹配实际炉次','实际开口时间','匹配规则','周期分钟','提前量分钟','P10','P50','P90','实际平均Si','绝对误差','±0.05命中'];
    const rows=items.map(item=>[item.prediction_id,item.request_mode,item.requested_at,item.execution_completed_at,item.schedule_slot_ts,item.prediction_cutoff_ts,item.feature_watermarks?.sensors?.max_source_ts||item.feature_watermarks?.pci?.max_source_ts,item.predicted_target_meltno||item.target_meltno,item.matched_actual_meltno||item.actual_meltno,item.matched_actual_open_ts||item.target_open_ts,item.match_rule_version,item.cadence_minutes,item.lead_minutes,item.prediction_p10,item.prediction_si_mean,item.prediction_p90,item.actual_si_mean,item.absolute_error,item.hit_abs_le_005===true?'命中':item.hit_abs_le_005===false?'未命中':'等待化验']);
    downloadCsv(`V20_Si预测曲线_${$('#from').value}_${$('#to').value}.csv`,headers,rows);
    $('#exportStatus').textContent=`已导出 ${rows.length} 个预测点；范围 ${$('#from').value} 至 ${$('#to').value}。`;
  }
  function exportActualCurve() {
    const unique=new Map();
    visibleHistory().filter(item=>item.actual_ready).forEach(item=>{const meltno=rowMeltno(item);if(meltno&&!unique.has(meltno))unique.set(meltno,item)});
    const items=[...unique.values()];
    if(!items.length){$('#exportStatus').textContent='当前范围没有实际平均 Si，无法导出。';return;}
    const headers=['炉次','正式开口时间','实际平均Si','有效试样数','实际数据更新时间','来源状态'];
    const rows=items.map(item=>[rowMeltno(item),item.matched_actual_open_ts||item.target_open_ts,item.actual_si_mean,item.actual_sample_count,item.source_updated_at,item.source_status||item.history_status]);
    downloadCsv(`实际平均Si曲线_${$('#from').value}_${$('#to').value}.csv`,headers,rows);
    $('#exportStatus').textContent=`已导出 ${rows.length} 炉实际平均 Si（已按炉次去重）。`;
  }
  function hourlySourceText(item) {
    if (item.prediction_source === 'strict_hourly') return '严格整点';
    if (item.prediction_source === 'scheduled_interval_fallback') return '60分钟任务（严格槽临时对照）';
    return '缺少预测';
  }
  function renderHourlyTable(data) {
    state.hourlyRows = Array.isArray(data.items) ? data.items : [];
    const metrics=data.metrics||{};
    $('#hourlyTableStatus').textContent=`${metrics.hour_count??state.hourlyRows.length} 个整点 · 严格预测 ${metrics.strict_prediction_count??0} · 临时对照 ${metrics.fallback_prediction_count??0} · 严格失败槽 ${metrics.failed_strict_slot_count??0} · 已对比 ${metrics.evaluated_count??0}`;
    $('#hourlyTableRows').innerHTML=state.hourlyRows.length?state.hourlyRows.map(item=>{
      const values=Array.isArray(item.actual_si_values)?item.actual_si_values:[];
      const source=hourlySourceText(item);
      const slotState=item.strict_slot_status||'尚无严格槽';
      const statusClass=item.strict_slot_status==='success'?'hit':item.strict_slot_status==='failed_retryable'?'miss':'wait';
      const actualMelt=item.matched_actual_meltno||item.target_meltno||'--';
      const close=item.matched_actual_close_ts?isoText(item.matched_actual_close_ts):(item.matched_actual_open_ts?'等待堵口':'--');
      const comparison=item.absolute_error==null?'等待化验':`${num(item.absolute_error)} / ${item.hit_abs_le_005?'命中':'未命中'}`;
      return `<tr><td>${esc(isoText(item.schedule_slot_ts))}</td><td><span class="${statusClass}">${esc(source)}</span><br>${esc(slotState)}${item.strict_attempt_count!=null?` · ${esc(item.strict_attempt_count)}次`:''}</td><td>${item.has_prediction?`${num(item.prediction_si_mean)}%`:'--'}</td><td>${item.has_prediction?`${num(item.prediction_p10)}–${num(item.prediction_p90)}%`:'--'}</td><td>${esc(actualMelt)}</td><td>${esc(isoText(item.matched_actual_open_ts))}</td><td>${esc(close)}</td><td class="wrap-values">${values.length?values.map(value=>`${num(value)}%`).join(' / '):'<span class="wait">等待化验</span>'}</td><td>${item.actual_ready?`${num(item.actual_si_mean)}%`:'--'}</td><td class="${item.hit_abs_le_005===true?'hit':item.hit_abs_le_005===false?'miss':'wait'}">${esc(comparison)}</td></tr>`;
    }).join(''):'<tr><td colspan="10" class="empty">当前日期范围暂无整点槽或60分钟预测记录</td></tr>';
  }
  async function loadHourlyTable() {
    try {
      const q=new URLSearchParams({date_from:$('#from').value,date_to:$('#to').value,limit:'5000',_ts:String(Date.now())});
      renderHourlyTable(await api(`/api/si-v20/hourly-table?${q}`));
    } catch(error) {
      $('#hourlyTableStatus').textContent=`每小时汇总读取失败：${error.message}`;
      $('#hourlyTableRows').innerHTML=`<tr><td colspan="10"><div class="error">${esc(error.message)}</div></td></tr>`;
    }
  }
  function exportHourlyTable() {
    if(!state.hourlyRows.length){$('#hourlyTableStatus').textContent='当前范围没有每小时记录，无法导出。';return;}
    const headers=['预测整点','预测来源','严格槽状态','严格重试次数','预测平均Si','P10','P90','对应炉次','实际开口时间','实际堵口时间','各次化验Si','平均Si','绝对误差','±0.05命中'];
    const rows=state.hourlyRows.map(item=>[item.schedule_slot_ts,hourlySourceText(item),item.strict_slot_status,item.strict_attempt_count,item.prediction_si_mean,item.prediction_p10,item.prediction_p90,item.matched_actual_meltno||item.target_meltno,item.matched_actual_open_ts,item.matched_actual_close_ts,(item.actual_si_values||[]).join(' / '),item.actual_si_mean,item.absolute_error,item.hit_abs_le_005===true?'命中':item.hit_abs_le_005===false?'未命中':'等待化验']);
    downloadCsv(`每小时Si预测与炉次化验_${$('#from').value}_${$('#to').value}.csv`,headers,rows);
    $('#hourlyTableStatus').textContent=`已导出 ${rows.length} 个整点的预测与炉次化验汇总。`;
  }
  function drawChart(items) {
    const canvas = $('#chart'); const ratio = window.devicePixelRatio || 1; const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(320, Math.floor(rect.width * ratio)); canvas.height = Math.max(180, Math.floor(rect.height * ratio));
    const ctx = canvas.getContext('2d'); ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,rect.width,rect.height);
    const ordered = [...items].sort((a,b) => String(a.schedule_slot_ts||a.target_open_ts||a.prediction_cutoff_ts||'').localeCompare(String(b.schedule_slot_ts||b.target_open_ts||b.prediction_cutoff_ts||'')));
    const values = ordered.flatMap(item => [item.actual_si_mean,item.prediction_p10,item.prediction_p90]).filter(hasNumber).map(Number);
    if (!values.length) { ctx.fillStyle='#a7c0c7';ctx.font='13px SimSun';ctx.fillText('暂无可绘制的实际或预测数据',20,32);return; }
    let min=Math.min(...values,0.15),max=Math.max(...values,0.45);const pad=Math.max(.02,(max-min)*.12);min-=pad;max+=pad;const m={l:48,r:15,t:15,b:48};const innerW=rect.width-m.l-m.r,innerH=rect.height-m.t-m.b;
    const parseTs=value=>{if(!value)return NaN;const normalized=String(value).trim().replace(' ','T');const parsed=Date.parse(normalized);return Number.isFinite(parsed)?parsed:NaN};
    const timestamps=ordered.map(item=>parseTs(item.schedule_slot_ts||item.target_open_ts||item.prediction_cutoff_ts||item.requested_at));
    const validTimes=timestamps.filter(Number.isFinite);const timeMin=validTimes.length?Math.min(...validTimes):0;const timeMax=validTimes.length?Math.max(...validTimes):0;const timeSpan=timeMax-timeMin;
    const x=i=>{if(!Number.isFinite(timestamps[i])||!timeSpan)return m.l+(ordered.length<2?innerW/2:i*innerW/(ordered.length-1));return m.l+(timestamps[i]-timeMin)*innerW/timeSpan};const y=v=>m.t+(max-v)*innerH/(max-min);
    ctx.strokeStyle='#294a57';ctx.fillStyle='#a7c0c7';ctx.font='11px SimSun';for(let i=0;i<=5;i++){const v=min+(max-min)*i/5,yy=y(v);ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(rect.width-m.r,yy);ctx.stroke();ctx.fillText(v.toFixed(2),5,yy+4)}
    const band = (topKey,bottomKey) => { ctx.fillStyle='rgba(101,211,157,.18)';ctx.beginPath();let started=false;ordered.forEach((item,i)=>{if(!hasNumber(item[topKey]))return;const xx=x(i),yy=y(Number(item[topKey]));if(!started){ctx.moveTo(xx,yy);started=true}else ctx.lineTo(xx,yy)});for(let i=ordered.length-1;i>=0;i--){const item=ordered[i];if(!hasNumber(item[bottomKey]))continue;ctx.lineTo(x(i),y(Number(item[bottomKey])))}ctx.closePath();ctx.fill()};
    band('prediction_p90','prediction_p10');
    const line=(key,color)=>{ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2;ctx.beginPath();let started=false;ordered.forEach((item,i)=>{if(!hasNumber(item[key])){started=false;return}const xx=x(i),yy=y(Number(item[key]));if(!started){ctx.moveTo(xx,yy);started=true}else ctx.lineTo(xx,yy)});ctx.stroke();ordered.forEach((item,i)=>{if(!hasNumber(item[key]))return;ctx.beginPath();ctx.arc(x(i),y(Number(item[key])),3,0,Math.PI*2);ctx.fill()})};
    line('actual_si_mean','#5cb8e8');line('prediction_si_mean','#65d39d');
    ctx.strokeStyle='#315866';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(m.l,rect.height-m.b+1);ctx.lineTo(rect.width-m.r,rect.height-m.b+1);ctx.stroke();
    ctx.fillStyle='#a7c0c7';ctx.textAlign='center';
    if(validTimes.length){
      const hour=60*60*1000;const firstHour=Math.ceil(timeMin/hour)*hour;const lastHour=Math.floor(timeMax/hour)*hour;const ticks=[];
      for(let tick=firstHour;tick<=lastHour;tick+=hour)ticks.push(tick);
      const stride=Math.max(1,Math.ceil(ticks.length/12));const multiDay=new Date(timeMin).toLocaleDateString()!==new Date(timeMax).toLocaleDateString();
      ticks.forEach((tick,index)=>{if(index%stride)return;const xx=m.l+(tick-timeMin)*innerW/(timeSpan||1);ctx.strokeStyle='#315866';ctx.beginPath();ctx.moveTo(xx,rect.height-m.b+1);ctx.lineTo(xx,rect.height-m.b+6);ctx.stroke();const date=new Date(tick);const label=multiDay?`${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')} ${String(date.getHours()).padStart(2,'0')}:00`:`${String(date.getHours()).padStart(2,'0')}:00`;ctx.fillStyle='#a7c0c7';ctx.fillText(label,xx,rect.height-17)});
    } else {const step=Math.max(1,Math.ceil(ordered.length/12));ordered.forEach((item,i)=>{if(i%step&&i!==ordered.length-1)return;ctx.fillText(String(item.target_meltno||'').split('-').pop(),x(i),rect.height-17)})}
    ctx.textAlign='start';
  }
  function detailLink(item) { return item.prediction_id ? `<span class="row-link" data-prediction-id="${esc(item.prediction_id)}">查看审计</span>` : '仅实际实绩'; }
  function renderHistory(data) {
    state.history = Array.isArray(data.items) ? data.items : [];
    const metrics=data.metrics||{}; const actualCount=metrics.unique_actual_heat_count ?? metrics.actual_count ?? metrics.matched_heat_count; const matchedPoints=metrics.matched_prediction_count; $('#metrics').innerHTML=[['匹配/实际炉次',actualCount],...(matchedPoints===undefined?[]:[['已匹配预测点',matchedPoints]]),['已预测',metrics.prediction_count],['已完成对比',metrics.evaluated_count],['MAE',num(metrics.mae,4)],['RMSE',num(metrics.rmse,4)],['bias',num(metrics.bias,4)],['±0.02',pct(metrics.hit_rate_abs_le_002)],['±0.05',pct(metrics.hit_rate_abs_le_005)]].map(([a,b])=>`<span class="chip">${a} ${b ?? '--'}</span>`).join('');
    const items=visibleHistory(); $('#historyRows').innerHTML=items.length?items.map(item=>{const timed=['strict_hourly','hourly_schedule','scheduled_interval','scheduled_time_replay'].includes(item.request_mode);const cadence=item.cadence_minutes?` · 每${item.cadence_minutes}分钟`:'';const strict=item.request_mode==='strict_hourly';const heatLabel=timed?`<b>${strict?'严格整点候选':'预测候选'} ${esc(item.predicted_target_meltno||item.target_meltno||'--')}${esc(cadence)}</b><br>${item.matched_actual_meltno?`匹配实际 ${esc(item.matched_actual_meltno)} · ${esc(isoText(item.matched_actual_open_ts))}`:strict?'等待预测完成后的下一次真实开口':'等待该时间点之后的下一次真实开口'}${item.schedule_slot_ts?`<br>时间槽 ${esc(isoText(item.schedule_slot_ts))}`:''}`:`<b>${esc(item.target_meltno||'--')}</b><br>${esc(isoText(item.target_open_ts))}`;return `<tr><td>${heatLabel}</td><td>${item.has_prediction?esc(isoText(item.requested_at)):'--'}</td><td>${item.has_prediction?esc(isoText(item.execution_completed_at)):'--'}</td><td>${esc(isoText(item.prediction_cutoff_ts))}</td><td>${item.has_prediction?`${num(item.lead_minutes,1)} min`:'--'}</td><td>${item.has_prediction?`${num(item.prediction_si_mean)}%`:'--'}</td><td>${item.has_prediction?`${num(item.prediction_p10)}–${num(item.prediction_p90)}%`:'--'}</td><td>${item.actual_ready?`${num(item.actual_si_mean)}%`:'<span class="wait">等待化验</span>'}</td><td>${item.actual_sample_count ?? '--'}</td><td>${item.absolute_error == null?'--':num(item.absolute_error)}</td><td class="${item.hit_abs_le_005===true?'hit':item.hit_abs_le_005===false?'miss':'wait'}">${item.hit_abs_le_005===true?'命中':item.hit_abs_le_005===false?'未命中':item.has_prediction?'待对比':'未预测'}</td><td>${detailLink(item)}</td></tr>`}).join(''):'<tr><td colspan="12" class="empty">当前筛选没有记录</td></tr>';
    drawChart(items);
    document.querySelectorAll('[data-prediction-id]').forEach(node=>node.addEventListener('click',()=>loadDetail(node.dataset.predictionId)));
  }
  async function loadHistory() {
    $('#historyError').textContent='';
    state.historyMode='heat';
    try { const q=new URLSearchParams({date_from:$('#from').value,date_to:$('#to').value,latest_per_heat:'1',limit:'1200',_ts:String(Date.now())});renderHistory(await api(`/api/si-v20/history?${q}`)); }
    catch(error){setError($('#historyError'),error)}
  }
  async function loadHourlyHistory() {
    $('#historyError').textContent=''; state.historyMode='hourly';
    try { const q=new URLSearchParams({date_from:$('#from').value,date_to:$('#to').value,limit:'1200',_ts:String(Date.now())});renderHistory(await api(`/api/si-v20/hourly-history?${q}`)); }
    catch(error){setError($('#historyError'),error)}
  }
  async function loadStrictHourlyHistory() {
    $('#historyError').textContent=''; state.historyMode='strictHourly';
    try { const q=new URLSearchParams({date_from:$('#from').value,date_to:$('#to').value,meltno_from:$('#meltFrom').value,meltno_to:$('#meltTo').value,limit:'5000',_ts:String(Date.now())});renderHistory(await api(`/api/si-v20/strict-hourly/history?${q}`)); }
    catch(error){setError($('#historyError'),error)}
  }
  async function loadScheduledHistory() {
    $('#historyError').textContent=''; state.historyMode='scheduled';
    try { const q=new URLSearchParams({date_from:$('#from').value,date_to:$('#to').value,cadence_minutes:$('#batchCadence').value,limit:'10000',_ts:String(Date.now())});renderHistory(await api(`/api/si-v20/scheduled-history?${q}`)); }
    catch(error){setError($('#historyError'),error)}
  }
  async function loadActiveHistory(){return state.historyMode==='strictHourly'?loadStrictHourlyHistory():state.historyMode==='hourly'?loadHourlyHistory():state.historyMode==='scheduled'?loadScheduledHistory():loadHistory()}
  async function refreshAll() {
    if (state.refreshInFlight) return;
    state.refreshInFlight = true;
    try {
      const now = new Date();
      const nextDateTo = dateIso(now);
      const nextDateFrom = dateIso(new Date(now.getTime() - 6 * 86400000));
      if ($('#to').value === state.autoDateTo) {
        $('#to').value = nextDateTo;
        state.autoDateTo = nextDateTo;
      }
      if ($('#from').value === state.autoDateFrom) {
        $('#from').value = nextDateFrom;
        state.autoDateFrom = nextDateFrom;
      }
      await Promise.all([loadStatus(),loadSchedule(),loadStrictHourlyStatus(),loadHourlyTable()]);
      await loadActiveHistory();
      if ($('#target').value.trim()) await checkReadiness();
      $('#refreshMeta').textContent = `最近刷新 ${new Date().toLocaleTimeString('zh-CN',{hour12:false})} · 每60秒自动刷新`;
    } finally { state.refreshInFlight = false; }
  }
  async function loadDetail(id) {
    try { const data=await api(`/api/si-v20/prediction-detail?prediction_id=${encodeURIComponent(id)}`);const values=Object.entries(data.features||{}).map(([k,v])=>`${k}=${v ?? '缺失'}`).join('\n');const watermarks=JSON.stringify(data.prediction.feature_watermarks||{},null,2);window.alert(`预测审计 #${id}\n初始候选：${data.prediction.initial_target_meltno||data.prediction.target_meltno}\n固定匹配：${data.prediction.matched_actual_meltno||'等待下一炉'}\n预测：${num(data.prediction.prediction_si_mean)}%\n实际：${num(data.prediction.actual_si_mean)}%\n发起：${isoText(data.prediction.requested_at)}\n完成：${isoText(data.prediction.execution_completed_at)}\n\n数据水位：\n${watermarks}\n\n输入特征：\n${values}`); }
    catch(error){window.alert(`读取预测详情失败：${error.message}`)}
  }
  async function replay(){const button=$('#replayBtn');button.disabled=true;button.textContent='回放中…';try{await api('/api/si-v20/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date_from:$('#from').value,date_to:$('#to').value,limit:200})});await loadHistory()}catch(error){setError($('#historyError'),error)}finally{button.disabled=false;button.textContent='按开口前60分钟回放'}}
  async function scheduledReplay(specified=false){const button=specified?$('#specifiedReplayBtn'):$('#batchReplayBtn');button.disabled=true;button.textContent='预测中…';try{const payload=specified?{cutoff_ts:$('#specifiedTs').value,cadence_minutes:Number($('#batchCadence').value),furnace_no:'2'}:{start_ts:$('#batchStartTs').value,end_ts:$('#batchEndTs').value,cadence_minutes:Number($('#batchCadence').value),furnace_no:'2'};const data=await api('/api/si-v20/scheduled-replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('#scheduledReplayStatus').textContent=`批次 #${data.run_id} · ${data.run_status} · 成功 ${data.predicted_count}/${data.requested_count} · 失败 ${data.failed_count}`;await loadScheduledHistory()}catch(error){$('#scheduledReplayStatus').textContent=`定时回放失败：${error.message}`}finally{button.disabled=false;button.textContent=specified?'预测指定时刻':'按时间粒度批量预测'}}
  $('#from').value=state.autoDateFrom;$('#to').value=state.autoDateTo;
  $('#batchStartTs').value=`${state.autoDateFrom}T00:00`;$('#batchEndTs').value=`${state.autoDateTo}T23:59`;$('#specifiedTs').value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
  $('#cutoffMode').addEventListener('change',()=>{$('#cutoffTs').disabled=$('#cutoffMode').value!=='explicit';checkReadiness()});$('#target').addEventListener('change',()=>{const item=[...(state.status?.candidate_targets||[]),...(state.status?.targets||[])].find(x=>x.meltno===$('#target').value.trim());if(item){state.selected=item;$('#openTs').value=localInput(item.open_ts)}checkReadiness()});$('#openTs').addEventListener('change',checkReadiness);$('#cutoffTs').addEventListener('change',checkReadiness);$('#readinessBtn').addEventListener('click',checkReadiness);$('#predictBtn').addEventListener('click',predict);$('#strictHourlyBtn').addEventListener('click',strictHourlyPredict);$('#saveScheduleBtn').addEventListener('click',saveSchedule);$('#historyBtn').addEventListener('click',loadHistory);$('#strictHourlyHistoryBtn').addEventListener('click',loadStrictHourlyHistory);$('#hourlyHistoryBtn').addEventListener('click',loadHourlyHistory);$('#scheduledHistoryBtn').addEventListener('click',loadScheduledHistory);$('#batchReplayBtn').addEventListener('click',()=>scheduledReplay(false));$('#specifiedReplayBtn').addEventListener('click',()=>scheduledReplay(true));$('#replayBtn').addEventListener('click',replay);$('#filter').addEventListener('change',()=>renderHistory({items:state.history,metrics:{actual_count:state.history.filter(x=>x.actual_ready).length,prediction_count:state.history.filter(x=>x.has_prediction).length,evaluated_count:state.history.filter(x=>x.absolute_error!=null).length}}));$('#applyRangeBtn').addEventListener('click',()=>{renderHistory({items:state.history,metrics:{actual_count:visibleHistory().filter(x=>x.actual_ready).length,prediction_count:visibleHistory().filter(x=>x.has_prediction).length,evaluated_count:visibleHistory().filter(x=>x.absolute_error!=null).length}});loadHourlyTable();$('#exportStatus').textContent=`已应用炉次范围：${$('#meltFrom').value||'不限'} 至 ${$('#meltTo').value||'不限'}。`});$('#downloadPredictionBtn').addEventListener('click',exportPredictionCurve);$('#downloadActualBtn').addEventListener('click',exportActualCurve);$('#downloadHourlyTableBtn').addEventListener('click',exportHourlyTable);$('#refresh').addEventListener('click',refreshAll);window.addEventListener('resize',()=>drawChart(visibleHistory()));
  loadStatus();loadSchedule();loadStrictHourlyStatus();loadHistory();loadHourlyTable();setInterval(refreshAll,60000);
})();
