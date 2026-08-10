"""Read-only heat-centric aggregation for the local GL02 database dashboard.

Requirements:
* REQ-HEAT-CENTRIC-DASHBOARD-20260725
* REQ-HEAT-SI-DISTRIBUTION-20260726

The service joins two permission surfaces in IMES Vastbase with the GL02
PostgreSQL sensor mirror:

* the historical operations account can read heat/output tables;
* the dedicated lab account can read named hot-metal, slag and sinter views;
* the GL02 read-only account can read the 133 physical sensor points.

No database object is created or modified.  Passwords never appear in API
responses.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import re
from statistics import median
import sys
import time
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMES_ENV = ROOT / "PT" / "imes_vastbase.local.env"
LOCAL_EXTERNAL_ENV = ROOT / "PT" / "external_sources.local.env"
DIAGNOSIS_SERVICE_DIR = ROOT / "自动诊断服务"
if DIAGNOSIS_SERVICE_DIR.exists() and str(DIAGNOSIS_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSIS_SERVICE_DIR))
try:
    from recommendation_adapter import generate_recommendation
except Exception:  # pragma: no cover - deployment can run diagnosis-only without the engine
    generate_recommendation = None

HOT_METAL_VIEW = "public.v_qpes_inner_batch_insp_final_sample"
SLAG_VIEW = "public.v_qpes_slag_insoection_final"
SINTER_VIEW = "public.v_qpes_sinter_machine_sample_insp_final"
HOT_SAMPLE_RE = re.compile(
    r"^(?P<furnace>\d)(?P<year>\d{2})(?P<month>\d{2})-"
    r"(?P<heat_tail>\d{3})-(?P<sample_seq>\d{3})$"
)
HEAT_RE = re.compile(
    r"^(?P<furnace>\d+)#(?P<date>\d{8})-(?P<heat_tail>\d{3})$"
)

CORE_SENSOR_VARIABLES = (
    "P_top",
    "DP_total",
    "DP_upper",
    "DP_lower",
    "PI",
    "Q_blast",
    "P_blast",
    "T_blast",
    "O2_rate",
    "Q_O2",
    "PCI_rate",
    "GasUtil",
    "L",
    "L_south",
    "L_north",
    "T_taphole_1",
    "T_taphole_2",
)
VALID_WINDOWS = {"pre_tap", "tapping", "inter_heat"}
VALID_GROUPS = {"core", "static", "body", "all", "custom"}
DIAGNOSIS_DISPLAY_LABELS = {
    "normal": "正常顺行",
    "cold": "热制度下行",
    "hot": "热制度上行",
    "edge": "边缘气流发展",
    "center": "中心气流发展",
    "channel": "管道行程",
    "column": "悬料",
    "lowline": "低料线",
    "data_quality_low": "数据质量不足",
    "sync_pending": "数据同步中",
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


def _setting(name: str, file_values: dict[str, str], default: str = "") -> str:
    return str(os.getenv(name) or file_values.get(name) or default)


def _credential_values() -> dict[str, str]:
    """Load protected site-local credentials without exposing them through APIs."""

    values = _load_env_file(LOCAL_IMES_ENV)
    values.update(_load_env_file(LOCAL_EXTERNAL_ENV))
    return values


def imes_lab_params() -> dict[str, Any]:
    """Resolve the dedicated lab-view login, preferring process overrides."""

    file_values = _credential_values()
    user = (
        os.getenv("IMES_LAB_DB_USER")
        or file_values.get("IMES_LAB_DB_USER")
        or file_values.get("IMES_DB_USER")
    )
    password = (
        os.getenv("IMES_LAB_DB_PASSWORD")
        or file_values.get("IMES_LAB_DB_PASSWORD")
        or file_values.get("IMES_DB_PASSWORD")
    )
    if not user or not password:
        raise RuntimeError("缺少 IMES 化验视图只读账号配置")
    return {
        "host": _setting("IMES_LAB_DB_HOST", file_values, "127.0.0.1"),
        "port": int(_setting("IMES_LAB_DB_PORT", file_values, "15433")),
        "dbname": _setting(
            "IMES_LAB_DB_NAME",
            file_values,
            file_values.get("IMES_DB_NAME", "vastbase"),
        ),
        "user": user,
        "password": password,
        "connect_timeout": int(
            _setting("IMES_DB_CONNECT_TIMEOUT_SECONDS", file_values, "3")
        ),
        "options": "-c default_transaction_read_only=on -c statement_timeout=3500",
    }


def imes_ops_params() -> dict[str, Any]:
    """Resolve the project-approved operations-table read account."""

    file_values = _credential_values()
    user = (
        os.getenv("IMES_OPS_DB_USER")
        or file_values.get("IMES_OPS_DB_USER")
        or file_values.get("IMES_DB_USER")
    )
    password = (
        os.getenv("IMES_OPS_DB_PASSWORD")
        or file_values.get("IMES_OPS_DB_PASSWORD")
        or file_values.get("IMES_DB_PASSWORD")
    )
    if not user or not password:
        raise RuntimeError("缺少 IMES 生产作业表只读账号配置")
    return {
        "host": _setting(
            "IMES_OPS_DB_HOST",
            file_values,
            file_values.get("IMES_DB_HOST", "127.0.0.1"),
        ),
        "port": int(_setting(
            "IMES_OPS_DB_PORT",
            file_values,
            file_values.get("IMES_DB_PORT", "15433"),
        )),
        "dbname": _setting(
            "IMES_OPS_DB_NAME",
            file_values,
            file_values.get("IMES_DB_NAME", "vastbase"),
        ),
        "user": user,
        "password": password,
        "connect_timeout": 2,
        "options": "-c default_transaction_read_only=on -c statement_timeout=2000",
        "_max_attempts": 1,
    }


def _vastbase_connect(params: dict[str, Any]):
    last_error: Exception | None = None
    max_attempts = params.pop("_max_attempts", 3)
    for attempt in range(max_attempts):
        try:
            return psycopg.connect(**params, row_factory=dict_row)
        except psycopg.OperationalError as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _heat_identity(meltno: str, open_ts: datetime | None) -> tuple[str, str, str] | None:
    match = HEAT_RE.fullmatch(str(meltno or "").strip())
    if not match:
        return None
    date_text = match.group("date")
    yymm = date_text[2:6]
    if open_ts:
        yymm = open_ts.strftime("%y%m")
    return match.group("furnace"), yymm, match.group("heat_tail")


def _normalize_heat(row: dict[str, Any]) -> dict[str, Any]:
    open_ts = parse_datetime(row.get("opentime"))
    raw_close_ts = parse_datetime(row.get("closetime"))
    close_ts = (
        raw_close_ts
        if open_ts and raw_close_ts and raw_close_ts >= open_ts
        else None
    )
    fallback_duration = number(row.get("tappingtime"))
    if fallback_duration is not None and not 0 < fallback_duration <= 600:
        fallback_duration = None
    duration = (
        round((close_ts - open_ts).total_seconds() / 60, 1)
        if open_ts and close_ts
        else fallback_duration
    )
    return {
        "meltno": str(row.get("meltno") or ""),
        "workdate": str(row.get("workdate") or ""),
        "open_ts": open_ts,
        "close_ts": close_ts,
        "duration_minutes": duration,
        "batch_start": row.get("sumbatchstart"),
        "batch_end": row.get("sumbatchend"),
        "batch_count": number(row.get("sumbatch")),
        "theory_iron_qty": number(row.get("theoryquan")),
        "slag_rate": number(row.get("slagrate")),
        "shift": row.get("workshift"),
        "work_class": row.get("workclass"),
        "identity": _heat_identity(str(row.get("meltno") or ""), open_ts),
        "outputs": [],
        "hot_metal_samples": [],
        "slag_samples": [],
    }


def _fetch_heat_rows(
    limit: int,
    furnace_no: str = "2",
    meltno: str | None = None,
    date_from: datetime | None = None,
    date_to_exclusive: datetime | None = None,
    max_open_time: datetime | None = None,
) -> list[dict[str, Any]]:
    where = ["opentime IS NOT NULL"]
    values: list[Any] = []
    if meltno:
        where.append("meltno = %s")
        values.append(meltno)
    else:
        where.append("(prodcentercode = %s OR meltno LIKE %s)")
        values.extend((f"{furnace_no}D012", f"{furnace_no}#%"))
    if date_from:
        where.append("opentime >= %s")
        values.append(date_from.strftime("%Y-%m-%d %H:%M:%S"))
    if date_to_exclusive:
        where.append("opentime < %s")
        values.append(date_to_exclusive.strftime("%Y-%m-%d %H:%M:%S"))
    if max_open_time:
        where.append("opentime <= %s")
        values.append(max_open_time.strftime("%Y-%m-%d %H:%M:%S"))
    values.append(max(1, min(int(limit), 200)))
    with _vastbase_connect(imes_ops_params()) as conn:
        rows = conn.execute(
            f"""
            SELECT meltno, workdate, prodcentercode, sumbatchstart, sumbatchend,
                   sumbatch, opentime, closetime, tappingtime, theoryquan,
                   slagrate, workshift, workclass
            FROM public.t_ipes_cond
            WHERE {' AND '.join(where)}
            ORDER BY opentime DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    return [_normalize_heat(dict(row)) for row in rows]


