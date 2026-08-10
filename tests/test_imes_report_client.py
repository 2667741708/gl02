from __future__ import annotations

from datetime import date
from pathlib import Path

import sys


SRC = Path(__file__).resolve().parents[1] / "数据库同步和存取" / "src"
sys.path.insert(0, str(SRC))

from imes_report_client import parse_operation_log_html  # noqa: E402


def test_parse_operation_log_report_preserves_all_cells_and_recomputes_metrics() -> None:
    fixture = Path(__file__).resolve().parents[1] / "logs" / "jn_ts_glbb_tb_query_20260807.html"
    payload = parse_operation_log_html(fixture.read_text(encoding="utf-8"), date(2026, 8, 7))

    assert payload["ok"] is True
    assert payload["dataset"] == "bf2_operation_log_report"
    assert payload["rows_count"] >= 20
    first = payload["rows"][0]
    assert first["report_batch_count"] == 7.0
    assert first["report_coal_ratio"] is not None
    assert first["report_fuel_ratio"] is not None
    assert first["material_rate"] is None
    assert first["material_rate_status"] == "semantic_unconfirmed"
    assert len(first["cells"]) >= 60
    assert first["cells"]["R"]["raw_value"] == "3753.08"


def test_parser_skips_report_subsections_and_uses_stable_row_keys() -> None:
    fixture = Path(__file__).resolve().parents[1] / "logs" / "jn_ts_glbb_tb_query_20260807.html"
    payload = parse_operation_log_html(fixture.read_text(encoding="utf-8"), "2026-08-07")

    rows = payload["rows"]
    assert all(row["report_row_number"] < 34 for row in rows)
    assert len({row["_row_key"] for row in rows}) == len(rows)

