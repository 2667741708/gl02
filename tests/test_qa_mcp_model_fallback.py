from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _module():
    return importlib.import_module("ollama_proxy_server")


def test_model_fallback_disables_tools_and_states_live_data_boundary(monkeypatch) -> None:
    module = _module()
    calls = []

    def fake_call(messages, tools=None, temperature=0.1, max_tokens=900):
        calls.append({"messages": messages, "tools": tools, "max_tokens": max_tokens})
        return {"message": {"content": "实时数据库未核实；可先结合送风与炉身温度趋势复核软熔带变化。"}}

    monkeypatch.setattr(module, "call_ollama_chat_obj", fake_call)
    result = module.qa_mcp_final_fallback(
        [{"role": "user", "content": "检查软熔带是否上升或下降"}],
        reason_code="MCP_PLAN_LIMIT_REACHED",
        reason_message="达到两轮上限",
    )

    assert result["ok"] is True
    assert result["fallback_used"] is True
    assert result["answer_route"] == "model_without_tools_after_mcp_failure"
    assert calls[0]["tools"] is None
    boundary = calls[0]["messages"][-1]["content"]
    assert "不能再请求" in boundary
    assert "实时数据库未核实" in boundary
    assert "不得编造当前数值、趋势、时间戳" in boundary


def test_empty_mcp_failure_gets_one_model_fallback(monkeypatch) -> None:
    module = _module()
    seen = []

    def fake_fallback(messages, *, reason_code, reason_message):
        seen.append((messages, reason_code, reason_message))
        return {"ok": True, "answer": "降级回答", "fallback_used": True}

    monkeypatch.setattr(module, "qa_mcp_final_fallback", fake_fallback)
    result = module.qa_mcp_result_with_fallback(
        {"ok": False, "answer": "", "error": "MCP服务不可用"},
        [{"role": "user", "content": "问题"}],
    )
    assert result["answer"] == "降级回答"
    assert len(seen) == 1
    assert seen[0][1] == "MCP_TOOL_UNAVAILABLE"


def test_successful_tool_answer_does_not_call_fallback(monkeypatch) -> None:
    module = _module()

    def forbidden(*args, **kwargs):
        raise AssertionError("successful tool answer must not trigger fallback")

    monkeypatch.setattr(module, "qa_mcp_final_fallback", forbidden)
    result = module.qa_mcp_result_with_fallback(
        {"ok": True, "answer": "工具已返回事实", "tool_used": True},
        [{"role": "user", "content": "问题"}],
    )
    assert result["answer"] == "工具已返回事实"


def test_legacy_round_limit_text_is_removed() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert "数据库查询轮数超过上限，请缩小问题范围或明确变量名。" not in source
    assert "model_without_tools_after_mcp_failure" in source

