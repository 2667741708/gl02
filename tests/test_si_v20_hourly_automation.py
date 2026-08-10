from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_si_v20_hourly_prediction",
        TOOLS / "run_si_v20_hourly_prediction.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hourly_runner_floors_current_hour() -> None:
    runner = _load_runner()
    assert runner.floor_hour(datetime(2026, 8, 9, 20, 47, 59, 123)) == datetime(2026, 8, 9, 20, 0)


def test_hourly_task_registration_contract() -> None:
    source = (TOOLS / "register_22012_si_v20_hourly_task.ps1").read_text(encoding="utf-8")
    assert "SiV20HourlyShadowPrediction" in source
    assert "-RepetitionInterval (New-TimeSpan -Hours 1)" in source
    assert ".AddSeconds(5)" in source
    assert "-UserId 'SYSTEM'" in source
    assert "-MultipleInstances IgnoreNew" in source
    assert "run_22012_si_v20_hourly_prediction.ps1" in source
    assert "Unregister-ScheduledTask" in source
    assert "Stop-Service" not in source
    assert "Restart-Service" not in source


def test_heat_quality_summary_one_minute_contract() -> None:
    source = (TOOLS / "set_22012_heat_quality_sync_1min.ps1").read_text(encoding="utf-8")
    assert "HeatPerformanceQualitySync" in source
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in source
    assert ".AddSeconds(35)" in source
    assert "$policy.InnerText = 'IgnoreNew'" in source
    assert "Export-ScheduledTask" in source
    assert "action_preserved" in source
    assert "principal_preserved" in source
    assert "foreach ($port in @(8093, 8768, 8094, 8770))" in source
    assert "Stop-Service" not in source
    assert "Restart-Service" not in source


def test_hourly_wrapper_uses_local_8093_and_exact_hour() -> None:
    source = (TOOLS / "run_22012_si_v20_hourly_prediction.ps1").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8093" in source
    assert "yyyy-MM-dd HH:00:00" in source
    assert "si_v20_hourly_prediction.log" in source


def test_hourly_outcome_matches_first_real_open_after_request() -> None:
    source = (
        ROOT / "高炉前端数据" / "智能助手" / "backend" / "si_v20_shadow.py"
    ).read_text(encoding="utf-8")
    assert "h.open_ts >= (p.requested_at AT TIME ZONE 'Asia/Shanghai')" in source
    assert "ORDER BY h.open_ts, h.meltno" in source
    assert "LIMIT 1" in source
    assert "first_real_heat_open_after_requested_at" in source


def test_production_hourly_mode_does_not_depend_on_open_browser() -> None:
    page = (ROOT / "高炉前端数据" / "si_v20_workbench.html").read_text(encoding="utf-8")
    script = (ROOT / "高炉前端数据" / "assets" / "bf-si-v20-workbench.js").read_text(encoding="utf-8")
    assert "严格整点预测（独立常开）" in page
    assert "操作者可调的定时趋势预测" in page
    assert "hourlyAuto" not in page
    assert "scheduleHourlyAuto" not in script
