from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_exception_group_is_flattened_to_leaf_types() -> None:
    module = importlib.import_module("mcp_host.client_manager")
    exc = ExceptionGroup("outer", [TimeoutError("slow"), ExceptionGroup("inner", [ValueError("bad")])])
    diagnostic = module.lifecycle_error("request_handler", exc)
    assert diagnostic["stage"] == "request_handler"
    assert [leaf["type"] for leaf in diagnostic["leaves"]] == ["TimeoutError", "ValueError"]


def test_stdio_teardown_group_becomes_warning_not_request_failure() -> None:
    module = importlib.import_module("mcp_host.client_manager")

    class BrokenStack:
        async def aclose(self):
            raise ExceptionGroup("teardown", [RuntimeError("closed")])

    class Registry:
        pass

    manager = module.McpClientManager(Registry(), "python")
    manager._stack = BrokenStack()
    asyncio.run(manager.__aexit__(None, None, None))
    assert manager.lifecycle_warnings[0]["stage"] == "stdio_teardown"
    assert manager.lifecycle_warnings[0]["leaves"][0]["type"] == "RuntimeError"


def test_request_group_returns_structured_failure_for_single_fallback(monkeypatch) -> None:
    proxy = importlib.import_module("ollama_proxy_server")

    async def broken(*args, **kwargs):
        raise ExceptionGroup("request", [RuntimeError("boom")])

    monkeypatch.setattr(proxy, "qa_mcp_tool_loop_async", broken)
    result = proxy.run_qa_mcp_tool_loop([{"role": "user", "content": "问题"}])
    assert result["ok"] is False
    assert result["error_detail"]["stage"] == "request_handler"
    assert result["error_detail"]["leaves"][0]["type"] == "RuntimeError"
