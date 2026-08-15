"""Interpretable cohesive-zone movement feature fusion.

Requirement: REQ-COHESIVE-ZONE-INTELLIGENT-DIAGNOSIS-20260810.

The source document lists process features and directional rules but does not
provide accepted ``H_cz`` labels, training samples, or a calibrated model.
This module therefore implements a conservative, deterministic feature layer:

* strictly historical current/reference windows with no future fill;
* a complete machine-readable feature vector for later ML training;
* advisory up/stable/down probabilities and related-condition evidence;
* fixed ``estimated/uncalibrated/control_use=prohibited`` metadata.

It does not claim to be a trained Chronos-2, TabPFN, or Transformer model.
Those models can consume the emitted feature vector after accepted labels and
time-cut validation data become available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pandas as pd
import yaml


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "cohesive_zone_intelligent_diagnosis.yaml"
)
_TIMESTAMP_COLUMNS = ("timestamp", "time", "ts", "datetime")


def _finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _iso(value: Optional[pd.Timestamp]) -> Optional[str]:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).isoformat()


@dataclass(frozen=True)
class _WindowBounds:
    current_start: pd.Timestamp
    current_end: pd.Timestamp
    reference_start: pd.Timestamp
    reference_end: pd.Timestamp


def load_intelligent_diagnosis_config(
    config_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Load and validate the diagnosis configuration.

    Raises:
        FileNotFoundError: The YAML file does not exist.
        ValueError: Required sections or safety boundaries are invalid.
    """
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"cohesive-zone diagnosis config not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    required = ("model", "time", "decision", "features", "risk_labels")
    missing = [section for section in required if section not in config]
    if missing:
        raise ValueError(f"cohesive-zone diagnosis config missing sections: {missing}")
    confidence_cap = _finite_float(config["model"].get("confidence_cap"))
    if confidence_cap is None or not 0.0 <= confidence_cap <= 0.45:
        raise ValueError("model.confidence_cap must be in [0, 0.45]")
    if config["model"].get("control_use") != "prohibited":
        raise ValueError("model.control_use must remain prohibited")
    if not config["features"]:
        raise ValueError("features must not be empty")
    return config


