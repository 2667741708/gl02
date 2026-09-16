"""Update the 33-item ledger from frozen V24 evidence without upgrading open issues."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    public = ROOT / 'tests/qa_regression'
    path = public / 'optimization_execution_ledger_20260916.json'
    ledger = json.loads(path.read_text(encoding='utf-8'))
    evidence = json.loads((public / 'routing_v24_paired_observations_20260917.json').read_text(encoding='utf-8'))
    if evidence['requests'] != 5 or evidence['not_sent'] != 402 or len(ledger['rows']) != 33:
        raise ValueError('Frozen denominator changed')
    previous = ledger['latest_production_retest']
    if previous['version'] != 'routing-v23':
        raise ValueError('Ledger already updated or unexpected predecessor')
    ledger.setdefault('historical_production_retests', []).append(previous)
    ledger.update(production_commit=evidence['production_commit'], checked_at='2026-09-17')
    ledger['latest_production_retest'] = {
        'version': 'routing-v24', 'requests': 5, 'sse_done': 5, **evidence['counts'],
        'planned': 407, 'not_sent': 402, 'model_identity_drift_or_unavailable': True,
        'automatic_post_retries': 0, 'stable_sample': 4, 'stable_sample_correct_complete': 1,
        'stable_sample_correct_complete_rate': 0.25, 'first_405_failed_attempted': 3,
        'full_dataset_accuracy_available': False,
        'evidence': 'routing_v24_paired_observations_20260917.json',
        'dependency_records': 'routing_v24_unattempted_dependencies_20260917.json',
    }
    ledger['current_local_candidate'] = {'version': 'v24', 'issues': ['QAOPT-E01', 'QAOPT-R08', 'QAOPT-R09'],
        'state': 'deployed_targeted_improvement_verified_remaining_failures_open', 'focused_tests_passed': 76}
    ledger['manual_828_review_progress'] = {'reviewed': 540, 'remaining': 288, 'passed': 157,
        'partial': 131, 'failed': 122, 'insufficient_evidence': 41, 'oracle_blocked': 89,
        'state': 'intermediate_snapshot_not_final_accuracy', 'model': 'gpt-5.6-luna'}
    additions = {
        'QAOPT-E01': 'V24原题温度由failed变partial，真实读数保留；压力由partial变passed，99.219秒→0.094秒；均0追加工具/0模型，单位缺项保持partial。',
        'QAOPT-R08': 'V24禁代码承诺及合法算式76项关联回归通过；真实图表题未再提供代码，图表任务本身仍failed。',
        'QAOPT-R09': 'V24图表原题仍0工具且错误否认数据库/图表能力，必须修正任务路由和能力来源，不能标resolved。',
        'QAOPT-R03': 'V24图表原题仍failed；中文钟点/高度与方位范围仍需修复。',
        'QAOPT-E04': 'V24压差对比仍partial，缺单位与直接比较结论；单点温度解释末尾未完成，微量舍入/方向及Held质量单列。',
        'QAOPT-E05': 'V24图表答案completed却实际failed，温度分析结尾未完成；仍需覆盖MCP最终答案终态校验。',
        'QAOPT-O01': 'V24第5题后身份未核实停止；只读恢复时模型曾恢复批准:0，随后latest切为批准:1；402题无claim证明未发。',
        'QAOPT-T04': 'gpt-5.6-luna真实人工审核540/828，中间五类157/131/122/41/89；剩288，未发布全量准确率。',
        'QAOPT-T05': 'V24精确3写/24读、497代理AST和22共享标记、受保护PID/HTTP/哈希及生产CAS验收通过；5发送+402逐题阻断冻结。',
    }
    for row in ledger['rows']:
        if row['issue_id'] in additions:
            row['evidence'] += ' ' + additions[row['issue_id']]
        if row['issue_id'] == 'QAOPT-R08':
            row['state'] = 'deployed_partial_verified'
        if row['issue_id'] == 'QAOPT-O01':
            row['next_gate'] = '独立授权受控模型窗口；固定版本后只续跑402证明未发送题，已发送不重放'
    path.write_bytes((json.dumps(ledger, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    markdown = public / 'optimization_execution_ledger_20260916.md'
    text = markdown.read_text(encoding='utf-8')
    start = text.index('|1|QAOPT-R01')
    end = text.index('\n\n', start)
    lines = []
    for row in ledger['rows']:
        cells = [row['order'], row['issue_id'] + ' ' + row['title'], row['priority'], row['state'], row['evidence'], row['next_gate']]
        lines.append('|' + '|'.join(str(value).replace('|', '\\|').replace('\n', ' ') for value in cells) + '|')
    text = text[:start] + '\n'.join(lines) + text[end:]
    text += '\n\n## V24最新冻结（2026-09-17）\n\n'
    text += '当前生产V24 `b55f754ac8d8592e2819083f01a71438bd6e23c7`，8093 PID8396。5题一次发送、SSE完成5题；全文审核1通过/3部分/1失败。模型身份稳定4题中1题完整通过（25%，仅小样本），第5题身份未核实；402题逐条阻断未发送。历史V23九题统计保留，不能与V24合并为准确率。\n\n'
    text += '[V24实施、统计和剩余方案](../../docs/handoffs/2026-09-17-qa-v24-latest-reuse-and-code-boundary.md)、[5题冻结结果](routing_v24_paired_observations_20260917.json)、[402题逐题阻断](routing_v24_unattempted_dependencies_20260917.json)。33项仍按验证范围保留，不称全部解决。\n'
    markdown.write_bytes(text.encode('utf-8'))
    print(json.dumps({'ok': True, 'issues': 33, 'requests': 5, 'dependency_records': 402}))


if __name__ == '__main__':
    main()
