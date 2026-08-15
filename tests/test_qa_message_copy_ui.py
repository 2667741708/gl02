from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def _source() -> str:
    return HTML.read_text(encoding="utf-8")


def _copy_contract(source: str) -> str:
    start = source.index("/* REQ-QA-MESSAGE-COPY-20260814")
    end = source.index("/* OPS-8093-QA-SSE-ROBUST-V1", start)
    return source[start:end]


def test_sent_questions_and_assistant_replies_have_distinct_copy_controls() -> None:
    contract = _copy_contract(_source())
    assert "'.qa-server-msg,.qa-msg'" in contract
    assert "'.qa-server-bubble,.qa-msg-bubble'" in contract
    assert "isUser ? '复制问题' : '复制回复'" in contract
    assert "button.dataset.copyRole = isUser ? 'question' : 'answer'" in contract
    assert "button.setAttribute('aria-label', label)" in contract
    assert "button.title = label" in contract


def test_copy_payload_excludes_metadata_controls_and_hidden_context() -> None:
    contract = _copy_contract(_source())
    assert ".qa-server-time,.qa-msg-time,.qa-message-copy" in contract
    assert "button,script,style,[hidden],[aria-hidden=\"true\"]" in contract
    assert "qaExtractCopyableMessageText(messageElement)" in contract
    assert "clone.innerText || clone.textContent" in contract
    assert "图表：" in contract


def test_only_bounded_same_origin_mcp_chart_urls_are_appended() -> None:
    contract = _copy_contract(_source())
    assert "qaNormalizeMcpImageUrl" in contract
    assert "messageElement.querySelectorAll('img[src]')" in contract
    assert "chartUrls.join('\\n')" in contract
    assert "img.src" not in contract


def test_clipboard_has_secure_api_and_legacy_fallback_with_feedback() -> None:
    contract = _copy_contract(_source())
    assert "navigator.clipboard?.writeText" in contract
    assert "window.isSecureContext" in contract
    assert "document.execCommand('copy')" in contract
    assert "button.textContent = '已复制'" in contract
    assert "button.textContent = '复制失败'" in contract


def test_copy_action_never_calls_or_replays_qa_api() -> None:
    contract = _copy_contract(_source())
    assert "fetch(" not in contract
    assert "qaServerChatStream" not in contract
    assert "/api/qa/chat" not in contract

