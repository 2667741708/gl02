"""Exercise accepted production route and visible-output boundaries without services."""
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "高炉前端数据/智能助手/backend"))
import qa_evidence_policy as policy

SOURCE = (ROOT / ".codex_runtime/qa-routing-v9/candidate/ollama_proxy_server.py").read_text(encoding="utf-8")

def test_actual_route_preserves_mixed_live_query():
    tree = ast.parse(SOURCE)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "qa_answer_route")
    scope = {"qa_evidence_policy": policy, "normalize_spoken_question": str, "qa_mcp_variables": lambda q: ["P_top"] if "压力" in q else []}
    for name in ("CODE", "ANALYSIS", "FACT", "GENERAL"):
        scope["QA_ANSWER_ROUTE_" + name] = name
    constants = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith("QA_ANSWER_ROUTE_") for t in n.targets)]
    for const in constants:
        exec(compile(ast.Module(body=[const], type_ignores=[]), "route-constant", "exec"), scope)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "production-route", "exec"), scope)
    assert scope["qa_answer_route"]("查询当前炉顶压力，同时生成Python代码示例") != scope["QA_ANSWER_ROUTE_CODE"]
    assert scope["qa_answer_route"]("生成查询当前炉顶压力的Python代码") == scope["QA_ANSWER_ROUTE_CODE"]

def test_residual_stream_checks_boundary_before_first_visible_delta():
    start = SOURCE.index("            stream_completed = False\n")
    end = SOURCE.index("            with db_connect() as conn:\n", start)
    block = SOURCE[start:end]
    assert block.count('write_qa_event("delta"') == 1
    assert block.index("apply_request_boundary") < block.index('write_qa_event("delta"')
    assert block.index('if obj.get("done")') < block.index('write_qa_event("delta"')
    assert "tools=" not in block  # No second model turn or automatic replay.

def test_mixed_completion_retains_fact_coverage_and_rejects_code():
    result = {"completion": {"covered_objects": ["炉顶压力"], "complete": True}}
    bounded = policy.boundary_result("查询当前炉顶压力，同时生成Python代码示例", result)
    assert bounded["completion"]["covered_objects"] == ["炉顶压力"]
    assert bounded["completion"]["terminal_state"] == "partial"
    assert bounded["completion"]["policy_limited"]
    assert result["completion"]["complete"]  # Do not mutate saved original result.
