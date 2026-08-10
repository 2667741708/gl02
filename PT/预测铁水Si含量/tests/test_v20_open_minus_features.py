"""Tests for REQ-SI-V20-OPEN-MINUS-HITRATE-20260807."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from si_semantic_engine.v20_open_minus_features import (
    build_history_gap_features,
    build_pci_window_features,
    compute_cutoff_ts,
    expand_lead_samples,
    merge_feature_blocks,
    regression_metrics,
)


class V20OpenMinusFeatureTests(unittest.TestCase):
    def test_cutoff_is_open_minus_lead_minutes(self) -> None:
        cutoff = compute_cutoff_ts("2026-08-07 07:40:00", 60)
        self.assertEqual(str(cutoff), "2026-08-07 06:40:00")

    def test_expand_lead_samples_keeps_each_lead_separate(self) -> None:
        heats = pd.DataFrame(
            {
                "official_meltno": ["2#20260807-095"],
                "open_ts": pd.to_datetime(["2026-08-07 07:40:00"]),
                "label_available_ts": pd.to_datetime(["2026-08-07 09:00:00"]),
                "target__Si_mean": [0.31],
            }
        )
        samples = expand_lead_samples(heats, [60, 15])
        self.assertEqual(list(samples["lead_minutes"]), [60, 15])
        self.assertEqual(str(samples.loc[0, "prediction_cutoff_ts"]), "2026-08-07 06:40:00")
        self.assertEqual(str(samples.loc[1, "prediction_cutoff_ts"]), "2026-08-07 07:25:00")

    def test_history_uses_previous_published_heats_not_current_or_unpublished(self) -> None:
        heats = pd.DataFrame(
            {
                "official_meltno": ["H1", "H2", "H3"],
                "open_ts": pd.to_datetime(
                    ["2026-08-07 00:00", "2026-08-07 02:00", "2026-08-07 04:00"]
                ),
                "label_available_ts": pd.to_datetime(
                    ["2026-08-07 00:30", "2026-08-07 05:00", "2026-08-07 04:10"]
                ),
                "target__Si_mean": [0.28, 0.41, 0.35],
            }
        )
        samples = pd.DataFrame(
            {
                "official_meltno": ["H3"],
                "open_ts": pd.to_datetime(["2026-08-07 04:00"]),
                "prediction_cutoff_ts": pd.to_datetime(["2026-08-07 03:00"]),
            }
        )
        features = build_history_gap_features(samples, heats).iloc[0]
        self.assertAlmostEqual(features["history_mean__Si_lag_1"], 0.28)
        self.assertTrue(pd.isna(features["history_mean__Si_lag_2"]))
        self.assertEqual(features["v20_history__latest_label_meltno_distance"], 2.0)
        self.assertEqual(features["v20_history__unlabeled_heat_gap"], 1.0)

    def test_current_heat_target_is_not_visible_even_if_label_time_is_early(self) -> None:
        heats = pd.DataFrame(
            {
                "official_meltno": ["H1", "H2"],
                "open_ts": pd.to_datetime(["2026-08-07 00:00", "2026-08-07 02:00"]),
                "label_available_ts": pd.to_datetime(["2026-08-07 00:30", "2026-08-07 01:30"]),
                "target__Si_mean": [0.25, 0.55],
            }
        )
        samples = pd.DataFrame(
            {
                "official_meltno": ["H2"],
                "open_ts": pd.to_datetime(["2026-08-07 02:00"]),
                "prediction_cutoff_ts": pd.to_datetime(["2026-08-07 03:00"]),
            }
        )
        features = build_history_gap_features(samples, heats).iloc[0]
        self.assertAlmostEqual(features["history_mean__Si_lag_1"], 0.25)

    def test_pci_windows_use_strictly_before_cutoff_and_no_zero_fill(self) -> None:
        samples = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "prediction_cutoff_ts": pd.to_datetime(["2026-08-07 10:00"]),
            }
        )
        minute_values = pd.DataFrame(
            {
                "official_meltno": ["H1", "H1", "H1"],
                "ts": pd.to_datetime(
                    ["2026-08-07 09:00", "2026-08-07 09:30", "2026-08-07 10:01"]
                ),
                "value": [60.0, 120.0, 999.0],
            }
        )
        features = build_pci_window_features(samples, minute_values, windows_hours=[1, 8]).iloc[0]
        self.assertAlmostEqual(features["v20_pci__1h_amount_t"], 3.0)
        self.assertEqual(features["v20_pci__1h_coverage_minutes"], 2.0)
        self.assertAlmostEqual(features["v20_pci__8h_amount_t"], 3.0)

    def test_merge_rejects_target_columns(self) -> None:
        base = pd.DataFrame({"official_meltno": ["H1"], "x": [1.0]})
        with self.assertRaises(ValueError):
            merge_feature_blocks(
                base,
                pd.DataFrame({"official_meltno": ["H1"], "target__Si_mean": [0.3]}),
            )

    def test_merge_uses_sample_id_when_multiple_leads_share_one_heat(self) -> None:
        base = pd.DataFrame(
            {
                "v20_sample_id": ["H1__lead_60m", "H1__lead_15m"],
                "official_meltno": ["H1", "H1"],
            }
        )
        block = pd.DataFrame(
            {
                "v20_sample_id": ["H1__lead_60m", "H1__lead_15m"],
                "official_meltno": ["H1", "H1"],
                "v20_pci__1h_amount_t": [1.0, 2.0],
            }
        )
        merged = merge_feature_blocks(base, block)
        self.assertEqual(list(merged["v20_pci__1h_amount_t"]), [1.0, 2.0])

    def test_metrics_define_abs_005_hit_rate(self) -> None:
        metrics = regression_metrics(
            pd.Series([0.30, 0.40, 0.50]),
            pd.Series([0.34, 0.46, 0.51]),
        )
        self.assertAlmostEqual(metrics["hit_rate_abs_le_005"], 2.0 / 3.0)
        self.assertAlmostEqual(metrics["mae"], np.mean([0.04, 0.06, 0.01]))


if __name__ == "__main__":
    unittest.main()
