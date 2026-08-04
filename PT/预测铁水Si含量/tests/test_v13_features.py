from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.v13_features import (  # noqa: E402
    derive_lag_moment_neurons,
)


class LagMomentNeuronTests(unittest.TestCase):
    def test_recovers_disjoint_band_standard_deviation(self) -> None:
        recent = np.asarray([1.0, 2.0, 3.0])
        older = np.asarray([10.0, 12.0, 14.0])
        cumulative = np.concatenate([recent, older])
        temporal = pd.DataFrame(
            {
                "temporal__X__w3_count": [len(recent)],
                "temporal__X__w3_mean": [recent.mean()],
                "temporal__X__w3_std": [recent.std(ddof=1)],
                "temporal__X__w6_count": [len(cumulative)],
                "temporal__X__w6_mean": [cumulative.mean()],
                "temporal__X__w6_std": [
                    cumulative.std(ddof=1)
                ],
                "temporal__X__w9_count": [len(cumulative) + 3],
                "temporal__X__w9_mean": [
                    np.concatenate([cumulative, [20.0, 21.0, 22.0]]).mean()
                ],
                "temporal__X__w9_std": [
                    np.concatenate(
                        [cumulative, [20.0, 21.0, 22.0]]
                    ).std(ddof=1)
                ],
            }
        )
        result = derive_lag_moment_neurons(temporal)
        self.assertAlmostEqual(
            result.loc[0, "lagmoment__X__m3_6__std"],
            older.std(ddof=1),
        )
        self.assertAlmostEqual(
            result.loc[0, "lagmoment__X__m0_3__rms"],
            np.sqrt(np.mean(recent**2)),
        )

    def test_never_reads_target_columns(self) -> None:
        temporal = pd.DataFrame(
            {
                "temporal__X__w1_count": [1],
                "temporal__X__w1_mean": [2.0],
                "temporal__X__w1_std": [np.nan],
                "temporal__X__w2_count": [2],
                "temporal__X__w2_mean": [2.5],
                "temporal__X__w2_std": [np.sqrt(0.5)],
                "temporal__X__w3_count": [3],
                "temporal__X__w3_mean": [3.0],
                "temporal__X__w3_std": [1.0],
                "target__Si_representative": [9.99],
            }
        )
        result = derive_lag_moment_neurons(temporal)
        self.assertFalse(
            any(column.startswith("target__") for column in result)
        )


if __name__ == "__main__":
    unittest.main()
