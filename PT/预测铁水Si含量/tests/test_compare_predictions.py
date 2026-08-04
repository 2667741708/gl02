from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.compare_predictions import (  # noqa: E402
    compare_files,
    paired_comparison,
)


class PairedComparisonTests(unittest.TestCase):
    def test_delta_signs_favor_b_when_b_is_better(self) -> None:
        actual = np.asarray([0.20, 0.30, 0.40, 0.50])
        a = np.asarray([0.10, 0.20, 0.30, 0.40])
        b = np.asarray([0.20, 0.30, 0.39, 0.51])
        result = paired_comparison(
            actual, a, b, bootstrap_repeats=1000
        )
        self.assertLess(result["delta_b_minus_a"]["mae"], 0.0)
        self.assertGreater(
            result["delta_b_minus_a"]["hit_rate_abs_le_002"], 0.0
        )

    def test_compare_files_supports_same_prediction_column(
        self,
    ) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            rows = pd.DataFrame(
                {
                    "official_meltno": ["1", "2"],
                    "prediction_cutoff_ts": [
                        "2026-07-01T00:00:00",
                        "2026-07-01T01:00:00",
                    ],
                    "target__Si_representative": [0.20, 0.30],
                    "prediction__Si_representative": [0.21, 0.29],
                }
            )
            a_path = root / "a.csv"
            b_path = root / "b.csv"
            rows.to_csv(a_path, index=False)
            rows.to_csv(b_path, index=False)
            result = compare_files(
                candidate_a_path=a_path,
                candidate_a_column="prediction__Si_representative",
                candidate_b_path=b_path,
                candidate_b_column="prediction__Si_representative",
                target_column="target__Si_representative",
            )
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["delta_b_minus_a"]["mae"], 0.0)


if __name__ == "__main__":
    unittest.main()
