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
    "QAOPT-R02": ("deployed_partial_verified", "3条生产复测中2条路由正确但渲染不佳，1条生命周期失败", "完成历史结果中文投影、owner隔离和生命周期保全"),
    "QAOPT-R03": ("local_candidate_verified", "V4实体解析器已覆盖CO/CO2/H2、A-D、南北探尺，19项聚焦测试通过", "受控部署后只复测3条代表题"),
    "QAOPT-R04": ("local_candidate_verified", "V4已补TaskPlan门禁、固定时区锚点、两窗串行与30日基线质量/时间校验；本机合同已通过", "受控部署后各首次复测1次，核对两窗/基线实际证据"),
    "QAOPT-R05": ("local_candidate_verified", "V4已补list→select→read→摘要摘录；中文字符/字节截断缺陷已在准确生产MCP基线上修正", "受控部署后复测真实日报摘要；长报表无摘要章节时保持明确摘录边界"),
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
        "production_commit": "70b36c52c2ccddb1fa08429fc0fe6455cfff4ba9",
        "production_retest": {"passed": 2, "partial": 6, "failed": 7, "blocked_client_contract": 1},
        "current_local_candidate": {"version": "routing-v4", "issues": ["QAOPT-R03", "QAOPT-R04", "QAOPT-R05"], "state": "local_candidate_verified_production_pending"},
        "rows": rows,
    }
    OUT_JSON.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    lines = [
        "# QA 33项问题逐项执行台账",
        "",
        "- 状态：执行中；最后核对：2026-09-16。",
        "- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。",
        "- 权威机器数据：[optimization_execution_ledger_20260916.json](optimization_execution_ledger_20260916.json)。",
        "- 生产基线：`70b36c52c2ccddb1fa08429fc0fe6455cfff4ba9`；V4本机候选覆盖 `QAOPT-R03/R04/R05`，尚未部署；R05全文完整性仍待验收。",
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
