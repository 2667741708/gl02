"""Read-only IMES MCP server for the local relay or trusted 220.12 host.

On a workstation, start tools/imes_22012_relay.py first.  On the trusted
220.12 server, set IMES_MCP_CONNECTION_MODE=direct_22012: this mode permits
all data that the connected database account can read, including arbitrary
read-only SQL.  Writes remain blocked by a read-only transaction.

Requirement: REQ-IMES-22012-RELAY-MCP-20260716
"""
from __future__ import annotations

import json
import os
import socket
import statistics
import sys
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql as pgsql
from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
import export_vastbase_local as vastbase  # noqa: E402


MCP_NAME = os.getenv("IMES_RELAY_MCP_NAME", "imes-22012-readonly-mcp")
RELAY_HOST = os.getenv("IMES_RELAY_DB_HOST", "127.0.0.1")
RELAY_PORT = int(os.getenv("IMES_RELAY_DB_PORT", "15433"))
RELAY_WEB_PORT = int(os.getenv("IMES_RELAY_WEB_PORT", "18080"))
RELAY_PSPACE_PORT = int(os.getenv("IMES_RELAY_PSPACE_PORT", "18889"))
MAX_ROWS = min(max(int(os.getenv("IMES_RELAY_MCP_MAX_ROWS", "200")), 1), 500)
MAX_DAYS = min(max(int(os.getenv("IMES_RELAY_MCP_MAX_DAYS", "93")), 1), 366)
ALLOWED_CATEGORIES = {"生产实绩", "批次投料", "炉次化验", "炉渣检验", "原料投入", "配料方案", "料仓", "生产计划"}
CONNECTION_MODE = os.getenv("IMES_MCP_CONNECTION_MODE", "relay").strip().lower()
DIRECT_22012_TARGET = ("10.10.181.195", 5432)
CHEMISTRY_ACCOUNT_PROFILE = os.getenv(
    "IMES_CHEMISTRY_ACCOUNT_PROFILE", "operations"
).strip().lower()
if CHEMISTRY_ACCOUNT_PROFILE not in {"operations", "laboratory"}:
    raise RuntimeError(
        "IMES_CHEMISTRY_ACCOUNT_PROFILE must be operations or laboratory"
    )
ACTIVE_HEAT_MAX_AGE_HOURS = max(
    1.0, float(os.getenv("IMES_ACTIVE_HEAT_MAX_AGE_HOURS", "72"))
)
HEAT_TIME_RANGE_MAX_HOURS = min(
    max(float(os.getenv("IMES_HEAT_TIME_RANGE_MAX_HOURS", "168")), 1.0),
    168.0,
)
LOCAL_IMES_ENV = ROOT / "PT" / "imes_vastbase.local.env"
FULL_VARIABLE_CATALOG_PATH = Path(__file__).with_name(
    "imes_full_variable_catalog.json"
)
ANY_QUERY_MAX_ROWS = min(
    max(int(os.getenv("IMES_MCP_ANY_QUERY_MAX_ROWS", "5000")), 1),
    50000,
)
DISCOVERY_SCHEMAS = tuple(
    value.strip()
    for value in os.getenv("IMES_MCP_DISCOVERY_SCHEMAS", "public").split(",")
    if value.strip()
)
mcp = FastMCP(MCP_NAME, json_response=True)


OBJECT_SEMANTICS = {
    "public.t_ipes_out_put": {"name": "生产实绩", "aliases": ["生产实绩", "出铁实绩", "铁量", "出铁量", "每炉铁量", "出了多少铁", "产量", "毛重", "皮重", "计量", "出库"]},
    "public.batch_input": {"name": "批次投料", "aliases": ["批次投料", "投料", "上料", "矿批", "焦批", "料批", "料仓通道"]},
    "public.t_ipes_cond": {"name": "炉次作业条件", "aliases": ["炉次条件", "炉次作业", "开炉", "堵口", "出铁时间", "批次范围", "渣比"]},
    "public.t_qpes_inner_batch": {"name": "炉次化验索引", "aliases": ["化验批号", "炉次化验索引", "取样", "判定状态", "检验批次"]},
    "public.inner_batch_insp_bb": {"name": "铁水化验结果", "aliases": ["铁水化验", "铁水成分", "硅含量", "铁水硅", "碳硅锰磷硫"]},
    "public.slag_inspection": {"name": "炉渣检验", "aliases": ["炉渣", "炉渣化验", "渣样", "渣成分", "炉渣检验"]},
    "public.v_qpes_inner_batch_insp_final_sample": {"name": "高炉铁水化验", "aliases": ["铁水成分", "炉次成分", "硅含量", "锰含量", "碳硅锰", "铁水化验"]},
    "public.v_qpes_mat_final": {"name": "原料最终化验", "aliases": ["原料化验", "物料化验", "原料成分", "物料成分", "最终化验"]},
    "public.v_qpes_slag_insoection_final": {"name": "高炉炉渣化验", "aliases": ["炉渣含量", "炉渣成分", "渣成分", "渣样", "炉渣化验"]},
    "public.v_qpes_sinter_machine_sample_insp_final": {"name": "烧结矿进料化验", "aliases": ["进料成分", "进料化学成分", "来料成分", "来料化学成分", "原料成分", "烧结矿成分", "入炉料成分"]},
    "public.v_qpes_steel_final": {"name": "炼钢最终试样", "aliases": ["炼钢化验", "钢样", "钢水成分", "炼钢成分", "最终试样"]},
}


def _field(object_name: str, field_name: str, meaning: str, aliases: list[str], confidence: str = "structural", unit: str | None = None, note: str | None = None) -> dict[str, Any]:
    return {"object": object_name, "field": field_name, "meaning": meaning, "aliases": aliases, "confidence": confidence, "unit": unit, "note": note}


