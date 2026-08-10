from __future__ import annotations

from datetime import date, datetime
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "sync_22012_heat_performance_quality.py"


def load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_heat_quality_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cross_midnight_repair_uses_workdate_and_preserves_raw_reason_codes() -> None:
    module = load_sync_module()
    repaired_open, repaired_close, reasons = module._repair_times_from_workdate({
        "meltno": "2#20260806-090",
        "workdate": date(2026, 8, 6),
        "opentime": datetime(2026, 8, 7, 23, 33),
        "closetime": datetime(2026, 8, 7, 0, 30),
        "tappingtime": -1,
    })

    assert repaired_open == datetime(2026, 8, 6, 23, 33)
    assert repaired_close == datetime(2026, 8, 7, 0, 30)
    assert "opentime_date_rebased_to_workdate" in reasons
    assert "closetime_rollover_next_day" in reasons
    assert "raw_closetime_before_opentime" in reasons
    assert "negative_tappingtime" in reasons


def test_meltno_and_workdate_mismatch_is_structured_instead_of_silently_guessed() -> None:
    module = load_sync_module()
    repaired_open, _, reasons = module._repair_times_from_workdate({
        "meltno": "2#20260806-090",
        "workdate": date(2026, 8, 7),
        "opentime": datetime(2026, 8, 7, 23, 33),
        "closetime": datetime(2026, 8, 8, 0, 30),
        "tappingtime": 57,
    })

    assert repaired_open == datetime(2026, 8, 7, 23, 33)
    assert "meltno_workdate_date_mismatch" in reasons


def test_output_times_are_rebased_for_repaired_and_future_pending_rows() -> None:
    module = load_sync_module()
    rows = [
        {
            "alignment_status": "time_anomaly_repaired",
            "open_ts": datetime(2026, 8, 6, 23, 33),
            "outputs": [{"workdate": datetime(2026, 8, 7, 0, 10), "weight_time": datetime(2026, 8, 7, 23, 50)}],
        },
        {
            "alignment_status": "future_pending",
            "open_ts": datetime(2026, 8, 8, 8, 0),
            "outputs": [{"workdate": datetime(2026, 8, 7, 8, 30), "weight_time": None}],
        },
    ]

    module._repair_output_times(rows)

    assert rows[0]["outputs"][0]["workdate"] == datetime(2026, 8, 7, 0, 10)
    assert rows[0]["outputs"][0]["weight_time"] == datetime(2026, 8, 6, 23, 50)
    assert rows[1]["outputs"][0]["workdate"] == datetime(2026, 8, 8, 8, 30)


def test_repair_scan_contract_is_future_bounded_paginated_and_reports_precise_metrics() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "AND workdate < %s" in source
    assert "LIMIT %s OFFSET %s" in source
    assert '"anomaly_detected"' in source
    assert '"evidence_eligible"' in source
    assert '"skipped_no_evidence"' in source
    assert '"future_workdate_filtered"' in source
    assert '"repair_prepared"' in source
    assert '"repair_truncated"' in source
    assert "build_gap_audit" in source
    assert "LIMIT 500" not in source
    assert "OR h.si_avg IS NULL" in source


def test_local_22012_mirror_recovers_completed_heat_average_without_external_imes() -> None:
    module = load_sync_module()
    now = datetime.now().replace(second=0, microsecond=0)
    open_ts = now.replace(hour=max(now.hour - 2, 0), minute=3)
    close_ts = open_ts.replace(hour=min(open_ts.hour + 1, 23), minute=15)
    work_date = open_ts.date().isoformat()
    heat = module.build_local_mirror_recovery_heat({
        "meltno": f"2#{open_ts:%Y%m%d}-110",
        "work_date": open_ts.date(),
        "mirrored_at": now,
        "output_json": {
            "meltNo": f"2#{open_ts:%Y%m%d}-110",
            "workDate": work_date,
            "openTime": open_ts.isoformat(sep=" "),
            "closeTime": close_ts.isoformat(sep=" "),
            "tappingTime": "72.00",
            "workClass": "乙班",
        },
        "lab_json": {
            "value_01": "4.88", "value_02": "0.41", "value_03": "0.29",
            "value_04": "0.168", "value_05": "0.016",
        },
    })

    assert heat is not None
    assert heat["alignment_status"] == "local_imes_mirror_recovered"
    assert heat["open_ts"] == open_ts
    assert heat["hot_metal_samples"][0]["Si"] == "0.41"
    assert heat["hot_metal_samples"][0]["sample_kind"] == "per_heat_average_not_original_sample"


