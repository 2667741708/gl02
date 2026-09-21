from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "高炉前端数据" / "智能助手" / "backend" / "qa_entity_resolution.py"
SPEC = importlib.util.spec_from_file_location("qa_entity_resolution", MODULE_PATH)
assert SPEC and SPEC.loader
qa_entity_resolution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa_entity_resolution)


def variables(question: str) -> list[str]:
    return qa_entity_resolution.resolve_requested_entities(question)["variables"]


def test_shared_prefix_chemical_list_keeps_every_requested_entity() -> None:
    assert variables("炉顶CO、CO2、H2现在分别是多少？") == ["CO_top", "CO2_top", "H2_top"]


def test_letter_range_expands_all_throat_temperature_points() -> None:
    assert variables("炉喉温度A-D最近半小时温差大不大？") == [
        "T_throat_A", "T_throat_B", "T_throat_C", "T_throat_D"
    ]


def test_paired_stock_rods_preserve_user_order() -> None:
    assert variables("南北探尺现在多少？") == ["L_south", "L_north"]
    assert variables("北、南料线现在多少？") == ["L_north", "L_south"]


def test_two_tapholes_expand_without_inventing_a_third_point() -> None:
    assert variables("俩铁口温度。") == ["T_taphole_1", "T_taphole_2"]


def test_unknown_objects_are_not_converted_to_fake_ids() -> None:
    result = qa_entity_resolution.resolve_requested_entities("东南探尺和X7炉喉温度")
    assert "X7" not in result["variables"]
    assert all(not item.startswith("X7") for item in result["variables"])
