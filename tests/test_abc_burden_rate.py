from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

from abc_burden_rate import _merge_probe_events, calculate_burden_rate_snapshot
from abc_rule_catalog import RULE_BY_ID
from abc_rule_engine import evaluate, load_config


def _rows(evaluation: datetime, *, recent_small_cycle_minutes: float = 4.0, recent_hours: int = 0):
    start = datetime.combine(evaluation.date() - timedelta(days=1), datetime.min.time())
    split = evaluation - timedelta(hours=recent_hours) if recent_hours else evaluation + timedelta(minutes=1)
    event_times: list[datetime] = []
    cursor = start + timedelta(minutes=4)
    while cursor < split:
        event_times.append(cursor)
        cursor += timedelta(minutes=4)
    if recent_hours:
        cursor = event_times[-1] + timedelta(minutes=recent_small_cycle_minutes)
        while cursor <= evaluation:
            event_times.append(cursor)
            cursor += timedelta(minutes=recent_small_cycle_minutes)
    rows = []
    event_set = set(event_times)
    for minute_index in range(int((evaluation-start).total_seconds()/60)+1):
        stamp = start + timedelta(minutes=minute_index)
        for probe, lifted in (("L_south", -0.50), ("L_north", -0.46)):
            value = lifted
            if stamp + timedelta(minutes=1) in event_set:
                value = 1.8 if probe == "L_south" else 2.4
            elif stamp + timedelta(minutes=2) in event_set:
                value = 1.0 if probe == "L_south" else 1.6
            rows.append({"variable_name": probe, "ts": stamp, "value": value})
        matching = [index for index, event in enumerate(event_times) if event-timedelta(minutes=2) <= stamp <= event]
        if matching:
            rows.append({"variable_name": "Hopper_weight", "ts": stamp,
                         "value": 42.0 if matching[-1] % 2 == 0 else 9.0})
        else:
            rows.append({"variable_name": "Hopper_weight", "ts": stamp, "value": 0.0})
    return rows


def _published_config():
    config = load_config()
    config["release_control"] = {"mode": "published", "scores_visible": True, "alerts_enabled": False}
    return config


def test_steady_complete_cycles_produce_7_5_large_batches_per_hour_and_zero_directional_risk():
    evaluation = datetime(2026, 8, 10, 12, 0)
    snapshot = calculate_burden_rate_snapshot(_rows(evaluation), evaluation)
    values = snapshot["values"]
    assert abs(values["BurdenRate_previous_30_large_per_hour"] - 7.5) < 1e-9
    assert abs(values["BurdenRate_current_30_large_per_hour"] - 7.5) < 1e-9
    assert all(values[name] == 0 for name in (
        "BurdenRateHalfHourDev", "BurdenRateYesterdayDev", "BurdenRate2hDev",
        "BurdenRateHalfHourSlow", "BurdenRateYesterdaySlow", "BurdenRate2hSlow",
        "BurdenRateHalfHourFast", "BurdenRateYesterdayFast", "BurdenRate2hFast",
    ))
    assert snapshot["source_semantics"] == "south_north_probe_descent_then_lift_equals_one_small_batch"
    assert {event["charge_type"] for event in snapshot["detected_events"]} == {"矿批", "焦批"}


def test_two_hours_one_large_batch_per_hour_above_rolling_average_forces_fast_factor_to_one():
    evaluation = datetime(2026, 8, 10, 12, 0)
    snapshot = calculate_burden_rate_snapshot(
        _rows(evaluation, recent_small_cycle_minutes=3.0, recent_hours=2),
        evaluation,
    )
    values = snapshot["values"]
    assert values["BurdenRate_rolling_2h_large_per_hour"] - values["BurdenRate_rolling_24h_large_per_hour"] >= 1.0
    assert values["BurdenRate2hFast"] == 1.0
    assert values["BurdenRate2hDev"] == 1.0


def test_missing_windows_do_not_become_zero_or_available():
    evaluation = datetime(2026, 8, 10, 12, 0)
    snapshot = calculate_burden_rate_snapshot([], evaluation)
    assert not any(snapshot["availability"].values())
    assert not any(name in snapshot["values"] for name in snapshot["availability"])


