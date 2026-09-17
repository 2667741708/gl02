from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import sys
import uuid
import warnings
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from business_object_catalog import (
    get_catalog_object,
    list_catalog_objects,
    load_business_object_catalog,
    search_catalog_objects,
)


logging.basicConfig(stream=sys.stderr, level=os.getenv("BF_MCP_LOG_LEVEL", "INFO"))
logger = logging.getLogger("bf_data_mcp")

MCP_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = MCP_DIR.parent
FRONTEND_DIR = ASSISTANT_DIR.parent
PROJECT_ROOT = FRONTEND_DIR.parent

DEFAULT_MAPPING_PATH = PROJECT_ROOT / "趋势分析" / "trend_backend" / "config" / "gl02_sio_mapping.json"
DEFAULT_STATIC_PRESSURE_EXTENSION_PATH = MCP_DIR / "gl02_static_pressure_points.json"
DEFAULT_SEMANTIC_POINT_CATALOG_PATH = PROJECT_ROOT / "数据库同步和存取" / "config" / "点位语义目录.json"
DEFAULT_STORAGE_CONFIG = PROJECT_ROOT / "趋势分析" / "trend_backend" / "config" / "gl02_1min_storage.json"
DEFAULT_REPORTS_DIR = FRONTEND_DIR / "data" / "reports"
DEFAULT_CHARTS_DIR = FRONTEND_DIR / "data" / "mcp_charts"
DEFAULT_PSPACE_SDK_ROOT = PROJECT_ROOT / "pythonSDK(1)"
DEFAULT_PSPACE_CONFIG = PROJECT_ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml"
BACKEND_DIR = ASSISTANT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from assistant_pg import ensure_assistant_schema, raw_pg_connect, schema_name  # noqa: E402

GL02_MAPPING_PATH = Path(os.getenv("BF_GL02_MAPPING_PATH", str(DEFAULT_MAPPING_PATH)))
GL02_STORAGE_CONFIG = Path(os.getenv("BF_GL02_STORAGE_CONFIG", str(DEFAULT_STORAGE_CONFIG)))
REPORTS_DIR = Path(os.getenv("BF_REPORTS_DIR", str(DEFAULT_REPORTS_DIR))).resolve()


def resolve_static_chart_location(configured_dir: str | Path) -> tuple[Path, str]:
    candidate = Path(configured_dir).resolve()
    try:
        relative = candidate.relative_to(FRONTEND_DIR)
    except ValueError:
        candidate = DEFAULT_CHARTS_DIR.resolve()
        relative = candidate.relative_to(FRONTEND_DIR)
    return candidate, "/" + relative.as_posix().strip("/")


CHARTS_DIR, CHARTS_URL_PREFIX = resolve_static_chart_location(
    os.getenv("BF_MCP_CHARTS_DIR", str(DEFAULT_CHARTS_DIR))
)

MCP_NAME = os.getenv("BF_MCP_NAME", "blast-furnace-gl02-data-mcp")
FURNACE_ID = os.getenv("BF_MCP_FURNACE_ID", "GL02")
MAX_HISTORY_LIMIT = int(os.getenv("BF_MCP_MAX_HISTORY_LIMIT", "5000"))
DEFAULT_HISTORY_LIMIT = int(os.getenv("BF_MCP_DEFAULT_HISTORY_LIMIT", "500"))
FEATURE_MAX_HISTORY_LIMIT = int(os.getenv("BF_MCP_FEATURE_MAX_HISTORY_LIMIT", "50000"))
MAX_REPORT_CHARS = int(os.getenv("BF_MCP_MAX_REPORT_CHARS", "12000"))
LOCAL_TZ = ZoneInfo(os.getenv("BF_LOCAL_TZ", "Asia/Shanghai"))
DATA_SOURCE = os.getenv("BF_MCP_DATA_SOURCE", "hybrid").strip().lower()
AUTO_PSPACE_FALLBACK = os.getenv("BF_MCP_AUTO_PSPACE_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}
PSPACE_SERVER = os.getenv("PSPACE_SERVER", "10.22.181.243")
PSPACE_PORT = os.getenv("PSPACE_PORT", "8889")
def first_existing_path(candidates: list[Path]) -> Path:
    """Return the first existing runtime dependency, otherwise retain the primary path for clear errors."""
    return next((path for path in candidates if path.exists()), candidates[0])


PSPACE_SDK_ROOT = first_existing_path([
    Path(os.getenv("PSPACE_SDK_ROOT", str(DEFAULT_PSPACE_SDK_ROOT))),
    PROJECT_ROOT.parent / "高炉炼铁项目-real-sensor-v2_V3" / "pythonSDK(1)",
])
PSPACE_CONFIG = first_existing_path([
    Path(os.getenv("PSPACE_CONFIG", str(DEFAULT_PSPACE_CONFIG))),
    PROJECT_ROOT.parent / "高炉炼铁项目-real-sensor-v2_V3_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
    PROJECT_ROOT.parent / "高炉炼铁项目-real-sensor-v2_V3" / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
])
PSPACE_INTERVAL_SECONDS = int(os.getenv("BF_MCP_PSPACE_INTERVAL_SECONDS", "60"))
PSPACE_AGGREGATE = os.getenv("BF_MCP_PSPACE_AGGREGATE", "PS_HIS_AVERAGE")
PSPACE_MAX_QUERY_DAYS = float(os.getenv("BF_MCP_PSPACE_MAX_QUERY_DAYS", "93"))

mcp = FastMCP(MCP_NAME, json_response=True)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def as_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


CORE_FALLBACK_VARIABLES = [
    {
        "variable_name": "P_top",
        "aliases": ["顶压", "炉顶压力", "炉顶压", "综合顶压", "煤气顶压"],
        "status": "physical",
        "confidence": "high",
        "source_branch": "LD",
        "short_name": "SIO_GL02_LD_T0034",
        "point_id": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0034",
        "tag_long_name": r"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0034",
        "description": "2号炉炉顶_顶压平均",
        "unit": "kPa",
    },
    {
        "variable_name": "DP_total",
        "aliases": ["总压差", "全炉压差", "炉内压差", "总体压差"],
        "status": "physical",
        "confidence": "high",
        "source_branch": "BT",
        "short_name": "SIO_GL02_BT_T0132",
        "point_id": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0132",
        "tag_long_name": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0132",
        "description": "2号炉本体_全炉压差",
        "unit": "kPa",
    },
    *[
        {
            "variable_name": f"P_top_{position}",
            "aliases": [
                f"顶压{position}",
                f"{position}点顶压",
                f"顶压{position}点",
                f"{position}上升管煤气压力",
                f"上升管煤气压力{position}",
                f"P_top_gas_{position}",
            ],
            "legacy_variable_names": [f"P_top_gas_{position}"],
            "status": "physical",
            "confidence": "high",
            "source_branch": "LD",
            "short_name": f"SIO_GL02_LD_T{66 + offset:04d}",
            "point_id": rf"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T{66 + offset:04d}",
            "tag_long_name": rf"\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T{66 + offset:04d}",
            "description": f"2号炉炉顶_上升管煤气压力{position}",
            "unit": "kPa",
        }
        for offset, position in enumerate("ABCD", start=1)
    ],
]


def load_optional_json(path: Path, fallback: dict[str, Any], label: str) -> dict[str, Any]:
    """Load an optional runtime config while keeping database-backed core queries available."""

    if path.exists():
        return load_json(path)
    logger.warning("%s不存在，启用数据库核心变量兼容目录: %s", label, path)
    return fallback


MAPPING_CONFIG = load_optional_json(
    GL02_MAPPING_PATH,
    {"variables": CORE_FALLBACK_VARIABLES, "body_temperature_range": {}, "missing_or_disabled": []},
    "GL02映射文件",
)
STORAGE_CONFIG = load_optional_json(GL02_STORAGE_CONFIG, {"profiles": {}}, "GL02存储配置")
STATIC_PRESSURE_EXTENSION_PATH = Path(
    os.getenv("BF_STATIC_PRESSURE_EXTENSION_PATH", str(DEFAULT_STATIC_PRESSURE_EXTENSION_PATH))
)
SEMANTIC_POINT_CATALOG_PATH = Path(
    os.getenv("BF_SEMANTIC_POINT_CATALOG_PATH", str(DEFAULT_SEMANTIC_POINT_CATALOG_PATH))
)


def load_semantic_point_aliases(path: Path) -> dict[str, list[str]]:
    """Load generated spoken aliases without changing physical point authority."""
    if not path.exists():
        return {}
    payload = load_json(path)
    if payload.get("schema_version") != "semantic_point_catalog.v1":
        raise ValueError(f"unsupported semantic point catalog: {path}")
    return {
        str(item.get("object_id") or ""): list(item.get("semantic_aliases") or [])
        for item in payload.get("objects") or []
        if item.get("object_id")
    }


SEMANTIC_POINT_ALIASES = load_semantic_point_aliases(SEMANTIC_POINT_CATALOG_PATH)


def semantic_point_variables(path: Path) -> list[dict[str, Any]]:
    """Build a complete read-only runtime fallback from the authoritative TSV projection."""
    if not path.exists():
        return []
    payload = load_json(path)
    variables: list[dict[str, Any]] = []
    for item in payload.get("objects") or []:
        source = item.get("source") or {}
        object_id = str(item.get("object_id") or "").strip()
        point_id = str(source.get("point_id") or "").strip()
        if not object_id or not point_id:
            continue
        status_usage = str(source.get("status_usage") or "")
        unit_match = re.search(r"单位\s*([^；，,\s]+)", status_usage)
        variables.append({
            "variable_name": object_id,
            "aliases": list(item.get("semantic_aliases") or []),
            "status": "derived" if item.get("object_kind") == "derived_metric" else "physical",
            "confidence": "high" if "明确可用" in status_usage or "实测确认" in status_usage else "medium",
            "source_branch": str(source.get("branch") or ""),
            "short_name": str(source.get("short_name") or ""),
            "point_id": point_id,
            "tag_long_name": point_id,
            "description": str(source.get("description") or item.get("display_name") or object_id),
            "unit": unit_match.group(1) if unit_match else None,
        })
    return variables


def merge_variable_catalog(*catalogs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge catalog extensions by variable_name while preserving the first catalog order."""
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for catalog in catalogs:
        for item in catalog:
            variable_name = str(item.get("variable_name") or "").strip()
            if not variable_name:
                continue
            if variable_name in positions:
                merged[positions[variable_name]] = item
            else:
                positions[variable_name] = len(merged)
                merged.append(item)
    return merged


TOP_PRESSURE_LEGACY_TO_CANONICAL = {
    f"P_top_gas_{position}": f"P_top_{position}" for position in "ABCD"
}


def canonicalize_variable_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose stable top-pressure IDs while accepting the historical application aliases."""
    normalized: list[dict[str, Any]] = []
    for source in catalog:
        item = dict(source)
        legacy_name = str(item.get("variable_name") or "").strip()
        canonical_name = TOP_PRESSURE_LEGACY_TO_CANONICAL.get(legacy_name)
        if not canonical_name and re.fullmatch(r"P_top_[A-D]", legacy_name):
            canonical_name = legacy_name
        if canonical_name:
            position = canonical_name.rsplit("_", 1)[-1]
            compatibility_name = f"P_top_gas_{position}"
            item["variable_name"] = canonical_name
            item["legacy_variable_names"] = list(dict.fromkeys([
                *list(item.get("legacy_variable_names") or []),
                compatibility_name,
            ]))
            item["aliases"] = list(dict.fromkeys([
                *list(item.get("aliases") or []),
                compatibility_name,
                f"顶压{position}",
                f"{position}点顶压",
                f"顶压{position}点",
                f"{position}上升管煤气压力",
                f"上升管煤气压力{position}",
            ]))
        object_id = str(item.get("variable_name") or "").strip()
        if object_id in SEMANTIC_POINT_ALIASES:
            item["aliases"] = list(dict.fromkeys([
                *list(item.get("aliases") or []),
                *SEMANTIC_POINT_ALIASES[object_id],
            ]))
        normalized.append(item)
    return normalized


STATIC_PRESSURE_EXTENSION = (
    load_json(STATIC_PRESSURE_EXTENSION_PATH).get("variables", [])
    if STATIC_PRESSURE_EXTENSION_PATH.exists()
    else []
)
def build_body_temperature_variables() -> list[dict[str, Any]]:
    """Return the canonical 80 BT points when the optional mapping is absent."""
    variables: list[dict[str, Any]] = []
    for layer in range(7, 17):
        for offset, sector in enumerate("ABCDEFGH"):
            tag_no = 155 + (layer - 7) * 8 + offset
            short_name = f"SIO_GL02_BT_T{tag_no:04d}"
            tag = "\\" + "\u51b6\u5357\u94a2\u94c1" + "\\SIO\\GL02\\BT\\" + short_name
            variables.append({
                "variable_name": f"T_body_L{layer}_{sector}",
                "aliases": ["\u7089\u4f53\u6e29\u5ea6", "\u7089\u8eab\u6e29\u5ea6", f"{layer}\u5c42{sector}\u70b9\u6e29\u5ea6"],
                "status": "physical", "confidence": "high", "source_branch": "BT",
                "short_name": short_name, "point_id": tag, "tag_long_name": tag,
                "description": f"GL02 {layer}\u5c42{sector}\u7089\u8eab\u6e29\u5ea6", "unit": "\u2103",
            })
    return variables


VARIABLES = merge_variable_catalog(
    canonicalize_variable_catalog(CORE_FALLBACK_VARIABLES),
    canonicalize_variable_catalog(semantic_point_variables(SEMANTIC_POINT_CATALOG_PATH)),
    canonicalize_variable_catalog(MAPPING_CONFIG.get("variables", [])),
    canonicalize_variable_catalog(STATIC_PRESSURE_EXTENSION),
    canonicalize_variable_catalog(build_body_temperature_variables()),
)
BUSINESS_OBJECT_CATALOG = load_business_object_catalog(VARIABLES)
STATIC_PRESSURE_EXTENSION_VARIABLES = {
    str(item.get("variable_name") or "") for item in STATIC_PRESSURE_EXTENSION
}


def extension_source_preference(meta: dict[str, Any], requested: str | None) -> str | None:
    """Keep extension points on the standard database-first policy after catalog synchronization."""
    return requested
BODY_TEMPERATURE_RANGE = MAPPING_CONFIG.get("body_temperature_range", {})
MISSING_OR_DISABLED = MAPPING_CONFIG.get("missing_or_disabled", [])


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def parse_iso_datetime(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError("时间不能为空，应使用 ISO8601，例如 2026-05-08T08:00:00+08:00")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"时间格式应为 ISO8601，例如 2026-05-08T08:00:00+08:00: {value}") from exc
    return value


def parse_datetime_value(value: str) -> datetime:
    return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))


def validate_time_range(start_time: str, end_time: str) -> tuple[str, str]:
    start_time = parse_iso_datetime(start_time)
    end_time = parse_iso_datetime(end_time)
    start_dt = parse_datetime_value(start_time)
    end_dt = parse_datetime_value(end_time)
    if start_dt > end_dt:
        raise ValueError(f"start_time 不能晚于 end_time: {start_time} > {end_time}")
    return start_time, end_time