def _count_future_heat_rows(
    furnace_no: str,
    date_from: datetime | None,
    date_to_exclusive: datetime | None,
    max_open_time: datetime,
) -> int:
    where = [
        "opentime IS NOT NULL",
        "(prodcentercode = %s OR meltno LIKE %s)",
        "opentime > %s",
    ]
    values: list[Any] = [
        f"{furnace_no}D012",
        f"{furnace_no}#%",
        max_open_time.strftime("%Y-%m-%d %H:%M:%S"),
    ]
    if date_from:
        where.append("opentime >= %s")
        values.append(date_from.strftime("%Y-%m-%d %H:%M:%S"))
    if date_to_exclusive:
        where.append("opentime < %s")
        values.append(date_to_exclusive.strftime("%Y-%m-%d %H:%M:%S"))
    with _vastbase_connect(imes_ops_params()) as conn:
        row = conn.execute(
            f"SELECT count(*) AS n FROM public.t_ipes_cond WHERE {' AND '.join(where)}",
            values,
        ).fetchone()
    return int(row["n"] or 0)


def _attach_outputs(heats: list[dict[str, Any]]) -> None:
    melt_numbers = [heat["meltno"] for heat in heats]
    if not melt_numbers:
        return
    with _vastbase_connect(imes_ops_params()) as conn:
        rows = conn.execute(
            """
            SELECT meltno, workdate, ironquan, workshift, workclass,
                   grossweigh, tareweigh, weighttime
            FROM public.t_ipes_out_put
            WHERE meltno = ANY(%s)
            ORDER BY workdate, id
            """,
            (melt_numbers,),
        ).fetchall()
    by_heat = {heat["meltno"]: heat for heat in heats}
    for raw in rows:
        row = dict(raw)
        item = {
            "workdate": parse_datetime(row.get("workdate")) or row.get("workdate"),
            "iron_qty": number(row.get("ironquan")),
            "shift": row.get("workshift"),
            "work_class": row.get("workclass"),
            "gross_weight": number(row.get("grossweigh")),
            "tare_weight": number(row.get("tareweigh")),
            "weight_time": parse_datetime(row.get("weighttime")) or row.get("weighttime"),
        }
        target = by_heat.get(str(row.get("meltno") or ""))
        if target is not None:
            target["outputs"].append(item)
    for heat in heats:
        quantities = [item["iron_qty"] for item in heat["outputs"] if item["iron_qty"] is not None]
        heat["actual_iron_qty"] = round(sum(quantities), 3) if quantities else None
        heat["output_count"] = len(heat["outputs"])


