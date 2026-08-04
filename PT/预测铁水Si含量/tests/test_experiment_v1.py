from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.experiment_data import (  # noqa: E402
    assign_chronological_splits,
    build_heat_level_dataset,
    heat_group_from_sample_no,
)


class ExperimentDataTests(unittest.TestCase):
    def test_heat_group_parsing(self) -> None:
        self.assertEqual(
            heat_group_from_sample_no("22607-318-003"), "22607-318"
        )
        self.assertIsNone(heat_group_from_sample_no("invalid"))

    def test_split_is_chronological_and_disjoint(self) -> None:
        frame = pd.DataFrame(
            {
                "temporary_heat_group": [f"h{i:03d}" for i in range(40)],
                "feature_end_ts": pd.date_range(
                    "2026-01-01", periods=40, freq="h"
                ),
            }
        )
        output = assign_chronological_splits(frame)
        self.assertEqual(output["temporary_heat_group"].nunique(), len(output))
        self.assertLess(
            output.loc[
                output["experiment_split"] == "train", "feature_end_ts"
            ].max(),
            output.loc[
                output["experiment_split"] == "validation", "feature_end_ts"
            ].min(),
        )
        self.assertLess(
            output.loc[
                output["experiment_split"] == "validation", "feature_end_ts"
            ].max(),
            output.loc[
                output["experiment_split"] == "test", "feature_end_ts"
            ].min(),
        )

    def test_previous_si_requires_result_before_feature_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            labels = pd.DataFrame(
                [
                    {
                        "si_sample_no": "22607-001-001",
                        "si_result_ts": "2026-01-01 10:00:00",
                        "hot_metal_si_pct": 0.20,
                    },
                    {
                        "si_sample_no": "22607-002-001",
                        "si_result_ts": "2026-01-01 20:00:00",
                        "hot_metal_si_pct": 0.30,
                    },
                ]
            )
            feature_rows = []
            for index in range(40):
                feature_rows.append(
                    {
                        "si_sample_no": f"22607-{index + 2:03d}-001",
                        "feature_end_ts": (
                            pd.Timestamp("2026-01-01 15:00:00")
                            + pd.Timedelta(hours=index)
                        ),
                        "feature__z60_T_blast": float(index),
                        "hot_metal_si_pct": 9.99,
                    }
                )
                if index >= 1:
                    labels.loc[len(labels)] = {
                        "si_sample_no": f"22607-{index + 2:03d}-001",
                        "si_result_ts": (
                            pd.Timestamp("2026-01-01 21:00:00")
                            + pd.Timedelta(hours=index)
                        ),
                        "hot_metal_si_pct": 0.30,
                    }
            labels_path = root / "labels.csv"
            features_path = root / "features.csv"
            labels.to_csv(labels_path, index=False)
            pd.DataFrame(feature_rows).to_csv(features_path, index=False)
            output = build_heat_level_dataset(labels_path, features_path)
            first = output.iloc[0]
            self.assertEqual(first["history__previous_Si_1"], 0.20)
            self.assertNotIn("hot_metal_si_pct", output.columns)
            self.assertEqual(
                output["temporary_heat_group"].nunique(), len(output)
            )


if __name__ == "__main__":
    unittest.main()

