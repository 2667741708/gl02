"""V10 lag-band and spatial-field semantic neurons.

The inputs are cumulative statistics already restricted to measurements
strictly before the MES tapping cutoff.  This module never reads labels.

Requirement:
    REQ-SI-LAG-FIELD-MODES-V10-20260727
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .v6_features import (
    _numeric,
    _safe_ratio,
    _spatial_values,
    _temporal_column,
    temporal_inventory,
)


def _band_mean(
    temporal: pd.DataFrame,
    variable: str,
    start_minute: int,
    end_minute: int,
) -> tuple[pd.Series, pd.Series] | None:
    """Recover a non-overlapping band mean from nested cumulative windows."""

    end_mean = _numeric(
        temporal, _temporal_column(variable, end_minute, "mean")
    )
    end_count = _numeric(
        temporal, _temporal_column(variable, end_minute, "count")
    )
    if end_mean is None or end_count is None:
        return None
    if start_minute == 0:
        band_count = end_count
        band_sum = end_mean * end_count
    else:
        start_mean = _numeric(
            temporal, _temporal_column(variable, start_minute, "mean")
        )
        start_count = _numeric(
            temporal, _temporal_column(variable, start_minute, "count")
        )
        if start_mean is None or start_count is None:
            return None
        band_count = end_count - start_count
        band_sum = end_mean * end_count - start_mean * start_count
    valid_count = band_count.where(band_count > 0)
    return band_sum / valid_count, valid_count


def derive_lag_band_neurons(temporal: pd.DataFrame) -> pd.DataFrame:
    """Create explicit 0–30 ... 240–480 minute response bands."""

    variables, windows, _ = temporal_inventory(temporal.columns)
    ordered_windows = tuple(sorted(windows))
    band_edges = (0, *ordered_windows)
    output: dict[str, pd.Series] = {}
    for variable in variables:
        band_means: list[pd.Series] = []
        band_centers: list[float] = []
        band_names: list[str] = []
        for start, end in zip(band_edges[:-1], band_edges[1:]):
            recovered = _band_mean(temporal, variable, start, end)
            if recovered is None:
                continue
            mean, count = recovered
            prefix = f"lagband__{variable}__m{start}_{end}"
            output[f"{prefix}__mean"] = mean
            output[f"{prefix}__coverage_ratio"] = (
                count / float(end - start)
            ).clip(lower=0.0, upper=1.0)
            band_means.append(mean)
            band_centers.append((start + end) / 2.0)
            band_names.append(prefix)

        if len(band_means) < 3:
            continue
        recent = band_means[0]
        for prefix, older in zip(band_names[1:], band_means[1:]):
            output[
                f"lagprofile__{variable}__recent_minus_"
                f"{prefix.rsplit('__', 1)[-1]}__mean"
            ] = recent - older
        for index in range(len(band_means) - 2):
            current_change = band_means[index] - band_means[index + 1]
            prior_change = band_means[index + 1] - band_means[index + 2]
            output[
                f"lagprofile__{variable}__bands_{index}_{index + 2}"
                "__curvature"
            ] = current_change - prior_change

        profile = pd.concat(band_means, axis=1)
        profile.columns = band_names
        # x increases toward the cutoff, so a positive slope means rising
        # toward the present.
        x = -np.asarray(band_centers, dtype=float)
        centered = x - x.mean()
        denominator = float(np.sum(centered**2))
        complete = profile.notna().all(axis=1)
        slope = profile.mul(centered, axis=1).sum(axis=1) / denominator
        output[f"lagprofile__{variable}__mean_slope_toward_cutoff"] = (
            slope.where(complete)
        )
        output[f"lagprofile__{variable}__band_mean_std"] = profile.std(
            axis=1
        )
        output[f"lagprofile__{variable}__band_mean_range"] = (
            profile.max(axis=1) - profile.min(axis=1)
        )
    return pd.DataFrame(output, index=temporal.index).replace(
        [np.inf, -np.inf], np.nan
    )


def _circular_modes(
    values: pd.DataFrame,
    *,
    prefix: str,
    harmonics: Sequence[int] = (1, 2),
) -> dict[str, pd.Series]:
    """Return interpretable Fourier modes for an ordered circular field."""

    if values.shape[1] < 4:
        return {}
    numeric = values.apply(pd.to_numeric, errors="coerce")
    count = numeric.notna().sum(axis=1)
    required = max(3, int(np.ceil(values.shape[1] * 0.75)))
    valid = count >= required
    field_mean = numeric.mean(axis=1)
    centered = numeric.sub(field_mean, axis=0)
    output: dict[str, pd.Series] = {
        f"{prefix}__mean": field_mean.where(valid),
        f"{prefix}__std": numeric.std(axis=1).where(valid),
        f"{prefix}__range": (
            numeric.max(axis=1) - numeric.min(axis=1)
        ).where(valid),
    }
    angles = 2.0 * np.pi * np.arange(values.shape[1]) / values.shape[1]
    for harmonic in harmonics:
        cosine = np.cos(harmonic * angles)
        sine = np.sin(harmonic * angles)
        real = centered.mul(cosine, axis=1).sum(axis=1) * 2.0 / count
        imaginary = (
            centered.mul(sine, axis=1).sum(axis=1) * 2.0 / count
        )
        amplitude = np.sqrt(real**2 + imaginary**2)
        mode = f"{prefix}__harmonic{harmonic}"
        output[f"{mode}__cosine"] = real.where(valid)
        output[f"{mode}__sine"] = imaginary.where(valid)
        output[f"{mode}__amplitude"] = amplitude.where(valid)
    return output


def _mode_key(prefix: str, harmonic: int, component: str) -> str:
    return f"{prefix}__harmonic{harmonic}__{component}"


def _profile_slope(
    frame: pd.DataFrame,
    coordinates: Sequence[float],
) -> pd.Series:
    x = np.asarray(coordinates, dtype=float)
    centered = x - x.mean()
    denominator = float(np.sum(centered**2))
    complete = frame.notna().all(axis=1)
    return (
        frame.mul(centered, axis=1).sum(axis=1) / denominator
    ).where(complete)


def derive_spatial_field_modes(temporal: pd.DataFrame) -> pd.DataFrame:
    """Describe circumferential bias and vertical coherence of furnace fields."""

    _, windows, _ = temporal_inventory(temporal.columns)
    output: dict[str, pd.Series] = {}
    for window in windows:
        for statistic in ("mean", "slope_per_min"):
            for name, variables in (
                (
                    "top_temperature",
                    [f"T_top_{sector}" for sector in "ABCD"],
                ),
                (
                    "top_pressure",
                    [f"P_top_gas_{sector}" for sector in "ABCD"],
                ),
            ):
                prefix = f"fieldmode__{name}__w{window}_{statistic}"
                output.update(
                    _circular_modes(
                        _spatial_values(
                            temporal, variables, window, statistic
                        ),
                        prefix=prefix,
                    )
                )

            static_prefixes: list[str] = []
            for height in ("lower", "middle", "upper"):
                prefix = (
                    f"fieldmode__static_{height}"
                    f"__w{window}_{statistic}"
                )
                static_prefixes.append(prefix)
                output.update(
                    _circular_modes(
                        _spatial_values(
                            temporal,
                            [
                                f"P_static_{height}_{sector}"
                                for sector in "ABCDEF"
                            ],
                            window,
                            statistic,
                        ),
                        prefix=prefix,
                    )
                )
            for harmonic in (1, 2):
                amplitude_columns = [
                    output.get(_mode_key(prefix, harmonic, "amplitude"))
                    for prefix in static_prefixes
                ]
                if all(series is not None for series in amplitude_columns):
                    frame = pd.concat(amplitude_columns, axis=1)
                    output[
                        f"fieldmode__static_vertical__w{window}_{statistic}"
                        f"__harmonic{harmonic}_amplitude_slope"
                    ] = _profile_slope(frame, (0.0, 1.0, 2.0))

            body_prefixes: list[str] = []
            body_h1: list[tuple[pd.Series, pd.Series, pd.Series]] = []
            for layer in range(7, 17):
                prefix = (
                    f"fieldmode__body_L{layer}"
                    f"__w{window}_{statistic}"
                )
                body_prefixes.append(prefix)
                modes = _circular_modes(
                    _spatial_values(
                        temporal,
                        [
                            f"T_body_L{layer}_{sector}"
                            for sector in "ABCDEFGH"
                        ],
                        window,
                        statistic,
                    ),
                    prefix=prefix,
                )
                output.update(modes)
                real = modes.get(_mode_key(prefix, 1, "cosine"))
                imaginary = modes.get(_mode_key(prefix, 1, "sine"))
                amplitude = modes.get(_mode_key(prefix, 1, "amplitude"))
                if (
                    real is not None
                    and imaginary is not None
                    and amplitude is not None
                ):
                    body_h1.append((real, imaginary, amplitude))
            if len(body_h1) >= 4:
                real_frame = pd.concat(
                    [item[0] for item in body_h1], axis=1
                )
                imaginary_frame = pd.concat(
                    [item[1] for item in body_h1], axis=1
                )
                amplitude_frame = pd.concat(
                    [item[2] for item in body_h1], axis=1
                )
                vector_sum = np.sqrt(
                    real_frame.sum(axis=1) ** 2
                    + imaginary_frame.sum(axis=1) ** 2
                )
                amplitude_sum = amplitude_frame.sum(axis=1)
                vertical_prefix = (
                    f"fieldmode__body_vertical__w{window}_{statistic}"
                )
                output[f"{vertical_prefix}__harmonic1_coherence"] = (
                    _safe_ratio(vector_sum, amplitude_sum)
                )
                output[
                    f"{vertical_prefix}__harmonic1_amplitude_slope"
                ] = _profile_slope(
                    amplitude_frame,
                    tuple(range(7, 7 + len(body_h1))),
                )

    return pd.DataFrame(output, index=temporal.index).replace(
        [np.inf, -np.inf], np.nan
    )

