from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from backtest_chronos2_from_pg import post_json
from run_chronos_sparse_prepredict import SPARSE_COVARIATES


ROOT = Path(__file__).resolve().parents[1]
TARGET_IDS = list(SPARSE_COVARIATES)
CORE_CANDIDATES = [
    "P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "GasUtil", "TFT", "T_blast", "T_top_A", "T_top_B", "T_top_C", "T_top_D",
    "Q_blast", "P_blast_cold", "P_blast", "O2_rate", "Q_O2", "PI",
    "DP_upper", "DP_lower", "DP_total", "L", "L_south", "L_north",
    "PCI_rate", "PCI_set", "T_taphole_1", "T_taphole_2", "T_top",
]
RAW_CORE_IDS = [item for item in CORE_CANDIDATES if item != "T_top"]
LAGS = (0, 5, 10, 20, 30, 60, 120)
FEATURE_VARIANTS = {
    "target_only": "main_select_target_only",
    "expert_sparse": "main_select_expert_sparse",
    "auto_selected": "main_select_auto_selected",
}
FEATURE_TO_VARIANT = {value: key for key, value in FEATURE_VARIANTS.items()}


def load_core_frame(conn_params: dict[str, Any], start: datetime, end: datetime) -> pd.DataFrame:
    query = """
        SELECT r.variable_name, v.ts, v.value
        FROM bf_sensor.sensor_registry AS r
        JOIN bf_sensor.one_minute_values AS v ON v.tag_long_name = r.tag_long_name
        WHERE r.variable_name = ANY(%s)
          AND v.ts >= %s
          AND v.ts <= %s
        ORDER BY v.ts, r.variable_name
    """
    with psycopg.connect(**conn_params) as conn:
        rows = conn.execute(query, (RAW_CORE_IDS, start, end)).fetchall()
    values = pd.DataFrame(rows, columns=["variable_name", "ts", "value"])
    if values.empty:
        return pd.DataFrame()
    frame = values.pivot_table(index="ts", columns="variable_name", values="value", aggfunc="last").sort_index()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    top_columns = [item for item in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if item in frame]
    frame["T_top"] = frame[top_columns].mean(axis=1)
    return frame


def baseline_stats(conn_params: dict[str, Any], cutoff: pd.Timestamp, baseline_days: int) -> dict[str, dict[str, float]]:
    query = """
        WITH raw_values AS (
            SELECT r.variable_name, v.ts, v.value
            FROM bf_sensor.sensor_registry AS r
            JOIN bf_sensor.one_minute_values AS v ON v.tag_long_name = r.tag_long_name
            WHERE r.variable_name = ANY(%s)
              AND v.ts > %s
              AND v.ts <= %s
              AND v.value IS NOT NULL
        ), top_values AS (
            SELECT 'T_top'::text AS variable_name, ts, AVG(value) AS value
            FROM raw_values
            WHERE variable_name = ANY(%s)
            GROUP BY ts
        ), all_values AS (
            SELECT variable_name, ts, value FROM raw_values
            UNION ALL
            SELECT variable_name, ts, value FROM top_values
        )
        SELECT variable_name,
               percentile_cont(0.25) WITHIN GROUP (ORDER BY value) AS q1,
               percentile_cont(0.50) WITHIN GROUP (ORDER BY value) AS q2,
               percentile_cont(0.75) WITHIN GROUP (ORDER BY value) AS q3,
               (array_agg(value ORDER BY ts DESC))[1] AS last_value,
               COUNT(*) AS sample_count
        FROM all_values
        WHERE variable_name = ANY(%s)
        GROUP BY variable_name
    """
    start = cutoff.to_pydatetime() - timedelta(days=baseline_days)
    top_ids = ["T_top_A", "T_top_B", "T_top_C", "T_top_D"]
    with psycopg.connect(**conn_params) as conn:
        rows = conn.execute(query, (RAW_CORE_IDS, start, cutoff.to_pydatetime(), top_ids, TARGET_IDS)).fetchall()
    return {
        str(variable_name): {
            "q1": float(q1),
            "q2": float(q2),
            "q3": float(q3),
            "last_value": float(last_value),
            "sample_count": int(sample_count),
        }
        for variable_name, q1, q2, q3, last_value, sample_count in rows
    }


