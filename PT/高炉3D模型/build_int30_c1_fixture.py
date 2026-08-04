from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STAGE_DIR = ROOT / "PT" / "高炉3D模型" / "work" / "INT_30_20260718_R1"
FIXTURE_DIR = STAGE_DIR / "fixtures"
REPORT_DIR = STAGE_DIR / "reports"
SOURCE_MAPPING = (
    ROOT
    / "高炉前端数据"
    / "智能助手"
    / "mcp"
    / "gl02_static_pressure_points.json"
)
FIXTURE_PATH = FIXTURE_DIR / "int30_c1_hmi_snapshot_20260715_104809.json"
SCHEMA_PATH = FIXTURE_DIR / "int30_c1_fixture_schema.json"
REPORT_PATH = REPORT_DIR / "fixture_validation.json"

SAMPLE_TIME = "2026-07-15T10:48:09+08:00"
SOURCE_IMAGE = (
    r"C:\Users\hmw20\Downloads\_cgi-bin_mmwebwx-bin_webwxgetmsgimg__"
    r"&MsgID=6420780204754585878&skey=@crypt_17bb7b93_"
    r"87e983c19f1baba139bb00570e1a95ad&mmweb_appid=wx_webfilehelper.jpg"
)

PRESSURE_VALUES = {
    "lower": {"A": 371.7, "B": 362.9, "C": 395.9, "D": 409.5, "E": 371.5, "F": 375.7},
    "middle": {"A": 348.5, "B": 334.1, "C": 301.9, "D": 346.8, "E": 339.5, "F": 338.8},
    "upper": {"A": 290.4, "B": 342.9, "C": 311.5, "D": 314.1, "E": 312.6, "F": 314.8},
}

BODY_LAYERS = {
    "L7": 16.860,
    "L8": 18.335,
    "L9": 20.125,
    "L10": 21.860,
    "L11": 23.711,
    "L12": 25.441,
    "L13": 27.171,
    "L14": 28.901,
    "L15": 30.631,
    "L16": 32.361,
}


