(function installMultiConditionBrowserFixture() {
  const labels = ["normal", "edge", "center", "channel", "cold", "hot", "lowline", "column"];
  const names = {
    normal: "正常顺行",
    edge: "边缘发展",
    center: "中心发展",
    channel: "管道行程",
    cold: "热制度下行",
    hot: "热制度上行",
    lowline: "低料线",
    column: "悬料",
  };
  const scores = { normal: 42, edge: 68, center: 31, channel: 46, cold: 84, hot: 19, lowline: 72, column: 38 };
  const statuses = ["eligible", "blocked", "needs_data", "manual_confirm"];

  function makeAction(label, status, index) {
    return {
      id: `${label}_${status}`,
      name: `${names[label]}动作${index + 1}`,
      user_facing_text: status === "eligible"
        ? "满足条件，可进入现场确认队列"
        : status === "blocked"
          ? "当前被安全门禁阻断，不得执行"
          : status === "needs_data"
            ? "关键输入缺失，补齐后重新计算"
            : "具备研判依据，但必须人工审批确认",
      status,
      read_only: true,
      source_refs: ["《高炉工长技术操作规程》第4章", "《炉况异常处理制度》第2节"],
      trigger_evidence: [
        { description: `${names[label]}诊断分数为${scores[label]}分`, satisfied: true },
        { description: "最近30分钟趋势与规则方向一致", satisfied: true },
      ],
      preconditions: [
        { description: "确认风量、风压和顶压仪表有效", satisfied: true },
        { description: "核对上一动作观察窗口已结束", satisfied: index === 0 },
      ],
      blocking_reasons: status === "blocked" ? ["压差门禁已触发", "与当前主炉况有效方案存在冲突"] : [],
      delta: { direction: index % 2 ? "下调" : "上调", min: 2, max: 4, unit: "%", hourly_limit: { max: 5, unit: "%" } },
      sequence: { position: index + 1, depends_on: index ? [`${label}_${statuses[index - 1]}`] : [] },
      missing_inputs: status === "needs_data" ? ["PCI_set", "L_north"] : [],
      observation_window: { min_minutes: 15, max_minutes: 30 },
      approval: { required: status === "manual_confirm" || status === "eligible", role: "值班工长" },
    };
  }

  function makeRecommendation(label) {
    return {
      schema_version: "recommendation.v5",
      engine_version: "v5-complete",
      goal: `围绕${names[label]}进行只读调剂研判`,
      immediate_actions: [{ text: "先核对关键证据与安全门禁" }, { text: "按顺序执行单变量小幅调剂" }],
      followup_actions: [{ text: "观察15～30分钟后重新诊断" }],
      forbidden_actions: [{ text: "禁止绕过审批或同时大幅调整多项参数" }],
      observe_items: ["压差变化", "煤气利用率", "料线与风量响应"],
      recheck_minutes: 30,
      safety_warnings: ["所有动作均为只读建议，现场操作需审批"],
      operator_confirm_required: true,
      actions: statuses.map((status, index) => makeAction(label, status, index)),
    };
  }

  const conditions = labels.map((label) => ({
    label,
    display_name: names[label],
    score: scores[label],
    role: label === "cold" ? "main" : label === "lowline" ? "secondary" : "watch",
    scope: label === "cold" ? "active" : label === "lowline" ? "supporting" : "hypothetical",
    read_only: true,
    action_count: 4,
    status_counts: { eligible: 1, blocked: 1, needs_data: 1, manual_confirm: 1 },
    recommendation: makeRecommendation(label),
  }));
  const timestamps = Array.from({ length: 120 }, (_, index) => new Date(Date.now() - (119 - index) * 60000).toISOString());
  const bases = {
    PI: 0.82,
    P_top: 0.19,
    DP_total: 155,
    DP_upper: 71,
    DP_lower: 84,
    GasUtil: 47,
    T_top: 182,
    T_top_A: 178,
    T_top_B: 181,
    T_top_C: 186,
    T_top_D: 183,
    PCI_rate: 151,
    PCI_set: 152,
    Q_blast: 3720,
    T_blast: 1185,
    O2_rate: 3.2,
    L: 1.8,
    L_south: 1.7,
    L_north: 1.9,
  };
  const history = { timestamps };
  Object.keys(bases).forEach((key, keyIndex) => {
    history[key] = timestamps.map((unused, index) => bases[key] + Math.sin((index + keyIndex) / 12) * (Math.abs(bases[key]) * 0.01 + 0.03));
  });
  const diagnosisHistory = timestamps.filter((unused, index) => index % 10 === 0).map((timestamp, index) => ({
    timestamp,
    main_label: "cold",
    main_score: 78 + index * 0.5,
    secondary_label: "lowline",
    raw_scores: { ...scores, cold: 78 + index * 0.5 },
  }));
  const activePlan = makeRecommendation("cold");
  const diagnosis = {
    diagnosis_ts: timestamps[timestamps.length - 1],
    calculated_at: timestamps[timestamps.length - 1],
    main_label: "cold",
    main_score: 84,
    main_confidence: 0.88,
    secondary_label: "lowline",
    secondary_score: 72,
    raw_scores: scores,
    evidence: ["热制度下行分数持续上升", "低料线伴随证据成立"],
    baseline_compare: { T_top: { z_score: -1.7 }, GasUtil: { z_score: -1.2 } },
    data_coverage: { available: 27, total: 28, ratio: 0.964 },
    recommendation: activePlan,
    recommendation_bundle: { schema_version: "multi_condition_recommendation.v1", active_plan: activePlan, conditions },
  };
  const initMessage = {
    type: "init",
    timestamp: timestamps[timestamps.length - 1],
    history,
    diagnosis,
    diagnosis_history: diagnosisHistory,
    data_quality: { status: "good", coverage: 0.964 },
  };

  class FixtureWebSocket {
    constructor() {
      this.readyState = 0;
      this.listeners = {};
      setTimeout(() => {
        this.readyState = 1;
        this.emit("open", {});
        setTimeout(() => {
          this.emit("message", { data: JSON.stringify(initMessage) });
        }, 20);
      }, 10);
    }

    addEventListener(type, listener) {
      if (!this.listeners[type]) this.listeners[type] = new Set();
      this.listeners[type].add(listener);
    }

    removeEventListener(type, listener) {
      this.listeners[type]?.delete(listener);
    }

    emit(type, event) {
      if (typeof this[`on${type}`] === "function") this[`on${type}`](event);
      (this.listeners[type] || []).forEach((listener) => listener.call(this, event));
    }

    send() {}

    close() {
      this.readyState = 3;
    }
  }

  FixtureWebSocket.OPEN = 1;
  window.WebSocket = FixtureWebSocket;
})();
