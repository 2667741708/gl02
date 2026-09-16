import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "高炉前端数据/智能助手/backend"))
import qa_document_knowledge as doc
import qa_prompt_sources
import qa_task_plan


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE rag_document(doc_id,title,version,authority_level,content_hash,updated_at,full_text)")
    conn.execute("CREATE TABLE rag_chunk(chunk_id,doc_id,title,content,enriched_content,content_hash,authority_level,chunk_type)")
    body = "1. 未确认条件，不得操作。\n设备 | 要求\n阀门 | 确认关闭"
    conn.execute("INSERT INTO rag_document VALUES(?,?,?,?,?,?,?)", (doc.THREE_RULES, "冀钢炼铁三规二制", "v1", "knowledge_doc", digest(body), "2026-09-16", body))
    add_piece(conn, 1, body)
    yield conn
    conn.close()


def add_piece(conn, part, content, *, chapter="高炉工长", regulation="安全操作规程", hash_value=None):
    header = f"【岗位/制度】1. {chapter}\n【规程类型】{regulation}\n【粒度】section\n【原文】\n{content}"
    conn.execute("INSERT INTO rag_chunk VALUES(?,?,?,?,?,?,?,?)", (f"piece{part}", doc.THREE_RULES, f"{chapter} - {regulation} - 第{part}部分", content, header, hash_value or digest(content), "knowledge_doc", "three_rules_section"))


def run(conn, question):
    return doc.execute_document_question(conn, question, qa_task_plan.build_task_plan(question))


def test_preserves_original_prohibitions_and_whole_table(connection):
    result = run(connection, "完整列出高炉工长安全操作规程原文")
    assert "设备 | 要求\n阀门 | 确认关闭" in result["answer"]
    assert "不得操作" in result["answer"]
    assert result["completion"]["terminal_state"] == "completed"
    assert result["knowledge_manifest"][0]["version"] == "v1"


def test_unknown_book_never_falls_back_to_other_sources(connection):
    result = run(connection, "根据《不存在的制度》列出完整条款")
    assert result["completion"]["terminal_state"] == "needs_clarification"
    assert "阀门" not in result["answer"]


def test_history_and_report_cannot_be_authority(connection):
    connection.execute("UPDATE rag_document SET authority_level='qa_history'")
    assert run(connection, "列出高炉工长安全操作规程原文")["completion"]["reason"] == "document_integrity_unverified"


def test_document_hash_drift_blocks_answer(connection):
    connection.execute("UPDATE rag_document SET full_text='已变更但未更新哈希'")
    assert run(connection, "完整列出高炉工长安全操作规程")["completion"]["terminal_state"] == "dependency_blocked"


def test_chunk_hash_drift_blocks_answer(connection):
    connection.execute("UPDATE rag_chunk SET content='禁止条款被修改'")
    assert run(connection, "完整列出高炉工长安全操作规程")["completion"]["reason"] == "section_integrity_unverified"


def test_missing_or_duplicate_parts_do_not_claim_full_text(connection):
    add_piece(connection, 3, "3. 第三部分")
    result = run(connection, "完整列出高炉工长安全操作规程")
    assert result["completion"]["reason"] == "section_parts_not_contiguous"


def test_pagination_preserves_piece_and_marks_partial(connection, monkeypatch):
    monkeypatch.setattr(doc, "PAGE_CHARS", 20)
    add_piece(connection, 2, "设备 | 要求\n风口 | 确认工作状态\n铁口 | 确认排放情况")
    first = run(connection, "完整列出高炉工长安全操作规程原文第1页")
    second = run(connection, "完整列出高炉工长安全操作规程原文第2页")
    assert first["completion"]["terminal_state"] == "partial"
    assert first["completion"]["coverage"]["pages"] == 2
    assert "风口 | 确认工作状态\n铁口 | 确认排放情况" in second["answer"]
    assert "此前页面须分别读取" in second["answer"]


def test_crlf_transport_can_verify_canonical_hash(connection):
    row = connection.execute("SELECT content FROM rag_chunk").fetchone()
    connection.execute("UPDATE rag_chunk SET content=?", (row["content"].replace("\n", "\r\n"),))
    assert run(connection, "完整列出高炉工长安全操作规程")["completion"]["terminal_state"] == "completed"


def test_unknown_chapter_requires_clarification(connection):
    assert run(connection, "完整列出《三规二制》第99章原文")["completion"]["reason"] == "chapter_unknown"


def test_compound_is_not_shortcut_to_document_only(connection):
    assert run(connection, "根据《三规二制》列出条款，同时查询当前顶压") is None


def test_nolive_prompt_keeps_knowledge_and_drops_old_claims():
    messages = qa_prompt_sources.build_source_messages("顶压升高通常有哪些原因？不要查询实时数据。", [{"role": "assistant", "content": "当前风量9999"}], "原文规定不得依据单点认定原因")
    assert "原文规定" in messages[0]["content"]
    assert "当前风量9999" not in str(messages)


def test_user_given_data_does_not_import_knowledge_or_history():
    messages = qa_prompt_sources.build_source_messages("仅根据我提供的这些数：10,20，计算均值", [{"role": "assistant", "content": "真实温度900"}], "无关现场证据")
    assert "无关现场证据" not in str(messages)
    assert "真实温度900" not in str(messages)


def test_abc_initial_keeps_strict_existing_prompt():
    assert qa_prompt_sources.build_source_messages("解释规则", analysis_mode="initial_context_explanation") is None


def test_quoted_title_is_document_reference_not_live_keyword():
    plan = qa_task_plan.build_task_plan("根据《三规二制》解释工长职责，不要查询实时数据。")
    assert plan["intents"] == ["document_knowledge"]
    assert plan["search_knowledge"] is True
    assert plan["allow_prefetch"] is False


def test_quoted_live_terms_do_not_enable_data_tools():
    assert qa_task_plan.build_task_plan("解释《当前炉顶压力》这份文档")["allow_mcp_tools"] is False


def test_mixed_code_and_live_question_keeps_data_evidence_route():
    assert qa_prompt_sources.build_source_messages("查询当前顶压，同时写Python代码") is None
