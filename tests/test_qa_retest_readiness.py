import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_qa_failed_retest_once as retest


def test_readiness_get_recovers_without_exposing_payload_or_sending_question(monkeypatch):
    payloads = iter([
        {"ok": False, "proxy_ok": True, "ollama_ok": True, "model_ok": False, "secret": "must not retain"},
        {"ok": True, "proxy_ok": True, "ollama_ok": True, "model_ok": True},
    ])
    calls = []
    def get(url, timeout):
        calls.append(url)
        return io.BytesIO(json.dumps(next(payloads)).encode())
    monkeypatch.setattr(retest, "urlopen", get)
    monkeypatch.setattr(retest.time, "sleep", lambda _: None)
    monkeypatch.setattr(retest, "request_once", lambda *a: (_ for _ in ()).throw(AssertionError("POST forbidden")))
    evidence = []
    assert retest.status_ready("http://example.invalid/status", 6, evidence)
    assert len(calls) == 2 and len(evidence) == 2
    assert "secret" not in json.dumps(evidence)


def test_readiness_stops_after_three_failed_gets(monkeypatch):
    calls = []
    def get(url, timeout):
        calls.append(url)
        raise TimeoutError()
    monkeypatch.setattr(retest, "urlopen", get)
    monkeypatch.setattr(retest.time, "sleep", lambda _: None)
    evidence = []
    assert not retest.status_ready("http://example.invalid/status", 6, evidence)
    assert len(calls) == 3 and all(row["error_type"] == "TimeoutError" for row in evidence)
