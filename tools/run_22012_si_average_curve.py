"""Build a 15-day actual-versus-predicted average-Si heat curve.

The command is read-only against 220.12.  It uses the mean-target V9 adaptive
ensemble and rebuilds all current-heat features strictly before MES open time.

Requirement: REQ-SI-HEAT-AVERAGE-CURVE-20260806
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
SI_ROOT = ROOT / "PT" / "预测铁水Si含量"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(SI_ROOT / "src"))

import build_hot_metal_si_dataset as legacy_reader  # noqa: E402
import build_formal_si_dataset_v3 as formal_reader  # noqa: E402
from audit_22012_si_prediction_sources import audit as audit_sources  # noqa: E402
from si_semantic_engine.extract_v4_temporal_stats import run_extraction  # noqa: E402
from si_semantic_engine.prospective import build_inference_feature_frame  # noqa: E402
from si_semantic_engine.train_v6 import _history_baseline  # noqa: E402


REQUIREMENT_ID = "REQ-SI-HEAT-AVERAGE-CURVE-20260806"
DEFAULT_CATALOG = (
    ROOT / "PT" / "高炉3D模型" / "docs" / "GL02传感器点位清单.v1.json"
)
DEFAULT_MODEL = (
    SI_ROOT
    / "reports"
    / "experiments"
    / "EXP-SI-V9-MEAN-TARGET-HISTORYFIXR12-001_20260806"
    / "models"
    / "selected_v9_ensemble.joblib"
)
DEFAULT_OUTPUT = (
    SI_ROOT
    / "reports"
    / "experiments"
    / "EXP-SI-AVERAGE-CURVE-22012-001_20260806"
)
PROSPECTIVE_BOUNDARY = pd.Timestamp("2026-07-27 00:00:00")
PG_ENV_NAMES = (
    "GL02_PGHOST",
    "GL02_PGPORT",
    "GL02_PGDATABASE",
    "GL02_PGUSER",
    "GL02_PGPASSWORD",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return str(value)


def _as_timestamp(value: Any) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return pd.Timestamp(timestamp).tz_localize(None)


def _sample_result_ts(sample: dict[str, Any]) -> pd.Timestamp | None:
    for key in ("result_ts", "publish_ts", "sample_ts"):
        timestamp = _as_timestamp(sample.get(key))
        if timestamp is not None:
            return timestamp
    return None


def _valid_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def fetch_heat_rows(connection: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    """Read the one-row-per-official-heat average-Si source."""

    rows = connection.execute(
        """
        SELECT meltno, furnace_no, work_date, open_ts, close_ts,
               hot_metal_sample_count, first_sample_ts, last_sample_ts,
               c_avg, si_avg, mn_avg, p_avg, s_avg,
               si_median, si_min, si_max, si_spread,
               chemistry_stats, sample_details, source_updated_at,
               aggregated_at, aggregation_version
        FROM bf_assistant.heat_performance_quality_summary
        WHERE meltno IS NOT NULL
          AND open_ts IS NOT NULL
          AND si_avg IS NOT NULL
        ORDER BY open_ts, meltno
        """
    ).fetchall()
    return [dict(row) for row in rows]


def build_targets_and_samples(
    heat_rows: Iterable[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Convert PostgreSQL summaries into the model's mean-Si label contract."""

    targets: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    fallback_label_times = 0
    for row in heat_rows:
        meltno = str(row.get("meltno") or "").strip()
        open_ts = _as_timestamp(row.get("open_ts"))
        si_avg = _valid_number(row.get("si_avg"))
        if not meltno or open_ts is None or si_avg is None:
            continue
        details = row.get("sample_details")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = []
        details = details if isinstance(details, list) else []
        visible_times: list[pd.Timestamp] = []
        for index, item in enumerate(details):
            if not isinstance(item, dict):
                continue
            result_ts = _sample_result_ts(item)
            if result_ts is not None:
                visible_times.append(result_ts)
            samples.append(
                {
                    "official_meltno": meltno,
                    "open_ts": open_ts,
                    "result_ts": result_ts,
                    "sample_index": index,
                    "c_pct": _valid_number(item.get("C")),
                    "si_pct": _valid_number(item.get("Si")),
                    "mn_pct": _valid_number(item.get("Mn")),
                    "p_pct": _valid_number(item.get("P")),
                    "s_pct": _valid_number(item.get("S")),
                }
            )
        label_available_ts = max(visible_times) if visible_times else None
        if label_available_ts is None:
            label_available_ts = _as_timestamp(row.get("last_sample_ts"))
            fallback_label_times += 1
        if label_available_ts is None:
            label_available_ts = _as_timestamp(row.get("source_updated_at"))
            fallback_label_times += 1
        if not details:
            samples.append(
                {
                    "official_meltno": meltno,
                    "open_ts": open_ts,
                    "result_ts": label_available_ts,
                    "sample_index": 0,
                    "c_pct": _valid_number(row.get("c_avg")),
                    "si_pct": si_avg,
                    "mn_pct": _valid_number(row.get("mn_avg")),
                    "p_pct": _valid_number(row.get("p_avg")),
                    "s_pct": _valid_number(row.get("s_avg")),
                }
            )
        targets.append(
            {
                "official_meltno": meltno,
                "furnace_no": row.get("furnace_no"),
                "prediction_cutoff_ts": open_ts,
                "label_available_ts": label_available_ts,
                "target__Si_representative": si_avg,
                "target__Si_mean": si_avg,
                "target__Si_median": _valid_number(row.get("si_median")),
                "target__Si_min": _valid_number(row.get("si_min")),
                "target__Si_max": _valid_number(row.get("si_max")),
                "target__Si_spread": _valid_number(row.get("si_spread")),
                "target__Si_sample_count": int(
                    row.get("hot_metal_sample_count") or len(details) or 1
                ),
                "source_aggregation_version": row.get("aggregation_version"),
            }
        )
    target_frame = pd.DataFrame(targets).sort_values(
        ["prediction_cutoff_ts", "official_meltno"], kind="stable"
    )
    sample_frame = pd.DataFrame(samples)
    for column in ("open_ts", "result_ts"):
        sample_frame[column] = pd.to_datetime(sample_frame[column], errors="coerce")
    sample_frame = sample_frame.dropna(
        subset=["official_meltno", "open_ts", "result_ts"]
    )
    return target_frame, sample_frame, {
        "heat_rows": len(target_frame),
        "sample_rows": len(sample_frame),
        "label_time_fallback_count": fallback_label_times,
        "target_column": "target__Si_mean",
    }