def test_synchronous_south_north_lift_is_one_small_batch_not_two():
    evaluation = datetime(2026, 8, 10, 12, 0)
    snapshot = calculate_burden_rate_snapshot(_rows(evaluation), evaluation)
    recent = [event for event in snapshot["detected_events"] if event["event_ts"] > evaluation-timedelta(minutes=30)]
    assert recent
    assert all(event["probes"] == ["L_north", "L_south"] for event in recent)
    assert abs(snapshot["values"]["BurdenRate_current_30_small_per_hour"] - 15.0) < 1e-9


def test_two_nearby_returns_from_same_probe_remain_two_small_batches():
    start = datetime(2026, 8, 10, 12, 0)
    merged = _merge_probe_events(
        [(start, "L_south"), (start+timedelta(minutes=1), "L_south")],
        tolerance_minutes=2.0,
    )
    assert len(merged) == 2
    assert [item["probes"] for item in merged] == [["L_south"], ["L_south"]]


def test_previous_and_current_half_hour_only_release_half_hour_factors():
    evaluation = datetime(2026, 8, 10, 12, 0)
    rows = [row for row in _rows(evaluation) if row["ts"] > evaluation-timedelta(minutes=65)]
    snapshot = calculate_burden_rate_snapshot(rows, evaluation)
    assert all(snapshot["availability"][name] for name in (
        "BurdenRateHalfHourDev", "BurdenRateHalfHourSlow", "BurdenRateHalfHourFast",
    ))
    assert not any(snapshot["availability"][name] for name in (
        "BurdenRateYesterdayDev", "BurdenRateYesterdaySlow", "BurdenRateYesterdayFast",
        "BurdenRate2hDev", "BurdenRate2hSlow", "BurdenRate2hFast",
    ))


def test_a2_b4_b5_burden_factors_are_first_weights_14_4_2_and_total_is_100():
    expected = {
        "A2": ("BurdenRateHalfHourDev", "BurdenRateYesterdayDev", "BurdenRate2hDev"),
        "B4": ("BurdenRateHalfHourSlow", "BurdenRateYesterdaySlow", "BurdenRate2hSlow"),
        "B5": ("BurdenRateHalfHourFast", "BurdenRateYesterdayFast", "BurdenRate2hFast"),
    }
    for rule_id, factors in expected.items():
        terms = RULE_BY_ID[rule_id].terms
        assert tuple(terms)[:3] == factors
        assert [terms[factor] for factor in factors] == [14, 4, 2]
        assert sum(terms.values()) == 100


def test_required_burden_factor_missing_fails_closed_even_when_other_80_percent_is_available():
    spec = RULE_BY_ID["B4"]
    features = {term: 0.0 for term in spec.terms if term != "BurdenRateHalfHourSlow"}
    quality = {term: {"available": True} for term in features}
    quality.update({
        "BurdenRateHalfHourSlow": {"available": False, "required": True},
        "coverage_ratio": 1.0,
        "data_age_seconds": 10,
    })
    bundle = evaluate(features, quality=quality, config=_published_config())
    item = next(item for item in bundle["evaluations"] if item["rule_id"] == "B4")
    assert item["confidence"] == 0.86
    assert item["status"] == "needs_data"
    assert item["required_missing_features"] == ["BurdenRateHalfHourSlow"]


def test_b_class_pressure_and_coal_semantics_are_not_mixed_during_sensor_expansion():
    assert "P_blast" in RULE_BY_ID["B2"].primary_sensors
    assert "P_blast_cold" not in RULE_BY_ID["B2"].primary_sensors
    assert "PCI_rate" in RULE_BY_ID["B4"].primary_sensors
    assert "PCI_rate" in RULE_BY_ID["B5"].primary_sensors
    assert "PCI_set" not in RULE_BY_ID["B4"].primary_sensors
    assert "PCI_set" not in RULE_BY_ID["B5"].primary_sensors
    assert {"T_taphole_1", "T_taphole_2"}.issubset(RULE_BY_ID["B4"].primary_sensors)
    assert {"T_top_A", "T_top_B", "T_top_C", "T_top_D"}.issubset(RULE_BY_ID["B5"].primary_sensors)