def _fetch_lab_rows_for_heats(heats: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    opens = [heat["open_ts"] for heat in heats if heat.get("open_ts")]
    closes = [heat["close_ts"] for heat in heats if heat.get("close_ts")]
    if not opens:
        return [], []
    melt_numbers = [heat["meltno"] for heat in heats]
    with _vastbase_connect(imes_ops_params()) as conn:
        hot_rows = conn.execute(
            """
            SELECT CAST(s.id AS text) AS id,
                   CAST(s.batchno AS text) AS batchno,
                   CAST(s.heatno AS text) AS official_meltno,
                   COALESCE(b.judgetime, s.judgetime) AS result_ts,
                   COALESCE(s.takesampletime, b.takesampletime) AS sample_ts,
                   s.takesampleclass AS sample_class,
                   s.inspphyclass AS physical_class,
                   b.inspshift AS shift_name,
                   b.value_01 AS cvalue,
                   b.value_02 AS sivalue,
                   b.value_03 AS mnvalue,
                   b.value_04 AS pvalue,
                   b.value_05 AS svalue,
                   b.value_06 AS tivalue,
                   b.value_07 AS vvalue,
                   b.value_08 AS crvalue,
                   b.value_09 AS nivalue,
                   b.value_10 AS cuvalue,
                   b.value_11 AS asvalue
            FROM public.t_qpes_inner_batch AS s
            JOIN public.inner_batch_insp_bb AS b
              ON b.batchno = s.batchno
            WHERE s.heatno = ANY(%s)
              AND s.batchno IS NOT NULL
            ORDER BY s.heatno, result_ts, s.batchno
            """,
            (melt_numbers,),
        ).fetchall()
        batchnos = [str(row.get("batchno") or "") for row in hot_rows if row.get("batchno")]
        tank_numbers = {}
        if batchnos:
            try:
                tank_rows = conn.execute(
                    """
                    SELECT DISTINCT ON (batchno)
                           CAST(batchno AS text) AS batchno,
                           CAST(thankno AS text) AS tank_no
                      FROM public.v_qpes_mat_final
                     WHERE batchno = ANY(%s)
                     ORDER BY batchno, publishtime DESC NULLS LAST
                    """,
                    (batchnos,),
                ).fetchall()
                tank_numbers = {
                    str(row.get("batchno") or ""): row.get("tank_no")
                    for row in tank_rows
                    if row.get("batchno") and row.get("tank_no") not in (None, "")
                }
            except Exception:
                tank_numbers = {}
        for row in hot_rows:
            row["tank_no"] = tank_numbers.get(str(row.get("batchno") or ""))
    with _vastbase_connect(imes_lab_params()) as conn:
        slag_rows = conn.execute(
            f"""
            SELECT sampleno, meltno, prodcentercode, publishtime,
                   tfe, feo, cao, mgo, sio2, al2o3, tio2,
                   r2, r3, r4, mgo_al2o3, sio2_al2o3
            FROM {SLAG_VIEW}
            WHERE meltno = ANY(%s)
            ORDER BY publishtime, sampleno
            """,
            (melt_numbers,),
        ).fetchall()
    return [dict(row) for row in hot_rows], [dict(row) for row in slag_rows]


def _normalize_hot_sample(row: dict[str, Any]) -> dict[str, Any]:
    match = HOT_SAMPLE_RE.fullmatch(str(row.get("sample_no") or "").strip())
    result_ts = parse_datetime(row.get("result_ts"))
    official_meltno = str(row.get("official_meltno") or "").strip() or None
    item = {
        "id": str(row.get("id") or ""),
        "sample_no": row.get("sample_no") or row.get("batchno"),
        "batchno": row.get("batchno"),
        "official_meltno": official_meltno,
        "result_ts": result_ts,
        "sample_ts": parse_datetime(row.get("sample_ts")) or row.get("sample_ts"),
        "publish_date": row.get("publish_date"),
        "furnace_no": row.get("furnace_no"),
        "tank_no": row.get("tank_no"),
        "shift": row.get("shift_name"),
        "sample_class": row.get("sample_class"),
        "physical_class": row.get("physical_class"),
        "C": number(row.get("cvalue")),
        "Si": number(row.get("sivalue")),
        "Mn": number(row.get("mnvalue")),
        "P": number(row.get("pvalue")),
        "S": number(row.get("svalue")),
        "Ti": number(row.get("tivalue")),
        "V": number(row.get("vvalue")),
        "Cr": number(row.get("crvalue")),
        "Ni": number(row.get("nivalue")),
        "Cu": number(row.get("cuvalue")),
        "As": number(row.get("asvalue")),
        "sample_seq": match.group("sample_seq") if match else None,
        "identity": (
            (
                match.group("furnace"),
                f"{match.group('year')}{match.group('month')}",
                match.group("heat_tail"),
            )
            if match
            else None
        ),
        "alignment_method": (
            "exact_heatno_batchno" if official_meltno else "legacy_sample_number_audit"
        ),
    }
    return item


def _normalize_slag_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_no": row.get("sampleno"),
        "meltno": row.get("meltno"),
        "publish_ts": parse_datetime(row.get("publishtime")) or row.get("publishtime"),
        "TFe": number(row.get("tfe")),
        "FeO": number(row.get("feo")),
        "CaO": number(row.get("cao")),
        "MgO": number(row.get("mgo")),
        "SiO2": number(row.get("sio2")),
        "Al2O3": number(row.get("al2o3")),
        "TiO2": number(row.get("tio2")),
        "R2": number(row.get("r2")),
        "R3": number(row.get("r3")),
        "R4": number(row.get("r4")),
        "MgO_Al2O3": number(row.get("mgo_al2o3")),
        "SiO2_Al2O3": number(row.get("sio2_al2o3")),
        "alignment_method": "exact_meltno",
    }


