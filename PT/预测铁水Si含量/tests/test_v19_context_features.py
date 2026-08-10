"""Tests for REQ-SI-V19-CONTEXT-ABLATION-20260806."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from si_semantic_engine.v19_context_features import (
    CHEMISTRY_FIELDS,
    build_chemistry_context_features,
    build_mean_si_history_context,
    build_pci_context_features,
    context_feature_groups,
    merge_v19_context_features,
)


class V19ContextFeatureTests(unittest.TestCase):
    def test_previous_five_mean_si_are_strictly_earlier_and_published(self) -> None:
        cutoffs = pd.date_range("2026-02-01 00:00", periods=7, freq="h")
        targets = pd.DataFrame(
            {
                "official_meltno": [f"H{i}" for i in range(7)],
                "prediction_cutoff_ts": cutoffs,
                "label_available_ts": cutoffs + pd.Timedelta(minutes=10),
                "target__Si_mean": np.arange(7, dtype=float) / 10.0,
            }
        )
        history = build_mean_si_history_context(targets)
        row = history.loc[history["official_meltno"].eq("H6")].iloc[0]
        self.assertEqual(row["history_mean__available_heat_count"], 6)
        self.assertAlmostEqual(row["history_mean__Si_lag_1"], 0.5)
        self.assertAlmostEqual(row["history_mean__Si_lag_5"], 0.1)
        self.assertAlmostEqual(row["history_mean__Si_mean_5"], 0.3)

    def test_unpublished_previous_si_is_not_visible(self) -> None:
        targets = pd.DataFrame(
            {
                "official_meltno": ["H1", "H2"],
                "prediction_cutoff_ts": pd.to_datetime(
                    ["2026-02-01 01:00", "2026-02-01 02:00"]
                ),
                "label_available_ts": pd.to_datetime(
                    ["2026-02-01 03:00", "2026-02-01 01:30"]
                ),
                "target__Si_mean": [0.2, 0.3],
            }
        )
        history = build_mean_si_history_context(targets)
        row = history.loc[history["official_meltno"].eq("H2")].iloc[0]
        self.assertTrue(pd.isna(row["history_mean__Si_lag_1"]))

    def test_pci_current_and_previous_clock_hours_use_no_zero_imputation(self) -> None:
        targets = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "prediction_cutoff_ts": pd.to_datetime(["2026-02-01 10:30"]),
            }
        )
        minute_values = pd.DataFrame(
            {
                "official_meltno": ["H1"] * 3,
                "ts": pd.to_datetime(
                    ["2026-02-01 09:30", "2026-02-01 09:59", "2026-02-01 10:10"]
                ),
                "value": [60.0, 60.0, 120.0],
            }
        )
        result = build_pci_context_features(targets, minute_values).iloc[0]
        self.assertAlmostEqual(result["pci_context__current_hour_total"], 2.0)
        self.assertAlmostEqual(result["pci_context__previous_hour_total"], 2.0)
        self.assertEqual(result["pci_context__current_hour_coverage_minutes"], 1.0)
        self.assertEqual(result["pci_context__source_official"], 0.0)

    def test_future_chemistry_is_excluded_and_stale_is_marked(self) -> None:
        targets = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "prediction_cutoff_ts": pd.to_datetime(["2026-02-02 12:00"]),
            }
        )
        row = {field: 1.0 for field in CHEMISTRY_FIELDS}
        chemistry = pd.DataFrame(
            [
                {"published_ts": "2026-01-31 12:00", "machine": "JS1", **row},
                {"published_ts": "2026-02-03 12:00", "machine": "JS2", **row},
            ]
        )
        result = build_chemistry_context_features(targets, chemistry).iloc[0]
        self.assertAlmostEqual(result["chem_context__tfe__latest__JS1"], 1.0)
        self.assertTrue(pd.isna(result["chem_context__tfe__latest__JS2"]))
        self.assertEqual(result["chem_context__stale_flag"], 0.0)
        self.assertEqual(result["chem_context__lineage_confidence"], 0.0)

    def test_merge_rejects_target_columns_and_reports_groups(self) -> None:
        base = pd.DataFrame({"official_meltno": ["H1"], "x": [1.0]})
        context = pd.DataFrame(
            {
                "official_meltno": ["H1"],
                "history_mean__Si_lag_1": [0.2],
                "pci_context__current_hour_total": [1.0],
            }
        )
        merged = merge_v19_context_features(base, context)
        groups = context_feature_groups(merged)
        self.assertEqual(groups["history_si"], ["history_mean__Si_lag_1"])
        self.assertEqual(groups["pci"], ["pci_context__current_hour_total"])
        with self.assertRaises(ValueError):
            merge_v19_context_features(
                base,
                pd.DataFrame({"official_meltno": ["H1"], "target__bad": [1.0]}),
            )


if __name__ == "__main__":
    unittest.main()
