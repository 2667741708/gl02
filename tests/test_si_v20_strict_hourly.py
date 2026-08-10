from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import si_v20_shadow as shadow  # noqa: E402
from si_v20_strict_context import (  # noqa: E402
    _window_stats,
    load_strict_context_model,
)


def test_strict_history_uses_first_available_time_not_business_source_time() -> None:
    cutoff = datetime(2026, 8, 10, 2, 0)
    heats = [
        {
            "meltno": "2#20260810-001",
            "open_ts": datetime(2026, 8, 10, 0, 10),
            "source_updated_at": datetime(2026, 8, 10, 0, 30),
            "si_available_at": datetime(2026, 8, 10, 2, 10),
            "si_availability_confidence": "observed_first_ingest",
            "si_avg": 0.31,
        },
        {
            "meltno": "2#20260810-002",
            "open_ts": datetime(2026, 8, 10, 1, 10),
            "source_updated_at": datetime(2026, 8, 10, 1, 30),
            "si_available_at": datetime(2026, 8, 10, 1, 40),
            "si_availability_confidence": "observed_first_ingest",
            "si_avg": 0.34,
        },
    ]
    features = shadow.build_history_features(
        target_meltno="2#20260810-003",
        target_open_ts=datetime(2026, 8, 10, 3, 0),
        cutoff_ts=cutoff,
        heats=heats,
        strict_availability=True,
    )
    assert features["v20_history__visible_label_count"] == 1.0
    assert features["history_mean__Si_lag_1"] == pytest.approx(0.34)
    assert features["history_mean__Si_lag_2"] is None


def test_strict_sensor_window_includes_exact_slot_and_excludes_after_slot() -> None:
    cutoff = datetime(2026, 8, 10, 2, 0)
    stats = _window_stats(
        [
            (datetime(2026, 8, 10, 1, 59, 59), 10.0),
            (datetime(2026, 8, 10, 2, 0, 0), 20.0),
            (datetime(2026, 8, 10, 2, 0, 0, 1000), 99.0),
        ],
        cutoff_ts=cutoff,
        window_minutes=30,
    )
    assert stats["last"] == pytest.approx(20.0)
    assert stats["max"] == pytest.approx(20.0)


def test_strict_slot_rejects_non_hour_and_future() -> None:
    service = shadow.SiV20ShadowService(store=object())
    current_slot = service._strict_slot()
    assert current_slot.minute == current_slot.second == current_slot.microsecond == 0
    assert current_slot <= datetime.now()
    past_hour = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    assert service._strict_slot(past_hour) == past_hour
    with pytest.raises(ValueError, match="HH:00:00"):
        service._strict_slot(datetime(2026, 8, 10, 2, 0, 5))
    with pytest.raises(ValueError, match="当前时刻之后"):
        service._strict_slot(datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=2))


def test_strict_dispatch_delay_normalizes_server_local_timezone() -> None:
    execution = datetime(2026, 8, 10, 2, 0, 5, tzinfo=timezone(timedelta(hours=8)))
    cutoff = datetime(2026, 8, 10, 2, 0, 0)
    assert shadow._local_elapsed_seconds(execution, cutoff) == pytest.approx(5.0)


def test_strict_dispatch_failure_keeps_slot_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeModel:
        sha256 = "model-sha"

    class FakeStore:
        failed: list[tuple[int, str]] = []
        success: list[int] = []

        def ensure_schema(self) -> None:
            return None

        def ensure_strict_hourly_slots(self, furnace_no: str, slot: datetime) -> int:
            return 1

        def claim_strict_hourly_slots(self, now: datetime, limit: int = 24):
            return [{"slot_id": 7, "schedule_slot_ts": now.replace(minute=0, second=0, microsecond=0), "attempt_count": 2}]

        def get_strict_prediction(self, furnace_no: str, slot_ts: datetime, model_sha256: str):
            return None

        def mark_strict_hourly_failure(self, slot_id: int, error: str) -> None:
            self.failed.append((slot_id, error))

        def mark_strict_hourly_success(self, **kwargs) -> None:
            self.success.append(kwargs["slot_id"])

        def reconcile_strict_hourly_matches(self) -> int:
            return 0

    store = FakeStore()
    service = shadow.SiV20ShadowService(store=store)
    service.status = lambda target_limit=100: {
        "candidate_targets": [{"meltno": "2#20260810-999", "open_ts": (datetime.now() + timedelta(hours=2)).isoformat(sep=" "), "source_type": "test"}],
        "targets": [],
    }
    monkeypatch.setattr(shadow, "_SCHEDULE_SCHEMA_READY", True)
    monkeypatch.setattr(shadow, "load_strict_context_model", lambda: FakeModel())
    monkeypatch.setattr(service, "_predict_row", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("model unavailable")))
    result = service.dispatch_strict_hourly(now=datetime(2026, 8, 10, 2, 0, 5))
    assert result["ok"] is False
    assert store.failed == [(7, "model unavailable")]
    assert store.success == []


