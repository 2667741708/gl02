from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from evaluate_ridge_fixed_cutoffs_19 import (  # noqa: E402
    CONTEXT_MINUTES,
    HORIZON_MINUTES,
    SPARSE_COVARIATES,
    TARGET_IDS,
    clean_context,
    evaluate_window,
    load_model,
    predict_ridge,
)


DISPLAY_NAMES = {
    "P_top": "综合顶压",
    "P_top_gas_A": "上升管压A",
    "P_top_gas_B": "上升管压B",
    "P_top_gas_C": "上升管压C",
    "P_top_gas_D": "上升管压D",
    "Q_blast": "冷风流量",
    "P_blast_cold": "冷风压力",
    "P_blast": "热风压力",
    "T_blast": "热风温度",
    "T_top": "综合顶温",
    "T_top_A": "顶温A",
    "T_top_B": "顶温B",
    "T_top_C": "顶温C",
    "T_top_D": "顶温D",
    "PI": "透气性指数",
    "DP_total": "总压差",
    "DP_upper": "上部压差",
    "DP_lower": "下部压差",
    "GasUtil": "煤气利用率",
}

COLORS = (
    "#47a3ff", "#35d4bd", "#ffb73d", "#ff6f61", "#91b6ff",
    "#42d7f5", "#36d6c5", "#ffa93a", "#ff6b64", "#9fd64d",
    "#6ee65c", "#ff8338", "#dce943", "#f2649d", "#9ad44f",
    "#44c9ff", "#ff914d", "#67da8b", "#c5a7ff",
)


def parse_cutoff(value: str | None, summary_path: Path) -> pd.Timestamp:
    if value:
        return pd.Timestamp(value).tz_localize(None)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return pd.Timestamp(summary["cutoffs"][-1]).tz_localize(None)


def load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col="ts", parse_dates=["ts"])
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    full_index = pd.date_range(frame.index.min().floor("min"), frame.index.max().floor("min"), freq="1min")
    return frame.reindex(full_index)


def build_curves(
    frame: pd.DataFrame,
    model_dir: Path,
    cutoff: pd.Timestamp,
    variant: str,
    history_minutes: int,
) -> tuple[dict[str, dict[str, object]], pd.DataFrame]:
    curves: dict[str, dict[str, object]] = {}
    rows: list[dict[str, object]] = []
    history_index = pd.date_range(cutoff - pd.Timedelta(minutes=history_minutes - 1), cutoff, freq="1min")
    future_index = pd.date_range(cutoff + pd.Timedelta(minutes=1), periods=HORIZON_MINUTES, freq="1min")

    for target_id in TARGET_IDS:
        context = frame[target_id].loc[
            (frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)
        ]
        history = clean_context(context)
        model = load_model(model_dir, target_id, variant)
        covariates: dict[str, np.ndarray] = {}
        if variant == "expert_sparse":
            for covariate_id in model.get("covariate_ids") or SPARSE_COVARIATES[target_id]:
                cov_context = frame[covariate_id].loc[
                    (frame.index > cutoff - pd.Timedelta(minutes=CONTEXT_MINUTES)) & (frame.index <= cutoff)
                ]
                covariates[covariate_id] = clean_context(cov_context)

        p10, p50, p90 = predict_ridge(model, history, covariates)
        truth = pd.to_numeric(frame[target_id].reindex(future_index), errors="coerce").to_numpy(dtype=float)
        raw_history = pd.to_numeric(frame[target_id].reindex(history_index), errors="coerce").to_numpy(dtype=float)
        history_values = pd.to_numeric(frame[target_id].loc[frame.index <= cutoff], errors="coerce").tail(30 * 24 * 60)
        q1, q3 = np.nanquantile(history_values.to_numpy(dtype=float), [0.25, 0.75])
        metrics = evaluate_window(history, truth, p10, p50, p90, float(q3 - q1))

        curves[target_id] = {
            "history_index": history_index,
            "future_index": future_index,
            "history": raw_history,
            "truth": truth,
            "p10": p10,
            "p50": p50,
            "p90": p90,
            "metrics": metrics,
        }

        for timestamp, actual in zip(history_index, raw_history):
            rows.append({
                "target_id": target_id,
                "display_name": DISPLAY_NAMES[target_id],
                "timestamp": timestamp,
                "phase": "history",
                "actual": actual,
                "p10": np.nan,
                "p50": np.nan,
                "p90": np.nan,
            })
        for timestamp, actual, low, mid, high in zip(future_index, truth, p10, p50, p90):
            rows.append({
                "target_id": target_id,
                "display_name": DISPLAY_NAMES[target_id],
                "timestamp": timestamp,
                "phase": "future",
                "actual": actual,
                "p10": low,
                "p50": mid,
                "p90": high,
            })

    return curves, pd.DataFrame(rows)


