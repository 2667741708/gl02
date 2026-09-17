"""Bind actual request/persistence/reply boundaries over the verified V44 closure."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v44/candidate-r2'
PRIOR_SHA = '9b9b797b82bd261bfbcce936e8f24aef5974f5b5f056e001633acc4b856a7ee6'


def replace_function(text, name, before, after):
    node = next(item for item in ast.walk(ast.parse(text)) if isinstance(item, ast.FunctionDef) and item.name == name)
    lines = text.splitlines(keepends=True)
    original = ''.join(lines[node.lineno - 1:node.end_lineno])
    assert original.count(before) == 1, (name, before)
    lines[node.lineno - 1:node.end_lineno] = [original.replace(before, after)]
    return ''.join(lines)


def build_proxy(text):
    before_tree = ast.parse(text)
    assert text.count('import qa_fixed_model_identity\n') == 1
    text = text.replace('import qa_fixed_model_identity\n', 'import qa_fixed_model_identity\nimport qa_prompt_binding\n')
    assert text.count('    def handle_qa_chat(self) -> None:\n') == 1
    text = text.replace('    def handle_qa_chat(self) -> None:\n', '    @qa_prompt_binding.trace_turn\n    def handle_qa_chat(self) -> None:\n')
    # Cache keys always carry the new provenance contract, even with a configured base version.
    current = next(item for item in ast.parse(text).body if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name) and item.targets[0].id == 'ABC_RULE_ASSISTANT_PROMPT_VERSION')
    original = ast.get_source_segment(text, current)
    value = ast.get_source_segment(text, current.value)
    assert text.count(original) == 1
    text = text.replace(original, 'ABC_RULE_ASSISTANT_PROMPT_VERSION = qa_prompt_binding.cache_version(' + value + ')')
    text = replace_function(text, 'build_ollama_request', '        body = json_bytes(payload)\n', '        body = json_bytes(payload)\n        qa_prompt_binding.record_request(body)\n')
    text = replace_function(text, 'add_message', '    ts = iso_now()\n', '    if role == "assistant":\n        hidden_context = qa_prompt_binding.with_binding(hidden_context)\n    ts = iso_now()\n')
    text = replace_function(text, 'cache_abc_rule_analysis', 'json.dumps(analysis_payload or {"answer": analysis_text}, ensure_ascii=False)', 'json.dumps(qa_prompt_binding.cache_envelope(analysis_payload or {"answer": analysis_text}), ensure_ascii=False)')
    text = replace_function(text, '_abc_rule_cached_analysis', '    return {\n', '    prompt_binding = qa_prompt_binding.cached_binding(load_json(row["analysis_json"], {}))\n    if prompt_binding is None:\n        return None\n    return {\n        "prompt_binding": prompt_binding,\n')
    text = replace_function(text, 'send_cached_abc_initial_analysis', '            "prompt_version": cached.get("prompt_version"),\n', '            "prompt_version": cached.get("prompt_version"),\n            "prompt_binding": qa_prompt_binding.cache_reply_binding(cached.get("prompt_binding")),\n')
    capture = ('            qa_prompt_binding.record_prepared(prepared, template=QA_SYSTEM_PROMPT_TEMPLATE, versions={\n'
               '                "sources": qa_prompt_sources.VERSION, "evidence": qa_evidence_policy.VERSION,\n'
               '                "task_plan": qa_task_plan.VERSION, "abc_initial": ABC_RULE_ASSISTANT_PROMPT_VERSION})\n')
    text = replace_function(text, 'handle_qa_chat_json', '            prepared = self.prepare_qa_chat(payload, question)\n', '            prepared = self.prepare_qa_chat(payload, question)\n' + capture)
    text = replace_function(text, 'handle_qa_chat_stream', '            prepared = self.prepare_qa_chat(payload, question, include_conversations=False)\n', '            prepared = self.prepare_qa_chat(payload, question, include_conversations=False)\n' + capture)
    text = replace_function(text, 'send_json', '        data = json_bytes(payload)\n', '        payload = qa_prompt_binding.public_payload(payload)\n        data = json_bytes(payload)\n')
    text = replace_function(text, 'write_qa_event', '        try:\n', '        if event in {"final", "error"}:\n            payload = qa_prompt_binding.public_payload(payload)\n        try:\n')
    text = replace_function(text, 'qa_host_log_summary', '        "model_timing": dict(timing),\n', '        "model_timing": dict(timing),\n        "prompt_binding": qa_prompt_binding.snapshot(),\n')
    allowed = {'handle_qa_chat', 'build_ollama_request', 'add_message', 'cache_abc_rule_analysis', '_abc_rule_cached_analysis',
               'send_cached_abc_initial_analysis', 'handle_qa_chat_json', 'handle_qa_chat_stream', 'send_json', 'write_qa_event', 'qa_host_log_summary'}
    def functions(tree): return {item.name: ast.dump(item, include_attributes=False) for item in ast.walk(tree) if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
    before, after = functions(before_tree), functions(ast.parse(text))
    assert set(before) == set(after)
    assert {name for name in before if before[name] != after[name]} == allowed
    return text


def main(revision):
    target = ROOT / '.codex_runtime/qa-routing-v45' / ('candidate-' + revision)
    assert not target.exists()
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(prior_raw).hexdigest() == PRIOR_SHA
    prior = json.loads(prior_raw)
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, raw in payloads.items(): assert hashlib.sha256(raw).hexdigest() == prior['files'][name]['sha256']
    payloads['ollama_proxy_server.py'] = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    payloads['qa_prompt_binding.py'] = (ROOT / '高炉前端数据/智能助手/backend/qa_prompt_binding.py').read_bytes()
    assert len(payloads) == 16
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    inherited = [name for name in prior['files'] if name != 'ollama_proxy_server.py']
    metadata = {'schema': 'bf.qa.private-prompt-binding-candidate.v1', 'candidate': 'v45-' + revision,
        'state': 'local_frozen_not_production_sealed', 'prior_manifest_sha256': PRIOR_SHA,
        'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
        'inherited_v44_files_byte_identical': inherited, 'changed_modules': ['ollama_proxy_server.py'],
        'added_modules': ['qa_prompt_binding.py'], 'abc_cache_namespace_suffix': '.fixed-pin-binding.v1',
        'additional_runtime_read_set': prior['additional_runtime_read_set'], 'production_dependency_refresh_required': True,
        'model_name': prior['model_name'], 'model_digest': prior['model_digest'],
        'model_switch_allowed': False, 'same_name_weight_replacement_allowed': False, 'fallback_model_allowed': False,
        'production_writes': 0, 'model_operations': 0}
    assert len(inherited) == 14 and metadata['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    target.mkdir(parents=True)
    for name, raw in payloads.items():
        with (target / name).open('xb') as stream: stream.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as stream: stream.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 16, 'inherited': 14,
                      'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'production_sealed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', choices=('r1', 'r2', 'r3', 'r4'), default='r1')
    main(parser.parse_args().revision)
