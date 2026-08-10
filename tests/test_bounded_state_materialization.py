from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "数据库同步和存取" / "src" / "raw_minute_pipeline.py"
SPEC = importlib.util.spec_from_file_location("raw_minute_pipeline_under_test", MODULE)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def test_bounded_hold_fills_minutes_without_claiming_raw_samples() -> None:
    series = {"tag": {"2026-08-10 10:02:00": 12.5}}
    audits = {"tag": {"2026-08-10 10:02:00": {"quality": "Good"}}}
    output, output_audits, count = pipeline.materialize_bounded_state_minutes(
        series,
        audits,
        hold_minutes_by_tag={"tag": 3},
        seed_by_tag={"tag": (datetime(2026, 8, 10, 9, 59), 10.0)},
        start_time=datetime(2026, 8, 10, 10, 0),
        end_time=datetime(2026, 8, 10, 10, 6),
    )

    assert count == 5
    assert output["tag"]["2026-08-10 10:00:00"] == 10.0
    assert output["tag"]["2026-08-10 10:01:00"] == 10.0
    assert output["tag"]["2026-08-10 10:02:00"] == 12.5
    assert output["tag"]["2026-08-10 10:05:00"] == 12.5
    assert output_audits["tag"]["2026-08-10 10:01:00"]["aggregate"] == "PS_STATE_HOLD"
    assert output_audits["tag"]["2026-08-10 10:01:00"]["coverage_ratio"] == 0.0
    assert output_audits["tag"]["2026-08-10 10:01:00"]["semantic_version"] == "bounded_state_hold_v1"


def test_bounded_hold_stops_after_source_age_limit() -> None:
    output, _, count = pipeline.materialize_bounded_state_minutes(
        {},
        {},
        hold_minutes_by_tag={"tag": 2},
        seed_by_tag={"tag": (datetime(2026, 8, 10, 9, 59), 10.0)},
        start_time=datetime(2026, 8, 10, 10, 0),
        end_time=datetime(2026, 8, 10, 10, 4),
    )

    assert count == 2
    assert set(output["tag"]) == {"2026-08-10 10:00:00", "2026-08-10 10:01:00"}

