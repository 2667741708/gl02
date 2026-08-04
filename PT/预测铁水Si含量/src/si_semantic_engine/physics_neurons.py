"""Deterministic cross-sensor physics composite neurons.

Inputs must already be aligned to the prediction cutoff. Missing components
produce missing composites instead of silently substituting zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


def _number(values: Mapping[str, Any], key: str) -> float | None:
    try:
        value = float(values[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _available(
    values: Mapping[str, Any],
    keys: Sequence[str],
) -> list[float]:
    output = []
    for key in keys:
        value = _number(values, key)
        if value is not None:
            output.append(value)
    return output


def _spread_features(
    output: dict[str, float],
    prefix: str,
    values: Sequence[float],
) -> None:
    if len(values) < 2:
        return
    array = np.asarray(values, dtype=float)
    mean = float(np.mean(array))
    output[f"{prefix}__mean"] = mean
    output[f"{prefix}__range"] = float(np.max(array) - np.min(array))
    output[f"{prefix}__std"] = float(np.std(array, ddof=1))
    output[f"{prefix}__cv"] = (
        float(np.std(array, ddof=1) / abs(mean))
        if abs(mean) > 1e-12
        else float("nan")
    )


def derive_physics_composite_neurons(
    values: Mapping[str, Any],
    *,
    body_layers: Sequence[int] = tuple(range(7, 17)),
    body_sectors: Sequence[str] = tuple("ABCDEFGH"),
    static_sectors: Sequence[str] = tuple("ABCDEF"),
) -> dict[str, float]:
    """Build interpretable pressure, burden and spatial-distribution features."""

    output: dict[str, float] = {}

    pci_set = _number(values, "PCI_set")
    pci_rate = _number(values, "PCI_rate")
    if pci_set is not None and pci_rate is not None:
        output["coupling__pci_set_actual_gap_unit_check_required"] = (
            pci_set - pci_rate
        )
        output["coupling__pci_set_actual_abs_gap_unit_check_required"] = abs(
            pci_set - pci_rate
        )

    oxygen = _number(values, "Q_O2")
    blast_flow = _number(values, "Q_blast")
    if oxygen is not None and blast_flow not in (None, 0.0):
        output["coupling__oxygen_to_blast_flow_ratio"] = oxygen / blast_flow

    blast_pressure = _number(values, "P_blast")
    top_pressure = _number(values, "P_top")
    if blast_pressure is not None and top_pressure is not None:
        output["coupling__blast_top_pressure_margin"] = (
            blast_pressure - top_pressure
        )

    upper_dp = _number(values, "DP_upper")
    lower_dp = _number(values, "DP_lower")
    total_dp = _number(values, "DP_total")
    if upper_dp is not None and lower_dp is not None:
        output["coupling__upper_lower_dp_difference"] = upper_dp - lower_dp
    if total_dp not in (None, 0.0):
        if upper_dp is not None:
            output["coupling__upper_dp_share"] = upper_dp / total_dp
        if lower_dp is not None:
            output["coupling__lower_dp_share"] = lower_dp / total_dp
        if upper_dp is not None and lower_dp is not None:
            output["coupling__dp_closure_error"] = (
                upper_dp + lower_dp - total_dp
            )

    south = _number(values, "L_south")
    north = _number(values, "L_north")
    if south is not None and north is not None:
        output["spatial__stockline_south_minus_north"] = south - north
        output["spatial__stockline_ns_abs_difference"] = abs(south - north)

    top_temperatures = _available(
        values, [f"T_top_{sector}" for sector in "ABCD"]
    )
    _spread_features(output, "spatial__top_temperature_4pt", top_temperatures)

    top_pressures = _available(
        values, [f"P_top_gas_{sector}" for sector in "ABCD"]
    )
    _spread_features(output, "spatial__top_pressure_4pt", top_pressures)

    taphole_1 = _number(values, "T_taphole_1")
    taphole_2 = _number(values, "T_taphole_2")
    if taphole_1 is not None and taphole_2 is not None:
        output["spatial__taphole_1_minus_2"] = taphole_1 - taphole_2
        output["spatial__taphole_abs_difference"] = abs(
            taphole_1 - taphole_2
        )

    for height in ("lower", "middle", "upper"):
        pressure_values = _available(
            values,
            [f"P_static_{height}_{sector}" for sector in static_sectors],
        )
        _spread_features(
            output,
            f"spatial__static_pressure_{height}",
            pressure_values,
        )
    for sector in static_sectors:
        lower = _number(values, f"P_static_lower_{sector}")
        middle = _number(values, f"P_static_middle_{sector}")
        upper = _number(values, f"P_static_upper_{sector}")
        if lower is not None and middle is not None:
            output[f"spatial__static_dp_lower_middle_{sector}"] = (
                lower - middle
            )
        if middle is not None and upper is not None:
            output[f"spatial__static_dp_middle_upper_{sector}"] = (
                middle - upper
            )
        if lower is not None and upper is not None:
            output[f"spatial__static_dp_lower_upper_{sector}"] = lower - upper

    for layer in body_layers:
        layer_values = _available(
            values,
            [f"T_body_L{layer}_{sector}" for sector in body_sectors],
        )
        _spread_features(
            output,
            f"spatial__body_temperature_L{layer}",
            layer_values,
        )
    if body_layers:
        lowest = int(min(body_layers))
        highest = int(max(body_layers))
        for sector in body_sectors:
            low_value = _number(values, f"T_body_L{lowest}_{sector}")
            high_value = _number(values, f"T_body_L{highest}_{sector}")
            if low_value is not None and high_value is not None:
                output[
                    f"spatial__body_vertical_gradient_L{lowest}_L{highest}_{sector}"
                ] = high_value - low_value
    return output
