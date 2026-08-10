#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compare the foreman fuel-ratio rule with V20 history-Si predictions.

The comparison is intentionally limited to heats that can be matched by both
heat number and opening timestamp.  V20 train rows are reported separately;
the headline comparison uses validation + confirmation rows only.

Requirement: REQ-SI-FUELRATIO-V20-SIDE-BY-SIDE-20260808.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FUEL = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-FUELRATIO-REPORT-20260808"
    / "fuel_ratio_rule_eval"
    / "fuel_ratio_rule_predictions.csv"
)
DEFAULT_V20 = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V20-OPEN-MINUS-20260807"
    / "quick60_history_pci_training_ablationselect"
    / "v20_predictions.csv"
)
DEFAULT_V19_METRICS = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-V19-AUGUST-HOLDOUT-20260807"
    / "metrics.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "PT"
    / "预测铁水Si含量"
    / "reports"
    / "experiments"
    / "EXP-SI-FUELRATIO-V20-COMPARE-20260808"
)
FONT_PATHS = (
    Path("C:/Windows/Fonts/simsun.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="同炉次并列评估工长燃料比经验法与 V20 历史 Si 方法。"
    )
    parser.add_argument("--fuel-csv", type=Path, default=DEFAULT_FUEL)
    parser.add_argument("--v20-csv", type=Path, default=DEFAULT_V20)
    parser.add_argument("--v19-metrics", type=Path, default=DEFAULT_V19_METRICS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _heat_no(value: Any) -> str:
    match = re.search(r"-(\d+)$", str(value).strip())
    if not match:
        return ""
    return str(int(match.group(1)))


def _metrics(actual: pd.Series, prediction: pd.Series) -> dict[str, Any]:
    frame = pd.DataFrame(
        {
            "actual": pd.to_numeric(actual, errors="coerce"),
            "prediction": pd.to_numeric(prediction, errors="coerce"),
        }
    ).dropna()
    if frame.empty:
        return {"n": 0}
    error = frame["prediction"] - frame["actual"]
    absolute = error.abs()
    corr = frame["actual"].corr(frame["prediction"])
    return {
        "n": int(len(frame)),
        "mae": float(absolute.mean()),
        "rmse": float(math.sqrt(float(np.mean(np.square(error))))),
        "bias": float(error.mean()),
        "hit_abs_le_002": float((absolute <= 0.02).mean()),
        "hit_abs_le_005": float((absolute <= 0.05).mean()),
        "correlation": None if pd.isna(corr) else float(corr),
    }


def _font() -> FontProperties | None:
    for path in FONT_PATHS:
        if path.exists():
            return FontProperties(fname=str(path))
    return None


def _v19_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected = str(payload.get("selected_candidate", ""))
    ranking = next(
        (item for item in payload.get("rankings", []) if item.get("ablation") == selected),
        {},
    )
    return {
        "note": "V19 为8月时间外回放，不是开口前1小时共同样本，禁止直接排名。",
        "selected_candidate": selected,
        "training_rows": payload.get("training_rows"),
        "test_rows": payload.get("test_rows"),
        "test_mae": ranking.get("test_mae"),
        "test_hit_rate_abs_le_005": ranking.get("test_hit_rate_abs_le_005"),
        "model_status": payload.get("model_status"),
    }


def build_comparison(fuel_path: Path, v20_path: Path) -> pd.DataFrame:
    fuel = pd.read_csv(fuel_path)
    v20 = pd.read_csv(v20_path)
    fuel["heat_no_key"] = fuel["heat_no"].astype(str).str.replace(r"\.0$", "", regex=True)
    v20["heat_no_key"] = v20["official_meltno"].map(_heat_no)
    fuel["open_ts_key"] = pd.to_datetime(fuel["heat_open_ts"], errors="coerce")
    v20["open_ts_key"] = pd.to_datetime(v20["open_ts"], errors="coerce")

    merged = fuel.merge(
        v20,
        on=["heat_no_key", "open_ts_key"],
        how="inner",
        suffixes=("__fuel", "__v20"),
        validate="one_to_one",
    )
    if merged.empty:
        raise RuntimeError("没有找到炉号与开口时间同时一致的共同炉次。")

    merged["actual_si_quality_summary"] = pd.to_numeric(
        merged["target__Si_mean"], errors="coerce"
    )
    merged["actual_si_report"] = pd.to_numeric(merged["actual_si"], errors="coerce")
    merged["actual_label_delta"] = (
        merged["actual_si_report"] - merged["actual_si_quality_summary"]
    )
    merged["prediction_foreman_fixed030"] = pd.to_numeric(
        merged["prediction_fixed030"], errors="coerce"
    )
    merged["prediction_foreman_prev2si"] = pd.to_numeric(
        merged["prediction_rolling2d_si"], errors="coerce"
    )
    merged["prediction_v20_history"] = pd.to_numeric(
        merged["prediction__Si_mean"], errors="coerce"
    )
    merged["evaluation_scope"] = np.where(
        merged["split"].isin(["validation", "confirm"]),
        "time_forward_eval",
        "train_in_sample",
    )
    merged = merged.sort_values("open_ts_key").reset_index(drop=True)
    keep = [
        "official_meltno",
        "open_ts_key",
        "prediction_cutoff_ts",
        "split",
        "evaluation_scope",
        "actual_si_quality_summary",
        "actual_si_report",
        "actual_label_delta",
        "baseline_fuel_prev2d",
        "current_prev4h_fuel",
        "fuel_delta",
        "prediction_foreman_fixed030",
        "prediction_foreman_prev2si",
        "prediction_v20_history",
    ]
    return merged[keep].rename(columns={"open_ts_key": "open_ts"})


def evaluate_scopes(frame: pd.DataFrame) -> dict[str, Any]:
    methods = {
        "foreman_fixed_si_030": "prediction_foreman_fixed030",
        "foreman_prev2d_si_baseline": "prediction_foreman_prev2si",
        "v20_history_si": "prediction_v20_history",
    }
    scopes = {
        "all_common_descriptive": frame,
        "time_forward_eval": frame[frame["evaluation_scope"] == "time_forward_eval"],
        "validation": frame[frame["split"] == "validation"],
        "confirm": frame[frame["split"] == "confirm"],
        "train_in_sample_not_for_ranking": frame[frame["split"] == "train"],
    }
    result: dict[str, Any] = {}
    for scope, subset in scopes.items():
        result[scope] = {
            name: _metrics(subset["actual_si_quality_summary"], subset[column])
            for name, column in methods.items()
        }
    label_delta = frame["actual_label_delta"].abs()
    result["label_alignment"] = {
        "n": int(label_delta.notna().sum()),
        "exact_match_count": int((label_delta.fillna(np.inf) <= 1e-12).sum()),
        "max_abs_delta": float(label_delta.max()) if label_delta.notna().any() else None,
        "actual_used_for_metrics": "220.12 heat_performance_quality_summary target__Si_mean",
    }
    return result


def plot_comparison(frame: pd.DataFrame, output: Path) -> None:
    subset = frame[frame["evaluation_scope"] == "time_forward_eval"].copy()
    if subset.empty:
        subset = frame.copy()
    labels = subset["official_meltno"].str.extract(r"-(\d+)$", expand=False)
    x = np.arange(len(subset))
    font = _font()
    fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.plot(x, subset["actual_si_quality_summary"], marker="o", linewidth=2.2, label="实际平均Si")
    ax.plot(x, subset["prediction_foreman_fixed030"], marker="s", linewidth=1.8, label="工长燃料比法（基准Si=0.30）")
    ax.plot(x, subset["prediction_v20_history"], marker="^", linewidth=1.8, label="V20历史Si法")
    ax.axhspan(0.20, 0.40, color="#6aa84f", alpha=0.08)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0)
    ax.set_xlabel("炉号", fontproperties=font)
    ax.set_ylabel("平均Si（%）", fontproperties=font)
    ax.set_title("同炉次开口前1小时：工长燃料比法 vs V20历史Si法", fontproperties=font)
    ax.grid(alpha=0.25)
    ax.legend(prop=font)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_markdown(metrics: dict[str, Any], output: Path) -> None:
    scope = metrics["time_forward_eval"]
    rows = []
    labels = {
        "foreman_fixed_si_030": "工长燃料比法（固定Si=0.30）",
        "foreman_prev2d_si_baseline": "工长燃料比法（前两日Si基准）",
        "v20_history_si": "V20历史Si法",
    }
    for key, label in labels.items():
        item = scope[key]
        rows.append(
            f"| {label} | {item['n']} | {item['mae']:.4f} | "
            f"{item['hit_abs_le_005']:.2%} | {item['hit_abs_le_002']:.2%} |"
        )
    content = "\n".join(
        [
            "# 工长燃料比法与 V20 历史 Si 法同炉次并列评估",
            "",
            "主表只使用 V20 的 validation + confirm 共同炉次；训练段不参与排名。",
            "实际值统一采用 220.12 炉次质量汇总表的每炉有效 Si 算术平均值。",
            "",
            "| 方法 | 炉次 | MAE | ±0.05命中率 | ±0.02命中率 |",
            "|---|---:|---:|---:|---:|",
            *rows,
            "",
            "V19 指标只作为历史背景：其时间外测试不是严格开口前1小时共同样本，不能直接排名。",
        ]
    )
    output.write_text(content + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame = build_comparison(args.fuel_csv, args.v20_csv)
    metrics = evaluate_scopes(frame)
    metrics["schema"] = "bf.si.fuelratio_v20_side_by_side.v1"
    metrics["comparison_contract"] = {
        "join_keys": ["heat_number", "open_ts"],
        "headline_scope": "V20 validation + confirm common heats",
        "prediction_cutoff": "open_ts - 60min for V20; previous 4 full report hours for foreman rule",
        "foreman_formula": "baseline_si + (prev4h_fuel - prev2d_daily_fuel_mean) / 5 * 0.1",
        "warning": "MES Web source currently exposes one report heat block per day; common sample is small.",
    }
    metrics["v19_context_only"] = _v19_summary(args.v19_metrics)

    frame.to_csv(args.output_dir / "side_by_side_predictions.csv", index=False, encoding="utf-8-sig")
    (args.output_dir / "side_by_side_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    plot_comparison(frame, args.output_dir / "side_by_side_actual_vs_prediction.png")
    write_markdown(metrics, args.output_dir / "side_by_side_report.md")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
