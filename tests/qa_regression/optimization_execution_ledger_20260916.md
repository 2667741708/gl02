# QA 33项问题逐项执行台账

- 状态：执行中；最后核对：2026-09-16。
- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。
- 权威机器数据：[optimization_execution_ledger_20260916.json](optimization_execution_ledger_20260916.json)。
- 生产基线：`312085a88ae95027728d5b8b72c4293af834d055`；V5已部署，八题复测2通过/4部分/2失败；V6候选106项回归通过。

## 借鉴 DSH 与 Codex 的实施边界

1. 采用 DSH 的可替换插件接缝：TaskPlan、实体解析、证据提供器、计算器、渲染器、终态校验分别演进，不再继续把规则堆进代理主文件。
2. 采用 DSH 的追加式会话事实：工具成功证据先提交到 EvidenceLedger，后续模型或生命周期失败不能抹掉已经成功的事实。
3. 采用 Codex 的 thread/turn/item 分层：一个用户问题是 turn，每个查询或模型调用是 step/item，均有开始、完成、失败、取消和未知状态。
4. 采用 Codex 的类型化工具与权限边界：TaskPlan固定允许的数据域和工具域；未知工具默认拒绝；用户明确禁实时查询时执行层也拒绝。
5. 采用结构化最终输出：CompletionContract逐项检查对象、窗口、来源、缺项和终态，避免答案非空但实际漏答。

参考：<https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md>；<https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>。

## 逐项状态

