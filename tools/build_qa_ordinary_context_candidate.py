"""Gate ordinary sensor preparation and retain explicitly requested ABC authority."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

from probe_qa_shared_proxy_delta_readonly import stable_ast_dump

if not __debug__:
    raise RuntimeError('Ordinary context candidate requires assertions enabled')
ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v47/candidate-r1'
PRIOR_SHA = '3deab6a3937a3a2afab099b0cabea0277c507176bf326f2529845a24116defe6'
HELPERS = {'sensor_context_policy', 'bound_rule_context_requested'}


def build_proxy(text):
    before = ast.parse(text)
    changed = text
    replacements = [
        ('            sensor_context_enabled = (not source_task_plan.get("no_live_lookup")\n'
         '                and not qa_evidence_policy.code_request_only(question))\n',
         '            sensor_policy = qa_task_plan.sensor_context_policy(\n'
         '                source_task_plan, code_only=qa_evidence_policy.code_request_only(question))\n'
         '            sensor_context_enabled = sensor_policy["enabled"]\n'),
        ('                trend_meta = {"sensor_context_skipped": True, "sensor_context_skip_reason": "source_policy"}\n',
         '                trend_meta = {"sensor_context_skipped": True, "sensor_context_skip_reason": sensor_policy["reason"]}\n'),
        ('                "sensor_context_policy": {"schema": "qa-sensor-context-source-gate-v1",\n'
         '                    "enabled": bool(sensor_context_enabled), "skipped": not sensor_context_enabled},\n',
         '                "sensor_context_policy": dict(sensor_policy),\n'),
        ('    if source_messages is not None:\n        return source_messages\n',
         '    if source_messages is not None:\n'
         '        if assistant_rule_context and qa_task_plan.bound_rule_context_requested(question):\n'
         '            source_messages[0]["content"] += (\n'
         '                "\\n\\n【本对话绑定的ABC规则权威上下文】\\n"\n'
         '                "该上下文由服务端按会话来源加载，解释所指规则必须以它为准；"\n'
         '                "仅对应绑定批次，不能代表其后现场变化，不以聊天断言或浏览器数值覆盖。"\n'
         '                "可以解释合同已公开的公式项、权重、归一化分和加权得分，"\n'
         '                "仍不得暴露程序实现或未公开字段。\\n" + assistant_rule_context)\n'
         '        return source_messages\n'),
    ]
    for old, new in replacements:
        assert changed.count(old) == 1, 'Expected unique frozen patch anchor'
        changed = changed.replace(old, new)
    after = ast.parse(changed)
    old_functions = {n.name: n for n in ast.walk(before) if isinstance(n, ast.FunctionDef)
        and n.name in {'prepare_qa_chat', 'build_hidden_qa_messages'}}
    assert len(old_functions) == 2
    seen = set()
    class Restore(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name in old_functions:
                assert node.name not in seen
                seen.add(node.name)
                return copy.deepcopy(old_functions[node.name])
            return self.generic_visit(node)
    normalized = Restore().visit(after)
    assert seen == set(old_functions) and stable_ast_dump(before) == stable_ast_dump(normalized)
    return changed


def validate_planner(before, after):
    old, new = ast.parse(before), ast.parse(after)
    additions = [n for n in new.body if isinstance(n, ast.FunctionDef) and n.name in HELPERS]
    assert len(additions) == 2 and {n.name for n in additions} == HELPERS
    assert not any(isinstance(n, ast.FunctionDef) and n.name in HELPERS for n in old.body)
    new.body = [n for n in new.body if n not in additions]
    assert stable_ast_dump(old) == stable_ast_dump(new), 'Existing task planning changed unexpectedly'


def main(revision):
    target = ROOT / '.codex_runtime/qa-routing-v48' / ('candidate-' + revision)
    assert not target.exists()
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(prior_raw).hexdigest() == PRIOR_SHA
    prior = json.loads(prior_raw)
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    assert all(hashlib.sha256(raw).hexdigest() == prior['files'][name]['sha256'] for name, raw in payloads.items())
    planner = (ROOT / '高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes()
    validate_planner(payloads['qa_task_plan.py'], planner)
    payloads['qa_task_plan.py'] = planner
    payloads['ollama_proxy_server.py'] = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    inherited = sorted(set(payloads) - {'ollama_proxy_server.py', 'qa_task_plan.py'})
    assert len(payloads) == 16 and len(inherited) == 14
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    metadata = {**prior, 'candidate': 'v48-' + revision, 'prior_manifest_sha256': PRIOR_SHA,
        'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
        'inherited_v47_files_byte_identical': inherited, 'changed_modules': ['ollama_proxy_server.py', 'qa_task_plan.py'],
        'sensor_context_gate': 'qa-sensor-context-source-gate-v2',
        'gate_scope': 'explicit_task_plan_live_source_grant_only',
        'bound_rule_authority_retained_for_explicit_rule_question': True,
        'request_page_snapshot_archival_preserved': True, 'production_writes': 0, 'model_operations': 0}
    metadata.pop('inherited_v46_files_byte_identical', None)
    metadata.pop('nonrestricted_ordinary_and_abc_followup_path_unchanged', None)
    assert metadata['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(metadata[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    target.mkdir(parents=True)
    for name, raw in payloads.items():
        with (target / name).open('xb') as f: f.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as f: f.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 16, 'inherited': 14,
        'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'production_sealed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=('r1', 'r2', 'r3', 'r4'), default='r1')
    main(parser.parse_args().revision)
