"""Batch predict heat mean Si at a fixed lead time before each heat opens."""

from __future__ import annotations

import argparse
import csv
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_hot_metal_si_dataset as tunnel_builder  # noqa: E402
from run_live_si_prediction_5min import compact_record, extract_json  # noqa: E402


ATOMIC = ROOT / "tools" / "predict_next_heat_si_v19.py"
DEFAULT_OUT = ROOT / "PT" / "预测铁水Si含量" / "reports" / "open_minus_predictions"
FONT_PATHS = (
    Path("C:/Windows/Fonts/simsun.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/msyh.ttc"),
)


def chinese_font() -> FontProperties | None:
    for path in FONT_PATHS:
        if path.exists():
            return FontProperties(fname=str(path))
    return None


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


def fetch_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    clauses = ["furnace_no = %s", "open_ts IS NOT NULL", "si_avg IS NOT NULL"]
    params: list[Any] = [args.furnace_no]
    if args.date_from:
        clauses.append("work_date >= %s")
        params.append(args.date_from)
    if args.date_to:
        clauses.append("work_date <= %s")
        params.append(args.date_to)
    if args.meltno_from:
        clauses.append("meltno >= %s")
        params.append(args.meltno_from)
    if args.meltno_to:
        clauses.append("meltno <= %s")
        params.append(args.meltno_to)
    params.append(max(1, min(args.limit, 500)))
    sql = f"""
        SELECT meltno, furnace_no, work_date, open_ts, close_ts, si_avg
        FROM bf_assistant.heat_performance_quality_summary
        WHERE {' AND '.join(clauses)}
        ORDER BY open_ts
        LIMIT %s
    """
    ns = _ns(args.local_tunnel_port)
    with tunnel_builder.sensor_ssh_tunnel(ns) as (port, client):
        pg = tunnel_builder.remote_sensor_params(ns, port, client)
        pg["options"] = "-c default_transaction_read_only=on -c statement_timeout=30000"
        with psycopg.connect(**pg, row_factory=dict_row) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]


def run_atomic(args: argparse.Namespace, meltno: str, cutoff: pd.Timestamp) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ATOMIC),
        "--target-meltno",
        meltno,
        "--cutoff-ts",
        cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "--output-dir",
        str(args.atomic_output_dir),
        "--windows-minutes",
        args.windows_minutes,
    ]
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return extract_json(completed.stdout)


def write_outputs(records: list[dict[str, Any]], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl = output_dir / "open_minus_si_predictions.jsonl"
    csv_path = output_dir / "open_minus_si_predictions.csv"
    with jsonl.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    if records:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
    return {"jsonl": jsonl, "csv": csv_path}


def plot(records: list[dict[str, Any]], output_path: Path, lead_minutes: int) -> None:
    if not records:
        return
    frame = pd.DataFrame(records)
    frame["open_ts"] = pd.to_datetime(frame["open_ts"])
    for column in ("prediction_si", "actual_si_mean", "p10", "p90"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    font = chinese_font()
    fig, ax = plt.subplots(figsize=(16, 7), dpi=160)
    x = range(len(frame))
    ax.fill_between(x, frame["p10"], frame["p90"], color="#77aadd", alpha=0.16, label="P10-P90经验区间")
    ax.plot(x, frame["actual_si_mean"], marker="o", linewidth=1.8, label="实际平均Si")
    ax.plot(x, frame["prediction_si"], marker="s", linewidth=1.6, label=f"开口前{lead_minutes}分钟预测Si")
    ax.set_xticks(list(x))
    ax.set_xticklabels(frame["target_meltno"], rotation=45, ha="right", fontproperties=font)
    ax.set_ylabel("平均Si（%）", fontproperties=font)
    ax.set_title(f"每炉开口前{lead_minutes}分钟平均Si预测 vs 实际", fontproperties=font)
    ax.grid(alpha=0.25)
    ax.legend(prop=font)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch predict each heat at open_ts minus a fixed lead time.")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--meltno-from")
    parser.add_argument("--meltno-to")
    parser.add_argument("--furnace-no", default="2")
    parser.add_argument("--lead-minutes", type=int, default=60)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--windows-minutes", default="30,60,120,240,360,480")
    parser.add_argument("--local-tunnel-port", type=int, default=15440)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--atomic-output-dir", type=Path, default=DEFAULT_OUT / "atomic")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.atomic_output_dir.mkdir(parents=True, exist_ok=True)
    targets = fetch_targets(args)
    records: list[dict[str, Any]] = []
    for target in targets:
        open_ts = pd.Timestamp(target["open_ts"])
        cutoff = open_ts - pd.Timedelta(minutes=args.lead_minutes)
        result = run_atomic(args, str(target["meltno"]), cutoff)
        record = compact_record(result)
        record["open_ts"] = str(open_ts)
        record["lead_minutes"] = args.lead_minutes
        records.append(record)
        print(json.dumps(record, ensure_ascii=False, default=str), flush=True)
    paths = write_outputs(records, args.output_dir)
    plot_path = args.output_dir / "open_minus_si_predictions.png"
    plot(records, plot_path, args.lead_minutes)
    print(json.dumps({
        "ok": True,
        "heats": len(records),
        "jsonl": str(paths["jsonl"]),
        "csv": str(paths["csv"]),
        "plot": str(plot_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
