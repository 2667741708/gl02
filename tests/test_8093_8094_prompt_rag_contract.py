"""Contracts for 8093/8094 fixed Prompt prefix and RAG runtime docs.

OPS-8093-8094-PROMPT-RAG-RUNTIME-20260805
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
RAG = ROOT / "高炉前端数据" / "智能助手" / "backend" / "bf_knowledge_rag.py"
RUNNER_8094 = ROOT / "tools" / "run_22012_8094_preview.ps1"
PROBE = ROOT / "tools" / "probe_8093_8094_prompt_rag_runtime.ps1"
DOC = ROOT / "docs" / "8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md"


def test_fixed_prompt_precedes_dynamic_sections() -> None:
    source = PROXY.read_text(encoding="utf-8")
    template_start = source.index("QA_SYSTEM_PROMPT_TEMPLATE =")
    rules_placeholder = source.index("{project_rules}", template_start)
    furnace_context = source.index("【炉况上下文】", template_start)
    mcp_context = source.index("【数据库查询结果】", template_start)
    knowledge_context = source.index("【知识证据】", template_start)
    assert rules_placeholder < furnace_context < mcp_context < knowledge_context
    assert "project_rules=QA_PROJECT_RULES_BLOCK" in source
    assert "knowledge_context=evidence_pack_text(knowledge_pack)" in source


def test_knowledge_and_mcp_routes_remain_enabled_by_default() -> None:
    source = PROXY.read_text(encoding="utf-8")
    for marker in (
        'BF_QA_MCP_PREFETCH", "1"',
        'BF_QA_MCP_TOOLS", "1"',
        'BF_QA_MCP_TOOL_MODE", "auto"',
        'BF_QA_KNOWLEDGE_ENABLED", "1"',
        'BF_QA_KNOWLEDGE_INTENT_GATE", "1"',
        'BF_QA_KNOWLEDGE_TOP_K", "6"',
        'BF_QA_KNOWLEDGE_SEARCH_MODE", "hybrid"',
        "def qa_should_search_knowledge(",
        "mcp_prefetch = qa_mcp_prefetch(routing_question)",
        "knowledge_pack = qa_search_knowledge(",
        "connection=conn",
        "use_mcp_tools = qa_mcp_should_use_tools(",
    ):
        assert marker in source


def test_knowledge_backend_uses_postgresql_and_supports_both_modes() -> None:
    source = RAG.read_text(encoding="utf-8")
    for marker in (
        "当前运行期固定使用 PostgreSQL bf_assistant.rag_* 表",
        'search_mode in {"keyword", "hybrid"}',
        'search_mode in {"vector", "hybrid"}',
        "top_k: int = 6",
        "FROM rag_chunk",
        "FROM rag_chunk_embedding",
    ):
        assert marker in source


def test_8094_explicitly_uses_keyword_mode() -> None:
    runner = RUNNER_8094.read_text(encoding="utf-8")
    assert '$env:BF_QA_KNOWLEDGE_SEARCH_MODE = "keyword"' in runner
    assert "ollama_proxy_server_8094.py" in runner


def test_read_only_probe_and_document_preserve_runtime_boundary() -> None:
    probe = PROBE.read_text(encoding="utf-8")
    document = DOC.read_text(encoding="utf-8")
    for marker in (
        "system_prompt_template",
        "knowledge_intent_gate",
        "knowledge_search_mode",
        "mcp_prefetch_enabled",
        "keyword_knowledge_http_probe",
        "mode=keyword",
    ):
        assert marker in probe
    for forbidden in ("Restart-Service", "Stop-Service", "Start-Service", "Set-ScheduledTask"):
        assert forbidden not in probe
    for marker in (
        "不是模型内部可直接配置的“注意力分数”",
        "每次正常问答都会构造该模板",
        "知识库**不是每一个问题都检索**",
        "8093 与 8094 当前都显式使用 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`",
        "只做 PostgreSQL 关键词/词法检索",
        "实际监听进程环境均已核对",
        "23885.6",
        "只读关键词知识探针",
    ):
        assert marker in document
