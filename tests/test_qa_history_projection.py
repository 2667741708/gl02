import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据" / "智能助手" / "backend"))
import qa_history_projection as history


def database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE qa_conversations (id TEXT, owner_subject TEXT)")
    conn.execute("CREATE TABLE qa_messages (id INTEGER, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT)")
    conn.executemany("INSERT INTO qa_conversations VALUES (?, ?)", [("a", "owner-a"), ("b", "owner-b")])
    conn.executemany("INSERT INTO qa_messages VALUES (?, ?, ?, ?, ?)", [
        (1, "a", "user", "顶压波动", "2026-09-15"),
        (2, "b", "assistant", "顶压波动：其他用户秘密", "2026-09-15"),
        (3, "a", "assistant", "顶压波动：旧回答", "2026-09-15"),
        (4, "a", "user", "之前有没有问过顶压波动？", "2026-09-16"),
    ])
    return conn


def test_real_sql_scope_excludes_other_owner_and_current_question():
    conn = database()
    result = history.fetch_owned_history(conn, owner="owner-a", before_message_id=4, question="之前有没有问过顶压波动？")
    assert result["count"] == 2
    answer = history.history_outcome(result)["answer"]
    assert "其他用户秘密" not in answer and "之前有没有" not in answer
    assert "旧回答" in answer and "不代表当前" in answer
    conn.close()


def test_absent_owner_never_queries_and_wildcards_are_literal():
    conn = database()
    assert not history.fetch_owned_history(conn, owner="", before_message_id=4, question="顶压")["ok"]
    assert history.fetch_owned_history(conn, owner="owner-a", before_message_id=4, question="%_")["count"] == 0
    assert history.fetch_owned_history(conn, owner="owner-b", before_message_id=4, question="顶压波动")["count"] == 1
    conn.close()


def test_projection_suppresses_raw_json_code_and_authority_claims():
    payload = {"ok": True, "source": {"type": "owner_scoped_qa_history"}, "messages": [
        {"role": "assistant", "excerpt": '{"hidden_context": "secret"}', "created_at": "yesterday"},
        {"role": "assistant", "excerpt": "旧建议\n```python\nprint(1)\n```", "truncated": True},
    ]}
    answer = history.history_outcome(payload)["answer"]
    assert "hidden_context" not in answer and "print(1)" not in answer
    assert "摘录截断" in answer and "正式制度" in answer
    payload["source"]["type"] = "unscoped_mcp_history"
    assert history.history_outcome(payload)["answer_route"] == "history_scope_failed_closed"


def test_keyword_extraction_of_three_real_failures():
    assert history.history_keyword("检索历史问答里关于透气性的回答") == "透气性"
    assert history.history_keyword("最近有没有关于顶压波动的历史问答？") == "顶压波动"
    assert history.history_keyword("之前有没有问过顶压波动？") == "顶压波动"