def test_portable_full_context_model_contract_is_frozen() -> None:
    model = load_strict_context_model()
    assert model.schema == "bf.si.v20.strict_context_lightgbm.v1"
    assert len(model.feature_columns) == 7549
    assert any(name.startswith("history_mean__Si_lag_1") for name in model.feature_columns)
    assert any(name.startswith("v20_pci__12h_") for name in model.feature_columns)
    assert any(name.startswith("v20_sensor__") for name in model.feature_columns)


def test_schema_api_task_and_ui_keep_strict_hourly_independent() -> None:
    proxy = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    page = (ROOT / "高炉前端数据" / "si_v20_workbench.html").read_text(encoding="utf-8")
    script = (ROOT / "高炉前端数据" / "assets" / "bf-si-v20-workbench.js").read_text(encoding="utf-8")
    task = (ROOT / "tools" / "register_22012_si_v20_strict_hourly_task.ps1").read_text(encoding="utf-8")
    assert "si_v20_strict_hourly_slot" in shadow.TABLE_DDL
    assert "request_mode = 'strict_hourly'" in shadow.TABLE_DDL
    assert "first_open_strictly_after_prediction_completed.v1" in shadow.TABLE_DDL
    assert "Jsonb(_json_safe(value))" in (BACKEND / "si_v20_shadow.py").read_text(encoding="utf-8")
    assert "\"prediction_cutoff_ts\", \"requested_at\", \"requested_by\"" in (BACKEND / "si_v20_shadow.py").read_text(encoding="utf-8")
    assert "prediction.requested_at > prediction.execution_completed_at" in shadow.TABLE_DDL
    assert "/api/si-v20/strict-hourly/status" in proxy
    assert "/api/si-v20/strict-hourly/history" in proxy
    assert "/api/si-v20/strict-hourly/dispatch" in proxy
    assert "SiV20StrictHourlyPrediction" in task
    assert "MultipleInstances IgnoreNew" in task
    assert "C:\\Program Files\\PowerShell\\7\\pwsh.exe" in task
    assert "-Execute 'powershell.exe'" not in task
    assert "严格整点预测（独立常开）" in page
    assert "20260810-hourly-table-r2" in page
    assert "loadStrictHourlyHistory" in script
    assert "/api/si-v20/hourly-table" in proxy
    assert "hourlyTableRows" in page
    assert "loadHourlyTable" in script
    assert "target_meltno:$('#target')" not in script[script.find("strictHourlyPredict"):script.find("function visibleHistory")]


def test_twenty_four_whole_hour_slots_are_exact_and_unique() -> None:
    start = datetime(2026, 8, 9, 0, 0)
    slots = [start + timedelta(hours=index) for index in range(24)]
    assert len(set(slots)) == 24
    assert all(item.minute == item.second == item.microsecond == 0 for item in slots)


def test_strict_get_service_paths_are_domain_read_only() -> None:
    status_source = inspect.getsource(shadow.SiV20ShadowService.strict_hourly_status)
    history_source = inspect.getsource(shadow.SiV20ShadowService.strict_hourly_history)
    for source in (status_source, history_source):
        assert "ensure_schedule_schema_once" not in source
        assert "ensure_strict_hourly_slots" not in source
        assert "reconcile_strict_hourly_matches" not in source


def test_hourly_table_keeps_failed_strict_slot_and_labels_scheduled_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = datetime(2026, 8, 10, 2, 0)

    class FakeStore:
        def strict_schema_ready(self) -> bool:
            return True

        def list_strict_hourly_slots(self, **kwargs):
            return [{
                "slot_id": 1,
                "schedule_slot_ts": slot,
                "slot_status": "failed_retryable",
                "attempt_count": 6,
                "last_error": "timezone mismatch",
            }]

        def list_strict_hourly_outcomes(self, **kwargs):
            return []

        def list_scheduled_outcomes(self, **kwargs):
            return [{
                "prediction_id": 9,
                "request_mode": "scheduled_interval",
                "schedule_slot_ts": slot,
                "prediction_si_mean": 0.33,
                "prediction_p10": 0.28,
                "prediction_p90": 0.38,
                "matched_actual_meltno": "2#20260810-131",
                "matched_actual_open_ts": datetime(2026, 8, 10, 2, 40),
                "matched_actual_close_ts": datetime(2026, 8, 10, 3, 30),
                "actual_si_values": [0.31, 0.35],
                "actual_si_mean": 0.33,
                "absolute_error": 0.0,
                "hit_abs_le_005": True,
            }]

    monkeypatch.setattr(shadow, "_SCHEDULE_SCHEMA_READY", True)
    result = shadow.SiV20ShadowService(store=FakeStore()).hourly_table(
        date_from=slot.date(),
        date_to=slot.date(),
        limit=24,
    )
    assert result["count"] == 1
    row = result["items"][0]
    assert row["prediction_source"] == "scheduled_interval_fallback"
    assert row["strict_slot_status"] == "failed_retryable"
    assert row["actual_si_values"] == [0.31, 0.35]
    assert row["actual_si_mean"] == pytest.approx(0.33)
