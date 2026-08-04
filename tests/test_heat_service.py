from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db_dashboard"))

import heat_service  # noqa: E402


def test_hot_metal_and_slag_attach_to_exact_heat_identity() -> None:
    heats = [
        heat_service._normalize_heat(
            {
                "meltno": "2#20260725-329",
                "workdate": "2026-07-25",
                "opentime": "2026-07-25 18:20:00",
                "closetime": "2026-07-25 20:55:00",
                "tappingtime": "155",
            }
        )
    ]
    heat_service._attach_lab_samples(
        heats,
        [
            {
                "id": 1,
                "sample_no": "22607-329-001",
                "result_ts": "2026-07-25 19:42:11",
                "furnace_no": "2",
                "sivalue": "0.21",
            },
            {
                "id": 2,
                "sample_no": "22607-329-002",
                "result_ts": "2026-07-25 19:50:04",
                "furnace_no": "2",
                "sivalue": "0.19",
            },
            {
                "id": 3,
                "sample_no": "22607-329-003",
                "result_ts": "2026-07-25 20:31:56",
                "furnace_no": "2",
                "sivalue": "0.59",
            }
        ],
        [
            {
                "sampleno": "JL2260725-329-1",
                "meltno": "2#20260725-329",
                "publishtime": "2026-07-25 21:00:00",
                "feo": "9.62",
                "r2": "1.22",
            }
        ],
    )
    assert heats[0]["hot_metal_sample_count"] == 3
    assert heats[0]["latest_hot_metal"]["Si"] == 0.59
    si_summary = heats[0]["hot_metal_si_summary"]
    assert si_summary["sample_count"] == 3
    assert si_summary["valid_count"] == 3
    assert si_summary["min"] == 0.19
    assert si_summary["median"] == 0.21
    assert si_summary["max"] == 0.59
    assert round(si_summary["spread"], 2) == 0.40
    assert heats[0]["slag_sample_count"] == 1
    assert heats[0]["latest_slag"]["R2"] == 1.22
    assert heats[0]["alignment_status"] == "complete"


def test_mismatched_hot_sample_is_not_silently_joined() -> None:
    heats = [
        heat_service._normalize_heat(
            {
                "meltno": "2#20260725-329",
                "opentime": "2026-07-25 18:20:00",
                "closetime": "2026-07-25 20:55:00",
            }
        )
    ]
    heat_service._attach_lab_samples(
        heats,
        [
            {
                "id": 2,
                "sample_no": "22607-328-001",
                "result_ts": "2026-07-25 18:26:47",
                "furnace_no": "2",
                "sivalue": "0.32",
            }
        ],
        [],
    )
    assert heats[0]["hot_metal_sample_count"] == 0
    assert heats[0]["hot_metal_si_summary"]["valid_count"] == 0
    assert heats[0]["alignment_status"] == "missing"


def test_formal_hot_sample_uses_exact_heatno_and_batchno_contract() -> None:
    heats = [
        heat_service._normalize_heat(
            {
                "meltno": "2#20260726-345",
                "opentime": "2026-07-26 20:10:00",
                "closetime": "2026-07-26 22:30:00",
            }
        ),
        heat_service._normalize_heat(
            {
                "meltno": "2#20260726-346",
                "opentime": "2026-07-26 22:40:00",
                "closetime": "2026-07-27 00:50:00",
            }
        ),
    ]
    heat_service._attach_lab_samples(
        heats,
        [
            {
                "id": "formal-1",
                "batchno": "22607-345-001",
                "official_meltno": "2#20260726-345",
                "sample_ts": "2026-07-26 21:00:00",
                "result_ts": "2026-07-26 21:30:00",
                "sivalue": "0.38",
            },
            {
                "id": "not-in-requested-heats",
                "batchno": "22607-999-001",
                "official_meltno": "2#20260726-999",
                "result_ts": "2026-07-26 21:31:00",
                "sivalue": "0.99",
            },
        ],
        [],
    )
    assert heats[0]["hot_metal_sample_count"] == 1
    assert heats[0]["latest_hot_metal"]["official_meltno"] == "2#20260726-345"
    assert heats[0]["latest_hot_metal"]["batchno"] == "22607-345-001"
    assert heats[0]["latest_hot_metal"]["alignment_method"] == "exact_heatno_batchno"
    assert heats[0]["hot_metal_alignment_contract"] == "exact_heatno_batchno"
    assert heats[1]["hot_metal_sample_count"] == 0


def test_hot_metal_si_summary_ignores_missing_results() -> None:
    summary = heat_service.summarize_hot_metal_si(
        [{"Si": 0.31}, {"Si": None}, {"Si": 0.27}, {"Si": 0.42}]
    )
    assert summary["sample_count"] == 4
    assert summary["valid_count"] == 3
    assert summary["min"] == 0.27
    assert summary["median"] == 0.31
    assert summary["max"] == 0.42
    assert round(summary["spread"], 2) == 0.15


def test_sensor_windows_use_open_and_close_anchors() -> None:
    heat = {
        "open_ts": datetime(2026, 7, 25, 18, 20),
        "close_ts": datetime(2026, 7, 25, 20, 55),
    }
    start, end, boundary = heat_service.resolve_sensor_window(
        heat, "pre_tap", 120
    )
    assert start == datetime(2026, 7, 25, 16, 20)
    assert end == datetime(2026, 7, 25, 18, 20)
    assert boundary == "left_closed_right_open"

    start, end, boundary = heat_service.resolve_sensor_window(
        heat, "tapping", 120
    )
    assert start == datetime(2026, 7, 25, 18, 20)
    assert end == datetime(2026, 7, 25, 20, 56)
    assert boundary == "both_closed_source"


def test_sensor_units_keep_pressure_temperature_and_level_distinct() -> None:
    assert heat_service.infer_unit("P_static_upper_A") == "kPa"
    assert heat_service.infer_unit("T_body_L10_A") == "℃"
    assert heat_service.infer_unit("L_north") == "m"
    assert heat_service.infer_unit("GasUtil") == "%"


def test_invalid_negative_heat_duration_is_not_used_in_summary() -> None:
    heat = heat_service._normalize_heat(
        {
            "meltno": "2#20260724-310",
            "opentime": "2026-07-24 10:26:00",
            "closetime": "2026-06-29 12:10:00",
            "tappingtime": "-35896",
        }
    )
    assert heat["close_ts"] is None
    assert heat["duration_minutes"] is None
