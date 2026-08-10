"""Build local pre-aggregated sensor-window caches for V20/V21 Si experiments.

The original V20 dataset builder can aggregate sensor windows directly in
PostgreSQL, but the query shape is intentionally exhaustive
``sample x window x sensor``.  That is useful for correctness, yet very heavy
for 133 enabled tags and long 360/480/720 minute windows.

This script keeps the same leakage boundary, reads minute values from 220.12 in
read-only mode, and computes the window aggregates locally into a wide CSV
cache.  The V20 dataset builder can then merge the cache by ``v20_sample_id``.

Requirement: REQ-SI-V21-SENSOR-CACHE-20260808.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "PT" / "预测铁水Si含量" / "src"))

import build_hot_metal_si_dataset as tunnel_builder  # noqa: E402
from build_open_minus_si_dataset_v20 import (  # noqa: E402
    CORE_SENSOR_NAMES,
    _ns,
    fetch_heat_rows,
)
from si_semantic_engine.v20_open_minus_features import (  # noqa: E402
    DEFAULT_LEAD_MINUTES,
    DEFAULT_SENSOR_WINDOWS_MINUTES,
    expand_lead_samples,
    parse_int_list,
)


DEFAULT_OUTPUT = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V21-SENSOR-CACHE-20260808"
    / "cache"
)
STATS = (
    "mean",
    "std",
    "min",
    "max",
    "last",
    "delta",
    "coverage_minutes",
    "coverage_ratio",
    "slope_per_hour",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def _emit(event: str, **payload: Any) -> None:
    print(
        json.dumps({"event": event, **payload}, ensure_ascii=False, default=_json_default),
        flush=True,
    )


def _safe_feature_token(value: str) -> str:
    return (
        str(value)
        .strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("%", "pct")
    )


def _timestamp_ns(values: pd.Series) -> np.ndarray:
    timestamps = pd.to_datetime(values, errors="coerce").dt.tz_localize(None)
    return timestamps.astype("datetime64[ns]").astype(np.int64).to_numpy()


def _prefix(values: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(values, dtype=float)])


def _range_sum(prefix: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    return prefix[end] - prefix[start]


def _build_sparse_table(values: np.ndarray, *, op: str) -> list[np.ndarray]:
    if len(values) == 0:
        return []
    if op == "min":
        reducer = np.minimum
    elif op == "max":
        reducer = np.maximum
    else:
        raise ValueError(f"unsupported sparse-table op: {op}")
    table = [values.astype(float, copy=False)]
    span = 1
    while span * 2 <= len(values):
        previous = table[-1]
        table.append(reducer(previous[:-span], previous[span:]))
        span *= 2
    return table


def _range_sparse_query(
    table: list[np.ndarray],
    start: np.ndarray,
    end: np.ndarray,
    *,
    op: str,
) -> np.ndarray:
    out = np.full(len(start), np.nan, dtype=float)
    lengths = end - start
    valid = lengths > 0
    if not valid.any() or not table:
        return out
    log2 = np.floor(np.log2(lengths[valid])).astype(int)
    valid_positions = np.flatnonzero(valid)
    for level in np.unique(log2):
        mask = log2 == level
        rows = valid_positions[mask]
        span = 1 << int(level)
        left = table[int(level)][start[rows]]
        right = table[int(level)][end[rows] - span]
        if op == "min":
            out[rows] = np.minimum(left, right)
        elif op == "max":
            out[rows] = np.maximum(left, right)
        else:
            raise ValueError(f"unsupported sparse-table op: {op}")
    return out


def compute_sensor_feature_block(
    samples: pd.DataFrame,
    sensor_values: pd.DataFrame,
    *,
    short_name: str,
    windows_minutes: tuple[int, ...],
) -> pd.DataFrame:
    """Compute leakage-safe sensor windows for one sensor into wide columns.

    Window contract: for a sample cutoff ``T0`` and a window ``W``, only minute
    values with ``T0-W <= ts < T0`` are visible.  No zero filling is used; empty
    windows keep numeric aggregates missing and coverage at zero.
    """

    sample_count = len(samples)
    prefix = f"v20_sensor__{_safe_feature_token(short_name)}"
    block: dict[str, np.ndarray] = {}
    for window in windows_minutes:
        for stat in STATS:
            column = f"{prefix}__{int(window)}m_{stat}"
            if stat in {"coverage_minutes", "coverage_ratio"}:
                block[column] = np.zeros(sample_count, dtype=float)
            else:
                block[column] = np.full(sample_count, np.nan, dtype=float)
    if sample_count == 0:
        return pd.DataFrame(block)

    values = sensor_values.copy()
    if values.empty:
        return pd.DataFrame(block)
    values["ts"] = pd.to_datetime(values["ts"], errors="coerce")
    values["value"] = pd.to_numeric(values["value"], errors="coerce")
    values = values.dropna(subset=["ts", "value"]).sort_values("ts", kind="stable")
    values = values.loc[np.isfinite(values["value"].to_numpy(dtype=float))].copy()
    if values.empty:
        return pd.DataFrame(block)

    ts_ns = _timestamp_ns(values["ts"])
    y = values["value"].astype(float).to_numpy()
    order = np.argsort(ts_ns, kind="stable")
    ts_ns = ts_ns[order]
    y = y[order]
    duplicate_mask = np.concatenate([[True], ts_ns[1:] != ts_ns[:-1]])
    ts_ns = ts_ns[duplicate_mask]
    y = y[duplicate_mask]
    if len(y) == 0:
        return pd.DataFrame(block)

    x_hours = ts_ns.astype(float) / 3_600_000_000_000.0
    sum_y = _prefix(y)
    sum_y2 = _prefix(y * y)
    sum_x = _prefix(x_hours)
    sum_x2 = _prefix(x_hours * x_hours)
    sum_xy = _prefix(x_hours * y)
    min_table = _build_sparse_table(y, op="min")
    max_table = _build_sparse_table(y, op="max")

    cutoff_ns = _timestamp_ns(samples["prediction_cutoff_ts"])
    for window in windows_minutes:
        window_ns = int(window) * 60_000_000_000
        start = np.searchsorted(ts_ns, cutoff_ns - window_ns, side="left")
        end = np.searchsorted(ts_ns, cutoff_ns, side="left")
        count = (end - start).astype(float)
        valid = count > 0
        prefix_name = f"{prefix}__{int(window)}m"

        coverage_minutes = count
        coverage_ratio = np.minimum(count / float(max(int(window), 1)), 1.0)
        block[f"{prefix_name}_coverage_minutes"] = coverage_minutes
        block[f"{prefix_name}_coverage_ratio"] = coverage_ratio
        if not valid.any():
            continue

        sy = _range_sum(sum_y, start, end)
        sy2 = _range_sum(sum_y2, start, end)
        sx = _range_sum(sum_x, start, end)
        sx2 = _range_sum(sum_x2, start, end)
        sxy = _range_sum(sum_xy, start, end)

        mean = np.full(sample_count, np.nan, dtype=float)
        mean[valid] = sy[valid] / count[valid]
        block[f"{prefix_name}_mean"] = mean

        std = np.full(sample_count, np.nan, dtype=float)
        multi = count > 1
        if multi.any():
            numerator = sy2[multi] - (sy[multi] * sy[multi] / count[multi])
            variance = numerator / (count[multi] - 1.0)
            std[multi] = np.sqrt(np.maximum(variance, 0.0))
        block[f"{prefix_name}_std"] = std

        block[f"{prefix_name}_min"] = _range_sparse_query(
            min_table,
            start,
            end,
            op="min",
        )
        block[f"{prefix_name}_max"] = _range_sparse_query(
            max_table,
            start,
            end,
            op="max",
        )

        last = np.full(sample_count, np.nan, dtype=float)
        first = np.full(sample_count, np.nan, dtype=float)
        valid_rows = np.flatnonzero(valid)
        last[valid_rows] = y[end[valid_rows] - 1]
        first[valid_rows] = y[start[valid_rows]]
        block[f"{prefix_name}_last"] = last
        block[f"{prefix_name}_delta"] = last - first

        slope = np.full(sample_count, np.nan, dtype=float)
        denom = count * sx2 - sx * sx
        slope_valid = (count >= 2) & (np.abs(denom) > 0)
        if slope_valid.any():
            slope[slope_valid] = (
                count[slope_valid] * sxy[slope_valid]
                - sx[slope_valid] * sy[slope_valid]
            ) / denom[slope_valid]
        block[f"{prefix_name}_slope_per_hour"] = slope
    return pd.DataFrame(block)


def fetch_sensor_registry(
    conn: psycopg.Connection[Any],
    *,
    sensor_name_scope: str,
) -> pd.DataFrame:
    params: list[Any] = []
    filter_sql = ""
    if sensor_name_scope == "core28":
        filter_sql = """
          AND (
                r.variable_name = ANY(%s::text[])
             OR r.short_name = ANY(%s::text[])
          )
        """
        params.extend([list(CORE_SENSOR_NAMES), list(CORE_SENSOR_NAMES)])
    elif sensor_name_scope == "process133":
        filter_sql = """
          AND left(r.short_name, 3) <> 'EQ_'
        """
    sql = f"""
        SELECT
            r.short_name,
            r.variable_name,
            r.tag_long_name,
            r.chinese_name
        FROM bf_sensor.sensor_registry AS r
        WHERE r.is_enabled
          AND NOT r.is_derived
          {filter_sql}
        ORDER BY r.short_name, r.tag_long_name
    """
    frame = pd.DataFrame(conn.execute(sql, params).fetchall())
    if frame.empty:
        return frame
    frame["short_name"] = frame["short_name"].astype(str)
    frame["tag_long_name"] = frame["tag_long_name"].astype(str)
    frame = frame.drop_duplicates(subset=["short_name"], keep="first")
    return frame.reset_index(drop=True)


def fetch_one_sensor_values(
    conn: psycopg.Connection[Any],
    *,
    tag_long_name: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> pd.DataFrame:
    sql = """
        SELECT v.ts, v.value::double precision AS value
        FROM bf_sensor.one_minute_values AS v
        WHERE v.tag_long_name = %s
          AND v.ts >= %s
          AND v.ts < %s
          AND v.value IS NOT NULL
        ORDER BY v.ts
    """
    return pd.DataFrame(conn.execute(sql, [tag_long_name, start_ts, end_ts]).fetchall())


def build_sensor_window_cache(
    conn: psycopg.Connection[Any],
    samples: pd.DataFrame,
    *,
    windows_minutes: tuple[int, ...],
    sensor_name_scope: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    samples = samples.copy()
    samples["v20_sample_id"] = samples["v20_sample_id"].astype(str)
    samples["official_meltno"] = samples["official_meltno"].astype(str)
    samples["prediction_cutoff_ts"] = pd.to_datetime(
        samples["prediction_cutoff_ts"], errors="coerce"
    )
    samples = samples.dropna(subset=["prediction_cutoff_ts"]).reset_index(drop=True)
    if samples.empty:
        raise RuntimeError("no V20 samples available for sensor cache")

    registry = fetch_sensor_registry(conn, sensor_name_scope=sensor_name_scope)
    if registry.empty:
        raise RuntimeError(f"no sensor registry rows matched scope={sensor_name_scope!r}")

    max_window = max(int(item) for item in windows_minutes)
    min_cutoff = pd.Timestamp(samples["prediction_cutoff_ts"].min())
    max_cutoff = pd.Timestamp(samples["prediction_cutoff_ts"].max())
    range_start = min_cutoff - pd.Timedelta(minutes=max_window)
    range_end = max_cutoff
    _emit(
        "v21_sensor_cache_scope_ready",
        samples=len(samples),
        sensors=len(registry),
        windows=list(windows_minutes),
        range_start=range_start,
        range_end=range_end,
        sensor_name_scope=sensor_name_scope,
    )

    base = samples[["official_meltno", "v20_sample_id"]].copy()
    blocks: list[pd.DataFrame] = [base]
    sensor_audit: list[dict[str, Any]] = []
    for index, sensor in registry.iterrows():
        short_name = str(sensor["short_name"])
        tag_long_name = str(sensor["tag_long_name"])
        values = fetch_one_sensor_values(
            conn,
            tag_long_name=tag_long_name,
            start_ts=range_start,
            end_ts=range_end,
        )
        block = compute_sensor_feature_block(
            samples,
            values,
            short_name=short_name,
            windows_minutes=windows_minutes,
        )
        blocks.append(block)
        non_empty_coverage = [
            column
            for column in block.columns
            if column.endswith("_coverage_minutes")
            and pd.to_numeric(block[column], errors="coerce").fillna(0).gt(0).any()
        ]
        sensor_audit.append(
            {
                "short_name": short_name,
                "variable_name": sensor.get("variable_name"),
                "tag_long_name": tag_long_name,
                "raw_rows": int(len(values)),
                "feature_columns": int(len(block.columns)),
                "has_any_coverage": bool(non_empty_coverage),
            }
        )
        _emit(
            "v21_sensor_cache_sensor_done",
            sensor_index=int(index) + 1,
            sensors=int(len(registry)),
            short_name=short_name,
            raw_rows=int(len(values)),
            feature_columns=int(len(block.columns)),
        )
    wide = pd.concat(blocks, axis=1)
    audit = {
        "schema": "bf.si.v21.sensor_window_cache.v1",
        "requirement_id": "REQ-SI-V21-SENSOR-CACHE-20260808",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "read_one_sensor_then_local_prefix_aggregate",
        "leakage_contract": "[prediction_cutoff_ts - window, prediction_cutoff_ts)",
        "source": "220.12 bf_sensor.sensor_registry + bf_sensor.one_minute_values read-only",
        "sensor_name_scope": sensor_name_scope,
        "samples": int(len(samples)),
        "heats": int(samples["official_meltno"].nunique()),
        "sensors": int(len(registry)),
        "windows_minutes": list(windows_minutes),
        "range_start": range_start,
        "range_end": range_end,
        "feature_columns": int(max(len(wide.columns) - 2, 0)),
        "stats": list(STATS),
        "sensor_audit": sensor_audit,
    }
    return wide, audit


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Build V20/V21 pre-aggregated sensor-window cache.")
    cli.add_argument("--date-from")
    cli.add_argument("--date-to")
    cli.add_argument("--meltno-from")
    cli.add_argument("--meltno-to")
    cli.add_argument("--furnace-no", default="2")
    cli.add_argument("--limit", type=int, default=3000)
    cli.add_argument(
        "--lead-minutes-list",
        default="60",
        help="Comma-separated lead times to cache. Default only builds open-minus 60min.",
    )
    cli.add_argument(
        "--sensor-windows-minutes",
        default=",".join(str(item) for item in DEFAULT_SENSOR_WINDOWS_MINUTES),
    )
    cli.add_argument(
        "--sensor-name-scope",
        choices=("all", "process133", "core28"),
        default="core28",
        help=(
            "core28 caches the fixed 28 process variables; process133 excludes EQ_* "
            "quality/equipment tags; all caches every enabled non-derived tag."
        ),
    )
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15448)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    cli.add_argument("--connect-timeout", type=int, default=20)
    cli.add_argument("--statement-timeout-ms", type=int, default=300000)
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return cli


def run(args: argparse.Namespace) -> dict[str, Any]:
    lead_minutes = parse_int_list(args.lead_minutes_list, default=DEFAULT_LEAD_MINUTES)
    windows_minutes = parse_int_list(
        args.sensor_windows_minutes,
        default=DEFAULT_SENSOR_WINDOWS_MINUTES,
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ns = _ns(args)
    with tunnel_builder.sensor_ssh_tunnel(ns) as (port, client):
        params = tunnel_builder.remote_sensor_params(ns, port, client)
        params["options"] = (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={int(args.statement_timeout_ms)}"
        )
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            heats = fetch_heat_rows(conn, args)
            if heats.empty:
                raise RuntimeError("No heat-quality rows matched the cache query")
            samples = expand_lead_samples(heats, lead_minutes)
            cache, audit = build_sensor_window_cache(
                conn,
                samples,
                windows_minutes=windows_minutes,
                sensor_name_scope=args.sensor_name_scope,
            )
    stem = (
        f"v21_sensor_window_cache_{args.sensor_name_scope}_"
        f"lead{'-'.join(str(item) for item in lead_minutes)}"
    )
    csv_path = output_dir / f"{stem}.csv"
    audit_path = output_dir / f"{stem}.audit.json"
    cache.to_csv(csv_path, index=False, encoding="utf-8-sig")
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "cache_csv": str(csv_path),
        "audit_json": str(audit_path),
        "rows": int(len(cache)),
        "feature_columns": int(max(len(cache.columns) - 2, 0)),
        "sensors": int(audit["sensors"]),
        "windows_minutes": list(windows_minutes),
        "lead_minutes": list(lead_minutes),
    }


def main() -> int:
    args = parser().parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