def plot_overview(curves: dict[str, dict[str, object]], cutoff: pd.Timestamp, variant: str, output_path: Path) -> None:
    plt.rcParams.update({
        "font.family": ["SimSun", "Microsoft YaHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 9,
    })
    figure, axes = plt.subplots(len(TARGET_IDS), 1, figsize=(20, 17), sharex=True)
    figure.patch.set_facecolor("#071d33")

    for index, (axis, target_id, color) in enumerate(zip(axes, TARGET_IDS, COLORS)):
        curve = curves[target_id]
        history_index = curve["history_index"]
        future_index = curve["future_index"]
        axis.set_facecolor("#0a2847")
        axis.plot(history_index, curve["history"], color="#d8e8f8", linewidth=1.15, alpha=0.82)
        axis.plot(future_index, curve["truth"], color="#ffffff", linewidth=1.35, label="未来实测真值")
        axis.fill_between(future_index, curve["p10"], curve["p90"], color=color, alpha=0.13, linewidth=0)
        axis.plot(future_index, curve["p50"], color=color, linewidth=1.65, linestyle=(0, (5, 3)), label="Ridge P50预测")
        axis.axvline(cutoff, color="#f2c14e", linewidth=0.9, alpha=0.85)
        axis.grid(axis="y", color="#285071", linestyle="--", linewidth=0.55, alpha=0.65)
        axis.tick_params(axis="y", colors="#b9d0e5", labelsize=7, length=0)
        axis.tick_params(axis="x", colors="#b9d0e5", labelsize=9)
        axis.set_ylabel(DISPLAY_NAMES[target_id], color="#d8e8f8", rotation=0, ha="right", va="center", labelpad=38)
        metrics = curve["metrics"]
        score = metrics.get("iqr_nmae")
        score_text = "缺少真值" if score is None else f"IQR-NMAE {score:.3f}"
        axis.text(0.995, 0.78, score_text, transform=axis.transAxes, ha="right", va="top", color="#8fb0ca", fontsize=7)
        for spine in axis.spines.values():
            spine.set_visible(False)
        if index < len(TARGET_IDS) - 1:
            axis.tick_params(labelbottom=False)

    axes[-1].xaxis.set_major_locator(mdates.MinuteLocator(interval=20))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[-1].set_xlabel("时间", color="#d8e8f8", labelpad=8)
    figure.suptitle(
        f"19项核心变量实际预测曲线  |  Ridge-Delta {variant}  |  切点 {cutoff:%Y-%m-%d %H:%M}",
        color="#f5fbff",
        fontsize=17,
        y=0.992,
    )
    figure.text(0.5, 0.968, "切点前：历史实测    切点后白线：未来实测真值    彩色虚线：当时预测P50    阴影：P10-P90", ha="center", color="#a9c6dd", fontsize=10)
    figure.tight_layout(rect=(0.055, 0.022, 0.995, 0.955), h_pad=0.08)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export actual Ridge prediction curves for all 19 trend variables.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--cutoff-summary", required=True)
    parser.add_argument("--cutoff")
    parser.add_argument("--variant", choices=("target_only", "expert_sparse"), default="expert_sparse")
    parser.add_argument("--history-minutes", type=int, default=60)
    parser.add_argument("--model-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "models"))
    parser.add_argument("--output-dir", default=str(ROOT / "PT" / "时间序列预测评测" / "results"))
    args = parser.parse_args()

    cutoff = parse_cutoff(args.cutoff, Path(args.cutoff_summary))
    frame = load_frame(Path(args.input_csv))
    curves, detail = build_curves(frame, Path(args.model_dir), cutoff, args.variant, args.history_minutes)
    output_dir = Path(args.output_dir)
    stem = f"ridge_actual_prediction_curves_{cutoff:%Y%m%d_%H%M}_{args.variant}"
    png_path = output_dir / f"{stem}.png"
    csv_path = output_dir / f"{stem}.csv"
    plot_overview(curves, cutoff, args.variant, png_path)
    detail.to_csv(csv_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S")
    print(f"PNG={png_path.resolve()}")
    print(f"CSV={csv_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
