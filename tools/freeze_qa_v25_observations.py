"""Freeze one reviewed V25 failure and every proven-unsent dependency record."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v25'
    plan_path = runtime / 'failure-round.plan.private.json'
    plan = load(plan_path)
    recovery = load(runtime / 'release/readonly-recovery.json')
    snapshot = load(runtime / 'snapshots/results.private.json')
    artifact = load(runtime / 'release/chart-artifact-evidence.json')
    case_id = 'TPL-C5DF79304112ED85'
    rows, progress = snapshot['rows'], snapshot['progress']
    if (not recovery['ok'] or not recovery['process_absent'] or recovery['claim_case_ids'] != [case_id]
            or len(rows) != 1 or rows[0]['case_id'] != case_id or progress['completed'] != 1
            or progress['requests'] != 1 or progress['state'] != 'blocked'
            or recovery['plan_sha256'] != hashlib.sha256(plan_path.read_bytes()).hexdigest()
            or recovery['head'] != plan['production_commit']):
        raise ValueError('Uncertain evidence; do not replay')
    row = rows[0]
    if row['question'] != plan['cases'][0]['prompt'] or row['request_count'] != 1 or not row['done']:
        raise ValueError('Question or transport binding mismatch')
    if artifact['artifact_series_count'] != 16 or len(artifact['requested_variables']) != 18 or artifact['image_http_status'] != 200:
        raise ValueError('Independent chart evidence changed')
    observation = {'schema': 'bf.qa.paired-observations.v1', 'checked_at': '2026-09-17',
        'version': 'v25', 'production_commit': plan['production_commit'], 'planned': 822,
        'attempted': 1, 'transport_complete': 1, 'passed': 0, 'partial': 0, 'failed': 1,
        'proven_unsent': 821, 'stable_model_samples': 0, 'full_dataset_accuracy_available': False,
        'accuracy_scope': 'One reviewed actual failure; post-turn model identity not verified. No overall gain or fixed-model causal comparison claim.',
        'initial_failed': 637, 'initial_partial': 185,
        'rows': [{'case_id': case_id, 'status': 'failed', 'before_v24': 'failed',
            'result_sha256': row['result_file_sha256'], 'original_prompt_sha256': plan['cases'][0]['original_prompt_sha256'],
            'seconds': row['elapsed_seconds'], 'actual_tool_calls': len(row['tool_starts']),
            'route': row['final']['answer_route'], 'model_digest_before': progress['results'][0]['before_identity']['digest'],
            'model_identity_after': 'drift_or_unavailable', 'requested_objects': 18, 'artifact_objects': 16,
            'missing_objects': artifact['missing_requested_variables'], 'artifact_http_ok': True,
            'artifact_data_sha256': artifact['artifact_data_sha256'], 'artifact_image_sha256': artifact['artifact_image_sha256'],
            'final_chart_not_delivered': True, 'issue_ids': ['QAOPT-R03', 'QAOPT-E01', 'QAOPT-E05', 'QAOPT-O01', 'QAOPT-O03'],
            'reason': 'Route correctly requested all eighteen points; MCP silently limited output to sixteen. Chart artifact exists and responds HTTP200, but final lifecycle fallback omitted both chart and facts. Cannot count nonempty response as success.'}]}
    dependencies = {'schema': 'bf.qa.unattempted-dependencies.v1', 'version': 'v25',
        'production_commit': plan['production_commit'], 'plan_sha256': recovery['plan_sha256'],
        'sent': 1, 'proven_unsent': 821, 'automatic_post_retries': 0,
        'proof': 'Exited batch PID and exact single claim/result set read independently; remaining IDs have no claim/result.',
        'rows': [{'case_id': c['case_id'], 'original_prompt_sha256': c['original_prompt_sha256'],
                  'initial_status': c['initial_semantic_status'], 'status': 'dependency_blocked_proven_unsent',
                  'reason': 'frozen_model_identity_drift_or_unavailable', 'automatic_replay': False}
                 for c in plan['cases'] if c['case_id'] != case_id]}
    if len(dependencies['rows']) != 821:
        raise ValueError('Proven unsent count mismatch')
    public = ROOT / 'tests/qa_regression'
    write(public / 'routing_v25_paired_observations_20260917.json', observation)
    write(public / 'routing_v25_unattempted_dependencies_20260917.json', dependencies)
    print(json.dumps({'ok': True, 'attempted': 1, 'failed': 1, 'proven_unsent': 821, 'all_case_ids_accounted': True}))


if __name__ == '__main__':
    main()
