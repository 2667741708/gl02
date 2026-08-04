from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.v4_features import (  # noqa: E402
    attach_extended_si_history,
    build_semantic_sensor_frame,
    derive_physics_feature_frame,
    load_sensor_catalog,
)


class V4FeatureTests(unittest.TestCase):
    def test_extended_history_excludes_unpublished_and_current_label(self) -> None:
        targets = pd.DataFrame(
            [
                {
                    "official_meltno": "H1",
                    "prediction_cutoff_ts": "2026-07-26 10:00:00",
                    "label_available_ts": "2026-07-26 11:00:00",
                    "target__Si_representative": 0.20,
                },
                {
                    "official_meltno": "H2",
                    "prediction_cutoff_ts": "2026-07-26 11:00:00",
                    "label_available_ts": "2026-07-26 13:00:00",
                    "target__Si_representative": 9.99,
                },
                {
                    "official_meltno": "H3",
                    "prediction_cutoff_ts": "2026-07-26 12:00:00",
                    "label_available_ts": "2026-07-26 14:00:00",
                    "target__Si_representative": 0.30,
                },
            ]
        )
        prediction = targets.loc[
            targets["official_meltno"] == "H3",
            ["official_meltno", "prediction_cutoff_ts"],
        ]
        result = attach_extended_si_history(prediction, targets).iloc[0]
        self.assertEqual(result["history_v4__available_heat_count"], 1)
        self.assertAlmostEqual(result["history_v4__Si_lag_1"], 0.20)
        self.assertNotEqual(result["history_v4__Si_lag_1"], 9.99)
        self.assertNotEqual(result["history_v4__Si_lag_1"], 0.30)

    def test_exact_eq_short_name_preserves_static_pressure_identity(self) -> None:
        payload = {
            "points": [
                {
                    "database": {
                        "short_name": "SIO_X",
                        "variable_name": "DP_lower",
                    }
                },
                {
                    "database": {
                        "short_name": "EQ_SIO_X",
                        "variable_name": "P_static_lower_A",
                    }
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            catalog = load_sensor_catalog(path)
        frame = pd.DataFrame(
            {
                "sensor__SIO_X__last": [10.0],
                "sensor__EQ_SIO_X__last": [20.0],
            }
        )
        semantic, audit = build_semantic_sensor_frame(frame, catalog)
        self.assertEqual(audit["mapped_sensor_count"], 2)
        self.assertEqual(semantic["semantic__DP_lower__last"].iloc[0], 10.0)
        self.assertEqual(
            semantic["semantic__P_static_lower_A__last"].iloc[0], 20.0
        )

    def test_physics_deltas_are_reconstructed_from_prior_snapshots(self) -> None:
        semantic = pd.DataFrame(
            {
                "semantic__P_blast__last": [500.0],
                "semantic__P_blast__delta_60m": [20.0],
                "semantic__P_blast__delta_120m": [40.0],
                "semantic__P_top__last": [300.0],
                "semantic__P_top__delta_60m": [10.0],
                "semantic__P_top__delta_120m": [20.0],
            }
        )
        physics = derive_physics_feature_frame(semantic)
        prefix = "physics__coupling__blast_top_pressure_margin"
        self.assertAlmostEqual(physics[f"{prefix}__last"].iloc[0], 200.0)
        self.assertAlmostEqual(
            physics[f"{prefix}__delta_60m"].iloc[0], 10.0
        )
        self.assertAlmostEqual(
            physics[f"{prefix}__slope_120m_per_min"].iloc[0],
            20.0 / 120.0,
        )


if __name__ == "__main__":
    unittest.main()
