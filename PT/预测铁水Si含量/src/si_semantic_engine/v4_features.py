"""Leakage-safe V4 history and physical semantic features.

V3 source files remain immutable.  This module derives additional features
in memory from the formal heat table and the versioned 133-point catalog.

Requirement:
    REQ-SI-SEMANTIC-HYBRID-V4-20260726
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .physics_neurons import derive_physics_composite_neurons


SENSOR_FEATURE_PATTERN = re.compile(
    r"^sensor__(?P<sensor_id>.+)__(?P<stat>"
    r"last|delta_60m|slope_60m_per_min|delta_120m|"
    r"slope_120m_per_min)$"
)
HISTORY_WINDOWS = (3, 6, 12, 24)
HISTORY_LAGS = (1, 2, 3, 4, 6, 12, 24)


def load_sensor_catalog(path: Path) -> dict[str, dict[str, Any]]:
    """Load an exact short-name mapping from the versioned sensor catalog."""

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    points = payload.get("points")
    if not isinstance(points, list):
        raise ValueError("传感器目录缺少points列表")
    catalog: dict[str, dict[str, Any]] = {}
    variable_names: set[str] = set()
    for point in points:
        database = point.get("database") or {}
        short_name = str(database.get("short_name") or "").strip()
        variable_name = str(database.get("variable_name") or "").strip()
        if not short_name or not variable_name:
            raise ValueError("传感器目录存在空short_name或variable_name")
        if short_name in catalog:
            raise ValueError(f"传感器目录short_name重复：{short_name}")
        if variable_name in variable_names:
            raise ValueError(f"传感器目录variable_name重复：{variable_name}")
        catalog[short_name] = point
        variable_names.add(variable_name)
    return catalog


def semantic_sensor_columns(
    columns: Sequence[str],
    catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Map raw V3 feature columns to stable process-variable feature names."""

    output: dict[str, str] = {}
    mapped_sensors: set[str] = set()
    unmapped_sensors: set[str] = set()
    for column in columns:
        match = SENSOR_FEATURE_PATTERN.match(str(column))
        if not match:
            continue
        sensor_id = match.group("sensor_id")
        point = catalog.get(sensor_id)
        if point is None:
            unmapped_sensors.add(sensor_id)
            continue
        variable_name = str(point["database"]["variable_name"])
        semantic_name = f"semantic__{variable_name}__{match.group('stat')}"
        if semantic_name in output.values():
            raise ValueError(f"语义传感器特征重复：{semantic_name}")
        output[column] = semantic_name
        mapped_sensors.add(sensor_id)
    return output, {
        "catalog_sensor_count": len(catalog),
        "mapped_sensor_count": len(mapped_sensors),
        "unmapped_sensor_count": len(unmapped_sensors),
        "unmapped_sensors": sorted(unmapped_sensors),
        "mapped_feature_count": len(output),
    }


