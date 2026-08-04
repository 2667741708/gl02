from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "自动诊断服务" / "local_pg_ws_bridge.py"
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("local_pg_ws_bridge_cohesive_zone_test", MODULE_PATH)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


@pytest.fixture(autouse=True)
def reset_snapshot_cache(monkeypatch):
    bridge._COHESIVE_ZONE_SNAPSHOT_CACHE["computed_monotonic"] = 0.0
    bridge._COHESIVE_ZONE_SNAPSHOT_CACHE["source_key"] = None
    bridge._COHESIVE_ZONE_SNAPSHOT_CACHE["snapshot"] = None
    monkeypatch.setattr(bridge, "COHESIVE_ZONE_ENABLED", True)
    monkeypatch.setattr(bridge, "COHESIVE_ZONE_COMPUTE_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(bridge, "COHESIVE_ZONE_STALE_AFTER_SECONDS", 600.0)
    yield
    bridge._COHESIVE_ZONE_SNAPSHOT_CACHE["computed_monotonic"] = 0.0
    bridge._COHESIVE_ZONE_SNAPSHOT_CACHE["source_key"] = None
    bridge._COHESIVE_ZONE_SNAPSHOT_CACHE["snapshot"] = None


def complete_input_frame(evaluation_time: datetime, *, include_future: bool = False) -> pd.DataFrame:
    periods = 31 if include_future else 30
    index = pd.date_range(evaluation_time - timedelta(minutes=29), periods=periods, freq="min")
    data: dict[str, list[float]] = {}
    variables = {
        *bridge.COHESIVE_ZONE_DISPLAY_VARIABLES,
        *bridge.COHESIVE_ZONE_STOCKLINE_VARIABLES,
        *bridge.COHESIVE_ZONE_BLAST_VARIABLES,
    }
    for position, variable in enumerate(sorted(variables)):
        data[variable] = [float(position + minute / 100.0) for minute in range(periods)]
    return pd.DataFrame(data, index=index)


def available_estimate(sample_time: datetime) -> dict[str, Any]:
    return {
        "status": "available",
        "centerHeight": 21.2,
        "thickness": 2.4,
        "innerRadius": 1.1,
        "outerRadius": 4.0,
        "eccentricity": 0.12,
        "eccentricAngle": 0.4,
        "amplitude": 2.0,
        "uncertainty": 0.7,
        "shape": "inverted_v",
        "evidence": "estimated",
        "model_version": "C2-ROOT-MOTION-v1",
        "calibration_status": "uncalibrated",
        "control_use": "prohibited",
        "root_definition": "wall_thermal_activity_centroid",
        "azimuth_reference": "sensor_relative_A_zero",
        "absolute_azimuth_status": "unconfirmed",
        "movement": {
            "direction": "up",
            "velocity_m_per_h": 0.08,
            "forecast_horizon_minutes": 15,
            "forecast_height_m": 21.22,
            "forecast_assumption": "constant_velocity_uncalibrated",
        },
        "sector_roots": [],
        "confidence": 0.42,
        "input_coverage": 1.0,
        "quality": {"state": "good"},
        "sample_time": sample_time.isoformat(sep=" "),
    }


def real_estimator_input_frame(evaluation_time: datetime) -> pd.DataFrame:
    periods = 90
    split = periods - 30
    index = pd.date_range(end=evaluation_time, periods=periods, freq="min")
    data: dict[str, list[float]] = {}
    for layer, height in {
        7: 16.860,
        8: 18.335,
        9: 20.125,
        10: 21.860,
        11: 23.711,
        12: 25.441,
        13: 27.171,
    }.items():
        for sector in "ABCDEFGH":
            values = []
            for row in range(periods):
                target_height = 18.5 if row < split else 25.5
                value = 45.0 + 60.0 * math.exp(-((height - target_height) ** 2) / 7.0)
                if sector == "A":
                    value += 18.0
                values.append(value)
            data[f"T_body_L{layer}_{sector}"] = values
    for height_index, height in enumerate(("lower", "middle", "upper")):
        for sector_index, sector in enumerate("ABCDEF"):
            data[f"P_static_{height}_{sector}"] = [
                180.0 - height_index * 22.0 + sector_index * 0.4
            ] * periods
    data.update(
        {
            "DP_total": [170.0] * split + [195.0] * (periods - split),
            "DP_lower": [90.0] * periods,
            "DP_upper": [80.0] * periods,
            "PI": [20.0] * periods,
            "Q_blast": [5200.0] * periods,
            "P_blast": [390.0] * periods,
            "P_blast_cold": [410.0] * periods,
            "T_blast": [1180.0] * periods,
            "Q_O2": [14500.0] * periods,
            "O2_rate": [4.2] * periods,
            "PCI_rate": [42.0] * periods,
            "PCI_set": [42.0] * periods,
            "TFT": [2150.0] * periods,
            "T_top_A": [145.0] * periods,
            "T_top_B": [146.0] * periods,
            "T_top_C": [144.0] * periods,
            "T_top_D": [145.0] * periods,
            "P_top": [250.0] * periods,
            "L": [1.8] * periods,
            "L_south": [1.82] * periods,
            "L_north": [1.78] * periods,
        }
    )
    return pd.DataFrame(data, index=index)


def test_lazy_loader_resolves_estimator_public_api():
    estimator, warning = bridge._load_cohesive_zone_estimator()

    assert warning is None
    assert callable(estimator)
    assert estimator.__name__ == "estimate_cohesive_zone"


def test_success_is_knowledge_time_bounded_and_process_cached(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    frame = complete_input_frame(evaluation_time, include_future=True)
    frame.loc[pd.Timestamp(evaluation_time), :] = pd.NA
    captured: list[pd.DataFrame] = []

    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: frame,
    )

    def estimator(data, **kwargs):
        captured.append(data.copy())
        assert kwargs["evaluation_time"] == evaluation_time
        return available_estimate(evaluation_time)

    monkeypatch.setattr(bridge, "_load_cohesive_zone_estimator", lambda: (estimator, None))

    first = bridge.build_bf3d_snapshot(object(), evaluation_time)
    second = bridge.build_bf3d_snapshot(object(), evaluation_time + timedelta(minutes=1))

    assert first is second
    assert len(captured) == 1
    assert captured[0].index.max().to_pydatetime() <= evaluation_time
    assert first["schema_version"] == "bf3d_snapshot.v1"
    assert first["estimated"]["cohesive_zone"]["status"] == "available"
    assert first["estimated"]["cohesive_zone"]["movement"]["direction"] == "up"
    assert first["watermarks"]["sensor_sample_time"] == (
        evaluation_time - timedelta(minutes=1)
    ).isoformat(sep=" ")
    assert len(first["measured"]["static_pressure"]) == 18
    assert first["measured"]["stockline"]["L"] is not None
    assert first["measured"]["blast"]["Q_blast"] is not None


def test_cache_recomputes_for_reverse_knowledge_time(monkeypatch):
    later = datetime.now().replace(second=0, microsecond=0)
    earlier = later - timedelta(hours=1)
    estimator_calls: list[datetime] = []

    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: complete_input_frame(until),
    )

    def estimator(data, **kwargs):
        evaluation_time = kwargs["evaluation_time"]
        estimator_calls.append(evaluation_time)
        return available_estimate(evaluation_time)

    monkeypatch.setattr(bridge, "_load_cohesive_zone_estimator", lambda: (estimator, None))

    later_snapshot = bridge.build_bf3d_snapshot(object(), later)
    earlier_snapshot = bridge.build_bf3d_snapshot(object(), earlier)

    assert len(estimator_calls) == 2
    assert later_snapshot["knowledge_time"] == later.isoformat(sep=" ")
    assert earlier_snapshot["knowledge_time"] == earlier.isoformat(sep=" ")
    assert earlier_snapshot is not later_snapshot


