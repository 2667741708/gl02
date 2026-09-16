"""Apply reviewed exact edits to a hash-bound live baseline, preserving other code."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path


def build(baseline, rules, output):
    raw = baseline.read_bytes()
    spec = json.loads(rules.read_text(encoding='utf-8'))
    if hashlib.sha256(raw).hexdigest() != spec['baseline_sha256']:
        raise ValueError('Live baseline hash changed; review a new candidate')
    source = raw.decode('utf-8')
    candidate = source
    for change in spec['edits']:
        count = candidate.count(change['old'])
        if count != 1:
            raise ValueError(f'Expected one match, found {count}: {change["old"][:100]}')
        candidate = candidate.replace(change['old'], change['new'], 1)
    if '\r' in candidate or candidate.startswith('\ufeff'):
        raise ValueError('Candidate must be UTF-8 LF without BOM')
    ast.parse(candidate)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'ollama_proxy_server.py').write_bytes(candidate.encode('utf-8'))
    policy = Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend/qa_evidence_policy.py'
    ast.parse(policy.read_text(encoding='utf-8'))
    (output / policy.name).write_bytes(policy.read_bytes())
    diff = ''.join(difflib.unified_diff(source.splitlines(True), candidate.splitlines(True),
                                      fromfile='live/ollama_proxy_server.py', tofile='candidate/ollama_proxy_server.py'))
    (output / 'proxy.patch').write_bytes(diff.encode('utf-8'))
    report = {'requirement_id': spec['requirement_id'], 'baseline_sha256': spec['baseline_sha256'],
              'candidate_sha256': hashlib.sha256(candidate.encode('utf-8')).hexdigest(),
              'edits': len(spec['edits']), 'syntax': 'passed', 'production_changed': False}
    (output / 'build.json').write_bytes((json.dumps(report, indent=2) + '\n').encode('utf-8'))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--rules', type=Path, default=Path(__file__).with_name('qa_evidence_candidate_changes.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.baseline, args.rules, args.output), ensure_ascii=False))
