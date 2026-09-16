"""Freeze reviewed V24 observations and every proven-unsent dependency record."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = {
    'TPL-BE97AA4EAD567003': ('partial', '最新温度事实保留；单位未登记，不能记完整通过。'),
    'TPL-A60B0CD794D49E48': ('passed', '压力实际值、时刻、只读来源与规范单位血缘完整，未重复规划或模型调用。'),
    'TPL-C5DF79304112ED85': ('failed', '无代码承诺，但0工具且错误否认已有数据库和绘图能力；completed不能代表通过。'),
    'TPL-FACD6F5FE05C74FC': ('partial', '三对象同窗真实统计保留；上下压差单位缺失，缺少直接比较结论及总压差单位血缘披露。'),
    'TPL-01EEE414179DB624': ('partial', '真实统计与条件解释保留；单位和阈值未核实，忽略Held质量，微小变化舍入为零却保留方向；结尾未完成且模型身份后采样无法核实。'),
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v24'
    plan = load(runtime / 'failure-round.plan.private.json')
    progress = load(runtime / 'snapshots/progress.json')
    recovery = load(runtime / 'release/readonly-recovery.json')
    if progress['state'] != 'blocked' or progress['automatic_retries'] != 0:
        raise ValueError('Expected stopped no-replay round')
    cases = {row['case_id']: row for row in plan['cases']}
    claims = {row['case_id']: row for row in recovery['claims']}
    observed = {row['case_id']: row for row in progress['results']}
    if len(cases) != 407 or set(claims) != set(observed) or set(observed) != set(DECISIONS):
        raise ValueError('Every send must have exactly one observation and manual decision')
    if recovery['head'] != plan['production_commit'] or '10388' in recovery['process']:
        raise ValueError('Recovery must prove the old batch has exited without version drift')
    rows = []
    for caseid, entry in observed.items():
        path = runtime / 'snapshots' / (caseid + '.json')
        row = load(path)
        original_hash = hashlib.sha256(cases[caseid]['prompt'].encode('utf-8')).hexdigest()
        if row['case_id'] != caseid or row['request_count'] != 1 or not row['terminated'] or row.get('transport_error'):
            raise ValueError('Uncertain or duplicate result')
        if claims[caseid]['prompt_sha256'] != original_hash:
            raise ValueError('Original question changed')
        final = row['final']
        state, reason = DECISIONS[caseid]
        rows.append({'case_id': caseid, 'review_state': state, 'review_reason': reason,
            'original_prompt_sha256': original_hash, 'result_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'answer_sha256': hashlib.sha256(row['answer'].encode('utf-8')).hexdigest(),
            'request_count': 1, 'sse_done': True, 'seconds': row['elapsed_seconds'],
            'answer_route': final.get('answer_route'), 'model_request_count': final.get('model_request_count'),
            'additional_tool_start_count': len(row.get('tool_starts') or []),
            'terminal_state': (final.get('completion') or {}).get('terminal_state'),
            'post_turn_identity': entry.get('post_turn_identity')})
    stable = [row for row in rows if row['post_turn_identity'] == 'matched']
    passed = sum(row['review_state'] == 'passed' for row in stable)
    evidence = {'schema': 'bf.qa.routing-paired-observations.v1', 'checked_at': '2026-09-17',
        'version': 'v24', 'production_commit': plan['production_commit'], 'focused_tests_passed': 76,
        'planned': 407, 'requests': 5, 'sse_done': 5, 'automatic_post_retries': 0,
        'counts': dict(Counter(row['review_state'] for row in rows)), 'stable_sample': len(stable),
        'stable_sample_correct_complete': passed, 'stable_sample_correct_complete_rate': passed / len(stable),
        'full_dataset_accuracy_available': False, 'state': 'blocked_model_identity_after_fifth_result',
        'not_sent': 402, 'review_method': 'Root full original-question/final-answer/tool-evidence review; source facts compared with successful tool output, finite values/time/object/source/unit checked; raw series not independently re-queried; nonempty/terminal status are not semantic pass.',
        'deployment': {'accepted': True, 'rollback_applied': False, 'guard_restored': True,
            'old_8093_pid': 19444, 'new_8093_pid': 8396, 'http_8093': 200, 'protected_pids_unchanged': True,
            'production_version_ref': 'refs/prod-8093/20260917/qa-routing-v24-20260916-r1'},
        'results': rows, 'privacy': 'No raw questions, answers, production measurements, identities or credentials.'}
    dependencies = {'schema': 'bf.qa.routing-unsent-dependencies.v1', 'checked_at': '2026-09-17',
        'version': 'v24', 'production_commit': plan['production_commit'], 'count': 402,
        'evidence': 'Stopped progress plus 5 exact durable claims and independent process absence; no additional claims; frozen original plan.',
        'rows': [{'case_id': key, 'original_prompt_sha256': hashlib.sha256(case['prompt'].encode('utf-8')).hexdigest(),
            'state': 'dependency_blocked_proven_unsent', 'reason': 'Frozen model identity unavailable or switched; no question POST sent.'}
            for key, case in cases.items() if key not in claims]}
    if len(dependencies['rows']) != 402:
        raise ValueError('Unsent denominator mismatch')
    public = ROOT / 'tests/qa_regression'
    for name, payload in [('routing_v24_paired_observations_20260917.json', evidence),
        ('routing_v24_unattempted_dependencies_20260917.json', dependencies)]:
        (public / name).write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'counts': evidence['counts'], 'stable_sample': len(stable), 'not_sent': 402}))


if __name__ == '__main__':
    main()
