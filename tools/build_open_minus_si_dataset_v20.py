"""Build V20 open-minus mean-Si datasets from 220.12 read-only sources.

This script writes only local offline artifacts.  It reads repaired heat
quality, sensor minute values, official hourly PCI, and optionally IMES sinter
chemistry background.  It never writes 220.12 business tables.

Requirement: REQ-SI-V20-OPEN-MINUS-HITRATE-20260807.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "PT" / "预测铁水Si含量" / "src"))

import build_hot_metal_si_dataset as tunnel_builder  # noqa: E402
from si_semantic_engine.v19_context_features import (  # noqa: E402
    build_chemistry_context_features,
)
from si_semantic_engine.v20_open_minus_features import (  # noqa: E402
    DEFAULT_LEAD_MINUTES,
    DEFAULT_PCI_WINDOWS_HOURS,
    DEFAULT_SENSOR_WINDOWS_MINUTES,
    TARGET_COLUMN,
    build_history_gap_features,
    build_pci_window_features,
    expand_lead_samples,
    feature_coverage,
    merge_feature_blocks,
    parse_int_list,
    pivot_sensor_window_rows,
)


DEFAULT_OUTPUT = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V20-OPEN-MINUS-20260807"
)
DEFAULT_IMES_ENV = ROOT / "PT" / "imes_vastbase.local.env"
CORE_SENSOR_NAMES = (
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
)
CHEMISTRY_FIELD_MAP = {
    "tfe": "tfevalue",
    "feo": "feovalue",
    "sio2": "sio2value",
    "al2o3": "al2o3value",
    "cao": "caovalue",
    "mgo": "mgovalue",
    "p": "pvalue",
    "s": "svalue",
    "tio2": "tio2value",
    "mno": "mnovalue",
    "zn": "znvalue",
    "cr": "crvalue",
    "r2": "r2value",
    "mgal": "mgalvalue",
    "alsi": "alsivalue",
    "qd": "qdvalue",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def _emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, default=_json_default), flush=True)


def _ns(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        ssh_host=args.ssh_host,
        ssh_user=args.ssh_user,
        remote_pg_host=args.remote_pg_host,
        remote_pg_port=args.remote_pg_port,
        local_tunnel_port=args.local_tunnel_port,
        remote_pg_user=args.remote_pg_user,
        remote_pg_db=args.remote_pg_db,
        connect_timeout=args.connect_timeout,
    )


def _chunks(records: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(records), size):
        yield records[start : start + size]


def fetch_heat_rows(conn: psycopg.Connection[Any], args: argparse.Namespace) -> pd.DataFrame:
    """Fetch repaired heat-quality rows from the 220.12 summary table."""

    clauses = [
        "furnace_no = %s",
        "open_ts IS NOT NULL",
        "si_avg IS NOT NULL",
    ]
    params: list[Any] = [args.furnace_no]
    if args.date_from:
        clauses.append("work_date >= %s")
        params.append(args.date_from)
    if args.date_to:
        clauses.append("work_date <= %s")
        params.append(args.date_to)
    if args.meltno_from:
        clauses.append("meltno >= %s")
        params.append(args.meltno_from)
    if args.meltno_to:
        clauses.append("meltno <= %s")
        params.append(args.meltno_to)
    params.append(max(1, min(args.limit, 5000)))
    sql = f"""
        SELECT
            meltno AS official_meltno,
            furnace_no,
            work_date,
            open_ts,
            close_ts,
            source_status,
            source_updated_at,
            COALESCE(source_updated_at, close_ts, open_ts) AS label_available_ts,
            si_avg AS "target__Si_mean",
            si_median AS "target__Si_median",
            si_min AS "target__Si_min",
            si_max AS "target__Si_max",
            si_spread AS "target__Si_spread",
            hot_metal_sample_count AS "target__Si_sample_count"
        FROM bf_assistant.heat_performance_quality_summary
        WHERE {' AND '.join(clauses)}
        ORDER BY open_ts, meltno
        LIMIT %s
    """
    frame = pd.DataFrame(conn.execute(sql, params).fetchall())
    if frame.empty:
        return pd.DataFrame()
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    frame["open_ts"] = pd.to_datetime(frame["open_ts"], errors="coerce")
    frame["close_ts"] = pd.to_datetime(frame["close_ts"], errors="coerce")
    frame["label_available_ts"] = pd.to_datetime(frame["label_available_ts"], errors="coerce")
    frame[TARGET_COLUMN] = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    return frame


def fetch_pci_rate_minutes(
    conn: psycopg.Connection[Any],
    samples: pd.DataFrame,
    *,
    max_window_hours: int,
    chunk_size: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    tag_row = conn.execute(
        """
        SELECT tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE variable_name = 'PCI_rate' AND is_enabled
        LIMIT 1
        """
    ).fetchone()
    if not tag_row:
        return pd.DataFrame(columns=["official_meltno", "ts", "value"]), {
            "available": False,
            "reason": "PCI_rate tag missing",
        }
    records = (
        samples[["v20_sample_id", "official_meltno", "prediction_cutoff_ts"]]
        .dropna()
        .sort_values(["prediction_cutoff_ts", "official_meltno"])
        .to_dict("records")
    )
    rows: list[dict[str, Any]] = []
    chunks = list(_chunks(records, max(1, chunk_size)))
    for chunk_no, chunk in enumerate(chunks, 1):
        values_sql = ",".join(["(%s::text,%s::text,%s::timestamp)"] * len(chunk))
        params: list[Any] = []
        for item in chunk:
            params.extend([
                str(item["v20_sample_id"]),
                str(item["official_meltno"]),
                item["prediction_cutoff_ts"],
            ])
        params.extend([str(tag_row["tag_long_name"]), max_window_hours])
        sql = f"""
            WITH targets(v20_sample_id, official_meltno, target_ts) AS (
                VALUES {values_sql}
            )
            SELECT t.v20_sample_id, t.official_meltno, v.ts, v.value
            FROM targets AS t
            JOIN bf_sensor.one_minute_values AS v
              ON v.tag_long_name = %s
             AND v.ts >= t.target_ts - (%s * interval '1 hour')
             AND v.ts < t.target_ts
             AND v.value IS NOT NULL
            ORDER BY t.official_meltno, v.ts
        """
        rows.extend(dict(row) for row in conn.execute(sql, params).fetchall())
        _emit("v20_pci_minutes_progress", chunk=chunk_no, chunks=len(chunks), rows=len(rows))
    return pd.DataFrame(rows, columns=["v20_sample_id", "official_meltno", "ts", "value"]), {
        "available": True,
        "tag_long_name": str(tag_row["tag_long_name"]),
        "minute_rows": len(rows),
    }


def fetch_pci_window_aggregates(
    conn: psycopg.Connection[Any],
    samples: pd.DataFrame,
    *,
    windows_hours: tuple[int, ...],
    chunk_size: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch PCI window features by aggregating on PostgreSQL."""

    tag_row = conn.execute(
        """
        SELECT tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE variable_name = 'PCI_rate' AND is_enabled
        LIMIT 1
        """
    ).fetchone()
    if not tag_row:
        return pd.DataFrame(columns=["v20_sample_id", "official_meltno"]), {
            "available": False,
            "reason": "PCI_rate tag missing",
        }
    records = (
        samples[["v20_sample_id", "official_meltno", "prediction_cutoff_ts"]]
        .dropna()
        .sort_values(["prediction_cutoff_ts", "official_meltno"])
        .to_dict("records")
    )
    window_values = ",".join([f"({int(window)}::int)" for window in windows_hours])
    wide: dict[str, dict[str, Any]] = {
        str(item["v20_sample_id"]): {
            "v20_sample_id": str(item["v20_sample_id"]),
            "official_meltno": str(item["official_meltno"]),
        }
        for item in records
    }
    long_rows = 0
    chunks = list(_chunks(records, max(1, chunk_size)))
    for chunk_no, chunk in enumerate(chunks, 1):
        values_sql = ",".join(["(%s::text,%s::text,%s::timestamp)"] * len(chunk))
        params: list[Any] = []
        for item in chunk:
            params.extend([
                str(item["v20_sample_id"]),
                str(item["official_meltno"]),
                item["prediction_cutoff_ts"],
            ])
        params.append(str(tag_row["tag_long_name"]))
        sql = f"""
            WITH targets(v20_sample_id, official_meltno, target_ts) AS (
                VALUES {values_sql}
            ),
            windows(window_hours) AS (
                VALUES {window_values}
            )
            SELECT
                t.v20_sample_id,
                t.official_meltno,
                w.window_hours,
                sum(v.value)::double precision / 60.0 AS amount_t,
                avg(v.value)::double precision AS avg_tph,
                stddev_samp(v.value)::double precision AS std_tph,
                count(v.value)::double precision AS coverage_minutes,
                least(count(v.value)::double precision / (w.window_hours * 60.0), 1.0) AS coverage_ratio,
                regr_slope(v.value, extract(epoch from v.ts) / 3600.0)::double precision AS slope_tph_per_hour
            FROM targets AS t
            CROSS JOIN windows AS w
            LEFT JOIN bf_sensor.one_minute_values AS v
              ON v.tag_long_name = %s
             AND v.ts >= t.target_ts - (w.window_hours * interval '1 hour')
             AND v.ts < t.target_ts
             AND v.value IS NOT NULL
            GROUP BY t.v20_sample_id, t.official_meltno, w.window_hours
            ORDER BY t.v20_sample_id, w.window_hours
        """
        for raw in conn.execute(sql, params).fetchall():
            row = dict(raw)
            sample_id = str(row["v20_sample_id"])
            hours = int(row["window_hours"])
            prefix = f"v20_pci__{hours}h"
            for source in (
                "amount_t",
                "avg_tph",
                "std_tph",
                "coverage_minutes",
                "coverage_ratio",
                "slope_tph_per_hour",
            ):
                wide[sample_id][f"{prefix}_{source}"] = row.get(source)
            long_rows += 1
        _emit("v20_pci_window_progress", chunk=chunk_no, chunks=len(chunks), long_rows=long_rows)
    return pd.DataFrame(wide.values()), {
        "available": True,
        "tag_long_name": str(tag_row["tag_long_name"]),
        "long_rows": long_rows,
        "windows_hours": list(windows_hours),
        "method": "postgresql_window_aggregation",
    }


