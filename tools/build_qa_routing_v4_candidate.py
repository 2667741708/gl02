"""Build QA routing V4 from the exact accepted V3 production artifacts.

V4 handles entity, temporal and latest-report workflows. It keeps the
accepted V3 files byte-for-byte except for the proxy import/executor seam and
the TaskPlan/entity resolver modules named in the build report.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import shutil
from pathlib import Path


REQ = "REQ-QA-FULL-ISSUE-INVENTORY-20260916"
PROXY_V3_SHA256 = "abd7cc463c42a7e1c707e1b840b33c9040b33cb850ac7719b164732329af6e67"
TASK_PLAN_V3_SHA256 = "bc34986d7a8cb7ff5af11d073809fce623b4cd924865484d5bf98cd9255510e8"
MCP_BASELINE_SHA256 = "35e35f540077e615d5a6213b3a81dbaf875be6d7257d4428ae2b2acb6a6bee31"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one exact match, found {count}")
    return source.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mcp-baseline", required=True, type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    backend = root / "高炉前端数据" / "智能助手" / "backend"
    source_dir = args.v3_candidate.resolve()
    output = args.output.resolve()
    proxy_path = source_dir / "ollama_proxy_server.py"
    task_plan_path = source_dir / "qa_task_plan.py"
    proxy_raw = proxy_path.read_bytes()
    task_plan_raw = task_plan_path.read_bytes()
    if sha256(proxy_raw) != PROXY_V3_SHA256:
        raise ValueError("V3 proxy baseline hash mismatch")
    if sha256(task_plan_raw) != TASK_PLAN_V3_SHA256:
        raise ValueError("V3 TaskPlan baseline hash mismatch")
    mcp_raw = args.mcp_baseline.read_bytes()
    if sha256(mcp_raw) != MCP_BASELINE_SHA256:
        raise ValueError("MCP production baseline hash mismatch")
    mcp_before = mcp_raw.decode("utf-8")
    mcp_after = replace_once(
        mcp_before,
        '    text = candidate.read_text(encoding="utf-8", errors="replace")\n',
        '    text = candidate.read_text(encoding="utf-8", errors="replace")\n    total_chars = len(text)\n',
        "report character count before slicing",
    )
    mcp_after = replace_once(
        mcp_after,
        '        "truncated": len(text) < candidate.stat().st_size,\n',
        '        "total_chars": total_chars,\n        "truncated": len(text) < total_chars,\n',
        "compare report characters with characters",
    )
    ast.parse(mcp_after)

    proxy_before = proxy_raw.decode("utf-8")
    proxy_after = replace_once(
        proxy_before,
        "import qa_evidence_policy\nimport qa_task_plan\nimport qa_registered_accounts",
        "import qa_entity_resolution\nimport qa_time_window_plan\nimport qa_report_workflow\nimport qa_evidence_policy\nimport qa_task_plan\nimport qa_registered_accounts",
        "entity resolver import",
    )
    proxy_after = replace_once(
        proxy_after,
        '    question = qa_mcp_planning_question(raw_question)\n    answer_route = qa_answer_route(question)\n',
        '    question = qa_mcp_planning_question(raw_question)\n'
        '    temporal_question = str(task_plan.get("instruction_text") or raw_question)\n'
        '    time_window_plan = qa_time_window_plan.build_time_window_plan(\n'
        '        temporal_question, qa_mcp_variables(temporal_question)\n'
        '    )\n'
        '    report_plan = qa_report_workflow.build_report_plan(temporal_question)\n'
        '    if task_plan.get("intents") != ["live_data"]:\n'
        '        time_window_plan = None\n'
        '    if task_plan.get("intents") != ["period_report"]:\n'
        '        report_plan = None\n'
        '    answer_route = qa_answer_route(question)\n',
        "freeze temporal workflow before MCP attachment",
    )
    proxy_after = replace_once(
        proxy_after,
        '    if not QA_MCP_PREFETCH_ENABLED:\n',
        '    if qa_time_window_plan.temporal_intent(question):\n'
        '        return {"used": False, "reason": "requires_complete_temporal_workflow"}\n'
        '    if not QA_MCP_PREFETCH_ENABLED:\n',
        "temporal workflow bypasses single-window prefetch",
    )
    workflow_seam = '''            if time_window_plan is not None or report_plan is not None:
                async def readonly_call(name, args):
                    result = await asyncio.wait_for(
                        qa_request_control.call_tool(session, name, args),
                        timeout=tool_timeout_seconds(),
                    )
                    return try_load_json(mcp_result_to_text(result, max_chars=None))

                def readonly_start(item):
                    working_messages.append({"role": "assistant", "content": "", "tool_calls": [
                        {"function": {"name": item["tool"], "arguments": item["arguments"]}}
                    ]})
                    public_trace = qa_mcp_public_trace("tool_start", item)
                    if public_trace:
                        item["public_trace"] = public_trace
                    if emit:
                        emit("tool_start", item)

                def readonly_result(item, payload):
                    item["server_id"] = tool_servers.get(item["tool"])
                    if item["policy"]["ok"]:
                        result_text = json.dumps(payload, ensure_ascii=False)
                        working_messages.append({"role": "tool", "name": item["tool"], "content": result_text})
                        evidence_sink.append({"name": item["tool"], "result_text": result_text})
                    public_trace = qa_mcp_public_trace("tool_result", {**item, "result": payload})
                    if public_trace:
                        item["public_trace"] = public_trace
                    if emit:
                        emit("tool_result", item)

                workflow_module = qa_time_window_plan if time_window_plan is not None else qa_report_workflow
                workflow_executor = workflow_module.execute_time_window_plan if time_window_plan is not None else workflow_module.execute_report_plan
                workflow_outcome = await workflow_executor(
                    time_window_plan if time_window_plan is not None else report_plan,
                    available_tools=tool_names,
                    validate=lambda name, args: validate_tool_call(name, args, tool_schemas, policy_limits),
                    call=readonly_call, on_start=readonly_start, on_result=readonly_result,
                    max_calls=max(1, QA_MCP_MAX_TOOL_CALLS),
                )
                workflow_outcome["messages"] = working_messages
                return workflow_outcome

'''
    proxy_after = replace_once(
        proxy_after,
        '            # A composite body-temperature query must win before the generic\n',
        workflow_seam + '            # A composite body-temperature query must win before the generic\n',
        "temporal workflow precedes generic DAG and single-plan execution",
    )
    proxy_after = replace_once(
        proxy_after,
        "def qa_mcp_variables(question: str) -> list[str]:\n"
        "    q = normalize_spoken_question(question)\n"
        "    variables = qa_mcp_exact_variables(question)\n",
        "def qa_mcp_variables(question: str) -> list[str]:\n"
        "    q = normalize_spoken_question(question)\n"
        "    entity_resolution = qa_entity_resolution.resolve_requested_entities(question)\n"
        "    variables = list(entity_resolution.get(\"variables\") or [])\n"
        "    for variable in qa_mcp_exact_variables(question):\n"
        "        if variable not in variables:\n"
        "            variables.append(variable)\n",
        "executor consumes frozen entity resolution",
    )
    ast.parse(proxy_after)

    output.mkdir(parents=True, exist_ok=True)
    (output / "ollama_proxy_server.py").write_bytes(proxy_after.encode("utf-8"))
    (output / "bf_data_mcp_server.py").write_bytes(mcp_after.encode("utf-8"))
    mcp_patch = "".join(difflib.unified_diff(mcp_before.splitlines(keepends=True), mcp_after.splitlines(keepends=True), fromfile="production/bf_data_mcp_server.py", tofile="v4/bf_data_mcp_server.py"))
    (output / "mcp.patch").write_bytes(mcp_patch.encode("utf-8"))
    for name in ("mcp_tool_selection.py", "qa_evidence_policy.py", "qa_evidence_claims.py"):
        shutil.copyfile(source_dir / name, output / name)
    shutil.copyfile(backend / "qa_task_plan.py", output / "qa_task_plan.py")
    shutil.copyfile(backend / "qa_entity_resolution.py", output / "qa_entity_resolution.py")
    shutil.copyfile(backend / "qa_time_window_plan.py", output / "qa_time_window_plan.py")
    shutil.copyfile(backend / "qa_report_workflow.py", output / "qa_report_workflow.py")

    patch = "".join(
        difflib.unified_diff(
            proxy_before.splitlines(keepends=True),
            proxy_after.splitlines(keepends=True),
            fromfile="v3/ollama_proxy_server.py",
            tofile="v4/ollama_proxy_server.py",
        )
    )
    (output / "proxy.patch").write_bytes(patch.encode("utf-8"))
    report = {
        "schema": "bf.qa.routing-candidate-build.v2",
        "requirement_id": REQ,
        "issues": ["QAOPT-R03", "QAOPT-R04", "QAOPT-R05"],
        "proxy_baseline_sha256": PROXY_V3_SHA256,
        "task_plan_baseline_sha256": TASK_PLAN_V3_SHA256,
        "mcp_baseline_sha256": MCP_BASELINE_SHA256,
        "artifacts": {
            path.name: sha256(path.read_bytes())
            for path in sorted(output.glob("*.py"))
        },
        "syntax": "passed",
        "production_changed": False,
    }
    (output / "build.json").write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"ok": True, "output": str(output), "issues": report["issues"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
