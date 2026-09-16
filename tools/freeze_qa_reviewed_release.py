"""Freeze explicit independent semantic decisions across once-only continuation batches."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--round', type=Path, action='append', required=True)
    parser.add_argument('--decision', action='append', required=True, help='case_id=passed|answer_contract_failed')
    parser.add_argument('--focused-tests', type=int, required=True)
    args = parser.parse_args()
    decisions = dict(item.split('=', 1) for item in args.decision)
    if len(decisions) != len(args.decision) or set(decisions.values()) - {'passed', 'answer_contract_failed'}:
        raise ValueError('Invalid or duplicate independent decisions')
    rows, claims, request_count = {}, set(), 0
    for directory in args.round:
        progress = json.loads((directory / 'progress.json').read_text(encoding='utf-8'))
        if progress.get('automatic_retries') != 0: raise ValueError('Automatic POST replay prohibited')
        request_count += progress['requests']
        for path in directory.glob('*.claim'):
            if path.stem in claims: raise ValueError('Duplicate claim across continuation batches')
            claims.add(path.stem)
        for path in directory.glob('TPL-*.json'):
            row = json.loads(path.read_text(encoding='utf-8'))
            case_id = row['case_id']
            if case_id in rows or not row.get('determinate') or row.get('request_count') != 1:
                raise ValueError('Uncertain, duplicated or replayed result')
            final = row.get('final') or {}
            rows[case_id] = {'case_id': case_id, 'state': decisions.get(case_id),
                'answer_sha256': hashlib.sha256((row.get('answer') or '').encode('utf-8')).hexdigest(),
                'answer_chars': len(row.get('answer') or ''), 'request_count': 1,
                'sse_done': bool(row.get('terminated')), 'route': final.get('answer_route'),
                'terminal_state': (final.get('completion') or {}).get('terminal_state'),
                'model_request_count': final.get('model_request_count'),
                'tool_start_count': len(row.get('tool_starts') or []),
                'message_count': len(final.get('messages') or []),
                'messages_projection': final.get('messages_projection')}
    if set(rows) != set(decisions) or claims != set(rows) or request_count != len(rows):
        raise ValueError('Every POST claim needs exactly one result and independent decision')
    activation = json.loads((ROOT / f'.codex_runtime/qa-routing-{args.version}/release/frozen-activation.json').read_text(encoding='utf-8'))
    payload = {'schema': 'bf.qa.routing-production-review.v1', 'checked_at': '2026-09-16',
        'requirement_id': 'REQ-QA-FULL-ISSUE-INVENTORY-20260916', 'version': args.version,
        'production_commit': args.commit, 'focused_tests_passed': args.focused_tests,
        'requests': request_count, 'automatic_post_retries': 0,
        'counts': {state: sum(row['state'] == state for row in rows.values()) for state in sorted(set(decisions.values()))},
        'review_method': 'Explicit independent post-release semantic review; nonempty and SSE done do not imply passing.',
        'results': list(rows.values()), 'deployment': activation,
        'privacy': 'No raw answers, conversation payloads, production measurements or identities.'}
    output = ROOT / f'tests/qa_regression/routing_{args.version}_production_review_20260916.json'
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'requests': request_count, 'counts': payload['counts']}))

if __name__ == '__main__': main()
