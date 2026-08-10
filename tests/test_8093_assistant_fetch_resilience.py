"""Contracts for transient 8093 fetch failures during controlled restarts."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def source() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_read_only_json_requests_retry_but_writes_do_not() -> None:
    text = source()

    assert "OPS-8093-QA-FETCH-RESILIENCE-20260806" in text
    assert "attempts = method === 'GET' ? 3 : 1" in text
    assert "await qaRetryDelay(attempt * 1500)" in text


def test_sse_question_is_never_automatically_reposted() -> None:
    text = source()
    match = re.search(
        r"async function qaServerChatStream\b(?P<body>.*?)\n    function QaTabServerLegacy",
        text,
        flags=re.DOTALL,
    )

    assert match is not None
    body = match.group("body")
    assert body.count("fetch('/api/qa/chat'") == 1
    assert "本次提问不会自动重发" in text
    assert "请约30秒后手动重试" in text


def test_raw_browser_failed_to_fetch_is_not_shown_to_operators() -> None:
    text = source()

    assert "/failed to fetch|networkerror|network request failed|load failed/i" in text
    assert "智能助手服务正在受控重启或暂不可达" in text