def _temporary_pg_environment(params: dict[str, Any]) -> dict[str, str | None]:
    previous = {name: os.environ.get(name) for name in PG_ENV_NAMES}
    os.environ.update(
        {
            "GL02_PGHOST": str(params["host"]),
            "GL02_PGPORT": str(params["port"]),
            "GL02_PGDATABASE": str(params["dbname"]),
            "GL02_PGUSER": str(params["user"]),
            "GL02_PGPASSWORD": str(params["password"]),
        }
    )
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def predict_mean_v9(features: pd.DataFrame, model_path: Path) -> pd.DataFrame:
    """Apply the trained mean-target V9 adaptive simplex ensemble."""

    bundle = joblib.load(model_path)
    if bundle.get("target_column") != "target__Si_mean":
        raise RuntimeError("所选V9模型不是平均Si训练目标")
    direct_features = list(bundle["direct_features"])
    thermal_features = list(bundle["thermal_features"])
    required = set(direct_features) | set(thermal_features)
    missing = sorted(required - set(features.columns))
    if missing:
        raise RuntimeError(f"最新炉次缺少V9特征：{missing[:12]}")
    baseline = _history_baseline(features, fallback=float(bundle["fallback"]))
    baseline_values = baseline.to_numpy(float)
    components = {
        "direct": bundle["direct_model"].predict(features[direct_features]),
        "thermal_xgb": bundle["thermal_model"].predict(
            features[thermal_features]
        )
        + baseline_values,
        "lgbm_huber7": bundle["lgbm_models"]["lgbm_huber7"].predict(
            features[thermal_features]
        )
        + baseline_values,
        "lgbm_huber15_decay90": bundle["lgbm_models"][
            "lgbm_huber15_decay90"
        ].predict(features[thermal_features])
        + baseline_values,
        "history": baseline_values,
    }
    prediction = np.zeros(len(features), dtype=float)
    for name, weight in bundle["weights"].items():
        prediction += float(weight) * np.asarray(components[name], dtype=float)
    output = features[["official_meltno", "prediction_cutoff_ts"]].copy()
    output["prediction__Si_mean"] = prediction
    for name, values in components.items():
        output[f"component__{name}"] = np.asarray(values, dtype=float)
    return output


