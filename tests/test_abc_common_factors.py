from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

from abc_feature_builder import build_feature_snapshot, standardized_window_features


def _baseline(*names):
    return {name: {"median_ref": 10.0, "iqr_ref": 2.0, "coverage_ratio": .9} for name in names}


def _times(count=90, *, end=None):
    end = end or datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    return [(end-timedelta(minutes=count-1-index)).isoformat() for index in range(count)]


def test_timestamp_windows_use_real_minutes_and_exact_formulas():
    history = {"timestamps": _times(), "X": list(range(90))}
    features = standardized_window_features(history, _baseline("X"), "X")
    assert features["z60_X"] == pytest.approx((59.5-10)/2)
    assert features["slope30_X"] == pytest.approx(15.0)
    values = list(range(75, 90))
    sample_std = (sum((x-sum(values)/15) ** 2 for x in values)/14) ** .5
    assert features["z15std_X"] == pytest.approx(sample_std/(2/1.35))


def test_duplicate_minute_is_deduplicated_and_latest_sample_wins():
    timestamps = _times(60)
    history = {"timestamps": timestamps + [timestamps[-1]], "X": [10.0]*60 + [14.0]}
    features = standardized_window_features(history, _baseline("X"), "X")
    assert features["z60_X"] == pytest.approx(((59*10+14)/60-10)/2)


def test_evaluation_timestamp_rejects_stale_window():
    end = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    history = {"timestamps": _times(60, end=end), "evaluation_ts": (end+timedelta(hours=2)).isoformat(), "X": [10.0]*60}
    assert standardized_window_features(history, _baseline("X"), "X") == {}


def test_global_quality_gate_blocks_all_window_and_composite_features():
    history = {"timestamps": _times(), "P_top": [12.0]*90}
    features, quality = build_feature_snapshot({"P_top": 12}, history=history, baseline=_baseline("P_top"), data_age_seconds=301)
    assert "z60_P_top" not in features
    assert quality["window_features_available"] is False
    features, _ = build_feature_snapshot({"P_top": 12}, history=history, baseline=_baseline("P_top"), coverage_ratio=.74)
    assert "z60_P_top" not in features


def test_derived_baseline_is_never_fabricated_from_component_statistics():
    history = {"timestamps": _times(), "T_taphole_1": [10.0]*90, "T_taphole_2": [12.0]*90}
    features, _ = build_feature_snapshot({"T_taphole_1": 10, "T_taphole_2": 12}, history=history,
                                         baseline=_baseline("T_taphole_1", "T_taphole_2"))
    assert "z60_T_taphole_mean" not in features
    assert "HeatProxy" not in features


def test_asynchronous_derived_series_are_not_positionally_joined():
    history = {"timestamps": _times(), "T_top_A": [10.0]*90, "T_top_B": [10.0]*89,
               "T_top_C": [10.0]*90, "T_top_D": [10.0]*90}
    baseline = _baseline("T_top")
    features, _ = build_feature_snapshot({}, history=history, baseline=baseline)
    assert "z60_T_top" not in features


def test_dphigh_and_pibad_propagate_missing_constituents():
    names = ("DP_total", "DP_upper", "DP_lower", "PI")
    history = {"timestamps": _times(), **{name: [12.0]*90 for name in names}}
    features, _ = build_feature_snapshot({name: 12 for name in names}, history=history, baseline=_baseline(*names))
    assert features["DPHigh"] == pytest.approx((1-.8)/(1.5-.8))
    assert features["PIBad"] == pytest.approx((1-.6)/(1.2-.6))
    history.pop("DP_lower")
    features, _ = build_feature_snapshot({}, history=history, baseline=_baseline(*names))
    assert "DPHigh" not in features


def test_static_pressure_range_requires_cross_section_points_and_thresholds():
    current = {"P_static_upper": 10, "P_static_middle": 20, "P_static_lower": 30}
    features, _ = build_feature_snapshot(current, thresholds={"static_pressure_range": {"warn": 5, "alarm": 15}})
    assert "StaticPressRange" not in features
    current = {"P_static_upper_A": 10, "P_static_upper_B": 20}
    features, _ = build_feature_snapshot(current, thresholds={"static_pressure_range": {"warn": 5, "alarm": 15}})
    assert features["StaticPressRange"] == pytest.approx(.5)


def test_line_loss_requires_explicit_normal_level():
    features, _ = build_feature_snapshot({"L": 3.0}, thresholds={"line": {}})
    assert "LineLoss" not in features


