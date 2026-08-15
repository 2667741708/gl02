"""GL02 blast-furnace foreman expert rule for an upward HCZ indication.

Requirement: REQ-HCZ-UPWARD-EXPERT-RULE-20260810.

The rule compares the latest 24 hourly means with the immediately preceding
five-day baseline.  It emits an upward *expert-rule indication* only when all
core deltas, the layer-temperature corroboration, and a 12-hour consecutive
trend gate pass.  It is not a direct cohesive-zone measurement or a calibrated
model and is prohibited from automatic control.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping, Optional

import yaml


REQUIREMENT_ID = "REQ-HCZ-UPWARD-EXPERT-RULE-20260810"
SCHEMA_VERSION = "gl02.hcz-upward-expert-rule.v1"
SENSITIVITY_SCHEMA_VERSION = "gl02.hcz-rule-sensitivity.v1"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "hcz_upward_expert_rule.yaml"
)
SHANGHAI_TZ = timezone(timedelta(hours=8))


class HczUpwardRuleConfigurationError(RuntimeError):
    """Raised when the rule configuration violates the fixed safety contract."""


class HczRuleSensitivityValidationError(ValueError):
    """Raised when a read-only sensitivity override is outside its safe range."""


SENSITIVITY_RANGES: dict[str, tuple[float, float, bool]] = {
    "top_temperature_delta_c": (0.0, 40.0, False),
    "total_pressure_drop_kpa": (0.0, 20.0, False),
    "permeability_drop": (0.0, 5.0, False),
    "gas_utilisation_drop_pp": (0.0, 10.0, False),
    "cold_blast_pressure_rise_kpa": (0.0, 20.0, False),
    "body_temperature_delta_c": (0.0, 40.0, False),
    "min_directional_layers": (1.0, 7.0, True),
    "required_consecutive_hours": (1.0, 24.0, True),
}


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    return parsed.astimezone(SHANGHAI_TZ)


def _hour(value: Any) -> datetime:
    return _timestamp(value).replace(minute=0, second=0, microsecond=0)


def load_hcz_upward_rule_config(path: Optional[Path] = None) -> dict[str, Any]:
    """Load and validate the versioned expert-rule configuration."""
    target = path or DEFAULT_CONFIG_PATH
    if not target.is_file():
        raise FileNotFoundError(f"HCZ upward rule config not found: {target}")
    config = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise HczUpwardRuleConfigurationError("HCZ upward rule config must be a mapping")
    if config.get("requirement_id") != REQUIREMENT_ID:
        raise HczUpwardRuleConfigurationError("unexpected HCZ upward rule requirement_id")
    windows = config.get("windows") or {}
    if (
        int(windows.get("current_hours") or 0) != 24
        or int(windows.get("baseline_days") or 0) != 5
        or int(windows.get("required_consecutive_hours") or 0) != 12
    ):
        raise HczUpwardRuleConfigurationError("24h/5d/12h expert-rule windows are fixed")
    safety = config.get("safety") or {}
    if (
        safety.get("evidence_type") != "expert_rule_indication"
        or safety.get("direct_measurement_truth") is not False
        or safety.get("calibrated_model") is not False
        or safety.get("automatic_control") != "prohibited"
        or safety.get("missing_data_policy") != "indeterminate"
    ):
        raise HczUpwardRuleConfigurationError("HCZ upward rule safety contract is invalid")
    return config


def required_variable_names(config: Optional[Mapping[str, Any]] = None) -> tuple[str, ...]:
    """Return the canonical registry variables needed by the rule adapter."""
    cfg = dict(config or load_hcz_upward_rule_config())
    names = {
        variable
        for metric in (cfg.get("core_metrics") or {}).values()
        for variable in metric.get("variables", [])
    }
    body = cfg.get("body_temperature") or {}
    for layer in body.get("layers", []):
        for sector in body.get("sectors", []):
            names.add(f"T_body_L{int(layer)}_{sector}")
    return tuple(sorted(names))


def sensitivity_defaults(config: Optional[Mapping[str, Any]] = None) -> dict[str, float | int]:
    """Return the production defaults exposed by the read-only trial UI."""
    cfg = dict(config or load_hcz_upward_rule_config())
    metrics = cfg["core_metrics"]
    body = cfg["body_temperature"]
    return {
        "top_temperature_delta_c": float(metrics["top_temperature"]["threshold"]),
        "total_pressure_drop_kpa": float(metrics["total_pressure_drop"]["threshold"]),
        "permeability_drop": float(metrics["permeability_index"]["threshold"]),
        "gas_utilisation_drop_pp": float(metrics["gas_utilisation"]["threshold"]),
        "cold_blast_pressure_rise_kpa": float(metrics["blast_pressure"]["threshold"]),
        "body_temperature_delta_c": float(body["rise_threshold_c"]),
        "min_directional_layers": int(body["min_rising_layers"]),
        "required_consecutive_hours": int(cfg["windows"]["required_consecutive_hours"]),
    }


def sensitivity_parameter_contract(config: Optional[Mapping[str, Any]] = None) -> dict[str, dict[str, Any]]:
    """Describe editable threshold ranges without allowing production persistence."""
    defaults = sensitivity_defaults(config)
    result: dict[str, dict[str, Any]] = {}
    for key, (minimum, maximum, integer) in SENSITIVITY_RANGES.items():
        result[key] = {
            "default": defaults[key],
            "minimum": int(minimum) if integer else minimum,
            "maximum": int(maximum) if integer else maximum,
            "integer": integer,
        }
    return result


def _scenario_config(
    config: Mapping[str, Any],
    overrides: Optional[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, float | int]]:
    values = sensitivity_defaults(config)
    for key, raw_value in (overrides or {}).items():
        if key not in SENSITIVITY_RANGES:
            raise HczRuleSensitivityValidationError(f"不支持的试算参数：{key}")
        minimum, maximum, integer = SENSITIVITY_RANGES[key]
        number = _finite(raw_value)
        if number is None or not minimum <= number <= maximum:
            raise HczRuleSensitivityValidationError(
                f"{key}必须在{minimum:g}到{maximum:g}之间"
            )
        if integer and not float(number).is_integer():
            raise HczRuleSensitivityValidationError(f"{key}必须是整数")
        values[key] = int(number) if integer else float(number)

    scenario = deepcopy(dict(config))
    metrics = scenario["core_metrics"]
    metrics["top_temperature"]["threshold"] = values["top_temperature_delta_c"]
    metrics["total_pressure_drop"]["threshold"] = values["total_pressure_drop_kpa"]
    metrics["permeability_index"]["threshold"] = values["permeability_drop"]
    metrics["gas_utilisation"]["threshold"] = values["gas_utilisation_drop_pp"]
    metrics["blast_pressure"]["threshold"] = values["cold_blast_pressure_rise_kpa"]
    scenario["body_temperature"]["rise_threshold_c"] = values["body_temperature_delta_c"]
    scenario["body_temperature"]["min_rising_layers"] = values["min_directional_layers"]
    scenario["windows"]["required_consecutive_hours"] = values["required_consecutive_hours"]
    return scenario, values


def _series_mean(series: Mapping[datetime, tuple[float, int]], hours: Iterable[datetime]) -> tuple[Optional[float], int]:
    values = [series[hour][0] for hour in hours if hour in series]
    return (fmean(values), len(values)) if values else (None, 0)


def _passes(delta: Optional[float], direction: str, threshold: float) -> bool:
    if delta is None:
        return False
    if direction == "increase":
        return delta >= threshold
    if direction == "decrease":
        return delta <= -threshold
    raise HczUpwardRuleConfigurationError(f"unsupported direction: {direction}")


def _maximum_consecutive(hours: list[datetime], qualification: Mapping[datetime, bool]) -> int:
    maximum = 0
    current = 0
    previous: Optional[datetime] = None
    for hour in hours:
        contiguous = previous is not None and hour - previous == timedelta(hours=1)
        if qualification.get(hour, False):
            current = current + 1 if contiguous else 1
            maximum = max(maximum, current)
        else:
            current = 0
        previous = hour
    return maximum


def evaluate_hcz_upward_rule(
    hourly_records: Iterable[Mapping[str, Any]],
    *,
    evaluation_time: Any = None,
    config_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Evaluate the strict 24h-vs-5d, 12h-sustained upward HCZ rule.

    Each input record must contain ``bucket``/``ts``, ``variable_name``,
    ``value`` and optionally ``sample_count``. Missing samples stay missing and
    interrupt the sustained gate.
    """
    config = load_hcz_upward_rule_config(config_path)
    coverage = config["coverage"]
    min_core_samples = int(coverage["min_core_samples_per_hour"])
    min_body_samples = int(coverage["min_body_samples_per_point_hour"])
    raw: dict[str, dict[datetime, tuple[float, int]]] = defaultdict(dict)
    latest_hour: Optional[datetime] = None
    record_count = 0
    for record in hourly_records:
        name = str(record.get("variable_name") or "").strip()
        value = _finite(record.get("value"))
        bucket_raw = record.get("bucket", record.get("ts"))
        if not name or value is None or bucket_raw in (None, ""):
            continue
        bucket = _hour(bucket_raw)
        sample_count = int(record.get("sample_count") or 0)
        if sample_count < 1:
            continue
        raw[name][bucket] = (value, sample_count)
        latest_hour = bucket if latest_hour is None else max(latest_hour, bucket)
        record_count += 1
    if latest_hour is None:
        return _insufficient_result(config, None, ["没有可用小时数据"], record_count)
    evaluation_hour = _hour(evaluation_time) if evaluation_time is not None else latest_hour
    current_hours = [evaluation_hour - timedelta(hours=offset) for offset in reversed(range(24))]
    baseline_end = evaluation_hour - timedelta(hours=24)
    baseline_hours = [baseline_end - timedelta(hours=offset) for offset in reversed(range(120))]

    top_series: dict[datetime, tuple[float, int]] = {}
    for hour in baseline_hours + current_hours:
        direct = raw.get("T_top", {}).get(hour)
        if direct is not None and direct[1] < min_core_samples:
            direct = None
        if direct is not None:
            top_series[hour] = direct
            continue
        points = [raw.get(f"T_top_{sector}", {}).get(hour) for sector in "ABCD"]
        points = [point if point is not None and point[1] >= min_core_samples else None for point in points]
        values = [point[0] for point in points if point is not None]
        if len(values) >= int(coverage["min_top_points_per_hour"]):
            top_series[hour] = (fmean(values), sum(point[1] for point in points if point is not None))

    virtual_series: dict[str, Mapping[datetime, tuple[float, int]]] = {"top_temperature": top_series}
    for key, spec in config["core_metrics"].items():
        if key == "top_temperature":
            continue
        variable = str(spec["variables"][0])
        virtual_series[key] = {
            hour: sample
            for hour, sample in raw.get(variable, {}).items()
            if sample[1] >= min_core_samples
        }

    metrics: dict[str, dict[str, Any]] = {}
    insufficient: list[str] = []
    baseline_means: dict[str, float] = {}
    for key, spec in config["core_metrics"].items():
        current_mean, current_count = _series_mean(virtual_series[key], current_hours)
        baseline_mean, baseline_count = _series_mean(virtual_series[key], baseline_hours)
        delta = current_mean - baseline_mean if current_mean is not None and baseline_mean is not None else None
        enough = (
            current_count >= int(coverage["min_current_valid_hours"])
            and baseline_count >= int(coverage["min_baseline_valid_hours"])
        )
        if not enough:
            insufficient.append(f"{spec['label']}有效小时不足")
        if baseline_mean is not None:
            baseline_means[key] = baseline_mean
        metrics[key] = {
            "label": spec["label"],
            "unit": spec["unit"],
            "direction": spec["direction"],
            "threshold": float(spec["threshold"]),
            "current_24h_mean": round(current_mean, 6) if current_mean is not None else None,
            "baseline_5d_mean": round(baseline_mean, 6) if baseline_mean is not None else None,
            "delta": round(delta, 6) if delta is not None else None,
            "current_valid_hours": current_count,
            "baseline_valid_hours": baseline_count,
            "coverage_pass": enough,
            "threshold_pass": enough and _passes(delta, spec["direction"], float(spec["threshold"])),
        }

    body = config["body_temperature"]
    layer_series: dict[int, dict[datetime, tuple[float, int]]] = {}
    layer_results: list[dict[str, Any]] = []
    for layer_raw in body["layers"]:
        layer = int(layer_raw)
        series: dict[datetime, tuple[float, int]] = {}
        for hour in baseline_hours + current_hours:
            points = [raw.get(f"T_body_L{layer}_{sector}", {}).get(hour) for sector in body["sectors"]]
            points = [point if point is not None and point[1] >= min_body_samples else None for point in points]
            values = [point[0] for point in points if point is not None]
            if len(values) >= int(coverage["min_body_sectors_per_layer_hour"]):
                series[hour] = (fmean(values), sum(point[1] for point in points if point is not None))
        layer_series[layer] = series
        current_mean, current_count = _series_mean(series, current_hours)
        baseline_mean, baseline_count = _series_mean(series, baseline_hours)
        delta = current_mean - baseline_mean if current_mean is not None and baseline_mean is not None else None
        enough = (
            current_count >= int(coverage["min_current_valid_hours"])
            and baseline_count >= int(coverage["min_baseline_valid_hours"])
        )
        layer_results.append(
            {
                "layer": layer,
                "current_24h_mean": round(current_mean, 6) if current_mean is not None else None,
                "baseline_5d_mean": round(baseline_mean, 6) if baseline_mean is not None else None,
                "delta_c": round(delta, 6) if delta is not None else None,
                "current_valid_hours": current_count,
                "baseline_valid_hours": baseline_count,
                "coverage_pass": enough,
                "rise_10c_pass": enough and delta is not None and delta >= float(body["rise_threshold_c"]),
                "rise_20c_pass": enough and delta is not None and delta >= float(body["strong_rise_threshold_c"]),
            }
        )
    eligible_layers = sum(1 for item in layer_results if item["coverage_pass"])
    if eligible_layers < int(body["min_rising_layers"]):
        insufficient.append("7至13层有效炉体温度层数不足")
    rising_layers = [item["layer"] for item in layer_results if item["rise_10c_pass"]]
    strong_layers = [item["layer"] for item in layer_results if item["rise_20c_pass"]]

    hourly_qualification: dict[datetime, bool] = {}
    hourly_details: list[dict[str, Any]] = []
    for hour in current_hours:
        core_hour_passes: dict[str, bool] = {}
        for key, spec in config["core_metrics"].items():
            sample = virtual_series[key].get(hour)
            delta = sample[0] - baseline_means[key] if sample is not None and key in baseline_means else None
            core_hour_passes[key] = _passes(delta, spec["direction"], float(spec["threshold"]))
        rising_hour_layers = []
        for layer, series in layer_series.items():
            sample = series.get(hour)
            baseline = next((item["baseline_5d_mean"] for item in layer_results if item["layer"] == layer), None)
            if sample is not None and baseline is not None and sample[0] - float(baseline) >= float(body["rise_threshold_c"]):
                rising_hour_layers.append(layer)
        qualified = all(core_hour_passes.values()) and len(rising_hour_layers) >= int(body["min_rising_layers"])
        hourly_qualification[hour] = qualified
        hourly_details.append(
            {
                "hour": hour.isoformat(),
                "qualified": qualified,
                "core_pass_count": sum(core_hour_passes.values()),
                "core_required_count": len(core_hour_passes),
                "rising_layers": rising_hour_layers,
            }
        )

    consecutive = _maximum_consecutive(current_hours, hourly_qualification)
    required_consecutive = int(config["windows"]["required_consecutive_hours"])
    core_all_pass = all(item["threshold_pass"] for item in metrics.values())
    layer_gate_pass = len(rising_layers) >= int(body["min_rising_layers"])
    duration_gate_pass = consecutive >= required_consecutive
    data_sufficient = not insufficient
    triggered = data_sufficient and core_all_pass and layer_gate_pass and duration_gate_pass
    evidence_strength = (
        "strong"
        if triggered
        and len(rising_layers) >= int(body["strong_rising_layers"])
        and len(strong_layers) >= 1
        else "standard" if triggered else "not_triggered"
    )
    status = "triggered" if triggered else "not_triggered" if data_sufficient else "insufficient_data"
    conclusion = (
        "软熔带上移综合趋势规则已触发"
        if triggered
        else "数据不足，暂不能判断软熔带上移"
        if not data_sufficient
        else "未达到软熔带上移综合趋势规则"
    )
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "rule_id": config["rule_id"],
        "rule_name": config["rule_name"],
        "furnace_id": config["furnace_id"],
        "evaluation_time": evaluation_hour.isoformat(),
        "status": status,
        "triggered": triggered,
        "decision": "up" if triggered else None,
        "conclusion": conclusion,
        "evidence_strength": evidence_strength,
        "windows": {
            "current_start": current_hours[0].isoformat(),
            "current_end": current_hours[-1].isoformat(),
            "baseline_start": baseline_hours[0].isoformat(),
            "baseline_end": baseline_hours[-1].isoformat(),
            "current_hours": 24,
            "baseline_days": 5,
        },
        "metrics": metrics,
        "body_temperature": {
            "rise_threshold_c": float(body["rise_threshold_c"]),
            "strong_rise_threshold_c": float(body["strong_rise_threshold_c"]),
            "min_rising_layers": int(body["min_rising_layers"]),
            "rising_layers": rising_layers,
            "strong_rising_layers": strong_layers,
            "layers": layer_results,
            "gate_pass": layer_gate_pass,
        },
        "sustained_trend": {
            "required_consecutive_hours": required_consecutive,
            "max_consecutive_hours": consecutive,
            "qualified_hour_count": sum(hourly_qualification.values()),
            "gate_pass": duration_gate_pass,
            "hours": hourly_details,
        },
        "gates": {
            "data_sufficient": data_sufficient,
            "core_all_pass": core_all_pass,
            "body_layers_pass": layer_gate_pass,
            "duration_pass": duration_gate_pass,
        },
        "missing_reasons": insufficient,
        "source_record_count": record_count,
        "safety": config["safety"],
    }


