from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.extract_v4_temporal_stats import (  # noqa: E402
    WINDOWS_MINUTES,
    _derive_statistics,
    build_statistics_query,
)


class V4TemporalStatisticsTests(unittest.TestCase):
    def test_query_is_strictly_before_cutoff_and_has_all_windows(self) -> None:
        query = build_statistics_query(2)
        self.assertEqual(query.count("(%s::text,%s::timestamp)"), 2)
        self.assertIn("v.ts < targets.target_ts", query)
        source = (
            ROOT
            / "src"
            / "si_semantic_engine"
            / "extract_v4_temporal_stats.py"
        ).read_text(encoding="utf-8")
        self.assertIn("default_transaction_read_only", source)
        for window in WINDOWS_MINUTES:
            self.assertIn(f"w{window}_mean", query)
            self.assertIn(f"w{window}_slope_per_min", query)

    def test_coverage_range_and_cv_are_derived_without_zero_fill(self) -> None:
        row = {}
        for window in WINDOWS_MINUTES:
            row.update(
                {
                    f"w{window}_count": window / 2,
                    f"w{window}_mean": 10.0,
                    f"w{window}_std": 2.0,
                    f"w{window}_min": 7.0,
                    f"w{window}_max": 13.0,
                    f"w{window}_slope_per_min": 0.1,
                }
            )
        output = _derive_statistics(pd.DataFrame([row])).iloc[0]
        for window in WINDOWS_MINUTES:
            self.assertAlmostEqual(
                output[f"w{window}_coverage_ratio"], 0.5
            )
            self.assertAlmostEqual(output[f"w{window}_range"], 6.0)
            self.assertAlmostEqual(output[f"w{window}_cv"], 0.2)

    def test_custom_480_minute_window_extends_database_lookback(self) -> None:
        windows = (30, 60, 120, 240, 480)
        query = build_statistics_query(1, windows)
        self.assertIn("w480_mean", query)
        self.assertIn("interval '480 minutes'", query)
        row = {}
        for window in windows:
            row.update(
                {
                    f"w{window}_count": window,
                    f"w{window}_mean": 10.0,
                    f"w{window}_std": 1.0,
                    f"w{window}_min": 8.0,
                    f"w{window}_max": 12.0,
                    f"w{window}_slope_per_min": 0.0,
                }
            )
        output = _derive_statistics(
            pd.DataFrame([row]), windows
        ).iloc[0]
        self.assertAlmostEqual(output["w480_coverage_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
