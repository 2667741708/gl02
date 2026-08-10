#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Evaluate the MES Web operation-log fuel-ratio Si rule.

This script intentionally reads the original MES Web report HTML files
(`mes/jn_ts_glbb_tb.sht`) downloaded from the report server. It does not query
pSpace. The report stores many displayed values as client-side Raqsoft cells,
so we reconstruct the fuel-ratio formula from the report's own JavaScript
formulas instead of relying on already-rendered text.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup


CELL_PREFIX = "sg2170_"
HOUR_ROWS = list(range(7, 15)) + list(range(16, 24)) + list(range(25, 33))


@dataclass
class HourRow:
    report_date: str
    hour_label: int
    batch_count: float | None
    ore_batch: float | None
    coke_batch: float | None
    nut_coke_batch: float | None
    coke_moisture: float | None
    coal_kg: float | None
    coal_ratio: float | None
    fuel_ratio: float | None


@dataclass
class ReportDay:
    date: str
    path: str
    report_id: str | None
    heat_no: str | None
    heat_open_ts: datetime | None
    heat_close_ts: datetime | None
    actual_si: float | None
    hourly: dict[int, HourRow]
    daily_fuel_mean: float | None


def col_name(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def clean_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("%", "")
    if text in {"-", "—", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def cell_text(soup: BeautifulSoup, ref: str) -> str:
    tag = soup.find(id=f"{CELL_PREFIX}{ref}")
    if tag is None:
        return ""
    value = tag.get("value")
    if value is not None:
        return str(value).strip()
    return tag.get_text(strip=True)


def parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def calc_hour_row(soup: BeautifulSoup, report_date: str, row_index: int) -> HourRow | None:
    hour_label = clean_float(cell_text(soup, f"A{row_index}"))
    if hour_label is None or not float(hour_label).is_integer():
        return None
    hour_label_int = int(hour_label)
    if hour_label_int < 1 or hour_label_int > 24:
        return None

    batch_count = clean_float(cell_text(soup, f"D{row_index}"))
    ore_batch = clean_float(cell_text(soup, f"F{row_index}"))
    coke_batch = clean_float(cell_text(soup, f"G{row_index}"))
    nut_coke_batch = clean_float(cell_text(soup, f"H{row_index}"))
    coke_moisture = clean_float(cell_text(soup, f"I{row_index}"))
    coal_kg = clean_float(cell_text(soup, f"J{row_index}"))

    grade_constant = clean_float(cell_text(soup, "G5"))
    yield_constant = clean_float(cell_text(soup, "I5"))
    metal_yield = None
    if ore_batch is not None and grade_constant is not None and yield_constant:
        metal_yield = ore_batch * grade_constant / yield_constant * 0.995

    coal_ratio = None
    if coal_kg is not None and batch_count and metal_yield:
        # Raqsoft formula K row:
        # J/1000/D/(F*G5/I5*0.995)*1000
        coal_ratio = coal_kg / 1000.0 / batch_count / metal_yield * 1000.0

    fuel_ratio = None
    if (
        coke_batch is not None
        and nut_coke_batch is not None
        and coke_moisture is not None
        and metal_yield
        and coal_ratio is not None
    ):
        # Raqsoft formula M row:
        # (G*(1-I)+H*(1-I))/(F*G5/I5*0.995/1000)+K
        dry_coke = coke_batch * (1.0 - coke_moisture)
        dry_nut_coke = nut_coke_batch * (1.0 - coke_moisture)
        fuel_ratio = (dry_coke + dry_nut_coke) / (metal_yield / 1000.0) + coal_ratio

    return HourRow(
        report_date=report_date,
        hour_label=hour_label_int,
        batch_count=batch_count,
        ore_batch=ore_batch,
        coke_batch=coke_batch,
        nut_coke_batch=nut_coke_batch,
        coke_moisture=coke_moisture,
        coal_kg=coal_kg,
        coal_ratio=coal_ratio,
        fuel_ratio=fuel_ratio,
    )


def parse_report(path: Path) -> ReportDay:
    match = re.search(r"(\d{8})", path.name)
    if not match:
        raise ValueError(f"Cannot infer report date from filename: {path}")
    date_token = match.group(1)
    report_date = datetime.strptime(date_token, "%Y%m%d").date().isoformat()

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    hourly: dict[int, HourRow] = {}
    for row_index in HOUR_ROWS:
        hour = calc_hour_row(soup, report_date, row_index)
        if hour:
            hourly[hour.hour_label] = hour

    fuel_values = [row.fuel_ratio for row in hourly.values() if row.fuel_ratio is not None]
    daily_fuel_mean = statistics.fmean(fuel_values) if fuel_values else None

    return ReportDay(
        date=report_date,
        path=str(path),
        report_id=cell_text(soup, "A2") or None,
        heat_no=cell_text(soup, "A38") or None,
        heat_open_ts=parse_datetime(cell_text(soup, "G38")),
        heat_close_ts=parse_datetime(cell_text(soup, "J38")),
        actual_si=clean_float(cell_text(soup, "AJ38")),
        hourly=hourly,
        daily_fuel_mean=daily_fuel_mean,
    )


def previous_full_hour_labels(cutoff_ts: datetime, count: int = 4) -> list[tuple[str, int]]:
    cutoff_hour = cutoff_ts.replace(minute=0, second=0, microsecond=0)
    labels: list[tuple[str, int]] = []
    end_ts = cutoff_hour
    for _ in range(count):
        if end_ts.hour == 0:
            report_day = (end_ts.date() - timedelta(days=1)).isoformat()
            label = 24
        else:
            report_day = end_ts.date().isoformat()
            label = end_ts.hour
        labels.append((report_day, label))
        end_ts -= timedelta(hours=1)
    labels.reverse()
    return labels


def mean(values: Iterable[float | None]) -> float | None:
    real = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.fmean(real) if real else None


def evaluate(days: list[ReportDay], baseline_si: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_date = {day.date: day for day in days}
    rows: list[dict[str, Any]] = []

    for day in days:
        if day.heat_open_ts is None or day.actual_si is None:
            continue

        report_date = datetime.strptime(day.date, "%Y-%m-%d").date()
        prev_1 = (report_date - timedelta(days=1)).isoformat()
        prev_2 = (report_date - timedelta(days=2)).isoformat()
        prev_days = [by_date.get(prev_2), by_date.get(prev_1)]
        if not all(prev_days):
            continue

        baseline_fuel = mean(prev.daily_fuel_mean for prev in prev_days if prev)
        if baseline_fuel is None:
            continue

        hour_labels = previous_full_hour_labels(day.heat_open_ts, count=4)
        hour_values: list[float | None] = []
        for label_date, label_hour in hour_labels:
            label_day = by_date.get(label_date)
            hour_values.append(label_day.hourly.get(label_hour).fuel_ratio if label_day and label_hour in label_day.hourly else None)
        current_4h_fuel = mean(hour_values)
        if current_4h_fuel is None:
            continue

        rolling_si_baseline = mean(prev.actual_si for prev in prev_days if prev)
        fixed_prediction = baseline_si + ((current_4h_fuel - baseline_fuel) / 5.0) * 0.1
        rolling_prediction = None
        if rolling_si_baseline is not None:
            rolling_prediction = rolling_si_baseline + ((current_4h_fuel - baseline_fuel) / 5.0) * 0.1

        row = {
            "report_date": day.date,
            "report_id": day.report_id,
            "heat_no": day.heat_no,
            "heat_open_ts": day.heat_open_ts.isoformat(sep=" "),
            "actual_si": day.actual_si,
            "baseline_fuel_prev2d": baseline_fuel,
            "current_prev4h_fuel": current_4h_fuel,
            "fuel_delta": current_4h_fuel - baseline_fuel,
            "baseline_si_fixed": baseline_si,
            "prediction_fixed030": fixed_prediction,
            "abs_error_fixed030": abs(fixed_prediction - day.actual_si),
            "hit005_fixed030": abs(fixed_prediction - day.actual_si) <= 0.05,
            "hit002_fixed030": abs(fixed_prediction - day.actual_si) <= 0.02,
            "baseline_si_prev2_reports": rolling_si_baseline,
            "prediction_rolling2d_si": rolling_prediction,
            "abs_error_rolling2d_si": abs(rolling_prediction - day.actual_si) if rolling_prediction is not None else None,
            "hit005_rolling2d_si": abs(rolling_prediction - day.actual_si) <= 0.05 if rolling_prediction is not None else None,
            "hit002_rolling2d_si": abs(rolling_prediction - day.actual_si) <= 0.02 if rolling_prediction is not None else None,
            "prediction_constant030": baseline_si,
            "abs_error_constant030": abs(baseline_si - day.actual_si),
            "hit005_constant030": abs(baseline_si - day.actual_si) <= 0.05,
            "hit002_constant030": abs(baseline_si - day.actual_si) <= 0.02,
            "prediction_prev2_si_baseline": rolling_si_baseline,
            "abs_error_prev2_si_baseline": abs(rolling_si_baseline - day.actual_si) if rolling_si_baseline is not None else None,
            "hit005_prev2_si_baseline": abs(rolling_si_baseline - day.actual_si) <= 0.05 if rolling_si_baseline is not None else None,
            "hit002_prev2_si_baseline": abs(rolling_si_baseline - day.actual_si) <= 0.02 if rolling_si_baseline is not None else None,
            "prev4h_labels": ";".join(f"{d}#{h:02d}" for d, h in hour_labels),
            "source": "MES Web report mes/jn_ts_glbb_tb.sht",
        }
        rows.append(row)

    metrics = {
        "sample_count": len(rows),
        "source": "MES Web report mes/jn_ts_glbb_tb.sht",
        "method_fixed030": summarize_metric(rows, "abs_error_fixed030", "hit005_fixed030", "hit002_fixed030"),
        "method_rolling2d_si": summarize_metric(rows, "abs_error_rolling2d_si", "hit005_rolling2d_si", "hit002_rolling2d_si"),
        "baseline_constant030": summarize_metric(rows, "abs_error_constant030", "hit005_constant030", "hit002_constant030"),
        "baseline_prev2_report_si": summarize_metric(rows, "abs_error_prev2_si_baseline", "hit005_prev2_si_baseline", "hit002_prev2_si_baseline"),
        "diagnostic_ols_on_prev4h_fuel_delta": ols_diagnostic(rows),
        "note": "Each downloaded daily operation-log HTML exposes one furnace/tap block at row 38; this evaluation therefore uses one report heat per day, not all heats.",
    }
    return rows, metrics


def summarize_metric(rows: list[dict[str, Any]], error_key: str, hit005_key: str, hit002_key: str) -> dict[str, Any]:
    errors = [row[error_key] for row in rows if row.get(error_key) is not None]
    hit005 = [row[hit005_key] for row in rows if row.get(hit005_key) is not None]
    hit002 = [row[hit002_key] for row in rows if row.get(hit002_key) is not None]
    if not errors:
        return {"sample_count": 0}
    return {
        "sample_count": len(errors),
        "mae": statistics.fmean(errors),
        "rmse": math.sqrt(statistics.fmean([e * e for e in errors])),
        "hit005": sum(1 for v in hit005 if v) / len(hit005) if hit005 else None,
        "hit002": sum(1 for v in hit002 if v) / len(hit002) if hit002 else None,
        "max_abs_error": max(errors),
    }


def ols_diagnostic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (row.get("fuel_delta"), row.get("actual_si"))
        for row in rows
        if row.get("fuel_delta") is not None and row.get("actual_si") is not None
    ]
    if len(pairs) < 3:
        return {"sample_count": len(pairs)}
    x = [float(pair[0]) for pair in pairs]
    y = [float(pair[1]) for pair in pairs]
    xbar = statistics.fmean(x)
    ybar = statistics.fmean(y)
    var_x = sum((value - xbar) ** 2 for value in x)
    var_y = sum((value - ybar) ** 2 for value in y)
    if var_x <= 0 or var_y <= 0:
        return {"sample_count": len(pairs)}
    cov = sum((xv - xbar) * (yv - ybar) for xv, yv in zip(x, y))
    slope = cov / var_x
    intercept = ybar - slope * xbar
    predictions = [intercept + slope * value for value in x]
    errors = [abs(pred - actual) for pred, actual in zip(predictions, y)]

    loo_errors: list[float] = []
    for idx in range(len(x)):
        train_x = [value for j, value in enumerate(x) if j != idx]
        train_y = [value for j, value in enumerate(y) if j != idx]
        train_xbar = statistics.fmean(train_x)
        train_ybar = statistics.fmean(train_y)
        train_var_x = sum((value - train_xbar) ** 2 for value in train_x)
        if train_var_x <= 0:
            continue
        train_cov = sum((xv - train_xbar) * (yv - train_ybar) for xv, yv in zip(train_x, train_y))
        train_slope = train_cov / train_var_x
        train_intercept = train_ybar - train_slope * train_xbar
        loo_pred = train_intercept + train_slope * x[idx]
        loo_errors.append(abs(loo_pred - y[idx]))

    return {
        "sample_count": len(pairs),
        "in_sample_slope_si_per_kg": slope,
        "in_sample_kg_per_0p1_si": 0.1 / slope if abs(slope) > 1e-12 else None,
        "in_sample_intercept": intercept,
        "in_sample_correlation": cov / math.sqrt(var_x * var_y),
        "in_sample_mae": statistics.fmean(errors),
        "in_sample_rmse": math.sqrt(statistics.fmean([error * error for error in errors])),
        "in_sample_hit005": sum(error <= 0.05 for error in errors) / len(errors),
        "leave_one_out_mae": statistics.fmean(loo_errors) if loo_errors else None,
        "leave_one_out_rmse": math.sqrt(statistics.fmean([error * error for error in loo_errors])) if loo_errors else None,
        "leave_one_out_hit005": sum(error <= 0.05 for error in loo_errors) / len(loo_errors) if loo_errors else None,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_plot(rows: list[dict[str, Any]], path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    if not rows:
        return
    x = [row["report_date"] for row in rows]
    actual = [row["actual_si"] for row in rows]
    fixed = [row["prediction_fixed030"] for row in rows]
    rolling = [row["prediction_rolling2d_si"] for row in rows]

    plt.figure(figsize=(12, 5))
    plt.plot(x, actual, marker="o", linewidth=2.2, label="Actual Si from MES report")
    plt.plot(x, fixed, marker="s", linewidth=1.8, label="Fuel-ratio rule, baseline Si=0.30")
    if any(v is not None for v in rolling):
        plt.plot(x, rolling, marker="^", linewidth=1.6, label="Fuel-ratio rule, rolling 2-day Si")
    plt.axhline(0.20, color="#888888", linestyle="--", linewidth=0.8)
    plt.axhline(0.40, color="#888888", linestyle="--", linewidth=0.8)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Si (%)")
    plt.title("MES operation-log fuel-ratio Si rule audit")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--html-dir",
        default=r"PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\source_probe\imes_report_2d012_recent_days",
        help="Directory containing downloaded MES Web report HTML files.",
    )
    parser.add_argument(
        "--out-dir",
        default=r"PT\预测铁水Si含量\reports\experiments\EXP-SI-FUELRATIO-REPORT-20260808\fuel_ratio_rule_eval",
        help="Output directory.",
    )
    parser.add_argument("--baseline-si", type=float, default=0.30)
    args = parser.parse_args()

    html_dir = Path(args.html_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = [parse_report(path) for path in sorted(html_dir.glob("imes_report_2d012_*.html"))]
    rows, metrics = evaluate(reports, baseline_si=args.baseline_si)

    csv_path = out_dir / "fuel_ratio_rule_predictions.csv"
    json_path = out_dir / "fuel_ratio_rule_metrics.json"
    plot_path = out_dir / "fuel_ratio_rule_actual_vs_pred.png"
    reports_path = out_dir / "parsed_report_days.json"

    write_csv(rows, csv_path)
    json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    reports_path.write_text(
        json.dumps(
            [
                {
                    "date": day.date,
                    "path": day.path,
                    "report_id": day.report_id,
                    "heat_no": day.heat_no,
                    "heat_open_ts": day.heat_open_ts.isoformat(sep=" ") if day.heat_open_ts else None,
                    "actual_si": day.actual_si,
                    "daily_fuel_mean": day.daily_fuel_mean,
                    "hourly_count": len(day.hourly),
                }
                for day in reports
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_plot(rows, plot_path)

    print(json.dumps({"ok": True, "metrics": metrics, "csv": str(csv_path), "json": str(json_path), "plot": str(plot_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