def _full_common_fixture(level=12.0):
    scalar = [level] * 90
    names = {
        "P_top", "DP_total", "DP_upper", "DP_lower", "PI", "P_blast", "Q_blast", "GasUtil", "L",
        "Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water",
        "P_medium_pressure_water", "ExpansionTankLevel", "TFT", "T_taphole_mean", "T_top",
        "T_body_L7_A", "T_body_L7_B",
    }
    history = {"timestamps": _times(), **{name: list(scalar) for name in names}}
    current = {name: level for name in names}
    current.update({"T_top_A": level, "T_top_B": level, "T_top_C": level, "T_top_D": level,
                    "P_top_gas_A": level, "P_top_gas_B": level, "P_top_gas_C": level,
                    "P_top_gas_D": level, "L_south": level, "L_north": level,
                    "LineDropRate_15": 1.0})
    thresholds = {
        "line": {"normal_level": 10, "loss_direction": "higher", "drop_warn": .5, "drop_alarm": 1.5,
                 "south_north_bias_mean": 0, "bias_deviation_warn": .5, "bias_deviation_alarm": 1.0,
                 "rate_difference_warn": .5, "rate_difference_alarm": 1.0},
        "duration_minutes": {"warn": 15, "alarm": 60},
        "body_temperature_range": {"warn": 5, "alarm": 20},
    }
    return current, history, _baseline(*names), thresholds


@pytest.mark.parametrize("level", [6.0, 10.0, 12.0, 20.0])
def test_all_available_common_factors_are_bounded_for_wide_inputs(level):
    current, history, baseline, thresholds = _full_common_fixture(level)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    factor_names = {
        "TopTempRange", "TopPressRange", "GasUtilDev", "DPHigh", "PIBad", "AirAcceptBad",
        "BurdenStall", "BurdenSlip", "LineLoss", "LineBias", "BodyHotRisk", "BodyColdRisk",
        "CoolingRisk", "HeatProxy", "DrainProxy",
    }
    assert factor_names.issubset(features)
    assert all(0 <= features[name] <= 1 for name in factor_names)


@pytest.mark.parametrize("missing", ["DP_total", "DP_upper", "DP_lower"])
def test_dphigh_required_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "DPHigh" not in features
    assert "AirAcceptBad" not in features
    assert "DrainProxy" not in features


@pytest.mark.parametrize("missing", ["P_blast", "Q_blast", "DP_total", "DP_upper", "DP_lower"])
def test_air_acceptance_required_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "AirAcceptBad" not in features


@pytest.mark.parametrize("missing", [
    "Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water",
    "P_medium_pressure_water", "ExpansionTankLevel",
])
def test_cooling_required_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "CoolingRisk" not in features


@pytest.mark.parametrize("missing", ["T_taphole_mean", "T_top", "TFT"])
def test_heat_proxy_required_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "HeatProxy" not in features


def test_irregular_timestamp_slope_uses_elapsed_minutes_not_row_number():
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    offsets = [-29, -27, -25, -24, -22, -21, -20, -18, -17, -16, -15, -14,
               -13, -12, -11, -10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0]
    timestamps = [(end+timedelta(minutes=offset)).isoformat() for offset in offsets]
    values = [10 + 2*offset for offset in offsets]
    result = standardized_window_features({"timestamps": timestamps, "evaluation_ts": end.isoformat(), "X": values},
                                          _baseline("X"), "X")
    assert result["slope30_X"] == pytest.approx(30.0)


def test_future_points_are_excluded_relative_to_evaluation_timestamp():
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    timestamps = _times(60, end=end) + [(end+timedelta(minutes=1)).isoformat()]
    values = [10.0]*60 + [10000.0]
    result = standardized_window_features({"timestamps": timestamps, "evaluation_ts": end.isoformat(), "X": values},
                                          _baseline("X"), "X")
    assert result["z60_X"] == pytest.approx(0.0)


def test_same_minute_latest_timestamp_wins_not_largest_value():
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    timestamps = _times(59, end=end-timedelta(minutes=1))
    timestamps += [(end-timedelta(seconds=50)).isoformat(), (end-timedelta(seconds=10)).isoformat()]
    values = [10.0]*59 + [999.0, 14.0]
    result = standardized_window_features({"timestamps": timestamps, "evaluation_ts": end.isoformat(), "X": values},
                                          _baseline("X"), "X")
    assert result["z60_X"] == pytest.approx(((58*10+14)/59-10)/2)


@pytest.mark.parametrize("missing", ["L", "P_blast", "Q_blast", "DP_total", "DP_upper", "DP_lower"])
def test_burden_stall_required_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "BurdenStall" not in features
    assert "DrainProxy" not in features


@pytest.mark.parametrize("missing", ["L", "P_top", "DP_total"])
def test_burden_slip_required_window_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "BurdenSlip" not in features


def test_burden_slip_requires_drop_value_or_derivable_line_history():
    current, history, baseline, thresholds = _full_common_fixture()
    current.pop("LineDropRate_15")
    history.pop("L")
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "BurdenSlip" not in features


