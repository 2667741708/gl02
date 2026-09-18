"""Freeze literal-vector scope on V50; no production or model operations."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

from probe_qa_shared_proxy_delta_readonly import stable_ast_dump

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v50/candidate-r3'
PRIOR_SHA = '0b30d0f39df03eeee14e9660252398454f434d8e233fea13850a11aecf23c8d0'
CHANGED_FUNCTIONS = {'instruction_clauses', '_declared_input_clause'}
ADDED_BINDINGS = {'_VECTOR_VALUE', '_NUMERIC_VECTOR_PATTERN', '_VECTOR_QUESTION_SUFFIX'}


def validate_planner(before, after):
    old, current = ast.parse(before), ast.parse(after)
    old_functions = {node.name: node for node in old.body if isinstance(node, ast.FunctionDef)}
    bindings = lambda node: (node.targets[0].id if isinstance(node, ast.Assign)
                            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) else None)
    old_version = next(node for node in old.body if bindings(node) == 'VERSION')
    restored=[]
    seen=set()
    for node in current.body:
        name=bindings(node)
        if name in ADDED_BINDINGS:
            assert name not in seen
            seen.add(name)
        elif name == 'VERSION':
            assert ast.literal_eval(node.value) == 'qa-task-plan-v10-numeric-vector-scope'
            restored.append(copy.deepcopy(old_version))
        elif isinstance(node, ast.FunctionDef) and node.name in CHANGED_FUNCTIONS:
            restored.append(copy.deepcopy(old_functions[node.name]))
        else:
            restored.append(node)
    current.body=restored
    assert seen == ADDED_BINDINGS
    assert stable_ast_dump(old) == stable_ast_dump(current), 'Unreviewed planner change'


def main(revision):
    if not __debug__:
        raise RuntimeError('Candidate assertions must be enabled')
    target = ROOT / '.codex_runtime/qa-routing-v51' / ('candidate-' + revision)
    assert not target.exists(), 'Never overwrite a frozen candidate'
    raw_manifest=(PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(raw_manifest).hexdigest() == PRIOR_SHA
    previous=json.loads(raw_manifest)
    payloads={name:(PRIOR / name).read_bytes() for name in previous['files']}
    assert len(payloads) == 16
    for name, raw in payloads.items():
        assert Path(name).name == name
        assert hashlib.sha256(raw).hexdigest() == previous['files'][name]['sha256']
    planner=(ROOT / '高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes()
    validate_planner(payloads['qa_task_plan.py'], planner)
    payloads['qa_task_plan.py']=planner
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw, filename=name)
    inherited=sorted(set(payloads)-{'qa_task_plan.py'})
    manifest={**previous,'candidate':'v51-'+revision,'prior_manifest_sha256':PRIOR_SHA,
              'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
                       for name,raw in sorted(payloads.items())},
              'inherited_v50_files_byte_identical':inherited,
              'numeric_vector_input_scope':True,'numeric_vector_changed_functions':sorted(CHANGED_FUNCTIONS),
              'production_writes':0,'model_operations':0}
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert all(manifest[key] is False for key in ('model_switch_allowed','fallback_model_allowed','same_name_weight_replacement_allowed'))
    target.mkdir(parents=True)
    for name,raw in payloads.items():
        with (target / name).open('xb') as stream: stream.write(raw)
    raw=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as stream: stream.write(raw)
    print(json.dumps({'ok':True,'candidate':manifest['candidate'],'files':16,'inherited':15,
                      'manifest_sha256':hashlib.sha256(raw).hexdigest(),'production_sealed':False}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision',choices=tuple('r'+str(i) for i in range(1,21)),default='r1')
    main(parser.parse_args().revision)
