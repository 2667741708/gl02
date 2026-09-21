from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "tools/run_qa_v52_scheduled_background.py"
SPEC = importlib.util.spec_from_file_location("v52_schedule_under_test", SOURCE)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def plan():
    return {
        "schema": "bf.qa.v52-scheduled-retest-plan.v1",
        "application_version": "V52",
        "model_identity": {
            "name": worker.MODEL_NAME,
            "digest": worker.MODEL_DIGEST,
            "approved_digests": [worker.MODEL_DIGEST],
        },
        "authorized_case_count": 822,
        "prior_completed_records": [],
        "approved_live_runtime_delta": worker.APPROVED_LIVE_RUNTIME_DELTA,
        "process_identity": {"port": 8093, "pid": 10212, "create_time": 1790003038.3367703},
        "schedule": {
            "timezone": "Asia/Shanghai",
            "start": "22:30",
            "end": "07:30",
            "poll_seconds": 10,
            "stable_observations": 3,
            "external_user_quiet_seconds": 300,
            "gpu_utilization_max_percent": 5,
            "test_conversation_title_prefix": "回归基线 ",
        },
        "cases": [{"case_id": f"CASE-{index}", "prompt": "合成问题"} for index in range(822)],
    }


@pytest.mark.parametrize(
    ("clock", "expected"),
    [("22:29", False), ("22:30", True), ("23:59", True), ("00:00", True), ("07:29", True), ("07:30", False)],
)
def test_overnight_schedule_boundaries(clock, expected):
    hour, minute = map(int, clock.split(":"))
    now = datetime(2026, 9, 21, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert worker.inside_window(now, "22:30", "07:30") is expected


@pytest.mark.parametrize("change", [
    "version", "digest", "alternate", "count", "duplicate", "uncertain", "timezone", "live_delta",
    "process_identity",
])
def test_plan_fails_closed(change):
    value = plan()
    if change == "version":
        value["application_version"] = "V26"
    elif change == "digest":
        value["model_identity"]["digest"] = "9" * 64
    elif change == "alternate":
        value["model_identity"]["approved_digests"].append("9" * 64)
    elif change == "count":
        value["cases"].pop()
    elif change == "duplicate":
        value["cases"][1]["case_id"] = value["cases"][0]["case_id"]
    elif change == "uncertain":
        value["cases"][0]["case_id"] = "TPL-10C8C8FAF2C694EF"
    elif change == "timezone":
        value["schedule"]["timezone"] = "UTC"
    elif change == "live_delta":
        value["approved_live_runtime_delta"] = {}
    elif change == "process_identity":
        value["process_identity"]["pid"] = 0
    with pytest.raises(ValueError):
        worker.validate_plan(value)


def test_plan_accepts_only_proven_continuation_without_replay():
    value = plan()
    completed = value["cases"].pop(0)
    value["prior_completed_records"] = [{
        "case_id": completed["case_id"],
        "claim_sha256": "a" * 64,
        "result_sha256": "b" * 64,
        "request_count": 1,
        "automatic_retries": 0,
        "http_status": 200,
        "transport_error": False,
        "terminated": True,
        "done": True,
        "proven_complete": True,
    }]
    worker.validate_plan(value)
    value["prior_completed_records"][0]["request_count"] = 2
    with pytest.raises(ValueError):
        worker.validate_plan(value)


def test_gate_waits_for_recent_real_user_before_any_model_check(monkeypatch):
    value = plan()
    now = datetime(2026, 9, 21, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    monkeypatch.setattr(worker, "latest_external_user_epoch", lambda *_: now - 30)
    monkeypatch.setattr(worker, "gpu_utilization_percent", lambda: pytest.fail("GPU check must wait"))
    ready, reason, evidence = worker.gate_status(value, Path("."), now)
    assert not ready and reason == "recent_external_user_activity"
    assert evidence["latest_external_user_age_seconds"] == 30


def test_gate_requires_idle_gpu_and_exact_model(monkeypatch):
    value = plan()
    now = datetime(2026, 9, 21, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
    monkeypatch.setattr(worker, "latest_external_user_epoch", lambda *_: now - 1000)
    monkeypatch.setattr(worker, "gpu_utilization_percent", lambda: 3)
    monkeypatch.setattr(worker, "exact_model_ready", lambda: True)
    assert worker.gate_status(value, Path("."), now)[0]
    monkeypatch.setattr(worker, "gpu_utilization_percent", lambda: 9)
    assert worker.gate_status(value, Path("."), now)[1] == "gpu_busy"


def test_gpu_probe_uses_windows_standard_path_when_path_is_missing(monkeypatch, tmp_path):
    system_root = tmp_path / "Windows"
    executable = system_root / "System32/nvidia-smi.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"placeholder")
    monkeypatch.setenv("SystemRoot", str(system_root))
    monkeypatch.setattr(worker.shutil, "which", lambda *_: None)

    class Result:
        returncode = 0
        stdout = "4\n"

    observed = {}

    def run(command, **_kwargs):
        observed["executable"] = command[0]
        return Result()

    monkeypatch.setattr(worker.subprocess, "run", run)
    assert worker.gpu_utilization_percent() == 4
    assert Path(observed["executable"]) == executable


def test_listener_selection_ignores_unattributed_and_unrelated_listeners():
    class Address:
        port = 8093

    class Connection:
        def __init__(self, pid):
            self.pid = pid
            self.status = "LISTEN"
            self.laddr = Address()

    class Process:
        def __init__(self, pid):
            self.pid = pid

        def cmdline(self):
            return [r"F:\production\server.py"] if self.pid == 10 else [r"C:\other\server.py"]

    class Psutil:
        AccessDenied = RuntimeError
        NoSuchProcess = LookupError

        @staticmethod
        def net_connections(kind):
            assert kind == "tcp"
            return [Connection(None), Connection(10), Connection(11)]

    Psutil.Process = Process
    assert worker.production_listener_process(Psutil, Path(r"F:\production")).pid == 10


def test_process_identity_rejects_service_restart(monkeypatch):
    value = plan()

    class Process:
        pid = value["process_identity"]["pid"] + 1

        @staticmethod
        def create_time():
            return value["process_identity"]["create_time"] + 1

    monkeypatch.setattr(worker, "production_listener_process", lambda *_: Process())
    with pytest.raises(ValueError, match="process identity changed"):
        worker.verify_process_identity(value, Path("."), object())


def test_runtime_hash_requires_three_expected_reads_after_a_mismatch():
    observations = iter(["bad", "expected", "bad", "expected", "expected", "expected"])
    assert worker.runtime_hash_matches(
        Path("runtime.py"), "expected", hash_reader=lambda _path: next(observations), pause=lambda _seconds: None
    )


def test_runtime_hash_rejects_persistent_or_unstable_mismatch():
    observations = iter(["bad", "expected", "bad", "expected", "bad", "expected"])
    assert not worker.runtime_hash_matches(
        Path("runtime.py"), "expected", hash_reader=lambda _path: next(observations), pause=lambda _seconds: None
    )


def test_runtime_hash_accepts_only_an_explicit_alternate():
    assert worker.runtime_hash_matches(
        Path("runtime.py"), {"base", "reviewed"}, hash_reader=lambda _path: "reviewed", pause=lambda _seconds: None
    )
    assert not worker.runtime_hash_matches(
        Path("runtime.py"), {"base", "reviewed"}, hash_reader=lambda _path: "unknown", pause=lambda _seconds: None
    )


def test_summary_never_copies_answers(tmp_path):
    summary_source = Path(__file__).resolve().parents[1] / "tools/summarize_qa_scheduled_retest.py"
    spec = importlib.util.spec_from_file_location("summary_under_test", summary_source)
    summary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summary)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({
        "requirement_id": "REQ", "execution_id": "EXEC",
        "cases": [{"case_id": "CASE-1", "prompt": "private question"}],
    }), encoding="utf-8")
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "CASE-1.claim").write_text("{}", encoding="utf-8")
    (batch / "CASE-1.json").write_text(json.dumps({
        "request_count": 1, "automatic_retries": 0, "http_status": 200,
        "terminated": True, "done": True, "answer": "private answer",
        "model": worker.MODEL_NAME, "program_commit": "a" * 40,
        "final": {"answer_route": "model"},
    }), encoding="utf-8")
    receipt = summary.summarize(plan_path, batch)
    encoded = json.dumps(receipt, ensure_ascii=False)
    assert receipt["transport_gate_passed"]
    assert "private answer" not in encoded and "private question" not in encoded


