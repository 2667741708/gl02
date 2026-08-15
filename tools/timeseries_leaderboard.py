from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCHEMA = "bf.timeseries.leaderboard.v1"
TARGET_COUNT = 19
REQUIRED_INPUT_FIELDS = {
    "model", "target_id", "cutoff", "mae", "iqr_nmae", "wis_80",
    "mae_m00_30", "mae_m31_60", "mae_m61_120", "std_ratio",
    "diff_std_ratio", "direction_accuracy", "coverage_p10_p90",
}
LOWER_IS_BETTER = (
    "iqr_nmae",
    "iqr_nwis_80",
    "nmae_m00_30",
    "nmae_m31_60",
    "nmae_m61_120",
    "coverage_error_80",
    "std_log_distance",
    "diff_std_log_distance",
)
OVERALL_WEIGHTS = {
    "iqr_nmae": 0.25,
    "iqr_nwis_80": 0.20,
    "nmae_m00_30": 0.10,
    "nmae_m31_60": 0.10,
    "nmae_m61_120": 0.10,
    "direction_accuracy": 0.10,
    "coverage_error_80": 0.05,
    "std_log_distance": 0.05,
    "diff_std_log_distance": 0.05,
}


def model_key(frame: pd.DataFrame) -> pd.Series:
    variant = frame.get("variant", pd.Series("target_only", index=frame.index)).fillna("target_only").astype(str)
    return frame["model"].astype(str) + "::" + variant


def display_name(key: str) -> str:
    model, variant = key.split("::", 1)
    names = {
        "chronos2_zero_shot": "Chronos-2",
        "ibm_ttm_r2_zero_shot": "IBM TTM R2",
        "last_value": "LastValue",
        "ridge_delta": "Ridge-Delta",
    }
    base = names.get(model, model)
    return base if variant == "target_only" and model != "ridge_delta" else f"{base} {variant}"