def _normalise_frame(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas.DataFrame")
    frame = data.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        timestamp_column = next(
            (name for name in _TIMESTAMP_COLUMNS if name in frame.columns), None
        )
        if timestamp_column is None:
            raise ValueError(
                "data must have a DatetimeIndex or timestamp/time/ts/datetime column"
            )
        timestamps = pd.to_datetime(frame.pop(timestamp_column), errors="coerce")
        frame = frame.loc[timestamps.notna()].copy()
        frame.index = pd.DatetimeIndex(timestamps.loc[timestamps.notna()])
    else:
        frame = frame.loc[frame.index.notna()].copy()
    if frame.empty:
        return frame
    frame = frame.sort_index()
    return frame.loc[~frame.index.duplicated(keep="last")]


def _align_evaluation_time(value: Any, index: pd.DatetimeIndex) -> pd.Timestamp:
    evaluation = pd.Timestamp(index.max() if value is None else value)
    if index.tz is None and evaluation.tzinfo is not None:
        return evaluation.tz_localize(None)
    if index.tz is not None and evaluation.tzinfo is None:
        return evaluation.tz_localize(index.tz)
    if index.tz is not None and evaluation.tzinfo is not None:
        return evaluation.tz_convert(index.tz)
    return evaluation


def _make_bounds(evaluation: pd.Timestamp, config: Mapping[str, Any]) -> _WindowBounds:
    time_config = config["time"]
    current_start = evaluation - pd.Timedelta(
        minutes=float(time_config["current_window_minutes"])
    )
    reference_end = current_start - pd.Timedelta(
        minutes=float(time_config["reference_separation_minutes"])
    )
    reference_start = reference_end - pd.Timedelta(
        minutes=float(time_config["reference_window_minutes"])
    )
    return _WindowBounds(current_start, evaluation, reference_start, reference_end)


def _body_columns(frame: pd.DataFrame, layers: Sequence[str]) -> list[str]:
    prefixes = tuple(f"T_body_{layer}_" for layer in layers)
    return [column for column in frame.columns if column.startswith(prefixes)]


def _concept_series(
    frame: pd.DataFrame, meta: Mapping[str, Any]
) -> tuple[Optional[pd.Series], Optional[str]]:
    direct_columns = [name for name in meta.get("columns", []) if name in frame.columns]
    columns = direct_columns or _body_columns(frame, meta.get("body_layers", []))
    if not columns:
        return None, None
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce")
    valid_min = float(meta["valid_min"])
    valid_max = float(meta["valid_max"])
    numeric = numeric.where(numeric.ge(valid_min) & numeric.le(valid_max))
    if meta.get("combine") == "median" or len(columns) > 1:
        series = numeric.median(axis=1, skipna=True)
        source = "+".join(columns)
    else:
        series = numeric[columns[0]]
        source = columns[0]
    return series.dropna(), source


def _window_values(
    series: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
    minimum_samples: int,
) -> Optional[pd.Series]:
    values = series.loc[(series.index >= start) & (series.index <= end)].dropna()
    return values if len(values) >= minimum_samples else None


def _statistic(values: pd.Series, statistic: str) -> float:
    if statistic == "volatility":
        return float(values.quantile(0.90) - values.quantile(0.10))
    return float(values.median())


def _softmax(values: Sequence[float]) -> list[float]:
    maximum = max(values)
    exponents = [math.exp(value - maximum) for value in values]
    total = sum(exponents)
    return [value / total for value in exponents]


def _unavailable(
    config: Mapping[str, Any],
    evaluation: Optional[pd.Timestamp],
    reasons: Sequence[str],
    *,
    drivers: Optional[Sequence[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    model = config["model"]
    return {
        "schema": "cohesive_zone_intelligent_diagnosis.v1",
        "status": "unavailable",
        "evaluation_time": _iso(evaluation),
        "model_version": model["version"],
        "prediction_method": model["method"],
        "evidence": model["evidence"],
        "calibration_status": model["calibration_status"],
        "control_use": model["control_use"],
        "confidence": 0.0,
        "reason_codes": list(dict.fromkeys(reasons)),
        "drivers": list(drivers or []),
        "warnings": [
            "输入不足，未形成软熔带移动诊断",
            "本模型未使用真实H_cz标签标定，禁止自动控制",
        ],
    }


def diagnose_cohesive_zone_movement(
    data: pd.DataFrame,
    *,
    evaluation_time: Any = None,
    config_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Build the document-defined feature vector and movement diagnosis.

    Args:
        data: One-minute process data with a DatetimeIndex or timestamp column.
        evaluation_time: Optional historical cutoff; later rows are discarded.
        config_path: Optional YAML override.

    Returns:
        JSON-serialisable diagnosis with movement probabilities, feature
        vectors, data coverage, related-condition evidence, and safety labels.

    This function never trains a model or writes production state.
    """
    config = load_intelligent_diagnosis_config(config_path)
    frame = _normalise_frame(data)
    if frame.empty:
        return _unavailable(config, None, ["empty_input"])
    evaluation = _align_evaluation_time(evaluation_time, frame.index)
    frame = frame.loc[frame.index <= evaluation].copy()
    if frame.empty:
        return _unavailable(config, evaluation, ["no_data_at_or_before_evaluation_time"])
    bounds = _make_bounds(evaluation, config)
    minimum_samples = int(config["time"]["min_samples_per_window"])
    maximum_age = pd.Timedelta(minutes=float(config["time"]["max_age_minutes"]))

    drivers: list[dict[str, Any]] = []
    scored: list[tuple[float, float]] = []
    available_groups: dict[str, int] = {}
    group_totals: dict[str, int] = {}
    feature_vector: dict[str, Optional[float]] = {}
    trend_vector: dict[str, Optional[float]] = {}
    risk_evidence: dict[str, list[tuple[float, float, str]]] = {
        key: [] for key in config["risk_labels"]
    }
    total_movement_weight = 0.0
    available_movement_weight = 0.0

    for feature_name, meta in config["features"].items():
        group = str(meta["group"])
        group_totals[group] = group_totals.get(group, 0) + 1
        movement_weight = float(meta.get("movement_weight", 0.0))
        total_movement_weight += max(movement_weight, 0.0)
        series, source = _concept_series(frame, meta)
        if series is None or series.empty:
            feature_vector[feature_name] = None
            trend_vector[feature_name] = None
            continue
        latest = pd.Timestamp(series.loc[series.index <= evaluation].index.max())
        if evaluation - latest > maximum_age:
            feature_vector[feature_name] = None
            trend_vector[feature_name] = None
            continue
        current_values = _window_values(
            series, bounds.current_start, bounds.current_end, minimum_samples
        )
        statistic = str(meta.get("statistic", "level"))
        if current_values is None:
            feature_vector[feature_name] = None
            trend_vector[feature_name] = None
            continue
        current = _statistic(current_values, statistic)
        if statistic == "current_level":
            reference = 0.0
        else:
            reference_values = _window_values(
                series, bounds.reference_start, bounds.reference_end, minimum_samples
            )
            if reference_values is None:
                feature_vector[feature_name] = round(current, 6)
                trend_vector[feature_name] = None
                continue
            reference = _statistic(reference_values, statistic)
        scale = max(float(meta["delta_scale"]), float.fromhex("0x1.0p-52"))
        raw_delta = current - reference
        direction_up = float(meta.get("direction_up", 0.0))
        signal = _clamp(raw_delta / scale, -1.0, 1.0) * direction_up
        signal = _clamp(signal, -1.0, 1.0)
        feature_vector[feature_name] = round(current, 6)
        trend_vector[feature_name] = round(signal, 6)
        available_groups[group] = available_groups.get(group, 0) + 1
        if movement_weight > 0 and direction_up != 0:
            scored.append((signal, movement_weight))
            available_movement_weight += movement_weight
        for risk, relationship in meta.get("risk_links", {}).items():
            risk_direction, risk_weight = float(relationship[0]), float(relationship[1])
            support = _clamp(signal * risk_direction, 0.0, 1.0)
            risk_evidence.setdefault(risk, []).append(
                (support, risk_weight, feature_name)
            )
        drivers.append(
            {
                "feature": feature_name,
                "label": meta["label"],
                "group": group,
                "source": source,
                "statistic": statistic,
                "current": round(current, 6),
                "reference": round(reference, 6),
                "delta": round(raw_delta, 6),
                "normalised_up_signal": round(signal, 6),
                "movement_weight": movement_weight,
                "sample_time": _iso(latest),
            }
        )

    decision = config["decision"]
    group_coverage = {
        group: round(available_groups.get(group, 0) / total, 6)
        for group, total in group_totals.items()
    }
    missing_required_groups = [
        group
        for group in decision["required_groups"]
        if group_coverage.get(group, 0.0) < float(decision["min_group_coverage"])
    ]
    reasons: list[str] = []
    if len(scored) < int(decision["min_scored_features"]):
        reasons.append("insufficient_scored_features")
    reasons.extend(f"insufficient_{group}" for group in missing_required_groups)
    if reasons:
        return _unavailable(config, evaluation, reasons, drivers=drivers)

    numerator = sum(signal * weight for signal, weight in scored)
    denominator = sum(weight for _signal, weight in scored)
    movement_score = numerator / denominator if denominator else 0.0
    threshold = float(decision["stable_score_threshold"])
    if movement_score > threshold:
        direction = "up"
    elif movement_score < -threshold:
        direction = "down"
    else:
        direction = "stable"

    sharpness = float(decision["probability_sharpness"])
    logits = [
        sharpness * movement_score,
        float(decision["stable_logit_bias"])
        - float(decision["stable_logit_decay"]) * abs(movement_score),
        -sharpness * movement_score,
    ]
    up_probability, stable_probability, down_probability = _softmax(logits)
    coverage = _clamp(
        available_movement_weight / max(total_movement_weight, 1e-12), 0.0, 1.0
    )
    evidence_strength = sum(abs(signal) * weight for signal, weight in scored) / denominator
    confidence_cap = float(config["model"]["confidence_cap"])
    confidence = confidence_cap * coverage * (0.35 + 0.65 * evidence_strength)

    related_conditions: list[dict[str, Any]] = []
    for risk, label in config["risk_labels"].items():
        evidence = risk_evidence.get(risk, [])
        weight_total = sum(weight for _support, weight, _name in evidence)
        support = (
            sum(value * weight for value, weight, _name in evidence) / weight_total
            if weight_total
            else 0.0
        )
        related_conditions.append(
            {
                "condition": risk,
                "label": label,
                "support": round(_clamp(support, 0.0, 1.0), 6),
                "evidence_features": [
                    name for value, _weight, name in evidence if value > 0
                ],
                "relation": "association_only",
            }
        )

    model = config["model"]
    return {
        "schema": "cohesive_zone_intelligent_diagnosis.v1",
        "status": "available",
        "evaluation_time": _iso(evaluation),
        "model_version": model["version"],
        "prediction_method": model["method"],
        "evidence": model["evidence"],
        "calibration_status": model["calibration_status"],
        "control_use": model["control_use"],
        "movement": {
            "direction": direction,
            "score": round(movement_score, 6),
            "probabilities": {
                "up": round(up_probability, 6),
                "stable": round(stable_probability, 6),
                "down": round(down_probability, 6),
            },
            "field_summary": {
                "up": "顶凉、压高、料慢、风紧",
                "down": "顶热、压松、炉凉",
                "stable": "当前与历史参考窗口未形成显著合成方向",
            }[direction],
        },
        "confidence": round(_clamp(confidence, 0.0, confidence_cap), 6),
        "input_coverage": round(coverage, 6),
        "group_coverage": group_coverage,
        "feature_vector": feature_vector,
        "trend_vector": trend_vector,
        "drivers": drivers,
        "related_conditions": related_conditions,
        "ml_readiness": {
            "feature_vector_ready": True,
            "accepted_h_cz_labels_available": False,
            "trained_sequence_model": False,
            "next_step": "取得经接受的H_cz真值后按时间切分训练和回测Chronos-2/TabPFN/Transformer候选模型",
        },
        "warnings": [
            "软熔带移动为未标定估计，不是现场实测值",
            "关联炉况只提供证据，不覆盖现有8类炉况规则分数",
            "禁止用于自动控制",
        ],
    }


def estimate_and_diagnose_cohesive_zone(
    data: pd.DataFrame,
    *,
    evaluation_time: Any = None,
    estimator_config_path: Optional[str | Path] = None,
    diagnosis_config_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Run the existing C2 geometry estimator and the new diagnosis together."""
    from .cohesive_zone_estimator import estimate_cohesive_zone

    geometry = estimate_cohesive_zone(
        data,
        evaluation_time=evaluation_time,
        config_path=estimator_config_path,
    )
    diagnosis = diagnose_cohesive_zone_movement(
        data,
        evaluation_time=evaluation_time,
        config_path=diagnosis_config_path,
    )
    geometry_direction = (geometry.get("movement") or {}).get("direction")
    diagnosis_direction = (diagnosis.get("movement") or {}).get("direction")
    if geometry_direction and diagnosis_direction:
        direction_consistency = (
            "consistent" if geometry_direction == diagnosis_direction else "review_required"
        )
    else:
        direction_consistency = "not_comparable"
    return {
        "schema": "cohesive_zone_estimate_and_diagnosis.v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "cohesive_zone": geometry,
        "intelligent_diagnosis": diagnosis,
        "direction_consistency": direction_consistency,
        "control_use": "prohibited",
    }
