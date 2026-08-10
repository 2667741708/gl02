"""Per-heat production-performance and hot-metal-quality fact store.

The source IMES rows remain authoritative.  This module stores one derived,
idempotently replaceable row per official ``meltno`` in PostgreSQL so the 8093
front end does not have to join multiple remote IMES tables on every refresh.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import math
import os
from statistics import median
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


TABLE_NAME = "bf_assistant.heat_performance_quality_summary"
AGGREGATION_VERSION = "heat-performance-quality.v2"
ELEMENTS = ("C", "Si", "Mn", "P", "S")
SI_TARGET_LOW = float(os.getenv("BF_HEAT_QUALITY_SI_TARGET_LOW", "0.20"))
SI_TARGET_HIGH = float(os.getenv("BF_HEAT_QUALITY_SI_TARGET_HIGH", "0.40"))

TABLE_DDL = f"""
CREATE SCHEMA IF NOT EXISTS bf_assistant;
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    meltno text PRIMARY KEY,
    furnace_no text NOT NULL,
    work_date date,
    open_ts timestamp without time zone,
    close_ts timestamp without time zone,
    raw_open_ts timestamp without time zone,
    raw_close_ts timestamp without time zone,
    repaired_open_ts timestamp without time zone,
    repaired_close_ts timestamp without time zone,
    duration_minutes numeric(10,2),
    batch_start text,
    batch_end text,
    batch_count numeric(12,2),
    theory_iron_qty numeric(14,3),
    actual_iron_qty numeric(14,3),
    gross_weight_total numeric(14,3),
    tare_weight_total numeric(14,3),
    net_weight_total numeric(14,3),
    slag_rate numeric(14,4),
    output_count integer NOT NULL DEFAULT 0,
    shift text,
    work_class text,
    hot_metal_sample_count integer NOT NULL DEFAULT 0,
    first_sample_ts timestamp without time zone,
    last_sample_ts timestamp without time zone,
    c_avg numeric(12,5),
    si_avg numeric(12,5),
    mn_avg numeric(12,5),
    p_avg numeric(12,5),
    s_avg numeric(12,5),
    si_median numeric(12,5),
    si_min numeric(12,5),
    si_max numeric(12,5),
    si_spread numeric(12,5),
    si_available_at timestamp with time zone,
    si_availability_confidence text NOT NULL DEFAULT 'not_available',
    si_band text,
    quality_status text NOT NULL,
    quality_summary text NOT NULL,
    chemistry_stats jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    sample_details jsonb NOT NULL DEFAULT '[]'::jsonb,
    output_details jsonb NOT NULL DEFAULT '[]'::jsonb,
    missing_elements jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_status text NOT NULL,
    time_anomaly_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    repair_checked_at timestamp with time zone,
    future_pending boolean NOT NULL DEFAULT false,
    source_updated_at timestamp without time zone,
    aggregated_at timestamp with time zone NOT NULL DEFAULT now(),
    aggregation_version text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_heat_performance_quality_open_ts
    ON {TABLE_NAME} (open_ts DESC);
CREATE INDEX IF NOT EXISTS idx_heat_performance_quality_si_band
    ON {TABLE_NAME} (si_band, open_ts DESC);
COMMENT ON TABLE {TABLE_NAME} IS
    'Derived one-row-per-official-meltno production and hot-metal chemistry summary; raw IMES samples remain authoritative.';
"""

SCHEMA_UPGRADE_DDL = f"""
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS raw_open_ts timestamp without time zone;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS raw_close_ts timestamp without time zone;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS repaired_open_ts timestamp without time zone;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS repaired_close_ts timestamp without time zone;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS time_anomaly_reasons jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS repair_checked_at timestamp with time zone;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS future_pending boolean NOT NULL DEFAULT false;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS si_available_at timestamp with time zone;
ALTER TABLE {TABLE_NAME}
    ADD COLUMN IF NOT EXISTS si_availability_confidence text NOT NULL DEFAULT 'not_available';
UPDATE {TABLE_NAME}
SET si_available_at = COALESCE(si_available_at, aggregated_at, now()),
    si_availability_confidence = CASE
        WHEN si_availability_confidence = 'observed_first_ingest' THEN si_availability_confidence
        WHEN aggregated_at IS NOT NULL THEN 'recovered_aggregation_timestamp'
        ELSE 'legacy_availability_unknown'
    END
