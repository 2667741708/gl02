"""Refresh the 33-item execution plan with final baseline and actual V25 evidence."""
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEASURES = {
 'R01': '统一外层任务计划，固定来源、对象、时间窗、子任务和完成条件；所有降级分支读取同一计划。验收：复合问题逐项覆盖，引用或关键词不抢路由。',
 'R02': '聊天历史仅作对话证据，业务事实另查权威源；owner 和消息截止 ID 固定。验收：历史+当前任务分别有来源，跨用户历史不可见。',
 'R03': '保留全对象集合，高度和方位分别解析；工具不得静默截断列表。验收：18 个请求点=18 个返回/明确失败点，未知层位先澄清。',
 'R04': '明确日期钟点优先于滚动窗口和旧上下文；相邻窗统一冻结时钟，基线质量独立审查。验收：起止时间精确、跨午夜正确、缺基线不冒充正常。',
 'R05': '目录检索后读取实际报表正文；缺正文和类型不符分别记录。验收：摘要可追溯到该报告，不用文件名替代正文。',
 'R06': '诊断从权威批次加载，复合任务生成有依赖的只读步骤。验收：每个子任务有结果或明确缺项，不仅回答最容易的一问。',
 'R07': '无工具解释、用户给定数据和已核实证据可直接回答；新实时事实才查询。验收：禁实时请求零数据调用，数学复算正确。',
 'R08': '代码执行与代码示例独立禁用，拒绝该子任务同时完成允许的查询/统计/图表。验收：不承诺提供代码，不误拒普通问题。',
 'R09': '能力说明由工具注册、授权和实时健康派生，与 Prompt 目标一致。验收：已接通查询/绘图时不虚假否认能力，故障准确说明具体限制。',
 'R10': '多轮仅继承已确认对象/窗口/来源，换题清空不适用上下文。验收：追问/最新值/主题切换及用户数据任务均独立可复现。',
 'K01': '正式知识采用岗位、文档版本、章节和条款定位，检索与现场数据路由独立。验收：原文证据和语义答案分别审核，覆盖不算正确。',
 'K02': '权威知识排除聊天及测试标准答案，原文源单独登记。验收：回归集和旧助手回答不能成为正式制度引用。',
 'K03': '全文章节及表格按结构边界读取，校验开头/结尾/连续性及多章节完整覆盖。验收：不漏尾、不串岗、不丢表头和单位。',
 'K04': '未知正式制度先说明资料缺失；一般工艺解释必须标明非正式条款。验收：不编造制度编号、阈值或操作授权。',
 'K05': '报表和制度来源域分离，复合问题分别组织证据。验收：报表目录不能冒充制度内容，存在两来源时不漏问。',
 'K06': '文档和 oracle 分别版本化；89 题标准阻断对照岗位原文逐条确认，记录修正理由和旧标准。验收：同问不同标准/错编号不自动改答案。',
 'E01': '完整类型化工具结果先追加保存，再生成界面/模型摘录；生命周期错误保留成功事实及图表。验收：成功生成的图与真实数据不会被失败回合清空。',
 'E02': '证据绑定对象、窗口、来源、单位、质量、适用范围及原始哈希。验收：当前单点不能证明历史趋势，目录不能证明实时数据。',
 'E03': '数值、单位和派生量逐字段核对；缺单位保持缺项，舍入不改变方向。验收：温标/CV/零值和微小变化可独立复算且保留血缘。',
 'E04': '固定计算器统一均值、总体标准差、首末变化、回归和局部趋势；明确冲突与质量。验收：Held、稀疏覆盖和近零均值不会判成正式稳定等级。',
 'E05': '所有最终出口检查任务覆盖、截断、结束原因和缺项；传输完成与语义成功分开。验收：未完成句子或缺图回答不能标 complete。',
 'E06': '多源时间、数值和制度冲突显式展示；区分描述性观察与有阈值的风险判断。验收：对比题有直接结论和适用限制，不仅堆统计。',
 'O01': '在独立授权窗口内固定已批准 Qwen digest，模型管理器与问答共享调度边界；单驻留并核对 alias。验收：请求前/后身份一致，波动停止下一发送。',
 'O02': '注册、连接、工具、模型和流式分别限时，失败只影响依赖步骤；同请求允许一次有证据降级。验收：成功步骤保留，断线未知不自动 POST 重放。',
 'O03': '工具 schema、参数范围和 DAG 依赖在执行前校验，显式拒绝超限；完整证据与模型投影分开。验收：18 点列表不缩为16，长 JSON 不被剪成非法证据。',
 'O04': 'turn/step/item 统一状态、耗时和故障类型；浏览器有界合并与历史分页。验收：可区分数据空、超时、模型变化和答案不完整，不泄漏身份/凭据。',
 'O05': '按用户要求全服务同时仅一个问答 owner，另一人立即409，不排队；取消确认实际结束再释放。验收：真实双角色隔离、并发409和取消释放均通过。',
 'T01': '全题唯一 ID、发送 claim、程序/模型/Prompt/结果哈希冻结。验收：全题对账，首次未知题永不重发，续跑仅限证明未发。',
 'T02': '结构误导入26条剔除评分但保留事实；标准冲突和证据不足单列。验收：分母可复算，不把无效行、无答案或无法判定当成功。',
 'T03': '绑定服务端最终系统 Prompt、模板版本、请求策略及故障夹具。验收：每条回复可追溯实际 Prompt hash，不只绑定源文件名。',
 'T04': '已完成828逐题审核；每版继续审核原失败/部分题，再增加持出集。验收：完整正确率、完整有用回答率、传输率分开，模型不同分层。',
 'T05': '冻结最小写/读集合，独立审查、recordability、共享功能合同、8093守卫和CAS。验收：版本/哈希/HTTP/PID可核对，失败回滚不自动重试同候选。',
 'T06': '以新故障追加回归并记录覆盖空白和响应时间目标；定期按题型发布质量趋势。验收：新增题无原始生产数据/身份，历史报告可复现。',
}


