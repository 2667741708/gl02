from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "audit_imes_material_fuel_metrics.py"
SPEC = importlib.util.spec_from_file_location("audit_imes_material_fuel_metrics", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_classify_column_uses_explicit_chinese_comments() -> None:
    assert MODULE.classify_column("value_01", "综合燃料比") == ["fuel_ratio"]
    assert MODULE.classify_column("value_02", "料速") == ["material_speed"]


def test_classify_column_supports_confirmed_english_aliases() -> None:
    assert MODULE.classify_column("fuel_ratio", None) == ["fuel_ratio"]
    assert MODULE.classify_column("cokeRatio", None) == ["coke_ratio"]
    assert MODULE.classify_column("coal_ratio", None) == ["coal_ratio"]


def test_classify_column_does_not_guess_opaque_values() -> None:
    assert MODULE.classify_column("value_17", None) == []


def test_plain_serializes_decimal_without_recursion() -> None:
    assert MODULE.plain(Decimal("123.450")) == "123.450"
