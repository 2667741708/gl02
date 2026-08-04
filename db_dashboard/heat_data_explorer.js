/* REQ-HEAT-MULTISOURCE-EXPLORER-20260727 */
(() => {
  "use strict";

  const style = document.createElement("style");
  style.textContent = `
    .multi-source{margin-top:14px;border:1px solid var(--line);border-radius:6px;background:var(--panel)}
    .multi-source .panel-head{padding:10px 12px;border-bottom:1px solid var(--line)}
    .source-grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:8px;padding:10px 12px}
    .source-card{min-height:76px;padding:9px;border:1px solid #3b4b4b;border-radius:5px;background:#172020}
    .source-card strong{display:block;margin-bottom:5px}.source-card small{display:block;color:var(--muted);line-height:1.55}
    .source-card .ready{color:#82d6a1}.source-card .pending{color:#e2bc72}
    .multi-source,.source-grid,.data-query-form,.data-query-form>*{min-width:0}
    .data-query-form{display:grid;grid-template-columns:repeat(6,minmax(150px,1fr));gap:8px;padding:10px 12px;border-top:1px solid var(--line)}
    .data-query-form input,.data-query-form select{box-sizing:border-box;width:100%;max-width:100%;min-width:0}
    .data-query-form .wide{grid-column:span 2}.data-query-form .actions-row{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
    .data-result-meta{display:flex;flex-wrap:wrap;gap:7px;padding:0 12px 10px;color:var(--muted)}
    .data-result-wrap{max-height:540px;overflow:auto;border-top:1px solid var(--line)}
    .data-result-wrap table{min-width:100%;width:max-content}.data-result-wrap td{max-width:480px;white-space:normal;overflow-wrap:anywhere;vertical-align:top}
    .data-result-wrap th{position:sticky;top:0;z-index:1;background:#202a2b}
    .data-chart{height:300px;border-top:1px solid var(--line);display:none}
    .web-login{display:none;align-items:end;gap:8px;padding:0 12px 10px}
    .web-login.visible{display:flex}.web-login label{min-width:180px}
    @media(max-width:1280px){.source-grid{grid-template-columns:repeat(2,minmax(180px,1fr))}.data-query-form{grid-template-columns:repeat(3,minmax(150px,1fr))}}
    @media(max-width:768px){.source-grid,.data-query-form{grid-template-columns:minmax(0,1fr)}.data-query-form .wide{grid-column:auto}.data-query-form .actions-row{min-width:0;max-width:100%}.web-login{align-items:stretch;flex-direction:column}.web-login input{box-sizing:border-box;width:100%;max-width:100%;min-width:0}}
  `;
  document.head.append(style);

  const footer = document.querySelector("main footer");
  if (!footer) return;
  const section = document.createElement("section");
  section.className = "multi-source";
  section.innerHTML = `
    <div class="panel-head">
      <h2>多源数据查询工作台</h2>
      <span id="dataCatalogTag" class="tag">正在读取目录</span>
      <button id="refreshSourceHealth" type="button">刷新数据源状态</button>
    </div>
    <div id="sourceGrid" class="source-grid">
      <div class="loading">正在装载 pSpace、IMES Web、Vastbase 与 PostgreSQL 数据目录…</div>
    </div>
    <div id="webLogin" class="web-login">
      <label>IMES Web 当前验证码
        <input id="imesCaptcha" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="输入登录页验证码">
      </label>
      <button id="imesLoginBtn" type="button">授权 IMES Web 会话</button>
      <span id="imesLoginStatus" class="tag">密码不会返回浏览器</span>
    </div>
    <form id="dataQueryForm" class="data-query-form">
      <label class="wide">数据集
        <select id="dataDataset"></select>
      </label>
      <label>开始时间（含）
        <input id="dataStart" type="datetime-local" step="60">
      </label>
      <label>结束时间（不含）
        <input id="dataEnd" type="datetime-local" step="60">
      </label>
      <label>炉次号
        <input id="dataMeltno" type="search" placeholder="如 2#20260726-345">
      </label>
      <label>关键字
        <input id="dataSearch" type="search" placeholder="点位、批号、班次等">
      </label>
      <label class="wide">变量编号
        <input id="dataVariables" type="text" placeholder="逗号分隔，如 P_top,DP_total,GasUtil">
      </label>
      <label>每页行数
        <select id="dataLimit"><option>50</option><option selected>200</option><option>500</option><option>1000</option><option>5000</option></select>
      </label>
      <label>pSpace 聚合间隔
        <select id="dataInterval"><option value="10">10秒</option><option value="60" selected>1分钟</option><option value="300">5分钟</option><option value="900">15分钟</option><option value="3600">1小时</option></select>
      </label>
      <label>pSpace 聚合方式
        <select id="dataAggregate"><option value="PS_HIS_AVERAGE">平均值</option><option value="PS_HIS_MAXIMUM">最大值</option><option value="PS_HIS_MINIMUM">最小值</option><option value="PS_HIS_TOTAL">累计值</option></select>
      </label>
      <div class="actions-row">
        <button id="dataQueryBtn" class="primary" type="submit">查询数据</button>
        <button type="button" data-range="8h">最近8小时</button>
        <button type="button" data-range="24h">最近24小时</button>
        <button type="button" data-range="7d">最近7天</button>
        <button id="clearDataRange" type="button">不限时间</button>
        <button id="dataPrev" type="button" disabled>上一页</button>
        <button id="dataNext" type="button" disabled>下一页</button>
        <a id="dataCsv" class="button-link" href="#">导出当前页CSV</a>
        <a id="dataXlsx" class="button-link" href="#">导出当前页XLSX</a>
      </div>
    </form>
    <div id="dataResultMeta" class="data-result-meta"><span class="tag">等待查询</span></div>
    <div id="dataResultWrap" class="data-result-wrap"><div class="empty">选择数据集和任意时间范围后查询。所有接口只读。</div></div>
    <div id="dataChart" class="data-chart"></div>
  `;
  footer.before(section);

  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));
  const explorerState = {catalog: null, datasets: new Map(), offset: 0, hasMore: false, controller: null, chart: null, health: {}};

  function localInputValue(value) {
    const date = value instanceof Date ? value : new Date(value);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
  }

  function setRange(milliseconds) {
    const end = new Date();
    byId("dataEnd").value = localInputValue(end);
    byId("dataStart").value = localInputValue(new Date(end.getTime() - milliseconds));
    explorerState.offset = 0;
  }

  function sourceCards(catalog) {
    const present = catalog.credential_fields_present || {};
    const counts = Object.fromEntries(
      Object.entries(catalog.sources || {}).map(([key, items]) => [key, items.length])
    );
    const items = [
      ["pspace", "pSpace", counts.pspace || 0, present.pspace, "实时133点＋任意范围历史聚合"],
      ["imes_web", "IMES Web", counts.imes_web || 0, present.imes_web, "12个已核实只读业务端点；验证码/会话授权"],
      ["vastbase", "Vastbase", (counts.vastbase_operations || 0) + (counts.vastbase_laboratory || 0), present.vastbase_operations && present.vastbase_laboratory, "作业账号＋化验账号两套权限面"],
      ["postgres_gl02", "PostgreSQL GL02", counts.postgres_gl02 || 0, true, "传感器、炉况、基线、质量与短时总结"]
    ];
    byId("sourceGrid").innerHTML = items.map(([key, label, count, configured, text]) => `
      <div class="source-card" data-source="${escapeHtml(key)}">
        <strong>${escapeHtml(label)} <span data-health="${escapeHtml(key)}" class="${configured ? "ready" : "pending"}">${configured ? "已配置，待探测" : "待配置/授权"}</span></strong>
        <small>${escapeHtml(count)} 个数据集</small><small>${escapeHtml(text)}</small>
      </div>`).join("");
    byId("webLogin").classList.toggle("visible", Boolean(present.imes_web));
  }

  async function probeOneSource(source) {
    const status = document.querySelector(`[data-health="${source}"]`);
    if (status) {
      status.textContent = "探测中";
      status.className = "pending";
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort("timeout"), 7000);
    try {
      const response = await fetch(`/api/data-source-health?source=${encodeURIComponent(source)}`, {
        cache: "no-store",
        signal: controller.signal
      });
      const data = await response.json();
      explorerState.health[source] = data;
      if (!response.ok && data.state !== "authorization_required") {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      if (status) {
        const needsAuth = data.state === "authorization_required";
        status.textContent = needsAuth ? "等待验证码授权" : `可用 · ${data.elapsed_ms}ms`;
        status.className = needsAuth ? "pending" : "ready";
        status.title = JSON.stringify(data.detail || {});
      }
    } catch (error) {
      explorerState.health[source] = {ok: false, error: error.message};
      if (status) {
        status.textContent = error.name === "AbortError" ? "探测超时" : "不可用";
        status.className = "pending";
        status.title = error.message;
      }
    } finally {
      clearTimeout(timer);
    }
  }

  async function refreshSourceHealth() {
    byId("refreshSourceHealth").disabled = true;
    try {
      await Promise.allSettled(["pspace", "imes_web", "vastbase", "postgres_gl02"].map(probeOneSource));
    } finally {
      byId("refreshSourceHealth").disabled = false;
    }
  }

  function datasetOptions(catalog) {
    const select = byId("dataDataset");
    select.innerHTML = "";
    explorerState.datasets.clear();
    Object.entries(catalog.sources || {}).forEach(([source, items]) => {
      const group = document.createElement("optgroup");
      group.label = source;
      items.forEach(item => {
        explorerState.datasets.set(item.key, item);
        const option = document.createElement("option");
        option.value = item.key;
        option.textContent = `${item.label} · ${item.relation}`;
        group.append(option);
      });
      select.append(group);
    });
    const preferred = new URLSearchParams(location.search).get("dataset") || "vastbase.heat_master";
    if (explorerState.datasets.has(preferred)) select.value = preferred;
  }

  async function loadCatalog() {
    try {
      const response = await fetch("/api/data-catalog", {cache: "no-store"});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
      explorerState.catalog = data;
      datasetOptions(data);
      sourceCards(data);
      byId("dataCatalogTag").textContent = `${data.dataset_count} 个只读数据集`;
      byId("dataCatalogTag").className = "tag good";
      refreshSourceHealth();
    } catch (error) {
      byId("dataCatalogTag").textContent = "目录读取失败";
      byId("dataCatalogTag").className = "tag bad";
      byId("sourceGrid").innerHTML = `<div class="error">数据目录读取失败：${escapeHtml(error.message)}<br><button id="retryCatalog">重试</button></div>`;
      byId("retryCatalog")?.addEventListener("click", loadCatalog);
    }
  }

  function queryParams(format = "json") {
    const params = new URLSearchParams({
      dataset: byId("dataDataset").value,
      limit: byId("dataLimit").value,
      offset: String(explorerState.offset),
      interval_seconds: byId("dataInterval").value,
      aggregate: byId("dataAggregate").value,
      format
    });
    const fields = [
      ["start", "dataStart"], ["end", "dataEnd"], ["meltno", "dataMeltno"],
      ["search", "dataSearch"], ["variables", "dataVariables"]
    ];
    fields.forEach(([key, id]) => {
      const value = byId(id).value.trim();
      if (value) params.set(key, value);
    });
    return params;
  }

  function displayValue(value) {
    if (value === null || value === undefined) return '<span class="muted">NULL</span>';
    if (typeof value === "object") {
      return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
    }
    return escapeHtml(value);
  }

  function renderTable(data) {
    const columns = data.columns || [];
    const rows = data.rows || [];
    if (!rows.length) {
      byId("dataResultWrap").innerHTML = '<div class="empty">该数据集在当前条件下没有记录。</div>';
      renderDataChart(data);
      return;
    }
    const head = columns.map(column => `<th>${escapeHtml(column)}</th>`).join("");
    const body = rows.map(row => `<tr>${columns.map(column => `<td>${displayValue(row[column])}</td>`).join("")}</tr>`).join("");
    byId("dataResultWrap").innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    renderDataChart(data);
  }

  function renderDataChart(data) {
    const container = byId("dataChart");
    const rows = data.rows || [];
    const hasSeries = rows.some(row => row.timestamp && row.variable_name && Number.isFinite(Number(row.value)));
    container.style.display = hasSeries && window.echarts ? "block" : "none";
    if (!hasSeries || !window.echarts) return;
    explorerState.chart ||= echarts.init(container);
    const groups = {};
    rows.forEach(row => {
      const value = Number(row.value);
      if (!row.timestamp || !Number.isFinite(value)) return;
      (groups[row.variable_name] ||= []).push([row.timestamp, value]);
    });
    explorerState.chart.setOption({
      animation: false,
      backgroundColor: "transparent",
      tooltip: {trigger: "axis"},
      legend: {type: "scroll", textStyle: {color: "#c9d6d3"}},
      grid: {left: 56, right: 28, top: 48, bottom: 50},
      xAxis: {type: "time", axisLabel: {color: "#a9b8b5"}, axisLine: {lineStyle: {color: "#546563"}}},
      yAxis: {type: "value", scale: true, axisLabel: {color: "#a9b8b5"}, splitLine: {lineStyle: {color: "#2e3b3b"}}},
      dataZoom: [{type: "inside"}, {type: "slider", bottom: 8}],
      series: Object.entries(groups).map(([name, values]) => ({name, type: "line", showSymbol: false, connectNulls: false, data: values}))
    }, true);
  }

  async function runQuery({preserveOffset = false} = {}) {
    if (!explorerState.catalog) return;
    if (!preserveOffset) explorerState.offset = 0;
    explorerState.controller?.abort();
    explorerState.controller = new AbortController();
    const timeout = setTimeout(() => explorerState.controller.abort("timeout"), 15000);
    byId("dataQueryBtn").disabled = true;
    byId("dataResultWrap").innerHTML = '<div class="loading">正在执行只读查询…</div>';
    try {
      const params = queryParams();
      const response = await fetch(`/api/data-query?${params}`, {cache: "no-store", signal: explorerState.controller.signal});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
      explorerState.hasMore = Boolean(data.has_more);
      byId("dataPrev").disabled = explorerState.offset <= 0;
      byId("dataNext").disabled = !explorerState.hasMore;
      const page = Math.floor(explorerState.offset / Number(byId("dataLimit").value)) + 1;
      byId("dataResultMeta").innerHTML = [
        `<span class="tag good">${escapeHtml(data.dataset.label)}</span>`,
        `<span class="tag">第 ${page} 页 · ${data.rows.length} 行</span>`,
        `<span class="tag">${escapeHtml(data.elapsed_ms)} ms</span>`,
        `<span class="tag">${escapeHtml(data.query.window_semantics)}</span>`,
        data.source_meta ? `<span class="tag warn">${escapeHtml(JSON.stringify(data.source_meta))}</span>` : ""
      ].join("");
      renderTable(data);
      byId("dataCsv").href = `/api/data-query?${queryParams("csv")}`;
      byId("dataXlsx").href = `/api/data-query?${queryParams("xlsx")}`;
      const url = new URL(location.href);
      url.searchParams.set("dataset", byId("dataDataset").value);
      history.replaceState(null, "", url);
    } catch (error) {
      const message = error.name === "AbortError" ? "查询超过15秒，已在浏览器侧停止等待；请缩小范围或增加聚合间隔。" : error.message;
      byId("dataResultWrap").innerHTML = `<div class="error">数据查询失败：${escapeHtml(message)}<br><button id="retryDataQuery">重试</button></div>`;
      byId("dataResultMeta").innerHTML = '<span class="tag bad">查询失败</span>';
      byId("retryDataQuery")?.addEventListener("click", () => runQuery({preserveOffset: true}));
    } finally {
      clearTimeout(timeout);
      byId("dataQueryBtn").disabled = false;
    }
  }

  byId("dataQueryForm").addEventListener("submit", event => {
    event.preventDefault();
    runQuery();
  });
  byId("refreshSourceHealth").addEventListener("click", refreshSourceHealth);
  byId("dataPrev").addEventListener("click", () => {
    explorerState.offset = Math.max(0, explorerState.offset - Number(byId("dataLimit").value));
    runQuery({preserveOffset: true});
  });
  byId("dataNext").addEventListener("click", () => {
    explorerState.offset += Number(byId("dataLimit").value);
    runQuery({preserveOffset: true});
  });
  section.querySelectorAll("[data-range]").forEach(button => {
    button.addEventListener("click", () => {
      setRange(button.dataset.range === "8h" ? 8 * 3600e3 : button.dataset.range === "24h" ? 24 * 3600e3 : 7 * 86400e3);
      runQuery();
    });
  });
  byId("clearDataRange").addEventListener("click", () => {
    byId("dataStart").value = "";
    byId("dataEnd").value = "";
    explorerState.offset = 0;
  });
  byId("dataDataset").addEventListener("change", () => {
    explorerState.offset = 0;
    const spec = explorerState.datasets.get(byId("dataDataset").value);
    const exact = spec?.supports_exact_time !== false;
    byId("dataStart").disabled = !exact;
    byId("dataEnd").disabled = !exact;
  });
  byId("imesLoginBtn").addEventListener("click", async () => {
    const button = byId("imesLoginBtn");
    button.disabled = true;
    byId("imesLoginStatus").textContent = "正在建立只读会话";
    try {
      const response = await fetch("/api/imes-web/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({captcha: byId("imesCaptcha").value.trim()})
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
      byId("imesLoginStatus").textContent = "IMES Web 会话已授权";
      byId("imesLoginStatus").className = "tag good";
      byId("imesCaptcha").value = "";
      probeOneSource("imes_web");
    } catch (error) {
      byId("imesLoginStatus").textContent = `授权失败：${error.message}`;
      byId("imesLoginStatus").className = "tag bad";
    } finally {
      button.disabled = false;
    }
  });
  window.addEventListener("resize", () => explorerState.chart?.resize());
  setRange(24 * 3600e3);
  loadCatalog();
})();
