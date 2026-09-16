"""Bind verified read-only evidence to a registered release recipe locally."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('v21','v22','v23','v24'), required=True)
    args = parser.parse_args()
    release = ROOT/f'.codex_runtime/qa-routing-{args.version}/release'
    baseline = json.loads((release/'readonly-baseline.json').read_text(encoding='utf-8'))
    evidence = json.loads((release/'git-recordability.json').read_text(encoding='utf-8'))
    expectation = json.loads((release/'recordability-expectation.json').read_text(encoding='utf-8'))
    if not (baseline['ok'] and baseline['head_match'] and not baseline['dirty_scope']
            and all(row['match'] for row in baseline['dependencies'])
            and all(row['sha_match'] for row in baseline['compile_checks'])
            and evidence['ok'] and evidence['action']=='recordable'
            and evidence['expected_head']==expectation['expected_head']
            and set(evidence['changed_paths'])==set(expectation['targets'])
            and all(evidence['candidate_hashes'][path].lower()==row['sha256'].lower()
                    for path,row in expectation['targets'].items())):
        raise ValueError('Preflight evidence is not a verified release match')
    registry=ROOT/'tools/qa_routing_release_extensions.json'
    recipes=json.loads(registry.read_text(encoding='utf-8'))
    for validation in recipes[args.version]['validations']:
        if validation['id']=='remote-readonly-preflight':
            validation.update(status='passed',evidence='Exact HEAD/dependency hashes/scoped clean and staged Python3.11 compile; candidate recordability verified; no EOL migration')
    registry.write_bytes((json.dumps(recipes,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok':True,'version':args.version}))


if __name__=='__main__':main()
