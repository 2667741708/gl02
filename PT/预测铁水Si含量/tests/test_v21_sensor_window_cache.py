"""Tests for REQ-SI-V21-SENSOR-CACHE-20260808."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "PT" / "预测铁水Si含量" / "src"))

from build_open_minus_si_dataset_v20 import load_sensor_window_cache  # noqa: E402
from build_v20_sensor_window_cache import compute_sensor_feature_block  # noqa: E402


class V21SensorWindowCacheTests(unittest.TestCase):
    def test_sensor_cache_window_is_left_closed_and_right_open(self) -> None:
        samples = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "v20_sample_id": ["H1__lead_60m"],
                "prediction_cutoff_ts": pd.to_datetime(["2026-08-07 10:00:00"]),
            }
        )
        values = pd.DataFrame(
            {
                "ts": pd.to_datetime(
                    [
                        "2026-08-07 08:59:00",
                        "2026-08-07 09:00:00",
                        "2026-08-07 09:30:00",
                        "2026-08-07 10:00:00",
                    ]
                ),
                "value": [999.0, 10.0, 20.0, 777.0],
            }
        )
        block = compute_sensor_feature_block(
            samples,
            values,
            short_name="PCI_rate",
            windows_minutes=(60, 30),
        ).iloc[0]
        self.assertAlmostEqual(block["v20_sensor__PCI_rate__60m_mean"], 15.0)
        self.assertEqual(block["v20_sensor__PCI_rate__60m_coverage_minutes"], 2.0)
        self.assertAlmostEqual(block["v20_sensor__PCI_rate__60m_last"], 20.0)
        self.assertAlmostEqual(block["v20_sensor__PCI_rate__60m_delta"], 10.0)
        self.assertAlmostEqual(block["v20_sensor__PCI_rate__30m_mean"], 20.0)
        self.assertEqual(block["v20_sensor__PCI_rate__30m_coverage_minutes"], 1.0)

    def test_dataset_builder_loads_cache_by_sample_id_not_heat_only(self) -> None:
        samples = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "v20_sample_id": ["H1__lead_60m"],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.csv"
            pd.DataFrame(
                {
                    "official_meltno": ["H1", "H1"],
                    "v20_sample_id": ["H1__lead_60m", "H1__lead_15m"],
                    "v20_sensor__PCI_rate__60m_mean": [11.0, 99.0],
                }
            ).to_csv(cache_path, index=False, encoding="utf-8-sig")
            loaded, audit = load_sensor_window_cache(
                cache_path,
                samples,
                windows_minutes=(60,),
                sensor_name_scope="core28",
            )
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["v20_sample_id"], "H1__lead_60m")
        self.assertAlmostEqual(loaded.iloc[0]["v20_sensor__PCI_rate__60m_mean"], 11.0)
        self.assertEqual(audit["merge_key"], ["v20_sample_id"])


if __name__ == "__main__":
    unittest.main()
