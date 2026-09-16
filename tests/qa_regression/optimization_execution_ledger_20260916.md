# QA 33项问题逐项执行台账

- 状态：执行中；最后核对：2026-09-16。
- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。
- 权威机器数据：[optimization_execution_ledger_20260916.json](optimization_execution_ledger_20260916.json)。
- 生产基线：`36b8d938f23923fca81026d7d668891bbf928dfb`；V9五题3通过/2部分/0失败，73项针对性回归通过；剩余项继续核对，非空不算通过。

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
|2|`QAOPT-R02` 历史问答与业务证据分离|P0|production_verified|V7三条owner隔离历史题通过，实际PostgreSQL占位符正确，生成摘录排除|补历史与当前数据复合任务|
|3|`QAOPT-R03` 完整解析多对象及范围|P1|deployed_partial_verified|V6实际A-D统计已返回；缺单位、零值和稀疏覆盖已明确标记|核对数据依赖后扩展多对象质量回归|
|4|`QAOPT-R04` 多时间窗与历史基线|P1|production_verified|V5真实相邻两窗统计、差值及相对变化通过；V4真实30日基线通过|扩展多对象、缺失数据及窗口覆盖回归|
|5|`QAOPT-R05` 报表工作流读取正文|P1|production_verified|V5真实最新日报摘要提取通过；缺摘要单独partial合同已验证|扩大报表类型并保持正文依赖和权威边界|
|6|`QAOPT-R06` 权威诊断和复合问题覆盖|P1|production_verified|2条诊断/复合分析题均通过生产复测|扩大持出集，保持每子任务完成合同|
|7|`QAOPT-R07` 无工具、用户数据与已有证据优先|P1|deployed_partial_verified|V7无工具题完整回复且0调用；因果方向仍需控制系统限定|修正工艺因果限定并复测|
|8|`QAOPT-R08` 禁代码策略不误伤正常回答|P0|production_verified|V9混合请求正常查询子任务通过，代码单独拒绝；纯代码不查询；全流式禁代码边界通过|扩展混合请求持出集，整体保持policy-limited partial|
|9|`QAOPT-R09` 统一能力说明与Prompt目标|P1|deployed_partial_verified|V8统一能力目标与允许证据，禁实时不抹掉允许的原文知识|核对所有复合与降级分支|
|10|`QAOPT-R10` 多轮范围继承与主题切换|P1|deployed_contract_verified|V6上下文主题/窗口/对象重置、600秒失效与禁止旧证据复用通过|真实多轮角色矩阵|
|11|`QAOPT-K01` 原文知识路由独立于现场数据|P0|deployed_partial_verified|V8正式原文/目录；V9指定小节代表题通过；833未全语义通过|原子条款与题库源冲突核对|
|12|`QAOPT-K02` 禁止用聊天或回归记录替代权威知识|P0|deployed_partial_verified|V8纯制度任务严格knowledge_doc与原文哈希，不用聊天/报表替代|复合制度任务补相同来源硬门|
|13|`QAOPT-K03` 完整章节及表格读取|P1|deployed_partial_verified|V8完整块分页；V9完整表格但多带下一节未编号标题|独立源标题边界与末尾覆盖核对|
|14|`QAOPT-K04` 避免通用知识补写正式制度|P0|deployed_partial_verified|V8未知正式制度明确澄清；确定性原文不生成条款|复合模型分支同样禁止补写|
|15|`QAOPT-K05` 报表目录不能回答制度问题|P1|deployed_partial_verified|V8纯制度绕开报表/聊天及跨文档top-k|复合双来源标签与独立覆盖|
|16|`QAOPT-K06` 知识数据质量和更新可追踪|P1|deployed_partial_verified|V8原文版本/更新/哈希、缺页和分页状态公开|独立章节末尾与源索引完整性|
|17|`QAOPT-E01` 成功证据不能被生命周期异常清空|P0|deployed_partial_verified|V3能在晚期异常时保留已成功证据；无证据生命周期失败仍开放|细分请求阶段并将成功证据独立提交|
|18|`QAOPT-E02` 有类型的证据与适用范围|P1|deployed_partial_verified|V6当前对象及A-D统计EvidenceItem绑定对象/时间/单位/来源|全部工具证据追加账本|
|19|`QAOPT-E03` 字段级事实校验与合理舍入|P0|deployed_contract_verified|字段级数值归属和舍入校验已通过聚焦测试|扩展到单位、时间戳和派生量血缘|
|20|`QAOPT-E04` 固定计算与统计定义|P1|deployed_partial_verified|V5相邻两窗/V6确定性统计及公式样本数质量限制|统一跨工具派生计算与冲突|
|21|`QAOPT-E05` 输出字段边界及完整性|P0|deployed_partial_verified|V6长度中止一次内部压缩；V8分页/V9策略缺项终态公开|全部复合子任务覆盖检查|
|22|`QAOPT-E06` 多源证据冲突与分析深度|P1|deployed_partial_verified|V6当前单点不推趋势；空间窗口均值不冒充同步温差|工艺因果限定与多源时效冲突|
|23|`QAOPT-O01` 模型就绪与请求间竞态|P0|production_reproduced_open|状态检查健康后SSE仍出现模型未驻留|请求级模型租约、单加载槽串行和就绪后再生成|
|24|`QAOPT-O02` 工具超时和故障域隔离|P1|planned|工具超时可扩大为整轮失败|按工具隔离超时、熔断、证据保留和一次无工具降级|
|25|`QAOPT-O03` 工具参数schema及步骤依赖|P1|planned|参数schema和步骤依赖未形成统一执行图|引入类型化StepPlan、输入输出schema和依赖检查|
|26|`QAOPT-O04` 状态、耗时与可观测性|P1|deployed_partial_verified|耗时、completion、语义待审状态公开；shared guest最终载荷仍包含全历史|兼容消息窗口与有界客户端契约|
|27|`QAOPT-O05` 并发与角色边界|P1|planned|并发请求、共享访客和角色能力缺系统矩阵|补并发预算、owner隔离和角色能力回归|
|28|`QAOPT-T01` 题目状态、分母与未知发送隔离|P0|implemented_verified|1418行分母、1259已收集和1条不确定发送已独立记录|保持不确定发送永不自动重放|
|29|`QAOPT-T02` 导入错误与评测污染|P0|implemented_partial_verified|原分母保持；833源题库新增编号与同问不同标准答案冲突审计|原子未编号条款特殊合同与oracle修正审查|
|30|`QAOPT-T03` 系统Prompt绑定与故障夹具|P1|partial|TaskPlan/故障夹具已建立；系统Prompt版本绑定仍需全链路证明|记录prompt_hash并覆盖工具/模型/流式故障|
|31|`QAOPT-T04` 全答案审阅、持出集与重复可靠性|P1|in_progress|仍有828条pending_semantic_review，非空未计通过|建立分层审阅、持出集和重复稳定性门|
|32|`QAOPT-T05` 版本冻结、候选对比与受控发布|P1|implemented_verified|V3至V9密封/守卫/CAS/受保护PID/定向单发送复测闭环|后续版本同流程|
|33|`QAOPT-T06` 范围缺口与长期运营|P2|ongoing|回归集已公开并可扩展，长期范围和SLO仍需运营|按新故障自动归类并每版发布覆盖/SLO报告|

## 固定处理顺序

1. **S1 线上明确失败**：R03 → R04 → R05 → O01 → R02/E01。
2. **S2 完成合同与证据类型**：E02 → O03 → E05 → E04/E06。
3. **S3 知识全文链**：K01 → K02/K04/K05 → K03/K06。
4. **S4 多轮与无工具回答**：R07 → R10 → R08/R09。
5. **S5 稳定性和全量评测**：O02/O04/O05 → T03/T04/T06。

每项只能在对应代码、聚焦回归、真实生产复测及脱敏证据四者齐全后标为 `resolved`。
