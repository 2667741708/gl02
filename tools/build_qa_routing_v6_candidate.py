"""Build V6 from hash-pinned accepted V5 bytes; no tracked legacy proxy deployment."""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

PROXY_SHA = '4f4258b1bfe5bfc2d428198f1928528e025fdc28202075cb5f03aecba40e4dc3'


def replace(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError(f'{label}: exact accepted seam not unique')
    return source.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v5-candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline, output = args.v5_candidate.resolve(), args.output.resolve()
    if hashlib.sha256((baseline / 'ollama_proxy_server.py').read_bytes()).hexdigest() != PROXY_SHA:
        raise ValueError('Accepted V5 proxy hash mismatch')
    before = (baseline / 'ollama_proxy_server.py').read_text(encoding='utf-8')
    source = replace(before, 'import qa_history_projection\n', 'import qa_history_projection\nimport qa_verified_facts\nimport qa_completion\n', 'typed fact and completion seams')
    for spaces in (12, 8):
        p = ' ' * spaces
        old = p + 'if tool_result.get("answer") is None and prepared.get("history_result") is not None:\n' + p + '    tool_result = qa_history_projection.history_outcome(prepared["history_result"])\n'
        new = old + p + 'if tool_result.get("answer") is None and not prepared.get("use_mcp_tools"):\n' + p + '    verified_prefetch = qa_verified_facts.prefetch_outcome(prepared.get("mcp_prefetch") or {}, prepared["hidden_context"].get("qa_task_plan") or {})\n' + p + '    if verified_prefetch is not None:\n' + p + '        tool_result = verified_prefetch\n'
        source = replace(source, old, new, f'prefetch verified facts {spaces}')
    old = '''                response = call_ollama_chat_obj(stream_messages, tools=None, max_tokens=720, response_mode=prepared.get("response_mode") or QA_RESPONSE_MODE_FLASH)
                precomputed_answer = qa_evidence_policy.enforce_no_code(clean_llm_output((response.get("message") or {}).get("content") or response.get("response") or ""))
                model_timing.update(ollama_response_timing(response))
                tool_result = {"answer_route": "evidence_without_tools", "model_request_count": 1}
'''
    new = '''                class CompletionTiming:
                    def update(self, response):
                        model_timing.update(ollama_response_timing(response))
                precomputed_answer, tool_result = qa_completion.complete_model_response(
                    stream_messages, call=call_ollama_chat_obj,
                    clean=lambda text: qa_evidence_policy.enforce_no_code(clean_llm_output(text)),
                    timing=CompletionTiming(), response_mode=prepared.get("response_mode") or QA_RESPONSE_MODE_FLASH,
                )
'''
    source = replace(source, old, new, 'bounded SSE ordinary completion')
    old = '''                answer = (
                    call_ollama_chat_strict_json(
                        prepared["messages"],
                        prepared.get("bound_assistant_context") or {},
                        timing_out=model_timing,
                    )
                    if prepared.get("analysis_mode") == "initial_context_explanation"
                    else call_ollama_chat(
                        prepared["messages"],
                        timing_out=model_timing,
                        response_mode=prepared.get("response_mode") or QA_RESPONSE_MODE_FLASH,
                    )
                )
'''
    new = '''                if prepared.get("analysis_mode") == "initial_context_explanation":
                    answer = call_ollama_chat_strict_json(prepared["messages"], prepared.get("bound_assistant_context") or {}, timing_out=model_timing)
                else:
                    class CompletionTiming:
                        def update(self, response):
                            model_timing.update(ollama_response_timing(response))
                    answer, tool_result = qa_completion.complete_model_response(
                        prepared["messages"], call=call_ollama_chat_obj,
                        clean=lambda text: qa_evidence_policy.enforce_no_code(clean_llm_output(text)),
                        timing=CompletionTiming(), response_mode=prepared.get("response_mode") or QA_RESPONSE_MODE_FLASH,
                    )
'''
    source = replace(source, old, new, 'JSON completion parity')
    source = replace(source, '                direct_answer = deterministic_mcp_answer(name, result_text)\n', '''                direct_answer = deterministic_mcp_answer(name, result_text)
                comparison = qa_verified_facts.temperature_comparison(try_load_json(result_text) or {}, temporal_question, args) if name == "query_gl02_sensors" else None
                if comparison is not None:
                    direct_answer = comparison["answer"]
''', 'question-specific spatial comparison')
    # Keep existing guarded grounding checks; add honest completion to the
    # deterministic branch without claiming a quality-blocked answer is complete.
    marker = '                    final_answer_route = "grounded_fact_only"\n'
    source = replace(source, marker, marker + '''                    if comparison is not None:
                        final_answer_route = "deterministic_temperature_comparison"
''', 'comparison route')
    # Public completion metadata in both transports; no history data is added.
    marker = '"mcp_model_explanation": tool_result.get("model_explanation"),'
    if source.count(marker) != 3:
        raise ValueError('Expected three final response seams')
    source = source.replace(marker, marker + '\n                        "completion": qa_completion.public_completion(tool_result),')
    source = replace(source, '                    elif answer_route == QA_ANSWER_ROUTE_ANALYSIS:\n', '                    elif answer_route == QA_ANSWER_ROUTE_ANALYSIS and comparison is None:\n', 'keep quality-bound comparison deterministic')
    source = replace(source, '                        "answer_route": final_answer_route,\n', '''                        "answer_route": final_answer_route,
                        "completion": {"schema": qa_completion.VERSION, "terminal_state": "completed" if comparison["complete"] else "partial", "complete": comparison["complete"], "covered_objects": comparison.get("covered", []), "missing_objects": comparison.get("missing", []), "quality_warnings": comparison.get("quality_warnings", [])} if comparison is not None else qa_completion.public_completion({}),
''', 'spatial comparison completion')
    # Legacy SSE prepare telemetry was accidentally unreachable after return.
    old = '''            emit_host_log(
                "qa.prepare.completed",
                request_id=request_id,
                transport="sse",
                answer_route=prepared.get("qa_answer_route"),
                **qa_host_log_summary(prepared),
        )
'''
    new = '''        emit_host_log(
            "qa.prepare.completed",
            request_id=request_id,
            transport="sse",
            answer_route=prepared.get("qa_answer_route"),
            **qa_host_log_summary(prepared),
        )
'''
    source = replace(source, old, new, 'reachable prepare telemetry')
    ast.parse(source)
    output.mkdir(parents=True, exist_ok=True)
    for path in baseline.glob('*.py'):
        shutil.copyfile(path, output / path.name)
    for name in ('qa_history_projection.py', 'mcp_conversation_context.py', 'qa_verified_facts.py', 'qa_completion.py'):
        shutil.copyfile(root / '高炉前端数据/智能助手/backend' / name, output / name)
    (output / 'ollama_proxy_server.py').write_text(source, encoding='utf-8', newline='\n')
    (output / 'proxy.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), source.splitlines(True), fromfile='accepted-v5', tofile='routing-v6')), encoding='utf-8', newline='\n')
    result = {'ok': True, 'schema': 'bf.qa.routing-v6-build.v1', 'requirement_id': 'REQ-QA-FULL-ISSUE-INVENTORY-20260916', 'baseline_commit': '312085a88ae95027728d5b8b72c4293af834d055', 'hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.glob('*.py'))}}
    (output / 'build.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
