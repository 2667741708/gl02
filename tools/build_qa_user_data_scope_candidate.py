"""Build the complete user-input/live-input source closure without production calls."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v38/candidate-r2'
TARGET = ROOT / '.codex_runtime/qa-routing-v39/candidate-r3'
SEAMS = (
 ('def qa_mcp_duration_minutes(question: str) -> int | None:\n    text = question.strip()',
  'def qa_mcp_duration_minutes(question: str) -> int | None:\n    question = qa_task_plan.live_query_text(question)\n    text = question.strip()'),
 ('    """Batch clear sensor requests without an extra LLM planning round."""\n\n    text = str(question or "")',
  '    """Batch clear sensor requests without an extra LLM planning round."""\n\n    question = qa_task_plan.live_query_text(question)\n    text = str(question or "")'),
 ('def qa_mcp_variables(question: str) -> list[str]:\n    q = normalize_spoken_question(question)',
  'def qa_mcp_variables(question: str) -> list[str]:\n    question = qa_task_plan.live_query_text(question)\n    q = normalize_spoken_question(question)'),
 ('    """Expand explicit variables with a bounded, read-only process-risk bundle."""\n\n    variables = list(qa_mcp_variables(question))',
  '    """Expand explicit variables with a bounded, read-only process-risk bundle."""\n\n    question = qa_task_plan.live_query_text(question)\n    variables = list(qa_mcp_variables(question))'),
 ('            task_plan = qa_history_compound.execution_plan(execution_question, history_request)\n            tool_context = update_tool_context(',
  '            task_plan = qa_history_compound.execution_plan(execution_question, history_request)\n            if "user_supplied_data" in task_plan["intents"] and "live_data" in task_plan["intents"]:\n                task_plan["entities"] = qa_mcp_variables(execution_question)\n            tool_context = update_tool_context('),
 ('                enrich_routing_question(execution_question, tool_context)\n                if task_plan.get("allow_prefetch")',
  '                enrich_routing_question(qa_task_plan.live_query_text(execution_question), tool_context)\n                if task_plan.get("allow_prefetch")'),
)


def transform(text):
    result = text
    for before, after in SEAMS:
        assert result.count(before) == 1
        result = result.replace(before, after)
    restored = result
    for before, after in reversed(SEAMS):
        assert restored.count(after) == 1
        restored = restored.replace(after, before)
    assert ast.dump(ast.parse(restored)) == ast.dump(ast.parse(text))
    return result


def main():
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    report = json.loads((ROOT / 'tests/qa_regression/math_function_policy_20260917.json').read_bytes())
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert sha(prior_raw) == report['private_candidate']['manifest_sha256']
    prior = json.loads(prior_raw)
    assert len(prior['files']) == 15 and not TARGET.exists()
    assert prior['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, raw in payloads.items():
        assert sha(raw) == prior['files'][name]['sha256']
    payloads['qa_task_plan.py'] = (ROOT / '高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes()
    payloads['ollama_proxy_server.py'] = transform(payloads['ollama_proxy_server.py'].decode('utf-8')).encode()
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    inherited = [name for name in prior['files'] if name not in ('qa_task_plan.py', 'ollama_proxy_server.py')]
    assert len(inherited) == 13
    metadata = {'schema': 'bf.qa.private-user-data-scope-candidate.v1', 'candidate': 'v39-r3',
      'state': 'local_frozen_not_production_sealed', 'prior_manifest_sha256': sha(prior_raw),
      'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
      'inherited_v38_files_byte_identical': inherited, 'proxy_scoped_transformations': len(SEAMS),
      'proxy_unrelated_ast_preserved': True, 'production_dependency_refresh_required': True,
      'additional_runtime_read_set': prior['additional_runtime_read_set'],
      'model_name': prior['model_name'], 'model_digest': prior['model_digest'],
      'model_switch_allowed': False, 'same_name_weight_replacement_allowed': False,
      'fallback_model_allowed': False, 'production_writes': 0, 'model_operations': 0}
    TARGET.mkdir(parents=True)
    for name, raw in payloads.items():
        with (TARGET / name).open('xb') as handle: handle.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
    with (TARGET / 'package_manifest.private.json').open('xb') as handle: handle.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 15, 'inherited': 13,
      'manifest_sha256': sha(raw), 'proxy_sha256': sha(payloads['ollama_proxy_server.py']),
      'production_sealed': False, 'model_operations': 0}))


if __name__ == '__main__':
    main()
