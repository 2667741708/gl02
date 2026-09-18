"""Freeze owned object clarification completion while preserving all V49 handlers."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

from probe_qa_shared_proxy_delta_readonly import stable_ast_dump

if not __debug__:
    raise RuntimeError('Pending object candidate requires assertions enabled')

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v49/candidate-r6'
PRIOR_SHA = '73da30da0e2aebcfec7fafd8453598af11c4337a5ef538f29d3ae79854d70a42'
HELPERS = {'pending_data_object_context', 'resolve_pending_data_object'}


def validate_planner(before, after):
    original, current = ast.parse(before), ast.parse(after)
    added = [n for n in current.body if isinstance(n, ast.FunctionDef) and n.name in HELPERS]
    assert {n.name for n in added} == HELPERS and len(added) == 2
    assert not any(isinstance(n, ast.FunctionDef) and n.name in HELPERS for n in original.body)
    for node in added:
        current.body.remove(node)
    imports = [n for n in current.body if isinstance(n, ast.Import) and
               len(n.names) == 1 and n.names[0].name == 'math' and n.names[0].asname is None]
    assert len(imports) == 1
    current.body.remove(imports[0])
    assert stable_ast_dump(original) == stable_ast_dump(current), 'Existing V49 planner semantics changed'


def build_proxy(text):
    original = ast.parse(text)
    before = '            source_task_plan = qa_task_plan.build_task_plan(question)\n'
    after = (
        before
        + '            previous_tool_context = last_qa_tool_context(conn, conversation_id, owner_subject)\n'
        + '            early_object_confirmation = qa_task_plan.resolve_pending_data_object(\n'
        + '                question, source_task_plan, previous_tool_context, SPOKEN_MCP_VARIABLE_ALIASES,\n'
        + '                now=time.time(), code_only=qa_evidence_policy.code_request_only(question)\n'
        + '                    or (payload.get("_qa_tool_selection") or {}).get("mode") == "none")\n')
    assert text.count(before) == 1
    changed = text.replace(before, after)
    old_load = '            previous_tool_context = last_qa_tool_context(conn, conversation_id, owner_subject)\n'
    assert changed.count(old_load) == 2
    position = changed.rindex(old_load)
    changed = changed[:position] + changed[position + len(old_load):]
    before = '                source_task_plan, code_only=qa_evidence_policy.code_request_only(question))\n'
    after = '                source_task_plan, code_only=qa_evidence_policy.code_request_only(question)\n                    or (payload.get("_qa_tool_selection") or {}).get("mode") == "none")\n'
    assert changed.count(before) == 1
    changed = changed.replace(before, after)
    before = '            sensor_context_enabled = sensor_policy["enabled"]\n'
    after = (
        '            if early_object_confirmation["state"] in {"confirmed_data_object", "needs_clarification"}:\n'
        '                sensor_policy.update(enabled=False, skipped=True, reason="pending_object_resolution_before_source_read")\n'
        + before)
    assert changed.count(before) == 1
    changed = changed.replace(before, after)
    before = '            task_plan = qa_history_compound.execution_plan(execution_question, history_request)\n'
    after = (before
        + '            if (payload.get("_qa_tool_selection") or {}).get("mode") == "none":\n'
        + '                task_plan.update(all_tools_disabled=True, no_live_lookup=True,\n'
        + '                    allow_prefetch=False, allow_mcp_tools=False, search_knowledge=False,\n'
        + '                    allowed_sources=[], allowed_tool_domains=[], reason="explicit_source_restriction")\n')
    assert changed.count(before) == 1
    changed = changed.replace(before, after)
    before = '            tool_context = update_tool_context(\n                None if context_forbidden else previous_tool_context,\n'
    after = (
        '            object_confirmation = (early_object_confirmation if execution_question == question else\n'
        '                qa_task_plan.resolve_pending_data_object(\n'
        '                execution_question, task_plan, previous_tool_context, SPOKEN_MCP_VARIABLE_ALIASES,\n'
        '                now=time.time(), code_only=context_forbidden\n'
        '                    or (payload.get("_qa_tool_selection") or {}).get("mode") == "none"))\n'
        '            if object_confirmation["state"] == "confirmed_data_object":\n'
        '                execution_question = object_confirmation["execution_question"]\n'
        '                task_plan = object_confirmation["task_plan"]\n'
        '                context_instruction = str(task_plan.get("instruction_text") or "")\n'
        '            tool_context = update_tool_context(\n'
        '                None if context_forbidden or object_confirmation["state"] == "confirmed_data_object" else previous_tool_context,\n')
    assert changed.count(before) == 1
    changed = changed.replace(before, after)
    before = '            task_plan = followup_resolution["task_plan"]\n'
    after = (
        '            if object_confirmation["state"] in {"confirmed_data_object", "needs_clarification"}:\n'
        '                followup_resolution = {key: object_confirmation[key]\n'
        '                    for key in ("state", "task_plan", "outcome")}\n'
        '                if object_confirmation.get("pending_context"):\n'
        '                    tool_context.update(object_confirmation["pending_context"])\n'
        '            tool_context = qa_task_plan.pending_data_object_context(tool_context, followup_resolution)\n'
        '            task_plan = followup_resolution["task_plan"]\n')
    assert changed.count(before) == 1
    changed = changed.replace(before, after)
    current = ast.parse(changed)
    prepare = [n for n in ast.walk(original) if isinstance(n, ast.FunctionDef) and n.name == 'prepare_qa_chat']
    assert len(prepare) == 1
    count = 0
    class Restore(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            nonlocal count
            if node.name == 'prepare_qa_chat':
                count += 1
                return copy.deepcopy(prepare[0])
            return self.generic_visit(node)
    restored = Restore().visit(current)
    assert count == 1 and stable_ast_dump(original) == stable_ast_dump(restored)
    return changed


def main(revision):
    target = ROOT / '.codex_runtime/qa-routing-v50' / ('candidate-' + revision)
    assert not target.exists(), 'Never overwrite or replay a frozen revision'
    raw_manifest = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(raw_manifest).hexdigest() == PRIOR_SHA
    previous = json.loads(raw_manifest)
    payloads = {name: (PRIOR / name).read_bytes() for name in previous['files']}
    assert all(hashlib.sha256(raw).hexdigest() == previous['files'][name]['sha256']
               for name, raw in payloads.items())
    planner = (ROOT / '高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes()
    validate_planner(payloads['qa_task_plan.py'], planner)
    payloads['qa_task_plan.py'] = planner
    payloads['ollama_proxy_server.py'] = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw, filename=name)
    inherited = sorted(set(payloads) - {'qa_task_plan.py', 'ollama_proxy_server.py'})
    assert len(payloads) == 16 and len(inherited) == 14
    manifest = {**previous, 'candidate': 'v50-' + revision, 'prior_manifest_sha256': PRIOR_SHA,
        'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
        'inherited_v49_files_byte_identical': inherited, 'pending_object_confirmation': True,
        'pending_task_ttl_seconds': 600, 'pending_object_proxy_changed_functions': ['prepare_qa_chat'],
        'production_writes': 0, 'model_operations': 0}
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert all(manifest[k] is False for k in ('model_switch_allowed', 'fallback_model_allowed', 'same_name_weight_replacement_allowed'))
    target.mkdir(parents=True)
    for name, raw in payloads.items():
        with (target / name).open('xb') as stream:
            stream.write(raw)
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'ok': True, 'candidate': manifest['candidate'], 'files': 16, 'inherited': 14,
        'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'production_sealed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=tuple('r' + str(i) for i in range(1, 21)), default='r1')
    main(parser.parse_args().revision)
