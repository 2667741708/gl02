"""Deterministic evidence builders for five-minute diagnosis AI explanations.

The language model is only an explanation layer.  This module owns the numeric
facts shown to operators: rule features, minute values, 30-day references,
read-only recommendation actions, and knowledge-document provenance.

Corresponding requirements:
- REQ-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805
- REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806
"""

from __future__ import annotations

import importlib
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DIAGNOSIS_LABELS = (
    "normal",
    "lowline",
    "edge",
    "center",
    "channel",
    "cold",
    "hot",
    "column",
)

DISPLAY_NAMES = {
    "normal": "正常顺行",
    "lowline": "低料线",
    "edge": "边缘煤气流发展",
    "center": "边缘不足/中心过吹",
    "channel": "管道行程",
    "cold": "热制度下行",
    "hot": "热制度上行",
    "column": "崩滑料/悬料",
}

VARIABLE_META: dict[str, tuple[str, str]] = {
    "P_top": ("综合顶压", "kPa"),
    "P_top_gas_A": ("顶压A点", "kPa"),
    "P_top_gas_B": ("顶压B点", "kPa"),
    "P_top_gas_C": ("顶压C点", "kPa"),
    "P_top_gas_D": ("顶压D点", "kPa"),
    "GasUtil": ("煤气利用率", "%"),
    "TFT": ("理论燃烧温度", "℃"),
    "T_blast": ("热风温度", "℃"),
    "T_top": ("综合顶温", "℃"),
    "T_top_A": ("顶温A点", "℃"),
    "T_top_B": ("顶温B点", "℃"),
    "T_top_C": ("顶温C点", "℃"),
    "T_top_D": ("顶温D点", "℃"),
    "Q_blast": ("冷风流量", "m³/min"),
    "P_blast_cold": ("冷风压力", "kPa"),
    "P_blast": ("热风压力", "kPa"),
    "O2_rate": ("富氧率", "%"),
    "Q_O2": ("氧气流量", "m³/h"),
    "PI": ("透气性指数", "m³/(min·kPa)"),
    "DP_upper": ("上部压差", "kPa"),
    "DP_lower": ("下部压差", "kPa"),
    "DP_total": ("全炉压差", "kPa"),
    "L": ("主料线", "m"),
    "L_south": ("南探尺料线", "m"),
    "L_north": ("北探尺料线", "m"),
    "PCI_rate": ("喷煤流量", "t/h"),
    "PCI_set": ("喷煤设定", "t/h"),
    "T_taphole_1": ("1号出铁口温度", "℃"),
    "T_taphole_2": ("2号出铁口温度", "℃"),
}

SENSOR_VARIABLES = tuple(VARIABLE_META)

# Fixed operator-facing order requested for the diagnosis evidence expander.
# Internal keys stay unchanged so rules, database rows and API compatibility are
# preserved.  T_top is read directly when available and otherwise derived from
# synchronous T_top_A-D minute values.
CORE_EVIDENCE_VARIABLES = (
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "P_top",
    "T_top",
    "Q_blast",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "PI",
    "DP_total",
    "DP_upper",
    "DP_lower",
    "GasUtil",
)

FOREMAN_KNOWLEDGE_DOC_ID = "bf_foreman_ops_v1"
FOREMAN_KNOWLEDGE_SOURCE_VERSION = "bf-foreman-knowledge-v1"


def _driver(
    driver_id: str,
    name: str,
    feature_keys: Sequence[str],
    variables: Sequence[str],
    mode: str,
    threshold: float,
    weight: float,
    *,
    aggregate: str = "first",
) -> dict[str, Any]:
    return {
        "id": driver_id,
        "name": name,
        "feature_keys": tuple(feature_keys),
        "variables": tuple(variables),
        "mode": mode,
        "threshold": threshold,
        "weight": weight,
        "aggregate": aggregate,
    }


