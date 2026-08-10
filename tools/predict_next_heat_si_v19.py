"""One-command V19 mean-Si prediction for a specified GL02 heat.

The command is read-only against 220.12 PostgreSQL and writes only local
offline artifacts.  It generalizes the earlier heat-92 replay script:

* ``--target-meltno`` predicts that official heat;
* ``--previous-meltno`` infers the next heat number and predicts it using the
  previous heat close time as the cutoff unless ``--cutoff-ts`` is supplied;
* if the target heat already has a published average Si, the output includes
  actual value and error; otherwise it emits prediction and empirical range
  only.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

import joblib
import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "PT" / "预测铁水Si含量" / "src"))

import build_formal_si_dataset_v3 as formal_builder  # noqa: E402
import build_hot_metal_si_dataset as tunnel_builder  # noqa: E402
from si_semantic_engine.extract_v4_temporal_stats import (  # noqa: E402
    _derive_statistics,
    build_statistics_query,
)
from si_semantic_engine.formal_dataset import canonicalize_history_features  # noqa: E402
from si_semantic_engine.prospective import _available_history_for_predictions  # noqa: E402
from si_semantic_engine.train_v6 import _history_baseline  # noqa: E402
from si_semantic_engine.v10_features import (  # noqa: E402
    derive_lag_band_neurons,
    derive_spatial_field_modes,
)
from si_semantic_engine.v13_features import derive_lag_moment_neurons  # noqa: E402
from si_semantic_engine.v19_context_features import (  # noqa: E402
    build_mean_si_history_context,
    build_pci_context_features,
    merge_v19_context_features,
)
from si_semantic_engine.v20_open_minus_features import (  # noqa: E402
    build_history_gap_features as build_v20_history_gap_features,
    build_pci_window_features as build_v20_pci_window_features,
    merge_feature_blocks as merge_v20_feature_blocks,
)
from si_semantic_engine.v4_features import build_v4_feature_blocks  # noqa: E402
from si_semantic_engine.v5_features import (  # noqa: E402
    derive_temporal_spatial_neurons,
    pivot_temporal_statistics,
)
from si_semantic_engine.v6_features import (  # noqa: E402
    CHEMISTRY_COLUMNS,
    attach_published_chemistry_history,
    derive_heat_state_neurons,
    derive_multiscale_neurons,
)


MODEL = ROOT / "PT/预测铁水Si含量/reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/selected_v19_august_holdout.joblib"
CATALOG = ROOT / "PT/高炉3D模型/docs/GL02传感器点位清单.v1.json"
EMPIRICAL = ROOT / "PT/预测铁水Si含量/reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/predictions_pci.csv"
DEFAULT_OUT = ROOT / "PT/预测铁水Si含量/reports/live_predictions"
MELTNO_RE = re.compile(r"^(?P<furnace>\d+)#(?P<date>\d{8})-(?P<seq>\d{3})$")
DEFAULT_WINDOWS_MINUTES = (30, 60, 120, 240, 360, 480, 720)


def _ns(port: int) -> argparse.Namespace:
    return argparse.Namespace(
        ssh_host="10.30.220.12",
        ssh_user="administrator",
        remote_pg_host="127.0.0.1",
        remote_pg_port=5432,
        local_tunnel_port=port,
        remote_pg_user="gl02_sync",
        remote_pg_db="bf_trend",
        connect_timeout=20,
    )


def infer_next_meltno(previous_meltno: str) -> str:
    match = MELTNO_RE.fullmatch(previous_meltno.strip())
    if not match:
        raise ValueError(f"无法从炉号推断下一炉：{previous_meltno!r}")
    return (
        f"{match.group('furnace')}#{match.group('date')}-"
        f"{int(match.group('seq')) + 1:03d}"
    )


def _parse_timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    result = pd.to_datetime(value, errors="raise")
    return pd.Timestamp(result).tz_localize(None)


def _fetch_heat(conn: psycopg.Connection[Any], meltno: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT meltno AS official_meltno, furnace_no, work_date, open_ts, close_ts,
               raw_open_ts, raw_close_ts, repaired_open_ts, repaired_close_ts,
               source_status, source_updated_at,
               si_avg AS target__Si_mean, si_median AS target__Si_median,
               si_min AS target__Si_min, si_max AS target__Si_max,
               si_spread AS target__Si_spread,
               hot_metal_sample_count AS target__Si_sample_count
        FROM bf_assistant.heat_performance_quality_summary
        WHERE meltno = %s
        """,
        (meltno,),
    ).fetchone()
    return _canonical_columns(dict(row)) if row else None


