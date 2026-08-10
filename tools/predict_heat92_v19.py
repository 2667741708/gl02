"""Offline V19 prediction for the current 220.12 heat-92 case.

The script is read-only against 220.12 and writes only local offline artifacts.
It supports a strict pre-open cutoff and a retrospective cutoff that includes
the previous heat's published Si result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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
from si_semantic_engine.train_v6 import _history_baseline  # noqa: E402
from si_semantic_engine.v19_context_features import (  # noqa: E402
    build_mean_si_history_context,
    build_pci_context_features,
    merge_v19_context_features,
)
from si_semantic_engine.v4_features import build_v4_feature_blocks  # noqa: E402
from si_semantic_engine.v5_features import (  # noqa: E402
    derive_temporal_spatial_neurons,
    pivot_temporal_statistics,
)
from si_semantic_engine.v6_features import (  # noqa: E402
    attach_published_chemistry_history,
    derive_heat_state_neurons,
    derive_multiscale_neurons,
)
from si_semantic_engine.v10_features import (  # noqa: E402
    derive_lag_band_neurons,
    derive_spatial_field_modes,
)
from si_semantic_engine.v13_features import derive_lag_moment_neurons  # noqa: E402
from si_semantic_engine.v6_features import CHEMISTRY_COLUMNS  # noqa: E402


MODEL = ROOT / "PT/预测铁水Si含量/reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/selected_v19_august_holdout.joblib"
CATALOG = ROOT / "PT/高炉3D模型/docs/GL02传感器点位清单.v1.json"
OUT = ROOT / "PT/预测铁水Si含量/reports/experiments/EXP-SI-V19-HEAT92-20260807"
EMPIRICAL = ROOT / "PT/预测铁水Si含量/reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807/predictions_pci.csv"


def _ns(port: int) -> argparse.Namespace:
    return argparse.Namespace(
        ssh_host="10.30.220.12", ssh_user="administrator", remote_pg_host="127.0.0.1",
        remote_pg_port=5432, local_tunnel_port=port, remote_pg_user="gl02_sync",
        remote_pg_db="bf_trend", connect_timeout=20,
    )


def _targets(conn: psycopg.Connection[Any]) -> pd.DataFrame:
    rows = conn.execute("""
        SELECT meltno AS official_meltno, furnace_no, open_ts, source_updated_at,
               si_avg AS target__Si_mean, si_median AS target__Si_median,
               si_min AS target__Si_min, si_max AS target__Si_max,
               si_spread AS target__Si_spread, hot_metal_sample_count AS target__Si_sample_count
        FROM bf_assistant.heat_performance_quality_summary
        WHERE furnace_no='2' AND open_ts IS NOT NULL
          AND open_ts <= timestamp '2026-08-07 02:25:00'
        ORDER BY open_ts DESC LIMIT 8
    """).fetchall()
    frame = pd.DataFrame(rows)
    frame["official_meltno"] = frame["official_meltno"].astype(str)
    frame["prediction_cutoff_ts"] = pd.to_datetime(frame["open_ts"])
    frame["label_available_ts"] = pd.to_datetime(frame["source_updated_at"])
    frame["furnace_no"] = frame["furnace_no"].astype(str)
    frame = frame.sort_values("prediction_cutoff_ts").reset_index(drop=True)
    return frame


def _build_frame(conn: psycopg.Connection[Any], targets: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, Any]]:
    target = targets.loc[targets["official_meltno"].eq("2#20260807-092")].iloc[0].copy()
    target["prediction_cutoff_ts"] = cutoff
    target_row = pd.DataFrame([target])
    registry = conn.execute("SELECT variable_name,short_name,tag_long_name FROM bf_sensor.sensor_registry WHERE is_enabled AND NOT is_derived ORDER BY short_name").fetchall()
    base = formal_builder.fetch_temporal_sensor_features(
        conn, target_row[["official_meltno", "prediction_cutoff_ts"]], registry,
        max_lag_minutes=10, chunk_size=1,
    )
    base["prediction_cutoff_ts"] = cutoff
    base["prediction_month"] = cutoff.to_period("M").astype(str)
    base["experiment_split"] = "replay"
    base["furnace_no"] = "2"

    stats_sql = build_statistics_query(1, windows_minutes=(30, 60, 120, 240))
    stats = pd.DataFrame(conn.execute(stats_sql, [str(target["official_meltno"]), cutoff]).fetchall())
    stats = _derive_statistics(stats, windows_minutes=(30, 60, 120, 240))
    temporal, temporal_audit = pivot_temporal_statistics(
        stats, target_row[["official_meltno", "prediction_cutoff_ts"]], windows_minutes=(30, 60, 120, 240)
    )
    v4_blocks, v4_audit = build_v4_feature_blocks(base, targets, CATALOG)
    samples = pd.DataFrame(columns=["official_meltno", "open_ts", "result_ts", *CHEMISTRY_COLUMNS])
    chemistry, chemistry_audit = attach_published_chemistry_history(base, samples)
    combined = pd.concat([
        base, *v4_blocks.values(), temporal,
        derive_temporal_spatial_neurons(temporal, windows_minutes=(30, 60, 120, 240)),
        derive_multiscale_neurons(temporal), derive_heat_state_neurons(temporal), chemistry,
        derive_lag_band_neurons(temporal), derive_spatial_field_modes(temporal),
        derive_lag_moment_neurons(temporal),
    ], axis=1).replace([np.inf, -np.inf], np.nan)
    history = build_mean_si_history_context(pd.concat([targets, target_row], ignore_index=True))
    rate_tag = conn.execute("SELECT tag_long_name FROM bf_sensor.sensor_registry WHERE variable_name='PCI_rate' AND is_enabled LIMIT 1").fetchone()[0]
    rates = pd.DataFrame(conn.execute("SELECT %s::text AS official_meltno,ts,value FROM bf_sensor.one_minute_values WHERE tag_long_name=%s AND ts >= %s - interval '3 hours' AND ts < %s ORDER BY ts", (str(target["official_meltno"]), rate_tag, cutoff, cutoff)).fetchall())
    pci = build_pci_context_features(target_row[["official_meltno", "prediction_cutoff_ts"]], rates)
    combined = merge_v19_context_features(combined, history, pci)
    audit = {"cutoff": str(cutoff), "history": history.to_dict("records"), "pci": pci.to_dict("records"), "temporal": temporal_audit, "v4": v4_audit, "chemistry": chemistry_audit, "raw_sensor_points": int(len(registry))}
    return combined, audit


def _predict(frame: pd.DataFrame) -> dict[str, float]:
    bundle = joblib.load(MODEL)
    for key in ("direct_features", "thermal_features", "lgbm_features"):
        missing = sorted(set(bundle[key]) - set(frame.columns))
        if missing:
            raise RuntimeError(f"模型特征缺失 {key}: {missing[:8]}")
    baseline = _history_baseline(frame, fallback=bundle["fallback"]).to_numpy(float)
    lgbm7 = bundle["lgbm_models"]["lgbm_huber7"].predict(frame[bundle["lgbm_features"]]) + baseline
    lgbm15 = bundle["lgbm_models"]["lgbm_huber15_decay90"].predict(frame[bundle["lgbm_features"]]) + baseline
    direct = bundle["direct_model"].predict(frame[bundle["direct_features"]])
    thermal = bundle["thermal_model"].predict(frame[bundle["thermal_features"]]) + baseline
    components = {"direct": float(direct[0]), "thermal_xgb": float(thermal[0]), "lgbm_huber7": float(lgbm7[0]), "lgbm_huber15_decay90": float(lgbm15[0]), "history": float(baseline[0])}
    point = sum(float(bundle["weights"][k]) * v for k, v in components.items())
    return {**components, "prediction": float(point)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("strict", "include91"), default="include91")
    p.add_argument("--output-dir", type=Path, default=OUT)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tunnel_builder.sensor_ssh_tunnel(_ns(15437)) as (port, client):
        params = tunnel_builder.remote_sensor_params(_ns(15437), port, client)
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=120000"
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            targets = _targets(conn)
            target = targets.loc[targets["official_meltno"].eq("2#20260807-092")].iloc[0]
            strict_cutoff = pd.Timestamp(target["prediction_cutoff_ts"])
            include_cutoff = pd.Timestamp("2026-08-07 02:45:39")
            cutoff = strict_cutoff if args.mode == "strict" else include_cutoff
            frame, audit = _build_frame(conn, targets, cutoff)
    prediction = _predict(frame)
    empirical = pd.read_csv(EMPIRICAL)
    residual = pd.to_numeric(empirical["actual__Si_mean"], errors="coerce") - pd.to_numeric(empirical["prediction__selected"], errors="coerce")
    residual = residual.dropna()
    p10 = prediction["prediction"] + float(residual.quantile(0.10))
    p90 = prediction["prediction"] + float(residual.quantile(0.90))
    actual = float(targets.loc[targets["official_meltno"].eq("2#20260807-092"), "target__Si_mean"].iloc[0])
    result = {"mode": args.mode, "official_meltno": "2#20260807-092", "prediction_cutoff_ts": str(cutoff), "actual_si_mean": actual, "prediction": prediction, "empirical_p10": float(p10), "empirical_p90": float(p90), "probability_max_value_proxy": prediction["prediction"], "absolute_error": abs(prediction["prediction"] - actual), "signed_error": prediction["prediction"] - actual, "interval_method": "August V19 PCI holdout residual empirical 10%-90%; not a native probabilistic head", "input_history": audit["history"], "pci": audit["pci"], "target_label_available_ts": str(targets.loc[targets["official_meltno"].eq("2#20260807-092"), "label_available_ts"].iloc[0])}
    (args.output_dir / f"heat92_{args.mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
