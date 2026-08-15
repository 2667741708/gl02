from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
REMOVED_THROAT_IDS = {
    "T_throat_A",
    "T_throat_B",
    "T_throat_C",
    "T_throat_D",
}


def _source_html() -> str:
    return SOURCE_HTML.read_text(encoding="utf-8")


def _foreman_core_ids(html: str) -> list[str]:
    match = re.search(r"const FOREMAN_CORE_IDS = (\[[^;]+\]);", html)
    assert match, "FOREMAN_CORE_IDS must remain an explicit auditable list"
    value = ast.literal_eval(match.group(1))
    assert isinstance(value, list)
    return value


def test_diagnosis_core_variables_exclude_four_throat_temperatures() -> None:
    html = _source_html()
    ids = _foreman_core_ids(html)

    assert len(ids) == 32
    assert REMOVED_THROAT_IDS.isdisjoint(ids)
    assert len(ids) == len(set(ids))
    assert "BUG-8093-DIAGNOSIS-REMOVE-THROAT-TEMPERATURES-20260811" in html
    assert 'data-core-variable-contract="no-throat-temperature-20260811"' in html
    assert "data-core-variable-count={ids.length}" in html
    assert "data-core-variable-id={id}" in html


def test_four_point_top_temperatures_remain_core_diagnosis_variables() -> None:
    ids = _foreman_core_ids(_source_html())

    assert {"T_top_A", "T_top_B", "T_top_C", "T_top_D"}.issubset(ids)


def test_throat_points_remain_in_the_general_sensor_catalog() -> None:
    html = _source_html()

    for variable_id in sorted(REMOVED_THROAT_IDS):
        assert f"['{variable_id}'" in html