def regression_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    actual = frame["actual__Si_mean"].to_numpy(float)
    predicted = frame["prediction__Si_mean"].to_numpy(float)
    error = predicted - actual
    actual_delta = np.diff(actual)
    predicted_delta = np.diff(predicted)
    comparable = (np.abs(actual_delta) > 1e-12) | (np.abs(predicted_delta) > 1e-12)
    direction = (
        float(
            np.mean(
                np.sign(actual_delta[comparable])
                == np.sign(predicted_delta[comparable])
            )
        )
        if comparable.any()
        else None
    )
    return {
        "rows": len(frame),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(np.square(error)))),
        "bias_prediction_minus_actual": float(np.mean(error)),
        "hit_rate_abs_le_002": float(np.mean(np.abs(error) <= 0.02)),
        "hit_rate_abs_le_005": float(np.mean(np.abs(error) <= 0.05)),
        "pearson_level_correlation": float(
            pd.Series(actual).corr(pd.Series(predicted), method="pearson")
        ),
        "spearman_level_correlation": float(
            pd.Series(actual).corr(pd.Series(predicted), method="spearman")
        ),
        "heat_to_heat_direction_agreement": direction,
    }


def render_curve(frame: pd.DataFrame, output_path: Path) -> None:
    """Render actual and predicted average Si on the official heat timeline."""

    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    chinese = FontProperties(fname=str(font_path)) if font_path.is_file() else None
    figure, axis = plt.subplots(figsize=(18, 8.5), dpi=160)
    axis.plot(
        frame["prediction_cutoff_ts"],
        frame["actual__Si_mean"],
        color="#205493",
        linewidth=2.2,
        marker="o",
        markersize=3.5,
        label="实际逐炉平均 Si",
    )
    axis.plot(
        frame["prediction_cutoff_ts"],
        frame["prediction__Si_mean"],
        color="#d97706",
        linewidth=2.0,
        linestyle="--",
        marker="s",
        markersize=3.0,
        label="V9 自适应权重预测平均 Si",
    )
    if (frame["prediction_cutoff_ts"] >= PROSPECTIVE_BOUNDARY).any():
        axis.axvline(
            PROSPECTIVE_BOUNDARY,
            color="#6b7280",
            linewidth=1.2,
            linestyle=":",
            label="严格时间外区间起点（2026-07-27）",
        )
    start = frame["prediction_cutoff_ts"].min()
    end = frame["prediction_cutoff_ts"].max()
    axis.set_title(
        f"2#高炉最近15天逐炉平均硅含量：实际 vs 预测\n"
        f"{start:%Y-%m-%d %H:%M} — {end:%Y-%m-%d %H:%M}，{len(frame)}炉",
        fontproperties=chinese,
        fontsize=16,
        pad=14,
    )
    axis.set_xlabel("开铁时间", fontproperties=chinese, fontsize=12)
    axis.set_ylabel("平均 Si（%）", fontproperties=chinese, fontsize=12)
    axis.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    axis.grid(True, color="#d1d5db", alpha=0.55, linewidth=0.8)
    axis.legend(prop=chinese, loc="best", frameon=True)
    axis.margins(x=0.01)
    figure.autofmt_xdate(rotation=35, ha="right")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="只读生成220.12最近15天逐炉平均Si真实/预测双曲线。"
    )
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    cli.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    cli.add_argument("--sensor-catalog", type=Path, default=DEFAULT_CATALOG)
    cli.add_argument("--days", type=int, default=15)
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15449)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    cli.add_argument("--connect-timeout", type=int, default=20)
    return cli