def local_time_text(value: str) -> str:
    dt = parse_datetime_value(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def clamp_limit(limit: int | None, default: int = DEFAULT_HISTORY_LIMIT, maximum: int = MAX_HISTORY_LIMIT) -> int:
    try:
        value = int(limit if limit is not None else default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def public_variable(v: dict[str, Any]) -> dict[str, Any]:
    tag = v.get("tag_long_name") or ""
    return {
        "variable_name": v.get("variable_name", ""),
        "legacy_variable_names": v.get("legacy_variable_names", []),
        "aliases": v.get("aliases", []),
        "status": v.get("status", ""),
        "confidence": v.get("confidence", ""),
        "source_branch": v.get("source_branch", ""),
        "path_group": v.get("source_branch", ""),
        "short_name": v.get("short_name", ""),
        "point_id": v.get("point_id") or tag,
        "tag_long_name": tag,
        "tag": tag,
        "description": v.get("description", ""),
        "unit": v.get("unit", ""),
        "usage": v.get("usage", ""),
        "notes": v.get("notes", ""),
        "max_history_range": v.get("max_history_range") or {"status": "未探明"},
    }


def public_body_temperature_range() -> dict[str, Any]:
    return {
        "variable_name": BODY_TEMPERATURE_RANGE.get("variable_pattern", "T_body_L{layer}_{sector}"),
        "status": BODY_TEMPERATURE_RANGE.get("status", "available"),
        "confidence": BODY_TEMPERATURE_RANGE.get("confidence", "high"),
        "source_branch": BODY_TEMPERATURE_RANGE.get("source_branch", "BT"),
        "path_group": BODY_TEMPERATURE_RANGE.get("source_branch", "BT"),
        "short_name": BODY_TEMPERATURE_RANGE.get("short_name_range", "SIO_GL02_BT_T0155..SIO_GL02_BT_T0234"),
        "point_id": "炉体温度变量族：请指定层号 7..16 与方位 A..H",
        "tag_long_name": "",
        "tag": "",
        "description": "2号炉 7-16 层 A-H 炉体温度变量族",
        "unit": "",
        "usage": BODY_TEMPERATURE_RANGE.get("usage", ""),
        "notes": "这是变量族，不是单一测点。查询实时值或历史值时请指定具体层号和方位，例如 7层A 炉体温度。",
        "max_history_range": {"status": "未探明"},
    }


def body_temperature_variable_from_text(text: str) -> dict[str, Any] | None:
    raw = str(text or "")
    match = re.search(r"(?P<layer>7|8|9|10|11|12|13|14|15|16)\s*层\s*(?P<sector>[A-Ha-h])", raw)
    if match:
        layer = int(match.group("layer"))
        sector = match.group("sector").upper()
    else:
        symbolic = re.fullmatch(r"(?i)t_body_l(?P<layer>7|8|9|10|11|12|13|14|15|16)_(?P<sector>[a-h])", raw.strip())
        if symbolic:
            layer = int(symbolic.group("layer"))
            sector = symbolic.group("sector").upper()
        else:
            tag_match = re.search(r"(?i)SIO_GL02_BT_T(?P<num>0?1[5-9][5-9]|0?2[0-2][0-9]|0?23[0-4])", raw)
            if tag_match:
                tag_no = int(tag_match.group("num"))
                if 155 <= tag_no <= 234:
                    offset = tag_no - 155
                    layer = 7 + offset // 8
                    sector = chr(ord("A") + offset % 8)
                else:
                    return None
            else:
                if "炉体温度" not in raw and "炉身温度" not in raw:
                    return None
                return None
    offset = (layer - 7) * 8 + (ord(sector) - ord("A"))
    tag_no = 155 + offset
    short_name = f"SIO_GL02_BT_T{tag_no:04d}"
    tag = f"\\冀南钢铁\\SIO\\GL02\\BT\\{short_name}"
    return {
        "variable_name": f"T_body_L{layer}_{sector}",
        "status": "available",
        "confidence": "high",
        "source_branch": "BT",
        "short_name": short_name,
        "point_id": tag,
        "tag_long_name": tag,
        "description": f"2号炉本体_{layer}层{sector}炉体温度",
        "usage": BODY_TEMPERATURE_RANGE.get("usage", ""),
        "unit": "",
    }


def public_missing_variable(v: dict[str, Any]) -> dict[str, Any]:
    name = v.get("variable_name", "")
    return {
        "variable_name": name,
        "status": v.get("status", "missing"),
        "confidence": "missing",
        "source_branch": "",
        "path_group": "",
        "short_name": "",
        "point_id": "",
        "tag_long_name": "",
        "tag": "",
        "description": v.get("reason", ""),
        "unit": "",
        "usage": v.get("handling", ""),
        "notes": v.get("reason", ""),
        "max_history_range": {"status": "不可用", "reason": v.get("reason", "")},
    }


def variable_fields(v: dict[str, Any]) -> list[str]:
    return [
        v.get("variable_name", ""),
        v.get("short_name", ""),
        v.get("point_id", ""),
        v.get("tag_long_name", ""),
        v.get("description", ""),
        v.get("usage", ""),
        v.get("source_branch", ""),
        *list(v.get("legacy_variable_names") or []),
        *list(v.get("aliases") or []),
    ]


def variable_score(keyword: str, v: dict[str, Any]) -> float:
    q = normalize_text(keyword)
    if not q:
        return 0.0
    fields = [normalize_text(x) for x in variable_fields(v) if normalize_text(x)]
    if any(q == field for field in fields):
        return 1.0
    if any(q in field for field in fields):
        return 0.92
    if any(field in q for field in fields if len(field) >= 3):
        return 0.78
    return max((SequenceMatcher(None, q, field).ratio() for field in fields), default=0.0)


def search_variables(keyword: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        limit = int(limit or 10)
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))
    q = normalize_text(keyword)
    matches: list[dict[str, Any]] = []
    body_point = body_temperature_variable_from_text(str(keyword or ""))
    if body_point:
        item = public_variable(body_point)
        item["score"] = 1.0
        matches.append(item)
    for missing in MISSING_OR_DISABLED:
        fields = [
            missing.get("variable_name", ""),
            missing.get("status", ""),
            missing.get("reason", ""),
            missing.get("handling", ""),
        ]
        score = 0.0
        norm_fields = [normalize_text(x) for x in fields if normalize_text(x)]
        if q == "精确顶温" and "精确 t_top" in normalize_text(missing.get("variable_name", "")):
            score = 0.98
        elif any(q == f for f in norm_fields):
            score = 1.0
        elif any(q in f or f in q for f in norm_fields):
            score = 0.96
        else:
            score = max((SequenceMatcher(None, q, f).ratio() for f in norm_fields), default=0.0)
        if score >= 0.35:
            item = public_missing_variable(missing)
            item["score"] = round(score, 4)
            matches.append(item)
    if "炉体温度" in q or "炉身温度" in q:
        item = public_body_temperature_range()
        item["score"] = 0.99
        matches.append(item)
    for v in VARIABLES:
        if ("炉体温度" in q or "炉身温度" in q) and v.get("variable_name") == "T_blast":
            continue
        score = variable_score(keyword, v)
        if score >= 0.18:
            item = public_variable(v)
            item["score"] = round(score, 4)
            matches.append(item)
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:limit]


def resolve_variable(variable: str) -> dict[str, Any]:
    q = normalize_text(variable)
    if not q:
        raise ValueError("变量名不能为空")
    body_point = body_temperature_variable_from_text(str(variable or ""))
    if body_point:
        return body_point

    for v in VARIABLES:
        if any(q == normalize_text(field) for field in variable_fields(v)):
            return v

    if "炉体温度" in q or "炉身温度" in q:
        raise ValueError("炉体温度是 7-16 层 A-H 的变量族，请指定具体层号和方位，例如 7层A 炉体温度。")

    # Canonical identifiers are machine contracts. Never fuzzy-map an unknown
    # identifier (for example DP_totl) to another valid point such as P_top.
    if re.fullmatch(r"[a-z][a-z0-9_]*", q):
        raise ValueError(f"未找到变量: {variable}")

    for missing in MISSING_OR_DISABLED:
        missing_name = normalize_text(missing.get("variable_name", ""))
        missing_terms = {
            missing_name,
            "煤气利用率" if missing_name == "gasutil" else "",
            "南尺" if missing_name == "l_south" else "",
            "南探尺" if missing_name == "l_south" else "",
            "北尺" if missing_name == "l_north" else "",
            "北探尺" if missing_name == "l_north" else "",
            "精确顶温" if "t_top" in missing_name else "",
        }
        if q not in {term for term in missing_terms if term}:
            continue
        raise ValueError(
            f"变量 {missing.get('variable_name')} 当前状态为 {missing.get('status')}，"
            f"原因：{missing.get('reason')}；处理方式：{missing.get('handling')}"
        )

    matches = search_variables(variable, limit=3)
    if not matches:
        raise ValueError(f"未找到变量: {variable}")
    if matches[0]["score"] < 0.45:
        raise ValueError(f"变量匹配不够确定: {variable}。候选: {json.dumps(matches, ensure_ascii=False)}")
    if len(matches) > 1 and abs(matches[0]["score"] - matches[1]["score"]) < 0.05:
        raise ValueError(f"变量名称存在歧义，请用户确认。候选: {json.dumps(matches, ensure_ascii=False)}")

    variable_name = matches[0]["variable_name"]
    for v in VARIABLES:
        if v.get("variable_name") == variable_name:
            return v
    raise ValueError(f"变量解析失败: {variable}")


def get_profile() -> dict[str, Any]:
    profiles = STORAGE_CONFIG.get("profiles", {})
    profile_name = os.getenv("BF_MCP_DB_PROFILE") or "bf_sensor_postgresql"
    if profile_name == "bf_sensor_postgresql":
        return {
            "profile_name": "bf_sensor_postgresql",
            "engine": "bf_sensor_postgresql",
            "schema": "bf_sensor",
            "tables": {
                "one_minute_values": "one_minute_values",
            },
            "env": {
                "host": "GL02_PGHOST",
                "port": "GL02_PGPORT",
                "database": "GL02_PGDATABASE",
                "user": "GL02_PGUSER",
                "password": "GL02_PGPASSWORD",
            },
            "defaults": {
                "host": "10.30.220.12",
                "port": 5432,
                "database": "bf_trend",
            },
        }
    profile = profiles.get(profile_name)
    if not profile:
        raise RuntimeError(f"未知 BF_MCP_DB_PROFILE: {profile_name}")
    out = dict(profile)
    out["profile_name"] = profile_name
    return out


def db_profile_summary() -> dict[str, Any]:
    if DATA_SOURCE in {"hybrid", "auto", "database_then_pspace", "db_then_pspace"}:
        return {
            "profile": "hybrid",
            "engine": "database_then_pspace",
            "database": get_profile(),
            "pspace": pspace_profile_summary(),
            "fallback_enabled": AUTO_PSPACE_FALLBACK,
        }
    if DATA_SOURCE == "pspace_243":
        return pspace_profile_summary()
    profile = get_profile()
    engine = profile.get("engine")
    if engine == "sqlite":
        return {"profile": profile["profile_name"], "engine": engine, "disabled": True, "message": "MCP 运行期已禁用 SQLite profile"}
    return {
        "profile": profile["profile_name"],
        "engine": engine,
        "dsn_env": profile.get("dsn_env", "BF_TREND_DB_DSN"),
        "schema": profile.get("schema", "bf_sensor"),
        "read_policy": "readonly",
    }


def pspace_profile_summary() -> dict[str, Any]:
    return {
        "profile": "pspace_243",
        "engine": "pspace_python_api",
        "server": PSPACE_SERVER,
        "port": PSPACE_PORT,
        "sdk_root": str(PSPACE_SDK_ROOT),
        "config": str(PSPACE_CONFIG),
        "read_policy": "readonly",
        "root_path": "\\冀南钢铁\\SIO\\GL02",
        "interval_seconds": PSPACE_INTERVAL_SECONDS,
        "aggregate": PSPACE_AGGREGATE,
    }


def clean_config_value(raw: str) -> str:
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def read_pspace_config(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    in_pspace = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if re.match(r"^pspace\s*:\s*$", line):
            in_pspace = True
            continue
        if in_pspace and line.strip() and not line[:1].isspace():
            break
        if not in_pspace:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if key in {"ip", "port", "username", "password"}:
            values[key] = clean_config_value(raw_value)
    return values


def resolve_pspace_connection() -> dict[str, str]:
    config = read_pspace_config(PSPACE_CONFIG)
    user = os.getenv("PSPACE_USER") or config.get("username") or ""
    password = os.getenv("PSPACE_PASSWORD") or config.get("password") or ""
    if not user or not password:
        raise RuntimeError("缺少 pSpace 账号。请设置 PSPACE_USER/PSPACE_PASSWORD 或 PSPACE_CONFIG。")
    return {
        "server": os.getenv("PSPACE_SERVER") or config.get("ip") or PSPACE_SERVER,
        "port": str(os.getenv("PSPACE_PORT") or config.get("port") or PSPACE_PORT),
        "user": user,
        "password": password,
    }


def load_pspace_sdk():
    sdk_root = PSPACE_SDK_ROOT
    if not (sdk_root / "PythonAPI" / "PsServer.py").exists():
        raise FileNotFoundError(f"找不到 pSpace PythonAPI SDK: {sdk_root}")
    if str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))
    from PythonAPI.PsServer import PsObject
    from PythonAPI import Type as T

    return PsObject, T


def connect_pspace():
    PsObject, T = load_pspace_sdk()
    connection = resolve_pspace_connection()
    pspace = PsObject()
    result = pspace.Connect(
        {
            T.ServerDict: connection["server"],
            T.ServerPortDict: connection["port"],
            T.UserDict: connection["user"],
            T.PassDict: connection["password"],
        }
    )
    if result.get(T.Return) != 0:
        raise RuntimeError(f"pSpace Connect failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    return pspace, T, connection


def format_pspace_time(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return value.strftime("%Y/%m/%d %H:%M:%S.000")


def numeric_items(mapping: dict[str, Any] | dict[int, Any]):
    def sort_key(item):
        key, _ = item
        try:
            return int(key)
        except (TypeError, ValueError):
            return 10**12

    for key, value in sorted(mapping.items(), key=sort_key):
        try:
            int(key)
        except (TypeError, ValueError):
            continue
        yield key, value


def pspace_row_from_processed(record: dict[str, Any], T) -> dict[str, Any]:
    return {
        "ts": record.get(T.TimeStamp, ""),
        "value": record.get(T.ValueDict, None),
        "quality": record.get(T.QualityDict, ""),
        "value_type": record.get(T.ReadTypeDict, ""),
        "aggregate": PSPACE_AGGREGATE,
        "interval_seconds": PSPACE_INTERVAL_SECONDS,
        "source_server": f"{PSPACE_SERVER}:{PSPACE_PORT}",
        "collected_at": now_text(),
    }


def run_pspace_helper(
    action: str,
    tag: str | list[str],
    start_time: str = "",
    end_time: str = "",
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    helper = MCP_DIR / "gl02_pspace_direct_query.py"
    cmd = [
        sys.executable,
        str(helper),
        action,
        "--server",
        PSPACE_SERVER,
        "--port",
        PSPACE_PORT,
        "--sdk-root",
        str(PSPACE_SDK_ROOT),
        "--config",
        str(PSPACE_CONFIG),
        "--interval-seconds",
        str(PSPACE_INTERVAL_SECONDS),
        "--aggregate",
        PSPACE_AGGREGATE,
        "--limit",
        str(limit),
    ]
    tags = [tag] if isinstance(tag, str) else list(tag)
    for item in tags:
        cmd.extend(["--tag", item])
    if start_time:
        cmd.extend(["--start", start_time])
    if end_time:
        cmd.extend(["--end", end_time])
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=int(os.getenv("BF_MCP_PSPACE_HELPER_TIMEOUT", "120")),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"pSpace helper failed: exit={completed.returncode}; stderr={completed.stderr[-1200:]}; stdout={completed.stdout[-1200:]}"
        )
    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"pSpace helper did not return JSON: stdout={completed.stdout[-1200:]}; stderr={completed.stderr[-1200:]}")


def query_pspace_latest(tag: str) -> dict[str, Any] | None:
    result = run_pspace_helper("latest", tag)
    row = result.get("latest")
    if row:
        row["collected_at"] = now_text()
    return row


def query_pspace_latest_many(tags: list[str]) -> dict[str, dict[str, Any]]:
    result = run_pspace_helper("latest", tags)
    rows = result.get("latest_by_tag") or {}
    for row in rows.values():
        row["collected_at"] = now_text()
    return rows


def query_pspace_history(tag: str, start_time: str, end_time: str, limit: int) -> list[dict[str, Any]]:
    start_dt = parse_datetime_value(start_time)
    end_dt = parse_datetime_value(end_time)
    if end_dt - start_dt > timedelta(days=PSPACE_MAX_QUERY_DAYS):
        raise ValueError(f"pSpace 单次查询时间跨度不能超过 {PSPACE_MAX_QUERY_DAYS:g} 天")
    result = run_pspace_helper("history", tag, start_time=start_time, end_time=end_time, limit=limit)
    rows = result.get("data") or []
    for row in rows:
        row["collected_at"] = now_text()
    return rows


def query_pspace_statistics(tag: str, start_time: str, end_time: str) -> dict[str, Any]:
    rows = query_pspace_history(tag, start_time, end_time, MAX_HISTORY_LIMIT)
    return statistics_from_rows(rows)


def import_psycopg() -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("当前环境未安装 psycopg，无法使用 prod_postgresql profile") from exc
    return psycopg, dict_row


def pg_table(profile: dict[str, Any], table_key: str) -> str:
    schema = profile.get("schema", "bf_trend")
    table = profile.get("tables", {}).get(table_key)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema or ""):
        raise RuntimeError("非法 PostgreSQL schema 配置")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
        raise RuntimeError("非法 PostgreSQL table 配置")
    return f"{schema}.{table}"


