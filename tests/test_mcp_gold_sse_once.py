from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_8093_mcp_gold_sse_once.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_mcp_gold_sse_once_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, *, status=200, content_type="application/json", body=b"", headers=(), lines=()):
        self.status = status
        self._content_type = content_type
        self._body = body
        self._headers = list(headers)
        self._lines = iter(lines)

    def read(self, _size=None):
        return self._body

    def getheaders(self):
        return self._headers

    def getheader(self, name):
        return self._content_type if name.lower() == "content-type" else None

    def readline(self):
        return next(self._lines, b"")


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body, headers or {}))

    def getresponse(self):
        return self.response

    def close(self):
        return None


def event(name: str, payload: dict) -> list[bytes]:
    return [f"event: {name}\n".encode(), f"data: {json.dumps(payload)}\n".encode(), b"\n"]


def test_guest_bootstrap_and_exactly_one_mcp_sse_request(monkeypatch) -> None:
    module = load_module()
    bootstrap_response = FakeResponse(
        body=json.dumps(
            {
                "access_mode": "guest_shared",
                "conversation": {"id": "qa_guest_acceptance"},
            }
        ).encode(),
        headers=[("Set-Cookie", "bf_qa_guest=test; Path=/; HttpOnly")],
    )
    lines = []
    lines += event("start", {"stage": "preparing"})
    lines += event("start", {"stage": "prepared", "mcp_tool_calling": True})
    lines += event("tool_start", {"server_id": "gl02-data", "tool": "query_gl02_sensors"})
    lines += event("tool_result", {"ok": True})
    lines += event("delta", {"delta": "综合顶压 220 kPa；数据时间已核实；来源 GL02。"})
    lines += event("final", {"ok": True, "mcp_tool_trace": [{"ok": True}]})
    lines += event("done", {"ok": True})
    sse_response = FakeResponse(content_type="text/event-stream", lines=lines)
    bootstrap_connection = FakeConnection(bootstrap_response)
    sse_connection = FakeConnection(sse_response)
    connections = [bootstrap_connection, sse_connection]
    monkeypatch.setattr(module, "connection_for", lambda _parsed, _timeout: connections.pop(0))

    boot, cookie = module.bootstrap("http://127.0.0.1:8093", 30)
    counters = {"request_count": 0}
    result = module.run_once(
        "http://127.0.0.1:8093",
        module.QUESTION,
        30,
        cookie,
        "qa_guest_acceptance",
        counters,
    )

    assert boot["access_mode"] == "guest_shared"
    assert cookie == "bf_qa_guest=test"
    assert result["tool_start_count"] == 1
    assert result["tool_result_count"] == 1
    assert result["events"].count("done") == 1
    assert counters == {"request_count": 1}
    assert result["model_request_count"] is None
    request_body = json.loads(sse_connection.requests[0][2].decode("utf-8"))
    assert request_body["conversation_id"] == "qa_guest_acceptance"


def test_rejected_chat_is_not_counted_as_a_model_request(monkeypatch) -> None:
    module = load_module()
    rejected = FakeResponse(status=400, body=b'{"error":"conversation_id_required"}')
    connection = FakeConnection(rejected)
    monkeypatch.setattr(module, "connection_for", lambda _parsed, _timeout: connection)
    counters = {"request_count": 0}

    with pytest.raises(RuntimeError, match="SSE HTTP 400"):
        module.run_once(
            "http://127.0.0.1:8093",
            module.QUESTION,
            30,
            "",
            "qa_guest_acceptance",
            counters,
        )

    assert counters == {"request_count": 1}


def test_no_tool_security_acceptance_requires_refusal_terms(monkeypatch) -> None:
    module = load_module()
    lines = []
    lines += event("start", {"stage": "preparing"})
    lines += event("start", {"stage": "prepared", "mcp_tool_calling": True})
    lines += event("delta", {"delta": "拒绝执行；当前仅支持只读。本次未调用任何数据工具。"})
    lines += event("final", {"ok": True, "mcp_tool_trace": []})
    lines += event("done", {"ok": True})
    connection = FakeConnection(FakeResponse(content_type="text/event-stream", lines=lines))
    monkeypatch.setattr(module, "connection_for", lambda _parsed, _timeout: connection)

    result = module.run_once(
        "http://127.0.0.1:8093",
        "拒绝写请求",
        30,
        "",
        "qa_guest_acceptance",
        {"request_count": 0},
        require_tool_events=False,
        required_answer_terms=("拒绝执行", "只读", "本次未调用任何数据工具"),
    )
    assert result["tool_start_count"] == 0
    assert result["tool_result_count"] == 0