def test_cache_recomputes_when_database_profile_changes(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    calls = 0
    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: complete_input_frame(until),
    )

    def estimator(data, **kwargs):
        nonlocal calls
        calls += 1
        return available_estimate(kwargs["evaluation_time"])

    monkeypatch.setattr(bridge, "_load_cohesive_zone_estimator", lambda: (estimator, None))
    monkeypatch.setenv("GL02_PGDATABASE", "bf_profile_a")
    bridge.build_bf3d_snapshot(object(), evaluation_time)
    monkeypatch.setenv("GL02_PGDATABASE", "bf_profile_b")
    bridge.build_bf3d_snapshot(object(), evaluation_time)

    assert calls == 2


def test_missing_data_returns_null_estimate_and_quality(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: pd.DataFrame(),
    )

    snapshot = bridge.build_bf3d_snapshot(object(), evaluation_time)

    assert snapshot["estimated"]["cohesive_zone"] is None
    assert snapshot["quality"]["state"] == "missing"
    assert snapshot["quality"]["missing"]
    assert "cohesive_zone_input_empty" in snapshot["quality"]["warnings"]
    assert snapshot["watermarks"]["sensor_sample_time"] is None
    assert len(snapshot["measured"]["static_pressure"]) == 18
    assert all(row["value"] is None for row in snapshot["measured"]["static_pressure"])


