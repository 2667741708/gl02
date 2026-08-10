from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
SPEC = importlib.util.spec_from_file_location("si_v20_shadow_schedule", BACKEND / "si_v20_shadow.py")
assert SPEC and SPEC.loader
si = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(si)


class ScheduleStore:
    def __init__(self) -> None:
        self.configured = None
        self.marked = []
        self.finished = None

    def get_schedule(self, _key):
        return {"schedule_id": 1, "cadence_minutes": 60, "enabled": True}

    def configure_schedule(self, **kwargs):
        self.configured = kwargs
        return {"schedule_id": 1, **kwargs}

    def due_schedules(self, _now):
        return [{"schedule_id": 1, "furnace_no": "2", "cadence_minutes": 10, "next_slot_ts": "2026-08-09 20:10:00"}]

    def mark_schedule_result(self, **kwargs):
        self.marked.append(kwargs)

    def create_schedule_run(self, **_kwargs):
        return {"run_id": 88}

    def finish_schedule_run(self, **kwargs):
        self.finished = kwargs


def test_supported_schedule_cadences_and_slot_alignment() -> None:
    assert [si.validate_cadence_minutes(v) for v in (1, 10, 30, 60, 1440)] == [1, 10, 30, 60, 1440]
    with pytest.raises(ValueError):
        si.validate_cadence_minutes(5)
    assert si.floor_schedule_slot(datetime(2026, 8, 9, 20, 37, 51), 10) == datetime(2026, 8, 9, 20, 30)
    assert si.next_schedule_slot(datetime(2026, 8, 9, 20, 37, 51), 60) == datetime(2026, 8, 9, 21, 0)


def test_schedule_slots_include_both_requested_boundaries() -> None:
    slots = si.schedule_slots(datetime(2026, 8, 9, 20, 0), datetime(2026, 8, 9, 20, 3), 1)
    assert slots == [datetime(2026, 8, 9, 20, minute) for minute in range(4)]


def test_configure_schedule_persists_next_aligned_slot() -> None:
    store = ScheduleStore()
    service = si.SiV20ShadowService(store=store)
    with mock.patch.object(si, "datetime", wraps=datetime) as dt:
        dt.now.return_value = datetime(2026, 8, 9, 20, 37, 12)
        result = service.configure_schedule({"cadence_minutes": 30, "enabled": True}, username="operator")
    assert result["schedule"]["cadence_minutes"] == 30
    assert store.configured["next_slot_ts"] == datetime(2026, 8, 9, 21, 0)
    assert store.configured["actor"] == "operator"


def test_dispatcher_executes_due_slot_and_advances_schedule() -> None:
    store = ScheduleStore()
    service = si.SiV20ShadowService(store=store)
    with mock.patch.object(service, "_scheduled_slot_prediction", return_value={"prediction": {"prediction_id": 7}}):
        result = service.dispatch_due_schedules(now=datetime(2026, 8, 9, 20, 10, 5))
    assert result["ok"] is True
    assert result["due_count"] == 1
    assert store.marked[0]["slot_ts"] == datetime(2026, 8, 9, 20, 10)
    assert store.marked[0]["next_slot_ts"] == datetime(2026, 8, 9, 20, 20)


def test_historical_batch_creates_run_and_one_prediction_per_slot() -> None:
    store = ScheduleStore()
    service = si.SiV20ShadowService(store=store)
    calls = []

    def fake_slot(**kwargs):
        calls.append(kwargs)
        return {"prediction": {"prediction_id": len(calls), "schedule_slot_ts": kwargs["slot_ts"]}}

    with mock.patch.object(service, "_scheduled_slot_prediction", side_effect=fake_slot):
        result = service.scheduled_replay(
            {"start_ts": "2026-08-09 20:00:00", "end_ts": "2026-08-09 20:03:00", "cadence_minutes": 1},
            username="operator",
            role="operator",
        )
    assert result["run_id"] == 88
    assert result["predicted_count"] == 4
    assert all(call["request_mode"] == "scheduled_time_replay" for call in calls)
    assert all(call["schedule_run_id"] == 88 for call in calls)
    assert store.finished["status"] == "completed"


def test_schema_api_ui_and_minute_dispatch_task_contracts() -> None:
    source = (BACKEND / "si_v20_shadow.py").read_text(encoding="utf-8")
    server = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    page = (ROOT / "高炉前端数据" / "si_v20_workbench.html").read_text(encoding="utf-8")
    script = (ROOT / "高炉前端数据" / "assets" / "bf-si-v20-workbench.js").read_text(encoding="utf-8")
    task = (ROOT / "tools" / "register_22012_si_v20_schedule_task.ps1").read_text(encoding="utf-8")
    assert "si_v20_prediction_schedule" in source
    assert "si_v20_prediction_run" in source
    assert "schedule_slot_ts" in source
    for route in ("/api/si-v20/schedule", "/api/si-v20/schedule/configure", "/api/si-v20/schedule/dispatch", "/api/si-v20/scheduled-replay", "/api/si-v20/scheduled-history"):
        assert route in server or route in script
    for label in ("每1分钟", "每10分钟", "每30分钟", "每1小时", "每1天", "按时间粒度批量预测", "预测指定时刻", "查询定时预测曲线"):
        assert label in page
    assert "schedule_slot_ts||item.target_open_ts" in script
    assert "SiV20ScheduledShadowPrediction" in task
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in task
    assert "-MultipleInstances IgnoreNew" in task
