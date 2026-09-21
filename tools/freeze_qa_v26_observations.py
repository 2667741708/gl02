"""Publish hash-bound V26 deployment/recovery facts without raw questions or data."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v26'
    snapshot = load(runtime / 'release/post-record-snapshot.json')
    record = load(runtime / 'release/accepted-version-record.json')
    recovery = load(runtime / 'readonly-recovery.json')
    plan_path = runtime / 'failure-round.plan.private.json'
    plan = load(plan_path)
    if (not snapshot['ok'] or not record['ok'] or snapshot['head'] != record['head_after']
            or snapshot['production_version_ref'] != snapshot['head'] or plan['production_commit'] != snapshot['head']
            or recovery['plan_sha256'] != hashlib.sha256(plan_path.read_bytes()).hexdigest()
            or not recovery['process_absent'] or recovery['claim_ids'] or recovery['result_ids']
            or recovery['requests'] != 0 or recovery['completed'] != 0 or len(plan['cases']) != 822):
        raise ValueError('Unverified accepted version or unsent recovery')
    public = ROOT / 'tests/qa_regression'
    proof = {'schema': 'bf.qa.production-proof.v1', 'version': 'v26', 'checked_at': '2026-09-17',
             'production_commit': snapshot['head'], 'production_version_ref_matches': True,
             'accepted_git_record': record['ok'], 'post_record_readiness': snapshot['status'],
             'write_count': 3, 'read_count': 25, 'focused_tests_passed': 174,
             'protected_proxy_ast_nodes': 494, 'protected_mcp_ast_nodes': 186, 'shared_markers': 22,
             'independent_candidate_and_deployment_review': 'gpt-5.6-luna low PASS',
             'installed_hashes': {k: v for k, v in snapshot['runtime_hashes'].items()
                                  if k.endswith(('ollama_proxy_server.py', 'qa_tool_fallback.py', 'bf_data_mcp_server.py'))},
             'chart_repair': ['explicit_24_object_limit_without_silent_truncation', 'complete_typed_evidence_retained',
                              'bounded_model_projection_separate_from_evidence', 'chart_preserved_after_lifecycle_failure'],
             'production_semantic_effectiveness_verified': False}
    write(public / 'routing_v26_production_20260917.json', proof)
    observation = {'schema': 'bf.qa.paired-observations.v1', 'version': 'v26', 'checked_at': '2026-09-17',
                   'production_commit': snapshot['head'], 'planned': 822, 'attempted': 0, 'transport_complete': 0,
                   'passed': 0, 'partial': 0, 'failed': 0, 'proven_unsent': 822,
                   'initial_failed': 636, 'initial_partial': 186, 'full_dataset_accuracy_available': False,
                   'reason': 'Approved Qwen alias changed before the first send; strict identity gate blocked the batch.',
                   'rows': []}
    write(public / 'routing_v26_paired_observations_20260917.json', observation)
    dependencies = {'schema': 'bf.qa.unattempted-dependencies.v1', 'version': 'v26',
                    'production_commit': snapshot['head'], 'plan_sha256': recovery['plan_sha256'], 'sent': 0,
                    'proven_unsent': 822, 'automatic_post_retries': 0,
                    'proof': 'Exited batch PID and zero claims/results independently read; no question was sent.',
                    'rows': [{'case_id': c['case_id'], 'original_prompt_sha256': c['original_prompt_sha256'],
                              'initial_status': c['initial_semantic_status'], 'status': 'dependency_blocked_proven_unsent',
                              'reason': 'frozen_model_identity_changed_before_first_send', 'automatic_replay': False}
                             for c in plan['cases']]}
    write(public / 'routing_v26_unattempted_dependencies_20260917.json', dependencies)
    ledger_path = public / 'optimization_execution_ledger_20260916.json'
    ledger = load(ledger_path)
    if ledger['production_commit'] not in {record['head_before'], snapshot['head']} or len(ledger['rows']) != 33:
        raise ValueError('Unexpected issue ledger predecessor')
    if ledger['production_commit'] != snapshot['head']:
        ledger['historical_v25_retest'] = ledger['latest_production_retest']
    ledger['production_commit'] = snapshot['head']
    ledger['latest_production_retest'] = dict(observation, evidence='routing_v26_paired_observations_20260917.json',
                                             dependency_records='routing_v26_unattempted_dependencies_20260917.json')
    ledger['current_local_candidate'] = {'version': 'v26', 'state': 'deployed_semantic_retest_blocked',
                                        'focused_tests_passed': 174, 'production_semantic_effectiveness_verified': False}
    for row in ledger['rows']:
        if row['issue_id'] in {'QAOPT-R03', 'QAOPT-E01', 'QAOPT-E05', 'QAOPT-O03'}:
            addition = '; V26工具上限/完整类型化证据/异常图表保留已部署，本机174检查通过；822题发送前身份拦截，真实效果未确认。'
            if addition not in row['evidence']:
                row['evidence'] += addition
            row['next_gate'] = '固定已批准Qwen模型的授权测试窗口内，原18点绘图题和822原失败/部分题逐题复测，非空不算通过'
        if row['issue_id'] == 'QAOPT-O01':
            row['state'] = 'dependency_blocked'
            addition = '; V26首题前批准Qwen版本1切为0，822题均无claim/result；恢复任务先改alias再热身，两候选HTTP发送失败后未提交状态。'
            if addition not in row['evidence']:
                row['evidence'] += addition
            row['next_gate'] = '独立授权限时暂停恢复任务未来触发，固定已驻留批准digest，结束恢复原enabled；长期管理器冷却/失败回滚另行审查授权'
    write(ledger_path, ledger)
    print(json.dumps({'ok': True, 'version': 'v26', 'planned': 822, 'attempted': 0, 'proven_unsent': 822, 'issue_rows': 33}))


if __name__ == '__main__':
    main()