@pytest.mark.parametrize("missing", ["T_taphole_mean", "DP_lower", "PI", "L", "P_blast", "Q_blast"])
def test_drain_proxy_required_inputs_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "DrainProxy" not in features


@pytest.mark.parametrize("missing", ["T_body_L7_A", "T_body_L7_B"])
def test_body_risks_required_points_each_propagate_missing(missing):
    current, history, baseline, thresholds = _full_common_fixture()
    history.pop(missing)
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert "BodyHotRisk" not in features
    assert "BodyColdRisk" not in features


@pytest.mark.parametrize("factor,prefix", [("TopTempRange", "T_top_"), ("TopPressRange", "P_top_gas_")])
def test_four_point_ranges_require_all_current_points(factor, prefix):
    current, history, baseline, thresholds = _full_common_fixture()
    current.pop(f"{prefix}D")
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert factor not in features


def test_shared_timestamps_length_mismatch_never_falls_back_to_row_positions():
    history = {"timestamps": _times(60), "X": [10.0]*59}
    assert standardized_window_features(history, _baseline("X"), "X") == {}


def test_line_loss_duration_uses_continuous_real_minute_buckets():
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    thresholds = {"line": {"normal_level": 10, "loss_direction": "higher"},
                  "duration_minutes": {"warn": 15, "alarm": 60}}
    sparse = {"timestamps": [(end-timedelta(minutes=value)).isoformat() for value in (20, 10, 0)],
              "evaluation_ts": end.isoformat(), "L": [11.0, 11.0, 11.0]}
    features, _ = build_feature_snapshot({"L": 11}, history=sparse, baseline=_baseline("L"), thresholds=thresholds)
    assert features["LineLossDuration"] == 0
    regular = {"timestamps": _times(20, end=end), "evaluation_ts": end.isoformat(), "L": [11.0]*20}
    features, _ = build_feature_snapshot({"L": 11}, history=regular, baseline=_baseline("L"), thresholds=thresholds)
    assert features["LineLossDuration"] == pytest.approx((20-15)/(60-15))


def test_line_bias_duration_joins_both_series_on_real_minute_bucket():
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    thresholds = {"duration_minutes": {"warn": 2, "alarm": 6},
                  "line": {"south_north_bias_mean": 0, "bias_deviation_warn": .5,
                           "bias_deviation_alarm": 1.0}}
    history = {"timestamps": _times(4, end=end), "evaluation_ts": end.isoformat(),
               "L_south": [11.0]*4, "L_north": [10.0]*4}
    features, _ = build_feature_snapshot({}, history=history,
                                         baseline=_baseline("L_south", "L_north"), thresholds=thresholds)
    assert features["LineBiasDuration"] == pytest.approx(.5)


@pytest.mark.parametrize("prefix", ["T_top_", "P_top_gas_"])
def test_four_point_range_accepts_bounded_asynchronous_field_timestamps(prefix):
    current, history, baseline, thresholds = _full_common_fixture()
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    stamps = {f"{prefix}{letter}": end.isoformat() for letter in "ABCD"}
    stamps[f"{prefix}D"] = (end-timedelta(minutes=1)).isoformat()
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds,
                                         current_timestamps=stamps)
    factor = "TopTempRange" if prefix == "T_top_" else "TopPressRange"
    assert factor in features
    stamps.pop(f"{prefix}D")
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds,
                                         current_timestamps=stamps)
    assert factor not in features


@pytest.mark.parametrize("prefix", ["T_top_", "P_top_gas_"])
def test_four_point_range_rejects_stale_or_missing_field_timestamp(prefix):
    current, history, baseline, thresholds = _full_common_fixture()
    end = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    history["evaluation_ts"] = end.isoformat()
    stamps = {f"{prefix}{letter}": (end-timedelta(minutes=6)).isoformat() for letter in "ABCD"}
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds,
                                         current_timestamps=stamps)
    factor = "TopTempRange" if prefix == "T_top_" else "TopPressRange"
    assert factor not in features


def test_a9_intensity_edge_uses_highest_two_rates_and_current_constraints():
    current, history, baseline, thresholds = _full_common_fixture()
    history["O2_rate"] = [10.0] * 90
    history["PCI_rate"] = [10.0] * 90
    baseline.update(_baseline("O2_rate", "PCI_rate"))
    features, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    expected_q = (1-.8)/(1.5-.8)
    expected_strength = .60 * expected_q  # second-highest O2/PCI rate risk is zero
    expected_limit = max(features[key] for key in (
        "DPHigh", "PIBad", "GasUtilDev", "DrainProxy", "CoolingRisk", "low60_Ttap"
    ))
    assert features["EconomicIntensityStrength"] == pytest.approx(expected_strength)
    assert features["EconomicOperatingLimit"] == pytest.approx(expected_limit)
    assert features["EconomicIntensityEdge"] == pytest.approx(expected_strength * (.30 + .70 * expected_limit))


