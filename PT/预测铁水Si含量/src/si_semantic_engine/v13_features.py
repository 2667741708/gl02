"""Non-overlapping lag-band volatility and shock semantic neurons.

The temporal source contains cumulative count/mean/sample-standard-deviation
statistics for nested windows.  Their first and second moments can therefore
be subtracted to recover the variance of disjoint response bands without
reading raw observations or labels.

Requirement:
    REQ-SI-LAG-MOMENT-NEURONS-V13-20260727
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .v6_features import _numeric, _temporal_column, temporal_inventory


def _cumulative_moments(
    temporal: pd.DataFrame,
    variable: str,
    window: int,
) -> tuple[pd.Series, pd.Series, pd.Series] | None:
    count = _numeric(
        temporal, _temporal_column(variable, window, "count")
    )
    mean = _numeric(
        temporal, _temporal_column(variable, window, "mean")
    )
    std = _numeric(
        temporal, _temporal_column(variable, window, "std")
    )
    if count is None or mean is None or std is None:
        return None
    safe_std = std.where(count > 1, 0.0)
    total = mean * count
    total_squares = (
        safe_std.pow(2) * (count - 1).clip(lower=0.0)
        + count * mean.pow(2)
    )
    return count, total, total_squares


def _band_moments(
    temporal: pd.DataFrame,
    variable: str,
    start: int,
    end: int,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series] | None:
    end_moments = _cumulative_moments(temporal, variable, end)
    if end_moments is None:
        return None
    end_count, end_total, end_squares = end_moments
    if start == 0:
        count, total, squares = end_count, end_total, end_squares
    else:
        start_moments = _cumulative_moments(
            temporal, variable, start
        )
        if start_moments is None:
            return None
        start_count, start_total, start_squares = start_moments
        count = end_count - start_count
        total = end_total - start_total
        squares = end_squares - start_squares
    valid_count = count.where(count > 0)
    mean = total / valid_count
    population_variance = (
        squares / valid_count - mean.pow(2)
    ).clip(lower=0.0)
    sample_variance = (
        (squares - total.pow(2) / valid_count)
        / (valid_count - 1.0)
    ).clip(lower=0.0)
    std = np.sqrt(sample_variance).where(valid_count > 1)
    rms = np.sqrt((squares / valid_count).clip(lower=0.0))
    return mean, std, rms, valid_count


def derive_lag_moment_neurons(temporal: pd.DataFrame) -> pd.DataFrame:
    """Recover volatility, energy and standardized shocks by disjoint band."""

    variables, windows, _ = temporal_inventory(temporal.columns)
    edges = (0, *tuple(sorted(windows)))
    output: dict[str, pd.Series] = {}
    for variable in variables:
        means: list[pd.Series] = []
        standard_deviations: list[pd.Series] = []
        centers: list[float] = []
        names: list[str] = []
        for start, end in zip(edges[:-1], edges[1:]):
            moments = _band_moments(temporal, variable, start, end)
            if moments is None:
                continue
            mean, std, rms, count = moments
            prefix = f"lagmoment__{variable}__m{start}_{end}"
            output[f"{prefix}__std"] = std
            output[f"{prefix}__rms"] = rms
            output[f"{prefix}__cv_abs"] = (
                std / mean.abs().where(mean.abs() > 1e-12)
            )
            output[f"{prefix}__effective_count"] = count
            means.append(mean)
            standard_deviations.append(std)
            centers.append((start + end) / 2.0)
            names.append(f"m{start}_{end}")

        if len(means) < 3:
            continue
        recent_mean = means[0]
        recent_std = standard_deviations[0]
        for name, older_mean, older_std in zip(
            names[1:], means[1:], standard_deviations[1:]
        ):
            pooled_scale = np.sqrt(
                (recent_std.pow(2) + older_std.pow(2)) / 2.0
            )
            output[
                f"lagshock__{variable}__recent_vs_{name}__pooled_z"
            ] = (
                (recent_mean - older_mean)
                / pooled_scale.where(pooled_scale > 1e-12)
            )
            output[
                f"lagshock__{variable}__recent_vs_{name}__std_ratio"
            ] = (
                recent_std
                / older_std.abs().where(older_std.abs() > 1e-12)
            )

        profile = pd.concat(standard_deviations, axis=1)
        x = -np.asarray(centers, dtype=float)
        centered = x - x.mean()
        denominator = float(np.sum(centered**2))
        complete = profile.notna().all(axis=1)
        output[
            f"lagmoment__{variable}__std_slope_toward_cutoff"
        ] = (
            profile.mul(centered, axis=1).sum(axis=1) / denominator
        ).where(complete)
        output[
            f"lagmoment__{variable}__std_profile_range"
        ] = profile.max(axis=1) - profile.min(axis=1)
        output[
            f"lagmoment__{variable}__recent_std_over_profile_mean"
        ] = (
            recent_std
            / profile.mean(axis=1).abs().where(
                profile.mean(axis=1).abs() > 1e-12
            )
        )
    return pd.DataFrame(output, index=temporal.index).replace(
        [np.inf, -np.inf], np.nan
    )
