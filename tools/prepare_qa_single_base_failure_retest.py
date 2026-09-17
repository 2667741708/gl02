"""Freeze unchanged first-collection failures for a single e4 base; never send requests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PIN = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
UNKNOWN = 'TPL-10C8C8FAF2C694EF'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(root: Path, snapshot: Path, output: Path, round_name: str = 'paired-v26-single-base-20260917-r4') -> dict:
    previous = root / '.codex_runtime/qa-routing-v26/failure-round.plan.private.json'
    summary_path = root / 'tests/qa_regression/initial_semantic_summary_20260917.json'
    plan = json.loads(previous.read_text(encoding='utf-8-sig'))
    summary = json.loads(summary_path.read_text(encoding='utf-8-sig'))
    current = json.loads(snapshot.read_text(encoding='utf-8-sig'))
    recovery = current['predecessor_recovery']
    if (recovery['plan_sha256'] != sha(previous) or
            recovery['old_batch_running'] is not False or
            recovery['requests'] != 0 or recovery['completed'] != 0 or
            recovery['claim_ids'] or recovery['result_ids'] or
            current['retired_r2_output_exists'] is not False):
        raise ValueError('Fresh read-only recovery does not prove all predecessor cases unsent')
    expected = {r['case_id']: r for r in summary['rows'] if r['status'] in {'failed', 'partial'}}
    ids = [r['case_id'] for r in plan['cases']]
    if len(ids) != 822 or len(set(ids)) != 822 or set(ids) != set(expected) or UNKNOWN in ids:
        raise ValueError('Unexpected first-collection cohort; uncertain originals excluded')
    if plan['initial_semantic_summary_sha256'] != sha(summary_path):
        raise ValueError('First-collection adjudication changed')
    for case in plan['cases']:
        initial = expected[case['case_id']]
        if (hashlib.sha256(case['prompt'].encode('utf-8')).hexdigest() != initial['original_prompt_sha256'] or
                case['previous_result_sha256'] != initial['original_result_sha256']):
            raise ValueError('Original prompt/result binding changed')
    if set(current['runtime_hashes']) != set(plan['runtime_hashes']):
        raise ValueError('Incomplete production runtime snapshot')
    for value in [current['production_commit'], current['catalog_sha256'], *current['runtime_hashes'].values()]:
        size = 40 if value == current['production_commit'] else 64
        if len(value) != size or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid frozen production hash')
    plan.update(
        phase='after-v26-single-base-manager-r5', round=round_name,
        production_commit=current['production_commit'], runtime_hashes=current['runtime_hashes'],
        catalog_sha256=current['catalog_sha256'],
        collector_sha256=sha(root / 'tools/run_qa_live_case.py'),
        model_identity={'name': 'chiqiongblastfuenace:latest', 'digest': PIN, 'approved_digests': [PIN]},
        predecessor_frozen_plan_sha256=sha(previous), readonly_snapshot_sha256=sha(snapshot),
        comparison_scope='Current V26 application and installed manager r5; one identical frozen base. No V50 deployment claim.',
        first_collection_counts=summary['counts'],
        policy='Only original failed/partial prompts. One POST per case. Full frozen alias/resident identity before and after every turn. Stop on uncertainty or drift; no replay. Nonempty answers require independent semantic review.',
    )
    for obsolete in ('original_first_eight', 'oracle_blocked_attempts', 'v22_reproduced_extra',
                     'v23_preceding_version_confirmed_failed'):
        plan.pop(obsolete, None)
    # This is preparation only. Runtime identity must pass fresh gates before any POST.
    manifest = {'schema': 'bf.qa.single-base-retest-preparation.v1', 'total': len(ids),
                'first_collection_failed': summary['counts']['failed'],
                'first_collection_partial': summary['counts']['partial'],
                'model_digest': PIN, 'requests_sent': 0, 'production_identity_verified': False,
                'automatic_replay': False, 'snapshot_sha256': sha(snapshot),
                'production_commit': current['production_commit'],
                'application_version': 'V26', 'manager_operation': 'single-base-20260917-r5'}
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'templates.remaining.plan.private.json'
    target.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    manifest['plan_sha256'] = sha(target)
    (output / 'preparation.manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--round-name', default='paired-v26-single-base-20260917-r4')
    args = parser.parse_args()
    print(json.dumps(freeze(args.root, args.snapshot, args.output, args.round_name)))