WHERE si_avg IS NOT NULL
  AND si_available_at IS NULL;
UPDATE {TABLE_NAME}
SET raw_open_ts = COALESCE(raw_open_ts, open_ts),
    raw_close_ts = COALESCE(raw_close_ts, close_ts)
WHERE raw_open_ts IS NULL OR raw_close_ts IS NULL;
UPDATE {TABLE_NAME}
SET repaired_open_ts = COALESCE(repaired_open_ts, open_ts),
    repaired_close_ts = COALESCE(repaired_close_ts, close_ts)
WHERE source_status = 'time_anomaly_repaired'
  AND (repaired_open_ts IS NULL OR repaired_close_ts IS NULL);
"""


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def chemistry_statistics(samples: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sample_list = list(samples)
    result: dict[str, dict[str, Any]] = {}
    for element in ELEMENTS:
        values = [
            value
            for value in (_number(sample.get(element)) for sample in sample_list)
            if value is not None
        ]
        if not values:
            result[element] = {
                "valid_count": 0,
                "avg": None,
                "median": None,
                "min": None,
                "max": None,
                "spread": None,
            }
            continue
        low, high = min(values), max(values)
        result[element] = {
            "valid_count": len(values),
            "avg": sum(values) / len(values),
            "median": float(median(values)),
            "min": low,
            "max": high,
            "spread": high - low,
        }
    return result


def _sample_time(sample: dict[str, Any]) -> datetime | None:
    for key in ("sample_ts", "result_ts", "publish_ts"):
        value = sample.get(key)
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if value:
            try:
                return datetime.fromisoformat(str(value).replace("T", " ")).replace(tzinfo=None)
            except ValueError:
                pass
    return None


def _si_band(si_avg: float | None) -> str | None:
    if si_avg is None:
        return None
    if si_avg < SI_TARGET_LOW:
        return "below_target"
    if si_avg > SI_TARGET_HIGH:
        return "above_target"
    return "target"


def build_summary_row(heat: dict[str, Any]) -> dict[str, Any]:
    """Build one auditable row without discarding the original sample detail."""

    samples = list(heat.get("hot_metal_samples") or [])
    stats = chemistry_statistics(samples)
    missing = [element for element in ELEMENTS if stats[element]["avg"] is None]
    si = stats["Si"]
    band = _si_band(si["avg"])
    if len(missing) == len(ELEMENTS):
        quality_status = "missing"
    elif missing:
        quality_status = "partial"
    else:
        quality_status = "complete"
    band_text = {
        "below_target": f"Si均值低于{SI_TARGET_LOW:.2f}%目标带",
        "target": f"Si均值位于{SI_TARGET_LOW:.2f}%–{SI_TARGET_HIGH:.2f}%目标带",
        "above_target": f"Si均值高于{SI_TARGET_HIGH:.2f}%目标带",
        None: "暂无有效Si试样",
    }[band]
    if missing:
        completeness = "；缺少" + "、".join(missing)
    else:
        completeness = "；C/Si/Mn/P/S均有有效结果"
    spread_text = (
        f"；Si样本范围{si['min']:.3f}%–{si['max']:.3f}%"
        if si["min"] is not None
        else ""
    )
    sample_times = [value for value in (_sample_time(sample) for sample in samples) if value]
    outputs = list(heat.get("outputs") or [])
    gross_weights = [value for value in (_number(item.get("gross_weight")) for item in outputs) if value is not None]
    tare_weights = [value for value in (_number(item.get("tare_weight")) for item in outputs) if value is not None]
    source_times = sample_times + [
        value
        for value in (
            heat.get("close_ts"),
            *[item.get("weight_time") for item in outputs],
        )
        if isinstance(value, datetime)
    ]
    meltno = str(heat.get("meltno") or "").strip()
    furnace_no = meltno.split("#", 1)[0] if "#" in meltno else "2"
    work_date = heat.get("workdate") or None
    if isinstance(work_date, str):
        try:
            work_date = date.fromisoformat(work_date[:10])
        except ValueError:
            work_date = None
    return {
        "meltno": meltno,
        "furnace_no": furnace_no,
        "work_date": work_date,
        "open_ts": heat.get("open_ts"),
        "close_ts": heat.get("close_ts"),
        "raw_open_ts": heat.get("raw_open_ts") or heat.get("open_ts"),
        "raw_close_ts": heat.get("raw_close_ts") or heat.get("close_ts"),
        "repaired_open_ts": heat.get("repaired_open_ts"),
        "repaired_close_ts": heat.get("repaired_close_ts"),
        "duration_minutes": _number(heat.get("duration_minutes")),
        "batch_start": str(heat.get("batch_start")) if heat.get("batch_start") is not None else None,
        "batch_end": str(heat.get("batch_end")) if heat.get("batch_end") is not None else None,
        "batch_count": _number(heat.get("batch_count")),
        "theory_iron_qty": _number(heat.get("theory_iron_qty")),
        "actual_iron_qty": _number(heat.get("actual_iron_qty")),
        "gross_weight_total": sum(gross_weights) if gross_weights else None,
        "tare_weight_total": sum(tare_weights) if tare_weights else None,
        "net_weight_total": (
            sum(gross_weights) - sum(tare_weights)
            if gross_weights and tare_weights
            else None
        ),
        "slag_rate": _number(heat.get("slag_rate")),
        "output_count": int(heat.get("output_count") or 0),
        "shift": heat.get("shift"),
        "work_class": heat.get("work_class"),
        "hot_metal_sample_count": len(samples),
        "first_sample_ts": min(sample_times) if sample_times else None,
        "last_sample_ts": max(sample_times) if sample_times else None,
        "c_avg": stats["C"]["avg"],
        "si_avg": si["avg"],
        "mn_avg": stats["Mn"]["avg"],
        "p_avg": stats["P"]["avg"],
        "s_avg": stats["S"]["avg"],
        "si_median": si["median"],
        "si_min": si["min"],
        "si_max": si["max"],
        "si_spread": si["spread"],
        "si_band": band,
        "quality_status": quality_status,
        "quality_summary": band_text + spread_text + completeness,
        "chemistry_stats": _json_safe(stats),
        "sample_details": _json_safe(samples),
        "output_details": _json_safe(outputs),
        "missing_elements": missing,
        "source_status": str(heat.get("alignment_status") or quality_status),
        "time_anomaly_reasons": _json_safe(heat.get("time_anomaly_reasons") or []),
        "repair_checked_at": heat.get("repair_checked_at"),
        "future_pending": bool(heat.get("future_pending")),
        "source_updated_at": max(source_times) if source_times else heat.get("open_ts"),
        "aggregation_version": AGGREGATION_VERSION,
    }


def _connection_params(read_only: bool) -> dict[str, Any]:
    password_env = os.getenv("BF_DIAG_REVIEW_PGPASSWORD_ENV", "GL02_PGPASSWORD")
    password = os.getenv("BF_HEAT_PERFORMANCE_PGPASSWORD") or os.getenv(password_env)
    if not password:
        raise RuntimeError("缺少炉次实绩库密码环境变量")
    params: dict[str, Any] = {
        "host": os.getenv("BF_HEAT_PERFORMANCE_PGHOST") or os.getenv("BF_DIAG_REVIEW_PGHOST") or os.getenv("GL02_PGHOST") or "127.0.0.1",
        "port": int(os.getenv("BF_HEAT_PERFORMANCE_PGPORT") or os.getenv("BF_DIAG_REVIEW_PGPORT") or os.getenv("GL02_PGPORT") or "5432"),
        "dbname": os.getenv("BF_HEAT_PERFORMANCE_PGDATABASE") or os.getenv("BF_DIAG_REVIEW_PGDATABASE") or os.getenv("GL02_PGDATABASE") or "bf_trend",
        "user": os.getenv("BF_HEAT_PERFORMANCE_PGUSER") or os.getenv("BF_DIAG_REVIEW_PGUSER") or os.getenv("GL02_PGUSER") or "gl02_sync",
        "password": password,
        "connect_timeout": 5,
        "application_name": "bf_heat_performance_quality",
    }
    if read_only:
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=5000"
    return params


class HeatPerformanceQualityStore:
    def connect(self, *, read_only: bool = True):
        return psycopg.connect(**_connection_params(read_only), row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self.connect(read_only=False) as connection:
            connection.execute(TABLE_DDL)
            connection.execute(SCHEMA_UPGRADE_DDL)

    def upsert_rows(self, rows: Iterable[dict[str, Any]]) -> int:
        columns = (
            "meltno", "furnace_no", "work_date", "open_ts", "close_ts",
            "raw_open_ts", "raw_close_ts", "repaired_open_ts", "repaired_close_ts",
            "duration_minutes", "batch_start", "batch_end", "batch_count",
            "theory_iron_qty", "actual_iron_qty", "gross_weight_total",
            "tare_weight_total", "net_weight_total", "slag_rate",
            "output_count", "shift", "work_class", "hot_metal_sample_count",
            "first_sample_ts", "last_sample_ts", "c_avg", "si_avg", "mn_avg",
            "p_avg", "s_avg", "si_median", "si_min", "si_max", "si_spread",
            "si_available_at", "si_availability_confidence",
            "si_band", "quality_status", "quality_summary", "chemistry_stats",
            "sample_details", "output_details", "missing_elements", "source_status",
            "time_anomaly_reasons", "repair_checked_at", "future_pending", "source_updated_at",
            "aggregation_version",
        )
        protected_columns = {
            "open_ts", "close_ts", "raw_open_ts", "raw_close_ts",
            "repaired_open_ts", "repaired_close_ts",
            "duration_minutes", "source_status", "time_anomaly_reasons",
            "repair_checked_at", "future_pending",
        }
        protected_existing = (
            "(existing.source_status = 'time_anomaly_repaired' "
            "OR (existing.source_status = 'future_pending' "
            "AND (existing.open_ts > now() + interval '5 minutes' "
            "OR existing.time_anomaly_reasons ? 'meltno_workdate_date_mismatch'))) "
            "AND EXCLUDED.source_status NOT IN ('time_anomaly_repaired', 'future_pending')"
        )
        assignments_list: list[str] = []
        for column in columns:
            if column == "meltno":
                continue
            if column == "si_available_at":
                assignments_list.append(
                    "si_available_at=CASE "
                    "WHEN existing.si_available_at IS NOT NULL THEN existing.si_available_at "
                    "WHEN EXCLUDED.si_avg IS NOT NULL "
                    "THEN COALESCE(EXCLUDED.si_available_at, existing.aggregated_at, now()) "
                    "ELSE NULL END"
                )
            elif column == "si_availability_confidence":
                assignments_list.append(
                    "si_availability_confidence=CASE "
                    "WHEN existing.si_available_at IS NOT NULL THEN existing.si_availability_confidence "
                    "WHEN EXCLUDED.si_avg IS NOT NULL "
                    "THEN EXCLUDED.si_availability_confidence "
                    "ELSE existing.si_availability_confidence END"
                )
            elif column in protected_columns:
                assignments_list.append(
                    f"{column}=CASE WHEN {protected_existing} "
                    f"THEN existing.{column} ELSE EXCLUDED.{column} END"
                )
            else:
                assignments_list.append(f"{column}=EXCLUDED.{column}")
        assignments = ", ".join(assignments_list)
        sql = f"""
            INSERT INTO {TABLE_NAME} AS existing ({', '.join(columns)})
            VALUES ({', '.join(['%s'] * len(columns))})
            ON CONFLICT (meltno) DO UPDATE SET {assignments}, aggregated_at=now()
        """
        prepared = list(rows)
        if not prepared:
            return 0
        with self.connect(read_only=False) as connection:
            for row in prepared:
                if row.get("si_avg") is not None and row.get("si_available_at") is None:
                    row["si_available_at"] = datetime.now().astimezone()
                    row["si_availability_confidence"] = "observed_first_ingest"
                elif row.get("si_avg") is None:
                    row["si_availability_confidence"] = "not_available"
                values = []
                for column in columns:
                    value = row.get(column)
                    if column in {
                        "chemistry_stats", "sample_details", "output_details",
                        "missing_elements", "time_anomaly_reasons",
                    }:
                        value = Jsonb(value)
                    values.append(value)
                connection.execute(sql, values)
        return len(prepared)

    def apply_time_repairs(self, rows: Iterable[dict[str, Any]]) -> int:
        """Update only time-lineage fields for already aggregated heats.

        The local IMES mirror contains a per-heat chemistry average rather than
        the original ladle samples.  A repair pass must therefore never replace
        the richer chemistry/sample/output payload already stored for a heat.
        """

        prepared = list(rows)
        if not prepared:
            return 0
        sql = f"""
            UPDATE {TABLE_NAME}
               SET work_date = %s,
                   open_ts = %s,
                   close_ts = %s,
                   raw_open_ts = %s,
                   raw_close_ts = %s,
                   repaired_open_ts = %s,
                   repaired_close_ts = %s,
                   duration_minutes = %s,
                   source_status = %s,
                   time_anomaly_reasons = %s,
                   repair_checked_at = %s,
                   future_pending = %s,
                   aggregated_at = now(),
                   aggregation_version = %s
             WHERE meltno = %s
        """
        with self.connect(read_only=False) as connection:
            for row in prepared:
                connection.execute(sql, (
                    row.get("work_date"), row.get("open_ts"), row.get("close_ts"),
                    row.get("raw_open_ts"), row.get("raw_close_ts"),
                    row.get("repaired_open_ts"), row.get("repaired_close_ts"),
                    row.get("duration_minutes"), row.get("source_status"),
                    Jsonb(row.get("time_anomaly_reasons") or []),
                    row.get("repair_checked_at"), bool(row.get("future_pending")),
                    row.get("aggregation_version") or AGGREGATION_VERSION,
                    row.get("meltno"),
                ))
        return len(prepared)

    def list_rows(
        self,
        *,
        limit: int = 12,
        meltno: str | None = None,
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        has_samples: bool = False,
        include_future: bool = False,
    ) -> dict[str, Any]:
        """List heat summaries with IMES-style read-only filters."""

        limit = max(1, min(int(limit), 100))
        clauses: list[str] = []
        params: list[Any] = []
        if meltno:
            clauses.append("meltno = %s")
            params.append(meltno)
        if query:
            like = f"%{query[:120]}%"
            clauses.append(
                "(meltno ILIKE %s OR sample_details::text ILIKE %s OR output_details::text ILIKE %s)"
            )
            params.extend((like, like, like))
        if date_from:
            clauses.append("work_date >= %s::date")
            params.append(date_from)
        if date_to:
            clauses.append("work_date <= %s::date")
            params.append(date_to)
        if has_samples:
            clauses.append("hot_metal_sample_count > 0")
        if not include_future:
            clauses.append("future_pending IS NOT TRUE")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect(read_only=True) as connection:
            exists_row = connection.execute(
                "SELECT to_regclass(%s) AS relation_name",
                (TABLE_NAME,),
            ).fetchone()
            exists = exists_row["relation_name"] if exists_row else None
            if not exists:
                return {
                    "ok": False,
                    "error_code": "HEAT_PERFORMANCE_TABLE_NOT_READY",
                    "items": [],
                    "read_only": True,
                }
            rows = connection.execute(
                f"SELECT * FROM {TABLE_NAME} {where} ORDER BY open_ts DESC NULLS LAST LIMIT %s",
                tuple(params),
            ).fetchall()
        items = [_json_safe(dict(row)) for row in rows]
        return {
            "ok": True,
            "items": items,
            "count": len(items),
            "table": TABLE_NAME,
            "read_only": True,
            "quality_contract": {
                "si_target_low": SI_TARGET_LOW,
                "si_target_high": SI_TARGET_HIGH,
                "statement": "\u76ee\u6807\u5e26\u4e0e\u6837\u672c\u5b8c\u6574\u6027\u63cf\u8ff0\uff0c\u4e0d\u66ff\u4ee3\u6b63\u5f0f\u8d28\u91cf\u5224\u5b9a",
            },
            "filters": {
                "meltno": meltno,
                "query": query or None,
                "date_from": date_from or None,
                "date_to": date_to or None,
                "has_samples": bool(has_samples),
                "include_future": bool(include_future),
            },
        }

    def existing_lineage(self, meltnos: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Return compact existing target facts for pre-upsert gap auditing."""

        values = sorted({str(item).strip() for item in meltnos if str(item).strip()})
        if not values:
            return {}
        with self.connect(read_only=True) as connection:
            exists_row = connection.execute(
                "SELECT to_regclass(%s) AS relation_name",
                (TABLE_NAME,),
            ).fetchone()
            if not exists_row or not exists_row["relation_name"]:
                return {}
            rows = connection.execute(
                f"""
                SELECT meltno, open_ts, close_ts, output_count,
                       hot_metal_sample_count, source_status,
                       source_updated_at
                  FROM {TABLE_NAME}
                 WHERE meltno = ANY(%s)
                """,
                (values,),
            ).fetchall()
        return {str(row["meltno"]): dict(row) for row in rows}

    def existing_mirror_lineage(
        self,
        meltnos: Iterable[str],
    ) -> dict[str, dict[str, Any]] | None:
        """Return raw IMES mirror presence without treating a missing table as zero gaps."""

        values = sorted({str(item).strip() for item in meltnos if str(item).strip()})
        if not values:
            return {}
        with self.connect(read_only=True) as connection:
            exists_row = connection.execute(
                "SELECT to_regclass('bf_imes.raw_rows') AS relation_name"
            ).fetchone()
            if not exists_row or not exists_row["relation_name"]:
                return None
            rows = connection.execute(
                """
                SELECT COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
                       count(*) AS mirror_row_count,
                       bool_or(NULLIF(COALESCE(row_json->>'openTime', row_json->>'opentime'), '') IS NOT NULL)
                           AS open_ts_present,
                       bool_or(NULLIF(COALESCE(row_json->>'closeTime', row_json->>'closetime'), '') IS NOT NULL)
                           AS close_ts_present,
                       bool_or(NULLIF(COALESCE(row_json->>'ironQuan', row_json->>'ironquan'), '') IS NOT NULL)
                           AS output_present,
                       bool_or(NULLIF(COALESCE(row_json->>'value_02', row_json->>'Si', row_json->>'si'), '') IS NOT NULL)
                           AS si_present
                  FROM bf_imes.raw_rows
                 WHERE COALESCE(row_json->>'meltNo', row_json->>'meltno') = ANY(%s)
                 GROUP BY COALESCE(row_json->>'meltNo', row_json->>'meltno')
                """,
                (values,),
            ).fetchall()
        return {str(row["meltno"]): dict(row) for row in rows}