def _insufficient_result(
    config: Mapping[str, Any],
    evaluation_hour: Optional[datetime],
    reasons: list[str],
    record_count: int,
) -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "rule_id": config["rule_id"],
        "rule_name": config["rule_name"],
        "furnace_id": config["furnace_id"],
        "evaluation_time": evaluation_hour.isoformat() if evaluation_hour else None,
        "status": "insufficient_data",
        "triggered": False,
        "decision": None,
        "conclusion": "数据不足，暂不能判断软熔带上移",
        "evidence_strength": "not_triggered",
        "metrics": {},
        "body_temperature": {"layers": [], "rising_layers": [], "gate_pass": False},
        "sustained_trend": {"required_consecutive_hours": 12, "max_consecutive_hours": 0, "gate_pass": False},
        "gates": {"data_sufficient": False, "core_all_pass": False, "body_layers_pass": False, "duration_pass": False},
        "missing_reasons": reasons,
        "source_record_count": record_count,
        "safety": config["safety"],
    }


def _prepare_history_series(
    hourly_records: Iterable[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build reusable hourly series once for threshold sensitivity replay."""
    coverage = config["coverage"]
    min_core_samples = int(coverage["min_core_samples_per_hour"])
    min_body_samples = int(coverage["min_body_samples_per_point_hour"])
    raw: dict[str, dict[datetime, tuple[float, int]]] = defaultdict(dict)
    record_count = 0
    for record in hourly_records:
        name = str(record.get("variable_name") or "").strip()
        value = _finite(record.get("value"))
        bucket_raw = record.get("bucket", record.get("ts"))
        if not name or value is None or bucket_raw in (None, ""):
            continue
        sample_count = int(record.get("sample_count") or 0)
        if sample_count < 1:
            continue
        raw[name][_hour(bucket_raw)] = (value, sample_count)
        record_count += 1

    all_hours = sorted({hour for series in raw.values() for hour in series})
    top_series: dict[datetime, tuple[float, int]] = {}
    for hour in all_hours:
        direct = raw.get("T_top", {}).get(hour)
        if direct is not None and direct[1] >= min_core_samples:
            top_series[hour] = direct
            continue
        points = [raw.get(f"T_top_{sector}", {}).get(hour) for sector in "ABCD"]
        valid = [point for point in points if point is not None and point[1] >= min_core_samples]
        if len(valid) >= int(coverage["min_top_points_per_hour"]):
            top_series[hour] = (fmean(point[0] for point in valid), sum(point[1] for point in valid))

    core_series: dict[str, dict[datetime, tuple[float, int]]] = {
        "top_temperature": top_series
    }
    for key, spec in config["core_metrics"].items():
        if key == "top_temperature":
            continue
        variable = str(spec["variables"][0])
        core_series[key] = {
            hour: sample
            for hour, sample in raw.get(variable, {}).items()
            if sample[1] >= min_core_samples
        }

    body = config["body_temperature"]
    layer_series: dict[int, dict[datetime, tuple[float, int]]] = {}
    for layer_raw in body["layers"]:
        layer = int(layer_raw)
        series: dict[datetime, tuple[float, int]] = {}
        for hour in all_hours:
            points = [raw.get(f"T_body_L{layer}_{sector}", {}).get(hour) for sector in body["sectors"]]
            valid = [point for point in points if point is not None and point[1] >= min_body_samples]
            if len(valid) >= int(coverage["min_body_sectors_per_layer_hour"]):
                series[hour] = (fmean(point[0] for point in valid), sum(point[1] for point in valid))
        layer_series[layer] = series
    return {
        "core_series": core_series,
        "layer_series": layer_series,
        "record_count": record_count,
    }


def _directional_metric_pass(
    delta: Optional[float],
    spec: Mapping[str, Any],
    movement: str,
) -> bool:
    effective = delta if movement == "up" or delta is None else -delta
    return _passes(effective, str(spec["direction"]), float(spec["threshold"]))


def _evaluate_prepared_history_hour(
    prepared: Mapping[str, Any],
    evaluation_hour: datetime,
    config: Mapping[str, Any],
    *,
    movement: str,
) -> dict[str, Any]:
    if movement not in {"up", "down"}:
        raise HczRuleSensitivityValidationError("movement必须是up或down")
    coverage = config["coverage"]
    current_hours = [evaluation_hour - timedelta(hours=offset) for offset in reversed(range(24))]
    baseline_end = evaluation_hour - timedelta(hours=24)
    baseline_hours = [baseline_end - timedelta(hours=offset) for offset in reversed(range(120))]
    core_series = prepared["core_series"]
    layer_series = prepared["layer_series"]

    core_current_passes: list[bool] = []
    core_coverage: list[bool] = []
    baseline_means: dict[str, float] = {}
    for key, spec in config["core_metrics"].items():
        current_mean, current_count = _series_mean(core_series[key], current_hours)
        baseline_mean, baseline_count = _series_mean(core_series[key], baseline_hours)
        enough = (
            current_count >= int(coverage["min_current_valid_hours"])
            and baseline_count >= int(coverage["min_baseline_valid_hours"])
        )
        delta = current_mean - baseline_mean if current_mean is not None and baseline_mean is not None else None
        core_coverage.append(enough)
        core_current_passes.append(enough and _directional_metric_pass(delta, spec, movement))
        if baseline_mean is not None:
            baseline_means[key] = baseline_mean

    body = config["body_temperature"]
    layer_baselines: dict[int, float] = {}
    layer_coverage: dict[int, bool] = {}
    directional_layers: list[int] = []
    for layer, series in layer_series.items():
        current_mean, current_count = _series_mean(series, current_hours)
        baseline_mean, baseline_count = _series_mean(series, baseline_hours)
        enough = (
            current_count >= int(coverage["min_current_valid_hours"])
            and baseline_count >= int(coverage["min_baseline_valid_hours"])
        )
        layer_coverage[layer] = enough
        if baseline_mean is not None:
            layer_baselines[layer] = baseline_mean
        delta = current_mean - baseline_mean if current_mean is not None and baseline_mean is not None else None
        effective = delta if movement == "up" or delta is None else -delta
        if enough and effective is not None and effective >= float(body["rise_threshold_c"]):
            directional_layers.append(layer)

    minimum_layers = int(body["min_rising_layers"])
    data_sufficient = all(core_coverage) and sum(layer_coverage.values()) >= minimum_layers
    core_gate = all(core_current_passes)
    body_gate = len(directional_layers) >= minimum_layers
    hourly_qualification: dict[datetime, bool] = {}
    for hour in current_hours:
        core_hour_passes = []
        for key, spec in config["core_metrics"].items():
            sample = core_series[key].get(hour)
            delta = sample[0] - baseline_means[key] if sample is not None and key in baseline_means else None
            core_hour_passes.append(_directional_metric_pass(delta, spec, movement))
        hourly_layers = 0
        for layer, series in layer_series.items():
            sample = series.get(hour)
            if sample is None or layer not in layer_baselines:
                continue
            delta = sample[0] - layer_baselines[layer]
            effective = delta if movement == "up" else -delta
            if effective >= float(body["rise_threshold_c"]):
                hourly_layers += 1
        hourly_qualification[hour] = all(core_hour_passes) and hourly_layers >= minimum_layers

    maximum_consecutive = _maximum_consecutive(current_hours, hourly_qualification)
    required_consecutive = int(config["windows"]["required_consecutive_hours"])
    duration_gate = maximum_consecutive >= required_consecutive
    triggered = data_sufficient and core_gate and body_gate and duration_gate
    return {
        "evaluation_time": evaluation_hour.isoformat(),
        "status": "triggered" if triggered else "not_triggered" if data_sufficient else "insufficient_data",
        "triggered": triggered,
        "core_pass_count": sum(core_current_passes),
        "directional_layer_count": len(directional_layers),
        "max_consecutive_hours": maximum_consecutive,
    }


def _history_episodes(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    episodes: list[list[dict[str, Any]]] = []
    active: list[dict[str, Any]] = []
    previous: Optional[datetime] = None
    for item in (result for result in results if result["triggered"]):
        stamp = _timestamp(item["evaluation_time"])
        if previous is None or stamp - previous == timedelta(hours=1):
            active.append(item)
        else:
            episodes.append(active)
            active = [item]
        previous = stamp
    if active:
        episodes.append(active)
    return [
        {
            "start": episode[0]["evaluation_time"],
            "end": episode[-1]["evaluation_time"],
            "triggered_evaluation_hours": len(episode),
            "peak_consecutive_hours": max(item["max_consecutive_hours"] for item in episode),
        }
        for episode in episodes
    ]


def _history_summary(results: list[dict[str, Any]], *, definition: str) -> dict[str, Any]:
    episodes = _history_episodes(results)
    return {
        "definition": definition,
        "evaluation_hours": len(results),
        "data_sufficient_hours": sum(item["status"] != "insufficient_data" for item in results),
        "insufficient_hours": sum(item["status"] == "insufficient_data" for item in results),
        "triggered_evaluation_hours": sum(item["triggered"] for item in results),
        "episode_count": len(episodes),
        "episodes": episodes[:100],
    }


def _history_comparison(
    baseline: list[dict[str, Any]],
    scenario: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_hours = {item["evaluation_time"] for item in baseline if item["triggered"]}
    scenario_hours = {item["evaluation_time"] for item in scenario if item["triggered"]}
    added = sorted(scenario_hours - baseline_hours)
    removed = sorted(baseline_hours - scenario_hours)
    return {
        "added_triggered_hour_count": len(added),
        "removed_triggered_hour_count": len(removed),
        "added_triggered_hours": added[:100],
        "removed_triggered_hours": removed[:100],
        "timestamps_truncated": len(added) > 100 or len(removed) > 100,
    }


def evaluate_hcz_rule_sensitivity(
    hourly_records: Iterable[Mapping[str, Any]],
    evaluation_hours: Iterable[Any],
    *,
    threshold_overrides: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Compare production defaults with editable thresholds over real history.

    The downward result is an exact sign-inverted mirror candidate. It is
    intentionally labelled as a trial result rather than a production rule.
    """
    config = load_hcz_upward_rule_config()
    scenario_config, adjusted = _scenario_config(config, threshold_overrides)
    prepared = _prepare_history_series(hourly_records, config)
    hours = sorted({_hour(value) for value in evaluation_hours})
    baseline_results: dict[str, list[dict[str, Any]]] = {}
    scenario_results: dict[str, list[dict[str, Any]]] = {}
    for movement in ("up", "down"):
        baseline_results[movement] = [
            _evaluate_prepared_history_hour(prepared, hour, config, movement=movement)
            for hour in hours
        ]
        scenario_results[movement] = [
            _evaluate_prepared_history_hour(prepared, hour, scenario_config, movement=movement)
            for hour in hours
        ]
    return {
        "ok": True,
        "schema_version": SENSITIVITY_SCHEMA_VERSION,
        "requirement_id": REQUIREMENT_ID,
        "rule_id": config["rule_id"],
        "read_only_trial": True,
        "production_defaults_changed": False,
        "evaluation_start": hours[0].isoformat() if hours else None,
        "evaluation_end": hours[-1].isoformat() if hours else None,
        "parameters": {
            "contract": sensitivity_parameter_contract(config),
            "baseline": sensitivity_defaults(config),
            "scenario": adjusted,
        },
        "baseline": {
            "up": _history_summary(baseline_results["up"], definition="production_upward_rule"),
            "down": _history_summary(baseline_results["down"], definition="symmetric_mirror_candidate"),
        },
        "scenario": {
            "up": _history_summary(scenario_results["up"], definition="trial_upward_rule"),
            "down": _history_summary(scenario_results["down"], definition="trial_symmetric_downward_candidate"),
        },
        "comparison": {
            "up": _history_comparison(baseline_results["up"], scenario_results["up"]),
            "down": _history_comparison(baseline_results["down"], scenario_results["down"]),
        },
        "source_record_count": prepared["record_count"],
        "safety": {
            **config["safety"],
            "downward_definition": "symmetric_mirror_candidate_only",
            "threshold_persistence": "none",
        },
    }


__all__ = [
    "HczRuleSensitivityValidationError",
    "evaluate_hcz_upward_rule",
    "evaluate_hcz_rule_sensitivity",
    "load_hcz_upward_rule_config",
    "required_variable_names",
    "sensitivity_defaults",
    "sensitivity_parameter_contract",
]