def fetch_official_hourly_pci(
    conn: psycopg.Connection[Any],
    samples: pd.DataFrame,
    *,
    chunk_size: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    exists = conn.execute(
        "SELECT to_regclass('bf_sensor.v_coal_injection_hourly') AS view_name"
    ).fetchone()
    if not exists or not exists["view_name"]:
        return pd.DataFrame(), {"available": False, "reason": "hourly view missing"}
    targets = samples[["v20_sample_id", "official_meltno", "prediction_cutoff_ts"]].dropna().copy()
    targets["prediction_cutoff_ts"] = pd.to_datetime(
        targets["prediction_cutoff_ts"], errors="coerce"
    )
    targets = targets.dropna(subset=["prediction_cutoff_ts"])
    if targets.empty:
        return pd.DataFrame(), {"available": False, "reason": "no valid cutoffs"}
    start_hour = targets["prediction_cutoff_ts"].min().floor("h") - pd.Timedelta(hours=1)
    end_hour = targets["prediction_cutoff_ts"].max().floor("h") + pd.Timedelta(hours=1)
    hour_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT hour_start, amount_t, amount_source, data_until_ts, coverage_ratio
            FROM bf_sensor.v_coal_injection_hourly
            WHERE hour_start >= %s
              AND hour_start <= %s
            ORDER BY hour_start
            """,
            (start_hour.to_pydatetime(), end_hour.to_pydatetime()),
        ).fetchall()
    ]
    hourly = {pd.Timestamp(row["hour_start"]).floor("h"): row for row in hour_rows}
    rows: list[dict[str, Any]] = []
    for item in targets.to_dict("records"):
        cutoff = pd.Timestamp(item["prediction_cutoff_ts"])
        hour_start = cutoff.floor("h")
        prev = hourly.get(hour_start - pd.Timedelta(hours=1), {})
        curr = hourly.get(hour_start, {})
        row: dict[str, Any] = {
            "v20_sample_id": str(item["v20_sample_id"]),
            "official_meltno": str(item["official_meltno"]),
            "v20_pci__previous_complete_hour_amount_t": prev.get("amount_t"),
            "v20_pci__previous_complete_hour_coverage_ratio": prev.get("coverage_ratio"),
            "v20_pci__previous_complete_hour_source": prev.get("amount_source"),
        }
        curr_data_until = curr.get("data_until_ts")
        if curr and curr_data_until is not None and pd.Timestamp(curr_data_until) <= cutoff:
            row["v20_pci__current_hour_amount_t"] = curr.get("amount_t")
            row["v20_pci__current_hour_coverage_ratio"] = curr.get("coverage_ratio")
            row["v20_pci__current_hour_source"] = curr.get("amount_source")
        elif curr:
            row["v20_pci__current_hour_amount_t"] = np.nan
            row["v20_pci__current_hour_coverage_ratio"] = np.nan
            row["v20_pci__current_hour_source"] = "minute_integral_required_to_avoid_future_leakage"
        rows.append(row)
    frame = pd.DataFrame(rows)
    _emit("v20_official_pci_progress", chunks=1, rows=len(frame), hourly_rows=len(hour_rows))
    coverage = 0.0
    if not frame.empty and "v20_pci__previous_complete_hour_amount_t" in frame.columns:
        coverage = float(frame["v20_pci__previous_complete_hour_amount_t"].notna().mean())
    return frame, {
        "available": True,
        "rows": len(frame),
        "hourly_rows": len(hour_rows),
        "previous_hour_coverage": coverage,
        "method": "range_read_then_local_cutoff_mapping",
    }


def fetch_sensor_windows(
    conn: psycopg.Connection[Any],
    samples: pd.DataFrame,
    *,
    windows_minutes: tuple[int, ...],
    chunk_size: int,
    sensor_names: tuple[str, ...] | None = None,
    exclude_short_name_prefixes: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    records = (
        samples[["v20_sample_id", "official_meltno", "prediction_cutoff_ts"]]
        .dropna()
        .sort_values(["prediction_cutoff_ts", "official_meltno"])
        .to_dict("records")
    )
    if not records:
        return pd.DataFrame(), {"available": False, "reason": "no samples"}
    window_values = ",".join([f"({int(window)}::int)" for window in windows_minutes])
    long_rows: list[dict[str, Any]] = []
    chunks = list(_chunks(records, max(1, chunk_size)))
    for chunk_no, chunk in enumerate(chunks, 1):
        values_sql = ",".join(["(%s::text,%s::text,%s::timestamp)"] * len(chunk))
        params: list[Any] = []
        for item in chunk:
            params.extend([
                str(item["v20_sample_id"]),
                str(item["official_meltno"]),
                item["prediction_cutoff_ts"],
            ])
        sensor_filter_clauses: list[str] = []
        if sensor_names:
            sensor_filter_clauses.append(
                """(
                    r.variable_name = ANY(%s::text[])
                 OR r.short_name = ANY(%s::text[])
                )"""
            )
            params.extend([list(sensor_names), list(sensor_names)])
        for prefix in exclude_short_name_prefixes:
            sensor_filter_clauses.append("left(r.short_name, %s) <> %s")
            params.extend([len(prefix), prefix])
        sensor_filter_sql = (
            "AND " + " AND ".join(sensor_filter_clauses)
            if sensor_filter_clauses
            else ""
        )
        sql = f"""
            WITH targets(v20_sample_id, official_meltno, target_ts) AS (
                VALUES {values_sql}
            ),
            windows(window_minutes) AS (
                VALUES {window_values}
            )
            SELECT
                t.v20_sample_id,
                t.official_meltno,
                r.short_name,
                w.window_minutes,
                avg(v.value)::double precision AS avg_value,
                stddev_samp(v.value)::double precision AS std_value,
                min(v.value)::double precision AS min_value,
                max(v.value)::double precision AS max_value,
                (array_agg(v.value ORDER BY v.ts DESC) FILTER (WHERE v.value IS NOT NULL))[1]::double precision AS last_value,
                count(v.value)::double precision AS coverage_minutes,
                least(count(v.value)::double precision / w.window_minutes::double precision, 1.0) AS coverage_ratio,
                regr_slope(v.value, extract(epoch from v.ts) / 3600.0)::double precision AS slope_per_hour
            FROM targets AS t
            CROSS JOIN windows AS w
            CROSS JOIN bf_sensor.sensor_registry AS r
            LEFT JOIN bf_sensor.one_minute_values AS v
              ON v.tag_long_name = r.tag_long_name
             AND v.ts >= t.target_ts - (w.window_minutes * interval '1 minute')
             AND v.ts < t.target_ts
             AND v.value IS NOT NULL
            WHERE r.is_enabled
              AND NOT r.is_derived
              {sensor_filter_sql}
            GROUP BY t.v20_sample_id, t.official_meltno, r.short_name, w.window_minutes
            ORDER BY t.official_meltno, r.short_name, w.window_minutes
        """
        long_rows.extend(dict(row) for row in conn.execute(sql, params).fetchall())
        _emit(
            "v20_sensor_window_progress",
            chunk=chunk_no,
            chunks=len(chunks),
            long_rows=len(long_rows),
        )
    long_frame = pd.DataFrame(long_rows)
    wide = pivot_sensor_window_rows(long_frame, samples, windows_minutes=windows_minutes)
    return wide, {
        "available": True,
        "sample_rows": len(samples),
        "long_rows": len(long_rows),
        "wide_columns": max(len(wide.columns) - 1, 0),
        "windows_minutes": list(windows_minutes),
        "sensor_names": list(sensor_names or ()),
        "excluded_short_name_prefixes": list(exclude_short_name_prefixes),
        "sensor_name_scope": "filtered" if sensor_names else "all_enabled_non_derived",
    }


def load_sensor_window_cache(
    path: Path,
    samples: pd.DataFrame,
    *,
    windows_minutes: tuple[int, ...],
    sensor_name_scope: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load a local pre-aggregated sensor-window cache.

    The cache is a wide CSV generated by ``tools/build_v20_sensor_window_cache.py``.
    It preserves the V20 leakage contract because every feature is keyed by
    ``v20_sample_id`` and was computed against that sample's cutoff timestamp.
    """

    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"sensor window cache not found: {resolved}")
    frame = pd.read_csv(resolved, low_memory=False)
    if "official_meltno" not in frame.columns:
        raise ValueError("sensor window cache must include official_meltno")
    sample_ids = set()
    if "v20_sample_id" in samples.columns:
        sample_ids = set(samples["v20_sample_id"].dropna().astype(str))
    use_sample_id = bool(sample_ids) and "v20_sample_id" in frame.columns
    key_columns = ["v20_sample_id"] if use_sample_id else ["official_meltno"]
    feature_columns = [
        column for column in frame.columns if str(column).startswith("v20_sensor__")
    ]
    if not feature_columns:
        raise ValueError(f"sensor window cache has no v20_sensor__ feature columns: {resolved}")
    forbidden = [
        column
        for column in frame.columns
        if str(column).startswith(("target__", "actual__", "prediction__", "error__"))
    ]
    if forbidden:
        raise ValueError(f"sensor window cache contains forbidden columns: {forbidden[:5]}")

    selected_columns = list(dict.fromkeys([*key_columns, "official_meltno", *feature_columns]))
    prepared = frame[selected_columns].copy()
    prepared["official_meltno"] = prepared["official_meltno"].astype(str)
    if use_sample_id:
        prepared["v20_sample_id"] = prepared["v20_sample_id"].astype(str)
        before_rows = len(prepared)
        prepared = prepared.loc[prepared["v20_sample_id"].isin(sample_ids)].copy()
        missing_samples = int(len(sample_ids - set(prepared["v20_sample_id"].astype(str))))
        unused_rows = int(before_rows - len(prepared))
    else:
        heat_ids = set(samples["official_meltno"].dropna().astype(str))
        before_rows = len(prepared)
        prepared = prepared.loc[prepared["official_meltno"].isin(heat_ids)].copy()
        missing_samples = int(len(heat_ids - set(prepared["official_meltno"].astype(str))))
        unused_rows = int(before_rows - len(prepared))

    duplicate_rows = int(prepared.duplicated(subset=key_columns).sum())
    if duplicate_rows:
        raise ValueError(
            f"sensor window cache has duplicate rows for {key_columns}: {duplicate_rows}"
        )
    for column in feature_columns:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    coverage_columns = [
        column for column in feature_columns if column.endswith("_coverage_ratio")
    ]
    coverage = float(prepared[coverage_columns].notna().mean().mean()) if coverage_columns else np.nan
    return prepared, {
        "available": True,
        "method": "local_preaggregated_sensor_window_cache",
        "path": str(resolved),
        "sample_rows": int(len(samples)),
        "cache_rows": int(len(frame)),
        "matched_rows": int(len(prepared)),
        "missing_samples_or_heats": missing_samples,
        "unused_cache_rows": unused_rows,
        "wide_columns": int(len(feature_columns)),
        "windows_minutes": list(windows_minutes),
        "sensor_name_scope": sensor_name_scope,
        "merge_key": key_columns,
        "coverage_ratio_column_mean_notna": coverage,
        "leakage_contract": "[prediction_cutoff_ts - window, prediction_cutoff_ts)",
    }


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def fetch_chemistry_context(
    samples: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    env = read_env_file(args.imes_env_file.resolve())
    user = env.get("IMES_DB_USER")
    password = env.get("IMES_DB_PASSWORD")
    database = env.get("IMES_DB_NAME", "vastbase")
    if not user or not password:
        return pd.DataFrame(), {
            "available": False,
            "reason": "IMES credentials missing; chemistry skipped",
            "lineage_confidence": 0.0,
        }
    cutoffs = pd.to_datetime(samples["prediction_cutoff_ts"], errors="coerce").dropna()
    if cutoffs.empty:
        return pd.DataFrame(), {"available": False, "reason": "no cutoffs"}
    start_ts = cutoffs.min() - pd.Timedelta(hours=max(72, args.chemistry_lookback_hours))
    end_ts = cutoffs.max()
    select_fields = ", ".join(
        f"NULLIF(trim({source}), '') AS {target}"
        for target, source in CHEMISTRY_FIELD_MAP.items()
    )
    sql = f"""
        SELECT
            "发布时间" AS published_ts,
            "加工中心编码" AS machine,
            {select_fields}
        FROM public.v_qpes_sinter_machine_sample_insp_final
        WHERE "发布时间" >= %s
          AND "发布时间" < %s
          AND "加工中心编码" IN ('JS1', 'JS2')
        ORDER BY "发布时间"
    """
    try:
        with psycopg.connect(
            host=args.imes_host,
            port=args.imes_port,
            dbname=database,
            user=user,
            password=password,
            connect_timeout=15,
            options="-c statement_timeout=30000",
            row_factory=dict_row,
        ) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            rows = [dict(row) for row in conn.execute(sql, (start_ts, end_ts)).fetchall()]
    except Exception as exc:
        if args.chemistry_required:
            raise
        return pd.DataFrame(), {
            "available": False,
            "reason": f"chemistry query failed: {type(exc).__name__}",
            "lineage_confidence": 0.0,
        }
    chemistry = pd.DataFrame(rows)
    if chemistry.empty:
        context = build_chemistry_context_features(samples, pd.DataFrame(columns=["published_ts", "machine", *CHEMISTRY_FIELD_MAP]))
    else:
        for column in CHEMISTRY_FIELD_MAP:
            chemistry[column] = pd.to_numeric(chemistry[column], errors="coerce")
        context = build_chemistry_context_features(samples, chemistry)
    return context, {
        "available": True,
        "source": "public.v_qpes_sinter_machine_sample_insp_final",
        "raw_rows": len(chemistry),
        "lineage_confidence": 0.0,
        "boundary": "sinter chemistry is time-background only; no batch-bin-charge-heat lineage is implied",
    }


def add_protocol_features(frame: pd.DataFrame, leads: tuple[int, ...]) -> pd.DataFrame:
    output = frame.copy()
    output["v20_protocol__lead_minutes"] = pd.to_numeric(
        output["lead_minutes"], errors="coerce"
    )
    for lead in leads:
        output[f"v20_protocol__is_lead_{lead}m"] = (
            output["v20_protocol__lead_minutes"].eq(float(lead)).astype(float)
        )
    return output


def write_artifacts(
    dataset: pd.DataFrame,
    args: argparse.Namespace,
    audit: dict[str, Any],
) -> dict[str, str]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "v20_open_minus_dataset.csv"
    labels_path = output_dir / "v20_open_minus_labels.csv"
    contract_path = output_dir / "v20_data_contract.json"
    leakage_path = output_dir / "v20_leakage_audit.json"
    dataset.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    label_columns = [
        column
        for column in (
            "v20_sample_id",
            "official_meltno",
            "furnace_no",
            "work_date",
            "open_ts",
            "close_ts",
            "lead_minutes",
            "prediction_cutoff_ts",
            "label_available_ts",
            TARGET_COLUMN,
            "target__Si_median",
            "target__Si_min",
            "target__Si_max",
            "target__Si_spread",
            "target__Si_sample_count",
            "source_status",
        )
        if column in dataset.columns
    ]
    dataset[label_columns].to_csv(labels_path, index=False, encoding="utf-8-sig")
    target_like = {
        "official_meltno",
        "v20_sample_id",
        "furnace_no",
        "work_date",
        "open_ts",
        "close_ts",
        "source_status",
        "source_updated_at",
        "label_available_ts",
        "lead_minutes",
        "prediction_cutoff_ts",
        TARGET_COLUMN,
        "target__Si_median",
        "target__Si_min",
        "target__Si_max",
        "target__Si_spread",
        "target__Si_sample_count",
    }
    feature_columns = [
        column
        for column in dataset.columns
        if column not in target_like and not column.startswith("target__")
    ]
    coverage = feature_coverage(dataset, feature_columns)
    contract = {
        "schema": "bf.si.v20.open_minus_dataset.v1",
        "requirement_id": "REQ-SI-V20-OPEN-MINUS-HITRATE-20260807",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "read_policy": "readonly_remote_22012_and_optional_readonly_imes",
        "write_policy": "local_artifacts_only",
        "target": {
            "column": TARGET_COLUMN,
            "definition": "arithmetic mean of valid hot-metal Si samples per heat from bf_assistant.heat_performance_quality_summary.si_avg",
        },
        "prediction_protocol": {
            "sample_cutoff": "open_ts - lead_minutes",
            "main_lead_minutes": 60,
            "lead_minutes": sorted(dataset["lead_minutes"].dropna().astype(int).unique().tolist()),
        },
        "feature_count": len(feature_columns),
        "rows": len(dataset),
        "feature_coverage": coverage,
        "lineage_boundaries": {
            "history_si": "published earlier heat labels only",
            "pci": "strictly before cutoff; no zero imputation",
            "sensors": "strictly before cutoff; SQL window is [cutoff-window, cutoff)",
            "chemistry": "low confidence time background only until batch-bin-charge-heat lineage is verified",
        },
    }
    leakage = {
        "schema": "bf.si.v20.leakage_audit.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_heat_target_columns_excluded_from_feature_list": True,
        "history_visibility_rule": "prior open_ts < target open_ts AND label_available_ts <= prediction_cutoff_ts",
        "sensor_window_rule": "[prediction_cutoff_ts - window, prediction_cutoff_ts)",
        "pci_window_rule": "[prediction_cutoff_ts - window, prediction_cutoff_ts)",
        "official_current_hour_pci_rule": "accepted only when data_until_ts <= prediction_cutoff_ts",
        "audit": audit,
    }
    contract_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    leakage_path.write_text(
        json.dumps(leakage, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return {
        "dataset": str(dataset_path),
        "labels": str(labels_path),
        "contract": str(contract_path),
        "leakage_audit": str(leakage_path),
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Build V20 open-minus mean-Si dataset.")
    cli.add_argument("--date-from")
    cli.add_argument("--date-to")
    cli.add_argument("--meltno-from")
    cli.add_argument("--meltno-to")
    cli.add_argument("--furnace-no", default="2")
    cli.add_argument("--limit", type=int, default=2500)
    cli.add_argument(
        "--lead-minutes-list",
        default=",".join(str(item) for item in DEFAULT_LEAD_MINUTES),
        help="Comma-separated lead times; default 120,90,60,30,15,0.",
    )
    cli.add_argument(
        "--sensor-windows-minutes",
        default=",".join(str(item) for item in DEFAULT_SENSOR_WINDOWS_MINUTES),
        help="Comma-separated sensor windows; default includes 360/480/720.",
    )
    cli.add_argument(
        "--pci-windows-hours",
        default=",".join(str(item) for item in DEFAULT_PCI_WINDOWS_HOURS),
    )
    cli.add_argument("--skip-sensor-windows", action="store_true")
    cli.add_argument(
        "--sensor-name-scope",
        choices=("all", "process133", "core28"),
        default="core28",
        help=(
            "Sensor registry filter. core28 is the safe default after the V21 full-context "
            "rollback; process133 excludes EQ_* quality/equipment tags; all keeps the "
            "historical all-enabled behavior for explicit offline research only."
        ),
    )
    cli.add_argument("--skip-chemistry", action="store_true")
    cli.add_argument("--chemistry-required", action="store_true")
    cli.add_argument("--chemistry-lookback-hours", type=int, default=72)
    cli.add_argument("--imes-host", default="10.30.220.12")
    cli.add_argument("--imes-port", type=int, default=15433)
    cli.add_argument("--imes-env-file", type=Path, default=DEFAULT_IMES_ENV)
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15445)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    cli.add_argument("--connect-timeout", type=int, default=20)
    cli.add_argument("--statement-timeout-ms", type=int, default=180000)
    cli.add_argument("--chunk-size", type=int, default=20)
    cli.add_argument("--sensor-chunk-size", type=int, default=5)
    cli.add_argument(
        "--sensor-window-cache",
        type=Path,
        help=(
            "Optional local wide CSV generated by tools/build_v20_sensor_window_cache.py. "
            "When provided, the builder merges this cache instead of running the heavy "
            "database-side sample x window x sensor aggregation."
        ),
    )
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return cli


def run(args: argparse.Namespace) -> dict[str, Any]:
    lead_minutes = parse_int_list(args.lead_minutes_list, default=DEFAULT_LEAD_MINUTES)
    sensor_windows = parse_int_list(
        args.sensor_windows_minutes, default=DEFAULT_SENSOR_WINDOWS_MINUTES
    )
    pci_windows = parse_int_list(args.pci_windows_hours, default=DEFAULT_PCI_WINDOWS_HOURS)
    audit: dict[str, Any] = {
        "lead_minutes": list(lead_minutes),
        "sensor_windows_minutes": list(sensor_windows),
        "pci_windows_hours": list(pci_windows),
    }
    ns = _ns(args)
    with tunnel_builder.sensor_ssh_tunnel(ns) as (port, client):
        params = tunnel_builder.remote_sensor_params(ns, port, client)
        params["options"] = (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={int(args.statement_timeout_ms)}"
        )
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            heat_rows = fetch_heat_rows(conn, args)
            if heat_rows.empty:
                raise RuntimeError("No heat-quality rows matched the V20 query")
            _emit("v20_heat_rows_ready", rows=len(heat_rows))
            samples = expand_lead_samples(heat_rows, lead_minutes)
            _emit("v20_lead_samples_ready", rows=len(samples))
            history = build_history_gap_features(samples, heat_rows)
            _emit("v20_history_features_ready", columns=max(len(history.columns) - 1, 0))
            pci, pci_window_audit = fetch_pci_window_aggregates(
                conn,
                samples,
                windows_hours=pci_windows,
                chunk_size=args.chunk_size,
            )
            official_pci, official_pci_audit = fetch_official_hourly_pci(
                conn,
                samples,
                chunk_size=args.chunk_size,
            )
            pci = merge_feature_blocks(pci, official_pci)
            audit["pci_windows"] = pci_window_audit
            audit["official_pci"] = official_pci_audit
            if args.sensor_window_cache:
                sensor, sensor_audit = load_sensor_window_cache(
                    args.sensor_window_cache,
                    samples,
                    windows_minutes=sensor_windows,
                    sensor_name_scope=args.sensor_name_scope,
                )
                audit["sensor_windows"] = sensor_audit
            elif args.skip_sensor_windows:
                sensor = pd.DataFrame({"official_meltno": samples["official_meltno"].astype(str)})
                audit["sensor_windows"] = {"available": False, "reason": "--skip-sensor-windows"}
            else:
                sensor_names = CORE_SENSOR_NAMES if args.sensor_name_scope == "core28" else None
                exclude_prefixes = ("EQ_",) if args.sensor_name_scope == "process133" else ()
                sensor, sensor_audit = fetch_sensor_windows(
                    conn,
                    samples,
                    windows_minutes=sensor_windows,
                    chunk_size=args.sensor_chunk_size,
                    sensor_names=sensor_names,
                    exclude_short_name_prefixes=exclude_prefixes,
                )
                sensor_audit["sensor_name_scope"] = args.sensor_name_scope
                audit["sensor_windows"] = sensor_audit
    if args.skip_chemistry:
        chemistry = pd.DataFrame({"official_meltno": samples["official_meltno"].astype(str)})
        audit["chemistry"] = {"available": False, "reason": "--skip-chemistry"}
    else:
        chemistry, chemistry_audit = fetch_chemistry_context(samples, args)
        audit["chemistry"] = chemistry_audit
    dataset = merge_feature_blocks(
        samples,
        history,
        pci,
        sensor,
        chemistry,
    )
    dataset = add_protocol_features(dataset, lead_minutes)
    paths = write_artifacts(dataset, args, audit)
    return {"ok": True, "rows": len(dataset), "heats": int(len(heat_rows)), **paths}


def main() -> int:
    args = parser().parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
