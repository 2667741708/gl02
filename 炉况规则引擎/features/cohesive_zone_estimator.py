"""Interpretable low-confidence cohesive-zone root estimator.

This module implements REQ-BF3D-C2-001.  It estimates the wall-root movement,
thickness and circumferential eccentricity of the blast-furnace cohesive zone
from a one-minute wide :class:`pandas.DataFrame`.

The estimator is deliberately conservative:

* it never reads rows later than ``evaluation_time``;
* current and reference windows do not overlap and no backward fill is used;
* without direct cohesive-zone ground truth it always emits
  ``evidence="estimated"`` and ``calibration_status="uncalibrated"``;
* confidence is capped by configuration at 0.45;
* insufficient or stale inputs return a structured ``status="unavailable"``
  diagnostic rather than a plausible-looking geometry.

Public API:

``estimate_cohesive_zone(data, evaluation_time=None, config_path=None)``
    Return a JSON-serialisable dictionary.  A successful response can be
    placed directly under the Three.js ``estimated.cohesive_zone`` payload.
    An unavailable response must not be passed to the renderer as geometry;
    callers should retain or hide the previous estimate and show the supplied
    ``reason_codes``.

Input contract:

* a one-minute wide DataFrame with a ``DatetimeIndex``; alternatively a
  ``timestamp``, ``time``, ``ts`` or ``datetime`` column is accepted;
* body-temperature columns ``T_body_L7_A`` ... ``T_body_L13_H``;
* at least one pressure/permeability concept (DP, PI, 18 static pressures or
  one of the three static-pressure mean proxies);
* enough earlier data to form a strictly historical reference window.

This is an advisory visual estimate only.  It is not a production-control
signal and must be calibrated against an accepted plant reference before its
confidence policy can be changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import pandas as pd
import yaml


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "cohesive_zone_estimator.yaml"
)

_TIMESTAMP_COLUMNS: Tuple[str, ...] = ("timestamp", "time", "ts", "datetime")


def _finite_float(value: Any) -> Optional[float]:
    """Return a native finite float, otherwise ``None``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _weighted_mean(items: Iterable[Tuple[float, float]]) -> Optional[float]:
    numerator = 0.0
    denominator = 0.0
    for value, weight in items:
        if not math.isfinite(value) or not math.isfinite(weight) or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
    return numerator / denominator if denominator > 0 else None


