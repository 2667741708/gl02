"""Contracts for the permanent 8093 assistant repair handbook.

TEST-8093-ASSISTANT-REPAIR-DOC-CONTRACT-20260804
OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805
"""

from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "docs" / "8093智能助手不可用原因与正式修复手册_20260804.docx"
AGENTS = ROOT / "AGENTS.md"
GENERATOR = ROOT / "tools" / "generate_8093_assistant_repair_docx.py"

WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_docx_text() -> str:
    assert DOCX.is_file(), f"DOCX is missing: {DOCX}"
    try:
        with ZipFile(DOCX) as archive:
            assert archive.testzip() is None
            xml = archive.read("word/document.xml")
    except BadZipFile as exc:  # pragma: no cover - assertion carries the cause
        raise AssertionError(f"invalid DOCX: {DOCX}") from exc

    root = ElementTree.fromstring(xml)
    return "".join(node.text or "" for node in root.iter(f"{WORD_NAMESPACE}t"))


def test_docx_records_confirmed_cause_and_historical_failures() -> None:
    text = read_docx_text()
    for marker in (
        "8093 智能助手不可用原因与正式修复手册",
        "不是 27B 模型整体崩溃",
        "健康守卫",
        "切断在途 /api/qa/chat SSE",
        "20:46",
        "20:47",
        "20:51",
        "20:56",
        "20:59",
        "21:15",
        "21:48",
        "restart_service_done",
        "没有发现能解释上述 7 次时间点的模型崩溃堆栈",
    ):
        assert marker in text


def test_docx_records_repair_rationale_and_recurrence_playbook() -> None:
    text = read_docx_text()
    for marker in (
        "health.failureThreshold",
        "health.serviceNotRunningFailureThreshold",
        "health.preRestartBackoffSeconds",
        "health.restartCooldownSeconds",
        "为什么当前方案可行可用",
        "再次出现不可用时的固定处理流程",
        "连续三次失败",
        "15 秒",
        "600 秒",
        "start(preparing/prepared) → delta → final → done",
        "6.5837",
        "23.8856",
        "不得绕过哈希保护",
        "只提交一次真实智能助手短问",
        "BF_QA_KNOWLEDGE_SEARCH_MODE",
        "keyword",
        "固定的不是模型内部 attention score",
        "身份 → 职责与使用原则 → 安全边界",
        "parameter_optimization",
        "命中 2 条词法证据",
        "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE",
        "8093_keyword_knowledge_20260805_20260805_084403",
    ):
        assert marker in text


def test_docx_contains_no_embedded_secret_assignments() -> None:
    text = read_docx_text().lower()
    for forbidden in (
        "password=",
        "passwd=",
        "pgpassword=",
        "authorization: bearer ",
        "api_key=",
        "api-key=",
    ):
        assert forbidden not in text


def test_agents_points_to_docx_and_preserves_decision_boundary() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    for marker in (
        "8093 智能助手再次不可用时的直接修复记录（长期固定）",
        "8093智能助手不可用原因与正式修复手册_20260804.docx",
        "3/1/15/600",
        "若没有守卫重启证据",
        "部署器应拒绝覆盖",
        "当前方案可行的原因固定为五点",
        "只允许做一次新会话短问验收",
        "8093 与 8094 当前都必须显式使用 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`",
        "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE",
        "23.8856s",
    ):
        assert marker in agents
    assert "DEFAULT_OUTPUT" in generator
    assert "The document intentionally contains no passwords" in generator
