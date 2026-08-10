from __future__ import annotations

import math
from statistics import fmean, pstdev
from typing import Any, Iterable


SCHEMA = "bf.timeseries.ridge-delta.v1"
CONTEXT_MINUTES = 480
HORIZON_MINUTES = 120
TARGET_LAGS = (0, 1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 479)
ROLLING_WINDOWS = (5, 15, 30, 60, 120, 240, 480)
COVARIATE_LAGS = (0, 5, 15, 30, 60, 120, 240, 479)
COVARIATE_WINDOWS = (30, 120, 480)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def historical_fill(values: Iterable[Any], required: int = CONTEXT_MINUTES) -> list[float]:
    raw = [finite(value) for value in values]
    if len(raw) < required:
        raise ValueError(f"context has {len(raw)} points; {required} required")
    raw = raw[-required:]
    first = next((value for value in raw if value is not None), None)
    if first is None:
        raise ValueError("context contains no finite values")
    output: list[float] = []
    previous = first
    for value in raw:
        if value is not None:
            previous = value
        output.append(float(previous))
    return output


def _window_features(prefix: str, values: list[float], windows: Iterable[int]) -> tuple[list[str], list[float]]:
    names: list[str] = []
    features: list[float] = []
    for window in windows:
        part = values[-window:]
        names.extend((f"{prefix}_mean_{window}", f"{prefix}_std_{window}", f"{prefix}_delta_{window}"))
        features.extend((fmean(part), pstdev(part) if len(part) > 1 else 0.0, part[-1] - part[0]))
    return names, features


def extract_feature_vector(
    target_values: Iterable[Any],
    covariate_values: dict[str, Iterable[Any]],
    covariate_ids: list[str],
) -> tuple[list[str], list[float]]:
    target = historical_fill(target_values)
    names = [f"target_lag_{lag}" for lag in TARGET_LAGS]
    features = [target[-1 - lag] for lag in TARGET_LAGS]
    window_names, window_features = _window_features("target", target, ROLLING_WINDOWS)
    names.extend(window_names)
    features.extend(window_features)
    for covariate_id in covariate_ids:
        if covariate_id not in covariate_values:
            raise ValueError(f"required covariate is missing: {covariate_id}")
        values = historical_fill(covariate_values[covariate_id])
        names.extend(f"{covariate_id}_lag_{lag}" for lag in COVARIATE_LAGS)
        features.extend(values[-1 - lag] for lag in COVARIATE_LAGS)
        cov_names, cov_features = _window_features(covariate_id, values, COVARIATE_WINDOWS)
        names.extend(cov_names)
        features.extend(cov_features)
    if not all(math.isfinite(value) for value in features):
        raise ValueError("feature vector contains non-finite values")
    return names, features


def quantile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

