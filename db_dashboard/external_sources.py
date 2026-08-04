"""Read-only multi-source adapters for the heat-centric dashboard.

Requirement: REQ-HEAT-MULTISOURCE-EXPLORER-20260727

The module deliberately exposes an allow-list instead of accepting SQL, URLs or
pSpace tag paths from a browser.  Credentials are read from process variables
or ``PT/external_sources.local.env`` and are never returned by an API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable, Iterable
from urllib.parse import urljoin

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import requests

import heat_service


APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = (
    APP_ROOT.parent if APP_ROOT.name.startswith("standalone_heat_dashboard") else APP_ROOT
)
EXTERNAL_ENV = APP_ROOT / "PT" / "external_sources.local.env"
LEGACY_IMES_ENV = APP_ROOT / "PT" / "imes_vastbase.local.env"
DEFAULT_IMES_WEB_URL = "http://10.10.181.209:8080/imes.web/"
DEFAULT_PSPACE_HOST = "10.22.181.243"
DEFAULT_PSPACE_PORT = "8889"
DEFAULT_PSPACE_WS = "ws://127.0.0.1:8770"
PSPACE_MAX_POINTS_PER_TAG = 5000
PSPACE_MAX_TAGS = 133
SOURCE_TIMEOUT_SECONDS = 10
PSPACE_HISTORY_AGGREGATES = {
    "PS_HIS_AVERAGE",
    "PS_HIS_MINIMUM",
    "PS_HIS_MAXIMUM",
    "PS_HIS_TOTAL",
    "PS_HIS_COUNT",
    "PS_HIS_STDDEV",
}


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def settings() -> dict[str, str]:
    values = _load_env_file(LEGACY_IMES_ENV)
    values.update(_load_env_file(EXTERNAL_ENV))
    for name in (
        "IMES_WEB_URL",
        "IMES_WEB_USER",
        "IMES_WEB_PASSWORD",
        "IMES_WEB_CAPTCHA",
        "IMES_WEB_JSESSIONID",
        "PSPACE_SERVER",
        "PSPACE_PORT",
        "PSPACE_USER",
        "PSPACE_PASSWORD",
        "PSPACE_SDK_ROOT",
        "PSPACE_WS_URL",
    ):
        if os.getenv(name):
            values[name] = str(os.environ[name])
    return values


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    source: str
    relation: str
    description: str
    time_field: str | None = None
    order_field: str | None = None
    meltno_field: str | None = None
    search_fields: tuple[str, ...] = ()
    supports_exact_time: bool = True
    lineage: str = "source_record"


DATASETS: dict[str, DatasetSpec] = {
    "vastbase.batch_input": DatasetSpec(
        "vastbase.batch_input",
        "矿焦批次投料",
        "vastbase_operations",
        "public.batch_input",
        "24路通道、矿批/焦批汇总和批次时间。",
        "workdate2",
        "workdate2",
        search_fields=("prodcentercode", "charge", "remark3", "lot"),
        lineage="upstream_burden_batch",
    ),
    "vastbase.formal_hot_metal": DatasetSpec(
        "vastbase.formal_hot_metal",
        "正式铁水化验",
        "vastbase_operations",
        "public.t_qpes_inner_batch + public.inner_batch_insp_bb",
        "以正式 heatno 精确关联炉次的铁水 C/Si/Mn/P/S/Ti/V/Cr/Cu/Ni/As。",
        "result_ts",
        "result_ts",
        "official_meltno",
        ("official_meltno", "batchno"),
        lineage="exact_heatno_batchno",
    ),
    "vastbase.inner_batch_insp_bb": DatasetSpec(
        "vastbase.inner_batch_insp_bb",
        "铁水元素原始视图",
        "vastbase_operations",
        "public.inner_batch_insp_bb",
        "按化验批号保存的元素原始结果；需与化验索引联用。",
        "judgetime",
        "judgetime",
        search_fields=("batchno", "prodcentercode"),
    ),
    "vastbase.slag_inspection": DatasetSpec(
        "vastbase.slag_inspection",
        "旧炉渣检验视图",
        "vastbase_operations",
        "public.slag_inspection",
        "旧炉渣检验原始字段，保留用于历史审计。",
        "publishtime",
        "publishtime",
        "meltno",
        ("meltno", "sampleno", "prodcentercode"),
    ),
    "vastbase.heat_master": DatasetSpec(
        "vastbase.heat_master",
        "炉次作业主表",
        "vastbase_operations",
        "public.t_ipes_cond",
        "正式炉次、开口、堵口、出铁时长和作业字段。",
        "opentime",
        "opentime",
        "meltno",
        ("meltno", "prodcentercode", "workclass", "workshift"),
        lineage="formal_meltno",
    ),
    "vastbase.output": DatasetSpec(
        "vastbase.output",
        "铁水生产实绩",
        "vastbase_operations",
        "public.t_ipes_out_put",
        "铁量、毛重、皮重、计量和班次信息。",
        "weighttime",
        "weighttime",
        "meltno",
        ("meltno", "prodcentercode", "materialname"),
        lineage="formal_meltno",
    ),
    "vastbase.lab_hot_metal_view": DatasetSpec(
        "vastbase.lab_hot_metal_view",
        "铁水化验发布视图",
        "vastbase_laboratory",
        "public.v_qpes_inner_batch_insp_final_sample",
        "按试样号发布的铁水化验视图；用于来源核验，不替代正式 heatno 连接。",
        "发布时间",
        "发布时间",
        search_fields=("试样号", "高炉", "罐号"),
        lineage="sample_number_audit_only",
    ),
    "vastbase.lab_material_view": DatasetSpec(
        "vastbase.lab_material_view",
        "铁水化验批号视图",
        "vastbase_laboratory",
        "public.v_qpes_mat_final",
        "与铁水发布视图同源的批号/罐号视图，禁止与前者相加统计。",
        "publishtime",
        "publishtime",
        search_fields=("batchno", "prodcentercode", "thankno"),
        lineage="duplicate_projection",
    ),
    "vastbase.sinter_chemistry": DatasetSpec(
        "vastbase.sinter_chemistry",
        "烧结矿化验",
        "vastbase_laboratory",
        "public.v_qpes_sinter_machine_sample_insp_final",
        "烧结矿 TFe、FeO、CaO、MgO、SiO2、Al2O3、R2 等上游化验。",
        "制样时间",
        "制样时间",
        search_fields=("试样单号", "加工中心编码", "加工中心名称"),
        lineage="upstream_time_context",
    ),
    "vastbase.slag_chemistry": DatasetSpec(
        "vastbase.slag_chemistry",
        "炉渣化验",
        "vastbase_laboratory",
        "public.v_qpes_slag_insoection_final",
        "按 meltno 可精确关联的炉渣成分和碱度。",
        "publishtime",
        "publishtime",
        "meltno",
        ("meltno", "sampleno", "prodcentercode"),
        lineage="exact_meltno",
    ),
    "vastbase.steel_chemistry": DatasetSpec(
        "vastbase.steel_chemistry",
        "炼钢化验（边界数据）",
        "vastbase_laboratory",
        "public.v_qpes_steel_final",
        "可读但不属于高炉铁水；仅在通用数据查询中提供并明确边界。",
        "publishtime",
        "publishtime",
        "heatno",
        ("heatno", "sampleno", "steelgrade", "prodcentercode"),
        lineage="downstream_steel_not_hot_metal",
    ),
    "postgres.sensor_registry": DatasetSpec(
        "postgres.sensor_registry",
        "传感器语义清单",
        "postgres_gl02",
        "bf_sensor.sensor_registry",
        "133点及派生变量的中文语义、分组、单位和启用状态。",
        None,
        "variable_name",
        search_fields=("variable_name", "chinese_name", "branch", "short_name"),
        supports_exact_time=False,
    ),
    "postgres.sensor_values": DatasetSpec(
        "postgres.sensor_values",
        "分钟传感器历史",
        "postgres_gl02",
        "bf_sensor.one_minute_values",
        "GL02 物理点分钟值、质量标记和值类型。",
        "ts",
        "ts",
        search_fields=("tag_long_name",),
    ),
    "postgres.diagnosis": DatasetSpec(
        "postgres.diagnosis",
        "炉况诊断快照",
        "postgres_gl02",
        "bf_sensor.diagnosis_snapshots",
        "8种炉况分数、主次诊断、置信度和证据。",
        "diagnosis_ts",
        "diagnosis_ts",
        search_fields=("main_label", "secondary_label"),
    ),
    "postgres.baselines": DatasetSpec(
        "postgres.baselines",
        "每日滚动基线",
        "postgres_gl02",
        "bf_sensor.daily_baselines",
        "变量30天滚动中位数、分位数和样本覆盖。",
        "baseline_day",
        "baseline_day",
        search_fields=("variable_name",),
    ),
    "postgres.data_quality": DatasetSpec(
        "postgres.data_quality",
        "数据质量审计",
        "postgres_gl02",
        "bf_sensor.data_quality_status",
        "缺失、延迟、覆盖率和同步质量。",
        "checked_at",
        "checked_at",
        search_fields=("window_kind",),
    ),
    "postgres.short_summaries": DatasetSpec(
        "postgres.short_summaries",
        "短时大模型总结",
        "postgres_gl02",
        "bf_sensor.short_window_summaries",
        "短时队列的大模型状态、总结和报告路径。",
        "created_at",
        "created_at",
        search_fields=("queue_id", "model_name", "status"),
    ),
    "pspace.realtime": DatasetSpec(
        "pspace.realtime",
        "pSpace 实时133点",
        "pspace",
        "ws://127.0.0.1:8770",
        "8770 只读桥发布的133个 Billboard 当前值、质量和时间。",
        "timestamp",
        "timestamp",
        search_fields=("variable_name",),
    ),
    "pspace.history": DatasetSpec(
        "pspace.history",
        "pSpace 历史133点",
        "pspace",
        r"\冀南钢铁\SIO\GL02",
        "按任意时间范围读取 pSpace 历史；跨度过大时自动增加聚合间隔。",
        "timestamp",
        "timestamp",
        search_fields=("variable_name",),
    ),
}


def catalog() -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for spec in DATASETS.values():
        grouped.setdefault(spec.source, []).append(asdict(spec))
    return {
        "ok": True,
        "schema_version": "heat_multisource_catalog_v1",
        "policy": "read_only_allowlist",
        "dataset_count": len(DATASETS),
        "sources": grouped,
        "credential_fields_present": {
            "vastbase_operations": bool(
                os.getenv("IMES_OPS_DB_PASSWORD")
                or _load_env_file(EXTERNAL_ENV).get("IMES_OPS_DB_PASSWORD")
            ),
            "vastbase_laboratory": bool(
                os.getenv("IMES_LAB_DB_PASSWORD")
                or _load_env_file(EXTERNAL_ENV).get("IMES_LAB_DB_PASSWORD")
                or _load_env_file(LEGACY_IMES_ENV).get("IMES_DB_PASSWORD")
            ),
            "imes_web": bool(settings().get("IMES_WEB_USER"))
            and bool(settings().get("IMES_WEB_PASSWORD")),
            "pspace": bool(settings().get("PSPACE_USER"))
            and bool(settings().get("PSPACE_PASSWORD")),
        },
    }


def _normalize_time(value: str | None) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _relation_parts(relation: str) -> tuple[str, str]:
    schema_name, table_name = relation.split(".", 1)
    return schema_name, table_name


def _source_connection(spec: DatasetSpec, pg_connect: Callable[[], Any]):
    if spec.source == "vastbase_operations":
        return heat_service._vastbase_connect(heat_service.imes_ops_params())
    if spec.source == "vastbase_laboratory":
        return heat_service._vastbase_connect(heat_service.imes_lab_params())
    if spec.source == "postgres_gl02":
        return pg_connect()
    raise ValueError(f"dataset {spec.key} is not SQL-backed")


def _formal_hot_metal_query(
    *,
    start: str | None,
    end: str | None,
    meltno: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    where: list[str] = []
    values: list[Any] = []
    result_expr = "COALESCE(b.judgetime, s.judgetime)"
    if start:
        where.append(f"{result_expr} >= %s")
        values.append(start)
    if end:
        where.append(f"{result_expr} < %s")
        values.append(end)
    if meltno:
        where.append("s.heatno = %s")
        values.append(meltno)
    if search:
        where.append("(CAST(s.heatno AS text) LIKE %s OR CAST(s.batchno AS text) LIKE %s)")
        token = f"%{search}%"
        values.extend((token, token))
    values.extend((limit + 1, offset))
    query = f"""
        SELECT CAST(s.id AS text) AS sample_record_id,
               CAST(s.batchno AS text) AS batchno,
               CAST(s.heatno AS text) AS official_meltno,
               {result_expr} AS result_ts,
               COALESCE(s.takesampletime, b.takesampletime) AS sample_ts,
               b.value_01 AS C, b.value_02 AS Si, b.value_03 AS Mn,
               b.value_04 AS P, b.value_05 AS S, b.value_06 AS Ti,
                b.value_07 AS V, b.value_08 AS Cr, b.value_09 AS Ni,
                b.value_10 AS Cu, b.value_11 AS As,
               s.takesampleclass AS sample_class,
               s.inspphyclass AS physical_class
        FROM public.t_qpes_inner_batch AS s
        JOIN public.inner_batch_insp_bb AS b ON b.batchno = s.batchno
        WHERE {' AND '.join(where) if where else 'TRUE'}
        ORDER BY result_ts DESC, s.heatno DESC, s.batchno
        LIMIT %s OFFSET %s
    """
    with heat_service._vastbase_connect(heat_service.imes_ops_params()) as conn:
        rows = [dict(row) for row in conn.execute(query, values).fetchall()]
    has_more = len(rows) > limit
    return {
        "rows": rows[:limit],
        "columns": list(rows[0]) if rows else [],
        "has_more": has_more,
    }


def _sql_query(
    spec: DatasetSpec,
    *,
    pg_connect: Callable[[], Any],
    start: str | None,
    end: str | None,
    meltno: str | None,
    search: str | None,
    variables: list[str],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    if spec.key == "vastbase.formal_hot_metal":
        return _formal_hot_metal_query(
            start=start,
            end=end,
            meltno=meltno,
            search=search,
            limit=limit,
            offset=offset,
        )
    schema_name, table_name = _relation_parts(spec.relation)
    where: list[sql.Composed] = []
    values: list[Any] = []
    if start and spec.time_field:
        where.append(sql.SQL("{} >= %s").format(sql.Identifier(spec.time_field)))
        values.append(start)
    if end and spec.time_field:
        where.append(sql.SQL("{} < %s").format(sql.Identifier(spec.time_field)))
        values.append(end)
    if meltno and spec.meltno_field:
        where.append(sql.SQL("{} = %s").format(sql.Identifier(spec.meltno_field)))
        values.append(meltno)
    if search and spec.search_fields:
        token = f"%{search}%"
        clauses = [
            sql.SQL("CAST({} AS text) LIKE %s").format(sql.Identifier(field))
            for field in spec.search_fields
        ]
        where.append(sql.SQL("(") + sql.SQL(" OR ").join(clauses) + sql.SQL(")"))
        values.extend([token] * len(clauses))
    if spec.key == "postgres.sensor_values" and variables:
        with pg_connect() as conn:
            registry = conn.execute(
                """
                SELECT tag_long_name
                FROM bf_sensor.sensor_registry
                WHERE variable_name = ANY(%s) AND is_enabled IS TRUE
                """,
                (variables,),
            ).fetchall()
        tags = [row["tag_long_name"] for row in registry]
        if not tags:
            return {"rows": [], "columns": [], "has_more": False}
        where.append(sql.SQL("{} = ANY(%s)").format(sql.Identifier("tag_long_name")))
        values.append(tags)
    query = sql.SQL("SELECT * FROM {}.{}").format(
        sql.Identifier(schema_name), sql.Identifier(table_name)
    )
    if where:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where)
    if spec.order_field:
        query += sql.SQL(" ORDER BY {} DESC").format(sql.Identifier(spec.order_field))
    query += sql.SQL(" LIMIT %s OFFSET %s")
    values.extend((limit + 1, offset))
    with _source_connection(spec, pg_connect) as conn:
        conn.execute("SET statement_timeout = 10000")
        rows = [dict(row) for row in conn.execute(query, values).fetchall()]
    has_more = len(rows) > limit
    return {
        "rows": rows[:limit],
        "columns": list(rows[0]) if rows else [],
        "has_more": has_more,
    }


_module_lock = threading.Lock()
_module_cache: dict[str, Any] = {}


def _load_local_module(cache_key: str, path: Path):
    with _module_lock:
        if cache_key in _module_cache:
            return _module_cache[cache_key]
        spec = importlib.util.spec_from_file_location(cache_key, path)
        if not spec or not spec.loader:
            raise RuntimeError(f"cannot load module: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[cache_key] = module
        spec.loader.exec_module(module)
        _module_cache[cache_key] = module
        return module


def _project_tool(name: str) -> Path:
    candidates = (
        PROJECT_ROOT / "tools" / name,
        APP_ROOT / "tools" / name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(name)


_imes_web_lock = threading.Lock()
_imes_web_session: requests.Session | None = None
_imes_web_authenticated_at: float | None = None


def _imes_web_module():
    return _load_local_module(
        "_heat_dashboard_imes_web_readonly",
        _project_tool("export_imes_web_readonly.py"),
    )


def _imes_web_session_for_query(captcha: str | None = None) -> requests.Session:
    global _imes_web_session, _imes_web_authenticated_at
    cfg = settings()
    user = cfg.get("IMES_WEB_USER")
    password = cfg.get("IMES_WEB_PASSWORD")
    if not user or not password:
        raise RuntimeError("IMES Web 账号尚未配置")
    with _imes_web_lock:
        if _imes_web_session is not None:
            return _imes_web_session
        session = requests.Session()
        jsessionid = cfg.get("IMES_WEB_JSESSIONID")
        if jsessionid:
            session.cookies.set("JSESSIONID", jsessionid)
            _imes_web_session = session
            _imes_web_authenticated_at = time.time()
            return session
        captcha_value = captcha or cfg.get("IMES_WEB_CAPTCHA")
        if not captcha_value:
            raise RuntimeError("IMES Web 需要当前验证码或有效 JSESSIONID")
        module = _imes_web_module()
        module.login(
            session,
            cfg.get("IMES_WEB_URL", DEFAULT_IMES_WEB_URL).rstrip("/") + "/",
            user,
            password,
            captcha_value,
            SOURCE_TIMEOUT_SECONDS,
        )
        _imes_web_session = session
        _imes_web_authenticated_at = time.time()
        return session


def imes_web_login(captcha: str) -> dict[str, Any]:
    global _imes_web_session, _imes_web_authenticated_at
    with _imes_web_lock:
        _imes_web_session = None
        _imes_web_authenticated_at = None
    _imes_web_session_for_query(captcha.strip())
    return {
        "ok": True,
        "source": "imes_web",
        "authenticated": True,
        "authenticated_at": datetime.now().isoformat(timespec="seconds"),
    }


def imes_web_catalog() -> list[dict[str, Any]]:
    module = _imes_web_module()
    return [
        {
            "key": f"imes_web.{key}",
            "label": spec.label,
            "source": "imes_web",
            "relation": spec.path,
            "description": "IMES Web 已核实只读查询端点。",
            "time_field": spec.time_field,
            "date_mode": spec.date_mode,
            "supports_exact_time": False,
            "lineage": "authorized_web_query",
        }
        for key, spec in module.DATASETS.items()
    ]


def _imes_web_query(
    key: str,
    *,
    start: str | None,
    end: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    module = _imes_web_module()
    dataset_key = key.split(".", 1)[1]
    if dataset_key not in module.DATASETS:
        raise KeyError(key)
    today = date.today()
    start_date = datetime.fromisoformat(start).date() if start else today - timedelta(days=1)
    end_date = datetime.fromisoformat(end).date() if end else today
    if end_date < start_date:
        raise ValueError("end must be on or after start")
    session = _imes_web_session_for_query()
    base_url = settings().get("IMES_WEB_URL", DEFAULT_IMES_WEB_URL).rstrip("/") + "/"
    spec = module.DATASETS[dataset_key]
    rows: list[dict[str, Any]] = []
    consumed = 0
    page_size = min(200, max(20, limit))
    for params in module.build_query_windows(
        spec, start_date.isoformat(), end_date.isoformat(), None
    ):
        for row in module.fetch_dataset(
            session,
            base_url,
            spec,
            params,
            page_size=page_size,
            max_pages=max(1, math.ceil((offset + limit + 1) / page_size)),
            timeout=SOURCE_TIMEOUT_SECONDS,
        ):
            if consumed >= offset and len(rows) <= limit:
                rows.append(row)
            consumed += 1
            if len(rows) > limit:
                break
        if len(rows) > limit:
            break
    return {
        "rows": rows[:limit],
        "columns": list(rows[0]) if rows else [],
        "has_more": len(rows) > limit,
    }


def _pspace_bridge_module():
    return _load_local_module(
        "_heat_dashboard_pspace_bridge",
        _project_tool("pspace_8092_realtime_bridge.py"),
    )


def _pspace_connect():
    cfg = settings()
    user = cfg.get("PSPACE_USER")
    password = cfg.get("PSPACE_PASSWORD")
    if not user or not password:
        raise RuntimeError("pSpace 只读账号尚未配置")
    bridge = _pspace_bridge_module()
    sdk_root = bridge.find_sdk_root(
        cfg.get("PSPACE_SDK_ROOT") or str(PROJECT_ROOT / "pythonSDK(1)")
    )
    PsObject, T = bridge.load_sdk(sdk_root)
    args = type(
        "PspaceArgs",
        (),
        {
            "pspace_server": cfg.get("PSPACE_SERVER", DEFAULT_PSPACE_HOST),
            "pspace_port": cfg.get("PSPACE_PORT", DEFAULT_PSPACE_PORT),
            "pspace_user": user,
            "pspace_password": password,
        },
    )()
    return bridge, T, bridge.connect_pspace(PsObject, T, args)


def _pspace_tag_map(bridge) -> dict[str, str]:
    mapping = bridge.normalize_confirmed_sio_gl02_mapping(
        {}, bridge.DEFAULT_SIO_GL02_ROOT
    )
    return bridge.mapped_tags(mapping)


def _pspace_live_query(
    *, variables: list[str], search: str | None, limit: int, offset: int
) -> dict[str, Any]:
    import websocket

    ws_url = settings().get("PSPACE_WS_URL", DEFAULT_PSPACE_WS)
    ws = websocket.create_connection(ws_url, timeout=3)
    try:
        payload = json.loads(ws.recv())
    finally:
        ws.close()
    current = payload.get("values") or payload.get("current") or {}
    timestamp = payload.get("timestamp")
    if not current and isinstance(payload.get("history"), dict):
        history = payload["history"]
        timestamps = history.get("timestamps") or []
        timestamp = timestamps[-1] if timestamps else timestamp
        current = {
            key: values[-1]
            for key, values in history.items()
            if key != "timestamps" and isinstance(values, list) and values
        }
    point_meta = payload.get("point_meta") or {}
    ids = variables or sorted(
        key
        for key in current
        if key not in {"timestamp"} and isinstance(current.get(key), (int, float))
    )
    if search:
        token = search.lower()
        ids = [
            item
            for item in ids
            if token in item.lower()
            or token in str(point_meta.get(item, {})).lower()
        ]
    rows = [
        {
            "timestamp": timestamp,
            "variable_name": sensor_id,
            "value": current.get(sensor_id),
            "quality": (point_meta.get(sensor_id) or {}).get("quality"),
            "source_timestamp": (point_meta.get(sensor_id) or {}).get("timestamp"),
        }
        for sensor_id in ids
    ]
    sliced = rows[offset : offset + limit]
    return {
        "rows": sliced,
        "columns": list(sliced[0]) if sliced else [],
        "has_more": offset + limit < len(rows),
        "source_meta": {
            "frame_type": payload.get("type"),
            "mapped": (payload.get("mapping") or {}).get("mapped"),
        },
    }


def _pspace_history_query(
    *,
    start: str | None,
    end: str | None,
    variables: list[str],
    limit: int,
    offset: int,
    interval_seconds: int,
    aggregate: str,
) -> dict[str, Any]:
    if not start or not end:
        raise ValueError("pSpace 历史查询必须提供 start 和 end")
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if end_dt <= start_dt:
        raise ValueError("end must be later than start")
    bridge, T, pspace = _pspace_connect()
    tag_map = _pspace_tag_map(bridge)
    selected = variables or list(tag_map)
    selected = [item for item in selected if item in tag_map][:PSPACE_MAX_TAGS]
    if not selected:
        return {"rows": [], "columns": [], "has_more": False}
    duration_seconds = max(1, int((end_dt - start_dt).total_seconds()))
    effective_interval = max(
        1,
        int(interval_seconds or 60),
        math.ceil(duration_seconds / PSPACE_MAX_POINTS_PER_TAG),
    )
    stats = (
        aggregate
        if aggregate in PSPACE_HISTORY_AGGREGATES
        else "PS_HIS_AVERAGE"
    )
    tags = [tag_map[item] for item in selected]
    result = pspace.HisReadProcessed(
        {
            T.HisReadProcessedTagNameBuffer: tags,
            T.HisReadProcessedstartTime: bridge.format_ps_history_time(start_dt),
            T.HisReadProcessedendTime: bridge.format_ps_history_time(end_dt),
            T.HisReadProcessedInterval: effective_interval,
            T.HisReadProcessedStatistics: [stats] * len(tags),
        }
    )
    if isinstance(result, dict) and result.get(T.Return, 0) not in (0, None):
        raise RuntimeError(
            f"pSpace history failed: {result.get(T.Error) or result.get(T.Return)}"
        )
    sensor_by_tag = {tag_map[sensor_id]: sensor_id for sensor_id in selected}
    rows: list[dict[str, Any]] = []
    for tag, sensor_id in sensor_by_tag.items():
        records = result.get(tag, {}) if isinstance(result, dict) else {}
        if not isinstance(records, dict):
            continue
        for _, record in bridge.numeric_items(records):
            if not isinstance(record, dict):
                continue
            ts = bridge.history_record_timestamp(T, record, True)
            rows.append(
                {
                    "timestamp": ts,
                    "variable_name": sensor_id,
                    "value": bridge.history_record_value(T, record, True),
                    "aggregate": stats,
                    "interval_seconds": effective_interval,
                }
            )
    rows.sort(key=lambda row: (row["timestamp"] or datetime.min, row["variable_name"]))
    sliced = rows[offset : offset + limit]
    return {
        "rows": sliced,
        "columns": list(sliced[0]) if sliced else [],
        "has_more": offset + limit < len(rows),
        "source_meta": {
            "requested_interval_seconds": interval_seconds,
            "effective_interval_seconds": effective_interval,
            "aggregate": stats,
            "selected_variables": selected,
            "total_rows_before_page": len(rows),
        },
    }


def query_dataset(
    key: str,
    *,
    pg_connect: Callable[[], Any],
    start: str | None = None,
    end: str | None = None,
    meltno: str | None = None,
    search: str | None = None,
    variables: Iterable[str] = (),
    limit: int = 200,
    offset: int = 0,
    interval_seconds: int = 60,
    aggregate: str = "PS_HIS_AVERAGE",
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 5000))
    offset = max(0, min(int(offset), 1_000_000))
    start_normalized = _normalize_time(start)
    end_normalized = _normalize_time(end)
    if start_normalized and end_normalized and start_normalized >= end_normalized:
        raise ValueError("start must be earlier than end")
    variable_list = [item.strip() for item in variables if item.strip()]
    started = time.monotonic()
    if key.startswith("imes_web."):
        result = _imes_web_query(
            key,
            start=start_normalized,
            end=end_normalized,
            limit=limit,
            offset=offset,
        )
        spec_payload = next(
            item for item in imes_web_catalog() if item["key"] == key
        )
    else:
        if key not in DATASETS:
            raise KeyError(f"unknown dataset: {key}")
        spec = DATASETS[key]
        spec_payload = asdict(spec)
        if key == "pspace.realtime":
            result = _pspace_live_query(
                variables=variable_list,
                search=search,
                limit=limit,
                offset=offset,
            )
        elif key == "pspace.history":
            result = _pspace_history_query(
                start=start_normalized,
                end=end_normalized,
                variables=variable_list,
                limit=limit,
                offset=offset,
                interval_seconds=interval_seconds,
                aggregate=aggregate,
            )
        else:
            result = _sql_query(
                spec,
                pg_connect=pg_connect,
                start=start_normalized,
                end=end_normalized,
                meltno=meltno,
                search=search,
                variables=variable_list,
                limit=limit,
                offset=offset,
            )
    return {
        "ok": True,
        "schema_version": "heat_multisource_query_v1",
        "dataset": spec_payload,
        "query": {
            "start": start_normalized,
            "end": end_normalized,
            "meltno": meltno,
            "search": search,
            "variables": variable_list,
            "limit": limit,
            "offset": offset,
            "window_semantics": "[start,end)",
        },
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        **result,
    }


def full_catalog() -> dict[str, Any]:
    payload = catalog()
    web = imes_web_catalog()
    payload["sources"]["imes_web"] = web
    payload["dataset_count"] += len(web)
    payload["service_boundaries"] = {
        "imes_web": "requires a valid JSESSIONID or current captcha login",
        "pspace": "realtime via 8770; historical queries use the read-only SDK",
        "vastbase": "two independent read-only permission surfaces",
        "postgres_gl02": "local PostgreSQL read account; failures do not block other sources",
    }
    return payload


def probe_source(source: str, pg_connect: Callable[[], Any]) -> dict[str, Any]:
    """Run one bounded, read-only source probe without returning connection secrets."""

    started = time.monotonic()
    checked_at = datetime.now().isoformat(timespec="seconds")
    try:
        if source == "postgres_gl02":
            with pg_connect() as conn:
                row = conn.execute(
                    "SELECT current_timestamp AS server_time"
                ).fetchone()
            detail = dict(row or {})
            state = "ready"
        elif source == "vastbase":
            detail = {"permission_surfaces": {}}
            for key, params in (
                ("operations", heat_service.imes_ops_params()),
                ("laboratory", heat_service.imes_lab_params()),
            ):
                with heat_service._vastbase_connect(params) as conn:
                    row = conn.execute(
                        "SELECT current_timestamp AS server_time"
                    ).fetchone()
                detail["permission_surfaces"][key] = dict(row or {})
            state = "ready"
        elif source == "pspace":
            result = _pspace_live_query(
                variables=[],
                search=None,
                limit=1,
                offset=0,
            )
            detail = {
                "frame": result.get("source_meta"),
                "sample_row_count": len(result.get("rows") or []),
            }
            state = "ready"
        elif source == "imes_web":
            configured = bool(settings().get("IMES_WEB_USER")) and bool(
                settings().get("IMES_WEB_PASSWORD")
            )
            authenticated = _imes_web_session is not None
            detail = {
                "configured": configured,
                "authenticated": authenticated,
                "requires_current_captcha": configured and not authenticated,
            }
            state = "ready" if authenticated else "authorization_required"
        else:
            raise KeyError(f"unknown source: {source}")
        return {
            "ok": True,
            "source": source,
            "state": state,
            "checked_at": checked_at,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "detail": detail,
            "policy": "read_only_probe",
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": source,
            "state": "unavailable",
            "checked_at": checked_at,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error_type": type(exc).__name__,
            "error": "数据源连接或只读探测失败",
            "policy": "read_only_probe",
        }
