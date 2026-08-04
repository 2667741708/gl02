from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.v5_features import (  # noqa: E402
    load_temporal_statistics,
    pivot_temporal_statistics,
    select_train_correlated_features,
)
from si_semantic_engine.formal_dataset import sha256_file  # noqa: E402


class V5FeatureTests(unittest.TestCase):
    def test_loader_rejects_tampered_hashed_part(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            part_path = directory / "part-00001.parquet"
            pd.DataFrame(
                {
                    "official_meltno": ["H1"],
                    "sensor_id": ["S1"],
                }
            ).to_parquet(part_path, index=False)
            manifest = {
                "total_rows": 1,
                "parts": [
                    {
                        "name": part_path.name,
                        "sha256": sha256_file(part_path),
                    }
                ],
            }
            (directory / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            part_path.write_bytes(part_path.read_bytes() + b"tampered")
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                load_temporal_statistics(directory)

    def test_pivot_requires_exact_cutoff_and_preserves_heat_order(self) -> None:
        rows = []
        for meltno, cutoff in (
            ("H1", "2026-07-27 01:00:00"),
            ("H2", "2026-07-27 02:00:00"),
        ):
            row = {
                "official_meltno": meltno,
                "feature_cutoff_ts": cutoff,
                "sensor_id": "S1",
                "variable_name": "PI",
            }
            for window in (30, 60, 120, 240):
                for statistic in (
                    "count",
                    "mean",
                    "std",
                    "min",
                    "max",
                    "slope_per_min",
                    "coverage_ratio",
                    "range",
                    "cv",
                ):
                    row[f"w{window}_{statistic}"] = float(window)
            rows.append(row)
        heats = pd.DataFrame(
            {
                "official_meltno": ["H2", "H1"],
                "prediction_cutoff_ts": [
                    "2026-07-27 02:00:00",
                    "2026-07-27 01:00:00",
                ],
            }
        )
        wide, audit = pivot_temporal_statistics(
            pd.DataFrame(rows), heats
        )
        self.assertEqual(audit["physical_sensor_count"], 1)
        self.assertEqual(audit["feature_count"], 36)
        self.assertEqual(
            wide["temporal__PI__w30_mean"].tolist(), [30.0, 30.0]
        )

    def test_feature_ranking_uses_only_supplied_training_rows(self) -> None:
        train = pd.DataFrame(
            {
                "good": [1.0, 2.0, 3.0, 4.0],
                "reverse": [4.0, 3.0, 2.0, 1.0],
                "constant": [9.0, 9.0, 9.0, 9.0],
                "invalid": [float("inf")] * 4,
            }
        )
        selected, ranking = select_train_correlated_features(
            train,
            pd.Series([1.0, 2.0, 3.0, 4.0]),
            list(train.columns),
            top_k=2,
        )
        self.assertEqual(set(selected), {"good", "reverse"})
        self.assertNotIn("constant", ranking["feature"].tolist())
        self.assertNotIn("invalid", ranking["feature"].tolist())


if __name__ == "__main__":
    unittest.main()
