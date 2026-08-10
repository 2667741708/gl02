from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from run_22012_si_average_curve import (  # noqa: E402
    build_targets_and_samples,
    predict_mean_v9,
    regression_metrics,
    render_curve,
)


class ConstantPredictor:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> list[float]:
        return [self.value] * len(frame)


class AverageSiCurveTests(unittest.TestCase):
    def test_heat_target_uses_arithmetic_mean_and_latest_result(self) -> None:
        rows = [
            {
                "meltno": "2#TEST-001",
                "furnace_no": "2",
                "open_ts": datetime(2026, 8, 1, 8, 0),
                "si_avg": 0.25,
                "si_median": 0.24,
                "si_min": 0.20,
                "si_max": 0.30,
                "si_spread": 0.10,
                "hot_metal_sample_count": 2,
                "sample_details": [
                    {
                        "Si": 0.20,
                        "C": 4.2,
                        "result_ts": "2026-08-01 09:00:00",
                    },
                    {
                        "Si": 0.30,
                        "C": 4.3,
                        "result_ts": "2026-08-01 09:20:00",
                    },
                ],
                "aggregation_version": "test",
            }
        ]
        targets, samples, audit = build_targets_and_samples(rows)
        self.assertEqual(len(targets), 1)
        self.assertAlmostEqual(targets.iloc[0]["target__Si_mean"], 0.25)
        self.assertAlmostEqual(
            targets.iloc[0]["target__Si_representative"], 0.25
        )
        self.assertEqual(
            targets.iloc[0]["label_available_ts"],
            pd.Timestamp("2026-08-01 09:20:00"),
        )
        self.assertEqual(len(samples), 2)
        self.assertEqual(audit["target_column"], "target__Si_mean")

    def test_metrics_and_chart_are_generated(self) -> None:
        frame = pd.DataFrame(
            {
                "official_meltno": ["H1", "H2", "H3"],
                "prediction_cutoff_ts": pd.to_datetime(
                    [
                        "2026-08-01 00:00:00",
                        "2026-08-01 08:00:00",
                        "2026-08-01 16:00:00",
                    ]
                ),
                "actual__Si_mean": [0.20, 0.25, 0.22],
                "prediction__Si_mean": [0.21, 0.24, 0.23],
            }
        )
        metrics = regression_metrics(frame)
        self.assertAlmostEqual(metrics["mae"], 0.01)
        self.assertEqual(metrics["heat_to_heat_direction_agreement"], 1.0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "curve.png"
            render_curve(frame, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)

    def test_v9_residual_components_are_reconstructed_on_history_baseline(self) -> None:
        features = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "prediction_cutoff_ts": pd.to_datetime(["2026-08-01 00:00:00"]),
                "feature_a": [1.0],
                "history__previous_Si_1": [0.30],
            }
        )
        bundle = {
            "target_column": "target__Si_mean",
            "direct_features": ["feature_a"],
            "thermal_features": ["feature_a"],
            "fallback": 0.25,
            "direct_model": ConstantPredictor(0.20),
            "thermal_model": ConstantPredictor(0.01),
            "lgbm_models": {
                "lgbm_huber7": ConstantPredictor(0.02),
                "lgbm_huber15_decay90": ConstantPredictor(-0.01),
            },
            "weights": {
                "direct": 0.0,
                "thermal_xgb": 0.0,
                "lgbm_huber7": 0.7,
                "lgbm_huber15_decay90": 0.2,
                "history": 0.1,
            },
        }
        with patch("run_22012_si_average_curve.joblib.load", return_value=bundle):
            result = predict_mean_v9(features, Path("unused.joblib"))
        self.assertAlmostEqual(result.iloc[0]["component__lgbm_huber7"], 0.32)
        self.assertAlmostEqual(
            result.iloc[0]["component__lgbm_huber15_decay90"], 0.29
        )
        self.assertAlmostEqual(result.iloc[0]["prediction__Si_mean"], 0.312)


if __name__ == "__main__":
    unittest.main()
