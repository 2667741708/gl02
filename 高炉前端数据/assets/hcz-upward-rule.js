(() => {
  "use strict";

  const el = Object.fromEntries([
    "serviceState", "refreshButton", "loadingState", "errorState", "errorText", "retryButton", "content",
    "decisionCard", "conclusion", "decisionDetail", "decisionBadge", "evaluationTime", "gateGrid",
    "durationValue", "durationProgress", "durationText", "windowText", "metricBody", "layerSummary",
    "layerGrid", "sourceText", "sensitivityForm", "runSensitivityButton", "resetSensitivityButton",
    "trialTopTemperature", "trialPressureDrop", "trialPermeability", "trialGasUtilisation",
    "trialBlastPressure", "trialBodyTemperature", "trialMinLayers", "trialConsecutiveHours",
    "trialHistoryDays", "sensitivityState", "sensitivityResult", "sensitivitySummary",
    "baselineUpEpisodes", "baselineUpHours", "scenarioUpEpisodes", "scenarioUpHours",
    "baselineDownEpisodes", "baselineDownHours", "scenarioDownEpisodes", "scenarioDownHours",
    "sensitivityChangeBody", "sensitivitySource",
  ].map((id) => [id, document.getElementById(id)]));
  const metricOrder = ["top_temperature", "total_pressure_drop", "permeability_index", "gas_utilisation", "blast_pressure"];
  const trialFields = {
    top_temperature_delta_c: el.trialTopTemperature,
    total_pressure_drop_kpa: el.trialPressureDrop,
    permeability_drop: el.trialPermeability,
    gas_utilisation_drop_pp: el.trialGasUtilisation,
    cold_blast_pressure_rise_kpa: el.trialBlastPressure,
    body_temperature_delta_c: el.trialBodyTemperature,
    min_directional_layers: el.trialMinLayers,
    required_consecutive_hours: el.trialConsecutiveHours,
  };
  let loading = false;
  let sensitivityLoading = false;
  let productionDefaults = null;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
  }
  function formatTime(value) {
    if (!value) return "--";
    return new Intl.DateTimeFormat("zh-CN", {year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value));
  }
  function number(value, digits = 2) {
    return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "--";
  }
  function valueUnitText(metric) {
    return metric.unit === "percentage_point" ? "%" : metric.unit;
  }
  function changeUnitText(metric) {
    return metric.unit === "percentage_point" ? "个百分点" : metric.unit;
  }
  function deltaText(metric) {
    if (!Number.isFinite(Number(metric.delta))) return "--";
    const sign = Number(metric.delta) > 0 ? "+" : "";
    return `${sign}${number(metric.delta)} ${changeUnitText(metric)}`;
  }
  function thresholdText(metric) {
    const sign = metric.direction === "increase" ? "≥+" : "≤−";
    return `${sign}${number(metric.threshold)} ${changeUnitText(metric)}`;
  }
  function gate(label, passed, detail) {
    return `<div class="gate ${passed ? "pass" : "fail"}"><span>${escapeHtml(label)}</span><strong>${passed ? "通过" : "未通过"}</strong><small>${escapeHtml(detail)}</small></div>`;
  }

  function applyProductionDefaults() {
    if (!productionDefaults) return;
    Object.entries(trialFields).forEach(([key, input]) => {
      if (input && productionDefaults[key] !== undefined) input.value = productionDefaults[key];
    });
  }

  function render(payload) {
    const status = payload.status;
    el.content.hidden = false;
    el.errorState.hidden = true;
    el.loadingState.hidden = true;
    el.serviceState.className = "status ready";
    el.serviceState.textContent = "实测规则就绪";
    el.decisionCard.className = `decision-card ${status === "triggered" ? "triggered" : status === "insufficient_data" ? "insufficient" : ""}`;
    el.conclusion.textContent = payload.conclusion;
    el.decisionBadge.textContent = status === "triggered" ? "上移指示" : status === "insufficient_data" ? "数据不足" : "未触发";
    const reasons = payload.missing_reasons || [];
    el.decisionDetail.textContent = reasons.length ? reasons.join("；") : "该结论仅表示是否达到本条高炉长经验组合，不是软熔带直接测量。";
    el.evaluationTime.textContent = `评价时刻 ${formatTime(payload.evaluation_time)}`;
    const gates = payload.gates || {};
    el.gateGrid.innerHTML = [
      gate("五项核心指标", gates.core_all_pass, "24小时均值对前5天"),
      gate("炉壁温度层数", gates.body_layers_pass, `上升层：${(payload.body_temperature?.rising_layers || []).join("、") || "无"}`),
      gate("连续12小时", gates.duration_pass, `最长连续${payload.sustained_trend?.max_consecutive_hours || 0}小时`),
    ].join("");
    const duration = Number(payload.sustained_trend?.max_consecutive_hours || 0);
    const required = Number(payload.sustained_trend?.required_consecutive_hours || 12);
    el.durationValue.textContent = `${duration}小时`;
    el.durationProgress.style.width = `${Math.min(100, duration / required * 100)}%`;
    el.durationText.textContent = `最近24小时共有${payload.sustained_trend?.qualified_hour_count || 0}个合格小时，最长连续${duration}小时。`;
    const windows = payload.windows || {};
    el.windowText.textContent = `${formatTime(windows.current_start)} 至 ${formatTime(windows.current_end)}`;
    el.metricBody.innerHTML = metricOrder.map((key) => {
      const metric = payload.metrics?.[key] || {};
      const css = !metric.coverage_pass ? "missing-text" : metric.threshold_pass ? "pass-text" : "fail-text";
      const result = !metric.coverage_pass ? "数据不足" : metric.threshold_pass ? "通过" : "未达到";
      return `<tr><td>${escapeHtml(metric.label || key)}</td><td>${number(metric.current_24h_mean)} ${escapeHtml(valueUnitText(metric))}</td><td>${number(metric.baseline_5d_mean)} ${escapeHtml(valueUnitText(metric))}</td><td>${escapeHtml(deltaText(metric))}</td><td>${escapeHtml(thresholdText(metric))}</td><td class="${css}">${result}</td></tr>`;
    }).join("");
    const body = payload.body_temperature || {};
    el.layerSummary.textContent = `≥10℃：${(body.rising_layers || []).length}层｜≥20℃：${(body.strong_rising_layers || []).length}层`;
    el.layerGrid.innerHTML = (body.layers || []).map((layer) => {
      const css = layer.rise_20c_pass ? "strong" : layer.rise_10c_pass ? "rise" : "";
      const state = !layer.coverage_pass ? "数据不足" : layer.rise_20c_pass ? "强上升" : layer.rise_10c_pass ? "上升" : "未达到";
      return `<div class="layer ${css}"><strong>第${layer.layer}层</strong><span>${Number.isFinite(Number(layer.delta_c)) && Number(layer.delta_c) > 0 ? "+" : ""}${number(layer.delta_c)}℃</span><small>${state}</small></div>`;
    }).join("");
    const source = payload.source || {};
    el.sourceText.textContent = `数据：bf_sensor分钟实测｜最新 ${formatTime(source.latest_sample_time)}｜${payload.cache === "hit" ? "缓存结果" : `查询${source.query_elapsed_ms || 0}ms`}`;
    if (!productionDefaults && payload.sensitivity?.parameters) {
      productionDefaults = Object.fromEntries(Object.entries(payload.sensitivity.parameters).map(([key, spec]) => [key, spec.default]));
      applyProductionDefaults();
    }
  }

  function countText(summary) {
    return `${Number(summary?.episode_count || 0)}次`;
  }

  function hourText(summary) {
    return `命中评价小时 ${Number(summary?.triggered_evaluation_hours || 0)} 个`;
  }

  function signed(value) {
    const amount = Number(value || 0);
    return `${amount > 0 ? "+" : ""}${amount}`;
  }

  function timeSamples(values) {
    const items = (values || []).slice(0, 4).map(formatTime);
    return items.length ? items.join("、") : "无";
  }

  function renderSensitivity(payload) {
    const baseline = payload.baseline || {};
    const scenario = payload.scenario || {};
    const comparison = payload.comparison || {};
    el.baselineUpEpisodes.textContent = countText(baseline.up);
    el.baselineUpHours.textContent = hourText(baseline.up);
    el.scenarioUpEpisodes.textContent = countText(scenario.up);
    el.scenarioUpHours.textContent = hourText(scenario.up);
    el.baselineDownEpisodes.textContent = countText(baseline.down);
    el.baselineDownHours.textContent = hourText(baseline.down);
    el.scenarioDownEpisodes.textContent = countText(scenario.down);
    el.scenarioDownHours.textContent = hourText(scenario.down);
    const upEpisodeDelta = Number(scenario.up?.episode_count || 0) - Number(baseline.up?.episode_count || 0);
    const downEpisodeDelta = Number(scenario.down?.episode_count || 0) - Number(baseline.down?.episode_count || 0);
    el.sensitivitySummary.textContent = `近${payload.history_days}天：上移事件 ${baseline.up?.episode_count || 0}→${scenario.up?.episode_count || 0}（${signed(upEpisodeDelta)}），对称下移候选 ${baseline.down?.episode_count || 0}→${scenario.down?.episode_count || 0}（${signed(downEpisodeDelta)}）。事件按连续命中评价小时合并。`;
    el.sensitivityChangeBody.innerHTML = [
      ["上移", comparison.up],
      ["对称下移候选", comparison.down],
    ].map(([label, item]) => `<tr><td>${escapeHtml(label)}</td><td>+${Number(item?.added_triggered_hour_count || 0)}</td><td>−${Number(item?.removed_triggered_hour_count || 0)}</td><td>${escapeHtml(timeSamples(item?.added_triggered_hours))}</td></tr>`).join("");
    const source = payload.source || {};
    el.sensitivitySource.textContent = `回放 ${formatTime(payload.evaluation_start)} 至 ${formatTime(payload.evaluation_end)}｜实测小时记录 ${source.hourly_record_count || 0}｜历史数据${source.history_cache === "hit" ? "缓存复用" : `查询${source.query_elapsed_ms || 0}ms`}｜规则计算${source.evaluation_elapsed_ms || 0}ms。下移是上移公式的符号对称候选，不是已确认生产规则。`;
    el.sensitivityState.className = "trial-state";
    el.sensitivityState.textContent = "试算完成。输入值没有保存到生产配置，也不会触发自动控制。";
    el.sensitivityResult.hidden = false;
  }

  async function runSensitivity(event) {
    event?.preventDefault();
    if (sensitivityLoading) return;
    if (!el.sensitivityForm.reportValidity()) return;
    sensitivityLoading = true;
    el.runSensitivityButton.disabled = true;
    el.resetSensitivityButton.disabled = true;
    el.sensitivityState.className = "trial-state";
    el.sensitivityState.textContent = `正在回放近${el.trialHistoryDays.value}天真实历史，请稍候…`;
    try {
      const query = new URLSearchParams({days: el.trialHistoryDays.value, t: Date.now().toString()});
      Object.entries(trialFields).forEach(([key, input]) => query.set(key, input.value));
      const response = await fetch(`/api/hcz-rule-sensitivity?${query}`, {cache: "no-store"});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) throw new Error(payload.message || `试算接口返回${response.status}`);
      renderSensitivity(payload);
    } catch (error) {
      el.sensitivityState.className = "trial-state error";
      el.sensitivityState.textContent = error.message || "阈值试算失败";
    } finally {
      sensitivityLoading = false;
      el.runSensitivityButton.disabled = false;
      el.resetSensitivityButton.disabled = false;
    }
  }

  async function load() {
    if (loading) return;
    loading = true;
    el.refreshButton.disabled = true;
    el.serviceState.className = "status waiting";
    el.serviceState.textContent = "计算中";
    if (el.content.hidden) el.loadingState.hidden = false;
    try {
      const response = await fetch(`/api/hcz-upward-rule?t=${Date.now()}`, {cache:"no-store"});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) throw new Error(payload.message || `接口返回${response.status}`);
      render(payload);
    } catch (error) {
      el.loadingState.hidden = true;
      el.errorState.hidden = false;
      el.errorText.textContent = error.message || "规则数据暂不可用";
      el.serviceState.className = "status error";
      el.serviceState.textContent = "读取失败";
    } finally {
      loading = false;
      el.refreshButton.disabled = false;
    }
  }

  el.refreshButton.addEventListener("click", load);
  el.retryButton.addEventListener("click", load);
  el.sensitivityForm.addEventListener("submit", runSensitivity);
  el.resetSensitivityButton.addEventListener("click", () => {
    applyProductionDefaults();
    el.trialHistoryDays.value = "90";
    el.sensitivityResult.hidden = true;
    el.sensitivityState.className = "trial-state";
    el.sensitivityState.textContent = "已恢复生产默认值；点击“运行历史试算”重新计算。";
  });
  load();
  window.setInterval(load, 5 * 60 * 1000);
})();
