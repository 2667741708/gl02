from __future__ import annotations

import json
import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine import (  # noqa: E402
    FeatureValidationError,
    ModelNotCalibratedError,
    SemanticSiEngine,
)
from si_semantic_engine.cli import main as cli_main  # noqa: E402


def calibrated_config() -> dict:
    return {
        "model_id": "fixture",
        "model_version": "test",
        "model_status": "calibrated_experimental",
        "intercept": 0.30,
        "residual_std": 0.05,
        "target_band": {"low": 0.20, "high": 0.40},
        "neurons": [
            {
                "id": "thermal_input",
                "display_name": "热输入",
                "feature_weights": {"z__thermal": 1.0},
                "threshold": 0.0,
                "scale": 1.0,
                "neutral_activation": 0.5,
                "output_weight": 0.20,
                "expected_direction": "positive",
            },
            {
                "id": "previous_si",
                "display_name": "前序炉Si",
                "feature_weights": {"z__previous_si": 1.0},
                "threshold": 0.0,
                "scale": 1.0,
                "neutral_activation": 0.5,
                "output_weight": 0.10,
                "expected_direction": "positive",
            },
        ],
    }


class SemanticSiEngineTests(unittest.TestCase):
    def test_design_config_refuses_prediction(self) -> None:
        path = ROOT / "configs" / "semantic_neurons.design.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        engine = SemanticSiEngine.from_mapping(config)
        with self.assertRaises(ModelNotCalibratedError):
            engine.predict({})

    def test_probabilities_sum_to_one_and_contributions_are_visible(self) -> None:
        engine = SemanticSiEngine.from_mapping(calibrated_config())
        result = engine.predict({"z__thermal": 0.5, "z__previous_si": -0.2})
        probabilities = result["distribution"]["probabilities"]
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=12)
        self.assertEqual(len(result["neurons"]), 2)
        self.assertIn("weighted_inputs", result["neurons"][0])
        self.assertIn("contribution_to_si_pct", result["neurons"][0])

    def test_positive_thermal_neuron_increases_predicted_mean(self) -> None:
        engine = SemanticSiEngine.from_mapping(calibrated_config())
        lower = engine.predict({"z__thermal": -2.0, "z__previous_si": 0.0})
        higher = engine.predict({"z__thermal": 2.0, "z__previous_si": 0.0})
        self.assertGreater(
            higher["distribution"]["mean"], lower["distribution"]["mean"]
        )

    def test_missing_feature_is_rejected(self) -> None:
        engine = SemanticSiEngine.from_mapping(calibrated_config())
        with self.assertRaises(FeatureValidationError) as context:
            engine.predict({"z__thermal": 0.0})
        self.assertIn("z__previous_si", str(context.exception))

    def test_cli_returns_structured_error_for_design_config(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = cli_main(
                [
                    "--config",
                    str(ROOT / "configs" / "semantic_neurons.design.json"),
                    "--features",
                    str(ROOT / "tests" / "fixtures" / "example_features.json"),
                ]
            )
        payload = json.loads(stderr.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["error_type"], "ModelNotCalibratedError")
        self.assertIn("不允许输出预测", payload["message"])


if __name__ == "__main__":
    unittest.main()
