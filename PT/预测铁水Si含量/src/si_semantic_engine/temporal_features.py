"""Leakage-safe temporal micro-neurons for high-latency BF sensor series.

The functions in this module are deliberately independent from PostgreSQL.
Callers provide a long-form frame with ``ts``, ``sensor_id`` and ``value``.
Only observations at or before the prediction cutoff are admitted.

Requirement:
    REQ-SI-TEMPORAL-NEURONS-V2-20260726
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import ceil
import re
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_WINDOWS_MINUTES = (30, 60, 120, 240)
GOOD_QUALITY_VALUES = {"good", "0", "192"}


@dataclass(frozen=True)
class TemporalFeatureConfig:
    """Contract for deterministic per-sensor temporal feature extraction."""

    windows_minutes: tuple[int, ...] = DEFAULT_WINDOWS_MINUTES
    frequency_minutes: int = 1
    minimum_points: int = 3
    spike_mad_multiplier: float = 3.0

    def __post_init__(self) -> None:
        if not self.windows_minutes:
            raise ValueError("windows_minutes cannot be empty")
        if any(int(item) <= 0 for item in self.windows_minutes):
            raise ValueError("all windows must be positive")
        if self.frequency_minutes <= 0:
            raise ValueError("frequency_minutes must be positive")
        if self.minimum_points < 2:
            raise ValueError("minimum_points must be at least 2")
        if self.spike_mad_multiplier <= 0:
            raise ValueError("spike_mad_multiplier must be positive")


def _safe_sensor_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("sensor_id cannot be blank")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_")


def _quality_mask(values: pd.Series) -> pd.Series:
    normalized = values.astype(str).str.strip().str.lower()
    return normalized.isin(GOOD_QUALITY_VALUES)


def _longest_false_run(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        if bool(value):
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return int(longest)


def _finite_or_nan(value: float) -> float:
    return float(value) if np.isfinite(value) else float("nan")


def _series_features(
    series: pd.Series,
    *,
    cutoff: pd.Timestamp,
    expected_count: int,
    minimum_points: int,
    spike_mad_multiplier: float,
    occupancy: np.ndarray,
) -> dict[str, float]:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    count = int(clean.size)
    base: dict[str, float] = {
        "count": float(count),
        "coverage_ratio": float(min(1.0, count / max(expected_count, 1))),
        "longest_missing_run": float(_longest_false_run(occupancy)),
    }
    if count == 0:
        return {
            **base,
            **{
                name: float("nan")
                for name in (
                    "latest",
                    "mean",
                    "median",
                    "min",
                    "max",
                    "range",
                    "std",
                    "iqr",
                    "mad",
                    "slope_per_minute",
                    "delta",
                    "early_late_delta",
                    "diff_mean",
                    "diff_std",
                    "total_variation",
                    "acf1",
                    "sign_change_rate",
                    "spike_rate",
                    "upper_excursion_fraction",
                    "lower_excursion_fraction",
                    "last_age_minutes",
                )
            },
        }

    values = clean.to_numpy(dtype=float)
    median = float(np.median(values))
    q25, q75 = np.quantile(values, [0.25, 0.75])
    mad = float(np.median(np.abs(values - median)))
    std = float(np.std(values, ddof=1)) if count >= 2 else 0.0
    diffs = np.diff(values)
    last_age = max(
        0.0,
        float((cutoff - pd.Timestamp(clean.index[-1])).total_seconds() / 60.0),
    )
    output = {
        **base,
        "latest": float(values[-1]),
        "mean": float(np.mean(values)),
        "median": median,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "range": float(np.max(values) - np.min(values)),
        "std": std,
        "iqr": float(q75 - q25),
        "mad": mad,
        "delta": float(values[-1] - values[0]),
        "diff_mean": float(np.mean(diffs)) if diffs.size else 0.0,
        "diff_std": (
            float(np.std(diffs, ddof=1)) if diffs.size >= 2 else 0.0
        ),
        "total_variation": float(np.sum(np.abs(diffs))),
        "last_age_minutes": last_age,
    }

    if count >= minimum_points:
        elapsed = (
            clean.index.to_series().sub(clean.index[0]).dt.total_seconds()
            / 60.0
        ).to_numpy(dtype=float)
        output["slope_per_minute"] = _finite_or_nan(
            np.polyfit(elapsed, values, 1)[0]
        )
        block = max(1, count // 3)
        output["early_late_delta"] = float(
            np.mean(values[-block:]) - np.mean(values[:block])
        )
        centered = values - np.mean(values)
        denominator = float(np.dot(centered, centered))
        output["acf1"] = (
            float(np.dot(centered[:-1], centered[1:]) / denominator)
            if denominator > 0
            else 0.0
        )
    else:
        output["slope_per_minute"] = float("nan")
        output["early_late_delta"] = float("nan")
        output["acf1"] = float("nan")

    if diffs.size >= 2:
        signs = np.sign(diffs)
        nonzero = signs[signs != 0]
        output["sign_change_rate"] = (
            float(np.mean(nonzero[1:] != nonzero[:-1]))
            if nonzero.size >= 2
            else 0.0
        )
    else:
        output["sign_change_rate"] = 0.0

    robust_scale = max(1.4826 * mad, std, 1e-12)
    output["spike_rate"] = float(
        np.mean(
            np.abs(values - median)
            > spike_mad_multiplier * robust_scale
        )
    )
    output["upper_excursion_fraction"] = float(
        np.mean(values > median + robust_scale)
    )
    output["lower_excursion_fraction"] = float(
        np.mean(values < median - robust_scale)
    )
    return output


def derive_temporal_micro_neurons(
    frame: pd.DataFrame,
    cutoff: Any,
    *,
    sensor_ids: Sequence[str] | None = None,
    config: TemporalFeatureConfig | None = None,
) -> dict[str, float]:
    """Derive multi-window features without admitting future observations.

    Window semantics are ``(cutoff - window, cutoff]``. Duplicate samples in
    the same sensor/minute are reduced with their median. When a ``quality``
    column exists, only Good/0/192 samples contribute to value statistics.
    Coverage and missing-run features are still calculated on the expected
    one-minute grid.
    """

    required = {"ts", "sensor_id", "value"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    config = config or TemporalFeatureConfig()
    cutoff_ts = pd.Timestamp(cutoff)
    if cutoff_ts.tzinfo is not None:
        cutoff_ts = cutoff_ts.tz_localize(None)

    working = frame.loc[:, list(frame.columns)].copy()
    working["ts"] = pd.to_datetime(working["ts"], errors="coerce")
    if getattr(working["ts"].dt, "tz", None) is not None:
        working["ts"] = working["ts"].dt.tz_localize(None)
    working = working[working["ts"].notna() & (working["ts"] <= cutoff_ts)]
    working["sensor_id"] = working["sensor_id"].map(_safe_sensor_id)
    working["value"] = pd.to_numeric(working["value"], errors="coerce")
    if "quality" in working.columns:
        working.loc[~_quality_mask(working["quality"]), "value"] = np.nan

    selected = (
        [_safe_sensor_id(item) for item in sensor_ids]
        if sensor_ids is not None
        else sorted(working["sensor_id"].dropna().unique().tolist())
    )
    output: dict[str, float] = {}
    frequency = f"{config.frequency_minutes}min"
    for sensor_id in selected:
        sensor = working[working["sensor_id"] == sensor_id].copy()
        for window in config.windows_minutes:
            start = cutoff_ts - pd.Timedelta(minutes=int(window))
            subset = sensor[(sensor["ts"] > start) & (sensor["ts"] <= cutoff_ts)]
            expected_count = int(
                ceil(int(window) / config.frequency_minutes)
            )
            grid = pd.date_range(
                end=cutoff_ts.floor(frequency),
                periods=expected_count,
                freq=frequency,
            )
            if subset.empty:
                reduced = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            else:
                subset["bucket"] = subset["ts"].dt.floor(frequency)
                reduced = subset.groupby("bucket", sort=True)["value"].median()
            occupancy = grid.isin(reduced.dropna().index)
            features = _series_features(
                reduced,
                cutoff=cutoff_ts,
                expected_count=expected_count,
                minimum_points=config.minimum_points,
                spike_mad_multiplier=config.spike_mad_multiplier,
                occupancy=np.asarray(occupancy, dtype=bool),
            )
            prefix = f"ts__{sensor_id}__w{int(window)}"
            for name, value in features.items():
                output[f"{prefix}__{name}"] = float(value)
    return output


def temporal_feature_names(
    sensor_ids: Iterable[str],
    config: TemporalFeatureConfig | None = None,
) -> list[str]:
    """Return the deterministic feature contract without needing observations."""

    config = config or TemporalFeatureConfig()
    statistic_names = (
        "count",
        "coverage_ratio",
        "longest_missing_run",
        "latest",
        "mean",
        "median",
        "min",
        "max",
        "range",
        "std",
        "iqr",
        "mad",
        "slope_per_minute",
        "delta",
        "early_late_delta",
        "diff_mean",
        "diff_std",
        "total_variation",
        "acf1",
        "sign_change_rate",
        "spike_rate",
        "upper_excursion_fraction",
        "lower_excursion_fraction",
        "last_age_minutes",
    )
    names: list[str] = []
    for sensor_id in sensor_ids:
        safe_id = _safe_sensor_id(sensor_id)
        for window in config.windows_minutes:
            names.extend(
                f"ts__{safe_id}__w{int(window)}__{stat}"
                for stat in statistic_names
            )
    return names
