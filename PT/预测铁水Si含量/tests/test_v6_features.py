from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.v6_features import (  # noqa: E402
    attach_published_chemistry_history,
    derive_heat_state_neurons,
    derive_multiscale_neurons,
    select_best_window_features,
)


def _row(variable: str, values: dict[int, float]) -> dict[str, float]:
    output: dict[str, float] = {}
    for window, value in values.items():
        output[f"temporal__{variable}__w{window}_mean"] = value
        output[f"temporal__{variable}__w{window}_std"] = 2.0
        output[f"temporal__{variable}__w{window}_range"] = 6.0
        output[f"temporal__{variable}__w{window}_slope_per_min"] = (
            value / 100.0
        )
    return output


class V6FeatureTests(unittest.TestCase):
    def test_multiscale_neurons_include_eight_hour_divergence(self) -> None:
        frame = pd.DataFrame(
            [
                _row(
                    "T_blast",
                    {30: 1100.0, 60: 1090.0, 120: 1080.0,
                     240: 1070.0, 480: 1060.0},
                )
            ]
        )
        output = derive_multiscale_neurons(frame)
        self.assertAlmostEqual(
            output[
                "multiscale__T_blast__w30_minus_w480"
                "__mean_difference"
            ].iloc[0],
            40.0,
        )
        self.assertIn(
            "multiscale__T_blast__slope__direction_agreement",
            output,
        )

    def test_heat_state_neurons_keep_taphole_as_named_proxy(self) -> None:
        values = {30: 1.0, 60: 1.0, 120: 1.0, 240: 1.0}
        row: dict[str, float] = {}
        for variable in (
            "T_taphole_1",
            "T_taphole_2",
            "DP_upper",
            "DP_lower",
            "DP_total",
        ):
            row.update(_row(variable, values))
        row["temporal__T_taphole_1__w30_mean"] = 420.0
        row["temporal__T_taphole_2__w30_mean"] = 400.0
        output = derive_heat_state_neurons(pd.DataFrame([row]))
        self.assertAlmostEqual(
            output[
                "heat_state__taphole_temperature_difference_proxy"
                "__w30_mean"
            ].iloc[0],
            20.0,
        )
        self.assertFalse(
            any("hot_metal_temperature" in column for column in output)
        )

    def test_best_window_selection_uses_training_correlation(self) -> None:
        target = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        train = pd.DataFrame(
            {
                "temporal__PI__w30_mean": target,
                "temporal__PI__w480_mean": [2.0, 1.0, 4.0, 3.0, 5.0],
                "temporal__PI__w30_std": [5.0, 4.0, 3.0, 2.0, 1.0],
                "temporal__PI__w480_std": [1.0, 3.0, 2.0, 5.0, 4.0],
            }
        )
        selected, audit = select_best_window_features(
            train, target, list(train.columns)
        )
        self.assertIn("temporal__PI__w30_mean", selected)
        self.assertIn("temporal__PI__w30_std", selected)
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(np.isfinite(item["spearman"]) for item in audit))

    def test_chemistry_history_excludes_current_and_unpublished_rows(
        self,
    ) -> None:
        predictions = pd.DataFrame(
            {
                "official_meltno": ["H3"],
                "prediction_cutoff_ts": ["2026-07-27 03:00:00"],
            }
        )
        rows = []
        for meltno, open_ts, result_ts, silicon in (
            ("H1", "2026-07-27 00:00:00", "2026-07-27 01:00:00", 0.20),
            ("H2", "2026-07-27 01:00:00", "2026-07-27 04:00:00", 0.90),
            ("H3", "2026-07-27 03:00:00", "2026-07-27 02:00:00", 0.80),
        ):
            rows.append(
                {
                    "official_meltno": meltno,
                    "open_ts": open_ts,
                    "result_ts": result_ts,
                    "si_pct": silicon,
                    "c_pct": 4.5,
                    "mn_pct": 0.2,
                    "p_pct": 0.1,
                    "s_pct": 0.03,
                }
            )
        history, audit = attach_published_chemistry_history(
            predictions, pd.DataFrame(rows)
        )
        self.assertAlmostEqual(
            history["chem_history__si__lag_1"].iloc[0], 0.20
        )
        self.assertEqual(
            history["chem_history__visible_heat_count"].iloc[0], 1
        )
        self.assertTrue(audit["current_heat_excluded"])


if __name__ == "__main__":
    unittest.main()
