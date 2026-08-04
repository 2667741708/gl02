from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.v10_features import (  # noqa: E402
    derive_lag_band_neurons,
    derive_spatial_field_modes,
)


def _window_row(variable: str, values: list[float]) -> dict[str, float]:
    row: dict[str, float] = {}
    windows = (30, 60, 120, 240, 480)
    cumulative: list[float] = []
    previous = 0
    for window, value in zip(windows, values):
        cumulative.extend([value] * (window - previous))
        prefix = f"temporal__{variable}__w{window}"
        row[f"{prefix}_count"] = float(window)
        row[f"{prefix}_mean"] = float(np.mean(cumulative))
        row[f"{prefix}_std"] = float(np.std(cumulative))
        row[f"{prefix}_min"] = float(np.min(cumulative))
        row[f"{prefix}_max"] = float(np.max(cumulative))
        row[f"{prefix}_slope_per_min"] = 0.0
        row[f"{prefix}_coverage_ratio"] = 1.0
        row[f"{prefix}_range"] = float(np.ptp(cumulative))
        row[f"{prefix}_cv"] = 0.0
        previous = window
    return row


class V10FeatureTests(unittest.TestCase):
    def test_non_overlapping_lag_bands_are_recovered(self) -> None:
        frame = pd.DataFrame(
            [_window_row("PI", [10.0, 20.0, 30.0, 40.0, 50.0])]
        )
        derived = derive_lag_band_neurons(frame)
        self.assertAlmostEqual(
            derived.loc[0, "lagband__PI__m0_30__mean"], 10.0
        )
        self.assertAlmostEqual(
            derived.loc[0, "lagband__PI__m30_60__mean"], 20.0
        )
        self.assertAlmostEqual(
            derived.loc[0, "lagband__PI__m240_480__mean"], 50.0
        )
        self.assertLess(
            derived.loc[
                0, "lagprofile__PI__mean_slope_toward_cutoff"
            ],
            0.0,
        )

    def test_uniform_circular_field_has_zero_harmonic(self) -> None:
        row: dict[str, float] = {}
        for sector in "ABCDEF":
            row.update(
                _window_row(f"P_static_lower_{sector}", [100.0] * 5)
            )
        derived = derive_spatial_field_modes(pd.DataFrame([row]))
        self.assertAlmostEqual(
            derived.loc[
                0,
                "fieldmode__static_lower__w30_mean"
                "__harmonic1__amplitude",
            ],
            0.0,
            places=9,
        )

    def test_sparse_circular_field_is_missing_not_zero(self) -> None:
        row: dict[str, float] = {}
        for index, sector in enumerate("ABCDEF"):
            value = 100.0 if index < 3 else float("nan")
            row.update(
                _window_row(f"P_static_lower_{sector}", [value] * 5)
            )
        derived = derive_spatial_field_modes(pd.DataFrame([row]))
        self.assertTrue(
            np.isnan(
                derived.loc[
                    0,
                    "fieldmode__static_lower__w30_mean"
                    "__harmonic1__amplitude",
                ]
            )
        )

    def test_first_harmonic_recovers_directional_amplitude(self) -> None:
        row: dict[str, float] = {}
        angles = 2.0 * np.pi * np.arange(6) / 6.0
        for sector, angle in zip("ABCDEF", angles):
            value = 100.0 + 12.0 * np.cos(angle)
            row.update(
                _window_row(f"P_static_lower_{sector}", [value] * 5)
            )
        derived = derive_spatial_field_modes(pd.DataFrame([row]))
        self.assertAlmostEqual(
            derived.loc[
                0,
                "fieldmode__static_lower__w30_mean"
                "__harmonic1__amplitude",
            ],
            12.0,
            places=6,
        )
        self.assertAlmostEqual(
            derived.loc[
                0,
                "fieldmode__static_lower__w30_mean"
                "__harmonic1__sine",
            ],
            0.0,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