def _iso_timestamp(value: Optional[pd.Timestamp]) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def load_cohesive_zone_config(
    config_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Load and minimally validate the REQ-BF3D-C2-001 YAML configuration."""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"cohesive-zone estimator config not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    required = (
        "model",
        "time",
        "coverage",
        "body_temperature",
        "pressure",
        "geometry",
        "eccentricity",
        "movement",
        "uncertainty",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"cohesive-zone estimator config missing sections: {missing}")
    confidence_cap = _finite_float(config["model"].get("confidence_cap"))
    if confidence_cap is None or not 0 <= confidence_cap <= 0.45:
        raise ValueError("model.confidence_cap must be in [0, 0.45]")
    return config


def _normalise_frame(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas.DataFrame")
    frame = data.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        timestamp_column = next(
            (column for column in _TIMESTAMP_COLUMNS if column in frame.columns),
            None,
        )
        if timestamp_column is None:
            raise ValueError(
                "data must have a DatetimeIndex or timestamp/time/ts/datetime column"
            )
        timestamps = pd.to_datetime(frame.pop(timestamp_column), errors="coerce")
        valid = timestamps.notna()
        frame = frame.loc[valid].copy()
        frame.index = pd.DatetimeIndex(timestamps.loc[valid])
    else:
        valid = frame.index.notna()
        frame = frame.loc[valid].copy()
    if frame.empty:
        return frame
    return frame.sort_index().loc[~frame.sort_index().index.duplicated(keep="last")]


def _align_evaluation_time(
    value: Optional[Any], index: pd.DatetimeIndex
) -> pd.Timestamp:
    if index.empty:
        if value is None:
            return pd.Timestamp(datetime.now())
        return pd.Timestamp(value)
    evaluation = pd.Timestamp(index.max() if value is None else value)
    index_tz = index.tz
    if index_tz is None and evaluation.tzinfo is not None:
        evaluation = evaluation.tz_localize(None)
    elif index_tz is not None and evaluation.tzinfo is None:
        evaluation = evaluation.tz_localize(index_tz)
    elif index_tz is not None and evaluation.tzinfo is not None:
        evaluation = evaluation.tz_convert(index_tz)
    return evaluation


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
    valid_min: float,
    valid_max: float,
) -> Optional[pd.Series]:
    if column not in frame.columns:
        return None
    series = pd.to_numeric(frame[column], errors="coerce")
    return series.where(series.between(valid_min, valid_max, inclusive="both"))


def _window_stat(
    frame: pd.DataFrame,
    column: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    valid_min: float,
    valid_max: float,
    min_samples: int,
) -> Optional[float]:
    series = _numeric_series(frame, column, valid_min, valid_max)
    if series is None:
        return None
    values = series.loc[(series.index >= start) & (series.index <= end)].dropna()
    if len(values) < min_samples:
        return None
    return _finite_float(values.median())


def _latest_valid_timestamp(
    frame: pd.DataFrame,
    columns: Sequence[str],
    valid_min: float,
    valid_max: float,
    evaluation_time: pd.Timestamp,
) -> Optional[pd.Timestamp]:
    latest: Optional[pd.Timestamp] = None
    for column in columns:
        series = _numeric_series(frame, column, valid_min, valid_max)
        if series is None:
            continue
        values = series.loc[series.index <= evaluation_time].dropna()
        if values.empty:
            continue
        timestamp = pd.Timestamp(values.index[-1])
        if latest is None or timestamp > latest:
            latest = timestamp
    return latest


def _first_available_stat(
    frame: pd.DataFrame,
    columns: Sequence[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    valid_min: float,
    valid_max: float,
    min_samples: int,
    freshness_time: Optional[pd.Timestamp] = None,
    max_age_minutes: Optional[float] = None,
) -> Tuple[Optional[float], Optional[str]]:
    for column in columns:
        if freshness_time is not None and max_age_minutes is not None:
            latest = _latest_valid_timestamp(
                frame,
                [column],
                valid_min,
                valid_max,
                freshness_time,
            )
            maximum_age = pd.Timedelta(minutes=float(max_age_minutes))
            if latest is None or freshness_time - latest > maximum_age:
                continue
        value = _window_stat(
            frame,
            column,
            start,
            end,
            valid_min,
            valid_max,
            min_samples,
        )
        if value is not None:
            return value, column
    return None, None


def _column_window_values(
    frame: pd.DataFrame,
    columns: Sequence[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    valid_min: float,
    valid_max: float,
    min_samples: int,
    freshness_time: Optional[pd.Timestamp] = None,
    max_age_minutes: Optional[float] = None,
) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for column in columns:
        if freshness_time is not None and max_age_minutes is not None:
            latest = _latest_valid_timestamp(
                frame,
                [column],
                valid_min,
                valid_max,
                freshness_time,
            )
            maximum_age = pd.Timedelta(minutes=float(max_age_minutes))
            if latest is None or freshness_time - latest > maximum_age:
                continue
        value = _window_stat(
            frame,
            column,
            start,
            end,
            valid_min,
            valid_max,
            min_samples,
        )
        if value is not None:
            values[column] = value
    return values


@dataclass(frozen=True)
class _WindowBounds:
    current_start: pd.Timestamp
    current_end: pd.Timestamp
    reference_start: pd.Timestamp
    reference_end: pd.Timestamp

    @property
    def centre_separation_hours(self) -> float:
        current_centre = self.current_start + (
            self.current_end - self.current_start
        ) / 2
        reference_centre = self.reference_start + (
            self.reference_end - self.reference_start
        ) / 2
        seconds = (current_centre - reference_centre).total_seconds()
        return max(seconds / 3600.0, 0.0)


def _make_bounds(evaluation_time: pd.Timestamp, config: Mapping[str, Any]) -> _WindowBounds:
    time_config = config["time"]
    current_minutes = float(time_config["current_window_minutes"])
    reference_minutes = float(time_config["reference_window_minutes"])
    separation_minutes = float(time_config["reference_separation_minutes"])
    current_start = evaluation_time - pd.Timedelta(minutes=current_minutes)
    reference_end = current_start - pd.Timedelta(minutes=separation_minutes)
    reference_start = reference_end - pd.Timedelta(minutes=reference_minutes)
    return _WindowBounds(
        current_start=current_start,
        current_end=evaluation_time,
        reference_start=reference_start,
        reference_end=reference_end,
    )


def _body_profiles(
    frame: pd.DataFrame,
    bounds: _WindowBounds,
    config: Mapping[str, Any],
    evaluation_time: pd.Timestamp,
) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, float]],
    List[str],
]:
    body = config["body_temperature"]
    time_config = config["time"]
    min_samples = int(time_config["min_samples_per_sensor_per_window"])
    valid_min = float(body["valid_min"])
    valid_max = float(body["valid_max"])
    maximum_age = pd.Timedelta(minutes=float(time_config["max_body_age_minutes"]))

    current_layers: Dict[str, float] = {}
    reference_layers: Dict[str, float] = {}
    current_matrix: Dict[str, Dict[str, float]] = {}
    reference_matrix: Dict[str, Dict[str, float]] = {}
    stale_columns: List[str] = []

    for layer in body["layers"]:
        current_values: Dict[str, float] = {}
        reference_values: Dict[str, float] = {}
        for sector in body["sectors"]:
            column = f"T_body_{layer}_{sector}"
            series = _numeric_series(frame, column, valid_min, valid_max)
            latest = None
            if series is not None:
                valid = series.loc[series.index <= evaluation_time].dropna()
                latest = pd.Timestamp(valid.index[-1]) if not valid.empty else None
            is_fresh = latest is not None and evaluation_time - latest <= maximum_age
            current_value = None
            if is_fresh:
                current_value = _window_stat(
                    frame,
                    column,
                    bounds.current_start,
                    bounds.current_end,
                    valid_min,
                    valid_max,
                    min_samples,
                )
            elif latest is not None:
                stale_columns.append(column)
            reference_value = _window_stat(
                frame,
                column,
                bounds.reference_start,
                bounds.reference_end,
                valid_min,
                valid_max,
                min_samples,
            )
            if current_value is not None:
                current_values[sector] = current_value
            if reference_value is not None:
                reference_values[sector] = reference_value

        min_sectors = int(config["coverage"]["min_sectors_per_layer"])
        if len(current_values) >= min_sectors:
            current_matrix[layer] = current_values
            current_layers[layer] = float(
                pd.Series(list(current_values.values())).median()
            )
        if len(reference_values) >= min_sectors:
            reference_matrix[layer] = reference_values
            reference_layers[layer] = float(
                pd.Series(list(reference_values.values())).median()
            )
    return (
        current_layers,
        reference_layers,
        current_matrix,
        reference_matrix,
        sorted(set(stale_columns)),
    )


def _profile_centre(
    layer_values: Mapping[str, float],
    config: Mapping[str, Any],
) -> Tuple[Optional[float], Optional[float]]:
    body = config["body_temperature"]
    centroid = body["centroid"]
    available = [
        (float(body["layers"][layer]), float(value))
        for layer, value in layer_values.items()
        if layer in body["layers"]
    ]
    if not available:
        return None, None
    temperatures = [value for _, value in available]
    minimum = min(temperatures)
    span = max(temperatures) - minimum
    minimum_span = float(centroid["minimum_profile_span_degC"])
    denominator = max(span, minimum_span)
    floor = float(centroid["weight_floor"])
    power = float(centroid["weight_power"])
    weighted: List[Tuple[float, float]] = []
    for height, value in available:
        normalised = _clamp((value - minimum) / denominator, 0.0, 1.0)
        weighted.append((height, floor + normalised**power))
    centre = _weighted_mean(weighted)
    if centre is None:
        return None, None
    variance = _weighted_mean(
        ((height - centre) ** 2, weight) for (height, weight) in weighted
    )
    spread = math.sqrt(max(variance or 0.0, 0.0))
    return centre, spread


def _comparable_body_profiles(
    current_matrix: Mapping[str, Mapping[str, float]],
    reference_matrix: Mapping[str, Mapping[str, float]],
    config: Mapping[str, Any],
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
    """Build both profiles from identical ``(layer, sector)`` support."""
    body = config["body_temperature"]
    minimum_sectors = int(config["coverage"]["min_sectors_per_layer"])
    current_profile: Dict[str, float] = {}
    reference_profile: Dict[str, float] = {}
    shared_sectors_by_layer: Dict[str, List[str]] = {}
    support_matrix: Dict[str, Dict[str, bool]] = {}
    for layer in body["layers"]:
        current_values = current_matrix.get(layer, {})
        reference_values = reference_matrix.get(layer, {})
        shared = [
            sector
            for sector in body["sectors"]
            if sector in current_values and sector in reference_values
        ]
        shared_sectors_by_layer[layer] = shared
        support_matrix[layer] = {
            sector: sector in shared for sector in body["sectors"]
        }
        if len(shared) < minimum_sectors:
            continue
        current_profile[layer] = float(
            pd.Series([current_values[sector] for sector in shared]).median()
        )
        reference_profile[layer] = float(
            pd.Series([reference_values[sector] for sector in shared]).median()
        )
    total_cells = max(len(body["layers"]) * len(body["sectors"]), 1)
    shared_cells = sum(
        int(value)
        for row in support_matrix.values()
        for value in row.values()
    )
    return current_profile, reference_profile, {
        "shared_layers": sorted(current_profile),
        "shared_sectors_by_layer": shared_sectors_by_layer,
        "matrix": support_matrix,
        "coverage": round(shared_cells / total_cells, 6),
    }


def _concept_delta_index(
    frame: pd.DataFrame,
    concepts: Mapping[str, Mapping[str, Any]],
    bounds: _WindowBounds,
    default_valid_min: float,
    default_valid_max: float,
    min_samples: int,
    freshness_time: Optional[pd.Timestamp] = None,
    max_age_minutes: Optional[float] = None,
) -> Tuple[float, int, List[Dict[str, Any]]]:
    contributions: List[Tuple[float, float]] = []
    drivers: List[Dict[str, Any]] = []
    available = 0
    for concept, meta in concepts.items():
        valid_min = float(meta.get("valid_min", default_valid_min))
        valid_max = float(meta.get("valid_max", default_valid_max))
        columns = list(meta.get("columns", []))
        current, source = _first_available_stat(
            frame,
            columns,
            bounds.current_start,
            bounds.current_end,
            valid_min,
            valid_max,
            min_samples,
            freshness_time=freshness_time,
            max_age_minutes=max_age_minutes,
        )
        reference, _ = _first_available_stat(
            frame,
            columns,
            bounds.reference_start,
            bounds.reference_end,
            valid_min,
            valid_max,
            min_samples,
        )
        if current is None or reference is None:
            continue
        current_sample_time = _latest_valid_timestamp(
            frame,
            [source] if source is not None else columns,
            valid_min,
            valid_max,
            freshness_time or bounds.current_end,
        )
        reference_sample_time = _latest_valid_timestamp(
            frame,
            [source] if source is not None else columns,
            valid_min,
            valid_max,
            bounds.reference_end,
        )
        scale = max(float(meta["delta_scale"]), float.fromhex("0x1.0p-52"))
        direction = float(meta.get("direction", 1.0))
        weight = float(meta.get("weight", 1.0))
        contribution = _clamp((current - reference) / scale, -1.0, 1.0) * direction
        contributions.append((contribution, weight))
        available += 1
        drivers.append(
            {
                "group": concept,
                "source": source,
                "current": round(current, 6),
                "reference": round(reference, 6),
                "normalised_contribution": round(contribution, 6),
                "sample_time": _iso_timestamp(current_sample_time),
                "reference_sample_time": _iso_timestamp(
                    reference_sample_time
                ),
            }
        )
    index = _weighted_mean(contributions)
    return float(index or 0.0), available, drivers


def _static_level_stats(
    frame: pd.DataFrame,
    bounds: _WindowBounds,
    config: Mapping[str, Any],
    evaluation_time: pd.Timestamp,
) -> Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    int,
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    pressure = config["pressure"]
    min_samples = int(config["time"]["min_samples_per_sensor_per_window"])
    valid_min = float(pressure["valid_min"])
    valid_max = float(pressure["valid_max"])
    maximum_age_minutes = float(config["time"]["max_pressure_age_minutes"])
    gradient_config = pressure["static_gradient"]
    min_exact_sectors = int(gradient_config["min_exact_sectors_per_level"])
    current_levels: Dict[str, float] = {}
    reference_levels: Dict[str, float] = {}
    current_exact_matrix: Dict[str, Dict[str, float]] = {}
    drivers: List[Dict[str, Any]] = []

    for level, meta in pressure["static_levels"].items():
        exact_columns = list(meta["exact_columns"])
        current_exact = _column_window_values(
            frame,
            exact_columns,
            bounds.current_start,
            bounds.current_end,
            valid_min,
            valid_max,
            min_samples,
            freshness_time=evaluation_time,
            max_age_minutes=maximum_age_minutes,
        )
        reference_exact = _column_window_values(
            frame,
            exact_columns,
            bounds.reference_start,
            bounds.reference_end,
            valid_min,
            valid_max,
            min_samples,
        )
        if len(current_exact) >= min_exact_sectors:
            current_levels[level] = float(
                pd.Series(list(current_exact.values())).median()
            )
            current_exact_matrix[level] = {}
            for column, value in current_exact.items():
                sector = column.rsplit("_", 1)[-1]
                if sector in pressure["static_sector_angles_deg"]:
                    current_exact_matrix[level][sector] = value
        else:
            current_proxy, _ = _first_available_stat(
                frame,
                list(meta["proxy_columns"]),
                bounds.current_start,
                bounds.current_end,
                valid_min,
                valid_max,
                min_samples,
                freshness_time=evaluation_time,
                max_age_minutes=maximum_age_minutes,
            )
            if current_proxy is not None:
                current_levels[level] = current_proxy
        if len(reference_exact) >= min_exact_sectors:
            reference_levels[level] = float(
                pd.Series(list(reference_exact.values())).median()
            )
        else:
            reference_proxy, _ = _first_available_stat(
                frame,
                list(meta["proxy_columns"]),
                bounds.reference_start,
                bounds.reference_end,
                valid_min,
                valid_max,
                min_samples,
            )
            if reference_proxy is not None:
                reference_levels[level] = reference_proxy

    pressure_index = 0.0
    shared = [
        level
        for level in pressure["static_levels"]
        if level in current_levels and level in reference_levels
    ]
    minimum_levels = int(gradient_config["min_levels"])
    available_concepts = 0
    if len(shared) >= minimum_levels:
        available_concepts = 1
        ordered = sorted(
            shared,
            key=lambda level: float(pressure["static_levels"][level]["height_m"]),
        )
        current_gradient = abs(current_levels[ordered[0]] - current_levels[ordered[-1]])
        reference_gradient = abs(
            reference_levels[ordered[0]] - reference_levels[ordered[-1]]
        )
        pressure_index = _clamp(
            (current_gradient - reference_gradient)
            / float(gradient_config["delta_scale"]),
            -1.0,
            1.0,
        )
        drivers.append(
            {
                "group": "static_vertical_gradient",
                "source": f"{ordered[0]}->{ordered[-1]}",
                "current": round(current_gradient, 6),
                "reference": round(reference_gradient, 6),
                "normalised_contribution": round(pressure_index, 6),
            }
        )

    eccentric_levels = [
        level for level in shared if level in current_exact_matrix
    ]
    if len(eccentric_levels) >= minimum_levels:
        sector_residuals, sector_support = _balanced_residual_profile(
            current_exact_matrix,
            eccentric_levels,
            list(pressure["static_sector_angles_deg"]),
        )
    else:
        sector_residuals = {}
        sector_support = {
            "participating_rows": eccentric_levels,
            "shared_sectors": [],
            "matrix": {
                level: {
                    sector: bool(
                        level in current_exact_matrix
                        and sector in current_exact_matrix[level]
                    )
                    for sector in pressure["static_sector_angles_deg"]
                }
                for level in eccentric_levels
            },
            "raw_coverage": 0.0,
            "balanced_coverage": 0.0,
        }
    return (
        current_levels,
        reference_levels,
        sector_residuals,
        available_concepts,
        drivers,
        sector_support,
    )


def _harmonic_vector(
    values: Mapping[str, float],
    angles_deg: Mapping[str, float],
    normalisation: float,
) -> Tuple[float, float]:
    shared = [key for key in angles_deg if key in values]
    if len(shared) < 3:
        return 0.0, 0.0
    mean = sum(values[key] for key in shared) / len(shared)
    scale = max(float(normalisation), float.fromhex("0x1.0p-52"))
    x = 0.0
    y = 0.0
    for key in shared:
        deviation = _clamp((values[key] - mean) / scale, -1.0, 1.0)
        angle = math.radians(float(angles_deg[key]))
        x += deviation * math.cos(angle)
        y += deviation * math.sin(angle)
    harmonic_scale = 2.0 / len(shared)
    return x * harmonic_scale, y * harmonic_scale


def _balanced_residual_profile(
    matrix: Mapping[str, Mapping[str, float]],
    participating_rows: Sequence[str],
    sector_order: Sequence[str],
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Remove each row mean, then aggregate only equally supported sectors.

    A row is a furnace-temperature layer or a static-pressure elevation.  The
    strict shared-sector intersection prevents missing sensors at hotter or
    colder rows from becoming a false first-harmonic eccentricity.
    """
    rows = [row for row in participating_rows if row in matrix]
    shared_sectors = [
        sector
        for sector in sector_order
        if rows and all(sector in matrix[row] for row in rows)
    ]
    support_matrix = {
        row: {
            sector: bool(row in matrix and sector in matrix[row])
            for sector in sector_order
        }
        for row in participating_rows
    }
    residual_samples: MutableMapping[str, List[float]] = {
        sector: [] for sector in shared_sectors
    }
    for row in rows:
        row_mean = sum(matrix[row][sector] for sector in shared_sectors) / max(
            len(shared_sectors), 1
        )
        for sector in shared_sectors:
            residual_samples[sector].append(matrix[row][sector] - row_mean)
    residuals = {
        sector: float(pd.Series(values).median())
        for sector, values in residual_samples.items()
        if len(values) == len(rows) and values
    }
    total_cells = max(len(participating_rows) * len(sector_order), 1)
    present_cells = sum(
        int(present)
        for row in support_matrix.values()
        for present in row.values()
    )
    support = {
        "participating_rows": list(participating_rows),
        "shared_sectors": shared_sectors,
        "matrix": support_matrix,
        "raw_coverage": round(present_cells / total_cells, 6),
        "balanced_coverage": round(
            len(shared_sectors) / max(len(sector_order), 1), 6
        ),
    }
    return residuals, support


def _latest_times_by_group(
    frame: pd.DataFrame,
    config: Mapping[str, Any],
    evaluation_time: pd.Timestamp,
) -> Dict[str, Optional[pd.Timestamp]]:
    """Return the latest valid source timestamp for every evidence group."""

    def latest_of_specs(
        specs: Sequence[Tuple[Sequence[str], float, float]]
    ) -> Optional[pd.Timestamp]:
        candidates: List[pd.Timestamp] = []
        for columns, valid_min, valid_max in specs:
            timestamp = _latest_valid_timestamp(
                frame,
                columns,
                valid_min,
                valid_max,
                evaluation_time,
            )
            if timestamp is not None:
                candidates.append(timestamp)
        return max(candidates) if candidates else None

    body = config["body_temperature"]
    body_columns = [
        f"T_body_{layer}_{sector}"
        for layer in body["layers"]
        for sector in body["sectors"]
    ]
    pressure = config["pressure"]
    pressure_specs: List[Tuple[Sequence[str], float, float]] = [
        (
            list(meta["columns"]),
            float(meta.get("valid_min", pressure["valid_min"])),
            float(meta.get("valid_max", pressure["valid_max"])),
        )
        for meta in pressure["concepts"].values()
    ]
    pressure_specs.extend(
        (
            list(meta["exact_columns"]) + list(meta["proxy_columns"]),
            float(pressure["valid_min"]),
            float(pressure["valid_max"]),
        )
        for meta in pressure["static_levels"].values()
    )

    def section_specs(section_name: str) -> List[Tuple[Sequence[str], float, float]]:
        return [
            (
                list(meta["columns"]),
                float(meta["valid_min"]),
                float(meta["valid_max"]),
            )
            for meta in config[section_name]["concepts"].values()
        ]

    return {
        "body_temperature": latest_of_specs(
            [
                (
                    body_columns,
                    float(body["valid_min"]),
                    float(body["valid_max"]),
                )
            ]
        ),
        "pressure_permeability": latest_of_specs(pressure_specs),
        "thermal_forcing": latest_of_specs(section_specs("thermal_forcing")),
        "top_distribution": latest_of_specs(section_specs("top_distribution")),
        "burden_descent": latest_of_specs(section_specs("burden_descent")),
    }


def _group_coverage(
    frame: pd.DataFrame,
    bounds: _WindowBounds,
    config: Mapping[str, Any],
    body_current_layers: Mapping[str, float],
    pressure_concepts_available: int,
    evaluation_time: pd.Timestamp,
) -> Dict[str, float]:
    min_samples = int(config["time"]["min_samples_per_sensor_per_window"])
    body = config["body_temperature"]
    body_coverage = len(body_current_layers) / max(len(body["layers"]), 1)

    # All static elevations together form one vertical-gradient concept.
    pressure_expected = len(config["pressure"]["concepts"]) + 1
    pressure_coverage = pressure_concepts_available / max(pressure_expected, 1)

    def concept_coverage(section_name: str) -> float:
        section = config[section_name]
        concepts = section.get("concepts", {})
        found = 0
        for meta in concepts.values():
            valid_min = float(meta["valid_min"])
            valid_max = float(meta["valid_max"])
            value, _ = _first_available_stat(
                frame,
                list(meta["columns"]),
                bounds.current_start,
                bounds.current_end,
                valid_min,
                valid_max,
                min_samples,
            )
            if value is not None:
                found += 1
        return found / max(len(concepts), 1)

    thermal_found = 0
    thermal_concepts = config["thermal_forcing"]["concepts"]
    thermal_max_age_minutes = float(
        config["time"]["max_thermal_age_minutes"]
    )
    for meta in thermal_concepts.values():
        value, _ = _first_available_stat(
            frame,
            list(meta["columns"]),
            bounds.current_start,
            bounds.current_end,
            float(meta["valid_min"]),
            float(meta["valid_max"]),
            min_samples,
            freshness_time=evaluation_time,
            max_age_minutes=thermal_max_age_minutes,
        )
        if value is not None:
            thermal_found += 1

    return {
        "body_temperature": round(_clamp(body_coverage, 0.0, 1.0), 6),
        "pressure_permeability": round(
            _clamp(pressure_coverage, 0.0, 1.0), 6
        ),
        "thermal_forcing": round(
            _clamp(thermal_found / max(len(thermal_concepts), 1), 0.0, 1.0),
            6,
        ),
        "top_distribution": round(
            _clamp(concept_coverage("top_distribution"), 0.0, 1.0), 6
        ),
        "burden_descent": round(
            _clamp(concept_coverage("burden_descent"), 0.0, 1.0), 6
        ),
    }


def _unavailable_result(
    config: Mapping[str, Any],
    reason_codes: Sequence[str],
    sample_time: Optional[pd.Timestamp],
    coverage: Optional[Mapping[str, float]] = None,
    stale_columns: Optional[Sequence[str]] = None,
    latest_time_by_group: Optional[
        Mapping[str, Optional[pd.Timestamp]]
    ] = None,
    extra_quality: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    model = config["model"]
    coverage_by_group = dict(coverage or {})
    weights = config["coverage"]["group_weights"]
    weighted_coverage = sum(
        float(coverage_by_group.get(group, 0.0)) * float(weight)
        for group, weight in weights.items()
    )
    context_groups = ("top_distribution", "burden_descent")
    context_coverage = sum(
        float(coverage_by_group.get(group, 0.0)) for group in context_groups
    ) / len(context_groups)
    quality: Dict[str, Any] = {
        "state": "unavailable",
        "coverage_by_group": coverage_by_group,
        "context_coverage_by_group": {
            group: float(coverage_by_group.get(group, 0.0))
            for group in context_groups
        },
        "latest_time_by_group": {
            group: _iso_timestamp(timestamp)
            for group, timestamp in (latest_time_by_group or {}).items()
        },
        "stale_columns": list(stale_columns or []),
        "warnings": [
            "软熔带为未标定估计，不是现场实测值",
            "输入不足或陈旧，未生成几何体",
        ],
    }
    if extra_quality:
        quality.update(dict(extra_quality))
    return {
        "status": "unavailable",
        "evidence": model["evidence"],
        "model_version": model["version"],
        "calibration_status": model["calibration_status"],
        "root_definition": model["root_definition"],
        "azimuth_reference": model["azimuth_reference"],
        "absolute_azimuth_status": model["absolute_azimuth_status"],
        "control_use": model["control_use"],
        "confidence": 0.0,
        "input_coverage": round(_clamp(weighted_coverage, 0.0, 1.0), 6),
        "context_coverage": round(_clamp(context_coverage, 0.0, 1.0), 6),
        "sample_time": _iso_timestamp(sample_time),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "quality": quality,
    }


class CohesiveZoneEstimator:
    """Reusable estimator configured by ``cohesive_zone_estimator.yaml``.

    Corresponding requirement: REQ-BF3D-C2-001.

    ``estimate`` returns only native Python scalar/list/dict values so the
    result can be serialised with :func:`json.dumps` without a custom encoder.
    """

    def __init__(self, config_path: Optional[str | Path] = None):
        self.config = load_cohesive_zone_config(config_path)

    def estimate(
        self,
        data: pd.DataFrame,
        *,
        evaluation_time: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Estimate cohesive-zone root geometry at ``evaluation_time``.

        Args:
            data: One-minute wide process data.  See the module input contract.
            evaluation_time: Optional timestamp.  Rows later than this value
                are discarded before any feature is calculated.

        Returns:
            JSON-serialisable ``status="available"`` geometry or structured
            ``status="unavailable"`` diagnostics.

        Raises:
            TypeError: ``data`` is not a DataFrame.
            ValueError: the DataFrame has no parseable time axis.
        """
        frame = _normalise_frame(data)
        if frame.empty:
            return _unavailable_result(
                self.config, ["empty_input"], sample_time=None
            )
        evaluation = _align_evaluation_time(evaluation_time, frame.index)
        frame = frame.loc[frame.index <= evaluation].copy()
        if frame.empty:
            return _unavailable_result(
                self.config, ["no_data_at_or_before_evaluation_time"], None
            )

        bounds = _make_bounds(evaluation, self.config)
        body_config = self.config["body_temperature"]
        (
            raw_current_layers,
            raw_reference_layers,
            current_body_matrix,
            reference_body_matrix,
            stale_columns,
        ) = _body_profiles(frame, bounds, self.config, evaluation)
        (
            current_layers,
            reference_layers,
            temporal_body_support,
        ) = _comparable_body_profiles(
            current_body_matrix,
            reference_body_matrix,
            self.config,
        )
        common_body_layers = sorted(current_layers)
        body_sector_residuals, body_sector_support = _balanced_residual_profile(
            current_body_matrix,
            common_body_layers,
            list(body_config["sectors"]),
        )
        latest_times = _latest_times_by_group(
            frame, self.config, evaluation
        )
        sample_time = latest_times["body_temperature"]

        time_config = self.config["time"]
        pressure_config = self.config["pressure"]
        min_samples = int(time_config["min_samples_per_sensor_per_window"])
        pressure_max_age_minutes = float(
            time_config["max_pressure_age_minutes"]
        )
        pressure_index, pressure_concepts, pressure_drivers = _concept_delta_index(
            frame,
            pressure_config["concepts"],
            bounds,
            float(pressure_config["valid_min"]),
            float(pressure_config["valid_max"]),
            min_samples,
            freshness_time=evaluation,
            max_age_minutes=pressure_max_age_minutes,
        )
        (
            _current_static,
            _reference_static,
            static_sectors,
            static_concepts,
            static_drivers,
            static_sector_support,
        ) = _static_level_stats(
            frame, bounds, self.config, evaluation
        )
        total_pressure_concepts = pressure_concepts + static_concepts
        if static_drivers:
            static_weight = float(pressure_config["static_gradient"]["weight"])
            pressure_components: List[Tuple[float, float]] = []
            if pressure_concepts > 0:
                pressure_components.append(
                    (pressure_index, float(pressure_concepts))
                )
            pressure_components.append(
                (
                    float(static_drivers[0]["normalised_contribution"]),
                    static_weight,
                )
            )
            combined = _weighted_mean(pressure_components)
            pressure_index = float(combined or 0.0)
        pressure_drivers.extend(static_drivers)

        coverage = _group_coverage(
            frame,
            bounds,
            self.config,
            current_layers,
            total_pressure_concepts,
            evaluation,
        )
        support_quality = {
            "current_body_layers": sorted(raw_current_layers),
            "reference_body_layers": sorted(raw_reference_layers),
            "common_body_layers": common_body_layers,
            "body_temporal_support": temporal_body_support,
            "body_sector_support": body_sector_support,
            "static_pressure_sector_support": static_sector_support,
        }
        reasons: List[str] = []
        coverage_config = self.config["coverage"]
        if len(raw_current_layers) < int(
            coverage_config["min_current_body_layers"]
        ):
            reasons.append("insufficient_current_body_layers")
        if len(raw_reference_layers) < int(
            coverage_config["min_reference_body_layers"]
        ):
            reasons.append("insufficient_reference_body_layers")
        if len(common_body_layers) < int(
            coverage_config["min_common_body_layers"]
        ):
            reasons.append("insufficient_common_body_layers")
        if len(body_sector_support["shared_sectors"]) < int(
            coverage_config["min_common_eccentric_sectors"]
        ):
            reasons.append("insufficient_common_eccentric_sectors")
        if total_pressure_concepts < int(
            coverage_config["min_pressure_concepts"]
        ):
            reasons.append("insufficient_pressure_or_permeability_data")
            pressure_latest = latest_times["pressure_permeability"]
            if (
                pressure_latest is not None
                and evaluation - pressure_latest
                > pd.Timedelta(minutes=pressure_max_age_minutes)
            ):
                reasons.append("stale_pressure_or_permeability")
        if sample_time is None:
            reasons.append("missing_body_temperature")
        else:
            maximum_age = pd.Timedelta(
                minutes=float(time_config["max_body_age_minutes"])
            )
            if evaluation - sample_time > maximum_age:
                reasons.append("stale_body_temperature")
        if reasons:
            return _unavailable_result(
                self.config,
                reasons,
                sample_time,
                coverage,
                stale_columns,
                latest_times,
                support_quality,
            )

        current_centre, current_spread = _profile_centre(
            current_layers, self.config
        )
        reference_centre, _reference_spread = _profile_centre(
            reference_layers, self.config
        )
        if current_centre is None or reference_centre is None:
            return _unavailable_result(
                self.config,
                ["body_profile_not_estimable"],
                sample_time,
                coverage,
                stale_columns,
                latest_times,
                support_quality,
            )

        thermal_index, _thermal_available, thermal_drivers = _concept_delta_index(
            frame,
            self.config["thermal_forcing"]["concepts"],
            bounds,
            0.0,
            1.0,
            min_samples,
            freshness_time=evaluation,
            max_age_minutes=float(
                time_config["max_thermal_age_minutes"]
            ),
        )
        geometry = self.config["geometry"]
        corrected_centre = current_centre + thermal_index * float(
            self.config["thermal_forcing"]["center_height_gain_m"]
        )
        center_height = _clamp(
            corrected_centre,
            float(geometry["center_height_min"]),
            float(geometry["center_height_max"]),
        )

        reference_corrected_centre = reference_centre
        separation_hours = bounds.centre_separation_hours
        velocity = (
            (center_height - reference_corrected_centre) / separation_hours
            if separation_hours > 0
            else 0.0
        )
        movement_config = self.config["movement"]
        velocity = _clamp(
            velocity,
            -float(movement_config["max_abs_velocity_m_per_h"]),
            float(movement_config["max_abs_velocity_m_per_h"]),
        )
        stable_threshold = float(
            movement_config["stable_velocity_threshold_m_per_h"]
        )
        if velocity > stable_threshold:
            direction = "up"
        elif velocity < -stable_threshold:
            direction = "down"
        else:
            direction = "stable"

        spread_delta = (current_spread or 0.0) - float(
            geometry["thermal_spread_reference_m"]
        )
        thickness = (
            float(geometry["base_thickness"])
            + pressure_index * float(geometry["thickness_pressure_gain_m"])
            + spread_delta * float(geometry["thickness_thermal_spread_gain"])
        )
        thickness = _clamp(
            thickness,
            float(geometry["thickness_min"]),
            float(geometry["thickness_max"]),
        )
        amplitude = _clamp(
            float(geometry["base_amplitude"])
            + pressure_index * float(geometry["amplitude_pressure_gain_m"]),
            float(geometry["amplitude_min"]),
            float(geometry["amplitude_max"]),
        )

        eccentric_config = self.config["eccentricity"]
        temp_x, temp_y = _harmonic_vector(
            body_sector_residuals,
            body_config["sectors"],
            float(eccentric_config["temperature_normalisation_degC"]),
        )
        static_x, static_y = _harmonic_vector(
            static_sectors,
            pressure_config["static_sector_angles_deg"],
            float(eccentric_config["pressure_normalisation_kPa"]),
        )
        vector_x = (
            temp_x * float(eccentric_config["temperature_vector_weight"])
            + static_x * float(eccentric_config["static_pressure_vector_weight"])
        )
        vector_y = (
            temp_y * float(eccentric_config["temperature_vector_weight"])
            + static_y * float(eccentric_config["static_pressure_vector_weight"])
        )
        vector_magnitude = _clamp(math.hypot(vector_x, vector_y), 0.0, 1.0)
        eccentricity = vector_magnitude * float(
            geometry["max_eccentricity_m"]
        )
        eccentric_angle = (
            math.atan2(vector_y, vector_x) % (2.0 * math.pi)
            if vector_magnitude > 0
            else 0.0
        )
        if math.isclose(
            eccentric_angle,
            2.0 * math.pi,
            rel_tol=0.0,
            abs_tol=float.fromhex("0x1.0p-40"),
        ):
            eccentric_angle = 0.0
        shape = (
            "eccentric"
            if eccentricity >= float(geometry["eccentric_shape_threshold_m"])
            else str(geometry["default_shape"])
        )
        forecast_horizon_minutes = float(
            movement_config["forecast_horizon_minutes"]
        )
        forecast_height = _clamp(
            center_height + velocity * forecast_horizon_minutes / 60.0,
            float(geometry["center_height_min"]),
            float(geometry["center_height_max"]),
        )

        sector_roots: List[Dict[str, Any]] = []
        for sector, angle_deg in body_config["sectors"].items():
            angle = math.radians(float(angle_deg))
            root_height = center_height + eccentricity * math.cos(
                angle - eccentric_angle
            )
            sector_roots.append(
                {
                    "sector": sector,
                    "angle_deg": float(angle_deg),
                    "centerHeight": round(root_height, 6),
                    "lowerHeight": round(root_height - thickness / 2.0, 6),
                    "upperHeight": round(root_height + thickness / 2.0, 6),
                }
            )

        weights = self.config["coverage"]["group_weights"]
        input_coverage = sum(
            float(coverage.get(group, 0.0)) * float(weight)
            for group, weight in weights.items()
        )
        context_groups = ("top_distribution", "burden_descent")
        context_coverage = sum(
            float(coverage.get(group, 0.0)) for group in context_groups
        ) / len(context_groups)
        sector_support_factor = float(
            body_sector_support["balanced_coverage"]
        )
        static_support_factor = 1.0
        if static_sector_support["shared_sectors"]:
            static_support_factor = float(
                static_sector_support["balanced_coverage"]
            )
        confidence_cap = float(self.config["model"]["confidence_cap"])
        confidence = min(
            confidence_cap,
            confidence_cap
            * _clamp(input_coverage, 0.0, 1.0)
            * _clamp(coverage["body_temperature"], 0.0, 1.0)
            * _clamp(sector_support_factor, 0.0, 1.0)
            * _clamp(static_support_factor, 0.0, 1.0),
        )
        uncertainty_config = self.config["uncertainty"]
        confidence_fraction = (
            confidence / confidence_cap if confidence_cap > 0 else 0.0
        )
        uncertainty = float(uncertainty_config["max_m"]) - confidence_fraction * (
            float(uncertainty_config["max_m"])
            - float(uncertainty_config["min_m"])
        )
        if coverage["pressure_permeability"] <= 0:
            uncertainty += float(
                uncertainty_config["missing_pressure_penalty_m"]
            )
        uncertainty = _clamp(
            uncertainty,
            float(uncertainty_config["min_m"]),
            float(uncertainty_config["max_m"]),
        )

        model = self.config["model"]
        drivers = pressure_drivers + thermal_drivers
        return {
            "status": "available",
            "centerHeight": round(center_height, 6),
            "thickness": round(thickness, 6),
            "innerRadius": float(geometry["inner_radius"]),
            "outerRadius": float(geometry["outer_radius"]),
            "eccentricity": round(eccentricity, 6),
            "eccentricAngle": round(eccentric_angle, 6),
            "amplitude": round(amplitude, 6),
            "uncertainty": round(uncertainty, 6),
            "shape": shape,
            "evidence": model["evidence"],
            "model_version": model["version"],
            "calibration_status": model["calibration_status"],
            "root_definition": model["root_definition"],
            "azimuth_reference": model["azimuth_reference"],
            "absolute_azimuth_status": model["absolute_azimuth_status"],
            "control_use": model["control_use"],
            "movement": {
                "direction": direction,
                "velocity_m_per_h": round(velocity, 6),
                "forecast_horizon_minutes": int(forecast_horizon_minutes),
                "forecast_height_m": round(forecast_height, 6),
                "forecast_assumption": movement_config[
                    "forecast_assumption"
                ],
            },
            "sector_roots": sector_roots,
            "confidence": round(confidence, 6),
            "input_coverage": round(_clamp(input_coverage, 0.0, 1.0), 6),
            "context_coverage": round(
                _clamp(context_coverage, 0.0, 1.0), 6
            ),
            "quality": {
                "state": "estimated_uncalibrated",
                "coverage_by_group": coverage,
                "context_coverage_by_group": {
                    group: float(coverage.get(group, 0.0))
                    for group in context_groups
                },
                "latest_time_by_group": {
                    group: _iso_timestamp(timestamp)
                    for group, timestamp in latest_times.items()
                },
                "current_body_layers": sorted(raw_current_layers),
                "reference_body_layers": sorted(raw_reference_layers),
                "common_body_layers": common_body_layers,
                "stale_columns": stale_columns,
                "body_temporal_support": temporal_body_support,
                "body_sector_support": body_sector_support,
                "static_pressure_sector_support": static_sector_support,
                "support_confidence_factors": {
                    "body_sector": round(sector_support_factor, 6),
                    "static_pressure_sector": round(
                        static_support_factor, 6
                    ),
                },
                "body_profile_degC": {
                    "current": {
                        layer: round(value, 6)
                        for layer, value in current_layers.items()
                    },
                    "reference": {
                        layer: round(value, 6)
                        for layer, value in reference_layers.items()
                    },
                },
                "latent_indices": {
                    "body_center_current_m": round(current_centre, 6),
                    "body_center_reference_m": round(reference_centre, 6),
                    "thermal_forcing_index": round(thermal_index, 6),
                    "thermal_center_correction_m": round(
                        center_height - current_centre, 6
                    ),
                    "pressure_resistance_index": round(
                        pressure_index, 6
                    ),
                    "body_profile_spread_m": round(
                        current_spread or 0.0, 6
                    ),
                },
                "drivers": drivers,
                "warnings": [
                    "软熔带为未标定估计，不是现场实测值",
                    "仅供可视化和工艺研判，不得直接驱动生产控制",
                ],
            },
            "sample_time": _iso_timestamp(sample_time),
        }


def estimate_cohesive_zone(
    data: pd.DataFrame,
    *,
    evaluation_time: Optional[Any] = None,
    config_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Stable functional API for REQ-BF3D-C2-001.

    See :class:`CohesiveZoneEstimator` and the module docstring for the full
    input/output contract.  Data-quality failures return ``status=unavailable``;
    malformed input types or time axes raise ``TypeError``/``ValueError``.
    """
    return CohesiveZoneEstimator(config_path).estimate(
        data, evaluation_time=evaluation_time
    )


__all__ = [
    "CohesiveZoneEstimator",
    "estimate_cohesive_zone",
    "load_cohesive_zone_config",
]