def paired_arrays(left: pd.Series, right: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    left_values = pd.to_numeric(left, errors="coerce").to_numpy(dtype=float)
    right_values = pd.to_numeric(right, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(left_values) & np.isfinite(right_values)
    return left_values[valid], right_values[valid]


def pearson_arrays(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 90 or np.unique(left).size < 5 or np.unique(right).size < 5:
        return float("nan")
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = float(np.sqrt(np.dot(left_centered, left_centered) * np.dot(right_centered, right_centered)))
    if denominator <= 1e-15:
        return float("nan")
    return float(np.dot(left_centered, right_centered) / denominator)


def pair_correlations(left: pd.Series, right: pd.Series) -> tuple[float, float, np.ndarray, np.ndarray]:
    left_values, right_values = paired_arrays(left, right)
    pearson = pearson_arrays(left_values, right_values)
    if not math.isfinite(pearson):
        return float("nan"), float("nan"), left_values, right_values
    left_ranks = pd.Series(left_values).rank(method="average").to_numpy(dtype=float)
    right_ranks = pd.Series(right_values).rank(method="average").to_numpy(dtype=float)
    spearman = pearson_arrays(left_ranks, right_ranks)
    return pearson, spearman, left_values, right_values


def candidate_score(
    context: pd.DataFrame,
    target_id: str,
    candidate_id: str,
    expert_ids: set[str],
) -> dict[str, Any] | None:
    target = context[target_id]
    candidate = context[candidate_id]
    coverage = float(candidate.notna().mean())
    if coverage < 0.80 or candidate.dropna().nunique() < 5:
        return None

    best = None
    for lag in LAGS:
        pearson, spearman, left_values, right_values = pair_correlations(target, candidate.shift(lag))
        if not math.isfinite(pearson) or not math.isfinite(spearman):
            continue
        strength = 0.55 * abs(spearman) + 0.45 * abs(pearson)
        if best is None or strength > best["strength"]:
            best = {
                "lag_minutes": lag,
                "pearson": pearson,
                "spearman": spearman,
                "strength": strength,
                "left_values": left_values,
                "right_values": right_values,
            }
    if best is None:
        return None

    left_values = best.pop("left_values")
    right_values = best.pop("right_values")
    midpoint = len(left_values) // 2
    first = pearson_arrays(left_values[:midpoint], right_values[:midpoint])
    second = pearson_arrays(left_values[midpoint:], right_values[midpoint:])
    stable_strength = 0.0
    sign_consistent = 0.0
    if math.isfinite(first) and math.isfinite(second):
        stable_strength = min(abs(first), abs(second))
        sign_consistent = 1.0 if first * second >= 0 else 0.0
    expert_bonus = 0.05 if candidate_id in expert_ids else 0.0
    lead_bonus = 0.02 if best["lag_minutes"] > 0 else 0.0
    score = (
        0.45 * abs(best["spearman"])
        + 0.30 * abs(best["pearson"])
        + 0.15 * stable_strength
        + 0.03 * sign_consistent
        + expert_bonus
        + lead_bonus
    )
    return {
        "target_id": target_id,
        "candidate_id": candidate_id,
        "score": score,
        "coverage": coverage,
        "lag_minutes": best["lag_minutes"],
        "pearson": best["pearson"],
        "spearman": best["spearman"],
        "stable_strength": stable_strength,
        "sign_consistent": bool(sign_consistent),
        "expert_prior": candidate_id in expert_ids,
    }


def select_main_variables(context: pd.DataFrame, target_id: str, max_variables: int) -> list[dict[str, Any]]:
    expert_ids = set(SPARSE_COVARIATES.get(target_id, []))
    scored = []
    for candidate_id in CORE_CANDIDATES:
        if candidate_id == target_id or candidate_id not in context:
            continue
        item = candidate_score(context, target_id, candidate_id, expert_ids)
        if item:
            scored.append(item)
    scored.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    deferred = []
    for item in scored:
        redundancy = 0.0
        for prior in selected:
            left_values, right_values = paired_arrays(
                context[item["candidate_id"]],
                context[prior["candidate_id"]],
            )
            value = pearson_arrays(left_values, right_values)
            if math.isfinite(value):
                redundancy = max(redundancy, abs(value))
        item["max_redundancy"] = redundancy
        if redundancy > 0.98 and len(selected) >= 3:
            deferred.append(item)
            continue
        selected.append(item)
        if len(selected) >= max_variables:
            break
    if len(selected) < max_variables:
        for item in deferred:
            selected.append(item)
            if len(selected) >= max_variables:
                break
    for rank, item in enumerate(selected, start=1):
        item["rank"] = rank
    return selected


def clean_values(series: pd.Series, length: int) -> list[float | None]:
    values = pd.to_numeric(series.tail(length), errors="coerce")
    return [None if not math.isfinite(float(value)) else float(value) for value in values]


def build_job(
    model_frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    target_id: str,
    variant: str,
    selected_ids: list[str],
    context_minutes: int,
    horizon_minutes: int,
) -> dict[str, Any]:
    context = model_frame.loc[model_frame.index <= cutoff].tail(context_minutes)
    target_values = clean_values(context[target_id], context_minutes)
    if variant == "target_only":
        covariate_ids = []
    elif variant == "expert_sparse":
        covariate_ids = [item for item in SPARSE_COVARIATES[target_id] if item in context]
    else:
        covariate_ids = [item for item in selected_ids if item in context]
    covariates = []
    for covariate_id in covariate_ids:
        values = clean_values(context[covariate_id], context_minutes)
        covariates.append(
            {
                "id": covariate_id,
                "name": covariate_id,
                "values": values,
                "nonnull_count": sum(value is not None for value in values),
            }
        )
    return {
        "target_id": target_id,
        "target_name": target_id,
        "target": {
            "id": target_id,
            "name": target_id,
            "values": target_values,
            "nonnull_count": sum(value is not None for value in target_values),
        },
        "covariates": covariates,
        "context_minutes": len(target_values),
        "prediction_minutes": horizon_minutes,
        "feature_type": FEATURE_VARIANTS[variant],
        "feature_engine": "MAIN-VARIABLE-SELECTION-19-20260808",
        "covariate_ids": covariate_ids,
        "cutoff_time": cutoff.isoformat(sep=" "),
        "future_timestamps": [
            (cutoff + pd.Timedelta(minutes=minute)).isoformat(sep=" ")
            for minute in range(1, horizon_minutes + 1)
        ],
    }


def evaluate(
    prediction: dict[str, Any],
    truth_frame: pd.DataFrame,
    baselines: dict[str, dict[str, float]],
) -> dict[str, Any] | None:
    target_id = str(prediction.get("target_id"))
    variant = FEATURE_TO_VARIANT.get(str(prediction.get("feature_type")))
    if not variant or target_id not in truth_frame or target_id not in baselines:
        return None
    timestamps = pd.to_datetime(prediction.get("future_timestamps") or [])
    forecast = pd.to_numeric(pd.Series(prediction.get("p50") or []), errors="coerce").to_numpy(dtype=float)
    truth = pd.to_numeric(truth_frame[target_id].reindex(timestamps), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(forecast) & np.isfinite(truth)
    if not valid.any():
        return None
    forecast = forecast[valid]
    truth = truth[valid]
    stats = baselines[target_id]
    iqr = stats["q3"] - stats["q1"]
    scale = max(iqr, abs(stats["q2"]) * 0.01, 1e-6)
    absolute_errors = np.abs(forecast - truth)
    raw_mae = float(absolute_errors.mean())
    persistence_mae = float(np.abs(truth - stats["last_value"]).mean())
    median_mae = float(np.abs(truth - stats["q2"]).mean())
    band_values = {}
    for label, start, end in (("m00_30", 0, 30), ("m31_60", 30, 60), ("m61_120", 60, 120)):
        subset = absolute_errors[start:min(end, len(absolute_errors))]
        band_values[f"{label}_iqr_nmae"] = None if len(subset) == 0 else float(subset.mean() / scale)
    return {
        "cutoff": prediction.get("cutoff_time"),
        "target_id": target_id,
        "variant": variant,
        "points": int(valid.sum()),
        "covariate_count": int(prediction.get("covariate_count") or 0),
        "mae": raw_mae,
        "iqr_nmae": raw_mae / scale,
        "persistence_iqr_nmae": persistence_mae / scale,
        "median_iqr_nmae": median_mae / scale,
        "skill_vs_persistence": None if persistence_mae <= 1e-12 else 1.0 - raw_mae / persistence_mae,
        "skill_vs_median": None if median_mae <= 1e-12 else 1.0 - raw_mae / median_mae,
        "q1": stats["q1"],
        "q2": stats["q2"],
        "q3": stats["q3"],
        "iqr": iqr,
        **band_values,
    }


def weighted_average(group: pd.DataFrame, column: str) -> float:
    valid = group[column].notna()
    return float(np.average(group.loc[valid, column].astype(float), weights=group.loc[valid, "points"].astype(float)))


def summarize(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (target_id, variant), group in detail.groupby(["target_id", "variant"], sort=False):
        iqr_nmae = weighted_average(group, "iqr_nmae")
        rows.append(
            {
                "target_id": target_id,
                "variant": variant,
                "cutoffs": int(group["cutoff"].nunique()),
                "points": int(group["points"].sum()),
                "mae": weighted_average(group, "mae"),
                "iqr_nmae": iqr_nmae,
                "accuracy_class": "高" if iqr_nmae <= 0.25 else "较高" if iqr_nmae <= 0.5 else "一般" if iqr_nmae <= 1 else "较低",
                "skill_vs_persistence": weighted_average(group, "skill_vs_persistence"),
                "skill_vs_median": weighted_average(group, "skill_vs_median"),
                "m00_30_iqr_nmae": weighted_average(group, "m00_30_iqr_nmae"),
                "m31_60_iqr_nmae": weighted_average(group, "m31_60_iqr_nmae"),
                "m61_120_iqr_nmae": weighted_average(group, "m61_120_iqr_nmae"),
                "q1": weighted_average(group, "q1"),
                "q2": weighted_average(group, "q2"),
                "q3": weighted_average(group, "q3"),
                "iqr": weighted_average(group, "iqr"),
            }
        )
    return pd.DataFrame(rows).sort_values(["target_id", "iqr_nmae"])


def consensus_selection(selection: pd.DataFrame, max_variables: int) -> dict[str, list[dict[str, Any]]]:
    output = {}
    for target_id, group in selection.groupby("target_id", sort=False):
        rows = []
        for candidate_id, candidate_group in group.groupby("candidate_id"):
            lag_mode = Counter(candidate_group["lag_minutes"].astype(int)).most_common(1)[0][0]
            rows.append(
                {
                    "id": candidate_id,
                    "selected_cutoffs": int(candidate_group["cutoff"].nunique()),
                    "average_score": float(candidate_group["score"].mean()),
                    "average_abs_spearman": float(candidate_group["spearman"].abs().mean()),
                    "typical_lag_minutes": int(lag_mode),
                }
            )
        rows.sort(key=lambda item: (item["selected_cutoffs"], item["average_score"]), reverse=True)
        output[target_id] = rows[:max_variables]
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Select and backtest 19 Chronos target-specific main variables.")
    parser.add_argument("--db-host", default="10.30.220.12")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--chronos-url", default="http://10.30.220.12:8777")
    parser.add_argument("--context-minutes", type=int, default=480)
    parser.add_argument("--horizon-minutes", type=int, default=120)
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--cutoff-offset-hours", default="0,8,16,24")
    parser.add_argument("--max-main-variables", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "chronos_main_variable_selection_19"))
    args = parser.parse_args()

    password = os.environ.get(args.db_password_env, "")
    if not password:
        raise SystemExit(f"missing database password environment variable: {args.db_password_env}")
    conn_params = {
        "host": args.db_host,
        "port": args.db_port,
        "dbname": args.db_name,
        "user": args.db_user,
        "password": password,
        "connect_timeout": 12,
    }

    now = datetime.now()
    lookback_hours = max(float(item) for item in args.cutoff_offset_hours.split(",") if item.strip())
    start = now - timedelta(hours=lookback_hours, minutes=args.context_minutes + args.horizon_minutes + 30)
    raw_frame = load_core_frame(conn_params, start, now)
    if raw_frame.empty:
        raise SystemExit("no core variable history was loaded")
    full_index = pd.date_range(raw_frame.index.min().floor("min"), raw_frame.index.max().floor("min"), freq="1min")
    truth_frame = raw_frame.reindex(full_index)
    model_frame = truth_frame.ffill().bfill()
    latest = truth_frame.index.max().floor("min")
    offsets = [float(item.strip()) for item in args.cutoff_offset_hours.split(",") if item.strip()]
    cutoffs = [latest - pd.Timedelta(minutes=args.horizon_minutes) - pd.Timedelta(hours=offset) for offset in offsets]

    selection_rows = []
    detail_rows = []
    raw_results = []
    for cutoff in cutoffs:
        context = model_frame.loc[
            (model_frame.index > cutoff - pd.Timedelta(minutes=args.context_minutes))
            & (model_frame.index <= cutoff)
        ]
        if len(context) < args.context_minutes * 0.80:
            raise SystemExit(f"not enough selection context at cutoff {cutoff}: {len(context)}")
        selected_by_target = {}
        for target_id in TARGET_IDS:
            selected = select_main_variables(context, target_id, args.max_main_variables)
            selected_by_target[target_id] = [item["candidate_id"] for item in selected]
            for item in selected:
                selection_rows.append({"cutoff": cutoff.isoformat(sep=" "), **item})
        baselines = baseline_stats(conn_params, cutoff, args.baseline_days)
        jobs = [
            build_job(
                model_frame,
                cutoff,
                target_id,
                variant,
                selected_by_target[target_id],
                args.context_minutes,
                args.horizon_minutes,
            )
            for variant in FEATURE_VARIANTS
            for target_id in TARGET_IDS
        ]
        payload = {
            "jobs": jobs,
            "feature_source": {
                "type": "core_28_recent_8h_main_variable_selection",
                "candidate_count": len(CORE_CANDIDATES) - 1,
                "selection_context_minutes": args.context_minutes,
            },
            "request": {
                "cutoff_time": cutoff.isoformat(sep=" "),
                "target_ids": TARGET_IDS,
                "variants": list(FEATURE_VARIANTS),
                "baseline_days": args.baseline_days,
                "prediction_minutes": args.horizon_minutes,
            },
        }
        print(f"REQUEST cutoff={cutoff} jobs={len(jobs)}", flush=True)
        result = post_json(args.chronos_url, payload, args.timeout_seconds)
        raw_results.append({"cutoff": cutoff.isoformat(sep=" "), "result": result})
        for prediction in result.get("predictions") or []:
            row = evaluate(prediction, truth_frame, baselines)
            if row:
                detail_rows.append(row)
        print(f"RESULT cutoff={cutoff} predictions={len(result.get('predictions') or [])}", flush=True)

    selection = pd.DataFrame(selection_rows)
    detail = pd.DataFrame(detail_rows)
    if selection.empty or detail.empty:
        raise SystemExit("selection or backtest produced no results")
    summary = summarize(detail)
    winners = summary.loc[summary.groupby("target_id")["iqr_nmae"].idxmin()].sort_values("iqr_nmae")
    consensus = consensus_selection(selection, args.max_main_variables)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    selection_path = output_dir / f"main_variable_selection_detail_{stamp}.csv"
    detail_path = output_dir / f"main_variable_backtest_detail_{stamp}.csv"
    summary_path = output_dir / f"main_variable_backtest_summary_{stamp}.csv"
    winners_path = output_dir / f"main_variable_backtest_winners_{stamp}.csv"
    consensus_path = output_dir / f"main_variable_consensus_{stamp}.json"
    raw_path = output_dir / f"main_variable_backtest_raw_{stamp}.json"
    selection.to_csv(selection_path, index=False, encoding="utf-8-sig")
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    winners.to_csv(winners_path, index=False, encoding="utf-8-sig")
    consensus_path.write_text(json.dumps(consensus, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("SELECTION", selection_path, flush=True)
    print("SUMMARY", summary_path, flush=True)
    print("WINNERS", winners_path, flush=True)
    print("CONSENSUS", consensus_path, flush=True)
    for row in winners.itertuples(index=False):
        print(
            "BEST",
            row.target_id,
            row.variant,
            "iqr_nmae",
            round(row.iqr_nmae, 4),
            "skill_vs_persistence",
            round(row.skill_vs_persistence, 4),
            "horizon",
            [round(row.m00_30_iqr_nmae, 4), round(row.m31_60_iqr_nmae, 4), round(row.m61_120_iqr_nmae, 4)],
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