def main() -> int:
    args = parser().parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with legacy_reader.sensor_ssh_tunnel(args) as (port, ssh_client):
        params = legacy_reader.remote_sensor_params(args, port, ssh_client)
        params["options"] = (
            "-c default_transaction_read_only=on -c statement_timeout=900000"
        )
        with psycopg.connect(**params, row_factory=dict_row) as connection:
            source_audit = audit_sources(connection, args.sensor_catalog.resolve())
            heat_rows = fetch_heat_rows(connection)
            targets, samples, label_audit = build_targets_and_samples(heat_rows)
            max_ts = targets["prediction_cutoff_ts"].max()
            window_start = max_ts - pd.Timedelta(days=max(1, args.days))
            recent_targets = targets.loc[
                targets["prediction_cutoff_ts"].between(window_start, max_ts)
            ].copy()
            registry = legacy_reader.fetch_registry(connection)
            sensor_features = formal_reader.fetch_temporal_sensor_features(
                connection,
                recent_targets,
                registry,
                max_lag_minutes=10,
                chunk_size=20,
            )
            prediction_rows = recent_targets.merge(
                sensor_features,
                on="official_meltno",
                how="inner",
                validate="one_to_one",
            )
            input_dir = output_dir / "inputs"
            input_dir.mkdir(exist_ok=True)
            targets.to_csv(
                input_dir / "heat_targets_mean.csv", index=False, encoding="utf-8-sig"
            )
            samples.to_csv(
                input_dir / "formal_samples.csv", index=False, encoding="utf-8-sig"
            )
            prediction_rows.to_csv(
                input_dir / "prediction_rows.csv", index=False, encoding="utf-8-sig"
            )
            previous_env = _temporary_pg_environment(params)
            try:
                temporal_dir = output_dir / "temporal_stats"
                run_extraction(
                    dataset_path=input_dir / "prediction_rows.csv",
                    output_dir=temporal_dir,
                    chunk_size=20,
                    windows_minutes=(30, 60, 120, 240, 480),
                )
            finally:
                _restore_environment(previous_env)
    inference, feature_audit = build_inference_feature_frame(
        prediction_rows,
        targets,
        samples,
        args.sensor_catalog.resolve(),
        output_dir / "temporal_stats",
    )
    predictions = predict_mean_v9(inference, args.model.resolve())
    actual = recent_targets[
        ["official_meltno", "prediction_cutoff_ts", "target__Si_mean", "target__Si_sample_count"]
    ].rename(columns={"target__Si_mean": "actual__Si_mean"})
    curve = actual.merge(
        predictions,
        on=["official_meltno", "prediction_cutoff_ts"],
        how="inner",
        validate="one_to_one",
    ).sort_values(["prediction_cutoff_ts", "official_meltno"], kind="stable")
    curve["absolute_error"] = (
        curve["prediction__Si_mean"] - curve["actual__Si_mean"]
    ).abs()
    all_metrics = regression_metrics(curve)
    prospective = curve.loc[
        curve["prediction_cutoff_ts"] >= PROSPECTIVE_BOUNDARY
    ].copy()
    metrics = {
        "requirement_id": REQUIREMENT_ID,
        "status": "experimental_offline_readonly",
        "target": "arithmetic mean of all valid Si samples per official meltno",
        "model": "V9 mean-target adaptive simplex ensemble",
        "window": {
            "days": int(args.days),
            "start": curve["prediction_cutoff_ts"].min(),
            "end": curve["prediction_cutoff_ts"].max(),
        },
        "all_latest_15_days": all_metrics,
        "strictly_after_2026_07_27": (
            regression_metrics(prospective) if len(prospective) >= 2 else None
        ),
        "model_weights": joblib.load(args.model.resolve())["weights"],
        "label_audit": label_audit,
        "feature_audit": feature_audit,
        "source_audit_file": "source_audit.json",
        "new_points_used_by_frozen_model": False,
        "new_points_policy": (
            "inventoried now; require historical coverage and a new time-split "
            "training experiment before inclusion"
        ),
    }
    curve.to_csv(output_dir / "si_average_actual_vs_prediction.csv", index=False, encoding="utf-8-sig")
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (output_dir / "source_audit.json").write_text(
        json.dumps(source_audit, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    added = pd.DataFrame(source_audit["sensor_registry"]["new_physical_points"])
    added.to_csv(output_dir / "new_sensor_points.csv", index=False, encoding="utf-8-sig")
    render_curve(curve, output_dir / "si_average_actual_vs_prediction.png")
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(output_dir),
                "curve_rows": len(curve),
                "metrics": metrics["strictly_after_2026_07_27"],
            },
            ensure_ascii=False,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