def test_estimator_exception_degrades_without_raising(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    frame = complete_input_frame(evaluation_time)
    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: frame,
    )

    def broken_estimator(data, **kwargs):
        raise RuntimeError("deliberate test failure")

    monkeypatch.setattr(
        bridge,
        "_load_cohesive_zone_estimator",
        lambda: (broken_estimator, None),
    )

    snapshot = bridge.build_bf3d_snapshot(object(), evaluation_time)

    assert snapshot["estimated"]["cohesive_zone"] is None
    assert snapshot["quality"]["state"] == "degraded"
    assert "cohesive_zone_estimator_failed:RuntimeError" in snapshot["quality"]["warnings"]


def test_malformed_available_result_is_hidden_by_contract_gate(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    frame = complete_input_frame(evaluation_time)
    malformed = available_estimate(evaluation_time)
    malformed["outerRadius"] = float("nan")
    malformed["confidence"] = 0.9
    malformed["movement"] = {
        "direction": "sideways",
        "velocity_m_per_h": float("inf"),
    }
    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: frame,
    )
    monkeypatch.setattr(
        bridge,
        "_load_cohesive_zone_estimator",
        lambda: (lambda data, **kwargs: malformed, None),
    )

    snapshot = bridge.build_bf3d_snapshot(object(), evaluation_time)

    assert snapshot["estimated"]["cohesive_zone"] is None
    assert snapshot["quality"]["state"] == "degraded"
    assert snapshot["quality"]["cohesive_zone"]["status"] == "contract_invalid"
    assert any(
        warning.startswith("cohesive_zone_estimator_contract_invalid:")
        for warning in snapshot["quality"]["warnings"]
    )
    json.dumps(snapshot, ensure_ascii=False, allow_nan=False)


