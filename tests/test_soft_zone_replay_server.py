from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "tools" / "soft_zone_replay_server.py"
FRONTEND_DIR = ROOT / "高炉前端数据" / "soft_zone_replay"


def load_module():
    spec = importlib.util.spec_from_file_location("soft_zone_replay_server", SERVER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeRepository:
    def __init__(self, latest: datetime):
        self.latest = latest

    def latest_timestamp(self) -> datetime:
        return self.latest


def test_request_defaults_to_fast_temperature_only_replay() -> None:
    module = load_module()
    latest = datetime(2026, 8, 8, 12, 0)
    service = module.ReplayService(FakeRepository(latest))

    request = service.resolve_request({})

    assert request.end == latest
    assert request.start == latest - timedelta(hours=6)
    assert request.step_minutes == 5
    assert request.include_cohesive is False


def test_request_can_enable_estimated_cohesive_overlay() -> None:
    module = load_module()
    latest = datetime(2026, 8, 8, 12, 0)
    service = module.ReplayService(FakeRepository(latest))

    request = service.resolve_request(
        {
            "start": ["2026-08-08 10:00:00"],
            "end": ["2026-08-08 12:00:00"],
            "step_minutes": ["2"],
            "include_cohesive": ["true"],
        }
    )

    assert request.step_minutes == 2
    assert request.include_cohesive is True


def test_request_rejects_unbounded_window() -> None:
    module = load_module()
    latest = datetime(2026, 8, 8, 12, 0)
    service = module.ReplayService(FakeRepository(latest))

    with pytest.raises(ValueError, match="最长"):
        service.resolve_request(
            {
                "start": ["2026-08-04 00:00:00"],
                "end": ["2026-08-08 12:00:00"],
            }
        )


def test_downsample_uses_last_past_value_without_backfill() -> None:
    module = load_module()
    index = pd.to_datetime(
        ["2026-08-08 10:00:00", "2026-08-08 10:04:00", "2026-08-08 10:09:00"]
    )
    frame = pd.DataFrame({"T_body_L7_A": [100.0, 104.0, 109.0]}, index=index)

    sampled = module.downsample_frame(
        frame,
        datetime(2026, 8, 8, 10, 0),
        datetime(2026, 8, 8, 10, 10),
        5,
    )

    assert sampled.loc[pd.Timestamp("2026-08-08 10:00:00"), "T_body_L7_A"] == 100.0
    assert sampled.loc[pd.Timestamp("2026-08-08 10:05:00"), "T_body_L7_A"] == 104.0
    assert sampled.loc[pd.Timestamp("2026-08-08 10:10:00"), "T_body_L7_A"] == 109.0


def test_payload_contains_80_temperature_points_and_skips_c2_by_default() -> None:
    module = load_module()
    index = pd.to_datetime(["2026-08-08 10:00:00", "2026-08-08 10:05:00"])
    frame = pd.DataFrame(
        {
            "T_body_L7_A": [100.0, 110.0],
            "T_body_L16_H": [200.0, 210.0],
        },
        index=index,
    )
    metadata = {
        "T_body_L7_A": {"unit": "℃", "description": "L7A"},
        "T_body_L16_H": {"unit": "℃", "description": "L16H"},
    }
    request = module.ReplayRequest(
        start=datetime(2026, 8, 8, 10, 0),
        end=datetime(2026, 8, 8, 10, 5),
        step_minutes=5,
        include_cohesive=False,
    )

    payload = module.build_replay_payload(request, metadata, frame)
    temperatures = [point for point in payload["points"] if point["metric"] == "temperature"]
    pressures = [point for point in payload["points"] if point["metric"] == "pressure"]

    assert payload["ok"] is True
    assert payload["feature_requirement_id"] == "REQ-BODY-TEMP-INFRARED-REPLAY-20260808"
    assert payload["schema_version"] == "gl02.body-temperature-replay.v1"
    assert len(temperatures) == 80
    assert len(pressures) == 18
    assert payload["cohesive_zone"] == []
    assert payload["scales"]["temperature"]["low"] is not None


def test_frontend_exposes_database_replay_and_video_controls() -> None:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    javascript = (FRONTEND_DIR / "soft-zone-replay.js").read_text(encoding="utf-8")
    css = (FRONTEND_DIR / "soft-zone-replay.css").read_text(encoding="utf-8")

    for marker in (
        "炉体温度红外时空回放",
        'id="startInput"',
        'id="endInput"',
        'id="timelineInput"',
        'id="recordButton"',
        'id="loadingState"',
        'id="errorState"',
        'id="emptyState"',
        'id="temperatureTrendCanvas"',
        'id="pressureTrendCanvas"',
        'id="temperatureLayerSelect"',
        'id="pressureBandSelect"',
        'id="rangePrevButton"',
        'id="rangeNextButton"',
        'step="3600"',
    ):
        assert marker in html
    assert "/api/replay" in javascript
    assert "captureStream" in javascript
    assert "MediaRecorder" in javascript
    assert "renderTrendCharts" in javascript
    assert "pressure_band" in javascript
    assert "contextmenu" in javascript
    assert "点位ID" in javascript
    assert "时间戳" in javascript
    assert "SimSun" in css
    assert "overflow-x: hidden" in css
