"""Merge exactly the pinned public ABC33 delta into the complete V46 closure."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from probe_qa_shared_proxy_delta_readonly import IMPORT, SYMBOLS, prove_delta, selected, stable_ast_dump

if not __debug__:
    raise RuntimeError('Frozen candidate guards require Python assertions enabled')

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v46/candidate-r2'
PRIOR_SHA = 'a98a564b758a2e9dbb6640c81d1d04f6cb921030b0ebf2d4ae49d64f15867a6a'
EVIDENCE = ROOT / '.codex_runtime/qa-full-import-20260917/shared-fragments-v2.private.json'
EVIDENCE_SHA = 'dda1d2fce703923bc484146583db6702d6786700e21efe2e15f38efd8df9e1c7'
HEAD = 'cdd390cc386ce486d8a4685ebe060b8eeda7c38a'
PROXY_SHA = 'd84cfe9d67ded7344e9c15b9de10c807d6d3846fc872b8f53d66b8bfaffe8382'
PINS = {
 '高炉前端数据/智能助手/backend/furnace_display_policy.py': '494e24e76180d1a05aa70225a07355040e088a3a372f4ab395f0e6ef3c453f7d',
 '高炉前端数据/智能助手/backend/abc_score_explanation.py': '51cd8030f014c81de1824b452369ee474a90cb09a192b1d0e5a938926b1b98bd'}


def validate_fragments(evidence):
    assert evidence.get('schema') == 'bf.qa.shared-proxy-fragments.v2'
    assert evidence.get('before') == 'df9dde1abe06b386906a2bfad508403732fd40ae'
    assert evidence.get('after') == HEAD and evidence.get('after_proxy_sha256') == PROXY_SHA
    assert evidence.get('before_proxy_sha256') == '47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431'
    assert evidence.get('new_import') == IMPORT and evidence.get('dependency_hashes') == PINS
    assert evidence.get('whole_ast_delta_covered') is True
    assert evidence.get('before_ast_sha256') == evidence.get('normalized_after_ast_sha256') == '9120e434b03e6172e7467a57a3a38bcfa2e2a616c97bfb78d31b03a2411a1bc4'
    assert evidence.get('deployment_authorized') is False
    assert all(type(evidence.get(key)) is int and evidence[key] == 0
        for key in ('production_writes', 'model_calls', 'question_posts'))
    for version in ('old', 'new'):
        rows = evidence.get(version) or {}
        assert set(rows) == SYMBOLS
        for key, row in rows.items():
            assert set(row) == {'source', 'ast_sha256'} and '\r' not in row['source']
            # Dedenting a method also changes indentation inside triple-quoted
            # string values. Parse in its class scope to preserve exact semantics.
            tree = ast.parse(('class Handler:\n' if key.startswith('Handler.') else '') + row['source'])
            if key.startswith('Handler.'):
                assert len(tree.body) == 1 and isinstance(tree.body[0], ast.ClassDef) and tree.body[0].name == 'Handler'
                nodes = tree.body[0].body
            else:
                nodes = tree.body
            assert len(nodes) == 1 and isinstance(nodes[0], ast.FunctionDef) and nodes[0].name == key.split('.')[-1]
            assert hashlib.sha256(stable_ast_dump(nodes[0]).encode()).hexdigest() == row['ast_sha256']


def build_proxy(text, evidence):
    validate_fragments(evidence)
    current = selected(text)
    assert all(current[name]['ast_sha256'] == evidence['old'][name]['ast_sha256'] for name in SYMBOLS), 'Shared symbol conflict; review instead of overwrite'
    tree = ast.parse(text)
    positions = {}
    def visit(body, prefix=''):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = prefix + node.name
                if key in SYMBOLS:
                    assert key not in positions
                    positions[key] = (min([node.lineno] + [n.lineno for n in getattr(node, 'decorator_list', [])]) - 1, node.end_lineno)
                if isinstance(node, ast.ClassDef): visit(node.body, key + '.')
    visit(tree.body)
    assert set(positions) == SYMBOLS
    lines = text.splitlines(keepends=True)
    for key in sorted(positions, key=lambda name: positions[name][0], reverse=True):
        start, end = positions[key]
        lines[start:end] = [evidence['new'][key]['source']]
    changed = ''.join(lines)
    anchor = 'from abc_score_explanation import build_score_explanation, build_trend_point_evidence\n'
    assert changed.count(anchor) == 1 and IMPORT not in changed
    changed = changed.replace(anchor, anchor + IMPORT + '\n')
    assert prove_delta(text, changed)['whole_ast_delta_covered']
    assert selected(changed) == evidence['new']
    return changed


def main(revision):
    target = ROOT / '.codex_runtime/qa-routing-v47' / ('candidate-' + revision)
    assert not target.exists()
    raw = EVIDENCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EVIDENCE_SHA
    evidence = json.loads(raw)
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(prior_raw).hexdigest() == PRIOR_SHA
    prior = json.loads(prior_raw)
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, value in payloads.items():
        assert hashlib.sha256(value).hexdigest() == prior['files'][name]['sha256']
    payloads['ollama_proxy_server.py'] = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8'), evidence).encode('utf-8')
    inherited = sorted(set(payloads) - {'ollama_proxy_server.py'})
    assert len(payloads) == 16 and len(inherited) == 15
    for name, value in payloads.items():
        assert b'\r' not in value and not value.startswith(b'\xef\xbb\xbf')
        ast.parse(value.decode('utf-8'), filename=name)
    metadata = {**prior, 'candidate': 'v47-' + revision, 'prior_manifest_sha256': PRIOR_SHA,
        'files': {name: {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)} for name, value in sorted(payloads.items())},
        'inherited_v46_files_byte_identical': inherited,
        'shared_proxy_integration': {'production_head': HEAD, 'production_proxy_sha256': PROXY_SHA,
            'evidence_sha256': EVIDENCE_SHA, 'symbols': sorted(SYMBOLS), 'whole_ast_delta_covered': True},
        'runtime_dependency_pins': PINS, 'shared_proxy_rebase_required': False,
        'additional_runtime_read_set': sorted(set(prior['additional_runtime_read_set']) | {Path(name).name for name in PINS}),
        'production_dependency_refresh_required': True, 'production_writes': 0, 'model_operations': 0}
    metadata.pop('inherited_v45_files_byte_identical', None)
    assert metadata['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(metadata[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    target.mkdir(parents=True)
    for name, value in payloads.items():
        with (target / name).open('xb') as stream: stream.write(value)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as stream: stream.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 16, 'inherited': 15,
        'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'production_sealed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=('r1', 'r2', 'r3', 'r4'), default='r1')
    main(parser.parse_args().revision)