def build_gap_audit(
    rows: Iterable[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    *,
    mirror: dict[str, dict[str, Any]] | None = None,
    detail_limit: int = 100,
) -> dict[str, Any]:
    """Compare source facts with the raw mirror and derived summary independently."""

    incoming = list(rows)
    mirror_missing: list[str] = []
    mirror_field_empty: list[dict[str, Any]] = []
    summary_missing: list[str] = []
    sample_changes: list[dict[str, Any]] = []
    mirror_field_contract = (
        ("open_ts", "open_ts_present"),
        ("close_ts", "close_ts_present"),
        ("output_count", "output_present"),
        ("si_avg", "si_present"),
    )
    for row in incoming:
        meltno = str(row.get("meltno") or "")
        if mirror is not None:
            mirrored = mirror.get(meltno)
            if mirrored is None:
                mirror_missing.append(meltno)
            else:
                missing_fields = [
                    source_field
                    for source_field, mirror_flag in mirror_field_contract
                    if row.get(source_field) not in {None, "", 0}
                    and not bool(mirrored.get(mirror_flag))
                ]
                if missing_fields:
                    mirror_field_empty.append({"meltno": meltno, "fields": missing_fields})
        old = existing.get(meltno)
        if old is None:
            summary_missing.append(meltno)
            continue
        old_samples = int(old.get("hot_metal_sample_count") or 0)
        new_samples = int(row.get("hot_metal_sample_count") or 0)
        if old_samples != new_samples:
            sample_changes.append({
                "meltno": meltno,
                "previous": old_samples,
                "current": new_samples,
                "delta": new_samples - old_samples,
            })

    limit = max(1, min(int(detail_limit), 1000))
    return {
        "mirror_audit_available": mirror is not None,
        "source_present_mirror_missing": mirror_missing[:limit],
        "source_field_mirror_empty": mirror_field_empty[:limit],
        "summary_missing": summary_missing[:limit],
        "sample_count_changes": sample_changes[:limit],
        "counts": {
            "source_present_mirror_missing": len(mirror_missing),
            "source_field_mirror_empty": len(mirror_field_empty),
            "summary_missing": len(summary_missing),
            "sample_count_changes": len(sample_changes),
        },
        "truncated": any(
            len(items) > limit
            for items in (mirror_missing, mirror_field_empty, summary_missing, sample_changes)
        ),
        "detail_limit": limit,
        "target": TABLE_NAME,
    }