def test_summary_combines_proven_prior_and_current_transport_evidence(tmp_path):
    summary_source = Path(__file__).resolve().parents[1] / "tools/summarize_qa_scheduled_retest.py"
    spec = importlib.util.spec_from_file_location("continuation_summary_under_test", summary_source)
    summary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summary)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({
        "requirement_id": "REQ",
        "execution_id": "EXEC",
        "authorized_case_count": 2,
        "prior_completed_records": [{
            "case_id": "CASE-0", "claim_sha256": "a" * 64, "result_sha256": "b" * 64,
            "request_count": 1, "automatic_retries": 0, "http_status": 200,
            "transport_error": False, "terminated": True, "done": True, "proven_complete": True,
        }],
        "cases": [{"case_id": "CASE-1", "prompt": "private question"}],
    }), encoding="utf-8")
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "CASE-1.claim").write_text("{}", encoding="utf-8")
    (batch / "CASE-1.json").write_text(json.dumps({
        "request_count": 1, "automatic_retries": 0, "http_status": 200,
        "terminated": True, "done": True, "answer": "private answer",
        "model": worker.MODEL_NAME, "program_commit": "a" * 40,
        "final": {"answer_route": "model"},
    }), encoding="utf-8")
    receipt = summary.summarize(plan_path, batch)
    assert receipt["total"] == receipt["result_count"] == 2
    assert receipt["prior_completed_count"] == receipt["current_plan_total"] == 1
    assert receipt["transport_gate_passed"]
