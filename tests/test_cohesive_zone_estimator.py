from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from 炉况规则引擎.features.cohesive_zone_estimator import (
    CohesiveZoneEstimator,
    estimate_cohesive_zone,
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
SECTORS = "ABCDEFGH"


def make_frame(
    *,
    movement: str = "stable",
    hot_sector: str | None = None,
    pressure_step: float = 0.0,
    periods: int = 90,
) -> pd.DataFrame:
    index = pd.date_range("2026-07-19 08:00", periods=periods, freq="min")
    frame = pd.DataFrame(index=index)
    split = periods - 30

    for layer, height in LAYERS.items():
        for sector in SECTORS:
            values = []
            for row in range(periods):
                if row < split:
                    target_height = 18.5
                elif movement == "up":
                    target_height = 25.5
                elif movement == "down":
                    target_height = 17.5
                else:
                    target_height = 18.5
                value = 45.0 + 60.0 * math.exp(
                    -((height - target_height) ** 2) / 7.0
                )
                if hot_sector is not None and sector == hot_sector:
                    value += 18.0
                values.append(value)
            frame[f"T_body_L{layer}_{sector}"] = values

    reference_dp = 170.0
    frame["DP_total"] = reference_dp
    frame.loc[frame.index >= frame.index[split], "DP_total"] = (
        reference_dp + pressure_step
    )
    frame["DP_lower"] = 90.0
    frame["DP_upper"] = 80.0
    frame["PI"] = 20.0
    frame["Q_blast"] = 5200.0
    frame["T_blast"] = 1180.0
    frame["Q_O2"] = 14500.0
    frame["PCI_rate"] = 42.0
    frame["TFT"] = 2150.0
    frame["T_top_A"] = 145.0
    frame["T_top_B"] = 146.0
    frame["T_top_C"] = 144.0
    frame["T_top_D"] = 145.0
    frame["P_top"] = 250.0
    frame["L"] = 1.8
    return frame


@pytest.mark.parametrize(
    ("movement", "expected"),
    [("up", "up"), ("down", "down"), ("stable", "stable")],
)
def test_movement_direction(movement: str, expected: str) -> None:
    result = estimate_cohesive_zone(make_frame(movement=movement))
    assert result["status"] == "available"
    assert result["movement"]["direction"] == expected
    assert abs(result["movement"]["velocity_m_per_h"]) <= 2.4
    if expected == "up":
        assert (
            result["movement"]["forecast_height_m"]
            > result["centerHeight"]
        )
    elif expected == "down":
        assert (
            result["movement"]["forecast_height_m"]
            < result["centerHeight"]
        )
    else:
        assert result["movement"]["forecast_height_m"] == pytest.approx(
            result["centerHeight"]
        )


def test_hot_sector_produces_eccentric_root_towards_sector_a() -> None:
    result = estimate_cohesive_zone(
        make_frame(movement="stable", hot_sector="A")
    )
    assert result["status"] == "available"
    assert result["shape"] == "eccentric"
    assert result["eccentricity"] > 0.1
    assert result["eccentricAngle"] == pytest.approx(0.0, abs=0.2)
    roots = {item["sector"]: item for item in result["sector_roots"]}
    assert roots["A"]["centerHeight"] > roots["E"]["centerHeight"]


def test_higher_pressure_drop_increases_thickness() -> None:
    baseline = estimate_cohesive_zone(make_frame(pressure_step=0.0))
    high_drop = estimate_cohesive_zone(make_frame(pressure_step=35.0))
    assert baseline["status"] == high_drop["status"] == "available"
    assert high_drop["thickness"] > baseline["thickness"]


def test_missing_body_data_returns_explicit_unavailable() -> None:
    frame = make_frame().drop(
        columns=[
            f"T_body_L{layer}_{sector}"
            for layer in (7, 8, 9, 10)
            for sector in SECTORS
        ]
    )
    result = estimate_cohesive_zone(frame)
    assert result["status"] == "unavailable"
    assert "insufficient_current_body_layers" in result["reason_codes"]
    assert result["confidence"] == 0.0
    assert result["control_use"] == "prohibited"
    assert "centerHeight" not in result


def test_stale_body_data_returns_explicit_unavailable() -> None:
    frame = make_frame()
    evaluation_time = frame.index[-1] + pd.Timedelta(minutes=20)
    result = estimate_cohesive_zone(frame, evaluation_time=evaluation_time)
    assert result["status"] == "unavailable"
    assert "stale_body_temperature" in result["reason_codes"]


def test_future_rows_cannot_change_past_estimate() -> None:
    frame = make_frame(periods=120)
    evaluation_time = frame.index[89]
    past = frame.loc[frame.index <= evaluation_time].copy()
    future_modified = frame.copy()
    future_mask = future_modified.index > evaluation_time
    for layer in LAYERS:
        for sector in SECTORS:
            future_modified.loc[
                future_mask, f"T_body_L{layer}_{sector}"
            ] = 599.0 if layer == 13 else -19.0
    future_modified.loc[future_mask, "DP_total"] = 399.0

    expected = estimate_cohesive_zone(past, evaluation_time=evaluation_time)
    actual = estimate_cohesive_zone(
        future_modified, evaluation_time=evaluation_time
    )
    assert actual == expected


def test_result_is_json_serialisable_and_confidence_is_capped() -> None:
    result = estimate_cohesive_zone(
        make_frame(movement="up", hot_sector="C", pressure_step=25.0)
    )
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["status"] == "available"
    assert decoded["evidence"] == "estimated"
    assert decoded["calibration_status"] == "uncalibrated"
    assert decoded["root_definition"] == "wall_thermal_activity_centroid"
    assert decoded["azimuth_reference"] == "sensor_relative_A_zero"
    assert decoded["absolute_azimuth_status"] == "unconfirmed"
    assert decoded["control_use"] == "prohibited"
    assert decoded["confidence"] <= 0.45
    assert len(decoded["sector_roots"]) == 8
    assert decoded["movement"]["forecast_horizon_minutes"] == 15
    assert (
        decoded["movement"]["forecast_assumption"]
        == "constant_velocity_uncalibrated"
    )


def test_forecast_height_is_clamped_to_geometry_bounds() -> None:
    estimator = CohesiveZoneEstimator()
    estimator.config["geometry"]["center_height_max"] = 22.0
    result = estimator.estimate(make_frame(movement="up"))
    assert result["status"] == "available"
    assert result["movement"]["direction"] == "up"
    assert result["centerHeight"] <= 22.0
    assert result["movement"]["forecast_height_m"] == pytest.approx(22.0)


def test_movement_requires_five_common_layers() -> None:
    frame = make_frame()
    current_mask = frame.index >= frame.index[-16]
    reference_mask = (frame.index >= frame.index[-46]) & (
        frame.index <= frame.index[-31]
    )
    for layer in (7, 8):
        frame.loc[
            current_mask,
            [f"T_body_L{layer}_{sector}" for sector in SECTORS],
        ] = float("nan")
    for layer in (12, 13):
        frame.loc[
            reference_mask,
            [f"T_body_L{layer}_{sector}" for sector in SECTORS],
        ] = float("nan")

    result = estimate_cohesive_zone(frame)
    assert result["status"] == "unavailable"
    assert "insufficient_common_body_layers" in result["reason_codes"]
    assert len(result["quality"]["current_body_layers"]) == 5
    assert len(result["quality"]["reference_body_layers"]) == 5
    assert len(result["quality"]["body_temporal_support"]["shared_layers"]) == 3


def test_movement_uses_common_layer_sector_support() -> None:
    frame = make_frame()
    current_mask = frame.index >= frame.index[-16]
    reference_mask = (frame.index >= frame.index[-46]) & (
        frame.index <= frame.index[-31]
    )
    for layer in LAYERS:
        frame.loc[
            current_mask,
            [f"T_body_L{layer}_{sector}" for sector in "EFGH"],
        ] = float("nan")
        frame.loc[
            reference_mask,
            [f"T_body_L{layer}_{sector}" for sector in "ABCD"],
        ] = float("nan")

    result = estimate_cohesive_zone(frame)
    assert result["status"] == "unavailable"
    assert "insufficient_common_body_layers" in result["reason_codes"]
    support = result["quality"]["body_temporal_support"]
    assert support["shared_layers"] == []
    assert support["coverage"] == 0.0


def test_unbalanced_missing_sectors_do_not_create_false_eccentricity() -> None:
    frame = make_frame()
    current_mask = frame.index >= frame.index[-16]
    for layer in (7, 8, 9):
        frame.loc[current_mask, f"T_body_L{layer}_H"] = float("nan")
    for layer in (10, 11, 12, 13):
        frame.loc[current_mask, f"T_body_L{layer}_G"] = float("nan")

    full_result = estimate_cohesive_zone(make_frame())
    result = estimate_cohesive_zone(frame)
    assert result["status"] == "available"
    assert result["eccentricity"] == pytest.approx(0.0, abs=1e-9)
    support = result["quality"]["body_sector_support"]
    assert support["shared_sectors"] == list("ABCDEF")
    assert support["balanced_coverage"] == pytest.approx(0.75)
    assert result["confidence"] < full_result["confidence"]


def test_static_pressure_residuals_use_balanced_elevation_support() -> None:
    frame = make_frame()
    current_mask = frame.index >= frame.index[-16]
    level_values = {"lower": 390.0, "middle": 340.0, "upper": 300.0}
    for level, base_value in level_values.items():
        for sector in "ABCDEF":
            frame[f"P_static_{level}_{sector}"] = base_value
    frame.loc[current_mask, "P_static_lower_F"] = float("nan")
    frame.loc[current_mask, "P_static_middle_E"] = float("nan")

    result = estimate_cohesive_zone(frame)
    assert result["status"] == "available"
    assert result["eccentricity"] == pytest.approx(0.0, abs=1e-9)
    support = result["quality"]["static_pressure_sector_support"]
    assert support["shared_sectors"] == list("ABCD")


def test_stale_pressure_returns_unavailable_with_group_timestamps() -> None:
    frame = make_frame()
    stale_mask = frame.index > frame.index[-7]
    for column in ("DP_total", "DP_lower", "DP_upper", "PI"):
        frame.loc[stale_mask, column] = float("nan")

    result = estimate_cohesive_zone(frame)
    assert result["status"] == "unavailable"
    assert "stale_pressure_or_permeability" in result["reason_codes"]
    latest = result["quality"]["latest_time_by_group"]
    assert set(latest) == {
        "body_temperature",
        "pressure_permeability",
        "thermal_forcing",
        "top_distribution",
        "burden_descent",
    }
    assert latest["pressure_permeability"] < latest["body_temperature"]


def test_one_static_pressure_elevation_is_not_a_pressure_concept() -> None:
    frame = make_frame().drop(
        columns=["DP_total", "DP_lower", "DP_upper", "PI"]
    )
    for sector in "ABCDEF":
        frame[f"P_static_lower_{sector}"] = 390.0

    result = estimate_cohesive_zone(frame)
    assert result["status"] == "unavailable"
    assert (
        "insufficient_pressure_or_permeability_data"
        in result["reason_codes"]
    )


def test_o2_rate_is_a_unit_specific_thermal_fallback() -> None:
    flat = make_frame().drop(columns=["Q_O2"])
    rising = flat.copy()
    flat["O2_rate"] = 3.0
    rising["O2_rate"] = 3.0
    rising.loc[rising.index >= rising.index[-30], "O2_rate"] = 5.0

    flat_result = estimate_cohesive_zone(flat)
    rising_result = estimate_cohesive_zone(rising)
    assert rising_result["status"] == "available"
    assert rising_result["centerHeight"] > flat_result["centerHeight"]
    oxygen_driver = next(
        driver
        for driver in rising_result["quality"]["drivers"]
        if driver["group"] == "O2_rate"
    )
    assert oxygen_driver["source"] == "O2_rate"
    assert oxygen_driver["normalised_contribution"] > 0


def test_context_only_groups_do_not_increase_model_confidence() -> None:
    with_context = make_frame()
    without_context = with_context.drop(
        columns=[
            "T_top_A",
            "T_top_B",
            "T_top_C",
            "T_top_D",
            "P_top",
            "L",
        ]
    )
    full_result = estimate_cohesive_zone(with_context)
    reduced_result = estimate_cohesive_zone(without_context)
    assert full_result["status"] == reduced_result["status"] == "available"
    assert full_result["input_coverage"] == reduced_result["input_coverage"]
    assert full_result["confidence"] == reduced_result["confidence"]
    assert full_result["context_coverage"] > reduced_result["context_coverage"]


def test_stale_thermal_driver_is_ignored_without_false_movement() -> None:
    frame = make_frame(movement="stable")
    current_start = frame.index[-1] - pd.Timedelta(minutes=15)
    stale_cutoff = frame.index[-1] - pd.Timedelta(minutes=6)
    frame.loc[
        (frame.index >= current_start) & (frame.index <= stale_cutoff),
        "Q_blast",
    ] = 6200.0
    frame.loc[frame.index > stale_cutoff, "Q_blast"] = float("nan")

    result = estimate_cohesive_zone(frame)

    assert result["status"] == "available"
    assert result["movement"]["direction"] == "stable"
    assert result["quality"]["latent_indices"]["thermal_forcing_index"] == 0.0
    assert all(
        driver["group"] != "Q_blast"
        for driver in result["quality"]["drivers"]
    )


def test_fresh_thermal_driver_records_own_sample_times() -> None:
    frame = make_frame(movement="stable")
    frame.loc[frame.index >= frame.index[-16], "Q_blast"] = 5700.0

    result = estimate_cohesive_zone(frame)

    driver = next(
        item
        for item in result["quality"]["drivers"]
        if item["group"] == "Q_blast"
    )
    assert driver["sample_time"] == frame.index[-1].isoformat()
    assert driver["reference_sample_time"] is not None