def test_local_mirror_meltno_workdate_conflict_is_quarantined() -> None:
    module = load_sync_module()
    heat = module.build_local_mirror_recovery_heat({
        "meltno": "2#20260806-090",
        "work_date": date(2026, 8, 7),
        "mirrored_at": datetime(2026, 8, 7, 8, 0),
        "output_json": {
            "meltNo": "2#20260806-090",
            "workDate": "2026-08-07",
            "openTime": "2026-08-07 00:10:00",
            "closeTime": "2026-08-07 01:00:00",
        },
        "lab_json": {"value_02": "0.31"},
    })

    assert heat is not None
    assert heat["alignment_status"] == "future_pending"
    assert heat["future_pending"] is True
    assert "meltno_workdate_date_mismatch" in heat["time_anomaly_reasons"]


def test_local_mirror_repairs_stale_summary_even_when_source_is_now_correct() -> None:
    module = load_sync_module()
    mirrored_at = datetime(2026, 8, 9, 18, 40)
    heat = module.build_local_mirror_time_repair({
        "meltno": "2#20260806-089",
        "work_date": date(2026, 8, 6),
        "mirrored_at": mirrored_at,
        "existing_work_date": date(2026, 8, 6),
        "existing_open_ts": datetime(2026, 8, 7, 22, 50),
        "existing_close_ts": datetime(2026, 8, 7, 23, 33),
        "output_json": {
            "meltNo": "2#20260806-089",
            "workDate": "2026-08-06",
            "openTime": "2026-08-06 22:50:00",
            "closeTime": "2026-08-06 23:33:00",
            "tappingTime": "43",
        },
    })

    assert heat is not None
    assert heat["open_ts"] == datetime(2026, 8, 6, 22, 50)
    assert heat["close_ts"] == datetime(2026, 8, 6, 23, 33)
    assert heat["alignment_status"] == "time_anomaly_repaired"
    assert heat["repaired_open_ts"] == datetime(2026, 8, 6, 22, 50)
    assert "summary_time_differs_from_imes_mirror" in heat["time_anomaly_reasons"]


def test_summary_lineage_repairs_089_when_mirror_row_has_expired() -> None:
    module = load_sync_module()
    heat = module.build_summary_lineage_repair({
        "meltno": "2#20260806-089",
        "work_date": date(2026, 8, 6),
        "open_ts": datetime(2026, 8, 7, 22, 50),
        "close_ts": datetime(2026, 8, 7, 23, 33),
        "raw_open_ts": datetime(2026, 8, 7, 22, 50),
        "raw_close_ts": datetime(2026, 8, 7, 23, 33),
        "duration_minutes": 43,
        "source_status": "partial",
        "time_anomaly_reasons": [],
        "future_pending": False,
    })

    assert heat is not None
    assert heat["open_ts"] == datetime(2026, 8, 6, 22, 50)
    assert heat["close_ts"] == datetime(2026, 8, 6, 23, 33)
    assert heat["alignment_status"] == "time_anomaly_repaired"
    assert "opentime_date_rebased_to_workdate" in heat["time_anomaly_reasons"]


def test_local_mirror_default_path_rechecks_existing_heats_without_overwriting_samples() -> None:
    sync_source = SCRIPT.read_text(encoding="utf-8")
    store_source = (
        ROOT
        / "高炉前端数据"
        / "智能助手"
        / "backend"
        / "heat_performance_quality.py"
    ).read_text(encoding="utf-8")

    assert "fetch_local_mirror_time_repairs" in sync_source
    assert "store.apply_time_repairs(repair_rows)" in sync_source
    assert "COALESCE(workdate, (row_json->>'workDate')::date) < %s" in sync_source
    method = store_source.split("def apply_time_repairs", 1)[1].split("def list_rows", 1)[0]
    assert "UPDATE {TABLE_NAME}" in method
    assert "sample_details" not in method
    assert "output_details" not in method


def test_scheduled_runner_propagates_python_exit_code_and_writes_run_markers() -> None:
    runner = (ROOT / "tools" / "run_22012_heat_performance_sync.ps1").read_text(
        encoding="utf-8"
    )

    assert "Start-Process" in runner
    assert "$process.ExitCode" in runner
    assert "$root = Split-Path -Parent $PSScriptRoot" in runner
    assert "F:\\高炉" not in runner
    assert "scheduled_sync_start" in runner
    assert "scheduled_sync_end" in runner
    assert "exit $exitCode" in runner
