from __future__ import annotations

import importlib
import sys
import threading
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
SERVICE = ROOT / "自动诊断服务"
for path in (BACKEND, SERVICE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _ClaimConnection:
    claimed = False

    def execute(self, sql, params=()):
        if "FROM qa_conversation_origins" in sql:
            return _Cursor({"context_snapshot_id": 81})
        if "INSERT INTO abc_rule_ai_explanations" in sql and "RETURNING id" in sql:
            if not type(self).claimed:
                type(self).claimed = True
                return _Cursor({"id": 1})
            return _Cursor(None)
        if "UPDATE abc_rule_ai_explanations" in sql and "RETURNING id" in sql:
            return _Cursor(None)
        if "FROM abc_rule_ai_explanations" in sql:
            return _Cursor(None)
        raise AssertionError(sql)

    def commit(self):
        return None


def test_six_identical_initial_requests_have_one_generation_owner(monkeypatch) -> None:
    module = importlib.import_module("ollama_proxy_server")

    @contextmanager
    def fake_connect():
        yield _ClaimConnection()

    monkeypatch.setattr(module, "db_connect", fake_connect)
    monkeypatch.setattr(module, "_abc_rule_analysis_model_name", lambda: "test-model")
    _ClaimConnection.claimed = False
    module._ABC_RULE_ANALYSIS_INFLIGHT.clear()
    barrier = threading.Barrier(6)
    results = []

    def claim() -> None:
        barrier.wait()
        results.append(module.claim_abc_rule_initial_analysis("conv-1", "operator-1"))

    threads = [threading.Thread(target=claim) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert [item["state"] for item in results].count("owner") == 1
    assert [item["state"] for item in results].count("waiter") == 5
    owner = next(item for item in results if item["state"] == "owner")
    module.finish_abc_rule_initial_analysis(owner)
    assert all(item["event"].is_set() for item in results)
    assert module._ABC_RULE_ANALYSIS_INFLIGHT == {}


class _CacheConnection:
    def __init__(self):
        self.commits = 0

    def execute(self, sql, params=()):
        if "SELECT rule_id" in sql:
            return _Cursor({
                "rule_id": "B4",
                "evaluation_id": 18,
                "context_hash": "abc",
                "operator_explanation_json": "{}",
                "assistant_context_json": "{}",
            })
        if "INSERT INTO abc_rule_ai_explanations" in sql:
            return _Cursor()
        raise AssertionError(sql)

    def commit(self):
        self.commits += 1


def test_completed_analysis_cache_is_committed() -> None:
    module = importlib.import_module("ollama_proxy_server")
    conn = _CacheConnection()
    module.cache_abc_rule_analysis(conn, 81, "解释结果", model_name="test-model")
    assert conn.commits == 1