def canonical_bytes(data: Any) -> bytes:
    return (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_fixture() -> dict[str, Any]:
    source = json.loads(SOURCE_MAPPING.read_text(encoding="utf-8"))
    variables = source["variables"]
    pressure_points: list[dict[str, Any]] = []
    relative_angles = {letter: index * 60.0 for index, letter in enumerate("ABCDEF")}
    for item in sorted(
        variables,
        key=lambda row: (
            {"lower": 0, "middle": 1, "upper": 2}[
                row["variable_name"].split("_")[2]
            ],
            row["position"],
        ),
    ):
        group = item["variable_name"].split("_")[2]
        point = dict(item)
        point.update(
            {
                "sample_time": SAMPLE_TIME,
                "value": PRESSURE_VALUES[group][item["position"]],
                "evidence": "measured",
                "evidence_detail": "measured_hmi_snapshot",
                "derivation": {"type": "raw", "method_id": None, "method_version": None},
                "quality": {
                    "state": "unverified",
                    "reason_codes": ["visual_transcription_unverified"],
                    "input_coverage": 1.0,
                },
                "orientation_status": "blocked_pending_azimuth_confirmation",
                "relative_angle_deg": relative_angles[item["position"]],
                "azimuth_deg": None,
                "not_cfd": True,
            }
        )
        pressure_points.append(point)

    body_points: list[dict[str, Any]] = []
    for layer, height_m in BODY_LAYERS.items():
        for position in "ABCDEFGH":
            body_points.append(
                {
                    "variable_name": f"T_body_{layer}_{position}",
                    "layer_id": layer,
                    "position": position,
                    "height_m": height_m,
                    "blender_z_m": round(height_m - 20.0, 3),
                    "three_y_m": round(height_m - 20.0, 3),
                    "unit": "°C",
                    "value": None,
                    "sample_time": None,
                    "evidence": "measured",
                    "derivation": {"type": "raw", "method_id": None, "method_version": None},
                    "quality": {
                        "state": "missing",
                        "reason_codes": ["missing_pending_snapshot"],
                        "input_coverage": 0.0,
                    },
                    "orientation_status": "relative_order_only",
                }
            )

    stockline = {
        "status": "blocked_pending_field_confirmation",
        "display_enabled": False,
        "deformation_enabled": False,
        "reason_codes": [
            "zero_datum_not_confirmed",
            "positive_direction_not_confirmed",
            "valid_range_not_confirmed",
            "south_north_probe_semantics_conflict",
        ],
        "points": [
            {
                "variable_name": variable,
                "unit": "m",
                "value": None,
                "sample_time": None,
                "evidence": "measured",
                "quality": {"state": "blocked", "reason_codes": ["mapping_gate_closed"]},
                "zero_datum": None,
                "positive_direction": None,
                "valid_range": None,
                "source_probe_count": 1,
            }
            for variable in ("L", "L_south", "L_north")
        ],
    }

    event_contract = {
        "status": "blocked_pending_time_semantics_confirmation",
        "records": [],
        "batch_input_fields": [
            "workdate",
            "workdate2",
            "lot",
            "charge",
            "value_01...value_24",
            "value_sum",
            "mining_batch_sum",
            "coke_charge_sum",
        ],
        "t_ipes_cond_fields": [
            "meltno",
            "sumbatchstart",
            "sumbatchend",
            "sumbatch",
            "opentime",
            "closetime",
            "tappingtime",
        ],
        "t_ipes_out_put_fields": [
            "meltno",
            "ironquan",
            "grossweigh",
            "tareweigh",
            "weighttime",
        ],
        "reason_codes": [
            "workdate_workdate2_semantics_not_confirmed",
            "batch_to_heat_relation_not_confirmed",
            "no_instantaneous_tapping_flow",
        ],
    }

    return {
        "schema_version": "bf3d.int30.fixture.v1",
        "requirement_id": "REQ-BF3D-10STAGE-EXECUTION-20260718",
        "stage": "INT-30_R1",
        "fixture_id": "GL02_HMI_STATIC_PRESSURE_20260715_104809",
        "deterministic_seed": 0,
        "clock": {
            "sample_time": SAMPLE_TIME,
            "timezone": "Asia/Shanghai",
            "replay_time": SAMPLE_TIME,
        },
        "source": {
            "type": "user_supplied_hmi_photo",
            "image_path": SOURCE_IMAGE,
            "mapping_path": str(SOURCE_MAPPING),
            "mapping_requirement": source["requirement"],
        },
        "coordinate_contract": {
            "unit": "m",
            "blender_axis": "Z-up",
            "threejs_axis": "Y-up",
            "height_rule": "axis_value_m = plant_elevation_m - 20.0",
            "static_pressure_azimuth": "relative_only_until_field_confirmation",
        },
        "static_pressure": {
            "status": "fixture_ready",
            "point_count": len(pressure_points),
            "unit": "kPa",
            "points": pressure_points,
            "interpolation_enabled": False,
            "cfd_claim_allowed": False,
        },
        "body_temperature": {
            "status": "mapping_ready_values_missing",
            "point_count": len(body_points),
            "unit": "°C",
            "points": body_points,
            "interpolation_enabled": False,
        },
        "stockline": stockline,
        "events": event_contract,
        "chemistry": {
            "status": "out_of_scope_for_int30_r1_visual_objects",
            "allowed_use": "timeline_result_card_after_heat_and_publish_time_linkage",
            "records": [],
        },
        "safety_contract": {
            "no_cfd_claim": True,
            "no_absolute_static_pressure_azimuth_claim": True,
            "no_stockline_deformation_until_gate_opens": True,
            "no_missing_value_zero_fill": True,
            "no_formal_glb_replacement": True,
        },
        "expected": {
            "static_pressure_count": 18,
            "body_temperature_count": 80,
            "body_temperature_layers": {layer: 8 for layer in BODY_LAYERS},
            "stockline_count": 3,
            "event_record_count": 0,
        },
    }


def build_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "bf3d.int30.fixture.v1",
        "title": "GL02 INT-30 C1 deterministic fixture",
        "type": "object",
        "required": [
            "schema_version",
            "fixture_id",
            "clock",
            "coordinate_contract",
            "static_pressure",
            "body_temperature",
            "stockline",
            "events",
            "safety_contract",
            "expected",
        ],
        "properties": {
            "schema_version": {"const": "bf3d.int30.fixture.v1"},
            "fixture_id": {"type": "string"},
            "static_pressure": {
                "type": "object",
                "required": ["point_count", "points", "cfd_claim_allowed"],
            },
            "body_temperature": {
                "type": "object",
                "required": ["point_count", "points"],
            },
            "stockline": {
                "type": "object",
                "required": ["status", "display_enabled", "points"],
            },
            "events": {"type": "object", "required": ["status", "records"]},
            "safety_contract": {"type": "object"},
        },
        "additionalProperties": True,
    }