def test_a9_uses_measured_pci_rate_and_never_pci_set():
    current, history, baseline, thresholds = _full_common_fixture()
    history["O2_rate"] = [10.0] * 90
    history["PCI_rate"] = [12.0] * 90
    history["PCI_set"] = [45.0] * 90
    baseline.update(_baseline("O2_rate", "PCI_rate", "PCI_set"))
    first, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    history["PCI_set"] = [10.0] * 90
    second, _ = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    assert first["EconomicIntensityEdge"] == pytest.approx(second["EconomicIntensityEdge"])


def test_heat_proxy_uses_aligned_taphole_mean_and_exact_own_baseline():
    ramp = [float(value) for value in range(90)]
    history = {"timestamps": _times(), "T_taphole_1": ramp, "T_taphole_2": ramp,
               "T_top": [0.5*value for value in ramp], "TFT": [27.0]*90}
    baseline = {
        "T_taphole_mean": {"median_ref": 0, "iqr_ref": 30, "coverage_ratio": 1},
        "T_top": {"median_ref": 0, "iqr_ref": 30, "coverage_ratio": 1},
        "TFT": {"median_ref": 0, "iqr_ref": 30, "coverage_ratio": 1},
    }
    features, _ = build_feature_snapshot({}, history=history, baseline=baseline)
    assert features["z60_T_taphole_mean"] == pytest.approx(59.5/30)
    assert features["slope30_T_taphole_mean"] == pytest.approx(1.0)
    assert features["HeatProxy"] == 1.0


def test_real_t_top_series_is_preferred_over_four_point_derivation():
    history = {"timestamps": _times(), "T_top": [10.0]*90, "TFT": [10.0]*90,
               "T_taphole_1": [10.0]*90, "T_taphole_2": [10.0]*90,
               "T_top_A": list(range(90)), "T_top_B": list(range(90)),
               "T_top_C": list(range(90)), "T_top_D": list(range(90))}
    baseline = _baseline("T_top", "TFT", "T_taphole_mean")
    features, _ = build_feature_snapshot({}, history=history, baseline=baseline)
    assert features["slope30_T_top"] == 0
    assert features["HeatProxy"] == 0


def test_taphole_mean_requires_same_minute_values_not_alternating_points():
    first = [10.0 if index % 2 == 0 else None for index in range(90)]
    second = [None if index % 2 == 0 else 10.0 for index in range(90)]
    history = {"timestamps": _times(), "T_taphole_1": first, "T_taphole_2": second,
               "T_top": [10.0]*90, "TFT": [10.0]*90}
    features, _ = build_feature_snapshot({}, history=history,
                                         baseline=_baseline("T_taphole_mean", "T_top", "TFT"))
    assert "z60_T_taphole_mean" not in features
    assert "HeatProxy" not in features


def test_heat_proxy_requires_derived_taphole_mean_own_baseline():
    history = {"timestamps": _times(), "T_taphole_1": [10.0]*90, "T_taphole_2": [10.0]*90,
               "T_top": [10.0]*90, "TFT": [10.0]*90}
    baseline = _baseline("T_taphole_1", "T_taphole_2", "T_top", "TFT")
    features, _ = build_feature_snapshot({}, history=history, baseline=baseline)
    assert "z60_T_taphole_mean" not in features
    assert "HeatProxy" not in features


@pytest.mark.parametrize("missing", ["T_taphole_1", "T_taphole_2", "T_top", "TFT"])
def test_heat_proxy_four_inputs_are_all_required(missing):
    history = {"timestamps": _times(), "T_taphole_1": [10.0]*90, "T_taphole_2": [10.0]*90,
               "T_top": [10.0]*90, "TFT": [10.0]*90}
    history.pop(missing)
    features, _ = build_feature_snapshot({}, history=history,
                                         baseline=_baseline("T_taphole_mean", "T_top", "TFT"))
    assert "HeatProxy" not in features


def test_feature_builder_records_admin_only_factor_lineage():
    current, history, baseline, thresholds = _full_common_fixture()
    features, quality = build_feature_snapshot(current, history=history, baseline=baseline, thresholds=thresholds)
    audit = quality["factor_audit"]
    assert audit["low60_Qblast"]["factor_value"] == features["low60_Qblast"]
    assert audit["low60_Qblast"]["source_features"]["z60_Q_blast"] == features["z60_Q_blast"]
    assert audit["low60_Qblast"]["source_values"]["Q_blast"] == current["Q_blast"]
    assert audit["low60_Qblast"]["baseline_snapshot"]["Q_blast"]["median_ref"] == baseline["Q_blast"]["median_ref"]
    assert audit["low60_Qblast"]["effective_thresholds"]["input_transform"] == {
        "mode": "low", "a": -0.8, "b": -1.5, "input": "z60_Q_blast"
    }
