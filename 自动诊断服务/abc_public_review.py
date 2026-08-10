"""Production-safe sensor review details for ABC33 operator pages.

This module deliberately exposes physical measurements and plain-language
trend semantics only.  Formula text, weights, exact trigger thresholds,
normalized contributions and internal feature keys stay in the admin contract.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from abc_feature_builder import BODY_POINT_NAMES
from abc_rule_catalog import RULE_BY_ID


COOLING_NAMES = (
    "Q_soft_water", "P_soft_water", "Q_high_pressure_water",
    "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel",
)
TOP_NAMES = (
    "T_top_A", "T_top_B", "T_top_C", "T_top_D",
    "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D", "P_top",
)
COMMON_LABELS = {
    "Q_soft_water": "软水流量", "P_soft_water": "软水压力",
    "Q_high_pressure_water": "高压水流量", "P_high_pressure_water": "高压水压力",
    "P_medium_pressure_water": "中压水压力", "ExpansionTankLevel": "膨胀罐液位",
    "T_top_A": "顶温A", "T_top_B": "顶温B", "T_top_C": "顶温C", "T_top_D": "顶温D",
    "P_top_gas_A": "上升管压力A", "P_top_gas_B": "上升管压力B",
    "P_top_gas_C": "上升管压力C", "P_top_gas_D": "上升管压力D", "P_top": "综合顶压",
    "DP_total": "全炉压差", "DP_upper": "上部压差", "DP_lower": "下部压差",
    "PI": "透气性指数", "Q_blast": "冷风流量", "P_blast": "热风压力",
    "P_blast_cold": "冷风压力", "T_taphole_1": "1号铁口温度",
    "T_taphole_2": "2号铁口温度", "L": "料线", "L_south": "南探尺料线",
    "L_north": "北探尺料线", "GasUtil": "煤气利用率", "PCI_rate": "实际喷煤速率",
    "PCI_set": "喷煤设定", "O2_rate": "富氧率", "Q_O2": "富氧流量",
}
UNITS = {
    "Q_soft_water": "m³/h", "Q_high_pressure_water": "m³/h", "Q_blast": "m³/min",
    "P_soft_water": "MPa", "P_high_pressure_water": "MPa", "P_medium_pressure_water": "MPa",
    "ExpansionTankLevel": "%", "P_top": "kPa", "DP_total": "kPa", "DP_upper": "kPa",
    "DP_lower": "kPa", "P_blast": "kPa", "P_blast_cold": "kPa", "PI": "-",
    "GasUtil": "%", "PCI_rate": "t/h", "PCI_set": "t/h", "O2_rate": "%", "Q_O2": "m³/min",
    "L": "m", "L_south": "m", "L_north": "m",
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _align_ts(value: datetime, reference: datetime) -> datetime:
    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is None:
        return value.replace(tzinfo=None)
    return value


def _label(name: str) -> str:
    match = re.fullmatch(r"T_body_L(\d+)_([A-H])", name)
    if match:
        return f"炉身第{match.group(1)}层{match.group(2)}点温度"
    return COMMON_LABELS.get(name, name)


def _unit(name: str) -> str:
    if name.startswith("T_"):
        return "°C"
    if name.startswith("P_top_gas_"):
        return "kPa"
    return UNITS.get(name, "")


def variables_for_rule(rule_id: str) -> list[str]:
    spec = RULE_BY_ID[rule_id]
    values = list(spec.primary_sensors)
    if rule_id in {"C4", "C5", "C7"}:
        values = [*BODY_POINT_NAMES, *COOLING_NAMES, *TOP_NAMES, "DP_total", "DP_lower", "PI", "T_taphole_1", "T_taphole_2"]
    return list(dict.fromkeys(str(value) for value in values if value and not str(value).endswith("Risk")))


def _nearest_before(samples: Sequence[tuple[datetime, float]], target: datetime, tolerance_minutes: int = 5) -> float | None:
    candidates = [(ts, value) for ts, value in samples if ts <= target and ts >= target - timedelta(minutes=tolerance_minutes)]
    return candidates[-1][1] if candidates else None


def _window_values(samples: Sequence[tuple[datetime, float]], end: datetime, minutes: int) -> list[float]:
    start = end - timedelta(minutes=minutes)
    return [value for ts, value in samples if start <= ts <= end]


def _fmt(value: float | None, digits: int = 2) -> str:
    return "无数据" if value is None else f"{value:.{digits}f}"


def _semantic(metric: Mapping[str, Any]) -> str:
    unit = str(metric.get("unit") or "")
    current = _number(metric.get("current_value"))
    median = _number((metric.get("baseline") or {}).get("median"))
    z_value = _number(metric.get("relative_to_baseline_iqr"))
    pieces = [f"当前{_fmt(current)}{unit}"]
    if median is not None and current is not None:
        direction = "高于" if current >= median else "低于"
        pieces.append(f"{direction}30日中位数{abs(current-median):.2f}{unit}")
        if z_value is not None:
            pieces.append(f"相当于{abs(z_value):.2f}个历史四分位距")
    for minutes in (15, 30, 60):
        delta = _number((metric.get("changes") or {}).get(str(minutes)))
        if delta is not None:
            direction = "增加" if delta > 0 else "降低" if delta < 0 else "不变"
            pieces.append(f"{minutes}分钟{direction}{abs(delta):.2f}{unit}")
    volatility = metric.get("volatility") or {}
    ratios = [(minutes, _number((volatility.get(str(minutes)) or {}).get("baseline_multiple"))) for minutes in (15, 30, 60)]
    ratios = [(minutes, ratio) for minutes, ratio in ratios if ratio is not None]
    if ratios:
        minutes, ratio = max(ratios, key=lambda item: item[1])
        pieces.append(f"{minutes}分钟波动为历史典型波动的{ratio:.2f}倍")
    return "；".join(pieces) + "。"


def _metric(name: str, samples: Sequence[tuple[datetime, float]], baseline: Mapping[str, Any] | None, evaluation_ts: datetime) -> dict[str, Any]:
    valid = [(_align_ts(ts, evaluation_ts), value) for ts, raw in samples if (value := _number(raw)) is not None and _align_ts(ts, evaluation_ts) <= evaluation_ts]
    current_ts, current = valid[-1] if valid else (None, None)
    changes: dict[str, float | None] = {}
    volatility: dict[str, dict[str, float | None]] = {}
    baseline = dict(baseline or {})
    median = _number(baseline.get("median_ref"))
    iqr = _number(baseline.get("iqr_ref"))
    historical_sigma = iqr / 1.349 if iqr is not None and iqr > 0 else None
    for minutes in (15, 30, 60):
        prior = _nearest_before(valid, evaluation_ts - timedelta(minutes=minutes))
        changes[str(minutes)] = current - prior if current is not None and prior is not None else None
        values = _window_values(valid, evaluation_ts, minutes)
        std_value = pstdev(values) if len(values) >= 2 else None
        volatility[str(minutes)] = {
            "sample_count": len(values), "std": std_value,
            "baseline_multiple": std_value / historical_sigma if std_value is not None and historical_sigma else None,
        }
    metric = {
        "variable_name": name, "label": _label(name), "unit": _unit(name),
        "current_value": current, "timestamp": current_ts,
        "data_age_seconds": (evaluation_ts-current_ts).total_seconds() if current_ts else None,
        "changes": changes,
        "window_means": {
            str(minutes): (mean(values) if (values := _window_values(valid, evaluation_ts, minutes)) else None)
            for minutes in (15, 30, 60)
        },
        "volatility": volatility,
        "baseline": {
            "baseline_day": baseline.get("baseline_day"), "median": median, "iqr": iqr,
            "p25": _number(baseline.get("p25")), "p75": _number(baseline.get("p75")),
            "coverage_ratio": _number(baseline.get("coverage_ratio")), "sample_count": baseline.get("sample_count"),
        },
        "relative_to_baseline_iqr": (current-median)/iqr if current is not None and median is not None and iqr else None,
        "series_60m": [{"ts": ts, "value": value} for ts, value in valid if ts >= evaluation_ts-timedelta(minutes=60)],
    }
    missing: list[str] = []
    if current is None:
        missing.append("当前值缺失")
    if median is None or iqr is None or iqr <= 0:
        missing.append("30日基线缺失或无有效离散度")
    if current_ts and (evaluation_ts-current_ts).total_seconds() > 300:
        missing.append("数据超过5分钟未更新")
    metric["data_state"] = "needs_data" if missing else "available"
    metric["missing_reasons"] = missing
    metric["semantic_summary"] = _semantic(metric)
    metric["review_priority"] = abs(_number(metric.get("relative_to_baseline_iqr")) or 0) + max(
        (_number((item or {}).get("baseline_multiple")) or 0) for item in volatility.values()
    )
    return metric


def build_public_review(conn: Any, rule_id: str, evaluation_ts: datetime) -> dict[str, Any]:
    variables = variables_for_rule(rule_id)
    rows = conn.execute(
        """
        SELECT r.variable_name, v.ts, avg(v.value)::double precision AS value
        FROM bf_sensor.one_minute_values v
        JOIN bf_sensor.sensor_registry r ON r.tag_long_name=v.tag_long_name
        WHERE r.variable_name=ANY(%s) AND v.ts>%s AND v.ts<=%s
        GROUP BY r.variable_name,v.ts ORDER BY r.variable_name,v.ts
        """,
        (variables, evaluation_ts-timedelta(minutes=65), evaluation_ts),
    ).fetchall()
    history: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        item = dict(row) if isinstance(row, Mapping) else {"variable_name": row[0], "ts": row[1], "value": row[2]}
        value = _number(item.get("value"))
        if value is not None:
            history[str(item["variable_name"])].append((item["ts"], value))
    baseline_rows = conn.execute(
        """
        SELECT DISTINCT ON(variable_name) variable_name,baseline_day,median_ref,iqr_ref,p25,p75,coverage_ratio,sample_count
        FROM bf_sensor.daily_baselines
        WHERE baseline_days=30 AND baseline_day<=%s AND variable_name=ANY(%s)
        ORDER BY variable_name,baseline_day DESC
        """,
        (evaluation_ts.date(), variables),
    ).fetchall()
    baselines: dict[str, dict[str, Any]] = {}
    for row in baseline_rows:
        item = dict(row) if isinstance(row, Mapping) else {
            "variable_name": row[0], "baseline_day": row[1], "median_ref": row[2], "iqr_ref": row[3],
            "p25": row[4], "p75": row[5], "coverage_ratio": row[6], "sample_count": row[7],
        }
        baselines[str(item["variable_name"])] = item
    metrics = [_metric(name, history.get(name, []), baselines.get(name), evaluation_ts) for name in variables]
    ranked = sorted(metrics, key=lambda item: float(item.get("review_priority") or 0), reverse=True)
    main = ranked[:8]
    body = [item for item in metrics if str(item["variable_name"]).startswith("T_body_L")]
    cooling = [item for item in metrics if item["variable_name"] in COOLING_NAMES]
    other = [item for item in metrics if item not in body and item not in cooling]
    return {
        "schema_version": "furnace_rule_sensor_review.v2",
        "main_metrics": main,
        "body_metrics": body,
        "cooling_metrics": cooling,
        "other_metrics": other,
        "metric_count": len(metrics),
        "available_count": sum(1 for item in metrics if item["data_state"] == "available"),
        "missing_count": sum(1 for item in metrics if item["data_state"] != "available"),
        "data_semantics": "变化量均为当前值减去对应时刻实测值；波动倍数以当前窗口标准差与30日IQR换算的典型波动比较。",
    }