|序号|问题|优先级|当前状态|已核对证据|下一验收门|
|---:|---|---|---|---|---|
|1|`QAOPT-R01` 统一任务决策，阻止关键词抢路由|P0|deployed_partial_verified|V3 TaskPlan已在预取前运行；结构未知任务终态仍未收紧|补结构失败/歧义澄清门并做复合意图回归|
|2|`QAOPT-R02` 历史问答与业务证据分离|P0|deployed_partial_verified|V5三条历史检索均中文回答且owner受限；生成历史摘录再次被检索|V6排除生成摘录、回答角色过滤并复测|
|3|`QAOPT-R03` 完整解析多对象及范围|P1|deployed_partial_verified|V4三条代表题中CO/CO2/H2及南北探尺通过；A-D温差问句未过动作门|V5修复观测式问句并复测四点实际统计|
|4|`QAOPT-R04` 多时间窗与历史基线|P1|production_verified|V5真实相邻两窗统计、差值及相对变化通过；V4真实30日基线通过|扩展多对象、缺失数据及窗口覆盖回归|
|5|`QAOPT-R05` 报表工作流读取正文|P1|production_verified|V5真实最新日报摘要提取通过；缺摘要单独partial合同已验证|扩大报表类型并保持正文依赖和权威边界|
|6|`QAOPT-R06` 权威诊断和复合问题覆盖|P1|production_verified|2条诊断/复合分析题均通过生产复测|扩大持出集，保持每子任务完成合同|
|7|`QAOPT-R07` 无工具、用户数据与已有证据优先|P1|deployed_partial_verified|无工具题正确保持0调用，但答案因长度截断|加入无工具完成度检查和长度续写/压缩策略|
|8|`QAOPT-R08` 禁代码策略不误伤正常回答|P0|deployed_partial_verified|禁代码未再吞掉正常压力回答；1条因Origin合同未发送|用合规同源客户端复测并补混合请求部分拒绝|
|9|`QAOPT-R09` 统一能力说明与Prompt目标|P1|deployed_contract_verified|能力目标与工具域已进入V3 TaskPlan合同|统一所有分支的能力说明与终态文案|
|10|`QAOPT-R10` 多轮范围继承与主题切换|P1|planned|多轮上下文仍可能把旧对象/窗口带入新主题|给继承字段加来源回合、置信度和主题切换清空|
|11|`QAOPT-K01` 原文知识路由独立于现场数据|P0|deployed_contract_verified_semantic_pending|文档意图已独立于现场数据；833知识题尚未逐条语义通过|分层抽样后补全文知识专用执行器|
|12|`QAOPT-K02` 禁止用聊天或回归记录替代权威知识|P0|planned|仍需证明聊天、测试结果和报表不会替代权威文档|实施EvidenceSource类型和来源优先级硬门|
|13|`QAOPT-K03` 完整章节及表格读取|P1|planned|长章节和表格完整性尚无通过证据|章节树检索、分页聚合、表格行完整性校验|
|14|`QAOPT-K04` 避免通用知识补写正式制度|P0|planned|正式制度仍可能被通用知识补写|正式制度答案只允许权威文档事实并逐段标来源|
|15|`QAOPT-K05` 报表目录不能回答制度问题|P1|planned|报表目录与制度知识的证据域仍需彻底隔离|制度任务禁用report域并加配对回归|
|16|`QAOPT-K06` 知识数据质量和更新可追踪|P1|planned|知识版本、更新时间和缺章状态未统一暴露|建立KnowledgeManifest、版本哈希和缺口状态|
|17|`QAOPT-E01` 成功证据不能被生命周期异常清空|P0|deployed_partial_verified|V3能在晚期异常时保留已成功证据；无证据生命周期失败仍开放|细分请求阶段并将成功证据独立提交|
|18|`QAOPT-E02` 有类型的证据与适用范围|P1|planned|证据仍主要是字符串，适用对象/时间窗未完全类型化|建立EvidenceItem及适用范围schema|
|19|`QAOPT-E03` 字段级事实校验与合理舍入|P0|deployed_contract_verified|字段级数值归属和舍入校验已通过聚焦测试|扩展到单位、时间戳和派生量血缘|
|20|`QAOPT-E04` 固定计算与统计定义|P1|planned|统计定义和窗口边界仍分散在各工具|集中确定性计算库并输出公式/样本数/缺失规则|
|21|`QAOPT-E05` 输出字段边界及完整性|P0|planned|答案非空仍可能遗漏对象、步骤或末句|实现CompletionContract覆盖率和截断检测|
|22|`QAOPT-E06` 多源证据冲突与分析深度|P1|planned|多源冲突、时效差和分析深度没有统一裁决|建立冲突矩阵与事实/推断/建议分层|
|23|`QAOPT-O01` 模型就绪与请求间竞态|P0|production_reproduced_open|状态检查健康后SSE仍出现模型未驻留|请求级模型租约、单加载槽串行和就绪后再生成|
|24|`QAOPT-O02` 工具超时和故障域隔离|P1|planned|工具超时可扩大为整轮失败|按工具隔离超时、熔断、证据保留和一次无工具降级|
|25|`QAOPT-O03` 工具参数schema及步骤依赖|P1|planned|参数schema和步骤依赖未形成统一执行图|引入类型化StepPlan、输入输出schema和依赖检查|
|26|`QAOPT-O04` 状态、耗时与可观测性|P1|partial|已有部分耗时和tool trace；缺统一终态和覆盖指标|统一turn/step/tool事件、terminal_state和覆盖率指标|
|27|`QAOPT-O05` 并发与角色边界|P1|planned|并发请求、共享访客和角色能力缺系统矩阵|补并发预算、owner隔离和角色能力回归|
|28|`QAOPT-T01` 题目状态、分母与未知发送隔离|P0|implemented_verified|1418行分母、1259已收集和1条不确定发送已独立记录|保持不确定发送永不自动重放|
|29|`QAOPT-T02` 导入错误与评测污染|P0|implemented_verified|重复、结构无效、fixture和导入错误已从有效分母分层|持续对新增来源运行导入校验|
|30|`QAOPT-T03` 系统Prompt绑定与故障夹具|P1|partial|TaskPlan/故障夹具已建立；系统Prompt版本绑定仍需全链路证明|记录prompt_hash并覆盖工具/模型/流式故障|
|31|`QAOPT-T04` 全答案审阅、持出集与重复可靠性|P1|in_progress|仍有828条pending_semantic_review，非空未计通过|建立分层审阅、持出集和重复稳定性门|
|32|`QAOPT-T05` 版本冻结、候选对比与受控发布|P1|implemented_verified|V3经密封候选、受控部署、生产提交和定向复测|V4继续使用精确基线、差分候选和CAS记录|
|33|`QAOPT-T06` 范围缺口与长期运营|P2|ongoing|回归集已公开并可扩展，长期范围和SLO仍需运营|按新故障自动归类并每版发布覆盖/SLO报告|

## 固定处理顺序

1. **S1 线上明确失败**：R03 → R04 → R05 → O01 → R02/E01。
2. **S2 完成合同与证据类型**：E02 → O03 → E05 → E04/E06。
3. **S3 知识全文链**：K01 → K02/K04/K05 → K03/K06。
4. **S4 多轮与无工具回答**：R07 → R10 → R08/R09。
5. **S5 稳定性和全量评测**：O02/O04/O05 → T03/T04/T06。

每项只能在对应代码、聚焦回归、真实生产复测及脱敏证据四者齐全后标为 `resolved`。