def validate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    pressure = fixture["static_pressure"]["points"]
    temperatures = fixture["body_temperature"]["points"]
    pressure_ids = [point["variable_name"] for point in pressure]
    temperature_ids = [point["variable_name"] for point in temperatures]
    layer_counts = {
        layer: sum(point["layer_id"] == layer for point in temperatures)
        for layer in BODY_LAYERS
    }
    assertions = {
        "static_pressure_count_18": len(pressure) == 18,
        "static_pressure_ids_unique": len(set(pressure_ids)) == 18,
        "static_pressure_unit_kpa": all(point["unit"] == "kPa" for point in pressure),
        "static_pressure_values_present": all(
            isinstance(point["value"], (int, float)) for point in pressure
        ),
        "static_pressure_evidence_measured_snapshot": all(
            point["evidence"] == "measured"
            and point["evidence_detail"] == "measured_hmi_snapshot"
            and point["quality"]["state"] == "unverified"
            for point in pressure
        ),
        "static_pressure_azimuth_blocked": all(
            point["azimuth_deg"] is None
            and point["orientation_status"] == "blocked_pending_azimuth_confirmation"
            for point in pressure
        ),
        "body_temperature_count_80": len(temperatures) == 80,
        "body_temperature_ids_unique": len(set(temperature_ids)) == 80,
        "body_temperature_layers_8_each": all(
            count == 8 for count in layer_counts.values()
        ),
        "body_temperature_values_missing_not_zero": all(
            point["value"] is None and point["quality"]["state"] == "missing"
            for point in temperatures
        ),
        "stockline_gate_closed": (
            fixture["stockline"]["status"] == "blocked_pending_field_confirmation"
            and fixture["stockline"]["display_enabled"] is False
            and fixture["stockline"]["deformation_enabled"] is False
        ),
        "stockline_values_missing_not_zero": all(
            point["value"] is None for point in fixture["stockline"]["points"]
        ),
        "events_empty_and_blocked": (
            fixture["events"]["records"] == []
            and fixture["events"]["status"]
            == "blocked_pending_time_semantics_confirmation"
        ),
        "no_cfd_claim": (
            fixture["static_pressure"]["cfd_claim_allowed"] is False
            and fixture["safety_contract"]["no_cfd_claim"] is True
        ),
        "sample_time_iso8601_offset": (
            datetime.fromisoformat(fixture["clock"]["sample_time"]).utcoffset()
            is not None
        ),
        "formal_glb_replacement_forbidden": fixture["safety_contract"][
            "no_formal_glb_replacement"
        ]
        is True,
    }
    canonical = canonical_bytes(fixture)
    return {
        "schema_version": "bf3d.int30.fixture.validation.v1",
        "fixture": str(FIXTURE_PATH),
        "fixture_sha256": sha256_bytes(canonical),
        "canonical_bytes": len(canonical),
        "assertions": assertions,
        "passed": sum(bool(value) for value in assertions.values()),
        "total": len(assertions),
        "status": "pass" if all(assertions.values()) else "fail",
        "counts": {
            "static_pressure": len(pressure),
            "body_temperature": len(temperatures),
            "body_temperature_layers": layer_counts,
            "stockline": len(fixture["stockline"]["points"]),
            "events": len(fixture["events"]["records"]),
        },
    }


def main() -> int:
    fixture = build_fixture()
    schema = build_schema()
    report = validate_fixture(fixture)
    write_json(FIXTURE_PATH, fixture)
    write_json(SCHEMA_PATH, schema)
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
