"""Publish reviewed, redacted V21 observations; never send or replay a question."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.codex_runtime/qa-routing-v21'
PUBLIC = ROOT / 'tests/qa_regression'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.write_bytes(text.encode('utf-8'))


def replace(path, old, new):
    text = path.read_text(encoding='utf-8-sig')
    if text.count(old) != 1:
        raise ValueError('Replacement must have exactly one match: ' + str(path))
    path.write_bytes(text.replace(old, new).encode('utf-8'))


def main():
    if (PUBLIC / 'routing_v21_paired_observations_20260916.json').exists():
        raise ValueError('Observation report is frozen; use a new report for a new round')
    evidence = read(PRIVATE / 'snapshots/results.private.json')
    plan = read(PRIVATE / 'paired-failures.private.json')
    rows = evidence['rows']
    progress = evidence['progress']
    if [row['case_id'] for row in rows] != ['LIVE-001', 'LIVE-002', 'LIVE-003', 'LIVE-004']:
        raise ValueError('These manual assessments apply only to the four reviewed answers')
    if progress['state'] != 'blocked' or progress['requests'] != 4 or len(plan['cases']) != 413:
        raise ValueError('Batch state or frozen denominator changed')
    reasons = [
        '主要能力与禁代码边界正确；不调用实时工具。',
        '均值4、总体方差8/3、标准差约1.633，计算过程与无工具约束正确。',
        '假设三点累计上升2kPa、约0.8%；不据此推断真实炉况恶化，说明补证据条件。',
        'MCP定义与客户端/服务器解释正确；把协议规范夸大成自动防越权，需要说明具体实现的责任。',
    ]
    reviewed = []
    for index, row in enumerate(rows):
        events = [event['event'] for event in row['events']]
        if row['request_count'] != 1 or row['http_status'] != 200 or not row['done'] or not row['answer']:
            raise ValueError('Observed transport or answer contract changed')
        if not all(event in events for event in ['start', 'delta', 'final', 'done']) or row['tool_starts']:
            raise ValueError('Observed stream or no-tools contract changed')
        reviewed.append({
            'case_id': row['case_id'], 'status': 'passed' if index < 3 else 'partial',
            'review_kind': 'primary_and_independent_final_answer_review', 'evidence': reasons[index],
            'answer_sha256': hashlib.sha256(row['answer'].encode('utf-8')).hexdigest(),
            'result_file_sha256': row['result_file_sha256'],
            'route': row['final']['answer_route'], 'tool_calls': 0,
            'model_requests': row['final']['model_request_count'],
            'transport_completed': True, 'model_digest_during_turn_verified': False,
        })
    ledger = read(PUBLIC / 'question_ledger_20260916.json')
    entries = ledger.get('rows', ledger.get('questions', []))
    collected = [row for row in entries if row['collection_status'] == 'collected']
    counts = Counter(row['answer_review_status'] for row in collected)
    failed = [row for row in collected if row['answer_review_status'] in
              ['confirmed_failed_manual', 'confirmed_failed_fixed_response']]
    if len(collected) != 1259 or len(failed) != 405:
        raise ValueError('Initial collection evidence denominator changed')
    summary = {
        'schema': 'bf.qa.paired-failure-observations.v1',
        'requirement_id': 'REQ-QA-PAIRED-FAILURE-RETEST-20260916',
        'checked_at': '2026-09-16', 'production_commit': plan['production_commit'],
        'production_version': 'routing-v21',
        'initial_first_eight': {'failed': 5, 'partial': 1, 'passed': 1, 'policy_changed': 1},
        'initial_extended_collection': {
            'collected': 1259, 'confirmed_failed': 405,
            'confirmed_failure_categories': dict(Counter(row['category'] for row in failed)),
            'review_counts': dict(counts), 'unresolved_sent_state_excluded_from_replay': 1,
            'invalid_structural_oracle': 26, 'valid_collected_denominator': 1233,
            'confirmed_failure_lower_bound_percent': round(405 / 1233 * 100, 2),
            'overall_accuracy_available': False,
        },
        'new_round': {
            'planned': 413, 'first_eight': 8, 'previous_confirmed_failures': 405,
            'completed': 4, 'not_sent': 409, 'automatic_post_retries': 0,
            'transport_completed': 4, 'content_passed': 3, 'content_partial': 1,
            'content_failed': 0, 'observed_content_accuracy_percent': 75.0,
            'observed_complete_answer_success_percent': 75.0,
            'observed_transport_success_percent': 100.0,
            'fixed_model_full_dataset_accuracy_available': False,
            'oracle_conflicted_cases_in_plan': 5,
            'state': 'blocked_before_fifth_question',
            'reason': 'Same latest model alias alternates between two digests during automatic model repair.',
            'scope': 'Four first-eight observations only; zero extended-failure cases have been retested.',
        },
        'reviews': reviewed,
        'new_issues': ['ERR-QA-MODEL-ALIAS-DRIFT-20260916', 'BUG-QA-MCP-SECURITY-OVERCLAIM-20260916'],
        'metric_rules': {
            'accuracy': 'Correct and complete final answers / independently scored valid cases.',
            'complete_answer_success': 'Useful complete answers / valid attempted cases; a refusal alone is not success.',
            'transport_success': 'HTTP200 + final + done + nonempty answer; not semantic accuracy.',
            'partial_credit_in_strict_accuracy': False,
        },
        'independent_review_agent': 'qa_v21_release_review',
        'mcp_reference': 'https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization',
        'raw_answers_published': False,
    }
    write(PUBLIC / 'routing_v21_paired_observations_20260916.json', summary)
    execution_path = PUBLIC / 'optimization_execution_ledger_20260916.json'
    execution = read(execution_path)
    execution['production_commit'] = plan['production_commit']
    execution['previous_targeted_retest'] = execution['latest_production_retest']
    execution['latest_production_retest'] = {
        'version': 'routing-v21', 'requests': 4, 'sse_done': 4,
        'passed': 3, 'partial': 1, 'failed': 0, 'planned': 413, 'not_sent': 409,
        'model_identity_drift': True, 'automatic_post_retries': 0,
        'full_dataset_accuracy_available': False,
    }
    issues = execution['rows']
    if len(issues) != 33:
        raise ValueError('Issue inventory changed')
    for issue in issues:
        if issue.get('issue_id') == 'QAOPT-O05':
            issue['state'] = 'deployed_partial_verified'
            issue['evidence'] = 'V21已受控发布：精确控制模块、受保护PID及生产CAS通过；独占9项和关联35项本机通过；真实双角色409/取消验收待测'
            issue['next_gate'] = '固定模型版本后完成真实双角色409、取消实际停止释放与owner隔离；不排队、不重放'
        if issue.get('issue_id') == 'QAOPT-O01':
            issue['evidence'] = 'V21复测4题后latest digest变化阻断；只读证明自动Repair候选失败后切换:1/:0，标签与实际驻留曾不一致；就绪true仍不能证明固定版本'
            issue['next_gate'] = '单一模型状态控制者、测试期间固定digest且标签/驻留一致；模型任务变更须独立授权，仅续跑已证明未发送409题'
    write(execution_path, execution)
    replace(PUBLIC / 'optimization_execution_ledger_20260916.md',
            '|23|`QAOPT-O01` 模型就绪与请求间竞态|P0|production_dependency_open|前轮model_ok临时false和启动失败已记录；本轮确认批准业务模型为已驻留Qwen，吞查询异常为空列表不足以证明卸载|先细分就绪检查失败/成功查询缺席，再按执行能力依赖门与Qwen驻留/调度方案验证|',
            '|23|`QAOPT-O01` 模型就绪与请求间竞态|P0|production_dependency_open|V21复测4题后latest digest漂移；自动Repair候选失败后切换:1/:0，标签与实际驻留曾不一致|模型控制单一来源、固定digest；独立授权后仅续跑未发送409题|')
    replace(PUBLIC / 'optimization_execution_ledger_20260916.md',
            '|27|`QAOPT-O05` 并发与角色边界|P1|implemented_local_verified_production_pending|用户限定所有角色同一时间一个活动问答；本机全局注册门与9项生命周期测试及独立审查通过，关联35项通过；生产未更新|受控发布后验证真实角色独占409、取消实际停止后释放与owner隔离；不排队、不自动重放|',
            '|27|`QAOPT-O05` 并发与角色边界|P1|deployed_partial_verified|V21单控制模块已受控发布，哈希/CAS/受保护PID通过；独占9项、关联35项本机通过|固定模型后完成真实双角色409、取消实际停止释放和owner隔离；不排队、不重放|')
    replacements = [
        ('docs/api_reference.md', '使用中拒绝（本机候选）', '使用中拒绝（V21已发布）'),
        ('docs/api_reference.md', '生产尚未更新；[范围与验收]', 'V21已受控发布，真实双角色/取消现场验收待测；[范围与验收]'),
        ('docs/requirements_traceability.md', '本机实现、35项关联测试及独立审查通过，生产尚未更新。', '本机实现、35项关联测试及独立审查通过；V21已受控发布，真实双角色与取消验收待测。'),
        ('docs/test_reference.md', '真实角色/浏览器与生产独占验收仍待受控发布。', 'V21已受控发布并通过字节/PID/CAS验收；真实角色409与取消现场行为仍待测。'),
        ('docs/handoffs/2026-09-16-qa-exclusive-use-local.md', '状态：本机代码及针对性验证完成，生产尚未更新。', '状态：V21已受控发布；本机验证完成，真实双角色409/取消现场验收待测。'),
        ('docs/handoffs/2026-09-16-qa-exclusive-use-local.md', '本轮尚未发布。后续遵守8093受控流程，替换精确模块、保护其他服务PID。', 'V21已按8093受控流程发布精确模块，其他服务PID保持不变；[生产与复测证据](2026-09-16-qa-routing-v21-paired-retest.md)。'),
    ]
    for path, old, new in replacements:
        replace(ROOT / path, old, new)
    print(json.dumps({'ok': True, 'initial_confirmed_failed': 405, 'observed_passed': 3,
                      'observed_partial': 1, 'not_sent': 409}))


if __name__ == '__main__':
    main()
