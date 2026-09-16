"""Build the hash-bound QA routing V3 candidate from the exact production V2 files."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path


PROXY_SHA256 = "c94dc585cd0d319ae9ef2235620acd7802d880f569510dac43c2e571a0e6298c"
SELECTION_SHA256 = "50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033"
REQ = "REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916"


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one exact match, found {count}")
    return source.replace(old, new, 1)


def _proxy_candidate(source: str) -> tuple[str, int]:
    edits = 0

    def replace(old: str, new: str, label: str) -> None:
        nonlocal source, edits
        source = _replace_once(source, old, new, label)
        edits += 1

    replace(
        "import qa_evidence_policy\nimport qa_registered_accounts",
        "import qa_evidence_policy\nimport qa_task_plan\nimport qa_registered_accounts",
        "task planner import",
    )
    replace(
        "    actor_role: str = \"operator\",\n"
        "    response_mode: str = QA_RESPONSE_MODE_FLASH,\n"
        ") -> dict[str, Any]:\n"
        "    response_mode = normalize_qa_response_mode(response_mode)\n"
        "    raw_question = routing_question or last_user_question(messages)",
        "    actor_role: str = \"operator\",\n"
        "    response_mode: str = QA_RESPONSE_MODE_FLASH,\n"
        "    task_plan: dict[str, Any] | None = None,\n"
        "    evidence_sink: list[dict[str, Any]] | None = None,\n"
        ") -> dict[str, Any]:\n"
        "    response_mode = normalize_qa_response_mode(response_mode)\n"
        "    evidence_sink = evidence_sink if evidence_sink is not None else []\n"
        "    raw_question = routing_question or last_user_question(messages)\n"
        "    task_plan = task_plan or qa_task_plan.build_task_plan(raw_question)",
        "request evidence sink",
    )
    replace(
        "    emit: Any | None,\n"
        "    response_mode: str = QA_RESPONSE_MODE_FLASH,\n"
        ") -> dict[str, Any]:\n"
        "    \"\"\"Plan arguments once, validate the whole batch, then execute exact tools.\"\"\"",
        "    emit: Any | None,\n"
        "    response_mode: str = QA_RESPONSE_MODE_FLASH,\n"
        "    evidence_sink: list[dict[str, Any]] | None = None,\n"
        ") -> dict[str, Any]:\n"
        "    \"\"\"Plan arguments once, validate the whole batch, then execute exact tools.\"\"\"\n\n"
        "    evidence_sink = evidence_sink if evidence_sink is not None else []",
        "forced evidence sink",
    )
    replace(
        "                    emit=emit,\n"
        "                    response_mode=response_mode,\n"
        "                )",
        "                    emit=emit,\n"
        "                    response_mode=response_mode,\n"
        "                    evidence_sink=evidence_sink,\n"
        "                )",
        "forward forced evidence sink",
    )
    replace(
        "                working_messages.append({\"role\": \"tool\", \"name\": name, \"content\": result_text})\n"
        "                trace_item = {",
        "                working_messages.append({\"role\": \"tool\", \"name\": name, \"content\": result_text})\n"
        "                evidence_sink.append({\"name\": name, \"result_text\": result_text})\n"
        "                trace_item = {",
        "record deterministic tool evidence",
    )
    replace(
        "                for item in batch:\n"
        "                    working_messages.append(\n"
        "                        {\"role\": \"tool\", \"name\": item[\"name\"], \"content\": item[\"result_text\"]}\n"
        "                    )\n"
        "                    trace.append(item[\"trace\"])",
        "                for item in batch:\n"
        "                    working_messages.append(\n"
        "                        {\"role\": \"tool\", \"name\": item[\"name\"], \"content\": item[\"result_text\"]}\n"
        "                    )\n"
        "                    evidence_sink.append({\"name\": item[\"name\"], \"result_text\": item[\"result_text\"]})\n"
        "                    trace.append(item[\"trace\"])",
        "record planner tool evidence",
    )
    replace(
        "    for item in batch:\n"
        "        working_messages.append(\n"
        "            {\"role\": \"tool\", \"name\": item[\"name\"], \"content\": item[\"result_text\"]}\n"
        "        )\n"
        "        trace.append(item[\"trace\"])",
        "    for item in batch:\n"
        "        working_messages.append(\n"
        "            {\"role\": \"tool\", \"name\": item[\"name\"], \"content\": item[\"result_text\"]}\n"
        "        )\n"
        "        evidence_sink.append({\"name\": item[\"name\"], \"result_text\": item[\"result_text\"]})\n"
        "        trace.append(item[\"trace\"])",
        "record forced tool evidence",
    )
    replace(
        "    try:\n"
        "        return asyncio.run(\n"
        "            qa_mcp_tool_loop_async(\n"
        "                messages,",
        "    evidence_sink: list[dict[str, Any]] = []\n"
        "    try:\n"
        "        return asyncio.run(\n"
        "            qa_mcp_tool_loop_async(\n"
        "                messages,",
        "lifecycle evidence ledger",
    )
    replace(
        "                response_mode=response_mode,\n"
        "            )\n"
        "        )\n"
        "    except (KeyboardInterrupt, SystemExit):",
        "                response_mode=response_mode,\n"
        "                evidence_sink=evidence_sink,\n"
        "            )\n"
        "        )\n"
        "    except (KeyboardInterrupt, SystemExit):",
        "pass lifecycle evidence ledger",
    )
    replace(
        "            usable_names = {\n"
        "                name for name, (available, _) in availability_by_name.items() if available\n"
        "            }",
        "            usable_names = {\n"
        "                name for name, (available, _) in availability_by_name.items()\n"
        "                if available and qa_task_plan.tool_allowed(name, task_plan)\n"
        "            }",
        "enforce task plan tool domains",
    )
    replace(
        "    except BaseException as exc:\n"
        "        diagnostic = lifecycle_error(\"request_handler\", exc)\n"
        "        return {\n"
        "            \"ok\": False,\n"
        "            \"tool_used\": False,\n"
        "            \"answer\": \"\",\n"
        "            \"error\": \"MCP请求生命周期异常\",\n"
        "            \"error_detail\": diagnostic,\n"
        "        }",
        "    except BaseException as exc:\n"
        "        diagnostic = lifecycle_error(\"request_handler\", exc)\n"
        "        if any(tool_result_succeeded(item.get(\"result_text\", \"\")) for item in evidence_sink):\n"
        "            return {\n"
        "                \"ok\": True,\n"
        "                \"tool_used\": True,\n"
        "                \"answer\": deterministic_evidence_summary(evidence_sink),\n"
        "                \"answer_route\": \"lifecycle_error_verified_evidence\",\n"
        "                \"grounding_status\": \"partial_verified_evidence\",\n"
        "                \"error\": \"MCP请求生命周期异常\",\n"
        "                \"error_detail\": diagnostic,\n"
        "            }\n"
        "        return {\n"
        "            \"ok\": False,\n"
        "            \"tool_used\": False,\n"
        "            \"answer\": \"\",\n"
        "            \"error\": \"MCP请求生命周期异常\",\n"
        "            \"error_detail\": diagnostic,\n"
        "        }",
        "preserve facts on lifecycle error",
    )
    replace(
        "def qa_should_search_knowledge(question: str, mcp_prefetch: dict[str, Any] | None = None) -> tuple[bool, str]:\n"
        "    if not QA_KNOWLEDGE_INTENT_GATE:\n"
        "        return True, \"intent_gate_disabled\"\n"
        "    answer_route = qa_answer_route(question)",
        "def qa_should_search_knowledge(\n"
        "    question: str,\n"
        "    mcp_prefetch: dict[str, Any] | None = None,\n"
        "    task_plan: dict[str, Any] | None = None,\n"
        ") -> tuple[bool, str]:\n"
        "    if not QA_KNOWLEDGE_INTENT_GATE:\n"
        "        return True, \"intent_gate_disabled\"\n"
        "    plan = task_plan or qa_task_plan.build_task_plan(question)\n"
        "    if plan.get(\"search_knowledge\"):\n"
        "        return True, str(plan.get(\"reason\") or \"task_plan_knowledge\")\n"
        "    if plan.get(\"primary_intent\") in {\n"
        "        \"conversation_history\", \"period_report\", \"live_data\", \"user_supplied_data\", \"ordinary_qa\"\n"
        "    }:\n"
        "        return False, str(plan.get(\"reason\") or \"task_plan_source_isolation\")\n"
        "    answer_route = qa_answer_route(question)",
        "knowledge task plan gate",
    )
    replace(
        "    mcp_prefetch: dict[str, Any] | None = None,\n"
        "    connection: Any | None = None,\n"
        ") -> dict[str, Any]:\n"
        "    if not QA_KNOWLEDGE_ENABLED:",
        "    mcp_prefetch: dict[str, Any] | None = None,\n"
        "    connection: Any | None = None,\n"
        "    task_plan: dict[str, Any] | None = None,\n"
        ") -> dict[str, Any]:\n"
        "    if not QA_KNOWLEDGE_ENABLED:",
        "knowledge search signature",
    )
    replace(
        "    should_search, reason = qa_should_search_knowledge(question, mcp_prefetch)",
        "    should_search, reason = qa_should_search_knowledge(question, mcp_prefetch, task_plan)",
        "knowledge plan forwarding",
    )
    old_flow = '''            tool_context = update_tool_context(
                previous_tool_context,
                question,
                detected_objects=qa_mcp_analysis_variables(question),
                duration_minutes=qa_mcp_duration_minutes(question),
            )
            routing_question = enrich_routing_question(question, tool_context)
            answer_route = qa_answer_route(question)
            tool_selection = dict(
                payload.get("_qa_tool_selection") or {"mode": "auto", "tools": []}
            )
            mcp_started = time.perf_counter()
            mcp_prefetch = (
                {"used": False, "reason": "forced_tool_selection"}
                if tool_selection.get("mode") == "required"
                else qa_mcp_prefetch(routing_question)
            )
            timing_ms["mcp_prefetch"] = round((time.perf_counter() - mcp_started) * 1000, 1)
            knowledge_started = time.perf_counter()
            knowledge_pack = qa_search_knowledge(
                question,
                mcp_prefetch=mcp_prefetch,
                connection=conn,
            )
            timing_ms["knowledge"] = round((time.perf_counter() - knowledge_started) * 1000, 1)
            use_mcp_tools = (
                True
                if tool_selection.get("mode") == "required"
                else qa_mcp_should_use_tools(routing_question, payload, mcp_prefetch)
            )'''
    new_flow = '''            task_plan = qa_task_plan.build_task_plan(question)
            tool_context = update_tool_context(
                previous_tool_context,
                question,
                detected_objects=qa_mcp_analysis_variables(question),
                duration_minutes=qa_mcp_duration_minutes(question),
            )
            routing_question = (
                enrich_routing_question(question, tool_context)
                if task_plan.get("allow_prefetch")
                else question
            )
            answer_route = qa_answer_route(question)
            tool_selection = dict(
                payload.get("_qa_tool_selection") or {"mode": "auto", "tools": []}
            )
            mcp_started = time.perf_counter()
            if tool_selection.get("mode") == "required":
                mcp_prefetch = {"used": False, "reason": "forced_tool_selection"}
            elif task_plan.get("allow_prefetch"):
                mcp_prefetch = qa_mcp_prefetch(routing_question)
            else:
                mcp_prefetch = {"used": False, "reason": "task_plan_disallows_prefetch"}
            timing_ms["mcp_prefetch"] = round((time.perf_counter() - mcp_started) * 1000, 1)
            knowledge_started = time.perf_counter()
            knowledge_pack = qa_search_knowledge(
                question,
                mcp_prefetch=mcp_prefetch,
                connection=conn,
                task_plan=task_plan,
            )
            timing_ms["knowledge"] = round((time.perf_counter() - knowledge_started) * 1000, 1)
            use_mcp_tools = (
                True
                if tool_selection.get("mode") == "required"
                else bool(task_plan.get("allow_mcp_tools"))
                and qa_mcp_should_use_tools(routing_question, payload, mcp_prefetch)
            )'''
    replace(old_flow, new_flow, "request task plan integration")
    replace(
        '                "qa_answer_route": answer_route,\n'
        '                "mcp_conversation_context": tool_context,',
        '                "qa_answer_route": answer_route,\n'
        '                "qa_task_plan": qa_task_plan.public_task_plan(task_plan),\n'
        '                "mcp_conversation_context": tool_context,',
        "task plan audit metadata",
    )
    return source, edits


def _selection_candidate(source: str) -> tuple[str, int]:
    edits = 0

    def replace(old: str, new: str, label: str) -> None:
        nonlocal source, edits
        source = _replace_once(source, old, new, label)
        edits += 1

    replace(
        "from typing import Any, Iterable, Mapping\n",
        "from typing import Any, Iterable, Mapping\n\nfrom qa_evidence_claims import answer_numbers_are_grounded\n",
        "field validator import",
    )
    replace(
        "    allowed_text = f\"{evidence}\\n{question}\"\n"
        "    allowed_numbers = {_canonical_number(item) for item in _NUMBER_RE.findall(allowed_text)}\n"
        "    for item in _NUMBER_RE.findall(answer_text):\n"
        "        if _canonical_number(item) not in allowed_numbers:\n"
        "            return False",
        "    if not answer_numbers_are_grounded(answer_text, evidence, question):\n"
        "        return False",
        "field-aware rounded numeric validation",
    )
    replace(
        "            blocks.append(\n"
        "                f\"### {name}\\n```json\\n{json.dumps(payload, ensure_ascii=False, default=str, indent=2)}\\n```\"\n"
        "            )",
        "            compact = json.dumps(payload, ensure_ascii=False, default=str, separators=(\",\", \":\"))\n"
        "            blocks.append(f\"### {name}\\n{compact}\")",
        "non-code deterministic evidence summary",
    )
    return source, edits


def build(proxy_baseline: Path, selection_baseline: Path, output: Path) -> dict[str, object]:
    proxy_raw = proxy_baseline.read_bytes()
    selection_raw = selection_baseline.read_bytes()
    if _hash(proxy_raw) != PROXY_SHA256:
        raise ValueError("Proxy V2 baseline hash changed; collect and review a new baseline")
    if _hash(selection_raw) != SELECTION_SHA256:
        raise ValueError("Tool-selection baseline hash changed; collect and review a new baseline")
    proxy_source = proxy_raw.decode("utf-8")
    selection_source = selection_raw.decode("utf-8")
    proxy_candidate, proxy_edits = _proxy_candidate(proxy_source)
    selection_candidate, selection_edits = _selection_candidate(selection_source)
    for name, source in (("ollama_proxy_server.py", proxy_candidate), ("mcp_tool_selection.py", selection_candidate)):
        if "\r" in source or source.startswith("\ufeff"):
            raise ValueError(f"{name} must be UTF-8 LF without BOM")
        ast.parse(source)
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    backend = root / "高炉前端数据" / "智能助手" / "backend"
    generated = {
        "ollama_proxy_server.py": proxy_candidate.encode("utf-8"),
        "mcp_tool_selection.py": selection_candidate.encode("utf-8"),
    }
    for name in ("qa_evidence_policy.py", "qa_task_plan.py", "qa_evidence_claims.py"):
        raw = (backend / name).read_bytes()
        ast.parse(raw.decode("utf-8"))
        generated[name] = raw
    for name, raw in generated.items():
        (output / name).write_bytes(raw)
    proxy_diff = difflib.unified_diff(proxy_source.splitlines(True), proxy_candidate.splitlines(True), fromfile="v2/ollama_proxy_server.py", tofile="v3/ollama_proxy_server.py")
    selection_diff = difflib.unified_diff(selection_source.splitlines(True), selection_candidate.splitlines(True), fromfile="v2/mcp_tool_selection.py", tofile="v3/mcp_tool_selection.py")
    (output / "proxy.patch").write_text("".join(proxy_diff), encoding="utf-8", newline="\n")
    (output / "selection.patch").write_text("".join(selection_diff), encoding="utf-8", newline="\n")
    report: dict[str, object] = {
        "requirement_id": REQ,
        "proxy_baseline_sha256": PROXY_SHA256,
        "selection_baseline_sha256": SELECTION_SHA256,
        "candidate_sha256": {name: _hash(raw) for name, raw in generated.items()},
        "proxy_edits": proxy_edits,
        "selection_edits": selection_edits,
        "syntax": "passed",
        "production_changed": False,
    }
    (output / "build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy-baseline", type=Path, required=True)
    parser.add_argument("--selection-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.proxy_baseline, args.selection_baseline, args.output), ensure_ascii=False))
