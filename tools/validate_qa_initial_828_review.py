"""Validate scope and privacy of a completed initial-828 semantic review offline."""
import argparse
from collections import Counter
import json
from pathlib import Path

from audit_qa_staged_publication import private_keys

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {'passed', 'partial', 'failed', 'oracle_blocked', 'insufficient_evidence'}


def validate(report_path):
    ledger = json.loads((ROOT / 'tests/qa_regression/question_ledger_20260916.json').read_text(encoding='utf-8-sig'))
    expected = {row['case_id']: row for row in ledger['rows']
                if row['collection_status'] == 'collected'
                and row['answer_review_status'] == 'pending_semantic_review'}
    if len(expected) != 828:
        raise ValueError('Initial pending-review scope changed')
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    rows = report.get('reviews', report.get('rows', []))
    ids = [row['case_id'] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('Review must include exactly the original 828 unique cases')
    for row in rows:
        if row.get('status', row.get('state')) not in STATUSES:
            raise ValueError('Unrecognized semantic result: ' + row['case_id'])
        if row.get('result_sha256', row.get('original_result_sha256')) != expected[row['case_id']]['result_sha256']:
            raise ValueError('Initial result hash mismatch: ' + row['case_id'])
    prohibited = private_keys(report)
    if prohibited:
        raise ValueError('Private fields in public report: ' + ','.join(sorted(prohibited)))
    counts = Counter(row.get('status', row.get('state')) for row in rows)
    return {'ok': True, 'reviewed': len(rows), 'remaining': 0, 'counts': dict(counts),
            'scope_and_hashes_verified': True, 'semantic_rejudgment_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.report), ensure_ascii=False))


if __name__ == '__main__':
    main()