# This catalog mirrors config/rule_weights.yaml and config/thresholds.yaml.  It
# names the rule inputs but deliberately does not recompute or replace scores.
RULE_DRIVERS: dict[str, tuple[dict[str, Any], ...]] = {
    "normal": (
        _driver("normal.top-pressure-stability", "顶压稳定", ["zstd_P_top"], ["P_top"], "stable_abs", 1.25, 18),
        _driver("normal.delta-pressure-stability", "压差稳定", ["zstd_DP_total"], ["DP_total"], "stable_abs", 1.25, 18),
        _driver("normal.permeability-stability", "透气性稳定", ["zstd_PI"], ["PI"], "stable_abs", 1.25, 18),
        _driver("normal.blast-pressure-stability", "风压稳定", ["zstd_P_blast"], ["P_blast"], "stable_abs", 1.25, 12),
        _driver("normal.top-temperature-dispersion", "顶温离散稳定", ["DispTop_15"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "stable_abs", 0.28, 12),
        _driver("normal.body-temperature-stability", "炉体温度稳定", ["zstd_T_body_lower", "zstd_T_body_middle", "zstd_T_body_upper"], [], "stable_abs", 1.25, 14, aggregate="p75"),
        _driver("normal.body-circumference-balance", "炉体圆周均衡", [f"T_body_circ_cv_L{layer}" for layer in range(7, 17)], [], "stable_abs", 0.38, 10, aggregate="p80"),
        _driver("normal.material-line-balance", "南北料线同步", ["L_diff_NS"], ["L_south", "L_north"], "stable_abs", 0.8, 8),
    ),
    "lowline": (
        _driver("lowline.depth", "低料线深度", ["DeltaL"], ["L", "L_south", "L_north"], "high", 0.5, 40),
        _driver("lowline.duration", "低料线持续", ["Dur_low"], ["L"], "high", 5, 10),
        _driver("lowline.top-temperature-rise", "顶温上升", ["z30_T_top_slope"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "high", 0.1, 15),
        _driver("lowline.upper-body-rise", "上部炉体温度升高", ["z60_T_body_upper"], [], "high", 0.8, 15),
        _driver("lowline.north-south-difference", "南北料线差", ["L_diff_NS"], ["L_south", "L_north"], "high", 0.25, 5),
        _driver("lowline.charging-fault", "上料故障信号", ["charge_fault_flag"], [], "boolean", 1, 15),
    ),
    "edge": (
        _driver("edge.upper-body-heat", "上部炉体热负荷", ["z60_T_body_upper"], [], "high", 0.8, 25),
        _driver("edge.middle-lower-heat", "中下部炉体热负荷", ["z60_T_body_middle", "z60_T_body_lower"], [], "high", 0.8, 20, aggregate="max"),
        _driver("edge.top-temperature-rise", "顶温上升", ["z30_T_top_slope"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "high", 0.1, 15),
        _driver("edge.hot-sector-bias", "圆周热点偏置", ["HotSectorScore"], [], "high", 15, 15),
        _driver("edge.top-temperature-dispersion", "顶温离散扩大", ["DispTop_15"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "high", 0.15, 10),
        _driver("edge.high-permeability", "透气性偏高", ["z60_PI"], ["PI"], "high", 0.8, 10),
        _driver("edge.low-gas-utilization", "煤气利用率偏低", ["z60_GasUtil"], ["GasUtil"], "low", -0.5, 5),
    ),
    "center": (
        _driver("center.low-body-wall-temperature", "炉墙温度偏低", ["z60_T_body_lower", "z60_T_body_middle", "z60_T_body_upper"], [], "low", -0.8, 25, aggregate="min"),
        _driver("center.high-total-delta-pressure", "全压差偏高", ["z60_DP_total"], ["DP_total"], "high", 0.8, 20),
        _driver("center.high-upper-delta-pressure", "上部压差偏高", ["z60_DP_upper"], ["DP_upper"], "high", 0.8, 15),
        _driver("center.high-blast-pressure", "风压偏高", ["z60_P_blast"], ["P_blast"], "high", 0.8, 15),
        _driver("center.low-permeability", "透气性下降", ["z60_PI"], ["PI"], "low", -0.8, 10),
        _driver("center.low-top-temperature", "顶温走低", ["z30_T_top_slope"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "low", -0.1, 10),
        _driver("center.static-pressure-unbalanced", "圆周静压力不均", ["P_top_gas_range_15"], ["P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"], "high", 8, 5),
    ),
    "channel": (
        _driver("channel.top-pressure-spikes", "顶压尖峰频次", ["SpikeTopP_15"], ["P_top"], "high", 1, 10),
        _driver("channel.pressure-oscillation", "压力振荡", ["zstd_P_top", "zstd_P_blast"], ["P_top", "P_blast"], "high", 1.0, 40, aggregate="max"),
        _driver("channel.hot-spot-jump", "炉体热点跳变", ["HotSpotJump"], [], "high", 0.8, 20),
        _driver("channel.top-temperature-dispersion", "顶温离散扩大", ["DispTop_15"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "high", 0.3, 15),
        _driver("channel.probe-abnormal", "探尺异常", ["probe_stall_flag"], ["L", "L_south", "L_north"], "boolean", 1, 10),
        _driver("channel.low-gas-utilization", "煤气利用率偏低", ["z60_GasUtil"], ["GasUtil"], "low", -0.5, 5),
    ),
    "cold": (
        _driver("cold.top-temperature-down", "顶温下降趋势", ["z30_T_top_slope"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "low", -0.1, 20),
        _driver("cold.low-body-temperature", "炉体温度偏低", ["z60_T_body_lower", "z60_T_body_middle", "z60_T_body_upper"], [], "low", -0.8, 20, aggregate="min"),
        _driver("cold.low-taphole-temperature", "出铁口温度代理偏低", ["z_T_taphole_mean", "z_T_taphole_max"], ["T_taphole_1", "T_taphole_2"], "low", -0.8, 15, aggregate="min"),
        _driver("cold.low-blast-pressure", "风压偏低", ["z60_P_blast"], ["P_blast"], "low", -0.8, 15),
        _driver("cold.high-permeability", "透气性偏高", ["z60_PI"], ["PI"], "high", 0.8, 10),
        _driver("cold.low-gas-utilization", "煤气利用率偏低", ["z60_GasUtil"], ["GasUtil"], "low", -0.5, 10),
        _driver("cold.operation-heat-reduction", "热量输入走低", ["z60_T_blast", "z60_PCI_rate", "z60_Q_O2"], ["T_blast", "PCI_rate", "Q_O2"], "low", -0.5, 10, aggregate="min"),
    ),
    "hot": (
        _driver("hot.top-temperature-rise", "顶温上升趋势", ["z30_T_top_slope"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "high", 0.1, 20),
        _driver("hot.high-body-temperature", "炉体温度偏高", ["z60_T_body_lower", "z60_T_body_middle", "z60_T_body_upper"], [], "high", 0.8, 20, aggregate="max"),
        _driver("hot.high-taphole-temperature", "出铁口温度代理偏高", ["z_T_taphole_mean", "z_T_taphole_max"], ["T_taphole_1", "T_taphole_2"], "high", 0.8, 15, aggregate="max"),
        _driver("hot.high-total-delta-pressure", "全压差偏高", ["z60_DP_total"], ["DP_total"], "high", 0.8, 15),
        _driver("hot.low-permeability", "透气性下降", ["z60_PI"], ["PI"], "low", -0.8, 10),
        _driver("hot.top-pressure-spikes", "顶压尖峰", ["SpikeTopP_15"], ["P_top"], "high", 1, 10),
        _driver("hot.operation-heat-increase", "热量输入走高", ["z60_T_blast", "z60_PCI_rate", "z60_Q_O2"], ["T_blast", "PCI_rate", "Q_O2"], "high", 0.5, 10, aggregate="max"),
    ),
    "column": (
        _driver("column.hang-stall", "悬料时探尺停滞", ["Dur_stall", "probe_stall_flag"], ["L", "L_south", "L_north"], "high", 1, 35, aggregate="max"),
        _driver("column.hang-delta-pressure-rise", "悬料时全压差升高", ["z60_DP_total"], ["DP_total"], "high", 0.8, 20),
        _driver("column.hang-blast-pressure-rise", "悬料时风压升高", ["z60_P_blast"], ["P_blast"], "high", 0.8, 15),
        _driver("column.hang-permeability-drop", "悬料时透气性下降", ["z60_PI"], ["PI"], "low", -0.8, 15),
        _driver("column.slip-drop", "崩滑料的料线突降", ["DropBatch"], ["L", "L_south", "L_north"], "high", 0.3, 40),
        _driver("column.slip-pressure-oscillation", "崩滑料伴随压力振荡", ["zstd_P_top", "zstd_P_blast"], ["P_top", "P_blast"], "high", 0.8, 20, aggregate="max"),
        _driver("column.slip-top-pressure-spike", "崩滑料伴随顶压尖峰", ["SpikeTopP_15"], ["P_top"], "high", 1, 15),
        _driver("column.slip-top-temperature-dispersion", "崩滑料伴随顶温离散", ["DispTop_15"], ["T_top_A", "T_top_B", "T_top_C", "T_top_D"], "high", 0.15, 15),
        _driver("column.slip-line-difference", "崩滑料伴随南北料线差", ["L_diff_NS"], ["L_south", "L_north"], "high", 0.25, 10),
    ),
}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _naive_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def build_variable_stats(
    sensor_rows: Iterable[Mapping[str, Any]],
    baseline_rows: Iterable[Mapping[str, Any]],
    diagnosis_ts: object,
) -> dict[str, dict[str, Any]]:
    """Build operator-facing 5/60-minute and baseline facts from read-only rows."""
    end = _naive_datetime(diagnosis_ts)
    grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in sensor_rows:
        variable = str(row.get("variable_name") or "")
        value = _finite(row.get("value"))
        if variable not in VARIABLE_META or value is None:
            continue
        try:
            ts = _naive_datetime(row.get("ts"))
        except (TypeError, ValueError):
            continue
        if end - timedelta(minutes=60) <= ts <= end:
            grouped[variable].append((ts, value))

    value_sources = {variable: "direct_sensor" for variable in grouped}
    if not grouped.get("T_top"):
        top_by_ts: dict[datetime, list[float]] = defaultdict(list)
        for variable in ("T_top_A", "T_top_B", "T_top_C", "T_top_D"):
            for ts, value in grouped.get(variable) or []:
                top_by_ts[ts].append(value)
        derived_top = [
            (ts, float(sum(values) / len(values)))
            for ts, values in sorted(top_by_ts.items())
            if values
        ]
        if derived_top:
            grouped["T_top"] = derived_top
            value_sources["T_top"] = "derived_mean_T_top_A_D"

    baselines: dict[str, Mapping[str, Any]] = {}
    for row in baseline_rows:
        variable = str(row.get("variable_name") or "")
        if variable in VARIABLE_META and variable not in baselines:
            baselines[variable] = row

    baseline_sources = {variable: "daily_baselines" for variable in baselines}
    if "T_top" not in baselines:
        top_baselines = [
            baselines[variable]
            for variable in ("T_top_A", "T_top_B", "T_top_C", "T_top_D")
            if variable in baselines
        ]
        top_medians = [
            value
            for row in top_baselines
            if (value := _finite(row.get("median_ref"))) is not None
        ]
        top_iqrs = [
            value
            for row in top_baselines
            if (value := _finite(row.get("iqr_ref"))) is not None
        ]
        if top_medians:
            baselines["T_top"] = {
                "baseline_day": max(
                    (str(row.get("baseline_day") or "") for row in top_baselines),
                    default="",
                ),
                "median_ref": _mean(top_medians),
                "iqr_ref": _mean(top_iqrs),
            }
            baseline_sources["T_top"] = "derived_mean_T_top_A_D_baselines"

    result: dict[str, dict[str, Any]] = {}
    for variable, meta in VARIABLE_META.items():
        samples = sorted(grouped.get(variable) or [], key=lambda item: item[0])
        recent = [value for ts, value in samples if ts > end - timedelta(minutes=5)]
        previous = [
            value
            for ts, value in samples
            if end - timedelta(minutes=10) < ts <= end - timedelta(minutes=5)
        ]
        values_60 = [value for _, value in samples]
        current = samples[-1][1] if samples else None
        recent_mean = _mean(recent)
        previous_mean = _mean(previous)
        delta = (
            recent_mean - previous_mean
            if recent_mean is not None and previous_mean is not None
            else None
        )
        delta_pct = (
            delta / abs(previous_mean) * 100
            if delta is not None and previous_mean not in (None, 0)
            else None
        )
        epsilon = max(abs(previous_mean or 0.0) * 0.001, 1e-6)
        direction = (
            "rising"
            if delta is not None and delta > epsilon
            else "falling"
            if delta is not None and delta < -epsilon
            else "stable"
            if delta is not None
            else "unknown"
        )
        baseline = baselines.get(variable) or {}
        median = _finite(baseline.get("median_ref"))
        iqr = _finite(baseline.get("iqr_ref"))
        mean_60 = _mean(values_60)
        baseline_z = (
            (mean_60 - median) / iqr
            if mean_60 is not None and median is not None and iqr not in (None, 0)
            else None
        )
        result[variable] = {
            "id": variable,
            "display_name": meta[0],
            "unit": meta[1],
            "current_value": _round(current),
            "recent_5m_mean": _round(recent_mean),
            "previous_5m_mean": _round(previous_mean),
            "delta_5m": _round(delta),
            "delta_5m_pct": _round(delta_pct, 2),
            "direction_5m": direction,
            "mean_60m": _round(mean_60),
            "min_60m": _round(min(values_60) if values_60 else None),
            "max_60m": _round(max(values_60) if values_60 else None),
            "baseline_median_30d": _round(median),
            "baseline_iqr_30d": _round(iqr),
            "baseline_z_60m": _round(baseline_z, 3),
            "sample_count_60m": len(values_60),
            "baseline_day": str(baseline.get("baseline_day") or ""),
            "series_60m": [
                {"ts": ts.isoformat(), "value": _round(value)}
                for ts, value in samples
            ],
            "series_window_minutes": 60,
            "value_source": value_sources.get(variable, "unavailable"),
            "baseline_source": baseline_sources.get(variable, "unavailable"),
            "source": (
                "derived AVG(T_top_A,T_top_B,T_top_C,T_top_D)"
                if value_sources.get(variable) == "derived_mean_T_top_A_D"
                else "bf_sensor.one_minute_values+daily_baselines"
            ),
        }
    return result


def build_core_variable_evidence(
    variable_stats: Mapping[str, Mapping[str, Any]],
    selected_driver_rows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return all 19 fixed core variables with trusted 60-minute series.

    The rule-selected driver cards remain the concise first view.  This list is
    the complete operator expander and therefore retains unavailable variables
    instead of silently dropping them.
    """
    selected_variables = {
        str(variable.get("id") or "")
        for driver in selected_driver_rows
        if isinstance(driver, Mapping)
        for variable in list(driver.get("variables") or [])
        if isinstance(variable, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for variable in CORE_EVIDENCE_VARIABLES:
        source = variable_stats.get(variable)
        item = dict(source) if isinstance(source, Mapping) else {}
        item.update(
            {
                "id": variable,
                "display_name": item.get("display_name") or VARIABLE_META[variable][0],
                "unit": item.get("unit") or VARIABLE_META[variable][1],
                "selected_rule_evidence": variable in selected_variables,
                "read_only": True,
            }
        )
        item["series_60m"] = [
            dict(point)
            for point in list(item.get("series_60m") or [])[:61]
            if isinstance(point, Mapping)
        ]
        rows.append(item)
    return rows


def build_truthful_data_limits(
    label: str,
    driver_rows: Sequence[Mapping[str, Any]],
    variable_stats: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return only server-confirmed evidence gaps for one diagnosis label.

    A sparse but usable minute series is not a missing sensor.  In particular,
    ``L_north``/``L_south`` and ``T_top_A-D`` may have fewer than 61 minute rows
    while still having a current value and a usable 60-minute series.  The
    model must not turn that sampling density into a false ``data_limits``
    warning.  This function therefore reports a limit only when a rule driver
    has no feature value and no linked sensor has any usable sample.

    Corresponding requirement:
    REQ-8093-DIAGNOSIS-AI-EVIDENCE-GUIDANCE-20260805.
    """
    if label not in DIAGNOSIS_LABELS:
        return []
    stats = variable_stats if isinstance(variable_stats, Mapping) else {}
    limits: list[str] = []
    seen: set[str] = set()
    for driver in driver_rows:
        if not isinstance(driver, Mapping):
            continue
        feature_value = _finite(driver.get("feature_value"))
        if feature_value is not None:
            continue
        variables = [
            str(item.get("id") or "")
            for item in list(driver.get("variables") or [])
            if isinstance(item, Mapping) and item.get("id")
        ]
        usable_variables: list[str] = []
        for variable in variables:
            row = stats.get(variable)
            if not isinstance(row, Mapping):
                continue
            current = _finite(row.get("current_value"))
            series = [
                point
                for point in list(row.get("series_60m") or [])
                if isinstance(point, Mapping) and _finite(point.get("value")) is not None
            ]
            if current is not None or series:
                usable_variables.append(variable)
        if variables and len(usable_variables) == len(variables):
            # The formula value itself can be unavailable for a calculation
            # reason, but the underlying sensors are present and explainable.
            continue
        if variables and not usable_variables:
            names = "、".join(VARIABLE_META.get(item, (item, ""))[0] for item in variables)
            message = f"{driver.get('name') or '该规则项'}关联传感器当前窗口无可用采样：{names}"
        elif not variables:
            message = f"{driver.get('name') or '该规则项'}公式项当前无可用值"
        else:
            missing = [item for item in variables if item not in usable_variables]
            names = "、".join(VARIABLE_META.get(item, (item, ""))[0] for item in missing)
            message = f"{driver.get('name') or '该规则项'}仍缺少可用传感器：{names}"
        if message not in seen:
            limits.append(message)
            seen.add(message)
    return limits[:4]


def latest_values(variable_stats: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for variable, row in variable_stats.items():
        value = _finite(row.get("current_value"))
        if value is not None:
            values[variable] = value
    return values


def _percentile(values: Sequence[float], ratio: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * ratio
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _feature_value(
    feature_snapshot: Mapping[str, Any], feature_keys: Sequence[str], aggregate: str
) -> tuple[float | None, list[str]]:
    rows = [
        (key, value)
        for key in feature_keys
        if (value := _finite(feature_snapshot.get(key))) is not None
    ]
    if not rows:
        return None, []
    values = [value for _, value in rows]
    if aggregate == "max":
        value = max(values)
    elif aggregate == "min":
        value = min(values)
    elif aggregate == "p75":
        value = _percentile(values, 0.75)
    elif aggregate == "p80":
        value = _percentile(values, 0.80)
    else:
        value = values[0]
    return value, [key for key, _ in rows]


def _signal_state(value: float | None, mode: str, threshold: float) -> str:
    if value is None:
        return "unavailable"
    if mode == "stable_abs":
        return "supporting" if abs(value) <= abs(threshold) else "not_supporting"
    if mode == "low":
        return "supporting" if value <= threshold else "not_triggered"
    if mode == "boolean":
        return "supporting" if value >= threshold else "not_triggered"
    return "supporting" if value >= threshold else "not_triggered"


def _num_text(value: object) -> str:
    number = _finite(value)
    if number is None:
        return "--"
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _driver_sentence(
    definition: Mapping[str, Any],
    feature_value: float | None,
    signal_state: str,
    variables: Sequence[Mapping[str, Any]],
) -> str:
    state_text = {
        "supporting": "已经进入该项规则的支持区间",
        "not_supporting": "稳定性已超出该项正常区间",
        "not_triggered": "当前尚未进入该项异常触发区间",
        "unavailable": "当前快照缺少该项规则特征",
    }[signal_state]
    measurable = next(
        (row for row in variables if row.get("current_value") is not None), None
    )
    parts: list[str] = []
    if measurable:
        unit = str(measurable.get("unit") or "")
        parts.append(
            f"{measurable['display_name']}当前{_num_text(measurable.get('current_value'))}{unit}"
        )
        delta = _finite(measurable.get("delta_5m"))
        if delta is not None:
            direction = "上升" if delta > 0 else "下降" if delta < 0 else "基本不变"
            parts.append(f"近5分钟比前5分钟{direction}{_num_text(abs(delta))}{unit}")
        baseline = _finite(measurable.get("baseline_median_30d"))
        if baseline is not None:
            parts.append(f"30天基线中位数{_num_text(baseline)}{unit}")
    if feature_value is not None:
        parts.append(f"规则特征值{_num_text(feature_value)}，{state_text}")
    else:
        parts.append(state_text)
    return "；".join(parts) + "。"


def build_rule_driver_context(
    feature_snapshot: Mapping[str, Any],
    variable_stats: Mapping[str, Mapping[str, Any]],
    *,
    max_per_label: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    """Map each diagnosis label to its actual rule inputs and trusted facts."""
    snapshot = feature_snapshot if isinstance(feature_snapshot, Mapping) else {}
    result: dict[str, list[dict[str, Any]]] = {}
    state_order = {
        "supporting": 0,
        "not_supporting": 1,
        "not_triggered": 2,
        "unavailable": 3,
    }
    for label in DIAGNOSIS_LABELS:
        rows: list[dict[str, Any]] = []
        for definition in RULE_DRIVERS[label]:
            value, used_keys = _feature_value(
                snapshot,
                definition["feature_keys"],
                str(definition.get("aggregate") or "first"),
            )
            variables = [
                dict(variable_stats[variable])
                for variable in definition["variables"]
                if variable in variable_stats
            ]
            state = _signal_state(
                value, str(definition["mode"]), float(definition["threshold"])
            )
            rows.append(
                {
                    "driver_id": definition["id"],
                    "name": definition["name"],
                    "feature_keys": used_keys or list(definition["feature_keys"]),
                    "feature_value": _round(value, 4),
                    "feature_semantics": (
                        "相对30天基线的标准化偏离/波动"
                        if any(key.startswith("z") for key in definition["feature_keys"])
                        else "规则派生特征"
                    ),
                    "signal_state": state,
                    "configured_threshold": definition["threshold"],
                    "configured_weight": definition["weight"],
                    "variables": variables,
                    "colloquial_evidence": _driver_sentence(
                        definition, value, state, variables
                    ),
                    "source": "diagnosis_snapshot.feature_snapshot",
                    "read_only": True,
                }
            )
        rows.sort(
            key=lambda row: (
                state_order.get(str(row["signal_state"]), 9),
                -float(row["configured_weight"]),
            )
        )
        result[label] = rows[: max(1, int(max_per_label))]
    return result


def _compact_text_list(value: object, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value[:limit]:
        if isinstance(item, Mapping):
            text = (
                item.get("description")
                or item.get("text")
                or item.get("name")
                or item.get("field")
            )
        else:
            text = item
        clean = " ".join(str(text or "").split())[:500]
        if clean:
            output.append(clean)
    return output


def normalize_recommendation_bundle(bundle: object) -> dict[str, Any]:
    """Keep the full read-only action audit fields needed by the explanation UI."""
    source = bundle if isinstance(bundle, Mapping) else {}
    conditions = source.get("conditions") if isinstance(source, Mapping) else []
    by_label: dict[str, Any] = {}
    for condition in conditions if isinstance(conditions, list) else []:
        if not isinstance(condition, Mapping):
            continue
        label = str(condition.get("label") or "")
        if label not in DIAGNOSIS_LABELS:
            continue
        recommendation = condition.get("recommendation")
        recommendation = recommendation if isinstance(recommendation, Mapping) else {}
        actions: list[dict[str, Any]] = []
        for action in recommendation.get("actions") or []:
            if not isinstance(action, Mapping):
                continue
            actions.append(
                {
                    "id": str(action.get("id") or ""),
                    "name": str(action.get("name") or action.get("user_facing_text") or "")[:200],
                    "text": str(action.get("user_facing_text") or action.get("name") or "")[:500],
                    "status": str(action.get("status") or "needs_data"),
                    "trigger_evidence": _compact_text_list(action.get("trigger_evidence")),
                    "preconditions": _compact_text_list(action.get("preconditions")),
                    "blocking_reasons": _compact_text_list(action.get("blocking_reasons")),
                    "missing_inputs": _compact_text_list(action.get("missing_inputs")),
                    "delta": action.get("delta") if isinstance(action.get("delta"), Mapping) else None,
                    "observation_window": action.get("observation_window") if isinstance(action.get("observation_window"), Mapping) else None,
                    "approval": action.get("approval") if isinstance(action.get("approval"), Mapping) else {},
                    "source_refs": [str(item)[:80] for item in (action.get("source_refs") or [])[:8]],
                    "read_only": True,
                }
            )
        by_label[label] = {
            "label": label,
            "display_name": DISPLAY_NAMES[label],
            "scope": str(condition.get("scope") or "hypothetical"),
            "goal": str(recommendation.get("goal") or "")[:500],
            "safety_gate_passed": bool(recommendation.get("safety_gate_passed", True)),
            "safety_warnings": _compact_text_list(recommendation.get("safety_warnings")),
            "observe_items": _compact_text_list(recommendation.get("observe_items"), limit=12),
            "recheck_minutes": _finite(recommendation.get("recheck_minutes")),
            "actions": actions[:16],
            "read_only": True,
        }
    return {
        "available": bool(by_label),
        "schema_version": str(source.get("schema_version") or ""),
        "engine_meta": dict(source.get("engine_meta") or {}),
        "conditions": by_label,
        "read_only": True,
    }


def load_recommendation_bundle(
    diagnosis: Mapping[str, Any], current_values: Mapping[str, Any]
) -> dict[str, Any]:
    """Use the existing recommendation engine without granting control authority."""
    project_root = Path(__file__).resolve().parents[3]
    service_dir = project_root / "自动诊断服务"
    if str(service_dir) not in sys.path:
        sys.path.insert(0, str(service_dir))
    try:
        adapter = importlib.import_module("recommendation_adapter")
        bundle = adapter.generate_recommendation_bundle(
            dict(diagnosis), dict(current_values)
        )
        return normalize_recommendation_bundle(bundle)
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "schema_version": "",
            "engine_meta": {"read_only": True},
            "conditions": {},
            "read_only": True,
            "error_type": type(exc).__name__,
        }


def normalize_knowledge_pack(pack: object, *, limit: int = 10) -> dict[str, Any]:
    source = pack if isinstance(pack, Mapping) else {}
    rows: list[dict[str, Any]] = []
    evidence = source.get("evidence") if isinstance(source, Mapping) else []
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "chunk_id": str(item.get("chunk_id") or "")[:160],
                "doc_id": str(item.get("doc_id") or "")[:160],
                "title": str(item.get("title") or "")[:240],
                "source_file": str(item.get("source_file") or "")[:300],
                "detail_url": (
                    f"/api/qa/knowledge/chunk?chunk_id={item.get('chunk_id')}&format=html"
                    if item.get("chunk_id")
                    else ""
                ),
                "knowledge_category": str(item.get("knowledge_category") or "")[:100],
                "chunk_type": str(item.get("chunk_type") or "")[:80],
                "content": " ".join(str(item.get("content") or "").split())[:900],
                "score": _round(_finite(item.get("score")), 4),
            }
        )
    return {
        "available": bool(source.get("enabled") and rows),
        "retrieval_mode": str(source.get("retrieval_mode") or ""),
        "evidence": rows[: max(1, int(limit))],
        "message": str(source.get("message") or "")[:300],
        "read_only": True,
    }


def _deviation_state(abs_z: float | None) -> str:
    if abs_z is None:
        return "缺少30天基线"
    if abs_z <= 0.25:
        return "接近最正常基线"
    if abs_z <= 0.5:
        return "轻度偏离基线"
    if abs_z <= 1.0:
        return "中度偏离基线"
    return "明显偏离基线"


def _sensor_basis(variable_stats: Mapping[str, Mapping[str, Any]], variable: str) -> list[str]:
    row = variable_stats.get(variable)
    if not isinstance(row, Mapping):
        return []
    name = str(row.get("display_name") or variable)
    unit = str(row.get("unit") or "")
    current = _finite(row.get("current_value"))
    delta = _finite(row.get("delta_5m"))
    baseline = _finite(row.get("baseline_median_30d"))
    parts: list[str] = []
    if current is not None:
        parts.append(f"{name}当前{current:g}{unit}")
    if delta is not None:
        direction = "上升" if delta > 0 else "下降" if delta < 0 else "基本不变"
        parts.append(f"近5分钟{direction}{abs(delta):g}{unit}")
    if baseline is not None:
        parts.append(f"30天基线{baseline:g}{unit}")
    return parts


def _foreman_control_candidates(variable_stats: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": "KB-CONTROL-PCI-INCREASE",
            "name": "候选：增加喷煤",
            "text": "当热制度下行、热量输入偏低或出铁口温度走低时，可评估小幅增加喷煤；先核对煤气利用率、压差和透气性。",
            "status": "manual_confirm",
            "data_basis": [
                item for variable in ("PCI_rate", "T_blast", "T_taphole_1", "T_taphole_2", "GasUtil")
                for item in _sensor_basis(variable_stats, variable)[:2]
            ][:8],
            "source_refs": [FOREMAN_KNOWLEDGE_DOC_ID],
            "read_only": True,
        },
        {
            "id": "KB-CONTROL-PCI-DECREASE",
            "name": "候选：减少喷煤",
            "text": "当热制度上行、热量输入偏高或出铁口温度走高时，可评估小幅减少喷煤；必须结合压差、顶压和料速确认。",
            "status": "manual_confirm",
            "data_basis": [
                item for variable in ("PCI_rate", "T_blast", "T_taphole_1", "T_taphole_2", "DP_total", "P_top")
                for item in _sensor_basis(variable_stats, variable)[:2]
            ][:8],
            "source_refs": [FOREMAN_KNOWLEDGE_DOC_ID],
            "read_only": True,
        },
        {
            "id": "KB-CONTROL-COLD-BLAST-PRESSURE-INCREASE",
            "name": "候选：增加冷风压",
            "text": "只有在压差、透气性和顶压均允许且需要恢复送风能力时，才评估小幅增加冷风压；不能仅凭单点温度操作。",
            "status": "manual_confirm",
            "data_basis": [
                item for variable in ("P_blast_cold", "P_blast", "PI", "DP_total", "P_top")
                for item in _sensor_basis(variable_stats, variable)[:2]
            ][:8],
            "source_refs": [FOREMAN_KNOWLEDGE_DOC_ID],
            "read_only": True,
        },
        {
            "id": "KB-CONTROL-COLD-BLAST-PRESSURE-DECREASE",
            "name": "候选：减少冷风压",
            "text": "当压差升高、透气性下降或顶压波动扩大时，可评估降低冷风压以抑制偏离；幅度和恢复节奏必须由现场确认。",
            "status": "manual_confirm",
            "data_basis": [
                item for variable in ("P_blast_cold", "P_blast", "PI", "DP_total", "P_top")
                for item in _sensor_basis(variable_stats, variable)[:2]
            ][:8],
            "source_refs": [FOREMAN_KNOWLEDGE_DOC_ID],
            "read_only": True,
        },
    ]


def build_sensor_deviation_summary(
    variable_stats: Mapping[str, Mapping[str, Any]],
    *,
    normal_score: float | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    abs_z_values: list[float] = []
    for variable in CORE_EVIDENCE_VARIABLES:
        source = variable_stats.get(variable)
        source = source if isinstance(source, Mapping) else {}
        current = _finite(source.get("current_value"))
        baseline = _finite(source.get("baseline_median_30d"))
        baseline_z = _finite(source.get("baseline_z_60m"))
        delta = _finite(source.get("delta_5m"))
        if baseline_z is not None:
            abs_z_values.append(abs(baseline_z))
        rows.append(
            {
                "id": variable,
                "display_name": source.get("display_name") or VARIABLE_META[variable][0],
                "unit": source.get("unit") or VARIABLE_META[variable][1],
                "current_value": _round(current),
                "delta_5m": _round(delta),
                "baseline_median_30d": _round(baseline),
                "baseline_z_60m": _round(baseline_z, 3),
                "direction_5m": source.get("direction_5m") or "unknown",
                "deviation_state": _deviation_state(abs(baseline_z) if baseline_z is not None else None),
                "sample_count_60m": int(source.get("sample_count_60m") or 0),
                "detail_url": f"/api/qa/knowledge/search?q={variable}&source_doc_id={FOREMAN_KNOWLEDGE_DOC_ID}",
                "read_only": True,
            }
        )
    average_abs_z = (
        round(sum(abs_z_values) / len(abs_z_values), 3) if abs_z_values else None
    )
    max_abs_z = round(max(abs_z_values), 3) if abs_z_values else None
    if average_abs_z is None:
        label = "无法判断偏离程度"
    else:
        label = _deviation_state(average_abs_z)
    score_gap = (
        round(max(0.0, 100.0 - float(normal_score)), 1)
        if normal_score is not None
        else None
    )
    if normal_score is None:
        summary = f"核心传感器有{len(abs_z_values)}项具备30天基线，当前偏离程度为{label}。"
    else:
        summary = (
            f"正常顺行规则分{float(normal_score):g}分，距离100分相差{score_gap:g}分；"
            f"核心传感器有{len(abs_z_values)}项具备30天基线，平均绝对偏离{average_abs_z if average_abs_z is not None else '--'}个基线IQR，"
            f"当前属于{label}。"
        )
    return {
        "available": bool(rows),
        "rule_score": _round(normal_score, 1),
        "score_gap_to_100": score_gap,
        "total_sensor_count": len(rows),
        "baseline_available_count": len(abs_z_values),
        "average_abs_baseline_z": average_abs_z,
        "max_abs_baseline_z": max_abs_z,
        "deviation_label": label,
        "summary": summary,
        "sensors": rows,
        "control_candidates": _foreman_control_candidates(variable_stats),
        "read_only": True,
    }


def build_foreman_knowledge_recommendation_bundle(
    diagnosis: Mapping[str, Any],
    current_values: Mapping[str, Any],
    knowledge_pack: Mapping[str, Any],
    variable_stats: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    target_label: str | None = None,
) -> dict[str, Any]:
    """Build read-only candidate guidance from the 64-topic foreman knowledge source."""
    del current_values
    selected_label = str(target_label or diagnosis.get("main_label") or "normal")
    if selected_label not in DIAGNOSIS_LABELS:
        selected_label = "normal"
    rows = [
        dict(item)
        for item in list(knowledge_pack.get("evidence") or [])
        if isinstance(item, Mapping)
        and str(item.get("doc_id") or "") == FOREMAN_KNOWLEDGE_DOC_ID
    ]
    actions: list[dict[str, Any]] = []
    for row in rows[:6]:
        chunk_id = str(row.get("chunk_id") or "")
        title = str(row.get("title") or "高炉长知识依据")[:160]
        if not chunk_id:
            continue
        actions.append(
            {
                "id": f"KB-{chunk_id}",
                "name": f"候选建议：{title}",
                "text": "依据该主题先核对关联传感器和现场现象，再按小幅、分步、观察反馈原则评估；知识库内容不直接形成操作指令。",
                "status": "manual_confirm",
                "trigger_evidence": ["当前选定炉况的规则变量和传感器趋势"],
                "preconditions": ["现场确认热制度、压差、透气性和料速"],
                "blocking_reasons": ["知识库建议不能替代实时规则安全门禁"],
                "missing_inputs": ["具体操作幅度和现场审批条件"],
                "delta": None,
                "observation_window": {"min_minutes": 5, "max_minutes": 10, "basis": "继续观察相关传感器趋势"},
                "approval": {"required": True, "role": "高炉长"},
                "source_refs": [chunk_id],
                "knowledge_chunk_id": chunk_id,
                "read_only": True,
            }
        )
    conditions: dict[str, Any] = {}
    for label in DIAGNOSIS_LABELS:
        conditions[label] = {
            "label": label,
            "display_name": DISPLAY_NAMES[label],
            "scope": "active" if label == selected_label else "hypothetical",
            "goal": "只读引用64主题知识库，结合当前传感器数据进行人工复核和候选建议。",
            "safety_gate_passed": False,
            "safety_warnings": ["该来源不执行三规二制调控引擎；候选建议必须经现场确认。"],
            "observe_items": ["热制度", "压差", "透气性", "顶压", "料线"],
            "recheck_minutes": 5,
            "actions": actions if label == selected_label else [],
            "read_only": True,
        }
    return {
        "available": bool(rows),
        "schema_version": FOREMAN_KNOWLEDGE_SOURCE_VERSION,
        "engine_meta": {
            "name": "foreman-knowledge-advice",
            "version": FOREMAN_KNOWLEDGE_SOURCE_VERSION,
            "source_doc_id": FOREMAN_KNOWLEDGE_DOC_ID,
            "source_title": "控制室高炉长工长炉况判断与操作经验（64主题）",
            "read_only": True,
        },
        "source_mode": "foreman_knowledge_only",
        "conditions": conditions,
        "sensor_deviation_summary": build_sensor_deviation_summary(
            variable_stats or {},
            normal_score=_finite((diagnosis.get("raw_scores") or {}).get("normal")),
        ),
        "control_candidates": _foreman_control_candidates(variable_stats or {}),
        "read_only": True,
    }


def build_fixture_enrichment(context: Mapping[str, Any]) -> dict[str, Any]:
    """Create deterministic, explicitly labelled loopback-only browser evidence."""
    end = _naive_datetime(context.get("diagnosis_ts"))
    feature_snapshot = dict(context.get("feature_snapshot") or {})
    if not feature_snapshot:
        feature_snapshot = {
            "z30_T_top_slope": -0.62,
            "z60_T_body_lower": -1.08,
            "z_T_taphole_mean": -0.84,
            "z60_P_blast": -0.91,
            "z60_PI": 0.94,
            "z60_GasUtil": -0.73,
            "z60_T_blast": -0.58,
            "zstd_P_top": 0.42,
            "zstd_DP_total": 0.51,
            "zstd_PI": 0.38,
            "zstd_P_blast": 0.47,
            "DispTop_15": 0.21,
            "L_diff_NS": 0.12,
        }
    fixture_values = {
        "T_top_A": (153.0, 158.0, 162.0),
        "T_top_B": (151.0, 155.0, 160.0),
        "P_blast": (384.0, 388.0, 401.0),
        "PI": (1.24, 1.20, 1.11),
        "GasUtil": (47.2, 48.1, 50.0),
        "DP_total": (163.0, 161.0, 158.0),
        "L_south": (1.76, 1.75, 1.70),
        "L_north": (1.68, 1.67, 1.65),
        "T_blast": (1168.0, 1172.0, 1185.0),
    }
    sensor_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    for variable, (current, previous, baseline) in fixture_values.items():
        for offset, value in ((-8, previous), (-3, current)):
            sensor_rows.append(
                {"variable_name": variable, "ts": end + timedelta(minutes=offset), "value": value}
            )
        baseline_rows.append(
            {
                "variable_name": variable,
                "baseline_day": end.date(),
                "median_ref": baseline,
                "iqr_ref": max(abs(baseline) * 0.05, 0.1),
            }
        )
    stats = build_variable_stats(sensor_rows, baseline_rows, end)
    drivers = build_rule_driver_context(feature_snapshot, stats)
    fixture_actions = {
        label: {
            "label": label,
            "display_name": DISPLAY_NAMES[label],
            "scope": "active" if label == context.get("main_label") else "hypothetical",
            "goal": "先确认规则证据和现场状态，再按小幅、分步、观察反馈原则处置。",
            "safety_gate_passed": True,
            "safety_warnings": [],
            "observe_items": ["风压", "压差", "顶温", "料线"],
            "recheck_minutes": 5,
            "actions": [
                {
                    "id": f"FIXTURE-{label.upper()}-OBSERVE",
                    "name": "核对关键变量并保持小步调整",
                    "text": "先核对关键变量趋势和现场现象；测试场景不形成生产操作指令。",
                    "status": "manual_confirm",
                    "trigger_evidence": ["本机固定场景规则证据"],
                    "preconditions": ["现场确认"],
                    "blocking_reasons": [],
                    "missing_inputs": [],
                    "delta": None,
                    "observation_window": {"min_minutes": 5, "max_minutes": 10, "basis": "继续观察关键变量"},
                    "approval": {"required": True, "role": "高炉长"},
                    "source_refs": ["local_fixture"],
                    "read_only": True,
                }
            ],
            "read_only": True,
        }
        for label in DIAGNOSIS_LABELS
    }
    knowledge = {
        "available": True,
        "retrieval_mode": "local_fixture",
        "evidence": [
            {
                "chunk_id": "fixture-foreman-knowledge",
                "doc_id": FOREMAN_KNOWLEDGE_DOC_ID,
                "title": "本机测试：64主题知识库依据",
                "source_file": "local_fixture",
                "detail_url": "",
                "knowledge_category": "64主题知识库测试资料",
                "chunk_type": "建议",
                "content": "测试场景只用于验证64主题知识库引用、传感器逐项说明和人工确认边界。",
                "score": 1.0,
            }
        ],
        "message": "",
        "read_only": True,
    }
    return {
        "feature_snapshot": feature_snapshot,
        "variable_stats": stats,
        "rule_drivers": drivers,
        "recommendation_context": {
            "available": True,
            "schema_version": "local_fixture",
            "engine_meta": {"name": "foreman-knowledge-fixture", "version": FOREMAN_KNOWLEDGE_SOURCE_VERSION, "source_doc_id": FOREMAN_KNOWLEDGE_DOC_ID, "read_only": True},
            "source_mode": "foreman_knowledge_only",
            "conditions": fixture_actions,
            "sensor_deviation_summary": build_sensor_deviation_summary(
                stats,
                normal_score=_finite((context.get("scores") or {}).get("normal")),
            ),
            "read_only": True,
        },
        "sensor_deviation_summary": build_sensor_deviation_summary(
            stats,
            normal_score=_finite((context.get("scores") or {}).get("normal")),
        ),
        "knowledge_context": knowledge,
    }
