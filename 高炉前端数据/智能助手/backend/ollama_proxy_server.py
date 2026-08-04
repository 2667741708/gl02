from __future__ import annotations

import asyncio
import copy
import json
import html
import hmac
import importlib.util
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from assistant_pg import db_connect as _assistant_pg_connect, ensure_column, raw_pg_connect as _assistant_raw_pg_connect
import diagnosis_review
from mcp_conversation_context import (
    context_with_tool_trace,
    enrich_routing_question,
    update_tool_context,
)
from mcp_tool_policy import ToolPolicyLimits, validate_tool_call

try:
    from bf_knowledge_rag import (
        evidence_pack_text,
        initialize_knowledge_runtime,
        pgvector_status,
        rebuild_pgvector_embeddings,
        search_knowledge,
    )
except Exception as exc:  # noqa: BLE001
    _RAG_IMPORT_ERROR: Exception | None = exc

    def search_knowledge(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"enabled": False, "evidence": [], "message": f"知识库检索模块不可用：{_RAG_IMPORT_ERROR}"}

    def evidence_pack_text(pack: dict[str, Any]) -> str:
        return str(pack.get("message") or "知识库检索模块不可用")

    def pgvector_status() -> dict[str, Any]:
        return {"ok": False, "enabled": False, "message": f"知识库检索模块不可用：{_RAG_IMPORT_ERROR}"}

    def rebuild_pgvector_embeddings(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "updated": 0, "message": f"知识库检索模块不可用：{_RAG_IMPORT_ERROR}"}

    def initialize_knowledge_runtime() -> dict[str, Any]:
        return {"ok": False, "message": f"知识库检索模块不可用：{_RAG_IMPORT_ERROR}"}
else:
    _RAG_IMPORT_ERROR = None