def pg_conninfo(profile: dict[str, Any]) -> str:
    if profile.get("engine") == "bf_sensor_postgresql":
        env = profile.get("env", {})
        defaults = profile.get("defaults", {})
        host = os.getenv(env.get("host", "GL02_PGHOST"), str(defaults.get("host", "10.30.220.12")))
        port = os.getenv(env.get("port", "GL02_PGPORT"), str(defaults.get("port", 5432)))
        dbname = os.getenv(env.get("database", "GL02_PGDATABASE"), str(defaults.get("database", "bf_trend")))
        user = os.getenv(env.get("user", "GL02_PGUSER"), "")
        password = os.getenv(env.get("password", "GL02_PGPASSWORD"), "")
        if not user:
            raise RuntimeError("缺少 PostgreSQL 用户名。请设置 GL02_PGUSER/GL02_PGPASSWORD。")
        return f"host={host} port={port} dbname={dbname} user={user} password={password} connect_timeout=10"
    dsn_env = profile.get("dsn_env", "BF_TREND_DB_DSN")
    dsn = os.getenv(dsn_env)
    if not dsn:
        raise RuntimeError(f"环境变量 {dsn_env} 未设置")
    return dsn


def query_postgres_latest(profile: dict[str, Any], tag: str) -> dict[str, Any] | None:
    psycopg, dict_row = import_psycopg()
    if profile.get("engine") == "bf_sensor_postgresql":
        sql = """
            SELECT ts, value, quality, value_type,
                   aggregate, interval_seconds, source_server, collected_at
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = %s
            ORDER BY ts DESC
            LIMIT 1
        """
        with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag,))
                return cur.fetchone()
    table = pg_table(profile, "one_minute_average")
    sql = f"""
        SELECT ts, one_minute_average_value AS value, quality, value_type,
               aggregate, interval_seconds, source_server, collected_at
        FROM {table}
        WHERE furnace_id = %s AND tag_long_name = %s
        ORDER BY ts DESC
        LIMIT 1
    """
    with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (FURNACE_ID, tag))
            return cur.fetchone()


def query_postgres_history(profile: dict[str, Any], tag: str, start_time: str, end_time: str, limit: int) -> list[dict[str, Any]]:
    psycopg, dict_row = import_psycopg()
    if profile.get("engine") == "bf_sensor_postgresql":
        sql = """
            SELECT ts, value, quality, value_type,
                   aggregate, interval_seconds, source_server, collected_at
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = %s
              AND ts >= %s::timestamp AND ts <= %s::timestamp
            ORDER BY ts ASC
            LIMIT %s
        """
        with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag, local_time_text(start_time), local_time_text(end_time), limit))
                return list(cur.fetchall())
    table = pg_table(profile, "one_minute_average")
    sql = f"""
        SELECT ts, one_minute_average_value AS value, quality, value_type,
               aggregate, interval_seconds, source_server, collected_at
        FROM {table}
        WHERE furnace_id = %s AND tag_long_name = %s
          AND ts >= %s::timestamptz AND ts <= %s::timestamptz
        ORDER BY ts ASC
        LIMIT %s
    """
    with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (FURNACE_ID, tag, start_time, end_time, limit))
            return list(cur.fetchall())


def query_postgres_statistics(profile: dict[str, Any], tag: str, start_time: str, end_time: str) -> dict[str, Any]:
    psycopg, dict_row = import_psycopg()
    if profile.get("engine") == "bf_sensor_postgresql":
        stats_sql = """
            SELECT COUNT(value) AS count,
                   AVG(value) AS avg,
                   MIN(value) AS min,
                   MAX(value) AS max,
                   STDDEV_POP(value) AS stddev,
                   REGR_SLOPE(value, EXTRACT(EPOCH FROM ts) / 60.0) AS slope_per_min
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = %s
              AND ts >= %s::timestamp AND ts <= %s::timestamp
        """
        first_last_sql = """
            SELECT ts, value, quality
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = %s
              AND ts >= %s::timestamp AND ts <= %s::timestamp
            ORDER BY ts {order}
            LIMIT 1
        """
        start_key = local_time_text(start_time)
        end_key = local_time_text(end_time)
        with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(stats_sql, (tag, start_key, end_key))
                stats = dict(cur.fetchone() or {})
                cur.execute(first_last_sql.format(order="ASC"), (tag, start_key, end_key))
                first = cur.fetchone()
                cur.execute(first_last_sql.format(order="DESC"), (tag, start_key, end_key))
                last = cur.fetchone()
        stats["first"] = first
        stats["last"] = last
        first_value = numeric_row_value(first or {})
        last_value = numeric_row_value(last or {})
        delta = (last_value - first_value) if first_value is not None and last_value is not None else None
        stats["delta"] = delta
        stats["trend"] = trend_label(delta=delta, slope_per_min=numeric_row_value({"value": stats.get("slope_per_min")}))
        return stats
    table = pg_table(profile, "one_minute_average")
    stats_sql = f"""
        SELECT COUNT(one_minute_average_value) AS count,
               AVG(one_minute_average_value) AS avg,
               MIN(one_minute_average_value) AS min,
               MAX(one_minute_average_value) AS max,
               STDDEV_POP(one_minute_average_value) AS stddev,
               REGR_SLOPE(one_minute_average_value, EXTRACT(EPOCH FROM ts) / 60.0) AS slope_per_min
        FROM {table}
        WHERE furnace_id = %s AND tag_long_name = %s
          AND ts >= %s::timestamptz AND ts <= %s::timestamptz
    """
    first_last_sql = f"""
        SELECT ts, one_minute_average_value AS value, quality
        FROM {table}
        WHERE furnace_id = %s AND tag_long_name = %s
          AND ts >= %s::timestamptz AND ts <= %s::timestamptz
        ORDER BY ts {{order}}
        LIMIT 1
    """
    with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(stats_sql, (FURNACE_ID, tag, start_time, end_time))
            stats = dict(cur.fetchone() or {})
            cur.execute(first_last_sql.format(order="ASC"), (FURNACE_ID, tag, start_time, end_time))
            first = cur.fetchone()
            cur.execute(first_last_sql.format(order="DESC"), (FURNACE_ID, tag, start_time, end_time))
            last = cur.fetchone()
    stats["first"] = first
    stats["last"] = last
    first_value = numeric_row_value(first or {})
    last_value = numeric_row_value(last or {})
    delta = (last_value - first_value) if first_value is not None and last_value is not None else None
    stats["delta"] = delta
    stats["trend"] = trend_label(delta=delta, slope_per_min=numeric_row_value({"value": stats.get("slope_per_min")}))
    return stats


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def normalize_source_preference(source_preference: str | None = None) -> str:
    raw = normalize_text(source_preference or DATA_SOURCE or "hybrid")
    if raw in {"db", "database", "postgres", "postgresql", "storage", "local"}:
        return "database"
    if raw in {"pspace", "pspace_243", "real", "realtime"}:
        return "pspace"
    return "hybrid"


