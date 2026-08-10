"""Plot one heat's live V19 mean-Si prediction curve from a local ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
import pandas as pd  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "PT" / "预测铁水Si含量" / "reports" / "live_predictions"
FONT_PATHS = [
    Path("C:/Windows/Fonts/simsun.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
]


def chinese_font() -> FontProperties | None:
    for path in FONT_PATHS:
        if path.exists():
            return FontProperties(fname=str(path))
    return None


def read_ledger(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"ledger is empty: {path}")
    frame["prediction_cutoff_ts"] = pd.to_datetime(
        frame["prediction_cutoff_ts"], errors="raise"
    )
    numeric_columns = [
        "prediction_si",
        "p10",
        "p50",
        "p90",
        "actual_si_mean",
        "absolute_error",
        "signed_error",
    ]
    for column in numeric_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("prediction_cutoff_ts")


def plot_curve(frame: pd.DataFrame, output_path: Path) -> None:
    target = str(frame["target_meltno"].iloc[-1]) if "target_meltno" in frame else "heat"
    font = chinese_font()
    x = frame["prediction_cutoff_ts"]
    fig, ax = plt.subplots(figsize=(14, 6.5), dpi=160)
    if {"p10", "p90"}.issubset(frame.columns):
        ax.fill_between(
            x,
            frame["p10"].to_numpy(float),
            frame["p90"].to_numpy(float),
            color="#77aadd",
            alpha=0.18,
            label="P10-P90经验区间",
        )
    ax.plot(x, frame["prediction_si"], marker="o", linewidth=1.8, label="V19预测平均Si")
    if "actual_si_mean" in frame and frame["actual_si_mean"].notna().any():
        actual = float(frame["actual_si_mean"].dropna().iloc[-1])
        ax.axhline(actual, color="#d9534f", linestyle="--", linewidth=1.6, label=f"实际平均Si={actual:.3f}%")
    if "target_open_ts_effective" in frame and frame["target_open_ts_effective"].notna().any():
        open_ts = pd.to_datetime(frame["target_open_ts_effective"].dropna().iloc[-1], errors="coerce")
        if pd.notna(open_ts):
            ax.axvline(open_ts, color="#444444", linestyle=":", linewidth=1.4, label=f"开口={open_ts:%H:%M}")
    ax.set_title(f"{target} 每5分钟平均Si预测回放", fontproperties=font)
    ax.set_xlabel("预测截止时间", fontproperties=font)
    ax.set_ylabel("平均Si（%）", fontproperties=font)
    ax.grid(alpha=0.25)
    ax.legend(prop=font)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    fig.autofmt_xdate(rotation=0)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot live V19 Si prediction curve.")
    parser.add_argument("--target-meltno", help="Used to infer default ledger path.")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.ledger:
        if not args.target_meltno:
            raise SystemExit("provide --ledger or --target-meltno")
        safe = args.target_meltno.replace("/", "_").replace("\\", "_")
        args.ledger = DEFAULT_DIR / f"{safe}_v19_live_ledger.jsonl"
    output = args.output
    if output is None:
        output = args.ledger.with_suffix(".png")
    frame = read_ledger(args.ledger)
    plot_curve(frame, output)
    summary = {
        "ok": True,
        "points": int(len(frame)),
        "ledger": str(args.ledger),
        "output": str(output),
        "min_prediction": float(frame["prediction_si"].min()),
        "max_prediction": float(frame["prediction_si"].max()),
        "last_prediction": float(frame["prediction_si"].iloc[-1]),
        "actual_si_mean": (
            float(frame["actual_si_mean"].dropna().iloc[-1])
            if "actual_si_mean" in frame and frame["actual_si_mean"].notna().any()
            else None
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
