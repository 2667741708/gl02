"""Merge frozen initial failures with the completed 828 semantic decisions."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from validate_qa_initial_828_review import validate

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'tests/qa_regression/question_ledger_20260916.json'
    review_path = ROOT / 'tests/qa_regression/initial_828_semantic_review_20260916.json'
    validate(review_path)
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if not review.get('semantic_decisions_final') or review.get('review_layer') != 'manual_luna_semantic':
        raise ValueError('Final explicit semantic decisions required')
    ledger = json.loads(source.read_text(encoding='utf-8'))['rows']
    reviewed = {r['case_id']: r for r in review['reviews']}
    rows = []
    for original in ledger:
        if original['collection_status'] != 'collected' or original['answer_review_status'] == 'oracle_invalid_structural_line':
            continue
        decision = reviewed.get(original['case_id'])
        if decision:
            status, issues, reason = decision['status'], decision['issue_ids'], decision['reason']
        elif original['answer_review_status'].startswith('confirmed_failed'):
            status, issues, reason = 'failed', original['issue_ids'], original['answer_review_status']
        else:
            raise ValueError('Unclassified valid collected case: ' + original['case_id'])
        rows.append({'case_id': original['case_id'], 'status': status, 'category': original['category'],
                     'original_result_sha256': original['result_sha256'],
                     'original_prompt_sha256': hashlib.sha256(original['prompt'].encode()).hexdigest(),
                     'source_path': original['source_path'], 'source_line': original['source_line'],
                     'issue_ids': issues, 'reason': reason})
    counts = Counter(r['status'] for r in rows)
    if len(rows) != 1233 or counts != Counter({'passed': 269, 'partial': 186, 'failed': 636, 'oracle_blocked': 89, 'insufficient_evidence': 53}):
        raise ValueError('Initial merged semantic denominator changed')
    scoreable = sum(counts[k] for k in ('passed', 'partial', 'failed'))
    summary = {'schema': 'bf.qa.initial-semantic-summary.v1', 'checked_at': '2026-09-17',
               'requirement_id': 'REQ-QA-FULL-ISSUE-INVENTORY-20260916',
               'ledger_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'semantic_review_sha256': hashlib.sha256(review_path.read_bytes()).hexdigest(),
               'source_lines': 1418, 'ready': 1260, 'collected': 1259, 'structural_invalid_excluded': 26,
               'sent_unknown_never_replay': ['TPL-10C8C8FAF2C694EF'], 'valid_collected': len(rows),
               'counts': dict(counts), 'independently_scoreable': scoreable,
               'correct_complete_rate_scoreable': counts['passed'] / scoreable,
               'conservative_correct_complete_coverage': counts['passed'] / len(rows),
               'confirmed_failure_rate_valid': counts['failed'] / len(rows),
               'retest_failure_or_partial_count': counts['failed'] + counts['partial'],
               'category_counts': {c: dict(Counter(r['status'] for r in rows if r['category'] == c)) for c in sorted({r['category'] for r in rows})},
               'rates_rule': 'Nonempty text is not success. Unscoreable cases are reported separately, never silently passed or discarded.',
               'rows': rows}
    output = ROOT / 'tests/qa_regression/initial_semantic_summary_20260917.json'
    output.write_bytes((json.dumps(summary, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    lines = ['# 首次数据集最终语义统计', '', '状态：冻结统计；最后核对：2026-09-17。',
             '权威来源：首次 question_ledger 和已完成的 gpt-5.6-luna 828 题逐题审核；仅合并判定，不重发原始请求。', '',
             '| 判定 | 题数 |', '|---|---:|', *[f'|{key}|{counts[key]}|' for key in ('passed', 'partial', 'failed', 'oracle_blocked', 'insufficient_evidence')], '',
             f'有效已收集 1233 题，其中可判题 {scoreable} 题：完整正确率 {counts["passed"]/scoreable:.2%}；全集保守正确覆盖率 {counts["passed"]/1233:.2%}。',
             '636 题确认失败、186 题部分正确，共 822 题进入修复后原题复测集合。142 题须先补标准或证据，不能计作成功。',
             'TPL-4B4EC922336F4F2B 经首次原答案复核由失败修正为部分正确；修订日志保留。V25已执行计划按此前判定冻结，不修改原计划；待复测题ID集合不变。',
             '1259 条已收集结果中的 26 条结构误导入行不进入正确率分母；1 条发送状态不确定的题永久禁止自动重放。',
             '这些是首次全数据集统计；V21–V25 的小样本或未完成复测不得与首次数据混成优化后准确率。', '',
             '## 分类统计', '', '| 分类 | 完整正确 | 部分正确 | 失败 | 标准阻断 | 证据不足 |', '|---|---:|---:|---:|---:|---:|']
    for category, values in summary['category_counts'].items():
        lines.append('|'+category+'|'+ '|'.join(str(values.get(s, 0)) for s in ('passed', 'partial', 'failed', 'oracle_blocked', 'insufficient_evidence'))+'|')
    lines += ['', '## 逐题核对', '', '全部题 ID、首次结果哈希、原问题哈希、分类、判定、理由和问题编号见同名 JSON；公开报告不包含原始回答、实时数据或身份。',
              '逐项解决和验收方案继续以 optimization_execution_ledger_20260916.json 的 33 项需求为准；新题复测独立绑定代码、模型和原问题哈希。']
    output.with_suffix('.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    print(json.dumps({k:summary[k] for k in ['valid_collected','counts','independently_scoreable','correct_complete_rate_scoreable','retest_failure_or_partial_count','category_counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
