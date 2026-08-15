from __future__ import annotations

import asyncio
import copy
import json
import html
import hmac
import hashlib
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
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from assistant_pg import db_connect as _assistant_pg_connect, ensure_column, raw_pg_connect as _assistant_raw_pg_connect
import diagnosis_model_review
import diagnosis_ai_analysis_api
import diagnosis_review
import diag_ai_evidence
import hcz_upward_rule_api
import abc_rule_assistant_analysis
# REQ-8093-BC-SCORE-CONTRIBUTION-20260814: public A/B/C score explanation adapter.
from abc_score_explanation import build_score_explanation
from http_static_compression import compress_static_payload
from heat_performance_quality import HeatPerformanceQualityStore
import si_v20_shadow
from mcp_conversation_context import (
    context_with_cross_source_snapshot,
    context_with_tool_trace,
    enrich_routing_question,
    update_tool_context,
)
from mcp_tool_policy import ToolPolicyLimits, validate_tool_call
from mcp_host import (
    McpClientManager,
    McpHostError,
    McpServerRegistry,
    load_server_registry,
    select_mcp_servers,
)
from mcp_host.cross_source_plan import (  # noqa: E402
    CrossSourceFact,
    CrossSourcePlan,
    CrossSourceStep,
    CrossSourceSnapshot,
    failed_snapshot,
    partial_snapshot,
    success_snapshot,
)

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
ABC_SERVICE_DIR = BASE_DIR.parent / "自动诊断服务"
if str(ABC_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(ABC_SERVICE_DIR))
from abc_rule_engine import public_rule  # noqa: E402
from abc_rule_catalog import RULE_BY_ID  # noqa: E402
from abc_rule_engine import load_config as load_abc_config  # noqa: E402
from abc_public_review import build_public_review  # noqa: E402
from abc_rule_config_store import publish_atomic as publish_abc_config  # noqa: E402
from abc_term_semantics import term_semantics as abc_term_semantics  # noqa: E402
import thermal_trend_rule  # noqa: E402
ABC_CONFIG_PATH = ABC_SERVICE_DIR / "config" / "abc_furnace_rules.v1.json"
THERMAL_TREND_CONFIG_PATH = ASSISTANT_BACKEND_DIR / "config" / "thermal_trend_rule.v1.json"
THERMAL_TREND_CONDITION_PATH = BASE_DIR / "data" / "thermal_trend_condition.v1.json"
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
QA_GUEST_ENABLED = os.environ.get("BF_QA_GUEST_ENABLED", "1").strip().lower() not in {
    "0", "false", "no", "off",
}
QA_GUEST_ROOM_KEY = os.environ.get("BF_QA_GUEST_ROOM_KEY", "").strip()
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
DIAGNOSIS_MODEL_REVIEW_ENABLED = os.environ.get(
    "BF_DIAGNOSIS_MODEL_REVIEW_ENABLED", "1"
).strip().lower() not in {"0", "false", "off", "no"}
DIAGNOSIS_MODEL_REVIEW_CACHE_SECONDS = float(
    os.environ.get("BF_DIAGNOSIS_MODEL_REVIEW_CACHE_SECONDS", "900")
)
_DIAGNOSIS_MODEL_REVIEW_CACHE = diagnosis_model_review.DiagnosisModelReviewCache(
    ttl_seconds=DIAGNOSIS_MODEL_REVIEW_CACHE_SECONDS
)
DIAGNOSIS_AI_ANALYSIS_ENABLED = os.environ.get(
    "BF_DIAGNOSIS_AI_ANALYSIS_ENABLED", "0"
).strip().lower() not in {"0", "false", "off", "no"}
DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED = os.environ.get(
    "BF_DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED", "1"
).strip().lower() not in {"0", "false", "off", "no"}
DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES = max(
    1, int(os.environ.get("BF_DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES", "5"))
)
DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS = max(
    10.0, float(os.environ.get("BF_DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS", "30"))
)
DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS = max(
    30.0, float(os.environ.get("BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS", "120"))
)
DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT = max(
    2, min(24, int(os.environ.get("BF_DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT", "12")))
)
_DIAGNOSIS_AI_ANALYSIS_LOCK = threading.Lock()
_DIAGNOSIS_AI_ANALYSIS_STOP = threading.Event()
_DIAGNOSIS_AI_ANALYSIS_THREAD: threading.Thread | None = None
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
_QA_GUEST_ROOM_LOCKS_GUARD = threading.Lock()
_QA_GUEST_ROOM_LOCKS: dict[str, threading.Lock] = {}


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ABC_RULE_ASSISTANT_ENABLED = _env_enabled(
    "BF_ABC_RULE_ASSISTANT_ENABLED", default=(PORT == 8094)
)
from mcp_host.client_manager import lifecycle_error
ABC_RULE_ASSISTANT_AUTO_ANALYSIS = _env_enabled(
    "BF_ABC_RULE_ASSISTANT_AUTO_ANALYSIS", default=(PORT == 8094)
)
ABC_RULE_ASSISTANT_RETRY_SECONDS = max(
    1.0, float(os.environ.get("BF_ABC_RULE_ASSISTANT_RETRY_SECONDS", "60"))
)
ABC_RULE_INITIAL_QUESTION = "请解释当前炉况规则的判断依据、形成过程与处置顺序。"
ABC_RULE_ASSISTANT_PROMPT_VERSION = os.environ.get(
    "BF_ABC_RULE_ASSISTANT_PROMPT_VERSION", "abc_rule_explanation.v1"
).strip() or "abc_rule_explanation.v1"
ABC_RULE_ASSISTANT_WAIT_SECONDS = max(
    30.0, float(os.environ.get("BF_ABC_RULE_ASSISTANT_WAIT_SECONDS", "300"))
)
ABC_RULE_ASSISTANT_CONTEXT_MAX_BYTES = max(
    32768, int(os.environ.get("BF_ABC_RULE_ASSISTANT_CONTEXT_MAX_BYTES", str(256 * 1024)))
)
ABC_RULE_ASSISTANT_PROMPT_CONTEXT_MAX_BYTES = max(
    8192, int(os.environ.get("BF_ABC_RULE_ASSISTANT_PROMPT_CONTEXT_MAX_BYTES", str(24 * 1024)))
)
_ABC_RULE_ANALYSIS_GUARD = threading.Lock()
_ABC_RULE_ANALYSIS_INFLIGHT: dict[tuple[int, str, str], threading.Event] = {}
QA_MCP_PREFETCH_ENABLED = os.environ.get("BF_QA_MCP_PREFETCH", "1").strip().lower() not in {"0", "false", "no"}
MCP_DATA_SERVER_PATH = Path(
    os.environ.get(
        "BF_QA_MCP_DATA_SERVER",
        str(ASSISTANT_DIR / "mcp" / "bf_data_mcp_server.py"),
    )
)
MCP_SERVER_REGISTRY_PATH = Path(
    os.environ.get(
        "BF_QA_MCP_SERVER_REGISTRY",
        str(ASSISTANT_BACKEND_DIR / "mcp_host" / "server_registry.json"),
    )
)
_MCP_DATA_MODULE: Any | None = None
QA_MCP_TOOLS_ENABLED = os.environ.get("BF_QA_MCP_TOOLS", "1").strip().lower() not in {"0", "false", "no"}
QA_MCP_TOOL_MODE = os.environ.get("BF_QA_MCP_TOOL_MODE", "auto").strip().lower()
QA_MCP_MAX_TOOL_ROUNDS = int(os.environ.get("BF_QA_MCP_MAX_TOOL_ROUNDS", "5"))
QA_MCP_MAX_TOOL_CALLS = int(os.environ.get("BF_QA_MCP_MAX_TOOL_CALLS", "5"))
QA_MCP_PARALLEL_TOOL_CALLS = os.environ.get("BF_QA_MCP_PARALLEL_TOOL_CALLS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
QA_MCP_MAX_PARALLEL_TOOL_CALLS = int(os.environ.get("BF_QA_MCP_MAX_PARALLEL_TOOL_CALLS", "5"))
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
DIAGNOSIS_ADVICE_SOURCE = "foreman_knowledge_only"
QA_MCP_BRIDGE_SYSTEM_PROMPT = (
    "你可以使用冀南钢铁GL02传感器/图表和MES/IMES业务数据库查询能力。"
    "你要结合当前问题与最近对话自主决定是否调用工具，并可以在最多5轮规划内按“查目录→查数据→做计算/绘图→总结”的顺序连续调用。"
    "同一轮中相互独立的只读查询应一次返回多个tool_calls并行执行；存在依赖关系的调用必须放到后续轮次。"
    "追问省略了变量或时间范围时，优先继承最近对话中已经明确的对象；仍有多个可能对象时先查目录，不能唯一确定时再向用户追问。"
    "跨传感器、报表、历史问答、计算或图表能力的对象发现，优先调用search_business_objects；"
    "MES炉次、铁水/炉渣化验和进料成分不明确时调用imes__resolve_imes_natural_language；"
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
    "炉次、铁水/炉渣化验、硅含量、进料成分等MES业务必须使用imes__前缀的只读工具；"
    "当前炉次号调用imes__get_current_heat_context；当前炉次Si及已发布试样调用imes__query_current_heat_chemistry；"
    "当前与上一炉次Si摘要调用imes__get_current_previous_heat_si_summary。"
    "查询任意指定炉次的铁水化学成分时，优先一次调用imes__query_heat_chemistry；"
    "用户只给大概日期、钟点或上午/下午等时间段时，调用imes__query_heat_chemistry_by_time_range，"
    "把原始口语时间放入time_reference，由工具确定对应正式meltno并返回每罐/每试样结果；"
    "heat_reference可填写正式meltno、带日期炉次号或2-4位短炉号，components只填写用户要求的C/Si/Mn/P/S/Ti/V/Cr/Cu/Ni/As，"
    "该工具会自行解析炉次，不要预先重复调用炉次解析工具。"
    "你只能从本轮提供的已注册工具Schema中选择工具并构造参数，不得发明工具名、不得生成SQL。"
    "工具调用会经过服务端白名单和 JSON Schema 校验；收到 TOOL_POLICY_REJECTED 时应修正工具名或参数，不得绕过校验。"
    "不得生成 SQL、数据库连接参数或生产写操作。"
    "如果查询返回无数据或变量缺失，必须明确说明。最终回答只挑取与用户问题有关的有效数值，并同时引用变量、单位、时间戳/时间窗、来源、图片路径或报表路径；不得堆砌无关字段。"
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
    # OPS-8093-STABLE-GLB-URL-REWRITE-20260806-R1
    text = text.replace(
        "models/GL02_FURNACE_BODY_R1.glb?t=${Date.now()}",
        "models/GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1",
    )
    injections = []
    if "__BF_TREND_HISTORY_PATCHED__" not in text:
        injections.append(trend_history_injection())
    if os.environ.get("BF_AUTOMATION_MONITOR", "1").strip().lower() not in {"0", "false", "no"} and "__BF_AUTOMATION_MONITOR__" not in text:
        injections.append(automation_monitor_injection())
    if diagnosis_review.review_enabled() and "__BF_DIAGNOSIS_REVIEW_LOCAL__" not in text:
        injections.append(
            '<link rel="stylesheet" href="/assets/bf-diagnosis-review-local.css?v=20260810-abc33-b4-score-r1">\n'
            '<link rel="stylesheet" href="/assets/bf-diagnosis-manual-score-local.css?v=20260810-abc33-b4-score-r1">\n'
            '<script src="/assets/bf-diagnosis-review-local.js?v=20260814-evidence-cn-r2"></script>\n'
            '<script src="/assets/bf-diagnosis-manual-score-local.js?v=20260810-abc33-b4-score-r1"></script>'
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


def create_conversation(
    conn: Any,
    title: str = "新对话",
    *,
    owner_subject: str | None = None,
    owner_role: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    ts = iso_now()
    conv = {
        "id": conversation_id or f"qa_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
        "title": title,
        "created_at": ts,
        "updated_at": ts,
        "last_user_at": None,
        "status": "active",
        "is_pinned": False,
        "is_unread": False,
        "archived_at": None,
        "owner_subject": owner_subject,
        "owner_role": owner_role,
    }
    conn.execute(
        """
        INSERT INTO qa_conversations(
            id, title, created_at, updated_at, last_user_at, owner_subject, owner_role
        ) VALUES(
            :id, :title, :created_at, :updated_at, :last_user_at, :owner_subject, :owner_role
        )
        """,
        conv,
    )
    conn.commit()
    return conv


def shared_guest_identity(room_key: str) -> dict[str, Any]:
    """Build the stable, non-secret owner identity for one shared LAN guest room."""
    normalized = str(room_key or "default").strip().lower() or "default"
    room_id = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return {
        "sub": f"guest:{room_id}",
        "role": "anonymous_guest",
        "access_mode": "guest_shared",
        "shared_room_id": room_id,
    }


def ensure_shared_guest_conversation(conn: Any, identity: Mapping[str, Any]) -> dict[str, Any]:
    """Return the single durable conversation shared by every client of one address."""
    room_id = str(identity.get("shared_room_id") or "")
    owner_subject = str(identity.get("sub") or "")
    conversation_id = f"qa_guest_{room_id}"
    row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
    if row is None:
        try:
            return create_conversation(
                conn,
                title="局域网共享访客会话",
                owner_subject=owner_subject,
                owner_role="anonymous_guest",
                conversation_id=conversation_id,
            )
        except Exception:
            conn.rollback()
            row = conn.execute("SELECT * FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                raise
    if str(row["owner_subject"] or "") != owner_subject:
        raise PermissionError("shared guest room identity collision")
    return conversation_from_row(row)


def guest_room_generation_lock(owner_subject: str) -> threading.Lock:
    """Serialize model generation inside one process for a shared guest room."""
    with _QA_GUEST_ROOM_LOCKS_GUARD:
        lock = _QA_GUEST_ROOM_LOCKS.get(owner_subject)
        if lock is None:
            lock = threading.Lock()
            _QA_GUEST_ROOM_LOCKS[owner_subject] = lock
        return lock


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
    if "owner_role" in row.keys() and row["owner_role"] == "anonymous_guest":
        item["access_mode"] = "guest_shared"
        item["shared"] = True
    origin_source_type = row["origin_source_type"] if "origin_source_type" in row.keys() else None
    item["source_type"] = origin_source_type or "direct_qa"
    item["source_title"] = (
        row["origin_source_title"] if "origin_source_title" in row.keys() and row["origin_source_title"]
        else "历史会话" if not origin_source_type else row["title"]
    )
    if origin_source_type:
        item["source_ref_id"] = row["origin_source_ref_id"]
        item["rule_id"] = row["origin_source_ref_id"] if origin_source_type == "abc_rule" else None
        item["evaluation_id"] = row["origin_evaluation_id"]
        item["return_route"] = row["origin_return_route"]
        item["origin"] = {
            "source_type": origin_source_type,
            "source_page": row["origin_source_page"],
            "source_id": row["origin_source_id"],
            "source_ref_id": row["origin_source_ref_id"],
            "source_title": row["origin_source_title"],
            "evaluation_id": row["origin_evaluation_id"],
            "context_snapshot_id": row["origin_context_snapshot_id"],
            "reuse_policy": row["origin_reuse_policy"],
            "return_route": row["origin_return_route"],
        }
    return item


def list_conversations(
    conn: Any,
    limit: int = 40,
    project_id: int | None = None,
    owner_subject: str | None = None,
    origin_source_type: str | None = None,
    origin_source_id: str | None = None,
    origin_evaluation_id: int | None = None,
    status_filter: str = "active",
    date_from: str | None = None,
    date_to: str | None = None,
    query_text: str | None = None,
) -> list[dict[str, Any]]:
    where_parts: list[str] = []
    args: list[Any] = []
    if owner_subject is not None:
        where_parts.append("c.owner_subject = ?")
        args.append(owner_subject)
    if status_filter != "all":
        where_parts.append("COALESCE(c.status, 'active') = ?")
        args.append(status_filter)
    if project_id is not None:
        where_parts.append("c.project_id = ?")
        args.append(project_id)
    if origin_source_type == "direct_qa":
        where_parts.append("(o.source_type IS NULL OR o.source_type = 'direct_qa')")
    elif origin_source_type:
        where_parts.append("o.source_type = ?")
        args.append(origin_source_type)
    if origin_source_id:
        where_parts.append("o.source_id = ?")
        args.append(origin_source_id)
    if origin_evaluation_id is not None:
        where_parts.append("o.evaluation_id = ?")
        args.append(origin_evaluation_id)
    if date_from:
        where_parts.append("c.updated_at >= ?")
        args.append(date_from)
    if date_to:
        where_parts.append("c.updated_at <= ?")
        args.append(date_to)
    if query_text:
        pattern = f"%{query_text}%"
        where_parts.append(
            "(c.title ILIKE ? OR COALESCE(o.source_title, '') ILIKE ? "
            "OR EXISTS (SELECT 1 FROM qa_messages qm WHERE qm.conversation_id=c.id AND qm.content ILIKE ?))"
        )
        args.extend((pattern, pattern, pattern))
    args.append(limit)
    where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    rows = conn.execute(
        f"""
        SELECT c.*,
               o.source_type AS origin_source_type,
               o.source_id AS origin_source_id,
               o.evaluation_id AS origin_evaluation_id,
               o.context_snapshot_id AS origin_context_snapshot_id,
               o.reuse_policy AS origin_reuse_policy,
               o.source_page AS origin_source_page,
               o.source_ref_id AS origin_source_ref_id,
               o.source_title AS origin_source_title,
               o.return_route AS origin_return_route,
               (SELECT COUNT(*) FROM qa_messages m WHERE m.conversation_id = c.id) AS message_count
        FROM qa_conversations c
        LEFT JOIN qa_conversation_origins o ON o.conversation_id = c.id
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


def load_conversation_with_origin(conn: Any, conversation_id: str) -> dict[str, Any] | None:
    """Load one conversation and its optional immutable origin metadata."""
    row = conn.execute(
        """
        SELECT c.*,
               o.source_type AS origin_source_type,
               o.source_id AS origin_source_id,
               o.evaluation_id AS origin_evaluation_id,
               o.context_snapshot_id AS origin_context_snapshot_id,
               o.reuse_policy AS origin_reuse_policy,
               o.source_page AS origin_source_page,
               o.source_ref_id AS origin_source_ref_id,
               o.source_title AS origin_source_title,
               o.return_route AS origin_return_route
        FROM qa_conversations c
        LEFT JOIN qa_conversation_origins o ON o.conversation_id = c.id
        WHERE c.id = ?
        """,
        (conversation_id,),
    ).fetchone()
    return conversation_from_row(row) if row else None


def persist_non_abc_conversation_origin(
    conn: Any,
    *,
    conversation_id: str,
    source_type: str,
    source_ref_id: str,
    source_title: str,
    payload: Mapping[str, Any],
    source_page: str,
    return_route: str = "",
) -> int:
    """Persist an immutable short-window/report origin through the shared snapshot tables."""
    if source_type not in {"short_window", "period_report", "diagnosis"}:
        raise ValueError("unsupported conversation origin")
    ts = iso_now()
    payload_json = abc_rule_assistant_analysis.canonical_json(payload)
    context_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    context_key = f"{source_type}:{source_ref_id}:{context_hash[:12]}"
    conn.execute(
        """INSERT INTO qa_context_snapshots(
               context_hash, source_type, source_id, source_version,
               context_json, context_summary_json, context_type, context_key,
               schema_version, furnace_id, source_ref_id, source_ts,
               payload_json, payload_size_bytes, created_at
           ) VALUES (?, ?, ?, 'v1', ?, ?, ?, ?, 'qa_origin_context.v1',
                     'GL02', ?, ?, ?, ?, ?)
           ON CONFLICT(context_hash) DO NOTHING""",
        (
            context_hash, source_type, source_ref_id, payload_json,
            json.dumps({"title": source_title}, ensure_ascii=False), source_type,
            context_key, source_ref_id, payload.get("source_time") or payload.get("created_at"),
            payload_json, len(payload_json.encode("utf-8")), ts,
        ),
    )
    snapshot = conn.execute("SELECT id FROM qa_context_snapshots WHERE context_hash=?", (context_hash,)).fetchone()
    if not snapshot:
        raise RuntimeError("origin context snapshot persistence failed")
    snapshot_id = int(snapshot["id"])
    conn.execute(
        """INSERT INTO qa_conversation_origins(
               conversation_id, source_type, source_id, context_snapshot_id,
               reuse_policy, source_page, source_ref_id, source_title,
               initial_context_snapshot_id, return_route, created_at, updated_at
           ) VALUES (?, ?, ?, ?, 'force_new', ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(conversation_id) DO NOTHING""",
        (
            conversation_id, source_type, source_ref_id, snapshot_id, source_page,
            source_ref_id, source_title, snapshot_id, return_route, ts, ts,
        ),
    )
    return snapshot_id


def cache_abc_rule_analysis(
    conn: Any,
    context_snapshot_id: int | None,
    analysis_text: str,
    *,
    model_name: str,
    analysis_payload: Mapping[str, Any] | None = None,
    claim_token: str | None = None,
) -> None:
    """Cache a completed initial explanation after model generation has ended."""
    if context_snapshot_id is None:
        return
    source = conn.execute(
        """
        SELECT rule_id, evaluation_id, context_hash,
               operator_explanation_json, assistant_context_json
        FROM abc_rule_ai_explanations
        WHERE context_snapshot_id = ?
        ORDER BY id ASC LIMIT 1
        """,
        (context_snapshot_id,),
    ).fetchone()
    if not source:
        return
    ts = iso_now()
    conn.execute(
        """
        INSERT INTO abc_rule_ai_explanations(
            context_snapshot_id, rule_id, evaluation_id, context_hash,
            operator_explanation_json, assistant_context_json, analysis_json,
            analysis_text, prompt_version, model_name, state, generation_state,
            attempt_count, generation_completed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  'completed', 'completed', 1, ?, ?, ?)
        ON CONFLICT(context_snapshot_id, prompt_version, model_name) DO UPDATE SET
            analysis_json = EXCLUDED.analysis_json,
            analysis_text = EXCLUDED.analysis_text,
            state = 'completed', generation_state = 'completed',
            attempt_count = GREATEST(abc_rule_ai_explanations.attempt_count, 1),
            last_error_code = NULL,
            generation_completed_at = EXCLUDED.generation_completed_at,
            claim_token = NULL, lease_expires_at = NULL,
            updated_at = EXCLUDED.updated_at
        WHERE abc_rule_ai_explanations.claim_token = ?
        """,
        (
            context_snapshot_id, source["rule_id"], source["evaluation_id"], source["context_hash"],
            source["operator_explanation_json"], source["assistant_context_json"],
            json.dumps(analysis_payload or {"answer": analysis_text}, ensure_ascii=False), analysis_text,
            ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name, ts, ts, ts, claim_token,
        ),
    )
    conn.commit()


def validated_abc_initial_answer(raw_answer: str, assistant_context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate strict model JSON and return its operator-facing rendering."""
    payload = abc_rule_assistant_analysis.validate_initial_analysis(raw_answer, assistant_context)
    return abc_rule_assistant_analysis.render_initial_analysis(payload), payload


def validated_abc_initial_answer_with_repair(
    raw_answer: str,
    messages: list[dict[str, str]],
    assistant_context: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Validate once, then permit exactly one schema-constrained repair generation."""
    try:
        return validated_abc_initial_answer(raw_answer, assistant_context)
    except abc_rule_assistant_analysis.InitialAnalysisValidationError as exc:
        repair_messages = abc_rule_assistant_analysis.initial_analysis_repair_messages(
            messages,
            raw_answer,
            exc,
        )
        repaired = call_ollama_chat_strict_json(repair_messages, assistant_context)
        return validated_abc_initial_answer(repaired, assistant_context)


def set_abc_rule_analysis_state(
    context_snapshot_id: int | None,
    state: str,
    *,
    error_code: str | None = None,
    claim_token: str | None = None,
) -> None:
    """Persist one short state transition without retaining the DB connection."""
    if context_snapshot_id is None:
        return
    model_name = _abc_rule_analysis_model_name()
    ts = iso_now()
    started_at = ts if state == "generating" else None
    completed_at = ts if state in {"completed", "failed_retryable", "stopped"} else None
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE abc_rule_ai_explanations
            SET state=?, generation_state=?, last_error_code=?,
                generation_started_at=COALESCE(?, generation_started_at),
                generation_completed_at=?, updated_at=?,
                claim_token=CASE WHEN ?='generating' THEN claim_token ELSE NULL END,
                lease_expires_at=CASE WHEN ?='generating' THEN lease_expires_at ELSE NULL END
            WHERE context_snapshot_id=? AND prompt_version=? AND model_name=?
              AND (?='' OR claim_token=?)
            """,
            (
                state, state, error_code, started_at, completed_at, ts, state, state,
                context_snapshot_id, ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name,
                str(claim_token or ""), str(claim_token or ""),
            ),
        )
        conn.commit()


def _abc_rule_analysis_model_name() -> str:
    return normalize_model(None)


def _abc_rule_cached_analysis(
    conn: Any,
    context_snapshot_id: int,
    model_name: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT analysis_text, analysis_json, context_hash, generation_state,
               context_snapshot_id, prompt_version, model_name
        FROM abc_rule_ai_explanations
        WHERE context_snapshot_id = ? AND prompt_version = ? AND model_name = ?
        LIMIT 1
        """,
        (context_snapshot_id, ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name),
    ).fetchone()
    if not row or str(row["generation_state"] or "") != "completed":
        return None
    answer = str(row["analysis_text"] or "").strip()
    if not answer:
        return None
    return {
        "answer": answer,
        "context_hash": row["context_hash"],
        "context_snapshot_id": int(row["context_snapshot_id"]),
        "prompt_version": row["prompt_version"],
        "model_name": row["model_name"],
        "cache_hit": True,
    }


def _abc_rule_retry_after(conn: Any, context_snapshot_id: int, model_name: str) -> float:
    row = conn.execute(
        """SELECT generation_state, updated_at FROM abc_rule_ai_explanations
           WHERE context_snapshot_id=? AND prompt_version=? AND model_name=? LIMIT 1""",
        (context_snapshot_id, ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name),
    ).fetchone()
    if not row or str(row["generation_state"] or "") not in {"failed_retryable", "stopped"}:
        return 0.0
    updated = parse_iso(str(row["updated_at"] or ""))
    if updated is None:
        return 0.0
    elapsed = (now_utc() - updated.astimezone(timezone.utc)).total_seconds()
    return max(0.0, ABC_RULE_ASSISTANT_RETRY_SECONDS - elapsed)


def claim_abc_rule_initial_analysis(conversation_id: str, owner_subject: str) -> dict[str, Any]:
    """Return owner/waiter/cached without holding a database lease while waiting."""
    if not conversation_id:
        return {"state": "unbound"}
    model_name = _abc_rule_analysis_model_name()
    with db_connect() as conn:
        origin = conn.execute(
            """SELECT o.context_snapshot_id FROM qa_conversation_origins o
               JOIN qa_conversations c ON c.id=o.conversation_id
               WHERE o.conversation_id=? AND c.owner_subject=? AND o.source_type='abc_rule'""",
            (conversation_id, owner_subject),
        ).fetchone()
    if not origin:
        return {"state": "unbound"}
    context_snapshot_id = int(origin["context_snapshot_id"])
    key = (context_snapshot_id, ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name)
    claim_token = uuid.uuid4().hex
    claimed = False
    with _ABC_RULE_ANALYSIS_GUARD:
        with db_connect() as conn:
            cached = _abc_rule_cached_analysis(conn, context_snapshot_id, model_name)
            retry_after = _abc_rule_retry_after(conn, context_snapshot_id, model_name)
        if cached:
            return {"state": "cached", **cached}
        if retry_after > 0:
            return {"state": "retry_wait", "retry_after_seconds": round(retry_after, 1)}
        ts = iso_now()
        lease_expires = (now_utc() + timedelta(seconds=ABC_RULE_ASSISTANT_WAIT_SECONDS)).isoformat()
        retry_cutoff = (now_utc() - timedelta(seconds=ABC_RULE_ASSISTANT_RETRY_SECONDS)).isoformat()
        with db_connect() as conn:
            inserted = conn.execute(
                """
                INSERT INTO abc_rule_ai_explanations(
                    context_snapshot_id, rule_id, evaluation_id, context_hash,
                    operator_explanation_json, assistant_context_json,
                    prompt_version, model_name, state, generation_state,
                    attempt_count, claim_token, lease_expires_at,
                    generation_started_at, created_at, updated_at
                )
                SELECT context_snapshot_id, rule_id, evaluation_id, context_hash,
                       operator_explanation_json, assistant_context_json,
                       ?, ?, 'generating', 'generating', 1, ?, ?, ?, ?, ?
                FROM abc_rule_ai_explanations
                WHERE context_snapshot_id=?
                ORDER BY id ASC LIMIT 1
                ON CONFLICT(context_snapshot_id, prompt_version, model_name) DO NOTHING
                RETURNING id
                """,
                (
                    ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name, claim_token,
                    lease_expires, ts, ts, ts, context_snapshot_id,
                ),
            ).fetchone()
            if inserted:
                claimed = True
            else:
                reclaimed = conn.execute(
                    """
                    UPDATE abc_rule_ai_explanations
                    SET state='generating', generation_state='generating',
                        attempt_count=attempt_count+1, claim_token=?, lease_expires_at=?,
                        generation_started_at=?, generation_completed_at=NULL,
                        last_error_code=NULL, updated_at=?
                    WHERE context_snapshot_id=? AND prompt_version=? AND model_name=?
                      AND generation_state <> 'completed'
                      AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                      AND (generation_state NOT IN ('failed_retryable','stopped') OR updated_at <= ?)
                    RETURNING id
                    """,
                    (
                        claim_token, lease_expires, ts, ts, context_snapshot_id,
                        ABC_RULE_ASSISTANT_PROMPT_VERSION, model_name, ts, retry_cutoff,
                    ),
                ).fetchone()
                claimed = bool(reclaimed)
            conn.commit()
        event = _ABC_RULE_ANALYSIS_INFLIGHT.get(key)
        if not claimed:
            if event is None:
                event = threading.Event()
            return {"state": "waiter", "key": key, "event": event}
        event = threading.Event()
        _ABC_RULE_ANALYSIS_INFLIGHT[key] = event
        return {
            "state": "owner",
            "key": key,
            "event": event,
            "context_snapshot_id": context_snapshot_id,
            "claim_token": claim_token,
        }


def wait_for_abc_rule_initial_analysis(ticket: Mapping[str, Any]) -> dict[str, Any] | None:
    event = ticket.get("event")
    key = ticket.get("key")
    if not isinstance(event, threading.Event) or not isinstance(key, tuple):
        return None
    deadline = time.monotonic() + ABC_RULE_ASSISTANT_WAIT_SECONDS
    context_snapshot_id, _, model_name = key
    while time.monotonic() < deadline:
        if isinstance(event, threading.Event):
            event.wait(min(0.5, max(0.0, deadline - time.monotonic())))
        with db_connect() as conn:
            cached = _abc_rule_cached_analysis(conn, int(context_snapshot_id), str(model_name))
        if cached:
            return cached
    return None


def finish_abc_rule_initial_analysis(ticket: Mapping[str, Any] | None) -> None:
    if not ticket or ticket.get("state") != "owner":
        return
    key = ticket.get("key")
    event = ticket.get("event")
    with _ABC_RULE_ANALYSIS_GUARD:
        if isinstance(key, tuple):
            _ABC_RULE_ANALYSIS_INFLIGHT.pop(key, None)
        if isinstance(event, threading.Event):
            event.set()


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


def select_bootstrap_conversation(
    conn: Any,
    *,
    owner_subject: str,
    owner_role: str,
    force_new: bool = False,
) -> tuple[dict[str, Any], bool]:
    row = conn.execute(
        "SELECT * FROM qa_conversations WHERE owner_subject=? ORDER BY updated_at DESC LIMIT 1",
        (owner_subject,),
    ).fetchone()
    if force_new or row is None:
        return create_conversation(conn, owner_subject=owner_subject, owner_role=owner_role), True

    conv = conversation_from_row(row)
    last_user_at = parse_iso(conv.get("last_user_at"))
    if last_user_at is not None and now_utc() - last_user_at > timedelta(hours=QA_INACTIVITY_HOURS):
        return create_conversation(conn, owner_subject=owner_subject, owner_role=owner_role), True
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
    "P_top_A": "A点顶压",
    "P_top_B": "B点顶压",
    "P_top_C": "C点顶压",
    "P_top_D": "D点顶压",
    "T_taphole_1": "一号出铁口温度",
    "T_taphole_2": "二号出铁口温度",
}
PROMPT_METRIC_UNIT_FALLBACKS = {
    "P_top": "kPa",
    "DP_total": "kPa",
    "L_south": "m",
    "L_north": "m",
    "P_top_A": "kPa",
    "P_top_B": "kPa",
    "P_top_C": "kPa",
    "P_top_D": "kPa",
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
    value = table.get(text)
    if value is not None:
        return value
    normalized = str(text or "").strip()
    if "十" not in normalized:
        return None
    left, right = normalized.split("十", 1)
    if left and left not in table:
        return None
    if right and right not in table:
        return None
    tens = table.get(left, 1)
    ones = table.get(right, 0)
    return tens * 10 + ones


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
    ("P_top_A", ("顶压a", "a点顶压", "顶压a点", "a点上升管煤气压力", "a上升管煤气压力", "上升管煤气压力a", "a管煤气压力", "p_top_gas_a")),
    ("P_top_B", ("顶压b", "b点顶压", "顶压b点", "b点上升管煤气压力", "b上升管煤气压力", "上升管煤气压力b", "b管煤气压力", "p_top_gas_b")),
    ("P_top_C", ("顶压c", "c点顶压", "顶压c点", "c点上升管煤气压力", "c上升管煤气压力", "上升管煤气压力c", "c管煤气压力", "p_top_gas_c")),
    ("P_top_D", ("顶压d", "d点顶压", "顶压d点", "d点上升管煤气压力", "d上升管煤气压力", "上升管煤气压力d", "d管煤气压力", "p_top_gas_d")),
    ("T_top_A", ("顶温a", "顶温a点", "a点上升管煤气温度", "a上升管煤气温度", "上升管煤气温度a", "炉顶a点温度", "a点顶温")),
    ("T_top_B", ("顶温b", "顶温b点", "b点上升管煤气温度", "b上升管煤气温度", "上升管煤气温度b", "炉顶b点温度", "b点顶温")),
    ("T_top_C", ("顶温c", "顶温c点", "c点上升管煤气温度", "c上升管煤气温度", "上升管煤气温度c", "炉顶c点温度", "c点顶温")),
    ("T_top_D", ("顶温d", "顶温d点", "d点上升管煤气温度", "d上升管煤气温度", "上升管煤气温度d", "炉顶d点温度", "d点顶温")),
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

    def normalize_chinese_layer(match: re.Match[str]) -> str:
        value = chinese_int(match.group(1))
        if value is None or not 7 <= value <= 16:
            return match.group(0)
        return f"第{value}层"

    text = re.sub(
        r"第?\s*([一二两三四五六七八九十]{1,3})\s*层",
        normalize_chinese_layer,
        text,
    )
    symbolic = re.findall(r"(?i)(?<![a-z0-9_])t_body_l(7|8|9|10|11|12|13|14|15|16)_([a-h])(?![a-z0-9_])", text)
    if symbolic:
        return list(dict.fromkeys(f"T_body_L{int(layer)}_{position.upper()}" for layer, position in symbolic))
    body_terms = ("炉体温度", "炉身温度", "炉温", "炉墙温度", "炉壳温度", "炉身炉腹炉缸")
    point_temperature = re.search(
        r"(?<!\d)(?:[7-9]|1[0-6])\s*层\s*[A-H]\s*(?:点)?\s*(?:温度|炉温|和|、|，|,|$)",
        text,
        flags=re.IGNORECASE,
    )
    layer_temperature_scope = re.search(
        r"第?\s*(?:[7-9]|1[0-6])\s*层?.{0,20}[A-H].{0,20}(?:温度|炉温)",
        text,
        flags=re.IGNORECASE,
    )
    layer_statistics_scope = (
        re.search(
            r"第?\s*(?:[7-9]|1[0-6])\s*层\s*(?:到|至|-|—|－)\s*第?\s*(?:[7-9]|1[0-6])\s*层",
            text,
        )
        and "温度" in text
        and any(term in text for term in ("平均", "标准差", "波动", "极差", "变化", "斜率", "变异系数"))
    )
    if (
        not any(term in text for term in body_terms)
        and not point_temperature
        and not layer_temperature_scope
        and not layer_statistics_scope
    ):
        return []

    layers: list[int] = []
    for match in re.finditer(
        r"(?<!\d)第?\s*([7-9]|1[0-6])\s*层?\s*(?:到|至|-|—|－)\s*第?\s*([7-9]|1[0-6])\s*层",
        text,
    ):
        first, last = int(match.group(1)), int(match.group(2))
        step = 1 if first <= last else -1
        layers.extend(range(first, last + step, step))
    layers.extend(int(value) for value in re.findall(r"(?<!\d)第?\s*([7-9]|1[0-6])\s*层", text))
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


def qa_mcp_explicit_time_range(
    question: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """Parse a bounded Chinese clock range used by deterministic MCP routes."""
    text = str(question or "").split("\n[服务端对话状态：", 1)[0]
    anchor = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    date_value = anchor.date()
    if any(term in text for term in ("昨天", "昨日")):
        date_value -= timedelta(days=1)
    elif "前天" in text:
        date_value -= timedelta(days=2)
    else:
        date_match = re.search(
            r"(?:(\d{4})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?",
            text,
        )
        if date_match:
            year = int(date_match.group(1) or anchor.year)
            try:
                date_value = date(year, int(date_match.group(2)), int(date_match.group(3)))
            except ValueError:
                return None

    clock_match = re.search(
        r"(?:(上午|下午|中午|晚上|夜里|凌晨)\s*)?"
        r"(\d{1,2})\s*(?:点|时|:)\s*(\d{1,2})?\s*分?\s*"
        r"(?:到|至|-|—|－|~|～)\s*"
        r"(?:(上午|下午|中午|晚上|夜里|凌晨)\s*)?"
        r"(\d{1,2})\s*(?:点|时|:)\s*(\d{1,2})?\s*分?",
        text,
    )
    if not clock_match:
        return None

    def clock_hour(raw_hour: str, period: str) -> int:
        hour = int(raw_hour)
        if hour > 23:
            raise ValueError("hour out of range")
        if period in {"下午", "中午", "晚上", "夜里"} and hour < 12:
            hour += 12
        if period == "凌晨" and hour == 12:
            hour = 0
        return hour

    first_period = str(clock_match.group(1) or "")
    second_period = str(clock_match.group(4) or first_period)
    try:
        start = datetime.combine(
            date_value,
            datetime.min.time(),
            tzinfo=LOCAL_TZ,
        ).replace(
            hour=clock_hour(clock_match.group(2), first_period),
            minute=int(clock_match.group(3) or 0),
        )
        end = datetime.combine(
            date_value,
            datetime.min.time(),
            tzinfo=LOCAL_TZ,
        ).replace(
            hour=clock_hour(clock_match.group(5), second_period),
            minute=int(clock_match.group(6) or 0),
        )
    except ValueError:
        return None
    if end <= start:
        end += timedelta(days=1)
    return start, end


def qa_mcp_body_temperature_statistics_plan(question: str) -> dict[str, Any] | None:
    """Build one composite call for per-layer or exact-point temperature statistics."""
    text = str(question or "")
    body_variables = qa_mcp_body_temperature_variables(text)
    if not body_variables:
        return None
    all_variables = qa_mcp_variables(text)
    if any(variable not in body_variables for variable in all_variables):
        return None
    statistic_terms = (
        "平均", "均值", "标准差", "波动", "幅值", "极差", "最高", "最低",
        "首末", "变化量", "斜率", "变异系数", "逐层", "每一层", "每层", "统计",
    )
    if not any(term in text for term in statistic_terms):
        return None
    parsed = [
        re.fullmatch(r"T_body_L(7|8|9|1[0-6])_([A-H])", variable)
        for variable in body_variables
    ]
    matches = [match for match in parsed if match]
    if not matches:
        return None
    layers = list(dict.fromkeys(int(match.group(1)) for match in matches))
    positions = list(dict.fromkeys(match.group(2) for match in matches))
    explicit_range = qa_mcp_explicit_time_range(text)
    if explicit_range:
        start_dt, end_dt = explicit_range
    else:
        duration_text = re.sub(r"(?<!\d)\d{1,3}\s*分钟\s*滚动", "", text)
        duration_text = re.sub(r"滚动\s*(?<!\d)\d{1,3}\s*分钟", "", duration_text)
        duration_minutes = qa_mcp_duration_minutes(duration_text) or 60
        end_dt = datetime.now(LOCAL_TZ).replace(second=0, microsecond=0)
        start_dt = end_dt - timedelta(minutes=duration_minutes)
    rolling_match = re.search(r"(?<!\d)(\d{1,3})\s*分钟\s*滚动", text)
    rolling_minutes = int(rolling_match.group(1)) if rolling_match else 15
    point_detail_intent = any(
        term in text
        for term in ("各方位", "每个方位", "各点", "每个点", "逐点", "分别列出")
    )
    include_point_statistics = len(layers) == 1 and (len(positions) == 1 or point_detail_intent)
    return {
        "tool": "gl02ext__query_body_temperature_statistics",
        "arguments": {
            "start_layer": min(layers),
            "end_layer": max(layers),
            "start_time": start_dt.isoformat(timespec="seconds"),
            "end_time": end_dt.isoformat(timespec="seconds"),
            "positions": positions,
            "rolling_window_minutes": max(2, min(rolling_minutes, 120)),
            "require_all_positions": True,
            "include_point_statistics": include_point_statistics,
        },
    }


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
            *list(item.get("legacy_variable_names") or []),
            *list(item.get("aliases") or []),
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
    shared_top_temperature_pressure = any(term in normalized for term in (
        "上升管煤气温度和压力", "上升管煤气温度与压力", "上升管煤气温度及压力",
    ))
    top_pressure_group = "顶压" in normalized or "上升管煤气压力" in normalized or shared_top_temperature_pressure
    top_temperature_group = "顶温" in normalized or "上升管煤气温度" in normalized
    expand_top_groups = has_abcd or "四个" in normalized or "各上升管" in normalized
    ordered_top_groups: list[tuple[int, tuple[str, ...]]] = []
    if top_pressure_group and expand_top_groups:
        pressure_positions = [position for term in ("顶压", "上升管煤气压力") if (position := normalized.find(term)) >= 0]
        if not pressure_positions and shared_top_temperature_pressure:
            pressure_positions = [normalized.find("压力")]
        ordered_top_groups.append((min(pressure_positions), ("P_top_A", "P_top_B", "P_top_C", "P_top_D")))
    if top_temperature_group and expand_top_groups:
        temperature_positions = [position for term in ("顶温", "上升管煤气温度") if (position := normalized.find(term)) >= 0]
        ordered_top_groups.append((min(temperature_positions), ("T_top_A", "T_top_B", "T_top_C", "T_top_D")))
    for _, group in sorted(ordered_top_groups, key=lambda item: item[0]):
        add_group(group)
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
        matched_alias = False
        for term in terms:
            normalized_term = normalize_spoken_question(term)
            if re.fullmatch(r"[a-z0-9_]+", normalized_term):
                matched_alias = bool(re.search(
                    rf"(?<![a-z0-9_]){re.escape(normalized_term)}(?![a-z0-9_])",
                    q,
                ))
            else:
                matched_alias = normalized_term in q
            if matched_alias:
                break
        if matched_alias and variable not in variables:
            variables.append(variable)
    aggregate_suppressions = {
        "T_top": (("T_top_A", "T_top_B", "T_top_C", "T_top_D"), ("综合顶温", "平均顶温", "炉顶平均温度", "综合炉顶温度")),
        "P_top": (("P_top_A", "P_top_B", "P_top_C", "P_top_D"), ("综合顶压", "顶压平均", "炉顶平均压力")),
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
    physical_static_pressure = {
        "P_static_20m35": "P_static_lower_mean",
        "P_static_23m49": "P_static_middle_mean",
        "P_static_28m98": "P_static_upper_mean",
    }
    for physical_id, legacy_mean_id in physical_static_pressure.items():
        if physical_id in variables and legacy_mean_id in variables:
            variables.remove(legacy_mean_id)
    previous_hour_pci_terms = ("上小时喷煤量", "上一小时喷煤量", "前一小时喷煤量")
    current_hour_pci_terms = ("本小时喷煤量", "当前小时喷煤量", "这小时喷煤量")
    if any(normalize_spoken_question(term) in q for term in previous_hour_pci_terms):
        variables = [item for item in variables if item not in {"PCI_current_hour", "PCI_rate"}]
    elif any(normalize_spoken_question(term) in q for term in current_hour_pci_terms):
        variables = [item for item in variables if item not in {"PCI_previous_hour", "PCI_rate"}]
    if "阀前" in q and "阀后" not in q:
        variables = [item for item in variables if item != "P_O2_valve_out"]
    elif "阀后" in q and "阀前" not in q:
        variables = [item for item in variables if item != "P_O2_valve_in"]
    return variables


def qa_mcp_variable(question: str) -> str | None:
    variables = qa_mcp_variables(question)
    return variables[0] if variables else None


def qa_mcp_server_registry() -> McpServerRegistry:
    """Load the multi-server contract while preserving the legacy GL02 override."""

    registry = load_server_registry(MCP_SERVER_REGISTRY_PATH)
    servers = tuple(
        replace(server, script_path=MCP_DATA_SERVER_PATH.resolve())
        if server.server_id == "gl02-data"
        else server
        for server in registry.servers
    )
    return McpServerRegistry(version=registry.version, servers=servers)


def qa_mcp_imes_plan(question: str) -> dict[str, Any] | None:
    """Build zero-planner-round calls for frequent official MES heat questions."""

    text = (
        str(question or "")
        .split("\n[服务端对话状态：", 1)[0]
        .replace("鸬鹚", "炉次")
    )
    lowered = text.lower()
    heat_terms = ("炉次", "炉号", "铁次", "meltno")
    current_terms = ("当前", "现在", "目前", "本炉", "这一炉", "这炉")
    previous_terms = ("上一炉", "上一个炉次", "前一炉", "上一炉次", "前炉")
    silicon_terms = ("硅", "si", "silicon")
    has_heat = any(term in lowered for term in heat_terms)
    has_current = any(term in lowered for term in current_terms)
    has_previous = any(term in lowered for term in previous_terms if term != "前炉") or (
        "前炉" in lowered
        and not any(term in lowered for term in ("当前炉", "目前炉"))
    )
    has_silicon = any(term in lowered for term in silicon_terms)
    has_time_range = bool(
        re.search(r"最近\s*\d{1,3}\s*(分钟|小时)", lowered)
        or re.search(r"\d{4}[-年/]\d{1,2}[-月/]\d{1,2}", lowered)
        or re.search(r"\d{1,2}月\d{1,2}[日号]{0,1}", lowered)
        or re.search(r"\d{1,2}(点|时|:\d{2})", lowered)
        or any(
            term in lowered
            for term in ("今天", "今日", "昨天", "昨日", "前天", "凌晨", "上午", "中午", "下午", "傍晚", "晚上", "夜里")
        )
    )
    if has_previous and has_silicon:
        return {"tool": "imes__get_current_previous_heat_si_summary", "arguments": {}}
    if has_current and has_silicon:
        return {"tool": "imes__query_current_heat_chemistry", "arguments": {"components": ["si"]}}
    if has_silicon and has_time_range:
        return {
            "tool": "imes__query_heat_chemistry_by_time_range",
            "arguments": {"time_reference": text, "components": ["si"]},
        }
    if has_heat and has_current:
        return {"tool": "imes__get_current_heat_context", "arguments": {}}
    return None


def qa_mcp_imes_query_intent(question: str) -> bool:
    """Recognize MES fact requests before the legacy GL02-only context gate."""

    text = str(question or "").lower().replace("鸬鹚", "炉次")
    domains = ("炉次", "炉号", "铁次", "铁水", "炉渣", "渣样", "化验", "进料", "烧结矿", "meltno", "imes", "mes")
    fact_cues = ("当前", "现在", "上一炉", "前一炉", "某一炉", "某个炉", "多少", "是多少", "含量", "成分", "平均", "分布", "取样", "试样", "查", "看", "列出")
    explicit_heat_reference = bool(
        re.search(r"\d{1,3}#\d{8}-\d{3,4}", text)
        or re.search(r"\d{8}-\d{3,4}", text)
        or re.search(r"(?<!\d)\d{2,4}\s*(?:这炉|那炉|炉|炉次)", text)
    )
    chemistry_cues = ("碳", "硅", "锰", "磷", "硫", "钛", "钒", "铬", "铜", "镍", "砷", "c", "si", "mn")
    return (
        any(term in text for term in domains)
        and any(term in text for term in fact_cues)
    ) or (explicit_heat_reference and any(term in text for term in chemistry_cues))


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
    matrix_terms = (
        "热力矩阵",
        "温度矩阵",
        "矩阵图",
        "矩阵热度图",
        "矩阵热力图",
        "热度图",
        "热力图",
        "大矩阵",
        "每个小格",
        "每格",
    )
    if any(term in text for term in body_terms) and any(term in text for term in matrix_terms):
        layer_match = re.search(
            r"第?\s*(\d{1,2})\s*层?\s*(?:到|至|-|—|－)\s*第?\s*(\d{1,2})\s*层",
            text,
        )
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
    body_statistics_plan = qa_mcp_body_temperature_statistics_plan(text)
    if body_statistics_plan:
        return body_statistics_plan
    user_text = text.split("\n[服务端对话状态：", 1)[0]
    variables = qa_mcp_variables(text)
    if not variables:
        return None
    # The suffix may carry the previous turn's intent.  A temporal phrase in
    # the current user request must override that stale context, especially for
    # cross-source questions such as “上一炉 Si 平均值 + 当前顶压”.
    intent = ""
    if any(term in user_text for term in ("现在", "当前", "目前", "最新")):
        intent = "latest"
    elif any(term in user_text for term in ("平均", "最高", "最低", "统计", "波动", "稳不稳")):
        intent = "statistics"
    elif any(term in user_text for term in ("历史", "趋势", "走势", "变化", "最近", "过去")):
        intent = "history"
    if not intent:
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


# ---------------------------------------------------------------------------
# Cross-source plan builder (REQ-8093-CROSS-SOURCE-MCP-20260805)
# ---------------------------------------------------------------------------


def _detect_heat_reference(question: str) -> str | None:
    """Detect if the question contains a heat-number reference.

    Returns the raw heat reference string, or None.
    """
    text = str(question or "").split("\n[服务端对话状态：", 1)[0]
    # Full formal: 2#20260805-072
    m = re.search(r"(?<!\d)(\d{1,3}#\d{8}-\d{3,4})(?!\d)", text)
    if m:
        return m.group(1)
    # Date-prefix: 20260805-072 (standalone)
    m = re.search(r"(?<!\d)(\d{8}-\d{3,4})(?!\d)", text)
    if m:
        return m.group(1)
    # Spoken short form: "072这炉", "072的", etc — look for 2-4 digit pattern
    # near heat-related terms
    m = re.search(r"(?<!\d)(\d{2,4})\s*(?:这炉|那炉|炉|号炉|炉次)", text)
    if m:
        return m.group(1)
    # Bare short number with "炉次" or similar context
    m = re.search(r"(?:炉次|炉号|铁次|那炉|这炉)\s*(\d{2,4})(?!\d)", text)
    if m:
        return m.group(1)
    return None


def _step_server_id(
    source_domain: str,
    service_selection: "DomainSelection",
) -> str:
    """Map a source domain to the server_id selected by the domain router."""
    domain_map = {
        "imes": ("imes-readonly",),
        "gl02": ("gl02-data", "gl02-extended"),
    }
    candidates = domain_map.get(source_domain, ())
    for sid in service_selection.server_ids:
        if sid in candidates:
            return sid
    # Fallback: return first matching from candidates not in selection
    return candidates[0] if candidates else ""


def build_cross_source_plans(
    question: str,
    service_selection: "DomainSelection",
) -> CrossSourcePlan | None:
    """Build a deterministic DAG for cross-source or dependent IMES queries.

    Returns None for single-source questions (let the existing fast path
    handle them).  Returns a CrossSourcePlan with 2+ steps and distinct
    server_ids when the question genuinely spans MES + GL02.

    Rules:
    - Activates for 2+ different server_ids or a spoken-heat dependency chain.
    - GL02 internal priority: chart > correlation > sensor query.
    - P_top stays in query_gl02_sensors, never enters history tools.
    - Heat reference detected from question text; exact formats resolved
      synchronously via regex; spoken short forms become dependency steps.
    - find_gl02_variables NEVER appears in a cross-source plan.
    """
    cross_source_enabled = os.environ.get("BF_QA_MCP_CROSS_SOURCE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
    if not cross_source_enabled:
        return None

    text = str(question or "").split("\n[服务端对话状态：", 1)[0]

    # --- Detect explicit heat chemistry request ---
    heat_ref = _detect_heat_reference(question)
    has_chemistry_request = bool(heat_ref) and any(
        term in text.lower()
        for term in ("硅", "si", "锰", "mn", "磷", "p", "硫", "s", "碳", "c",
                     "化验", "成分", "含量", "铁水")
    )
    single_service_dependency = bool(
        has_chemistry_request and heat_ref and re.fullmatch(r"\d{2,4}", heat_ref)
    )
    if len(set(service_selection.server_ids)) < 2 and not single_service_dependency:
        return None  # Single independent source → existing fast path

    # --- Build candidate plans from all four planners ---
    imes_plan = qa_mcp_imes_plan(question)
    chart_plan = qa_mcp_chart_plan(question)
    standard_plan = qa_mcp_standard_analysis_plan(question)
    sensor_plan = qa_mcp_sensor_query_plan(question)

    steps: list[CrossSourceStep] = []
    requested_fact_ids: list[str] = []
    step_counter = 0

    # --- MES steps ---
    imes_server = _step_server_id("imes", service_selection)

    if has_chemistry_request and heat_ref:
        step_counter += 1
        # Check if heat_ref needs DB resolution
        if re.fullmatch(r"\d{2,4}", heat_ref):
            # Spoken short form → resolve first, then query chemistry
            resolve_step_id = f"s{step_counter}_resolve_heat"
            steps.append(CrossSourceStep(
                step_id=resolve_step_id,
                server_id=imes_server,
                source_domain="imes",
                tool="imes__resolve_spoken_heat_reference",
                arguments={"heat_reference": heat_ref},
                depends_on=(),
                # Resolution metadata is carried in the snapshot, not shown
                # as a user-requested fact.
                produces_fact_ids=(),
                required_for_answer=True,
                required_for_analysis=True,
            ))
            step_counter += 1
            chem_step_id = f"s{step_counter}_chemistry"
            steps.append(CrossSourceStep(
                step_id=chem_step_id,
                server_id=imes_server,
                source_domain="imes",
                tool="imes__query_hot_metal_chemistry_by_heat",
                arguments={"heat_no": heat_ref},
                depends_on=(resolve_step_id,),
                argument_bindings={
                    "heat_no": f"steps.{resolve_step_id}.resolved_heat_no",
                },
                produces_fact_ids=("hot_metal_chemistry",),
                required_for_answer=True,
                required_for_analysis=True,
            ))
            requested_fact_ids.extend(("hot_metal_chemistry",))
        else:
            # Exact format → query directly
            chem_step_id = f"s{step_counter}_chemistry"
            steps.append(CrossSourceStep(
                step_id=chem_step_id,
                server_id=imes_server,
                source_domain="imes",
                tool="imes__query_hot_metal_chemistry_by_heat",
                arguments={"heat_no": heat_ref},
                depends_on=(),
                produces_fact_ids=("hot_metal_chemistry",),
                required_for_answer=True,
                required_for_analysis=True,
            ))
            requested_fact_ids.append("hot_metal_chemistry")

    elif imes_plan:
        step_counter += 1
        sid = f"s{step_counter}_imes"
        steps.append(CrossSourceStep(
            step_id=sid,
            server_id=imes_server,
            source_domain="imes",
            tool=imes_plan["tool"],
            arguments=imes_plan["arguments"],
            depends_on=(),
            produces_fact_ids=(
                "current_heat_no", "previous_heat_no", "si_avg",
                "si_values", "sample_count",
            ) if imes_plan["tool"] == "imes__get_current_previous_heat_si_summary"
            else ("imes_result",),
            required_for_answer=True,
            required_for_analysis=True,
        ))
        if imes_plan["tool"] == "imes__get_current_previous_heat_si_summary":
            requested_fact_ids.extend((
                "current_heat_no", "previous_heat_no", "si_avg",
                "si_values", "sample_count",
            ))
        else:
            requested_fact_ids.append("imes_result")

    # --- GL02 steps (priority: chart > correlation > sensor) ---
    gl02_server = _step_server_id("gl02", service_selection)

    if chart_plan:
        step_counter += 1
        sid = f"s{step_counter}_gl02_chart"
        correlation_chart = (
            chart_plan["tool"] == "plot_gl02_analysis"
            and str(chart_plan["arguments"].get("analysis_type") or "").startswith("correlation")
        )
        chart_fact_ids = ["chart"]
        if correlation_chart:
            chart_fact_ids.extend(("pearson_r", "aligned_count", "correlation_left", "correlation_right", "correlation_window"))
        steps.append(CrossSourceStep(
            step_id=sid,
            server_id=gl02_server,
            source_domain="gl02",
            tool=chart_plan["tool"],
            arguments=chart_plan["arguments"],
            depends_on=(),
            produces_fact_ids=tuple(chart_fact_ids),
            required_for_answer=correlation_chart,
            required_for_analysis=correlation_chart,
        ))
        requested_fact_ids.extend(chart_fact_ids)
    elif standard_plan:
        step_counter += 1
        sid = f"s{step_counter}_gl02_analysis"
        correlation_fact_ids = (
            "pearson_r", "aligned_count", "correlation_left",
            "correlation_right", "correlation_window",
        )
        steps.append(CrossSourceStep(
            step_id=sid,
            server_id=gl02_server,
            source_domain="gl02",
            tool=standard_plan["tool"],
            arguments=standard_plan["arguments"],
            depends_on=(),
            produces_fact_ids=correlation_fact_ids,
            required_for_answer=True,
            required_for_analysis=True,
        ))
        requested_fact_ids.extend(correlation_fact_ids)
    elif sensor_plan:
        # Split body-temperature capability calls from ordinary GL02 sensor
        # calls. This keeps T_body_L13_C on the extended service while P_top
        # remains a sensor fact, even when both are requested together.
        args = dict(sensor_plan["arguments"])
        if (
            sensor_plan.get("tool") == "gl02ext__query_body_temperature_statistics"
            and "gl02-extended" in service_selection.server_ids
        ):
            step_counter += 1
            steps.append(CrossSourceStep(
                step_id=f"s{step_counter}_gl02_body_temperature_statistics",
                server_id="gl02-extended",
                source_domain="gl02",
                tool="gl02ext__query_body_temperature_statistics",
                arguments=args,
                depends_on=(),
                produces_fact_ids=("body_temperature_statistics",),
                required_for_answer=True,
                required_for_analysis=False,
            ))
            requested_fact_ids.append("body_temperature_statistics")
            args = {}
        all_variables = list(args.get("variables") or [])
        body_variables = [
            str(v) for v in all_variables
            if re.fullmatch(r"T_body_L(7|8|9|1[0-6])_([A-H])", str(v))
        ]
        sensor_variables = [str(v) for v in all_variables if str(v) not in body_variables]
        analysis_required = bool(
            any(term in text for term in ("分析", "判断", "比较", "相关", "是否一致", "怎么样", "正常吗"))
        )
        if body_variables and "gl02-extended" in service_selection.server_ids:
            for body_variable in body_variables:
                match = re.fullmatch(r"T_body_L(7|8|9|1[0-6])_([A-H])", body_variable)
                if not match:
                    continue
                step_counter += 1
                steps.append(CrossSourceStep(
                    step_id=f"s{step_counter}_gl02_body_temperature",
                    server_id="gl02-extended",
                    source_domain="gl02",
                    tool="gl02ext__query_body_temperature",
                    arguments={
                        "layer": int(match.group(1)),
                        "position": match.group(2),
                        "include_history": False,
                    },
                    depends_on=(),
                    produces_fact_ids=(body_variable,),
                    required_for_answer=True,
                    required_for_analysis=analysis_required,
                ))
                requested_fact_ids.append(body_variable)
        if args and (sensor_variables or not body_variables):
            step_counter += 1
            sid = f"s{step_counter}_gl02_sensor"
            tool_name = "query_gl02_sensors"
            variables = sensor_variables or all_variables
            if sensor_variables:
                args["variables"] = sensor_variables
            steps.append(CrossSourceStep(
                step_id=sid,
                server_id=gl02_server,
                source_domain="gl02",
                tool=tool_name,
                arguments=args,
                depends_on=(),
                produces_fact_ids=tuple(str(v) for v in variables) if isinstance(variables, list) else ("sensor_result",),
                required_for_answer=True,
                required_for_analysis=analysis_required,
            ))
            if isinstance(variables, list):
                requested_fact_ids.extend(str(v) for v in variables)
            else:
                requested_fact_ids.append("sensor_result")

    # --- Require at least 2 distinct server_ids ---
    distinct_servers = {s.server_id for s in steps}
    has_dependency_edge = any(step.depends_on for step in steps)
    if len(distinct_servers) < 2 and not (single_service_dependency and has_dependency_edge):
        return None  # Single source → fall through to fast path

    if not steps:
        return None

    return CrossSourcePlan(
        steps=tuple(steps),
        requested_fact_ids=tuple(requested_fact_ids),
        analysis_requested=any(
            term in text for term in ("分析", "判断", "是否一致", "怎么样", "正常吗")
        ),
        requested_heat_reference=heat_ref,
    )


# ---------------------------------------------------------------------------
# Cross-source answer formatter
# ---------------------------------------------------------------------------


def format_cross_source_answer(
    snapshot: CrossSourceSnapshot,
    analysis_text: str | None = None,
) -> str:
    """Build a deterministic answer from a CrossSourceSnapshot.

    Rules:
    - Fact queries: deterministic formatter only, no model call.
    - Partial data: output facts + missing facts + source_status, no model call.
    - Analysis: only when all evidence present AND user explicitly requested
      analysis.  Model output is appended AFTER the fact table.
    - Model failure/truncation → facts still returned, analysis_status=failed.
    """
    lines: list[str] = []
    lines.append("## 跨源数据查询结果\n")

    # --- Fact table ---
    if snapshot.facts:
        lines.append("| 查询项 | 数值 | 单位 | 数据时间 | 来源 | 状态 |")
        lines.append("|--------|------|------|----------|------|------|")
        fact_labels = {
            "pearson_r": "Pearson相关系数",
            "aligned_count": "对齐样本数",
            "correlation_left": "相关性左变量",
            "correlation_right": "相关性右变量",
            "correlation_window": "相关性时间窗",
        }
        for fact in snapshot.facts:
            status = "缺失" if fact.missing else "正常"
            value_str = (
                "—" if fact.missing
                else f"{fact.value}" if fact.value is not None
                else "—"
            )
            unit_str = fact.unit or ""
            time_str = fact.data_time or "—"
            source_str = fact.source_service or "—"
            lines.append(
                f"| {fact_labels.get(fact.fact_id, fact.label)} | {value_str} | {unit_str} | {time_str} | {source_str} | {status} |"
            )
        lines.append("")

    # --- Missing facts ---
    if snapshot.missing_fact_ids:
        lines.append("### 缺失数据\n")
        for fid in snapshot.missing_fact_ids:
            lines.append(f"- **{fid}**：数据源未返回有效结果")
        lines.append("")

    # --- Source status ---
    if snapshot.source_status:
        lines.append("### 数据源状态\n")
        for ss in snapshot.source_status:
            ok_mark = "✓" if ss.get("ok") else "✗"
            lines.append(
                f"- {ok_mark} **{ss.get('server_id', 'unknown')}** "
                f"→ {ss.get('tool', 'unknown')} "
                f"({ss.get('elapsed_ms', 0):.0f}ms"
                f"{', 缓存命中' if ss.get('cache_hit') else ''})"
            )
        lines.append("")

    # --- Heat reference ---
    if snapshot.heat_reference:
        hr = snapshot.heat_reference
        if isinstance(hr, dict):
            resolved = hr.get("resolved_heat_no") or "—"
            policy = hr.get("resolution_policy") or "—"
            lines.append(f"**炉次参考**：{resolved}（解析策略：{policy}）\n")
            heat_error = str(hr.get("error_code") or "")
            requested = hr.get("requested_heat_reference") or hr.get("requested_heat_no") or "该口语炉次"
            if heat_error == "HEAT_REFERENCE_NOT_FOUND":
                lines.append(
                    f"> 未找到口语炉次 `{requested}` 对应的权威正式炉号；禁止猜测或替换炉号，"
                    "因此未执行下游铁水 Si 查询。\n"
                )
            elif heat_error == "HEAT_REFERENCE_AMBIGUOUS":
                lines.append(
                    f"> 口语炉次 `{requested}` 匹配到多个候选；请补充日期或完整炉号。"
                    "在消除歧义前不会执行下游铁水 Si 查询。\n"
                )

    # --- Analysis (only when allowed) ---
    if analysis_text and snapshot.analysis_allowed:
        lines.append("## 分析\n")
        lines.append(analysis_text)
        lines.append("\n> 相关性描述不代表因果关系。")
        lines.append("")
    elif analysis_text and not snapshot.analysis_allowed:
        lines.append("> ⚠️ 证据不完整，已跳过分析。以上为已有事实。\n")

    has_pearson_fact = any(
        fact.fact_id == "pearson_r" and not fact.missing and fact.value is not None
        for fact in snapshot.facts
    )
    if has_pearson_fact and not analysis_text:
        lines.append("> Pearson 相关系数只描述线性相关程度；相关不等于因果。\n")

    # --- Footer ---
    if snapshot.partial:
        lines.append(
            f"_部分结果 — 已返回 {sum(1 for f in snapshot.facts if not f.missing)}/"
            f"{len(snapshot.facts)} 项事实，"
            f"{len(snapshot.missing_fact_ids)} 项缺失。_"
        )
    elif snapshot.complete:
        lines.append(
            f"_完整结果 — {len(snapshot.facts)} 项事实全部返回，"
            f"总耗时 {snapshot.total_elapsed_ms:.0f}ms。_"
        )

    return "\n".join(lines)


def cross_source_snapshot_payload(snapshot: CrossSourceSnapshot) -> dict[str, Any]:
    """Return the JSON-safe evidence contract used by SSE and follow-ups."""

    payload = asdict(snapshot)
    payload["facts"] = payload.get("facts", [])[-8:]
    payload["source_status"] = payload.get("source_status", [])[-8:]
    return payload


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
    if qa_mcp_imes_query_intent(question):
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


def qa_mcp_planner_tools(
    question: str, tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Select a small registered-schema catalog for one planning request.

    The function never creates tool definitions.  It only removes unrelated
    schemas from the live MCP registry response, so the model remains free to
    choose among relevant registered tools while prompt size and misrouting
    risk stay bounded.
    """

    text = str(question or "").lower()
    explicit_heat = bool(
        re.search(r"\d{1,3}#\d{8}-\d{3,4}", text)
        or re.search(r"\d{8}-\d{3,4}", text)
        or re.search(r"(?<!\d)\d{2,4}\s*(?:这炉|那炉|炉|炉次)", text)
    )
    chemistry_terms = (
        "铁水", "化验", "成分", "含量", "碳", "硅", "锰", "磷", "硫",
        "钛", "钒", "铬", "铜", "镍", "砷", "si", "mn",
    )
    if explicit_heat and any(term in text for term in chemistry_terms):
        preferred = {
            "imes__query_heat_chemistry",
            "imes__query_hot_metal_chemistry_by_heat",
        }
        selected = [
            item
            for item in tools
            if (item.get("function") or {}).get("name") in preferred
        ]
        if selected:
            return selected
    return tools


def truncate_tool_text(text: str, max_chars: int = QA_MCP_MAX_RESULT_CHARS) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...（工具结果过长，已截断；原始长度 {len(text)} 字符）"


def mcp_result_to_text(result: Any, max_chars: int | None = QA_MCP_MAX_RESULT_CHARS) -> str:
    structured = getattr(result, "structuredContent", None)
    if structured:
        text = json.dumps(structured, ensure_ascii=False, default=str)
        return text if max_chars is None else truncate_tool_text(text, max_chars=max_chars)
    parts = []
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        parts.append(text if text is not None else str(content))
    text = "\n".join(parts)
    return text if max_chars is None else truncate_tool_text(text, max_chars=max_chars)


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


def qa_mcp_public_trace(event_name: str, payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build a bounded, credential-free UI trace for an MCP execution event.

    The public trace is an execution summary, not model chain-of-thought.  It
    deliberately excludes raw SQL, connection strings, local paths and full
    tool output while retaining the selected scope, source, elapsed time and
    evidence counts needed for operator audit.
    """

    tool_name = str(payload.get("tool") or "")
    if tool_name != "gl02ext__query_body_temperature_statistics":
        return None
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), Mapping) else {}
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    if isinstance(result.get("result"), Mapping):
        result = result["result"]
    result_layers = result.get("layers") if isinstance(result.get("layers"), list) else []
    start_layer = arguments.get("start_layer") or (result_layers[0] if result_layers else None)
    end_layer = arguments.get("end_layer") or (result_layers[-1] if result_layers else None)
    positions = arguments.get("positions") or result.get("positions") or []
    position_labels = [
        str(value) for value in positions
        if len(str(value)) == 1 and str(value) in "ABCDEFGH"
    ]
    try:
        layer_count = abs(int(end_layer) - int(start_layer)) + 1
    except (TypeError, ValueError):
        layer_count = len(result.get("layers") or [])
    point_count = layer_count * len(position_labels) if layer_count and position_labels else None
    scope = (
        f"第{start_layer}层至第{end_layer}层，{position_labels[0]}至{position_labels[-1]}方位"
        if start_layer is not None and end_layer is not None and position_labels
        else "炉体温度矩阵"
    )
    trace_id = f"tool:{payload.get('round', 0)}:{tool_name}"
    if event_name == "tool_start":
        start_time = arguments.get("start_time") or "未指定"
        end_time = arguments.get("end_time") or "未指定"
        return {
            "trace_id": trace_id,
            "stage": "tool",
            "status": "running",
            "title": "正在执行炉体温度矩阵统计",
            "detail": f"{scope}，共{point_count or '待确认'}个点位；时间窗 {start_time} 至 {end_time}。",
            "server": "GL02炉体温度只读MCP",
            "tool": "炉体温度矩阵批量统计",
            "call_count": 1,
        }
    if event_name != "tool_result":
        return None
    ok = result.get("ok") is not False
    quality = result.get("data_quality") if isinstance(result.get("data_quality"), Mapping) else {}
    source = result.get("source") if isinstance(result.get("source"), Mapping) else {}
    raw_rows = quality.get("raw_row_count")
    expected_rows = quality.get("expected_rows")
    missing_rows = quality.get("missing_row_count")
    if ok:
        detail = (
            f"{scope}批量计算完成；读取{raw_rows or 0}行，预期{expected_rows or 0}行，"
            f"缺失{missing_rows or 0}行。"
        )
    else:
        detail = "炉体温度矩阵查询失败；系统将保留确定性失败边界，不会编造实时数值。"
    return {
        "trace_id": trace_id,
        "stage": "tool",
        "status": "succeeded" if ok else "failed",
        "title": "炉体温度矩阵统计完成" if ok else "炉体温度矩阵统计失败",
        "detail": detail,
        "server": "GL02炉体温度只读MCP",
        "tool": "炉体温度矩阵批量统计",
        "source": (
            f"{source.get('schema')}.{source.get('object')}"
            if source.get("schema") and source.get("object")
            else "bf_sensor.one_minute_values"
        ),
        "elapsed_ms": payload.get("elapsed_ms"),
        "cache_hit": bool(payload.get("cache_hit")),
        "call_count": 1,
        "row_count": raw_rows,
        "point_count": quality.get("queried_point_count") or point_count,
    }


def qa_mcp_body_route_trace(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Describe deterministic semantic resolution and composite routing."""

    arguments = plan.get("arguments") if isinstance(plan.get("arguments"), Mapping) else {}
    first = arguments.get("start_layer")
    last = arguments.get("end_layer")
    positions = [str(value) for value in (arguments.get("positions") or [])]
    layer_count = abs(int(last) - int(first)) + 1 if first is not None and last is not None else 0
    point_count = layer_count * len(positions)
    position_scope = f"{positions[0]}至{positions[-1]}" if positions else "未指定"
    return [
        {
            "public_trace": {
                "trace_id": "route:semantic-resolution",
                "stage": "routing",
                "status": "succeeded",
                "title": "已完成中文对象解析",
                "detail": f"识别为第{first}层至第{last}层炉体温度、{position_scope}方位，共{point_count}个物理点位。",
            }
        },
        {
            "public_trace": {
                "trace_id": "route:composite-selection",
                "stage": "routing",
                "status": "succeeded",
                "title": "已选择一次复合MCP调用",
                "detail": "使用炉体温度矩阵批量统计工具完成读取、分钟对齐和确定性统计，不展开为逐点循环查询。",
                "server": "GL02炉体温度只读MCP",
                "tool": "炉体温度矩阵批量统计",
                "call_count": 1,
            }
        },
    ]


def qa_body_temperature_model_explanation(question: str, factual_answer: str) -> tuple[str, str]:
    """Generate one bounded qualitative explanation after deterministic facts.

    The factual answer remains authoritative.  A missing, failed or numerically
    ungrounded model response is discarded so the operator still receives the
    complete database-derived result.
    """

    messages = [
        {
            "role": "system",
            "content": (
                "你是高炉工艺数据解释助手。只能解释下面已经确认的统计事实，不能新增或修改任何数值、"
                "时间、层位、方位、来源或结论；不得把相关或伴随变化写成因果。"
                "只写一段简短的定性解释，区分数据事实、可能含义和证据边界，不给自动调控指令。"
            ),
        },
        {
            "role": "user",
            "content": f"用户问题：{question}\n\n已确认事实：\n{factual_answer}\n\n请解释这些事实。",
        },
    ]
    try:
        response = call_ollama_chat_obj(messages, tools=None, temperature=0.1, max_tokens=420)
        explanation = clean_llm_output(
            (response.get("message") or {}).get("content") or response.get("response") or ""
        ).strip()
    except Exception:
        return "", "failed"
    if not explanation:
        return "", "empty"
    factual_numbers = {float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", factual_answer)}
    explanation_numbers = {float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", explanation)}
    if any(value not in factual_numbers for value in explanation_numbers):
        return "", "rejected_ungrounded_numbers"
    return explanation, "succeeded"


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
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]
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

    if tool_name == "gl02ext__query_body_temperature_statistics":
        start_time = payload.get("start_time") or "未知"
        end_time = payload.get("end_time") or "未知"
        unit = payload.get("unit") or "℃"
        positions = "、".join(str(item) for item in (payload.get("positions") or [])) or "未指定"
        lines = [f"统计时间：{start_time} 至 {end_time}；方位：{positions}；单位：{unit}。"]
        point_rows = payload.get("point_statistics") or []
        if len(point_rows) == 1:
            point = point_rows[0]
            stats = point.get("statistics") or {}
            first = stats.get("first") or {}
            last = stats.get("last") or {}
            lines.append(
                f"第{point.get('layer')}层{point.get('position')}点：样本 {stats.get('count') or 0}，"
                f"平均 {number(stats.get('avg'))}{unit}，总体标准差 {number(stats.get('stddev_pop'))}{unit}，"
                f"最低 {number(stats.get('min'))}{unit}，最高 {number(stats.get('max'))}{unit}，"
                f"极差 {number(stats.get('range'))}{unit}。"
            )
            lines.append(
                f"首值 {number(first.get('value'))}{unit}（{first.get('ts') or '未知'}），"
                f"末值 {number(last.get('value'))}{unit}（{last.get('ts') or '未知'}），"
                f"首末变化量 {number(stats.get('delta'))}{unit}，"
                f"每分钟斜率 {number(stats.get('slope_per_min'))}{unit}/min，"
                f"CV {number(stats.get('cv_percent'))}%。"
            )
        elif point_rows:
            for point in point_rows:
                stats = point.get("statistics") or {}
                lines.append(
                    f"第{point.get('layer')}层{point.get('position')}方位：样本 {stats.get('count') or 0}/"
                    f"{point.get('expected_minute_count') or 0}，覆盖率 "
                    f"{number(float(point.get('coverage_ratio') or 0) * 100)}%，"
                    f"平均 {number(stats.get('avg'))}{unit}，总体标准差 {number(stats.get('stddev_pop'))}{unit}，"
                    f"最低 {number(stats.get('min'))}{unit}，最高 {number(stats.get('max'))}{unit}，"
                    f"极差 {number(stats.get('range'))}{unit}。"
                )
            for item in payload.get("layer_statistics") or []:
                stats = item.get("statistics") or {}
                lines.append(
                    f"第{item.get('layer')}层空间平均：完整对齐样本 {stats.get('count') or 0}/"
                    f"{item.get('expected_minute_count') or 0}，平均 {number(stats.get('avg'))}{unit}，"
                    f"方位完整对齐后的时序极差 {number(stats.get('range'))}{unit}。"
                )
        else:
            for item in payload.get("layer_statistics") or []:
                stats = item.get("statistics") or {}
                rolling = item.get("rolling_variation") or {}
                rolling_start = rolling.get("start") or {}
                rolling_end = rolling.get("end") or {}
                stddev_delta = rolling.get("stddev_delta")
                if stddev_delta is None:
                    rolling_direction = "无法判断"
                elif float(stddev_delta) > 0:
                    rolling_direction = "增大"
                elif float(stddev_delta) < 0:
                    rolling_direction = "减小"
                else:
                    rolling_direction = "不变"
                lines.append(
                    f"第{item.get('layer')}层：完整对齐样本 {stats.get('count') or 0}/"
                    f"{item.get('expected_minute_count') or 0}，覆盖率 "
                    f"{number(float(item.get('coverage_ratio') or 0) * 100)}%，"
                    f"层平均 {number(stats.get('avg'))}{unit}，总体标准差 {number(stats.get('stddev_pop'))}{unit}，"
                    f"最低 {number(stats.get('min'))}{unit}，最高 {number(stats.get('max'))}{unit}，"
                    f"极差 {number(stats.get('range'))}{unit}，CV {number(stats.get('cv_percent'))}%，"
                    f"首末变化量 {number(stats.get('delta'))}{unit}，"
                    f"每分钟斜率 {number(stats.get('slope_per_min'))}{unit}/min。"
                )
                if rolling:
                    lines.append(
                        f"- {rolling.get('window_minutes') or 15}分钟滚动标准差："
                        f"{number(rolling_start.get('stddev_pop'))} → {number(rolling_end.get('stddev_pop'))}{unit}，"
                        f"变化 {number(stddev_delta)}{unit}（{rolling_direction}）；滚动极差："
                        f"{number(rolling_start.get('range'))} → {number(rolling_end.get('range'))}{unit}，"
                        f"变化 {number(rolling.get('range_delta'))}{unit}。"
                    )
        quality = payload.get("data_quality") or {}
        lines.append(
            f"数据质量：读取 {quality.get('raw_row_count') or 0} 行，预期 {quality.get('expected_rows') or 0} 行，"
            f"缺失 {quality.get('missing_row_count') or 0} 行，非有限值 {quality.get('nonfinite_count') or 0}，"
            f"零值 {quality.get('zero_count') or 0}；未插值、未静默过滤。"
        )
        source = payload.get("source") or {}
        lines.append(
            f"来源：{source.get('service') or 'GL02只读MCP'} / "
            f"{source.get('schema') or 'bf_sensor'}.{source.get('object') or 'one_minute_values'}；"
            f"统计口径：层均值为同一分钟所选方位完整对齐后的算术平均，标准差为总体标准差。"
        )
        return "\n".join(lines)

    if tool_name == "imes__get_current_heat_context":
        current = payload.get("current_heat_no") or "未查到"
        previous = payload.get("previous_heat_no") or "未查到"
        status = "正在出铁" if payload.get("status") == "active" else "最近已知炉次"
        return (
            f"当前炉次：{current}（{status}）；上一炉次：{previous}。\n"
            f"查询时点：{payload.get('as_of_time') or '未知'}；来源：{payload.get('source_object') or 'MES炉次作业条件'}。"
        )
    if tool_name == "imes__query_heat_chemistry_by_time_range":
        window = payload.get("time_range") or {}
        lines = [
            f"查询时间段：{window.get('start') or '未知'} 至 {window.get('end') or '未知'}。",
        ]
        heats = payload.get("heats") or []
        if not heats:
            lines.append("该时间段附近未找到可确认的正式炉次。")
            return "\n".join(lines)
        lines.append(
            f"匹配到 {len(heats)} 个炉次；最可能炉次：{payload.get('primary_heat_no') or '未查到'}。"
        )
        for heat in heats:
            chemistry = heat.get("chemistry") or {}
            si_summary = (chemistry.get("summary") or {}).get("si") or {}
            match_label = "时间重叠" if heat.get("match_kind") == "overlap" else "最近炉次"
            if si_summary.get("avg") is None:
                si_text = "暂无有效Si试样"
            else:
                si_text = (
                    f"Si平均 {number(si_summary.get('avg'))}%（"
                    f"{si_summary.get('count') or 0} 个试样，"
                    f"{number(si_summary.get('min'))}%～{number(si_summary.get('max'))}%）"
                )
            lines.append(
                f"炉次 {heat.get('heat_no') or '未编号'}（{match_label}）："
                f"开口 {heat.get('open_time') or '未知'}，"
                f"结束 {heat.get('close_time') or '尚未记录'}；{si_text}。"
            )
            for sample in chemistry.get("samples") or []:
                si_value = (sample.get("components") or {}).get("si")
                time_type = sample.get("sample_time_type")
                time_label = {
                    "take_sample_time": "取样时间",
                    "judge_time": "化验判定时间",
                    "publish_time": "结果发布时间",
                }.get(time_type, "样本时间")
                lines.append(
                    f"- 试样 {sample.get('sample_no') or '未编号'}，"
                    f"铁罐 {sample.get('tank_no') or '未关联'}，"
                    f"Si {number(si_value)}%，{time_label} "
                    f"{sample.get('sample_time') or '未知'}"
                )
        lines.append(f"来源：{payload.get('source_service') or 'imes-readonly'}。")
        return "\n".join(lines)

    if tool_name in {
        "imes__query_heat_chemistry",
        "imes__query_current_heat_chemistry",
    }:
        heat_no = payload.get("resolved_heat_no") or payload.get("requested_heat_reference") or "未查到"
        if payload.get("missing"):
            opening = payload.get("open_time") or ((payload.get("heat_time_window") or {}).get("start"))
            return (
                f"炉次 {heat_no}（开口时间 {opening or '未知'}）"
                "暂无已发布的铁水化验数据，缺失值不按0计算。"
            )
        component_labels = {
            "c": "C", "si": "Si", "mn": "Mn", "p": "P", "s": "S",
            "ti": "Ti", "v": "V", "cr": "Cr", "cu": "Cu", "ni": "Ni", "as": "As",
        }
        lines = [f"炉次：{heat_no}"]
        if tool_name == "imes__query_current_heat_chemistry":
            status = "正在出铁，结果为当前已发布试样的阶段性统计" if payload.get("provisional") else "最近已知炉次"
            lines.append(
                f"状态：{status}；开口时间：{payload.get('open_time') or '未知'}；"
                f"结束时间：{payload.get('close_time') or '尚未记录'}。"
            )
        else:
            heat_window = payload.get("heat_time_window") or {}
            if heat_window.get("start"):
                lines.append(
                    f"开口时间：{heat_window.get('start')}；"
                    f"结束时间：{heat_window.get('end') or '尚未记录'}。"
                )
        summary = payload.get("summary") or {}
        for component in payload.get("components") or []:
            item = summary.get(component) or {}
            name = component_labels.get(component, str(component))
            if item.get("missing") or item.get("avg") is None:
                lines.append(f"{name}：无有效样本")
                continue
            lines.append(
                f"{name}：平均 {number(item.get('avg'))}%（范围 "
                f"{number(item.get('min'))}%～{number(item.get('max'))}%，"
                f"{item.get('count')} 个样本）"
            )
        samples = payload.get("samples") or []
        if samples:
            lines.append("试样明细：")
            for sample in samples:
                values = []
                for component in payload.get("components") or []:
                    value = (sample.get("components") or {}).get(component)
                    if value is not None:
                        values.append(f"{component_labels.get(component, component)} {number(value)}%")
                time_type = sample.get("sample_time_type")
                time_label = {
                    "take_sample_time": "取样时间",
                    "judge_time": "化验判定时间",
                    "publish_time": "结果发布时间",
                }.get(time_type, "样本时间")
                lines.append(
                    f"- 试样 {sample.get('sample_no') or '未编号'}，"
                    f"铁罐 {sample.get('tank_no') or '未关联'}："
                    f"{('，'.join(values) or '所选成分无数据')}；"
                    f"{time_label} {sample.get('sample_time') or sample.get('take_sample_time') or '未知'}"
                )
        lines.append(
            f"数据时间：{payload.get('data_time') or '未知'}；来源："
            f"{payload.get('source_service') or 'imes-readonly'}"
        )
        return "\n".join(lines)

    if tool_name == "imes__get_current_previous_heat_si_summary":
        if payload.get("missing"):
            return (
                f"当前炉次为 {payload.get('current_heat_no') or '未查到'}，上一炉次为 "
                f"{payload.get('previous_heat_no') or '未查到'}；该上一炉次没有有效Si试样，不能把缺失值当作0。\n"
                f"查询时点：{payload.get('as_of_time') or '未知'}。"
            )
        values = "、".join(number(value) for value in payload.get("si_values") or [])
        return (
            f"当前炉次：{payload.get('current_heat_no') or '未查到'}；上一炉次：{payload.get('previous_heat_no') or '未查到'}。\n"
            f"上一炉次铁水Si平均值为 {number(payload.get('si_avg'))}%（{payload.get('sample_count') or 0} 个有效试样，"
            f"范围 {number(payload.get('si_min'))}%–{number(payload.get('si_max'))}%，试样值：{values or '无'}）。\n"
            f"查询时点：{payload.get('as_of_time') or '未知'}；来源：MES正式炉次与铁水化验表。"
        )

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
            unit_text = unit or "单位未登记"
            source = item.get("source") or {}
            source_parts = [
                str(source.get("profile") or source.get("engine") or "gl02-data"),
                str(source.get("read_policy") or "readonly"),
            ]
            source_text = " / ".join(part for part in dict.fromkeys(source_parts) if part)
            latest = item.get("latest") or {}
            statistics = item.get("statistics") or {}
            if isinstance(latest, dict) and latest.get("value") is not None:
                lines.append(
                    f"{label(requested)}（{requested}）：{number(latest.get('value'))}{unit_text}；"
                    f"数据时间 {latest.get('ts') or '未知'}；"
                    f"质量 {latest.get('quality') or item.get('quality') or '未知'}；"
                    f"采集时间 {latest.get('collected_at') or '未知'}；来源：{source_text}。"
                )
            elif isinstance(statistics, dict) and statistics:
                avg = statistics.get("avg")
                stddev = statistics.get("stddev")
                minimum = statistics.get("min")
                maximum = statistics.get("max")
                value_range = (
                    float(maximum) - float(minimum)
                    if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float))
                    else None
                )
                cv = (
                    float(stddev) / float(avg) * 100.0
                    if isinstance(avg, (int, float)) and isinstance(stddev, (int, float)) and float(avg) != 0
                    else None
                )
                first = statistics.get("first") or {}
                last = statistics.get("last") or {}
                lines.append(
                    f"{label(requested)}（{requested}）：时间范围 "
                    f"{item.get('start_time') or payload.get('start_time') or '未知'} 至 "
                    f"{item.get('end_time') or payload.get('end_time') or '未知'}；"
                    f"样本数 {statistics.get('count') or 0}；均值 {number(avg)}{unit_text}；"
                    f"总体标准差 STDDEV_POP {number(stddev)}{unit_text}；"
                    f"最低 {number(minimum)}{unit_text}；最高 {number(maximum)}{unit_text}；"
                    f"极差 {number(value_range)}{unit_text}；"
                    f"首值 {number(first.get('value'))}{unit_text}（{first.get('ts') or '未知'}）；"
                    f"末值 {number(last.get('value'))}{unit_text}（{last.get('ts') or '未知'}）；"
                    f"变化量 {number(statistics.get('delta'))}{unit_text}；"
                    f"每分钟斜率 {number(statistics.get('slope_per_min'))}{unit_text}/min；"
                    f"趋势 {statistics.get('trend') or '未知'}；"
                    + (
                        f"CV = STDDEV_POP ÷ 均值 × 100% = {number(cv)}%；"
                        if cv is not None else
                        "CV = STDDEV_POP ÷ 均值 × 100%，均值为0或数据缺失，无法计算；"
                    )
                    + f"来源：{source_text}。"
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


def qa_mcp_fallback_messages(
    messages: list[dict[str, Any]],
    *,
    reason_code: str,
    reason_message: str,
) -> list[dict[str, Any]]:
    """Force one final no-tool answer when MCP planning cannot complete."""
    boundary = (
        "工具查询未能完成。你现在必须直接回答，不能再请求或假装调用任何工具。"
        "可以使用对话中已经提供的最近炉况、知识库证据和通用高炉工艺知识；"
        "如果缺少足以判断当前状态的实时数据，必须明确写出‘实时数据库未核实’，"
        "区分已知事实、条件性判断和建议复核项。不得编造当前数值、趋势、时间戳、炉次或数据库结果。"
        f"工具终止原因：{reason_code}；{reason_message}"
    )
    return [*messages, {"role": "system", "content": boundary}]


def qa_mcp_final_fallback(
    messages: list[dict[str, Any]],
    *,
    reason_code: str,
    reason_message: str,
) -> dict[str, Any]:
    """Run exactly one model-only completion after a tool failure or step limit."""
    fallback_messages = qa_mcp_fallback_messages(
        messages,
        reason_code=reason_code,
        reason_message=reason_message,
    )
    try:
        response = call_ollama_chat_obj(
            fallback_messages,
            tools=None,
            temperature=0.1,
            max_tokens=700,
        )
        answer = clean_llm_output(
            (response.get("message") or {}).get("content") or response.get("response") or ""
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "answer": "",
            "fallback_used": True,
            "fallback_error": f"{type(exc).__name__}: {exc}",
            "termination_reason": reason_code,
        }
    return {
        "ok": bool(answer),
        "answer": answer,
        "fallback_used": True,
        "answer_route": "model_without_tools_after_mcp_failure",
        "termination_reason": reason_code,
    }


def qa_mcp_result_with_fallback(
    result: Mapping[str, Any] | None,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Preserve successful tool answers; turn an empty tool failure into one model answer."""
    normalized = dict(result or {})
    if str(normalized.get("answer") or "").strip():
        return normalized
    reason_code = str(normalized.get("termination_reason") or "MCP_TOOL_UNAVAILABLE")
    reason_message = str(normalized.get("error") or "数据库或工具没有返回可用结果。")
    fallback = qa_mcp_final_fallback(
        normalized.get("messages") or messages,
        reason_code=reason_code,
        reason_message=reason_message,
    )
    return {**normalized, **fallback}


async def qa_mcp_execute_parallel_batch(
    tool_calls: list[dict[str, Any]],
    *,
    session: Any,
    tool_schemas: dict[str, dict[str, Any]],
    tool_servers: dict[str, str],
    policy_limits: ToolPolicyLimits,
    server_locks: dict[str, asyncio.Lock],
    tool_timeout_seconds: Any,
    round_number: int,
    planner_catalog_size: int,
    emit: Any | None = None,
) -> list[dict[str, Any]]:
    """Run one model-planned batch concurrently across independent MCP servers.

    MCP stdio sessions are request scoped. Calls routed to the same server stay
    serial, while calls routed to different servers may overlap. Results are
    returned in planner order so the following model turn sees a stable tool
    transcript regardless of completion order.
    """

    semaphore = asyncio.Semaphore(max(1, QA_MCP_MAX_PARALLEL_TOOL_CALLS))

    async def execute_one(tool_call: dict[str, Any]) -> dict[str, Any]:
        name = tool_call["name"]
        args = tool_call["arguments"]
        server_id = tool_servers.get(name)
        start_payload = {
            "tool": name,
            "arguments": args,
            "round": round_number,
            "route": "model_planner_parallel",
            "server_id": server_id,
            "planner_call": {"name": name, "arguments": args},
            "planner_catalog_size": planner_catalog_size,
        }
        if emit:
            emit("tool_start", start_payload)

        policy = validate_tool_call(name, args, tool_schemas, policy_limits)
        cache_hit = False
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
                lock_key = server_id or f"unattached:{name}"
                lock = server_locks.setdefault(lock_key, asyncio.Lock())
                try:
                    async with semaphore:
                        async with lock:
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

        trace_item = {
            "round": round_number,
            "route": "model_planner_parallel",
            "tool": name,
            "server_id": server_id,
            "arguments": args,
            "cache_hit": cache_hit,
            "policy": {
                "ok": policy["ok"],
                "policy": policy.get("policy"),
                "errors": policy.get("errors") or [],
            },
            "result": compact_tool_result_for_event(result_text),
        }
        return {"name": name, "result_text": result_text, "trace": trace_item}

    if QA_MCP_PARALLEL_TOOL_CALLS and len(tool_calls) > 1:
        batch = await asyncio.gather(*(execute_one(tool_call) for tool_call in tool_calls))
    else:
        batch = []
        for tool_call in tool_calls:
            batch.append(await execute_one(tool_call))
    for item in batch:
        if emit:
            emit("tool_result", item["trace"])
    return batch


def qa_mcp_current_user_text(question: str) -> str:
    return str(question or "").split("\n[服务端对话状态：", 1)[0].strip()


def qa_mcp_planning_question(question: str) -> str:
    """Use prior context only for genuinely referential follow-up questions."""

    raw = str(question or "")
    current = qa_mcp_current_user_text(raw)
    has_reference = any(term in current for term in (
        "它", "该变量", "这个变量", "上述变量", "刚才的", "前面的",
    ))
    has_explicit_object = bool(
        qa_mcp_variables(current)
        or qa_mcp_imes_plan(current)
        or _detect_heat_reference(current)
    )
    return raw if has_reference and not has_explicit_object else current


def qa_mcp_preflight_answer(question: str) -> str | None:
    """Enforce zero-tool safety, ambiguity and unknown-object gates."""

    current = qa_mcp_current_user_text(question)
    normalized = normalize_spoken_question(current)
    lower = normalized.lower()
    write_terms = ("删除", "删掉", "修改", "写入", "更新数据库", "清空", "drop", "delete", "update")
    secret_terms = ("密码", "口令", "凭据", "token", "密钥", "连接串", "dsn")
    if any(term in lower for term in write_terms) or any(term in lower for term in secret_terms):
        return (
            "拒绝执行：智能助手只允许只读查询，不能删除、修改或写入生产数据，"
            "也不会提供数据库密码、连接串或其他凭据。本次未调用任何数据工具。"
        )

    ambiguous_pressure = any(term in normalized for term in ("中部压力", "上部压力", "下部压力"))
    disambiguated = any(term in normalized for term in (
        "静压力", "静压", "压差", "20.35", "20米35", "23.49", "23米49", "28.98", "28米98",
    ))
    if ambiguous_pressure and not disambiguated:
        return (
            "“中部/上部/下部压力”存在歧义。请明确是静压力还是压差，并补充层位高度或方位；"
            "在对象唯一确定前不会查询，也不会猜成 23.49 米静压力或其他相似点位。"
        )

    explicit_ids = re.findall(r"(?i)(?<![a-z0-9_])([a-z][a-z0-9]*(?:_[a-z0-9]+)+)(?![a-z0-9_])", current)
    known_ids = {item.lower() for item in QA_MCP_STANDARD_VARIABLES}
    for explicit_id in explicit_ids:
        lowered_id = explicit_id.lower()
        looks_like_sensor = lowered_id.startswith(("p_", "t_", "dp_", "q_", "pci_", "o2_", "l_", "co_"))
        catalog_match = bool(qa_mcp_catalog_variables(explicit_id))
        if looks_like_sensor and lowered_id not in known_ids and not catalog_match:
            return (
                f"不存在/未知点位 `{explicit_id}`：权威语义目录中没有该对象。"
                "不会把它替换成 P_top、A–D 点或其他相似变量；请核对标准变量名。"
            )
    return None


def qa_mcp_no_realtime_requested(question: str) -> bool:
    current = qa_mcp_current_user_text(question)
    return any(term in current for term in ("不要查询实时", "不查询实时", "无需查询实时", "不要查实时"))


async def qa_mcp_tool_loop_async(
    messages: list[dict[str, Any]],
    emit: Any | None = None,
    stop_after_tool_round: bool = False,
    routing_question: str = "",
) -> dict[str, Any]:
    raw_question = routing_question or last_user_question(messages)
    preflight_answer = qa_mcp_preflight_answer(raw_question)
    if preflight_answer:
        return {
            "ok": True,
            "tool_used": False,
            "answer": preflight_answer,
            "messages": messages,
            "tool_trace": [],
            "answer_route": "deterministic_preflight_gate",
        }
    working_messages = qa_messages_with_mcp_prompt(messages)
    if qa_mcp_no_realtime_requested(raw_question):
        response = call_ollama_chat_obj(working_messages, tools=None)
        answer = clean_llm_output((response.get("message") or {}).get("content") or response.get("response") or "")
        boundary = "本次未查询实时数据库，以上为一般工艺知识；用于当前炉况前请结合现场数据复核。"
        if boundary not in answer:
            answer = f"{answer.rstrip()}\n\n{boundary}".strip()
        return {
            "ok": True,
            "tool_used": False,
            "answer": answer,
            "messages": working_messages,
            "tool_trace": [],
            "answer_route": "explicit_no_realtime_model_answer",
        }
    question = qa_mcp_planning_question(raw_question)
    try:
        registry = qa_mcp_server_registry()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "tool_used": False,
            "answer": "",
            "error": f"MCP服务注册表不可用：{type(exc).__name__}: {exc}",
        }

    trace: list[dict[str, Any]] = []
    execution_started = time.monotonic()
    service_selection = select_mcp_servers(question, registry)
    # Resolve the Chinese layer/position scope before MCP discovery so the UI
    # can show a useful execution stage immediately instead of a generic wait.
    body_statistics_plan = qa_mcp_body_temperature_statistics_plan(question)
    if body_statistics_plan is not None and emit:
        for public_event in qa_mcp_body_route_trace(body_statistics_plan):
            emit("trace", public_event)

    def tool_timeout_seconds() -> float:
        remaining = QA_MCP_EXECUTION_BUDGET_SECONDS - (time.monotonic() - execution_started)
        if remaining <= 0:
            raise TimeoutError(f"MCP执行预算已用尽（{QA_MCP_EXECUTION_BUDGET_SECONDS:.0f}秒）")
        return max(0.1, min(QA_MCP_TOOL_TIMEOUT_SECONDS, remaining))

    manager = McpClientManager(registry, QA_MCP_PYTHON)
    async with manager:
        try:
            bindings = await manager.attach(service_selection.server_ids)
        except McpHostError as exc:
            return {
                "ok": False,
                "tool_used": False,
                "answer": "",
                "error": f"MCP服务不可用：{exc}",
                "server_selection": {
                    "server_ids": list(service_selection.server_ids),
                    "domains": list(service_selection.matched_domains),
                    "reasons": list(service_selection.reasons),
                },
            }
        # A partial attach is not a request-level failure.  The cross-source
        # executor records the unavailable server as a missing source and
        # returns already successful facts deterministically.  A total attach
        # failure still raises McpHostError above.
        async with manager.execution_scope() as session:
            tools = manager.ollama_tools()
            tool_names = {binding.exposed_name for binding in bindings}
            tool_schemas = {binding.exposed_name: binding.input_schema for binding in bindings}
            tool_servers = {binding.exposed_name: binding.server_id for binding in bindings}
            policy_limits = ToolPolicyLimits(
                max_argument_chars=max(1000, QA_MCP_MAX_ARGUMENT_CHARS),
                max_array_items=max(1, QA_MCP_MAX_ARRAY_ITEMS),
            )
            tool_call_count = 0
            planner_server_locks: dict[str, asyncio.Lock] = {}

            # A composite body-temperature query must win before the generic
            # DAG builder expands it into many individual point calls.
            # --- Cross-source plan path (REQ-8093-CROSS-SOURCE-MCP-20260805) ---
            cross_source_plan = (
                None
                if body_statistics_plan is not None
                else build_cross_source_plans(question, service_selection)
            )
            if (
                cross_source_plan is not None
                and len(set(s.step_id for s in cross_source_plan.steps)) >= 2
                and len(cross_source_plan.steps) <= max(1, QA_MCP_MAX_TOOL_CALLS)
            ):
                # Execute via cross-source DAG executor
                child_timeout = float(
                    os.environ.get(
                        "BF_QA_MCP_CROSS_SOURCE_CHILD_TIMEOUT_SECONDS", "15"
                    )
                )
                cross_source_budget = float(
                    os.environ.get(
                        "BF_QA_MCP_CROSS_SOURCE_BUDGET_SECONDS", "45"
                    )
                )
                from mcp_host.cross_source_executor import execute_cross_source_plan

                snapshot = await execute_cross_source_plan(
                    plan=cross_source_plan,
                    manager=manager,
                    session=session,
                    tool_schemas=tool_schemas,
                    tool_servers=tool_servers,
                    policy_limits=policy_limits,
                    tool_cache_get=qa_mcp_tool_cache_get,
                    tool_cache_put=qa_mcp_tool_cache_put,
                    execution_started=execution_started,
                    budget_seconds=cross_source_budget,
                    child_timeout_seconds=child_timeout,
                    emit=emit,
                )

                # Build trace from source_status
                for ss in snapshot.source_status or ():
                    trace.append({
                        "round": 0,
                        "route": "cross_source_dag",
                        "tool": ss.get("tool", ""),
                        "server_id": ss.get("server_id", ""),
                        "arguments": ss.get("arguments", {}),
                        "cache_hit": ss.get("cache_hit", False),
                        "policy": {"ok": ss.get("ok", False), "policy": "live_mcp_schema_readonly"},
                        "result": {"ok": ss.get("ok"), "error_code": ss.get("error_code")},
                        "orchestration_id": snapshot.orchestration_id,
                        "step_id": ss.get("step_id"),
                        "required_for_analysis": ss.get("required_for_analysis"),
                        "elapsed_ms": ss.get("elapsed_ms"),
                    })
                cross_snapshot_payload = cross_source_snapshot_payload(snapshot)

                if not snapshot.ok:
                    heat_resolution_error = next(
                        (
                            str(item.get("error_code") or "")
                            for item in snapshot.source_status
                            if str(item.get("tool") or "") == "imes__resolve_spoken_heat_reference"
                            and item.get("error_code")
                        ),
                        "",
                    )
                    if heat_resolution_error in {"HEAT_REFERENCE_NOT_FOUND", "HEAT_REFERENCE_AMBIGUOUS"}:
                        answer = format_cross_source_answer(snapshot)
                        return {
                            "ok": True,
                            "tool_used": True,
                            "answer": answer,
                            "tool_trace": trace,
                            "answer_route": "deterministic_heat_dependency_failure",
                            "mcp_cross_source": {
                                "orchestration_id": snapshot.orchestration_id,
                                "complete": snapshot.complete,
                                "partial": snapshot.partial,
                                "analysis_allowed": False,
                                "error_code": heat_resolution_error,
                                "step_count": len(cross_source_plan.steps),
                                "success_count": 0,
                                "total_elapsed_ms": snapshot.total_elapsed_ms,
                            },
                            "cross_source_snapshot": cross_snapshot_payload,
                        }
                    return {
                        "ok": False,
                        "tool_used": True,
                        "answer": "",
                        "error": "跨源数据查询失败，所有来源均未返回有效结果。",
                        "tool_trace": trace,
                        "mcp_cross_source": {
                            "orchestration_id": snapshot.orchestration_id,
                            "complete": snapshot.complete,
                            "partial": snapshot.partial,
                            "analysis_allowed": snapshot.analysis_allowed,
                            "error_code": snapshot.error_code,
                            "total_elapsed_ms": snapshot.total_elapsed_ms,
                        },
                        "cross_source_snapshot": cross_snapshot_payload,
                    }

                # Fact-only queries: deterministic formatter, no model call
                if not cross_source_plan.analysis_requested or not snapshot.analysis_allowed:
                    answer = format_cross_source_answer(snapshot)
                    return {
                        "ok": True,
                        "tool_used": True,
                        "answer": answer,
                        "tool_trace": trace,
                        "answer_route": "cross_source_deterministic_formatter",
                        "mcp_cross_source": {
                            "orchestration_id": snapshot.orchestration_id,
                            "complete": snapshot.complete,
                            "partial": snapshot.partial,
                            "analysis_allowed": snapshot.analysis_allowed,
                            "error_code": snapshot.error_code,
                            "step_count": len(cross_source_plan.steps),
                            "success_count": sum(1 for f in snapshot.facts if not f.missing),
                            "total_elapsed_ms": snapshot.total_elapsed_ms,
                        },
                        "cross_source_snapshot": cross_snapshot_payload,
                    }

                # Analysis requested + evidence complete → one low-temp model call
                fact_answer = format_cross_source_answer(snapshot)
                analysis_max_tokens = int(
                    os.environ.get(
                        "BF_QA_MCP_CROSS_SOURCE_ANALYSIS_MAX_TOKENS", "360"
                    )
                )
                analysis_messages = [
                    {"role": "system", "content": (
                        "你是高炉工艺助手。以下为已确认的跨数据源查询事实。"
                        "你只能基于这些事实进行解释，不得编造、猜测或建议操作。"
                        "输出应简洁，只解释用户问到的数据之间的关系；"
                        "凡涉及Pearson相关性，必须明确‘相关不等于因果’，不得使用导致、造成等因果措辞。"
                    )},
                    {"role": "user", "content": (
                        f"用户问题：{question}\n\n"
                        f"以下为查询结果：\n{fact_answer}\n\n"
                        f"请基于以上事实回答用户的分析需求。"
                    )},
                ]
                try:
                    analysis_response = call_ollama_chat_obj(
                        analysis_messages,
                        tools=None,
                        temperature=0.1,
                        max_tokens=analysis_max_tokens,
                    )
                    analysis_text = clean_llm_output(
                        (analysis_response.get("message") or {}).get("content")
                        or analysis_response.get("response") or ""
                    )
                except Exception:
                    analysis_text = None

                answer = format_cross_source_answer(snapshot, analysis_text)
                return {
                    "ok": True,
                    "tool_used": True,
                    "answer": answer,
                    "tool_trace": trace,
                    "answer_route": "cross_source_with_analysis",
                    "mcp_cross_source": {
                        "orchestration_id": snapshot.orchestration_id,
                        "complete": snapshot.complete,
                        "partial": snapshot.partial,
                        "analysis_allowed": snapshot.analysis_allowed,
                        "error_code": snapshot.error_code,
                        "analysis_status": "ok" if analysis_text else "failed",
                        "step_count": len(cross_source_plan.steps),
                        "success_count": sum(1 for f in snapshot.facts if not f.missing),
                        "total_elapsed_ms": snapshot.total_elapsed_ms,
                    },
                    "cross_source_snapshot": cross_snapshot_payload,
                }

            # --- Existing single-plan fast path (unchanged) ---
            imes_plan = qa_mcp_imes_plan(question)
            chart_plan = qa_mcp_chart_plan(question)
            standard_plan = qa_mcp_standard_analysis_plan(question)
            sensor_plan = body_statistics_plan or qa_mcp_sensor_query_plan(question)
            # Body-temperature-only questions may attach the extended server
            # whose exposed tool is namespaced and layer/position based.
            if (
                sensor_plan
                and "gl02-extended" in service_selection.server_ids
                and "gl02-data" not in service_selection.server_ids
            ):
                body_variables = sensor_plan.get("arguments", {}).get("variables") or []
                if len(body_variables) == 1:
                    body_match = re.fullmatch(
                        r"T_body_L(7|8|9|1[0-6])_([A-H])", str(body_variables[0])
                    )
                    if body_match:
                        sensor_plan = {
                            "tool": "gl02ext__query_body_temperature",
                            "arguments": {
                                "layer": int(body_match.group(1)),
                                "position": body_match.group(2),
                                "include_history": False,
                            },
                        }
            deterministic_plan = imes_plan or chart_plan or standard_plan or sensor_plan
            if deterministic_plan and deterministic_plan["tool"] in tool_names:
                name = deterministic_plan["tool"]
                args = deterministic_plan["arguments"]
                route = (
                    "deterministic_imes_query"
                    if imes_plan
                    else "deterministic_chart"
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
                start_payload = {"tool": name, "arguments": args, "round": 0, "route": route}
                public_start = qa_mcp_public_trace("tool_start", start_payload)
                if public_start:
                    start_payload["public_trace"] = public_start
                if emit:
                    emit("tool_start", start_payload)
                call_started = time.monotonic()
                result_text = qa_mcp_tool_cache_get(name, args)
                cache_hit = result_text is not None
                if result_text is None:
                    try:
                        result = await asyncio.wait_for(
                            session.call_tool(name, args),
                            timeout=tool_timeout_seconds(),
                        )
                        result_text = mcp_result_to_text(
                            result,
                            max_chars=None
                            if name == "gl02ext__query_body_temperature_statistics"
                            else QA_MCP_MAX_RESULT_CHARS,
                        )
                        qa_mcp_tool_cache_put(name, args, result_text)
                    except Exception as exc:  # noqa: BLE001
                        result_text = json.dumps(
                            {"ok": False, "error": type(exc).__name__, "message": str(exc), "tool": name},
                            ensure_ascii=False,
                        )
                elapsed_ms = round((time.monotonic() - call_started) * 1000, 1)
                working_messages.append({"role": "tool", "name": name, "content": result_text})
                trace_item = {
                    "round": 0,
                    "route": route,
                    "tool": name,
                    "server_id": tool_servers.get(name),
                    "arguments": args,
                    "cache_hit": cache_hit,
                    "elapsed_ms": elapsed_ms,
                    "policy": {"ok": True, "policy": policy["policy"]},
                    "result": compact_tool_result_for_event(result_text),
                }
                public_result_payload = {
                    **trace_item,
                    "result": try_load_json(result_text) or trace_item["result"],
                }
                public_result = qa_mcp_public_trace("tool_result", public_result_payload)
                if public_result:
                    trace_item["public_trace"] = public_result
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
                    model_explanation = {"status": "not_applicable"}
                    if name == "gl02ext__query_body_temperature_statistics":
                        analysis_start = {
                            "public_trace": {
                                "trace_id": "analysis:body-temperature",
                                "stage": "analysis",
                                "status": "running",
                                "title": "正在生成模型解释",
                                "detail": "模型只解释已确认的统计事实；新增数值或越过证据边界的内容将被丢弃。",
                            }
                        }
                        if emit:
                            emit("analysis_start", analysis_start)
                        analysis_started = time.monotonic()
                        explanation, explanation_status = qa_body_temperature_model_explanation(
                            question,
                            direct_answer,
                        )
                        analysis_elapsed_ms = round((time.monotonic() - analysis_started) * 1000, 1)
                        model_explanation = {
                            "status": explanation_status,
                            "elapsed_ms": analysis_elapsed_ms,
                        }
                        if explanation:
                            direct_answer = f"{direct_answer}\n\n模型解释（基于上述已确认事实）：\n{explanation}"
                        analysis_result = {
                            "public_trace": {
                                "trace_id": "analysis:body-temperature",
                                "stage": "analysis",
                                "status": "succeeded" if explanation else "failed",
                                "title": "模型解释完成" if explanation else "模型解释未采用",
                                "detail": (
                                    "解释已通过数值证据边界校验。"
                                    if explanation
                                    else "模型解释为空、调用失败或含未核实数字；最终答案保留完整确定性统计。"
                                ),
                                "elapsed_ms": analysis_elapsed_ms,
                            }
                        }
                        if emit:
                            emit("analysis_result", analysis_result)
                    return {
                        "ok": True,
                        "tool_used": True,
                        "answer": direct_answer,
                        "messages": working_messages,
                        "tool_trace": trace,
                        "answer_route": (
                            "deterministic_formatter_with_grounded_model_explanation"
                            if name == "gl02ext__query_body_temperature_statistics"
                            else "deterministic_formatter"
                        ),
                        "model_explanation": model_explanation,
                        "model_request_count": (
                            1 if name == "gl02ext__query_body_temperature_statistics" else 0
                        ),
                    }
                if name == "gl02ext__query_body_temperature_statistics":
                    return {
                        "ok": False,
                        "tool_used": True,
                        "answer": "炉体温度统计结果无法完整解析；本次没有交给模型重新计算，也没有编造数值。",
                        "error": "body_temperature_statistics_result_invalid",
                        "messages": working_messages,
                        "tool_trace": trace,
                        "answer_route": "deterministic_formatter_failed_closed",
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
                planner_tools = qa_mcp_planner_tools(question, tools)
                response = call_ollama_chat_obj(
                    planner_messages,
                    tools=planner_tools,
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

                remaining_calls = max(1, QA_MCP_MAX_TOOL_CALLS) - tool_call_count
                selected_calls = tool_calls[:remaining_calls]
                if not selected_calls:
                    break
                message["tool_calls"] = [
                    {"function": {"name": item["name"], "arguments": item["arguments"]}}
                    for item in selected_calls
                ]
                working_messages.append(message)
                tool_call_count += len(selected_calls)
                batch = await qa_mcp_execute_parallel_batch(
                    selected_calls,
                    session=session,
                    tool_schemas=tool_schemas,
                    tool_servers=tool_servers,
                    policy_limits=policy_limits,
                    server_locks=planner_server_locks,
                    tool_timeout_seconds=tool_timeout_seconds,
                    round_number=round_index + 1,
                    planner_catalog_size=len(planner_tools),
                    emit=emit,
                )
                for item in batch:
                    working_messages.append(
                        {"role": "tool", "name": item["name"], "content": item["result_text"]}
                    )
                    trace.append(item["trace"])
                result_text = batch[-1]["result_text"] if batch else ""

                if (
                    len(selected_calls) == 1
                    and trace
                    and trace[-1].get("tool") == "imes__query_heat_chemistry"
                    and trace[-1].get("policy", {}).get("ok")
                    and not qa_mcp_agent_planning_intent(question)
                ):
                    direct_answer = deterministic_mcp_answer(
                        "imes__query_heat_chemistry", result_text
                    )
                    if direct_answer:
                        return {
                            "ok": True,
                            "tool_used": True,
                            "answer": direct_answer,
                            "messages": working_messages,
                            "tool_trace": trace,
                            "answer_route": "model_planner_then_deterministic_formatter",
                        }

                if stop_after_tool_round:
                    return {
                        "ok": True,
                        "tool_used": True,
                        "needs_final": True,
                        "messages": working_messages,
                        "tool_trace": trace,
                    }

    fallback = qa_mcp_final_fallback(
        working_messages,
        reason_code="MCP_PLAN_LIMIT_REACHED",
        reason_message=(
            f"规划已达到 {max(1, QA_MCP_MAX_TOOL_ROUNDS)} 轮或 "
            f"{max(1, QA_MCP_MAX_TOOL_CALLS)} 次工具调用上限。"
        ),
    )
    return {
        **fallback,
        "tool_used": bool(trace),
        "messages": working_messages,
        "tool_trace": trace,
    }


def run_qa_mcp_tool_loop(
    messages: list[dict[str, Any]],
    emit: Any | None = None,
    stop_after_tool_round: bool = False,
    routing_question: str = "",
) -> dict[str, Any]:
    try:
        return asyncio.run(
            qa_mcp_tool_loop_async(
                messages,
                emit=emit,
                stop_after_tool_round=stop_after_tool_round,
                routing_question=routing_question,
            )
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        diagnostic = lifecycle_error("request_handler", exc)
        return {
            "ok": False,
            "tool_used": False,
            "answer": "",
            "error": "MCP请求生命周期异常",
            "error_detail": diagnostic,
        }


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


def qa_search_knowledge(
    question: str,
    mode: str | None = None,
    mcp_prefetch: dict[str, Any] | None = None,
    connection: Any | None = None,
) -> dict[str, Any]:
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
        connection=connection,
    )


def build_hidden_qa_messages(
    question: str,
    snapshots: list[dict[str, Any]],
    history: list[dict[str, Any]],
    project_context: str = "",
    mcp_context: str = "",
    context_meta: dict[str, Any] | None = None,
    knowledge_context: str = "",
    assistant_rule_context: str = "",
    analysis_mode: str = "",
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
    if assistant_rule_context:
        hidden_block += (
            "\n【本对话绑定的ABC规则权威上下文】\n"
            "该上下文由服务端按会话来源加载，回答规则形成过程时必须以它为准；"
            "不得用浏览器自带数值覆盖。"
            "对于本ABC规则上下文，可展示合同已公开的公式项、权重、归一化分和加权得分；"
            "这是对通用“不解释内部算法公式”边界的唯一例外，仍不得暴露程序实现或未公开字段。\n"
            f"{assistant_rule_context}"
        )
    system_prompt = QA_SYSTEM_PROMPT_TEMPLATE.format(
        hidden=hidden_block,
        project_rules=QA_PROJECT_RULES_BLOCK,
        selected_project_context=selected_project_context,
        mcp_context=mcp_context or "本轮未执行数据库预查询。",
        knowledge_context=knowledge_context or "本轮未检索到可用知识库证据。",
    )
    if analysis_mode == "initial_context_explanation" and assistant_rule_context:
        context_value = load_json(assistant_rule_context, {})
        system_prompt += "\n\n" + abc_rule_assistant_analysis.initial_analysis_prompt(context_value)
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


def call_ollama_chat_strict_json(
    messages: list[dict[str, str]],
    assistant_context: Mapping[str, Any],
    max_tokens: int = 1200,
) -> str:
    """Call the model without public-text rewriting; strict validation follows immediately."""
    payload = build_api_chat_payload(
        {
            "model": normalize_model(None),
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": False,
            "format": abc_rule_assistant_analysis.initial_analysis_json_schema(assistant_context),
        }
    )
    req = build_ollama_request("/api/chat", body=json_bytes(payload), stream=False)
    with urlopen(req, timeout=300) as resp:
        obj = json.loads(resp.read().decode("utf-8", errors="replace"))
    return str(((obj.get("message") or {}).get("content") or obj.get("response") or "")).strip()


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
    if payload.get("format") is not None:
        out["format"] = payload.get("format")
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


def load_latest_abc33_review_score(
    diagnosis_ts: Any, snapshot_id: Any, rule_id: str = "B4"
) -> dict[str, Any]:
    """Read the production-safe ABC33 rule aligned to one diagnosis snapshot."""

    try:
        with _assistant_raw_pg_connect() as conn:
            batch = conn.execute(
                """
                SELECT id, evaluation_ts, catalog_version, config_version,
                       source_snapshot_id, public_bundle
                FROM bf_sensor.abc_rule_evaluation_batches
                WHERE evaluation_ts <= %s::timestamptz
                ORDER BY CASE WHEN source_snapshot_id::text = %s THEN 0 ELSE 1 END,
                         evaluation_ts DESC, id DESC
                LIMIT 1
                """,
                (diagnosis_ts, str(snapshot_id)),
            ).fetchone()
        if not batch:
            return {"rule_id": rule_id, "state": "needs_data"}
        data = (
            dict(batch)
            if isinstance(batch, Mapping)
            else {
                "id": batch[0],
                "evaluation_ts": batch[1],
                "catalog_version": batch[2],
                "config_version": batch[3],
                "source_snapshot_id": batch[4],
                "public_bundle": batch[5],
            }
        )
        bundle = data.get("public_bundle") or {}
        if isinstance(bundle, str):
            bundle = json.loads(bundle)
        rules = bundle.get("rules") if isinstance(bundle, Mapping) else []
        rule = next(
            (
                dict(item)
                for item in rules or []
                if isinstance(item, Mapping) and item.get("rule_id") == rule_id
            ),
            None,
        )
        return {
            "evaluation_id": data.get("id"),
            "evaluation_ts": data.get("evaluation_ts"),
            "catalog_version": data.get("catalog_version"),
            "config_version": data.get("config_version"),
            "source_snapshot_id": data.get("source_snapshot_id"),
            "source_snapshot_match": str(data.get("source_snapshot_id"))
            == str(snapshot_id),
            "rule_id": rule_id,
            "rule": rule,
            "state": "current" if rule else "needs_data",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "rule_id": rule_id,
            "state": "unavailable",
            "error_type": type(exc).__name__,
        }


def load_five_minute_diagnosis_context(
    target_label: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read the latest diagnosis and trusted evidence for one selected condition."""
    review_store = diagnosis_review.DiagnosisReviewStore()
    normalized_rows = review_store.read_latest_diagnosis_rows(
        limit=max(32, DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT)
    )
    canonical = diagnosis_review.derive_current_episode(
        normalized_rows, furnace_id="BF"
    )
    if canonical.get("available"):
        canonical = diagnosis_review.apply_abc33_display_score(
            canonical,
            load_latest_abc33_review_score(
                canonical.get("diagnosis_ts"), canonical.get("snapshot_id"), "B4"
            ),
        )
        evidence_rows = review_store.read_diagnosis_evidence_rows(
            diagnosis_ts=canonical["diagnosis_ts"],
            variables=diag_ai_evidence.SENSOR_VARIABLES,
            window_minutes=60,
            baseline_days=30,
        )
        variable_stats = diag_ai_evidence.build_variable_stats(
            evidence_rows.get("sensor_rows") or [],
            evidence_rows.get("baseline_rows") or [],
            canonical["diagnosis_ts"],
        )
        feature_snapshot = canonical.get("feature_snapshot")
        feature_snapshot = feature_snapshot if isinstance(feature_snapshot, Mapping) else {}
        rule_drivers = diag_ai_evidence.build_rule_driver_context(
            feature_snapshot, variable_stats
        )
        secondary_rows = canonical.get("secondary")
        secondary_rows = secondary_rows if isinstance(secondary_rows, list) else []
        secondary_label = next(
            (
                str(row.get("label"))
                for row in secondary_rows
                if isinstance(row, Mapping) and row.get("label")
            ),
            None,
        )
        selected_label = str(target_label or canonical.get("main_label") or "normal")
        if selected_label not in diagnosis_model_review.DIAGNOSIS_LABELS:
            selected_label = str(canonical.get("main_label") or "normal")
        diagnosis_payload = {
            "timestamp": canonical.get("diagnosis_ts"),
            "main_label": canonical.get("main_label"),
            "main_score": canonical.get("display_main_score"),
            "secondary_label": secondary_label,
            "target_label": selected_label,
            "raw_scores": canonical.get("display_scores") or {},
            "feature_snapshot": feature_snapshot,
        }
        evidence_terms = "、".join(
            item
            for item in diagnosis_model_review._text_list(
                canonical.get("evidence"), limit=6
            )
            if item
        )
        knowledge_question = (
            f"{diagnosis_model_review.DISPLAY_NAMES[selected_label]}的现象特征、"
            "复查传感器、数据变化、候选调节方向和现场复盘依据。"
            f"本次只分析{diagnosis_model_review.DISPLAY_NAMES[selected_label]}。"
            f"当前证据：{evidence_terms or '以规则变量和趋势为准'}。"
        )
        if QA_KNOWLEDGE_ENABLED:
            knowledge_pack = search_knowledge(
                knowledge_question,
                db_path=QA_KNOWLEDGE_DB_PATH,
                top_k=max(8, min(QA_KNOWLEDGE_TOP_K, 10)),
                mode=QA_KNOWLEDGE_SEARCH_MODE,
                source_doc_ids=[diag_ai_evidence.FOREMAN_KNOWLEDGE_DOC_ID],
            )
        else:
            knowledge_pack = {
                "enabled": False,
                "evidence": [],
                "message": "知识库检索已关闭",
                "retrieval_mode": QA_KNOWLEDGE_SEARCH_MODE,
                "source_doc_ids": [diag_ai_evidence.FOREMAN_KNOWLEDGE_DOC_ID],
            }
        knowledge_context = diag_ai_evidence.normalize_knowledge_pack(
            knowledge_pack, limit=10
        )
        recommendation_context = (
            diag_ai_evidence.build_foreman_knowledge_recommendation_bundle(
                diagnosis_payload,
                diag_ai_evidence.latest_values(variable_stats),
                knowledge_context,
                variable_stats,
                target_label=selected_label,
            )
            if DIAGNOSIS_ADVICE_SOURCE == "foreman_knowledge_only"
            else {
                "available": False,
                "conditions": {},
                "engine_meta": {"read_only": True},
                "source_mode": DIAGNOSIS_ADVICE_SOURCE,
                "read_only": True,
                "error": "智能分析只允许使用64主题知识库",
            }
        )
        canonical.update(
            {
                "variable_stats": variable_stats,
                "rule_drivers": rule_drivers,
                "recommendation_context": recommendation_context,
                "sensor_deviation_summary": recommendation_context.get(
                    "sensor_deviation_summary"
                ),
                "knowledge_context": knowledge_context,
            }
        )
    history = list(reversed(normalized_rows[:DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT]))
    return canonical, history


def current_five_minute_analysis_context(
    target_label: str | None = None,
) -> dict[str, Any]:
    """Return the normalized, server-owned context for the current five-minute bucket."""
    canonical, history = load_five_minute_diagnosis_context(target_label)
    return diagnosis_model_review.normalize_five_minute_context(
        canonical,
        history,
        bucket_minutes=DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES,
    )


def current_core_variable_evidence(target_label: str) -> dict[str, Any]:
    """Return trusted core curves without model, recommendation, or knowledge work."""
    review_store = diagnosis_review.DiagnosisReviewStore()
    normalized_rows = review_store.read_latest_diagnosis_rows(
        limit=max(32, DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT)
    )
    canonical = diagnosis_review.derive_current_episode(
        normalized_rows, furnace_id="BF"
    )
    if not canonical.get("available"):
        raise RuntimeError("current diagnosis is unavailable")
    evidence_rows = review_store.read_diagnosis_evidence_rows(
        diagnosis_ts=canonical["diagnosis_ts"],
        variables=diag_ai_evidence.SENSOR_VARIABLES,
        window_minutes=60,
        baseline_days=30,
    )
    variable_stats = diag_ai_evidence.build_variable_stats(
        evidence_rows.get("sensor_rows") or [],
        evidence_rows.get("baseline_rows") or [],
        canonical["diagnosis_ts"],
    )
    feature_snapshot = canonical.get("feature_snapshot")
    feature_snapshot = feature_snapshot if isinstance(feature_snapshot, Mapping) else {}
    rule_drivers = diag_ai_evidence.build_rule_driver_context(
        feature_snapshot, variable_stats
    )
    selected_driver_rows = [
        dict(item)
        for item in (rule_drivers.get(target_label) or [])
        if isinstance(item, Mapping)
    ][:8]
    core_rows = diag_ai_evidence.build_core_variable_evidence(
        variable_stats, selected_driver_rows
    )
    context = diagnosis_model_review.normalize_five_minute_context(
        canonical,
        [],
        bucket_minutes=DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES,
    )
    return {
        "schema_version": "diagnosis_core_evidence.v1",
        "state": "available",
        "target_label": target_label,
        "target_display_name": diagnosis_model_review.DISPLAY_NAMES[target_label],
        "diagnosis_ts": context.get("diagnosis_ts"),
        "bucket_ts": context.get("bucket_ts"),
        "bucket_minutes": context.get("bucket_minutes"),
        "rule_score": float((context.get("scores") or {}).get(target_label, 0.0)),
        "core_variable_evidence": core_rows,
        "core_variable_count": len(diag_ai_evidence.CORE_EVIDENCE_VARIABLES),
        "core_series_window_minutes": 60,
        "read_only": True,
    }


def five_minute_analysis_store() -> diagnosis_review.DiagnosisReviewStore:
    """Return the loopback-only PostgreSQL store used by diagnosis review features."""
    store = diagnosis_review.DiagnosisReviewStore()
    store.ensure_schema()
    return store


def _analysis_retry_due(row: dict[str, Any] | None) -> bool:
    if not row or row.get("generation_state") != "failed":
        return True
    updated = row.get("updated_at")
    if not isinstance(updated, datetime):
        return True
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - updated).total_seconds() >= DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS


def run_five_minute_analysis_once(
    *, target_label: str | None = None, retry_failed: bool = False
) -> dict[str, Any]:
    """Generate only one selected condition for the latest diagnosis bucket."""
    if not DIAGNOSIS_AI_ANALYSIS_ENABLED:
        return {"state": "disabled"}
    if not _DIAGNOSIS_AI_ANALYSIS_LOCK.acquire(blocking=False):
        return {"state": "reasoning", "queued": False}
    context: dict[str, Any] | None = None
    store: diagnosis_review.DiagnosisReviewStore | None = None
    try:
        context = current_five_minute_analysis_context(target_label)
        label = str(target_label or context.get("main_label") or "normal")
        prompt_version = diagnosis_model_review.single_condition_prompt_version(label)
        store = five_minute_analysis_store()
        existing = store.get_ai_analysis(
            furnace_id=str(context["furnace_id"]),
            bucket_ts=context["bucket_ts"],
            prompt_version=prompt_version,
        )
        if existing and existing.get("generation_state") == "completed":
            return existing
        if existing and existing.get("generation_state") == "failed":
            if not retry_failed and not _analysis_retry_due(existing):
                return existing
        internal_model = normalize_model(None)
        snapshot_hash = diagnosis_model_review.five_minute_analysis_key(
            context, internal_model, target_label=label
        )
        store.begin_ai_analysis(
            context,
            prompt_version=prompt_version,
            snapshot_hash=snapshot_hash,
            model_public_name=PUBLIC_MODEL_NAME,
        )
        messages = diagnosis_model_review.build_single_condition_analysis_messages(
            context, label
        )
        answer = call_ollama_chat(messages, temperature=0.05, max_tokens=1200)
        parsed = diagnosis_model_review.parse_single_condition_analysis_payload(
            answer, label, context
        )
        completed = diagnosis_model_review.build_completed_five_minute_analysis(
            context,
            {"analyses": [parsed["analysis"]]},
            public_model_name=PUBLIC_MODEL_NAME,
            snapshot_hash=snapshot_hash,
        )
        store.complete_ai_analysis(
            furnace_id=str(context["furnace_id"]),
            bucket_ts=context["bucket_ts"],
            prompt_version=prompt_version,
            snapshot_hash=snapshot_hash,
            analyses=completed["analyses"],
        )
        return completed
    except Exception as exc:  # noqa: BLE001
        if context is not None and store is not None:
            try:
                store.fail_ai_analysis(
                    furnace_id=str(context["furnace_id"]),
                    bucket_ts=context["bucket_ts"],
                    prompt_version=diagnosis_model_review.single_condition_prompt_version(
                        str(target_label or context.get("main_label") or "normal")
                    ),
                    error_code=type(exc).__name__,
                )
            except Exception:
                pass
        print(
            "five-minute diagnosis AI analysis failed: "
            + sanitize_model_exposure(type(exc).__name__)
        )
        return {"state": "failed", "error_type": type(exc).__name__}
    finally:
        _DIAGNOSIS_AI_ANALYSIS_LOCK.release()


def queue_five_minute_analysis(
    *, target_label: str | None = None, retry_failed: bool = False
) -> bool:
    """Queue a non-blocking generation attempt; duplicate work is lock-deduplicated."""
    if not DIAGNOSIS_AI_ANALYSIS_ENABLED or _DIAGNOSIS_AI_ANALYSIS_LOCK.locked():
        return False
    thread = threading.Thread(
        target=run_five_minute_analysis_once,
        kwargs={"target_label": target_label, "retry_failed": retry_failed},
        name=f"diagnosis-ai-analysis-{target_label or 'main'}",
        daemon=True,
    )
    thread.start()
    return True


def _five_minute_analysis_scheduler() -> None:
    _DIAGNOSIS_AI_ANALYSIS_STOP.wait(3.0)
    while not _DIAGNOSIS_AI_ANALYSIS_STOP.is_set():
        run_five_minute_analysis_once()
        _DIAGNOSIS_AI_ANALYSIS_STOP.wait(DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS)


def start_five_minute_analysis_scheduler() -> None:
    """Start the single daemon scheduler after the proxy startup checks pass."""
    global _DIAGNOSIS_AI_ANALYSIS_THREAD
    if not DIAGNOSIS_AI_ANALYSIS_ENABLED or not DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED:
        return
    if _DIAGNOSIS_AI_ANALYSIS_THREAD and _DIAGNOSIS_AI_ANALYSIS_THREAD.is_alive():
        return
    five_minute_analysis_store()
    _DIAGNOSIS_AI_ANALYSIS_THREAD = threading.Thread(
        target=_five_minute_analysis_scheduler,
        name="diagnosis-ai-analysis-scheduler",
        daemon=True,
    )
    _DIAGNOSIS_AI_ANALYSIS_THREAD.start()


def public_five_minute_analysis(
    context: Mapping[str, Any],
    row: Mapping[str, Any] | None,
    target_label: str,
) -> dict[str, Any]:
    """Build a browser-safe response for one selected furnace condition."""
    state = str((row or {}).get("generation_state") or "preparing")
    analyses = (row or {}).get("analyses")
    analyses = analyses if isinstance(analyses, list) else []
    selected = next(
        (item for item in analyses if isinstance(item, Mapping) and item.get("label") == target_label),
        None,
    )
    if state == "completed" and selected is None:
        state = "failed"
    variable_stats = context.get("variable_stats")
    variable_stats = variable_stats if isinstance(variable_stats, Mapping) else {}
    rule_drivers = context.get("rule_drivers")
    rule_drivers = rule_drivers if isinstance(rule_drivers, Mapping) else {}
    selected_driver_rows = [
        dict(item)
        for item in (rule_drivers.get(target_label) or [])
        if isinstance(item, Mapping)
    ][:8]
    core_variable_evidence = diag_ai_evidence.build_core_variable_evidence(
        variable_stats, selected_driver_rows
    )
    return {
        "schema_version": diagnosis_model_review.FIVE_MINUTE_SCHEMA_VERSION,
        "state": state,
        "target_label": target_label,
        "target_display_name": diagnosis_model_review.DISPLAY_NAMES[target_label],
        "diagnosis_ts": context.get("diagnosis_ts"),
        "bucket_ts": context.get("bucket_ts"),
        "bucket_minutes": context.get("bucket_minutes"),
        "main_label": context.get("main_label"),
        "main_display_name": diagnosis_model_review.DISPLAY_NAMES.get(
            str(context.get("main_label") or "normal"), "正常顺行"
        ),
        "rule_score": float((context.get("scores") or {}).get(target_label, 0.0)),
        "analysis": dict(selected) if selected else None,
        # Trusted sensor evidence is available before model prose completes.
        # This keeps operator curves usable during preparing/failed states.
        "core_variable_evidence": core_variable_evidence,
        "core_variable_count": len(diag_ai_evidence.CORE_EVIDENCE_VARIABLES),
        "core_series_window_minutes": 60,
        "attempt_count": int((row or {}).get("attempt_count") or 0),
        "created_at": (row or {}).get("completed_at") or (row or {}).get("updated_at"),
        "retry_after_seconds": int(DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS),
        "read_only": True,
        "score_semantics": "规则符合度与模型证据吻合度，均不是概率",
    }


# OPS-8093-HTTP-STATIC-STABILITY-20260806-R1
class BlastFurnaceThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded server sized for browser cold-start resource bursts."""

    request_queue_size = max(32, int(os.environ.get("BF_8093_HTTP_REQUEST_QUEUE_SIZE", "128")))
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True


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
        if parsed.path == "/api/qa/mcp/health":
            self.handle_qa_mcp_health()
            return
        if parsed.path == "/api/heat-performance-quality":
            self.handle_heat_performance_quality(parsed.query)
            return
        if parsed.path == "/api/hcz-upward-rule":
            self.handle_hcz_upward_rule()
            return
        if parsed.path == "/api/hcz-rule-sensitivity":
            self.handle_hcz_rule_sensitivity(parsed.query)
            return
        if parsed.path == "/api/thermal-trend":
            self.handle_thermal_trend()
            return
        if parsed.path == "/api/si-v20/status":
            self.handle_si_v20_status(parsed.query)
            return
        if parsed.path == "/api/si-v20/history":
            self.handle_si_v20_history(parsed.query)
            return
        if parsed.path == "/api/si-v20/hourly-history":
            self.handle_si_v20_hourly_history(parsed.query)
            return
        if parsed.path == "/api/si-v20/strict-hourly/status":
            self.handle_si_v20_strict_hourly_status()
            return
        if parsed.path == "/api/si-v20/strict-hourly/history":
            self.handle_si_v20_strict_hourly_history(parsed.query)
            return
        if parsed.path == "/api/si-v20/hourly-table":
            self.handle_si_v20_hourly_table(parsed.query)
            return
        if parsed.path == "/api/si-v20/schedule":
            self.handle_si_v20_schedule_status()
            return
        if parsed.path == "/api/si-v20/scheduled-history":
            self.handle_si_v20_scheduled_history(parsed.query)
            return
        if parsed.path == "/api/si-v20/data-readiness":
            self.handle_si_v20_data_readiness(parsed.query)
            return
        if parsed.path == "/api/si-v20/prediction-detail":
            self.handle_si_v20_prediction_detail(parsed.query)
            return
        if parsed.path == "/api/auth/status":
            self.handle_auth_status()
            return
        if parsed.path == "/api/diagnosis-review-context":
            self.handle_diagnosis_review_context(parsed.query)
            return
        if parsed.path == "/api/diagnosis-ai-analysis":
            self.handle_diagnosis_ai_analysis_get(parsed.query)
            return
        if parsed.path == "/api/diagnosis-core-evidence":
            self.handle_diagnosis_core_evidence_get(parsed.query)
            return
        if parsed.path == "/api/diagnosis-reviews":
            self.handle_diagnosis_reviews_get(parsed.query)
            return
        if parsed.path == "/api/diagnosis-manual-scores":
            self.handle_diagnosis_manual_scores_get(parsed.query)
            return
        if parsed.path == "/api/furnace-rules/latest":
            self.handle_furnace_rules_latest()
            return
        if parsed.path.startswith("/api/furnace-rules/") and parsed.path.endswith("/explanation-context"):
            self.handle_furnace_rule_explanation_context(unquote(parsed.path).split("/")[3], parsed.query)
            return
        if parsed.path.startswith("/api/furnace-rules/") and parsed.path.endswith("/detail"):
            self.handle_furnace_rule_detail(unquote(parsed.path).split("/")[3])
            return
        if parsed.path.startswith("/api/furnace-rules/") and parsed.path.endswith("/trends"):
            self.handle_furnace_rule_trends(unquote(parsed.path).split("/")[3])
            return
        if parsed.path.startswith("/api/admin/furnace-rules/evaluations/"):
            self.handle_admin_furnace_rule_detail(unquote(parsed.path))
            return
        if parsed.path == "/api/admin/furnace-rules/latest-full":
            self.handle_admin_furnace_rules_latest_full(parsed.query)
            return
        if parsed.path == "/api/admin/furnace-rules/history":
            self.handle_admin_furnace_rules_history(parsed.query)
            return
        if parsed.path == "/api/admin/furnace-rules/config":
            self.handle_admin_abc_config_get()
            return
        if parsed.path == "/api/admin/thermal-trend/config":
            self.handle_admin_thermal_trend_config_get()
            return
        if parsed.path == "/api/qa/bootstrap":
            self.handle_qa_bootstrap(parsed.query)
            return
        if parsed.path == "/api/qa/conversation":
            self.handle_qa_conversation(parsed.query)
            return
        if parsed.path == "/api/qa/conversations":
            self.handle_qa_conversations_get(parsed.query)
            return
        if parsed.path == "/api/qa/projects":
            self.handle_qa_projects_get(parsed.query)
            return
        if parsed.path == "/api/qa/knowledge/search":
            self.handle_qa_knowledge_search(parsed.query)
            return
        if parsed.path == "/api/qa/knowledge/chunk":
            self.handle_qa_knowledge_chunk(parsed.query)
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
        self.serve_static(parsed.path, parsed.query)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/qa/") and not self.qa_write_request_allowed():
            return
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
        if parsed.path == "/api/diagnosis/model-review":
            self.handle_diagnosis_model_review_post()
            return
        if parsed.path == "/api/diagnosis-ai-analysis/retry":
            self.handle_diagnosis_ai_analysis_retry()
            return
        if parsed.path == "/api/si-v20/predict":
            self.handle_si_v20_predict()
            return
        if parsed.path == "/api/si-v20/hourly-predict":
            self.handle_si_v20_hourly_predict()
            return
        if parsed.path == "/api/si-v20/strict-hourly/predict":
            self.handle_si_v20_strict_hourly_predict()
            return
        if parsed.path == "/api/si-v20/strict-hourly/dispatch":
            self.handle_si_v20_strict_hourly_dispatch()
            return
        if parsed.path == "/api/si-v20/replay":
            self.handle_si_v20_replay()
            return
        if parsed.path == "/api/si-v20/schedule/configure":
            self.handle_si_v20_schedule_configure()
            return
        if parsed.path == "/api/si-v20/schedule/dispatch":
            self.handle_si_v20_schedule_dispatch()
            return
        if parsed.path == "/api/si-v20/scheduled-replay":
            self.handle_si_v20_scheduled_replay()
            return
        if parsed.path == "/api/admin/furnace-rules/config/publish":
            self.handle_admin_abc_config_publish()
            return
        if parsed.path == "/api/admin/thermal-trend/config/publish":
            self.handle_admin_thermal_trend_config_publish()
            return
        if parsed.path == "/api/thermal-trend/condition":
            self.handle_thermal_trend_condition_publish()
            return
        if parsed.path == "/api/qa/conversations":
            self.handle_qa_new_conversation()
            return
        if parsed.path == "/api/qa/contextual-conversations":
            self.handle_qa_contextual_conversation()
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

    def qa_write_request_allowed(self) -> bool:
        """Enforce JSON and same-origin CSRF boundaries for every QA mutation."""
        content_type = str(self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_json({"ok": False, "error": "qa_application_json_required"}, status=415)
            return False
        origin = str(self.headers.get("Origin") or "").strip()
        host = str(self.headers.get("Host") or "").strip().lower()
        if origin:
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme not in {"http", "https"} or parsed_origin.netloc.lower() != host:
                self.send_json({"ok": False, "error": "qa_same_origin_required"}, status=403)
                return False
            return True
        client_ip = str((getattr(self, "client_address", None) or ("",))[0])
        controlled = str(self.headers.get("X-BF-Controlled-Client") or "") == "1"
        allow_loopback = _env_enabled("BF_QA_ALLOW_ORIGINLESS_LOOPBACK_CONTROLLED", default=True)
        if allow_loopback and controlled and client_ip in {"127.0.0.1", "::1"}:
            return True
        self.send_json({"ok": False, "error": "qa_origin_required"}, status=403)
        return False

    def handle_diagnosis_model_review_post(self) -> None:
        """Generate or return a cached, read-only model review for one diagnosis score.

        Corresponding requirement:
        REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805.
        """
        if not DIAGNOSIS_MODEL_REVIEW_ENABLED:
            self.send_json(
                {
                    "ok": False,
                    "model_review": {
                        "schema_version": diagnosis_model_review.SCHEMA_VERSION,
                        "state": "failed",
                        "message": "后台高炉大模型复核未启用",
                        "read_only": True,
                    },
                },
                status=503,
            )
            return
        try:
            body = self.read_json_body()
            context = diagnosis_model_review.normalize_review_context(body)
            internal_model = normalize_model(None)
            cache_key = diagnosis_model_review.review_cache_key(context, internal_model)
            if not bool(body.get("force")):
                cached = _DIAGNOSIS_MODEL_REVIEW_CACHE.get(cache_key)
                if cached:
                    self.send_json({"ok": True, "model_review": cached})
                    return

            messages = diagnosis_model_review.build_review_messages(context)
            answer = call_ollama_chat(messages, temperature=0.05, max_tokens=1200)
            parsed = diagnosis_model_review.parse_model_payload(answer, context)
            review = diagnosis_model_review.build_completed_review(
                context,
                parsed,
                public_model_name=PUBLIC_MODEL_NAME,
                snapshot_hash=cache_key,
            )
            _DIAGNOSIS_MODEL_REVIEW_CACHE.put(cache_key, review)
            self.send_json({"ok": True, "model_review": review})
        except diagnosis_model_review.ModelReviewValidationError as exc:
            self.send_json(
                {
                    "ok": False,
                    "model_review": {
                        "schema_version": diagnosis_model_review.SCHEMA_VERSION,
                        "state": "failed",
                        "message": str(exc),
                        "read_only": True,
                    },
                },
                status=400,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "model_review": {
                        "schema_version": diagnosis_model_review.SCHEMA_VERSION,
                        "state": "failed",
                        "message": "后台高炉大模型复核暂不可用，请稍后重试",
                        "error_type": type(exc).__name__,
                        "read_only": True,
                    },
                },
                status=502,
            )

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

    def qa_guest_room_key(self) -> str:
        """Resolve a stable room key; configured value wins over the current Host."""
        configured = QA_GUEST_ROOM_KEY.strip()
        if configured:
            return configured
        host = str(self.headers.get("Host") or "default").strip().lower()
        return host or "default"

    def qa_access_identity(self) -> dict[str, Any] | None:
        """Use a private operator identity when logged in, else the shared guest room."""
        session = self.current_review_session()
        role = str((session or {}).get("role") or "").lower()
        subject = str((session or {}).get("sub") or "").strip()
        if subject and any(token in role for token in ("operator", "admin", "操作", "管理", "炉长")):
            return {**session, "access_mode": "authenticated"}
        if not QA_GUEST_ENABLED:
            return None
        return shared_guest_identity(self.qa_guest_room_key())

    def qa_session_required(self) -> dict[str, Any] | None:
        session = self.qa_access_identity()
        if session is None:
            self.send_json({"ok": False, "error": "qa_session_required"}, status=403)
            return None
        return session

    def qa_operator_session_required(self) -> dict[str, Any] | None:
        """Keep projects, reports and contextual assistants operator-only."""
        session = self.current_review_session()
        role = str((session or {}).get("role") or "").lower()
        subject = str((session or {}).get("sub") or "").strip()
        if not subject or not any(token in role for token in ("operator", "admin", "操作", "管理", "炉长")):
            self.send_json({"ok": False, "error": "qa_operator_session_required"}, status=403)
            return None
        return {**session, "access_mode": "authenticated"}

    def qa_conversation_owned(self, conn: Any, conversation_id: str, session: Mapping[str, Any]) -> bool:
        row = conn.execute(
            "SELECT owner_subject FROM qa_conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
        if not row or str(row["owner_subject"] or "") != str(session.get("sub") or ""):
            self.send_json({"ok": False, "error": "conversation_not_found"}, status=404)
            return False
        return True

    def qa_chat_conversation_id(
        self,
        conn: Any,
        requested_id: str,
        session: Mapping[str, Any],
    ) -> str | None:
        """Bind guests to the shared room while preserving private owner checks."""
        if session.get("access_mode") == "guest_shared":
            conversation = ensure_shared_guest_conversation(conn, session)
            return str(conversation["id"])
        if not requested_id:
            self.send_json({"ok": False, "error": "conversation_id_required"}, status=400)
            return None
        if not self.qa_conversation_owned(conn, requested_id, session):
            return None
        return requested_id

    def _abc_connection(self):
        return _assistant_raw_pg_connect()

    def _abc_admin_required(self) -> bool:
        session = self.current_review_session()
        role = str((session or {}).get("role") or "")
        if not session or not ("admin" in role.lower() or "管理" in role):
            self.send_json({"ok": False, "error": "admin_required"}, status=403)
            return False
        return True

    def _same_origin_action_required(self, action: str) -> bool:
        origin = str(self.headers.get("Origin") or "").strip()
        host = str(self.headers.get("Host") or "").strip()
        parsed_origin = urlparse(origin) if origin else None
        if not parsed_origin or parsed_origin.netloc != host or parsed_origin.scheme not in {"http", "https"}:
            self.send_json({"ok": False, "error": "same_origin_required"}, status=403)
            return False
        if self.headers.get("X-BF-Admin-Action") != action:
            self.send_json({"ok": False, "error": "admin_action_header_required"}, status=403)
            return False
        return True

    def _abc_admin_write_required(self, action: str = "publish-abc-rule-config") -> bool:
        if not self._abc_admin_required():
            return False
        return self._same_origin_action_required(action)

    def _abc_operator_write_required(self, action: str) -> bool:
        session = self.current_review_session()
        role = str((session or {}).get("role") or "").lower()
        if not session or not any(token in role for token in ("operator", "admin", "操作", "管理", "炉长")):
            self.send_json({"ok": False, "error": "operator_required"}, status=403)
            return False
        return self._same_origin_action_required(action)

    def handle_furnace_rules_latest(self) -> None:
        try:
            with self._abc_connection() as conn:
                batch = conn.execute(
                    "SELECT id, evaluation_ts, catalog_version, config_version, public_bundle FROM bf_sensor.abc_rule_evaluation_batches ORDER BY evaluation_ts DESC, id DESC LIMIT 1"
                ).fetchone()
            if not batch:
                self.send_json({"ok": True, "schema_version": "abc_rule_bundle.v1", "rules": [], "alerts": [], "state": "needs_data"})
                return
            data = dict(batch) if isinstance(batch, Mapping) else {"id": batch[0], "evaluation_ts": batch[1], "catalog_version": batch[2], "config_version": batch[3], "public_bundle": batch[4]}
            bundle = data.get("public_bundle") or {}
            if isinstance(bundle, str):
                bundle = json.loads(bundle)
            bundle = diagnosis_review.abc_public_bundle_for_display(
                bundle if isinstance(bundle, Mapping) else {}, data.get("evaluation_ts")
            )
            self.send_json({"ok": True, "evaluation_id": data.get("id"), "evaluation_ts": data.get("evaluation_ts"), "catalog_version": data.get("catalog_version"), "config_version": data.get("config_version"), **bundle})
        except Exception as exc:
            self.send_json({"ok": False, "state": "needs_data", "error_type": type(exc).__name__}, status=503)

    def _authoritative_abc_context(self, rule_id: str, evaluation_id: int) -> dict[str, Any] | None:
        """Reload identifiers from ABC tables, then format after releasing the DB lease."""
        with self._abc_connection() as conn:
            evaluation = abc_rule_assistant_analysis.load_authoritative_evaluation(
                conn,
                rule_id=rule_id,
                evaluation_id=evaluation_id,
            )
        if evaluation is None:
            return None
        artifacts = abc_rule_assistant_analysis.build_context_artifacts(
            evaluation,
            spec=RULE_BY_ID.get(rule_id),
        )
        artifacts["evaluation"] = evaluation
        artifacts["context_summary"] = abc_rule_assistant_analysis.context_summary(
            artifacts["operator_explanation"]
        )
        return artifacts

    def _persist_abc_context(self, rule_id: str, evaluation_id: int, artifacts: Mapping[str, Any]) -> int:
        """Persist deterministic context/cache records in a short assistant-DB transaction."""
        ts = iso_now()
        context_hash = str(artifacts["context_hash"])
        assistant_context_json = abc_rule_assistant_analysis.canonical_json(artifacts["assistant_context"])
        assistant_context_bytes = len(assistant_context_json.encode("utf-8"))
        if assistant_context_bytes > ABC_RULE_ASSISTANT_CONTEXT_MAX_BYTES:
            raise ValueError("ABC explanation context exceeds configured byte limit")
        prompt_context = abc_rule_assistant_analysis.bounded_prompt_context(
            artifacts["assistant_context"],
            max_bytes=ABC_RULE_ASSISTANT_PROMPT_CONTEXT_MAX_BYTES,
        )
        prompt_context_json = abc_rule_assistant_analysis.canonical_json(prompt_context)
        operator_json = abc_rule_assistant_analysis.canonical_json(artifacts["operator_explanation"])
        summary_json = abc_rule_assistant_analysis.canonical_json(artifacts["context_summary"])
        with db_connect() as conn:
            conn.execute(
                """
                INSERT INTO qa_context_snapshots(
                    context_hash, source_type, source_id, source_version,
                    context_json, context_summary_json, context_type, context_key,
                    schema_version, furnace_id, source_ref_id, evaluation_id,
                    source_ts, payload_json, payload_size_bytes, created_at
                ) VALUES (?, 'abc_rule', ?, ?, ?, ?, 'abc_rule_explanation', ?,
                          ?, 'GL02', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(context_hash) DO NOTHING
                """,
                (
                    context_hash,
                    rule_id,
                    str(evaluation_id),
                    assistant_context_json,
                    summary_json,
                    f"abc_rule:{rule_id}:{evaluation_id}",
                    str(artifacts["operator_explanation"].get("schema_version") or "abc_rule_explanation_context.v1"),
                    rule_id,
                    evaluation_id,
                    artifacts["context_summary"].get("evaluation_ts"),
                    prompt_context_json,
                    len(prompt_context_json.encode("utf-8")),
                    ts,
                ),
            )
            snapshot = conn.execute(
                "SELECT id FROM qa_context_snapshots WHERE context_hash = ?",
                (context_hash,),
            ).fetchone()
            if not snapshot:
                raise RuntimeError("context snapshot persistence failed")
            snapshot_id = int(snapshot["id"])
            conn.execute(
                """
                INSERT INTO abc_rule_ai_explanations(
                    context_snapshot_id, rule_id, evaluation_id, context_hash,
                    operator_explanation_json, assistant_context_json,
                    prompt_version, model_name, state, generation_state,
                    attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'abc_rule_explanation.v1', '',
                          'context_ready', 'context_ready', 0, ?, ?)
                ON CONFLICT(context_snapshot_id, prompt_version, model_name) DO UPDATE SET
                    operator_explanation_json = EXCLUDED.operator_explanation_json,
                    assistant_context_json = EXCLUDED.assistant_context_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (snapshot_id, rule_id, evaluation_id, context_hash, operator_json, assistant_context_json, ts, ts),
            )
            conn.commit()
        return snapshot_id

    def handle_furnace_rule_explanation_context(self, rule_id: str, query: str) -> None:
        """Return the deterministic operator explanation for an exact ABC evaluation."""
        request_id = f"abc_ctx_{uuid.uuid4().hex}"
        def fail(status: int, code: str, message: str, retryable: bool = False) -> None:
            self.send_json(
                {"ok": False, "error_code": code, "retryable": retryable, "request_id": request_id, "message": message},
                status=status,
                headers={"Cache-Control": "no-store"},
            )

        if rule_id not in RULE_BY_ID:
            fail(400, "invalid_rule_id", "规则编号无效。")
            return
        # The deterministic explanation is the read-only expansion of the
        # already public ABC33 latest/detail contract.  Keep model-backed
        # conversation creation protected separately; otherwise the public
        # optimization page cannot explain the same rule it is allowed to show.
        raw_id = (parse_qs(query).get("evaluation_id") or [""])[0]
        try:
            evaluation_id = int(raw_id)
        except (TypeError, ValueError):
            fail(400, "invalid_evaluation_id", "evaluation_id 必须为正整数。")
            return
        try:
            artifacts = self._authoritative_abc_context(rule_id, evaluation_id)
            if artifacts is None:
                with self._abc_connection() as conn:
                    any_rule = conn.execute(
                        "SELECT rule_id FROM bf_sensor.abc_rule_evaluation_items WHERE batch_id=%s LIMIT 1",
                        (evaluation_id,),
                    ).fetchone()
                if any_rule:
                    fail(409, "evaluation_rule_mismatch", "该评估批次不包含请求的规则。")
                else:
                    fail(404, "evaluation_not_found", "未找到指定评估批次。")
                return
            source_ts = artifacts["context_summary"].get("evaluation_ts")
            parsed_ts = source_ts if isinstance(source_ts, datetime) else parse_iso(str(source_ts or ""))
            age_seconds = (now_utc() - parsed_ts.astimezone(timezone.utc)).total_seconds() if parsed_ts else None
            stale = age_seconds is None or age_seconds > 1200 or age_seconds < -60
            self.send_json(
                {
                    "ok": True,
                    "request_id": request_id,
                    "rule_id": rule_id,
                    "evaluation_id": evaluation_id,
                    "context_hash": artifacts["context_hash"],
                    "context_summary": artifacts["context_summary"],
                    "operator_explanation": artifacts["operator_explanation"],
                    "assistant_context_ref": {
                        "id": artifacts["assistant_context"].get("context_id"),
                        "hash": artifacts["context_hash"],
                        "version": artifacts["assistant_context"].get("schema_version"),
                    },
                    "stale": stale,
                    "evaluation_age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
                    "stale_reason": (
                        "future_source_time" if age_seconds is not None and age_seconds < -60
                        else "older_than_20_minutes" if age_seconds is None or age_seconds > 1200
                        else None
                    ),
                },
                headers={"Cache-Control": "no-store"},
            )
        except (KeyError, TypeError, ValueError) as exc:
            fail(422, "context_incomplete", f"权威评估上下文不完整：{type(exc).__name__}")
        except Exception as exc:
            fail(503, "database_unavailable", f"规则上下文暂不可用：{type(exc).__name__}", retryable=True)

    def handle_furnace_rule_detail(self, rule_id: str) -> None:
        if rule_id not in RULE_BY_ID:
            self.send_json({"ok": False, "error": "unknown_rule"}, status=404)
            return
        try:
            with self._abc_connection() as conn:
                row = conn.execute(
                    """
                    SELECT i.batch_id, b.evaluation_ts, i.public_detail,
                           i.category, i.score, i.status, i.weights, i.contributions
                    FROM bf_sensor.abc_rule_evaluation_items i
                    JOIN bf_sensor.abc_rule_evaluation_batches b ON b.id=i.batch_id
                    WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC, b.id DESC LIMIT 1
                    """, (rule_id,)
                ).fetchone()
                if row:
                    raw_ts = row["evaluation_ts"] if isinstance(row, Mapping) else row[1]
                    sensor_review = build_public_review(conn, rule_id, raw_ts)
                else:
                    sensor_review = None
            if not row:
                self.send_json({"ok": True, "state": "needs_data", "rule_id": rule_id})
                return
            data = dict(row) if isinstance(row, Mapping) else {
                "batch_id": row[0], "evaluation_ts": row[1], "public_detail": row[2],
                "category": row[3], "score": row[4], "status": row[5],
                "weights": row[6], "contributions": row[7],
            }
            detail = public_rule(data.get("public_detail") or {"rule_id": rule_id})
            display_bundle = diagnosis_review.abc_public_bundle_for_display(
                {"rules": [detail], "alerts": []}, data.get("evaluation_ts")
            )
            detail = (display_bundle.get("rules") or [{"rule_id": rule_id}])[0]
            explanation = build_score_explanation(
                category=data.get("category") or detail.get("category"),
                score=data.get("score") if data.get("score") is not None else detail.get("score"),
                status=data.get("status") or detail.get("status"),
                weights=data.get("weights"),
                contributions=data.get("contributions"),
                label_for=lambda term: abc_term_semantics(term).get("label", ""),
            )
            if explanation is not None:
                detail["score_explanation"] = explanation
            self.send_json({
                "ok": True,
                "schema_version": "furnace_rule_detail.v2",
                "evaluation_id": data.get("batch_id"),
                "evaluation_ts": data.get("evaluation_ts"),
                "batch_state": display_bundle.get("batch_state"),
                "evaluation_age_seconds": display_bundle.get("evaluation_age_seconds"),
                "detail": detail,
                "sensor_review": sensor_review,
            })
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_furnace_rule_trends(self, rule_id: str) -> None:
        if rule_id not in RULE_BY_ID:
            self.send_json({"ok": False, "error": "unknown_rule"}, status=404)
            return
        try:
            with self._abc_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT b.evaluation_ts, i.score, i.confidence, i.status
                    FROM bf_sensor.abc_rule_evaluation_items i
                    JOIN bf_sensor.abc_rule_evaluation_batches b ON b.id=i.batch_id
                    WHERE i.rule_id=%s ORDER BY b.evaluation_ts DESC, b.id DESC LIMIT 72
                    """, (rule_id,)
                ).fetchall()
            self.send_json({"ok": True, "schema_version": "furnace_rule_trends.v1", "series_scope": "historical", "rule_id": rule_id, "points": [dict(row) if isinstance(row, Mapping) else {"evaluation_ts": row[0], "score": row[1], "confidence": row[2], "status": row[3]} for row in reversed(rows)]})
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_admin_furnace_rule_detail(self, path: str) -> None:
        if not self._abc_admin_required():
            return
        parts = path.split("/")
        if len(parts) < 7:
            self.send_json({"ok": False, "error": "invalid_path"}, status=400)
            return
        try:
            evaluation_id = int(parts[5])
        except ValueError:
            self.send_json({"ok": False, "error": "invalid_evaluation_id"}, status=400)
            return
        rule_id = parts[6]
        try:
            with self._abc_connection() as conn:
                row = conn.execute("SELECT * FROM bf_sensor.abc_rule_evaluation_items WHERE batch_id=%s AND rule_id=%s", (evaluation_id, rule_id)).fetchone()
            if not row:
                self.send_json({"ok": False, "error": "not_found"}, status=404)
                return
            data = dict(row) if isinstance(row, Mapping) else {"rule_id": rule_id}
            self.send_json({"ok": True, "schema_version": "furnace_rule_admin_detail.v1", "evaluation": data}, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_admin_furnace_rules_history(self, query: str) -> None:
        if not self._abc_admin_required():
            return
        try:
            params = parse_qs(query)
            start = (params.get("start") or [None])[0]
            end = (params.get("end") or [None])[0]
            limit = min(576, max(1, int((params.get("limit") or [288])[0])))
            clauses = []
            values: list[Any] = []
            if start:
                clauses.append("evaluation_ts >= %s::timestamptz")
                values.append(start)
            if end:
                clauses.append("evaluation_ts <= %s::timestamptz")
                values.append(end)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            values.append(limit)
            with self._abc_connection() as conn:
                rows = conn.execute(
                    f"""SELECT id,evaluation_ts,catalog_version,config_version,
                               (SELECT count(*) FROM bf_sensor.abc_rule_evaluation_items i WHERE i.batch_id=b.id) AS rule_count
                        FROM bf_sensor.abc_rule_evaluation_batches b{where}
                        ORDER BY evaluation_ts DESC,id DESC LIMIT %s""",
                    tuple(values),
                ).fetchall()
            self.send_json({"ok": True, "schema_version": "abc_rule_admin_history.v1", "batches": [dict(row) for row in rows]}, headers={"Cache-Control": "no-store"})
        except (TypeError, ValueError):
            self.send_json({"ok": False, "error": "invalid_history_query"}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_admin_furnace_rules_latest_full(self, query: str = "") -> None:
        if not self._abc_admin_required():
            return
        try:
            params = parse_qs(query)
            requested_id = (params.get("evaluation_id") or [None])[0]
            with self._abc_connection() as conn:
                if requested_id:
                    batch = conn.execute(
                        "SELECT id,evaluation_ts,catalog_version,config_version FROM bf_sensor.abc_rule_evaluation_batches WHERE id=%s",
                        (int(requested_id),),
                    ).fetchone()
                else:
                    batch = conn.execute(
                        "SELECT id,evaluation_ts,catalog_version,config_version FROM bf_sensor.abc_rule_evaluation_batches ORDER BY evaluation_ts DESC,id DESC LIMIT 1"
                    ).fetchone()
                if not batch:
                    self.send_json({"ok": True, "schema_version": "abc_rule_admin_runtime.v1", "rules": [], "state": "needs_data"}, headers={"Cache-Control": "no-store"})
                    return
                rows = conn.execute(
                    """SELECT rule_id,category,display_name,score,confidence,status,weights,
                              normalized_values,contributions,missing_features
                       FROM bf_sensor.abc_rule_evaluation_items
                       WHERE batch_id=%s ORDER BY category,rule_id""",
                    (batch["id"],),
                ).fetchall()
            rules = []
            for raw in rows:
                item = dict(raw)
                contributions = []
                for value in item.get("contributions") or []:
                    term = str(value.get("feature_key") or "")
                    contributions.append({**value, "physical": abc_term_semantics(term)})
                item["contributions"] = contributions
                rules.append(item)
            self.send_json({
                "ok": True,
                "schema_version": "abc_rule_admin_runtime.v1",
                "evaluation_id": batch["id"],
                "evaluation_ts": batch["evaluation_ts"],
                "catalog_version": batch["catalog_version"],
                "config_version": batch["config_version"],
                "rules": rules,
            }, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_admin_abc_config_get(self) -> None:
        if not self._abc_admin_required():
            return
        try:
            config = load_abc_config(ABC_CONFIG_PATH)
            config.pop("config_path", None)
            config.pop("config_hash", None)
            catalog = []
            for rule_id in sorted(RULE_BY_ID):
                spec = RULE_BY_ID[rule_id]
                overrides = ((config.get("rules") or {}).get(rule_id) or {}).get("weight_overrides") or {}
                terms = []
                for term, default_weight in spec.terms.items():
                    terms.append({
                        "feature_key": term,
                        "default_weight": float(default_weight),
                        "effective_weight": float(overrides.get(term, default_weight)),
                        "physical": abc_term_semantics(term),
                    })
                catalog.append({"rule_id": rule_id, "category": spec.category, "display_name": spec.display_name, "direction": spec.direction, "terms": terms})
            self.send_json({"ok": True, "schema_version": "abc_rule_config_admin.v2", "config": config, "catalog": catalog}, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_admin_abc_config_publish(self) -> None:
        if not self._abc_admin_write_required():
            return
        try:
            body = self.read_json_body()
            config = dict(body.get("config")) if isinstance(body.get("config"), Mapping) else None
            if config is not None:
                for key in ("config_hash", "published_by", "change_reason"):
                    config.pop(key, None)
            reason = str(body.get("reason") or "").strip()
            session = self.current_review_session() or {}
            actor = str(session.get("sub") or "").strip()
            if config is None or not reason or not actor:
                self.send_json({"ok": False, "error": "config_reason_and_admin_are_required"}, status=400)
                return
            result = publish_abc_config(config, ABC_CONFIG_PATH, reason=reason, actor=actor)
            self.send_json({"ok": True, "schema_version": "abc_rule_config_publish.v1", "published": result}, headers={"Cache-Control": "no-store"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_thermal_trend(self) -> None:
        """Return the public, advisory-only two-half-hour trend assessment."""
        try:
            abc_config = load_abc_config(ABC_CONFIG_PATH)
            burden_policy = ((abc_config.get("feature_thresholds") or {}).get("burden_rate") or {})
            payload = thermal_trend_rule.evaluate_latest(
                self.pg_connect,
                config_path=THERMAL_TREND_CONFIG_PATH,
                condition_path=THERMAL_TREND_CONDITION_PATH,
                burden_policy=burden_policy,
            )
            self.send_json(payload, headers={"Cache-Control": "no-store"})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=503, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            self.send_json({"ok": False, "error": "thermal_trend_unavailable", "error_type": type(exc).__name__}, status=503, headers={"Cache-Control": "no-store"})

    def handle_admin_thermal_trend_config_get(self) -> None:
        if not self._abc_admin_required():
            return
        try:
            config = thermal_trend_rule.load_config(THERMAL_TREND_CONFIG_PATH)
            for key in ("config_hash", "published_by", "change_reason", "published_at"):
                config.pop(key, None)
            self.send_json({"ok": True, "schema_version": "bf.thermal-trend.config.admin.v1", "config": config}, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_admin_thermal_trend_config_publish(self) -> None:
        if not self._abc_admin_write_required("publish-thermal-trend-config"):
            return
        try:
            body = self.read_json_body()
            config = dict(body.get("config")) if isinstance(body.get("config"), Mapping) else None
            reason = str(body.get("reason") or "").strip()
            session = self.current_review_session() or {}
            actor = str(session.get("sub") or "").strip()
            if config is None or not reason or not actor:
                self.send_json({"ok": False, "error": "config_reason_and_admin_are_required"}, status=400)
                return
            for key in ("config_hash", "published_by", "change_reason", "published_at"):
                config.pop(key, None)
            result = thermal_trend_rule.publish_config(config, THERMAL_TREND_CONFIG_PATH, reason=reason, actor=actor)
            self.send_json({"ok": True, "schema_version": "bf.thermal-trend.config.publish.v1", "published": result}, headers={"Cache-Control": "no-store"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_thermal_trend_condition_publish(self) -> None:
        if not self._abc_operator_write_required("confirm-thermal-trend-condition"):
            return
        try:
            body = self.read_json_body()
            session = self.current_review_session() or {}
            config = thermal_trend_rule.load_config(THERMAL_TREND_CONFIG_PATH)
            ttl = int((config.get("slag_iron_exception") or {}).get("confirmation_ttl_minutes") or 120)
            condition = thermal_trend_rule.write_condition(
                THERMAL_TREND_CONDITION_PATH,
                state=str(body.get("state") or "unknown"),
                actor=str(session.get("sub") or ""),
                role=str(session.get("role") or ""),
                ttl_minutes=ttl,
                reason=str(body.get("reason") or ""),
            )
            self.send_json({"ok": True, "schema_version": "bf.thermal-trend.condition.publish.v1", "condition": condition}, headers={"Cache-Control": "no-store"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def review_store(self) -> diagnosis_review.DiagnosisReviewStore:
        store = diagnosis_review.DiagnosisReviewStore()
        store.ensure_schema()
        return store

    def latest_review_diagnosis_rows(self) -> list[dict[str, Any]]:
        return diagnosis_review.DiagnosisReviewStore().read_latest_diagnosis_rows(limit=288)

    def latest_abc33_review_score(
        self, diagnosis_ts: Any, snapshot_id: Any, rule_id: str = "B4"
    ) -> dict[str, Any]:
        """Return the latest production-safe ABC33 rule aligned to a diagnosis snapshot."""
        return load_latest_abc33_review_score(diagnosis_ts, snapshot_id, rule_id)

    def canonical_review_context(self, params: dict[str, list[str]]) -> dict[str, Any]:
        fixture_label = (params.get("fixture") or [""])[0]
        fixture_case_id = (params.get("case_id") or ["default"])[0]
        if fixture_label:
            if not diagnosis_review.review_test_mode_enabled() or not diagnosis_review.client_is_loopback(self.client_address):
                raise PermissionError("测试场景只允许在本机测试模式使用")
            return diagnosis_review.build_fixture_context(fixture_label, fixture_case_id)
        context = diagnosis_review.derive_current_episode(self.latest_review_diagnosis_rows(), furnace_id="BF")
        if not context.get("available"):
            return context
        abc_snapshot = self.latest_abc33_review_score(
            context.get("diagnosis_ts"), context.get("snapshot_id"), "B4"
        )
        return diagnosis_review.apply_abc33_display_score(context, abc_snapshot)

    def handle_diagnosis_review_context(self, query: str) -> None:
        if not diagnosis_review.review_enabled():
            self.send_json({"ok": True, "enabled": False})
            return
        params = parse_qs(query)
        try:
            context = self.canonical_review_context(params)
            session = self.current_review_session()
            config = diagnosis_review.load_review_config(require_store=False)
            identity = diagnosis_review.submission_identity(session, config)
            reviewed = False
            review_storage = {"configured": False, "writable": False}
            try:
                store_config = diagnosis_review.load_review_config(require_store=True)
                review_storage["configured"] = store_config.store_configured
                store = self.review_store()
                if identity and context.get("episode_key"):
                    items = store.list_events(
                        episode_key=str(context["episode_key"]),
                        reviewer_username=str(identity.get("sub") or ""),
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
                    "username": identity.get("sub") if identity else None,
                    "role": identity.get("role") if identity else None,
                    "can_submit": bool(identity),
                    "login_required": config.require_login,
                    "identity_mode": identity.get("identity_mode") if identity else None,
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
        config = diagnosis_review.load_review_config(require_store=False)
        identity = diagnosis_review.submission_identity(session, config)
        if not identity and not session:
            self.send_json({"ok": False, "error": "请先登录"}, status=401)
            return
        if not identity:
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
            event, created = self.review_store().insert_event(canonical, review, identity)
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
                labels=tuple(
                    item.strip()
                    for item in (params.get("labels") or [""])[0].split(",")
                    if item.strip()
                ),
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
        config = diagnosis_review.load_review_config(require_store=False)
        identity = diagnosis_review.submission_identity(session, config)
        if not identity and not session:
            self.send_json({"ok": False, "error": "请先登录"}, status=401)
            return
        if not identity:
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
            event, created = self.review_store().insert_manual_score_event(canonical, manual_score, identity)
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

    def handle_qa_mcp_health(self) -> None:
        """Expose a cheap, read-only MCP Host contract for the 8093 guard.

        This endpoint deliberately does not query production databases or invoke
        a model. It verifies that the configured registry, cross-source modules,
        conversation context, and unified catalog are present in this process.
        """
        required_modules = {
            "cross_source_plan": ASSISTANT_BACKEND_DIR / "mcp_host" / "cross_source_plan.py",
            "cross_source_executor": ASSISTANT_BACKEND_DIR / "mcp_host" / "cross_source_executor.py",
            "conversation_context": ASSISTANT_BACKEND_DIR / "mcp_conversation_context.py",
        }
        catalog_manifest = ASSISTANT_DIR / "mcp" / "catalog" / "catalog_manifest.json"
        module_status = {
            name: {"present": path.is_file(), "path": path.name}
            for name, path in required_modules.items()
        }
        registry_status: dict[str, Any] = {"present": MCP_SERVER_REGISTRY_PATH.is_file()}
        registry_error: str | None = None
        try:
            registry = load_server_registry(MCP_SERVER_REGISTRY_PATH)
            registry_status["server_ids"] = sorted(str(item.server_id) for item in registry.servers)
        except Exception as exc:  # noqa: BLE001
            registry_error = str(exc)
            registry_status["error"] = registry_error
        catalog_status = {"present": catalog_manifest.is_file(), "path": catalog_manifest.name}
        module_ok = all(item["present"] for item in module_status.values())
        registry_ok = bool(registry_status.get("present")) and registry_error is None
        catalog_ok = bool(catalog_status["present"])
        ok = module_ok and registry_ok and catalog_ok
        self.send_json(
            {
                "ok": ok,
                "schema": "ops.8093.mcp-health.v1",
                "cross_source_enabled": os.environ.get("BF_QA_MCP_CROSS_SOURCE_ENABLED", "1")
                .strip()
                .lower()
                not in {"0", "false", "off", "no"},
                "registry": registry_status,
                "modules": module_status,
                "catalog": catalog_status,
                "checks": {
                    "registry_loaded": registry_ok,
                    "cross_source_modules_present": module_ok,
                    "catalog_manifest_present": catalog_ok,
                },
            },
            status=200 if ok else 503,
        )

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
        session = self.qa_session_required()
        if session is None:
            return
        params = parse_qs(query)
        force_new = params.get("new", ["0"])[0] in {"1", "true", "yes"}
        with db_connect() as conn:
            guest_mode = session.get("access_mode") == "guest_shared"
            if guest_mode:
                conversation = ensure_shared_guest_conversation(conn, session)
                auto_new = False
            else:
                conversation, auto_new = select_bootstrap_conversation(
                    conn,
                    owner_subject=str(session["sub"]),
                    owner_role=str(session.get("role") or "operator"),
                    force_new=force_new,
                )
            self.send_json(
                {
                    "ok": True,
                    "access_mode": session.get("access_mode"),
                    "shared_guest": guest_mode,
                    "shared_room_id": session.get("shared_room_id") if guest_mode else None,
                    "auto_new": auto_new,
                    "inactivity_hours": QA_INACTIVITY_HOURS,
                    "server_time": iso_now(),
                    "conversation": conversation,
                    "conversations": list_conversations(conn, owner_subject=str(session["sub"])),
                    "messages": load_messages(conn, conversation["id"]),
                    "latest_snapshot": latest_snapshot(conn),
                    "projects": [] if guest_mode else list_projects(conn),
                    "report_assets": [] if guest_mode else scan_report_assets(conn),
                }
            )

    def handle_qa_conversations_get(self, query: str) -> None:
        """List conversations with optional immutable-origin filters."""
        session = self.qa_session_required()
        if session is None:
            return
        params = parse_qs(query)
        try:
            limit = min(100, max(1, int((params.get("limit") or [40])[0])))
            evaluation_raw = (params.get("evaluation_id") or [""])[0]
            evaluation_id = int(evaluation_raw) if evaluation_raw else None
        except (TypeError, ValueError):
            self.send_json({"ok": False, "error": "invalid_conversation_filter"}, status=400)
            return
        source_type = str((params.get("source_type") or [""])[0]).strip() or None
        source_id = str((params.get("source_id") or params.get("source_ref_id") or params.get("rule_id") or [""])[0]).strip() or None
        status_filter = str((params.get("status") or ["active"])[0]).strip() or "active"
        if status_filter not in {"active", "archived", "all"}:
            self.send_json({"ok": False, "error": "invalid_conversation_status"}, status=400)
            return
        date_from = str((params.get("date_from") or [""])[0]).strip() or None
        date_to = str((params.get("date_to") or [""])[0]).strip() or None
        query_text = str((params.get("q") or [""])[0]).strip()[:80] or None
        with db_connect() as conn:
            items = list_conversations(
                conn,
                limit=limit,
                owner_subject=str(session["sub"]),
                origin_source_type=source_type,
                origin_source_id=source_id,
                origin_evaluation_id=evaluation_id,
                status_filter=status_filter,
                date_from=date_from,
                date_to=date_to,
                query_text=query_text,
            )
        self.send_json({"ok": True, "conversations": items, "items": items})

    def handle_qa_conversation(self, query: str) -> None:
        session = self.qa_session_required()
        if session is None:
            return
        params = parse_qs(query)
        conversation_id = params.get("id", [""])[0]
        if not conversation_id:
            self.send_json({"ok": False, "error": "missing conversation id"}, status=400)
            return
        with db_connect() as conn:
            if not self.qa_conversation_owned(conn, conversation_id, session):
                return
            conversation = load_conversation_with_origin(conn, conversation_id)
            if conversation is None:
                self.send_json({"ok": False, "error": "conversation not found"}, status=404)
                return
            self.send_json(
                {
                    "ok": True,
                    "conversation": conversation,
                    "conversations": list_conversations(conn, owner_subject=str(session["sub"])),
                    "messages": load_messages(conn, conversation_id),
                }
            )

    def handle_qa_projects_get(self, query: str) -> None:
        if self.qa_operator_session_required() is None:
            return
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

    def handle_qa_knowledge_chunk(self, query: str) -> None:
        params = parse_qs(query)
        chunk_id = (params.get("chunk_id") or [""])[0].strip()
        if not chunk_id or len(chunk_id) > 160 or not re.fullmatch(r"[A-Za-z0-9_.-]+", chunk_id):
            self.send_json({"ok": False, "error": "invalid knowledge chunk id"}, status=400)
            return
        try:
            with _assistant_raw_pg_connect() as conn:
                row = conn.execute(
                    """
                    SELECT chunk_id, doc_id, title, content, source_file,
                           knowledge_category, chunk_type, created_at
                    FROM bf_assistant.rag_chunk
                    WHERE chunk_id = %s
                      AND doc_id = %s
                    LIMIT 1
                    """,
                    (chunk_id, diag_ai_evidence.FOREMAN_KNOWLEDGE_DOC_ID),
                ).fetchone()
            if not row:
                self.send_json({"ok": False, "error": "knowledge chunk not found"}, status=404)
                return
            item = dict(row)
            if (params.get("format") or [""])[0].lower() == "html":
                title = html.escape(str(item.get("title") or "知识依据"))
                content = html.escape(str(item.get("content") or ""))
                source = html.escape(str(item.get("source_file") or ""))
                document = (
                    "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
                    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                    "<title>" + title + "</title>"
                    "<style>body{font-family:SimSun,宋体,serif;max-width:960px;margin:32px auto;padding:0 20px;color:#263238;line-height:1.8}"
                    "h1{font-size:26px;border-bottom:1px solid #b0bec5;padding-bottom:12px}"
                    "pre{white-space:pre-wrap;background:#f5f7f8;padding:18px;border-left:4px solid #607d8b}"
                    "small{color:#607d8b}</style></head><body><h1>" + title
                    + "</h1><small>来源：" + source + "；只读知识依据</small><pre>"
                    + content + "</pre></body></html>"
                )
                self.send_html(document)
                return
            self.send_json({"ok": True, "item": item, "read_only": True})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": f"knowledge chunk unavailable: {exc}"}, status=503)

    def handle_qa_knowledge_pgvector_rebuild(self) -> None:
        if self.qa_operator_session_required() is None:
            return
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
        if self.qa_operator_session_required() is None:
            return
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
        if self.qa_operator_session_required() is None:
            return
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
        if self.qa_operator_session_required() is None:
            return
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
        session = self.qa_operator_session_required()
        if session is None:
            return
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
                    f"SELECT * FROM qa_conversations WHERE id IN ({placeholders}) AND owner_subject = ?",
                    [*conversation_ids, str(session["sub"])],
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
                        "conversations": list_conversations(conn, owner_subject=str(session["sub"])),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_qa_new_conversation(self) -> None:
        session = self.qa_session_required()
        if session is None:
            return
        if session.get("access_mode") == "guest_shared":
            with db_connect() as conn:
                conversation = ensure_shared_guest_conversation(conn, session)
                self.send_json(
                    {
                        "ok": True,
                        "access_mode": "guest_shared",
                        "conversation": conversation,
                        "conversations": [conversation],
                        "messages": load_messages(conn, conversation["id"]),
                    }
                )
            return
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
            conversation = create_conversation(
                conn,
                title=title,
                owner_subject=str(session["sub"]),
                owner_role=str(session.get("role") or "operator"),
            )
            if short_seed:
                queue = short_seed.get("queue") or {}
                source_ref_id = str(
                    short_seed.get("conversation_id") or queue.get("queue_id") or short_conversation_id or short_queue_id
                )
                persist_non_abc_conversation_origin(
                    conn,
                    conversation_id=conversation["id"],
                    source_type="short_window",
                    source_ref_id=source_ref_id,
                    source_title=title,
                    payload=short_seed,
                    source_page="short-window",
                    return_route=str(payload.get("return_route") or ""),
                )
            period_report_id = payload.get("period_report_id")
            if period_report_id and not short_seed:
                report = conn.execute("SELECT * FROM period_reports WHERE id=?", (int(period_report_id),)).fetchone()
                if not report:
                    conn.execute("DELETE FROM qa_conversations WHERE id=?", (conversation["id"],))
                    conn.commit()
                    self.send_json({"ok": False, "error": "period_report_not_found"}, status=404)
                    return
                persist_non_abc_conversation_origin(
                    conn,
                    conversation_id=conversation["id"],
                    source_type="period_report",
                    source_ref_id=str(period_report_id),
                    source_title=str(report.get("title") or title),
                    payload=dict(report),
                    source_page="period-report",
                    return_route=str(payload.get("return_route") or ""),
                )
            conn.commit()
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
                    "conversations": list_conversations(conn, owner_subject=str(session["sub"])),
                    "messages": messages,
                }
            )

    def handle_qa_contextual_conversation(self) -> None:
        """Create/reuse an ABC-origin conversation from authoritative IDs only."""
        session = self.current_review_session()
        role = str((session or {}).get("role") or "").lower()
        if not session or not any(token in role for token in ("operator", "admin", "操作", "管理", "炉长")):
            self.send_json({"ok": False, "error": "explanation_permission_required"}, status=403)
            return
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        allowed_fields = {"source_type", "source_page", "rule_id", "evaluation_id", "reuse_policy"}
        rejected = sorted(set(payload).difference(allowed_fields))
        if rejected:
            self.send_json({"ok": False, "error": "contextual_conversation_unknown_fields", "rejected_fields": rejected}, status=400)
            return
        missing = sorted(allowed_fields.difference(payload))
        if missing:
            self.send_json({"ok": False, "error": "contextual_conversation_missing_fields", "missing_fields": missing}, status=400)
            return
        source_type = str(payload.get("source_type") or "").strip()
        source_page = str(payload.get("source_page") or "").strip()
        rule_id = str(payload.get("rule_id") or "").strip()
        reuse_policy = str(payload.get("reuse_policy") or "").strip()
        if source_type != "abc_rule":
            self.send_json({"ok": False, "error": "unsupported_source_type"}, status=400)
            return
        if source_page != "optimization":
            self.send_json({"ok": False, "error": "unsupported_source_page"}, status=400)
            return
        if rule_id not in RULE_BY_ID:
            self.send_json({"ok": False, "error": "unknown_rule"}, status=404)
            return
        if reuse_policy not in {"same_rule_active", "force_new"}:
            self.send_json({"ok": False, "error": "invalid_reuse_policy"}, status=400)
            return
        try:
            evaluation_id = int(payload.get("evaluation_id"))
        except (TypeError, ValueError):
            self.send_json({"ok": False, "error": "invalid_evaluation_id"}, status=400)
            return
        try:
            artifacts = self._authoritative_abc_context(rule_id, evaluation_id)
            if artifacts is None:
                self.send_json({"ok": False, "error": "evaluation_not_found"}, status=404)
                return
            context_snapshot_id = self._persist_abc_context(rule_id, evaluation_id, artifacts)
            ts = iso_now()
            operator_id = str((session or {}).get("sub") or "operator")
            local_now = datetime.now(ZoneInfo("Asia/Shanghai"))
            shift_key = f"{local_now.date().isoformat()}:{(local_now.hour // 8) * 8:02d}"
            summary = artifacts["context_summary"]
            title = str(summary.get("display_name") or rule_id)[:160]
            with db_connect() as conn:
                existing = None
                if reuse_policy == "same_rule_active":
                    existing = conn.execute(
                        """
                        SELECT c.id FROM qa_conversations c
                        JOIN qa_conversation_origins o ON o.conversation_id = c.id
                        WHERE COALESCE(c.status, 'active') = 'active'
                          AND o.source_type = 'abc_rule' AND o.source_id = ?
                          AND o.operator_id = ? AND o.shift_key = ?
                          AND c.owner_subject = ?
                        ORDER BY c.updated_at DESC LIMIT 1
                        """,
                        (rule_id, operator_id, shift_key, str(session["sub"])),
                    ).fetchone()
                if existing:
                    conversation_id = str(existing["id"])
                    conn.execute("UPDATE qa_conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id))
                    conn.execute(
                        """UPDATE qa_conversation_origins
                           SET evaluation_id = ?, context_snapshot_id = ?, reuse_policy = ?, updated_at = ?
                           WHERE conversation_id = ?""",
                        (evaluation_id, context_snapshot_id, reuse_policy, ts, conversation_id),
                    )
                else:
                    conversation_id = create_conversation(
                        conn,
                        title=title,
                        owner_subject=str(session["sub"]),
                        owner_role=str(session.get("role") or "operator"),
                    )["id"]
                    conn.execute(
                        """
                        INSERT INTO qa_conversation_origins(
                            conversation_id, source_type, source_id, evaluation_id,
                            context_snapshot_id, reuse_policy, source_page, source_ref_id,
                            source_title, initial_evaluation_id, initial_context_snapshot_id,
                            return_route, operator_id, shift_key, created_at, updated_at
                        ) VALUES (?, 'abc_rule', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            conversation_id, rule_id, evaluation_id, context_snapshot_id,
                            reuse_policy, source_page,
                            rule_id, title, evaluation_id, context_snapshot_id,
                            "", operator_id, shift_key, ts, ts,
                        ),
                    )
                conn.commit()
                conversation_payload = load_conversation_with_origin(conn, conversation_id)
                cached_analysis = _abc_rule_cached_analysis(
                    conn,
                    context_snapshot_id,
                    _abc_rule_analysis_model_name(),
                )
            self.send_json({
                "ok": True,
                "conversation": conversation_payload,
                "context_summary": summary,
                "operator_explanation": artifacts["operator_explanation"],
                "analysis_text": cached_analysis.get("answer") if cached_analysis else None,
                "analysis_state": "completed" if cached_analysis else "context_ready",
                "cache_hit": bool(cached_analysis),
                "assistant_enabled": ABC_RULE_ASSISTANT_ENABLED,
                "auto_analysis_enabled": ABC_RULE_ASSISTANT_AUTO_ANALYSIS,
            })
        except Exception as exc:
            self.send_json({"ok": False, "error_type": type(exc).__name__}, status=503)

    def handle_qa_snapshot(self) -> None:
        if self.qa_operator_session_required() is None:
            return
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return
        with db_connect() as conn:
            snapshot_id = insert_snapshot(conn, payload)
            self.send_json({"ok": True, "snapshot_id": snapshot_id})

    def send_cached_abc_initial_analysis(
        self,
        conversation_id: str,
        cached: Mapping[str, Any],
        *,
        stream: bool,
        session: Mapping[str, Any],
    ) -> None:
        """Return one completed initial analysis without another model request."""
        with db_connect() as conn:
            if not self.qa_conversation_owned(conn, conversation_id, session):
                return
            conversation = load_conversation_with_origin(conn, conversation_id)
            messages = load_messages(conn, conversation_id)
        payload = {
            "ok": True,
            "answer": cached.get("answer"),
            "conversation": conversation,
            "messages": messages,
            "context_snapshot_id": cached.get("context_snapshot_id"),
            "context_hash": cached.get("context_hash"),
            "prompt_version": cached.get("prompt_version"),
            "cache_hit": True,
        }
        if not stream:
            self.send_json(payload)
            return
        self.send_response(200)
        self.add_cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.end_headers()
        self.write_qa_event("start", {"ok": True, "stage": "preparing", "cache_hit": True})
        self.write_qa_event(
            "start",
            {
                "ok": True,
                "stage": "prepared",
                "conversation": conversation,
                "context_snapshot_id": cached.get("context_snapshot_id"),
                "context_hash": cached.get("context_hash"),
                "cache_hit": True,
            },
        )
        self.write_qa_event("delta", {"delta": cached.get("answer"), "content": cached.get("answer")})
        self.write_qa_event("final", payload)
        self.write_qa_event("done", {"ok": True, "cache_hit": True})

    def handle_qa_chat(self) -> None:
        session = self.qa_session_required()
        if session is None:
            return
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_json({"ok": False, "error": f"bad json: {exc}"}, status=400)
            return

        question = str(payload.get("message") or "").strip()
        if not question:
            self.send_json({"ok": False, "error": "message is required"}, status=400)
            return

        guest_mode = session.get("access_mode") == "guest_shared"
        if guest_mode:
            forbidden = {
                "analysis_mode", "project_id", "context_assets", "attachments",
                "manual_context_text", "context_mode",
            }.intersection(payload)
            if forbidden:
                self.send_json(
                    {
                        "ok": False,
                        "error": "guest_context_not_allowed",
                        "rejected_fields": sorted(forbidden),
                    },
                    status=403,
                )
                return
        requested_conversation_id = str(payload.get("conversation_id") or "").strip()
        with db_connect() as conn:
            conversation_id = self.qa_chat_conversation_id(conn, requested_conversation_id, session)
        if conversation_id is None:
            return
        payload["conversation_id"] = conversation_id

        wants_stream = bool(payload.get("stream")) or "text/event-stream" in self.headers.get("Accept", "")
        initial_ticket: dict[str, Any] | None = None
        if str(payload.get("analysis_mode") or "") == "initial_context_explanation":
            if not ABC_RULE_ASSISTANT_ENABLED:
                self.send_json(
                    {"ok": False, "error": "abc_rule_assistant_disabled", "retryable": False},
                    status=503,
                )
                return
            if not ABC_RULE_ASSISTANT_AUTO_ANALYSIS:
                self.send_json(
                    {"ok": False, "error": "abc_rule_auto_analysis_disabled", "retryable": False},
                    status=409,
                )
                return
            if question != ABC_RULE_INITIAL_QUESTION:
                self.send_json({"ok": False, "error": "invalid_initial_analysis_question"}, status=400)
                return
            initial_ticket = claim_abc_rule_initial_analysis(conversation_id, str(session["sub"]))
            if initial_ticket.get("state") == "unbound":
                self.send_json({"ok": False, "error": "abc_context_binding_required"}, status=409)
                return
            if initial_ticket.get("state") == "waiter":
                cached = wait_for_abc_rule_initial_analysis(initial_ticket)
                if cached:
                    self.send_cached_abc_initial_analysis(conversation_id, cached, stream=wants_stream, session=session)
                else:
                    self.send_json(
                        {"ok": False, "error": "initial_analysis_wait_timeout", "retryable": True},
                        status=503,
                    )
                return
            if initial_ticket.get("state") == "cached":
                self.send_cached_abc_initial_analysis(conversation_id, initial_ticket, stream=wants_stream, session=session)
                return
            if initial_ticket.get("state") == "retry_wait":
                self.send_json(
                    {
                        "ok": False,
                        "error": "initial_analysis_retry_delayed",
                        "retryable": True,
                        "retry_after_seconds": initial_ticket.get("retry_after_seconds"),
                    },
                    status=503,
                )
                return
            if initial_ticket.get("state") == "owner":
                payload["_abc_initial_analysis_ticket"] = initial_ticket

        payload["_qa_owner_subject"] = str(session["sub"])
        payload["_qa_owner_role"] = str(session.get("role") or "operator")
        payload["_qa_access_mode"] = str(session.get("access_mode") or "authenticated")

        try:
            lock = guest_room_generation_lock(str(session["sub"])) if guest_mode else nullcontext()
            with lock:
                if wants_stream:
                    self.handle_qa_chat_stream(payload, question)
                    return
                self.handle_qa_chat_json(payload, question)
        finally:
            finish_abc_rule_initial_analysis(initial_ticket)

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
            owner_subject = str(payload.get("_qa_owner_subject") or "")
            guest_mode = str(payload.get("_qa_access_mode") or "") == "guest_shared"
            row = conn.execute(
                "SELECT * FROM qa_conversations WHERE id = ? AND owner_subject = ?",
                (conversation_id, owner_subject),
            ).fetchone()
            if row is None:
                raise PermissionError("conversation ownership check failed")
            bound_context_row = conn.execute(
                """
                SELECT o.context_snapshot_id, o.source_type, s.context_hash, s.payload_json
                FROM qa_conversation_origins o
                JOIN qa_context_snapshots s ON s.id = o.context_snapshot_id
                WHERE o.conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            bound_assistant_context = ""
            bound_context_snapshot_id = None
            if bound_context_row:
                bound_context_snapshot_id = int(bound_context_row["context_snapshot_id"])
                if str(bound_context_row["source_type"] or "") == "abc_rule":
                    bound_assistant_context = str(bound_context_row["payload_json"] or "")
            project_id = None if guest_mode else payload.get("project_id")
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
                latest_pg_started = time.perf_counter()
                pg_snapshot = self.latest_pg_snapshot_for_qa(conn)
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
                    conn=conn,
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
            context_assets = [] if guest_mode else (
                payload.get("context_assets") if isinstance(payload.get("context_assets"), list) else []
            )
            report_attachments = [] if guest_mode else (
                payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
            )
            context_assets = [*context_assets, *report_attachments_to_context_assets(conn, report_attachments)]
            project_context, context_refs = build_project_context(
                conn,
                context_assets,
                manual_context_text="" if guest_mode else str(payload.get("manual_context_text") or ""),
            )
            report_ref = next(
                (item for item in context_refs if str(item.get("ref_type") or "") == "period_report"),
                None,
            )
            if report_ref:
                existing_origin = conn.execute(
                    "SELECT conversation_id FROM qa_conversation_origins WHERE conversation_id=?",
                    (conversation_id,),
                ).fetchone()
                if not existing_origin:
                    persist_non_abc_conversation_origin(
                        conn,
                        conversation_id=conversation_id,
                        source_type="period_report",
                        source_ref_id=str(report_ref.get("ref_id") or ""),
                        source_title=str(report_ref.get("inserted_title") or "报表问答"),
                        payload=report_ref,
                        source_page="qa-report-insert",
                    )
                    conn.commit()
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
            knowledge_pack = qa_search_knowledge(
                question,
                mcp_prefetch=mcp_prefetch,
                connection=conn,
            )
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
                "bound_context_snapshot_id": bound_context_snapshot_id,
                "bound_context_hash": bound_context_row["context_hash"] if bound_context_row else None,
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
            if bound_context_snapshot_id is not None:
                conn.execute(
                    """
                    INSERT INTO qa_message_context_snapshots(
                        conversation_id, message_id, context_snapshot_id, usage_kind, created_at
                    ) VALUES (?, ?, ?, 'assistant_prompt', ?)
                    ON CONFLICT(message_id, context_snapshot_id, usage_kind) DO NOTHING
                    """,
                    (conversation_id, user_message_id, bound_context_snapshot_id, iso_now()),
                )
                conn.commit()

            conversation_payload = load_conversation_with_origin(conn, conversation_id)
            return {
                "conversation_id": conversation_id,
                "owner_subject": owner_subject,
                "access_mode": "guest_shared" if guest_mode else "authenticated",
                "analysis_mode": str(payload.get("analysis_mode") or ""),
                "analysis_claim_token": str((payload.get("_abc_initial_analysis_ticket") or {}).get("claim_token") or ""),
                "bound_context_snapshot_id": bound_context_snapshot_id,
                "bound_context_hash": bound_context_row["context_hash"] if bound_context_row else None,
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
                    assistant_rule_context=bound_assistant_context,
                    analysis_mode=str(payload.get("analysis_mode") or ""),
                ),
                "bound_assistant_context": load_json(bound_assistant_context, {}),
                "conversation": conversation_payload,
                "conversations": list_conversations(conn, owner_subject=owner_subject) if include_conversations else None,
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
        prepared: dict[str, Any] | None = None
        try:
            prepared = self.prepare_qa_chat(payload, question)
            mcp_tool_trace: list[dict[str, Any]] = []
            tool_result: dict[str, Any] = {}
            if prepared.get("use_mcp_tools"):
                tool_result = run_qa_mcp_tool_loop(
                    prepared["messages"],
                    routing_question=prepared.get("routing_question") or "",
                )
                tool_result = qa_mcp_result_with_fallback(tool_result, prepared["messages"])
                mcp_tool_trace = tool_result.get("tool_trace") or []
                prepared["hidden_context"]["mcp_tool_trace"] = mcp_tool_trace
                prepared["hidden_context"]["mcp_conversation_context"] = context_with_tool_trace(
                    prepared["hidden_context"].get("mcp_conversation_context"),
                    mcp_tool_trace,
                )
                # Save cross-source facts for follow-up resolution
                if tool_result.get("mcp_cross_source"):
                    prepared["hidden_context"]["mcp_conversation_context"] = context_with_cross_source_snapshot(
                        prepared["hidden_context"].get("mcp_conversation_context"),
                        tool_result.get("cross_source_snapshot"),
                    )
                if tool_result.get("ok") is False and not tool_result.get("answer"):
                    answer = f"数据库查询失败：{tool_result.get('error') or '未知错误'}"
                else:
                    answer = clean_llm_output(tool_result.get("answer") or "")
            else:
                answer = (
                    call_ollama_chat_strict_json(
                        prepared["messages"],
                        prepared.get("bound_assistant_context") or {},
                    )
                    if prepared.get("analysis_mode") == "initial_context_explanation"
                    else call_ollama_chat(prepared["messages"])
                )
            analysis_payload = None
            if prepared.get("analysis_mode") == "initial_context_explanation":
                answer, analysis_payload = validated_abc_initial_answer_with_repair(
                    answer,
                    prepared["messages"],
                    prepared.get("bound_assistant_context") or {},
                )
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
                if prepared.get("analysis_mode") == "initial_context_explanation":
                    cache_abc_rule_analysis(
                        conn,
                        prepared.get("bound_context_snapshot_id"),
                        answer,
                        model_name=_abc_rule_analysis_model_name(),
                        analysis_payload=analysis_payload,
                        claim_token=prepared.get("analysis_claim_token"),
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
                        "conversations": list_conversations(conn, owner_subject=prepared.get("owner_subject")),
                        "messages": load_messages(conn, prepared["conversation_id"]),
                        "context_refs": prepared.get("context_refs", []),
                        "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                        "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                        "mcp_tool_trace": mcp_tool_trace,
                        "mcp_model_explanation": tool_result.get("model_explanation"),
                        "model_request_count": tool_result.get("model_request_count"),
                        "mcp_cross_source": tool_result.get("mcp_cross_source"),
                        "cross_source_snapshot": tool_result.get("cross_source_snapshot"),
                    }
                )
        except HTTPError as exc:
            if prepared and prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "failed_retryable", error_code="model_http_error", claim_token=prepared.get("analysis_claim_token"))
            detail = sanitize_model_exposure(exc.read().decode("utf-8", errors="replace"))
            self.send_json({"ok": False, "error": f"高炉大模型服务 HTTP {exc.code}", "detail": detail}, status=200)
        except URLError as exc:
            if prepared and prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "failed_retryable", error_code="model_unavailable", claim_token=prepared.get("analysis_claim_token"))
            self.send_json(
                {"ok": False, "error": f"高炉大模型服务不可达：{sanitize_model_exposure(exc.reason)}"},
                status=200,
            )
        except Exception as exc:  # noqa: BLE001
            if prepared and prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(
                    prepared.get("bound_context_snapshot_id"),
                    "failed_retryable",
                    error_code=(
                        "invalid_model_json"
                        if isinstance(exc, abc_rule_assistant_analysis.InitialAnalysisValidationError)
                        else type(exc).__name__
                    ),
                    claim_token=prepared.get("analysis_claim_token"),
                )
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
                "conversation_id": prepared["conversation_id"],
                "context_snapshot_id": prepared.get("bound_context_snapshot_id"),
                "context_hash": prepared.get("bound_context_hash"),
                "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                "knowledge": prepared.get("knowledge"),
                "qa_prepare_timing_ms": prepared.get("qa_prepare_timing_ms"),
            },
        )
        if prepared.get("analysis_mode") == "initial_context_explanation":
            set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "generating", claim_token=prepared.get("analysis_claim_token"))
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
        tool_result: dict[str, Any] = {}
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
                tool_result = qa_mcp_result_with_fallback(tool_result, prepared["messages"])
                mcp_tool_trace = tool_result.get("tool_trace") or []
                prepared["hidden_context"]["mcp_tool_trace"] = mcp_tool_trace
                prepared["hidden_context"]["mcp_conversation_context"] = context_with_tool_trace(
                    prepared["hidden_context"].get("mcp_conversation_context"),
                    mcp_tool_trace,
                )
                # Save cross-source facts for follow-up resolution
                if tool_result.get("mcp_cross_source"):
                    prepared["hidden_context"]["mcp_conversation_context"] = context_with_cross_source_snapshot(
                        prepared["hidden_context"].get("mcp_conversation_context"),
                        tool_result.get("cross_source_snapshot"),
                    )
                if tool_result.get("tool_used") and tool_result.get("needs_final"):
                    stream_messages = tool_result.get("messages") or prepared["messages"]
                elif tool_result.get("ok") is False and not tool_result.get("answer"):
                    precomputed_answer = f"数据库查询失败：{tool_result.get('error') or '未知错误'}"
                else:
                    precomputed_answer = clean_llm_output(tool_result.get("answer") or "")

            if prepared.get("analysis_mode") == "initial_context_explanation" and precomputed_answer is None:
                # Buffer strict JSON and expose only the validated rendering to SSE clients.
                precomputed_answer = call_ollama_chat_strict_json(
                    stream_messages,
                    prepared.get("bound_assistant_context") or {},
                )

            if precomputed_answer is not None:
                analysis_payload = None
                answer = precomputed_answer
                if prepared.get("analysis_mode") == "initial_context_explanation":
                    answer, analysis_payload = validated_abc_initial_answer_with_repair(
                        answer,
                        stream_messages,
                        prepared.get("bound_assistant_context") or {},
                    )
                answer = append_mcp_chart_links(answer, mcp_tool_trace)
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
                    if prepared.get("analysis_mode") == "initial_context_explanation":
                        cache_abc_rule_analysis(
                            conn,
                            prepared.get("bound_context_snapshot_id"),
                            answer,
                            model_name=_abc_rule_analysis_model_name(),
                            analysis_payload=analysis_payload,
                            claim_token=prepared.get("analysis_claim_token"),
                        )
                    conv_row = conn.execute(
                        "SELECT * FROM qa_conversations WHERE id = ?",
                        (prepared["conversation_id"],),
                    ).fetchone()
                    final_payload = {
                        "ok": True,
                        "answer": answer,
                        "conversation": conversation_from_row(conv_row),
                        "conversations": list_conversations(conn, owner_subject=prepared.get("owner_subject")),
                        "messages": load_messages(conn, prepared["conversation_id"]),
                        "context_refs": prepared.get("context_refs", []),
                        "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                        "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                        "mcp_tool_trace": mcp_tool_trace,
                        "mcp_model_explanation": tool_result.get("model_explanation"),
                        "model_request_count": tool_result.get("model_request_count"),
                        "mcp_cross_source": tool_result.get("mcp_cross_source"),
                        "cross_source_snapshot": tool_result.get("cross_source_snapshot"),
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
                        if not self.write_qa_event(
                            "delta",
                            {
                                "delta": safe_delta,
                                "content": safe_full,
                            },
                        ):
                            raise ConnectionAbortedError("SSE client disconnected")
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
                if prepared.get("analysis_mode") == "initial_context_explanation":
                    cache_abc_rule_analysis(
                        conn,
                        prepared.get("bound_context_snapshot_id"),
                        answer,
                        model_name=_abc_rule_analysis_model_name(),
                        claim_token=prepared.get("analysis_claim_token"),
                    )
                conv_row = conn.execute(
                    "SELECT * FROM qa_conversations WHERE id = ?",
                    (prepared["conversation_id"],),
                ).fetchone()
                final_payload = {
                    "ok": True,
                    "answer": answer,
                    "conversation": conversation_from_row(conv_row),
                    "conversations": list_conversations(conn, owner_subject=prepared.get("owner_subject")),
                    "messages": load_messages(conn, prepared["conversation_id"]),
                    "context_refs": prepared.get("context_refs", []),
                    "mcp_prefetch": {k: v for k, v in prepared.get("mcp_prefetch", {}).items() if k != "context_text"},
                    "mcp_tool_calling": bool(prepared.get("use_mcp_tools")),
                    "mcp_tool_trace": mcp_tool_trace,
                    "mcp_model_explanation": tool_result.get("model_explanation"),
                    "model_timing": model_timing,
                    "mcp_cross_source": tool_result.get("mcp_cross_source"),
                    "cross_source_snapshot": tool_result.get("cross_source_snapshot"),
                }
            self.write_qa_event("final", final_payload)
            self.write_qa_event("done", {"ok": True})
        except HTTPError as exc:
            if prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "failed_retryable", error_code="model_http_error", claim_token=prepared.get("analysis_claim_token"))
            detail = sanitize_model_exposure(exc.read().decode("utf-8", errors="replace"))
            self.write_qa_event("error", {"ok": False, "error": f"高炉大模型服务 HTTP {exc.code}", "detail": detail})
        except URLError as exc:
            if prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "failed_retryable", error_code="model_unavailable", claim_token=prepared.get("analysis_claim_token"))
            self.write_qa_event(
                "error",
                {"ok": False, "error": f"高炉大模型服务不可达：{sanitize_model_exposure(exc.reason)}"},
            )
        except ConnectionAbortedError:
            if prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "stopped", error_code="client_stopped", claim_token=prepared.get("analysis_claim_token"))
        except Exception as exc:  # noqa: BLE001
            if prepared.get("analysis_mode") == "initial_context_explanation":
                set_abc_rule_analysis_state(prepared.get("bound_context_snapshot_id"), "failed_retryable", error_code=type(exc).__name__, claim_token=prepared.get("analysis_claim_token"))
            self.write_qa_event("error", {"ok": False, "error": f"问答服务失败：{exc}"})

    def write_qa_event(self, event: str, payload: object) -> bool:
        try:
            self.wfile.write(qa_sse_event(event, payload))
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

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

    def handle_heat_performance_quality(self, query: str) -> None:
        """Return read-only IMES-style heat/sample/output quality facts."""

        params = parse_qs(query)
        try:
            limit = max(1, min(int(params.get("limit", ["12"])[0]), 100))
        except ValueError:
            self.send_json({"ok": False, "error": "limit must be an integer"}, status=400)
            return
        meltno = str(params.get("meltno", [""])[0]).strip() or None
        search = str(params.get("q", [""])[0]).strip() or None
        date_from = str(params.get("date_from", [""])[0]).strip() or None
        date_to = str(params.get("date_to", [""])[0]).strip() or None
        for name, value in (("date_from", date_from), ("date_to", date_to)):
            if value:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                    return
        has_samples = str(params.get("has_samples", ["0"])[0]).lower() in {"1", "true", "yes"}
        include_future = str(params.get("include_future", ["0"])[0]).lower() in {"1", "true", "yes"}
        try:
            payload = HeatPerformanceQualityStore().list_rows(
                limit=limit,
                meltno=meltno,
                query=search,
                date_from=date_from,
                date_to=date_to,
                has_samples=has_samples,
                include_future=include_future,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "HEAT_PERFORMANCE_QUERY_FAILED",
                    "error": sanitize_model_exposure(exc),
                    "items": [],
                    "read_only": True,
                },
                status=503,
            )
            return
        self.send_json(payload, status=200 if payload.get("ok") else 503)

    def handle_hcz_upward_rule(self) -> None:
        """Return the current read-only foreman expert-rule evaluation."""
        try:
            payload = hcz_upward_rule_api.evaluate_latest(self.pg_connect)
        except hcz_upward_rule_api.HczUpwardRuleDataError as exc:
            self.send_json(
                {
                    "ok": False,
                    "error": "hcz_upward_rule_data_unavailable",
                    "message": str(exc),
                    "requirement_id": hcz_upward_rule_api.REQUIREMENT_ID,
                },
                status=503,
            )
            return
        self.send_json(payload, status=200)

    def handle_hcz_rule_sensitivity(self, query_string: str) -> None:
        """Compare editable HCZ thresholds against measured history, read-only."""
        try:
            payload = hcz_upward_rule_api.evaluate_sensitivity(self.pg_connect, query_string)
        except hcz_upward_rule_api.HczRuleSensitivityValidationError as exc:
            self.send_json(
                {
                    "ok": False,
                    "error": "hcz_rule_sensitivity_invalid_request",
                    "message": str(exc),
                    "requirement_id": hcz_upward_rule_api.REQUIREMENT_ID,
                },
                status=400,
            )
            return
        except hcz_upward_rule_api.HczUpwardRuleDataError as exc:
            self.send_json(
                {
                    "ok": False,
                    "error": "hcz_rule_sensitivity_data_unavailable",
                    "message": str(exc),
                    "requirement_id": hcz_upward_rule_api.REQUIREMENT_ID,
                },
                status=503,
            )
            return
        self.send_json(payload, status=200)

    # REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808
    def _si_v20_operator_session(self) -> dict[str, Any] | None:
        session = self.current_review_session()
        if si_v20_shadow.require_login() and not session:
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_LOGIN_REQUIRED",
                    "error": "请先使用生产账号登录，再发起V20影子预测或历史回放。",
                },
                status=401,
            )
            return None
        return session or {"sub": "local_operator", "role": "operator"}

    def handle_si_v20_status(self, query: str) -> None:
        params = parse_qs(query)
        try:
            target_limit = max(1, min(int(params.get("limit", ["120"])[0]), 300))
            payload = si_v20_shadow.SiV20ShadowService().status(target_limit=target_limit)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_STATUS_UNAVAILABLE",
                    "error": sanitize_model_exposure(exc),
                },
                status=503,
            )
            return
        self.send_json(payload)

    def handle_si_v20_history(self, query: str) -> None:
        params = parse_qs(query)
        parsed_dates: dict[str, date | None] = {"date_from": None, "date_to": None}
        for name in parsed_dates:
            value = str(params.get(name, [""])[0]).strip()
            if not value:
                continue
            try:
                parsed_dates[name] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                return
        try:
            limit = max(1, min(int(params.get("limit", ["1000"])[0]), 2000))
        except ValueError:
            self.send_json({"ok": False, "error": "limit must be an integer"}, status=400)
            return
        meltno = str(params.get("meltno", [""])[0]).strip() or None
        latest_per_heat = str(params.get("latest_per_heat", ["1"])[0]).lower() in {
            "1", "true", "yes",
        }
        compact = str(params.get("compact", ["0"])[0]).lower() in {
            "1", "true", "yes",
        }
        try:
            payload = si_v20_shadow.SiV20ShadowService().history(
                date_from=parsed_dates["date_from"],
                date_to=parsed_dates["date_to"],
                meltno=meltno,
                limit=limit,
                latest_per_heat=latest_per_heat,
                compact=compact,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_HISTORY_UNAVAILABLE",
                    "error": sanitize_model_exposure(exc),
                    "items": [],
                },
                status=503,
            )
            return
        self.send_json(payload)

    def handle_si_v20_hourly_history(self, query: str) -> None:
        params = parse_qs(query)
        parsed_dates: dict[str, date | None] = {"date_from": None, "date_to": None}
        for name in parsed_dates:
            value = str(params.get(name, [""])[0]).strip()
            if not value:
                continue
            try:
                parsed_dates[name] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                return
        try:
            limit = max(1, min(int(params.get("limit", ["1000"])[0]), 2000))
            payload = si_v20_shadow.SiV20ShadowService().hourly_history(
                date_from=parsed_dates["date_from"],
                date_to=parsed_dates["date_to"],
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_HOURLY_HISTORY_UNAVAILABLE",
                    "error": sanitize_model_exposure(exc),
                    "items": [],
                },
                status=503,
            )
            return
        self.send_json(payload)

    def handle_si_v20_strict_hourly_status(self) -> None:
        try:
            payload = si_v20_shadow.SiV20ShadowService().strict_hourly_status()
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {"ok": False, "error_code": "SI_V20_STRICT_HOURLY_STATUS_UNAVAILABLE", "error": sanitize_model_exposure(exc)},
                status=503,
            )
            return
        self.send_json(payload, headers={"Cache-Control": "no-store"})

    def handle_si_v20_strict_hourly_history(self, query: str) -> None:
        params = parse_qs(query)
        parsed_dates: dict[str, date | None] = {"date_from": None, "date_to": None}
        for name in parsed_dates:
            value = str(params.get(name, [""])[0]).strip()
            if not value:
                continue
            try:
                parsed_dates[name] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                return
        try:
            limit = max(1, min(int(params.get("limit", ["5000"])[0]), 5000))
            payload = si_v20_shadow.SiV20ShadowService().strict_hourly_history(
                date_from=parsed_dates["date_from"],
                date_to=parsed_dates["date_to"],
                meltno_from=str(params.get("meltno_from", [""])[0]).strip() or None,
                meltno_to=str(params.get("meltno_to", [""])[0]).strip() or None,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {"ok": False, "error_code": "SI_V20_STRICT_HOURLY_HISTORY_UNAVAILABLE", "error": sanitize_model_exposure(exc), "items": []},
                status=503,
            )
            return
        self.send_json(payload, headers={"Cache-Control": "no-store"})

    def handle_si_v20_hourly_table(self, query: str) -> None:
        params = parse_qs(query)
        parsed_dates: dict[str, date | None] = {"date_from": None, "date_to": None}
        for name in parsed_dates:
            value = str(params.get(name, [""])[0]).strip()
            if not value:
                continue
            try:
                parsed_dates[name] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                return
        try:
            limit = max(1, min(int(params.get("limit", ["5000"])[0]), 5000))
            payload = si_v20_shadow.SiV20ShadowService().hourly_table(
                date_from=parsed_dates["date_from"],
                date_to=parsed_dates["date_to"],
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {"ok": False, "error_code": "SI_V20_HOURLY_TABLE_UNAVAILABLE", "error": sanitize_model_exposure(exc), "items": []},
                status=503,
            )
            return
        self.send_json(payload, headers={"Cache-Control": "no-store"})

    def handle_si_v20_schedule_status(self) -> None:
        try:
            payload = si_v20_shadow.SiV20ShadowService().schedule_status()
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {"ok": False, "error_code": "SI_V20_SCHEDULE_UNAVAILABLE", "error": sanitize_model_exposure(exc)},
                status=503,
            )
            return
        self.send_json(payload, headers={"Cache-Control": "no-store"})

    def handle_si_v20_scheduled_history(self, query: str) -> None:
        params = parse_qs(query)
        parsed_dates: dict[str, date | None] = {"date_from": None, "date_to": None}
        for name in parsed_dates:
            value = str(params.get(name, [""])[0]).strip()
            if not value:
                continue
            try:
                parsed_dates[name] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                self.send_json({"ok": False, "error": f"{name} must be YYYY-MM-DD"}, status=400)
                return
        try:
            cadence_raw = str(params.get("cadence_minutes", [""])[0]).strip()
            cadence = si_v20_shadow.validate_cadence_minutes(cadence_raw) if cadence_raw else None
            run_raw = str(params.get("schedule_run_id", [""])[0]).strip()
            run_id = int(run_raw) if run_raw else None
            limit = max(1, min(int(params.get("limit", ["5000"])[0]), 10000))
            payload = si_v20_shadow.SiV20ShadowService().scheduled_history(
                date_from=parsed_dates["date_from"],
                date_to=parsed_dates["date_to"],
                cadence_minutes=cadence,
                schedule_run_id=run_id,
                limit=limit,
            )
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {"ok": False, "error_code": "SI_V20_SCHEDULED_HISTORY_UNAVAILABLE", "error": sanitize_model_exposure(exc), "items": []},
                status=503,
            )
            return
        self.send_json(payload)

    def handle_si_v20_data_readiness(self, query: str) -> None:
        params = parse_qs(query)
        payload = {
            "target_meltno": str(params.get("target_meltno", [""])[0]).strip(),
            "target_open_ts": str(params.get("target_open_ts", [""])[0]).strip() or None,
            "cutoff_mode": str(params.get("cutoff_mode", ["now"])[0]).strip(),
            "cutoff_ts": str(params.get("cutoff_ts", [""])[0]).strip() or None,
        }
        if not payload["target_meltno"]:
            self.send_json({"ok": False, "error": "target_meltno不能为空"}, status=400)
            return
        try:
            result = si_v20_shadow.SiV20ShadowService().data_readiness(payload)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_READINESS_UNAVAILABLE",
                    "error": sanitize_model_exposure(exc),
                },
                status=503,
            )
            return
        self.send_json(result)

    def handle_si_v20_prediction_detail(self, query: str) -> None:
        params = parse_qs(query)
        try:
            prediction_id = int(str(params.get("prediction_id", [""])[0]).strip())
        except ValueError:
            self.send_json({"ok": False, "error": "prediction_id必须是整数"}, status=400)
            return
        try:
            result = si_v20_shadow.SiV20ShadowService().prediction_detail(prediction_id)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=404)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_DETAIL_UNAVAILABLE",
                    "error": sanitize_model_exposure(exc),
                },
                status=503,
            )
            return
        self.send_json(result)

    def _handle_si_v20_write(self, action: str) -> None:
        session = self._si_v20_operator_session()
        if session is None:
            return
        try:
            payload = self.read_json_body()
        except Exception:
            self.send_json({"ok": False, "error": "请求JSON格式不正确"}, status=400)
            return
        service = si_v20_shadow.SiV20ShadowService()
        try:
            if action == "predict":
                result = service.predict(
                    payload,
                    username=str(session.get("sub") or "operator"),
                    role=str(session.get("role") or "operator"),
                )
            elif action == "hourly_predict":
                result = service.hourly_predict(
                    payload,
                    username=str(session.get("sub") or "operator"),
                    role=str(session.get("role") or "operator"),
                )
            else:
                result = service.replay(
                    payload,
                    username=str(session.get("sub") or "operator"),
                    role=str(session.get("role") or "operator"),
                )
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json(
                {
                    "ok": False,
                    "error_code": "SI_V20_PREDICTION_FAILED",
                    "error": sanitize_model_exposure(exc),
                },
                status=503,
            )
            return
        self.send_json(result)

    def handle_si_v20_predict(self) -> None:
        self._handle_si_v20_write("predict")

    def handle_si_v20_hourly_predict(self) -> None:
        self._handle_si_v20_write("hourly_predict")

    def handle_si_v20_strict_hourly_predict(self) -> None:
        session = self._si_v20_operator_session()
        if session is None:
            return
        try:
            payload = self.read_json_body()
            result = si_v20_shadow.SiV20ShadowService().strict_hourly_predict(
                payload,
                username=str(session.get("sub") or "operator"),
                role=str(session.get("role") or "operator"),
            )
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_STRICT_HOURLY_PREDICT_FAILED", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(result, status=200 if result.get("ok") else 207)

    def handle_si_v20_strict_hourly_dispatch(self) -> None:
        try:
            result = si_v20_shadow.SiV20ShadowService().dispatch_strict_hourly()
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_STRICT_HOURLY_DISPATCH_FAILED", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(result, status=200 if result.get("ok") else 207)

    def handle_si_v20_replay(self) -> None:
        self._handle_si_v20_write("replay")

    def handle_si_v20_schedule_configure(self) -> None:
        session = self._si_v20_operator_session()
        if session is None:
            return
        try:
            payload = self.read_json_body()
            result = si_v20_shadow.SiV20ShadowService().configure_schedule(
                payload,
                username=str(session.get("sub") or "operator"),
            )
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_SCHEDULE_CONFIG_FAILED", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(result)

    def handle_si_v20_schedule_dispatch(self) -> None:
        try:
            result = si_v20_shadow.SiV20ShadowService().dispatch_due_schedules()
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_SCHEDULE_DISPATCH_FAILED", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(result, status=200 if result.get("ok") else 207)

    def handle_si_v20_scheduled_replay(self) -> None:
        session = self._si_v20_operator_session()
        if session is None:
            return
        try:
            payload = self.read_json_body()
            result = si_v20_shadow.SiV20ShadowService().scheduled_replay(
                payload,
                username=str(session.get("sub") or "operator"),
                role=str(session.get("role") or "operator"),
            )
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error_code": "SI_V20_SCHEDULED_REPLAY_FAILED", "error": sanitize_model_exposure(exc)}, status=503)
            return
        self.send_json(result, status=200 if result.get("ok") else 207)

    def forward_response(self, resp, content_type: str) -> None:
        data = resp.read()
        self.send_response(getattr(resp, "status", 200))
        self.add_cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self, request_path: str, request_query: str = "") -> None:
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
        is_html = target.suffix.lower() == ".html"
        response_data, content_encoding = compress_static_payload(
            data,
            content_type,
            self.headers.get("Accept-Encoding", ""),
        )
        is_hashed_asset = bool(re.search(r"-[A-Za-z0-9_-]{8,}\.", target.name))
        has_version_query = any(key in parse_qs(request_query) for key in ("v", "release"))
        etag = None
        if not is_html:
            stat = target.stat()
            encoding_tag = content_encoding or "identity"
            etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}-{encoding_tag}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.add_cors()
                self.send_header("ETag", etag)
                if is_hashed_asset:
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                else:
                    self.send_header("Cache-Control", "public, max-age=300")
                if content_encoding:
                    self.send_header("Content-Encoding", content_encoding)
                if content_type.startswith("text/") or content_type.startswith("application/"):
                    self.send_header("Vary", "Accept-Encoding")
                self.end_headers()
                return
        self.send_response(200)
        self.add_cors()
        self.send_header("Content-Type", content_type)
        if is_html:
            self.send_header("Cache-Control", "no-store")
        elif is_hashed_asset or has_version_query:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "public, max-age=300")
        if etag:
            self.send_header("ETag", etag)
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        if content_type.startswith("text/") or content_type.startswith("application/"):
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(response_data)))
        self.end_headers()
        self.wfile.write(response_data)

    def send_html(self, document: str, status: int = 200) -> None:
        data = document.encode("utf-8")
        self.send_response(status)
        self.add_cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
        request_path = urlparse(getattr(self, "path", "")).path
        origin = str(self.headers.get("Origin") or "").strip()
        host = str(self.headers.get("Host") or "").strip().lower()
        if request_path.startswith("/api/qa"):
            parsed_origin = urlparse(origin) if origin else None
            if (
                parsed_origin
                and parsed_origin.scheme in {"http", "https"}
                and parsed_origin.netloc.lower() == host
            ):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-BF-Controlled-Client")


diagnosis_ai_analysis_api.install_handler(Handler, globals())


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
    if DIAGNOSIS_AI_ANALYSIS_ENABLED:
        try:
            start_five_minute_analysis_scheduler()
            print("five-minute diagnosis AI analysis scheduler initialized")
        except Exception as exc:  # noqa: BLE001
            print(
                "five-minute diagnosis AI analysis startup failed: "
                + sanitize_model_exposure(type(exc).__name__)
            )
    server = BlastFurnaceThreadingHTTPServer((HOST, PORT), Handler)
    print(f"8092 proxy/static server: http://{HOST}:{PORT}/")
    print(f"model upstream: {OLLAMA_BASE_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
