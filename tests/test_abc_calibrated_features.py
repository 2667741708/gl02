from pathlib import Path
import sys

import pytest

SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

from abc_feature_builder import build_feature_snapshot
from abc_rule_catalog import RULES
from abc_rule_engine import g_L


def _history(value, count=90):
    return [value for _ in range(count)]


def test_z60_uses_60_minute_mean_and_baseline_iqr():
    history = {"P_top": [10.0] * 30 + [14.0] * 60}
    baseline = {"P_top": {"median_ref": 10, "iqr_ref": 2, "coverage_ratio": .9}}
    features, _ = build_feature_snapshot({"P_top": 14}, history=history, baseline=baseline)
    assert features["z60_P_top"] == pytest.approx(2.0)


def test_z15std_and_slope30_are_iqr_normalized():
    ramp = list(range(90))
    baseline = {"X": {"median_ref": 0, "iqr_ref": 30, "coverage_ratio": 1}}
    features, _ = build_feature_snapshot({"X": 89}, history={"X": ramp}, baseline=baseline)
    assert features["slope30_X"] == pytest.approx(1.0)
    assert features["z15std_X"] > 0


def test_incomplete_windows_do_not_become_zero():
    baseline = {"X": {"median_ref": 1, "iqr_ref": 1, "coverage_ratio": 1}}
    features, _ = build_feature_snapshot({"X": 1}, history={"X": [1] * 10}, baseline=baseline)
    assert "z60_X" not in features
    assert "z15std_X" not in features
    assert "slope30_X" not in features


@pytest.mark.parametrize("coverage", [None, .74])
def test_baseline_missing_or_low_coverage_is_rejected(coverage):
    baseline = {"X": {"median_ref": 1, "iqr_ref": 1, "coverage_ratio": coverage}}
    features, _ = build_feature_snapshot({"X": 2}, history={"X": [2] * 90}, baseline=baseline)
    assert "z60_X" not in features
    assert "z15std_X" not in features
    assert "slope30_X" not in features


def test_low_membership_uses_document_direction():
    assert g_L(-.8, -.8, -1.5) == 0
    assert g_L(-1.5, -.8, -1.5) == 1


def test_catalog_contains_only_normalized_factors_not_raw_controls():
    forbidden = {"Q_blast", "P_blast", "P_blast_cold", "P_top", "T_taphole_1", "DP_lower", "PI"}
    for rule in RULES:
        assert forbidden.isdisjoint(rule.terms), rule.rule_id


def test_a9_uses_one_interacting_economic_boundary_term():
    a9 = next(rule for rule in RULES if rule.rule_id == "A9")
    assert a9.terms == {
        "DPHigh": 20,
        "PIBad": 15,
        "GasUtilDev": 15,
        "DrainProxy": 15,
        "CoolingRisk": 10,
        "low60_Ttap": 10,
        "EconomicIntensityEdge": 15,
    }
    assert sum(a9.terms.values()) == 100
    assert "PCI_set" not in a9.terms


def test_common_factors_are_bounded():
    names = ["P_top", "DP_total", "DP_upper", "DP_lower", "PI", "P_blast", "Q_blast", "GasUtil"]
    baseline = {name: {"median_ref": 0, "iqr_ref": 1, "coverage_ratio": 1} for name in names}
    history = {name: _history(2 if name != "GasUtil" else -2) for name in names}
    current = {name: values[-1] for name, values in history.items()}
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline)
    for key in ("DPHigh", "PIBad", "GasUtilDev", "AirAcceptBad"):
        assert 0 <= features[key] <= 1


def test_single_cooling_sensor_can_raise_maintenance_risk_but_not_c_event_concurrence():
    names = ["Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel"]
    baseline = {name: {"median_ref": 0, "iqr_ref": 1, "coverage_ratio": 1} for name in names}
    history = {name: _history(-2 if name == "Q_high_pressure_water" else 0) for name in names}
    current = {name: values[-1] for name, values in history.items()}
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline)
    assert features["CoolingRisk"] == 1
    assert features["CoolingConcurrence"] == 0