def _bool_series(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin(("true", "1", "yes"))


def prepare_detail(frames: Iterable[pd.DataFrame], target_count: int = TARGET_COUNT) -> tuple[pd.DataFrame, list[str]]:
    detail = pd.concat(list(frames), ignore_index=True, sort=False)
    missing_fields = sorted(REQUIRED_INPUT_FIELDS - set(detail.columns))
    if missing_fields:
        raise ValueError(f"detail rows are missing required fields: {', '.join(missing_fields)}")
    if "aggregation" in detail:
        detail = detail[detail["aggregation"].isna() | detail["aggregation"].eq("1min")]
    if "failed" in detail:
        detail = detail[~_bool_series(detail["failed"])]
    detail = detail.copy()
    detail["model_key"] = model_key(detail)
    detail["cutoff"] = pd.to_datetime(detail["cutoff"], errors="raise").dt.strftime("%Y-%m-%d %H:%M:%S")
    detail = detail.drop_duplicates(["model_key", "target_id", "cutoff"], keep="first")

    complete_by_model: dict[str, set[str]] = {}
    for key, group in detail.groupby("model_key"):
        counts = group.groupby("cutoff")["target_id"].nunique()
        complete_by_model[key] = set(counts[counts == target_count].index)
    if not complete_by_model:
        raise ValueError("no model rows were found")
    common_cutoffs = sorted(set.intersection(*complete_by_model.values()))
    if not common_cutoffs:
        raise ValueError("no common complete cutoffs across all models")
    detail = detail[detail["cutoff"].isin(common_cutoffs)].copy()

    scale = pd.to_numeric(detail["mae"], errors="coerce") / pd.to_numeric(detail["iqr_nmae"], errors="coerce")
    scale = scale.where(np.isfinite(scale) & (scale > 0))
    detail["iqr_nwis_80"] = pd.to_numeric(detail["wis_80"], errors="coerce") / scale
    detail["nmae_m00_30"] = pd.to_numeric(detail["mae_m00_30"], errors="coerce") / scale
    detail["nmae_m31_60"] = pd.to_numeric(detail["mae_m31_60"], errors="coerce") / scale
    detail["nmae_m61_120"] = pd.to_numeric(detail["mae_m61_120"], errors="coerce") / scale
    detail["coverage_error_80"] = (pd.to_numeric(detail["coverage_p10_p90"], errors="coerce") - 0.80).abs()
    detail["std_log_distance"] = pd.to_numeric(detail["std_ratio"], errors="coerce").clip(lower=1e-9).map(lambda value: abs(math.log(value)))
    detail["diff_std_log_distance"] = pd.to_numeric(detail["diff_std_ratio"], errors="coerce").clip(lower=1e-9).map(lambda value: abs(math.log(value)))
    return detail, common_cutoffs


def _rank_percentile(values: pd.Series, ascending: bool) -> pd.Series:
    ranks = values.rank(method="min", ascending=ascending)
    denominator = max(len(values) - 1, 1)
    return (ranks - 1.0) / denominator


def build_leaderboard(frames: Iterable[pd.DataFrame], target_count: int = TARGET_COUNT) -> dict[str, Any]:
    detail, common_cutoffs = prepare_detail(frames, target_count)
    metrics = [
        "mae", "rmse", "iqr_nmae", "mase", "std_ratio", "diff_std_ratio",
        "direction_accuracy", "coverage_p10_p90", "wis_80", "iqr_nwis_80",
        "nmae_m00_30", "nmae_m31_60", "nmae_m61_120", "coverage_error_80",
        "std_log_distance", "diff_std_log_distance", "latency_ms", "missing_ratio",
    ]
    available = [field for field in metrics if field in detail]
    summary = detail.groupby("model_key", as_index=True)[available].mean(numeric_only=True)
    summary["display_name"] = [display_name(key) for key in summary.index]
    non_finite = [field for field in OVERALL_WEIGHTS if not np.isfinite(summary[field]).all()]
    if non_finite:
        raise ValueError(f"leaderboard metrics contain non-finite values: {', '.join(non_finite)}")

    rank_fields: list[str] = []
    for field in OVERALL_WEIGHTS:
        ascending = field != "direction_accuracy"
        rank_field = f"rank_score_{field}"
        summary[rank_field] = _rank_percentile(summary[field], ascending=ascending)
        rank_fields.append(rank_field)
    summary["overall_score"] = sum(summary[f"rank_score_{field}"] * weight for field, weight in OVERALL_WEIGHTS.items())
    summary["overall_rank"] = summary["overall_score"].rank(method="min", ascending=True).astype(int)

    public_rank_fields = {
        "point_accuracy_rank": ("iqr_nmae", True),
        "probability_rank": ("iqr_nwis_80", True),
        "direction_rank": ("direction_accuracy", False),
        "dynamic_amplitude_rank": ("std_log_distance", True),
        "minute_dynamics_rank": ("diff_std_log_distance", True),
        "coverage_rank": ("coverage_error_80", True),
        "horizon_00_30_rank": ("nmae_m00_30", True),
        "horizon_31_60_rank": ("nmae_m31_60", True),
        "horizon_61_120_rank": ("nmae_m61_120", True),
    }
    for output_field, (metric, ascending) in public_rank_fields.items():
        summary[output_field] = summary[metric].rank(method="min", ascending=ascending).astype(int)

    entries = []
    for key, row in summary.sort_values(["overall_rank", "overall_score"]).iterrows():
        entries.append({
            "model_key": key,
            "display_name": row["display_name"],
            "overall_rank": int(row["overall_rank"]),
            "overall_score": round(float(row["overall_score"]), 6),
            **{field: int(row[field]) for field in public_rank_fields},
            "metrics": {
                field: (None if not math.isfinite(float(row[field])) else round(float(row[field]), 6))
                for field in available
            },
        })

    winners = {
        "overall": entries[0]["model_key"],
        **{
            field.removesuffix("_rank"): min(entries, key=lambda item: (item[field], item["overall_rank"]))["model_key"]
            for field in public_rank_fields
        },
    }
    return {
        "schema": SCHEMA,
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "target_count": target_count,
        "common_cutoff_count": len(common_cutoffs),
        "common_cutoffs": common_cutoffs,
        "ranking_policy": {
            "lower_score_is_better": True,
            "overall_weights": OVERALL_WEIGHTS,
            "notes": [
                "All models use identical complete cutoffs and the same 19 targets.",
                "Segment MAE and WIS are normalized by the per-window historical IQR scale.",
                "STD ratios are ranked by symmetric log-distance from 1, not by the largest raw ratio.",
                "The leaderboard is experimental and does not authorize production model switching.",
            ],
        },
        "winners": winners,
        "entries": entries,
    }


def markdown_report(leaderboard: dict[str, Any]) -> str:
    lines = [
        "# 19项时间序列模型统一排行榜",
        "",
        f"- 生成时间：{leaderboard['created_at']}",
        f"- 公共完整切点：{leaderboard['common_cutoff_count']}个",
        f"- 目标变量：{leaderboard['target_count']}项",
        "- 综合分越低越好；所有模型使用同切点、同目标集合。",
        "",
        "| 综合排名 | 模型 | 综合分 | IQR-NMAE | IQR-NWIS | 0-30分 | 31-60分 | 61-120分 | 方向准确率 | STD比 | 差分STD比 | 80%覆盖率 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in leaderboard["entries"]:
        metric = item["metrics"]
        lines.append(
            f"| {item['overall_rank']} | {item['display_name']} | {item['overall_score']:.4f} | "
            f"{metric['iqr_nmae']:.4f} | {metric['iqr_nwis_80']:.4f} | {metric['nmae_m00_30']:.4f} | "
            f"{metric['nmae_m31_60']:.4f} | {metric['nmae_m61_120']:.4f} | {metric['direction_accuracy']:.2%} | "
            f"{metric['std_ratio']:.4f} | {metric['diff_std_ratio']:.4f} | {metric['coverage_p10_p90']:.2%} |"
        )
    lines.extend((
        "",
        "## 分维度冠军",
        "",
        *(f"- `{name}`：`{key}`" for name, key in leaderboard["winners"].items()),
        "",
        "该排行榜只用于实验决策。扩大切点并完成人工确认前，不得据此自动切换8777、8778或生产趋势页。",
    ))
    return "\n".join(lines) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build a same-cutoff, multi-metric leaderboard for the 19 trend targets.")
    parser.add_argument("--detail", action="append", required=True, help="Detail CSV; repeat for each benchmark batch.")
    parser.add_argument("--output-json", default=str(root / "PT" / "时间序列预测评测" / "results" / "timeseries_model_leaderboard_current.json"))
    parser.add_argument("--output-csv", default=str(root / "PT" / "时间序列预测评测" / "results" / "timeseries_model_leaderboard_current.csv"))
    parser.add_argument("--output-md", default=str(root / "PT" / "时间序列预测评测" / "results" / "timeseries_model_leaderboard_current.md"))
    args = parser.parse_args()

    paths = [Path(value) for value in args.detail]
    leaderboard = build_leaderboard([pd.read_csv(path) for path in paths])
    leaderboard["source_files"] = [str(path.resolve()) for path in paths]
    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    output_md = Path(args.output_md)
    for path in (output_json, output_csv, output_md):
        path.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(leaderboard, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.json_normalize(leaderboard["entries"]).to_csv(output_csv, index=False, encoding="utf-8-sig")
    output_md.write_text(markdown_report(leaderboard), encoding="utf-8")
    print(f"JSON={output_json.resolve()}")
    print(f"CSV={output_csv.resolve()}")
    print(f"REPORT={output_md.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
