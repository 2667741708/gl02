from __future__ import annotations

from datetime import datetime

from tools.build_hot_metal_si_dataset import (
    build_dictionary_rows,
    classify_quality,
    display_diagnosis_label,
    flatten_json,
    is_good_quality,
    load_static_pressure_dictionary_metadata,
    parse_imes_timestamp,
    parse_numeric,
    value_is_numeric,
)


def test_parse_numeric_rejects_blank_status_and_non_finite_values() -> None:
    assert parse_numeric("0.23") == 0.23
    assert parse_numeric(" 0.23% ") == 0.23
    assert parse_numeric("") is None
    assert parse_numeric("未发布") is None
    assert parse_numeric("NaN") is None


def test_timestamp_and_diagnosis_display_contract() -> None:
    assert parse_imes_timestamp("2026-07-19 17:25:54") == datetime(
        2026, 7, 19, 17, 25, 54
    )
    assert parse_imes_timestamp("") is None
    assert display_diagnosis_label("cold") == "热制度下行"
    assert display_diagnosis_label("hot") == "热制度上行"
    assert display_diagnosis_label("normal") == "正常顺行"


def test_flatten_json_and_numeric_column_detection() -> None:
    assert flatten_json(
        {"a": 1, "nested": {"b": 2}, "items": [1, 2]}, "feature"
    ) == {
        "feature__a": 1,
        "feature__items": "[1,2]",
        "feature__nested__b": 2,
    }
    assert value_is_numeric("1.25")
    assert value_is_numeric(None)
    assert not value_is_numeric("A区")
    assert is_good_quality("Good")
    assert is_good_quality("192")
    assert not is_good_quality("Bad")
    assert classify_quality("") == "unknown"
    assert classify_quality("Good") == "good"
    assert classify_quality("Bad") == "bad"


def test_static_pressure_dictionary_metadata_keeps_semantics_and_uncertainty() -> None:
    metadata = load_static_pressure_dictionary_metadata()

    assert len(metadata) == 18
    assert metadata["P_static_lower_A"]["business_level_name"] == "炉身下部"
    middle_f = metadata["P_static_middle_F"]
    assert middle_f["height_m"] == 23.488
    assert middle_f["position"] == "F"
    assert middle_f["orientation_status"] == "relative_only"
    assert middle_f["source_description_raw"] == (
        "2#高炉本体-23488 高炉炉身下部静压力F"
    )
    assert middle_f["hmi_instrument_id"] == "PE242022F"
    assert middle_f["hmi_instrument_id_status"] == (
        "unconfirmed_conflicting_records"
    )
    assert middle_f["unit"] == "kPa"
    assert middle_f["unit_status"] == (
        "configured_kpa_source_metadata_blank_unconfirmed"
    )


def test_future_dictionary_rows_enrich_static_pressure_without_database() -> None:
    column = "sensor__EQ_SIO_GL02_BT_T0110"
    registry = [
        {
            "variable_name": "P_static_middle_F",
            "chinese_name": "23.49米炉身下部静压力F",
            "branch": "EQ/SI0/GL02/BT",
            "short_name": "EQ_SIO_GL02_BT_T0110",
            "tag_long_name": (
                "\\冀南二期\\EQ\\SI0\\GL02\\BT\\EQ_SIO_GL02_BT_T0110"
            ),
            "description": "2#高炉本体-23488 高炉炉身下部静压力F",
        }
    ]

    dictionary = build_dictionary_rows(
        [{column: 334.4}], [column], registry
    )[0]

    assert dictionary["semantic_id"] == "P_static_middle_F"
    assert dictionary["business_level_name"] == "炉身中部"
    assert dictionary["source_description_raw"] == registry[0]["description"]
    assert dictionary["orientation_status"] == "relative_only"
    assert dictionary["unit"] == "kPa"