def _canonical_columns(row: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "target__si_mean": "target__Si_mean",
        "target__si_median": "target__Si_median",
        "target__si_min": "target__Si_min",
        "target__si_max": "target__Si_max",
        "target__si_spread": "target__Si_spread",
        "target__si_sample_count": "target__Si_sample_count",
    }
    for old, new in aliases.items():
        if old in row and new not in row:
            row[new] = row.pop(old)
    return row


def _fetch_history(
    conn: psycopg.Connection[Any],
    *,
    furnace_no: str,
    cutoff: pd.Timestamp,
    limit: int,
) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT meltno AS official_meltno, furnace_no, open_ts, close_ts,
               source_status, source_updated_at,
               si_avg AS target__Si_mean, si_median AS target__Si_median,
               si_min AS target__Si_min, si_max AS target__Si_max,
               si_spread AS target__Si_spread,
               hot_metal_sample_count AS target__Si_sample_count
        FROM bf_assistant.heat_performance_quality_summary
        WHERE furnace_no = %s
          AND open_ts IS NOT NULL
          AND open_ts <= %s
        ORDER BY open_ts DESC, meltno DESC
        LIMIT %s
        """,
        (furnace_no, cutoff.to_pydatetime(), limit),
    ).fetchall()
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"截止 {cutoff} 前没有可用炉次历史")
    frame = frame.rename(
        columns={
            "target__si_mean": "target__Si_mean",
            "target__si_median": "target__Si_median",
            "target__si_min": "target__Si_min",
            "target__si_max": "target__Si_max",
            "target__si_spread": "target__Si_spread",
            "target__si_sample_count": "target__Si_sample_count",
        }
    )
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    frame["prediction_cutoff_ts"] = pd.to_datetime(frame["open_ts"], errors="coerce")
    frame["label_available_ts"] = pd.to_datetime(frame["source_updated_at"], errors="coerce")
    frame["target__Si_representative"] = pd.to_numeric(
        frame["target__Si_mean"], errors="coerce"
    )
    frame["furnace_no"] = frame["furnace_no"].astype(str)
    return frame.sort_values(["prediction_cutoff_ts", "official_meltno"]).reset_index(drop=True)


def _target_row(
    *,
    target_meltno: str,
    furnace_no: str,
    cutoff: pd.Timestamp,
    existing: dict[str, Any] | None,
) -> pd.DataFrame:
    base: dict[str, Any] = {
        "v20_sample_id": f"{target_meltno}__live",
        "official_meltno": target_meltno,
        "furnace_no": furnace_no,
        "work_date": pd.NaT,
        "open_ts": cutoff,
        "close_ts": pd.NaT,
        "source_status": None,
        "source_updated_at": pd.NaT,
        "prediction_cutoff_ts": cutoff,
        "label_available_ts": pd.NaT,
        "target__Si_mean": np.nan,
        "target__Si_median": np.nan,
        "target__Si_min": np.nan,
        "target__Si_max": np.nan,
        "target__Si_spread": np.nan,
        "target__Si_sample_count": np.nan,
        "target__Si_representative": np.nan,
    }
    if existing:
        for key in list(base):
            if key in existing and existing[key] is not None:
                base[key] = existing[key]
        base["official_meltno"] = target_meltno
        base["prediction_cutoff_ts"] = cutoff
        base["label_available_ts"] = existing.get("source_updated_at")
        base["target__Si_representative"] = base.get("target__Si_mean")
    return pd.DataFrame([base])


def _choose_cutoff(
    *,
    conn: psycopg.Connection[Any],
    target_meltno: str,
    previous_meltno: str | None,
    cutoff_ts: pd.Timestamp | None,
    mode: str,
    target: dict[str, Any] | None,
) -> pd.Timestamp:
    if cutoff_ts is not None:
        return cutoff_ts
    if mode == "target-open":
        if not target or not target.get("open_ts"):
            raise RuntimeError("--mode target-open 要求目标炉次已在汇总表中存在 open_ts")
        return pd.Timestamp(target["open_ts"])
    if not previous_meltno:
        if target and target.get("open_ts"):
            return pd.Timestamp(target["open_ts"])
        raise RuntimeError("未提供 --previous-meltno 或 --cutoff-ts，且目标炉无 open_ts")
    previous = _fetch_heat(conn, previous_meltno)
    if not previous:
        raise RuntimeError(f"找不到截止炉次/上一炉：{previous_meltno}")
    for key in ("close_ts", "open_ts", "source_updated_at"):
        value = previous.get(key)
        if value:
            return pd.Timestamp(value)
    raise RuntimeError(f"上一炉 {previous_meltno} 没有可用截止时间")


def _build_frame(
    conn: psycopg.Connection[Any],
    *,
    target_row: pd.DataFrame,
    context_rows: pd.DataFrame,
    cutoff: pd.Timestamp,
    windows_minutes: tuple[int, ...],
    include_v20: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    target_meltno = str(target_row["official_meltno"].iloc[0])
    registry = conn.execute(
        """
        SELECT variable_name, short_name, tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE is_enabled AND NOT is_derived
        ORDER BY short_name
        """
    ).fetchall()
    base = formal_builder.fetch_temporal_sensor_features(
        conn,
        target_row[["official_meltno", "prediction_cutoff_ts"]],
        registry,
        max_lag_minutes=10,
        chunk_size=1,
    )
    base["prediction_cutoff_ts"] = cutoff
    base["prediction_month"] = str(cutoff.to_period("M"))
    base["experiment_split"] = "live_one_click"
    base["furnace_no"] = str(target_row["furnace_no"].iloc[0])
    base = base.merge(
        _available_history_for_predictions(base, context_rows),
        on="official_meltno",
        how="left",
        validate="one_to_one",
    )

    stats_sql = build_statistics_query(1, windows_minutes=windows_minutes)
    stats = pd.DataFrame(conn.execute(stats_sql, [target_meltno, cutoff]).fetchall())
    stats = _derive_statistics(stats, windows_minutes=windows_minutes)
    temporal, temporal_audit = pivot_temporal_statistics(
        stats,
        target_row[["official_meltno", "prediction_cutoff_ts"]],
        windows_minutes=windows_minutes,
    )
    v4_blocks, v4_audit = build_v4_feature_blocks(base, context_rows, CATALOG)
    samples = pd.DataFrame(
        columns=["official_meltno", "open_ts", "result_ts", *CHEMISTRY_COLUMNS]
    )
    chemistry, chemistry_audit = attach_published_chemistry_history(base, samples)
    combined = pd.concat(
        [
            base,
            *v4_blocks.values(),
            temporal,
            derive_temporal_spatial_neurons(temporal, windows_minutes=windows_minutes),
            derive_multiscale_neurons(temporal),
            derive_heat_state_neurons(temporal),
            chemistry,
            derive_lag_band_neurons(temporal),
            derive_spatial_field_modes(temporal),
            derive_lag_moment_neurons(temporal),
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)
    combined = canonicalize_history_features(combined)
    history = build_mean_si_history_context(context_rows)
    rate_row = conn.execute(
        """
        SELECT tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE variable_name = 'PCI_rate' AND is_enabled
        LIMIT 1
        """
    ).fetchone()
    if not rate_row:
        rates = pd.DataFrame(columns=["official_meltno", "ts", "value"])
    else:
        rates = pd.DataFrame(
            conn.execute(
                """
                SELECT %s::text AS official_meltno, ts, value
                FROM bf_sensor.one_minute_values
                WHERE tag_long_name = %s
                  AND ts >= %s - interval '12 hours'
                  AND ts < %s
                ORDER BY ts
                """,
                (target_meltno, rate_row["tag_long_name"], cutoff.to_pydatetime(), cutoff.to_pydatetime()),
            ).fetchall()
        )
        if rates.empty:
            rates = pd.DataFrame(columns=["official_meltno", "ts", "value"])
    official_pci = fetch_pci_official_context(conn, target_meltno, cutoff)
    pci = build_pci_context_features(
        target_row[["official_meltno", "prediction_cutoff_ts"]],
        rates,
        official_pci,
    )
    combined = merge_v19_context_features(combined, history, pci)
    v20_audit: dict[str, Any] = {"enabled": include_v20}
    if include_v20:
        v20_target_columns = [
            column
            for column in (
                "official_meltno",
                "v20_sample_id",
                "furnace_no",
                "work_date",
                "open_ts",
                "close_ts",
                "prediction_cutoff_ts",
                "label_available_ts",
                "target__Si_mean",
            )
            if column in target_row.columns
        ]
        v20_context_columns = [
            column
            for column in (
                "official_meltno",
                "furnace_no",
                "work_date",
                "open_ts",
                "close_ts",
                "prediction_cutoff_ts",
                "label_available_ts",
                "target__Si_mean",
            )
            if column in context_rows.columns
        ]
        v20_samples = target_row[v20_target_columns].copy()
        v20_heats = context_rows[v20_context_columns].copy()
        v20_history = build_v20_history_gap_features(v20_samples, v20_heats)
        v20_pci = build_v20_pci_window_features(v20_samples, rates)
        try:
            from build_open_minus_si_dataset_v20 import fetch_sensor_windows

            v20_sensor, v20_sensor_audit = fetch_sensor_windows(
                conn,
                v20_samples,
                windows_minutes=windows_minutes,
                chunk_size=1,
            )
        except Exception as exc:
            v20_sensor = pd.DataFrame({"official_meltno": v20_samples["official_meltno"].astype(str)})
            v20_sensor_audit = {
                "available": False,
                "reason": f"single-heat sensor window fetch failed: {type(exc).__name__}",
            }
        combined = merge_v20_feature_blocks(combined, v20_history, v20_pci, v20_sensor)
        combined["v20_protocol__lead_minutes"] = np.nan
        if target_row.get("open_ts") is not None and pd.notna(target_row["open_ts"].iloc[0]):
            combined["v20_protocol__lead_minutes"] = (
                pd.Timestamp(target_row["open_ts"].iloc[0]) - cutoff
            ).total_seconds() / 60.0
        v20_audit = {
            "enabled": True,
            "history": v20_history.to_dict("records"),
            "pci_window_columns": max(len(v20_pci.columns) - 1, 0),
            "sensor_windows": v20_sensor_audit,
        }
    audit = {
        "cutoff": str(cutoff),
        "history": history.loc[
            history["official_meltno"].eq(target_meltno)
        ].to_dict("records"),
        "pci": pci.to_dict("records"),
        "temporal": temporal_audit,
        "v4": v4_audit,
        "chemistry": chemistry_audit,
        "raw_sensor_points": int(len(registry)),
        "windows_minutes": list(windows_minutes),
        "pci_official": official_pci.to_dict("records"),
        "v20": v20_audit,
    }
    return combined, audit


def _load_model_bundle(model_path: Path) -> dict[str, Any]:
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict):
        raise RuntimeError(f"模型文件不是可识别的bundle: {model_path}")
    return bundle


def _is_v20_bundle(bundle: dict[str, Any]) -> bool:
    return str(bundle.get("schema", "")).startswith("bf.si.v20.")


def _predict(frame: pd.DataFrame, model_path: Path, bundle: dict[str, Any] | None = None) -> dict[str, float]:
    bundle = bundle or _load_model_bundle(model_path)
    if _is_v20_bundle(bundle):
        features = list(bundle.get("feature_columns", []))
        if not features:
            raise RuntimeError("V20模型bundle缺少feature_columns")
        fill_values = {
            str(key): float(value)
            for key, value in dict(bundle.get("fill_values", {})).items()
        }
        matrix = frame.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
        fill = pd.Series({column: fill_values.get(column, 0.0) for column in features})
        matrix = matrix.fillna(fill)
        value = float(bundle["model"].predict(matrix)[0])
        history_value = np.nan
        if "history_mean__Si_lag_1" in matrix.columns:
            history_value = float(matrix["history_mean__Si_lag_1"].iloc[0])
        return {
            "v20_selected": value,
            "history": history_value,
            "prediction": value,
        }
    for key in ("direct_features", "thermal_features", "lgbm_features"):
        missing = sorted(set(bundle[key]) - set(frame.columns))
        if missing:
            raise RuntimeError(f"模型特征缺失 {key}: {missing[:12]}")
    baseline = _history_baseline(frame, fallback=bundle["fallback"]).to_numpy(float)
    lgbm7 = (
        bundle["lgbm_models"]["lgbm_huber7"].predict(frame[bundle["lgbm_features"]])
        + baseline
    )
    lgbm15 = (
        bundle["lgbm_models"]["lgbm_huber15_decay90"].predict(frame[bundle["lgbm_features"]])
        + baseline
    )
    direct = bundle["direct_model"].predict(frame[bundle["direct_features"]])
    thermal = bundle["thermal_model"].predict(frame[bundle["thermal_features"]]) + baseline
    components = {
        "direct": float(direct[0]),
        "thermal_xgb": float(thermal[0]),
        "lgbm_huber7": float(lgbm7[0]),
        "lgbm_huber15_decay90": float(lgbm15[0]),
        "history": float(baseline[0]),
    }
    point = sum(float(bundle["weights"][key]) * value for key, value in components.items())
    return {**components, "prediction": float(point)}


def _empirical_interval(point: float, bundle: dict[str, Any] | None = None) -> dict[str, float | str]:
    if bundle and _is_v20_bundle(bundle):
        quantiles = dict(bundle.get("residual_quantiles", {}))
        if {"q10", "q90"} <= set(quantiles):
            return {
                "p10": float(point + float(quantiles.get("q10", 0.0))),
                "p50": float(point + float(quantiles.get("q50", 0.0))),
                "p90": float(point + float(quantiles.get("q90", 0.0))),
                "method": "V20 validation residual empirical 10%-90%; offline shadow interval",
            }
    empirical = pd.read_csv(EMPIRICAL)
    residual = (
        pd.to_numeric(empirical["actual__Si_mean"], errors="coerce")
        - pd.to_numeric(empirical["prediction__selected"], errors="coerce")
    ).dropna()
    return {
        "p10": float(point + residual.quantile(0.10)),
        "p50": float(point),
        "p90": float(point + residual.quantile(0.90)),
        "method": "August V19 PCI holdout residual empirical 10%-90%; not a native probabilistic head",
    }


def fetch_pci_official_context(
    conn: psycopg.Connection[Any],
    target_meltno: str,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Fetch leakage-safe official PCI current/previous hour context.

    The previous completed clock hour can use ``v_coal_injection_hourly``'s
    official/meter-preferred amount.  The current clock hour is accepted from
    the hourly view only if the stored row is known to be truncated at or
    before the prediction cutoff; otherwise ``build_pci_context_features``
    falls back to strict minute-level PCI_rate integration.
    """

    exists = conn.execute(
        "SELECT to_regclass('bf_sensor.v_coal_injection_hourly') AS view_name"
    ).fetchone()
    audit: dict[str, Any] = {
        "official_meltno": target_meltno,
        "pci_current_hour": np.nan,
        "pci_previous_hour": np.nan,
        "pci_current_hour_source": None,
        "pci_previous_hour_source": None,
    }
    if not exists or not exists["view_name"]:
        audit["pci_current_hour_source"] = "hourly_view_missing"
        audit["pci_previous_hour_source"] = "hourly_view_missing"
        return pd.DataFrame([audit])
    hour_start = cutoff.floor("h")
    rows = conn.execute(
        """
        SELECT hour_start, amount_t, amount_source, data_until_ts, coverage_ratio,
               hour_complete, metered_amount_t, integrated_amount_t
        FROM bf_sensor.v_coal_injection_hourly
        WHERE hour_start IN (%s, %s)
        ORDER BY hour_start
        """,
        (
            (hour_start - pd.Timedelta(hours=1)).to_pydatetime(),
            hour_start.to_pydatetime(),
        ),
    ).fetchall()
    for item in rows:
        item_hour = pd.Timestamp(item["hour_start"])
        amount = item.get("amount_t")
        data_until = item.get("data_until_ts")
        if item_hour == hour_start - pd.Timedelta(hours=1):
            if amount is not None:
                audit["pci_previous_hour"] = float(amount)
                audit["pci_previous_hour_source"] = item.get("amount_source")
        elif item_hour == hour_start:
            if amount is not None and data_until is not None and pd.Timestamp(data_until) <= cutoff:
                audit["pci_current_hour"] = float(amount)
                audit["pci_current_hour_source"] = item.get("amount_source")
            else:
                audit["pci_current_hour_source"] = (
                    "minute_integral_fallback_to_avoid_future_leakage"
                )
    return pd.DataFrame([audit])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Predict one heat average Si from 220.12 repaired heat-quality and sensor data."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target-meltno", help="Official target heat, e.g. 2#20260807-094")
    group.add_argument("--previous-meltno", help="Last known heat; target is inferred as next sequence")
    parser.add_argument("--cutoff-meltno", help="Use this heat's close/open time as prediction cutoff")
    parser.add_argument("--cutoff-ts", help="Explicit prediction cutoff timestamp")
    parser.add_argument(
        "--mode",
        choices=("previous-close", "target-open"),
        default="previous-close",
        help="Default cutoff rule when --cutoff-ts is omitted.",
    )
    parser.add_argument("--history-limit", type=int, default=40)
    parser.add_argument(
        "--windows-minutes",
        default=",".join(str(value) for value in DEFAULT_WINDOWS_MINUTES),
        help="Comma-separated temporal windows; default includes 360/480/720 for burden-to-hot-metal delay.",
    )
    parser.add_argument("--local-tunnel-port", type=int, default=15439)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    model_path = args.model.resolve()
    windows_minutes = tuple(
        sorted({int(item.strip()) for item in str(args.windows_minutes).split(",") if item.strip()})
    )
    if not windows_minutes:
        raise SystemExit("--windows-minutes cannot be empty")
    target_meltno = args.target_meltno or infer_next_meltno(args.previous_meltno)
    cutoff_ts = _parse_timestamp(args.cutoff_ts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_bundle = _load_model_bundle(model_path)
    include_v20 = _is_v20_bundle(model_bundle)
    ns = _ns(args.local_tunnel_port)
    with tunnel_builder.sensor_ssh_tunnel(ns) as (port, client):
        params = tunnel_builder.remote_sensor_params(ns, port, client)
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=120000"
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            target = _fetch_heat(conn, target_meltno)
            previous_meltno = args.cutoff_meltno or args.previous_meltno
            cutoff = _choose_cutoff(
                conn=conn,
                target_meltno=target_meltno,
                previous_meltno=previous_meltno,
                cutoff_ts=cutoff_ts,
                mode=args.mode,
                target=target,
            )
            furnace_no = (
                str(target.get("furnace_no"))
                if target and target.get("furnace_no")
                else target_meltno.split("#", 1)[0]
            )
            history = _fetch_history(
                conn,
                furnace_no=furnace_no,
                cutoff=cutoff,
                limit=max(8, min(args.history_limit, 200)),
            )
            target_frame = _target_row(
                target_meltno=target_meltno,
                furnace_no=furnace_no,
                cutoff=cutoff,
                existing=target,
            )
            context_rows = pd.concat([history, target_frame], ignore_index=True)
            context_rows = context_rows.drop_duplicates(
                subset=["official_meltno"], keep="last"
            ).sort_values(["prediction_cutoff_ts", "official_meltno"], kind="stable")
            frame, audit = _build_frame(
                conn,
                target_row=target_frame,
                context_rows=context_rows,
                cutoff=cutoff,
                windows_minutes=windows_minutes,
                include_v20=include_v20,
            )

    prediction = _predict(frame, model_path, model_bundle)
    interval = _empirical_interval(prediction["prediction"], model_bundle)
    actual = None
    if target and target.get("target__Si_mean") is not None:
        actual = float(target["target__Si_mean"])
    result: dict[str, Any] = {
        "schema": "bf.si.v20.one_click_prediction.v1" if include_v20 else "bf.si.v19.one_click_prediction.v1",
        "target_meltno": target_meltno,
        "previous_meltno": args.previous_meltno,
        "cutoff_meltno": args.cutoff_meltno,
        "prediction_cutoff_ts": str(cutoff),
        "cutoff_rule": "explicit --cutoff-ts" if cutoff_ts is not None else args.mode,
        "model_path": str(model_path),
        "model_schema": str(model_bundle.get("schema", "unknown")),
        "model_name": str(model_bundle.get("model_name", "v19_blend")),
        "prediction": prediction,
        "prediction_interval": interval,
        "probability_max_value_proxy": prediction["prediction"],
        "actual_si_mean": actual,
        "absolute_error": abs(prediction["prediction"] - actual) if actual is not None else None,
        "signed_error": prediction["prediction"] - actual if actual is not None else None,
        "target_source_status": target.get("source_status") if target else None,
        "target_open_ts_effective": str(target.get("open_ts")) if target and target.get("open_ts") else None,
        "target_close_ts_effective": str(target.get("close_ts")) if target and target.get("close_ts") else None,
        "target_raw_open_ts": str(target.get("raw_open_ts")) if target and target.get("raw_open_ts") else None,
        "target_raw_close_ts": str(target.get("raw_close_ts")) if target and target.get("raw_close_ts") else None,
        "target_repaired_open_ts": str(target.get("repaired_open_ts")) if target and target.get("repaired_open_ts") else None,
        "target_repaired_close_ts": str(target.get("repaired_close_ts")) if target and target.get("repaired_close_ts") else None,
        "audit": audit,
    }
    safe = re.sub(r"[^0-9A-Za-z#_-]+", "_", target_meltno)
    output_path = args.output_dir / f"{safe}_{'v20' if include_v20 else 'v19'}_prediction.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps({**result, "output_path": str(output_path)}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