HOST = os.environ.get("BF_PROXY_HOST", "0.0.0.0")
PORT = int(os.environ.get("BF_PROXY_PORT", "8092"))
ASSISTANT_BACKEND_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = ASSISTANT_BACKEND_DIR.parent
BASE_DIR = Path(os.environ.get("BF_FRONTEND_DIR", str(ASSISTANT_DIR.parent))).resolve()
INDEX_FILE = os.environ.get("BF_INDEX_FILE", "frontend_dashboard_v3.server.html")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://10.30.220.12:11434").rstrip("/")
PUBLIC_MODEL_NAME = os.environ.get("BF_PUBLIC_MODEL_NAME", "高炉大模型服务")
# Optional pin only.  When it is absent, resolve the model from the configured
# Ollama endpoint instead of silently falling back to a particular model.
DEFAULT_MODEL = os.environ.get("BF_LLM_MODEL", "").strip()
ALLOWED_LOADED_MODELS = tuple(
    name.strip()
    for name in os.environ.get(
        "BF_ALLOWED_LOADED_MODELS",
        "chiqiong-blast-furnace:latest,chiqiong-blast-furnace:latest_s",
    ).split(",")
    if name.strip()
)
QA_INACTIVITY_HOURS = float(os.environ.get("BF_QA_INACTIVITY_HOURS", "5"))
PROJECTS_DIR = Path(os.environ.get("BF_QA_PROJECTS_DIR", str(BASE_DIR / "data" / "projects")))
REPORTS_DIR = Path(os.environ.get("BF_REPORTS_DIR", str(BASE_DIR / "data" / "reports")))
LOCAL_TZ = ZoneInfo(os.environ.get("BF_LOCAL_TZ", "Asia/Shanghai"))
MAX_CONTEXT_ASSETS = int(os.environ.get("BF_QA_MAX_CONTEXT_ASSETS", "12"))
MAX_CONTEXT_ASSET_CHARS = int(os.environ.get("BF_QA_MAX_CONTEXT_ASSET_CHARS", "6000"))
MAX_CONTEXT_TOTAL_CHARS = int(os.environ.get("BF_QA_MAX_CONTEXT_TOTAL_CHARS", "18000"))
QA_PROMPT_MAX_SNAPSHOTS = int(os.environ.get("BF_QA_PROMPT_MAX_SNAPSHOTS", "10"))
QA_TREND_HOURS = float(os.environ.get("BF_QA_TREND_HOURS", "8"))
QA_TREND_DIAGNOSIS_LIMIT = int(os.environ.get("BF_QA_TREND_DIAGNOSIS_LIMIT", "96"))
QA_TREND_CADENCE_MINUTES = int(os.environ.get("BF_QA_TREND_CADENCE_MINUTES", "5"))
QA_TREND_WINDOW_MINUTES = int(os.environ.get("BF_QA_TREND_WINDOW_MINUTES", "60"))
QA_PROMPT_VALUE_KEYS = tuple(
    key.strip()
    for key in os.environ.get(
        "BF_QA_PROMPT_VALUE_KEYS",
        "DP_total,DP_upper,DP_lower,PI,P_blast,T_blast,Q_blast,P_top,T_top,"
        "PCI_rate,PCI_set,Q_O2,GasUtil,L,L_south,L_north",
    ).split(",")
    if key.strip()
)
MODEL_ALIASES = {
    "Blast Furnace Condition Diagnosis Agent": DEFAULT_MODEL,
    "chiqiong-blast-furnace:latest": DEFAULT_MODEL,
    "chiqiong-blast-furnace:latest_s": DEFAULT_MODEL,
    "chiqiong-blast-furnace:latest_M": DEFAULT_MODEL,
}
_SENSITIVE_MODEL_PREFIXES = ("qw" + "en", "Qw" + "en")
_MODEL_NAME_EXPOSURE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(x) for x in _SENSITIVE_MODEL_PREFIXES) + r")[A-Za-z0-9_.:/@+\-]*\b"
    r"|\b(?:27B|30B|32B|72B)\b"
)
PROJECT_ROOT = BASE_DIR.parent
TREND_BACKEND_PATH = Path(
    os.environ.get(
        "BF_TREND_BACKEND",
        str(PROJECT_ROOT / "趋势分析" / "trend_backend" / "pspace_history.py"),
    )
)
TREND_HISTORY_CACHE_SECONDS = float(os.environ.get("BF_TREND_HISTORY_CACHE_SECONDS", "30"))
_TREND_BACKEND_MODULE: Any | None = None
_TREND_HISTORY_CACHE: dict[str, Any] = {"key": "", "created": 0.0, "payload": None}
_QA_DB_BOOTSTRAP_LOCK = threading.Lock()
_QA_DB_BOOTSTRAPPED = False
_QA_PG_TREND_CACHE_LOCK = threading.Lock()
_QA_PG_TREND_CACHE: dict[str, Any] = {"key": None, "snapshots": None, "meta": None}
_QA_MCP_TOOL_CACHE_LOCK = threading.Lock()
_QA_MCP_TOOL_CACHE: dict[str, tuple[float, str]] = {}
QA_MCP_PREFETCH_ENABLED = os.environ.get("BF_QA_MCP_PREFETCH", "1").strip().lower() not in {"0", "false", "no"}
MCP_DATA_SERVER_PATH = Path(
    os.environ.get(
        "BF_QA_MCP_DATA_SERVER",
        str(ASSISTANT_DIR / "mcp" / "bf_data_mcp_server.py"),
    )
)
_MCP_DATA_MODULE: Any | None = None
QA_MCP_TOOLS_ENABLED = os.environ.get("BF_QA_MCP_TOOLS", "1").strip().lower() not in {"0", "false", "no"}
QA_MCP_TOOL_MODE = os.environ.get("BF_QA_MCP_TOOL_MODE", "auto").strip().lower()
QA_MCP_MAX_TOOL_ROUNDS = int(os.environ.get("BF_QA_MCP_MAX_TOOL_ROUNDS", "2"))
QA_MCP_MAX_TOOL_CALLS = int(os.environ.get("BF_QA_MCP_MAX_TOOL_CALLS", "4"))
QA_MCP_MAX_ARGUMENT_CHARS = int(os.environ.get("BF_QA_MCP_MAX_ARGUMENT_CHARS", "12000"))
QA_MCP_MAX_ARRAY_ITEMS = int(os.environ.get("BF_QA_MCP_MAX_ARRAY_ITEMS", "80"))
QA_MCP_MAX_RESULT_CHARS = int(os.environ.get("BF_QA_MCP_MAX_RESULT_CHARS", "20000"))
QA_MCP_PLANNER_TEMPERATURE = float(os.environ.get("BF_QA_MCP_PLANNER_TEMPERATURE", "0"))
QA_MCP_PLANNER_MAX_TOKENS = int(os.environ.get("BF_QA_MCP_PLANNER_MAX_TOKENS", "360"))
QA_MCP_PLANNER_CONTEXT_MESSAGES = int(os.environ.get("BF_QA_MCP_PLANNER_CONTEXT_MESSAGES", "6"))
QA_MCP_PLANNER_MESSAGE_CHARS = int(os.environ.get("BF_QA_MCP_PLANNER_MESSAGE_CHARS", "1200"))
QA_MCP_TOOL_CACHE_TTL_SECONDS = float(os.environ.get("BF_QA_MCP_TOOL_CACHE_TTL_SECONDS", "30"))
QA_MCP_TOOL_TIMEOUT_SECONDS = float(os.environ.get("BF_QA_MCP_TOOL_TIMEOUT_SECONDS", "45"))
QA_MCP_EXECUTION_BUDGET_SECONDS = float(os.environ.get("BF_QA_MCP_EXECUTION_BUDGET_SECONDS", "45"))
QA_MCP_PYTHON = os.environ.get("BF_MCP_PYTHON") or sys.executable or "python"
QA_KNOWLEDGE_ENABLED = os.environ.get("BF_QA_KNOWLEDGE_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
QA_KNOWLEDGE_INTENT_GATE = os.environ.get("BF_QA_KNOWLEDGE_INTENT_GATE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
QA_KNOWLEDGE_TOP_K = int(os.environ.get("BF_QA_KNOWLEDGE_TOP_K", "6"))
QA_KNOWLEDGE_DB_PATH = Path(os.environ.get("BF_QA_KNOWLEDGE_DB", "__postgresql_bf_assistant_rag__"))
QA_KNOWLEDGE_SEARCH_MODE = os.environ.get("BF_QA_KNOWLEDGE_SEARCH_MODE", "hybrid").strip().lower()
QA_MCP_BRIDGE_SYSTEM_PROMPT = (
    "你可以使用冀南钢铁 GL02 高炉数据库查询能力。"
    "你要结合当前问题与最近对话自主决定是否调用工具，并可以在限定轮数内按“查目录→查数据→做计算/绘图→总结”的顺序连续调用。"
    "追问省略了变量或时间范围时，优先继承最近对话中已经明确的对象；仍有多个可能对象时先查目录，不能唯一确定时再向用户追问。"
    "跨传感器、炉次、铁水/炉渣化验、进料成分、报表、历史问答、计算或图表能力的对象发现，优先调用search_business_objects；"
    "仅在已确认是GL02传感器且需要更细点位匹配时调用find_gl02_variables。"
    "涉及实时值、历史值、统计值、变量点位、报表事实、历史问答、趋势图、曲线图、多个变量对比图时，必须先查询或生成，不得编造。"
    "默认高炉范围是 \\冀南钢铁\\SIO\\GL02，不得混用 \\冀南二期\\EQ\\SI0\\GL02。"
    "当用户要求时间走势、曲线、趋势图时调用 plot_gl02_trends；未指定样式时使用 chart_type=auto，"
    "不同单位会自动双轴或分面，只有用户强调形态比较/归一化时才使用 scale=minmax 或 zscore。"
    "当用户要求关系图、相关性、散点图、相关矩阵、分布图、直方图或箱线图时调用 plot_gl02_analysis，"
    "分别选择 correlation_scatter、correlation_heatmap、distribution 或 boxplot。"
    "当用户要求一个或多个任意已配置传感器的当前值、历史数据或统计摘要时调用 query_gl02_sensors，"
    "不确定变量时先调用 find_gl02_variables；variables 必须使用变量目录解析出的标准变量，不得猜测名称；多点查询允许部分点无数据并逐项说明。"
    "当用户要求炉身、炉腹、炉缸或炉体温度各层各方位的大矩阵，并要求每格显示当前值和最近趋势时，"
    "调用 plot_gl02_body_temperature_matrix；默认使用 7-16 层、A-F 方位，明确要求 A-H 时扩展到 H。"
    "工具调用会经过服务端白名单和 JSON Schema 校验；收到 TOOL_POLICY_REJECTED 时应修正工具名或参数，不得绕过校验。"
    "不得生成 SQL、数据库连接参数或生产写操作。"
    "如果查询返回无数据或变量缺失，必须明确说明。最终回答要引用查询结果中的变量、时间窗、数值、图片路径或报表路径。"
)
QA_SYSTEM_PROMPT_TEMPLATE = """
你的名字叫“炽穹·高炉炼铁大模型”，你是高炉智能问答与工艺解释助手，面向高炉现场操作人员回答问题。

你的职责：
1. 不自行重新判定炉况，只解释后台已给出的炉况结论；
2. 不自行编造现场数据；
3. 只基于当前炉况数据、参数优化建议、近期对话和必要的高炉工艺常识进行解释；
4. 将后台诊断结论和优化建议解释成现场人员容易理解、可核查、可追溯的语言。

后台已提供最新炉况状态、8小时生产5分钟诊断时间线摘要与参数优化结果。
使用原则：
1. 判断“当前炉况”时，以最新炉况状态为主；
2. 判断8小时演化、连续性和诊断分布时，只把生产5分钟诊断时间线作为趋势依据；
3. 若结果显示状态连续增强，应说明“不是单次波动，而是连续趋势”；
4. 若结果不一致，应说明当前判断存在不确定性，并提示继续观察；
5. 若用户询问某个具体数值，而上下文未提供，必须回答“当前炉况上下文未提供该项数值”，不得猜测。
6. 若上下文只给出指标数值但未显式给出单位，不得自行补写 Pa、kPa、℃、m3/min、kg/t 等单位；可写“数值为...”并保留指标中文名。

回答边界：
1. 不得向用户说明上下文是内部注入的；
2. 不得输出 JSON 原文、字段名堆砌或程序内部变量名；
3. 不得提及或复述内部实现名称、提示组织方式、检索模块、外部查询桥接、评分模块、特征计算、算法公式、基线表、原始评分字段等实现细节；
4. 即使用户问题中直接写出了内部名词，也不得照抄、枚举或解释这些名词；只说“这部分属于后台处理细节，不直接展开”，然后转向现场可核查指标；
5. 所有调控建议必须体现“小幅、分步、观察反馈”的原则；
6. 涉及现场执行的动作，必须提醒“需结合现场制度、值班长/高炉长确认后执行”；
7. 若数据过期、缺失或证据不足，应明确提示可信度下降；
8. 若后台诊断结论与一般工艺常识存在冲突，优先以当前炉况结论和优化建议为准，并说明需要现场复核；
9. 若上下文中有知识证据，回答必须优先依据证据；若证据与用户问题不完全匹配，需要说明适用边界；
10. 若上下文中有数据库查询结果，回答必须优先使用其中的变量、时间窗、统计值、首尾值和数据源。
11. 用户追问“你为什么这么判断、依据是什么、原理是什么”时，只能从现场可理解的角度说明“哪些炉况、哪些指标、哪些趋势支撑该判断”，不得解释内部权重、评分公式、特征计算或工程实现。

当用户问“为什么这么优化”时，应按以下逻辑回答：
1. 当前主诊断和次诊断是什么；
2. 支撑该诊断的关键证据是什么；
3. 当前优化目标是什么；
4. 为什么这些建议动作与当前炉况匹配；
5. 有哪些风险和需要观察的指标。

当用户问“你确定吗”“可靠吗”时，不要简单回答“确定”。应说明：
1. 当前判断把握或连续性依据；
2. 最近结果是否支持该判断；
3. 哪些证据最强；
4. 哪些因素仍不确定；
5. 后续应观察哪些指标验证。

回答风格：
1. 直接回答问题；
2. 面向现场，语言简洁、稳健、专业；
3. 不做长篇理论展开；
4. 输出控制在420字以内；
5. 结尾给出下一步重点观察指标。

【固定工艺规则】
{project_rules}

下面是后台动态提供的炉况资料、主动选择资料、数据库查询结果和知识证据。回答时只吸收其中的结论、数值和现场可理解证据，不要暴露资料来源形式或内部实现：
【炉况上下文】
{hidden}

{selected_project_context}

【数据库查询结果】
{mcp_context}

【知识证据】
{knowledge_context}
""".strip()


QA_PROJECT_RULES_BLOCK = """
基本工艺解释：
1. 压差持续升高通常说明料柱阻力增加，透气性存在变差风险。
2. 透气性指数下降通常说明炉内煤气通过料柱能力变差。
3. 边缘顶温持续高于中心顶温，通常提示边缘煤气流发展。
4. 中心顶温持续高于边缘顶温，通常提示中心煤气流发展。
5. 理论燃烧温度、热风温度、富氧率、喷煤量共同反映下部热状态。
6. 铁水温度和 Si 属于滞后反馈，不能单独作为即时调控依据。

调控原则：
1. 所有调控建议必须小幅、分步、观察反馈。
2. 当透气性变差或压差持续升高时，不宜盲目继续加风或提高喷煤。
3. 当气流分布异常时，应结合顶温分布、压差、透气性指数和煤气利用率综合判断。
4. 任何现场执行动作都必须结合现场制度，并经值班长或高炉长确认。
""".strip()
QA_MCP_INTENT_KEYWORDS = (
    "查询",
    "查一下",
    "看一下",
    "看看",
    "告诉我",
    "给我说",
    "说一下",
    "数据库",
    "实时",
    "最新",
    "历史",
    "趋势",
    "走势",
    "变化",
    "波动",
    "稳不稳",
    "正不正常",
    "正常吗",
    "怎么样",
    "咋样",
    "高不高",
    "低不低",
    "平均",
    "最大",
    "最小",
    "多少",
    "是多少",
    "变量",
    "点位",
    "报表",
    "日报",
    "周报",
    "月报",
    "之前",
    "问过",
    "画图",
    "画一下",
    "画个",
    "画出",
    "图",
    "曲线",
    "趋势图",
    "对比图",
    "对比",
)


def load_trend_backend():
    global _TREND_BACKEND_MODULE
    if _TREND_BACKEND_MODULE is not None:
        return _TREND_BACKEND_MODULE
    if not TREND_BACKEND_PATH.exists():
        raise FileNotFoundError(f"trend backend not found: {TREND_BACKEND_PATH}")
    spec = importlib.util.spec_from_file_location("bf_trend_pspace_history", TREND_BACKEND_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load trend backend: {TREND_BACKEND_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _TREND_BACKEND_MODULE = module
    return module


def load_mcp_data_module():
    global _MCP_DATA_MODULE
    if _MCP_DATA_MODULE is not None:
        return _MCP_DATA_MODULE
    if not MCP_DATA_SERVER_PATH.exists():
        raise FileNotFoundError(f"数据库查询服务不存在: {MCP_DATA_SERVER_PATH}")
    spec = importlib.util.spec_from_file_location("bf_data_mcp_server_for_qa", MCP_DATA_SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载数据库查询服务: {MCP_DATA_SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MCP_DATA_MODULE = module
    return module


def trend_history_injection() -> str:
    return r"""
<script>
(function(){
  if (window.__BF_TREND_HISTORY_PATCHED__) return;
  window.__BF_TREND_HISTORY_PATCHED__ = true;
  const NativeWebSocket = window.WebSocket;
  if (!NativeWebSocket) return;
  function mergedInitMessage(msg, trend) {
    const history = Object.assign({}, msg.history || {}, trend.history || {});
    const next = Object.assign({}, msg, {
      history,
      data_quality: Object.assign({}, msg.data_quality || {}, {
        trend_history: trend.data_quality || {},
        trend_source: trend.source,
        trend_server: trend.server,
        trend_interval_seconds: trend.interval_seconds,
        trend_aggregate: trend.aggregate
      })
    });
    if (history.timestamps && history.timestamps.length) {
      next.timestamp = history.timestamps[history.timestamps.length - 1];
    }
    return next;
  }
  function deliver(handler, ws, event) {
    if (typeof handler === "function") handler.call(ws, event);
  }
  function patchSocket(ws) {
    let userOnMessage = null;
    const nativeAdd = ws.addEventListener.bind(ws);
    const nativeRemove = ws.removeEventListener ? ws.removeEventListener.bind(ws) : null;
    const wrapped = new Map();
    Object.defineProperty(ws, "onmessage", {
      configurable: true,
      enumerable: true,
      get: function(){ return userOnMessage; },
      set: function(handler){ userOnMessage = typeof handler === "function" ? handler : null; }
    });
    function wrap(handler) {
      return function(event) {
        try {
          const msg = JSON.parse(event.data);
          if (msg && msg.type === "init") {
            fetch("/api/trend/history?hours=8", {cache: "no-store"})
              .then(function(resp){ return resp.json(); })
              .then(function(trend){
                if (trend && trend.ok && trend.history) {
                  const patched = mergedInitMessage(msg, trend);
                  deliver(handler, ws, new MessageEvent("message", {data: JSON.stringify(patched)}));
                } else {
                  deliver(handler, ws, event);
                }
              })
              .catch(function(){ deliver(handler, ws, event); });
            return;
          }
        } catch (err) {}
        deliver(handler, ws, event);
      };
    }
    nativeAdd("message", function(event){ if (userOnMessage) wrap(userOnMessage)(event); });
    ws.addEventListener = function(type, handler, options) {
      if (type !== "message" || typeof handler !== "function") {
        return nativeAdd(type, handler, options);
      }
      const patched = wrap(handler);
      wrapped.set(handler, patched);
      return nativeAdd(type, patched, options);
    };
    if (nativeRemove) {
      ws.removeEventListener = function(type, handler, options) {
        return nativeRemove(type, wrapped.get(handler) || handler, options);
      };
    }
    return ws;
  }
  window.WebSocket = function(url, protocols) {
    const ws = protocols === undefined ? new NativeWebSocket(url) : new NativeWebSocket(url, protocols);
    return patchSocket(ws);
  };
  window.WebSocket.prototype = NativeWebSocket.prototype;
  Object.keys(NativeWebSocket).forEach(function(key){ window.WebSocket[key] = NativeWebSocket[key]; });
})();
</script>
"""


def automation_monitor_injection() -> str:
    return r"""
<script>
(function(){
  if (window.__BF_AUTOMATION_MONITOR__) return;
  window.__BF_AUTOMATION_MONITOR__ = true;
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function(ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch];
    });
  }
  function md(value) {
    var text = esc(value || "").replace(/\r\n/g, "\n").trim();
    if (!text) return "";
    return text.split(/\n{2,}/).map(function(block) {
      var lines = block.split("\n").map(function(x){ return x.trim(); }).filter(Boolean);
      if (!lines.length) return "";
      if (/^###\s+/.test(lines[0])) return "<h4>" + lines[0].replace(/^###\s+/, "") + "</h4>" + (lines.slice(1).length ? "<p>" + lines.slice(1).join("<br>") + "</p>" : "");
      if (/^##\s+/.test(lines[0])) return "<h4>" + lines[0].replace(/^##\s+/, "") + "</h4>" + (lines.slice(1).length ? "<p>" + lines.slice(1).join("<br>") + "</p>" : "");
      if (lines.every(function(x){ return /^[-*•]\s+/.test(x); })) return "<ul>" + lines.map(function(x){ return "<li>" + x.replace(/^[-*•]\s+/, "") + "</li>"; }).join("") + "</ul>";
      return "<p>" + lines.join("<br>") + "</p>";
    }).join("").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  }
  function fmtTs(value) {
    if (!value) return "-";
    return String(value).replace("T", " ").replace(/\.\d+$/, "");
  }
  function mount() {
    if (document.getElementById("bf-auto-monitor")) return;
    var box = document.createElement("section");
    box.id = "bf-auto-monitor";
    box.innerHTML = '<div class="bf-auto-head"><b>自动诊断值守</b><div><span id="bf-auto-status">连接中</span><button id="bf-auto-toggle" type="button" aria-label="展开自动诊断值守">+</button></div></div><div id="bf-auto-body" class="bf-auto-body">正在读取自动化事件...</div>';
    var style = document.createElement("style");
    style.textContent = [
      "#bf-auto-monitor{position:fixed;right:14px;top:96px;z-index:99999;width:min(360px,calc(100vw - 28px));max-width:calc(100vw - 28px);box-sizing:border-box;max-height:52vh;overflow:hidden;border:1px solid rgba(54,164,255,.72);border-radius:6px;background:rgba(3,16,33,.94);box-shadow:0 10px 24px rgba(0,0,0,.28),0 0 14px rgba(0,120,255,.22);color:#dcecff;font-family:SimSun,'宋体',serif}",
      ".bf-auto-head{height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 10px;background:rgba(7,49,88,.96);border-bottom:1px solid rgba(54,164,255,.55);cursor:move;user-select:none}",
      ".bf-auto-head b{font-size:15px;color:#fff}.bf-auto-head span{font-size:12px;color:#8ee6a3}.bf-auto-head button{margin-left:8px;width:22px;height:22px;border:1px solid rgba(130,205,255,.5);background:rgba(5,28,56,.9);color:#dcecff;border-radius:4px;cursor:pointer}",
      ".bf-auto-body{padding:9px;display:grid;gap:7px;font-size:12px;line-height:1.35;max-height:calc(52vh - 34px);overflow:auto;box-sizing:border-box}.bf-auto-row{display:grid;grid-template-columns:86px minmax(0,1fr);gap:8px;min-width:0}.bf-auto-row b{color:#91c7ff}.bf-auto-row span{min-width:0;overflow-wrap:anywhere;word-break:break-word}.bf-auto-card{min-width:0;box-sizing:border-box;border:1px solid rgba(54,164,255,.32);background:rgba(7,34,65,.72);padding:7px;border-radius:4px}.bf-auto-list{display:grid;gap:6px;min-width:0}.bf-auto-item{min-width:0;border:1px solid rgba(54,164,255,.24);background:rgba(4,23,45,.72);padding:6px;border-radius:4px;cursor:pointer}.bf-auto-item:hover{border-color:rgba(80,185,255,.72)}.bf-auto-title{display:flex;justify-content:space-between;gap:8px;color:#fff;min-width:0}.bf-auto-muted{color:#96afc8}.bf-auto-summary{margin-top:4px;color:#dcecff;max-height:44px;overflow:hidden}.bf-auto-warn{color:#ffc45a}.bf-auto-bad{color:#ff6678}.bf-auto-ok{color:#7ff0a1}.bf-auto-collapsed .bf-auto-body{display:none}",
      "#bf-auto-monitor.bf-auto-collapsed{top:52px;right:70px;width:auto;max-width:calc(100vw - 96px);max-height:30px;border-radius:999px;border-color:rgba(78,171,232,.5);background:rgba(3,18,36,.76);box-shadow:0 0 8px rgba(0,120,255,.18)}#bf-auto-monitor.bf-auto-collapsed .bf-auto-head{height:30px;gap:10px;padding:0 8px 0 12px;border-bottom:0;border-radius:999px;background:rgba(6,34,65,.82);cursor:pointer}#bf-auto-monitor.bf-auto-collapsed .bf-auto-head b{font-size:13px;white-space:nowrap}#bf-auto-monitor.bf-auto-collapsed .bf-auto-head span{display:inline-block;max-width:76px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle}#bf-auto-monitor.bf-auto-collapsed .bf-auto-head button{width:20px;height:20px;border-radius:50%;line-height:18px}",
      "#bf-sw-chat{position:fixed;right:14px;bottom:74px;z-index:100000;width:420px;max-height:64vh;display:none;border:1px solid rgba(54,164,255,.82);border-radius:6px;background:rgba(3,16,33,.96);box-shadow:0 0 22px rgba(0,120,255,.32);color:#dcecff;font-family:SimSun,'宋体',serif}",
      "#bf-sw-chat.open{display:grid;grid-template-rows:34px minmax(130px,1fr) auto}.bf-sw-chat-head{display:flex;align-items:center;justify-content:space-between;padding:0 10px;background:rgba(7,49,88,.96);border-bottom:1px solid rgba(54,164,255,.55)}.bf-sw-chat-head b{font-size:14px}.bf-sw-chat-head button{width:24px;height:24px;border:1px solid rgba(130,205,255,.5);background:rgba(5,28,56,.9);color:#dcecff;border-radius:4px;cursor:pointer}",
      ".bf-sw-chat-body{padding:9px;display:grid;gap:8px;overflow:auto;max-height:42vh}.bf-sw-msg{border:1px solid rgba(54,164,255,.22);background:rgba(4,23,45,.72);padding:7px;border-radius:4px}.bf-sw-msg.user{border-color:rgba(127,240,161,.35);white-space:pre-wrap}.bf-sw-msg.assistant{border-color:rgba(145,199,255,.35)}.bf-sw-msg.system{border-color:rgba(255,196,90,.38)}.bf-sw-meta{font-size:11px;color:#96afc8;margin-bottom:4px}.bf-sw-md h4{margin:6px 0 5px;color:#fff;font-size:15px}.bf-sw-md p{margin:4px 0;line-height:1.45}.bf-sw-md ul{margin:4px 0 4px 18px;padding:0}.bf-sw-md strong{color:#fff}.bf-sw-lead-line{display:grid;grid-template-columns:74px 1fr;gap:8px;margin:3px 0;color:#dcecff}.bf-sw-lead-line b{color:#91c7ff}.bf-sw-judgement{margin-top:8px;padding-top:7px;border-top:1px solid rgba(54,164,255,.25)}.bf-sw-input{display:grid;grid-template-columns:1fr 68px;gap:8px;padding:9px;border-top:1px solid rgba(54,164,255,.3)}.bf-sw-input textarea{min-height:58px;resize:vertical;background:rgba(2,12,26,.9);color:#dcecff;border:1px solid rgba(130,205,255,.35);border-radius:4px;padding:7px}.bf-sw-input button{border:1px solid rgba(54,164,255,.72);background:rgba(16,86,150,.9);color:#fff;border-radius:4px;cursor:pointer}",
      "@media(max-width:1500px){#bf-auto-monitor{right:8px;top:96px;width:min(320px,calc(100vw - 16px));max-height:38vh}.bf-auto-body{max-height:calc(38vh - 34px)}#bf-auto-monitor.bf-auto-collapsed{top:52px;right:62px;width:auto;max-width:calc(100vw - 78px)}#bf-sw-chat{right:8px;width:min(380px,calc(100vw - 16px))}}",
      "@media(max-width:1280px){#bf-auto-monitor.bf-auto-collapsed{top:52px;right:52px;max-width:calc(100vw - 64px)}#bf-auto-monitor:not(.bf-auto-collapsed){right:8px;top:96px;width:min(320px,calc(100vw - 16px))}}@media(max-width:900px){#bf-auto-monitor{display:none}.bf-auto-row{grid-template-columns:72px 1fr}#bf-sw-chat{left:8px;right:8px;width:auto;bottom:8px}}"
    ].join("");
    document.head.appendChild(style);
    document.body.appendChild(box);
    var toggle = document.getElementById("bf-auto-toggle");
    if (toggle) toggle.addEventListener("click", function(ev) {
      ev.stopPropagation();
      box.classList.toggle("bf-auto-collapsed");
      var collapsed = box.classList.contains("bf-auto-collapsed");
      toggle.textContent = collapsed ? "+" : "-";
      toggle.setAttribute("aria-label", collapsed ? "展开自动诊断值守" : "收起自动诊断值守");
    });
    box.classList.add("bf-auto-collapsed");
    var head = box.querySelector(".bf-auto-head");
    var dragging = false, startX = 0, startY = 0, startLeft = 0, startTop = 0;
    if (head) head.addEventListener("mousedown", function(ev) {
      if (ev.target && ev.target.tagName === "BUTTON") return;
      dragging = true;
      startX = ev.clientX; startY = ev.clientY;
      var rect = box.getBoundingClientRect();
      startLeft = rect.left; startTop = rect.top;
      box.style.right = "auto";
      ev.preventDefault();
    });
    window.addEventListener("mousemove", function(ev) {
      if (!dragging) return;
      box.style.left = Math.max(0, Math.min(window.innerWidth - box.offsetWidth, startLeft + ev.clientX - startX)) + "px";
      box.style.top = Math.max(0, Math.min(window.innerHeight - 40, startTop + ev.clientY - startY)) + "px";
    });
    window.addEventListener("mouseup", function(){ dragging = false; });
    var chat = document.createElement("section");
    chat.id = "bf-sw-chat";
    chat.innerHTML = '<div class="bf-sw-chat-head"><b id="bf-sw-title">短时炉况会话</b><button id="bf-sw-close" type="button">x</button></div><div id="bf-sw-body" class="bf-sw-chat-body"></div><div class="bf-sw-input"><textarea id="bf-sw-text" placeholder="输入高炉长补充或追问"></textarea><button id="bf-sw-send" type="button">发送</button></div>';
    document.body.appendChild(chat);
    document.getElementById("bf-sw-close").addEventListener("click", function(){ chat.classList.remove("open"); });
    document.getElementById("bf-sw-send").addEventListener("click", function(){ sendShortWindowMessage(); });
  }
  var activeQueueId = "";
  var activeConversationId = "";
  function shortWindowLead(q, summary) {
    q = q || {};
    summary = summary || {};
    var text = summary.summary_text || summary.llm_summary || q.llm_summary || "该短时队列尚未生成大模型总判断。";
    return [
      '<div class="bf-sw-lead-line"><b>队列窗口</b><span>' + esc(fmtTs(q.queue_start_ts)) + " - " + esc(fmtTs(q.queue_end_ts)) + '</span></div>',
      '<div class="bf-sw-lead-line"><b>状态</b><span>' + esc(q.status || "-") + '</span></div>',
      '<div class="bf-sw-lead-line"><b>诊断数</b><span>' + esc(q.diagnosis_count == null ? "-" : q.diagnosis_count) + '</span></div>',
      '<div class="bf-sw-judgement"><div class="bf-sw-meta">总判断</div><div class="bf-sw-md">' + md(text) + '</div></div>'
    ].join("");
  }
  function renderChatMessages(items, lead) {
    var body = document.getElementById("bf-sw-body");
    if (!body) return;
    var html = lead ? '<div class="bf-sw-msg system"><div class="bf-sw-meta">队列摘要</div>' + lead + '</div>' : "";
    html += (items || []).map(function(m) {
      var role = m.role || "";
      var content = role === "assistant" || role === "system" ? '<div class="bf-sw-md">' + md(m.content || "") + '</div>' : esc(m.content || "");
      return '<div class="bf-sw-msg ' + esc(role) + '"><div class="bf-sw-meta">' + esc(role || "-") + ' / ' + fmtTs(m.created_at) + '</div>' + content + '</div>';
    }).join("");
    body.innerHTML = html || '<div class="bf-sw-msg system">暂无会话消息，可以直接追问。</div>';
    body.scrollTop = body.scrollHeight;
  }
  function openShortWindowChat(queueId, conversationId) {
    if (!queueId && !conversationId) return;
    activeQueueId = queueId || "";
    activeConversationId = conversationId || (queueId ? "swc_" + queueId : "");
    var chat = document.getElementById("bf-sw-chat");
    var title = document.getElementById("bf-sw-title");
    if (title) title.textContent = "短时炉况会话 " + (queueId || conversationId);
    if (chat) chat.classList.add("open");
    renderChatMessages([], "正在读取队列与历史会话...");
    var convUrl = conversationId ? "/api/short-window/conversation?conversation_id=" + encodeURIComponent(conversationId) : "/api/short-window/conversation?queue_id=" + encodeURIComponent(queueId);
    var queueUrl = queueId ? "/api/short-window/queue?queue_id=" + encodeURIComponent(queueId) : "";
    Promise.all([
      queueUrl ? fetch(queueUrl, {cache:"no-store"}).then(function(r){ return r.json(); }).catch(function(){ return {}; }) : Promise.resolve({}),
      fetch(convUrl, {cache:"no-store"}).then(function(r){ return r.json(); }).catch(function(){ return {}; })
    ]).then(function(parts) {
      var conv = parts[1] || {};
      var q = (parts[0] && parts[0].queue) || conv.queue || {};
      if (conv.ok && conv.conversation) {
        activeConversationId = conv.conversation.conversation_id || activeConversationId;
        activeQueueId = conv.conversation.queue_id || activeQueueId || queueId;
      }
      var lead = shortWindowLead(q, conv.summary || (parts[0] && parts[0].summary) || {});
      renderChatMessages(conv.messages || [], lead);
    });
  }
  function sendShortWindowMessage() {
    var input = document.getElementById("bf-sw-text");
    var text = input ? input.value.trim() : "";
    if (!text || !activeQueueId) return;
    if (input) input.value = "";
    var body = document.getElementById("bf-sw-body");
    if (body) body.insertAdjacentHTML("beforeend", '<div class="bf-sw-msg user"><div class="bf-sw-meta">user / 发送中</div>' + esc(text) + '</div>');
    fetch("/api/short-window/chat", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({queue_id: activeQueueId, conversation_id: activeConversationId, message: text})
    }).then(function(resp){ return resp.json(); }).then(function(payload) {
      if (!payload.ok) throw new Error(payload.error || "短时会话失败");
      activeConversationId = payload.conversation_id || activeConversationId;
      renderChatMessages(payload.messages || [], '<div class="bf-sw-lead-line"><b>本轮补充</b><span>新增炉况 ' + esc(((payload.hidden_context || {}).delta_diagnoses || []).length) + ' 条；队列诊断 ' + esc(((payload.hidden_context || {}).queue_diagnoses || []).length) + ' 条</span></div>');
      setTimeout(refresh, 300);
    }).catch(function(err) {
      if (body) body.insertAdjacentHTML("beforeend", '<div class="bf-sw-msg system bf-auto-bad">' + esc(String(err)) + '</div>');
    });
  }
  function render(payload) {
    var status = document.getElementById("bf-auto-status");
    var body = document.getElementById("bf-auto-body");
    if (!body) return;
    if (!payload || !payload.ok) {
      if (status) status.textContent = "异常";
      body.innerHTML = '<div class="bf-auto-card bf-auto-bad">' + esc(payload && payload.error || "自动诊断状态不可用") + '</div>';
      return;
    }
    var latest = payload.latest || {};
    var quality = payload.latest_quality || {};
    var run = (payload.runs || [])[0] || {};
    var summaries = payload.short_window_summaries || [];
    var conversations = payload.short_window_conversations || [];
    var lag = latest.source_lag_seconds == null ? quality.source_lag_seconds : latest.source_lag_seconds;
    var lagCls = lag > 600 ? "bf-auto-bad" : (lag > 300 ? "bf-auto-warn" : "bf-auto-ok");
    if (status) status.textContent = payload.database_ok ? "运行中" : "数据库异常";
    var summaryHtml = summaries.length ? summaries.map(function(item) {
      return '<div class="bf-auto-item" data-queue-id="' + esc(item.queue_id || "") + '">' +
        '<div class="bf-auto-title"><b>' + fmtTs(item.queue_end) + '</b><span>' + esc(item.queue_status || item.model_name || "-") + '</span></div>' +
        '<div class="bf-auto-muted">' + esc(item.word_path || item.docx_path || "暂无 Word 路径") + '</div>' +
        '<div class="bf-auto-summary">' + esc(item.summary_text || item.summary || "-") + '</div>' +
        '</div>';
    }).join("") : '<div class="bf-auto-muted">暂无短时综合判断</div>';
    var conversationHtml = conversations.length ? conversations.map(function(item) {
      return '<div class="bf-auto-item bf-auto-conv" data-conversation-id="' + esc(item.conversation_id || "") + '" data-queue-id="' + esc(item.queue_id || "") + '">' +
        '<div class="bf-auto-title"><b>' + fmtTs(item.queue_end || item.updated_at) + '</b><span>' + esc((item.message_count || 0) + " 条") + '</span></div>' +
        '<div class="bf-auto-muted">' + esc(item.conversation_id || "-") + '</div>' +
        '<div class="bf-auto-summary">' + esc(item.initial_summary || item.queue_status || "点击继续追问") + '</div>' +
        '</div>';
    }).join("") : '<div class="bf-auto-muted">暂无短时会话</div>';
    body.innerHTML = [
      '<div class="bf-auto-card">',
      '<div class="bf-auto-row"><b>最新诊断</b><span>' + fmtTs(latest.diagnosis_ts) + '</span></div>',
      '<div class="bf-auto-row"><b>炉况标签</b><span>' + esc(latest.main_label || "-") + ' / ' + esc(latest.main_score == null ? "-" : Number(latest.main_score).toFixed(2)) + '</span></div>',
      '<div class="bf-auto-row"><b>诊断窗口</b><span>' + fmtTs(latest.diagnosis_window_start) + ' - ' + fmtTs(latest.diagnosis_window_end) + '</span></div>',
      '<div class="bf-auto-row"><b>覆盖率</b><span>' + esc(latest.coverage_ratio == null ? "-" : (Number(latest.coverage_ratio) * 100).toFixed(1) + "%") + '</span></div>',
      '<div class="bf-auto-row"><b>源延迟</b><span class="' + lagCls + '">' + esc(lag == null ? "-" : lag + " 秒") + '</span></div>',
      '</div>',
      '<div class="bf-auto-card">',
      '<div class="bf-auto-row"><b>最近任务</b><span>' + esc(run.task_name || "-") + ' / ' + esc(run.status || "-") + '</span></div>',
      '<div class="bf-auto-row"><b>任务时间</b><span>' + fmtTs(run.started_at) + '</span></div>',
      '<div class="bf-auto-row"><b>写入行数</b><span>' + esc(run.rows_written == null ? "-" : run.rows_written) + '</span></div>',
      '</div>',
      '<div class="bf-auto-card">',
      '<div class="bf-auto-row"><b>质量状态</b><span>' + esc(quality.status || "-") + '</span></div>',
      '<div class="bf-auto-row"><b>缺变量数</b><span>' + esc((latest.missing_variables || []).length) + '</span></div>',
      '<div class="bf-auto-row"><b>数据源</b><span>' + esc((latest.source || {}).read_policy || (latest.source || {}).type || "-") + '</span></div>',
      '</div>',
      '<div class="bf-auto-card">',
      '<div class="bf-auto-row"><b>短时队列</b><span>' + esc(summaries.length ? summaries.length + " 条" : "-") + '</span></div>',
      '<div class="bf-auto-list">' + summaryHtml + '</div>',
      '</div>',
      '<div class="bf-auto-card">',
      '<div class="bf-auto-row"><b>近期会话</b><span>' + esc(conversations.length ? conversations.length + " 条" : "-") + '</span></div>',
      '<div class="bf-auto-list">' + conversationHtml + '</div>',
      '</div>'
    ].join("");
    Array.prototype.forEach.call(body.querySelectorAll(".bf-auto-item"), function(node) {
      node.addEventListener("click", function() {
        var queueId = node.getAttribute("data-queue-id") || "";
        var conversationId = node.getAttribute("data-conversation-id") || "";
        window.dispatchEvent(new CustomEvent("bf-short-window-select", {detail:{queue_id: queueId, conversation_id: conversationId}}));
      });
    });
  }
  function refresh() {
    Promise.all([
      fetch("/api/automation/status", {cache: "no-store"}).then(function(resp){ return resp.json(); }),
      fetch("/api/short-window/summaries?limit=8", {cache: "no-store"}).then(function(resp){ return resp.json(); }).catch(function(){ return {ok:false,items:[]}; }),
      fetch("/api/short-window/conversations?limit=8", {cache: "no-store"}).then(function(resp){ return resp.json(); }).catch(function(){ return {ok:false,items:[]}; })
    ])
      .then(function(parts){
        var payload = parts[0] || {};
        payload.short_window_summaries = (parts[1] && (parts[1].items || parts[1].summaries)) || [];
        payload.short_window_conversations = (parts[2] && (parts[2].items || parts[2].conversations)) || [];
        render(payload);
      })
      .catch(function(err){ render({ok:false,error:String(err)}); });
  }
  function start() {
    mount();
    window.addEventListener("bf-short-window-select", function(ev) {
      var detail = ev.detail || {};
      openShortWindowChat(detail.queue_id || "", detail.conversation_id || "");
    });
    refresh();
    setInterval(refresh, 5000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
</script>
"""


def inject_trend_history_loader(data: bytes, target: Path) -> bytes:
    if target.name != INDEX_FILE or target.suffix.lower() != ".html":
        return data
    text = data.decode("utf-8", errors="replace")
    injections = []
    if "__BF_TREND_HISTORY_PATCHED__" not in text:
        injections.append(trend_history_injection())
    if os.environ.get("BF_AUTOMATION_MONITOR", "1").strip().lower() not in {"0", "false", "no"} and "__BF_AUTOMATION_MONITOR__" not in text:
        injections.append(automation_monitor_injection())
    if diagnosis_review.review_enabled() and "__BF_DIAGNOSIS_REVIEW_LOCAL__" not in text:
        injections.append(
            '<link rel="stylesheet" href="/assets/bf-diagnosis-review-local.css">\n'
            '<link rel="stylesheet" href="/assets/bf-diagnosis-manual-score-local.css">\n'
            '<script defer src="/assets/bf-diagnosis-review-local.js"></script>\n'
            '<script defer src="/assets/bf-diagnosis-manual-score-local.js"></script>'
        )
    if not injections:
        return data
    injection = "\n".join(injections)
    if "</head>" in text:
        text = text.replace("</head>", injection + "\n</head>", 1)
    else:
        text = injection + "\n" + text
    return text.encode("utf-8")


def normalize_model(model: str | None) -> str:
    # Caller-supplied model names are display metadata only. Never forward
    # them to Ollama because a legacy alias can load a second large runner.
    return resolve_upstream_model()


def resolve_upstream_model() -> str:
    """Return one approved model that is already resident on Ollama 11434.

    The proxy deliberately does not fall back to /api/tags. Selecting an
    installed-but-unloaded tag and then calling /api/chat would load another
    runner, which is forbidden on the shared production GPU.
    """
    try:
        req = Request(f"{OLLAMA_BASE_URL}/api/ps", headers={"Accept": "application/json"})
        with urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"无法读取 Ollama 11434 已驻留模型：{exc}") from exc

    models = payload.get("models") if isinstance(payload, dict) else None
    loaded_names = [
        str(item.get("name") or item.get("model") or "").strip()
        for item in (models or [])
        if isinstance(item, dict)
    ]
    if DEFAULT_MODEL:
        if DEFAULT_MODEL not in ALLOWED_LOADED_MODELS:
            raise RuntimeError("配置的模型不在生产允许清单中")
        if DEFAULT_MODEL in loaded_names:
            return DEFAULT_MODEL
        raise RuntimeError("配置的生产模型当前未驻留在 Ollama 11434")
    for name in ALLOWED_LOADED_MODELS:
        if name in loaded_names:
            return name
    raise RuntimeError("Ollama 11434 当前没有已驻留的生产问答模型")


def sanitize_model_exposure(value: Any) -> str:
    """Remove upstream model implementation details before returning UI-visible errors."""
    text = str(value or "")
    text = _MODEL_NAME_EXPOSURE_RE.sub("业务模型", text)
    text = text.replace("Ollama", "高炉大模型服务")
    text = text.replace("ollama", "高炉大模型服务")
    return text


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


def parse_dotenv_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def auth_env_values() -> dict[str, str]:
    candidates: list[Path] = []
    explicit = os.environ.get("BF_AUTH_ENV_FILE", "").strip()
    if explicit:
        candidates.extend(Path(item.strip()) for item in re.split(r"[;,]", explicit) if item.strip())
    candidates.extend([
        PROJECT_ROOT / ".env",
        BASE_DIR / ".env",
        ASSISTANT_DIR / ".env",
        ASSISTANT_BACKEND_DIR / ".env",
        Path.cwd() / ".env",
    ])
    values: dict[str, str] = {}
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            path = candidate.expanduser().resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        values.update(parse_dotenv_file(path))
    values.update({k: v for k, v in os.environ.items() if isinstance(v, str)})
    return values


def safe_env_account_key(username: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", username.strip()).upper().strip("_")


def first_env_value(values: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def configured_login_accounts() -> dict[str, dict[str, str]]:
    values = auth_env_values()
    raw_users = values.get("BF_LOGIN_USERS") or values.get("LOGIN_USERS") or ""
    users = [item.strip() for item in raw_users.split(",") if item.strip()]
    users.extend([
        values.get("BF_LOGIN_USER", "").strip(),
        values.get("LOGIN_USERNAME", "").strip(),
        values.get("USER_NAME", "").strip(),
        "zhgl",
    ])
    accounts: dict[str, dict[str, str]] = {}
    for username in users:
        if not username or username in accounts:
            continue
        account_key = safe_env_account_key(username)
        password = first_env_value(values, [
            f"BF_LOGIN_{account_key}_PASSWORD",
            f"LOGIN_{account_key}_PASSWORD",
            f"{account_key}_LOGIN_PASSWORD",
            f"{account_key}_PASSWORD",
            "BF_LOGIN_PASSWORD",
            "LOGIN_PASSWORD",
            "USER_PASSWORD",
            "APP_LOGIN_PASSWORD",
            "APP_PASSWORD",
        ])
        if not password:
            continue
        role = first_env_value(values, [
            f"BF_LOGIN_{account_key}_ROLE",
            f"LOGIN_{account_key}_ROLE",
            f"{account_key}_ROLE",
            "BF_LOGIN_ROLE",
            "LOGIN_ROLE",
        ]) or "综合管理"
        accounts[username] = {"password": password, "role": role}
    return accounts


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def db_connect():
    global _QA_DB_BOOTSTRAPPED
    conn = _assistant_pg_connect()
    try:
        if not _QA_DB_BOOTSTRAPPED:
            with _QA_DB_BOOTSTRAP_LOCK:
                if not _QA_DB_BOOTSTRAPPED:
                    ensure_db(conn)
                    _QA_DB_BOOTSTRAPPED = True
        return conn
    except Exception:
        conn.close()
        raise


def ensure_db(conn) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    seed_report_templates(conn)
    conn.commit()


REPORT_TYPE_LABELS = {
    "hourly": "时报",
    "daily": "日报",
    "weekly": "周报",
    "monthly": "月报",
}


DEFAULT_REPORT_TEMPLATES = [
    {
        "code": "BF_HOURLY_BRIEF",
        "name": "炉况小时简报",
        "report_type": "hourly",
        "description": "按小时汇总高炉关键指标、异常信号和班中建议。",
        "sections": ["生产与数据概况", "关键炉况指标", "异常信号", "调控建议"],
    },
    {
        "code": "BF_DAILY_REPORT",
        "name": "高炉生产日报",
        "report_type": "daily",
        "description": "展示当日生产、炉况、异常和 AI 建议，适合班后复盘。",
        "sections": ["生产与数据概况", "关键炉况指标", "异常信号", "调控建议"],
    },
    {
        "code": "BF_WEEKLY_REPORT",
        "name": "高炉运行周报",
        "report_type": "weekly",
        "description": "按周组织炉况趋势、波动风险和调控回顾。",
        "sections": ["生产与数据概况", "关键炉况指标", "异常信号", "调控建议"],
    },
    {
        "code": "BF_MONTHLY_REPORT",
        "name": "设备异常月报",
        "report_type": "monthly",
        "description": "按月归纳高炉运行异常、设备信号和后续关注项。",
        "sections": ["生产与数据概况", "关键炉况指标", "异常信号", "调控建议"],
    },
]


def seed_report_templates(conn: Any) -> None:
    ts = iso_now()
    for item in DEFAULT_REPORT_TEMPLATES:
        schema = {
            "version": 1,
            "storage": "markdown+docx",
            "sections": [{"title": title} for title in item["sections"]],
        }
        conn.execute(
            """
            INSERT INTO report_template(code, name, report_type, description, template_schema, render_type, enabled, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, 'json_card', 1, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                report_type = excluded.report_type,
                description = excluded.description,
                template_schema = excluded.template_schema,
                enabled = 1,
                updated_at = excluded.updated_at
            """,
            (
                item["code"],
                item["name"],
                item["report_type"],
                item["description"],
                json.dumps(schema, ensure_ascii=False),
                ts,
                ts,
            ),
        )


def load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def title_from_question(question: str) -> str:
    cleaned = " ".join(str(question or "").strip().split())
    return (cleaned[:22] or "新对话")


def create_conversation(conn: Any, title: str = "新对话") -> dict[str, Any]:
    ts = iso_now()
    conv = {
        "id": f"qa_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
        "title": title,
        "created_at": ts,
        "updated_at": ts,
        "last_user_at": None,
        "status": "active",
        "is_pinned": False,
        "is_unread": False,
        "archived_at": None,
    }
    conn.execute(
        """
        INSERT INTO qa_conversations(id, title, created_at, updated_at, last_user_at)
        VALUES(:id, :title, :created_at, :updated_at, :last_user_at)
        """,
        conv,
    )
    conn.commit()
    return conv


def conversation_from_row(row: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_user_at": row["last_user_at"],
    }
    if "project_id" in row.keys():
        item["project_id"] = row["project_id"]
    if "status" in row.keys():
        item["status"] = row["status"]
    if "is_pinned" in row.keys():
        item["is_pinned"] = bool(row["is_pinned"])
    if "is_unread" in row.keys():
        item["is_unread"] = bool(row["is_unread"])
    if "archived_at" in row.keys():
        item["archived_at"] = row["archived_at"]
    return item


def list_conversations(
    conn: Any,
    limit: int = 40,
    project_id: int | None = None,
) -> list[dict[str, Any]]:
    where_parts = ["COALESCE(c.status, 'active') = 'active'"]
    args: list[Any] = []
    if project_id is not None:
        where_parts.append("c.project_id = ?")
        args.append(project_id)
    args.append(limit)
    where = "WHERE " + " AND ".join(where_parts)
    rows = conn.execute(
        f"""
        SELECT c.*,
               (SELECT COUNT(*) FROM qa_messages m WHERE m.conversation_id = c.id) AS message_count
        FROM qa_conversations c
        {where}
        ORDER BY COALESCE(c.is_pinned, 0) DESC, c.updated_at DESC
        LIMIT ?
        """,
        args,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = conversation_from_row(row)
        item["message_count"] = int(row["message_count"] or 0)
        out.append(item)
    return out


def load_messages(conn: Any, conversation_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, conversation_id, role, content, created_at, snapshot_id
        FROM qa_messages
        WHERE conversation_id = ?
        ORDER BY id ASC
        """,
        (conversation_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
            "snapshot_id": row["snapshot_id"],
        }
        for row in rows
    ]


def project_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "furnace_id": row["furnace_id"],
        "name": row["name"],
        "folder_path": row["folder_path"],
        "display_path": display_path(row["folder_path"]),
        "description": row["description"] or "",
        "status": row["status"],
        "is_pinned": bool(row["is_pinned"]) if "is_pinned" in row.keys() else False,
        "archived_at": row["archived_at"] if "archived_at" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_projects(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM qa_projects
        WHERE status = 'active'
        ORDER BY COALESCE(is_pinned, 0) DESC, updated_at DESC, id DESC
        """
    ).fetchall()
    return [project_from_row(row) for row in rows]


def safe_folder_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:80] or f"project_{int(time.time())}")


def allowed_roots() -> list[Path]:
    return [PROJECTS_DIR.resolve(), REPORTS_DIR.resolve()]


def is_allowed_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved == root or root in resolved.parents for root in allowed_roots())


def resolve_allowed_path(value: str | None, default_root: Path | None = None) -> Path:
    raw = str(value or "").strip()
    if not raw:
        if default_root is None:
            raise ValueError("missing folder path")
        target = default_root
    else:
        candidate = Path(raw)
        target = candidate if candidate.is_absolute() else (BASE_DIR / candidate)
    target = target.resolve()
    if not is_allowed_path(target):
        raise ValueError("folder is outside allowed project/report roots")
    return target


def display_path(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def static_url_for_path(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(BASE_DIR.resolve())
    except ValueError:
        return None
    return "/" + "/".join(rel.parts)


def create_project(
    conn: Any,
    name: str,
    folder_path: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    ts = iso_now()
    if folder_path:
        folder = resolve_allowed_path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
    else:
        base_name = safe_folder_name(name)
        folder = (PROJECTS_DIR / base_name).resolve()
        if folder.exists():
            folder = (PROJECTS_DIR / f"{base_name}_{int(time.time())}").resolve()
        folder.mkdir(parents=True, exist_ok=True)
    row = conn.execute(
        "SELECT * FROM qa_projects WHERE furnace_id = 'GL02' AND folder_path = ?",
        (str(folder),),
    ).fetchone()
    if row is not None:
        conn.execute("UPDATE qa_projects SET updated_at = ?, status = 'active' WHERE id = ?", (ts, row["id"]))
        conn.commit()
        return project_from_row(conn.execute("SELECT * FROM qa_projects WHERE id = ?", (row["id"],)).fetchone())

    cur = conn.execute(
        """
        INSERT INTO qa_projects(furnace_id, name, folder_path, description, created_by, status, created_at, updated_at)
        VALUES('GL02', ?, ?, ?, 'local', 'active', ?, ?)
        """,
        (safe_folder_name(name), str(folder), description, ts, ts),
    )
    conn.commit()
    return project_from_row(conn.execute("SELECT * FROM qa_projects WHERE id = ?", (cur.lastrowid,)).fetchone())


def infer_asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if path.is_dir():
        return "folder"
    if suffix == ".md":
        return "markdown_file"
    if suffix == ".docx":
        return "docx_file"
    if suffix == ".pdf":
        return "pdf_file"
    if suffix in {".xlsx", ".xls"}:
        return "spreadsheet_file"
    if suffix == ".csv":
        return "csv_file"
    if suffix == ".txt":
        return "txt_file"
    return "other"


def asset_from_file(path: Path, root: Path | None = None) -> dict[str, Any]:
    stat = path.stat()
    suffix = path.suffix.lower()
    return {
        "id": f"file:{display_path(str(path))}",
        "asset_type": infer_asset_type(path),
        "asset_ref_id": None,
        "file_path": str(path.resolve()),
        "display_path": display_path(str(path)),
        "display_name": path.name,
        "title": path.stem,
        "extension": suffix,
        "size": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "static_url": static_url_for_path(path),
        "root": display_path(str(root)) if root else "",
        **guess_report_hierarchy(path),
    }


def guess_report_hierarchy(path: Path) -> dict[str, Any]:
    text = "/".join(path.parts)
    parts = list(path.parts)
    year = None
    month = None
    day = None
    hour = None
    week = None
    period_kind = None

    for idx, part in enumerate(parts):
        clean = part.strip()
        if year is None and re.fullmatch(r"20\d{2}", clean):
            year = int(clean)
            if idx + 1 < len(parts):
                month_match = re.fullmatch(r"0?([1-9]|1[0-2])月?", parts[idx + 1].strip())
                if month_match:
                    month = int(month_match.group(1))
            continue
        if week is None:
            week_match = re.fullmatch(r"[Ww](\d{1,2})", clean)
            if week_match:
                week = int(week_match.group(1))
                if idx + 1 < len(parts):
                    day_match = re.fullmatch(r"0?([1-9]|[12]\d|3[01])日?", parts[idx + 1].strip())
                    if day_match:
                        day = f"{int(day_match.group(1)):02d}"
                if idx + 2 < len(parts):
                    hour_match = re.fullmatch(r"0?([0-9]|1\d|2[0-3])时?", parts[idx + 2].strip())
                    if hour_match:
                        hour = int(hour_match.group(1))

    m = re.search(r"(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})", text)
    if m and (year is None or month is None or day is None):
        year = year or int(m.group(1))
        month = month or int(m.group(2))
        day = day or f"{int(m.group(3)):02d}"
    ym = re.search(r"(20\d{2})[-_/](\d{1,2})", text)
    if ym and (year is None or month is None):
        year = year or int(ym.group(1))
        month = month or int(ym.group(2))
    hm = re.search(r"(\d{1,2})[-_:：](\d{1,2})", path.stem)
    if hm:
        hour = int(hm.group(1))
    lower = text.lower()
    if "hourly" in lower or "时报" in text:
        period_kind = "hourly"
    elif "daily" in lower or "日报" in text:
        period_kind = "daily"
    elif "weekly" in lower or "周报" in text:
        period_kind = "weekly"
    elif "monthly" in lower or "月报" in text:
        period_kind = "monthly"
    return {"year": year, "month": month, "week": week, "day": day, "hour": hour, "period_kind": period_kind}


def iter_files_limited(root: Path, max_files: int = 400) -> list[Path]:
    if not root.exists():
        return []
    allowed_suffixes = {".md", ".docx", ".txt", ".pdf", ".xlsx", ".xls", ".csv"}
    out: list[Path] = []
    for path in root.rglob("*"):
        if len(out) >= max_files:
            break
        if path.is_file() and path.suffix.lower() in allowed_suffixes and is_allowed_path(path):
            out.append(path)
    return sorted(out, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)


def scan_report_assets(conn: Any | None = None) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    if conn is not None:
        rows = conn.execute(
            """
            SELECT *
            FROM period_reports
            ORDER BY period_end DESC, id DESC
            LIMIT 200
            """
        ).fetchall()
        for row in rows:
            md_path = Path(row["markdown_path"]) if row["markdown_path"] else None
            docx_path = Path(row["docx_path"]) if row["docx_path"] else None
            assets.append(
                {
                    "id": f"period_report:{row['id']}",
                    "asset_type": "period_report",
                    "asset_ref_id": str(row["id"]),
                    "file_path": str(md_path or docx_path or ""),
                    "display_path": display_path(str(md_path or docx_path or "")),
                    "display_name": row["title"],
                    "title": row["title"],
                    "period_kind": row["period_kind"],
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "static_url": static_url_for_path(md_path) if md_path else None,
                    "docx_url": static_url_for_path(docx_path) if docx_path else None,
                }
            )
    seen = {item.get("display_path") for item in assets}
    for path in iter_files_limited(REPORTS_DIR):
        item = asset_from_file(path, REPORTS_DIR)
        if item["display_path"] not in seen:
            assets.append(item)
    return assets


def parse_report_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt


def iso_local(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ).replace(microsecond=0).isoformat()


def resolve_report_range(report_type: str, payload: dict[str, Any]) -> tuple[datetime, datetime]:
    report_type = normalize_report_type(report_type)
    start = parse_report_dt(payload.get("time_start") or payload.get("start"))
    end = parse_report_dt(payload.get("time_end") or payload.get("end"))
    anchor = parse_report_dt(payload.get("anchor") or payload.get("date") or payload.get("time") or payload.get("month"))
    if start and end:
        return start, end
    if anchor is None:
        anchor = datetime.now(LOCAL_TZ)
    anchor = anchor.astimezone(LOCAL_TZ)
    if report_type == "hourly":
        start = anchor.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1) - timedelta(seconds=1)
    elif report_type == "daily":
        start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
    elif report_type == "weekly":
        start = (anchor - timedelta(days=anchor.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7) - timedelta(seconds=1)
    else:
        start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        end = next_month - timedelta(seconds=1)
    return start, end


def normalize_report_type(value: str | None) -> str:
    value = str(value or "daily").strip().lower()
    if value in {"hour", "hourly", "小时", "时报"}:
        return "hourly"
    if value in {"week", "weekly", "周报"}:
        return "weekly"
    if value in {"month", "monthly", "月报"}:
        return "monthly"
    return "daily"


def report_template_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "report_type": row["report_type"],
        "description": row["description"] or "",
        "template_schema": load_json(row["template_schema"], {}),
        "render_type": row["render_type"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def report_instance_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "template_id": row["template_id"],
        "period_report_id": row["period_report_id"],
        "furnace_id": row["furnace_id"],
        "report_type": row["report_type"],
        "report_type_label": REPORT_TYPE_LABELS.get(row["report_type"], row["report_type"]),
        "time_start": row["time_start"],
        "time_end": row["time_end"],
        "title": row["title"],
        "summary": row["summary"] or "",
        "content_json": load_json(row["content_json"], {}),
        "content_markdown": row["content_markdown"],
        "preview_html": row["preview_html"] or "",
        "markdown_path": row["markdown_path"],
        "docx_path": row["docx_path"],
        "markdown_url": static_url_for_path(Path(row["markdown_path"])) if row["markdown_path"] else None,
        "docx_url": static_url_for_path(Path(row["docx_path"])) if row["docx_path"] else None,
        "display_path": display_path(row["markdown_path"] or row["docx_path"] or ""),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_report_templates(conn: Any, report_type: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = "WHERE enabled = 1"
    if report_type:
        where += " AND report_type = ?"
        params.append(normalize_report_type(report_type))
    rows = conn.execute(
        f"""
        SELECT *
        FROM report_template
        {where}
        ORDER BY CASE report_type WHEN 'hourly' THEN 1 WHEN 'daily' THEN 2 WHEN 'weekly' THEN 3 ELSE 4 END, id
        """,
        params,
    ).fetchall()
    return [report_template_from_row(row) for row in rows]


def list_report_instances(conn: Any, report_type: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = "WHERE 1 = 1"
    if report_type:
        where += " AND report_type = ?"
        params.append(normalize_report_type(report_type))
    rows = conn.execute(
        f"""
        SELECT *
        FROM report_instance
        {where}
        ORDER BY time_start DESC, id DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [report_instance_from_row(row) for row in rows]


def number_or_none(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def collect_report_snapshots(conn: Any, start: datetime, end: datetime, limit: int = 500) -> list[dict[str, Any]]:
    start_utc = start.astimezone(timezone.utc).isoformat()
    end_utc = end.astimezone(timezone.utc).isoformat()
    rows = conn.execute(
        """
        SELECT *
        FROM furnace_snapshots
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """,
        (start_utc, end_utc, limit),
    ).fetchall()
    if not rows:
        return []
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        snapshots.append(
            {
                "id": row["id"],
                "source_time": row["source_time"],
                "created_at": row["created_at"],
                "values": load_json(row["values_json"], {}),
                "diagnosis": load_json(row["diagnosis_json"], {}),
                "recommendation": load_json(row["recommendation_json"], {}),
                "data_quality": load_json(row["data_quality_json"], {}),
                "payload": load_json(row["payload_json"], {}),
            }
        )
    return snapshots


REPORT_METRICS = [
    ("DP_total", "全压差", "kPa"),
    ("DP_upper", "上部压差", "kPa"),
    ("DP_lower", "下部压差", "kPa"),
    ("PI", "透气性指数", ""),
    ("P_top", "炉顶压力", "kPa"),
    ("T_top", "综合顶温", "℃"),
    ("T_blast", "热风温度", "℃"),
    ("Q_blast", "冷风流量", "Nm³/min"),
    ("GasUtil", "煤气利用率", "%"),
    ("PCI_rate", "喷煤量", "t/h"),
]


def metric_summary(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label, unit in REPORT_METRICS:
        vals: list[float] = []
        for snap in snapshots:
            values = snap.get("values") or {}
            n = number_or_none(values.get(key))
            if n is not None:
                vals.append(n)
        if not vals:
            rows.append({"key": key, "label": label, "unit": unit, "latest": None, "avg": None, "min": None, "max": None})
            continue
        rows.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "latest": vals[-1],
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
        )
    return rows


def diagnosis_text(snapshot: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    if not snapshot:
        return "暂无诊断快照", [], []
    diagnosis = snapshot.get("diagnosis") or {}
    recommendation = snapshot.get("recommendation") or {}
    if isinstance(diagnosis, dict) and isinstance(diagnosis.get("diagnosis"), dict):
        recommendation = diagnosis.get("recommendation") or recommendation
        diagnosis = diagnosis.get("diagnosis") or {}
    label = "暂无明确诊断"
    if isinstance(diagnosis, dict):
        label = str(diagnosis.get("main_label") or diagnosis.get("label") or diagnosis.get("state") or label)
    def item_text(item: Any) -> str:
        if isinstance(item, dict):
            text = item.get("text") or item.get("message") or item.get("name") or item.get("id") or ""
            reason = item.get("reason")
            if reason and reason not in str(text):
                return f"{text}（{reason}）"
            return str(text)
        return str(item)

    evidence = diagnosis.get("evidence", []) if isinstance(diagnosis, dict) else []
    actions: list[str] = []
    if isinstance(recommendation, dict):
        for key in ("immediate_actions", "followup_actions", "forbidden_actions", "observe"):
            items = recommendation.get(key)
            if isinstance(items, list):
                actions.extend(item_text(x) for x in items[:4])
    return label, [item_text(x) for x in (evidence or [])[:6]], actions[:8]


def build_report_content(
    template: dict[str, Any],
    report_type: str,
    start: datetime,
    end: datetime,
    snapshots: list[dict[str, Any]],
    furnace_id: str = "GL02",
) -> dict[str, Any]:
    label = REPORT_TYPE_LABELS.get(report_type, report_type)
    start_text = start.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    end_text = end.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    if report_type == "hourly":
        title_date = start.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H时")
    elif report_type == "daily":
        title_date = start.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    elif report_type == "weekly":
        year, week, _ = start.astimezone(LOCAL_TZ).isocalendar()
        title_date = f"{year}年第{week:02d}周"
    else:
        title_date = start.astimezone(LOCAL_TZ).strftime("%Y-%m")
    title = f"{furnace_id} {template['name']} - {title_date}"
    metrics = metric_summary(snapshots)
    latest = snapshots[-1] if snapshots else None
    diag_label, evidence, actions = diagnosis_text(latest)
    abnormal = evidence or ["当前范围内未记录明确异常证据，建议结合现场班报补充。"]
    summary = f"时间范围 {start_text} 至 {end_text}，读取 {len(snapshots)} 条炉况快照；最新诊断：{diag_label}。"
    sections = [
        {
            "title": "生产与数据概况",
            "items": [
                {"label": "高炉", "value": furnace_id},
                {"label": "报表周期", "value": label},
                {"label": "时间范围", "value": f"{start_text} 至 {end_text}"},
                {"label": "快照数量", "value": str(len(snapshots))},
                {"label": "最新诊断", "value": diag_label},
            ],
        },
        {
            "title": "关键炉况指标",
            "items": [
                {
                    "label": item["label"],
                    "value": "--" if item["latest"] is None else f"{item['latest']:.3g} {item['unit']}".strip(),
                    "avg": "--" if item["avg"] is None else f"{item['avg']:.3g} {item['unit']}".strip(),
                    "range": "--" if item["min"] is None else f"{item['min']:.3g} ~ {item['max']:.3g} {item['unit']}".strip(),
                }
                for item in metrics
            ],
        },
        {
            "title": "异常信号",
            "items": [{"label": f"信号 {idx + 1}", "value": text} for idx, text in enumerate(abnormal[:8])],
        },
        {
            "title": "调控建议",
            "items": [{"label": f"建议 {idx + 1}", "value": text} for idx, text in enumerate(actions[:8])]
            or [{"label": "建议", "value": "暂无自动建议，请结合现场制度和班组确认补充。"}],
        },
    ]
    return {
        "type": "report",
        "furnace_id": furnace_id,
        "template_id": template["id"],
        "template_code": template["code"],
        "template_name": template["name"],
        "report_type": report_type,
        "report_type_label": label,
        "time_start": iso_local(start),
        "time_end": iso_local(end),
        "title": title,
        "summary": summary,
        "sections": sections,
        "metrics": metrics,
        "snapshot_ids": [snap.get("id") for snap in snapshots if snap.get("id")],
    }


def render_report_markdown(content: dict[str, Any]) -> str:
    lines = [
        f"# {content['title']}",
        "",
        f"- 报表类型：{content.get('report_type_label')}",
        f"- 时间范围：{content.get('time_start')} 至 {content.get('time_end')}",
        f"- 摘要：{content.get('summary')}",
        "",
    ]
    for section in content.get("sections", []):
        lines.extend([f"## {section.get('title')}", ""])
        for item in section.get("items", []):
            extra = ""
            if item.get("avg") or item.get("range"):
                extra = f"；均值：{item.get('avg', '--')}；范围：{item.get('range', '--')}"
            lines.append(f"- {item.get('label')}：{item.get('value')}{extra}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_report_html(content: dict[str, Any]) -> str:
    parts = [
        "<article class='bf-report-preview-doc'>",
        f"<h1>{html.escape(str(content.get('title') or '报表预览'))}</h1>",
        f"<p class='bf-report-summary'>{html.escape(str(content.get('summary') or ''))}</p>",
    ]
    for section in content.get("sections", []):
        parts.append(f"<section><h2>{html.escape(str(section.get('title') or ''))}</h2><table><tbody>")
        for item in section.get("items", []):
            value = html.escape(str(item.get("value") or "--"))
            if item.get("avg") or item.get("range"):
                value += f"<br><span>均值：{html.escape(str(item.get('avg') or '--'))}；范围：{html.escape(str(item.get('range') or '--'))}</span>"
            parts.append(f"<tr><th>{html.escape(str(item.get('label') or ''))}</th><td>{value}</td></tr>")
        parts.append("</tbody></table></section>")
    parts.append("</article>")
    return "".join(parts)


def safe_filename(value: str, fallback: str = "report") -> str:
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", str(value or "").strip()).strip("._")
    return text[:80] or fallback


def report_storage_dir(report_type: str, start: datetime) -> Path:
    local = start.astimezone(LOCAL_TZ)
    year = f"{local.year:04d}"
    month = f"{local.month:02d}"
    _, week, _ = local.isocalendar()
    week_folder = f"W{week:02d}"
    day = f"{local.day:02d}"
    hour = f"{local.hour:02d}"
    if report_type == "hourly":
        return REPORTS_DIR / year / month / week_folder / day / hour / "时报"
    if report_type == "daily":
        return REPORTS_DIR / year / month / week_folder / day / "日报"
    if report_type == "weekly":
        return REPORTS_DIR / year / month / week_folder / "周报"
    return REPORTS_DIR / year / month / "月报"


def make_docx_from_markdown(markdown: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    paras: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            paras.append("<w:p/>")
            continue
        is_heading = line.startswith("#")
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"^\-\s*", "• ", line)
        style = "<w:pStyle w:val=\"Heading1\"/>" if is_heading else ""
        paras.append(
            "<w:p><w:pPr>"
            + style
            + "</w:pPr><w:r><w:t xml:space=\"preserve\">"
            + html.escape(line)
            + "</w:t></w:r></w:p>"
        )
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body>"
        + "".join(paras)
        + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\"/></w:sectPr>"
        "</w:body></w:document>"
    )
    content_types = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
        "</Types>"
    )
    rels = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
        "</Relationships>"
    )
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)


def write_report_files(content: dict[str, Any], markdown: str, report_type: str, start: datetime) -> tuple[Path, Path]:
    folder = report_storage_dir(report_type, start)
    folder.mkdir(parents=True, exist_ok=True)
    local = start.astimezone(LOCAL_TZ)
    stamp = local.strftime("%Y%m%d_%H%M")
    base = safe_filename(f"{content.get('template_code', 'REPORT')}_{stamp}_{content.get('report_type_label', '')}")
    md_path = folder / f"{base}.md"
    docx_path = folder / f"{base}.docx"
    md_path.write_text(markdown, encoding="utf-8")
    make_docx_from_markdown(markdown, docx_path)
    return md_path.resolve(), docx_path.resolve()


def upsert_period_report(
    conn: Any,
    content: dict[str, Any],
    markdown: str,
    md_path: Path,
    docx_path: Path,
    metrics: list[dict[str, Any]],
) -> int:
    ts = iso_now()
    snapshot_ids = [int(x) for x in content.get("snapshot_ids", []) if str(x).isdigit()]
    conn.execute(
        """
        INSERT INTO period_reports(
            furnace_id, period_kind, period_start, period_end, timezone, title, report_markdown,
            markdown_path, docx_path, metrics_json, diagnosis_json, recommendation_json,
            sensor_refs_json, source_snapshot_min_id, source_snapshot_max_id, created_at, updated_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(furnace_id, period_kind, period_start, period_end)
        DO UPDATE SET title = excluded.title,
                      report_markdown = excluded.report_markdown,
                      markdown_path = excluded.markdown_path,
                      docx_path = excluded.docx_path,
                      metrics_json = excluded.metrics_json,
                      diagnosis_json = excluded.diagnosis_json,
                      recommendation_json = excluded.recommendation_json,
                      sensor_refs_json = excluded.sensor_refs_json,
                      source_snapshot_min_id = excluded.source_snapshot_min_id,
                      source_snapshot_max_id = excluded.source_snapshot_max_id,
                      updated_at = excluded.updated_at
        """,
        (
            content.get("furnace_id") or "GL02",
            content["report_type"],
            content["time_start"],
            content["time_end"],
            str(LOCAL_TZ),
            content["title"],
            markdown,
            str(md_path),
            str(docx_path),
            json.dumps(metrics, ensure_ascii=False),
            json.dumps({"summary": content.get("summary")}, ensure_ascii=False),
            json.dumps(content.get("sections", [])[-1] if content.get("sections") else {}, ensure_ascii=False),
            json.dumps([item.get("key") for item in metrics], ensure_ascii=False),
            min(snapshot_ids) if snapshot_ids else None,
            max(snapshot_ids) if snapshot_ids else None,
            ts,
            ts,
        ),
    )
    row = conn.execute(
        """
        SELECT id
        FROM period_reports
        WHERE furnace_id = ? AND period_kind = ? AND period_start = ? AND period_end = ?
        """,
        (content.get("furnace_id") or "GL02", content["report_type"], content["time_start"], content["time_end"]),
    ).fetchone()
    return int(row["id"])


def build_report_preview(conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    template_id = int(payload.get("template_id") or 0)
    if template_id <= 0:
        first = list_report_templates(conn, payload.get("report_type"))[0]
        template_id = int(first["id"])
    row = conn.execute("SELECT * FROM report_template WHERE id = ? AND enabled = 1", (template_id,)).fetchone()
    if row is None:
        raise ValueError("report template not found")
    template = report_template_from_row(row)
    report_type = normalize_report_type(payload.get("report_type") or template["report_type"])
    start, end = resolve_report_range(report_type, payload)
    furnace_id = str((payload.get("params") or {}).get("furnace_id") or payload.get("furnace_id") or "GL02")
    snapshots = collect_report_snapshots(conn, start, end)
    content = build_report_content(template, report_type, start, end, snapshots, furnace_id=furnace_id)
    markdown = render_report_markdown(content)
    preview_html = render_report_html(content)
    return {
        "ok": True,
        "template": template,
        "title": content["title"],
        "summary": content["summary"],
        "report_type": report_type,
        "time_start": content["time_start"],
        "time_end": content["time_end"],
        "content_json": content,
        "content_markdown": markdown,
        "preview_html": preview_html,
    }


def create_report_instance(conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    preview = payload if payload.get("content_json") and payload.get("content_markdown") else build_report_preview(conn, payload)
    content = preview["content_json"]
    markdown = str(preview.get("content_markdown") or render_report_markdown(content))
    report_type = normalize_report_type(preview.get("report_type") or content.get("report_type"))
    start = parse_report_dt(preview.get("time_start") or content.get("time_start")) or datetime.now(LOCAL_TZ)
    md_path, docx_path = write_report_files(content, markdown, report_type, start)
    period_report_id = upsert_period_report(conn, content, markdown, md_path, docx_path, content.get("metrics", []))
    ts = iso_now()
    cur = conn.execute(
        """
        INSERT INTO report_instance(
            template_id, period_report_id, furnace_id, report_type, time_start, time_end, title, summary,
            content_json, content_markdown, preview_html, markdown_path, docx_path, created_by, created_at, updated_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(content.get("template_id") or preview.get("template", {}).get("id") or 0),
            period_report_id,
            content.get("furnace_id") or "GL02",
            report_type,
            content["time_start"],
            content["time_end"],
            content["title"],
            content.get("summary") or "",
            json.dumps(content, ensure_ascii=False),
            markdown,
            preview.get("preview_html") or render_report_html(content),
            str(md_path),
            str(docx_path),
            str(payload.get("created_by") or "local_operator"),
            ts,
            ts,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM report_instance WHERE id = ?", (cur.lastrowid,)).fetchone()
    instance = report_instance_from_row(row)
    asset = {
        "id": f"period_report:{period_report_id}",
        "asset_type": "period_report",
        "asset_ref_id": str(period_report_id),
        "file_path": str(md_path),
        "display_path": display_path(str(md_path)),
        "display_name": instance["title"],
        "title": instance["title"],
        "period_kind": report_type,
        "period_start": instance["time_start"],
        "period_end": instance["time_end"],
        "static_url": static_url_for_path(md_path),
        "docx_url": static_url_for_path(docx_path),
    }
    return {
        "ok": True,
        "report_instance_id": instance["id"],
        "period_report_id": period_report_id,
        "instance": instance,
        "asset": asset,
        "insert_payload": {
            "insert_type": "report_card",
            "report_instance_id": instance["id"],
            "period_report_id": period_report_id,
            "report_type": report_type,
            "title": instance["title"],
            "summary": instance["summary"],
            "markdown": markdown,
            "time_start": instance["time_start"],
            "time_end": instance["time_end"],
        },
    }


def report_tree_from_instances(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root: dict[str, dict[str, Any]] = {}

    def node(
        children: dict[str, dict[str, Any]],
        key: str,
        label: str,
        node_type: str,
        folder: Path,
        sort_key: tuple[int, int],
    ) -> dict[str, Any]:
        if key not in children:
            children[key] = {
                "key": key,
                "label": label,
                "node_type": node_type,
                "folder_path": str(folder.resolve()),
                "display_path": display_path(str(folder)),
                "sort_key": sort_key,
                "items": [],
                "children_map": {},
            }
        return children[key]

    def week_label(local: datetime) -> tuple[str, str]:
        iso_year, week, _ = local.isocalendar()
        week_start = (local - timedelta(days=local.weekday())).date()
        week_end = week_start + timedelta(days=6)
        label = f"W{week:02d}  {week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}"
        return f"{iso_year}-W{week:02d}", label

    for raw_item in instances:
        dt = parse_report_dt(raw_item.get("time_start")) or datetime.now(LOCAL_TZ)
        local = dt.astimezone(LOCAL_TZ)
        year = f"{local.year:04d}"
        month = f"{local.month:02d}"
        week_key, week_text = week_label(local)
        day = f"{local.day:02d}"
        hour = f"{local.hour:02d}"

        year_node = node(root, year, f"{year}年", "year", REPORTS_DIR / year, (-local.year, 0))
        month_node = node(
            year_node["children_map"],
            month,
            f"{int(month)}月",
            "month",
            REPORTS_DIR / year / month,
            (int(month), 0),
        )
        week_node = node(
            month_node["children_map"],
            week_key,
            week_text,
            "week",
            REPORTS_DIR / year / month / f"W{local.isocalendar().week:02d}",
            (local.isocalendar().week, 0),
        )
        day_node = node(
            week_node["children_map"],
            day,
            f"{int(day)}日",
            "day",
            REPORTS_DIR / year / month / f"W{local.isocalendar().week:02d}" / day,
            (int(day), 0),
        )
        hour_node = node(
            day_node["children_map"],
            hour,
            f"{int(hour)}时",
            "hour",
            REPORTS_DIR / year / month / f"W{local.isocalendar().week:02d}" / day / hour,
            (int(hour), 0),
        )

        rtype = raw_item.get("report_type")
        target = {
            "monthly": month_node,
            "weekly": week_node,
            "daily": day_node,
            "hourly": hour_node,
        }.get(str(rtype), day_node)
        item = dict(raw_item)
        item["tree_folder_path"] = target["folder_path"]
        item["tree_display_path"] = target["display_path"]
        item["tree_scope"] = {
            "year": local.year,
            "month": local.month,
            "week": local.isocalendar().week,
            "day": local.day,
            "hour": local.hour,
        }
        target["items"].append(item)

    def finish(item: dict[str, Any]) -> dict[str, Any]:
        children = [finish(child) for child in item.pop("children_map").values()]
        children.sort(key=lambda child: tuple(child.get("sort_key") or (0, 0)))
        item["children"] = children
        item["items"].sort(key=lambda report: str(report.get("time_start") or ""), reverse=True)
        item["item_count"] = len(item["items"]) + sum(int(child.get("item_count") or 0) for child in children)
        return item

    out = [finish(item) for item in root.values()]
    out.sort(key=lambda item: tuple(item.get("sort_key") or (0, 0)))
    return out


def list_allowed_folders(max_depth: int = 6) -> list[dict[str, Any]]:
    folders: list[dict[str, Any]] = []
    for root in allowed_roots():
        root.mkdir(parents=True, exist_ok=True)
        folders.append({"folder_path": str(root), "display_path": display_path(str(root)), "name": root.name})
        for path in root.rglob("*"):
            if not path.is_dir():
                continue
            try:
                depth = len(path.resolve().relative_to(root).parts)
            except ValueError:
                continue
            if depth > max_depth:
                continue
            folders.append({"folder_path": str(path.resolve()), "display_path": display_path(str(path)), "name": path.name})
    return folders[:300]


def preferred_file_opener(action: str, suffix: str) -> str | None:
    action = action.lower()
    candidates: list[str] = []
    if action == "office":
        if suffix in {".doc", ".docx", ".rtf"}:
            candidates = ["WINWORD.EXE", "winword.exe"]
        elif suffix in {".xls", ".xlsx", ".csv"}:
            candidates = ["EXCEL.EXE", "excel.exe"]
        elif suffix in {".ppt", ".pptx"}:
            candidates = ["POWERPNT.EXE", "powerpnt.exe"]
    elif action == "wps":
        if suffix in {".doc", ".docx", ".rtf", ".pdf"}:
            candidates = ["wps.exe", "WPS.EXE"]
        elif suffix in {".xls", ".xlsx", ".csv"}:
            candidates = ["et.exe", "ET.EXE", "wps.exe"]
        elif suffix in {".ppt", ".pptx"}:
            candidates = ["wpp.exe", "WPP.EXE", "wps.exe"]
    for name in candidates:
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def open_allowed_local_path(path_value: str, action: str = "default") -> dict[str, Any]:
    path = resolve_allowed_path(path_value)
    if not path.exists():
        raise ValueError("file or folder does not exist")
    action = (action or "default").lower()
    if action in {"reveal", "folder"}:
        if os.name != "nt":
            raise ValueError("system file manager open is only enabled on Windows in this project")
        if action == "reveal" and path.is_file():
            subprocess.Popen(["explorer.exe", "/select,", str(path)])
        else:
            folder = path if path.is_dir() else path.parent
            subprocess.Popen(["explorer.exe", str(folder)])
        mode_used = action
    elif action in {"default", "office", "wps"}:
        if path.is_dir():
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", str(path)])
                mode_used = "folder"
            else:
                raise ValueError("folder open is only enabled on Windows in this project")
        else:
            opener = preferred_file_opener(action, path.suffix.lower()) if action in {"office", "wps"} else None
            if opener:
                subprocess.Popen([opener, str(path)])
                mode_used = action
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
                mode_used = "default"
            else:
                raise ValueError("default file open is only enabled on Windows in this project")
    else:
        raise ValueError(f"unknown open action: {action}")
    return {"path": str(path), "display_path": display_path(str(path)), "action": action, "mode_used": mode_used}


def project_asset_from_row(row: dict[str, Any]) -> dict[str, Any]:
    path = Path(row["file_path"]) if row["file_path"] else None
    static_url = static_url_for_path(path) if path and path.exists() and path.is_file() else None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "asset_type": row["asset_type"],
        "asset_ref_id": row["asset_ref_id"],
        "file_path": row["file_path"],
        "display_path": display_path(row["file_path"]),
        "display_name": row["display_name"],
        "title": row["display_name"],
        "default_include_mode": row["default_include_mode"],
        "static_url": static_url,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_project_assets(conn: Any, project_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM project_assets
        WHERE project_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (project_id,),
    ).fetchall()
    return [project_asset_from_row(row) for row in rows]


def add_project_asset(conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    ts = iso_now()
    project_id = int(payload.get("project_id") or 0)
    if project_id <= 0:
        raise ValueError("missing project_id")
    project = conn.execute("SELECT * FROM qa_projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise ValueError("project not found")
    asset_type = str(payload.get("asset_type") or infer_asset_type(Path(str(payload.get("file_path") or ""))))
    if asset_type not in {"period_report", "markdown_file", "docx_file", "folder", "txt_file", "pdf_file", "spreadsheet_file", "csv_file", "other"}:
        asset_type = "other"
    file_path = payload.get("file_path")
    if file_path:
        file_path = str(resolve_allowed_path(str(file_path)))
    else:
        file_path = ""
    display_name = str(payload.get("display_name") or payload.get("title") or (Path(file_path).name if file_path else "asset"))
    mode = str(payload.get("default_include_mode") or payload.get("insert_mode") or "summary")
    if mode not in {"summary", "full_text", "selected_sections", "citation_only"}:
        mode = "summary"
    conn.execute(
        """
        INSERT INTO project_assets(project_id, asset_type, asset_ref_id, file_path, display_name, default_include_mode, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, asset_type, asset_ref_id, file_path)
        DO UPDATE SET display_name = excluded.display_name,
                      default_include_mode = excluded.default_include_mode,
                      updated_at = excluded.updated_at
        """,
        (
            project_id,
            asset_type,
            str(payload.get("asset_ref_id") or ""),
            file_path,
            display_name,
            mode,
            ts,
            ts,
        ),
    )
    conn.execute("UPDATE qa_projects SET updated_at = ? WHERE id = ?", (ts, project_id))
    conn.commit()
    row = conn.execute(
        """
        SELECT *
        FROM project_assets
        WHERE project_id = ? AND asset_type = ? AND asset_ref_id = ? AND IFNULL(file_path, '') = IFNULL(?, '')
        """,
        (project_id, asset_type, str(payload.get("asset_ref_id") or ""), file_path),
    ).fetchone()
    return project_asset_from_row(row)


def select_bootstrap_conversation(conn: Any, force_new: bool = False) -> tuple[dict[str, Any], bool]:
    row = conn.execute(
        "SELECT * FROM qa_conversations ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    if force_new or row is None:
        return create_conversation(conn), True

    conv = conversation_from_row(row)
    last_user_at = parse_iso(conv.get("last_user_at"))
    if last_user_at is not None and now_utc() - last_user_at > timedelta(hours=QA_INACTIVITY_HOURS):
        return create_conversation(conn), True
    return conv, False


def snapshot_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source_time": row["source_time"],
        "created_at": row["created_at"],
        "values": load_json(row["values_json"], {}),
        "diagnosis": load_json(row["diagnosis_json"], {}),
        "recommendation": load_json(row["recommendation_json"], {}),
        "data_quality": load_json(row["data_quality_json"], {}),
        "payload": load_json(row["payload_json"], {}),
    }


def snapshot_by_id(conn: Any, snapshot_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM furnace_snapshots WHERE id = ? LIMIT 1", (snapshot_id,)).fetchone()
    if row is None:
        return None
    return snapshot_from_row(row)


def latest_snapshot(conn: Any) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM furnace_snapshots ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return snapshot_from_row(row)


def recent_snapshots(conn: Any, hours: float = 8.0, limit: int = 120) -> list[dict[str, Any]]:
    cutoff = (now_utc() - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT * FROM furnace_snapshots
            WHERE created_at >= ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ) recent
        ORDER BY created_at ASC, id ASC
        """,
        (cutoff, limit),
    ).fetchall()
    if not rows:
        latest = latest_snapshot(conn)
        return [latest] if latest else []
    return [snapshot_from_row(row) for row in rows]


def snapshots_after_id(conn: Any, snapshot_id: int, limit: int = 120) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM (
            SELECT * FROM furnace_snapshots
            WHERE id > ?
            ORDER BY id DESC
            LIMIT ?
        ) recent
        ORDER BY id ASC
        """,
        (snapshot_id, limit),
    ).fetchall()
    return [snapshot_from_row(row) for row in rows]


def snapshot_sort_timestamp(snapshot: dict[str, Any] | None) -> float:
    if not snapshot:
        return 0.0
    raw = snapshot.get("source_time") or snapshot.get("created_at")
    dt: datetime | None
    if isinstance(raw, datetime):
        dt = raw
    else:
        dt = parse_iso(str(raw)) if raw is not None else None
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.timestamp()


def snapshot_has_known_diagnosis(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return False
    diagnosis = snapshot.get("diagnosis") or {}
    raw_label = (
        diagnosis.get("main_label")
        or diagnosis.get("label")
        or diagnosis.get("key")
        or diagnosis.get("mainLabel")
    )
    label = str(raw_label or "").strip().lower()
    return bool(label and label not in {"unknown", "none", "null", "未知", "未连接"})


def snapshot_id_sort_value(snapshot: dict[str, Any] | None) -> int:
    if not snapshot:
        return 0
    try:
        return int(snapshot.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def choose_latest_state_snapshot(snapshots: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    candidates = [snapshot for snapshot in snapshots if snapshot]
    if not candidates:
        return None
    known = [snapshot for snapshot in candidates if snapshot_has_known_diagnosis(snapshot)]
    pool = known or candidates
    return max(pool, key=lambda item: (snapshot_sort_timestamp(item), snapshot_id_sort_value(item)))


def last_qa_context_anchor(conn: Any, conversation_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, snapshot_id, hidden_context_json
        FROM qa_messages
        WHERE conversation_id = ?
          AND role = 'user'
          AND hidden_context_json IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()
    if row is None:
        return None
    hidden = load_json(row["hidden_context_json"], {})
    raw_snapshot_id = hidden.get("latest_snapshot_id") or row["snapshot_id"]
    try:
        snapshot_id = int(raw_snapshot_id) if raw_snapshot_id is not None else None
    except (TypeError, ValueError):
        snapshot_id = None
    if not snapshot_id:
        return None
    return {
        "message_id": row["id"],
        "snapshot_id": snapshot_id,
        "context_mode": hidden.get("context_mode"),
        "latest_snapshot_source_time": hidden.get("latest_snapshot_source_time"),
        "trend_end_time": hidden.get("trend_end_time"),
        "trend_count": hidden.get("trend_count"),
    }


def last_qa_tool_context(conn: Any, conversation_id: str) -> dict[str, Any] | None:
    """Return the latest persisted compact MCP conversation state."""

    rows = conn.execute(
        """
        SELECT hidden_context_json
        FROM qa_messages
        WHERE conversation_id = ?
          AND hidden_context_json IS NOT NULL
        ORDER BY id DESC
        LIMIT 8
        """,
        (conversation_id,),
    ).fetchall()
    for row in rows:
        hidden = load_json(row["hidden_context_json"], {})
        context = hidden.get("mcp_conversation_context")
        if isinstance(context, dict):
            return context
    return None


def qa_snapshots_for_turn(
    conn: Any,
    conversation_id: str,
    baseline_hours: float = 8.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    anchor = last_qa_context_anchor(conn, conversation_id)
    if not anchor:
        snapshots = recent_snapshots(conn, hours=baseline_hours)
        return snapshots, {
            "context_mode": "full_8h_baseline",
            "anchor_message_id": None,
            "anchor_snapshot_id": None,
            "baseline_hours": baseline_hours,
            "delta_only": False,
        }

    snapshots = snapshots_after_id(conn, int(anchor["snapshot_id"]))
    mode = "delta_since_previous_question"
    if not snapshots:
        latest = latest_snapshot(conn)
        snapshots = [latest] if latest else []
        mode = "latest_only_no_new_snapshot"

    return snapshots, {
        "context_mode": mode,
        "anchor_message_id": anchor.get("message_id"),
        "anchor_snapshot_id": anchor.get("snapshot_id"),
        "baseline_hours": baseline_hours,
        "delta_only": True,
    }


def insert_snapshot(conn: Any, snapshot: dict[str, Any]) -> int:
    source_time = str(snapshot.get("source_time") or snapshot.get("sourceTime") or snapshot.get("timestamp") or iso_now())
    values = snapshot.get("values") or {}
    if not values and isinstance(snapshot.get("variableSummary"), list):
        values = {
            item.get("id"): item.get("current_value")
            for item in snapshot.get("variableSummary", [])
            if isinstance(item, dict) and item.get("id")
        }
    diagnosis = snapshot.get("diagnosis") or {}
    recommendation = snapshot.get("recommendation") or diagnosis.get("recommendation") or {}
    if not recommendation and snapshot.get("optimizationContextArray"):
        recommendation = {"context": snapshot.get("optimizationContextArray")}
    data_quality = snapshot.get("data_quality") or {}
    payload = {
        "source_time": source_time,
        "values": values,
        "diagnosis": diagnosis,
        "recommendation": recommendation,
        "data_quality": data_quality,
    }
    cur = conn.execute(
        """
        INSERT INTO furnace_snapshots(
            source_time, created_at, values_json, diagnosis_json,
            recommendation_json, data_quality_json, payload_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_time,
            iso_now(),
            json.dumps(values, ensure_ascii=False, default=str),
            json.dumps(diagnosis, ensure_ascii=False, default=str),
            json.dumps(recommendation, ensure_ascii=False, default=str),
            json.dumps(data_quality, ensure_ascii=False, default=str),
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_message(
    conn: Any,
    conversation_id: str,
    role: str,
    content: str,
    snapshot_id: int | None = None,
    hidden_context: dict[str, Any] | None = None,
) -> int:
    ts = iso_now()
    cur = conn.execute(
        """
        INSERT INTO qa_messages(
            conversation_id, role, content, created_at, snapshot_id, hidden_context_json
        )
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            role,
            content,
            ts,
            snapshot_id,
            json.dumps(hidden_context, ensure_ascii=False) if hidden_context else None,
        ),
    )
    if role == "user":
        conn.execute(
            """
            UPDATE qa_conversations
            SET updated_at = ?, last_user_at = ?,
                title = CASE WHEN title = '新对话' THEN ? ELSE title END
            WHERE id = ?
            """,
            (ts, ts, title_from_question(content), conversation_id),
        )
    else:
        conn.execute(
            "UPDATE qa_conversations SET updated_at = ? WHERE id = ?",
            (ts, conversation_id),
        )
    conn.commit()
    return int(cur.lastrowid)


def clean_llm_output(text: str) -> str:
    out = str(text or "").replace("\r\n", "\n").strip()
    for marker in ("<|im_start|>", "<|im_end|>", "莿莿assistant", "莿莿"):
        out = out.replace(marker, "\n")
    out = sanitize_public_qa_answer(out)
    return out.strip() or "模型未返回内容。"


def sanitize_public_qa_answer(text: str) -> str:
    out = str(text or "")
    replacements = (
        ("RAG/MCP", "后台资料"),
        ("rag/mcp", "后台资料"),
        ("系统规则", "后台处理口径"),
        ("隐藏上下文", "后台炉况资料"),
        ("隐藏状态文本", "后台炉况资料"),
        ("隐藏注入", "后台资料组织"),
        ("规则引擎", "诊断处理过程"),
        ("规则库", "诊断参考资料"),
        ("提示词", "后台对话设置"),
        ("工具调用", "数据查询"),
        ("原始评分字段", "后台资料原文"),
        ("后台处理口径与算法", "后台处理细节"),
        ("算法公式", "计算细节"),
        ("算法原理", "处理细节"),
        ("算法", "处理过程"),
        ("技术实现细节", "后台处理细节"),
        ("技术细节", "处理细节"),
        ("评分权重", "处理细节"),
        ("评分公式", "处理细节"),
        ("特征计算", "计算细节"),
        ("后台核心逻辑", "后台处理细节"),
        ("内部实现逻辑", "后台处理细节"),
        ("系统内部实现", "后台处理细节"),
        ("内部实现", "后台处理"),
        ("基线表", "历史参考资料"),
        ("内部变量", "后台字段"),
        ("内部评分字段、内部特征字段", "后台字段"),
        ("内部评分字段", "后台字段"),
        ("内部特征字段", "后台字段"),
        ("MCP", "数据库查询"),
        ("mcp", "数据库查询"),
        ("RAG", "知识资料"),
        ("rag", "知识资料"),
        ("raw_scores", "内部评分字段"),
        ("feature_snapshot", "内部特征字段"),
        ("daily_baselines", "历史基线资料"),
        ("z-score", "偏离程度"),
        ("Z-score", "偏离程度"),
        ("IQR", "波动参考范围"),
        ("baseline", "历史参考"),
    )
    for old, new in replacements:
        out = out.replace(old, new)
    cleanup_replacements = (
        ("内部评分字段", "后台字段"),
        ("内部特征字段", "后台字段"),
        ("后台字段和后台字段字段", "后台资料"),
        ("后台字段和后台字段", "后台资料"),
        ("后台字段字段", "后台字段"),
        ("后台炉况资料、后台资料、后台资料", "后台资料"),
        ("后台炉况资料、后台资料", "后台资料"),
        ("后台资料结果", "后台资料"),
        ("后台资料、后台资料", "后台资料"),
        ("处理细节、处理细节", "处理细节"),
        ("后台处理口径、诊断处理过程、处理细节", "后台处理细节"),
        ("关于后台处理细节", "关于后台资料"),
        ("后台处理口径、诊断处理过程或处理细节等处理细节", "后台处理细节"),
        ("后台处理细节、处理细节或计算细节过程", "后台处理细节"),
        ("后台处理细节、后台资料原文或后台字段（如 后台字段 等）", "后台资料原文"),
        ("后台处理细节、后台资料原文或后台字段", "后台资料原文"),
    )
    for old, new in cleanup_replacements:
        out = out.replace(old, new)
    return out


def prompt_number(value: Any) -> Any:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(num):
        return None
    return round(num, 4)


def compact_prompt_values(values: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in QA_PROMPT_VALUE_KEYS:
        if key not in values:
            continue
        value = prompt_number(values.get(key))
        if value is not None:
            compact[key] = value
    return compact


def prompt_item_text(item: Any) -> str:
    if isinstance(item, dict):
        text = item.get("text") or item.get("name") or item.get("id") or item.get("reason") or ""
        if item.get("reason") and item.get("text") and item.get("reason") != item.get("text"):
            text = f"{item.get('text')} ({item.get('reason')})"
    else:
        text = str(item or "")
    return str(text).strip()[:160]


def compact_prompt_items(items: Any, limit: int = 3) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        text = prompt_item_text(item)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def prompt_diagnosis_and_recommendation(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnosis = snapshot.get("diagnosis") or {}
    rec = snapshot.get("recommendation") or (diagnosis.get("recommendation") if isinstance(diagnosis, dict) else None) or {}
    if isinstance(diagnosis, dict) and "diagnosis" in diagnosis:
        rec = diagnosis.get("recommendation") or rec
        diagnosis = diagnosis.get("diagnosis") or diagnosis
    if not isinstance(diagnosis, dict):
        diagnosis = {}
    if not isinstance(rec, dict):
        rec = {}
    frontend_label = diagnosis.get("main_label") or diagnosis.get("key")
    if not frontend_label:
        raw_label = str(diagnosis.get("label") or "").strip()
        label_map = {
            "炉热": "hot",
            "炉凉": "cold",
            "炉冷": "cold",
            "边缘气流": "edge",
            "中心气流": "center",
            "管道": "channel",
            "料柱异常": "column",
            "低料线": "lowline",
            "正常顺行": "normal",
            "正常": "normal",
        }
        frontend_label = label_map.get(raw_label, raw_label if raw_label in DIAG_KEYS else None)
    diagnosis_out = {
        "main_label": frontend_label,
        "secondary_label": diagnosis.get("secondary_label") or diagnosis.get("secondary"),
        "main_score": prompt_number(diagnosis.get("main_score", diagnosis.get("score"))),
        "main_confidence": prompt_number(diagnosis.get("main_confidence", diagnosis.get("confidence"))),
        "evidence": compact_prompt_items(diagnosis.get("evidence"), limit=3),
    }
    rec_out = {
        "goal": rec.get("goal"),
        "immediate_actions": compact_prompt_items(rec.get("immediate_actions"), limit=3),
        "followup_actions": compact_prompt_items(rec.get("followup_actions"), limit=2),
        "forbidden_actions": compact_prompt_items(rec.get("forbidden_actions"), limit=2),
        "observe": compact_prompt_items(rec.get("observe") or rec.get("observe_items"), limit=5),
        "recheck_minutes": rec.get("recheck_minutes"),
    }
    return diagnosis_out, rec_out


def compact_prompt_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    diagnosis, rec = prompt_diagnosis_and_recommendation(snapshot)
    return {
        "snapshot_id": snapshot.get("id"),
        "source_time": snapshot.get("source_time"),
        "values": compact_prompt_values(snapshot.get("values") or {}),
        "diagnosis": diagnosis,
        "recommendation": rec,
        "data_quality": snapshot.get("data_quality") or {},
    }


def prompt_values_from_feature_snapshot(feature_snapshot: Any) -> dict[str, Any]:
    if not isinstance(feature_snapshot, dict):
        return {}
    source: dict[str, Any] = feature_snapshot
    for key in ("values", "current_values", "latest_values", "variables"):
        nested = feature_snapshot.get(key)
        if isinstance(nested, dict):
            source = nested
            break
    values: dict[str, Any] = {}
    for key in QA_PROMPT_VALUE_KEYS:
        raw = source.get(key)
        if isinstance(raw, dict):
            raw = (
                raw.get("value")
                if raw.get("value") is not None
                else raw.get("current_value", raw.get("mean"))
            )
        value = prompt_number(raw)
        if value is not None:
            values[key] = value
    return values


def pg_diagnosis_row_to_prompt_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    feature_snapshot = row.get("feature_snapshot") or {}
    coverage = row.get("data_coverage") or {}
    diagnosis = {
        "main_label": row.get("main_label"),
        "secondary_label": row.get("secondary_label"),
        "main_score": row.get("main_score"),
        "main_confidence": row.get("main_confidence"),
        "evidence": row.get("evidence") or [],
        "raw_scores": row.get("raw_scores") or {},
        "diagnosis_ts": row.get("diagnosis_ts"),
        "diagnosis_window_start": row.get("diagnosis_window_start"),
        "diagnosis_window_end": row.get("diagnosis_window_end"),
        "baseline_window_start": row.get("baseline_window_start"),
        "baseline_window_end": row.get("baseline_window_end"),
    }
    return {
        "id": f"pg_diag:{row.get('id')}",
        "pg_diagnosis_id": row.get("id"),
        "source_time": str(row.get("diagnosis_ts") or row.get("created_at") or iso_now()),
        "created_at": str(row.get("updated_at") or row.get("created_at") or iso_now()),
        "values": prompt_values_from_feature_snapshot(feature_snapshot),
        "diagnosis": diagnosis,
        "recommendation": {},
        "data_quality": {
            "coverage_ratio": coverage.get("coverage_ratio") if isinstance(coverage, dict) else None,
            "missing_variables": row.get("missing_variables") or [],
            "source_lag_seconds": row.get("source_lag_seconds"),
            "source": row.get("source"),
            "baseline_days": row.get("baseline_days"),
            "window_minutes": row.get("window_minutes"),
            "from_pg_diagnosis_snapshots": True,
        },
    }


def sampled_prompt_snapshots(snapshots: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or len(snapshots) <= limit:
        return snapshots
    step = max(1, math.ceil(len(snapshots) / limit))
    sampled = snapshots[::step]
    if sampled[-1].get("id") != snapshots[-1].get("id"):
        sampled.append(snapshots[-1])
    return sampled[-limit:]


def prompt_value_ranges(snapshots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ranges: dict[str, dict[str, Any]] = {}
    for key in QA_PROMPT_VALUE_KEYS:
        nums: list[float] = []
        latest: Any = None
        for snapshot in snapshots:
            values = snapshot.get("values") or {}
            if key not in values:
                continue
            value = prompt_number(values.get(key))
            if value is None:
                continue
            latest = value
            if isinstance(value, (int, float)):
                nums.append(float(value))
        if latest is None:
            continue
        item: dict[str, Any] = {"latest": latest}
        if nums:
            item["min"] = round(min(nums), 4)
            item["max"] = round(max(nums), 4)
        ranges[key] = item
    return ranges


def prompt_label_counts(snapshots: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for snapshot in snapshots:
        diagnosis, _ = prompt_diagnosis_and_recommendation(snapshot)
        label = str(diagnosis.get("main_label") or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


PROMPT_METRIC_ALIASES = {
    "DP_total": "总压差",
    "DP_upper": "上部压差",
    "DP_lower": "下部压差",
    "PI": "透气性指数",
    "P_blast": "热风压力",
    "P_blast_cold": "冷风压力",
    "T_blast": "风温",
    "Q_blast": "风量",
    "P_top": "顶压",
    "T_top": "顶温",
    "PCI_rate": "喷煤",
    "PCI_set": "喷煤设定",
    "Q_O2": "富氧流量",
    "O2_rate": "富氧率",
    "GasUtil": "煤气利用率",
    "L": "料线",
    "L_south": "南料线",
    "L_north": "北料线",
    "P_top_gas_A": "A上升管煤气压力",
    "P_top_gas_B": "B上升管煤气压力",
    "P_top_gas_C": "C上升管煤气压力",
    "P_top_gas_D": "D上升管煤气压力",
    "T_taphole_1": "一号出铁口温度",
    "T_taphole_2": "二号出铁口温度",
}
PROMPT_METRIC_UNIT_FALLBACKS = {
    "L_south": "m",
    "L_north": "m",
    "P_top_gas_A": "kPa",
    "P_top_gas_B": "kPa",
    "P_top_gas_C": "kPa",
    "P_top_gas_D": "kPa",
    "P_blast_cold": "kPa",
    "Q_O2": "Nm³/h",
    "O2_rate": "%",
}


def prompt_short_number(value: Any) -> str | None:
    value = prompt_number(value)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        return str(value)[:20]
    number = float(value)
    magnitude = abs(number)
    if magnitude >= 1000:
        text = f"{number:.0f}"
    elif magnitude >= 100:
        text = f"{number:.1f}"
    elif magnitude >= 10:
        text = f"{number:.2f}"
    else:
        text = f"{number:.3g}"
    return text.rstrip("0").rstrip(".")


def prompt_time_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(LOCAL_TZ)
        return dt.strftime("%m-%d %H:%M")
    except ValueError:
        pass
    if len(text) >= 16 and text[4:5] == "-" and text[10:11] in {"T", " "}:
        return text[5:16].replace("T", " ")
    return text[:16]


def prompt_join_items(items: Any, limit: int = 2, max_chars: int = 64) -> str:
    texts = compact_prompt_items(items, limit=limit) if isinstance(items, list) else []
    out: list[str] = []
    for text in texts:
        cleaned = re.sub(r"\s*[（(].*?[）)]\s*$", "", text).strip()
        if cleaned:
            out.append(cleaned[:max_chars])
    return "、".join(out)


def prompt_metric_line(values: dict[str, Any], limit: int = 10) -> str:
    parts: list[str] = []
    for key in QA_PROMPT_VALUE_KEYS:
        if key not in values:
            continue
        value = prompt_short_number(values.get(key))
        if value is None:
            continue
        parts.append(f"{PROMPT_METRIC_ALIASES.get(key, key)}={value}")
        if len(parts) >= limit:
            break
    return " ".join(parts)


def prompt_missing_line(snapshot: dict[str, Any], limit: int = 3) -> str:
    data_quality = snapshot.get("data_quality") or {}
    if not isinstance(data_quality, dict):
        return ""
    missing: list[str] = []
    for key in ("missing_files", "missing_tags", "missing_points", "missing_values"):
        value = data_quality.get(key)
        if isinstance(value, list):
            missing.extend(str(item) for item in value if item)
        elif isinstance(value, dict):
            missing.extend(str(item_key) for item_key, item_value in value.items() if item_value)
        elif value:
            missing.append(str(value))
    errors = data_quality.get("realtime_errors")
    if isinstance(errors, dict):
        missing.extend(str(key) for key in errors.keys())
    seen: set[str] = set()
    compact: list[str] = []
    for item in missing:
        item = item.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        compact.append(item[:24])
        if len(compact) >= limit:
            break
    return "、".join(compact)


def prompt_status_line(snapshot: dict[str, Any]) -> str:
    diagnosis, rec = prompt_diagnosis_and_recommendation(snapshot)
    label = str(diagnosis.get("main_label") or "unknown")
    score = prompt_short_number(diagnosis.get("main_score") or diagnosis.get("main_confidence"))
    if score:
        label = f"{label}({score})"
    metrics = prompt_metric_line(snapshot.get("values") or {})
    actions = prompt_join_items(rec.get("immediate_actions"), limit=2)
    forbidden = prompt_join_items(rec.get("forbidden_actions"), limit=1)
    followup = prompt_join_items(rec.get("followup_actions"), limit=1)
    missing = prompt_missing_line(snapshot)
    parts = [
        f"- {prompt_time_label(snapshot.get('source_time'))}",
        f"id={snapshot.get('id')}",
        label,
    ]
    if metrics:
        parts.append(metrics)
    if actions:
        parts.append(f"建议:{actions}")
    elif followup:
        parts.append(f"后续:{followup}")
    if forbidden:
        parts.append(f"禁:{forbidden}")
    if missing:
        parts.append(f"缺:{missing}")
    return " | ".join(str(part) for part in parts if part)


def prompt_range_line(snapshots: list[dict[str, Any]], limit: int = 8) -> str:
    ranges = prompt_value_ranges(snapshots)
    parts: list[str] = []
    for key in QA_PROMPT_VALUE_KEYS:
        item = ranges.get(key)
        if not item:
            continue
        alias = PROMPT_METRIC_ALIASES.get(key, key)
        min_value = prompt_short_number(item.get("min"))
        max_value = prompt_short_number(item.get("max"))
        latest = prompt_short_number(item.get("latest"))
        if min_value is not None and max_value is not None:
            parts.append(f"{alias}:{min_value}-{max_value},末{latest}")
        elif latest is not None:
            parts.append(f"{alias}:末{latest}")
        if len(parts) >= limit:
            break
    return "；".join(parts)


def prompt_label_count_line(snapshots: list[dict[str, Any]]) -> str:
    counts = prompt_label_counts(snapshots)
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return "、".join(f"{label}x{count}" for label, count in ordered[:5])


def snapshot_summary_for_prompt(
    snapshots: list[dict[str, Any]],
    context_meta: dict[str, Any] | None = None,
) -> str:
    meta = dict(context_meta or {})
    latest_snapshot = meta.get("latest_snapshot") if isinstance(meta.get("latest_snapshot"), dict) else None
    if latest_snapshot is None and snapshots:
        latest_snapshot = snapshots[-1]
    if not snapshots and latest_snapshot:
        snapshots = [latest_snapshot]
    if not snapshots and latest_snapshot is None:
        return "当前服务端尚未写入炉况快照。"
    sampled = sampled_prompt_snapshots(snapshots, QA_PROMPT_MAX_SNAPSHOTS)
    context_mode = meta.get("context_mode", "full_8h_baseline")
    baseline_hours = meta.get("baseline_hours", 8)
    anchor_message_id = meta.get("anchor_message_id") or "无"
    anchor_snapshot_id = meta.get("anchor_snapshot_id") or "无"
    range_line = prompt_range_line(snapshots)
    label_line = prompt_label_count_line(snapshots)
    latest_metric_line = prompt_metric_line((latest_snapshot or {}).get("values") or {})
    trend_source_label = meta.get("trend_source_label") or "生产5min诊断"
    trend_count = meta.get("trend_count", len(snapshots))
    trend_limit = meta.get("trend_limit", QA_TREND_DIAGNOSIS_LIMIT)
    trend_cadence = meta.get("trend_cadence_minutes", QA_TREND_CADENCE_MINUTES)
    trend_end = meta.get("trend_end_time") or "未知"
    previous_latest_time = meta.get("previous_latest_snapshot_source_time") or "无"
    current_latest_time = (latest_snapshot or {}).get("source_time") or "未知"
    lines = [
        "【炉况状态包】",
        (
            f"模式={context_mode}；基线={baseline_hours}h；"
            f"{trend_source_label}底层记录={trend_count}/{trend_limit}条；采样间隔约{trend_cadence}min；"
            f"下方仅展示抽样时间线={len(sampled)}条；趋势终点={trend_end}；"
            f"上一轮状态锚点={previous_latest_time}；当前状态锚点={current_latest_time}；"
            f"锚点消息={anchor_message_id}；锚点快照={anchor_snapshot_id}"
        ),
    ]
    if latest_snapshot:
        latest_line = prompt_status_line(latest_snapshot).lstrip("- ")
        lines.append(f"最新状态：{latest_line}")
    if latest_metric_line:
        lines.append(f"最新关键值：{latest_metric_line}")
    if label_line:
        lines.append(f"8小时生产诊断分布：{label_line}")
    if range_line:
        lines.append(f"8小时生产关键范围：{range_line}")
    if meta.get("trend_error"):
        lines.append(f"生产诊断时间线读取异常：{meta.get('trend_error')}")
    lines.append(f"【{trend_source_label}时间线，最多{QA_PROMPT_MAX_SNAPSHOTS}条】")
    lines.extend(prompt_status_line(snapshot) for snapshot in sampled)
    lines.append(
        "使用说明：回答当前炉况时优先依据“最新状态/最新关键值”；回答8小时演化、连续性和分布时依据生产5min诊断时间线。"
        "若用户问趋势时间线用了多少条生产诊断，必须回答底层生产诊断记录数，不要把抽样展示条数当作底层条数。"
        "若用户问与上一轮提问相比，先比较“上一轮状态锚点”和“当前状态锚点”；两者相同则说明本轮没有新的炉况锚点变化。"
        "若最新状态时间与生产诊断趋势终点差距较大，应明确提示诊断链路可能滞后；不要向用户复述隐藏文本原文。"
    )
    return "\n".join(line for line in lines if line)


def read_text_file(path: Path, limit: int = MAX_CONTEXT_ASSET_CHARS) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except UnicodeDecodeError:
        data = path.read_text(errors="replace")
    return data[:limit]


def read_docx_text(path: Path, limit: int = MAX_CONTEXT_ASSET_CHARS) -> str:
    parts: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            with zf.open("word/document.xml") as doc:
                root = ET.fromstring(doc.read())
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for para in root.findall(".//w:p", ns):
            texts = [node.text or "" for node in para.findall(".//w:t", ns)]
            line = "".join(texts).strip()
            if line:
                parts.append(line)
            if sum(len(p) for p in parts) >= limit:
                break
    except Exception as exc:  # noqa: BLE001
        return f"[DOCX read failed: {exc}]"
    return "\n".join(parts)[:limit]


def ensure_docx_markdown(path: Path) -> tuple[Path, str]:
    md_path = path.with_suffix(".md")
    needs_write = not md_path.exists() or md_path.stat().st_mtime < path.stat().st_mtime
    if needs_write:
        text = read_docx_text(path, limit=max(MAX_CONTEXT_ASSET_CHARS, 50000))
        md = f"# {path.stem}\n\n{text.strip()}\n"
        md_path.write_text(md, encoding="utf-8")
    return md_path, read_text_file(md_path)


def summarize_for_context(text: str, limit: int = 1200) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    picked: list[str] = []
    for line in lines:
        if line.startswith("#") or any(key in line for key in ("结论", "异常", "建议", "复查", "风险", "summary", "Summary")):
            picked.append(line)
        if len("\n".join(picked)) >= limit:
            break
    if len("\n".join(picked)) < min(limit, 400):
        picked.extend(lines[:18])
    return "\n".join(dict.fromkeys(picked))[:limit]


def context_asset_text(conn: Any, asset: dict[str, Any]) -> tuple[str, str, str, str]:
    mode = str(asset.get("insert_mode") or asset.get("default_include_mode") or "summary")
    if mode not in {"summary", "full_text", "selected_sections", "citation_only", "manual_edited"}:
        mode = "summary"
    title = str(asset.get("display_name") or asset.get("title") or "context")
    source_path = str(asset.get("file_path") or "")
    ref_type = str(asset.get("ref_type") or asset.get("asset_type") or "project_file")
    ref_id = str(asset.get("asset_ref_id") or asset.get("ref_id") or asset.get("id") or "")

    if ref_type == "manual_text" or asset.get("manual_text"):
        return title, str(asset.get("manual_text") or "")[:MAX_CONTEXT_ASSET_CHARS], "manual_text", ref_id
    if mode == "selected_sections" and str(asset.get("selected_text") or "").strip():
        return title, str(asset.get("selected_text")).strip()[:MAX_CONTEXT_ASSET_CHARS], ref_type, ref_id

    text = ""
    if ref_type == "period_report" or str(ref_id).startswith("period_report:"):
        rid = str(ref_id).split(":", 1)[-1]
        row = conn.execute("SELECT * FROM period_reports WHERE id = ?", (rid,)).fetchone()
        if row is not None:
            title = row["title"]
            text = row["report_markdown"] or ""
            source_path = row["markdown_path"] or row["docx_path"] or ""
            ref_id = str(row["id"])
            ref_type = "period_report"
    elif str(ref_id).startswith("project_asset:"):
        aid = str(ref_id).split(":", 1)[-1]
        row = conn.execute("SELECT * FROM project_assets WHERE id = ?", (aid,)).fetchone()
        if row is not None:
            item = project_asset_from_row(row)
            title = item["display_name"]
            source_path = item.get("file_path") or source_path
            ref_id = str(row["id"])
            ref_type = "project_asset"

    if not text and source_path:
        path = resolve_allowed_path(source_path)
        if path.is_file():
            if path.suffix.lower() == ".docx":
                md_path, text = ensure_docx_markdown(path)
                source_path = str(md_path)
            else:
                text = read_text_file(path)
            if ref_type not in {"period_report", "project_asset"}:
                ref_type = "project_file"

    if mode == "citation_only":
        text = f"{title}\nsource: {display_path(source_path)}"
    elif mode == "summary":
        text = summarize_for_context(text)
    return title, text[:MAX_CONTEXT_ASSET_CHARS], ref_type, ref_id


def build_project_context(
    conn: Any,
    context_assets: list[dict[str, Any]] | None,
    manual_context_text: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    sections: list[str] = []
    refs: list[dict[str, Any]] = []
    total = 0
    assets = list(context_assets or [])[:MAX_CONTEXT_ASSETS]
    if manual_context_text and manual_context_text.strip():
        assets.append(
            {
                "ref_type": "manual_text",
                "insert_mode": "manual_edited",
                "display_name": "人工编辑上下文",
                "manual_text": manual_context_text,
            }
        )
    for asset in assets:
        try:
            title, text, ref_type, ref_id = context_asset_text(conn, asset)
        except Exception as exc:  # noqa: BLE001
            title = str(asset.get("display_name") or asset.get("title") or "context")
            text = f"[context asset skipped: {exc}]"
            ref_type = str(asset.get("ref_type") or "project_file")
            ref_id = str(asset.get("id") or "")
        if not text.strip():
            continue
        remaining = MAX_CONTEXT_TOTAL_CHARS - total
        if remaining <= 0:
            break
        text = text[:remaining]
        mode = str(asset.get("insert_mode") or asset.get("default_include_mode") or "summary")
        sections.append(f"【项目资料：{title}｜{mode}】\n{text}")
        refs.append(
            {
                "ref_type": ref_type if ref_type in {"period_report", "project_asset", "project_file", "manual_text"} else "project_file",
                "ref_id": ref_id,
                "insert_mode": "manual_edited" if mode == "manual_edited" else mode,
                "inserted_title": title,
                "inserted_text": text[:4000],
                "source_path": str(asset.get("file_path") or ""),
            }
        )
        total += len(text)
    if not sections:
        return "", []
    return "\n\n".join(sections), refs


def report_attachments_to_context_assets(conn: Any, attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        if str(attachment.get("type") or attachment.get("asset_type") or "") != "report":
            continue
        report_instance_id = attachment.get("report_instance_id") or attachment.get("reportInstanceId")
        period_report_id = attachment.get("period_report_id") or attachment.get("periodReportId")
        if report_instance_id:
            row = conn.execute("SELECT period_report_id FROM report_instance WHERE id = ?", (int(report_instance_id),)).fetchone()
            if row is not None:
                period_report_id = row["period_report_id"]
        if not period_report_id:
            continue
        prow = conn.execute("SELECT * FROM period_reports WHERE id = ?", (int(period_report_id),)).fetchone()
        if prow is None:
            continue
        out.append(
            {
                "asset_type": "period_report",
                "asset_ref_id": str(prow["id"]),
                "insert_mode": str(attachment.get("insert_mode") or attachment.get("mode") or "summary"),
                "display_name": prow["title"],
                "title": prow["title"],
                "file_path": prow["markdown_path"] or prow["docx_path"] or "",
            }
        )
    return out


def insert_context_refs(
    conn: Any,
    conversation_id: str,
    message_id: int,
    project_id: int | None,
    refs: list[dict[str, Any]],
) -> None:
    ts = iso_now()
    for ref in refs:
        mode = ref.get("insert_mode") if ref.get("insert_mode") in {
            "summary",
            "full_text",
            "selected_sections",
            "citation_only",
            "manual_edited",
        } else "summary"
        conn.execute(
            """
            INSERT INTO qa_message_context_refs(
                conversation_id, message_id, project_id, ref_type, ref_id,
                insert_mode, inserted_title, inserted_text, source_path, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                message_id,
                project_id,
                ref.get("ref_type") or "project_file",
                str(ref.get("ref_id") or ""),
                mode,
                ref.get("inserted_title"),
                ref.get("inserted_text"),
                ref.get("source_path"),
                ts,
            ),
        )


def chinese_int(text: str) -> int | None:
    table = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    return table.get(text)


SPOKEN_MCP_FILLER_TERMS = (
    "麻烦你",
    "麻烦",
    "请帮我",
    "帮我",
    "给我",
    "告诉我",
    "说一下",
    "看一下",
    "查一下",
    "问一下",
    "看下",
    "查下",
    "一下子",
    "一下",
    "现在",
    "当前",
    "此刻",
    "这会儿",
    "这个",
    "那个",
    "大概",
    "是不是",
    "有没有",
    "是多少",
    "多少",
    "如何",
    "怎样",
    "怎么样",
    "咋样",
    "的",
)


SPOKEN_MCP_VARIABLE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("P_top_gas_A", ("a点上升管煤气压力", "a上升管煤气压力", "上升管煤气压力a", "a管煤气压力")),
    ("P_top_gas_B", ("b点上升管煤气压力", "b上升管煤气压力", "上升管煤气压力b", "b管煤气压力")),
    ("P_top_gas_C", ("c点上升管煤气压力", "c上升管煤气压力", "上升管煤气压力c", "c管煤气压力")),
    ("P_top_gas_D", ("d点上升管煤气压力", "d上升管煤气压力", "上升管煤气压力d", "d管煤气压力")),
    ("T_top_A", ("a点上升管煤气温度", "a上升管煤气温度", "上升管煤气温度a", "炉顶a点温度", "a点顶温")),
    ("T_top_B", ("b点上升管煤气温度", "b上升管煤气温度", "上升管煤气温度b", "炉顶b点温度", "b点顶温")),
    ("T_top_C", ("c点上升管煤气温度", "c上升管煤气温度", "上升管煤气温度c", "炉顶c点温度", "c点顶温")),
    ("T_top_D", ("d点上升管煤气温度", "d上升管煤气温度", "上升管煤气温度d", "炉顶d点温度", "d点顶温")),
    ("T_throat_A", ("a点炉喉温度", "炉喉温度a", "a炉喉温度")),
    ("T_throat_B", ("b点炉喉温度", "炉喉温度b", "b炉喉温度")),
    ("T_throat_C", ("c点炉喉温度", "炉喉温度c", "c炉喉温度")),
    ("T_throat_D", ("d点炉喉温度", "炉喉温度d", "d炉喉温度")),
    ("TFT", ("理论燃烧温度", "理论燃温", "燃烧理论温度")),
    ("P_blast_cold", ("冷风管道压力", "冷风主管压力", "冷风压力")),
    ("PCI_set", ("喷煤设定值", "喷煤设定", "设定喷煤量", "一小时喷煤重量设定")),
    ("Q_O2", ("富氧流量", "氧气流量", "供氧流量")),
    ("O2_rate", ("富氧率", "富氧比例", "富氧百分比")),
    ("T_taphole_1", ("1号出铁口温度", "一号出铁口温度", "1#出铁口温度")),
    ("T_taphole_2", ("2号出铁口温度", "二号出铁口温度", "2#出铁口温度")),
    ("L_south", ("南探尺", "南尺", "南料线", "南侧探尺", "南边探尺")),
    ("L_north", ("北探尺", "北尺", "北料线", "北侧探尺", "北边探尺")),
    ("Hopper_weight", ("称量罐实际重量", "称量罐重量", "称量罐罐重", "罐重")),
    ("P_static_lower_mean", ("20.35米静压力", "20米35静压力", "下部静压力")),
    ("P_static_middle_mean", ("23.49米静压力", "23米49静压力", "中部静压力")),
    ("P_static_upper_mean", ("28.98米静压力", "28米98静压力", "上部静压力")),
    ("CO_top", ("炉顶一氧化碳", "炉顶co", "一氧化碳")),
    ("CO2_top", ("炉顶二氧化碳", "炉顶co2", "二氧化碳")),
    ("H2_top", ("炉顶氢气", "炉顶h2", "氢气")),
    (
        "T_top",
        (
            "t_top",
            "ttop",
            "炉顶温度",
            "炉顶温",
            "顶温",
            "炉顶平均温度",
            "综合顶温",
            "综合炉顶温",
            "综合炉顶温度",
            "炉顶煤气温度",
            "顶部温度",
            "上升管温度",
            "上升管温度平均",
            "上升管煤气温度",
            "上升管煤气温度平均",
        ),
    ),
    (
        "P_top",
        (
            "p_top",
            "ptop",
            "炉顶压力",
            "炉顶压",
            "顶压",
            "综合顶压",
            "综合炉顶压力",
            "炉顶煤气压力",
            "煤气顶压",
            "顶部压力",
        ),
    ),
    ("P_blast", ("p_blast", "热风压力", "风压", "送风压力", "鼓风压力")),
    ("T_blast", ("t_blast", "热风温度", "风温", "送风温度", "鼓风温度")),
    ("Q_blast", ("q_blast", "风量", "送风量", "冷风流量", "热风流量", "鼓风量")),
    ("PI", ("透气性指数", "透气性", "透气", "炉子透气", "炉况顺不顺", "顺不顺", "pi")),
    ("DP_upper", ("上部压差", "上压差", "上压")),
    ("DP_lower", ("下部压差", "下压差", "下压")),
    ("DP_total", ("全炉压差", "总压差", "压差", "炉内压差", "总体压差")),
    ("GasUtil", ("煤气利用率", "煤气利用", "煤气利用情况", "煤气利用水平")),
    ("PCI_rate", ("喷煤量", "喷煤率", "实际喷煤", "煤量", "pci_rate")),
    ("L", ("料线", "平均料线", "料面", "料位")),
)

QA_MCP_STANDARD_VARIABLES: tuple[str, ...] = tuple(variable for variable, _ in SPOKEN_MCP_VARIABLE_ALIASES)

QA_MCP_DIRECT_TOOL_TERMS = (
    "日报",
    "周报",
    "月报",
    "时报",
    "报表",
    "历史问答",
    "问答记录",
    "历史回答",
    "之前问过",
    "以前问过",
    "曾经问过",
    "list_recent_reports",
    "read_report_excerpt",
    "search_qa_messages",
)


def normalize_spoken_question(question: str) -> str:
    text = str(question or "").lower()
    text = re.sub(r"\s+", "", text)
    replacements = (
        ("炉顶的温度", "炉顶温度"),
        ("炉顶的压力", "炉顶压力"),
        ("顶上的温度", "炉顶温度"),
        ("顶上的压力", "炉顶压力"),
        ("综合的顶温", "综合顶温"),
        ("综合的顶压", "综合顶压"),
        ("煤气利用怎么样", "煤气利用率"),
        ("炉子顺不顺", "炉况顺不顺"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    for filler in SPOKEN_MCP_FILLER_TERMS:
        text = text.replace(filler, "")
    return text


def qa_mcp_duration_minutes(question: str) -> int | None:
    text = question.strip()
    user_text = text.split("\n[服务端对话状态：", 1)[0]
    if "半小时" in user_text:
        return 30
    explicit = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(h|小时|分钟|min|天)", user_text, flags=re.I)
    if explicit:
        value = float(explicit.group(1))
        unit = explicit.group(2).lower()
        if unit in {"h", "小时"}:
            return max(1, int(value * 60))
        if unit in {"分钟", "min"}:
            return max(1, int(value))
        if unit == "天":
            return max(1, int(value * 24 * 60))
    explicit_zh = re.search(r"([一二两三四五六七八九十])\s*(小时|分钟|天)", user_text)
    if explicit_zh:
        value = chinese_int(explicit_zh.group(1))
        if value is not None:
            unit = explicit_zh.group(2)
            if unit == "小时":
                return value * 60
            if unit == "分钟":
                return value
            if unit == "天":
                return value * 24 * 60
    # Follow-ups are commonly phrased as "换成两小时" without 最近/过去.
    # Parse the first explicit duration in the user's text before any private
    # routing suffix carrying the previously inherited time window.
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(h|小时|分钟|min|天)", text, flags=re.I)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit in {"h", "小时"}:
            return max(1, int(value * 60))
        if unit in {"分钟", "min"}:
            return max(1, int(value))
        if unit == "天":
            return max(1, int(value * 24 * 60))
    match = re.search(r"([一二两三四五六七八九十])\s*(小时|分钟|天)", text)
    if match:
        value = chinese_int(match.group(1))
        if value is not None:
            unit = match.group(2)
            if unit == "小时":
                return value * 60
            if unit == "分钟":
                return value
            if unit == "天":
                return value * 24 * 60
    if "半小时" in text:
        return 30
    match = re.search(r"(?:最近|近|过去)\s*(\d+(?:\.\d+)?)\s*(h|小时|分钟|min|天)", text, flags=re.I)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit in {"h", "小时"}:
            return max(1, int(value * 60))
        if unit in {"分钟", "min"}:
            return max(1, int(value))
        if unit == "天":
            return max(1, int(value * 24 * 60))
    match = re.search(r"(?:最近|近|过去)\s*([一二两三四五六七八九十])\s*(小时|分钟|天)", text)
    if match:
        value = chinese_int(match.group(1))
        if value is None:
            return None
        unit = match.group(2)
        if unit == "小时":
            return value * 60
        if unit == "分钟":
            return value
        if unit == "天":
            return value * 24 * 60
    if any(word in text for word in ["最近", "近一段", "近期"]) and any(word in text for word in ["趋势", "变化", "走势"]):
        return 60
    return None


def qa_mcp_body_temperature_variables(question: str) -> list[str]:
    """Expand body-temperature colloquialisms into concrete 7-16 layer/A-H sensor IDs."""
    text = str(question or "")
    symbolic = re.findall(r"(?i)(?<![a-z0-9_])t_body_l(7|8|9|10|11|12|13|14|15|16)_([a-h])(?![a-z0-9_])", text)
    if symbolic:
        return list(dict.fromkeys(f"T_body_L{int(layer)}_{position.upper()}" for layer, position in symbolic))
    body_terms = ("炉体温度", "炉身温度", "炉温", "炉墙温度", "炉壳温度", "炉身炉腹炉缸")
    if not any(term in text for term in body_terms):
        return []

    layers: list[int] = []
    for match in re.finditer(r"(?<!\d)([7-9]|1[0-6])\s*(?:到|至|-|—|－)\s*([7-9]|1[0-6])\s*层", text):
        first, last = int(match.group(1)), int(match.group(2))
        step = 1 if first <= last else -1
        layers.extend(range(first, last + step, step))
    layers.extend(int(value) for value in re.findall(r"(?<!\d)([7-9]|1[0-6])\s*层", text))
    layers = list(dict.fromkeys(layer for layer in layers if 7 <= layer <= 16))
    if not layers:
        return []

    positions: list[str] = []
    for match in re.finditer(r"(?i)(?<![a-z])([a-h])\s*(?:到|至|-|—|－)\s*([a-h])(?![a-z])", text):
        first, last = ord(match.group(1).upper()), ord(match.group(2).upper())
        step = 1 if first <= last else -1
        positions.extend(chr(code) for code in range(first, last + step, step))
    if not positions:
        positions.extend(letter.upper() for letter in re.findall(r"(?i)(?<![a-z])([a-h])(?=\s*(?:点|方位|、|，|,|和|与|及|各点|炉体温度|炉身温度|炉温))", text))
        positions.extend(letter.upper() for letter in re.findall(r"(?i)层\s*([a-h])", text))
    positions = list(dict.fromkeys(position for position in positions if position in "ABCDEFGH"))
    if not positions:
        positions = list("ABCDEFGH")
    return [f"T_body_L{layer}_{position}" for layer in layers for position in positions]


def qa_mcp_body_temperature_variable(question: str) -> str | None:
    variables = qa_mcp_body_temperature_variables(question)
    return variables[0] if variables else None


def qa_mcp_catalog_variables(question: str) -> list[str]:
    """Resolve arbitrary configured sensor IDs and unique catalog labels mentioned in a question."""
    original = str(question or "")
    normalized = normalize_spoken_question(original)
    try:
        mcp = load_mcp_data_module()
        catalog = list(getattr(mcp, "VARIABLES", []) or [])
    except Exception:
        return []
    generic_terms = {
        "温度", "压力", "流量", "变量", "传感器", "点位", "当前值", "实际值", "设定值",
        "炉体温度", "炉身温度", "上升管温度", "上升管压力",
    }
    matches: list[tuple[int, int, str]] = []
    for item in catalog:
        variable_name = str(item.get("variable_name") or "").strip()
        if not variable_name:
            continue
        exact = re.search(rf"(?i)(?<![a-z0-9_]){re.escape(variable_name)}(?![a-z0-9_])", original)
        if exact:
            matches.append((exact.start(), -len(variable_name), variable_name))
            continue
        fields = (
            item.get("short_name"),
            item.get("point_id"),
            item.get("tag_long_name"),
            item.get("description"),
        )
        for field in fields:
            term = normalize_spoken_question(str(field or ""))
            if len(term) < 3 or term in generic_terms:
                continue
            position = normalized.find(term)
            if position >= 0:
                matches.append((position, -len(term), variable_name))
                break
    out: list[str] = []
    for _, _, variable_name in sorted(matches):
        if variable_name not in out:
            out.append(variable_name)
    return out


def qa_mcp_direct_tool_intent(question: str) -> bool:
    text = str(question or "").lower()
    return any(term.lower() in text for term in QA_MCP_DIRECT_TOOL_TERMS)


def qa_mcp_exact_variables(question: str) -> list[str]:
    text = str(question or "").lower()
    matches: list[tuple[int, str]] = []
    for variable in QA_MCP_STANDARD_VARIABLES:
        match = re.search(rf"(?<![a-z0-9_]){re.escape(variable.lower())}(?![a-z0-9_])", text)
        if match:
            matches.append((match.start(), variable))
    return [variable for _, variable in sorted(matches)]


def qa_mcp_group_variables(question: str) -> list[str]:
    original = str(question or "").lower()
    normalized = normalize_spoken_question(question)
    variables: list[str] = []

    def add_group(items: tuple[str, ...]) -> None:
        for item in items:
            if item not in variables:
                variables.append(item)

    has_abcd = all(re.search(rf"(?<![a-z0-9_]){letter}(?![a-z0-9_])", original) for letter in "abcd")
    if "上升管煤气压力" in normalized and (has_abcd or "四个" in normalized or "各上升管" in normalized):
        add_group(("P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"))
    if "上升管煤气温度" in normalized and (has_abcd or "四个" in normalized or "各上升管" in normalized):
        add_group(("T_top_A", "T_top_B", "T_top_C", "T_top_D"))
    if "炉喉温度" in normalized and (has_abcd or "四个" in normalized or "各炉喉" in normalized):
        add_group(("T_throat_A", "T_throat_B", "T_throat_C", "T_throat_D"))
    if "出铁口温度" in normalized:
        if "1号" in original or "一号" in original or "1#" in original:
            add_group(("T_taphole_1",))
        if "2号" in original or "二号" in original or "2#" in original:
            add_group(("T_taphole_2",))
    static_pressure_intent = "静压力" in normalized or "静压" in normalized
    layer_pressure_intent = any(term in normalized for term in ("炉身下部", "炉身中部", "炉身上部", "炉腰")) and "压力" in normalized
    if static_pressure_intent or layer_pressure_intent:
        positions = list(dict.fromkeys(letter.upper() for letter in re.findall(
            r"(?i)(?<![a-z])([a-f])(?=\s*(?:点|方位|、|，|,|和|与|及|静压力))", original
        )))
        all_positions = (
            "a-f" in original or "a到f" in normalized or "a至f" in normalized
            or "六个" in normalized or "各点" in normalized or "各方位" in normalized
        )
        if all_positions:
            positions = list("ABCDEF")
        # 现场 HMI 层位口径：20350=炉身下部、23488=炉身中部、28976=炉身上部。
        # “炉腰”仅作为 pSpace 历史描述的兼容别名，仍指向 20350 层。
        height_groups = (
            (("20.35", "20米35", "20.350", "20350", "炉身下部", "炉腰"), "lower"),
            (("23.49", "23米49", "23.488", "23488", "炉身中部"), "middle"),
            (("28.98", "28米98", "28.976", "28976", "炉身上部"), "upper"),
        )
        for height_terms, level in height_groups:
            if any(term in original for term in height_terms) and positions:
                add_group(tuple(f"P_static_{level}_{position}" for position in positions))
        if any(term in original for term in ("20.35", "20米35", "20.350", "20350", "炉身下部", "炉腰")):
            if not positions:
                add_group(("P_static_lower_mean",))
        if any(term in original for term in ("23.49", "23米49", "23.488", "23488", "炉身中部")):
            if not positions:
                add_group(("P_static_middle_mean",))
        if any(term in original for term in ("28.98", "28米98", "28.976", "28976", "炉身上部")):
            if not positions:
                add_group(("P_static_upper_mean",))
    return variables


def qa_mcp_variables(question: str) -> list[str]:
    q = normalize_spoken_question(question)
    variables = qa_mcp_exact_variables(question)
    for body_variable in qa_mcp_body_temperature_variables(question):
        if body_variable not in variables:
            variables.append(body_variable)
    for variable in qa_mcp_group_variables(question):
        if variable not in variables:
            variables.append(variable)
    for variable in qa_mcp_catalog_variables(question):
        if variable not in variables:
            variables.append(variable)
    for variable, terms in SPOKEN_MCP_VARIABLE_ALIASES:
        if any(normalize_spoken_question(term) in q for term in terms) and variable not in variables:
            variables.append(variable)
    aggregate_suppressions = {
        "T_top": (("T_top_A", "T_top_B", "T_top_C", "T_top_D"), ("综合顶温", "平均顶温", "炉顶平均温度", "综合炉顶温度")),
        "P_top": (("P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"), ("综合顶压", "顶压平均", "炉顶平均压力")),
        "P_blast": (("P_blast_cold",), ("热风压力", "送风压力", "鼓风压力")),
        "L": (("L_south", "L_north"), ("平均料线", "总料线", "雷达料线", "雷达探尺")),
    }
    exact_variables = set(qa_mcp_exact_variables(question))
    for aggregate, (specifics, explicit_terms) in aggregate_suppressions.items():
        if aggregate not in variables or not any(item in variables for item in specifics):
            continue
        explicitly_requested = aggregate in exact_variables or any(
            normalize_spoken_question(term) in q for term in explicit_terms
        )
        if not explicitly_requested:
            variables.remove(aggregate)
    if "DP_total" in variables and any(variable in variables for variable in ("DP_upper", "DP_lower")):
        total_specific_terms = ("全炉压差", "总压差", "炉内压差", "总体压差")
        if not any(normalize_spoken_question(term) in q for term in total_specific_terms):
            variables.remove("DP_total")
    return variables


def qa_mcp_variable(question: str) -> str | None:
    variables = qa_mcp_variables(question)
    return variables[0] if variables else None


def qa_mcp_chart_plan(question: str) -> dict[str, Any] | None:
    """Build a deterministic MCP chart call from colloquial Chinese requests."""
    text = str(question or "")
    user_text = text.split("\n[服务端对话状态：", 1)[0]
    inherited_plot = "查询意图：plot" in text or "图表类型：" in text
    if not inherited_plot and not any(term in user_text for term in ("画", "图", "曲线", "可视化")):
        return None
    duration_minutes = qa_mcp_duration_minutes(text) or 60
    end_dt = datetime.now().astimezone().replace(second=0, microsecond=0)
    start_dt = end_dt - timedelta(minutes=duration_minutes)
    body_terms = ("炉体温度", "炉身", "炉腹", "炉缸", "炉刚", "炉墙温度", "炉壳温度")
    matrix_terms = ("热力矩阵", "温度矩阵", "矩阵图", "大矩阵", "每个小格", "每格")
    if any(term in text for term in body_terms) and any(term in text for term in matrix_terms):
        layer_match = re.search(r"(\d{1,2})\s*(?:到|至|-|—|－)\s*(\d{1,2})\s*层", text)
        start_layer = int(layer_match.group(1)) if layer_match else 7
        end_layer = int(layer_match.group(2)) if layer_match else 16
        if start_layer > end_layer:
            start_layer, end_layer = end_layer, start_layer
        lower_text = text.lower()
        position_match = re.search(r"(?<![a-z])([a-h])\s*(?:到|至|-|—|－)\s*([a-h])(?![a-z])", lower_text)
        if position_match:
            first_position, last_position = position_match.groups()
        elif "abcdefgh" in lower_text:
            first_position, last_position = "a", "h"
        else:
            first_position, last_position = "a", "f"
        first_code, last_code = ord(first_position), ord(last_position)
        step = 1 if first_code <= last_code else -1
        positions = [chr(code).upper() for code in range(first_code, last_code + step, step)]
        return {
            "tool": "plot_gl02_body_temperature_matrix",
            "arguments": {
                "start_time": start_dt.isoformat(timespec="seconds"),
                "end_time": end_dt.isoformat(timespec="seconds"),
                "start_layer": start_layer,
                "end_layer": end_layer,
                "positions": positions,
                "max_points_per_cell": min(720, max(60, duration_minutes + 5)),
                "title": f"GL02 炉体温度热力趋势矩阵（{start_layer}-{end_layer}层，{positions[0]}-{positions[-1]}方位）",
            },
        }
    variables = qa_mcp_variables(text)
    if not variables:
        return None
    common_args: dict[str, Any] = {
        "variables": variables,
        "start_time": start_dt.isoformat(timespec="seconds"),
        "end_time": end_dt.isoformat(timespec="seconds"),
    }
    theme = "dark" if any(term in text for term in ("深色", "暗色", "黑色背景")) else "industrial"
    scale = "zscore" if any(term in text.lower() for term in ("zscore", "z-score", "标准化")) else "raw"
    if any(term in text for term in ("归一化", "0-100", "形态对比")):
        scale = "minmax"

    chart_marker = re.search(r"图表类型：([a-z_]+)", text)
    chart_preference = chart_marker.group(1) if chart_marker else ""
    if chart_preference == "boxplot" or any(term in text for term in ("箱线图", "箱型图", "盒须图")):
        return {
            "tool": "plot_gl02_analysis",
            "arguments": {**common_args, "analysis_type": "boxplot", "scale": scale, "theme": theme},
        }
    if chart_preference == "distribution" or any(term in text for term in ("直方图", "分布图", "数据分布", "频数分布")):
        return {
            "tool": "plot_gl02_analysis",
            "arguments": {**common_args, "analysis_type": "distribution", "scale": scale, "theme": theme},
        }
    if chart_preference == "correlation_heatmap" or any(term in text for term in ("相关矩阵", "相关热力图", "相关性热力图")):
        return {
            "tool": "plot_gl02_analysis",
            "arguments": {**common_args, "analysis_type": "correlation_heatmap", "scale": scale, "theme": theme},
        }
    if chart_preference == "correlation_scatter" or any(term in text for term in ("相关散点", "关系散点", "相关性", "关系图", "散点图")):
        return {
            "tool": "plot_gl02_analysis",
            "arguments": {**common_args, "analysis_type": "correlation_scatter", "scale": scale, "theme": theme},
        }

    chart_type = "auto"
    chart_aliases = (
        ("双轴", "dual_axis"),
        ("分面", "small_multiples"),
        ("小图", "small_multiples"),
        ("面积图", "area"),
        ("阶梯图", "step"),
        ("散点", "scatter"),
    )
    for term, value in chart_aliases:
        if term in text:
            chart_type = value
            break
    average_match = re.search(r"(\d+)\s*点(?:移动平均|均线)", text)
    moving_average_points = int(average_match.group(1)) if average_match else 0
    arguments = {
        **common_args,
        "chart_type": chart_type,
        "scale": scale,
        "theme": theme,
        "moving_average_points": moving_average_points,
        "show_extrema": any(term in text for term in ("极值", "最高", "最低", "最大", "最小")),
        "show_latest": True,
    }
    return {"tool": "plot_gl02_trends", "arguments": arguments}


def qa_mcp_standard_analysis_plan(question: str) -> dict[str, Any] | None:
    """Build one composite analysis call for common multi-variable questions."""

    text = str(question or "")
    relationship_terms = ("相关", "相关性", "关系", "关联", "是否同步", "一起变化")
    if not any(term in text for term in relationship_terms):
        return None
    variables = qa_mcp_variables(text)
    if len(variables) < 2:
        return None
    duration_minutes = qa_mcp_duration_minutes(text) or 60
    end_dt = datetime.now().astimezone().replace(second=0, microsecond=0)
    start_dt = end_dt - timedelta(minutes=duration_minutes)
    analysis_type = "correlation_heatmap" if len(variables) > 2 else "correlation_scatter"
    return {
        "tool": "plot_gl02_analysis",
        "arguments": {
            "variables": variables,
            "start_time": start_dt.isoformat(timespec="seconds"),
            "end_time": end_dt.isoformat(timespec="seconds"),
            "analysis_type": analysis_type,
            "scale": "raw",
            "theme": "industrial",
            "title": f"GL02 最近{duration_minutes}分钟多变量相关性分析",
        },
    }


def qa_mcp_sensor_query_plan(question: str) -> dict[str, Any] | None:
    """Batch clear sensor requests without an extra LLM planning round."""

    text = str(question or "")
    variables = qa_mcp_variables(text)
    if not variables:
        return None
    intent_match = re.search(r"查询意图：(latest|history|statistics)", text)
    intent = intent_match.group(1) if intent_match else ""
    if not intent:
        if any(term in text for term in ("现在", "当前", "最新", "是多少", "多少")):
            intent = "latest"
        elif any(term in text for term in ("平均", "最高", "最低", "统计", "波动", "稳不稳")):
            intent = "statistics"
        elif any(term in text for term in ("历史", "趋势", "走势", "变化", "最近", "过去")):
            intent = "history"
    if not intent:
        return None
    arguments: dict[str, Any] = {
        "variables": variables,
        "query_type": "latest" if intent == "latest" else "statistics",
    }
    if intent != "latest":
        duration_minutes = qa_mcp_duration_minutes(text) or 60
        end_dt = datetime.now().astimezone().replace(second=0, microsecond=0)
        start_dt = end_dt - timedelta(minutes=duration_minutes)
        arguments.update(
            {
                "start_time": start_dt.isoformat(timespec="seconds"),
                "end_time": end_dt.isoformat(timespec="seconds"),
                "agg": "all",
            }
        )
    return {"tool": "query_gl02_sensors", "arguments": arguments}


def last_user_question(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
    return ""


def qa_mcp_planner_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create a compact planning context without furnace snapshots or RAG evidence."""

    system = (
        QA_MCP_BRIDGE_SYSTEM_PROMPT
        + f"\n当前本地时间：{datetime.now().astimezone().isoformat(timespec='seconds')}。"
        + "\n规划阶段只选择下一步必要工具；优先批量/复合工具，避免重复目录和重复数据查询。"
    )
    recent: list[dict[str, Any]] = []
    allowed_roles = {"user", "assistant", "tool"}
    for item in messages:
        if item.get("role") not in allowed_roles:
            continue
        compact = {key: value for key, value in item.items() if key in {"role", "name", "tool_calls", "content"}}
        content = compact.get("content")
        if isinstance(content, str) and len(content) > QA_MCP_PLANNER_MESSAGE_CHARS:
            compact["content"] = content[:QA_MCP_PLANNER_MESSAGE_CHARS] + "…"
        recent.append(compact)
    return [
        {"role": "system", "content": system},
        *recent[-max(1, QA_MCP_PLANNER_CONTEXT_MESSAGES) :],
    ]


def qa_mcp_tool_cache_key(tool_name: str, arguments: dict[str, Any]) -> str:
    normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    return f"{tool_name}:{normalized}"


def qa_mcp_tool_cache_get(tool_name: str, arguments: dict[str, Any]) -> str | None:
    if QA_MCP_TOOL_CACHE_TTL_SECONDS <= 0:
        return None
    key = qa_mcp_tool_cache_key(tool_name, arguments)
    with _QA_MCP_TOOL_CACHE_LOCK:
        item = _QA_MCP_TOOL_CACHE.get(key)
        if not item:
            return None
        created, result_text = item
        if time.monotonic() - created > QA_MCP_TOOL_CACHE_TTL_SECONDS:
            _QA_MCP_TOOL_CACHE.pop(key, None)
            return None
        return result_text


def qa_mcp_tool_cache_put(tool_name: str, arguments: dict[str, Any], result_text: str) -> None:
    if QA_MCP_TOOL_CACHE_TTL_SECONDS <= 0:
        return
    parsed = try_load_json(result_text)
    if isinstance(parsed, dict) and parsed.get("ok") is False:
        return
    key = qa_mcp_tool_cache_key(tool_name, arguments)
    with _QA_MCP_TOOL_CACHE_LOCK:
        _QA_MCP_TOOL_CACHE[key] = (time.monotonic(), result_text)
        if len(_QA_MCP_TOOL_CACHE) > 256:
            oldest = min(_QA_MCP_TOOL_CACHE, key=lambda item_key: _QA_MCP_TOOL_CACHE[item_key][0])
            _QA_MCP_TOOL_CACHE.pop(oldest, None)


def qa_is_current_furnace_context_question(question: str) -> bool:
    original = str(question or "").lower()
    normalized = normalize_spoken_question(question).lower()
    searchable = f"{original}\n{normalized}"
    furnace_context_words = (
        "炉况",
        "当前诊断",
        "最新诊断",
        "最近",
        "近期",
        "几个小时",
        "8小时",
        "八小时",
        "上一班",
        "下一班",
        "几点的数据",
        "数据新不新",
        "数据有没有滞后",
        "数据有没有缺点",
    )
    return any(word in searchable for word in furnace_context_words)


def parse_mcp_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def qa_mcp_prefetch(question: str) -> dict[str, Any]:
    if not QA_MCP_PREFETCH_ENABLED:
        return {"used": False, "reason": "disabled"}
    if qa_mcp_direct_tool_intent(question):
        return {"used": False, "reason": "direct_tool_intent"}
    variables = qa_mcp_variables(question)
    variable = variables[0] if variables else None
    duration_minutes = qa_mcp_duration_minutes(question)
    spoken_text = normalize_spoken_question(question)
    wants_data = any(
        word in question or word in spoken_text
        for word in [
            "趋势",
            "走势",
            "变化",
            "波动",
            "稳不稳",
            "平均",
            "最大",
            "最小",
            "最新",
            "现在",
            "当前",
            "告诉我",
            "给我说",
            "说一下",
            "看一下",
            "查一下",
            "看看",
            "查下",
            "问一下",
            "多少",
            "是多少",
            "在哪",
            "历史",
            "正常吗",
            "正不正常",
            "如何",
            "情况如何",
            "近况",
            "怎么样",
            "咋样",
            "高不高",
            "低不低",
        ]
    )
    if not variable or not wants_data:
        return {"used": False, "reason": "not_a_supported_data_query"}
    try:
        mcp = load_mcp_data_module()
        latest_by_variable = {
            item: mcp.get_latest_gl02_value(item, source_preference="database") for item in variables
        }
        compact_latest_by_variable = {}
        for item, result in latest_by_variable.items():
            meta = (result or {}).get("variable") or {}
            latest_row = (result or {}).get("latest") or {}
            compact_latest_by_variable[item] = {
                "ok": bool((result or {}).get("ok")),
                "variable_name": meta.get("variable_name") or item,
                "description": meta.get("description"),
                "unit": meta.get("unit"),
                "value": latest_row.get("value"),
                "ts": latest_row.get("ts"),
                "quality": latest_row.get("quality"),
                "error": (result or {}).get("error"),
                "message": (result or {}).get("message"),
            }
        if duration_minutes is None:
            duration_minutes = 0
        if duration_minutes <= 0:
            if len(variables) > 1:
                context_text = (
                    "【数据库查询结果】\n"
                    "查询类型：多变量最新值\n"
                    f"变量：{json.dumps(variables, ensure_ascii=False)}\n"
                    f"结果：{json.dumps(compact_latest_by_variable, ensure_ascii=False, default=str)[:18000]}"
                )
                return {
                    "used": True,
                    "kind": "multi_latest",
                    "variables": variables,
                    "latest_by_variable": latest_by_variable,
                    "context_text": context_text,
                }
            latest = latest_by_variable[variable]
            context_text = (
                "【数据库查询结果】\n"
                f"查询类型：最新值\n变量：{variable}\n"
                f"结果：{json.dumps(compact_latest_by_variable[variable], ensure_ascii=False, default=str)[:5000]}"
            )
            return {"used": True, "kind": "latest", "variable": variable, "latest": latest, "context_text": context_text}
        latest_timestamps = [
            parse_mcp_ts(((latest_by_variable[item] or {}).get("latest") or {}).get("ts"))
            for item in variables
        ]
        end_ts = max((item for item in latest_timestamps if item is not None), default=None)
        end_ts = end_ts or datetime.now().replace(second=0, microsecond=0)
        start_ts = end_ts - timedelta(minutes=duration_minutes)
        start_text = start_ts.strftime("%Y-%m-%d %H:%M:%S")
        end_text = end_ts.strftime("%Y-%m-%d %H:%M:%S")
        summaries: dict[str, dict[str, Any]] = {}
        for item in variables:
            stats = mcp.query_gl02_statistics(item, start_text, end_text, agg="all", source_preference="database")
            stat = stats.get("statistics") or {}
            first = stat.get("first") or {}
            last = stat.get("last") or {}
            first_value = first.get("value")
            last_value = last.get("value")
            delta = None
            trend = "无法判断"
            if isinstance(first_value, (int, float)) and isinstance(last_value, (int, float)):
                delta = float(last_value) - float(first_value)
                if abs(delta) < 1e-6:
                    trend = "基本持平"
                elif delta > 0:
                    trend = "上升"
                else:
                    trend = "下降"
            summaries[item] = {
                "tool": "query_gl02_statistics",
                "variable": item,
                "start_time": start_text,
                "end_time": end_text,
                "count": stat.get("count"),
                "avg": stat.get("avg"),
                "min": stat.get("min"),
                "max": stat.get("max"),
                "first": first,
                "last": last,
                "delta": delta,
                "trend": trend,
                "source": stats.get("source"),
            }
        if len(variables) > 1:
            context_text = (
                "【数据库查询结果】\n"
                "以下多变量统计来自同一个 PostgreSQL 只读时间窗，必须逐项比较，不得缺项或猜测。\n"
                f"{json.dumps(summaries, ensure_ascii=False, default=str)}"
            )
            return {
                "used": True,
                "kind": "multi_statistics",
                "variables": variables,
                "summaries": summaries,
                "context_text": context_text,
            }
        summary = summaries[variable]
        context_text = (
            "【数据库查询结果】\n"
            "以下内容由后台从 PostgreSQL 只读查询得到，"
            "回答数据库事实类问题时必须优先使用这些数值，不得用未核验历史记忆替代。\n"
            f"{json.dumps(summary, ensure_ascii=False, default=str)}"
        )
        return {"used": True, "kind": "statistics", "variable": variable, "summary": summary, "context_text": context_text}
    except Exception as exc:  # noqa: BLE001
        return {
            "used": False,
            "reason": "mcp_prefetch_failed",
            "error": str(exc),
            "variable": variable,
            "duration_minutes": duration_minutes,
        }


def qa_mcp_agent_planning_intent(question: str) -> bool:
    """Identify questions that benefit from model-planned, possibly multi-tool work."""

    text = normalize_spoken_question(question).lower()
    planning_keywords = (
        "分析",
        "比较",
        "对比",
        "关联",
        "相关",
        "相关性",
        "影响",
        "关系",
        "计算",
        "算一下",
        "统计",
        "一起看",
        "综合看",
        "结合",
        "同时",
        "并且",
        "然后",
        "画出来",
        "可视化",
        "矩阵",
        "热力",
        "分布",
        "箱线",
        "散点",
    )
    return any(keyword in text for keyword in planning_keywords)


def qa_mcp_should_use_tools(question: str, payload: dict[str, Any], mcp_prefetch: dict[str, Any]) -> bool:
    if not QA_MCP_TOOLS_ENABLED or QA_MCP_TOOL_MODE in {"0", "off", "false", "disabled", "none"}:
        return False
    forced = payload.get("use_mcp_tools")
    if forced is not None:
        return bool(forced)
    if QA_MCP_TOOL_MODE in {"1", "always", "force", "on"}:
        return True
    if qa_mcp_agent_planning_intent(question):
        return True
    if qa_mcp_direct_tool_intent(question):
        return True
    if qa_mcp_chart_plan(question) is not None:
        return True
    if (
        not (mcp_prefetch or {}).get("used")
        and qa_is_current_furnace_context_question(question)
        and not qa_mcp_variables(question)
    ):
        return False
    if qa_mcp_prefetch_is_complete(mcp_prefetch):
        full_tool_keywords = (
            "画",
            "图",
            "画图",
            "曲线",
            "趋势图",
            "对比图",
            "生成图",
            "报表",
            "导出",
            "多个变量",
            "多变量",
            "分别查询",
            "对比",
        )
        if not any(keyword in question for keyword in full_tool_keywords):
            return False
    if (mcp_prefetch or {}).get("used"):
        return True
    text = str(question or "").lower()
    spoken_text = normalize_spoken_question(question)
    for keyword in QA_MCP_INTENT_KEYWORDS:
        if keyword.lower() in text:
            return True
        normalized_keyword = normalize_spoken_question(keyword)
        if len(normalized_keyword) >= 2 and normalized_keyword in spoken_text:
            return True
    return False


def qa_mcp_prefetch_is_complete(mcp_prefetch: dict[str, Any] | None) -> bool:
    pack = mcp_prefetch or {}
    if not pack.get("used"):
        return False
    kind = str(pack.get("kind") or "")
    if kind == "latest":
        if not pack.get("variable"):
            return False
        latest = pack.get("latest") or {}
        row = latest.get("latest") if isinstance(latest, dict) else None
        return bool(isinstance(row, dict) and row.get("value") is not None and row.get("ts"))
    if kind == "statistics":
        if not pack.get("variable"):
            return False
        summary = pack.get("summary") or {}
        if not isinstance(summary, dict) or not summary.get("start_time") or not summary.get("end_time"):
            return False
        has_value = any(summary.get(key) is not None for key in ("avg", "min", "max", "first", "last", "delta"))
        return bool(summary.get("count") is not None and has_value)
    if kind == "multi_latest":
        variables = list(pack.get("variables") or [])
        rows = pack.get("latest_by_variable") or {}
        return bool(
            variables
            and all(
                isinstance((rows.get(item) or {}).get("latest"), dict)
                and (rows.get(item) or {}).get("latest", {}).get("value") is not None
                and (rows.get(item) or {}).get("latest", {}).get("ts")
                for item in variables
            )
        )
    if kind == "multi_statistics":
        variables = list(pack.get("variables") or [])
        summaries = pack.get("summaries") or {}
        return bool(
            variables
            and all(
                isinstance(summaries.get(item), dict)
                and summaries[item].get("start_time")
                and summaries[item].get("end_time")
                and summaries[item].get("count") is not None
                and any(summaries[item].get(key) is not None for key in ("avg", "min", "max", "first", "last", "delta"))
                for item in variables
            )
        )
    return False


def qa_messages_with_mcp_prompt(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [dict(item) for item in messages]
    if out and out[0].get("role") == "system":
        out[0]["content"] = str(out[0].get("content") or "") + "\n" + QA_MCP_BRIDGE_SYSTEM_PROMPT
        return out
    return [{"role": "system", "content": QA_MCP_BRIDGE_SYSTEM_PROMPT}, *out]


def mcp_tool_to_ollama_tool(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }


def normalize_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls") or []
    normalized = []
    for call in calls:
        fn = call.get("function") or {}
        name = fn.get("name") or call.get("name")
        args = fn.get("arguments") or call.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name:
            normalized.append({"name": name, "arguments": args if isinstance(args, dict) else {}})
    return normalized


def truncate_tool_text(text: str, max_chars: int = QA_MCP_MAX_RESULT_CHARS) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...（工具结果过长，已截断；原始长度 {len(text)} 字符）"


def mcp_result_to_text(result: Any) -> str:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return truncate_tool_text(json.dumps(structured, ensure_ascii=False, default=str))
    parts = []
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        parts.append(text if text is not None else str(content))
    return truncate_tool_text("\n".join(parts))


def try_load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def compact_tool_result_for_event(result_text: str) -> dict[str, Any]:
    parsed = try_load_json(result_text)
    if isinstance(parsed, dict):
        compact = dict(parsed)
        for key in ("data", "rows", "messages", "reports", "variables"):
            value = compact.get(key)
            if isinstance(value, list) and len(value) > 8:
                compact[key] = value[:5]
                compact[f"{key}_truncated_count"] = len(value) - 5
        text = json.dumps(compact, ensure_ascii=False, default=str)
        if len(text) <= 12000:
            return compact
    fallback: dict[str, Any] = {"text": result_text[:12000], "truncated": len(result_text) > 12000}
    image_match = re.search(r'"image_url"\s*:\s*"([^"\\]+(?:\\.[^"\\]*)*)"', result_text)
    if image_match:
        fallback["image_url"] = bytes(image_match.group(1), "utf-8").decode("unicode_escape")
    return fallback


def append_mcp_chart_links(answer: str, tool_trace: list[dict[str, Any]]) -> str:
    answer = str(answer or "")
    links: list[str] = []
    for item in tool_trace or []:
        result = item.get("result") if isinstance(item, dict) else None
        if not isinstance(result, dict):
            continue
        image_url = str(result.get("image_url") or "").strip()
        if image_url.startswith("/data/mcp_charts/") and image_url.lower().endswith(".png"):
            links.append(image_url)
    for image_url in dict.fromkeys(links):
        filename = re.escape(image_url.rsplit("/", 1)[-1])
        answer = re.sub(
            rf"/data/[^\s)\]}}>\"']*/{filename}",
            image_url,
            answer,
        )
    missing = [url for url in dict.fromkeys(links) if url not in answer]
    if not missing:
        return answer
    markdown = "\n".join(f"![MCP数据图]({url})" for url in missing)
    return (answer.rstrip() + "\n\n" + markdown).strip()


def deterministic_mcp_answer(tool_name: str, result_text: str) -> str:
    """Create a concise factual result for deterministic routes without another LLM round."""

    payload = try_load_json(result_text)
    if not isinstance(payload, dict):
        return ""
    if payload.get("ok") is False:
        return f"MCP查询失败：{payload.get('message') or payload.get('error') or '未知错误'}"

    def label(variable: Any) -> str:
        key = str(variable or "")
        return str(PROMPT_METRIC_ALIASES.get(key) or key)

    def number(value: Any) -> str:
        try:
            return f"{float(value):.3f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(value if value is not None else "无")

    if tool_name in {"plot_gl02_trends", "plot_gl02_analysis", "plot_gl02_body_temperature_matrix"}:
        variables = [str(item) for item in payload.get("variables") or [] if str(item)]
        lines = [
            f"已生成{('、'.join(label(item) for item in variables) or '所选变量')}的数据图。",
            f"时间范围：{payload.get('start_time') or '未提供'} 至 {payload.get('end_time') or '未提供'}。",
        ]
        correlation = ((payload.get("derived") or {}).get("correlation") or {})
        if isinstance(correlation, dict) and correlation.get("pearson_r") is not None:
            lines.append(
                "相关性："
                f"{label(correlation.get('left'))} 与 {label(correlation.get('right'))} "
                f"Pearson r={number(correlation.get('pearson_r'))}，"
                f"对齐样本 {correlation.get('aligned_count') or 0} 个。"
            )
        summaries: list[str] = []
        for series in payload.get("series") or []:
            if not isinstance(series, dict):
                continue
            summary = series.get("summary") or {}
            variable = series.get("requested_variable") or (series.get("variable") or {}).get("variable_name")
            last = summary.get("last") or {}
            if variable and isinstance(last, dict) and last.get("value") is not None:
                unit = str(
                    (series.get("variable") or {}).get("unit")
                    or PROMPT_METRIC_UNIT_FALLBACKS.get(str(variable))
                    or ""
                ).strip()
                summaries.append(
                    f"{label(variable)}当前/末值 {number(last.get('value'))}{unit}"
                    f"（{last.get('ts') or '时间未知'}）"
                )
        if summaries:
            lines.append("；".join(summaries[:8]) + "。")
        return "\n".join(lines)

    if tool_name == "query_gl02_sensors":
        lines = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            requested = item.get("requested_variable")
            if item.get("ok") is False:
                lines.append(f"{label(requested)}：{item.get('message') or item.get('error') or '无数据'}")
                continue
            variable = item.get("variable") or {}
            unit = str(variable.get("unit") or PROMPT_METRIC_UNIT_FALLBACKS.get(str(requested)) or "").strip()
            latest = item.get("latest") or {}
            statistics = item.get("statistics") or {}
            if isinstance(latest, dict) and latest.get("value") is not None:
                lines.append(
                    f"{label(requested)}：{number(latest.get('value'))}{unit}，"
                    f"数据时间 {latest.get('ts') or '未知'}"
                )
            elif isinstance(statistics, dict) and statistics:
                lines.append(
                    f"{label(requested)}：均值 {number(statistics.get('avg'))}{unit}，"
                    f"最低 {number(statistics.get('min'))}{unit}，"
                    f"最高 {number(statistics.get('max'))}{unit}，"
                    f"趋势 {statistics.get('trend') or '未知'}"
                )
        return "\n".join(lines)
    return ""


def call_ollama_chat_obj(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.1,
    max_tokens: int = 900,
) -> dict[str, Any]:
    payload = build_api_chat_payload(
        {
            "model": normalize_model(None),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": False,
            "stop": ["莿莿", "<|im_start|>", "<|im_end|>", "\nassistant", "\nuser"],
            "tools": tools or None,
        }
    )
    if tools:
        payload["tools"] = tools
    req = build_ollama_request("/api/chat", body=json_bytes(payload), stream=False)
    with urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


async def qa_mcp_tool_loop_async(
    messages: list[dict[str, Any]],
    emit: Any | None = None,
    stop_after_tool_round: bool = False,
    routing_question: str = "",
) -> dict[str, Any]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        return {
            "ok": False,
            "tool_used": False,
            "answer": "",
            "error": f"数据库查询 Python 依赖缺失：{exc}；当前解释器={sys.executable}，查询解释器={QA_MCP_PYTHON}",
        }

    if not MCP_DATA_SERVER_PATH.exists():
        return {"ok": False, "tool_used": False, "answer": "", "error": f"数据库查询服务不存在: {MCP_DATA_SERVER_PATH}"}

    env = dict(os.environ)
    server_params = StdioServerParameters(
        command=QA_MCP_PYTHON,
        args=[str(MCP_DATA_SERVER_PATH)],
        env=env,
    )
    working_messages = qa_messages_with_mcp_prompt(messages)
    trace: list[dict[str, Any]] = []
    execution_started = time.monotonic()

    def tool_timeout_seconds() -> float:
        remaining = QA_MCP_EXECUTION_BUDGET_SECONDS - (time.monotonic() - execution_started)
        if remaining <= 0:
            raise TimeoutError(f"MCP执行预算已用尽（{QA_MCP_EXECUTION_BUDGET_SECONDS:.0f}秒）")
        return max(0.1, min(QA_MCP_TOOL_TIMEOUT_SECONDS, remaining))

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            tools = [mcp_tool_to_ollama_tool(tool) for tool in tools_response.tools]
            tool_names = {tool.name for tool in tools_response.tools}
            tool_schemas = {tool.name: tool.inputSchema for tool in tools_response.tools}
            policy_limits = ToolPolicyLimits(
                max_argument_chars=max(1000, QA_MCP_MAX_ARGUMENT_CHARS),
                max_array_items=max(1, QA_MCP_MAX_ARRAY_ITEMS),
            )
            tool_call_count = 0

            question = routing_question or last_user_question(working_messages)
            chart_plan = qa_mcp_chart_plan(question)
            standard_plan = qa_mcp_standard_analysis_plan(question)
            sensor_plan = qa_mcp_sensor_query_plan(question)
            deterministic_plan = chart_plan or standard_plan or sensor_plan
            if deterministic_plan and deterministic_plan["tool"] in tool_names:
                name = deterministic_plan["tool"]
                args = deterministic_plan["arguments"]
                route = (
                    "deterministic_chart"
                    if chart_plan
                    else "standard_composite_analysis"
                    if standard_plan
                    else "deterministic_sensor_query"
                )
                policy = validate_tool_call(name, args, tool_schemas, policy_limits)
                if not policy["ok"]:
                    return {
                        "ok": False,
                        "tool_used": False,
                        "answer": "",
                        "error": f"确定性图表调用未通过工具策略校验：{policy['errors']}",
                        "tool_trace": [
                            {
                                "round": 0,
                                "route": route,
                                "tool": name,
                                "arguments": args,
                                "policy": policy,
                            }
                        ],
                    }
                tool_call_count += 1
                working_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": {"name": name, "arguments": args}}],
                    }
                )
                if emit:
                    emit("tool_start", {"tool": name, "arguments": args, "round": 0, "route": route})
                result_text = qa_mcp_tool_cache_get(name, args)
                cache_hit = result_text is not None
                if result_text is None:
                    try:
                        result = await asyncio.wait_for(
                            session.call_tool(name, args),
                            timeout=tool_timeout_seconds(),
                        )
                        result_text = mcp_result_to_text(result)
                        qa_mcp_tool_cache_put(name, args, result_text)
                    except Exception as exc:  # noqa: BLE001
                        result_text = json.dumps(
                            {"ok": False, "error": type(exc).__name__, "message": str(exc), "tool": name},
                            ensure_ascii=False,
                        )
                working_messages.append({"role": "tool", "name": name, "content": result_text})
                trace_item = {
                    "round": 0,
                    "route": route,
                    "tool": name,
                    "arguments": args,
                    "cache_hit": cache_hit,
                    "policy": {"ok": True, "policy": policy["policy"]},
                    "result": compact_tool_result_for_event(result_text),
                }
                trace.append(trace_item)
                if emit:
                    emit("tool_result", trace_item)
                if stop_after_tool_round:
                    return {
                        "ok": True,
                        "tool_used": True,
                        "needs_final": True,
                        "messages": working_messages,
                        "tool_trace": trace,
                    }
                direct_answer = deterministic_mcp_answer(name, result_text)
                if direct_answer:
                    return {
                        "ok": True,
                        "tool_used": True,
                        "answer": direct_answer,
                        "messages": working_messages,
                        "tool_trace": trace,
                        "answer_route": "deterministic_formatter",
                    }
                response = call_ollama_chat_obj(working_messages, tools=None)
                answer = clean_llm_output((response.get("message") or {}).get("content") or response.get("response") or "")
                return {
                    "ok": True,
                    "tool_used": True,
                    "answer": answer,
                    "messages": working_messages,
                    "tool_trace": trace,
                }

            for round_index in range(max(1, QA_MCP_MAX_TOOL_ROUNDS)):
                planner_messages = qa_mcp_planner_messages(working_messages)
                response = call_ollama_chat_obj(
                    planner_messages,
                    tools=tools,
                    temperature=QA_MCP_PLANNER_TEMPERATURE,
                    max_tokens=QA_MCP_PLANNER_MAX_TOKENS,
                )
                message = dict(response.get("message") or {})
                message.setdefault("role", "assistant")
                tool_calls = normalize_tool_calls(message)
                if not tool_calls:
                    answer = clean_llm_output(message.get("content") or response.get("response") or "")
                    return {
                        "ok": True,
                        "tool_used": bool(trace),
                        "answer": answer,
                        "messages": working_messages,
                        "tool_trace": trace,
                    }

                working_messages.append(message)
                for tool_call in tool_calls:
                    name = tool_call["name"]
                    args = tool_call["arguments"]
                    tool_call_count += 1
                    if emit:
                        emit("tool_start", {"tool": name, "arguments": args, "round": round_index + 1})
                    if tool_call_count > max(1, QA_MCP_MAX_TOOL_CALLS):
                        policy = {
                            "ok": False,
                            "error": "TOOL_CALL_LIMIT_EXCEEDED",
                            "tool": name,
                            "errors": [
                                {
                                    "code": "TOOL_CALL_LIMIT_EXCEEDED",
                                    "path": "tool_calls",
                                    "message": f"单次问答最多调用 {QA_MCP_MAX_TOOL_CALLS} 次工具",
                                }
                            ],
                        }
                    else:
                        policy = validate_tool_call(name, args, tool_schemas, policy_limits)
                    if not policy["ok"]:
                        result_text = json.dumps(
                            {
                                "ok": False,
                                "error": "TOOL_POLICY_REJECTED",
                                "tool": name,
                                "policy_errors": policy["errors"],
                                "message": "请根据当前工具 JSON Schema 修正工具名或参数后重试。",
                            },
                            ensure_ascii=False,
                        )
                    else:
                        result_text = qa_mcp_tool_cache_get(name, args)
                        cache_hit = result_text is not None
                        if result_text is None:
                            try:
                                result = await asyncio.wait_for(
                                    session.call_tool(name, args),
                                    timeout=tool_timeout_seconds(),
                                )
                                result_text = mcp_result_to_text(result)
                                qa_mcp_tool_cache_put(name, args, result_text)
                            except Exception as exc:  # noqa: BLE001
                                result_text = json.dumps(
                                    {"ok": False, "error": type(exc).__name__, "message": str(exc), "tool": name},
                                    ensure_ascii=False,
                                )
                    if not policy["ok"]:
                        cache_hit = False
                    working_messages.append({"role": "tool", "name": name, "content": result_text})
                    event_result = compact_tool_result_for_event(result_text)
                    trace_item = {
                        "round": round_index + 1,
                        "route": "model_planner",
                        "tool": name,
                        "arguments": args,
                        "cache_hit": cache_hit,
                        "policy": {
                            "ok": policy["ok"],
                            "policy": policy.get("policy"),
                            "errors": policy.get("errors") or [],
                        },
                        "result": event_result,
                    }
                    trace.append(trace_item)
                    if emit:
                        emit("tool_result", trace_item)
                    if tool_call_count >= max(1, QA_MCP_MAX_TOOL_CALLS):
                        break

                if stop_after_tool_round:
                    return {
                        "ok": True,
                        "tool_used": True,
                        "needs_final": True,
                        "messages": working_messages,
                        "tool_trace": trace,
                    }

    return {
        "ok": False,
        "tool_used": bool(trace),
        "answer": "数据库查询轮数超过上限，请缩小问题范围或明确变量名。",
        "messages": working_messages,
        "tool_trace": trace,
    }


def run_qa_mcp_tool_loop(
    messages: list[dict[str, Any]],
    emit: Any | None = None,
    stop_after_tool_round: bool = False,
    routing_question: str = "",
) -> dict[str, Any]:
    return asyncio.run(
        qa_mcp_tool_loop_async(
            messages,
            emit=emit,
            stop_after_tool_round=stop_after_tool_round,
            routing_question=routing_question,
        )
    )


def qa_should_search_knowledge(question: str, mcp_prefetch: dict[str, Any] | None = None) -> tuple[bool, str]:
    if not QA_KNOWLEDGE_INTENT_GATE:
        return True, "intent_gate_disabled"
    text = normalize_spoken_question(question)
    lower = text.lower()
    original_lower = str(question or "").lower()
    searchable = f"{original_lower}\n{lower}"
    if (mcp_prefetch or {}).get("used"):
        return False, "data_prefetch_already_used"
    fixed_prefix_words = (
        "你是谁",
        "你能做什么",
        "哪些事情不能",
        "系统提示词",
        "内部提示词",
        "隐藏指令",
        "隐藏规则",
        "隐藏上下文",
        "内部规则",
        "内部推理",
        "数据库密码",
        "环境变量",
        "文件路径",
        "base64",
        "忽略前面的",
    )
    if any(word in searchable for word in fixed_prefix_words):
        return False, "fixed_prefix_identity_or_safety_question"
    status_words = ("在线", "可用", "状态", "服务", "ping", "hello", "你好", "在吗", "是否在线")
    if len(text) <= 32 and any(word in searchable for word in status_words):
        return False, "short_status_or_greeting"
    explicit_knowledge_words = (
        "知识库",
        "文档",
        "手册",
        "引用",
        "来源",
        "原理",
        "为什么",
        "规则",
        "阈值",
        "制度",
        "基线",
        "机理",
    )
    if any(word in searchable for word in explicit_knowledge_words):
        return True, "knowledge_intent"
    data_words = (
        "当前",
        "最新",
        "实时",
        "现在",
        "多少",
        "查询",
        "趋势",
        "曲线",
        "历史",
        "统计",
        "平均",
        "最大",
        "最小",
        "p_top",
        "dp_",
        "gasutil",
        "t_top",
        "pci",
    )
    if any(word in searchable for word in data_words):
        return False, "data_or_metric_question"
    if qa_is_current_furnace_context_question(question):
        return False, "current_furnace_context_question"
    general_knowledge_words = (
        "说明",
        "依据",
        "原因",
        "如何",
        "怎么",
        "报警",
        "告警",
        "含义",
        "解释",
        "工艺",
        "方案",
    )
    if any(word in searchable for word in general_knowledge_words):
        return True, "knowledge_intent"
    return True, "default_knowledge_search"


def qa_search_knowledge(question: str, mode: str | None = None, mcp_prefetch: dict[str, Any] | None = None) -> dict[str, Any]:
    if not QA_KNOWLEDGE_ENABLED:
        return {"enabled": False, "evidence": [], "message": "知识库检索已关闭"}
    should_search, reason = qa_should_search_knowledge(question, mcp_prefetch)
    if not should_search:
        return {
            "enabled": False,
            "evidence": [],
            "message": f"知识库检索已按意图跳过：{reason}",
            "intent": {"intent_type": reason, "skipped": True},
        }
    return search_knowledge(
        question,
        db_path=QA_KNOWLEDGE_DB_PATH,
        top_k=QA_KNOWLEDGE_TOP_K,
        mode=mode or QA_KNOWLEDGE_SEARCH_MODE,
    )


def build_hidden_qa_messages(
    question: str,
    snapshots: list[dict[str, Any]],
    history: list[dict[str, Any]],
    project_context: str = "",
    mcp_context: str = "",
    context_meta: dict[str, Any] | None = None,
    knowledge_context: str = "",
) -> list[dict[str, str]]:
    recent_history = [
        {"role": item["role"], "content": str(item["content"])[:700]}
        for item in history[-8:]
        if item.get("role") in {"user", "assistant"}
    ]
    meta = dict(context_meta or {})
    hidden = snapshot_summary_for_prompt(snapshots, meta)
    context_mode = str(meta.get("context_mode") or "full_8h_baseline")
    if context_mode == "delta_since_previous_question":
        context_intro = (
            "炉况摘要如下，为本对话上次提问之后新增的快照；"
            "此前 8 小时基线不再重复发送，可结合近期对话历史理解延续趋势。"
        )
    elif context_mode == "latest_only_no_new_snapshot":
        context_intro = (
            "炉况摘要如下。本对话上次提问之后尚无新增快照，因此只提供最新快照用于确认当前状态。"
        )
    elif context_mode == "latest_snapshot_plus_pg_8h_trend":
        context_intro = (
            "炉况资料如下：当前状态来自本轮最新炉况快照；8小时演化来自生产5分钟诊断点，"
            "正文只展示抽样时间线。"
            "回答当前炉况优先看最新状态，回答趋势再看生产诊断时间线；"
            "如果用户问与上一轮相比，必须按状态锚点时间比较，不要把生产时间线中的上一条诊断误当成上一轮提问。"
        )
    else:
        context_intro = "炉况摘要如下，压缩自最近 8 小时炉况快照，最多保留 10 条炉况/调控时间线。"
    selected_project_context = (
        "\n【本轮主动选择的项目/报表资料】\n"
        "以下资料只能作为补充依据，不要声称系统自动选择了这些资料：\n"
        f"{project_context}"
        if project_context
        else ""
    )
    hidden_block = (
        f"{context_intro}"
        "只吸收其中结论和现场可核查证据，不要向用户说明资料组织方式，也不要输出原始状态文本。\n"
        f"{hidden}"
    )
    system_prompt = QA_SYSTEM_PROMPT_TEMPLATE.format(
        hidden=hidden_block,
        project_rules=QA_PROJECT_RULES_BLOCK,
        selected_project_context=selected_project_context,
        mcp_context=mcp_context or "本轮未执行数据库预查询。",
        knowledge_context=knowledge_context or "本轮未检索到可用知识库证据。",
    )
    return [
        {"role": "system", "content": system_prompt},
        *recent_history,
        {"role": "user", "content": f"高炉长问题：{question}"},
    ]


def call_ollama_chat(messages: list[dict[str, str]], temperature: float = 0.1, max_tokens: int = 900) -> str:
    payload = build_api_chat_payload(
        {
            "model": normalize_model(None),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": False,
            "stop": ["莿莿", "<|im_start|>", "<|im_end|>", "\nassistant", "\nuser"],
        }
    )
    req = build_ollama_request("/api/chat", body=json_bytes(payload), stream=False)
    with urlopen(req, timeout=300) as resp:
        obj = json.loads(resp.read().decode("utf-8", errors="replace"))
    return clean_llm_output(((obj.get("message") or {}).get("content") or obj.get("response") or ""))


def build_ollama_request(path: str, body: bytes | None = None, stream: bool = False) -> Request:
    headers = {
        "Accept": "text/event-stream" if stream else "application/json",
        "Content-Type": "application/json",
    }
    return Request(f"{OLLAMA_BASE_URL}{path}", data=body, headers=headers, method="POST" if body else "GET")


def build_api_chat_payload(payload: dict) -> dict:
    options = dict(payload.get("options") or {})
    if payload.get("temperature") is not None:
        options["temperature"] = payload.get("temperature")
    if payload.get("top_p") is not None:
        options["top_p"] = payload.get("top_p")
    if payload.get("max_tokens") is not None:
        options["num_predict"] = payload.get("max_tokens")
    if payload.get("stop") is not None:
        options["stop"] = payload.get("stop")
    options["think"] = False

    out = {
        "model": normalize_model(payload.get("model")),
        "messages": payload.get("messages") or [],
        "stream": bool(payload.get("stream")),
        "think": False,
        "options": options,
    }
    if payload.get("tools"):
        out["tools"] = payload.get("tools")
    return out


def ollama_response_timing(obj: dict[str, Any]) -> dict[str, Any]:
    def ns_to_ms(key: str) -> float | None:
        value = obj.get(key)
        if not isinstance(value, (int, float)):
            return None
        return round(float(value) / 1_000_000, 1)

    prompt_count = int(obj.get("prompt_eval_count") or 0)
    prompt_duration_ns = float(obj.get("prompt_eval_duration") or 0)
    eval_count = int(obj.get("eval_count") or 0)
    eval_duration_ns = float(obj.get("eval_duration") or 0)
    return {
        "done_reason": obj.get("done_reason"),
        "total_duration_ms": ns_to_ms("total_duration"),
        "load_duration_ms": ns_to_ms("load_duration"),
        "prompt_eval_count": prompt_count,
        "prompt_eval_duration_ms": ns_to_ms("prompt_eval_duration"),
        "prompt_tokens_per_second": (
            round(prompt_count / (prompt_duration_ns / 1_000_000_000), 1) if prompt_count and prompt_duration_ns else None
        ),
        "eval_count": eval_count,
        "eval_duration_ms": ns_to_ms("eval_duration"),
        "eval_tokens_per_second": (
            round(eval_count / (eval_duration_ns / 1_000_000_000), 1) if eval_count and eval_duration_ns else None
        ),
    }


def openai_chunk(model: str, content: str = "", finish_reason: str | None = None) -> bytes:
    chunk = {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return b"data: " + json_bytes(chunk) + b"\n\n"


def qa_sse_event(event: str, payload: object) -> bytes:
    return f"event: {event}\n".encode("utf-8") + b"data: " + json_bytes(payload) + b"\n\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "BlastFurnaceOllamaProxy/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.add_cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/v1/models":
            self.handle_models()
            return
        if parsed.path == "/api/ollama/status":
            self.handle_ollama_status()
            return
        if parsed.path == "/api/auth/status":
            self.handle_auth_status()
            return
        if parsed.path == "/api/diagnosis-review-context":
            self.handle_diagnosis_review_context(parsed.query)
            return
        if parsed.path == "/api/diagnosis-reviews":
            self.handle_diagnosis_reviews_get(parsed.query)
            return
        if parsed.path == "/api/diagnosis-manual-scores":
            self.handle_diagnosis_manual_scores_get(parsed.query)
            return
        if parsed.path == "/api/qa/bootstrap":
            self.handle_qa_bootstrap(parsed.query)
            return
        if parsed.path == "/api/qa/conversation":
            self.handle_qa_conversation(parsed.query)
            return
        if parsed.path == "/api/qa/projects":
            self.handle_qa_projects_get(parsed.query)
            return
        if parsed.path == "/api/qa/knowledge/search":
            self.handle_qa_knowledge_search(parsed.query)
            return
        if parsed.path == "/api/qa/knowledge/vector/search":
            self.handle_qa_knowledge_search(parsed.query, forced_mode="vector")
            return
        if parsed.path == "/api/qa/knowledge/pgvector/status":
            self.send_json(pgvector_status())
            return
        if parsed.path == "/api/reports/templates":
            self.handle_reports_templates(parsed.query)
            return
        if parsed.path == "/api/reports/instances":
            self.handle_reports_instances_get(parsed.query)
            return
        if parsed.path == "/api/reports/tree":
            self.handle_reports_tree(parsed.query)
            return
        if parsed.path == "/api/trend/history":
            self.handle_trend_history(parsed.query)
            return
        if parsed.path == "/api/automation/status":
            self.handle_automation_status(parsed.query)
            return
        if parsed.path == "/api/automation/diagnoses":
            self.handle_automation_diagnoses(parsed.query)
            return
        if parsed.path == "/api/short-window/summaries":
            self.handle_short_window_summaries(parsed.query)
            return
        if parsed.path == "/api/short-window/queue":
            self.handle_short_window_queue(parsed.query)
            return
        if parsed.path == "/api/short-window/conversations":
            self.handle_short_window_conversations(parsed.query)
            return
        if parsed.path == "/api/short-window/conversation":
            self.handle_short_window_conversation(parsed.query)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/v1/chat/completions":
            self.handle_chat_completions()
            return
        if parsed.path == "/api/qa/chat":
            self.handle_qa_chat()
            return
        if parsed.path == "/api/auth/login":
            self.handle_auth_login()
            return
        if parsed.path == "/api/auth/logout":
            self.handle_auth_logout()
            return
        if parsed.path == "/api/diagnosis-reviews":
            self.handle_diagnosis_reviews_post()
            return
        if parsed.path == "/api/diagnosis-manual-scores":
            self.handle_diagnosis_manual_scores_post()
            return
        if parsed.path == "/api/qa/conversations":
            self.handle_qa_new_conversation()
            return
        if parsed.path == "/api/qa/conversation-actions":
            self.handle_qa_conversation_action()
            return
        if parsed.path == "/api/qa/snapshots":
            self.handle_qa_snapshot()
            return
        if parsed.path == "/api/qa/projects":
            self.handle_qa_projects_post()
            return
        if parsed.path == "/api/qa/project-assets":
            self.handle_qa_project_assets()
            return
        if parsed.path == "/api/qa/knowledge/pgvector/rebuild":
            self.handle_qa_knowledge_pgvector_rebuild()
            return
        if parsed.path == "/api/qa/open-path":
            self.handle_qa_open_path()
            return
        if parsed.path == "/api/reports/preview":
            self.handle_reports_preview()
            return
        if parsed.path == "/api/reports/instances":
            self.handle_reports_instances_post()
            return
        if parsed.path == "/api/short-window/chat":
            self.handle_short_window_chat()
            return
        self.send_json({"error": f"unknown path: {parsed.path}"}, status=404)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def handle_auth_status(self) -> None:
        accounts = configured_login_accounts()
        session = diagnosis_review.session_from_cookie(self.headers.get("Cookie", ""))
        self.send_json({
            "ok": True,
            "configured": bool(accounts),
            "users": [{"username": username, "role": item["role"]} for username, item in accounts.items()],
            "authenticated": bool(session),
            "username": session.get("sub") if session else None,
            "role": session.get("role") if session else None,
        })

    def handle_auth_login(self) -> None:
        try:
            payload = self.read_json_body()
        except Exception:
            self.send_json({"ok": False, "message": "登录请求格式不正确。"}, status=400)
            return
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if not username or not password:
            self.send_json({"ok": False, "message": "请输入账号和密码。"}, status=400)
            return
        accounts = configured_login_accounts()
        authenticated = diagnosis_review.authenticate_account(accounts, username, password)
        if not authenticated:
            self.send_json({"ok": False, "message": "账号或密码不匹配。"}, status=401)
            return
        role = authenticated["role"]
        default_route = "admin" if ("管理" in role or "管理员" in role or "admin" in role.lower()) else "workspace"
        session_token = diagnosis_review.create_session_token(username, role)
        self.send_json({
            "ok": True,
            "username": username,
            "role": role,
            "message": "登录成功。",
            "access": {
                "mode": "local-env",
                "issued_at": iso_now(),
                "default_route": default_route,
                "routes": ["workspace", "admin"],
            },
        }, headers={"Set-Cookie": diagnosis_review.session_cookie_header(session_token)})

    def handle_auth_logout(self) -> None:
        self.send_json(
            {"ok": True, "message": "已退出登录。"},
            headers={"Set-Cookie": diagnosis_review.clear_session_cookie_header()},
        )

    def current_review_session(self) -> dict[str, Any] | None:
        return diagnosis_review.session_from_cookie(self.headers.get("Cookie", ""))

    def review_store(self) -> diagnosis_review.DiagnosisReviewStore:
        store = diagnosis_review.DiagnosisReviewStore()
        store.ensure_schema()
        return store

    def latest_review_diagnosis_rows(self) -> list[dict[str, Any]]:
        with self.pg_connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT DISTINCT ON (diagnosis_ts)
                           id, diagnosis_ts, main_label, main_score, main_confidence,
                           secondary_label, secondary_score, secondary_confidence,
                           evidence, raw_scores, data_coverage, updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
                ) snapshots
                ORDER BY diagnosis_ts DESC
                LIMIT 288
                """
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            secondary = []
            if item.get("secondary_label"):
                secondary.append({
                    "label": item.get("secondary_label"),
                    "score": item.get("secondary_score"),
                    "confidence": item.get("secondary_confidence"),
                })
            item["secondary"] = secondary
            result.append(item)
        return result

    def canonical_review_context(self, params: dict[str, list[str]]) -> dict[str, Any]:
        fixture_label = (params.get("fixture") or [""])[0]
        fixture_case_id = (params.get("case_id") or ["default"])[0]
        if fixture_label:
            if not diagnosis_review.review_test_mode_enabled() or not diagnosis_review.client_is_loopback(self.client_address):
                raise PermissionError("测试场景只允许在本机测试模式使用")
            return diagnosis_review.build_fixture_context(fixture_label, fixture_case_id)
        return diagnosis_review.derive_current_episode(self.latest_review_diagnosis_rows(), furnace_id="BF")

    def handle_diagnosis_review_context(self, query: str) -> None:
        if not diagnosis_review.review_enabled():
            self.send_json({"ok": True, "enabled": False})
            return
        params = parse_qs(query)
        try:
            context = self.canonical_review_context(params)
            session = self.current_review_session()
            reviewed = False
            review_storage = {"configured": False, "writable": False}
            try:
                config = diagnosis_review.load_review_config(require_store=True)
                review_storage["configured"] = config.store_configured
                store = self.review_store()
                if session and context.get("episode_key"):
                    items = store.list_events(
                        episode_key=str(context["episode_key"]),
                        reviewer_username=str(session.get("sub") or ""),
                        limit=1,
                    )
                    reviewed = bool(items)
                review_storage["writable"] = True
            except Exception as exc:  # noqa: BLE001
                review_storage["message"] = str(exc)
            self.send_json({
                "ok": True,
                "enabled": True,
                "context": context,
                "reviewed_by_current_user": reviewed,
                "auth": {
                    "authenticated": bool(session),
                    "username": session.get("sub") if session else None,
                    "role": session.get("role") if session else None,
                    "can_submit": bool(session and diagnosis_review.role_is_allowed(str(session.get("role") or ""))),
                },
                "review_storage": review_storage,
            })
        except PermissionError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=403)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=503)

    def handle_diagnosis_reviews_get(self, query: str) -> None:
        if not diagnosis_review.review_enabled():
            self.send_json({"ok": False, "error": "复核功能未启用"}, status=404)
            return
        session = self.current_review_session()
        if not session:
            self.send_json({"ok": False, "error": "请先登录"}, status=401)
            return
        if not diagnosis_review.role_is_allowed(str(session.get("role") or "")):
            self.send_json({"ok": False, "error": "当前角色无权查看复核事件"}, status=403)
            return
        params = parse_qs(query)
        try:
            limit = int((params.get("limit") or ["50"])[0])
        except ValueError:
            limit = 50
        try:
            items = self.review_store().list_events(
                episode_key=(params.get("episode_key") or [""])[0],
                reviewer_username=(params.get("reviewer") or [""])[0],
                limit=limit,
            )
            self.send_json({"ok": True, "items": items})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=503)

    def handle_diagnosis_reviews_post(self) -> None:
        if not diagnosis_review.review_enabled():
            self.send_json({"ok": False, "error": "复核功能未启用"}, status=404)
            return
        session = self.current_review_session()
        if not session:
            self.send_json({"ok": False, "error": "请先登录"}, status=401)
            return
        if not diagnosis_review.role_is_allowed(str(session.get("role") or "")):
            self.send_json({"ok": False, "error": "当前角色无权提交复核"}, status=403)
            return
        try:
            payload = self.read_json_body()
            snapshot_source = str(payload.get("snapshot_source") or "live_readonly")
            params: dict[str, list[str]] = {}
            if snapshot_source == "local_fixture":
                params = {
                    "fixture": [str(payload.get("fixture_label") or "")],
                    "case_id": [str(payload.get("fixture_case_id") or "default")],
                }
            canonical = self.canonical_review_context(params)
            if not canonical.get("available") or not canonical.get("is_abnormal"):
                raise diagnosis_review.ReviewValidationError("当前没有可复核的异常炉况")
            review = diagnosis_review.validate_review_payload(payload, canonical)
            event, created = self.review_store().insert_event(canonical, review, session)
            self.send_json({"ok": True, "created": created, "event": event}, status=201 if created else 200)
        except diagnosis_review.ReviewValidationError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except PermissionError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=403)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=503)

    def handle_diagnosis_manual_scores_get(self, query: str) -> None:
        if not diagnosis_review.review_enabled():
            self.send_json({"ok": False, "error": "复核功能未启用"}, status=404)
            return
        session = self.current_review_session()
        if not session:
            self.send_json({"ok": False, "error": "请先登录"}, status=401)
            return
        if not diagnosis_review.role_is_allowed(str(session.get("role") or "")):
            self.send_json({"ok": False, "error": "当前角色无权查看高炉长评分"}, status=403)
            return
        params = parse_qs(query)
        try:
            items = self.review_store().list_human_score_events(
                start=(params.get("start") or [None])[0],
                end=(params.get("end") or [None])[0],
                labels=diagnosis_review._split_csv((params.get("labels") or [""])[0]),
                limit=int((params.get("limit") or ["5000"])[0]),
            )
            self.send_json({"ok": True, "items": items})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=503)

    def handle_diagnosis_manual_scores_post(self) -> None:
        if not diagnosis_review.review_enabled():
            self.send_json({"ok": False, "error": "复核功能未启用"}, status=404)
            return
        session = self.current_review_session()
        if not session:
            self.send_json({"ok": False, "error": "请先登录"}, status=401)
            return
        if not diagnosis_review.role_is_allowed(str(session.get("role") or "")):
            self.send_json({"ok": False, "error": "当前角色无权提交高炉长评分"}, status=403)
            return
        try:
            payload = self.read_json_body()
            params: dict[str, list[str]] = {}
            if str(payload.get("snapshot_source") or "live_readonly") == "local_fixture":
                params = {
                    "fixture": [str(payload.get("fixture_label") or "")],
                    "case_id": [str(payload.get("fixture_case_id") or "default")],
                }
            canonical = self.canonical_review_context(params)
            if not canonical.get("available"):
                raise diagnosis_review.ReviewValidationError("当前没有可评分的炉况诊断快照")
            manual_score = diagnosis_review.validate_manual_score_payload(payload, canonical)
            event, created = self.review_store().insert_manual_score_event(canonical, manual_score, session)
            self.send_json({"ok": True, "created": created, "event": event}, status=201 if created else 200)
        except diagnosis_review.ReviewValidationError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except PermissionError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=403)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=503)

    def handle_reports_templates(self, query: str) -> None:
        params = parse_qs(query)
        report_type = params.get("type", [""])[0] or params.get("report_type", [""])[0]
        with db_connect() as conn:
            self.send_json({"ok": True, "items": list_report_templates(conn, report_type or None)})

    def handle_reports_instances_get(self, query: str) -> None:
        params = parse_qs(query)
        report_type = params.get("type", [""])[0] or params.get("report_type", [""])[0]
        try:
            limit = int(params.get("limit", ["200"])[0])
        except ValueError:
            limit = 200
        with db_connect() as conn:
            items = list_report_instances(conn, report_type or None, limit=max(1, min(limit, 1000)))
            self.send_json({"ok": True, "items": items, "tree": report_tree_from_instances(items)})

    def handle_reports_tree(self, query: str) -> None:
        params = parse_qs(query)
        report_type = params.get("type", [""])[0] or params.get("report_type", [""])[0]
        with db_connect() as conn:
            items = list_report_instances(conn, report_type or None, limit=1000)
            self.send_json({"ok": True, "tree": report_tree_from_instances(items), "items": items})

    def handle_reports_preview(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        try:
            with db_connect() as conn:
                self.send_json(build_report_preview(conn, payload))
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_reports_instances_post(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        try:
            with db_connect() as conn:
                result = create_report_instance(conn, payload)
                result["tree"] = report_tree_from_instances(list_report_instances(conn, None, limit=1000))
                self.send_json(result)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_trend_history(self, query: str) -> None:
        params = parse_qs(query)

        def float_param(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(params.get(name, [str(default)])[0])
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        def int_param(name: str, default: int, low: int, high: int) -> int:
            try:
                value = int(params.get(name, [str(default)])[0])
            except (TypeError, ValueError):
                value = default
            return max(low, min(high, value))

        hours = float_param("hours", 8.0, 0.1, 24 * 90)
        batch_size = int_param("batch_size", 8, 1, 64)
        max_workers = int_param("max_workers", 4, 1, 8)
        variables_text = params.get("variables", [""])[0]
        variables = [item.strip() for item in variables_text.split(",") if item.strip()] or None
        cache_key = json.dumps(
            {"hours": hours, "batch_size": batch_size, "max_workers": max_workers, "variables": variables},
            sort_keys=True,
        )
        now = time.time()
        cached = _TREND_HISTORY_CACHE.get("payload")
        if (
            cached
            and _TREND_HISTORY_CACHE.get("key") == cache_key
            and now - float(_TREND_HISTORY_CACHE.get("created", 0.0)) <= TREND_HISTORY_CACHE_SECONDS
        ):
            self.send_json(cached, status=200)
            return

        try:
            module = load_trend_backend()
            payload = module.collect_trend_history(
                hours=hours,
                variables=variables,
                batch_size=batch_size,
                max_workers=max_workers,
            )
            _TREND_HISTORY_CACHE.update({"key": cache_key, "created": now, "payload": payload})
            self.send_json(payload, status=200)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": f"trend history failed: {exc}"}, status=502)

    def handle_ollama_status(self) -> None:
        result: dict[str, Any] = {
            "ok": False,
            "proxy_ok": True,
            "ollama_ok": False,
            "model_ok": False,
            "target_model": PUBLIC_MODEL_NAME,
            "error": "",
        }
        try:
            req = Request(f"{OLLAMA_BASE_URL}/api/version", headers={"Accept": "application/json"})
            with urlopen(req, timeout=6) as resp:
                json.loads(resp.read().decode("utf-8", errors="replace"))
            resolved_model = resolve_upstream_model()
            show_payload = json_bytes({"name": resolved_model})
            req = Request(
                f"{OLLAMA_BASE_URL}/api/show",
                data=show_payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode("utf-8", errors="replace"))
            result["ollama_ok"] = True
            result["model_ok"] = True
            result["ok"] = bool(result["ollama_ok"] and result["model_ok"])
        except URLError as exc:
            result["error"] = f"高炉大模型服务不可达：{sanitize_model_exposure(exc.reason)}"
        except Exception as exc:  # noqa: BLE001
            result["ollama_ok"] = True
            result["error"] = "业务模型不可用或未完成安全别名创建。"
        self.send_json(result, status=200)

    def pg_connect(self):
        return _assistant_raw_pg_connect()

    def latest_pg_snapshot_for_qa(self, conn: Any | None = None) -> dict[str, Any] | None:
        if conn is None:
            try:
                with self.pg_connect() as owned_conn:
                    return self.latest_pg_snapshot_for_qa(owned_conn)
            except Exception:
                return None
        try:
            latest = conn.execute(
                """
                SELECT id, diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                       baseline_window_start, baseline_window_end, baseline_days, window_minutes,
                       source, data_coverage, missing_variables, source_lag_seconds,
                       main_label, main_score, main_confidence,
                       secondary_label, secondary_score, secondary_confidence,
                       evidence, raw_scores, created_at, updated_at
                FROM bf_sensor.diagnosis_snapshots
                ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if not latest:
                return None
            keys = [
                "DP_total", "DP_upper", "DP_lower", "PI", "P_blast", "T_blast",
                "Q_blast", "P_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D",
                "PCI_rate", "Q_O2", "GasUtil", "L", "L_south", "L_north",
            ]
            rows = conn.execute(
                """
                SELECT r.variable_name, latest.value, latest.ts
                FROM bf_sensor.sensor_registry r
                CROSS JOIN LATERAL (
                    SELECT v.value, v.ts
                    FROM bf_sensor.one_minute_values v
                    WHERE v.tag_long_name = r.tag_long_name
                    ORDER BY v.ts DESC
                    LIMIT 1
                ) latest
                WHERE r.variable_name = ANY(%s)
                ORDER BY r.variable_name
                """,
                (keys,),
            ).fetchall()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        values = {str(row["variable_name"]): row["value"] for row in rows if row.get("variable_name")}
        value_times = [row.get("ts") for row in rows if row.get("ts") is not None]
        value_ts = max(value_times) if value_times else latest.get("diagnosis_ts")
        top_values = [values.get(key) for key in ("T_top_A", "T_top_B", "T_top_C", "T_top_D")]
        top_nums = [float(value) for value in top_values if isinstance(value, (int, float))]
        if top_nums and "T_top" not in values:
            values["T_top"] = sum(top_nums) / len(top_nums)
        coverage = latest.get("data_coverage") or {}
        diagnosis = {
            "main_label": latest.get("main_label"),
            "secondary_label": latest.get("secondary_label"),
            "main_score": latest.get("main_score"),
            "main_confidence": latest.get("main_confidence"),
            "evidence": latest.get("evidence") or [],
            "raw_scores": latest.get("raw_scores") or {},
            "diagnosis_ts": latest.get("diagnosis_ts"),
            "diagnosis_window_start": latest.get("diagnosis_window_start"),
            "diagnosis_window_end": latest.get("diagnosis_window_end"),
            "baseline_window_start": latest.get("baseline_window_start"),
            "baseline_window_end": latest.get("baseline_window_end"),
        }
        return {
            "source_time": str(latest.get("diagnosis_ts") or value_ts or iso_now()),
            "pg_context_version": f"{latest.get('diagnosis_ts')}|{latest.get('updated_at')}|{latest.get('id')}",
            "pg_window_minutes": latest.get("window_minutes"),
            "values": values,
            "diagnosis": diagnosis,
            "recommendation": {},
            "data_quality": {
                "coverage_ratio": coverage.get("coverage_ratio"),
                "missing_variables": latest.get("missing_variables") or [],
                "source_lag_seconds": latest.get("source_lag_seconds"),
                "source": latest.get("source"),
                "from_pg_diagnosis_snapshots": True,
            },
        }

    def recent_pg_diagnosis_snapshots_for_qa(
        self,
        hours: float = QA_TREND_HOURS,
        limit: int = QA_TREND_DIAGNOSIS_LIMIT,
        conn: Any | None = None,
        latest_ts: Any | None = None,
        context_version: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        meta: dict[str, Any] = {
            "trend_source": "bf_sensor.diagnosis_snapshots",
            "trend_source_label": "生产5min诊断",
            "trend_limit": limit,
            "trend_cadence_minutes": QA_TREND_CADENCE_MINUTES,
            "trend_window_minutes": QA_TREND_WINDOW_MINUTES,
        }
        if conn is None:
            try:
                with self.pg_connect() as owned_conn:
                    return self.recent_pg_diagnosis_snapshots_for_qa(
                        hours=hours,
                        limit=limit,
                        conn=owned_conn,
                        latest_ts=latest_ts,
                        context_version=context_version,
                    )
            except Exception as exc:  # noqa: BLE001
                return [], {**meta, "trend_error": sanitize_model_exposure(exc)}
        try:
            if latest_ts is None:
                latest_row = conn.execute(
                    """
                    SELECT max(diagnosis_ts) AS ts, max(updated_at) AS updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    WHERE window_minutes = %s
                    """,
                    (QA_TREND_WINDOW_MINUTES,),
                ).fetchone()
                latest_ts = latest_row.get("ts") if latest_row else None
                context_version = context_version or (
                    f"{latest_ts}|{latest_row.get('updated_at')}" if latest_row else str(latest_ts)
                )
                if latest_ts is None:
                    latest_row = conn.execute(
                        "SELECT max(diagnosis_ts) AS ts, max(updated_at) AS updated_at "
                        "FROM bf_sensor.diagnosis_snapshots"
                    ).fetchone()
                    latest_ts = latest_row.get("ts") if latest_row else None
                    context_version = context_version or (
                        f"{latest_ts}|{latest_row.get('updated_at')}" if latest_row else str(latest_ts)
                    )
                if latest_ts is None:
                    return [], {**meta, "trend_error": "bf_sensor.diagnosis_snapshots 为空"}
            cache_key = (
                str(latest_ts),
                str(context_version or latest_ts),
                float(hours),
                int(limit),
                int(QA_TREND_WINDOW_MINUTES),
            )
            with _QA_PG_TREND_CACHE_LOCK:
                if _QA_PG_TREND_CACHE.get("key") == cache_key:
                    cached_snapshots = copy.deepcopy(_QA_PG_TREND_CACHE.get("snapshots") or [])
                    cached_meta = copy.deepcopy(_QA_PG_TREND_CACHE.get("meta") or meta)
                    cached_meta["trend_cache_hit"] = True
                    return cached_snapshots, cached_meta

            cutoff = latest_ts - timedelta(hours=hours)
            rows = conn.execute(
                """
                SELECT *
                FROM (
                    SELECT DISTINCT ON (diagnosis_ts)
                           id, diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                           baseline_window_start, baseline_window_end, baseline_days, window_minutes,
                           source, data_coverage, missing_variables, source_lag_seconds,
                           main_label, main_score, main_confidence,
                           secondary_label, secondary_score, secondary_confidence,
                           evidence, raw_scores, feature_snapshot, created_at, updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    WHERE diagnosis_ts >= %s
                      AND diagnosis_ts <= %s
                      AND window_minutes = %s
                    ORDER BY diagnosis_ts, updated_at DESC, id DESC
                ) latest
                ORDER BY diagnosis_ts DESC
                LIMIT %s
                """,
                (cutoff, latest_ts, QA_TREND_WINDOW_MINUTES, limit),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM (
                        SELECT DISTINCT ON (diagnosis_ts)
                               id, diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                               baseline_window_start, baseline_window_end, baseline_days, window_minutes,
                               source, data_coverage, missing_variables, source_lag_seconds,
                               main_label, main_score, main_confidence,
                               secondary_label, secondary_score, secondary_confidence,
                               evidence, raw_scores, feature_snapshot, created_at, updated_at
                        FROM bf_sensor.diagnosis_snapshots
                        WHERE diagnosis_ts >= %s
                          AND diagnosis_ts <= %s
                        ORDER BY diagnosis_ts, updated_at DESC, id DESC
                    ) latest
                    ORDER BY diagnosis_ts DESC
                    LIMIT %s
                    """,
                    (cutoff, latest_ts, limit),
                ).fetchall()
            rows = list(reversed([dict(row) for row in rows]))
            snapshots = [pg_diagnosis_row_to_prompt_snapshot(row) for row in rows]
            result_meta = {
                **meta,
                "trend_count": len(snapshots),
                "trend_start_time": str(snapshots[0].get("source_time")) if snapshots else None,
                "trend_end_time": str(snapshots[-1].get("source_time")) if snapshots else str(latest_ts),
                "trend_cache_hit": False,
                "trend_cache_key": str(context_version or latest_ts),
            }
            with _QA_PG_TREND_CACHE_LOCK:
                _QA_PG_TREND_CACHE.update(
                    {
                        "key": cache_key,
                        "snapshots": copy.deepcopy(snapshots),
                        "meta": copy.deepcopy(result_meta),
                    }
                )
            return snapshots, result_meta
        except Exception as exc:  # noqa: BLE001
            try:
                conn.rollback()
            except Exception:
                pass
            return [], {**meta, "trend_error": sanitize_model_exposure(exc)}

    def ensure_short_window_message_table(self, conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bf_sensor.short_window_conversation_messages (
                id bigserial PRIMARY KEY,
                conversation_id text NOT NULL REFERENCES bf_sensor.short_window_conversations(conversation_id) ON DELETE CASCADE,
                queue_id text NOT NULL REFERENCES bf_sensor.diagnosis_queues(queue_id) ON DELETE CASCADE,
                role text NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content text NOT NULL DEFAULT '',
                hidden_context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamp without time zone NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_short_window_conversation_messages_conv
                ON bf_sensor.short_window_conversation_messages(conversation_id, id)
            """
        )

    def short_window_message_rows(self, conn, conversation_id: str) -> list[dict[str, Any]]:
        self.ensure_short_window_message_table(conn)
        rows = conn.execute(
            """
            SELECT id, conversation_id, queue_id, role, content, hidden_context_json, created_at
            FROM bf_sensor.short_window_conversation_messages
            WHERE conversation_id=%s
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def short_window_summary_row(self, conn, queue_id: int | str | None) -> dict[str, Any] | None:
        """Return the latest LLM summary for a short-window diagnosis queue."""
        if not queue_id:
            return None
        row = conn.execute(
            """
            SELECT
                summary_id, queue_id, queue_hash, model_name,
                llm_summary AS summary_text,
                llm_summary,
                diagnosis_queue_json,
                docx_path,
                markdown_path,
                status AS summary_status,
                created_at,
                updated_at
            FROM bf_sensor.short_window_summaries
            WHERE queue_id = %s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, summary_id DESC
            LIMIT 1
            """,
            (queue_id,),
        ).fetchone()
        return dict(row) if row else None

    def short_window_seed_context(
        self,
        conversation_id: str | None = None,
        queue_id: int | str | None = None,
    ) -> dict[str, Any] | None:
        """Build a reusable QA seed payload from a short-window queue/conversation."""
        conversation_id = (conversation_id or "").strip()
        with self.pg_connect() as conn:
            conversation = None
            if conversation_id:
                conversation = conn.execute(
                    """
                    SELECT *
                    FROM bf_sensor.short_window_conversations
                    WHERE conversation_id = %s
                    LIMIT 1
                    """,
                    (conversation_id,),
                ).fetchone()
            resolved_queue_id = queue_id or (conversation["queue_id"] if conversation else None)
            queue = None
            if resolved_queue_id:
                queue = conn.execute(
                    """
                    SELECT *
                    FROM bf_sensor.diagnosis_queues
                    WHERE queue_id = %s
                    LIMIT 1
                    """,
                    (resolved_queue_id,),
                ).fetchone()
            summary = self.short_window_summary_row(conn, resolved_queue_id) if resolved_queue_id else None
            messages = self.short_window_message_rows(conn, conversation_id) if conversation_id else []
        if not queue:
            return None
        return {
            "conversation": dict(conversation) if conversation else None,
            "queue": dict(queue),
            "summary": summary,
            "messages": messages,
        }

    def short_window_seed_markdown(self, seed: dict[str, Any]) -> str:
        """Format a short-window queue as the first assistant message in QA."""
        queue = seed.get("queue") or {}
        summary = seed.get("summary") or {}
        messages = seed.get("messages") or []
        summary_text = (
            summary.get("summary_text")
            or summary.get("llm_summary")
            or "该短时队列尚未生成大模型总判断。"
        )
        tail_messages: list[str] = []
        for item in messages[-4:]:
            role = item.get("role") or ""
            content = (item.get("content") or "").strip()
            if content:
                tail_messages.append(f"- **{role}**：{content[:500]}")
        tail = "\n".join(tail_messages)
        extra = f"\n\n### 原短时会话最近消息\n{tail}" if tail else ""
        return (
            "### 短时炉况总判断\n"
            f"{summary_text}\n\n"
            "### 队列信息\n"
            f"- 队列窗口：{queue.get('queue_start_ts') or ''} - {queue.get('queue_end_ts') or ''}\n"
            f"- 状态：{queue.get('status') or ''}\n"
            f"- 诊断数：{queue.get('diagnosis_count') or 0}\n"
            f"- 队列 ID：{queue.get('queue_id')}\n"
            f"{extra}\n\n"
            "可以基于这段短时队列继续追问调整依据、风险变量、传感器证据或操作建议。"
        )

    def handle_automation_status(self, query: str) -> None:
        try:
            with self.pg_connect() as conn:
                latest = conn.execute(
                    """
                    SELECT id, diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                           baseline_window_start, baseline_window_end, baseline_days, window_minutes,
                           source, data_coverage, missing_variables, source_lag_seconds,
                           main_label, main_score, main_confidence,
                           secondary_label, secondary_score, secondary_confidence,
                           evidence, raw_scores, created_at, updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    ORDER BY diagnosis_ts DESC
                    LIMIT 1
                    """
                ).fetchone()
                runs = conn.execute(
                    """
                    SELECT id, started_at, finished_at, task_name, status, window_start, window_end,
                           rows_read, rows_written, message, details
                    FROM bf_sensor.automation_runs
                    ORDER BY started_at DESC
                    LIMIT 12
                    """
                ).fetchall()
                quality = conn.execute(
                    """
                    SELECT id, checked_at, window_start, window_end, window_kind, latest_data_ts,
                           source_lag_seconds, expected_minutes, observed_minutes, coverage_ratio,
                           missing_variables, stale_variables, status, details
                    FROM bf_sensor.data_quality_status
                    ORDER BY checked_at DESC
                    LIMIT 1
                    """
                ).fetchone()
                latest_data = conn.execute(
                    "SELECT max(ts) AS latest_data_ts FROM bf_sensor.one_minute_values"
                ).fetchone()
            latest_dict = dict(latest) if latest else None
            if latest_dict:
                coverage = latest_dict.get("data_coverage") or {}
                latest_dict["coverage_ratio"] = coverage.get("coverage_ratio")
            self.send_json(
                {
                    "ok": True,
                    "database_ok": True,
                    "latest_data_ts": latest_data.get("latest_data_ts") if latest_data else None,
                    "latest": latest_dict,
                    "latest_quality": dict(quality) if quality else None,
                    "runs": [dict(row) for row in runs],
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "database_ok": False, "error": str(exc)}, status=200)

    def handle_automation_diagnoses(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = int(params.get("limit", ["48"])[0])
        except ValueError:
            limit = 48
        limit = max(1, min(limit, 500))
        try:
            with self.pg_connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, diagnosis_ts, diagnosis_window_start, diagnosis_window_end,
                           baseline_window_start, baseline_window_end, baseline_days, window_minutes,
                           source, data_coverage, missing_variables, source_lag_seconds,
                           main_label, main_score, main_confidence,
                           secondary_label, secondary_score, secondary_confidence,
                           evidence, raw_scores, feature_snapshot, created_at, updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    ORDER BY diagnosis_ts DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            self.send_json({"ok": True, "items": [dict(row) for row in rows]})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=200)

    def handle_short_window_summaries(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = max(1, min(int(params.get("limit", ["20"])[0]), 200))
        except ValueError:
            limit = 20
        try:
            with self.pg_connect() as conn:
                rows = conn.execute(
                    """
                    SELECT s.summary_id, s.queue_id, s.queue_hash, s.model_name, s.llm_summary,
                           s.llm_summary AS summary_text,
                           s.diagnosis_queue_json, s.docx_path, s.markdown_path,
                           s.status AS summary_status, s.created_at, s.updated_at,
                           q.queue_start_ts AS queue_start, q.queue_end_ts AS queue_end,
                           q.status AS queue_status, q.diagnosis_count, q.expected_count
                    FROM bf_sensor.short_window_summaries s
                    LEFT JOIN bf_sensor.diagnosis_queues q ON q.queue_id = s.queue_id
                    ORDER BY s.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            self.send_json({"ok": True, "items": [dict(row) for row in rows]})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=200)

    def handle_short_window_conversations(self, query: str) -> None:
        params = parse_qs(query)
        try:
            limit = max(1, min(int(params.get("limit", ["50"])[0]), 200))
        except ValueError:
            limit = 50
        try:
            with self.pg_connect() as conn:
                self.ensure_short_window_message_table(conn)
                rows = conn.execute(
                    """
                    WITH latest_summaries AS (
                        SELECT DISTINCT ON (queue_id)
                               summary_id, queue_id, queue_hash, model_name, llm_summary, status,
                               created_at, updated_at
                        FROM bf_sensor.short_window_summaries
                        ORDER BY queue_id, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, summary_id DESC
                    ),
                    latest_conversations AS (
                        SELECT DISTINCT ON (queue_id)
                               conversation_id, queue_id, queue_hash, last_queue_diagnosis_ts,
                               created_at, updated_at
                        FROM bf_sensor.short_window_conversations
                        ORDER BY queue_id, updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                    ),
                    message_counts AS (
                        SELECT conversation_id, count(id) AS message_count, max(created_at) AS last_message_at
                        FROM bf_sensor.short_window_conversation_messages
                        GROUP BY conversation_id
                    )
                    SELECT c.conversation_id,
                           q.queue_id,
                           q.queue_hash,
                           COALESCE(c.last_queue_diagnosis_ts, q.queue_end_ts) AS last_queue_diagnosis_ts,
                           COALESCE(c.created_at, s.created_at, q.created_at) AS created_at,
                           COALESCE(c.updated_at, s.updated_at, q.updated_at) AS updated_at,
                           q.queue_start_ts AS queue_start, q.queue_end_ts AS queue_end,
                           q.status AS queue_status,
                           q.diagnosis_count,
                           q.expected_count,
                           s.status AS summary_status,
                           s.updated_at AS summary_updated_at,
                           s.llm_summary AS initial_summary,
                           COALESCE(m.message_count, 0) AS message_count,
                           m.last_message_at,
                           CASE WHEN c.conversation_id IS NULL THEN 'queue_summary' ELSE 'short_conversation' END AS source_type
                    FROM bf_sensor.diagnosis_queues q
                    LEFT JOIN latest_summaries s ON s.queue_id = q.queue_id
                    LEFT JOIN latest_conversations c ON c.queue_id = q.queue_id
                    LEFT JOIN message_counts m ON m.conversation_id = c.conversation_id
                    ORDER BY q.queue_end_ts DESC NULLS LAST, c.updated_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            self.send_json({"ok": True, "items": [dict(row) for row in rows]})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=200)

    def handle_short_window_conversation(self, query: str) -> None:
        params = parse_qs(query)
        conversation_id = params.get("conversation_id", [""])[0]
        queue_id = params.get("queue_id", [""])[0]
        try:
            with self.pg_connect() as conn:
                self.ensure_short_window_message_table(conn)
                if conversation_id:
                    conv = conn.execute(
                        "SELECT * FROM bf_sensor.short_window_conversations WHERE conversation_id=%s",
                        (conversation_id,),
                    ).fetchone()
                elif queue_id:
                    conv = conn.execute(
                        """
                        SELECT *
                        FROM bf_sensor.short_window_conversations
                        WHERE queue_id=%s OR queue_hash=%s
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (queue_id, queue_id),
                    ).fetchone()
                else:
                    conv = None
                if not conv:
                    self.send_json({"ok": False, "error": "conversation not found"}, status=404)
                    return
                queue = conn.execute(
                    "SELECT * FROM bf_sensor.diagnosis_queues WHERE queue_id=%s",
                    (conv["queue_id"],),
                ).fetchone()
                summary = self.short_window_summary_row(conn, conv["queue_id"])
                contexts = conn.execute(
                    """
                    SELECT *
                    FROM bf_sensor.conversation_delta_contexts
                    WHERE conversation_id=%s
                    ORDER BY message_ts ASC, id ASC
                    """,
                    (conv["conversation_id"],),
                ).fetchall()
                self.send_json(
                    {
                        "ok": True,
                        "conversation": dict(conv),
                        "queue": dict(queue) if queue else None,
                        "summary": summary,
                        "messages": self.short_window_message_rows(conn, conv["conversation_id"]),
                        "delta_contexts": [dict(row) for row in contexts],
                    }
                )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=200)

    def handle_short_window_queue(self, query: str) -> None:
        params = parse_qs(query)
        queue_id = params.get("queue_id", [""])[0] or params.get("queue_hash", [""])[0]
        try:
            with self.pg_connect() as conn:
                self.ensure_short_window_message_table(conn)
                if queue_id:
                    row = conn.execute(
                        """
                        SELECT *
                        FROM bf_sensor.diagnosis_queues
                        WHERE queue_id=%s OR queue_hash=%s
                        ORDER BY queue_end_ts DESC
                        LIMIT 1
                        """,
                        (queue_id, queue_id),
                    ).fetchone()
                else:
                    row = conn.execute("SELECT * FROM bf_sensor.diagnosis_queues ORDER BY queue_end_ts DESC LIMIT 1").fetchone()
                summary = self.short_window_summary_row(conn, row["queue_id"]) if row else None
            self.send_json({"ok": bool(row), "queue": dict(row) if row else None, "summary": summary})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=200)

    def handle_short_window_chat(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        message = str(payload.get("message") or "").strip()
        if not message:
            self.send_json({"ok": False, "error": "message is required"}, status=400)
            return
        conversation_id = str(payload.get("conversation_id") or f"swc_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}")
        queue_id = str(payload.get("queue_id") or "")
        message_ts = datetime.now().replace(second=0, microsecond=0)
        try:
            with self.pg_connect() as conn:
                if queue_id:
                    queue = conn.execute(
                        "SELECT * FROM bf_sensor.diagnosis_queues WHERE queue_id=%s OR queue_hash=%s ORDER BY queue_end_ts DESC LIMIT 1",
                        (queue_id, queue_id),
                    ).fetchone()
                else:
                    queue = conn.execute("SELECT * FROM bf_sensor.diagnosis_queues ORDER BY queue_end_ts DESC LIMIT 1").fetchone()
                if not queue:
                    raise RuntimeError("No short-window diagnosis queue is available.")
                conv = conn.execute(
                    """
                    INSERT INTO bf_sensor.short_window_conversations(conversation_id, queue_id, queue_hash, last_queue_diagnosis_ts, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (conversation_id) DO UPDATE SET updated_at=now()
                    RETURNING *
                    """,
                    (conversation_id, queue["queue_id"], queue["queue_hash"], queue["queue_end_ts"]),
                ).fetchone()
                delta = conn.execute(
                    """
                    SELECT id, diagnosis_ts, main_label, main_score, main_confidence, secondary_label, evidence
                    FROM bf_sensor.diagnosis_snapshots
                    WHERE diagnosis_ts > %s AND diagnosis_ts <= %s
                    ORDER BY diagnosis_ts ASC
                    """,
                    (conv["last_queue_diagnosis_ts"], message_ts),
                ).fetchall()
                queue_diagnoses = conn.execute(
                    """
                    SELECT id, diagnosis_ts, main_label, main_score, main_confidence, secondary_label, evidence
                    FROM bf_sensor.diagnosis_snapshots
                    WHERE diagnosis_ts >= COALESCE(%s, %s)
                      AND diagnosis_ts <= COALESCE(%s, %s)
                    ORDER BY diagnosis_ts ASC
                    LIMIT 240
                    """,
                    (
                        queue.get("queue_start_ts"),
                        queue["queue_end_ts"],
                        queue.get("queue_end_ts"),
                        message_ts,
                    ),
                ).fetchall()
                hidden = {
                    "operator_message_ts": message_ts,
                    "operator_message": message,
                    "conversation_id": conversation_id,
                    "queue_id": queue["queue_id"],
                    "queue_hash": queue["queue_hash"],
                    "queue_start_ts": queue.get("queue_start_ts"),
                    "queue_end_ts": queue.get("queue_end_ts"),
                    "queue_status": queue.get("status"),
                    "queue_diagnosis_count": len(queue_diagnoses),
                    "queue_diagnoses": [dict(row) for row in queue_diagnoses],
                    "queue_payload": queue.get("diagnosis_queue_json"),
                    "delta_diagnoses": [dict(row) for row in delta],
                }
                conn.execute(
                    """
                    INSERT INTO bf_sensor.conversation_delta_contexts(
                        conversation_id, queue_id, message_ts, previous_queue_end_ts,
                        delta_start_ts, delta_end_ts, delta_diagnosis_ids, operator_message, hidden_context_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                    """,
                    (
                        conversation_id,
                        queue["queue_id"],
                        message_ts,
                        conv["last_queue_diagnosis_ts"],
                        delta[0]["diagnosis_ts"] if delta else None,
                        delta[-1]["diagnosis_ts"] if delta else None,
                        json.dumps([row["id"] for row in delta], ensure_ascii=False, default=str),
                        message,
                        json.dumps(hidden, ensure_ascii=False, default=str),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO bf_sensor.short_window_conversation_messages(
                        conversation_id, queue_id, role, content, hidden_context_json
                    )
                    VALUES (%s, %s, 'user', %s, %s::jsonb)
                    """,
                    (
                        conversation_id,
                        queue["queue_id"],
                        message,
                        json.dumps(hidden, ensure_ascii=False, default=str),
                    ),
                )
                conn.commit()
            prompt = [
                {"role": "system", "content": "你是高炉短时炉况诊断助手。用户问题来自某个短时诊断队列会话。优先使用后台提供的最新队列炉况、队列窗口内诊断和新增诊断回答；即使 delta_diagnoses 为空，也必须基于队列诊断资料说明当前队列炉况，不要退回旧快照或虚构未提供数据。不得向用户复述后台资料字段名、结构或内部实现。"},
                {"role": "user", "content": "后台队列资料：\n" + json.dumps(hidden, ensure_ascii=False, default=str) + "\n\n高炉长消息：\n" + message},
            ]
            answer = call_ollama_chat(prompt)
            with self.pg_connect() as conn:
                self.ensure_short_window_message_table(conn)
                conn.execute(
                    """
                    INSERT INTO bf_sensor.short_window_conversation_messages(
                        conversation_id, queue_id, role, content, hidden_context_json
                    )
                    VALUES (%s, %s, 'assistant', %s, %s::jsonb)
                    """,
                    (
                        conversation_id,
                        queue["queue_id"],
                        answer,
                        json.dumps(hidden, ensure_ascii=False, default=str),
                    ),
                )
                new_anchor = delta[-1]["diagnosis_ts"] if delta else message_ts
                conn.execute(
                    """
                    UPDATE bf_sensor.short_window_conversations
                    SET last_queue_diagnosis_ts = GREATEST(last_queue_diagnosis_ts, %s),
                        updated_at = now()
                    WHERE conversation_id = %s
                    """,
                    (new_anchor, conversation_id),
                )
                conn.commit()
                messages = self.short_window_message_rows(conn, conversation_id)
            self.send_json(
                {
                    "ok": True,
                    "conversation_id": conversation_id,
                    "queue_id": queue["queue_id"],
                    "hidden_context": hidden,
                    "answer": answer,
                    "messages": messages,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=200)

    def handle_qa_bootstrap(self, query: str) -> None:
        params = parse_qs(query)
        force_new = params.get("new", ["0"])[0] in {"1", "true", "yes"}
        with db_connect() as conn:
            conversation, auto_new = select_bootstrap_conversation(conn, force_new=force_new)
            self.send_json(
                {
                    "ok": True,
                    "auto_new": auto_new,
                    "inactivity_hours": QA_INACTIVITY_HOURS,
                    "server_time": iso_now(),
                    "conversation": conversation,
                    "conversations": list_conversations(conn),
                    "messages": load_messages(conn, conversation["id"]),
                    "latest_snapshot": latest_snapshot(conn),
                    "projects": list_projects(conn),
                    "report_assets": scan_report_assets(conn),
                }
            )

    def handle_qa_conversation(self, query: str) -> None:
        params = parse_qs(query)
        conversation_id = params.get("id", [""])[0]
        if not conversation_id:
            self.send_json({"ok": False, "error": "missing conversation id"}, status=400)
            return
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                self.send_json({"ok": False, "error": "conversation not found"}, status=404)
                return
            self.send_json(
                {
                    "ok": True,
                    "conversation": conversation_from_row(row),
                    "conversations": list_conversations(conn),
                    "messages": load_messages(conn, conversation_id),
                }
            )

    def handle_qa_projects_get(self, query: str) -> None:
        params = parse_qs(query)
        project_id = params.get("id", [""])[0]
        with db_connect() as conn:
            payload: dict[str, Any] = {
                "ok": True,
                "projects": list_projects(conn),
                "allowed_folders": list_allowed_folders(),
                "report_assets": scan_report_assets(conn),
            }
            if project_id:
                try:
                    pid = int(project_id)
                except ValueError:
                    self.send_json({"ok": False, "error": "bad project id"}, status=400)
                    return
                row = conn.execute("SELECT * FROM qa_projects WHERE id = ?", (pid,)).fetchone()
                if row is None:
                    self.send_json({"ok": False, "error": "project not found"}, status=404)
                    return
                project = project_from_row(row)
                folder = Path(project["folder_path"])
                folder_assets = [asset_from_file(path, folder) for path in iter_files_limited(folder, max_files=200)]
                payload.update(
                    {
                        "project": project,
                        "project_assets": list_project_assets(conn, pid),
                        "folder_assets": folder_assets,
                        "conversations": list_conversations(conn, project_id=pid),
                    }
                )
            self.send_json(payload)

    def handle_qa_knowledge_search(self, query: str, forced_mode: str | None = None) -> None:
        params = parse_qs(query)
        question = (params.get("q") or params.get("query") or [""])[0].strip()
        if not question:
            self.send_json({"ok": False, "error": "missing query parameter q"}, status=400)
            return
        try:
            top_k = int((params.get("top_k") or [QA_KNOWLEDGE_TOP_K])[0])
        except (TypeError, ValueError):
            top_k = QA_KNOWLEDGE_TOP_K
        if not QA_KNOWLEDGE_ENABLED:
            self.send_json({"ok": True, "enabled": False, "evidence": [], "message": "知识库检索已关闭"})
            return
        mode = forced_mode or (params.get("mode") or [QA_KNOWLEDGE_SEARCH_MODE])[0]
        pack = search_knowledge(question, db_path=QA_KNOWLEDGE_DB_PATH, top_k=max(1, min(top_k, 20)), mode=mode)
        self.send_json({"ok": True, **pack})

    def handle_qa_knowledge_pgvector_rebuild(self) -> None:
        try:
            payload = self.read_json_body()
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        limit = payload.get("limit")
        try:
            limit_int = int(limit) if limit not in {None, ""} else None
        except (TypeError, ValueError):
            self.send_json({"ok": False, "error": "limit must be an integer"}, status=400)
            return
        force = str(payload.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
        result = rebuild_pgvector_embeddings(limit=limit_int, force=force)
        self.send_json(result, status=200 if result.get("ok") else 500)

    def handle_qa_projects_post(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        action = str(payload.get("action") or "create")
        try:
            with db_connect() as conn:
                if action in {"create", "bind_folder"}:
                    project = create_project(
                        conn,
                        str(payload.get("name") or payload.get("display_name") or "新项目"),
                        folder_path=payload.get("folder_path") if action == "bind_folder" else None,
                        description=str(payload.get("description") or ""),
                    )
                    self.send_json(
                        {
                            "ok": True,
                            "project": project,
                            "projects": list_projects(conn),
                            "project_assets": list_project_assets(conn, int(project["id"])),
                            "folder_assets": [
                                asset_from_file(path, Path(project["folder_path"]))
                                for path in iter_files_limited(Path(project["folder_path"]), max_files=200)
                            ],
                        }
                    )
                    return
                if action in {"rename", "pin", "unpin", "archive", "delete"}:
                    project_id = int(payload.get("project_id") or payload.get("id") or 0)
                    if project_id <= 0:
                        self.send_json({"ok": False, "error": "missing project_id"}, status=400)
                        return
                    ts = iso_now()
                    row = conn.execute("SELECT * FROM qa_projects WHERE id = ?", (project_id,)).fetchone()
                    if row is None:
                        self.send_json({"ok": False, "error": "project not found"}, status=404)
                        return
                    if action == "rename":
                        name = str(payload.get("name") or "").strip()
                        if not name:
                            self.send_json({"ok": False, "error": "missing project name"}, status=400)
                            return
                        conn.execute("UPDATE qa_projects SET name = ?, updated_at = ? WHERE id = ?", (name[:120], ts, project_id))
                    elif action == "pin":
                        conn.execute("UPDATE qa_projects SET is_pinned = 1, updated_at = ? WHERE id = ?", (ts, project_id))
                    elif action == "unpin":
                        conn.execute("UPDATE qa_projects SET is_pinned = 0, updated_at = ? WHERE id = ?", (ts, project_id))
                    elif action == "archive":
                        conn.execute(
                            "UPDATE qa_projects SET status = 'archived', is_pinned = 0, archived_at = ?, updated_at = ? WHERE id = ?",
                            (ts, ts, project_id),
                        )
                    elif action == "delete":
                        conn.execute("DELETE FROM project_assets WHERE project_id = ?", (project_id,))
                        conn.execute("UPDATE qa_conversations SET project_id = NULL WHERE project_id = ?", (project_id,))
                        conn.execute("DELETE FROM qa_projects WHERE id = ?", (project_id,))
                    conn.commit()
                    project_row = conn.execute("SELECT * FROM qa_projects WHERE id = ?", (project_id,)).fetchone()
                    self.send_json(
                        {
                            "ok": True,
                            "project": project_from_row(project_row) if project_row else None,
                            "projects": list_projects(conn),
                            "conversations": list_conversations(conn),
                        }
                    )
                    return
                self.send_json({"ok": False, "error": f"unknown project action: {action}"}, status=400)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_qa_project_assets(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        action = str(payload.get("action") or "add")
        try:
            with db_connect() as conn:
                if action == "add":
                    asset = add_project_asset(conn, payload)
                    self.send_json(
                        {
                            "ok": True,
                            "asset": asset,
                            "project_assets": list_project_assets(conn, int(payload.get("project_id"))),
                        }
                    )
                    return
                if action == "remove":
                    asset_id = int(payload.get("asset_id") or 0)
                    row = conn.execute("SELECT project_id FROM project_assets WHERE id = ?", (asset_id,)).fetchone()
                    conn.execute("DELETE FROM project_assets WHERE id = ?", (asset_id,))
                    conn.commit()
                    self.send_json(
                        {
                            "ok": True,
                            "project_assets": list_project_assets(conn, int(row["project_id"])) if row else [],
                        }
                    )
                    return
                self.send_json({"ok": False, "error": f"unknown asset action: {action}"}, status=400)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_qa_open_path(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        try:
            result = open_allowed_local_path(str(payload.get("file_path") or payload.get("folder_path") or ""), str(payload.get("action") or "default"))
            self.send_json({"ok": True, **result})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_qa_conversation_action(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        action = str(payload.get("action") or "").strip().lower()
        raw_ids = payload.get("conversation_ids") or payload.get("ids")
        if raw_ids is None:
            raw_ids = [payload.get("conversation_id") or payload.get("id")]
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        conversation_ids = [str(item or "").strip() for item in raw_ids if str(item or "").strip()]
        if not conversation_ids:
            self.send_json({"ok": False, "error": "missing conversation_id"}, status=400)
            return
        try:
            with db_connect() as conn:
                conversation_id = conversation_ids[0]
                placeholders = ",".join("?" for _ in conversation_ids)
                rows = conn.execute(
                    f"SELECT * FROM qa_conversations WHERE id IN ({placeholders})",
                    conversation_ids,
                ).fetchall()
                found_ids = {row["id"] for row in rows}
                missing_ids = [item for item in conversation_ids if item not in found_ids]
                row = rows[0] if len(conversation_ids) == 1 and rows else None
                if missing_ids:
                    self.send_json({"ok": False, "error": "conversation not found", "missing_ids": missing_ids}, status=404)
                    return
                if row is None:
                    row = rows[0] if rows else None
                ts = iso_now()
                if action == "rename":
                    if len(conversation_ids) != 1:
                        self.send_json({"ok": False, "error": "rename only supports one conversation"}, status=400)
                        return
                    title = str(payload.get("title") or "").strip()
                    if not title:
                        self.send_json({"ok": False, "error": "missing conversation title"}, status=400)
                        return
                    conn.execute("UPDATE qa_conversations SET title = ?, updated_at = ? WHERE id = ?", (title[:160], ts, conversation_id))
                elif action == "pin":
                    if len(conversation_ids) != 1:
                        self.send_json({"ok": False, "error": "pin only supports one conversation"}, status=400)
                        return
                    conn.execute("UPDATE qa_conversations SET is_pinned = 1, updated_at = ? WHERE id = ?", (ts, conversation_id))
                elif action == "unpin":
                    if len(conversation_ids) != 1:
                        self.send_json({"ok": False, "error": "unpin only supports one conversation"}, status=400)
                        return
                    conn.execute("UPDATE qa_conversations SET is_pinned = 0, updated_at = ? WHERE id = ?", (ts, conversation_id))
                elif action == "archive":
                    conn.execute(
                        f"UPDATE qa_conversations SET status = 'archived', is_pinned = 0, archived_at = ?, updated_at = ? WHERE id IN ({placeholders})",
                        [ts, ts, *conversation_ids],
                    )
                elif action == "delete":
                    conn.execute(
                        f"DELETE FROM qa_conversations WHERE id IN ({placeholders})",
                        conversation_ids,
                    )
                elif action == "mark_unread":
                    if len(conversation_ids) != 1:
                        self.send_json({"ok": False, "error": "mark_unread only supports one conversation"}, status=400)
                        return
                    conn.execute("UPDATE qa_conversations SET is_unread = 1, updated_at = ? WHERE id = ?", (ts, conversation_id))
                elif action == "mark_read":
                    if len(conversation_ids) != 1:
                        self.send_json({"ok": False, "error": "mark_read only supports one conversation"}, status=400)
                        return
                    conn.execute("UPDATE qa_conversations SET is_unread = 0, updated_at = ? WHERE id = ?", (ts, conversation_id))
                elif action == "move_to_project":
                    if len(conversation_ids) != 1:
                        self.send_json({"ok": False, "error": "move_to_project only supports one conversation"}, status=400)
                        return
                    project_id = payload.get("project_id")
                    conn.execute(
                        "UPDATE qa_conversations SET project_id = ?, updated_at = ? WHERE id = ?",
                        (int(project_id) if project_id else None, ts, conversation_id),
                    )
                else:
                    self.send_json({"ok": False, "error": f"unknown conversation action: {action}"}, status=400)
                    return
                conn.commit()
                new_row = None
                if len(conversation_ids) == 1 and action != "delete":
                    new_row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
                self.send_json(
                    {
                        "ok": True,
                        "conversation": conversation_from_row(new_row) if new_row else None,
                        "affected_ids": conversation_ids,
                        "conversations": list_conversations(conn),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_qa_new_conversation(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        title = str(payload.get("title") or "新对话")
        with db_connect() as conn:
            short_seed = None
            short_conversation_id = str(payload.get("short_window_conversation_id") or "").strip()
            short_queue_id = payload.get("short_window_queue_id") or payload.get("queue_id")
            if short_conversation_id or short_queue_id:
                short_seed = self.short_window_seed_context(short_conversation_id, short_queue_id)
                if short_seed:
                    queue = short_seed.get("queue") or {}
                    title = str(
                        payload.get("title")
                        or f"短时队列 {queue.get('queue_end_ts') or queue.get('queue_start_ts') or queue.get('queue_id')}"
                    )
            conversation = create_conversation(conn, title=title)
            project_id = payload.get("project_id")
            if project_id:
                conn.execute("UPDATE qa_conversations SET project_id = ? WHERE id = ?", (int(project_id), conversation["id"]))
                conn.commit()
                row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation["id"],)).fetchone()
                conversation = conversation_from_row(row)
            messages: list[dict[str, Any]] = []
            if short_seed:
                content = self.short_window_seed_markdown(short_seed)
                conn.execute(
                    """
                    INSERT INTO qa_messages(conversation_id, role, content, hidden_context_json, created_at)
                    VALUES (?, 'assistant', ?, ?, ?)
                    """,
                    (
                        conversation["id"],
                        content,
                        json.dumps({"source": "short_window_queue", **short_seed}, ensure_ascii=False, default=str),
                        iso_now(),
                    ),
                )
                conn.execute("UPDATE qa_conversations SET updated_at = ? WHERE id = ?", (iso_now(), conversation["id"]))
                conn.commit()
                row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation["id"],)).fetchone()
                conversation = conversation_from_row(row)
                messages = load_messages(conn, conversation["id"])
            self.send_json(
                {
                    "ok": True,
                    "conversation": conversation,
                    "conversations": list_conversations(conn),
                    "messages": messages,
                }
            )

    def handle_qa_snapshot(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        with db_connect() as conn:
            snapshot_id = insert_snapshot(conn, payload)
            self.send_json({"ok": True, "snapshot_id": snapshot_id})

    def handle_qa_chat(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return

        question = str(payload.get("message") or "").strip()
        if not question:
            self.send_json({"ok": False, "error": "message is required"}, status=400)
            return

        wants_stream = bool(payload.get("stream")) or "text/event-stream" in self.headers.get("Accept", "")
        if wants_stream:
            self.handle_qa_chat_stream(payload, question)
            return

        self.handle_qa_chat_json(payload, question)

    def prepare_qa_chat(
        self,
        payload: dict[str, Any],
        question: str,
        include_conversations: bool = True,
    ) -> dict[str, Any]:
        prepare_started = time.perf_counter()
        timing_ms: dict[str, Any] = {}
        with db_connect() as conn:
            db_started = time.perf_counter()
            conversation_id = str(payload.get("conversation_id") or "")
            row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                conversation = create_conversation(conn)
                conversation_id = conversation["id"]
            project_id = payload.get("project_id")
            project_id_int = int(project_id) if str(project_id or "").strip() else None
            if project_id_int is not None:
                conn.execute(
                    "UPDATE qa_conversations SET project_id = ?, updated_at = ? WHERE id = ?",
                    (project_id_int, iso_now(), conversation_id),
                )
                conn.commit()

            current_snapshot = payload.get("current_snapshot")
            current_prompt_snapshot: dict[str, Any] | None = None
            pg_prompt_snapshot: dict[str, Any] | None = None
            if current_snapshot:
                current_snapshot_id = insert_snapshot(conn, current_snapshot)
                current_prompt_snapshot = snapshot_by_id(conn, current_snapshot_id)
            pg_snapshot: dict[str, Any] | None = None
            trend_snapshots: list[dict[str, Any]] = []
            trend_meta: dict[str, Any] = {}
            timing_ms["assistant_before_pg"] = round((time.perf_counter() - db_started) * 1000, 1)
            pg_started = time.perf_counter()
            try:
                with self.pg_connect() as pg_conn:
                    latest_pg_started = time.perf_counter()
                    pg_snapshot = self.latest_pg_snapshot_for_qa(pg_conn)
                    timing_ms["pg_latest"] = round((time.perf_counter() - latest_pg_started) * 1000, 1)
                    same_trend_window = (pg_snapshot or {}).get("pg_window_minutes") == QA_TREND_WINDOW_MINUTES
                    latest_diagnosis_ts = (
                        ((pg_snapshot or {}).get("diagnosis") or {}).get("diagnosis_ts")
                        if same_trend_window
                        else None
                    )
                    trend_pg_started = time.perf_counter()
                    trend_snapshots, trend_meta = self.recent_pg_diagnosis_snapshots_for_qa(
                        hours=QA_TREND_HOURS,
                        limit=QA_TREND_DIAGNOSIS_LIMIT,
                        conn=pg_conn,
                        latest_ts=latest_diagnosis_ts,
                        context_version=(pg_snapshot or {}).get("pg_context_version") if same_trend_window else None,
                    )
                    timing_ms["pg_trend"] = round((time.perf_counter() - trend_pg_started) * 1000, 1)
            except Exception as exc:  # noqa: BLE001
                trend_meta = {"trend_error": sanitize_model_exposure(exc)}
            timing_ms["pg_context"] = round((time.perf_counter() - pg_started) * 1000, 1)
            timing_ms["trend_cache_hit"] = bool(trend_meta.get("trend_cache_hit"))
            if pg_snapshot:
                pg_snapshot_id = insert_snapshot(conn, pg_snapshot)
                pg_prompt_snapshot = snapshot_by_id(conn, pg_snapshot_id)

            previous_anchor = last_qa_context_anchor(conn, conversation_id)
            previous_tool_context = last_qa_tool_context(conn, conversation_id)
            latest_state_snapshot = choose_latest_state_snapshot(
                [current_prompt_snapshot, pg_prompt_snapshot, latest_snapshot(conn)]
            )
            if not trend_snapshots:
                trend_snapshots = recent_snapshots(
                    conn,
                    hours=QA_TREND_HOURS,
                    limit=QA_TREND_DIAGNOSIS_LIMIT,
                )
                trend_meta = {
                    **trend_meta,
                    "trend_source": "bf_assistant.furnace_snapshots",
                    "trend_source_label": "QA快照兜底",
                    "trend_count": len(trend_snapshots),
                    "trend_start_time": trend_snapshots[0].get("source_time") if trend_snapshots else None,
                    "trend_end_time": trend_snapshots[-1].get("source_time") if trend_snapshots else None,
                }
            snapshots = trend_snapshots or ([latest_state_snapshot] if latest_state_snapshot else [])
            context_meta = {
                "context_mode": "latest_snapshot_plus_pg_8h_trend",
                "anchor_message_id": previous_anchor.get("message_id") if previous_anchor else None,
                "anchor_snapshot_id": previous_anchor.get("snapshot_id") if previous_anchor else None,
                "previous_latest_snapshot_source_time": (
                    previous_anchor.get("latest_snapshot_source_time") if previous_anchor else None
                ),
                "previous_trend_end_time": previous_anchor.get("trend_end_time") if previous_anchor else None,
                "previous_trend_count": previous_anchor.get("trend_count") if previous_anchor else None,
                "baseline_hours": QA_TREND_HOURS,
                "delta_only": False,
                "latest_snapshot": latest_state_snapshot,
                **trend_meta,
            }
            snapshot_id = None
            if latest_state_snapshot:
                try:
                    snapshot_id = int(latest_state_snapshot.get("id"))
                except (TypeError, ValueError):
                    snapshot_id = None
            history = load_messages(conn, conversation_id)
            context_assets = payload.get("context_assets") if isinstance(payload.get("context_assets"), list) else []
            report_attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
            context_assets = [*context_assets, *report_attachments_to_context_assets(conn, report_attachments)]
            project_context, context_refs = build_project_context(
                conn,
                context_assets,
                manual_context_text=str(payload.get("manual_context_text") or ""),
            )
            timing_ms["db_context"] = round((time.perf_counter() - db_started) * 1000, 1)
            timing_ms["assistant_after_pg"] = round(
                timing_ms["db_context"] - timing_ms["assistant_before_pg"] - timing_ms["pg_context"],
                1,
            )
            tool_context = update_tool_context(
                previous_tool_context,
                question,
                detected_objects=qa_mcp_variables(question),
                duration_minutes=qa_mcp_duration_minutes(question),
            )
            routing_question = enrich_routing_question(question, tool_context)
            mcp_started = time.perf_counter()
            mcp_prefetch = qa_mcp_prefetch(routing_question)
            timing_ms["mcp_prefetch"] = round((time.perf_counter() - mcp_started) * 1000, 1)
            knowledge_started = time.perf_counter()
            knowledge_pack = qa_search_knowledge(question, mcp_prefetch=mcp_prefetch)
            timing_ms["knowledge"] = round((time.perf_counter() - knowledge_started) * 1000, 1)
            use_mcp_tools = qa_mcp_should_use_tools(routing_question, payload, mcp_prefetch)
            hidden_context = {
                "window_hours": QA_TREND_HOURS,
                "context_mode": context_meta.get("context_mode"),
                "anchor_message_id": context_meta.get("anchor_message_id"),
                "anchor_snapshot_id": context_meta.get("anchor_snapshot_id"),
                "delta_only": bool(context_meta.get("delta_only")),
                "snapshot_ids": [item.get("id") for item in snapshots],
                "latest_snapshot_id": snapshot_id,
                "latest_snapshot_source_time": latest_state_snapshot.get("source_time") if latest_state_snapshot else None,
                "previous_latest_snapshot_source_time": context_meta.get("previous_latest_snapshot_source_time"),
                "previous_trend_end_time": context_meta.get("previous_trend_end_time"),
                "previous_trend_count": context_meta.get("previous_trend_count"),
                "trend_source": context_meta.get("trend_source"),
                "trend_count": len(snapshots),
                "trend_limit": context_meta.get("trend_limit"),
                "trend_cadence_minutes": context_meta.get("trend_cadence_minutes"),
                "trend_start_time": context_meta.get("trend_start_time"),
                "trend_end_time": context_meta.get("trend_end_time"),
                "trend_diagnosis_ids": [
                    item.get("pg_diagnosis_id") or item.get("id")
                    for item in snapshots
                ],
                "trend_error": context_meta.get("trend_error"),
                "project_id": project_id_int,
                "context_asset_count": len(context_refs),
                "mcp_prefetch": {k: v for k, v in mcp_prefetch.items() if k != "context_text"},
                "mcp_tool_calling": use_mcp_tools,
                "mcp_conversation_context": tool_context,
                "knowledge_enabled": bool(knowledge_pack.get("enabled")),
                "knowledge_intent": (knowledge_pack.get("intent") or {}).get("intent_type"),
                "knowledge_chunk_ids": [item.get("chunk_id") for item in knowledge_pack.get("evidence", [])],
            }
            hidden_context["qa_prepare_timing_ms"] = {
                **timing_ms,
                "total": round((time.perf_counter() - prepare_started) * 1000, 1),
            }
            user_message_id = add_message(
                conn,
                conversation_id,
                "user",
                question,
                snapshot_id=snapshot_id,
                hidden_context=hidden_context,
            )
            if context_refs:
                insert_context_refs(conn, conversation_id, user_message_id, project_id_int, context_refs)
                conn.commit()

            conv_row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
            return {
                "conversation_id": conversation_id,
                "snapshot_id": snapshot_id,
                "hidden_context": hidden_context,
                "routing_question": routing_question,
                "messages": build_hidden_qa_messages(
                    question,
                    snapshots,
                    history,
                    project_context=project_context,
                    mcp_context=str(mcp_prefetch.get("context_text") or ""),
                    context_meta=context_meta,
                    knowledge_context=evidence_pack_text(knowledge_pack),
                ),
                "conversation": conversation_from_row(conv_row),
                "conversations": list_conversations(conn) if include_conversations else None,
                "context_refs": context_refs,
                "mcp_prefetch": mcp_prefetch,
                "knowledge_evidence": knowledge_pack.get("evidence", []),
                "knowledge": {
                    "enabled": bool(knowledge_pack.get("enabled")),
                    "message": knowledge_pack.get("message"),
                    "intent": knowledge_pack.get("intent"),
                },
                "qa_prepare_timing_ms": hidden_context["qa_prepare_timing_ms"],
                "use_mcp_tools": use_mcp_tools,
            }

    def handle_qa_chat_json(self, payload: dict[str, Any], question: str) -> None:
        try:
            prepared = self.prepare_qa_chat(payload, question)
            mcp_tool_trace: list[dict[str, Any]] = []
            if prepared.get("use_mcp_tools"):
                tool_result = run_qa_mcp_tool_loop(
                    prepared["messages"],
                    routing_question=prepared.get("routing_question") or "",
                )
                mcp_tool_trace = tool_result.get("tool_trace") or []
                prepared["hidden_context"]["mcp_tool_trace"] = mcp_tool_trace
                prepared["hidden_context"]["mcp_conversation_context"] = context_with_tool_trace(
                    prepared["hidden_context"].get("mcp_conversation_context"),
                    mcp_tool_trace,
                )
                if tool_result.get("ok") is False and not tool_result.get("answer"):
                    answer = f"数据库查询失败：{tool_result.get('error') or '未知错误'}"
                else:
                    answer = clean_llm_output(tool_result.get("answer") or "")
            else:
                answer = call_ollama_chat(prepared["messages"])
            answer = append_mcp_chart_links(answer, mcp_tool_trace)
            with db_connect() as conn:
                add_message(
                    conn,
                    prepared["conversation_id"],
                    "assistant",
                    answer,
                    snapshot_id=prepared["snapshot_id"],
                    hidden_context=prepared["hidden_context"],
                )
                conv_row = conn.execute(
                    "SELECT * FROM qa_conversations WHERE id = ?",
                    (prepared["conversation_id"],),
                ).fetchone()
                self.send_json(
                    {
                        "ok": True,
                        "answer": answer,
                        "conversation": conversation_from_row(conv_row),
                        "conversations": list_conversations(conn),
                        "messages": load_messages(conn, prepared["conversation_id"]),
                        "context_refs": prepared.get("context_refs", []),
                        "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                        "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                        "mcp_tool_trace": mcp_tool_trace,
                    }
                )
        except HTTPError as exc:
            detail = sanitize_model_exposure(exc.read().decode("utf-8", errors="replace"))
            self.send_json({"ok": False, "error": f"高炉大模型服务 HTTP {exc.code}", "detail": detail}, status=200)
        except URLError as exc:
            self.send_json(
                {"ok": False, "error": f"高炉大模型服务不可达：{sanitize_model_exposure(exc.reason)}"},
                status=200,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": f"问答服务失败：{exc}"}, status=500)

    def handle_qa_chat_stream(self, payload: dict[str, Any], question: str) -> None:
        self.send_response(200)
        self.add_cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.end_headers()
        self.write_qa_event("start", {"ok": True, "stage": "preparing"})
        try:
            prepared = self.prepare_qa_chat(payload, question, include_conversations=False)
        except Exception as exc:  # noqa: BLE001
            self.write_qa_event("error", {"ok": False, "error": f"问答服务失败：{exc}"})
            return

        self.write_qa_event(
            "start",
            {
                "ok": True,
                "stage": "prepared",
                "conversation": prepared["conversation"],
                "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                "knowledge": prepared.get("knowledge"),
                "qa_prepare_timing_ms": prepared.get("qa_prepare_timing_ms"),
            },
        )
        if (prepared.get("mcp_prefetch") or {}).get("used"):
            prefetch_event = {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"}
            if "tool" not in prefetch_event:
                prefetch_event["tool"] = ((prefetch_event.get("summary") or {}).get("tool") or "qa_mcp_prefetch")
            self.write_qa_event(
                "tool_result",
                prefetch_event,
            )

        answer_parts: list[str] = []
        mcp_tool_trace: list[dict[str, Any]] = []
        model_timing: dict[str, Any] = {}
        try:
            stream_messages = prepared["messages"]
            precomputed_answer: str | None = None
            if prepared.get("use_mcp_tools"):
                tool_result = run_qa_mcp_tool_loop(
                    prepared["messages"],
                    emit=self.write_qa_event,
                    stop_after_tool_round=False,
                    routing_question=prepared.get("routing_question") or "",
                )
                mcp_tool_trace = tool_result.get("tool_trace") or []
                prepared["hidden_context"]["mcp_tool_trace"] = mcp_tool_trace
                prepared["hidden_context"]["mcp_conversation_context"] = context_with_tool_trace(
                    prepared["hidden_context"].get("mcp_conversation_context"),
                    mcp_tool_trace,
                )
                if tool_result.get("tool_used") and tool_result.get("needs_final"):
                    stream_messages = tool_result.get("messages") or prepared["messages"]
                elif tool_result.get("ok") is False and not tool_result.get("answer"):
                    precomputed_answer = f"数据库查询失败：{tool_result.get('error') or '未知错误'}"
                else:
                    precomputed_answer = clean_llm_output(tool_result.get("answer") or "")

            if precomputed_answer is not None:
                answer = append_mcp_chart_links(precomputed_answer, mcp_tool_trace)
                self.write_qa_event("delta", {"delta": answer, "content": answer})
                with db_connect() as conn:
                    add_message(
                        conn,
                        prepared["conversation_id"],
                        "assistant",
                        answer,
                        snapshot_id=prepared["snapshot_id"],
                        hidden_context=prepared["hidden_context"],
                    )
                    conv_row = conn.execute(
                        "SELECT * FROM qa_conversations WHERE id = ?",
                        (prepared["conversation_id"],),
                    ).fetchone()
                    final_payload = {
                        "ok": True,
                        "answer": answer,
                        "conversation": conversation_from_row(conv_row),
                        "conversations": list_conversations(conn),
                        "messages": load_messages(conn, prepared["conversation_id"]),
                        "context_refs": prepared.get("context_refs", []),
                        "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                        "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                        "mcp_tool_trace": mcp_tool_trace,
                    }
                self.write_qa_event("final", final_payload)
                self.write_qa_event("done", {"ok": True})
                return

            chat_payload = build_api_chat_payload(
                {
                    "model": normalize_model(None),
                    "temperature": 0.1,
                    "max_tokens": 900,
                    "messages": stream_messages,
                    "stream": True,
                    "stop": ["莿莿", "<|im_start|>", "<|im_end|>", "\nassistant", "\nuser"],
                }
            )
            req = build_ollama_request("/api/chat", body=json_bytes(chat_payload), stream=True)
            last_safe_stream_content = ""
            with urlopen(req, timeout=300) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    try:
                        obj = json.loads(line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    content = ((obj.get("message") or {}).get("content") or obj.get("response") or "")
                    if content:
                        answer_parts.append(content)
                        full = "".join(answer_parts)
                        safe_full = clean_llm_output(full) if full.strip() else ""
                        safe_delta = (
                            safe_full[len(last_safe_stream_content):]
                            if safe_full.startswith(last_safe_stream_content)
                            else safe_full
                        )
                        last_safe_stream_content = safe_full
                        self.write_qa_event(
                            "delta",
                            {
                                "delta": safe_delta,
                                "content": safe_full,
                            },
                        )
                    if obj.get("done"):
                        model_timing = ollama_response_timing(obj)
                        break

            answer = append_mcp_chart_links(clean_llm_output("".join(answer_parts)), mcp_tool_trace)
            with db_connect() as conn:
                add_message(
                    conn,
                    prepared["conversation_id"],
                    "assistant",
                    answer,
                    snapshot_id=prepared["snapshot_id"],
                    hidden_context=prepared["hidden_context"],
                )
                conv_row = conn.execute(
                    "SELECT * FROM qa_conversations WHERE id = ?",
                    (prepared["conversation_id"],),
                ).fetchone()
                final_payload = {
                    "ok": True,
                    "answer": answer,
                    "conversation": conversation_from_row(conv_row),
                    "conversations": list_conversations(conn),
                    "messages": load_messages(conn, prepared["conversation_id"]),
                    "context_refs": prepared.get("context_refs", []),
                    "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                    "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                    "mcp_tool_trace": mcp_tool_trace,
                    "model_timing": model_timing,
                }
            self.write_qa_event("final", final_payload)
            self.write_qa_event("done", {"ok": True})
        except HTTPError as exc:
            detail = sanitize_model_exposure(exc.read().decode("utf-8", errors="replace"))
            self.write_qa_event("error", {"ok": False, "error": f"高炉大模型服务 HTTP {exc.code}", "detail": detail})
        except URLError as exc:
            self.write_qa_event(
                "error",
                {"ok": False, "error": f"高炉大模型服务不可达：{sanitize_model_exposure(exc.reason)}"},
            )
        except Exception as exc:  # noqa: BLE001
            self.write_qa_event("error", {"ok": False, "error": f"问答服务失败：{exc}"})

    def write_qa_event(self, event: str, payload: object) -> None:
        try:
            self.wfile.write(qa_sse_event(event, payload))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def handle_models(self) -> None:
        self.send_json(
            {
                "object": "list",
                "data": [
                    {
                        "id": PUBLIC_MODEL_NAME,
                        "object": "model",
                        "created": 0,
                        "owned_by": "blast-furnace-runtime",
                    }
                ],
            }
        )

    def handle_chat_completions(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self.send_json({"error": f"bad json: {exc}"}, status=400)
            return

        chat_payload = build_api_chat_payload(payload)
        stream = bool(chat_payload.get("stream"))
        body = json_bytes(chat_payload)
        req = build_ollama_request("/api/chat", body=body, stream=stream)

        try:
            with urlopen(req, timeout=300) as resp:
                if stream:
                    self.forward_api_chat_stream(resp, chat_payload["model"])
                else:
                    self.forward_api_chat_response(resp, chat_payload["model"])
        except HTTPError as exc:
            detail = sanitize_model_exposure(exc.read().decode("utf-8", errors="replace"))
            self.send_json({"error": f"高炉大模型服务 HTTP {exc.code}", "detail": detail}, status=exc.code)
        except URLError as exc:
            self.send_json({"error": f"高炉大模型服务网络错误：{sanitize_model_exposure(exc.reason)}"}, status=502)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=502)

    def forward_api_chat_stream(self, resp, model: str) -> None:
        self.send_response(200)
        self.add_cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.end_headers()

        while True:
            line = resp.readline()
            if not line:
                break
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            content = ((obj.get("message") or {}).get("content") or obj.get("response") or "")
            if content:
                self.wfile.write(openai_chunk(model, content=content))
                self.wfile.flush()
            if obj.get("done"):
                done_reason = obj.get("done_reason") or "stop"
                self.wfile.write(openai_chunk(model, finish_reason=done_reason))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                break

    def forward_api_chat_response(self, resp, model: str) -> None:
        obj = json.loads(resp.read().decode("utf-8", errors="replace"))
        content = ((obj.get("message") or {}).get("content") or obj.get("response") or "")
        payload = {
            "id": f"chatcmpl-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": obj.get("done_reason") or "stop",
                }
            ],
        }
        self.send_json(payload)

    def forward_response(self, resp, content_type: str) -> None:
        data = resp.read()
        self.send_response(getattr(resp, "status", 200))
        self.add_cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self, request_path: str) -> None:
        rel = unquote(request_path.lstrip("/")).replace("\\", "/")

        # Keep old bookmarks working when the frontend directory name is
        # included in the URL path, for example /高炉前端数据/frontend_dashboard_v3.html.
        for prefix in {BASE_DIR.name, "高炉前端数据"}:
            if rel == prefix:
                rel = ""
                break
            if rel.startswith(prefix + "/"):
                rel = rel[len(prefix) + 1 :]
                break

        if not rel or rel in {"frontend_dashboard_v3.html", "frontend_dashboard_v3.server.html"}:
            rel = INDEX_FILE
        target = (BASE_DIR / rel).resolve()
        if BASE_DIR not in target.parents and target != BASE_DIR:
            self.send_json({"error": "path outside static root"}, status=403)
            return
        if not target.exists() or not target.is_file():
            self.send_json({"error": "file not found"}, status=404)
            return
        data = inject_trend_history_loader(target.read_bytes(), target)
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix.lower() in {".html", ".js", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.add_cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: object, status: int = 200, headers: dict[str, str] | None = None) -> None:
        data = json_bytes(payload)
        self.send_response(status)
        self.add_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def add_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def main() -> None:
    skip_assistant_startup = os.environ.get("BF_SKIP_ASSISTANT_STARTUP", "0").strip().lower() in {"1", "true", "yes"}
    if skip_assistant_startup:
        print("assistant/RAG startup initialization skipped for isolated local prototype")
    else:
        try:
            with db_connect():
                pass
            print("assistant PostgreSQL runtime initialized")
        except Exception as exc:  # noqa: BLE001
            print(f"assistant PostgreSQL startup check failed: {sanitize_model_exposure(exc)}")
        knowledge_runtime = initialize_knowledge_runtime()
        if knowledge_runtime.get("ok"):
            print("knowledge retrieval runtime initialized")
        else:
            detail = knowledge_runtime.get("message") or (knowledge_runtime.get("vector") or {}).get("message") or "unknown"
            print(f"knowledge retrieval startup check failed: {sanitize_model_exposure(detail)}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"8092 proxy/static server: http://{HOST}:{PORT}/")
    print(f"model upstream: {OLLAMA_BASE_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()