SEMANTIC_FIELDS = [
    _field("public.t_ipes_out_put", "workdate", "生产/出铁业务时间", ["时间", "日期", "出铁时间"]),
    _field("public.t_ipes_out_put", "meltno", "炉次号", ["炉次", "炉号", "铁次"]),
    _field("public.t_ipes_out_put", "ironquan", "铁水量/实际铁量", ["铁量", "铁水量", "出铁量", "每炉铁量", "出了多少铁", "产量"], unit="t"),
    _field("public.t_ipes_out_put", "grossweigh", "计量毛重", ["毛重", "总重"], unit="t"),
    _field("public.t_ipes_out_put", "tareweigh", "计量皮重", ["皮重", "空罐重"], unit="t"),
    _field("public.t_ipes_out_put", "workshift", "班次", ["班次", "哪班"]),
    _field("public.t_ipes_out_put", "workclass", "班组", ["班组", "作业班组"]),
    _field("public.t_ipes_out_put", "weighttime", "称重时间", ["称重时间", "过磅时间"]),
    _field("public.batch_input", "workdate", "批次投料时间", ["投料时间", "上料时间", "日期"]),
    _field("public.batch_input", "lot", "料批/批序号", ["批次", "料批", "批号"]),
    _field("public.batch_input", "charge", "装料类别/批别", ["矿批", "焦批", "批别", "装料类别"]),
    _field("public.batch_input", "value_sum", "本批投料合计", ["投料总量", "批次合计", "总投料"], unit="源系统单位"),
    _field("public.batch_input", "mining_batch_sum", "矿批合计", ["矿批量", "矿批合计"], unit="源系统单位"),
    _field("public.batch_input", "coke_charge_sum", "焦批合计", ["焦批量", "焦炭量", "焦批合计"], unit="源系统单位"),
    _field("public.t_ipes_cond", "meltno", "炉次号", ["炉次", "炉号", "铁次"]),
    _field("public.t_ipes_cond", "sumbatchstart", "该炉次起始投料批次", ["起始批次", "从哪批开始"]),
    _field("public.t_ipes_cond", "sumbatchend", "该炉次结束投料批次", ["结束批次", "到哪批结束"]),
    _field("public.t_ipes_cond", "opentime", "开铁口时间", ["开口时间", "开铁口"]),
    _field("public.t_ipes_cond", "closetime", "堵铁口/结束时间", ["堵口时间", "关口时间", "结束时间"]),
    _field("public.t_ipes_cond", "tappingtime", "出铁持续时间", ["出铁时间", "出铁时长"]),
    _field("public.t_ipes_cond", "tappingtemp", "出铁温度", ["铁水温度", "出铁温度"], unit="℃"),
    _field("public.t_ipes_cond", "ironquan", "炉次实际铁量", ["实际铁量", "铁量"], unit="t"),
    _field("public.t_ipes_cond", "theoryquan", "炉次理论铁量", ["理论铁量", "理论产量"], unit="t"),
    _field("public.t_ipes_cond", "slagrate", "渣比", ["渣比", "炉渣比"]),
    _field("public.t_qpes_inner_batch", "heatno", "炉次号", ["炉次", "炉号", "铁次"]),
    _field("public.t_qpes_inner_batch", "batchno", "化验批号", ["化验批号", "检验批号", "样品批号"]),
    _field("public.t_qpes_inner_batch", "takesampletime", "取样时间", ["取样时间", "采样时间"]),
    _field("public.t_qpes_inner_batch", "judgetime", "化验判定时间", ["判定时间", "化验时间"]),
    _field("public.inner_batch_insp_bb", "value_01", "铁水碳 C", ["碳", "C", "碳含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_02", "铁水硅 Si", ["硅", "Si", "铁水硅", "硅含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_03", "铁水锰 Mn", ["锰", "Mn", "锰含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_04", "铁水磷 P", ["磷", "P", "磷含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_05", "铁水硫 S", ["硫", "S", "硫含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_06", "铁水钛 Ti", ["钛", "Ti", "钛含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_07", "铁水钒 V", ["钒", "V", "钒含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_08", "铁水铬 Cr", ["铬", "Cr", "铬含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_09", "铁水铜 Cu", ["铜", "Cu", "铜含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_10", "铁水镍 Ni", ["镍", "Ni", "镍含量"], "confirmed", "%"),
    _field("public.inner_batch_insp_bb", "value_11", "铁水砷 As", ["砷", "As", "砷含量"], "confirmed", "%"),
    _field("public.slag_inspection", "meltno", "炉次号", ["炉次", "炉号", "铁次"]),
    _field("public.slag_inspection", "sampleno", "炉渣试样号", ["渣样号", "试样号", "样品号"]),
    _field("public.slag_inspection", "publishtime", "炉渣检验发布时间", ["发布时间", "化验发布时间"]),
]
SEMANTIC_FIELDS.extend(
    _field("public.batch_input", f"value_{index:02d}", f"第 {index} 号料仓/称量通道投料值", [f"{index}号料仓", f"通道{index}", f"第{index}仓"], "structural", "源系统单位", "不是化学元素")
    for index in range(1, 25)
)
SEMANTIC_FIELDS.extend(
    _field("public.slag_inspection", f"value_{index:02d}", f"炉渣检验指标 {index:02d}", [f"炉渣指标{index}", f"渣value_{index:02d}"], "unknown", None, "缺少化验室字段字典，禁止猜测具体成分")
    for index in range(1, 13)
)


@lru_cache(maxsize=1)
def full_variable_catalog() -> dict[str, Any]:
    """Load the generated 315-field semantic catalog used by the MCP."""

    if not FULL_VARIABLE_CATALOG_PATH.is_file():
        return {
            "version": "fallback",
            "object_count": len({item["object"] for item in SEMANTIC_FIELDS}),
            "entry_count": len(SEMANTIC_FIELDS),
            "entries": [dict(item) for item in SEMANTIC_FIELDS],
        }
    payload = json.loads(FULL_VARIABLE_CATALOG_PATH.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(
            f"invalid IMES variable catalog: {FULL_VARIABLE_CATALOG_PATH}"
        )
    required = {"account_profile", "object", "field", "meaning", "aliases"}
    for index, item in enumerate(entries):
        if not isinstance(item, dict) or not required.issubset(item):
            raise RuntimeError(
                f"invalid IMES variable catalog entry at index {index}"
            )
    return payload


@lru_cache(maxsize=1)
def semantic_field_catalog() -> tuple[dict[str, Any], ...]:
    """Return generated fields enriched with legacy unit metadata."""

    legacy = {
        (item["object"].lower(), item["field"].lower()): item
        for item in SEMANTIC_FIELDS
    }
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in full_variable_catalog()["entries"]:
        item = dict(source)
        key = (str(item["object"]).lower(), str(item["field"]).lower())
        old = legacy.get(key, {})
        item["aliases"] = list(
            dict.fromkeys([*item.get("aliases", []), *old.get("aliases", [])])
        )
        if old.get("unit") and not item.get("unit"):
            item["unit"] = old["unit"]
        if old.get("note") and not item.get("note"):
            item["note"] = old["note"]
        merged.append(item)
        seen.add(key)
    for source in SEMANTIC_FIELDS:
        key = (source["object"].lower(), source["field"].lower())
        if key not in seen:
            merged.append(dict(source))
    return tuple(merged)


def validate_connection_target() -> None:
    """Allow relay loopback, or the one direct database endpoint on 220.12."""

    if CONNECTION_MODE == "relay":
        if RELAY_HOST not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("relay mode requires a loopback IMES_RELAY_DB_HOST")
        return
    if CONNECTION_MODE == "direct_22012" and (RELAY_HOST, RELAY_PORT) == DIRECT_22012_TARGET:
        return
    raise RuntimeError("unsupported IMES MCP connection mode or database target")


def is_direct_22012_mode() -> bool:
    return CONNECTION_MODE == "direct_22012"


READONLY_SQL_START = {"select", "with", "show", "explain", "values", "table"}
READONLY_SQL_BLOCKED = re.compile(
    r"\b(?:insert|update|delete|merge|create|alter|drop|grant|revoke|truncate|copy|call|do|set|reset|vacuum|analyze|lock|commit|rollback)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(statement: str) -> str:
    """Accept one query statement while preventing transaction escape or writes."""

    normalized = statement.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if not normalized or ";" in normalized:
        raise ValueError("exactly one read-only SQL statement is required")
    first = normalized.split(None, 1)[0].lower()
    if first not in READONLY_SQL_START or READONLY_SQL_BLOCKED.search(normalized):
        raise ValueError("only read-only query SQL is allowed")
    return normalized


def parse_date(value: str) -> str:
    """Validate the MCP's business-date input."""

    return date.fromisoformat(value).isoformat()


def bounded_range(start_date: str, end_date: str) -> tuple[str, str]:
    """Validate a non-reversed, bounded business-date interval."""

    start = date.fromisoformat(parse_date(start_date))
    end = date.fromisoformat(parse_date(end_date))
    if end < start:
        raise ValueError("end_date must not be before start_date")
    if not is_direct_22012_mode() and (end - start).days > MAX_DAYS:
        raise ValueError(f"date range must not exceed {MAX_DAYS} days")
    return start.isoformat(), end.isoformat()


def bounded_limit(limit: int | None) -> int:
    """Clamp results so MCP calls cannot accidentally dump the database."""

    value = (0 if is_direct_22012_mode() else MAX_ROWS) if limit is None else int(limit)
    if is_direct_22012_mode():
        if value < 0:
            raise ValueError("limit must be >= 0")
        return value
    if value < 1:
        raise ValueError("limit must be >= 1")
    return min(value, MAX_ROWS)


def _read_local_env(path: Path = LOCAL_IMES_ENV) -> dict[str, str]:
    """Read the approved local credential file without logging its values."""

    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value
    return values


def database_profiles() -> dict[str, dict[str, Any]]:
    """Return configured read-only database profiles, including account purpose."""

    local_values = _read_local_env()
    common_host = RELAY_HOST
    common_port = RELAY_PORT
    common_database = os.getenv("IMES_RELAY_DB_NAME", "vastbase")
    # The current authorized Vastbase account is lg_fq and is stored in the
    # protected local env file.  Keep the historical credential only as a
    # compatibility fallback for an older remote deployment that explicitly
    # has no IMES_DB_* settings; never prefer it on the workstation.
    common_user = os.getenv("IMES_DB_USER", local_values.get("IMES_DB_USER", ""))
    common_password = os.getenv(
        "IMES_DB_PASSWORD", local_values.get("IMES_DB_PASSWORD", "")
    )
    return {
        "operations": {
            "purpose": "炉次作业、生产实绩、批次投料、铁水旧化验和炉渣旧检验",
            "host": os.getenv("IMES_OPS_DB_HOST", common_host),
            "port": int(os.getenv("IMES_OPS_DB_PORT", str(common_port))),
            "dbname": os.getenv("IMES_OPS_DB_NAME", common_database),
            "user": os.getenv(
                "IMES_OPS_DB_USER", common_user or vastbase.HISTORICAL_DB_USER
            ),
            "password": os.getenv(
                "IMES_OPS_DB_PASSWORD", common_password or vastbase.HISTORICAL_DB_PASSWORD
            ),
        },
        "laboratory": {
            "purpose": "铁水、原料/烧结矿、炉渣和炼钢最终化验视图",
            "host": os.getenv("IMES_LAB_DB_HOST", common_host),
            "port": int(os.getenv("IMES_LAB_DB_PORT", str(common_port))),
            "dbname": os.getenv(
                "IMES_LAB_DB_NAME",
                local_values.get("IMES_DB_NAME", common_database),
            ),
            "user": os.getenv(
                "IMES_LAB_DB_USER", common_user
            ),
            "password": os.getenv(
                "IMES_LAB_DB_PASSWORD", common_password
            ),
        },
    }


def normalize_profile(account_profile: str | None) -> str:
    """Validate an MCP-visible profile name without accepting raw credentials."""

    profile = str(account_profile or "operations").strip().lower()
    if profile not in database_profiles():
        raise ValueError(
            "unknown account_profile; use operations or laboratory"
        )
    return profile


def safe_profile_summary(profile: str, config: dict[str, Any]) -> dict[str, Any]:
    """Describe one account without returning its password."""

    return {
        "account_profile": profile,
        "purpose": config["purpose"],
        "configured": bool(config.get("user") and config.get("password")),
        "database_user": config.get("user"),
        "database": config.get("dbname"),
        "host": config.get("host"),
        "port": config.get("port"),
        "password_exposed": False,
    }


def connection(account_profile: str = "operations") -> psycopg.Connection:
    """Open a read-only transaction through the approved endpoint."""

    validate_connection_target()
    profile = normalize_profile(account_profile)
    config = database_profiles()[profile]
    if not config.get("user") or not config.get("password"):
        raise RuntimeError(f"database profile {profile} is not configured")
    if (config["host"], int(config["port"])) != (RELAY_HOST, RELAY_PORT):
        raise RuntimeError(
            "database profile target must match the approved MCP endpoint"
        )
    conn = psycopg.connect(
        host=config["host"],
        port=int(config["port"]),
        dbname=config["dbname"],
        user=config["user"],
        password=config["password"],
        connect_timeout=10,
        options="-c statement_timeout=30000",
    )
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
    return conn


def plain(value: Any) -> Any:
    """Make PostgreSQL values safe for JSON responses."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def bounded_any_query_limit(limit: int | None) -> int:
    """Bound one MCP response while allowing callers to page through any data."""

    value = 500 if limit is None else int(limit)
    if value < 1:
        raise ValueError("row_limit must be >= 1")
    return min(value, ANY_QUERY_MAX_ROWS)


def cursor_rows(
    cur: psycopg.Cursor[Any], row_limit: int
) -> tuple[list[str], list[dict[str, Any]], bool]:
    """Read one bounded result set and report whether more rows exist."""

    if cur.description is None:
        return [], [], False
    columns = [description[0] for description in cur.description]
    fetched = cur.fetchmany(row_limit + 1)
    truncated = len(fetched) > row_limit
    rows = [
        dict(zip(columns, map(plain, row)))
        for row in fetched[:row_limit]
    ]
    return columns, rows, truncated


def _semantic_term_score(text: str, term: Any) -> int:
    """Score one term while preventing numeric identifiers from cross-matching."""

    candidate = re.sub(r"\s+", "", str(term or "")).lower()
    if not candidate:
        return 0
    pattern = "".join(
        rf"(?<!\d){re.escape(part)}(?!\d)"
        if part.isdigit()
        else re.escape(part)
        for part in re.split(r"(\d+)", candidate)
        if part
    )
    if re.search(pattern, text):
        return 8
    return 4 if text in candidate else 0


def semantic_matches(query: str, object_name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Rank all generated Chinese meanings/aliases for a colloquial query."""

    text = re.sub(r"\s+", "", str(query or "")).lower()
    if not text:
        raise ValueError("query must not be empty")
    normalized_object = str(object_name or "").strip().lower()
    matches: list[tuple[int, dict[str, Any]]] = []
    for item in semantic_field_catalog():
        if normalized_object and item["object"].lower() != normalized_object:
            continue
        terms = [item["field"], item["meaning"], *item["aliases"]]
        score = sum(_semantic_term_score(text, term) for term in terms)
        object_meta = OBJECT_SEMANTICS.get(item["object"], {})
        score += sum(2 for alias in object_meta.get("aliases", []) if alias.lower() in text)
        if score:
            matches.append((score, item))
    return [dict(item, score=score) for score, item in sorted(matches, key=lambda pair: (-pair[0], pair[1]["object"], pair[1]["field"]))[: max(1, min(int(limit), 100))]]


def resolve_semantic_intent(question: str) -> dict[str, Any]:
    """Resolve common process-language intent without guessing unknown fields."""

    text = re.sub(r"\s+", "", str(question or "")).lower()
    if not text:
        raise ValueError("question must not be empty")
    object_scores: list[tuple[int, str]] = []
    for object_name, meta in OBJECT_SEMANTICS.items():
        score = sum(5 for alias in meta["aliases"] if alias.lower() in text)
        if score:
            object_scores.append((score, object_name))
    fields = semantic_matches(text, limit=10)
    if fields:
        object_scores.append((fields[0]["score"], fields[0]["object"]))
    selected = sorted(object_scores, reverse=True)[0][1] if object_scores else None
    is_bf2 = any(term in text for term in ("2#", "2号炉", "二号炉", "2高炉", "2号高炉"))
    if any(term in text for term in ("炉渣", "渣样", "渣成分")):
        specialized_tool = "query_blast_furnace_slag_by_heat"
    elif any(term in text for term in ("进料成分", "进料化学成分", "来料成分", "来料化学成分", "原料成分", "烧结矿成分", "入炉料成分")):
        specialized_tool = "query_sinter_feed_chemistry"
    elif any(term in text for term in ("铁水", "炉次成分", "硅含量", "锰含量", "碳硅锰", "硅和锰", "硅、锰", "si", "mn")):
        specialized_tool = "query_heat_chemistry"
    else:
        specialized_tool = "query_imes_variables"
    next_arguments: dict[str, Any] = {}
    if selected and specialized_tool == "query_imes_variables":
        selected_score = max(
            (
                int(item["score"])
                for item in fields
                if item["object"] == selected
            ),
            default=0,
        )
        selected_fields = [
            item["field"]
            for item in fields
            if item["object"] == selected
            and int(item["score"]) == selected_score
        ]
        selected_meta = next(
            (item for item in fields if item["object"] == selected),
            {},
        )
        next_arguments = {
            "account_profile": selected_meta.get(
                "account_profile", "operations"
            ),
            "object_name": selected,
            "variables": list(dict.fromkeys(selected_fields)),
        }
        if selected_meta.get("time_field"):
            next_arguments["time_column"] = selected_meta["time_field"]
    return {
        "ok": bool(selected),
        "question": question,
        "resolved_object": selected,
        "object_meaning": OBJECT_SEMANTICS.get(selected or "", {}).get("name"),
        "matched_fields": fields,
        "furnace_filter": "2#" if is_bf2 else None,
        "recommended_tool": specialized_tool if selected else "search_imes_variables",
        "next_arguments": next_arguments,
        "note": None if selected else "未可靠识别对象，请先调用 search_imes_variables 或 list_imes_business_objects",
    }


def discover_selectable_objects(
    cur: psycopg.Cursor[Any],
) -> tuple[vastbase.DbObject, ...]:
    """Discover only relations with SELECT privilege, without probing all catalog rows."""

    cur.execute(
        """
        SELECT t.table_schema, t.table_name, t.table_type,
               c.column_name, c.ordinal_position
          FROM information_schema.tables t
          JOIN information_schema.columns c
            ON c.table_schema = t.table_schema
           AND c.table_name = t.table_name
         WHERE t.table_schema = ANY(%s)
           AND has_table_privilege(
                 quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),
                 'SELECT'
               )
         ORDER BY t.table_schema, t.table_name, c.ordinal_position
        """,
        (list(DISCOVERY_SCHEMAS),),
    )
    grouped = vastbase.group_catalog_rows(cur.fetchall())
    return tuple(
        vastbase.DbObject(
            schema=schema,
            name=name,
            object_type=object_type,
            category=vastbase.classify_object(schema, name, columns),
            columns=columns,
            date_column=vastbase.choose_date_column(columns),
            selectable=True,
        )
        for schema, name, object_type, columns in grouped
    )


@lru_cache(maxsize=8)
def selectable_mes_objects(
    account_profile: str = "operations",
) -> tuple[vastbase.DbObject, ...]:
    """Discover every object the selected database account can actually read."""

    profile = normalize_profile(account_profile)
    with connection(profile) as conn:
        with conn.cursor() as cur:
            return discover_selectable_objects(cur)


def object_by_name(
    object_name: str, account_profile: str = "operations"
) -> vastbase.DbObject:
    """Resolve a request only against objects readable by the selected account."""

    normalized = str(object_name or "").strip().lower()
    for item in selectable_mes_objects(normalize_profile(account_profile)):
        if item.qualified_name.lower() == normalized:
            return item
    raise ValueError("object is not selectable by the connected IMES database account")


def tcp_ok(port: int) -> bool:
    """Check the loopback listener without sending credentials."""

    try:
        with socket.create_connection((RELAY_HOST, port), timeout=2):
            return True
    except OSError:
        return False


@mcp.tool()
def imes_relay_status() -> dict[str, Any]:
    """Return 220.12 relay health without exposing credentials or tunnels externally."""

    payload: dict[str, Any] = {
        "ok": False,
        "read_policy": "readonly",
        "connection_mode": CONNECTION_MODE,
        "loopback_only": RELAY_HOST in {"127.0.0.1", "localhost", "::1"},
        "relay": {
            "vastbase_tcp": tcp_ok(RELAY_PORT),
            "imes_web_tcp": tcp_ok(RELAY_WEB_PORT),
            "pspace_tcp": tcp_ok(RELAY_PSPACE_PORT),
        },
        "max_rows": None if is_direct_22012_mode() else MAX_ROWS,
        "max_days": None if is_direct_22012_mode() else MAX_DAYS,
        "any_query_max_rows": ANY_QUERY_MAX_ROWS,
        "profiles": [],
    }
    if not payload["relay"]["vastbase_tcp"]:
        payload["message"] = "Vastbase endpoint is unavailable; start the local relay or check the approved 220.12 target."
        return payload
    for profile, config in database_profiles().items():
        status = safe_profile_summary(profile, config)
        if not status["configured"]:
            status["ok"] = False
            status["error"] = "profile_not_configured"
            payload["profiles"].append(status)
            continue
        try:
            with connection(profile) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT current_database(), current_user, "
                        "current_setting('transaction_read_only')"
                    )
                    database, user, read_only = cur.fetchone()
            status.update(
                {
                    "ok": True,
                    "database": database,
                    "database_user": user,
                    "transaction_read_only": read_only,
                    "catalog_objects": len(selectable_mes_objects(profile)),
                }
            )
        except Exception as exc:  # credentials are never added to our exception text
            status["ok"] = False
            status["error"] = type(exc).__name__
        payload["profiles"].append(status)
    payload["ok"] = bool(payload["profiles"]) and all(
        item.get("ok") for item in payload["profiles"]
    )
    if not payload["ok"]:
        payload["message"] = "one or more IMES database profiles are unavailable"
    return payload


@mcp.tool()
def list_imes_database_profiles() -> dict[str, Any]:
    """List configured account purposes without ever returning passwords."""

    return {
        "ok": True,
        "read_policy": "readonly",
        "profiles": [
            safe_profile_summary(profile, config)
            for profile, config in database_profiles().items()
        ],
    }


@mcp.tool()
def list_imes_business_objects(
    account_profile: str = "operations",
) -> dict[str, Any]:
    """List every object actually selectable by the chosen database account."""

    profile = normalize_profile(account_profile)
    objects = selectable_mes_objects(profile)
    return {
        "ok": True,
        "read_policy": "readonly",
        "account_profile": profile,
        "objects": [
            {
                "object": item.qualified_name,
                "type": item.object_type,
                "category": item.category,
                "date_column": item.date_column,
                "columns": list(item.columns),
            }
            for item in objects
        ],
        "not_exposed": [],
        "not_exposed_reason": (
            "Objects absent from this list are not SELECT-readable by the "
            "chosen database account."
        ),
    }


@mcp.tool()
def search_imes_variables(query: str, object_name: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Search field meanings and colloquial aliases such as 铁量、硅、堵口时间."""

    return {"ok": True, "query": query, "object": object_name, "matches": semantic_matches(query, object_name, limit)}


@mcp.tool()
def explain_imes_variable(object_name: str, field_name: str) -> dict[str, Any]:
    """Explain a field and state whether its business meaning is confirmed."""

    for item in semantic_field_catalog():
        if item["object"].lower() == object_name.lower() and item["field"].lower() == field_name.lower():
            return {"ok": True, **item}
    return {"ok": False, "object": object_name, "field": field_name, "meaning": "尚无已登记语义", "confidence": "unknown", "note": "请提供 IMES/化验室字段字典后登记，不能依据编号猜测"}


@mcp.tool()
def resolve_imes_natural_language(question: str) -> dict[str, Any]:
    """Turn a colloquial IMES question into an object/field/tool recommendation."""

    return resolve_semantic_intent(question)


@mcp.tool()
def query_imes_object(
    object_name: str,
    start_date: str,
    end_date: str,
    limit: int | None = None,
    account_profile: str = "operations",
) -> dict[str, Any]:
    """Read a bounded date range from one selectable IMES business object."""

    start_date, end_date = bounded_range(start_date, end_date)
    limit = bounded_limit(limit)
    profile = normalize_profile(account_profile)
    item = object_by_name(object_name, profile)
    query, params = vastbase.build_export_query(item, start_date, end_date, limit)
    with connection(profile) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [description[0] for description in cur.description]
            rows = [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]
    return {
        "ok": True,
        "read_policy": "readonly",
        "account_profile": profile,
        "object": item.qualified_name,
        "category": item.category,
        "date_column": item.date_column,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "rows": rows,
        "truncated": limit > 0 and len(rows) >= limit,
    }


@mcp.tool()
def query_imes_readonly_sql(
    sql: str,
    account_profile: str = "operations",
    parameters: list[Any] | None = None,
    row_limit: int | None = None,
) -> dict[str, Any]:
    """Execute one arbitrary read-only SQL query through either account profile."""

    profile = normalize_profile(account_profile)
    statement = validate_readonly_sql(str(sql or ""))
    result_limit = bounded_any_query_limit(row_limit)
    with connection(profile) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, tuple(parameters or ()))
            columns, rows, truncated = cursor_rows(cur, result_limit)
    return {
        "ok": True,
        "read_policy": "readonly",
        "account_profile": profile,
        "columns": columns,
        "rows": rows,
        "row_limit": result_limit,
        "truncated": truncated,
    }


@mcp.tool()
def query_imes_variables(
    object_name: str,
    variables: list[str],
    account_profile: str = "operations",
    time_column: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    exact_filters: dict[str, Any] | None = None,
    order_by: str | None = None,
    descending: bool = False,
    row_limit: int | None = None,
) -> dict[str, Any]:
    """Read selected variables with an optional [start_time, end_time) window."""

    profile = normalize_profile(account_profile)
    item = object_by_name(object_name, profile)
    by_lower = {column.lower(): column for column in item.columns}
    requested = [str(value).strip() for value in variables]
    if not requested:
        raise ValueError("variables must contain at least one column")
    unknown = [value for value in requested if value.lower() not in by_lower]
    if unknown:
        raise ValueError(f"unknown variables for {item.qualified_name}: {unknown}")
    selected = [by_lower[value.lower()] for value in requested]
    filters = exact_filters or {}
    unknown_filters = [
        value for value in filters if str(value).lower() not in by_lower
    ]
    if unknown_filters:
        raise ValueError(
            f"unknown exact_filters for {item.qualified_name}: {unknown_filters}"
        )
    has_any_time = any(value is not None for value in (time_column, start_time, end_time))
    if has_any_time and not all(
        value is not None for value in (time_column, start_time, end_time)
    ):
        raise ValueError(
            "time_column, start_time and end_time must be provided together"
        )
    resolved_time_column: str | None = None
    if time_column is not None:
        resolved_time_column = by_lower.get(str(time_column).lower())
        if resolved_time_column is None:
            raise ValueError(
                f"unknown time_column for {item.qualified_name}: {time_column}"
            )
        if str(start_time) >= str(end_time):
            raise ValueError("start_time must be earlier than end_time")
    resolved_order: str | None = None
    if order_by:
        resolved_order = by_lower.get(str(order_by).lower())
        if resolved_order is None:
            raise ValueError(
                f"unknown order_by for {item.qualified_name}: {order_by}"
            )
    result_limit = bounded_any_query_limit(row_limit)
    statement = pgsql.SQL("SELECT {} FROM {}").format(
        pgsql.SQL(", ").join(pgsql.Identifier(column) for column in selected),
        pgsql.Identifier(item.schema, item.name),
    )
    where_parts: list[pgsql.Composed] = []
    params: list[Any] = []
    if resolved_time_column is not None:
        where_parts.append(
            pgsql.SQL("{} >= %s AND {} < %s").format(
                pgsql.Identifier(resolved_time_column),
                pgsql.Identifier(resolved_time_column),
            )
        )
        params.extend([start_time, end_time])
    for field_name, value in filters.items():
        resolved_field = by_lower[str(field_name).lower()]
        if value is None:
            where_parts.append(
                pgsql.SQL("{} IS NULL").format(pgsql.Identifier(resolved_field))
            )
        else:
            where_parts.append(
                pgsql.SQL("{} = %s").format(pgsql.Identifier(resolved_field))
            )
            params.append(value)
    if where_parts:
        statement += pgsql.SQL(" WHERE ") + pgsql.SQL(" AND ").join(where_parts)
    if resolved_order:
        statement += pgsql.SQL(" ORDER BY {} {}").format(
            pgsql.Identifier(resolved_order),
            pgsql.SQL("DESC" if descending else "ASC"),
        )
    statement += pgsql.SQL(" LIMIT %s")
    params.append(result_limit + 1)
    with connection(profile) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            columns, rows, truncated = cursor_rows(cur, result_limit)
    return {
        "ok": True,
        "read_policy": "readonly",
        "account_profile": profile,
        "object": item.qualified_name,
        "variables": selected,
        "time_window": {
            "column": resolved_time_column,
            "start_inclusive": start_time,
            "end_exclusive": end_time,
        }
        if resolved_time_column
        else None,
        "exact_filters": filters,
        "columns": columns,
        "rows": rows,
        "row_limit": result_limit,
        "truncated": truncated,
    }


@mcp.tool()
def query_hot_metal_silicon(
    start_date: str,
    end_date: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Read published 2# furnace hot-metal chemistry, including Si, by batch/heat."""

    start_date, end_date = bounded_range(start_date, end_date)
    limit = bounded_limit(limit)
    end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
    query = """
        SELECT b.batchno, b.heatno, b.judgetime,
               e.publishtime, e.takesampletime, e.prodcentercode,
               e.value_01 AS c, e.value_02 AS si, e.value_03 AS mn,
               e.value_04 AS p, e.value_05 AS s, e.value_06 AS ti,
               e.value_07 AS v, e.value_08 AS cr, e.value_09 AS cu,
               e.value_10 AS ni, e.value_11 AS as
          FROM public.t_qpes_inner_batch b
          JOIN public.inner_batch_insp_bb e ON e.batchno = b.batchno
         WHERE b.judgetime >= %s
           AND b.judgetime < %s
           AND b.heatno LIKE '2#%%'
         ORDER BY b.judgetime, b.batchno
    """
    params: list[Any] = [start_date, end_exclusive]
    if limit > 0:
        query += " LIMIT %s"
        params.append(limit)
    # The verified 2026-08-05 production path reads the current Web-visible
    # chemistry rows through the operations profile. The profile remains
    # configurable for deployments that explicitly provision a laboratory
    # account; the model never chooses an arbitrary account.
    with connection(CHEMISTRY_ACCOUNT_PROFILE) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [description[0] for description in cur.description]
            rows = [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]
    return {
        "ok": True,
        "read_policy": "readonly",
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "si_field": "si",
        "account_profile": CHEMISTRY_ACCOUNT_PROFILE,
        "rows": rows,
        "truncated": limit > 0 and len(rows) >= limit,
    }


def _required_text(value: str, name: str, max_length: int = 80) -> str:
    """Validate a short business identifier used only as a query parameter."""

    normalized = str(value or "").strip()
    if not normalized or len(normalized) > max_length:
        raise ValueError(f"{name} must be a non-empty value no longer than {max_length} characters")
    return normalized


def _normalize_furnace_id(value: str) -> str:
    """Normalize a furnace identifier without allowing it to become SQL syntax."""

    normalized = str(value or "2#").strip().upper().replace("号", "#")
    if normalized.isdigit():
        normalized += "#"
    if not re.fullmatch(r"\d{1,3}#", normalized):
        raise ValueError("furnace_id must look like '2#' or '2'")
    return normalized


def _normalize_as_of_time(value: str | None) -> datetime:
    """Return a database-friendly local timestamp used as the heat ordering anchor."""

    if value is None or not str(value).strip():
        return datetime.now().astimezone().replace(tzinfo=None, microsecond=0)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of_time must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _plain_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _query_recent_heat_context_rows(
    as_of_time: datetime,
    furnace_id: str,
    limit: int = 2,
) -> list[dict[str, Any]]:
    query = """
        SELECT meltno, workdate, opentime, closetime, tappingtime,
               tappingtemp, ironquan, theoryquan, slagrate
          FROM public.t_ipes_cond
         WHERE meltno LIKE %s
            AND COALESCE(opentime, workdate) <= %s
          ORDER BY COALESCE(opentime, workdate) DESC NULLS LAST,
                   meltno DESC
         LIMIT %s
    """
    with connection("operations") as conn:
        with conn.cursor() as cur:
            cur.execute(query, (f"{furnace_id}%", as_of_time, limit))
            columns = [item[0] for item in cur.description]
            return [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]


def _query_hot_metal_chemistry_rows(heat_no: str) -> list[dict[str, Any]]:
    query = """
        SELECT b.heatno, b.batchno, b.judgetime, e.publishtime, e.takesampletime,
               e.prodcentercode, e.value_01 AS c, e.value_02 AS si,
               e.value_03 AS mn, e.value_04 AS p, e.value_05 AS s,
               e.value_06 AS ti, e.value_07 AS v, e.value_08 AS cr,
               e.value_09 AS cu, e.value_10 AS ni, e.value_11 AS arsenic
          FROM public.t_qpes_inner_batch b
          JOIN public.inner_batch_insp_bb e ON e.batchno = b.batchno
         WHERE b.heatno = %s
         ORDER BY b.judgetime DESC NULLS LAST, b.batchno DESC
    """
    # Use the verified chemistry profile for the exact official heat join;
    # production context is resolved separately from operations data.
    with connection(CHEMISTRY_ACCOUNT_PROFILE) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (heat_no,))
            columns = [item[0] for item in cur.description]
            rows = [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]
    tank_numbers = _query_tank_numbers_by_batchnos(
        [str(row.get("batchno") or "") for row in rows]
    )
    for row in rows:
        row["tank_no"] = tank_numbers.get(str(row.get("batchno") or ""))
    return rows


def _query_tank_numbers_by_batchnos(batchnos: list[str]) -> dict[str, Any]:
    """Return exact batch-to-tank mappings without failing chemistry queries.

    The verified label contract permits only ``batchno -> thankno`` exact
    joins. Missing permissions or missing mappings are represented by an
    empty mapping; a sample number is never relabelled as a tank number.

    Requirement: REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807.
    """

    values = list(dict.fromkeys(value for value in batchnos if value))
    if not values:
        return {}
    placeholders = ", ".join(["%s"] * len(values))
    query = f"""
        SELECT DISTINCT ON (batchno) batchno, thankno
          FROM public.v_qpes_mat_final
         WHERE batchno IN ({placeholders})
         ORDER BY batchno, publishtime DESC NULLS LAST
    """
    try:
        with connection(CHEMISTRY_ACCOUNT_PROFILE) as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                tank_rows = cur.fetchall()
    except Exception:
        return {}
    return {
        str(batchno): plain(tank_no)
        for batchno, tank_no in tank_rows
        if batchno is not None and tank_no not in (None, "")
    }


@mcp.tool()
def get_current_heat_context(
    as_of_time: str | None = None,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Return the current/latest-known and previous official MES heat numbers."""

    furnace_id = _normalize_furnace_id(furnace_id)
    anchor = _normalize_as_of_time(as_of_time)
    rows = _query_recent_heat_context_rows(anchor, furnace_id, limit=2)
    current = rows[0] if rows else None
    previous = rows[1] if len(rows) > 1 else None
    open_time = _plain_datetime(current.get("opentime")) if current else None
    close_time = _plain_datetime(current.get("closetime")) if current else None
    age_hours = (
        (anchor - open_time).total_seconds() / 3600.0
        if open_time is not None and open_time <= anchor
        else None
    )
    active = bool(
        current
        and open_time
        and open_time <= anchor
        and (close_time is None or close_time > anchor)
        and (age_hours is None or age_hours <= ACTIVE_HEAT_MAX_AGE_HOURS)
    )
    # Build heat_time_window for cross-source DAG argument_bindings
    current_heat_time_window = None
    if current:
        c_open = _plain_datetime(current.get("opentime")) or _plain_datetime(current.get("workdate"))
        c_close = _plain_datetime(current.get("closetime"))
        if c_open:
            current_heat_time_window = {
                "start": c_open.isoformat(),
                "end": c_close.isoformat() if c_close else None,
            }

    return {
        "ok": True,
        "read_policy": "readonly",
        "furnace_id": furnace_id,
        "as_of_time": anchor.isoformat(timespec="seconds"),
        "status": "active" if active else "latest_known",
        "current_heat_no": current.get("meltno") if current else None,
        "previous_heat_no": previous.get("meltno") if previous else None,
        "current_heat": current,
        "previous_heat": previous,
        "heat_time_window": current_heat_time_window,
        "missing": not rows,
        "source_object": "public.t_ipes_cond",
        "quality": {
            "official_meltno": True,
            "ordering_field": "COALESCE(opentime, workdate) DESC, meltno DESC",
            "selection_policy": "latest_official_meltno_before_anchor",
            "active_max_age_hours": ACTIVE_HEAT_MAX_AGE_HOURS,
            "previous_available": previous is not None,
        },
    }


@mcp.tool()
def get_current_previous_heat_si_summary(
    as_of_time: str | None = None,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Resolve the current heat and summarize all valid Si samples of its previous heat."""

    furnace_id = _normalize_furnace_id(furnace_id)
    anchor = _normalize_as_of_time(as_of_time)
    heat_rows = _query_recent_heat_context_rows(anchor, furnace_id, limit=2)
    current = heat_rows[0] if heat_rows else None
    previous = heat_rows[1] if len(heat_rows) > 1 else None
    if previous is None:
        return {
            "ok": False,
            "error": "PREVIOUS_HEAT_NOT_FOUND",
            "message": "MES炉次作业条件中未找到当前时点之前的两个正式炉次。",
            "furnace_id": furnace_id,
            "as_of_time": anchor.isoformat(timespec="seconds"),
            "current_heat_no": current.get("meltno") if current else None,
            "source_object": "public.t_ipes_cond",
        }
    previous_heat_no = str(previous.get("meltno") or "")
    chemistry_rows = _query_hot_metal_chemistry_rows(previous_heat_no)
    valid_samples: list[dict[str, Any]] = []
    for row in chemistry_rows:
        try:
            si_value = float(row.get("si"))
        except (TypeError, ValueError):
            continue
        valid_samples.append(
            {
                "batchno": row.get("batchno"),
                "si": si_value,
                "takesampletime": row.get("takesampletime"),
                "publishtime": row.get("publishtime"),
                "judgetime": row.get("judgetime"),
            }
        )
    si_values = [sample["si"] for sample in valid_samples]
    # Build heat_time_window for cross-source DAG argument_bindings
    prev_heat_time_window = None
    if previous:
        p_open = _plain_datetime(previous.get("opentime")) or _plain_datetime(previous.get("workdate"))
        p_close = _plain_datetime(previous.get("closetime"))
        if p_open:
            prev_heat_time_window = {
                "start": p_open.isoformat(),
                "end": p_close.isoformat() if p_close else None,
            }

    return {
        "ok": True,
        "read_policy": "readonly",
        "furnace_id": furnace_id,
        "as_of_time": anchor.isoformat(timespec="seconds"),
        "current_heat_no": current.get("meltno") if current else None,
        "previous_heat_no": previous_heat_no,
        "heat_time_window": prev_heat_time_window,
        "sample_count": len(valid_samples),
        "si_values": si_values,
        "si_avg": statistics.fmean(si_values) if si_values else None,
        "si_min": min(si_values) if si_values else None,
        "si_max": max(si_values) if si_values else None,
        "samples": valid_samples,
        "sample_times": [
            sample.get("takesampletime") or sample.get("publishtime") or sample.get("judgetime")
            for sample in valid_samples
        ],
        "missing": not valid_samples,
        "error_code": "NO_SI_SAMPLES" if not valid_samples else None,
        "unit": "%",
        "source_objects": ["public.t_ipes_cond", "public.t_qpes_inner_batch", "public.inner_batch_insp_bb"],
        "account_profiles": {
            "heat_context": "operations",
            "chemistry": CHEMISTRY_ACCOUNT_PROFILE,
        },
        "quality": {
            "official_meltno": True,
            "aggregation": "arithmetic_mean_of_non_null_numeric_si_samples",
            "sample_time_preference": ["takesampletime", "publishtime", "judgetime"],
        },
    }


def _resolve_spoken_heat_reference_core(
    heat_reference: str,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Pure resolution logic shared by MCP tool and internal callers.

    Returns a standardised heat-reference dict.  This function is NOT an
    MCP tool — it is called by resolve_spoken_heat_reference (the tool)
    and can also be imported by the proxy plan builder for regex-only
    fast-path resolution.
    """
    import re as _re

    ref = str(heat_reference or "").strip()
    if not ref:
        return {
            "requested_heat_reference": ref,
            "resolved_heat_no": None,
            "resolution_policy": "invalid",
            "error_code": "HEAT_REFERENCE_EMPTY",
            "heat_context_missing": True,
            "heat_time_window": None,
        }

    furnace_id = _normalize_furnace_id(furnace_id)

    # Rule 1: full formal format  "2#20260805-072"
    full_match = _re.fullmatch(r"(\d{1,3}#)(\d{8}-\d{3,4})", ref)
    if full_match:
        resolved = ref
        return {
            "requested_heat_reference": ref,
            "resolved_heat_no": resolved,
            "resolution_policy": "exact",
            "error_code": None,
            "heat_context_missing": False,
            "heat_time_window": None,
        }

    # Rule 2: date-prefix without furnace  "20260805-072"
    date_match = _re.fullmatch(r"(\d{8}-\d{3,4})", ref)
    if date_match:
        resolved = f"{furnace_id}{ref}"
        return {
            "requested_heat_reference": ref,
            "resolved_heat_no": resolved,
            "resolution_policy": "exact_with_prefix",
            "error_code": None,
            "heat_context_missing": False,
            "heat_time_window": None,
        }

    # Rule 3: spoken short form  "072" — requires database lookup
    short_match = _re.fullmatch(r"(\d{2,4})", ref)
    if short_match:
        suffix = short_match.group(1)
        # Query recent heats matching this suffix within 72 hours
        cutoff = datetime.now().astimezone().replace(tzinfo=None) - timedelta(hours=72)
        query = """
            SELECT meltno, opentime, closetime, workdate
              FROM public.t_ipes_cond
             WHERE meltno LIKE %s
               AND COALESCE(opentime, workdate) >= %s
             ORDER BY COALESCE(opentime, workdate) DESC, meltno DESC
        """
        try:
            with connection("operations") as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (f"%{suffix}", cutoff))
                    rows = cur.fetchall()
        except Exception as exc:
            return {
                "requested_heat_reference": ref,
                "resolved_heat_no": None,
                "resolution_policy": "spoken_72h_lookup",
                "error_code": "HEAT_REFERENCE_LOOKUP_ERROR",
                "heat_context_missing": True,
                "heat_time_window": None,
                "lookup_error": str(exc),
            }

        if not rows:
            return {
                "requested_heat_reference": ref,
                "resolved_heat_no": None,
                "resolution_policy": "spoken_72h_lookup",
                "error_code": "HEAT_REFERENCE_NOT_FOUND",
                "heat_context_missing": True,
                "heat_time_window": None,
                "candidates_found": 0,
            }

        if len(rows) > 1:
            return {
                "requested_heat_reference": ref,
                "resolved_heat_no": None,
                "resolution_policy": "spoken_72h_lookup",
                "error_code": "HEAT_REFERENCE_AMBIGUOUS",
                "heat_context_missing": True,
                "heat_time_window": None,
                "candidates_found": len(rows),
                "candidates": [row[0] for row in rows[:10]],
            }

        # Unique match
        resolved = rows[0][0]
        open_time = _plain_datetime(rows[0][1]) if rows[0][1] else _plain_datetime(rows[0][3])
        close_time = _plain_datetime(rows[0][2]) if len(rows[0]) > 2 and rows[0][2] else None

        return {
            "requested_heat_reference": ref,
            "resolved_heat_no": resolved,
            "resolution_policy": "spoken_72h_unique_match",
            "error_code": None,
            "heat_context_missing": False,
            "heat_time_window": {
                "start": open_time.isoformat() if open_time else None,
                "end": close_time.isoformat() if close_time else None,
            },
            "candidates_found": 1,
        }

    # Unrecognised format
    return {
        "requested_heat_reference": ref,
        "resolved_heat_no": None,
        "resolution_policy": "unrecognised",
        "error_code": "HEAT_REFERENCE_FORMAT_UNRECOGNISED",
        "heat_context_missing": True,
        "heat_time_window": None,
    }


@mcp.tool()
def resolve_spoken_heat_reference(
    heat_reference: str,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Resolve a spoken or short-form heat reference to an official meltno.

    Rules (in order):
    1. ``2#20260805-072`` — exact formal format, used as-is.
    2. ``20260805-072`` — auto-prefixed with furnace_id.
    3. ``072`` — 72-hour lookup on COALESCE(opentime, workdate); unique
       match only.  Zero matches → HEAT_REFERENCE_NOT_FOUND; multiple →
       HEAT_REFERENCE_AMBIGUOUS.
    4. Anything else → HEAT_REFERENCE_FORMAT_UNRECOGNISED.

    This tool is called deterministically by the proxy plan builder; the
    model does NOT need to discover it.
    """
    return _resolve_spoken_heat_reference_core(heat_reference, furnace_id)


def _query_heat_context_for_chemistry(heat_no: str) -> dict[str, Any]:
    """Fetch opentime/closetime for a resolved heat so the snapshot can
    populate heat_time_window even when the caller used an exact heat_no."""
    query = """
        SELECT opentime, closetime, workdate
          FROM public.t_ipes_cond
         WHERE meltno = %s
         LIMIT 1
    """
    try:
        with connection("operations") as conn:
            with conn.cursor() as cur:
                cur.execute(query, (heat_no,))
                row = cur.fetchone()
    except Exception:
        return {"heat_context_missing": True, "heat_time_window": None}

    if not row:
        return {"heat_context_missing": True, "heat_time_window": None}

    open_time = _plain_datetime(row[0]) if row[0] else _plain_datetime(row[2])
    close_time = _plain_datetime(row[1]) if row[1] else None
    return {
        "heat_context_missing": False,
        "heat_time_window": {
            "start": open_time.isoformat() if open_time else None,
            "end": close_time.isoformat() if close_time else None,
        },
    }


@mcp.tool()
def query_hot_metal_chemistry_by_heat(
    heat_no: str,
    as_of_time: str | None = None,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Query one blast-furnace heat's published hot-metal chemistry.

    Accepts exact formal meltno, date-prefix, or spoken short form.
    Spoken short forms (e.g. ``072``) are resolved via the same 72-hour
    lookup used by resolve_spoken_heat_reference.
    """

    heat_no = _required_text(heat_no, "heat_no")

    # Resolve the heat reference
    resolution = _resolve_spoken_heat_reference_core(heat_no, furnace_id)
    resolved = resolution.get("resolved_heat_no")
    error_code = resolution.get("error_code")

    if error_code and error_code != "HEAT_REFERENCE_EMPTY":
        # Unresolvable — return the resolution metadata without chemistry rows
        return {
            "ok": False,
            "read_policy": "readonly",
            "requested_heat_no": heat_no,
            "resolved_heat_no": None,
            "resolution_policy": resolution["resolution_policy"],
            "error_code": error_code,
            "heat_context_missing": True,
            "heat_time_window": None,
            "account_profile": CHEMISTRY_ACCOUNT_PROFILE,
            "unit": "% (subject to laboratory dictionary)",
            "rows": [],
            "missing": True,
        }

    rows = _query_hot_metal_chemistry_rows(resolved)
    ctx = _query_heat_context_for_chemistry(resolved)

    return {
        "ok": True,
        "read_policy": "readonly",
        "requested_heat_no": heat_no,
        "resolved_heat_no": resolved,
        "resolution_policy": resolution["resolution_policy"],
        "heat_context_missing": ctx["heat_context_missing"],
        "heat_time_window": ctx["heat_time_window"],
        "account_profile": CHEMISTRY_ACCOUNT_PROFILE,
        "unit": "% (subject to laboratory dictionary)",
        "rows": rows,
        "missing": not rows,
        "note": (
            "No direct hot-metal Fe percentage is exposed. "
            "'铁量/出了多少铁' must use the production-output tool, not this chemistry result."
        ),
    }


CHEMISTRY_COMPONENT_FIELDS: dict[str, str] = {
    "c": "c",
    "si": "si",
    "mn": "mn",
    "p": "p",
    "s": "s",
    "ti": "ti",
    "v": "v",
    "cr": "cr",
    "cu": "cu",
    "ni": "ni",
    "as": "arsenic",
}

CHEMISTRY_COMPONENT_ALIASES: dict[str, str] = {
    "c": "c", "碳": "c", "碳含量": "c",
    "si": "si", "硅": "si", "硅含量": "si",
    "mn": "mn", "锰": "mn", "锰含量": "mn",
    "p": "p", "磷": "p", "磷含量": "p",
    "s": "s", "硫": "s", "硫含量": "s",
    "ti": "ti", "钛": "ti", "钛含量": "ti",
    "v": "v", "钒": "v", "钒含量": "v",
    "cr": "cr", "铬": "cr", "铬含量": "cr",
    "cu": "cu", "铜": "cu", "铜含量": "cu",
    "ni": "ni", "镍": "ni", "镍含量": "ni",
    "as": "as", "arsenic": "as", "砷": "as", "砷含量": "as",
}


def _normalize_chemistry_components(components: list[str] | None) -> list[str]:
    """Normalize a model/user component list to the fixed laboratory fields."""

    if components is None:
        return list(CHEMISTRY_COMPONENT_FIELDS)
    if not isinstance(components, list) or not components:
        raise ValueError("components must be a non-empty array when provided")
    if len(components) > len(CHEMISTRY_COMPONENT_FIELDS):
        raise ValueError("components contains too many entries")
    normalized: list[str] = []
    for raw in components:
        key = re.sub(r"\s+", "", str(raw or "")).lower()
        component = CHEMISTRY_COMPONENT_ALIASES.get(key)
        if component is None:
            allowed = ", ".join(CHEMISTRY_COMPONENT_FIELDS)
            raise ValueError(f"unsupported chemistry component {raw!r}; allowed: {allowed}")
        if component not in normalized:
            normalized.append(component)
    return normalized


def _chemistry_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _chemistry_summary(
    rows: list[dict[str, Any]], components: list[str]
) -> dict[str, dict[str, Any]]:
    """Build stable per-component facts without treating missing values as zero."""

    summary: dict[str, dict[str, Any]] = {}
    for component in components:
        field = CHEMISTRY_COMPONENT_FIELDS[component]
        values = [
            value
            for row in rows
            if (value := _chemistry_number(row.get(field))) is not None
        ]
        summary[component] = {
            "count": len(values),
            "avg": round(statistics.fmean(values), 6) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "latest": values[0] if values else None,
            "unit": "%",
            "missing": not values,
        }
    return summary


@mcp.tool()
def query_heat_chemistry(
    heat_reference: str,
    components: list[str] | None = None,
    include_samples: bool = True,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Query selected hot-metal components for any one official heat.

    This is the preferred model-facing tool for questions such as
    ``065炉的硅锰是多少`` or ``2#20260805-065的C/Si/Mn/P/S``.  It accepts
    a formal meltno, a date-prefixed heat number, or a 2-4 digit spoken heat
    suffix.  The tool resolves the heat reference itself, so callers must not
    call the resolver first.  ``components`` accepts C, Si, Mn, P, S, Ti, V,
    Cr, Cu, Ni and As (English symbols or Chinese names).
    """

    requested_components = _normalize_chemistry_components(components)
    base = query_hot_metal_chemistry_by_heat(
        heat_no=heat_reference,
        furnace_id=furnace_id,
    )
    if not base.get("ok"):
        return {
            **base,
            "tool_contract": "heat_chemistry.v1",
            "source_service": "imes-readonly",
            "requested_heat_reference": heat_reference,
            "components": requested_components,
            "samples": [],
            "summary": {},
            "data_time": None,
        }

    rows = list(base.get("rows") or [])
    samples: list[dict[str, Any]] = []
    data_times: list[str] = []
    for row in rows:
        sample_time = (
            row.get("takesampletime")
            or row.get("judgetime")
            or row.get("publishtime")
        )
        sample_time_type = (
            "take_sample_time" if row.get("takesampletime")
            else "judge_time" if row.get("judgetime")
            else "publish_time" if row.get("publishtime")
            else "missing"
        )
        sample = {
            "heat_no": row.get("heatno"),
            "sample_no": row.get("batchno"),
            "tank_no": row.get("tank_no"),
            "take_sample_time": row.get("takesampletime"),
            "publish_time": row.get("publishtime"),
            "judge_time": row.get("judgetime"),
            "sample_time": sample_time,
            "sample_time_type": sample_time_type,
            "sample_time_is_actual": sample_time_type == "take_sample_time",
            "components": {
                component: _chemistry_number(
                    row.get(CHEMISTRY_COMPONENT_FIELDS[component])
                )
                for component in requested_components
            },
        }
        samples.append(sample)
        for key in ("take_sample_time", "publish_time", "judge_time"):
            if sample.get(key):
                data_times.append(str(sample[key]))

    component_summary = _chemistry_summary(rows, requested_components)
    missing_components = [
        component
        for component, item in component_summary.items()
        if item["missing"]
    ]
    return {
        "ok": True,
        "read_policy": "readonly",
        "tool_contract": "heat_chemistry.v1",
        "source_service": "imes-readonly",
        "requested_heat_reference": heat_reference,
        "resolved_heat_no": base.get("resolved_heat_no"),
        "resolution_policy": base.get("resolution_policy"),
        "heat_time_window": base.get("heat_time_window"),
        "components": requested_components,
        "unit": "%",
        "sample_count": len(rows),
        "samples": samples if include_samples else [],
        "summary": component_summary,
        "data_time": max(data_times) if data_times else None,
        "missing_components": missing_components,
        "missing": not rows,
        "error_code": "NO_CHEMISTRY_SAMPLES" if not rows else None,
    }


@mcp.tool()
def query_current_heat_chemistry(
    as_of_time: str | None = None,
    components: list[str] | None = None,
    include_samples: bool = True,
    furnace_id: str = "2#",
) -> dict[str, Any]:
    """Return all chemistry samples published so far for the current heat.

    An active heat is explicitly marked provisional. Its average is calculated
    only from non-null numeric samples available at the query time.

    Requirement: REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807.
    """

    context = get_current_heat_context(as_of_time=as_of_time, furnace_id=furnace_id)
    heat_no = context.get("current_heat_no")
    if not heat_no:
        return {
            "ok": False,
            "read_policy": "readonly",
            "tool_contract": "current_heat_chemistry.v1",
            "source_service": "imes-readonly",
            "error_code": "CURRENT_HEAT_NOT_FOUND",
            "message": "MES炉次作业条件中未找到当前或最近炉次。",
            "missing": True,
        }
    chemistry = query_heat_chemistry(
        heat_reference=str(heat_no),
        components=components,
        include_samples=include_samples,
        furnace_id=furnace_id,
    )
    active = context.get("status") == "active"
    current_heat = context.get("current_heat") or {}
    return {
        **chemistry,
        "tool_contract": "current_heat_chemistry.v1",
        "as_of_time": context.get("as_of_time"),
        "heat_status": "active" if active else "latest_known",
        "provisional": active,
        "partial_heat": active,
        "open_time": current_heat.get("opentime") or current_heat.get("workdate"),
        "close_time": current_heat.get("closetime"),
        "aggregation_scope": (
            "available_published_samples_as_of_query_time"
            if active
            else "all_currently_published_samples"
        ),
        "quality": {
            "official_meltno": True,
            "missing_values_are_not_zero": True,
            "sample_time_preference": [
                "takesampletime",
                "judgetime",
                "publishtime",
            ],
            "tank_join": "batchno_to_v_qpes_mat_final_thankno_exact",
        },
    }


def _parse_spoken_heat_time_range(
    time_reference: str,
    as_of_time: str | None = None,
) -> dict[str, Any]:
    """Parse a bounded Chinese approximate time expression for heat lookup."""

    text = _required_text(time_reference, "time_reference", max_length=300)
    anchor = _normalize_as_of_time(as_of_time)
    normalized = (
        text.replace("：", ":")
        .replace("号", "日")
        .replace("～", "到")
        .replace("~", "到")
        .replace("—", "到")
    )

    recent = re.search(r"最近\s*(\d{1,3})\s*(分钟|小时)", normalized)
    if recent:
        amount = int(recent.group(1))
        delta = timedelta(minutes=amount) if recent.group(2) == "分钟" else timedelta(hours=amount)
        start = anchor - delta
        end = anchor
        policy = "relative_recent"
    else:
        iso_datetimes = re.findall(
            r"\d{4}-\d{1,2}-\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?",
            normalized,
        )
        if len(iso_datetimes) >= 2:
            start = _normalize_as_of_time(iso_datetimes[0])
            end = _normalize_as_of_time(iso_datetimes[1])
            policy = "explicit_iso_range"
        else:
            full_date = re.search(
                r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?",
                normalized,
            )
            month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日?", normalized)
            if full_date:
                base_date = date(
                    int(full_date.group(1)),
                    int(full_date.group(2)),
                    int(full_date.group(3)),
                )
            elif month_day:
                base_date = date(
                    anchor.year,
                    int(month_day.group(1)),
                    int(month_day.group(2)),
                )
            elif any(term in normalized for term in ("前天", "前一日")):
                base_date = anchor.date() - timedelta(days=2)
            elif any(term in normalized for term in ("昨天", "昨日")):
                base_date = anchor.date() - timedelta(days=1)
            else:
                base_date = anchor.date()

            time_pattern = re.compile(
                r"(凌晨|早上|上午|中午|下午|傍晚|晚上|夜里)?\s*"
                r"(\d{1,2})(?:(?:[:](\d{1,2}))\s*|(?:点|时)\s*(半)?)"
            )
            tokens = list(time_pattern.finditer(normalized))

            def token_hour(match: re.Match[str], inherited: str | None = None) -> tuple[int, int]:
                qualifier = match.group(1) or inherited
                hour = int(match.group(2))
                minute = int(match.group(3) or (30 if match.group(4) else 0))
                if hour > 24 or minute > 59:
                    raise ValueError("time_reference contains an invalid clock time")
                if qualifier in {"中午", "下午", "傍晚", "晚上", "夜里"} and hour < 12:
                    hour += 12
                if qualifier == "凌晨" and hour == 12:
                    hour = 0
                return hour, minute

            if len(tokens) >= 2:
                inherited = tokens[0].group(1)
                first_hour, first_minute = token_hour(tokens[0])
                second_hour, second_minute = token_hour(tokens[1], inherited)
                start = datetime.combine(base_date, datetime.min.time()) + timedelta(
                    hours=first_hour, minutes=first_minute
                )
                end = datetime.combine(base_date, datetime.min.time()) + timedelta(
                    hours=second_hour, minutes=second_minute
                )
                if end <= start:
                    end += timedelta(days=1)
                policy = "spoken_clock_range"
            elif len(tokens) == 1:
                hour, minute = token_hour(tokens[0])
                center = datetime.combine(base_date, datetime.min.time()) + timedelta(
                    hours=hour, minutes=minute
                )
                approximate = any(
                    term in normalized
                    for term in ("左右", "大概", "前后", "附近", "那会", "那一阵")
                )
                start = center - timedelta(hours=1) if approximate else center
                end = center + timedelta(hours=1)
                policy = "spoken_approximate_clock" if approximate else "spoken_one_hour_window"
            else:
                periods = (
                    (("凌晨",), 0, 6),
                    (("早上", "上午"), 6, 12),
                    (("中午",), 11, 14),
                    (("下午",), 12, 18),
                    (("傍晚",), 17, 20),
                    (("晚上", "夜里"), 18, 24),
                )
                matched = next(
                    (
                        (start_hour, end_hour)
                        for terms, start_hour, end_hour in periods
                        if any(term in normalized for term in terms)
                    ),
                    None,
                )
                day_start = datetime.combine(base_date, datetime.min.time())
                if matched:
                    start = day_start + timedelta(hours=matched[0])
                    end = day_start + timedelta(hours=matched[1])
                    policy = "spoken_day_period"
                elif (
                    full_date
                    or month_day
                    or any(term in normalized for term in ("今天", "今日", "昨天", "昨日", "前天", "前一日"))
                ):
                    start = day_start
                    end = day_start + timedelta(days=1)
                    policy = "spoken_whole_day"
                else:
                    raise ValueError("无法从 time_reference 识别日期或时间段")

    if end <= start:
        raise ValueError("time range end must be after start")
    hours = (end - start).total_seconds() / 3600.0
    if hours > HEAT_TIME_RANGE_MAX_HOURS:
        raise ValueError(
            f"time range exceeds {HEAT_TIME_RANGE_MAX_HOURS:g} hours"
        )
    return {
        "requested": text,
        "start": start.replace(microsecond=0).isoformat(),
        "end": end.replace(microsecond=0).isoformat(),
        "resolution_policy": policy,
        "duration_hours": round(hours, 3),
        "anchor": anchor.isoformat(timespec="seconds"),
    }


def _query_heat_context_rows_near_range(
    start: datetime,
    end: datetime,
    furnace_id: str,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Return nearby official heats for overlap and nearest-window ranking."""

    query = """
        SELECT meltno, workdate, opentime, closetime, tappingtime,
               tappingtemp, ironquan, theoryquan, slagrate
          FROM public.t_ipes_cond
         WHERE meltno LIKE %s
           AND (
                (opentime IS NOT NULL AND opentime >= %s AND opentime < %s)
                OR (workdate >= %s AND workdate < %s)
           )
         ORDER BY workdate, meltno
         LIMIT %s
    """
    search_start = start - timedelta(hours=12)
    search_end = end + timedelta(hours=12)
    with connection("operations") as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    f"{furnace_id}%",
                    search_start,
                    search_end,
                    search_start.date(),
                    search_end.date() + timedelta(days=1),
                    limit,
                ),
            )
            columns = [item[0] for item in cur.description]
            return [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]


def _resolve_heat_times_for_range(
    heat: dict[str, Any],
) -> tuple[datetime | None, datetime | None, str, list[str]]:
    """Resolve trusted heat times without treating workdate midnight as opening.

    ``meltno`` and ``workdate`` are identity/date anchors.  A non-null
    ``opentime`` still supplies the time of day.  When both date anchors agree,
    the open/close dates are rebuilt from workdate so known MES future-date and
    cross-midnight defects follow the same contract as the aggregate repair.
    """

    raw_open = _plain_datetime(heat.get("opentime"))
    raw_close = _plain_datetime(heat.get("closetime"))
    if raw_open is None:
        return None, None, "missing_opentime", ["opentime_missing"]

    work_value = _plain_datetime(heat.get("workdate"))
    melt_match = re.search(r"#(\d{8})-", str(heat.get("meltno") or ""))
    melt_date: date | None = None
    if melt_match:
        try:
            melt_date = datetime.strptime(melt_match.group(1), "%Y%m%d").date()
        except ValueError:
            melt_date = None

    reasons: list[str] = []
    if work_value is None or melt_date is None or work_value.date() != melt_date:
        if work_value is not None and melt_date is not None:
            reasons.append("workdate_meltno_date_mismatch")
        return raw_open, raw_close, "raw_time_unrepaired", reasons

    resolved_open = datetime.combine(work_value.date(), raw_open.time())
    resolved_close = None
    if raw_close is not None:
        close_date = work_value.date()
        if raw_close.time() < raw_open.time():
            close_date += timedelta(days=1)
            reasons.append("closetime_rollover_next_day")
        resolved_close = datetime.combine(close_date, raw_close.time())
    if raw_open.date() != resolved_open.date():
        reasons.append("opentime_date_rebased_to_workdate")
    if raw_close is not None and raw_close.date() != resolved_close.date():
        reasons.append("closetime_date_rebased_to_workdate")
    status = "time_anomaly_repaired" if reasons else "exact"
    return resolved_open, resolved_close, status, sorted(set(reasons))


def _rank_heat_for_time_range(
    heat: dict[str, Any],
    start: datetime,
    end: datetime,
    anchor: datetime,
) -> dict[str, Any] | None:
    """Calculate overlap and midpoint distance for one official heat."""

    open_time, close_time, time_status, time_repair_reasons = (
        _resolve_heat_times_for_range(heat)
    )
    if open_time is None:
        return None
    effective_close = close_time or (
        anchor if open_time <= anchor else open_time + timedelta(hours=4)
    )
    if effective_close < open_time:
        effective_close = open_time
    overlap_start = max(start, open_time)
    overlap_end = min(end, effective_close)
    overlap_minutes = max(
        0.0, (overlap_end - overlap_start).total_seconds() / 60.0
    )
    query_mid = start + (end - start) / 2
    heat_mid = open_time + (effective_close - open_time) / 2
    distance_minutes = abs((heat_mid - query_mid).total_seconds()) / 60.0
    return {
        "heat": heat,
        "open_time": open_time,
        "close_time": close_time,
        "overlap_minutes": round(overlap_minutes, 3),
        "midpoint_distance_minutes": round(distance_minutes, 3),
        "match_kind": "overlap" if overlap_minutes > 0 else "nearest",
        "time_status": time_status,
        "time_repair_reasons": time_repair_reasons,
    }


@mcp.tool()
def query_heat_chemistry_by_time_range(
    time_reference: str,
    components: list[str] | None = None,
    include_samples: bool = True,
    as_of_time: str | None = None,
    furnace_id: str = "2#",
    heat_limit: int = 12,
) -> dict[str, Any]:
    """Resolve an approximate time range to official heats and chemistry.

    The result contains every overlapping heat within the bounded limit. If
    no heat overlaps, the nearest official heat is returned and marked
    nearest, so the user can confirm the inferred heat before relying on it.

    Requirement: REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807.
    """

    furnace_id = _normalize_furnace_id(furnace_id)
    requested_components = _normalize_chemistry_components(components)
    resolved_range = _parse_spoken_heat_time_range(time_reference, as_of_time)
    start = _normalize_as_of_time(resolved_range["start"])
    end = _normalize_as_of_time(resolved_range["end"])
    anchor = _normalize_as_of_time(as_of_time)
    limit = min(max(int(heat_limit), 1), 24)
    nearby = _query_heat_context_rows_near_range(
        start,
        end,
        furnace_id,
        limit=24,
    )
    ranked = [
        item
        for heat in nearby
        if (item := _rank_heat_for_time_range(heat, start, end, anchor)) is not None
    ]
    ranked.sort(
        key=lambda item: (
            0 if item["overlap_minutes"] > 0 else 1,
            -item["overlap_minutes"],
            item["midpoint_distance_minutes"],
        )
    )
    overlapping = [item for item in ranked if item["overlap_minutes"] > 0]
    selected = (overlapping or ranked[:1])[:limit]

    heats: list[dict[str, Any]] = []
    for item in selected:
        heat = item["heat"]
        heat_no = str(heat.get("meltno") or "")
        chemistry = query_heat_chemistry(
            heat_reference=heat_no,
            components=requested_components,
            include_samples=include_samples,
            furnace_id=furnace_id,
        )
        heats.append(
            {
                "heat_no": heat_no,
                "match_kind": item["match_kind"],
                "overlap_minutes": item["overlap_minutes"],
                "midpoint_distance_minutes": item["midpoint_distance_minutes"],
                "open_time": item["open_time"].isoformat(),
                "close_time": (
                    item["close_time"].isoformat()
                    if item["close_time"] is not None
                    else None
                ),
                "active_or_unclosed": item["close_time"] is None,
                "time_status": item["time_status"],
                "time_repair_reasons": item["time_repair_reasons"],
                "chemistry": chemistry,
            }
        )

    return {
        "ok": True,
        "read_policy": "readonly",
        "tool_contract": "heat_chemistry_time_range.v1",
        "source_service": "imes-readonly",
        "furnace_id": furnace_id,
        "time_range": resolved_range,
        "primary_heat_no": heats[0]["heat_no"] if heats else None,
        "matched_heat_count": len(heats),
        "heats": heats,
        "missing": not heats,
        "error_code": "HEAT_NOT_FOUND_FOR_TIME_RANGE" if not heats else None,
        "selection_policy": "all_overlaps_else_nearest_heat_midpoint",
        "truncated": len(selected) >= limit and len(ranked) > limit,
    }




@mcp.tool()
def query_blast_furnace_slag_by_heat(heat_no: str) -> dict[str, Any]:
    """Query named slag constituents and ratios for one exact blast-furnace heat."""

    heat_no = _required_text(heat_no, "heat_no")
    query = """
        SELECT sampleno, meltno, prodcentercode, publishtime,
               tfe, feo, cao, mgo, sio2, al2o3, tio2,
               r2, r3, r4, mgo_al2o3, sio2_al2o3
          FROM public.v_qpes_slag_insoection_final
         WHERE meltno = %s
         ORDER BY publishtime DESC NULLS LAST, sampleno DESC
    """
    with connection("laboratory") as conn:
        with conn.cursor() as cur:
            cur.execute(query, (heat_no,))
            columns = [item[0] for item in cur.description]
            rows = [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]
    return {"ok": True, "read_policy": "readonly", "heat_no": heat_no, "rows": rows, "missing": not rows,
            "note": "A heat may have multiple slag samples. Empty values are missing, never zero."}


@mcp.tool()
def query_sinter_feed_chemistry(
    start_date: str,
    end_date: str,
    machine: str | None = None,
    sample_no: str | None = None,
    limit: int | None = 50,
) -> dict[str, Any]:
    """Query sinter-feed chemistry by business date, machine and optional sample number."""

    start_date, end_date = bounded_range(start_date, end_date)
    end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
    limit = bounded_limit(limit)
    clauses = ['"业务日期" >= %s', '"业务日期" < %s']
    params: list[Any] = [start_date, end_exclusive]
    if machine:
        clauses.append('("加工中心编码" = %s OR "加工中心名称" ILIKE %s)')
        machine = _required_text(machine, "machine")
        params.extend((machine, f"%{machine}%"))
    if sample_no:
        clauses.append('("试样单号" = %s OR "检验批号" = %s)')
        sample_no = _required_text(sample_no, "sample_no")
        params.extend((sample_no, sample_no))
    query = f"""
        SELECT "试样单号", "业务日期", "检验批号", "加工中心编码", "加工中心名称",
               "发布时间", tfevalue, caovalue, mgovalue, sio2value, al2o3value,
               pvalue, tio2value, mnovalue, znvalue, crvalue, r2value,
               feovalue, svalue, mgalvalue, alsivalue, qdvalue
          FROM public.v_qpes_sinter_machine_sample_insp_final
         WHERE {' AND '.join(clauses)}
         ORDER BY "发布时间" DESC NULLS LAST, "试样单号" DESC
    """
    if limit > 0:
        query += " LIMIT %s"
        params.append(limit)
    with connection("laboratory") as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [item[0] for item in cur.description]
            rows = [dict(zip(columns, map(plain, row))) for row in cur.fetchall()]
    return {"ok": True, "read_policy": "readonly", "start_date": start_date, "end_date": end_date,
            "machine": machine, "sample_no": sample_no, "rows": rows, "missing": not rows,
            "note": "This is sinter chemistry, not a calculated whole-heat burden chemistry."}


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