def summarize_hot_metal_si(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize every valid Si result without discarding sample detail."""

    values = [
        float(item["Si"])
        for item in samples
        if item.get("Si") is not None
    ]
    if not values:
        return {
            "sample_count": len(samples),
            "valid_count": 0,
            "min": None,
            "median": None,
            "max": None,
            "spread": None,
        }
    low = min(values)
    high = max(values)
    return {
        "sample_count": len(samples),
        "valid_count": len(values),
        "min": low,
        "median": float(median(values)),
        "max": high,
        "spread": high - low,
    }


def _attach_lab_samples(
    heats: list[dict[str, Any]],
    hot_rows: list[dict[str, Any]],
    slag_rows: list[dict[str, Any]],
) -> None:
    identities: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for heat in heats:
        if heat.get("identity"):
            identities.setdefault(heat["identity"], []).append(heat)
    for raw in hot_rows:
        sample = _normalize_hot_sample(raw)
        official_meltno = sample.get("official_meltno")
        if official_meltno:
            target = next(
                (heat for heat in heats if heat.get("meltno") == official_meltno),
                None,
            )
            sample.pop("identity", None)
            if target is not None:
                target["hot_metal_samples"].append(sample)
            continue
        candidates = identities.get(sample.get("identity"), [])
        if not candidates:
            continue
        result_ts = sample.get("result_ts")
        ranked = sorted(
            candidates,
            key=lambda heat: abs(
                (
                    result_ts
                    - (heat.get("close_ts") or heat.get("open_ts") or result_ts)
                ).total_seconds()
            )
            if result_ts
            else 0,
        )
        target = ranked[0]
        anchor = target.get("close_ts") or target.get("open_ts")
        if result_ts and anchor and abs((result_ts - anchor).total_seconds()) > 24 * 3600:
            continue
        sample["alignment_method"] = "legacy_sample_number_with_24h_guard"
        sample.pop("identity", None)
        target["hot_metal_samples"].append(sample)
    by_heat = {heat["meltno"]: heat for heat in heats}
    for raw in slag_rows:
        target = by_heat.get(str(raw.get("meltno") or ""))
        if target is not None:
            target["slag_samples"].append(_normalize_slag_sample(raw))
    for heat in heats:
        heat.pop("identity", None)
        heat["hot_metal_samples"].sort(
            key=lambda item: item.get("result_ts") or datetime.min
        )
        heat["slag_samples"].sort(
            key=lambda item: item.get("publish_ts")
            if isinstance(item.get("publish_ts"), datetime)
            else datetime.min
        )
        heat["hot_metal_sample_count"] = len(heat["hot_metal_samples"])
        heat["hot_metal_alignment_contract"] = "exact_heatno_batchno"
        heat["hot_metal_si_summary"] = summarize_hot_metal_si(
            heat["hot_metal_samples"]
        )
        heat["slag_sample_count"] = len(heat["slag_samples"])
        heat["latest_hot_metal"] = (
            heat["hot_metal_samples"][-1] if heat["hot_metal_samples"] else None
        )
        heat["latest_slag"] = heat["slag_samples"][-1] if heat["slag_samples"] else None
        heat["alignment_status"] = (
            "complete"
            if heat["hot_metal_samples"] and heat["slag_samples"]
            else "partial"
            if heat["hot_metal_samples"] or heat["slag_samples"]
            else "missing"
        )


def list_heats(
    limit: int = 16,
    furnace_no: str = "2",
    date_from: datetime | None = None,
    date_to_exclusive: datetime | None = None,
    include_future: bool = False,
) -> dict[str, Any]:
    """Return recent heat master rows with quality-result summaries."""

    checked_at = datetime.now()
    max_open_time = None if include_future else checked_at + timedelta(minutes=5)
    heats = _fetch_heat_rows(
        limit=limit,
        furnace_no=furnace_no,
        date_from=date_from,
        date_to_exclusive=date_to_exclusive,
        max_open_time=max_open_time,
    )
    _attach_outputs(heats)
    hot_rows, slag_rows = _fetch_lab_rows_for_heats(heats)
    _attach_lab_samples(heats, hot_rows, slag_rows)
    excluded_future_count = (
        0
        if include_future
        else _count_future_heat_rows(
            furnace_no,
            date_from,
            date_to_exclusive,
            max_open_time or checked_at,
        )
    )
    total_iron = sum(
        heat.get("actual_iron_qty") or 0
        for heat in heats
        if heat.get("actual_iron_qty") is not None
    )
    durations = [
        heat["duration_minutes"]
        for heat in heats
        if heat.get("duration_minutes") is not None
    ]
    return {
        "ok": True,
        "checked_at": checked_at,
        "summary": {
            "heat_count": len(heats),
            "actual_iron_qty_total": round(total_iron, 3),
            "hot_metal_heat_count": sum(
                1 for heat in heats if heat["hot_metal_sample_count"]
            ),
            "slag_heat_count": sum(1 for heat in heats if heat["slag_sample_count"]),
            "complete_heat_count": sum(
                1 for heat in heats if heat["alignment_status"] == "complete"
            ),
            "average_duration_minutes": (
                round(sum(durations) / len(durations), 1) if durations else None
            ),
            "latest_meltno": heats[0]["meltno"] if heats else None,
        },
        "heats": heats,
        "query": {
            "furnace_no": furnace_no,
            "date_from": date_from,
            "date_to_exclusive": date_to_exclusive,
            "include_future": include_future,
        },
        "data_quality": {
            "excluded_future_heat_count": excluded_future_count,
            "future_heat_policy": "exclude_open_time_after_server_now_plus_5min",
            "warnings": (
                [f"已排除 {excluded_future_count} 条开口时间晚于当前时间的异常炉次记录"]
                if excluded_future_count
                else []
            ),
        },
        "sources": {
            "heat_master": "IMES public.t_ipes_cond",
            "outputs": "IMES public.t_ipes_out_put",
            "hot_metal": "IMES public.t_qpes_inner_batch + public.inner_batch_insp_bb",
            "slag": SLAG_VIEW,
            "policy": "read_only",
        },
    }


def _fetch_sinter_context(open_ts: datetime, hours: int = 12) -> list[dict[str, Any]]:
    start = open_ts - timedelta(hours=max(1, min(hours, 72)))
    with _vastbase_connect(imes_lab_params()) as conn:
        rows = conn.execute(
            f"""
            SELECT "试样单号" AS sample_no, "业务日期" AS business_date,
                   "加工中心编码" AS center_code, "加工中心名称" AS center_name,
                   "制样时间" AS sample_ts, "发布时间" AS publish_ts,
                   tfevalue, caovalue, mgovalue, sio2value, al2o3value,
                   pvalue, tio2value, mnovalue, znvalue, crvalue,
                   r2value, feovalue, svalue, mgalvalue, alsivalue, qdvalue
            FROM {SINTER_VIEW}
            WHERE "制样时间" >= %s
              AND "制样时间" < %s
            ORDER BY "制样时间" DESC
            LIMIT 24
            """,
            (
                start.strftime("%Y-%m-%d %H:%M:%S"),
                open_ts.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        sample_ts = parse_datetime(row.get("sample_ts"))
        result.append(
            {
                "sample_no": row.get("sample_no"),
                "center_code": row.get("center_code"),
                "center_name": row.get("center_name"),
                "sample_ts": sample_ts or row.get("sample_ts"),
                "publish_ts": parse_datetime(row.get("publish_ts"))
                or row.get("publish_ts"),
                "lag_to_heat_hours": (
                    round((open_ts - sample_ts).total_seconds() / 3600, 2)
                    if sample_ts
                    else None
                ),
                "TFe": number(row.get("tfevalue")),
                "CaO": number(row.get("caovalue")),
                "MgO": number(row.get("mgovalue")),
                "SiO2": number(row.get("sio2value")),
                "Al2O3": number(row.get("al2o3value")),
                "P": number(row.get("pvalue")),
                "TiO2": number(row.get("tio2value")),
                "MnO": number(row.get("mnovalue")),
                "Zn": number(row.get("znvalue")),
                "Cr": number(row.get("crvalue")),
                "R2": number(row.get("r2value")),
                "FeO": number(row.get("feovalue")),
                "S": number(row.get("svalue")),
                "MgO_Al2O3": number(row.get("mgalvalue")),
                "Al2O3_SiO2": number(row.get("alsivalue")),
                "QD": number(row.get("qdvalue")),
                "alignment_method": "time_context_only_not_exact_heat_lineage",
                "confidence": "low",
            }
        )
    return result


def _previous_heat_close(current: dict[str, Any]) -> datetime | None:
    open_ts = current.get("open_ts")
    if not open_ts:
        return None
    with _vastbase_connect(imes_ops_params()) as conn:
        row = conn.execute(
            """
            SELECT closetime
            FROM public.t_ipes_cond
            WHERE opentime IS NOT NULL
              AND opentime < %s
              AND (prodcentercode = '2D012' OR meltno LIKE '2#%')
            ORDER BY opentime DESC
            LIMIT 1
            """,
            (open_ts.strftime("%Y-%m-%d %H:%M:%S"),),
        ).fetchone()
    return parse_datetime(row["closetime"]) if row else None


def resolve_sensor_window(
    heat: dict[str, Any],
    window_kind: str,
    pre_tap_minutes: int = 120,
) -> tuple[datetime, datetime, str]:
    if window_kind not in VALID_WINDOWS:
        raise ValueError(f"不支持的传感器窗口：{window_kind}")
    open_ts = heat.get("open_ts")
    close_ts = heat.get("close_ts")
    if not open_ts:
        raise RuntimeError("该炉次缺少开铁口时间，不能生成传感器窗口")
    if window_kind == "pre_tap":
        start = open_ts - timedelta(minutes=max(15, min(pre_tap_minutes, 720)))
        return start, open_ts, "left_closed_right_open"
    if window_kind == "tapping":
        end = close_ts or min(datetime.now(), open_ts + timedelta(hours=6))
        return open_ts, end + timedelta(minutes=1), "both_closed_source"
    previous_close = _previous_heat_close(heat)
    start = previous_close or open_ts - timedelta(minutes=pre_tap_minutes)
    return start, open_ts, "left_closed_right_open"


def infer_unit(variable_name: str) -> str:
    if variable_name.startswith(("T_", "TFT")):
        return "℃"
    if variable_name.startswith(("P_", "DP_")):
        return "kPa"
    if variable_name.startswith("Q_"):
        return "m³/min"
    if variable_name in {"GasUtil", "O2_rate"}:
        return "%"
    if variable_name.startswith("L"):
        return "m"
    if variable_name.startswith("PCI"):
        return "t/h"
    return ""


def _select_registry(
    conn: Any,
    group: str,
    requested: list[str] | None,
) -> list[dict[str, Any]]:
    if group not in VALID_GROUPS:
        raise ValueError(f"不支持的传感器组：{group}")
    rows = conn.execute(
        """
        SELECT variable_name, chinese_name, branch, short_name,
               tag_long_name, description
        FROM bf_sensor.sensor_registry
        WHERE is_enabled IS TRUE
          AND COALESCE(is_derived, FALSE) IS FALSE
        ORDER BY variable_name
        """
    ).fetchall()
    materialized = [dict(row) for row in rows]
    requested_set = set(requested or [])
    if group == "core":
        allowed = set(CORE_SENSOR_VARIABLES)
        materialized = [row for row in materialized if row["variable_name"] in allowed]
    elif group == "static":
        materialized = [
            row
            for row in materialized
            if re.fullmatch(
                r"P_static_(?:lower|middle|upper)_[A-F]",
                row["variable_name"],
            )
        ]
    elif group == "body":
        materialized = [
            row for row in materialized if row["variable_name"].startswith("T_body_L")
        ]
    elif group == "custom":
        materialized = [
            row for row in materialized if row["variable_name"] in requested_set
        ]
    return materialized


def sensor_window_statistics(
    conn: Any,
    heat: dict[str, Any],
    window_kind: str,
    group: str,
    requested: list[str] | None,
    pre_tap_minutes: int,
) -> dict[str, Any]:
    start, end_exclusive, boundary = resolve_sensor_window(
        heat, window_kind, pre_tap_minutes
    )
    registry = _select_registry(conn, group, requested)
    tags = [row["tag_long_name"] for row in registry]
    expected_minutes = max(
        1, int((end_exclusive - start).total_seconds() // 60)
    )
    aggregates: dict[str, dict[str, Any]] = {}
    if tags:
        rows = conn.execute(
            """
            SELECT tag_long_name,
                   count(value) AS sample_count,
                   avg(value) AS mean_value,
                   min(value) AS min_value,
                   max(value) AS max_value,
                   stddev_samp(value) AS std_value,
                   regr_slope(value, extract(epoch from ts)) * 60 AS slope_per_minute,
                   (array_agg(value ORDER BY ts DESC))[1] AS latest_value,
                   max(ts) AS latest_ts
            FROM bf_sensor.one_minute_values
            WHERE ts >= %s AND ts < %s
              AND tag_long_name = ANY(%s)
            GROUP BY tag_long_name
            """,
            (start, end_exclusive, tags),
        ).fetchall()
        aggregates = {row["tag_long_name"]: dict(row) for row in rows}
    stats: list[dict[str, Any]] = []
    for meta in registry:
        agg = aggregates.get(meta["tag_long_name"], {})
        sample_count = int(agg.get("sample_count") or 0)
        coverage = min(1.0, sample_count / expected_minutes)
        stats.append(
            {
                **meta,
                "unit": infer_unit(meta["variable_name"]),
                "sample_count": sample_count,
                "expected_minutes": expected_minutes,
                "coverage_ratio": round(coverage, 4),
                "mean": number(agg.get("mean_value")),
                "min": number(agg.get("min_value")),
                "max": number(agg.get("max_value")),
                "std": number(agg.get("std_value")),
                "slope_per_minute": number(agg.get("slope_per_minute")),
                "latest": number(agg.get("latest_value")),
                "latest_ts": agg.get("latest_ts"),
                "status": (
                    "good" if coverage >= 0.95 else "partial" if coverage > 0 else "missing"
                ),
            }
        )
    return {
        "kind": window_kind,
        "group": group,
        "start": start,
        "end_exclusive": end_exclusive,
        "boundary": boundary,
        "expected_minutes": expected_minutes,
        "point_count": len(stats),
        "good_point_count": sum(1 for row in stats if row["status"] == "good"),
        "average_coverage": (
            round(sum(row["coverage_ratio"] for row in stats) / len(stats), 4)
            if stats
            else 0
        ),
        "statistics": stats,
    }


def _diagnosis_context(
    conn: Any,
    start: datetime,
    end_exclusive: datetime,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT diagnosis_ts, main_label, main_score, main_confidence,
               secondary_label, secondary_score, evidence, raw_scores,
               feature_snapshot, diagnosis_json, data_coverage,
               source_lag_seconds
        FROM (
            SELECT DISTINCT ON (diagnosis_ts)
                   diagnosis_ts, main_label, main_score, main_confidence,
                   secondary_label, secondary_score, evidence, raw_scores,
                   feature_snapshot, diagnosis_json, data_coverage,
                   source_lag_seconds, updated_at, id
            FROM bf_sensor.diagnosis_snapshots
            WHERE diagnosis_ts >= %s AND diagnosis_ts < %s
            ORDER BY diagnosis_ts, updated_at DESC, id DESC
        ) latest
        ORDER BY diagnosis_ts
        """,
        (start, end_exclusive),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for raw in rows:
        item = dict(raw)
        item["main_label_display"] = DIAGNOSIS_DISPLAY_LABELS.get(
            str(item.get("main_label") or ""),
            str(item.get("main_label") or "未知"),
        )
        secondary = str(item.get("secondary_label") or "")
        item["secondary_label_display"] = (
            DIAGNOSIS_DISPLAY_LABELS.get(secondary, secondary) if secondary else None
        )
        if generate_recommendation is not None:
            try:
                item["recommendation"] = generate_recommendation(item)
                item["recommendation_status"] = "ready"
            except Exception as exc:  # noqa: BLE001
                item["recommendation_status"] = "failed"
                item["recommendation_error_type"] = type(exc).__name__
        else:
            item["recommendation_status"] = "unavailable"
        items.append(item)
    distribution = Counter(str(row.get("main_label") or "unknown") for row in items)
    scores = [number(row.get("main_score")) for row in items]
    valid_scores = [value for value in scores if value is not None]
    return {
        "count": len(items),
        "distribution": dict(distribution),
        "average_main_score": (
            round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else None
        ),
        "latest": items[-1] if items else None,
        "items": items,
        "engine": {
            "diagnosis": "full115 diagnosis snapshots",
            "recommendation": "blast_furnace_recommendation_engine",
            "read_only": True,
        },
    }


def sensor_window_rows(
    conn: Any,
    heat: dict[str, Any],
    window_kind: str,
    group: str,
    requested: list[str] | None,
    pre_tap_minutes: int,
) -> list[dict[str, Any]]:
    """Return raw one-minute rows for an auditable per-heat export."""

    start, end_exclusive, _ = resolve_sensor_window(
        heat, window_kind, pre_tap_minutes
    )
    registry = _select_registry(conn, group, requested)
    if not registry:
        return []
    tags = [row["tag_long_name"] for row in registry]
    meta = {row["tag_long_name"]: row for row in registry}
    rows = conn.execute(
        """
        SELECT tag_long_name, ts, value, quality, value_type,
               aggregate, interval_seconds, source_server, collected_at
        FROM bf_sensor.one_minute_values
        WHERE ts >= %s AND ts < %s
          AND tag_long_name = ANY(%s)
        ORDER BY ts, tag_long_name
        """,
        (start, end_exclusive, tags),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        point = meta.get(row["tag_long_name"], {})
        result.append(
            {
                "meltno": heat.get("meltno"),
                "window_kind": window_kind,
                "window_start": start,
                "window_end_exclusive": end_exclusive,
                "variable_name": point.get("variable_name"),
                "chinese_name": point.get("chinese_name"),
                "unit": infer_unit(str(point.get("variable_name") or "")),
                **row,
            }
        )
    return result


def _numeric_median(items: list[dict[str, Any]], field: str) -> float | None:
    values = [
        float(item[field])
        for item in items
        if item.get(field) is not None
    ]
    return float(median(values)) if values else None


def build_model_feature_row(detail: dict[str, Any]) -> dict[str, Any]:
    """Build one auditable wide row for future quality-model experiments."""

    heat = detail["heat"]
    sensor = detail["sensor_window"]
    diagnosis = detail["diagnosis"]
    hot = heat.get("hot_metal_samples") or []
    slag = heat.get("slag_samples") or []
    sinter = heat.get("sinter_context") or []
    latest_diag = diagnosis.get("latest") or {}
    row: dict[str, Any] = {
        "meltno": heat.get("meltno"),
        "open_ts": heat.get("open_ts"),
        "close_ts": heat.get("close_ts"),
        "window_kind": sensor.get("kind"),
        "window_start": sensor.get("start"),
        "window_end_exclusive": sensor.get("end_exclusive"),
        "actual_iron_qty": heat.get("actual_iron_qty"),
        "hot_metal_sample_count": heat.get("hot_metal_sample_count"),
        "slag_sample_count": heat.get("slag_sample_count"),
        "sinter_context_sample_count": len(sinter),
        "target__hot_metal_Si_median": (
            heat.get("hot_metal_si_summary") or {}
        ).get("median"),
        "target__hot_metal_Si_min": (
            heat.get("hot_metal_si_summary") or {}
        ).get("min"),
        "target__hot_metal_Si_max": (
            heat.get("hot_metal_si_summary") or {}
        ).get("max"),
        "diagnosis__latest_label": latest_diag.get("main_label"),
        "diagnosis__latest_score": latest_diag.get("main_score"),
        "diagnosis__average_score": diagnosis.get("average_main_score"),
        "diagnosis__snapshot_count": diagnosis.get("count"),
        "sensor__point_count": sensor.get("point_count"),
        "sensor__good_point_count": sensor.get("good_point_count"),
        "sensor__average_coverage": sensor.get("average_coverage"),
        "mapping__hot_metal": "sample_no_heat_tail_with_24h_guard",
        "mapping__slag": "exact_meltno",
        "mapping__sinter": "time_context_only_not_exact_lineage",
    }
    for element in ("C", "Si", "Mn", "P", "S", "Ti", "V", "Cr", "Ni", "Cu", "As"):
        row[f"target__hot_metal_{element}_median"] = _numeric_median(hot, element)
    for element in ("TFe", "FeO", "CaO", "MgO", "SiO2", "Al2O3", "TiO2", "R2", "R3", "R4"):
        row[f"target__slag_{element}_median"] = _numeric_median(slag, element)
    for element in ("TFe", "FeO", "CaO", "MgO", "SiO2", "Al2O3", "P", "S", "TiO2", "MnO", "Zn", "R2"):
        row[f"context__sinter_{element}_median"] = _numeric_median(sinter, element)
    for point in sensor.get("statistics") or []:
        prefix = f"sensor__{point.get('variable_name')}"
        for field in ("mean", "min", "max", "std", "slope_per_minute", "latest", "coverage_ratio"):
            row[f"{prefix}__{field}"] = point.get(field)
    return row


def heat_detail(
    pg_connect: Callable[[], Any],
    meltno: str,
    window_kind: str = "pre_tap",
    sensor_group: str = "core",
    variables: list[str] | None = None,
    pre_tap_minutes: int = 120,
) -> dict[str, Any]:
    """Return one heat with chemistry, upstream context and sensor statistics."""

    heats = _fetch_heat_rows(limit=1, meltno=meltno)
    if not heats:
        raise KeyError(f"未找到炉次：{meltno}")
    heat = heats[0]
    _attach_outputs(heats)
    hot_rows, slag_rows = _fetch_lab_rows_for_heats(heats)
    _attach_lab_samples(heats, hot_rows, slag_rows)
    sinter = _fetch_sinter_context(heat["open_ts"], hours=12)
    sensor_source_error: str | None = None
    source_bounds: dict[str, Any] = {"min_ts": None, "max_ts": None}
    try:
        with pg_connect() as pg_conn:
            sensor_window = sensor_window_statistics(
                pg_conn,
                heat,
                window_kind,
                sensor_group,
                variables,
                pre_tap_minutes,
            )
            diagnosis = _diagnosis_context(
                pg_conn,
                sensor_window["start"],
                sensor_window["end_exclusive"],
            )
            source_bounds = dict(
                pg_conn.execute(
                    """
                    SELECT min(ts) AS min_ts, max(ts) AS max_ts
                    FROM bf_sensor.one_minute_values
                    """
                ).fetchone()
                or {}
            )
    except Exception as exc:  # one unavailable source must not hide the heat chemistry
        sensor_source_error = f"{type(exc).__name__}: 传感器数据库只读访问失败"
        start, end_exclusive, boundary = resolve_sensor_window(
            heat, window_kind, pre_tap_minutes
        )
        sensor_window = {
            "kind": window_kind,
            "group": sensor_group,
            "start": start,
            "end_exclusive": end_exclusive,
            "boundary": boundary,
            "expected_minutes": max(
                1, int((end_exclusive - start).total_seconds() // 60)
            ),
            "point_count": 0,
            "good_point_count": 0,
            "average_coverage": 0,
            "statistics": [],
            "source_error": sensor_source_error,
        }
        diagnosis = {
            "count": 0,
            "distribution": {},
            "average_main_score": None,
            "latest": None,
            "items": [],
            "source_error": sensor_source_error,
            "engine": {
                "diagnosis": "full115 diagnosis snapshots",
                "recommendation": "blast_furnace_recommendation_engine",
                "read_only": True,
            },
        }
    heat["sinter_context"] = sinter
    now = datetime.now()
    source_min = source_bounds["min_ts"]
    source_max = source_bounds["max_ts"]
    availability_reasons: list[str] = []
    if sensor_source_error:
        availability_reasons.append("sensor_source_unavailable")
    if heat.get("open_ts") and heat["open_ts"] > now + timedelta(minutes=5):
        availability_reasons.append("heat_open_time_is_in_future")
    if source_max and sensor_window["start"] > source_max:
        availability_reasons.append("sensor_window_after_latest_sensor_data")
    if source_min and sensor_window["end_exclusive"] <= source_min:
        availability_reasons.append("sensor_window_before_sensor_history")
    if sensor_window["average_coverage"] < 0.95:
        availability_reasons.append("sensor_window_partial_or_missing")
    if not heat.get("hot_metal_samples"):
        availability_reasons.append("hot_metal_sample_missing")
    if not heat.get("slag_samples"):
        availability_reasons.append("slag_sample_missing")
    result = {
        "ok": True,
        "checked_at": now,
        "heat": heat,
        "sensor_window": sensor_window,
        "diagnosis": diagnosis,
        "data_availability": {
            "state": "complete" if not availability_reasons else "partial",
            "reasons": availability_reasons,
            "sensor_source_min_ts": source_min,
            "sensor_source_max_ts": source_max,
            "sensor_window_point_count": sensor_window["point_count"],
            "sensor_window_good_point_count": sensor_window["good_point_count"],
            "sensor_window_average_coverage": sensor_window["average_coverage"],
            "sensor_source_error": sensor_source_error,
        },
        "alignment_audit": {
            "heat_key": "exact_meltno",
            "slag": "exact_meltno",
            "hot_metal": "exact_heatno_batchno",
            "sinter": "time_context_only_not_exact_heat_lineage",
            "sensor": f"{window_kind}:{sensor_window['boundary']}",
            "warnings": [
                "铁水化验以 t_qpes_inner_batch.heatno 精确关联炉次，并以 batchno 精确关联元素结果。",
                "化验判定时间不是取样或开铁口时间；时间分析优先使用 sample_ts，并保留 result_ts 供审计。",
                "烧结矿视图没有高炉炉次号；当前只显示开铁口前12小时背景，不能解释为该炉次实际入炉批次。",
                "生产级原料归属需补齐烧结试样到料仓、矿批、batch_input 与 sumbatchStart/sumbatchEnd 的谱系。",
            ],
        },
        "sources": {
            "heat_master": "IMES public.t_ipes_cond",
            "outputs": "IMES public.t_ipes_out_put",
            "hot_metal": "IMES public.t_qpes_inner_batch + public.inner_batch_insp_bb",
            "slag": SLAG_VIEW,
            "sinter": SINTER_VIEW,
            "sensor": "PostgreSQL bf_sensor.one_minute_values",
            "registry": "PostgreSQL bf_sensor.sensor_registry",
            "diagnosis": "PostgreSQL bf_sensor.diagnosis_snapshots",
            "policy": "read_only",
        },
    }
    result["model_feature_row"] = build_model_feature_row(result)
    return result


def flatten_heats_for_export(heats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for heat in heats:
        hot = heat.get("latest_hot_metal") or {}
        si = heat.get("hot_metal_si_summary") or {}
        slag = heat.get("latest_slag") or {}
        result.append(
            {
                "meltno": heat.get("meltno"),
                "open_ts": heat.get("open_ts"),
                "close_ts": heat.get("close_ts"),
                "duration_minutes": heat.get("duration_minutes"),
                "actual_iron_qty": heat.get("actual_iron_qty"),
                "hot_metal_sample_count": heat.get("hot_metal_sample_count"),
                "hot_metal_Si": hot.get("Si"),
                "hot_metal_Si_latest": hot.get("Si"),
                "hot_metal_Si_median": si.get("median"),
                "hot_metal_Si_min": si.get("min"),
                "hot_metal_Si_max": si.get("max"),
                "hot_metal_Si_spread": si.get("spread"),
                "hot_metal_S": hot.get("S"),
                "slag_sample_count": heat.get("slag_sample_count"),
                "slag_FeO": slag.get("FeO"),
                "slag_R2": slag.get("R2"),
                "alignment_status": heat.get("alignment_status"),
            }
        )
    return result
