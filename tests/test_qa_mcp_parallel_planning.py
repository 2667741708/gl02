from __future__ import annotations

import asyncio
import importlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _module():
    return importlib.import_module("ollama_proxy_server")


class _FakeSession:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def call_tool(self, name, arguments):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.06)
        self.active -= 1
        return SimpleNamespace(
            structuredContent={
                "ok": True,
                "variable": arguments["variable"],
                "value": arguments["value"],
                "unit": arguments["unit"],
                "data_time": "2026-08-13T09:00:00+08:00",
            }
        )


def _schema():
    return {
        "type": "object",
        "required": ["variable", "value", "unit"],
        "properties": {
            "variable": {"type": "string"},
            "value": {"type": "number"},
            "unit": {"type": "string"},
        },
    }


def _calls():
    return [
        {"name": "gl02__pressure", "arguments": {"variable": "P_top", "value": 231, "unit": "kPa"}},
        {"name": "imes__silicon", "arguments": {"variable": "Si", "value": 0.42, "unit": "%"}},
    ]


def test_default_planning_and_tool_limits_are_five() -> None:
    module = _module()
    assert module.QA_MCP_MAX_TOOL_ROUNDS == 5
    assert module.QA_MCP_MAX_TOOL_CALLS == 5
    assert module.QA_MCP_PARALLEL_TOOL_CALLS is True
    assert module.QA_MCP_MAX_PARALLEL_TOOL_CALLS == 5


def test_planned_calls_overlap_across_servers_and_keep_planner_order(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "qa_mcp_tool_cache_get", lambda *args: None)
    monkeypatch.setattr(module, "qa_mcp_tool_cache_put", lambda *args: None)
    session = _FakeSession()
    started = time.monotonic()
    result = asyncio.run(
        module.qa_mcp_execute_parallel_batch(
            _calls(),
            session=session,
            tool_schemas={"gl02__pressure": _schema(), "imes__silicon": _schema()},
            tool_servers={"gl02__pressure": "gl02-data", "imes__silicon": "imes"},
            policy_limits=module.ToolPolicyLimits(),
            server_locks={},
            tool_timeout_seconds=lambda: 1.0,
            round_number=1,
            planner_catalog_size=2,
        )
    )
    elapsed = time.monotonic() - started

    assert session.max_active == 2
    assert elapsed < 0.11
    assert [item["name"] for item in result] == ["gl02__pressure", "imes__silicon"]
    assert all(item["trace"]["route"] == "model_planner_parallel" for item in result)


def test_planned_calls_are_serial_within_one_stdio_server(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "qa_mcp_tool_cache_get", lambda *args: None)
    monkeypatch.setattr(module, "qa_mcp_tool_cache_put", lambda *args: None)
    session = _FakeSession()
    result = asyncio.run(
        module.qa_mcp_execute_parallel_batch(
            _calls(),
            session=session,
            tool_schemas={"gl02__pressure": _schema(), "imes__silicon": _schema()},
            tool_servers={"gl02__pressure": "shared", "imes__silicon": "shared"},
            policy_limits=module.ToolPolicyLimits(),
            server_locks={},
            tool_timeout_seconds=lambda: 1.0,
            round_number=2,
            planner_catalog_size=2,
        )
    )

    assert session.max_active == 1
    assert len(result) == 2


def test_prompt_requires_parallel_independent_calls_and_relevant_numbers() -> None:
    prompt = _module().QA_MCP_BRIDGE_SYSTEM_PROMPT
    assert "相互独立的只读查询" in prompt
    assert "多个tool_calls并行执行" in prompt
    assert "只挑取与用户问题有关的有效数值" in prompt
    assert "单位、时间戳/时间窗、来源" in prompt

