from pathlib import Path
import sys
from datetime import datetime


SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

import local_pg_ws_bridge as bridge


def test_blast_energy_is_loaded_as_internal_abc_history_input():
    assert "BlastEnergy" in bridge.ABC_SERVER_ONLY_VARIABLES
    assert "BlastEnergy" in bridge.ABC_HISTORY_VARIABLES
    assert "BlastEnergy" not in bridge.FRONTEND_VARIABLES


def test_abc_fallback_uses_live_values_and_snapshot_quality(monkeypatch):
    monkeypatch.setattr(bridge, "RECOMMENDATION_AUDIT_ENABLED", False)
    row = {
        "id": 501,
        "diagnosis_ts": "2026-08-08 11:25:00+08:00",
        "main_label": "normal",
        "main_score": 70,
        "main_confidence": 0.9,
        "secondary_label": None,
        "secondary_score": 0,
        "secondary_confidence": 0,
        "evidence": [],
        "raw_scores": {"normal": 70},
        "diagnosis_json": {
            "feature_snapshot": {"z60_DP_total": 0.2, "z60_PI": -0.1},
            "data_coverage": {"coverage_ratio": 1.0},
            "source_lag_seconds": 120,
        },
    }
    current_values = {
        "P_top": 255.0,
        "P_top_gas_A": 254.0,
        "P_top_gas_B": 256.0,
        "P_top_gas_C": 255.5,
        "P_top_gas_D": 254.5,
        "DP_total": 183.0,
        "Q_blast": 4100.0,
        "P_blast": 450.0,
        "P_blast_cold": 455.0,
        "T_top_A": 130.0,
        "T_top_B": 135.0,
        "T_top_C": 132.0,
        "T_top_D": 128.0,
        "L": 1.8,
    }

    payload = bridge.diagnosis_snapshot_payload(row, current_values=current_values)
    rules = payload["abc_rule_bundle"]["rules"]

    assert len(rules) == 33
    assert max(float(rule["confidence"]) for rule in rules) > 0
    a1 = next(rule for rule in rules if rule["rule_id"] == "A1")
    assert a1["missing_sensors"] == []
    assert a1["confidence"] > 0


def test_abc_fallback_fails_closed_when_snapshot_coverage_is_zero(monkeypatch):
    monkeypatch.setattr(bridge, "RECOMMENDATION_AUDIT_ENABLED", False)
    row = {
        "diagnosis_ts": "2026-08-08 11:25:00+08:00",
        "main_label": "normal",
        "raw_scores": {"normal": 70},
        "diagnosis_json": {
            "feature_snapshot": {},
            "data_coverage": {"coverage_ratio": 0.0},
            "source_lag_seconds": None,
        },
    }

    payload = bridge.diagnosis_snapshot_payload(row, current_values={"Q_blast": 4100.0})

    assert len(payload["abc_rule_bundle"]["rules"]) == 33
    assert {rule["status"] for rule in payload["abc_rule_bundle"]["rules"]} == {"needs_data"}
    assert all(rule["score"] is None for rule in payload["abc_rule_bundle"]["rules"])


def test_latest_values_uses_each_sensors_recent_non_null_sample(monkeypatch):
    monkeypatch.setattr(bridge, "latest_data_ts", lambda conn: datetime(2026, 8, 8, 12, 23))
    monkeypatch.setattr(
        bridge,
        "fetch_history",
        lambda conn, since: {
            "timestamps": [
                "2026-08-08 12:18:00",
                "2026-08-08 12:21:00",
                "2026-08-08 12:23:00",
            ],
            "DP_total": [180.0, 183.0, None],
            "P_blast": [None, None, 452.0],
        },
    )

    timestamp, values = bridge.latest_values(object())

    assert timestamp == "2026-08-08 12:23:00"
    assert values["DP_total"] == 183.0
    assert values["P_blast"] == 452.0


def test_latest_values_does_not_carry_stale_samples_forward(monkeypatch):
    monkeypatch.setattr(bridge, "latest_data_ts", lambda conn: datetime(2026, 8, 8, 12, 23))
    monkeypatch.setattr(
        bridge,
        "fetch_history",
        lambda conn, since: {
            "timestamps": ["2026-08-08 12:17:00", "2026-08-08 12:23:00"],
            "DP_total": [180.0, None],
        },
    )

    _, values = bridge.latest_values(object())

    assert values["DP_total"] is None
