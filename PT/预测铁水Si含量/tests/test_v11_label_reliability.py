from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.train_v11 import (  # noqa: E402
    label_reliability_weights,
    surrogate_target,
)
from si_semantic_engine.train_v12 import simplex_weights  # noqa: E402


class V11LabelReliabilityTests(unittest.TestCase):
    def test_surrogate_blends_mean_and_median_only_as_requested(self) -> None:
        frame = pd.DataFrame(
            {
                "target__Si_representative": [0.30, 0.40],
                "target__Si_mean": [0.34, 0.36],
            }
        )
        np.testing.assert_allclose(
            surrogate_target(frame, 0.25), [0.31, 0.39]
        )

    def test_reliable_multi_sample_heat_gets_more_weight(self) -> None:
        frame = pd.DataFrame(
            {
                "target__Si_sample_count": [4, 2],
                "target__Si_std": [0.01, 0.12],
            }
        )
        weights = label_reliability_weights(frame, "dispersion")
        self.assertAlmostEqual(float(weights.mean()), 1.0)
        self.assertGreater(weights[0], weights[1])

    def test_uniform_weights_do_not_depend_on_labels(self) -> None:
        frame = pd.DataFrame(
            {
                "target__Si_sample_count": [2, 5],
                "target__Si_std": [0.10, 0.01],
            }
        )
        np.testing.assert_allclose(
            label_reliability_weights(frame, "uniform"), [1.0, 1.0]
        )

    def test_v12_simplex_weights_are_nonnegative_and_sum_to_one(self) -> None:
        weights = simplex_weights(units=4)
        self.assertEqual(len(weights), 35)
        for item in weights:
            self.assertTrue(all(value >= 0.0 for value in item.values()))
            self.assertAlmostEqual(sum(item.values()), 1.0)


if __name__ == "__main__":
    unittest.main()
