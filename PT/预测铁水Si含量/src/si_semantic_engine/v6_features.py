"""V6 multi-scale and heat-state semantic neurons.

All neurons are deterministic functions of measurements strictly before the
MES tapping cutoff.  No target value is used in feature derivation.  Feature
ranking and any normalization remain training-fold responsibilities.

Requirement:
    REQ-SI-THERMAL-STATE-V6-20260727
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd


TEMPORAL_PATTERN = re.compile(
    r"^temporal__(?P<variable>.+)__w(?P<window>\d+)_(?P<statistic>.+)$"
)

CONTRAST_WINDOWS = (
    (30, 120),
    (30, 240),
    (30, 480),
    (60, 240),
    (60, 480),
    (120, 480),
    (240, 480),
)

THERMAL_INPUT_VARIABLES = (
    "T_blast",
    "TFT",
    "Q_blast",
    "P_blast",
    "Q_O2",
    "O2_rate",
    "PCI_set",
    "PCI_rate",
)
GAS_UTILIZATION_VARIABLES = (
    "GasUtil",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "P_top",
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
)
PERMEABILITY_VARIABLES = ("PI", "DP_upper", "DP_lower", "DP_total")
BURDEN_VARIABLES = ("L", "L_south", "L_north")
TAPHOLE_PROXY_VARIABLES = ("T_taphole_1", "T_taphole_2")
CHEMISTRY_COLUMNS = ("si_pct", "c_pct", "mn_pct", "p_pct", "s_pct")
CHEMISTRY_LAGS = (1, 2, 3, 6, 12)
CHEMISTRY_WINDOWS = (3, 6, 12)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in frame:
        return None
    return pd.to_numeric(frame[column], errors="coerce")


def _safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    minimum_denominator: float = 1e-12,
) -> pd.Series:
    valid = denominator.abs() > minimum_denominator
    return (numerator / denominator).where(valid)


def _temporal_column(variable: str, window: int, statistic: str) -> str:
    return f"temporal__{variable}__w{window}_{statistic}"


def temporal_inventory(
    columns: Sequence[str],
) -> tuple[tuple[str, ...], tuple[int, ...], dict[str, set[str]]]:
    """Return variables, windows and statistics present in a wide table."""

    variables: set[str] = set()
    windows: set[int] = set()
    statistics: dict[str, set[str]] = {}
    for column in columns:
        match = TEMPORAL_PATTERN.match(str(column))
        if not match:
            continue
        variable = match.group("variable")
        window = int(match.group("window"))
        statistic = match.group("statistic")
        variables.add(variable)
        windows.add(window)
        statistics.setdefault(variable, set()).add(statistic)
    if not variables or not windows:
        raise ValueError("未发现temporal多窗口特征")
    return tuple(sorted(variables)), tuple(sorted(windows)), statistics


def derive_multiscale_neurons(temporal: pd.DataFrame) -> pd.DataFrame:
    """Describe acceleration, persistence and short/long-window divergence."""

    variables, windows, _ = temporal_inventory(temporal.columns)
    window_set = set(windows)
    output: dict[str, pd.Series] = {}
    for variable in variables:
        for short, long in CONTRAST_WINDOWS:
            if short not in window_set or long not in window_set:
                continue
            short_mean = _numeric(
                temporal, _temporal_column(variable, short, "mean")
            )
            long_mean = _numeric(
                temporal, _temporal_column(variable, long, "mean")
            )
            long_std = _numeric(
                temporal, _temporal_column(variable, long, "std")
            )
            short_slope = _numeric(
                temporal, _temporal_column(variable, short, "slope_per_min")
            )
            long_slope = _numeric(
                temporal, _temporal_column(variable, long, "slope_per_min")
            )
            short_range = _numeric(
                temporal, _temporal_column(variable, short, "range")
            )
            long_range = _numeric(
                temporal, _temporal_column(variable, long, "range")
            )
            if short_mean is not None and long_mean is not None:
                difference = short_mean - long_mean
                prefix = (
                    f"multiscale__{variable}__w{short}_minus_w{long}"
                )
                output[f"{prefix}__mean_difference"] = difference
                output[f"{prefix}__mean_velocity_per_min"] = (
                    difference / float(long - short)
                )
                if long_std is not None:
                    output[f"{prefix}__mean_zscore"] = _safe_ratio(
                        difference, long_std
                    )
            if short_slope is not None and long_slope is not None:
                output[
                    f"multiscale__{variable}__w{short}_minus_w{long}"
                    "__slope_acceleration"
                ] = short_slope - long_slope
            if short_range is not None and long_range is not None:
                output[
                    f"multiscale__{variable}__w{short}_over_w{long}"
                    "__range_ratio"
                ] = _safe_ratio(short_range, long_range)

        slope_columns = [
            _temporal_column(variable, window, "slope_per_min")
            for window in windows
            if _temporal_column(variable, window, "slope_per_min") in temporal
        ]
        if len(slope_columns) >= 2:
            slope_frame = temporal[slope_columns].apply(
                pd.to_numeric, errors="coerce"
            )
            prefix = f"multiscale__{variable}__slope"
            output[f"{prefix}__mean"] = slope_frame.mean(axis=1)
            output[f"{prefix}__std"] = slope_frame.std(axis=1)
            output[f"{prefix}__range"] = (
                slope_frame.max(axis=1) - slope_frame.min(axis=1)
            )
            signs = np.sign(slope_frame)
            output[f"{prefix}__direction_agreement"] = (
                signs.sum(axis=1).abs() / signs.notna().sum(axis=1)
            ).where(signs.notna().sum(axis=1) > 0)
    return pd.DataFrame(output, index=temporal.index).replace(
        [np.inf, -np.inf], np.nan
    )


def _add_pair_statistic(
    output: dict[str, pd.Series],
    temporal: pd.DataFrame,
    *,
    name: str,
    left: str,
    right: str,
    window: int,
    statistic: str,
    operation: str,
) -> None:
    left_values = _numeric(
        temporal, _temporal_column(left, window, statistic)
    )
    right_values = _numeric(
        temporal, _temporal_column(right, window, statistic)
    )
    if left_values is None or right_values is None:
        return
    key = f"heat_state__{name}__w{window}_{statistic}"
    if operation == "difference":
        output[key] = left_values - right_values
    elif operation == "sum":
        output[key] = left_values + right_values
    elif operation == "product":
        output[key] = left_values * right_values
    elif operation == "ratio":
        output[key] = _safe_ratio(left_values, right_values)
    else:
        raise ValueError(f"未知语义运算：{operation}")


def _spatial_values(
    temporal: pd.DataFrame,
    variables: Sequence[str],
    window: int,
    statistic: str,
) -> pd.DataFrame:
    columns = [
        _temporal_column(variable, window, statistic)
        for variable in variables
        if _temporal_column(variable, window, statistic) in temporal
    ]
    if not columns:
        return pd.DataFrame(index=temporal.index)
    return temporal[columns].apply(pd.to_numeric, errors="coerce")


def derive_heat_state_neurons(temporal: pd.DataFrame) -> pd.DataFrame:
    """Create reviewable thermal-input, permeability and spatial neurons."""

    _, windows, _ = temporal_inventory(temporal.columns)
    output: dict[str, pd.Series] = {}
    for window in windows:
        for statistic in ("mean", "slope_per_min"):
            for name, left, right, operation in (
                (
                    "blast_sensible_power_proxy",
                    "T_blast",
                    "Q_blast",
                    "product",
                ),
                (
                    "oxygen_to_blast_ratio",
                    "Q_O2",
                    "Q_blast",
                    "ratio",
                ),
                (
                    "pci_to_oxygen_ratio",
                    "PCI_rate",
                    "Q_O2",
                    "ratio",
                ),
                (
                    "blast_pressure_per_flow",
                    "P_blast",
                    "Q_blast",
                    "ratio",
                ),
                (
                    "upper_dp_share",
                    "DP_upper",
                    "DP_total",
                    "ratio",
                ),
                (
                    "lower_dp_share",
                    "DP_lower",
                    "DP_total",
                    "ratio",
                ),
                (
                    "dp_component_consistency",
                    "DP_upper",
                    "DP_lower",
                    "sum",
                ),
                (
                    "stockline_south_minus_north",
                    "L_south",
                    "L_north",
                    "difference",
                ),
                (
                    "taphole_temperature_difference_proxy",
                    "T_taphole_1",
                    "T_taphole_2",
                    "difference",
                ),
            ):
                _add_pair_statistic(
                    output,
                    temporal,
                    name=name,
                    left=left,
                    right=right,
                    window=window,
                    statistic=statistic,
                    operation=operation,
                )
            component = output.get(
                f"heat_state__dp_component_consistency"
                f"__w{window}_{statistic}"
            )
            total = _numeric(
                temporal, _temporal_column("DP_total", window, statistic)
            )
            if component is not None and total is not None:
                output[
                    f"heat_state__dp_component_minus_total"
                    f"__w{window}_{statistic}"
                ] = component - total

        for statistic in ("mean", "std", "slope_per_min", "range"):
            top_temperature = _spatial_values(
                temporal,
                [f"T_top_{sector}" for sector in "ABCD"],
                window,
                statistic,
            )
            if len(top_temperature.columns) >= 2:
                prefix = (
                    f"heat_state__top_temperature_field"
                    f"__w{window}_{statistic}"
                )
                output[f"{prefix}__mean"] = top_temperature.mean(axis=1)
                output[f"{prefix}__std"] = top_temperature.std(axis=1)
                output[f"{prefix}__range"] = (
                    top_temperature.max(axis=1)
                    - top_temperature.min(axis=1)
                )
            top_pressure = _spatial_values(
                temporal,
                [f"P_top_gas_{sector}" for sector in "ABCD"],
                window,
                statistic,
            )
            if len(top_pressure.columns) >= 2:
                prefix = (
                    f"heat_state__top_pressure_field"
                    f"__w{window}_{statistic}"
                )
                output[f"{prefix}__mean"] = top_pressure.mean(axis=1)
                output[f"{prefix}__std"] = top_pressure.std(axis=1)
                output[f"{prefix}__range"] = (
                    top_pressure.max(axis=1) - top_pressure.min(axis=1)
                )

        for sector in "ABCDEF":
            for statistic in ("mean", "slope_per_min"):
                lower = _numeric(
                    temporal,
                    _temporal_column(
                        f"P_static_lower_{sector}", window, statistic
                    ),
                )
                middle = _numeric(
                    temporal,
                    _temporal_column(
                        f"P_static_middle_{sector}", window, statistic
                    ),
                )
                upper = _numeric(
                    temporal,
                    _temporal_column(
                        f"P_static_upper_{sector}", window, statistic
                    ),
                )
                if lower is not None and middle is not None:
                    output[
                        f"heat_state__static_lower_minus_middle_{sector}"
                        f"__w{window}_{statistic}"
                    ] = lower - middle
                if middle is not None and upper is not None:
                    output[
                        f"heat_state__static_middle_minus_upper_{sector}"
                        f"__w{window}_{statistic}"
                    ] = middle - upper
                if lower is not None and upper is not None:
                    output[
                        f"heat_state__static_lower_minus_upper_{sector}"
                        f"__w{window}_{statistic}"
                    ] = lower - upper

        for statistic in ("mean", "slope_per_min"):
            layer_means: dict[int, pd.Series] = {}
            for layer in range(7, 17):
                layer_values = _spatial_values(
                    temporal,
                    [f"T_body_L{layer}_{sector}" for sector in "ABCDEFGH"],
                    window,
                    statistic,
                )
                if len(layer_values.columns) >= 2:
                    layer_means[layer] = layer_values.mean(axis=1)
                    prefix = (
                        f"heat_state__body_L{layer}"
                        f"__w{window}_{statistic}"
                    )
                    output[f"{prefix}__circumferential_mean"] = (
                        layer_means[layer]
                    )
                    output[f"{prefix}__circumferential_std"] = (
                        layer_values.std(axis=1)
                    )
                    output[f"{prefix}__circumferential_range"] = (
                        layer_values.max(axis=1) - layer_values.min(axis=1)
                    )
            if len(layer_means) >= 4:
                profile = pd.DataFrame(layer_means)
                lower_band = profile[
                    [layer for layer in (7, 8, 9) if layer in profile]
                ].mean(axis=1)
                middle_band = profile[
                    [
                        layer
                        for layer in (10, 11, 12, 13)
                        if layer in profile
                    ]
                ].mean(axis=1)
                upper_band = profile[
                    [layer for layer in (14, 15, 16) if layer in profile]
                ].mean(axis=1)
                band_prefix = (
                    f"heat_state__body_vertical"
                    f"__w{window}_{statistic}"
                )
                output[f"{band_prefix}__lower_band"] = lower_band
                output[f"{band_prefix}__middle_band"] = middle_band
                output[f"{band_prefix}__upper_band"] = upper_band
                output[f"{band_prefix}__upper_minus_lower"] = (
                    upper_band - lower_band
                )
                layer_numbers = np.asarray(
                    list(profile.columns), dtype=float
                )
                centered = layer_numbers - layer_numbers.mean()
                denominator = float(np.sum(centered**2))
                output[f"{band_prefix}__profile_slope_per_layer"] = (
                    profile.mul(centered, axis=1).sum(axis=1)
                    / denominator
                )

    return pd.DataFrame(output, index=temporal.index).replace(
        [np.inf, -np.inf], np.nan
    )


def select_best_window_features(
    train: pd.DataFrame,
    target: pd.Series,
    temporal_columns: Sequence[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Select one train-only best lag/window per variable and statistic."""

    numeric = train[list(temporal_columns)].apply(
        pd.to_numeric, errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    target_values = pd.to_numeric(target, errors="coerce")
    records: list[dict[str, Any]] = []
    for column in temporal_columns:
        match = TEMPORAL_PATTERN.match(str(column))
        if not match:
            continue
        values = numeric[column]
        coverage = float(values.notna().mean())
        if coverage < 0.50 or values.nunique(dropna=True) <= 1:
            continue
        correlation = float(values.corr(target_values, method="spearman"))
        if not np.isfinite(correlation):
            continue
        records.append(
            {
                "feature": column,
                "variable": match.group("variable"),
                "window_minutes": int(match.group("window")),
                "statistic": match.group("statistic"),
                "spearman": correlation,
                "abs_spearman": abs(correlation),
                "train_non_null_ratio": coverage,
            }
        )
    ranking = sorted(
        records,
        key=lambda item: (
            item["variable"],
            item["statistic"],
            -item["abs_spearman"],
            item["window_minutes"],
        ),
    )
    selected: list[str] = []
    audit: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in ranking:
        key = (item["variable"], item["statistic"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(str(item["feature"]))
        audit.append(item)
    return selected, audit


def _sequence_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return float("nan")
    array = np.asarray(values, dtype=float)
    return float(
        np.polyfit(np.arange(len(array), dtype=float), array, 1)[0]
    )


def attach_published_chemistry_history(
    prediction_rows: pd.DataFrame,
    samples: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach earlier-heat chemistry that was published by each cutoff.

    The current heat is excluded by official melt number and by the strict
    earlier ``open_ts`` condition.  Partial results from an earlier heat are
    allowed only if their own ``result_ts`` was already visible.
    """

    prediction_required = {"official_meltno", "prediction_cutoff_ts"}
    sample_required = {
        "official_meltno",
        "open_ts",
        "result_ts",
        *CHEMISTRY_COLUMNS,
    }
    missing_predictions = sorted(
        prediction_required - set(prediction_rows)
    )
    missing_samples = sorted(sample_required - set(samples))
    if missing_predictions:
        raise ValueError(
            f"预测炉次缺少字段：{missing_predictions}"
        )
    if missing_samples:
        raise ValueError(f"铁水试样缺少字段：{missing_samples}")

    predictions = prediction_rows[
        ["official_meltno", "prediction_cutoff_ts"]
    ].copy()
    predictions["prediction_cutoff_ts"] = pd.to_datetime(
        predictions["prediction_cutoff_ts"], errors="raise"
    )
    source = samples[
        ["official_meltno", "open_ts", "result_ts", *CHEMISTRY_COLUMNS]
    ].copy()
    source["open_ts"] = pd.to_datetime(source["open_ts"], errors="coerce")
    source["result_ts"] = pd.to_datetime(
        source["result_ts"], errors="coerce"
    )
    for column in CHEMISTRY_COLUMNS:
        source[column] = pd.to_numeric(source[column], errors="coerce")
    source = source.dropna(
        subset=["official_meltno", "open_ts", "result_ts"]
    ).sort_values(["open_ts", "result_ts"], kind="stable")
    source["_official_meltno_text"] = source["official_meltno"].astype(str)

    records: list[dict[str, Any]] = []
    for current in predictions.to_dict("records"):
        cutoff = current["prediction_cutoff_ts"]
        meltno = str(current["official_meltno"])
        visible = source.loc[
            source["_official_meltno_text"].ne(meltno)
            & source["open_ts"].lt(cutoff)
            & source["result_ts"].le(cutoff)
        ]
        grouped = (
            visible.groupby("official_meltno", sort=False)
            .agg(
                open_ts=("open_ts", "min"),
                result_ts=("result_ts", "max"),
                **{
                    column: (column, "median")
                    for column in CHEMISTRY_COLUMNS
                },
            )
            .sort_values(["open_ts", "result_ts"], kind="stable")
        )
        row: dict[str, Any] = {
            "official_meltno": meltno,
            "chem_history__visible_heat_count": int(len(grouped)),
            "chem_history__visible_sample_count": int(len(visible)),
        }
        if not grouped.empty:
            row["chem_history__latest_result_age_hours"] = float(
                (cutoff - grouped["result_ts"].iloc[-1]).total_seconds()
                / 3600.0
            )
        else:
            row["chem_history__latest_result_age_hours"] = np.nan
        for column in CHEMISTRY_COLUMNS:
            element = column.removesuffix("_pct")
            values = grouped[column].dropna().to_numpy(float).tolist()
            for lag in CHEMISTRY_LAGS:
                row[f"chem_history__{element}__lag_{lag}"] = (
                    values[-lag] if len(values) >= lag else np.nan
                )
            for window in CHEMISTRY_WINDOWS:
                recent = values[-window:]
                prefix = f"chem_history__{element}__w{window}"
                if recent:
                    array = np.asarray(recent, dtype=float)
                    row[f"{prefix}__mean"] = float(np.mean(array))
                    row[f"{prefix}__median"] = float(np.median(array))
                    row[f"{prefix}__std"] = (
                        float(np.std(array, ddof=1))
                        if len(array) >= 2
                        else np.nan
                    )
                    row[f"{prefix}__slope_per_heat"] = _sequence_slope(
                        recent
                    )
                else:
                    for statistic in (
                        "mean",
                        "median",
                        "std",
                        "slope_per_heat",
                    ):
                        row[f"{prefix}__{statistic}"] = np.nan
            lag1 = row[f"chem_history__{element}__lag_1"]
            median3 = row[f"chem_history__{element}__w3__median"]
            row[f"chem_history__{element}__lag1_minus_median3"] = (
                lag1 - median3
                if np.isfinite(lag1) and np.isfinite(median3)
                else np.nan
            )
        records.append(row)
    history = pd.DataFrame(records)
    if history["official_meltno"].duplicated().any():
        raise RuntimeError("前炉化学成分历史出现重复official_meltno")
    ordered = predictions[["official_meltno"]].merge(
        history,
        on="official_meltno",
        how="left",
        validate="one_to_one",
    )
    feature_columns = [
        column
        for column in ordered.columns
        if column.startswith("chem_history__")
    ]
    return ordered[feature_columns], {
        "feature_count": len(feature_columns),
        "elements": [
            column.removesuffix("_pct") for column in CHEMISTRY_COLUMNS
        ],
        "visibility": (
            "strictly earlier official heat and sample result_ts <= cutoff"
        ),
        "current_heat_excluded": True,
        "source_sample_rows": int(len(source)),
    }
