"""Build the auditable 33-item QA remediation execution ledger."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tests" / "qa_regression" / "optimization_issue_catalog_20260916.json"
OUT_JSON = ROOT / "tests" / "qa_regression" / "optimization_execution_ledger_20260916.json"
OUT_MD = ROOT / "tests" / "qa_regression" / "optimization_execution_ledger_20260916.md"


STATUS = {
    "QAOPT-R01": ("deployed_partial_verified", "V3 TaskPlan已在预取前运行；结构未知任务终态仍未收紧", "补结构失败/歧义澄清门并做复合意图回归"),
    "QAOPT-R02": ("deployed_partial_verified", "V5三条历史检索均中文回答且owner受限；生成历史摘录再次被检索", "V6排除生成摘录、回答角色过滤并复测"),
    "QAOPT-R03": ("deployed_partial_verified", "V4三条代表题中CO/CO2/H2及南北探尺通过；A-D温差问句未过动作门", "V5修复观测式问句并复测四点实际统计"),
    "QAOPT-R04": ("production_verified", "V5真实相邻两窗统计、差值及相对变化通过；V4真实30日基线通过", "扩展多对象、缺失数据及窗口覆盖回归"),
    "QAOPT-R05": ("production_verified", "V5真实最新日报摘要提取通过；缺摘要单独partial合同已验证", "扩大报表类型并保持正文依赖和权威边界"),
    "QAOPT-R06": ("production_verified", "2条诊断/复合分析题均通过生产复测", "扩大持出集，保持每子任务完成合同"),
    "QAOPT-R07": ("deployed_partial_verified", "无工具题正确保持0调用，但答案因长度截断", "加入无工具完成度检查和长度续写/压缩策略"),
    "QAOPT-R08": ("deployed_partial_verified", "禁代码未再吞掉正常压力回答；1条因Origin合同未发送", "用合规同源客户端复测并补混合请求部分拒绝"),
    "QAOPT-R09": ("deployed_contract_verified", "能力目标与工具域已进入V3 TaskPlan合同", "统一所有分支的能力说明与终态文案"),
    "QAOPT-R10": ("planned", "多轮上下文仍可能把旧对象/窗口带入新主题", "给继承字段加来源回合、置信度和主题切换清空"),
    "QAOPT-K01": ("deployed_contract_verified_semantic_pending", "文档意图已独立于现场数据；833知识题尚未逐条语义通过", "分层抽样后补全文知识专用执行器"),
    "QAOPT-K02": ("planned", "仍需证明聊天、测试结果和报表不会替代权威文档", "实施EvidenceSource类型和来源优先级硬门"),
    "QAOPT-K03": ("planned", "长章节和表格完整性尚无通过证据", "章节树检索、分页聚合、表格行完整性校验"),
    "QAOPT-K04": ("planned", "正式制度仍可能被通用知识补写", "正式制度答案只允许权威文档事实并逐段标来源"),
    "QAOPT-K05": ("planned", "报表目录与制度知识的证据域仍需彻底隔离", "制度任务禁用report域并加配对回归"),
    "QAOPT-K06": ("planned", "知识版本、更新时间和缺章状态未统一暴露", "建立KnowledgeManifest、版本哈希和缺口状态"),
    "QAOPT-E01": ("deployed_partial_verified", "V3能在晚期异常时保留已成功证据；无证据生命周期失败仍开放", "细分请求阶段并将成功证据独立提交"),
    "QAOPT-E02": ("planned", "证据仍主要是字符串，适用对象/时间窗未完全类型化", "建立EvidenceItem及适用范围schema"),
    "QAOPT-E03": ("deployed_contract_verified", "字段级数值归属和舍入校验已通过聚焦测试", "扩展到单位、时间戳和派生量血缘"),
    "QAOPT-E04": ("planned", "统计定义和窗口边界仍分散在各工具", "集中确定性计算库并输出公式/样本数/缺失规则"),
    "QAOPT-E05": ("planned", "答案非空仍可能遗漏对象、步骤或末句", "实现CompletionContract覆盖率和截断检测"),
    "QAOPT-E06": ("planned", "多源冲突、时效差和分析深度没有统一裁决", "建立冲突矩阵与事实/推断/建议分层"),
    "QAOPT-O01": ("production_reproduced_open", "状态检查健康后SSE仍出现模型未驻留", "请求级模型租约、单加载槽串行和就绪后再生成"),
    "QAOPT-O02": ("planned", "工具超时可扩大为整轮失败", "按工具隔离超时、熔断、证据保留和一次无工具降级"),
    "QAOPT-O03": ("planned", "参数schema和步骤依赖未形成统一执行图", "引入类型化StepPlan、输入输出schema和依赖检查"),
    "QAOPT-O04": ("partial", "已有部分耗时和tool trace；缺统一终态和覆盖指标", "统一turn/step/tool事件、terminal_state和覆盖率指标"),
    "QAOPT-O05": ("planned", "并发请求、共享访客和角色能力缺系统矩阵", "补并发预算、owner隔离和角色能力回归"),
    "QAOPT-T01": ("implemented_verified", "1418行分母、1259已收集和1条不确定发送已独立记录", "保持不确定发送永不自动重放"),
    "QAOPT-T02": ("implemented_verified", "重复、结构无效、fixture和导入错误已从有效分母分层", "持续对新增来源运行导入校验"),
    "QAOPT-T03": ("partial", "TaskPlan/故障夹具已建立；系统Prompt版本绑定仍需全链路证明", "记录prompt_hash并覆盖工具/模型/流式故障"),
    "QAOPT-T04": ("in_progress", "仍有828条pending_semantic_review，非空未计通过", "建立分层审阅、持出集和重复稳定性门"),
    "QAOPT-T05": ("implemented_verified", "V3经密封候选、受控部署、生产提交和定向复测", "V4继续使用精确基线、差分候选和CAS记录"),
    "QAOPT-T06": ("ongoing", "回归集已公开并可扩展，长期范围和SLO仍需运营", "按新故障自动归类并每版发布覆盖/SLO报告"),
}

# Current verified evidence supersedes earlier phase snapshots above.
STATUS.update({
    "QAOPT-R02": ("production_verified", "V7三条owner隔离历史题通过，实际PostgreSQL占位符正确，生成摘录排除", "补历史与当前数据复合任务"),
    "QAOPT-R03": ("deployed_partial_verified", "V6实际A-D统计已返回；缺单位、零值和稀疏覆盖已明确标记", "核对数据依赖后扩展多对象质量回归"),
    "QAOPT-R07": ("deployed_partial_verified", "V7无工具题完整回复且0调用；因果方向仍需控制系统限定", "修正工艺因果限定并复测"),
    "QAOPT-R08": ("production_verified", "V9混合请求正常查询子任务通过，代码单独拒绝；纯代码不查询；全流式禁代码边界通过", "扩展混合请求持出集，整体保持policy-limited partial"),
    "QAOPT-R09": ("deployed_partial_verified", "V8统一能力目标与允许证据，禁实时不抹掉允许的原文知识", "核对所有复合与降级分支"),
    "QAOPT-R10": ("deployed_contract_verified", "V6上下文主题/窗口/对象重置、600秒失效与禁止旧证据复用通过", "真实多轮角色矩阵"),
    "QAOPT-K01": ("deployed_partial_verified", "V8正式原文/目录；V9指定小节代表题通过；833未全语义通过", "原子条款与题库源冲突核对"),
    "QAOPT-K02": ("deployed_partial_verified", "V8纯制度任务严格knowledge_doc与原文哈希，不用聊天/报表替代", "复合制度任务补相同来源硬门"),
    "QAOPT-K03": ("deployed_partial_verified", "V8完整块分页；V9完整表格但多带下一节未编号标题", "独立源标题边界与末尾覆盖核对"),
    "QAOPT-K04": ("deployed_partial_verified", "V8未知正式制度明确澄清；确定性原文不生成条款", "复合模型分支同样禁止补写"),
    "QAOPT-K05": ("deployed_partial_verified", "V8纯制度绕开报表/聊天及跨文档top-k", "复合双来源标签与独立覆盖"),
    "QAOPT-K06": ("deployed_partial_verified", "V8原文版本/更新/哈希、缺页和分页状态公开", "独立章节末尾与源索引完整性"),
    "QAOPT-E02": ("deployed_partial_verified", "V6当前对象及A-D统计EvidenceItem绑定对象/时间/单位/来源", "全部工具证据追加账本"),
    "QAOPT-E04": ("deployed_partial_verified", "V5相邻两窗/V6确定性统计及公式样本数质量限制", "统一跨工具派生计算与冲突"),
    "QAOPT-E05": ("deployed_partial_verified", "V6长度中止一次内部压缩；V8分页/V9策略缺项终态公开", "全部复合子任务覆盖检查"),
    "QAOPT-E06": ("deployed_partial_verified", "V6当前单点不推趋势；空间窗口均值不冒充同步温差", "工艺因果限定与多源时效冲突"),
    "QAOPT-O04": ("deployed_partial_verified", "耗时、completion、语义待审状态公开；shared guest最终载荷仍包含全历史", "兼容消息窗口与有界客户端契约"),
    "QAOPT-T02": ("implemented_partial_verified", "原分母保持；833源题库新增编号与同问不同标准答案冲突审计", "原子未编号条款特殊合同与oracle修正审查"),
    "QAOPT-T05": ("implemented_verified", "V3至V9密封/守卫/CAS/受保护PID/定向单发送复测闭环", "后续版本同流程"),
})


STATUS.update({
    'QAOPT-R01': ('deployed_partial_verified', 'V12制度子任务隔离、未知来源澄清；V13简单读取独立完成', '结构未知与全部复合子任务覆盖门'),
    'QAOPT-R07': ('production_verified', 'V12顶压调节控制和风温/焦比/喷煤条件性因果两题独立语义通过，0外部工具', '扩展工艺持出集和稳定性'),
    'QAOPT-R08': ('production_verified', 'V9/V12正常数据查询保留，代码子请求独立拒绝并标策略部分完成', '保留禁执行和禁生成代码，扩展混合类型'),
    'QAOPT-K01': ('production_coverage_verified_semantic_partial', 'V11有效803题真实单发送全部原文覆盖和来源/版本合同通过；30源标准答案冲突阻断', '独立语义持出审查与版本化修正30个oracle'),
    'QAOPT-K02': ('deployed_partial_verified', 'V12制度原文与实时/用户数据子任务隔离，原文由独立执行器完成', '扩展多书名、多章节及不可分复合问题'),
    'QAOPT-K03': ('deployed_partial_verified', 'V10完整表格、短术语、长原句和小节边界真实通过；V11有效803题原文覆盖', '索引独立末尾完整性门及多引用聚合'),
    'QAOPT-K04': ('production_verified', '纯制度及V12/V13未知制度复合题均明确澄清，不补写条款', '扩展未知标题持出集'),
    'QAOPT-K05': ('deployed_partial_verified', '纯制度绕开报表/聊天；复合分支过滤正式原文问题与旧聊天，独立原文合成', '全部来源组合持出回归'),
    'QAOPT-K06': ('deployed_partial_verified', '版本/哈希已公开；只读独立审计5897源非空行在原子索引中无缺行，聚合片段所有原文行属于权威源', '执行器独立缺失末尾门，不能仅凭连续片段编号推完整'),
    'QAOPT-E01': ('deployed_partial_verified', 'V12晚期失败保留成功的可读有界证据，未知结构不伪装成事实，错误不输出原文', '所有工具类型的追加证据账本'),
    'QAOPT-E03': ('deployed_partial_verified', 'V14实际压力单位/时间/来源及规范单位血缘独立通过，未知制度partial；未登记单位partial合同通过', '全部工具单位/派生量血缘'),
    'QAOPT-E06': ('deployed_partial_verified', '单点不推趋势、窗口均值不冒充同步温差、V12控制与热平衡条件性因果通过', '跨源冲突和时效矩阵'),
    'QAOPT-O01': ('production_dependency_open', '新部署器最多3次只读GET检查并保留失败状态；运行时仍出现批准模型未驻留', '核对跨服务模型占槽/请求租约；不修改Ollama或8094配置'),
    'QAOPT-O02': ('deployed_partial_verified', '执行器已有独立超时/每服务预算；V12成功证据保留和失败不扩散合同通过', 'MCP注册/会话/流式故障矩阵'),
    'QAOPT-O03': ('deployed_contract_verified', 'V12实际部署StepPlan依赖绑定、声明上游和环检查；67项DAG/完整性测试通过', '全部工具输入输出类型化及实际故障矩阵'),
    'QAOPT-O04': ('deployed_partial_verified', 'V11受控turn投影实际803题和定向题均仅返回当前2条消息；浏览器默认全历史兼容保留', '浏览器有界消息合并与历史分页，现场UI验收'),
    'QAOPT-T02': ('implemented_partial_verified', '原分母保留；833知识源明确30个编号/同问不同标准答案冲突，禁止当失败重发或自动改标准', '版本化修正经原文独立审核'),
    'QAOPT-T04': ('in_progress', '历史828待语义审查为旧快照；新有效803题原文覆盖已核验，30oracle阻断单列，不称833全通过', '旧case_id逐条对齐新覆盖结果及独立语义持出审查'),
    'QAOPT-T05': ('implemented_verified', 'V3至V14受控部署/CAS/保护PID/一次发送闭环；V12/V13启动健康失败先回滚只读恢复', '后续版本保持冻结字节与短阶段执行'),
})


STATUS.update({
    'QAOPT-R10': ('deployed_partial_verified', 'V15真实120分钟窗口后最新追问使用当前单点；无效时钟/非法窗口及清旧证据聚焦测试通过', '来源消息ID全链路绑定与多角色真实多轮矩阵'),
    'QAOPT-K03': ('deployed_partial_verified', 'V15多章节逐项原文真实通过、缺章partial；选中章节缺尾及缓存删改失效门部署', '独立岗位元数据和原子条款边界审核，扩大多引用持出集'),
    'QAOPT-K06': ('deployed_partial_verified', 'V15独立权威源全文行覆盖门和选中岗位跨索引缺尾门；实际833只读803覆盖候选通过/30冲突单列', '语义角色与源范围独立验证，版本化修正30项oracle'),
    'QAOPT-E05': ('deployed_partial_verified', 'V15多章节逐子任务完成与缺章partial真实通过，保持旧长度中止内部修复合同', '全部复合源及全部模型工具分支完成覆盖'),
    'QAOPT-T05': ('implemented_verified', 'V3至V15密封/8093-only守卫/CAS/保护PID/一次POST和独立审阅闭环', '后续版本保持当前冻结字节和精确基线'),
})


STATUS.update({
    'QAOPT-R02': ('deployed_partial_verified', 'V7身份隔离历史通过；V16独立历史/当前编排已部署，V17三种历史+当前/原文真实完成通过，无匹配明确，禁工具策略保留', '不可分历史推断及全来源复合持出集'),
    'QAOPT-E05': ('deployed_partial_verified', 'V15多章逐任务合同；V17既有原文合同归一化和实际最新工具事实复验，真实五题完成/缺项状态独立通过', '全部工具及模型分支完成覆盖，不凭非空升级'),
    'QAOPT-T05': ('implemented_verified', 'V3至V17密封/8093-only守卫/CAS/保护PID/一次POST闭环；V16三失败原样冻结，V17五通过独立审阅', '后续版本保持冻结字节、精确基线和独立审查'),
})


STATUS.update({
    'QAOPT-R10': ('deployed_partial_verified', 'V19服务端对象/窗口来源ID与owner user ancestry生产只读6/6通过；真实六题五通过一失败，旧窗口清除/换题/用户数据通过', '30分钟指代趋势答案失败需修复；operator/admin多轮并发矩阵'),
    'QAOPT-E01': ('deployed_partial_verified', 'V19实际CursorAdapter RETURNING绑定修复，真实适配器回归通过；WINDOW生命周期失败仅保留时间范围尚不满足答案', '成功工具结果的完整可读恢复与所有工具追加证据账本'),
    'QAOPT-O01': ('production_dependency_open', 'V18首次启动因批准模型未驻留回滚，用户明确授权后重部署；V19两次题目发送前阻断，仅未发送题续跑', '请求级模型驻留租约和跨服务占槽核查，不修改Ollama或8094配置'),
    'QAOPT-T05': ('implemented_verified', 'V3至V19受控切换/保护PID/CAS；回滚不自动重试，V18失败与V19五通过一失败分别冻结；续跑claim严格去重', '后续版本保持冻结字节、实际适配器测试及独立答案审查'),
})


STATUS.update({
    'QAOPT-R10': ('deployed_partial_verified', 'V19来源绑定生产6/6通过；V20修正规划器指代词，真实30分钟追问/最新/换题/用户分析5/5及数据库来源5/5通过', 'operator/admin真实多轮并发与指代持出集'),
    'QAOPT-E01': ('deployed_partial_verified', 'V19实际适配器绑定修复；V20已知指代趋势不再走失败绘图规划，确定性统计完整返回', '全部工具成功证据恢复与追加账本'),
    'QAOPT-E05': ('deployed_partial_verified', 'V15多章、V17历史复合、V20多轮代表题答案完成独立通过；趋势模型解释拒绝单列', '全部工具及模型分支完成覆盖，不凭非空升级'),
    'QAOPT-T05': ('implemented_verified', 'V3至V20受控切换/保护PID/CAS；V18/V19失败冻结，V20新五题独立通过；实际适配器和续跑claim去重门保持', '后续版本保持冻结字节与独立最终答案审查'),
})


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    issues = catalog["issues"]
    ids = [item["id"] for item in issues]
    if set(ids) != set(STATUS):
        raise ValueError(f"status coverage mismatch: missing={set(ids)-set(STATUS)} extra={set(STATUS)-set(ids)}")
    rows = []
    for order, item in enumerate(issues, start=1):
        state, evidence, next_gate = STATUS[item["id"]]
        rows.append({
            "order": order,
            "issue_id": item["id"],
            "priority": item["priority"],
            "title": item["title"],
            "state": state,
            "evidence": evidence,
            "next_gate": next_gate,
            "case_ids": item.get("case_ids") or [],
            "depends_on": item.get("depends_on") or [],
        })
    payload = {
        "schema": "bf.qa.optimization-execution-ledger.v1",
        "requirement_id": "REQ-QA-FULL-ISSUE-INVENTORY-20260916",
        "checked_at": "2026-09-16",
        "production_commit": "4304243a1e53cee2ed35c8f541b38be2d359f55e",
        "production_retest": {"passed": 2, "partial": 6, "failed": 7, "blocked_client_contract": 1},
        "latest_production_retest": {"version": "routing-v20", "requests": 5, "sse_done": 5, "passed": 5, "failed": 0, "provenance_readonly_passed": 5, "automatic_post_retries": 0},
        "knowledge_collection": {"source": 833, "valid_once_only_requests": 803, "original_coverage_contract_verified": 803, "oracle_conflicts_blocked": 30, "full_semantic_pass_inferred": False},
        "current_local_candidate": {"version": "next", "issues": ["QAOPT-K06", "QAOPT-R02", "QAOPT-R10", "QAOPT-O04", "QAOPT-T02", "QAOPT-T04"], "state": "remaining_items_in_progress"},
        "rows": rows,
    }
    OUT_JSON.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    lines = [
        "# QA 33项问题逐项执行台账",
        "",
        "- 状态：执行中；最后核对：2026-09-16。",
        "- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。",
        "- 权威机器数据：[optimization_execution_ledger_20260916.json](optimization_execution_ledger_20260916.json)。",
        "- 生产修复版本：`ab0dafa3f2008b819ed40211b43a17858ecf654c`；V16发现三项完成合同失败，V17新轮五题单发送并独立通过，缺章及禁工具历史按预期partial。有效803知识题已核验原文覆盖，30题标准答案冲突阻断；剩余项继续修复，非空不算通过。",
        "- 最新权威实施：[V17生产修复交接](../../docs/handoffs/2026-09-16-qa-routing-v17-production.md)。旧阶段记录保留为历史证据。",
        "",
        "## 借鉴 DSH 与 Codex 的实施边界",
        "",
        "1. 采用 DSH 的可替换插件接缝：TaskPlan、实体解析、证据提供器、计算器、渲染器、终态校验分别演进，不再继续把规则堆进代理主文件。",
        "2. 采用 DSH 的追加式会话事实：工具成功证据先提交到 EvidenceLedger，后续模型或生命周期失败不能抹掉已经成功的事实。",
        "3. 采用 Codex 的 thread/turn/item 分层：一个用户问题是 turn，每个查询或模型调用是 step/item，均有开始、完成、失败、取消和未知状态。",
        "4. 采用 Codex 的类型化工具与权限边界：TaskPlan固定允许的数据域和工具域；未知工具默认拒绝；用户明确禁实时查询时执行层也拒绝。",
        "5. 采用结构化最终输出：CompletionContract逐项检查对象、窗口、来源、缺项和终态，避免答案非空但实际漏答。",
        "",
        "参考：<https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md>；<https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>。",
        "",
        "## 逐项状态",
        "",
        "|序号|问题|优先级|当前状态|已核对证据|下一验收门|",
        "|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"|{row['order']}|`{row['issue_id']}` {row['title']}|{row['priority']}|{row['state']}|"
            f"{row['evidence']}|{row['next_gate']}|"
        )
    lines.extend([
        "",
        "## 固定处理顺序",
        "",
        "1. **S1 线上明确失败**：R03 → R04 → R05 → O01 → R02/E01。",
        "2. **S2 完成合同与证据类型**：E02 → O03 → E05 → E04/E06。",
        "3. **S3 知识全文链**：K01 → K02/K04/K05 → K03/K06。",
        "4. **S4 多轮与无工具回答**：R07 → R10 → R08/R09。",
        "5. **S5 稳定性和全量评测**：O02/O04/O05 → T03/T04/T06。",
        "",
        "每项只能在对应代码、聚焦回归、真实生产复测及脱敏证据四者齐全后标为 `resolved`。",
    ])
    OUT_MD.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(json.dumps({"ok": True, "issues": len(rows), "json": str(OUT_JSON), "markdown": str(OUT_MD)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
