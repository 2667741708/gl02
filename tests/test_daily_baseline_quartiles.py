"""Traceability tests for exact 30-day P25/P75 baseline persistence."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "自动诊断服务"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import baseline_maintainer  # noqa: E402


class FakeStore:
    last_rows: list[dict] = []

    def __init__(self, _config=None):
        self.frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-08-05", periods=100, freq="min"),
                "P_blast_cold": list(range(100)),
            }
        )

    def fetch_wide_frame(self, _start, _end):
        return self.frame

    def ensure_schema(self):
        return None

    def upsert_daily_baselines(self, _day, rows):
        FakeStore.last_rows = rows
        return len(rows)


def test_baseline_maintainer_persists_exact_series_quartiles() -> None:
    with patch.object(baseline_maintainer, "DiagnosisStore", FakeStore):
        result = baseline_maintainer.build_day(date(2026, 8, 6), write=True)
    row = result["rows"][0]
    assert row["variable_name"] == "P_blast_cold"
    assert row["p25"] == 24.75
    assert row["p75"] == 74.25
    assert row["iqr_ref"] == 49.5
    assert FakeStore.last_rows[0]["p25"] == 24.75
    assert FakeStore.last_rows[0]["p75"] == 74.25


def test_schema_upsert_and_8768_query_all_reference_p25_p75() -> None:
    schema = (SERVICE_DIR / "schema.sql").read_text(encoding="utf-8")
    store = (SERVICE_DIR / "store.py").read_text(encoding="utf-8")
    bridge = (SERVICE_DIR / "local_pg_ws_bridge.py").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS p25" in schema
    assert "ADD COLUMN IF NOT EXISTS p75" in schema
    assert "p10, p25, p50, p75, p90" in store
    compact_store = store.replace(" ", "").lower()
    assert "p25=excluded.p25" in compact_store
    assert "p75=excluded.p75" in compact_store
    assert "SELECT baseline_day, p25, p75, sample_count, coverage_ratio, updated_at" in bridge
    assert 'variable_name = \'P_blast_cold\'' in bridge
    assert 'context["pressure_baseline"] = baseline' in bridge


def test_strict_taphole_mean_requires_both_points_in_same_minute() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-08-05", periods=4, freq="min"),
            "T_taphole_1": [1400.0, 1410.0, None, 1430.0],
            "T_taphole_2": [1420.0, None, 1440.0, 1450.0],
        }
    )
    derived = baseline_maintainer.add_strict_derived_series(frame)
    assert derived["T_taphole_mean"].tolist()[0] == 1410.0
    assert pd.isna(derived["T_taphole_mean"].tolist()[1])
    assert pd.isna(derived["T_taphole_mean"].tolist()[2])
    assert derived["T_taphole_mean"].tolist()[3] == 1440.0


def test_top_mean_uses_bounded_five_minute_component_hold_and_preserves_real_series() -> None:
    frame = pd.DataFrame(
        {
            "T_top_A": [100.0, 100.0],
            "T_top_B": [110.0, None],
            "T_top_C": [120.0, 120.0],
            "T_top_D": [130.0, 130.0],
        }
    )
    derived = baseline_maintainer.add_strict_derived_series(frame)
    assert derived["T_top"].iloc[0] == 115.0
    assert derived["T_top"].iloc[1] == 115.0

    authoritative = frame.assign(T_top=[999.0, 998.0])
    preserved = baseline_maintainer.add_strict_derived_series(authoritative)
    assert preserved["T_top"].tolist() == [999.0, 998.0]


class DerivedFakeStore(FakeStore):
    def __init__(self, _config=None):
        self.frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-08-05", periods=12, freq="min"),
                "T_taphole_1": list(range(100, 112)),
                "T_taphole_2": list(range(120, 132)),
                "P_blast_cold": list(range(12)),
            }
        )


def test_derived_only_build_writes_real_aligned_series_statistics() -> None:
    with patch.object(baseline_maintainer, "DiagnosisStore", DerivedFakeStore):
        result = baseline_maintainer.build_day(
            date(2026, 8, 6), write=True, derived_only=True
        )
    assert [row["variable_name"] for row in result["rows"]] == ["T_taphole_mean"]
    row = result["rows"][0]
    expected = pd.Series(list(range(110, 122)), dtype=float)
    assert row["median_ref"] == round(float(expected.median()), 6)
    assert row["p25"] == round(float(expected.quantile(0.25)), 6)
    assert row["p75"] == round(float(expected.quantile(0.75)), 6)
    assert row["sample_count"] == 12
    assert row["source"]["components"] == ["T_taphole_1", "T_taphole_2"]
    assert row["source"]["alignment"] == "same_minute_all_components_required"


class CoolingFakeStore(FakeStore):
    requested_variables: list[str] | None = None

    def __init__(self, _config=None):
        values = list(range(12))
        self.frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-08-05", periods=12, freq="min"),
                **{
                    name: [float(value + offset) for value in values]
                    for offset, name in enumerate(baseline_maintainer.COOLING_BASELINE_VARIABLES)
                },
                "P_blast_cold": [450.0] * 12,
            }
        )

    def fetch_wide_frame(self, _start, _end, variables=None):
        CoolingFakeStore.requested_variables = variables
        columns = ["timestamp", *(variables or self.frame.columns[1:])]
        return self.frame.loc[:, columns]


def test_cooling_only_build_uses_six_independent_physical_series() -> None:
    with patch.object(baseline_maintainer, "DiagnosisStore", CoolingFakeStore):
        result = baseline_maintainer.build_day(
            date(2026, 8, 6), write=True, cooling_only=True
        )
    assert CoolingFakeStore.requested_variables == list(
        baseline_maintainer.COOLING_BASELINE_VARIABLES
    )
    assert {row["variable_name"] for row in result["rows"]} == set(
        baseline_maintainer.COOLING_BASELINE_VARIABLES
    ) - {"ExpansionTankLevel"}
    ordinary = [row for row in result["rows"] if row["variable_name"] != "ExpansionTankLevel"]
    assert all(row["source"]["type"] == "bounded_state_series" for row in ordinary)
    assert all(row["source"]["maximum_hold_minutes"] == 5 for row in ordinary)
    # Every row must retain its own shifted statistics; no cross-variable mean
    # and no zero-filling are permitted.
    medians = {row["variable_name"]: row["median_ref"] for row in result["rows"]}
    assert len(set(medians.values())) == 5
    assert all(row["sample_count"] == 12 for row in ordinary)


def test_body_temperature_baseline_uses_bounded_fifteen_minute_hold() -> None:
    timestamps = pd.date_range("2026-08-05", periods=20, freq="min")
    frame = pd.DataFrame({"timestamp": timestamps, "T_body_L10_A": [10.0, *([None] * 14), 20.0, *([None] * 4)]})
    series, source = baseline_maintainer.baseline_series(frame, "T_body_L10_A")
    assert len(series) == 20
    assert source["raw_sample_count"] == 2
    assert source["maximum_hold_minutes"] == 15


def test_expansion_tank_uses_hourly_then_daily_mean() -> None:
    class ExpansionStore(CoolingFakeStore):
        def __init__(self, _config=None):
            timestamps = pd.date_range("2026-07-07", periods=288, freq="h")
            self.frame = pd.DataFrame({
                "timestamp": timestamps,
                **{name: [10.0] * 288 for name in baseline_maintainer.COOLING_BASELINE_VARIABLES},
            })
            for day_index in range(12):
                self.frame.loc[day_index * 24:(day_index + 1) * 24 - 1, "ExpansionTankLevel"] = float(day_index + 1)

    with patch.object(baseline_maintainer, "DiagnosisStore", ExpansionStore):
        result = baseline_maintainer.build_day(date(2026, 8, 6), cooling_only=True)
    row = next(item for item in result["rows"] if item["variable_name"] == "ExpansionTankLevel")
    assert row["sample_count"] == 12
    assert row["median_ref"] == 6.5
    assert row["expected_minutes"] == 30
    assert row["coverage_ratio"] == round(12 / 30, 6)
    assert row["source"]["hourly_samples"] == 288
    assert row["source"]["daily_samples"] == 12


def test_cooling_only_does_not_persist_missing_signal_as_zero() -> None:
    class MissingCoolingStore(CoolingFakeStore):
        def __init__(self, _config=None):
            super().__init__(_config)
            self.frame["ExpansionTankLevel"] = float("nan")

    with patch.object(baseline_maintainer, "DiagnosisStore", MissingCoolingStore):
        result = baseline_maintainer.build_day(date(2026, 8, 6), cooling_only=True)
    names = {row["variable_name"] for row in result["rows"]}
    assert "ExpansionTankLevel" not in names
    assert names == set(baseline_maintainer.COOLING_BASELINE_VARIABLES) - {"ExpansionTankLevel"}


def test_cooling_and_derived_only_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        baseline_maintainer.build_day(
            date(2026, 8, 6), derived_only=True, cooling_only=True
        )
