"""Project explicit full-answer review decisions; do not infer pass from routes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = {
    'TPL-FACD6F5FE05C74FC': ('partial', '三对象同窗口统计与成功工具数据对应，已进入查询；仍缺综合对比结论，两对象单位未登记，总压差单位取渲染映射而非本次工具目录，不能算完整解决。', ['QAOPT-R03', 'QAOPT-E04', 'QAOPT-E06']),
    'TPL-01EEE414179DB624': ('partial', '单点查询成功，保留真实统计且未补造风险；综合被可信守卫拒绝，未回答稳定性，单位/阈值仍缺。', ['QAOPT-E01', 'QAOPT-E04']),
    'TPL-342113EAB17420C6': ('failed', '昨晚八点至九点的明确历史查询未调用工具，错误声称无已授权数据访问能力。', ['QAOPT-R01', 'QAOPT-R03']),
    'TPL-E1C7A67C947531E9': ('partial', '实际完成最近窗口查询并明确缺合格历史基线，不编造偏高结论；业务结论未完成，采集器仅保留工具成功摘要，须补数据质量证据。', ['QAOPT-E02', 'QAOPT-T04']),
    'TPL-FD3912331A49B991': ('passed', '返回可访问身份历史的相关提问和时间，历史回答明确为未重新核实的摘录；没有把旧答案冒充当前业务结论。', []),
    'TPL-8DA6777B502376D4': ('passed', '最近日报按文件更新时间选择且摘要与随后Reliable SSH只读读取的实际文件一致，历史范围明确，未执行写入。', []),
    'TPL-C5DF79304112ED85': ('failed', '没有查询或绘图；误把高度与A-F方位混淆并错误否认已授权能力，还提出生成绘图代码，违反禁代码目标。', ['QAOPT-R03', 'QAOPT-R09']),
    'TPL-BE97AA4EAD567003': ('failed', '预取已获得顶温值，但最终只输出点位目录；重复最新值查询耗尽预算且综合被拒绝，成功预取事实丢失。请求后身份未核实单列。', ['QAOPT-E01', 'QAOPT-O01']),
}

def main():
    data = json.loads((ROOT / '.codex_runtime/qa-routing-v23/snapshots/results.private.json').read_text(encoding='utf-8'))
    actual = {r['case_id']: r for r in data['rows']}
    progress = {r['case_id']: r for r in data['progress']['results']}
    if set(actual) != set(DECISIONS) or data['progress']['requests'] != 8:
        raise ValueError('Reviewed scope differs from retained evidence')
    rows = []
    for case_id, (status, reason, issues) in DECISIONS.items():
        source = actual[case_id]
        if source['request_count'] != 1 or not source['terminated'] or not source['done']:
            raise ValueError('Incomplete or repeated transport')
        rows.append({'case_id': case_id, 'cohort': 'v22_new_failure' if case_id in list(DECISIONS)[:2] else 'initial_confirmed_failure',
                     'status': status, 'reason': reason, 'issue_ids': issues,
                     'result_sha256': source['result_file_sha256'], 'route': source['final'].get('answer_route'),
                     'transport_complete': True, 'eligible_stable_sample': progress[case_id].get('post_turn_identity') == 'matched',
                     'model_identity_samples': {k: progress[case_id].get(k) for k in ['before_identity', 'after_identity', 'post_turn_identity']}})
    value = {'schema': 'bf.qa.v23.independent-observations.v1', 'checked_at': '2026-09-17',
             'requirement_id': 'REQ-QA-PAIRED-FAILURE-RETEST-20260916',
             'production_commit': 'baaa7496afbd43b35be98c1e231f79a71d3aa7cf',
             'method': 'Primary-agent full-question/full-answer review; statistical and prefetch evidence inspected, report source independently read; history response reviewed without a separate database re-query.',
             'planned': 407, 'attempted': 8, 'proven_unsent': 399, 'passed': 2, 'partial': 3, 'failed': 3,
             'stable_identity_sampled': 7, 'stable_sample_correct_complete': 2,
             'stable_sample_accuracy': 2/7, 'accuracy_scope': 'Seven observed samples only; not full assistant accuracy, causal improvement, or all 405 failure recovery.',
             'initial_405_failed_attempted': 6, 'initial_405_failed_proven_unsent': 399,
             'initial_failure_stable_sample': {'attempted': 5, 'passed': 2, 'partial': 1, 'failed': 2, 'correct_complete_rate': 2/5},
             'transport_complete': 8, 'transport_rate': 1.0, 'automatic_post_retries': 0,
             'state': 'blocked_model_identity_drift_or_unavailable', 'full_dataset_accuracy_available': False, 'rows': rows}
    r2_path = ROOT / '.codex_runtime/qa-routing-v23/r2-snapshots/results.private.json'
    if r2_path.exists():
        r2 = json.loads(r2_path.read_text(encoding='utf-8'))
        if len(r2['rows']) != 1 or r2['rows'][0]['case_id'] != 'TPL-A60B0CD794D49E48':
            raise ValueError('Continuation review scope mismatch')
        source = r2['rows'][0]
        if source['request_count'] != 1 or not source['done'] or not source['terminated']:
            raise ValueError('Continuation transport incomplete')
        item = r2['progress']['results'][0]
        rows.append({'case_id': source['case_id'], 'cohort': 'initial_confirmed_failure', 'round': 'r2',
                     'status': 'partial', 'reason': '实际顶压值和真实时间与成功最新值工具一致；单位未登记，简单值查询仍重复规划近百秒并出现未完成提示；请求后身份不可核实，不能计入固定模型效果。',
                     'issue_ids': ['QAOPT-E01', 'QAOPT-E04', 'QAOPT-O01'], 'result_sha256': source['result_file_sha256'],
                     'route': source['final'].get('answer_route'), 'transport_complete': True,
                     'eligible_stable_sample': item.get('post_turn_identity') == 'matched',
                     'model_identity_samples': {k: item.get(k) for k in ['before_identity','after_identity','post_turn_identity']}})
        value.update(attempted=9, proven_unsent=398, partial=4, initial_405_failed_attempted=7,
                     initial_405_failed_proven_unsent=398, transport_complete=9,
                     r1_counts={'attempted':8,'passed':2,'partial':3,'failed':3})
        value['continuation'] = {'round':'paired-v23-20260917-r2', 'planned':399,'attempted':1,'proven_unsent':398,
                                'excluded_predecessor_sent':8,'previous_process_absent_verified':True,'pid':14776,
                                'plan_sha256':'952f22764c8658b45904ef9eed0dd28da33669906b5e2f96fc9a432e48046fab',
                                'state':'blocked_model_identity_drift_or_unavailable','model_task_modified':False,
                                'automatic_post_retries':0}
    path = ROOT / 'tests/qa_regression/routing_v23_paired_observations_20260917.json'
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({k: value[k] for k in ['attempted','passed','partial','failed','proven_unsent']}))

if __name__ == '__main__':
    main()
