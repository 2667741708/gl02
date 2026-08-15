from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from tools.run_cohesive_zone_intelligent_diagnosis import main as cli_main
from 炉况规则引擎.features.cohesive_zone_intelligent_diagnosis import (
    diagnose_cohesive_zone_movement,
    estimate_and_diagnose_cohesive_zone,
    load_intelligent_diagnosis_config,
)


LAYERS = {
    7: 16.860,
    8: 18.335,
    9: 20.125,
    10: 21.860,
    11: 23.711,
    12: 25.441,
    13: 27.171,
}


def make_frame(direction: str = "stable", periods: int = 90) -> pd.DataFrame:
    index = pd.date_range("2026-08-10 08:00", periods=periods, freq="min")
    frame = pd.DataFrame(index=index)
    current_start = index[-16]
    for layer, height in LAYERS.items():
        for sector in "ABCDEFGH":
            frame[f"T_body_L{layer}_{sector}"] = [
                55.0 + 35.0 * math.exp(-((height - 20.0) ** 2) / 10.0)
                for _ in index
            ]
    frame["DP_total"] = 170.0
    frame["PI"] = 20.0
    frame["P_blast"] = 330.0
    frame["P_top"] = 250.0
    frame["T_top_A"] = 150.0
    frame["T_top_B"] = 150.0
    frame["T_top_C"] = 150.0
    frame["T_top_D"] = 150.0
    frame["CO2_utilisation"] = 46.0
    frame["CO"] = 23.0
    frame["BurdenSlip"] = 0.10
    frame["burden_descent_rate"] = 1.20
    frame["Si"] = 0.55
    frame["hot_metal_temperature"] = 1500.0
    frame["Fuel_ratio"] = 520.0
    frame["Q_blast"] = 5200.0
    frame["T_blast"] = 1180.0

    current = frame.index >= current_start
    if direction == "up":
        frame.loc[current, "DP_total"] = 200.0
        frame.loc[current, "PI"] = 15.0
        frame.loc[current, "P_blast"] = 350.0
        frame.loc[current, "CO2_utilisation"] = 40.0
        frame.loc[current, "CO"] = 28.0
        frame.loc[current, "BurdenSlip"] = 0.50
        frame.loc[current, "burden_descent_rate"] = 0.60
        frame.loc[current, ["T_top_A", "T_top_B", "T_top_C", "T_top_D"]] = 125.0
        for layer in (11, 12, 13):
            columns = [f"T_body_L{layer}_{sector}" for sector in "ABCDEFGH"]
            frame.loc[current, columns] += 20.0
        alternating = [244.0 if row % 2 else 256.0 for row in range(current.sum())]
        frame.loc[current, "P_top"] = alternating
    elif direction == "down":
        frame.loc[current, "DP_total"] = 145.0
        frame.loc[current, "PI"] = 24.0
        frame.loc[current, "P_blast"] = 310.0
        frame.loc[current, "Si"] = 0.25
        frame.loc[current, "hot_metal_temperature"] = 1460.0
        frame.loc[current, ["T_top_A", "T_top_B", "T_top_C", "T_top_D"]] = 180.0
        for layer in (11, 12, 13):
            columns = [f"T_body_L{layer}_{sector}" for sector in "ABCDEFGH"]
            frame.loc[current, columns] -= 15.0
    return frame


def test_config_keeps_uncalibrated_control_boundary() -> None:
    config = load_intelligent_diagnosis_config()
    assert config["model"]["confidence_cap"] <= 0.45
    assert config["model"]["control_use"] == "prohibited"


@pytest.mark.parametrize("direction", ["up", "stable", "down"])
def test_document_feature_combinations_classify_direction(direction: str) -> None:
    result = diagnose_cohesive_zone_movement(make_frame(direction))
    assert result["status"] == "available"
    assert result["movement"]["direction"] == direction
    assert result["confidence"] <= 0.45
    assert sum(result["movement"]["probabilities"].values()) == pytest.approx(1.0, abs=2e-6)


def test_upward_diagnosis_contains_pressure_temperature_and_risk_evidence() -> None:
    result = diagnose_cohesive_zone_movement(make_frame("up"))
    assert result["trend_vector"]["DP_total"] > 0
    assert result["trend_vector"]["PI"] > 0
    assert result["trend_vector"]["T_top"] > 0
    assert result["trend_vector"]["T_body_upper"] > 0
    assert result["trend_vector"]["P_top_volatility"] > 0
    related = {item["condition"]: item for item in result["related_conditions"]}
    assert related["channel"]["support"] > 0
    assert related["column"]["support"] > 0
    assert result["ml_readiness"]["trained_sequence_model"] is False


def test_downward_diagnosis_links_si_and_iron_temperature_to_cold_condition() -> None:
    result = diagnose_cohesive_zone_movement(make_frame("down"))
    related = {item["condition"]: item for item in result["related_conditions"]}
    assert result["trend_vector"]["Si"] < 0
    assert result["trend_vector"]["hot_metal_temperature"] < 0
    assert related["cold"]["support"] > 0


def test_future_rows_cannot_change_historical_diagnosis() -> None:
    frame = make_frame("up")
    cutoff = frame.index[-1]
    baseline = diagnose_cohesive_zone_movement(frame, evaluation_time=cutoff)
    future = make_frame("down", periods=90).iloc[-20:].copy()
    future.index = pd.date_range(cutoff + pd.Timedelta(minutes=1), periods=20, freq="min")
    combined = pd.concat([frame, future])
    replay = diagnose_cohesive_zone_movement(combined, evaluation_time=cutoff)
    assert replay == baseline


def test_missing_required_temperature_group_is_unavailable() -> None:
    frame = make_frame("up")
    frame = frame.drop(columns=[column for column in frame if column.startswith("T_")])
    result = diagnose_cohesive_zone_movement(frame)
    assert result["status"] == "unavailable"
    assert "insufficient_temperature_field" in result["reason_codes"]


def test_combined_wrapper_preserves_existing_geometry_contract() -> None:
    result = estimate_and_diagnose_cohesive_zone(make_frame("stable"))
    assert result["schema"] == "cohesive_zone_estimate_and_diagnosis.v1"
    assert result["cohesive_zone"]["status"] == "available"
    assert result["cohesive_zone"]["control_use"] == "prohibited"
    assert result["intelligent_diagnosis"]["status"] == "available"
    assert result["direction_consistency"] in {"consistent", "review_required"}


def test_cli_reads_csv_and_writes_utf8_json(tmp_path) -> None:
    source = tmp_path / "cohesive-input.csv"
    output = tmp_path / "cohesive-result.json"
    frame = make_frame("up").rename_axis("timestamp").reset_index()
    frame.to_csv(source, index=False)

    exit_code = cli_main(
        ["--input", str(source), "--output", str(output)]
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert result["status"] == "available"
    assert result["movement"]["direction"] == "up"
