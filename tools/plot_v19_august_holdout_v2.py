"""Corrected JSON loader for the August holdout plot."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    root = Path(r"PT/预测铁水Si含量/reports/experiments/EXP-SI-V19-AUGUST-HOLDOUT-20260807")
    selected = json.loads((root / "metrics.json").read_text(encoding="utf-8"))["selected_candidate"]
    data = pd.read_csv(root / f"predictions_{selected}.csv", low_memory=False)
    data["prediction_cutoff_ts"] = pd.to_datetime(data["prediction_cutoff_ts"])
    data = data.sort_values("prediction_cutoff_ts")
    plt.figure(figsize=(14, 5.5), dpi=160)
    plt.plot(data["prediction_cutoff_ts"], data["actual__Si_mean"], label="actual mean Si", linewidth=1.5)
    plt.plot(data["prediction_cutoff_ts"], data["prediction__selected"], label=f"V19 rolling prediction ({selected})", linewidth=1.3)
    plt.xlabel("heat cutoff time")
    plt.ylabel("mean Si")
    plt.title("V19 July-trained / August time-out holdout")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(root / "si_mean_actual_vs_prediction_august_holdout.png")


if __name__ == "__main__":
    main()