def main():
    path = ROOT / 'tests/qa_regression/optimization_execution_ledger_20260916.json'
    ledger = json.loads(path.read_text(encoding='utf-8'))
    initial = json.loads((ROOT / 'tests/qa_regression/initial_semantic_summary_20260917.json').read_text(encoding='utf-8'))
    observed = json.loads((ROOT / 'tests/qa_regression/routing_v25_paired_observations_20260917.json').read_text(encoding='utf-8'))
    if len(ledger['rows']) != 33 or len(MEASURES) != 33:
        raise ValueError('Full issue coverage required')
    if ledger['production_commit'] not in {'b55f754ac8d8592e2819083f01a71438bd6e23c7', observed['production_commit']}:
        raise ValueError('Unexpected predecessor; inspect rather than overwrite')
    if ledger['production_commit'] != observed['production_commit']:
        ledger['historical_v24_retest'] = ledger['latest_production_retest']
    ledger['production_commit'] = observed['production_commit']
    ledger['latest_production_retest'] = {'version': 'routing-v25', 'planned': 822, 'requests': 1, 'sse_done': 1,
        'passed': 0, 'partial': 0, 'failed': 1, 'not_sent': 821, 'stable_sample': 0,
        'model_identity_drift_or_unavailable': True, 'automatic_post_retries': 0,
        'full_dataset_accuracy_available': False, 'evidence': 'routing_v25_paired_observations_20260917.json',
        'dependency_records': 'routing_v25_unattempted_dependencies_20260917.json'}
    ledger['initial_semantic_review_final'] = {'valid_collected': 1233, 'counts': initial['counts'],
        'independently_scoreable': 1091, 'correct_complete_rate_scoreable': initial['correct_complete_rate_scoreable'],
        'failed_or_partial_retest': 822, 'evidence': 'initial_semantic_summary_20260917.json'}
    ledger['current_local_candidate'] = {'version': 'v25', 'state': 'deployed_new_runtime_defects_open',
        'issues': ['QAOPT-R01','QAOPT-R03','QAOPT-R04','QAOPT-E01','QAOPT-O03'], 'focused_tests_passed': 159}
    for row in ledger['rows']:
        key = row['issue_id'].removeprefix('QAOPT-')
        row['repair_and_acceptance_plan'] = MEASURES[key]
        row['initial_linked_semantic_counts'] = dict(Counter(r['status'] for r in initial['rows'] if row['issue_id'] in r['issue_ids']))
        if key in {'R03','E01','E05','O03'}:
            addition = '; V25真实绘图原题：18个请求点进入路由，工具仅16点且最终图表遗漏，不能标解决。'
            if addition not in row['evidence']: row['evidence'] += addition
            row['next_gate'] = '修复工具点数静默截断和完整JSON证据/图表恢复，再做新版原题一次复测'
        if key == 'O01':
            addition = '; V25首题后身份未核实停止，821题无claim证明未发。'
            if addition not in row['evidence']: row['evidence'] += addition
            row['next_gate'] = '独立授权固定Qwen窗口；只续跑821证明未发题，不自动重发已发首题'
        if key == 'T04':
            row['state'] = 'initial_review_complete_version_retests_open'
            row['evidence'] = 'gpt-5.6-luna 828/828实际逐题审核完成，269通过/186部分/231失败/89标准阻断/53证据不足；合并首次有效1233题，636失败。89标准阻断不等同89条标准冲突，833知识来源审计另有30条原文/标准冲突。'
            row['next_gate'] = '822原失败/部分题新版完整复测与持出集，不凭非空计算准确率'
        if key == 'T05':
            addition = '; V25精确4写24读、490 AST/22标记、受保护PID/HTTP/哈希和生产CAS通过。'
            if addition not in row['evidence']: row['evidence'] += addition
    path.write_bytes((json.dumps(ledger, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    lines = ['# 智能助手全问题优化与核对方案', '', '状态：持续实施；最后核对：2026-09-17。',
        '权威来源：首次最终语义统计、33项执行台账和V25实际线上证据；本方案不宣称全部缺陷已解决。', '',
        '## 最终首次基线', '', '1233个有效已收集问题：269完整正确、186部分正确、636失败、89标准阻断、53证据不足。',
        '1091个可判题完整正确率24.66%；有效全集保守正确覆盖率21.82%。822个失败/部分题纳入新版复测，142个未定题先补标准或证据。',
        '知识类553题失败、85题部分，属于主要首次缺口；当前代码已有多轮知识修复，必须真实复测后判断恢复数量。原文覆盖与语义正确分开统计。',
        '89题标准阻断主要涉及原文或评分证据缺失，不能都称为标准冲突；833知识来源原文覆盖审计中的30条冲突是另一个口径。首次单题复核由失败改为部分正确，待复测822个ID集合不变；已发送V25计划保留此前冻结判定。', '',
        '## 路由流程', '', '用户指令 → 任务与来源边界 → 全对象/准确时间窗 → 只读步骤与依赖 → 完整类型化证据 → 固定计算/图表 → 允许的模型解释 → 逐子任务完成校验。',
        '普通解释可无工具；仅给定数据时本地计算；已完成简单查询复用证据；正式知识查岗位原文；新实时/历史问题调用对应只读工具。复合问题拆分后合成，禁止用一个成功子任务替代全部回答。', '',
        '## 33项逐项核对', '', '关联题统计为多标签，不能求和当总失败次数；每项完成须同时有代码、聚焦回归、生产原题复测和脱敏证据。', '',
        '|序号|问题|优先级|修复措施与逐项验收|当前状态|', '|---:|---|---|---|---|']
    for row in ledger['rows']:
        lines.append(f"|{row['order']}|{row['issue_id']} {row['title']}|{row['priority']}|{row['repair_and_acceptance_plan']}|{row['state']}|")
    lines += ['', '## 本轮生产实证', '',
        'V25生产提交6ec408b17db75a040028fdee843cbd1b5b63c5ff，8093 PID3736；159本机检查、14黄金题结构验证、独立Luna审查、4写24读和守卫发布均通过。',
        '822题复测实际发送1题，该题失败；821题独立证明未发。请求完整传入18点，图表工具只处理16点，图像HTTP200，但最终生命周期降级遗漏图表；首题后模型身份未核实停止。没有优化后全量准确率。',
        '下一轮先修复：工具禁止静默截断、完整结构证据不得剪成非法JSON、图表在生命周期异常后保留、最终完成合同核对对象/图表/来源。', '',
        '## 实施和评分顺序', '',
        '1. 修复本轮实际暴露的工具/证据/图表出口，再经本机回归、独立审查和受控8093部署。',
        '2. 在独立授权的批准Qwen固定窗口内，按完整claim恢复证明未发送的题；已发题仅在明确新版修复比较时重新测试，不原批次重试。',
        '3. 每题比对首次结果与本版最终答案：完整正确、部分正确、失败、标准阻断、证据不足，另列未发送和传输未知。',
        '4. 同题、同模型层分别统计完整正确率、完整有用回答率、传输完成率和耗时；不同模型结果明确分层，不声称纯代码因果收益。',
        '5. 原失败/部分题恢复覆盖完成后，再用新的未参与修复持出集验证泛化；不保证所有任意问题100%正确。合理澄清或明确依赖不足须如实记录。', '',
        '[逐题首次判定与哈希](../../tests/qa_regression/initial_semantic_summary_20260917.json)、[V25复测冻结](../../tests/qa_regression/routing_v25_paired_observations_20260917.json)、[821题未发送证据](../../tests/qa_regression/routing_v25_unattempted_dependencies_20260917.json)。']
    report = ROOT / 'docs/handoffs/2026-09-17-qa-full-optimization-plan.md'
    report.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    md = ROOT / 'tests/qa_regression/optimization_execution_ledger_20260916.md'
    old = md.read_text(encoding='utf-8')
    marker = '## 以下为V24历史状态\n\n'
    if marker in old: old = old.split(marker, 1)[1]
    prefix = '# QA 33项问题逐项执行台账\n\n状态：V24及此前历史快照已保留；最新权威状态已更新至V25。\n\n'
    prefix += '[最新33项详细方案](../../docs/handoffs/2026-09-17-qa-full-optimization-plan.md)；[最新机器台账](optimization_execution_ledger_20260916.json)。\n\n'
    prefix += '首次1233有效题完整判定：269通过、186部分、636失败、142未定；V25新版822题仅发送1题且失败，821题证明未发，不能报告全量优化后准确率。\n\n## 以下为V24历史状态\n\n'
    md.write_bytes((prefix+old).encode('utf-8'))
    print(json.dumps({'ok':True,'issue_count':33,'initial_valid':1233,'latest_attempted':1,'latest_unsent':821}))


if __name__ == '__main__':
    main()
