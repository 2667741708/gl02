/**
 * 8093 core-metric live-value transport.
 *
 * The browser never connects to pSpace or receives pSpace credentials. It
 * subscribes to the server-side 8770 WebSocket bridge, which owns the
 * RealReadList SDK connection. PostgreSQL minute history remains owned by the
 * existing 8768 stream.
 */

const SCHEMA = "bf.core-metrics.pspace-live.8093.v1";
const EVENT_NAME = "bf:core-pspace-live";
const STALE_AFTER_MS = 12_000;
const RECONNECT_AFTER_MS = 3_000;

const CORE_IDS = Object.freeze([
  "P_top",
  "P_top_gas_A",
  "P_top_gas_B",
  "P_top_gas_C",
  "P_top_gas_D",
  "GasUtil",
  "TFT",
  "T_blast",
  "T_top_A",
  "T_top_B",
  "T_top_C",
  "T_top_D",
  "Q_blast",
  "P_blast_cold",
  "P_blast",
  "O2_rate",
  "Q_O2",
  "PI",
  "DP_upper",
  "DP_lower",
  "DP_total",
  "L",
  "L_south",
  "L_north",
  "PCI_rate",
  "PCI_set",
  "T_taphole_1",
  "T_taphole_2",
]);

const state = {
  schema: SCHEMA,
  status: "idle",
  url: "",
  connectedAt: "",
  lastFrameAt: "",
  lastReceivedAt: 0,
  validCount: 0,
  totalCount: CORE_IDS.length,
  lastError: "",
  staleAfterMs: STALE_AFTER_MS,
  values: {},
};

let socket = null;
let reconnectTimer = 0;
let ageTimer = 0;

function finiteValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function latestHistoryValue(history, id) {
  const values = history?.[id];
  if (!Array.isArray(values)) return finiteValue(values);
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = finiteValue(values[index]);
    if (value !== null) return value;
  }
  return null;
}

function qualityIsBad(quality, error = "") {
  const text = `${quality ?? ""} ${error ?? ""}`.trim().toLowerCase();
  return Boolean(
    text && /(bad|uncertain|invalid|error|failed|failure|异常|失败|无效|不确定)/i.test(text),
  );
}

function timestampMs(value) {
  if (!value) return null;
  const direct = Date.parse(String(value));
  if (Number.isFinite(direct)) return direct;
  const normalized = String(value).trim().replaceAll("/", "-").replace(" ", "T");
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function recordAgeMs(record, now = Date.now()) {
  const sourceMs = timestampMs(record?.timestamp);
  const basis = sourceMs ?? Number(record?.receivedAt || 0);
  return basis > 0 ? Math.max(0, now - basis) : Number.POSITIVE_INFINITY;
}

function transportAgeMs(record, now = Date.now()) {
  const receivedAt = Number(record?.receivedAt || 0);
  return receivedAt > 0 ? Math.max(0, now - receivedAt) : Number.POSITIVE_INFINITY;
}

function snapshot(now = Date.now()) {
  const values = {};
  for (const id of CORE_IDS) {
    const record = state.values[id];
    if (!record) continue;
    values[id] = {
      ...record,
      ageMs: recordAgeMs(record, now),
      sourceAgeMs: recordAgeMs(record, now),
      transportAgeMs: transportAgeMs(record, now),
      stale: transportAgeMs(record, now) > STALE_AFTER_MS,
    };
  }
  return {
    schema: state.schema,
    status: state.status,
    url: state.url,
    connectedAt: state.connectedAt,
    lastFrameAt: state.lastFrameAt,
    lastReceivedAt: state.lastReceivedAt,
    validCount: state.validCount,
    totalCount: state.totalCount,
    lastError: state.lastError,
    staleAfterMs: state.staleAfterMs,
    values,
    publishedAt: new Date(now).toISOString(),
  };
}

function publish() {
  const detail = snapshot();
  window.__BF_CORE_PSPACE_LIVE__ = {
    ...detail,
    snapshot,
    reconnect: connect,
  };
  document.documentElement.dataset.corePspaceStatus = detail.status;
  document.documentElement.dataset.corePspaceValidCount = String(detail.validCount);
  document.documentElement.dataset.corePspaceLastFrame = detail.lastFrameAt || "";
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail }));
}

function setStatus(status, error = "") {
  state.status = status;
  state.lastError = error ? String(error) : "";
  publish();
}

function websocketUrl() {
  const query = new URLSearchParams(window.location.search);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host =
    query.get("core_pspace_ws_host") ||
    query.get("billboard_ws_host") ||
    window.BF_CORE_PSPACE_WS_HOST ||
    window.location.hostname ||
    "10.30.220.12";
  const port =
    query.get("core_pspace_ws_port") ||
    query.get("billboard_ws_port") ||
    window.BF_CORE_PSPACE_WS_PORT ||
    "8770";
  return `${protocol}://${host}:${port}`;
}

function applyPayload(payload) {
  if (!payload || !["init", "tick"].includes(payload.type)) return;
  const values = payload.type === "init" ? payload.history : payload.values;
  if (!values || typeof values !== "object") return;
  const pointMeta = payload.point_meta || {};
  const receivedAt = Date.now();
  let touched = 0;

  for (const id of CORE_IDS) {
    if (!Object.prototype.hasOwnProperty.call(values, id)) continue;
    const value = payload.type === "init" ? latestHistoryValue(values, id) : finiteValue(values[id]);
    const meta = pointMeta[id] || {};
    const quality = meta.quality ?? "";
    const error = meta.error || "";
    state.values[id] = {
      id,
      value,
      timestamp: meta.timestamp || payload.timestamp || "",
      quality,
      error,
      receivedAt,
      valid: value !== null && !qualityIsBad(quality, error),
      source: "pspace_realtime_8770",
    };
    touched += 1;
  }

  if (!touched) return;
  state.status = "connected";
  state.lastError = "";
  state.lastFrameAt = payload.timestamp || new Date(receivedAt).toISOString();
  state.lastReceivedAt = receivedAt;
  state.validCount = CORE_IDS.filter((id) => state.values[id]?.valid).length;
  publish();
}

function connect() {
  if (
    socket &&
    (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
  ) {
    return;
  }
  window.clearTimeout(reconnectTimer);
  state.url = websocketUrl();
  setStatus("connecting");
  try {
    socket = new WebSocket(state.url);
  } catch (error) {
    socket = null;
    setStatus("error", error?.message || error);
    reconnectTimer = window.setTimeout(connect, RECONNECT_AFTER_MS);
    return;
  }

  socket.addEventListener("open", () => {
    state.connectedAt = new Date().toISOString();
    setStatus("connected");
  });
  socket.addEventListener("message", (event) => {
    try {
      applyPayload(JSON.parse(event.data));
    } catch (error) {
      setStatus("error", error?.message || error);
    }
  });
  socket.addEventListener("error", () => setStatus("error", "WebSocket error"));
  socket.addEventListener("close", () => {
    socket = null;
    setStatus("disconnected");
    reconnectTimer = window.setTimeout(connect, RECONNECT_AFTER_MS);
  });
}

window.__BF_CORE_PSPACE_LIVE__ = { ...snapshot(), snapshot, reconnect: connect };

const query = new URLSearchParams(window.location.search);
if (query.get("core_pspace_disabled") === "1") {
  setStatus("disabled", "core_pspace_disabled=1");
} else {
  connect();
}

if (!ageTimer) ageTimer = window.setInterval(publish, 1_000);
