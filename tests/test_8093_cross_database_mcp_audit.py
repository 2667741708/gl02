from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "audit_8093_cross_database_mcp.py"
SPEC = importlib.util.spec_from_file_location("audit_8093_cross_database_mcp", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_status_url_uses_same_production_host() -> None:
    assert (
        MODULE.status_url_for_chat("http://10.30.220.12:8093/api/qa/chat")
        == "http://10.30.220.12:8093/api/ollama/status"
    )


def test_trace_summary_preserves_server_tool_and_source_evidence() -> None:
    result = MODULE.trace_summary(
        [
            {
                "round": 1,
                "route": "model_planner",
                "server_id": "imes-readonly",
                "tool": "imes__query_hot_metal_chemistry_by_heat",
                "result": {"ok": True, "source_objects": ["public.inner_batch_insp_bb"]},
            }
        ]
    )

    assert result[0]["server_id"] == "imes-readonly"
    assert result[0]["tool"] == "imes__query_hot_metal_chemistry_by_heat"
    assert result[0]["source_objects"] == ["public.inner_batch_insp_bb"]
