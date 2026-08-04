from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.train_v14 import (  # noqa: E402
    _semantic_feature_group,
    _variable_group,
)


class SemanticLatentGroupTests(unittest.TestCase):
    def test_required_process_variables_have_expected_groups(self) -> None:
        self.assertEqual(_variable_group("TFT"), "thermal_input")
        self.assertEqual(
            _variable_group("GasUtil"), "gas_utilization"
        )
        self.assertEqual(_variable_group("DP_total"), "permeability")
        self.assertEqual(
            _variable_group("P_static_upper_F"),
            "static_pressure_field",
        )
        self.assertEqual(
            _variable_group("T_body_L16_H"),
            "body_thermal_field",
        )
        self.assertEqual(_variable_group("L_north"), "burden_motion")
        self.assertEqual(
            _variable_group("T_taphole_1"), "taphole_proxy"
        )

    def test_field_modes_keep_process_meaning(self) -> None:
        self.assertEqual(
            _semantic_feature_group(
                "fieldmode__static_upper__w120_mean__range"
            ),
            "static_pressure_field",
        )
        self.assertEqual(
            _semantic_feature_group(
                "fieldmode__body_L12__w240_mean__harmonic1__amplitude"
            ),
            "body_thermal_field",
        )
        self.assertEqual(
            _semantic_feature_group(
                "lagshock__TFT__recent_vs_m120_240__pooled_z"
            ),
            "thermal_input",
        )

    def test_target_columns_are_never_grouped(self) -> None:
        self.assertIsNone(
            _semantic_feature_group("target__Si_representative")
        )


if __name__ == "__main__":
    unittest.main()
