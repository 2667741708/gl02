"""Build a local V37 closure from hash-bound V36; no production operations."""
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / '高炉前端数据/智能助手/backend'
PRIOR = ROOT / '.codex_runtime/qa-routing-v36/candidate-r1'
TARGET = ROOT / '.codex_runtime/qa-routing-v37/candidate-r2'
MODULES = ('qa_task_plan.py', 'qa_document_compound.py', 'qa_history_compound.py',
           'qa_history_projection.py', 'qa_evidence_policy.py')
SEAMS = (
 ('    if qa_evidence_policy.no_live_lookup(question):\n        return False\n    if not QA_MCP_TOOLS_ENABLED',
  '    if qa_evidence_policy.no_live_lookup(question) and not qa_task_plan.build_task_plan(question).get("allow_mcp_tools"):\n        return False\n    if not QA_MCP_TOOLS_ENABLED'),
 ('    if not forced_mode and qa_mcp_no_realtime_requested(raw_question):',
  '    if not forced_mode and qa_mcp_no_realtime_requested(raw_question) and not task_plan.get("allow_mcp_tools"):'),
 ('                if (tool_selection.get("mode") == "none"\n                        or (tool_selection.get("mode") == "required" and requested != ("search_qa_messages",))):',
  '                if (not qa_task_plan.tool_allowed("search_qa_messages", task_plan)\n                        or tool_selection.get("mode") == "none"\n                        or (tool_selection.get("mode") == "required" and requested != ("search_qa_messages",))):'),
)


def transform(text):
    result = text
    for before, after in SEAMS:
        if result.count(before) != 1:
            raise ValueError('Unique accepted source-scope seam required')
        result = result.replace(before, after)
    original, restored = ast.parse(text), ast.parse(result)
    corrections = 0
    for node in ast.walk(restored):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.BoolOp):
            continue
        values = node.test.values
        if (isinstance(node.test.op, ast.And) and ast.unparse(values[0]) == 'qa_evidence_policy.no_live_lookup(question)'
                and ast.unparse(values[-1]) == "not qa_task_plan.build_task_plan(question).get('allow_mcp_tools')"):
            assert len(values) == 2
            node.test = values[0]
            corrections += 1
        elif (isinstance(node.test.op, ast.And) and ast.unparse(values[0]) == 'not forced_mode'
              and len(values) == 3 and ast.unparse(values[1]) == 'qa_mcp_no_realtime_requested(raw_question)'
              and ast.unparse(values[2]) == "not task_plan.get('allow_mcp_tools')"):
            node.test.values = values[:2]
            corrections += 1
        elif (isinstance(node.test.op, ast.Or) and ast.unparse(values[0]) == "not qa_task_plan.tool_allowed('search_qa_messages', task_plan)"):
            assert len(values) == 3
            node.test.values = values[1:]
            corrections += 1
    if corrections != 3 or ast.dump(original, include_attributes=False) != ast.dump(restored, include_attributes=False):
        raise ValueError('Unrelated accepted proxy semantics changed')
    return result


def main():
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    report = json.loads((ROOT / 'tests/qa_regression/fixed_model_override_20260917.json').read_bytes())
    old_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert sha(old_raw) == report['private_candidate']['manifest_sha256']
    prior = json.loads(old_raw)
    assert len(prior['files']) == 10 and not TARGET.exists(), 'No overwrite of immutable candidates'
    for name, item in prior['files'].items():
        assert sha((PRIOR / name).read_bytes()) == item['sha256']
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    payloads['ollama_proxy_server.py'] = transform(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    payloads.update({name: (BACKEND / name).read_bytes() for name in MODULES})
    payloads['qa_document_knowledge.py'] = (BACKEND / 'qa_document_knowledge.py').read_bytes()
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    TARGET.mkdir(parents=True)
    for name, raw in payloads.items():
        with (TARGET / name).open('xb') as handle:
            handle.write(raw)
    inherited = [name for name in prior['files'] if name not in ('ollama_proxy_server.py', 'qa_document_knowledge.py')]
    assert len(inherited) == 8
    sys.path.insert(0, str(BACKEND))
    sys.path.insert(0, str(TARGET))
    import qa_task_plan
    import qa_history_projection
    assert Path(qa_task_plan.__file__).parent == Path(qa_history_projection.__file__).parent == TARGET
    assert qa_task_plan.lookup_constraints('不要调用工具')['all_tools_disabled']
    metadata = {'schema': 'bf.qa.private-local-compound-scope-candidate.v1', 'candidate': 'v37-r2',
      'state': 'local_frozen_not_production_sealed',
      'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
      'inherited_v36_files_byte_identical': inherited, 'added_modules': list(MODULES),
      'proxy_unrelated_ast_preserved': True, 'proxy_predicates_changed': 3,
      'production_dependency_refresh_required': True,
      'additional_runtime_read_set': ['qa_entity_resolution.py', 'qa_time_window_plan.py', 'qa_document_integrity.py'],
      'model_name': prior['model_name'], 'model_digest': prior['model_digest'],
      'model_switch_allowed': False, 'same_name_weight_replacement_allowed': False,
      'fallback_model_allowed': False, 'production_writes': 0, 'model_operations': 0}
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (TARGET / 'package_manifest.private.json').open('xb') as handle:
        handle.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': len(payloads), 'inherited': len(inherited),
        'manifest_sha256': sha(raw), 'proxy_sha256': sha(payloads['ollama_proxy_server.py']),
        'proxy_unrelated_ast_preserved': True, 'production_sealed': False, 'model_operations': 0}))


if __name__ == '__main__':
    main()