def test_real_estimator_end_to_end_snapshot_contract(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    frame = real_estimator_input_frame(evaluation_time).drop(
        columns=[
            *bridge.COHESIVE_ZONE_STATIC_PRESSURE_VARIABLES,
            "P_blast",
            "P_blast_cold",
        ]
    )
    monkeypatch.setattr(
        bridge,
        "fetch_cohesive_zone_input_frame",
        lambda conn, since, until: frame,
    )

    snapshot = bridge.build_bf3d_snapshot(object(), evaluation_time)
    estimate = snapshot["estimated"]["cohesive_zone"]

    assert estimate["status"] == "available"
    assert estimate["evidence"] == "estimated"
    assert estimate["calibration_status"] == "uncalibrated"
    assert estimate["control_use"] == "prohibited"
    assert estimate["movement"]["direction"] == "up"
    assert estimate["movement"]["forecast_horizon_minutes"] == 15
    assert isinstance(estimate["movement"]["forecast_height_m"], float)
    assert estimate["thickness"] > 0
    assert estimate["eccentricity"] > 0
    assert snapshot["watermarks"]["sensor_sample_time"] == evaluation_time.isoformat(sep=" ")
    quality = snapshot["quality"]["cohesive_zone"]
    assert quality["calibration_status"] == "uncalibrated"
    assert quality["control_use"] == "prohibited"
    assert quality["root_definition"] == "wall_thermal_activity_centroid"
    assert quality["azimuth_reference"] == "sensor_relative_A_zero"
    assert quality["absolute_azimuth_status"] == "unconfirmed"
    assert snapshot["quality"]["state"] == "good"
    assert snapshot["quality"]["estimator_minimum_groups"]["body_temperature"][
        "state"
    ] == "satisfied"
    assert snapshot["quality"]["estimator_minimum_groups"][
        "pressure_permeability"
    ]["state"] == "satisfied"
    assert snapshot["quality"]["display_completeness"]["ratio"] < 1.0
    assert snapshot["quality"]["optional_enhancements"]["static_pressure_18"][
        "available"
    ] == 0
    json.dumps(snapshot, ensure_ascii=False, allow_nan=False)


def test_unexpected_snapshot_error_isolated_from_stream(monkeypatch):
    evaluation_time = datetime.now().replace(second=0, microsecond=0)
    monkeypatch.setattr(
        bridge,
        "build_bf3d_snapshot",
        lambda conn, evaluation_time: (_ for _ in ()).throw(KeyError("unexpected")),
    )

    snapshot = bridge.safe_build_bf3d_snapshot(object(), evaluation_time)

    assert snapshot["schema_version"] == "bf3d_snapshot.v1"
    assert snapshot["estimated"]["cohesive_zone"] is None
    assert snapshot["quality"]["state"] == "missing"
    assert "cohesive_zone_snapshot_failed:KeyError" in snapshot["quality"]["warnings"]


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_init_and_tick_keep_existing_fields_and_append_snapshot(monkeypatch):
    timestamp = datetime.now().replace(second=0, microsecond=0).isoformat(sep=" ")
    snapshot = unavailable_snapshot = bridge.unavailable_bf3d_snapshot(timestamp, "test")
    history = {"timestamps": [timestamp], "L": [2.1]}
    values = {variable: None for variable in bridge.FRONTEND_VARIABLES}
    values["L"] = 2.1

    monkeypatch.setattr(bridge.psycopg, "connect", lambda **kwargs: FakeConnection())
    monkeypatch.setattr(bridge, "latest_data_ts", lambda conn: datetime.fromisoformat(timestamp))
    monkeypatch.setattr(bridge, "fetch_history", lambda conn, since: history)
    monkeypatch.setattr(bridge, "fetch_diagnosis_history", lambda conn: [{"diagnosis_ts": timestamp}])
    monkeypatch.setattr(bridge, "latest_values", lambda conn: (timestamp, values))
    monkeypatch.setattr(bridge, "latest_quality", lambda conn, current_ts=None: {"status": "ok"})
    monkeypatch.setattr(bridge, "latest_diagnosis", lambda conn, current_values=None: {"label": "normal"})
    monkeypatch.setattr(bridge, "build_bf3d_snapshot", lambda conn, evaluation_time: snapshot)

    init_payload = bridge.build_init_payload()
    tick_payload = bridge.build_tick_payload()

    assert init_payload["type"] == "init"
    assert init_payload["timestamp"] == timestamp
    assert init_payload["history"] is history
    assert init_payload["values"]["L"] == 2.1
    assert init_payload["diagnosis_history"] == [{"diagnosis_ts": timestamp}]
    assert init_payload["data_quality"] == {"status": "ok"}
    assert init_payload["diagnosis"] == {"label": "normal"}
    assert init_payload["bf3d_snapshot"] is unavailable_snapshot
    assert "source" in init_payload and "replay" in init_payload

    assert tick_payload["type"] == "tick"
    assert tick_payload["timestamp"] == timestamp
    assert "history" not in tick_payload
    assert tick_payload["values"] is values
    assert tick_payload["diagnosis_history"] == [{"diagnosis_ts": timestamp}]
    assert tick_payload["data_quality"] == {"status": "ok"}
    assert tick_payload["diagnosis"] == {"label": "normal"}
    assert tick_payload["bf3d_snapshot"] is unavailable_snapshot
    assert "source" in tick_payload and "replay" in tick_payload


def test_cohesive_zone_history_window_cannot_be_shorter_than_model_windows():
    assert bridge.COHESIVE_ZONE_HISTORY_MINUTES >= 45


@pytest.mark.parametrize(
    ("reason_code", "group", "expected_state"),
    [
        (
            "insufficient_common_body_layers",
            "body_temperature",
            "insufficient",
        ),
        (
            "insufficient_common_eccentric_sectors",
            "body_temperature",
            "insufficient",
        ),
        (
            "stale_pressure_or_permeability",
            "pressure_permeability",
            "stale",
        ),
    ],
)
def test_quality_maps_estimator_reason_codes_to_minimum_group_state(
    reason_code,
    group,
    expected_state,
):
    evaluation_time = datetime.now().replace(microsecond=0)
    estimate = {
        "status": "unavailable",
        "reason_codes": [reason_code],
        "quality": {
            "coverage_by_group": {
                "body_temperature": 0.5,
                "pressure_permeability": 0.5,
            }
        },
    }

    quality = bridge._cohesive_zone_snapshot_quality(
        frame=pd.DataFrame({"marker": [1.0]}, index=[evaluation_time]),
        estimate=estimate,
        measured={},
        missing=[],
        stale=[],
        warnings=[],
        evaluation_time=evaluation_time,
    )

    assert quality["estimator_minimum_groups"][group]["state"] == expected_state