def query_database_latest(tag: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    profile = get_profile()
    engine = profile.get("engine")
    if engine == "sqlite":
        raise RuntimeError("MCP 运行期已禁用 SQLite profile，请使用 bf_sensor_postgresql 或 pSpace。")
    elif engine in {"postgresql_compatible", "bf_sensor_postgresql"}:
        row = query_postgres_latest(profile, tag)
    else:
        raise RuntimeError(f"不支持的数据库引擎: {engine}")
    source = db_profile_summary()
    if source.get("profile") == "hybrid":
        source = {"profile": "database", "engine": engine, "database": profile}
    return jsonable(row), source


def query_database_history(tag: str, start_time: str, end_time: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile = get_profile()
    engine = profile.get("engine")
    if engine == "sqlite":
        raise RuntimeError("MCP 运行期已禁用 SQLite profile，请使用 bf_sensor_postgresql 或 pSpace。")
    elif engine in {"postgresql_compatible", "bf_sensor_postgresql"}:
        rows = query_postgres_history(profile, tag, start_time, end_time, limit)
    else:
        raise RuntimeError(f"不支持的数据库引擎: {engine}")
    source = db_profile_summary()
    if source.get("profile") == "hybrid":
        source = {"profile": "database", "engine": engine, "database": profile}
    return jsonable(rows), source


def query_database_statistics(tag: str, start_time: str, end_time: str) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = get_profile()
    engine = profile.get("engine")
    if engine == "sqlite":
        raise RuntimeError("MCP 运行期已禁用 SQLite profile，请使用 bf_sensor_postgresql 或 pSpace。")
    elif engine in {"postgresql_compatible", "bf_sensor_postgresql"}:
        stats = query_postgres_statistics(profile, tag, start_time, end_time)
    else:
        raise RuntimeError(f"不支持的数据库引擎: {engine}")
    source = db_profile_summary()
    if source.get("profile") == "hybrid":
        source = {"profile": "database", "engine": engine, "database": profile}
    return jsonable(stats), source


def _with_fallback_source(primary: dict[str, Any], fallback: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **fallback,
        "fallback": True,
        "fallback_reason": reason,
        "primary_attempt": primary,
        "strategy": "database_then_pspace",
    }


def query_latest_from_storage(tag: str, source_preference: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    mode = normalize_source_preference(source_preference)
    if mode == "pspace":
        return jsonable(query_pspace_latest(tag)), pspace_profile_summary()
    db_row: dict[str, Any] | None = None
    db_source: dict[str, Any] = {}
    db_error = ""
    try:
        db_row, db_source = query_database_latest(tag)
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)
        db_source = {"profile": "database", "error": db_error}
    if db_row or mode == "database" or not AUTO_PSPACE_FALLBACK:
        return db_row, db_source
    pspace_row = jsonable(query_pspace_latest(tag))
    return pspace_row, _with_fallback_source(db_source, pspace_profile_summary(), db_error or "DATABASE_NO_DATA")


def query_history_from_storage(
    tag: str,
    start_time: str,
    end_time: str,
    limit: int,
    source_preference: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mode = normalize_source_preference(source_preference)
    if mode == "pspace":
        return jsonable(query_pspace_history(tag, start_time, end_time, limit)), pspace_profile_summary()
    db_rows: list[dict[str, Any]] = []
    db_source: dict[str, Any] = {}
    db_error = ""
    try:
        db_rows, db_source = query_database_history(tag, start_time, end_time, limit)
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)
        db_source = {"profile": "database", "error": db_error}
    if db_rows or mode == "database" or not AUTO_PSPACE_FALLBACK:
        return db_rows, db_source
    pspace_rows = jsonable(query_pspace_history(tag, start_time, end_time, limit))
    return pspace_rows, _with_fallback_source(db_source, pspace_profile_summary(), db_error or "DATABASE_NO_DATA")


def query_statistics_from_storage(
    tag: str,
    start_time: str,
    end_time: str,
    source_preference: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mode = normalize_source_preference(source_preference)
    if mode == "pspace":
        return jsonable(query_pspace_statistics(tag, start_time, end_time)), pspace_profile_summary()
    db_stats: dict[str, Any] = {}
    db_source: dict[str, Any] = {}
    db_error = ""
    try:
        db_stats, db_source = query_database_statistics(tag, start_time, end_time)
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)
        db_source = {"profile": "database", "error": db_error}
    if (db_stats.get("count") or 0) > 0 or mode == "database" or not AUTO_PSPACE_FALLBACK:
        return db_stats, db_source
    pspace_stats = jsonable(query_pspace_statistics(tag, start_time, end_time))
    return pspace_stats, _with_fallback_source(db_source, pspace_profile_summary(), db_error or "DATABASE_NO_DATA")


def derived_t_top_components() -> list[dict[str, Any]]:
    names = {"T_top_A", "T_top_B", "T_top_C", "T_top_D"}
    return [v for v in VARIABLES if v.get("variable_name") in names and v.get("tag_long_name")]


def query_latest_derived_t_top(source_preference: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    values = []
    source: dict[str, Any] | None = None
    for component in derived_t_top_components():
        row, source = query_latest_from_storage(component["tag_long_name"], source_preference=source_preference)
        if row and row.get("value") is not None:
            values.append({"component": component.get("variable_name"), **row})
    numeric = [float(item["value"]) for item in values if item.get("value") is not None]
    if not numeric:
        return None, source or db_profile_summary()
    latest_ts = max(str(item.get("ts", "")) for item in values)
    return {
        "ts": latest_ts,
        "value": sum(numeric) / len(numeric),
        "quality": "DERIVED_AVERAGE",
        "aggregate": "AVG(T_top_A,T_top_B,T_top_C,T_top_D)",
        "interval_seconds": 60,
        "components": values,
    }, source or db_profile_summary()


def query_history_derived_t_top(
    start_time: str,
    end_time: str,
    limit: int,
    source_preference: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_ts: dict[str, list[dict[str, Any]]] = {}
    source: dict[str, Any] | None = None
    for component in derived_t_top_components():
        rows, source = query_history_from_storage(
            component["tag_long_name"],
            start_time,
            end_time,
            MAX_HISTORY_LIMIT,
            source_preference=source_preference,
        )
        for row in rows:
            if row.get("value") is None:
                continue
            item = dict(row)
            item["component"] = component.get("variable_name")
            by_ts.setdefault(str(row.get("ts")), []).append(item)
    out = []
    for ts in sorted(by_ts.keys())[:limit]:
        items = by_ts[ts]
        values = [float(item["value"]) for item in items if item.get("value") is not None]
        if not values:
            continue
        out.append(
            {
                "ts": ts,
                "value": sum(values) / len(values),
                "quality": "DERIVED_AVERAGE",
                "aggregate": "AVG(T_top_A,T_top_B,T_top_C,T_top_D)",
                "interval_seconds": 60,
                "components_count": len(values),
                "components": items,
            }
        )
    return out, source or db_profile_summary()


def statistics_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if numeric_row_value(row) is not None]
    values = [float(numeric_row_value(row) or 0.0) for row in usable]
    first = usable[0] if usable else None
    last = usable[-1] if usable else None
    delta = (float(last["value"]) - float(first["value"])) if first and last else None
    slope = linear_slope_per_min(usable)
    return {
        "count": len(values),
        "avg": (sum(values) / len(values)) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "stddev": population_std(values),
        "slope_per_min": slope,
        "delta": delta,
        "trend": trend_label(delta=delta, slope_per_min=slope),
        "first": first,
        "last": last,
    }


def parse_variables_arg(variables: Any, max_items: int = 16) -> list[str]:
    if isinstance(variables, str):
        raw_items = re.split(r"[,，、;；\n]+", variables)
    elif isinstance(variables, list):
        raw_items = []
        for item in variables:
            if isinstance(item, str):
                raw_items.extend(re.split(r"[,，、;；\n]+", item))
            else:
                raw_items.append(str(item))
    else:
        raw_items = [str(variables or "")]
    out = []
    seen = set()
    for item in raw_items:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    if not out:
        raise ValueError("variables 至少需要一个变量名，例如 ['T_top'] 或 ['T_top','P_top']")
    maximum = max(1, min(int(max_items or 16), 80))
    if len(out) > maximum:
        raise ValueError(f"请求了 {len(out)} 个变量，本工具最多支持 {maximum} 个；请分组查询。未静默截断变量。")
    return out


def numeric_row_value(row: dict[str, Any]) -> float | None:
    try:
        value = float(row.get("value"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def row_datetime(row: dict[str, Any]) -> datetime | None:
    raw = row.get("ts")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(LOCAL_TZ).replace(tzinfo=None) if raw.tzinfo else raw
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(LOCAL_TZ).replace(tzinfo=None) if parsed.tzinfo else parsed


def population_std(values: list[float]) -> float | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def linear_slope_per_min(rows: list[dict[str, Any]]) -> float | None:
    points: list[tuple[float, float]] = []
    first_ts: datetime | None = None
    for row in rows:
        ts = row_datetime(row)
        value = numeric_row_value(row)
        if ts is None or value is None:
            continue
        if first_ts is None:
            first_ts = ts
        points.append(((ts - first_ts).total_seconds() / 60.0, value))
    if len(points) < 2:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in points) / denom


def trend_label(delta: float | None = None, slope_per_min: float | None = None) -> str:
    signal = slope_per_min if slope_per_min is not None else delta
    if signal is None:
        return "无法判断"
    if abs(signal) < 1e-9:
        return "基本持平"
    return "上升" if signal > 0 else "下降"


def series_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if numeric_row_value(row) is not None]
    values = [float(numeric_row_value(row) or 0.0) for row in usable]
    first = usable[0] if usable else None
    last = usable[-1] if usable else None
    delta = None
    if first and last:
        delta = float(last["value"]) - float(first["value"])
    slope = linear_slope_per_min(usable)
    return {
        "count": len(values),
        "first": first,
        "last": last,
        "avg": (sum(values) / len(values)) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "stddev": population_std(values),
        "slope_per_min": slope,
        "delta": delta,
        "trend": trend_label(delta=delta, slope_per_min=slope),
    }


def rows_since(rows: list[dict[str, Any]], end_time: str, minutes: int) -> list[dict[str, Any]]:
    end_dt = parse_datetime_value(end_time)
    if end_dt.tzinfo is not None:
        end_dt = end_dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
    start_dt = end_dt - timedelta(minutes=minutes)
    return [row for row in rows if (row_datetime(row) is not None and row_datetime(row) >= start_dt)]


def z_level_from_baseline(value: float | None, baseline: dict[str, Any] | None) -> float | None:
    if value is None or not baseline:
        return None
    median_ref = numeric_row_value({"value": baseline.get("median_ref")})
    iqr_ref = numeric_row_value({"value": baseline.get("iqr_ref")})
    if median_ref is None or iqr_ref in (None, 0):
        return None
    return (value - median_ref) / iqr_ref


def z_vol_from_baseline(stddev: float | None, baseline: dict[str, Any] | None) -> float | None:
    if stddev is None or not baseline:
        return None
    iqr_ref = numeric_row_value({"value": baseline.get("iqr_ref")})
    if iqr_ref in (None, 0):
        return None
    return stddev / (iqr_ref / 1.35)


def z_trend_from_baseline(slope_per_min: float | None, window_minutes: int, baseline: dict[str, Any] | None) -> float | None:
    if slope_per_min is None or not baseline:
        return None
    iqr_ref = numeric_row_value({"value": baseline.get("iqr_ref")})
    if iqr_ref in (None, 0):
        return None
    return (slope_per_min * window_minutes) / iqr_ref


def baseline_variable_candidates(meta: dict[str, Any]) -> list[str]:
    names = [meta.get("variable_name", ""), *list(meta.get("aliases") or [])]
    tag = meta.get("tag_long_name") or meta.get("tag") or ""
    for v in VARIABLES:
        if tag and v.get("tag_long_name") == tag:
            names.append(v.get("variable_name", ""))
            names.extend(v.get("aliases") or [])
    static_aliases = {
        "P_static_lower_mean": "P_static_20m35",
        "P_static_middle_mean": "P_static_23m49",
        "P_static_upper_mean": "P_static_28m98",
    }
    for name in list(names):
        if name in static_aliases:
            names.append(static_aliases[name])
    out = []
    seen = set()
    for name in names:
        name = str(name or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def query_daily_baseline(
    variable_names: list[str],
    end_time: str,
    baseline_day: str = "",
    baseline_days: int = 30,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    profile = get_profile()
    if profile.get("engine") not in {"bf_sensor_postgresql", "postgresql_compatible"}:
        return None, {"type": "postgresql", "available": False, "message": "当前 profile 不支持 daily_baselines 查询"}
    psycopg, dict_row = import_psycopg()
    end_dt = parse_datetime_value(end_time)
    if end_dt.tzinfo is not None:
        end_dt = end_dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
    day_value = baseline_day.strip() if baseline_day else ""
    with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if not day_value:
                cur.execute(
                    """
                    SELECT max(baseline_day) AS baseline_day
                    FROM bf_sensor.daily_baselines
                    WHERE baseline_days = %s
                      AND baseline_day <= %s::date
                      AND variable_name = ANY(%s)
                    """,
                    (baseline_days, end_dt.date(), variable_names),
                )
                row = cur.fetchone()
                day_value = str(row["baseline_day"]) if row and row.get("baseline_day") else ""
            if not day_value:
                cur.execute(
                    """
                    SELECT max(baseline_day) AS baseline_day
                    FROM bf_sensor.daily_baselines
                    WHERE baseline_days = %s
                      AND variable_name = ANY(%s)
                    """,
                    (baseline_days, variable_names),
                )
                row = cur.fetchone()
                day_value = str(row["baseline_day"]) if row and row.get("baseline_day") else ""
            if not day_value:
                return None, {"type": "postgresql", "schema": "bf_sensor", "table": "daily_baselines", "available": False}
            cur.execute(
                """
                SELECT baseline_day, baseline_window_start, baseline_window_end,
                       baseline_days, variable_name, median_ref, iqr_ref,
                       p10, p50, p90, sample_count, expected_minutes,
                       coverage_ratio, updated_at
                FROM bf_sensor.daily_baselines
                WHERE baseline_day = %s::date
                  AND baseline_days = %s
                  AND variable_name = ANY(%s)
                ORDER BY array_position(%s, variable_name)
                LIMIT 1
                """,
                (day_value, baseline_days, variable_names, variable_names),
            )
            baseline = cur.fetchone()
    return jsonable(baseline), {
        "type": "postgresql",
        "schema": "bf_sensor",
        "table": "daily_baselines",
        "read_policy": "readonly",
        "variable_candidates": variable_names,
        "baseline_day": day_value,
    }


def feature_statistics_payload(
    rows: list[dict[str, Any]],
    end_time: str,
    baseline: dict[str, Any] | None,
    last60_rows: list[dict[str, Any]] | None = None,
    last15_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    range_stats = statistics_from_rows(rows)
    last60 = statistics_from_rows(last60_rows if last60_rows is not None else rows_since(rows, end_time, 60))
    last15 = statistics_from_rows(last15_rows if last15_rows is not None else rows_since(rows, end_time, 15))
    return {
        "range": range_stats,
        "last_60min": last60,
        "last_15min": last15,
        "baseline_30d": baseline,
        "z": {
            "z_range": z_level_from_baseline(range_stats.get("avg"), baseline),
            "z60": z_level_from_baseline(last60.get("avg"), baseline),
            "z15": z_level_from_baseline(last15.get("avg"), baseline),
            "zstd": z_vol_from_baseline(last15.get("stddev"), baseline),
            "z_slope_range": z_trend_from_baseline(range_stats.get("slope_per_min"), max(range_stats.get("count") or 0, 1), baseline),
            "z_slope_60": z_trend_from_baseline(last60.get("slope_per_min"), 60, baseline),
            "z_slope_15": z_trend_from_baseline(last15.get("slope_per_min"), 15, baseline),
            "formula": {
                "z60": "(mean(last 60min) - median_ref) / iqr_ref",
                "z15": "(mean(last 15min) - median_ref) / iqr_ref",
                "zstd": "stddev(last 15min) / (iqr_ref / 1.35)",
                "z_slope": "(slope_per_min * window_minutes) / iqr_ref",
            },
        },
    }


def normalize_chart_scale(scale: str) -> str:
    value = normalize_text(scale or "raw")
    aliases = {
        "": "raw",
        "none": "raw",
        "原始": "raw",
        "原始值": "raw",
        "raw": "raw",
        "minmax": "minmax",
        "0-100": "minmax",
        "归一化": "minmax",
        "对比": "minmax",
        "zscore": "zscore",
        "z-score": "zscore",
        "标准化": "zscore",
    }
    if value not in aliases:
        raise ValueError("scale 只允许 raw、minmax、zscore；不同单位变量建议使用 minmax。")
    return aliases[value]


def normalize_chart_type(chart_type: str) -> str:
    """Normalize trend-chart aliases while keeping the public MCP schema compact."""
    value = normalize_text(chart_type or "auto").lower().replace("-", "_")
    aliases = {
        "": "auto",
        "auto": "auto",
        "自动": "auto",
        "line": "line",
        "trend": "line",
        "折线": "line",
        "折线图": "line",
        "area": "area",
        "面积": "area",
        "面积图": "area",
        "step": "step",
        "阶梯": "step",
        "阶梯图": "step",
        "scatter": "scatter",
        "散点": "scatter",
        "散点图": "scatter",
        "dual_axis": "dual_axis",
        "dualaxis": "dual_axis",
        "双轴": "dual_axis",
        "双y轴": "dual_axis",
        "small_multiples": "small_multiples",
        "smallmultiples": "small_multiples",
        "分面": "small_multiples",
        "分面图": "small_multiples",
    }
    if value not in aliases:
        raise ValueError("chart_type 只允许 auto、line、area、step、scatter、dual_axis、small_multiples。")
    return aliases[value]


def normalize_chart_theme(theme: str) -> str:
    value = normalize_text(theme or "industrial").lower()
    aliases = {
        "": "industrial",
        "industrial": "industrial",
        "工业": "industrial",
        "钢灰": "industrial",
        "light": "light",
        "亮色": "light",
        "dark": "dark",
        "深色": "dark",
    }
    if value not in aliases:
        raise ValueError("theme 只允许 industrial、light、dark。")
    return aliases[value]


def normalize_analysis_type(analysis_type: str) -> str:
    value = normalize_text(analysis_type or "auto").lower().replace("-", "_")
    aliases = {
        "": "auto",
        "auto": "auto",
        "自动": "auto",
        "correlation_scatter": "correlation_scatter",
        "correlation": "correlation_scatter",
        "关系": "correlation_scatter",
        "相关散点": "correlation_scatter",
        "相关散点图": "correlation_scatter",
        "correlation_heatmap": "correlation_heatmap",
        "heatmap": "correlation_heatmap",
        "相关矩阵": "correlation_heatmap",
        "相关热力图": "correlation_heatmap",
        "distribution": "distribution",
        "histogram": "distribution",
        "分布": "distribution",
        "直方图": "distribution",
        "boxplot": "boxplot",
        "box": "boxplot",
        "箱线图": "boxplot",
    }
    if value not in aliases:
        raise ValueError(
            "analysis_type 只允许 auto、correlation_scatter、correlation_heatmap、distribution、boxplot。"
        )
    return aliases[value]


def scaled_values(values: list[float], scale: str) -> list[float]:
    if scale == "raw":
        return values
    if not values:
        return []
    if scale == "minmax":
        lo = min(values)
        hi = max(values)
        if abs(hi - lo) < 1e-12:
            return [50.0 for _ in values]
        return [(value - lo) * 100.0 / (hi - lo) for value in values]
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / max(len(values), 1)
    std = math.sqrt(variance)
    if std < 1e-12:
        return [0.0 for _ in values]
    return [(value - avg) / std for value in values]


def moving_average(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return list(values)
    result: list[float] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        count = min(index + 1, window)
        result.append(running / count)
    return result


def chart_series_xy(item: dict[str, Any], scale: str) -> tuple[list[datetime], list[float]]:
    points: list[tuple[datetime, float]] = []
    for row in item.get("rows") or []:
        value = numeric_row_value(row)
        if value is None:
            continue
        try:
            ts = parse_datetime_value(str(row.get("ts")))
        except Exception:
            continue
        if ts.tzinfo is not None:
            ts = ts.astimezone(LOCAL_TZ).replace(tzinfo=None)
        points.append((ts, value))
    points.sort(key=lambda point: point[0])
    times = [point[0] for point in points]
    values = [point[1] for point in points]
    return times, scaled_values(values, scale)


def chart_series_label(item: dict[str, Any], scale: str) -> str:
    variable = item.get("variable") or {}
    name = variable.get("variable_name") or item.get("requested_variable") or "变量"
    desc = variable.get("description") or ""
    unit = variable.get("unit") or ""
    if unit and scale == "raw":
        return f"{name} ({unit})"
    if desc:
        return f"{name} - {desc[:12]}"
    return str(name)


def chart_theme_values(theme: str) -> dict[str, Any]:
    if theme == "dark":
        return {
            "figure": "#0f171d",
            "axes": "#17232c",
            "text": "#e6edf1",
            "grid": "#52636d",
            "colors": ["#46b3a6", "#e3a546", "#7da9d8", "#d66f6f", "#9f8bd4", "#73a95a", "#cf87b5", "#9aa7ad"],
        }
    if theme == "light":
        return {
            "figure": "#ffffff",
            "axes": "#ffffff",
            "text": "#263238",
            "grid": "#b0bec5",
            "colors": ["#00695c", "#ef6c00", "#1565c0", "#c62828", "#6a1b9a", "#558b2f", "#ad1457", "#546e7a"],
        }
    return {
        "figure": "#e9eef0",
        "axes": "#f8fafb",
        "text": "#263238",
        "grid": "#90a4ae",
        "colors": ["#2f7f78", "#b87822", "#496f91", "#a44f4f", "#74638f", "#66804f", "#9a607f", "#586970"],
    }


def choose_trend_chart_type(requested: str, series_items: list[dict[str, Any]]) -> str:
    if requested != "auto":
        if requested == "dual_axis" and len(series_items) != 2:
            return "line" if len(series_items) == 1 else "small_multiples"
        return requested
    units = {str((item.get("variable") or {}).get("unit") or "") for item in series_items}
    units.discard("")
    if len(series_items) == 2 and len(units) > 1:
        return "dual_axis"
    if len(series_items) > 2 and len(units) > 1:
        return "small_multiples"
    magnitudes: list[float] = []
    for item in series_items:
        values = sorted(abs(value) for row in item.get("rows") or [] if (value := numeric_row_value(row)) is not None)
        if not values:
            continue
        typical = values[len(values) // 2]
        if typical > 1e-9:
            magnitudes.append(typical)
    if len(magnitudes) >= 2 and max(magnitudes) / min(magnitudes) >= 20:
        return "dual_axis" if len(series_items) == 2 else "small_multiples"
    return "line"


def chart_url_for(path: Path) -> str:
    return f"{CHARTS_URL_PREFIX}/{path.name}"


def chart_time_label(value: str) -> str:
    try:
        parsed = parse_datetime_value(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(LOCAL_TZ)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def render_trend_chart(
    series_items: list[dict[str, Any]],
    start_time: str,
    end_time: str,
    scale: str,
    title: str,
    chart_type: str = "auto",
    moving_average_points: int = 0,
    show_extrema: bool = False,
    show_latest: bool = True,
    reference_values: dict[str, float] | None = None,
    theme: str = "industrial",
) -> dict[str, Any]:
    # In MCP stdio mode stdout/stderr are protocol-adjacent pipes. Matplotlib
    # font discovery and missing-glyph warnings can fill stderr and stall calls.
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    chart_type_used = choose_trend_chart_type(chart_type, series_items)
    palette = chart_theme_values(theme)
    if chart_type_used == "small_multiples":
        fig, axes_value = plt.subplots(
            len(series_items),
            1,
            sharex=True,
            figsize=(12, min(18, max(5, 2.8 * len(series_items)))),
            dpi=140,
            squeeze=False,
        )
        axes = [row[0] for row in axes_value]
    else:
        fig, first_axis = plt.subplots(figsize=(12, 6), dpi=140)
        axes = [first_axis]
    fig.patch.set_facecolor(palette["figure"])

    def style_axis(axis) -> None:
        axis.set_facecolor(palette["axes"])
        axis.tick_params(colors=palette["text"])
        axis.xaxis.label.set_color(palette["text"])
        axis.yaxis.label.set_color(palette["text"])
        axis.title.set_color(palette["text"])
        for spine in axis.spines.values():
            spine.set_color(palette["grid"])
        axis.grid(True, linestyle="--", alpha=0.32, color=palette["grid"])

    plotted = 0
    secondary_axis = axes[0].twinx() if chart_type_used == "dual_axis" else None
    if secondary_axis is not None:
        style_axis(secondary_axis)
    reference_values = reference_values or {}
    for index, item in enumerate(series_items):
        axis = axes[index] if chart_type_used == "small_multiples" else (secondary_axis if index == 1 and secondary_axis else axes[0])
        style_axis(axis)
        times, plot_values = chart_series_xy(item, scale)
        if not plot_values:
            continue
        label = chart_series_label(item, scale)
        color = palette["colors"][index % len(palette["colors"])]
        smoothed = moving_average(plot_values, moving_average_points)
        if moving_average_points > 1:
            axis.plot(times, plot_values, linewidth=1.0, alpha=0.28, color=color, label=f"{label} 原始")
        if chart_type_used == "area":
            axis.plot(times, smoothed, linewidth=2.0, color=color, label=label)
            axis.fill_between(times, smoothed, alpha=0.22, color=color)
        elif chart_type_used == "step":
            axis.step(times, smoothed, where="post", linewidth=2.0, color=color, label=label)
        elif chart_type_used == "scatter":
            axis.scatter(times, smoothed, s=18, alpha=0.78, color=color, label=label)
        else:
            axis.plot(
                times,
                smoothed,
                linewidth=2.0,
                marker="o" if len(times) <= 24 else None,
                markersize=3,
                color=color,
                label=f"{label}{f' {moving_average_points}点均线' if moving_average_points > 1 else ''}",
            )
        variable_name = str((item.get("variable") or {}).get("variable_name") or item.get("requested_variable") or "")
        if scale == "raw" and variable_name in reference_values:
            axis.axhline(
                float(reference_values[variable_name]),
                color=color,
                linestyle=":",
                linewidth=1.5,
                alpha=0.85,
                label=f"{variable_name} 参考值",
            )
        if show_extrema and len(series_items) <= 4:
            min_index = min(range(len(smoothed)), key=smoothed.__getitem__)
            max_index = max(range(len(smoothed)), key=smoothed.__getitem__)
            for point_index, prefix in ((min_index, "低"), (max_index, "高")):
                axis.annotate(
                    f"{prefix} {smoothed[point_index]:.3g}",
                    (times[point_index], smoothed[point_index]),
                    xytext=(4, 7),
                    textcoords="offset points",
                    fontsize=8,
                    color=color,
                )
        if show_latest and len(series_items) <= 4:
            axis.annotate(
                f"最新 {smoothed[-1]:.3g}",
                (times[-1], smoothed[-1]),
                xytext=(5, -13),
                textcoords="offset points",
                fontsize=8,
                color=color,
            )
        if chart_type_used == "small_multiples":
            axis.set_ylabel(label)
            axis.legend(loc="upper left", fontsize=8)
        elif chart_type_used == "dual_axis":
            axis.set_ylabel(label, color=color)
            axis.tick_params(axis="y", colors=color)
        plotted += 1
    if plotted <= 0:
        plt.close(fig)
        raise ValueError("没有可绘制的有效数值点")

    chart_title = title.strip() if title else f"GL02 变量趋势图：{chart_time_label(start_time)} 至 {chart_time_label(end_time)}"
    axes[0].set_title(chart_title)
    axes[-1].set_xlabel("时间")
    if chart_type_used not in {"small_multiples", "dual_axis"}:
        if scale == "raw":
            units = {str((item.get("variable") or {}).get("unit") or "") for item in series_items}
            units.discard("")
            axes[0].set_ylabel(next(iter(units)) if len(units) == 1 else "原始值")
        elif scale == "minmax":
            axes[0].set_ylabel("归一化值（每个变量 0-100）")
        else:
            axes[0].set_ylabel("标准化值（每个变量 z-score）")
        axes[0].legend(loc="best", fontsize=8)
    elif chart_type_used == "dual_axis" and secondary_axis is not None:
        handles1, labels1 = axes[0].get_legend_handles_labels()
        handles2, labels2 = secondary_axis.get_legend_handles_labels()
        axes[0].legend(handles1 + handles2, labels1 + labels2, loc="best", fontsize=8)
    for axis in axes:
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Glyph .* missing from font.*")
        warnings.filterwarnings("ignore", category=UserWarning, module=r"matplotlib\..*")
        fig.autofmt_xdate(rotation=30)
        fig.tight_layout()

    filename = f"gl02_{chart_type_used}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
    path = CHARTS_DIR / filename
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r"Glyph .* missing from font.*")
            warnings.filterwarnings("ignore", category=UserWarning, module=r"matplotlib\..*")
            fig.savefig(path)
    finally:
        plt.close(fig)
    return {"path": path, "url": chart_url_for(path), "chart_type_used": chart_type_used}


def minute_value_map(item: dict[str, Any]) -> dict[datetime, float]:
    """Build a minute-aligned value map for correlation charts."""
    values: dict[datetime, float] = {}
    for row in item.get("rows") or []:
        value = numeric_row_value(row)
        if value is None:
            continue
        try:
            ts = parse_datetime_value(str(row.get("ts")))
        except Exception:
            continue
        if ts.tzinfo is not None:
            ts = ts.astimezone(LOCAL_TZ).replace(tzinfo=None)
        values[ts.replace(second=0, microsecond=0)] = value
    return values


def pearson_correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_avg = sum(left) / len(left)
    right_avg = sum(right) / len(right)
    numerator = sum((x - left_avg) * (y - right_avg) for x, y in zip(left, right))
    left_sum = sum((x - left_avg) ** 2 for x in left)
    right_sum = sum((y - right_avg) ** 2 for y in right)
    denominator = math.sqrt(left_sum * right_sum)
    if denominator < 1e-12:
        return None
    return numerator / denominator


def aligned_pair(left_item: dict[str, Any], right_item: dict[str, Any]) -> tuple[list[float], list[float]]:
    left_map = minute_value_map(left_item)
    right_map = minute_value_map(right_item)
    timestamps = sorted(set(left_map).intersection(right_map))
    return [left_map[ts] for ts in timestamps], [right_map[ts] for ts in timestamps]


def render_analysis_chart(
    series_items: list[dict[str, Any]],
    start_time: str,
    end_time: str,
    analysis_type: str,
    scale: str,
    title: str,
    theme: str,
) -> dict[str, Any]:
    """Render relationship/distribution charts and return auditable derived metrics."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    palette = chart_theme_values(theme)
    used_type = analysis_type
    if used_type == "auto":
        used_type = "correlation_scatter" if len(series_items) == 2 else "correlation_heatmap"
    if used_type == "correlation_scatter" and len(series_items) != 2:
        used_type = "correlation_heatmap"

    derived: dict[str, Any] = {}
    if used_type == "correlation_heatmap":
        if len(series_items) < 2:
            raise ValueError("相关矩阵至少需要两个有效变量")
        size = len(series_items)
        fig, ax = plt.subplots(figsize=(max(9.5, size * 1.2), max(6, size * 0.9)), dpi=140)
        matrix: list[list[float]] = []
        aligned_counts: list[list[int]] = []
        correlations: dict[str, Any] = {}
        for left_index, left_item in enumerate(series_items):
            row_values: list[float] = []
            row_counts: list[int] = []
            left_name = str((left_item.get("variable") or {}).get("variable_name") or left_item.get("requested_variable"))
            for right_index, right_item in enumerate(series_items):
                right_name = str((right_item.get("variable") or {}).get("variable_name") or right_item.get("requested_variable"))
                if left_index == right_index:
                    corr = 1.0
                    count = len(minute_value_map(left_item))
                else:
                    left_values, right_values = aligned_pair(left_item, right_item)
                    corr_value = pearson_correlation(left_values, right_values)
                    corr = corr_value if corr_value is not None else 0.0
                    count = len(left_values)
                    if left_index < right_index:
                        correlations[f"{left_name}__{right_name}"] = {
                            "pearson_r": corr_value,
                            "aligned_count": count,
                        }
                row_values.append(corr)
                row_counts.append(count)
            matrix.append(row_values)
            aligned_counts.append(row_counts)
        image = ax.imshow(matrix, cmap="RdYlGn", vmin=-1, vmax=1)
        labels = [str((item.get("variable") or {}).get("variable_name") or item.get("requested_variable")) for item in series_items]
        ax.set_xticks(range(len(labels)), labels=labels, rotation=35, ha="right")
        ax.set_yticks(range(len(labels)), labels=labels)
        for row_index, row in enumerate(matrix):
            for column_index, value in enumerate(row):
                ax.text(column_index, row_index, f"{value:.2f}\nn={aligned_counts[row_index][column_index]}", ha="center", va="center", fontsize=8)
        fig.colorbar(image, ax=ax, label="Pearson 相关系数")
        derived["correlations"] = correlations
    elif used_type == "correlation_scatter":
        left_item, right_item = series_items
        left_values, right_values = aligned_pair(left_item, right_item)
        if len(left_values) < 3:
            raise ValueError("两个变量同分钟对齐后的有效数据不足 3 个点，无法绘制相关散点图")
        fig, ax = plt.subplots(figsize=(8.5, 7), dpi=140)
        left_name = chart_series_label(left_item, "raw")
        right_name = chart_series_label(right_item, "raw")
        corr = pearson_correlation(left_values, right_values)
        ax.scatter(left_values, right_values, s=22, alpha=0.68, color=palette["colors"][0])
        left_avg = sum(left_values) / len(left_values)
        right_avg = sum(right_values) / len(right_values)
        denominator = sum((value - left_avg) ** 2 for value in left_values)
        slope = sum((x - left_avg) * (y - right_avg) for x, y in zip(left_values, right_values)) / denominator if denominator > 1e-12 else 0.0
        intercept = right_avg - slope * left_avg
        x_line = [min(left_values), max(left_values)]
        ax.plot(x_line, [slope * value + intercept for value in x_line], color=palette["colors"][1], linewidth=2, label=f"线性拟合 r={corr:.3f}" if corr is not None else "线性拟合")
        ax.set_xlabel(left_name)
        ax.set_ylabel(right_name)
        ax.legend(loc="best")
        derived["correlation"] = {
            "left": str((left_item.get("variable") or {}).get("variable_name") or left_item.get("requested_variable")),
            "right": str((right_item.get("variable") or {}).get("variable_name") or right_item.get("requested_variable")),
            "pearson_r": corr,
            "aligned_count": len(left_values),
            "linear_slope": slope,
            "linear_intercept": intercept,
        }
    elif used_type == "distribution":
        columns = 2 if len(series_items) > 1 else 1
        rows_count = math.ceil(len(series_items) / columns)
        fig, axes_value = plt.subplots(rows_count, columns, figsize=(12, max(5, rows_count * 3.5)), dpi=140, squeeze=False)
        axes_flat = [axis for row in axes_value for axis in row]
        for index, item in enumerate(series_items):
            axis = axes_flat[index]
            _, values = chart_series_xy(item, scale)
            label = chart_series_label(item, scale)
            if not values:
                axis.set_visible(False)
                continue
            bins = max(6, min(30, int(math.sqrt(len(values))) + 1))
            axis.hist(values, bins=bins, alpha=0.74, color=palette["colors"][index % len(palette["colors"])], edgecolor=palette["axes"])
            avg = sum(values) / len(values)
            ordered = sorted(values)
            middle = len(ordered) // 2
            median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
            axis.axvline(avg, linestyle="--", color=palette["colors"][1], label=f"均值 {avg:.3g}")
            axis.axvline(median, linestyle=":", color=palette["colors"][2], label=f"中位数 {median:.3g}")
            axis.set_title(label)
            axis.legend(fontsize=8)
        for axis in axes_flat[len(series_items):]:
            axis.set_visible(False)
        ax = axes_flat[0]
    else:
        fig, ax = plt.subplots(figsize=(max(8, len(series_items) * 1.35), 6.5), dpi=140)
        values_list: list[list[float]] = []
        labels: list[str] = []
        for item in series_items:
            _, values = chart_series_xy(item, scale)
            if values:
                values_list.append(values)
                labels.append(str((item.get("variable") or {}).get("variable_name") or item.get("requested_variable")))
        if not values_list:
            raise ValueError("没有可绘制的箱线图数据")
        try:
            boxes = ax.boxplot(values_list, tick_labels=labels, patch_artist=True, showmeans=True)
        except TypeError:  # Matplotlib < 3.9 compatibility on older production hosts.
            boxes = ax.boxplot(values_list, labels=labels, patch_artist=True, showmeans=True)
        for index, box in enumerate(boxes["boxes"]):
            box.set_facecolor(palette["colors"][index % len(palette["colors"])])
            box.set_alpha(0.62)
        ax.tick_params(axis="x", rotation=25)
        if scale == "minmax":
            ax.set_ylabel("归一化值（每个变量 0-100）")
        elif scale == "zscore":
            ax.set_ylabel("标准化值（每个变量 z-score）")
        else:
            ax.set_ylabel("原始值")

    fig.patch.set_facecolor(palette["figure"])
    for axis in fig.axes:
        axis.set_facecolor(palette["axes"])
        axis.tick_params(colors=palette["text"])
        axis.xaxis.label.set_color(palette["text"])
        axis.yaxis.label.set_color(palette["text"])
        axis.title.set_color(palette["text"])
        for spine in axis.spines.values():
            spine.set_color(palette["grid"])
        if axis is not fig.axes[-1] or used_type != "correlation_heatmap":
            axis.grid(True, linestyle="--", alpha=0.24, color=palette["grid"])
    chart_title = title.strip() if title else f"GL02 数据分析图：{chart_time_label(start_time)} 至 {chart_time_label(end_time)}"
    fig.suptitle(chart_title, color=palette["text"], fontsize=14)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Glyph .* missing from font.*")
        warnings.filterwarnings("ignore", category=UserWarning, module=r"matplotlib\..*")
        fig.tight_layout(rect=(0, 0, 1, 0.96))

    filename = f"gl02_{used_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
    path = CHARTS_DIR / filename
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r"Glyph .* missing from font.*")
            warnings.filterwarnings("ignore", category=UserWarning, module=r"matplotlib\..*")
            fig.savefig(path)
    finally:
        plt.close(fig)
    return {
        "path": path,
        "url": chart_url_for(path),
        "analysis_type_used": used_type,
        "derived": derived,
    }


def query_statistics_derived_t_top(
    start_time: str,
    end_time: str,
    source_preference: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows, source = query_history_derived_t_top(start_time, end_time, MAX_HISTORY_LIMIT, source_preference=source_preference)
    return statistics_from_rows(rows), source


@mcp.tool()
def query_bf2_operation_log_report(workdate: str = "", limit: int = 200) -> dict[str, Any]:
    """查询 2# 高炉冀南新区高炉作业日志报表的已落库数据。

    该报表保留全部返回单元格；``fuel_ratio`` 是 Raqsoft 页面公式重算值，
    ``report_batch_count`` 是 D 列“批数”。料速语义尚未现场确认，因此返回
    ``material_rate=null`` 和明确的 ``material_rate_status``，避免把批数误报为料速。
    """
    day = (workdate or datetime.now(LOCAL_TZ).strftime("%Y-%m-%d"))[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("workdate 必须是 YYYY-MM-DD") from exc
    limit = max(1, min(int(limit or 200), 5000))
    profile = get_profile()
    if profile.get("engine") != "bf_sensor_postgresql":
        return {
            "ok": False,
            "error": "report_dataset_requires_postgresql",
            "message": "当前 BF_MCP_DB_PROFILE 不是 bf_sensor_postgresql，未查询报表库。",
        }
    psycopg, dict_row = import_psycopg()
    query = """
        SELECT workdate, report_row_number, report_id,
               report_time_raw, report_time_display,
               report_batch_count, report_coal_ratio, report_fuel_ratio,
               material_rate, material_rate_status, material_rate_note,
               report_headers, report_cells, fetched_at, updated_at
        FROM bf_imes.v_bf2_operation_log_report
        WHERE workdate = %s::date
        ORDER BY report_row_number
        LIMIT %s
    """
    try:
        with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(query, (day, limit))
                rows = [
                    {key: jsonable(value) for key, value in dict(row).items()}
                    for row in cur.fetchall()
                ]
    except Exception as exc:
        return {
            "ok": False,
            "workdate": day,
            "error": type(exc).__name__,
            "message": "报表视图不可用或数据库连接失败；请先执行 IMES 报表迁移/同步。",
        }
    return {
        "ok": True,
        "source": "bf_imes.v_bf2_operation_log_report",
        "furnace": "2#高炉",
        "workdate": day,
        "rows_count": len(rows),
        "rows": rows,
        "semantics": {
            "report_fuel_ratio": "Raqsoft 页面 M 列公式重算，不是 IMES 原始字段",
            "report_batch_count": "Raqsoft 页面 D 列批数",
            "material_rate": "语义待现场确认，当前不由批数推断",
        },
    }


def latest_snapshot_value(variable_name: str) -> dict[str, Any] | None:
    sql = """
        SELECT source_time, created_at, values_json, data_quality_json
        FROM furnace_snapshots
        ORDER BY created_at DESC
        LIMIT 1
    """
    try:
        with raw_pg_connect() as conn:
            ensure_assistant_schema(conn)
            row = conn.execute(sql).fetchone()
    except Exception:
        return None
    if not row:
        return None
    values = json.loads(row["values_json"] or "{}")
    quality = json.loads(row["data_quality_json"] or "{}")
    if variable_name not in values:
        return None
    return {
        "ts": row["source_time"] or row["created_at"],
        "value": values.get(variable_name),
        "quality": quality.get(variable_name),
        "source": "furnace_snapshots.values_json",
    }


@mcp.tool()
def list_business_objects(
    object_type: str = "",
    capability: str = "",
    status: str = "enabled",
    limit: int = 200,
) -> dict[str, Any]:
    """
    列出统一业务对象目录。可按object_type、capability和status筛选。
    object_type支持sensor、heat、hot_metal_analysis、slag_analysis、feed_chemistry、
    report、qa_history、calculation、chart。模型需要了解系统能查询或计算什么时优先调用。
    """
    items = list_catalog_objects(
        BUSINESS_OBJECT_CATALOG,
        object_type=normalize_text(object_type),
        capability=normalize_text(capability),
        status=normalize_text(status),
        limit=limit,
    )
    return {
        "ok": True,
        "catalog_version": BUSINESS_OBJECT_CATALOG["catalog_version"],
        "count": len(items),
        "total_count": BUSINESS_OBJECT_CATALOG["count"],
        "counts_by_type": BUSINESS_OBJECT_CATALOG["counts_by_type"],
        "filters": {"object_type": object_type, "capability": capability, "status": status},
        "objects": items,
    }


@mcp.tool()
def search_business_objects(
    query: str,
    object_types: list[str] | None = None,
    capability: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """
    在统一业务对象目录中搜索传感器、炉次、铁水/炉渣化验、进料化学成分、
    日报、历史问答、计算指标和图表类型。返回标准object_id、能力和执行工具。
    当用户对象名称不确定或问题跨传感器与业务化验时，应先调用本工具。
    """
    matches = search_catalog_objects(
        BUSINESS_OBJECT_CATALOG,
        query=query,
        object_types=object_types,
        capability=normalize_text(capability),
        limit=limit,
    )
    return {
        "ok": True,
        "query": query,
        "count": len(matches),
        "matches": matches,
    }


@mcp.tool()
def get_business_object(object_id: str) -> dict[str, Any]:
    """
    按统一object_id获取一个业务对象的显示名、别名、单位、能力、状态和执行器。
    例如P_top、hot_metal_chemistry、blast_furnace_slag_chemistry。
    """
    item = get_catalog_object(BUSINESS_OBJECT_CATALOG, object_id)
    if item is None:
        return {
            "ok": False,
            "error": "BUSINESS_OBJECT_NOT_FOUND",
            "object_id": object_id,
            "message": "统一业务对象目录中不存在该object_id。",
        }
    return {"ok": True, "object": item}


@mcp.tool()
def find_gl02_variables(keyword: str, limit: int = 10) -> dict[str, Any]:
    """
    按变量名、短名、点ID、完整长名、描述和用途检索 GL02 SIO 变量。
    用户说“炉顶温度”“炉顶压力”“南北探尺”“A-D上升管压力/温度”“富氧率”“出铁口温度”这类口语名称时，应先调用本工具。
    """
    return {
        "ok": True,
        "query": keyword,
        "root_path": MAPPING_CONFIG.get("root_path", "\\冀南钢铁\\SIO\\GL02"),
        "matches": search_variables(keyword, limit),
    }


@mcp.tool()
def get_gl02_variable_info(variable: str) -> dict[str, Any]:
    """
    查询 GL02 变量元数据。variable 可以是变量名、短名、点ID、完整长名或描述关键词。
    """
    v = resolve_variable(variable)
    return {"ok": True, "variable": public_variable(v)}


@mcp.tool()
def list_gl02_available_variables(include_medium_confidence: bool = True, limit: int = 200) -> dict[str, Any]:
    """
    列出当前 GL02 SIO 映射中可用的变量。
    include_medium_confidence=false 时只返回 high confidence 的 available 变量。
    """
    limit = max(1, min(int(limit or 200), 500))
    items = []
    for v in VARIABLES:
        status = v.get("status", "")
        confidence = v.get("confidence", "")
        if not include_medium_confidence and (status != "available" or confidence != "high"):
            continue
        if status in {"missing", "disabled"}:
            continue
        items.append(public_variable(v))
    return {
        "ok": True,
        "count": min(len(items), limit),
        "variables": items[:limit],
        "root_path": MAPPING_CONFIG.get("root_path", "\\冀南钢铁\\SIO\\GL02"),
    }


@mcp.tool()
def get_latest_gl02_value(variable: str, source_preference: str = "auto") -> dict[str, Any]:
    """
    查询某个 GL02 变量的最新 1 分钟均值。
    用户问“告诉我一下某指标”“现在某指标多少”“给我说一下炉顶的温度/压力”时适用。
    分点查询应传精确标准变量，例如 L_south、L_north、P_top_A-D、T_top_A-D、T_taphole_1/2，不得退化成总量变量。
    历史名称 P_top_gas_A-D 仅作为兼容别名接受，不再作为目录对外标准名。
    source_preference 可为 auto/database/pspace；auto 会先查 PostgreSQL，本地库无数据时再查 pSpace。
    """
    v = resolve_variable(variable)
    meta = public_variable(v)
    source_preference = extension_source_preference(meta, source_preference)
    if meta.get("variable_name") == "T_top":
        row, source = query_latest_derived_t_top(source_preference=source_preference)
        if row:
            return {"ok": True, "variable": meta, "latest": row, "source": {**source, "derived": True}}
        return {
            "ok": False,
            "error": "NO_DATA",
            "message": "没有查询到 T_top_A-D 组件的最新值，无法派生 T_top。",
            "variable": meta,
            "source": {**source, "derived": True},
        }
    tag = meta.get("tag_long_name")
    if not tag:
        return {
            "ok": False,
            "error": "DERIVED_NOT_MATERIALIZED",
            "message": "该变量是派生变量或未配置物理 tag，当前 MCP 版本不直接查询其时序值。",
            "variable": meta,
        }
    row, source = query_latest_from_storage(tag, source_preference=source_preference)
    if row:
        return {"ok": True, "variable": meta, "latest": row, "source": source}

#如果没查到不再返回快照了
    # fallback = latest_snapshot_value(meta["variable_name"])
    # if fallback:
    #     return {
    #         "ok": True,
    #         "variable": meta,
    #         "latest": fallback,
    #         "source": {"type": "postgresql", "schema": schema_name(), "table": "furnace_snapshots", "read_policy": "readonly"},
    #     }

    return {
        "ok": False,
        "error": "NO_DATA",
        "message": "没有查询到该变量的最新值。",
        "variable": meta,
        "source": source,
    }


@mcp.tool()
def query_gl02_history(
    variable: str,
    start_time: str,
    end_time: str,
    limit: int = DEFAULT_HISTORY_LIMIT,
    source_preference: str = "auto",
) -> dict[str, Any]:
    """
    查询某个 GL02 变量在指定 ISO8601 时间范围内的 1 分钟均值历史数据。
    source_preference 可为 auto/database/pspace；auto 会先查 PostgreSQL，本地库无数据时再查 pSpace。
    """
    v = resolve_variable(variable)
    meta = public_variable(v)
    source_preference = extension_source_preference(meta, source_preference)
    start_time, end_time = validate_time_range(start_time, end_time)
    limit = clamp_limit(limit)
    if meta.get("variable_name") == "T_top":
        rows, source = query_history_derived_t_top(start_time, end_time, limit, source_preference=source_preference)
        return {
            "ok": True,
            "variable": meta,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "count": len(rows),
            "data": rows,
            "source": {**source, "derived": True},
        }
    tag = meta.get("tag_long_name")
    if not tag:
        return {
            "ok": False,
            "error": "DERIVED_NOT_MATERIALIZED",
            "message": "该变量是派生变量或未配置物理 tag，当前 MCP 版本不直接查询其历史曲线。",
            "variable": meta,
        }
    rows, source = query_history_from_storage(tag, start_time, end_time, limit, source_preference=source_preference)
    return {
        "ok": True,
        "variable": meta,
        "start_time": start_time,
        "end_time": end_time,
        "limit": limit,
        "count": len(rows),
        "data": rows,
        "source": source,
    }


@mcp.tool()
def query_gl02_statistics(
    variable: str,
    start_time: str,
    end_time: str,
    agg: str = "avg",
    source_preference: str = "auto",
) -> dict[str, Any]:
    """
    查询某个 GL02 变量在指定时间范围内的统计值。
    用户问“最近半小时稳不稳”“有没有波动”“平均多少”“最高最低是多少”“变化大不大”时适用。
    agg 可为 avg、min、max、count、stddev、slope、trend、first、last、all。
    source_preference 可为 auto/database/pspace；auto 会先查 PostgreSQL，本地库无数据时再查 pSpace。
    """
    allowed = {"avg", "min", "max", "count", "stddev", "slope", "slope_per_min", "trend", "first", "last", "all"}
    agg = normalize_text(agg) or "avg"
    if agg not in allowed:
        raise ValueError(f"agg 只允许 {sorted(allowed)}")
    result_key = "slope_per_min" if agg == "slope" else agg
    v = resolve_variable(variable)
    meta = public_variable(v)
    source_preference = extension_source_preference(meta, source_preference)
    start_time, end_time = validate_time_range(start_time, end_time)
    if meta.get("variable_name") == "T_top":
        stats, source = query_statistics_derived_t_top(start_time, end_time, source_preference=source_preference)
        result = stats if agg == "all" else {result_key: stats.get(result_key), "count": stats.get("count")}
        return {
            "ok": True,
            "variable": meta,
            "start_time": start_time,
            "end_time": end_time,
            "agg": agg,
            "statistics": result,
            "source": {**source, "derived": True},
        }
    tag = meta.get("tag_long_name")
    if not tag:
        return {
            "ok": False,
            "error": "DERIVED_NOT_MATERIALIZED",
            "message": "该变量是派生变量或未配置物理 tag，当前 MCP 版本不直接统计其时序值。",
            "variable": meta,
        }
    stats, source = query_statistics_from_storage(tag, start_time, end_time, source_preference=source_preference)
    result = stats if agg == "all" else {result_key: stats.get(result_key), "count": stats.get("count")}
    return {
        "ok": True,
        "variable": meta,
        "start_time": start_time,
        "end_time": end_time,
        "agg": agg,
        "statistics": result,
        "source": source,
    }


@mcp.tool()
def query_gl02_sensors(
    variables: list[str],
    query_type: str = "latest",
    start_time: str = "",
    end_time: str = "",
    agg: str = "all",
    max_points_per_variable: int = 120,
    source_preference: str = "auto",
) -> dict[str, Any]:
    """
    统一查询一个或多个 GL02 传感器。variables 可传标准变量名、短名、点ID、完整长名、
    唯一描述或炉体温度点位（例如 T_body_L7_A / 7层A炉体温度）。
    query_type=latest 返回各点当前值和数据时间；history 返回同一时间窗历史数据；
    statistics 返回同一时间窗统计值。单个点和多个点使用同一合同，允许部分点无数据并逐项返回错误。
    history/statistics 必须提供 start_time/end_time；query_type 支持 latest/history/statistics。
    本工具只读，不执行任意 SQL，也不写生产控制。
    """
    names = parse_variables_arg(variables, max_items=80)
    mode_aliases = {
        "latest": "latest",
        "current": "latest",
        "realtime": "latest",
        "history": "history",
        "historical": "history",
        "trend": "history",
        "statistics": "statistics",
        "stats": "statistics",
        "summary": "statistics",
    }
    query_mode = mode_aliases.get(normalize_text(query_type))
    if query_mode is None:
        raise ValueError("query_type 只支持 latest/history/statistics。")
    if query_mode in {"history", "statistics"}:
        start_time, end_time = validate_time_range(start_time, end_time)
    limit = clamp_limit(max_points_per_variable, default=120, maximum=MAX_HISTORY_LIMIT)
    items: list[dict[str, Any]] = []
    batch_handled = False
    if query_mode == "latest" and names:
        try:
            resolved = [resolve_variable(name) for name in names]
        except Exception:  # preserve per-item partial failure behavior below
            resolved = []
        if resolved and all(item.get("variable_name") in STATIC_PRESSURE_EXTENSION_VARIABLES for item in resolved):
            meta_by_name = {name: public_variable(item) for name, item in zip(names, resolved)}
            rows = query_pspace_latest_many([meta_by_name[name]["tag_long_name"] for name in names])
            for name in names:
                meta = meta_by_name[name]
                row = rows.get(meta["tag_long_name"])
                if row:
                    items.append({"requested_variable": name, "ok": True, "variable": meta, "latest": row, "source": pspace_profile_summary()})
                else:
                    items.append({"requested_variable": name, "ok": False, "error": "NO_DATA", "message": "没有查询到该变量的最新值。", "variable": meta, "source": pspace_profile_summary()})
            batch_handled = True
    for name in names:
        if batch_handled:
            break
        try:
            if query_mode == "latest":
                result = get_latest_gl02_value(name, source_preference=source_preference)
            elif query_mode == "history":
                result = query_gl02_history(
                    name,
                    start_time,
                    end_time,
                    limit=limit,
                    source_preference=source_preference,
                )
            else:
                result = query_gl02_statistics(
                    name,
                    start_time,
                    end_time,
                    agg=agg,
                    source_preference=source_preference,
                )
            items.append({"requested_variable": name, **result})
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    "requested_variable": name,
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
            )
    success_count = sum(1 for item in items if item.get("ok"))
    return {
        "ok": success_count > 0,
        "tool": "query_gl02_sensors",
        "query_type": query_mode,
        "variables": names,
        "variable_count": len(names),
        "success_count": success_count,
        "failure_count": len(names) - success_count,
        "partial": 0 < success_count < len(names),
        "start_time": start_time or None,
        "end_time": end_time or None,
        "agg": agg if query_mode == "statistics" else None,
        "max_points_per_variable": limit if query_mode == "history" else None,
        "items": items,
        "notes": ["按变量逐项只读查询；无数据或变量错误不会阻断其他变量。"],
    }


@mcp.tool()
def query_gl02_feature_statistics(
    variable: str,
    start_time: str,
    end_time: str,
    baseline_day: str = "",
    baseline_days: int = 30,
    source_preference: str = "auto",
    max_points: int = FEATURE_MAX_HISTORY_LIMIT,
) -> dict[str, Any]:
    """
    查询某个 GL02 变量在指定时间范围内的增强统计和诊断特征。
    返回范围统计、最近 60 分钟/15 分钟窗口、30 天 daily_baselines、z60、z15、zstd 和斜率 Z。
    """
    v = resolve_variable(variable)
    meta = public_variable(v)
    start_time, end_time = validate_time_range(start_time, end_time)
    limit = clamp_limit(max_points, default=FEATURE_MAX_HISTORY_LIMIT, maximum=FEATURE_MAX_HISTORY_LIMIT)
    end_dt = parse_datetime_value(end_time)
    if end_dt.tzinfo is not None:
        end_dt = end_dt.astimezone(LOCAL_TZ)
    window60_start = (end_dt - timedelta(minutes=60)).isoformat(timespec="seconds")
    window15_start = (end_dt - timedelta(minutes=15)).isoformat(timespec="seconds")

    if meta.get("variable_name") == "T_top":
        rows, source = query_history_derived_t_top(start_time, end_time, limit, source_preference=source_preference)
        rows60, _ = query_history_derived_t_top(window60_start, end_time, 120, source_preference=source_preference)
        rows15, _ = query_history_derived_t_top(window15_start, end_time, 60, source_preference=source_preference)
    else:
        tag = meta.get("tag_long_name")
        if not tag:
            return {
                "ok": False,
                "error": "DERIVED_NOT_MATERIALIZED",
                "message": "该变量是派生变量或未配置物理 tag，当前 MCP 版本不能计算其增强统计。",
                "variable": meta,
            }
        rows, source = query_history_from_storage(tag, start_time, end_time, limit, source_preference=source_preference)
        rows60, _ = query_history_from_storage(tag, window60_start, end_time, 120, source_preference=source_preference)
        rows15, _ = query_history_from_storage(tag, window15_start, end_time, 60, source_preference=source_preference)

    baseline, baseline_source = query_daily_baseline(
        baseline_variable_candidates(meta),
        end_time=end_time,
        baseline_day=baseline_day,
        baseline_days=int(baseline_days or 30),
    )
    features = feature_statistics_payload(rows, end_time, baseline, last60_rows=rows60, last15_rows=rows15)
    return {
        "ok": True,
        "tool": "query_gl02_feature_statistics",
        "variable": meta,
        "start_time": start_time,
        "end_time": end_time,
        "count": len(rows),
        "limit": limit,
        "data_limited": len(rows) >= limit,
        "features": features,
        "source": source,
        "baseline_source": baseline_source,
        "notes": [
            "z60/z15/zstd 使用 daily_baselines 的 median_ref/iqr_ref，zstd 与当前规则引擎兼容：std15/(iqr_ref/1.35)。",
            "当 data_limited=true 时，范围统计只覆盖返回的前 limit 个点；缩短时间窗或提高 BF_MCP_FEATURE_MAX_HISTORY_LIMIT 后再测长窗口。",
        ],
    }


def normalize_body_temperature_positions(positions: list[str] | str | None) -> list[str]:
    """Normalize body-temperature sectors while preserving the requested order."""
    if positions is None:
        return list("ABCDEF")
    raw_items = [positions] if isinstance(positions, str) else list(positions)
    expanded: list[str] = []
    for raw in raw_items:
        token = str(raw or "").strip().upper().replace("—", "-").replace("－", "-")
        range_match = re.fullmatch(r"([A-H])\s*(?:-|到|至)\s*([A-H])", token)
        if range_match:
            start_code, end_code = (ord(value) for value in range_match.groups())
            step = 1 if start_code <= end_code else -1
            expanded.extend(chr(code) for code in range(start_code, end_code + step, step))
            continue
        compact = re.sub(r"[,，、;；\s]+", "", token)
        if compact and all(letter in "ABCDEFGH" for letter in compact):
            expanded.extend(compact)
            continue
        expanded.extend(item for item in re.split(r"[,，、;；\s]+", token) if item)
    out: list[str] = []
    for sector in expanded:
        if sector not in "ABCDEFGH":
            raise ValueError(f"炉体温度方位只支持 A-H，收到：{sector}")
        if sector not in out:
            out.append(sector)
    if not out:
        raise ValueError("positions 至少需要一个方位，例如 ['A','B','C','D','E','F']。")
    return out


def render_body_temperature_matrix(
    cells: list[dict[str, Any]],
    layers: list[int],
    positions: list[str],
    start_time: str,
    end_time: str,
    title: str,
) -> dict[str, Any]:
    """Render current-temperature heat cells with a one-hour sparkline in every cell."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from matplotlib import cm, colors

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    current_values = [float(cell["current_value"]) for cell in cells if cell.get("current_value") is not None]
    if not current_values:
        raise ValueError("所选炉体温度点在该时间窗内均无有效数据。")
    ordered = sorted(current_values)
    low_index = max(0, int((len(ordered) - 1) * 0.05))
    high_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))
    color_min = ordered[low_index]
    color_max = ordered[high_index]
    if math.isclose(color_min, color_max, rel_tol=1e-9, abs_tol=1e-9):
        color_min -= 1.0
        color_max += 1.0
    norm = colors.Normalize(vmin=color_min, vmax=color_max, clip=True)
    cmap = matplotlib.colormaps.get_cmap("turbo")

    rows_count = len(layers)
    columns_count = len(positions)
    fig_width = max(12.5, columns_count * 2.25)
    fig_height = max(12.0, rows_count * 1.62 + 2.3)
    fig, axes = plt.subplots(rows_count, columns_count, figsize=(fig_width, fig_height), dpi=145, squeeze=False)
    fig.patch.set_facecolor("#e7ecef")
    cell_by_key = {(int(cell["layer"]), str(cell["position"])): cell for cell in cells}

    for row_index, layer in enumerate(layers):
        for column_index, position in enumerate(positions):
            ax = axes[row_index][column_index]
            cell = cell_by_key.get((layer, position)) or {}
            current = cell.get("current_value")
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color("#263238")
                spine.set_linewidth(0.8)
            if row_index == 0:
                ax.set_title(f"{position} 方位", fontsize=12, fontweight="bold", color="#263238", pad=8)
            if column_index == 0:
                ax.set_ylabel(f"{layer} 层", fontsize=12, fontweight="bold", color="#263238", labelpad=10)
            if current is None:
                ax.set_facecolor("#c7ced2")
                ax.text(0.5, 0.54, "无数据", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="#455a64", fontweight="bold")
                ax.text(0.5, 0.25, "最近1小时", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="#607d8b")
                continue

            rgba = cmap(norm(float(current)))
            ax.set_facecolor(rgba)
            luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
            foreground = "#102027" if luminance > 0.58 else "#ffffff"
            rows = sorted(
                [row for row in cell.get("rows") or [] if row_datetime(row) is not None and numeric_row_value(row) is not None],
                key=lambda row: row_datetime(row) or datetime.min,
            )
            if rows:
                timestamps = [row_datetime(row) for row in rows]
                values = [float(numeric_row_value(row) or 0.0) for row in rows]
                line_color = "#111820" if luminance > 0.64 else "#ffffff"
                ax.plot(timestamps, values, color=line_color, linewidth=1.35, alpha=0.96)
                ax.fill_between(timestamps, values, min(values), color=line_color, alpha=0.11)
                ax.scatter(timestamps[-1], values[-1], s=13, color=line_color, zorder=3)
                lower = min(values)
                upper = max(values)
                padding = max((upper - lower) * 0.18, abs(upper) * 0.012, 0.8)
                ax.set_ylim(lower - padding, upper + padding)
            summary = cell.get("summary") or {}
            trend = str(summary.get("trend") or "无法判断")
            last_ts = row_datetime((summary.get("last") or {}))
            sample_time = last_ts.strftime("%H:%M") if last_ts else "--:--"
            unit = str(cell.get("unit") or "℃")
            ax.text(
                0.04,
                0.90,
                f"{float(current):.1f}{unit}",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=12.5,
                color=foreground,
                fontweight="bold",
                bbox={"boxstyle": "round,pad=0.18", "facecolor": (1, 1, 1, 0.25) if luminance < 0.58 else (1, 1, 1, 0.45), "edgecolor": "none"},
            )
            ax.text(0.96, 0.90, sample_time, transform=ax.transAxes, ha="right", va="top", fontsize=7.8, color=foreground)
            ax.text(0.96, 0.08, trend, transform=ax.transAxes, ha="right", va="bottom", fontsize=8.3, color=foreground, fontweight="bold")

    window_label = f"{chart_time_label(start_time)} 至 {chart_time_label(end_time)}"
    chart_title = title.strip() or f"GL02 炉体温度热力趋势矩阵（{layers[0]}–{layers[-1]}层，{positions[0]}–{positions[-1]}方位）"
    fig.suptitle(chart_title, fontsize=18, fontweight="bold", color="#263238", y=0.992)
    fig.text(0.5, 0.969, f"底色＝当前温度　折线＝最近1小时趋势　数据窗：{window_label}", ha="center", va="top", fontsize=10, color="#455a64")
    scalar = cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar.set_array([])
    fig.subplots_adjust(left=0.075, right=0.985, top=0.945, bottom=0.09, hspace=0.28, wspace=0.12)
    color_axis = fig.add_axes([0.14, 0.026, 0.72, 0.012])
    colorbar = fig.colorbar(scalar, cax=color_axis, orientation="horizontal")
    colorbar.set_label("当前温度（℃，颜色范围按有效点 5%–95% 分位）", fontsize=10)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Glyph .* missing from font.*")
        warnings.filterwarnings("ignore", category=UserWarning, module=r"matplotlib\..*")
        filename = f"gl02_body_temperature_matrix_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        path = CHARTS_DIR / filename
        fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return {
        "path": path,
        "url": chart_url_for(path),
        "color_min": color_min,
        "color_max": color_max,
    }


@mcp.tool()
def plot_gl02_trends(
    variables: list[str],
    start_time: str,
    end_time: str,
    scale: str = "raw",
    source_preference: str = "auto",
    max_points_per_variable: int = 720,
    title: str = "",
    chart_type: str = "auto",
    moving_average_points: int = 0,
    show_extrema: bool = False,
    show_latest: bool = True,
    reference_values: dict[str, float] | None = None,
    theme: str = "industrial",
) -> dict[str, Any]:
    """
    生成一个或多个 GL02 变量的趋势图 PNG，并返回图片路径、可访问 URL 和各变量统计摘要。
    用户问“画一下”“画个走势”“趋势图”“对比图”“顶温和顶压这一小时走势”时适用。
    variables 应传变量名数组，例如 ["T_top"]、["T_top","P_top"] 或 ["L_south","L_north"]；A-D 分点应分别传入四个精确变量。
    scale=raw 使用原始值；scale=minmax 适合不同单位变量做 0-100 归一化对比；scale=zscore 适合波动形态对比。
    chart_type=auto 会按单位自动选择折线、双轴或分面；还支持 line、area、step、scatter、dual_axis、small_multiples。
    moving_average_points 可叠加移动平均；show_extrema/show_latest 可标注极值和最新值；reference_values 可按标准变量名画参考线。
    theme 支持 industrial、light、dark。关系图、相关矩阵、分布图和箱线图请调用 plot_gl02_analysis。
    """
    # REQ-QA-CHART-COVERAGE-20260917: support all three heights A-F.
    names = parse_variables_arg(variables, max_items=24)
    if (
        os.getenv("BF_MCP_PLOT_WORKER") != "1"
        and os.getenv("BF_MCP_PLOT_SUBPROCESS", "1").strip().lower() not in {"0", "false", "no", "off"}
    ):
        worker_payload = {
            "_tool": "plot_gl02_trends",
            "variables": variables,
            "start_time": start_time,
            "end_time": end_time,
            "scale": scale,
            "source_preference": source_preference,
            "max_points_per_variable": max_points_per_variable,
            "title": title,
            "chart_type": chart_type,
            "moving_average_points": moving_average_points,
            "show_extrema": show_extrema,
            "show_latest": show_latest,
            "reference_values": reference_values,
            "theme": theme,
        }
        env = dict(os.environ)
        env["BF_MCP_PLOT_WORKER"] = "1"
        env.setdefault("MPLBACKEND", "Agg")
        timeout = int(os.getenv("BF_MCP_PLOT_TIMEOUT_SECONDS", "45"))
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(Path(__file__).resolve())],
                input=json.dumps(worker_payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "PLOT_WORKER_TIMEOUT",
                "message": f"趋势图生成超过 {timeout} 秒未返回，请缩短时间窗或稍后重试。",
                "variables": names,
                "start_time": start_time,
                "end_time": end_time,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
                "variables": names,
                "start_time": start_time,
                "end_time": end_time,
            }
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "PLOT_WORKER_FAILED",
                "message": (proc.stderr or proc.stdout or "").strip()[-4000:],
                "variables": names,
                "start_time": start_time,
                "end_time": end_time,
            }
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": "PLOT_WORKER_BAD_JSON",
                "message": str(exc),
                "stdout": (proc.stdout or "")[:2000],
                "stderr": (proc.stderr or "")[-2000:],
            }

    start_time, end_time = validate_time_range(start_time, end_time)
    scale = normalize_chart_scale(scale)
    chart_type = normalize_chart_type(chart_type)
    theme = normalize_chart_theme(theme)
    moving_average_points = max(0, min(int(moving_average_points or 0), 240))
    if reference_values is not None and not isinstance(reference_values, dict):
        raise ValueError("reference_values 必须是 {标准变量名: 数值} 对象。")
    limit = clamp_limit(max_points_per_variable, default=720, maximum=MAX_HISTORY_LIMIT)

    series_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    units = set()
    for name in names:
        try:
            history = query_gl02_history(
                name,
                start_time,
                end_time,
                limit=limit,
                source_preference=source_preference,
            )
            if not history.get("ok"):
                errors.append({"variable": name, "error": history.get("error"), "message": history.get("message")})
                continue
            rows = history.get("data") or []
            variable_meta = history.get("variable") or {}
            unit = str(variable_meta.get("unit") or "")
            if unit:
                units.add(unit)
            summary = series_summary(rows)
            series_items.append(
                {
                    "requested_variable": name,
                    "variable": variable_meta,
                    "rows": rows,
                    "count": len(rows),
                    "summary": summary,
                    "source": history.get("source"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"variable": name, "error": type(exc).__name__, "message": str(exc)})

    drawable = [item for item in series_items if (item.get("summary") or {}).get("count", 0) > 0]
    if not drawable:
        return {
            "ok": False,
            "error": "NO_DRAWABLE_DATA",
            "message": "指定变量在该时间窗内没有可绘制的有效数据。",
            "variables": names,
            "start_time": start_time,
            "end_time": end_time,
            "errors": errors,
        }

    chart = render_trend_chart(
        drawable,
        start_time,
        end_time,
        scale,
        title,
        chart_type=chart_type,
        moving_average_points=moving_average_points,
        show_extrema=bool(show_extrema),
        show_latest=bool(show_latest),
        reference_values=reference_values,
        theme=theme,
    )
    json_path = Path(str(chart["path"])).with_suffix(".json")
    compact_series = []
    for item in drawable:
        compact_series.append(
            {
                "requested_variable": item.get("requested_variable"),
                "variable": item.get("variable"),
                "count": item.get("count"),
                "summary": item.get("summary"),
                "source": item.get("source"),
            }
        )
    payload = {
        "ok": True,
        "tool": "plot_gl02_trends",
        "variables": names,
        "requested_variables": names,
        "covered_variables": [item["requested_variable"] for item in drawable],
        "missing_variables": [name for name in names if name not in {item["requested_variable"] for item in drawable}],
        "max_points_per_variable": limit,
        "start_time": start_time,
        "end_time": end_time,
        "scale": scale,
        "chart_type_requested": chart_type,
        "chart_type_used": chart["chart_type_used"],
        "theme": theme,
        "options": {
            "moving_average_points": moving_average_points,
            "show_extrema": bool(show_extrema),
            "show_latest": bool(show_latest),
            "reference_values": reference_values or {},
        },
        "image_path": str(chart["path"]),
        "image_url": chart["url"],
        "data_path": str(json_path),
        "series": compact_series,
        "errors": errors,
        "notes": [],
    }
    if len(units) > 1 and scale == "raw":
        if chart["chart_type_used"] in {"dual_axis", "small_multiples"}:
            payload["notes"].append(f"检测到不同单位，已自动使用 {chart['chart_type_used']} 保留各变量原始量纲。")
        else:
            payload["notes"].append("多个变量单位不同，原始值同轴对比可能失真；建议使用 chart_type=dual_axis/small_multiples 或 scale=minmax。")
    if reference_values and scale != "raw":
        payload["notes"].append("reference_values 仅在 scale=raw 时绘制；本次缩放模式未画参考线。")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload["markdown"] = f"![GL02趋势图]({chart['url']})"
    return payload


@mcp.tool()
def plot_gl02_body_temperature_matrix(
    start_time: str,
    end_time: str,
    start_layer: int = 7,
    end_layer: int = 16,
    positions: list[str] | str | None = None,
    source_preference: str = "auto",
    max_points_per_cell: int = 120,
    title: str = "",
) -> dict[str, Any]:
    """
    绘制 GL02 炉体温度热力趋势矩阵：行是炉体层号，列是 A-H 方位；每格底色表示当前温度，
    格内折线表示指定时间窗（通常最近1小时）的历史趋势，并显示当前值、末次采样时间与升降趋势。
    默认绘制 7-16 层、A-F 方位；positions 可传 ['A','B','C','D','E','F'] 或 'A-H'。
    用户问“炉身/炉腹/炉缸各层各点温度大矩阵”“7到16层 A-F 热力矩阵、每格带1小时曲线”时优先调用本工具。
    缺测点保持灰色并明确标记无数据，不插值、不伪造。
    """
    if (
        os.getenv("BF_MCP_PLOT_WORKER") != "1"
        and os.getenv("BF_MCP_PLOT_SUBPROCESS", "1").strip().lower() not in {"0", "false", "no", "off"}
    ):
        worker_payload = {
            "_tool": "plot_gl02_body_temperature_matrix",
            "start_time": start_time,
            "end_time": end_time,
            "start_layer": start_layer,
            "end_layer": end_layer,
            "positions": positions,
            "source_preference": source_preference,
            "max_points_per_cell": max_points_per_cell,
            "title": title,
        }
        env = dict(os.environ)
        env["BF_MCP_PLOT_WORKER"] = "1"
        env.setdefault("MPLBACKEND", "Agg")
        timeout = int(os.getenv("BF_MCP_BODY_MATRIX_TIMEOUT_SECONDS", "90"))
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(Path(__file__).resolve())],
                input=json.dumps(worker_payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "PLOT_WORKER_TIMEOUT",
                "message": f"炉体温度矩阵生成超过 {timeout} 秒未返回，请稍后重试。",
                "start_time": start_time,
                "end_time": end_time,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "PLOT_WORKER_FAILED",
                "message": (proc.stderr or proc.stdout or "").strip()[-4000:],
                "start_time": start_time,
                "end_time": end_time,
            }
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": "PLOT_WORKER_BAD_JSON",
                "message": str(exc),
                "stdout": (proc.stdout or "")[:2000],
                "stderr": (proc.stderr or "")[-2000:],
            }

    start_time, end_time = validate_time_range(start_time, end_time)
    first_layer = int(start_layer)
    last_layer = int(end_layer)
    if first_layer > last_layer:
        first_layer, last_layer = last_layer, first_layer
    if first_layer < 7 or last_layer > 16:
        raise ValueError("炉体温度矩阵层号只支持 7-16 层。")
    sectors = normalize_body_temperature_positions(positions)
    layers = list(range(first_layer, last_layer + 1))
    limit = clamp_limit(max_points_per_cell, default=120, maximum=720)
    cells: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for layer in layers:
        for sector in sectors:
            variable = f"T_body_L{layer}_{sector}"
            try:
                history = query_gl02_history(
                    variable,
                    start_time,
                    end_time,
                    limit=limit,
                    source_preference=source_preference,
                )
                rows = history.get("data") or [] if history.get("ok") else []
                summary = series_summary(rows)
                current_row = summary.get("last") or {}
                current_value = numeric_row_value(current_row)
                variable_meta = history.get("variable") or {}
                cell = {
                    "layer": layer,
                    "position": sector,
                    "variable": variable,
                    "description": variable_meta.get("description") or f"{layer}层{sector}方位炉体温度",
                    "unit": variable_meta.get("unit") or "℃",
                    "rows": rows,
                    "count": summary.get("count") or 0,
                    "current_value": current_value,
                    "current_time": current_row.get("ts"),
                    "summary": summary,
                    "source": history.get("source"),
                }
                cells.append(cell)
                if current_value is None:
                    errors.append({"variable": variable, "error": history.get("error") or "NO_DATA", "message": history.get("message") or "时间窗内没有有效数值点。"})
            except Exception as exc:  # noqa: BLE001
                cells.append(
                    {
                        "layer": layer,
                        "position": sector,
                        "variable": variable,
                        "unit": "℃",
                        "rows": [],
                        "count": 0,
                        "current_value": None,
                        "current_time": None,
                        "summary": series_summary([]),
                        "source": None,
                    }
                )
                errors.append({"variable": variable, "error": type(exc).__name__, "message": str(exc)})

    available_cells = [cell for cell in cells if cell.get("current_value") is not None]
    if not available_cells:
        return {
            "ok": False,
            "error": "NO_DRAWABLE_DATA",
            "message": "所选炉体温度点在该时间窗内均无可绘制数据。",
            "start_time": start_time,
            "end_time": end_time,
            "layers": layers,
            "positions": sectors,
            "errors": errors,
        }
    chart = render_body_temperature_matrix(cells, layers, sectors, start_time, end_time, title)
    json_path = Path(str(chart["path"])).with_suffix(".json")
    audit_cells = [
        {
            "layer": cell["layer"],
            "position": cell["position"],
            "variable": cell["variable"],
            "description": cell.get("description"),
            "unit": cell.get("unit"),
            "count": cell.get("count"),
            "current_value": cell.get("current_value"),
            "current_time": cell.get("current_time"),
            "summary": cell.get("summary"),
            "source": cell.get("source"),
        }
        for cell in cells
    ]
    response_cells = [
        {
            "layer": cell["layer"],
            "position": cell["position"],
            "variable": cell["variable"],
            "unit": cell.get("unit"),
            "count": cell.get("count"),
            "current_value": cell.get("current_value"),
            "current_time": cell.get("current_time"),
            "min": (cell.get("summary") or {}).get("min"),
            "max": (cell.get("summary") or {}).get("max"),
            "delta": (cell.get("summary") or {}).get("delta"),
            "trend": (cell.get("summary") or {}).get("trend"),
        }
        for cell in cells
    ]
    all_current_values = [float(cell["current_value"]) for cell in available_cells]
    payload = {
        "ok": True,
        "tool": "plot_gl02_body_temperature_matrix",
        "start_time": start_time,
        "end_time": end_time,
        "layers": layers,
        "positions": sectors,
        "cell_count": len(cells),
        "available_cell_count": len(available_cells),
        "missing_cell_count": len(cells) - len(available_cells),
        "coverage_ratio": len(available_cells) / len(cells),
        "current_temperature_range": {"min": min(all_current_values), "max": max(all_current_values), "unit": "℃"},
        "heat_scale": {"min": chart["color_min"], "max": chart["color_max"], "method": "current_value_p05_p95"},
        "image_path": str(chart["path"]),
        "image_url": chart["url"],
        "data_path": str(json_path),
        "cells": response_cells,
        "errors": errors,
        "notes": ["底色表示当前温度；每格折线表示所选时间窗内的历史趋势；缺测格不做插值。"],
    }
    sidecar_payload = {**payload, "cells": audit_cells}
    json_path.write_text(json.dumps(sidecar_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload["markdown"] = f"![GL02炉体温度热力趋势矩阵]({chart['url']})"
    return payload


@mcp.tool()
def plot_gl02_analysis(
    variables: list[str],
    start_time: str,
    end_time: str,
    analysis_type: str = "auto",
    scale: str = "raw",
    source_preference: str = "auto",
    max_points_per_variable: int = 720,
    title: str = "",
    theme: str = "industrial",
) -> dict[str, Any]:
    """
    生成 GL02 变量关系或分布分析 PNG，并返回图片 URL、统计摘要与可审计派生指标。
    用户问“关系图/相关性/散点图”时用 correlation_scatter（两个变量）或 correlation_heatmap（多个变量）；
    问“数据分布/直方图”时用 distribution；问“箱线图/离群点对比”时用 boxplot。
    analysis_type=auto 在两个变量时选择相关散点图，三个及以上变量时选择相关矩阵。
    scale 支持 raw/minmax/zscore；不同单位的箱线图建议 minmax 或 zscore。
    """
    if (
        os.getenv("BF_MCP_PLOT_WORKER") != "1"
        and os.getenv("BF_MCP_PLOT_SUBPROCESS", "1").strip().lower() not in {"0", "false", "no", "off"}
    ):
        worker_payload = {
            "_tool": "plot_gl02_analysis",
            "variables": variables,
            "start_time": start_time,
            "end_time": end_time,
            "analysis_type": analysis_type,
            "scale": scale,
            "source_preference": source_preference,
            "max_points_per_variable": max_points_per_variable,
            "title": title,
            "theme": theme,
        }
        env = dict(os.environ)
        env["BF_MCP_PLOT_WORKER"] = "1"
        env.setdefault("MPLBACKEND", "Agg")
        timeout = int(os.getenv("BF_MCP_PLOT_TIMEOUT_SECONDS", "45"))
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(Path(__file__).resolve())],
                input=json.dumps(worker_payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "PLOT_WORKER_TIMEOUT",
                "message": f"分析图生成超过 {timeout} 秒未返回，请缩短时间窗或稍后重试。",
                "variables": parse_variables_arg(variables),
                "start_time": start_time,
                "end_time": end_time,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
                "variables": parse_variables_arg(variables),
                "start_time": start_time,
                "end_time": end_time,
            }
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": "PLOT_WORKER_FAILED",
                "message": (proc.stderr or proc.stdout or "").strip()[-4000:],
                "variables": parse_variables_arg(variables),
                "start_time": start_time,
                "end_time": end_time,
            }
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": "PLOT_WORKER_BAD_JSON",
                "message": str(exc),
                "stdout": (proc.stdout or "")[:2000],
                "stderr": (proc.stderr or "")[-2000:],
            }

    names = parse_variables_arg(variables)
    start_time, end_time = validate_time_range(start_time, end_time)
    analysis_type = normalize_analysis_type(analysis_type)
    scale = normalize_chart_scale(scale)
    theme = normalize_chart_theme(theme)
    limit = clamp_limit(max_points_per_variable, default=720, maximum=MAX_HISTORY_LIMIT)
    series_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    units: set[str] = set()
    for name in names:
        try:
            history = query_gl02_history(
                name,
                start_time,
                end_time,
                limit=limit,
                source_preference=source_preference,
            )
            if not history.get("ok"):
                errors.append({"variable": name, "error": history.get("error"), "message": history.get("message")})
                continue
            rows = history.get("data") or []
            variable_meta = history.get("variable") or {}
            unit = str(variable_meta.get("unit") or "")
            if unit:
                units.add(unit)
            summary = series_summary(rows)
            if (summary.get("count") or 0) <= 0:
                errors.append({"variable": name, "error": "NO_DATA", "message": "时间窗内没有有效数值点。"})
                continue
            series_items.append(
                {
                    "requested_variable": name,
                    "variable": variable_meta,
                    "rows": rows,
                    "count": len(rows),
                    "summary": summary,
                    "source": history.get("source"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"variable": name, "error": type(exc).__name__, "message": str(exc)})
    if not series_items:
        return {
            "ok": False,
            "error": "NO_DRAWABLE_DATA",
            "message": "指定变量在该时间窗内没有可绘制的有效数据。",
            "variables": names,
            "start_time": start_time,
            "end_time": end_time,
            "errors": errors,
        }
    if analysis_type in {"auto", "correlation_scatter", "correlation_heatmap"} and len(series_items) < 2:
        return {
            "ok": False,
            "error": "INSUFFICIENT_VARIABLES",
            "message": "相关分析至少需要两个有数据的变量。",
            "variables": names,
            "available_variables": [item["requested_variable"] for item in series_items],
            "errors": errors,
        }

    try:
        chart = render_analysis_chart(series_items, start_time, end_time, analysis_type, scale, title, theme)
    except ValueError as exc:
        return {
            "ok": False,
            "error": "INSUFFICIENT_ANALYSIS_DATA",
            "message": str(exc),
            "variables": names,
            "start_time": start_time,
            "end_time": end_time,
            "errors": errors,
        }
    json_path = Path(str(chart["path"])).with_suffix(".json")
    compact_series = [
        {
            "requested_variable": item.get("requested_variable"),
            "variable": item.get("variable"),
            "count": item.get("count"),
            "summary": item.get("summary"),
            "source": item.get("source"),
        }
        for item in series_items
    ]
    payload = {
        "ok": True,
        "tool": "plot_gl02_analysis",
        "variables": names,
        "start_time": start_time,
        "end_time": end_time,
        "analysis_type_requested": analysis_type,
        "analysis_type_used": chart["analysis_type_used"],
        "scale": scale,
        "theme": theme,
        "image_path": str(chart["path"]),
        "image_url": chart["url"],
        "data_path": str(json_path),
        "series": compact_series,
        "derived": chart["derived"],
        "errors": errors,
        "notes": [],
    }
    if chart["analysis_type_used"] == "boxplot" and len(units) > 1 and scale == "raw":
        payload["notes"].append("变量单位不同，原始值箱线图只适合查看各自分布范围；建议 scale=minmax 或 zscore 后比较形态。")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload["markdown"] = f"![GL02数据分析图]({chart['url']})"
    return payload


@mcp.tool()
def get_latest_furnace_snapshot() -> dict[str, Any]:
    """
    查询 PostgreSQL 助手库中最新的炉况快照。
    """
    sql = """
        SELECT id, source_time, created_at, values_json, diagnosis_json,
               recommendation_json, data_quality_json
        FROM furnace_snapshots
        ORDER BY created_at DESC
        LIMIT 1
    """
    try:
        with raw_pg_connect() as conn:
            ensure_assistant_schema(conn)
            row = conn.execute(sql).fetchone()
    except Exception as exc:
        return {"ok": False, "error": "POSTGRES_UNAVAILABLE", "message": str(exc)}
    if not row:
        return {"ok": False, "error": "NO_DATA", "message": "furnace_snapshots 暂无数据"}
    return {
        "ok": True,
        "snapshot": {
            "id": row["id"],
            "source_time": row["source_time"],
            "created_at": row["created_at"],
            "values": json.loads(row["values_json"] or "{}"),
            "diagnosis": json.loads(row["diagnosis_json"] or "{}"),
            "recommendation": json.loads(row["recommendation_json"] or "{}"),
            "data_quality": json.loads(row["data_quality_json"] or "{}"),
        },
        "source": {"type": "postgresql", "schema": schema_name(), "table": "furnace_snapshots", "read_policy": "readonly"},
    }


@mcp.tool()
def search_qa_messages(keyword: str, limit: int = 20) -> dict[str, Any]:
    """
    只读检索 PostgreSQL 中的 8092 QA 历史消息。用于回答“之前是否问过某问题”“历史回答怎么说”等问题。
    """
    keyword = str(keyword or "").strip()
    if not keyword:
        raise ValueError("keyword 不能为空")
    limit = max(1, min(int(limit or 20), 100))
    sql = """
        SELECT m.id, m.conversation_id, c.title, m.role, m.content,
               m.created_at
        FROM qa_messages m
        LEFT JOIN qa_conversations c ON c.id = m.conversation_id
        WHERE m.content ILIKE %s
        ORDER BY m.created_at DESC
        LIMIT %s
    """
    try:
        with raw_pg_connect() as conn:
            ensure_assistant_schema(conn)
            rows = conn.execute(sql, (f"%{keyword}%", limit)).fetchall()
    except Exception as exc:
        return {"ok": False, "error": "POSTGRES_UNAVAILABLE", "message": str(exc)}
    messages = []
    for row in rows:
        content = row["content"] or ""
        messages.append(
            {
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "conversation_title": row["title"],
                "role": row["role"],
                "created_at": row["created_at"],
                "excerpt": content[:800],
                "truncated": len(content) > 800,
            }
        )
    return {
        "ok": True,
        "keyword": keyword,
        "count": len(messages),
        "messages": messages,
        "source": {"type": "postgresql", "schema": schema_name(), "table": "qa_messages", "read_policy": "readonly"},
    }


@mcp.tool()
def list_recent_reports(report_type: str = "", start_date: str = "", end_date: str = "", limit: int = 20) -> dict[str, Any]:
    """
    在允许的报表根目录内列出近期 Markdown 报表。
    report_type 可传 日报、周报、月报、时报 或留空。
    start_date/end_date 当前按路径字符串粗筛，格式建议 YYYY-MM-DD 或 YYYY/MM/DD。
    """
    limit = max(1, min(int(limit or 20), 100))
    report_type = str(report_type or "").strip()
    start_key = str(start_date or "").replace("-", "/").strip()
    end_key = str(end_date or "").replace("-", "/").strip()
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", end_key):
        end_key = end_key + "/\uffff"
    items: list[dict[str, Any]] = []
    if not REPORTS_DIR.exists():
        return {"ok": False, "error": "REPORTS_DIR_NOT_FOUND", "message": f"报表目录不存在: {REPORTS_DIR}"}
    for path in REPORTS_DIR.rglob("*.md"):
        rel = path.relative_to(REPORTS_DIR).as_posix()
        if report_type and report_type not in rel and report_type not in path.name:
            continue
        if start_key and rel < start_key:
            continue
        if end_key and rel > end_key:
            continue
        stat = path.stat()
        items.append(
            {
                "report_path": rel,
                "name": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    items.sort(key=lambda x: x["modified_at"], reverse=True)
    return {"ok": True, "count": min(len(items), limit), "reports": items[:limit], "root": str(REPORTS_DIR)}


@mcp.tool()
def read_report_excerpt(report_path: str, mode: str = "excerpt", max_chars: int = 4000) -> dict[str, Any]:
    """
    读取报表 Markdown/Text 片段。只能读取 BF_REPORTS_DIR 根目录内文件。
    mode 可为 excerpt 或 full；full 也会受 max_chars 和系统上限限制。
    """
    mode = normalize_text(mode) or "excerpt"
    max_chars = max(200, min(int(max_chars or 4000), MAX_REPORT_CHARS))
    candidate = (REPORTS_DIR / report_path).resolve()
    try:
        candidate.relative_to(REPORTS_DIR)
    except ValueError as exc:
        raise ValueError("禁止读取报表根目录之外的文件") from exc
    if candidate.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("当前工具只允许读取 .md 或 .txt 报表文本")
    text = candidate.read_text(encoding="utf-8", errors="replace")
    total_chars = len(text)
    if mode != "full":
        text = text[:max_chars]
    else:
        text = text[:max_chars]
    return {
        "ok": True,
        "report_path": str(candidate.relative_to(REPORTS_DIR)),
        "mode": mode,
        "chars_returned": len(text),
        "total_chars": total_chars,
        "truncated": len(text) < total_chars,
        "content": text,
    }


@mcp.resource("bf://gl02/variables")
def gl02_variable_catalog() -> str:
    public_vars = [public_variable(v) for v in VARIABLES]
    return json.dumps(public_vars, ensure_ascii=False, indent=2)


@mcp.resource("bf://mcp/status")
def mcp_status() -> str:
    payload = {
        "ok": True,
        "name": MCP_NAME,
        "created_at": now_text(),
        "mapping_path": str(GL02_MAPPING_PATH),
        "storage": db_profile_summary(),
        "assistant_store": {"type": "postgresql", "schema": schema_name()},
        "reports_dir": str(REPORTS_DIR),
        "root_path": MAPPING_CONFIG.get("root_path", "\\冀南钢铁\\SIO\\GL02"),
        "read_policy": "readonly",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if os.getenv("BF_MCP_PLOT_WORKER") == "1":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            tool_name = str(payload.pop("_tool", "plot_gl02_trends"))
            if tool_name == "plot_gl02_analysis":
                result = plot_gl02_analysis(**payload)
            elif tool_name == "plot_gl02_body_temperature_matrix":
                result = plot_gl02_body_temperature_matrix(**payload)
            elif tool_name == "plot_gl02_trends":
                result = plot_gl02_trends(**payload)
            else:
                raise ValueError(f"未知绘图 worker 工具：{tool_name}")
            sys.stdout.write(json.dumps(result, ensure_ascii=False, default=str))
        except Exception as exc:  # noqa: BLE001
            sys.stdout.write(
                json.dumps(
                    {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                    ensure_ascii=False,
                    default=str,
                )
            )
            raise SystemExit(1)
    else:
        mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
