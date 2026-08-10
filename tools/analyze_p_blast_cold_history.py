#!/usr/bin/env python3
"""Read-only analysis of P_blast_cold stability and step changes.

The report intentionally labels detected jumps as candidate operator-adjustment
intervals. It does not claim causality unless a separate operator log is joined.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import dict_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("GL02_PGHOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("GL02_PGPORT", "5432")))
    parser.add_argument("--database", default=os.getenv("GL02_PGDATABASE", "bf_trend"))
    parser.add_argument("--user", default=os.getenv("GL02_PGUSER", ""))
    parser.add_argument("--password", default=os.getenv("GL02_PGPASSWORD", ""))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out-prefix", default="logs/p_blast_cold_history_analysis")
    return parser.parse_args()


def analyze(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {"ok": False, "reason": "no_rows"}
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last")
    frame = frame.set_index("ts")["value"].astype(float).sort_index()
    sampled = frame.resample("5min").median().dropna()
    diffs = sampled.diff().dropna()
    abs_diffs = diffs.abs()
    q1, median, q3 = (float(frame.quantile(q)) for q in (0.25, 0.5, 0.75))
    mean = float(frame.mean())
    std = float(frame.std(ddof=0))
    iqr = q3 - q1
    q95_diff = float(abs_diffs.quantile(0.95)) if len(abs_diffs) else 0.0
    q99_diff = float(abs_diffs.quantile(0.99)) if len(abs_diffs) else 0.0
    jump_threshold = max(2.0, q99_diff * 2.0, q95_diff + max(0.5, iqr * 0.05))
    rolling_std = sampled.rolling(6, min_periods=3).std(ddof=0)
    stable_mask = rolling_std <= max(0.75, q99_diff * 0.5)
    stable_ratio = float(stable_mask.mean()) if len(stable_mask) else 0.0
    jumps = []
    for ts, delta in diffs.items():
        if abs(float(delta)) < jump_threshold:
            continue
        before = sampled.loc[:ts].iloc[:-1].tail(6)
        after_30m = sampled.loc[ts:].head(6)
        after_2h = sampled.loc[ts:].head(24)
        if before.empty or after_30m.empty:
            continue
        before_median = float(before.median())
        after_median = float(after_30m.median())
        hold_median = float(after_2h.median()) if not after_2h.empty else None
        hold_std = float(after_2h.std(ddof=0)) if len(after_2h) > 1 else 0.0
        jumps.append(
            {
                "timestamp": ts.isoformat(),
                "delta_kpa": round(float(delta), 4),
                "before_median_kpa": round(before_median, 4),
                "after_30m_median_kpa": round(after_median, 4),
                "after_2h_median_kpa": round(hold_median, 4) if hold_median is not None else None,
                "after_2h_std_kpa": round(hold_std, 4),
                "candidate_adjustment": bool(
                    abs(after_median - before_median) >= jump_threshold
                    and hold_std <= max(1.0, jump_threshold / 2)
                ),
            }
        )
    last_quarter = sampled.tail(max(1, len(sampled) // 4))
    prior = sampled.iloc[: max(1, len(sampled) - len(last_quarter))]
    tail_shift = float(last_quarter.median() - prior.median()) if not prior.empty else 0.0
    return {
        "ok": True,
        "sample_count": int(len(frame)),
        "resampled_5min_count": int(len(sampled)),
        "time_start": frame.index.min().isoformat(),
        "time_end": frame.index.max().isoformat(),
        "current_kpa": round(float(frame.iloc[-1]), 4),
        "min_kpa": round(float(frame.min()), 4),
        "max_kpa": round(float(frame.max()), 4),
        "mean_kpa": round(mean, 4),
        "std_kpa": round(std, 4),
        "q1_kpa": round(q1, 4),
        "median_kpa": round(median, 4),
        "q3_kpa": round(q3, 4),
        "stable_ratio_5min_windows": round(stable_ratio, 4),
        "jump_threshold_kpa": round(jump_threshold, 4),
        "p95_abs_5min_delta_kpa": round(q95_diff, 4),
        "p99_abs_5min_delta_kpa": round(q99_diff, 4),
        "last_quarter_median_shift_kpa": round(tail_shift, 4),
        "jumps": jumps,
    }


def main() -> None:
    args = parse_args()
    if not args.user:
        raise SystemExit("--user or GL02_PGUSER is required")
    end = datetime.now()
    start = end - timedelta(days=max(1, args.days))
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=args.password,
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:
        mapping = conn.execute(
            """
            SELECT tag_long_name
            FROM bf_sensor.sensor_registry
            WHERE variable_name = 'P_blast_cold' AND is_enabled = true
            ORDER BY is_derived ASC, tag_long_name
            LIMIT 1
            """
        ).fetchone()
        if not mapping:
            raise SystemExit("P_blast_cold is not enabled in bf_sensor.sensor_registry")
        tag = mapping["tag_long_name"]
        rows = conn.execute(
            """
            SELECT ts, value
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = %s AND ts >= %s AND ts <= %s
            ORDER BY ts ASC
            """,
            (tag, start, end),
        ).fetchall()
    frame = pd.DataFrame(rows)
    result = analyze(frame)
    result["variable"] = "P_blast_cold"
    result["tag_long_name"] = tag
    result["window_days"] = args.days
    result["generated_at"] = datetime.now().isoformat()
    prefix = Path(args.out_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# P_blast_cold历史稳定性分析",
        "",
        f"- 数据窗口：{result.get('time_start', '--')} 至 {result.get('time_end', '--')}",
        f"- 变量标签：{tag}",
        f"- 样本数：{result.get('sample_count', 0)}（5分钟重采样 {result.get('resampled_5min_count', 0)}）",
        f"- Q1/中位数/Q3：{result.get('q1_kpa', '--')} / {result.get('median_kpa', '--')} / {result.get('q3_kpa', '--')} kPa",
        f"- 均值±标准差：{result.get('mean_kpa', '--')} ± {result.get('std_kpa', '--')} kPa",
        f"- 5分钟窗口稳定比例：{float(result.get('stable_ratio_5min_windows', 0)) * 100:.1f}%",
        f"- 末四分之一窗口相对前段中位数变化：{result.get('last_quarter_median_shift_kpa', '--')} kPa",
        f"- 跃升检测阈值：{result.get('jump_threshold_kpa', '--')} kPa",
        "",
        "## 候选跃升点",
        "",
        "| 时间 | 5分钟变化 | 之前中位数 | 后30分钟中位数 | 后2小时中位数 | 后2小时标准差 | 候选调风时间 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in result.get("jumps", []):
        lines.append(
            f"| {item['timestamp']} | {item['delta_kpa']} | {item['before_median_kpa']} | "
            f"{item['after_30m_median_kpa']} | {item['after_2h_median_kpa']} | "
            f"{item['after_2h_std_kpa']} | {'是' if item['candidate_adjustment'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "> 说明：候选调风时间只表示数据形态与人工调节相似；若要确认是高炉长操作，需再与操作记录或指导留痕按时间关联，不能仅凭压力曲线断言。",
        ]
    )
    prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
