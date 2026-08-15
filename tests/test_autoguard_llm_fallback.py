from __future__ import annotations

import argparse
import sys
import types
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = PROJECT_ROOT / "自动诊断服务"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

_previous_pspace_history = sys.modules.get("pspace_history")
if _previous_pspace_history is None:
    sys.modules["pspace_history"] = types.ModuleType("pspace_history")
import auto_guard_once  # noqa: E402
import llm_short_window_summarizer as summarizer  # noqa: E402
if _previous_pspace_history is None:
    sys.modules.pop("pspace_history", None)


def _queue() -> dict:
    return {
        "queue_id": "dq_test",
        "queue_hash": "hash_test",
        "queue_start_ts": "2026-08-11 08:00:00",
        "queue_end_ts": "2026-08-11 09:00:00",
        "status": "complete",
        "diagnosis_count": 2,
        "expected_count": 2,
        "diagnosis_json": [
            {"diagnosis_ts": "2026-08-11 08:55:00", "main_label": "normal", "main_score": 92},
            {"diagnosis_ts": "2026-08-11 09:00:00", "main_label": "normal", "main_score": 90},
        ],
    }


def test_http_404_uses_structured_fallback_and_persists_degraded_status(monkeypatch) -> None:
    saved_payloads: list[dict] = []

    class FakeStore:
        def __init__(self, _config_path=None) -> None:
            pass

        def ensure_schema(self) -> None:
            pass

        def get_diagnosis_queue(self, _queue_id: str) -> dict:
            return _queue()

        def upsert_short_window_summary(self, payload: dict) -> dict:
            saved_payloads.append(payload)
            return payload

    def raise_404(*_args, **_kwargs) -> str:
        raise HTTPError("http://ollama.invalid/api/chat", 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(summarizer, "DiagnosisStore", FakeStore)
    monkeypatch.setattr(summarizer, "call_ollama", raise_404)

    result = summarizer.summarize(queue_id="dq_test", write=True)

    assert result["ok"] is True
    assert result["degraded"] is True
    assert result["degradation"] == {
        "stage": "llm_summary",
        "reason_code": "ollama_http_error",
        "error_type": "HTTPError",
        "message": "HTTP Error 404: Not Found",
        "http_status": 404,
        "fallback_kind": "deterministic_queue_summary",
    }
    assert saved_payloads[0]["status"] == "degraded"
    assert saved_payloads[0]["prompt_json"]["summary_runtime"]["mode"] == "fallback"
    assert "确定性队列摘要" in saved_payloads[0]["llm_summary"]


def test_guard_cycle_stays_successful_when_only_summary_is_degraded(monkeypatch) -> None:
    finished: list[tuple[str, dict]] = []

    class FakeStore:
        def ensure_schema(self) -> None:
            pass

        def start_run(self, *_args) -> int:
            return 7

        def baseline_meta_for_day(self, *_args, **_kwargs) -> list[dict]:
            return [{"variable": "P_top"}]

        def delete_invalid_diagnosis_snapshots(self, *_args, **_kwargs) -> int:
            return 0

        def delete_diagnosis_snapshots_after(self, *_args) -> int:
            return 0

        def finish_run(self, _run_id: int, status: str, **kwargs) -> None:
            finished.append((status, kwargs))

    class FakeScheduler:
        def __init__(self, _config_path=None) -> None:
            self.store = FakeStore()
            self.diag_cfg = {
                "diagnosis_interval_minutes": 5,
                "baseline_days": 30,
                "window_minutes": 60,
                "repair_invalid_snapshots": True,
                "min_window_coverage_ratio": 0.75,
            }
            self.config = {"zero_value_policy": {"enabled": False}}

        def latest_complete_target(self, wait=True):
            target = datetime(2026, 8, 11, 9, 0)
            return target, {"latest_data_ts": target}

        def find_diagnosis_work_points(self, *_args, **_kwargs):
            return [], {"existing": 12}

    class FakeQualityMonitor:
        def __init__(self, _config_path=None) -> None:
            pass

        def check_all(self, write=True) -> dict:
            return {"ok": True}

    degraded = {
        "stage": "llm_summary",
        "reason_code": "ollama_http_error",
        "error_type": "HTTPError",
        "message": "HTTP Error 404: Not Found",
        "http_status": 404,
        "fallback_kind": "deterministic_queue_summary",
    }
    monkeypatch.setattr(auto_guard_once, "AutoDiagnosisScheduler", FakeScheduler)
    monkeypatch.setattr(auto_guard_once, "DataQualityMonitor", FakeQualityMonitor)
    monkeypatch.setattr(auto_guard_once, "create_tasks_from_quality", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(auto_guard_once, "build_queue", lambda *_args, **_kwargs: _queue())
    monkeypatch.setattr(
        auto_guard_once,
        "summarize",
        lambda *_args, **_kwargs: {"ok": True, "degraded": True, "degradation": degraded, "summary": {}},
    )

    args = argparse.Namespace(
        config="",
        sync_wait_timeout_seconds=None,
        sync_wait_poll_seconds=None,
        dry_run=False,
        since_hours=24.0,
        max_diagnosis_points=288,
        quality_write=True,
        with_llm=True,
        export_docx=False,
        doctor=False,
        skip_zero_audit=True,
        zero_audit_minutes=180,
        zero_audit_limit=1000,
    )
    report = auto_guard_once.run_cycle(args)

    assert report["ok"] is True
    assert report["summary"]["degraded"] is True
    assert report["actions"] == [{"action": "llm_summary_fallback", "status": "degraded", "reason": degraded}]
    assert finished[0][0] == "ok"


def test_guard_cycle_does_not_mask_core_quality_failure(monkeypatch) -> None:
    summary_called = False

    class FakeStore:
        def ensure_schema(self) -> None:
            pass

        def start_run(self, *_args) -> int:
            return 8

        def finish_run(self, _run_id: int, status: str, **_kwargs) -> None:
            assert status == "error"

    class FakeScheduler:
        def __init__(self, _config_path=None) -> None:
            self.store = FakeStore()
            self.diag_cfg = {"diagnosis_interval_minutes": 5, "baseline_days": 30}
            self.config = {"zero_value_policy": {"enabled": False}}

        def latest_complete_target(self, wait=True):
            target = datetime(2026, 8, 11, 9, 0)
            return target, {"latest_data_ts": target}

    class FailingQualityMonitor:
        def __init__(self, _config_path=None) -> None:
            pass

        def check_all(self, write=True) -> dict:
            raise RuntimeError("quality failed")

    def fake_summary(*_args, **_kwargs) -> dict:
        nonlocal summary_called
        summary_called = True
        return {"ok": True}

    monkeypatch.setattr(auto_guard_once, "AutoDiagnosisScheduler", FakeScheduler)
    monkeypatch.setattr(auto_guard_once, "DataQualityMonitor", FailingQualityMonitor)
    monkeypatch.setattr(auto_guard_once, "summarize", fake_summary)
    args = argparse.Namespace(
        config="",
        sync_wait_timeout_seconds=None,
        sync_wait_poll_seconds=None,
        dry_run=False,
        since_hours=24.0,
        max_diagnosis_points=288,
        quality_write=True,
        with_llm=True,
        export_docx=False,
        doctor=False,
        skip_zero_audit=True,
        zero_audit_minutes=180,
        zero_audit_limit=1000,
    )

    report = auto_guard_once.run_cycle(args)

    assert report["ok"] is False
    assert report["error"] == "quality failed"
    assert summary_called is False
