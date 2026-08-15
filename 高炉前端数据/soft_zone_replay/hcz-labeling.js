(() => {
  "use strict";

  const labels = {
    high: "偏高", normal: "正常", low: "偏低", uncertain: "无法判断",
    up: "上移", stable: "稳定", down: "下移",
    contemporaneous_blind: "同期盲标",
    retrospective_with_post_observation_evidence: "事后证据盲标",
  };
  const el = Object.fromEntries([
    "serviceStatus", "refreshButton", "identityText", "frameState", "replayFrame",
    "labelForm", "observedAt", "windowText", "centerHeight", "thickness",
    "eccentricSector", "confidenceGrade", "operatorName", "note", "contextState",
    "formError", "formSuccess", "submitButton", "historyLoading", "historyEmpty",
    "historyError", "historyTableWrap", "historyBody", "historyCount",
  ].map((id) => [id, document.getElementById(id)]));

  const state = { frame: null, context: null, submitting: false, supersedes: null };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function formatTime(value) {
    if (!value) return "--";
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(new Date(value));
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || `请求失败（${response.status}）`);
    return body;
  }

  function showMessage(target, message) {
    el.formError.hidden = true;
    el.formSuccess.hidden = true;
    if (target && message) { target.textContent = message; target.hidden = false; }
  }

  async function loadContext() {
    const frame = state.frame;
    if (!frame) return;
    state.context = null;
    el.submitButton.disabled = true;
    el.contextState.className = "context-state";
    el.contextState.textContent = "正在由服务器固定实测证据...";
    const query = new URLSearchParams({
      observed_at: frame.observed_at,
      start: frame.source_window_start,
      end: frame.source_window_end,
    });
    try {
      const context = await fetchJson(`/api/hcz-label-context?${query}`);
      if (!state.frame || state.frame.observed_at !== frame.observed_at) return;
      state.context = context;
      const mode = labels[context.context_mode] || context.context_mode;
      el.contextState.className = "context-state ready";
      el.contextState.textContent = `实测证据已固定｜${mode}｜主变量新鲜覆盖 ${(Number(context.primary_coverage || 0) * 100).toFixed(0)}%｜指纹 ${context.source_data_hash.slice(0, 12)}…`;
      el.submitButton.disabled = false;
    } catch (error) {
      el.contextState.textContent = error.message;
    }
  }

  function receiveReplayFrame(event) {
    if (event.origin !== window.location.origin || event.source !== el.replayFrame.contentWindow) return;
    const frame = event.data;
    if (!frame || frame.type !== "hcz-replay-frame" || frame.blind_to_model !== true || frame.model_outputs_included !== false) return;
    const changed = state.frame?.observed_at !== frame.observed_at
      || state.frame?.source_window_start !== frame.source_window_start
      || state.frame?.source_window_end !== frame.source_window_end;
    state.frame = frame;
    el.observedAt.textContent = formatTime(frame.observed_at);
    el.windowText.textContent = `证据窗口：${formatTime(frame.source_window_start)} 至 ${formatTime(frame.source_window_end)}`;
    el.frameState.textContent = "已选择时刻";
    if (changed) loadContext();
  }

  function idempotencyKey() {
    if (crypto.randomUUID) return `hcz-ui:${crypto.randomUUID()}`;
    return `hcz-ui:${Date.now()}:${Math.random().toString(16).slice(2)}`;
  }

  function selected(name) {
    return el.labelForm.querySelector(`input[name="${name}"]:checked`)?.value || "";
  }

  function buildPayload() {
    if (!state.frame || !state.context) throw new Error("请先在实测回放中选择标注时刻");
    const root = selected("root_level_label");
    const movement = selected("movement_label");
    if (!root) throw new Error("请选择软熔带位置高低");
    if (!movement) throw new Error("请选择软熔带移动方向");
    if (!el.confidenceGrade.value) throw new Error("请选择可信等级");
    const operator = el.operatorName.value.trim();
    if (operator.length < 2) throw new Error("请填写实际标注人姓名或工号");
    const note = el.note.value.trim();
    if (root === "uncertain" && movement === "uncertain" && note.length < 5) throw new Error("位置和方向均无法判断时，请说明原因");
    return {
      idempotency_key: idempotencyKey(),
      observed_at: state.frame.observed_at,
      source_window_start: state.frame.source_window_start,
      source_window_end: state.frame.source_window_end,
      source_data_hash: state.context.source_data_hash,
      root_level_label: root,
      movement_label: movement,
      center_height_m: el.centerHeight.value || null,
      thickness_m: el.thickness.value || null,
      eccentric_sector: el.eccentricSector.value || null,
      confidence_grade: Number(el.confidenceGrade.value),
      evidence_codes: [...el.labelForm.querySelectorAll('input[name="evidence"]:checked')].map((input) => input.value),
      operator_name: operator,
      note,
      supersedes_label_id: state.supersedes,
      source_page: window.location.pathname,
    };
  }

  async function submitLabel(event) {
    event.preventDefault();
    if (state.submitting) return;
    showMessage(null, "");
    let payload;
    try { payload = buildPayload(); } catch (error) { showMessage(el.formError, error.message); return; }
    state.submitting = true;
    el.submitButton.disabled = true;
    el.submitButton.textContent = "正在保存...";
    try {
      const result = await fetchJson("/api/hcz-labels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const item = result.label;
      showMessage(el.formSuccess, `已保存：${item.reference_id}${state.supersedes ? `（修订#${state.supersedes}）` : ""}`);
      state.supersedes = null;
      el.labelForm.reset();
      await loadHistory();
      await loadContext();
    } catch (error) {
      showMessage(el.formError, error.message);
    } finally {
      state.submitting = false;
      el.submitButton.textContent = "保存专家弱标签";
      el.submitButton.disabled = !state.context;
    }
  }

  function revise(item) {
    state.supersedes = item.id;
    const setRadio = (name, value) => {
      const input = el.labelForm.querySelector(`input[name="${name}"][value="${value}"]`);
      if (input) input.checked = true;
    };
    setRadio("root_level_label", item.root_level_label);
    setRadio("movement_label", item.movement_label);
    el.centerHeight.value = item.center_height_m ?? "";
    el.thickness.value = item.thickness_m ?? "";
    el.eccentricSector.value = item.eccentric_sector ?? "";
    el.confidenceGrade.value = String(item.confidence_grade || "");
    el.operatorName.value = item.operator_name || "";
    el.note.value = `修订#${item.id}：${item.note || ""}`;
    showMessage(el.formSuccess, `正在创建#${item.id}的修订记录；原记录不会被覆盖。`);
    document.querySelector(".form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadHistory() {
    el.historyLoading.hidden = false; el.historyEmpty.hidden = true; el.historyError.hidden = true; el.historyTableWrap.hidden = true;
    try {
      const data = await fetchJson("/api/hcz-labels?limit=200");
      el.historyCount.textContent = `${data.count}条`;
      el.historyLoading.hidden = true;
      if (!data.labels.length) { el.historyEmpty.hidden = false; return; }
      el.historyBody.innerHTML = data.labels.map((item) => `<tr>
        <td>#${item.id}<br><small>${escapeHtml(item.reference_id)}</small></td>
        <td>${escapeHtml(formatTime(item.observed_at))}</td>
        <td>${escapeHtml(labels[item.root_level_label] || item.root_level_label)}</td>
        <td>${escapeHtml(labels[item.movement_label] || item.movement_label)}</td>
        <td>${escapeHtml(item.confidence_grade)}/5</td>
        <td>${escapeHtml(item.operator_name)}</td>
        <td>${escapeHtml(labels[item.context_mode] || item.context_mode)}</td>
        <td><button type="button" class="link-button" data-revise="${item.id}">创建修订</button></td>
      </tr>`).join("");
      el.historyBody.querySelectorAll("[data-revise]").forEach((button) => {
        const item = data.labels.find((candidate) => candidate.id === Number(button.dataset.revise));
        button.addEventListener("click", () => revise(item));
      });
      el.historyTableWrap.hidden = false;
    } catch (error) {
      el.historyLoading.hidden = true; el.historyError.hidden = false; el.historyError.textContent = error.message;
    }
  }

  async function initialise() {
    try {
      const config = await fetchJson("/api/hcz-label-config");
      if (config.blind_to_model !== true || config.model_outputs_included !== false) throw new Error("盲标注安全门禁未生效");
      el.serviceStatus.className = "status ready"; el.serviceStatus.textContent = "标注服务就绪";
      el.identityText.textContent = `服务身份：${config.identity.sub}（${config.identity.role}）`;
      await loadHistory();
    } catch (error) {
      el.serviceStatus.className = "status error"; el.serviceStatus.textContent = "服务不可用";
      showMessage(el.formError, error.message);
    }
  }

  window.addEventListener("message", receiveReplayFrame);
  el.labelForm.addEventListener("submit", submitLabel);
  el.refreshButton.addEventListener("click", loadHistory);
  initialise();
})();