def build_semantic_sensor_frame(
    frame: pd.DataFrame,
    catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create stable semantic aliases without dropping the raw V3 features."""

    column_map, audit = semantic_sensor_columns(frame.columns, catalog)
    semantic = frame[list(column_map)].rename(columns=column_map).copy()
    for column in semantic.columns:
        semantic[column] = pd.to_numeric(semantic[column], errors="coerce")
    return semantic, audit


def _history_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return float("nan")
    return float(
        np.polyfit(
            np.arange(len(values), dtype=float),
            np.asarray(values, dtype=float),
            1,
        )[0]
    )


def _history_ewma(values: Sequence[float], half_life: float) -> float:
    if not values:
        return float("nan")
    ages = np.arange(len(values) - 1, -1, -1, dtype=float)
    weights = np.power(0.5, ages / half_life)
    return float(np.average(np.asarray(values, dtype=float), weights=weights))


def attach_extended_si_history(
    prediction_rows: pd.DataFrame,
    all_heat_targets: pd.DataFrame,
) -> pd.DataFrame:
    """Attach published labels from strictly earlier official heats only.

    A label is visible only when its ``label_available_ts`` is no later than
    the current heat cutoff.  The current heat and later-opened heats are
    excluded even if their timestamps are malformed upstream.
    """

    required = {
        "official_meltno",
        "prediction_cutoff_ts",
        "label_available_ts",
        "target__Si_representative",
    }
    missing_predictions = sorted(
        {"official_meltno", "prediction_cutoff_ts"} - set(prediction_rows)
    )
    missing_targets = sorted(required - set(all_heat_targets))
    if missing_predictions:
        raise ValueError(
            f"预测炉次缺少字段：{', '.join(missing_predictions)}"
        )
    if missing_targets:
        raise ValueError(f"历史目标缺少字段：{', '.join(missing_targets)}")

    predictions = prediction_rows[
        ["official_meltno", "prediction_cutoff_ts"]
    ].copy()
    predictions["prediction_cutoff_ts"] = pd.to_datetime(
        predictions["prediction_cutoff_ts"], errors="raise"
    )
    targets = all_heat_targets[list(required)].copy()
    targets["prediction_cutoff_ts"] = pd.to_datetime(
        targets["prediction_cutoff_ts"], errors="coerce"
    )
    targets["label_available_ts"] = pd.to_datetime(
        targets["label_available_ts"], errors="coerce"
    )
    targets["target__Si_representative"] = pd.to_numeric(
        targets["target__Si_representative"], errors="coerce"
    )
    targets = targets.dropna(
        subset=[
            "official_meltno",
            "prediction_cutoff_ts",
            "label_available_ts",
            "target__Si_representative",
        ]
    ).sort_values(["prediction_cutoff_ts", "official_meltno"], kind="stable")
    if targets["official_meltno"].duplicated().any():
        raise ValueError("历史目标中official_meltno不唯一")

    target_records = targets.to_dict("records")
    history_rows: list[dict[str, Any]] = []
    for current in predictions.to_dict("records"):
        cutoff = current["prediction_cutoff_ts"]
        current_meltno = str(current["official_meltno"])
        available = [
            item
            for item in target_records
            if str(item["official_meltno"]) != current_meltno
            and item["prediction_cutoff_ts"] < cutoff
            and item["label_available_ts"] <= cutoff
        ]
        available.sort(
            key=lambda item: (
                item["prediction_cutoff_ts"],
                str(item["official_meltno"]),
            )
        )
        values = [
            float(item["target__Si_representative"]) for item in available
        ]
        row: dict[str, Any] = {
            "official_meltno": current_meltno,
            "history_v4__available_heat_count": len(available),
        }
        if available:
            previous = available[-1]
            row["history_v4__previous_heat_gap_hours"] = float(
                (cutoff - previous["prediction_cutoff_ts"]).total_seconds()
                / 3600.0
            )
            row["history_v4__previous_label_age_hours"] = float(
                (cutoff - previous["label_available_ts"]).total_seconds()
                / 3600.0
            )
        else:
            row["history_v4__previous_heat_gap_hours"] = np.nan
            row["history_v4__previous_label_age_hours"] = np.nan
        for lag in HISTORY_LAGS:
            row[f"history_v4__Si_lag_{lag}"] = (
                values[-lag] if len(values) >= lag else np.nan
            )
        for window in HISTORY_WINDOWS:
            recent = values[-window:]
            prefix = f"history_v4__Si_w{window}"
            if recent:
                array = np.asarray(recent, dtype=float)
                row[f"{prefix}__mean"] = float(np.mean(array))
                row[f"{prefix}__median"] = float(np.median(array))
                row[f"{prefix}__min"] = float(np.min(array))
                row[f"{prefix}__max"] = float(np.max(array))
                row[f"{prefix}__range"] = float(np.ptp(array))
                row[f"{prefix}__std"] = (
                    float(np.std(array, ddof=1))
                    if len(array) >= 2
                    else np.nan
                )
                row[f"{prefix}__slope_per_heat"] = _history_slope(recent)
            else:
                for statistic in (
                    "mean",
                    "median",
                    "min",
                    "max",
                    "range",
                    "std",
                    "slope_per_heat",
                ):
                    row[f"{prefix}__{statistic}"] = np.nan
        for half_life in (2, 4, 8):
            row[f"history_v4__Si_ewma_hl{half_life}"] = _history_ewma(
                values[-24:],
                float(half_life),
            )
        lag1 = row["history_v4__Si_lag_1"]
        median3 = row["history_v4__Si_w3__median"]
        median6 = row["history_v4__Si_w6__median"]
        row["history_v4__Si_lag1_minus_median3"] = (
            lag1 - median3
            if np.isfinite(lag1) and np.isfinite(median3)
            else np.nan
        )
        row["history_v4__Si_lag1_minus_median6"] = (
            lag1 - median6
            if np.isfinite(lag1) and np.isfinite(median6)
            else np.nan
        )
        slope3 = row["history_v4__Si_w3__slope_per_heat"]
        slope6 = row["history_v4__Si_w6__slope_per_heat"]
        row["history_v4__Si_slope_acceleration_3_minus_6"] = (
            slope3 - slope6
            if np.isfinite(slope3) and np.isfinite(slope6)
            else np.nan
        )
        history_rows.append(row)
    history = pd.DataFrame(history_rows)
    if history["official_meltno"].duplicated().any():
        raise RuntimeError("扩展历史特征出现重复official_meltno")
    return history


def _row_values(
    row: pd.Series,
    variables: Sequence[str],
    *,
    prior_minutes: int | None,
) -> dict[str, float]:
    output: dict[str, float] = {}
    for variable in variables:
        current = row.get(f"semantic__{variable}__last")
        if pd.isna(current):
            continue
        value = float(current)
        if prior_minutes is not None:
            delta = row.get(
                f"semantic__{variable}__delta_{prior_minutes}m"
            )
            if pd.isna(delta):
                continue
            value -= float(delta)
        if np.isfinite(value):
            output[variable] = value
    return output


def derive_physics_feature_frame(
    semantic: pd.DataFrame,
) -> pd.DataFrame:
    """Derive current and historical physical composites from snapshots."""

    variables = sorted(
        {
            column.split("__")[1]
            for column in semantic.columns
            if column.startswith("semantic__") and column.endswith("__last")
        }
    )
    records: list[dict[str, float]] = []
    for _, row in semantic.iterrows():
        current = derive_physics_composite_neurons(
            _row_values(row, variables, prior_minutes=None)
        )
        previous60 = derive_physics_composite_neurons(
            _row_values(row, variables, prior_minutes=60)
        )
        previous120 = derive_physics_composite_neurons(
            _row_values(row, variables, prior_minutes=120)
        )
        output: dict[str, float] = {}
        all_names = sorted(set(current) | set(previous60) | set(previous120))
        for name in all_names:
            now = current.get(name, np.nan)
            output[f"physics__{name}__last"] = now
            for minutes, prior in ((60, previous60), (120, previous120)):
                earlier = prior.get(name, np.nan)
                delta = (
                    float(now - earlier)
                    if np.isfinite(now) and np.isfinite(earlier)
                    else np.nan
                )
                output[f"physics__{name}__delta_{minutes}m"] = delta
                output[
                    f"physics__{name}__slope_{minutes}m_per_min"
                ] = (
                    delta / float(minutes) if np.isfinite(delta) else np.nan
                )
        records.append(output)
    return pd.DataFrame(records, index=semantic.index)


def derive_semantic_interactions(
    semantic: pd.DataFrame,
) -> pd.DataFrame:
    """Create a small, reviewable set of cross-process coupling neurons."""

    pairs = {
        "permeability_load": ("PI", "Q_blast"),
        "total_dp_load": ("DP_total", "Q_blast"),
        "blast_thermal_input": ("T_blast", "Q_blast"),
        "fuel_oxygen_coupling": ("PCI_rate", "O2_rate"),
        "tft_gas_utilization": ("TFT", "GasUtil"),
        "top_pressure_flow_load": ("P_top", "Q_blast"),
    }
    output: dict[str, pd.Series] = {}
    for name, (left, right) in pairs.items():
        left_values = pd.to_numeric(
            semantic.get(f"semantic__{left}__last"), errors="coerce"
        )
        right_values = pd.to_numeric(
            semantic.get(f"semantic__{right}__last"), errors="coerce"
        )
        if left_values is None or right_values is None:
            continue
        output[f"interaction__{name}__product"] = left_values * right_values
        for minutes in (60, 120):
            left_delta = pd.to_numeric(
                semantic.get(f"semantic__{left}__delta_{minutes}m"),
                errors="coerce",
            )
            right_delta = pd.to_numeric(
                semantic.get(f"semantic__{right}__delta_{minutes}m"),
                errors="coerce",
            )
            if left_delta is not None and right_delta is not None:
                output[
                    f"interaction__{name}__cochange_{minutes}m"
                ] = left_delta * right_delta
    return pd.DataFrame(output, index=semantic.index)


def build_v4_feature_blocks(
    frame: pd.DataFrame,
    all_heat_targets: pd.DataFrame,
    catalog_path: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Build independently auditable V4 feature blocks."""

    catalog = load_sensor_catalog(catalog_path)
    semantic, catalog_audit = build_semantic_sensor_frame(frame, catalog)
    history = attach_extended_si_history(frame, all_heat_targets)
    history = frame[["official_meltno"]].merge(
        history,
        on="official_meltno",
        how="left",
        validate="one_to_one",
    ).drop(columns=["official_meltno"])
    physics = derive_physics_feature_frame(semantic)
    interactions = derive_semantic_interactions(semantic)
    blocks = {
        "semantic": semantic,
        "history_v4": history,
        "physics": physics,
        "interactions": interactions,
    }
    audit = {
        "requirement_id": "REQ-SI-SEMANTIC-HYBRID-V4-20260726",
        "catalog": catalog_audit,
        "block_columns": {
            name: int(len(block.columns)) for name, block in blocks.items()
        },
        "history_visibility": (
            "strictly earlier heat and label_available_ts <= current cutoff"
        ),
        "physics_history_reconstruction": (
            "prior snapshot = current snapshot - recorded delta"
        ),
    }
    return blocks, audit
