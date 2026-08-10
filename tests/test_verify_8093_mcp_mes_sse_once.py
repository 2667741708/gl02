from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "verify_8093_mcp_mes_sse_once.py"
SPEC = importlib.util.spec_from_file_location("verify_8093_mcp_mes_sse_once", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_status_url_uses_remote_chat_host() -> None:
    assert (
        MODULE.status_url_for_chat("http://10.30.220.12:8093/api/qa/chat")
        == "http://10.30.220.12:8093/api/ollama/status"
    )


def test_status_url_rejects_relative_path() -> None:
    with pytest.raises(ValueError):
        MODULE.status_url_for_chat("/api/qa/chat")
