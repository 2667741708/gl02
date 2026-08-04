from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.expanded_neurons import (  # noqa: E402
    PRIMARY_ABSOLUTE_ERROR_TOLERANCE,
    expanded_semantic_feature_groups,
)
from si_semantic_engine.temporal_features import (  # noqa: E402
    TemporalFeatureConfig,
    derive_temporal_micro_neurons,
    temporal_feature_names,
)
from si_semantic_engine.physics_neurons import (  # noqa: E402
    derive_physics_composite_neurons,
)


class TemporalMicroNeuronTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cutoff = pd.Timestamp("2026-07-26 12:00:00")
        self.frame = pd.DataFrame(
            {
                "ts": pd.date_range(
                    "2026-07-26 11:51:00", periods=10, freq="min"
                ),
                "sensor_id": ["P_top"] * 10,
                "value": list(range(10)),
                "quality": ["Good"] * 10,
            }
        )
        self.config = TemporalFeatureConfig(windows_minutes=(10,))

    def test_positive_trend_and_complete_coverage(self) -> None:
        result = derive_temporal_micro_neurons(
            self.frame, self.cutoff, config=self.config
        )
        prefix = "ts__P_top__w10"
        self.assertAlmostEqual(result[f"{prefix}__coverage_ratio"], 1.0)
        self.assertAlmostEqual(result[f"{prefix}__slope_per_minute"], 1.0)
        self.assertAlmostEqual(result[f"{prefix}__delta"], 9.0)
        self.assertEqual(result[f"{prefix}__longest_missing_run"], 0.0)

    def test_future_value_cannot_change_features(self) -> None:
        baseline = derive_temporal_micro_neurons(
            self.frame, self.cutoff, config=self.config
        )
        future = pd.concat(
            [
                self.frame,
                pd.DataFrame(
                    [
                        {
                            "ts": self.cutoff + pd.Timedelta(minutes=1),
                            "sensor_id": "P_top",
                            "value": 999999,
                            "quality": "Good",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        actual = derive_temporal_micro_neurons(
            future, self.cutoff, config=self.config
        )
        self.assertEqual(baseline, actual)

    def test_bad_quality_is_missing_not_a_value(self) -> None:
        frame = self.frame.copy()
        frame.loc[9, "quality"] = "Bad"
        result = derive_temporal_micro_neurons(
            frame, self.cutoff, config=self.config
        )
        prefix = "ts__P_top__w10"
        self.assertEqual(result[f"{prefix}__count"], 9.0)
        self.assertAlmostEqual(result[f"{prefix}__coverage_ratio"], 0.9)
        self.assertEqual(result[f"{prefix}__latest"], 8.0)

    def test_feature_contract_has_24_statistics_per_window(self) -> None:
        names = temporal_feature_names(
            ["P_top", "T_body_L7_A"],
            TemporalFeatureConfig(windows_minutes=(30, 60)),
        )
        self.assertEqual(len(names), 2 * 2 * 24)
        self.assertEqual(len(names), len(set(names)))


class ExpandedNeuronTests(unittest.TestCase):
    def test_primary_tolerance_is_five_hundredths(self) -> None:
        self.assertEqual(PRIMARY_ABSOLUTE_ERROR_TOLERANCE, 0.05)

    def test_features_are_split_into_process_meaning(self) -> None:
        columns = [
            "feature__PCI_intensity",
            "feature__zstd_DP_total",
            "feature__T_body_circ_std_L10",
            "feature__T_body_mean_L15",
            "feature__SectorBias_A",
            "history__previous_Si_median_6",
            "history__previous_Si_slope_3",
            "score__cold",
            "diagnosis__coverage_ratio",
        ]
        groups = expanded_semantic_feature_groups(columns)
        self.assertEqual(groups["fuel_oxygen_input"], [columns[0]])
        self.assertEqual(groups["permeability_stability"], [columns[1]])
        self.assertEqual(groups["body_circumference"], [columns[2]])
        self.assertEqual(groups["body_layer_temperature"], [columns[3]])
        self.assertEqual(groups["body_sector_distribution"], [columns[4]])
        flattened = [item for values in groups.values() for item in values]
        self.assertEqual(sorted(flattened), sorted(columns))
        self.assertEqual(len(flattened), len(set(flattened)))

    def test_physics_composites_preserve_process_meaning(self) -> None:
        values = {
            "P_blast": 420.0,
            "P_top": 210.0,
            "DP_upper": 80.0,
            "DP_lower": 120.0,
            "DP_total": 200.0,
            "L_south": 1.8,
            "L_north": 2.1,
            "T_top_A": 100.0,
            "T_top_B": 110.0,
            "T_top_C": 120.0,
            "T_top_D": 130.0,
            "P_static_lower_A": 380.0,
            "P_static_middle_A": 340.0,
            "P_static_upper_A": 300.0,
            "T_body_L7_A": 450.0,
            "T_body_L16_A": 300.0,
        }
        output = derive_physics_composite_neurons(
            values, body_sectors=("A",), static_sectors=("A",)
        )
        self.assertEqual(
            output["coupling__blast_top_pressure_margin"], 210.0
        )
        self.assertAlmostEqual(output["coupling__upper_dp_share"], 0.4)
        self.assertAlmostEqual(output["coupling__lower_dp_share"], 0.6)
        self.assertAlmostEqual(output["coupling__dp_closure_error"], 0.0)
        self.assertAlmostEqual(
            output["spatial__stockline_south_minus_north"], -0.3
        )
        self.assertEqual(
            output["spatial__static_dp_lower_upper_A"], 80.0
        )
        self.assertEqual(
            output["spatial__body_vertical_gradient_L7_L16_A"], -150.0
        )

    def test_missing_components_do_not_become_zero(self) -> None:
        output = derive_physics_composite_neurons({"P_blast": 420.0})
        self.assertNotIn(
            "coupling__blast_top_pressure_margin",
            output,
        )


if __name__ == "__main__":
    unittest.main()
