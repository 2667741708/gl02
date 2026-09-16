# QA 33项问题逐项执行台账

- 状态：执行中；最后核对：2026-09-17。
- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`。
- 权威机器数据：[optimization_execution_ledger_20260916.json](optimization_execution_ledger_20260916.json)。
- 最新生产版本：V23 `baaa7496afbd43b35be98c1e231f79a71d3aa7cf`，8093 PID19444，受控验收与CAS记录通过。407题计划及安全续跑累计已发9题：2通过、4部分、3失败；身份稳定采样7题中2题正确完整（28.57%，仅小样本）。398道首次失败原题未发送，均有逐题依赖阻断记录；1条首次未知永不重放。
- 最新权威实施：[V23生产与失败题核验](../../docs/handoffs/2026-09-17-qa-v23-single-window-routing.md)及[模型固定窗口/V24逐项方案](../../docs/handoffs/2026-09-17-qa-model-window-and-v24-plan.md)。33项均保留实际验证范围，未全部解决；旧阶段记录仅作为历史证据。

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
|1|QAOPT-R01 统一任务决策，阻止关键词抢路由|P0|deployed_partial_verified|V12制度子任务隔离、未知来源澄清；V13简单读取独立完成; V23全文审核：TPL-342113EAB17420C6 failed|结构未知与全部复合子任务覆盖门|
|2|QAOPT-R02 历史问答与业务证据分离|P0|deployed_partial_verified|V7身份隔离历史通过；V16独立历史/当前编排已部署，V17三种历史+当前/原文真实完成通过，无匹配明确，禁工具策略保留|不可分历史推断及全来源复合持出集|
|3|QAOPT-R03 完整解析多对象及范围|P1|deployed_partial_verified|V6实际A-D统计已返回；缺单位、零值和稀疏覆盖已明确标记; V23全文审核：TPL-FACD6F5FE05C74FC partial；TPL-342113EAB17420C6 failed；TPL-C5DF79304112ED85 failed|核对数据依赖后扩展多对象质量回归|
|4|QAOPT-R04 多时间窗与历史基线|P1|production_verified|V5真实相邻两窗统计、差值及相对变化通过；V4真实30日基线通过|扩展多对象、缺失数据及窗口覆盖回归|
|5|QAOPT-R05 报表工作流读取正文|P1|production_verified|V5真实最新日报摘要提取通过；缺摘要单独partial合同已验证|扩大报表类型并保持正文依赖和权威边界|
|6|QAOPT-R06 权威诊断和复合问题覆盖|P1|production_verified|2条诊断/复合分析题均通过生产复测|扩大持出集，保持每子任务完成合同|
|7|QAOPT-R07 无工具、用户数据与已有证据优先|P1|production_verified|V12顶压调节控制和风温/焦比/喷煤条件性因果两题独立语义通过，0外部工具|扩展工艺持出集和稳定性|
|8|QAOPT-R08 禁代码策略不误伤正常回答|P0|production_verified|V9/V12正常数据查询保留，代码子请求独立拒绝并标策略部分完成|保留禁执行和禁生成代码，扩展混合类型|
|9|QAOPT-R09 统一能力说明与Prompt目标|P1|deployed_partial_verified|V8统一能力目标与允许证据，禁实时不抹掉允许的原文知识; V23全文审核：TPL-C5DF79304112ED85 failed|核对所有复合与降级分支|
|10|QAOPT-R10 多轮范围继承与主题切换|P1|deployed_partial_verified|V19来源绑定生产6/6通过；V20修正规划器指代词，真实30分钟追问/最新/换题/用户分析5/5及数据库来源5/5通过|operator/admin真实多轮与指代持出集；并发发送应按用户限定独占拒绝|
|11|QAOPT-K01 原文知识路由独立于现场数据|P0|production_coverage_verified_semantic_partial|V11有效803题真实单发送全部原文覆盖和来源/版本合同通过；30源标准答案冲突阻断|独立语义持出审查与版本化修正30个oracle|
|12|QAOPT-K02 禁止用聊天或回归记录替代权威知识|P0|deployed_partial_verified|V12制度原文与实时/用户数据子任务隔离，原文由独立执行器完成|扩展多书名、多章节及不可分复合问题|
|13|QAOPT-K03 完整章节及表格读取|P1|deployed_partial_verified|V15多章节逐项原文真实通过、缺章partial；选中章节缺尾及缓存删改失效门部署|独立岗位元数据和原子条款边界审核，扩大多引用持出集|
|14|QAOPT-K04 避免通用知识补写正式制度|P0|production_verified|纯制度及V12/V13未知制度复合题均明确澄清，不补写条款|扩展未知标题持出集|
|15|QAOPT-K05 报表目录不能回答制度问题|P1|deployed_partial_verified|纯制度绕开报表/聊天；复合分支过滤正式原文问题与旧聊天，独立原文合成|全部来源组合持出回归|
|16|QAOPT-K06 知识数据质量和更新可追踪|P1|deployed_partial_verified|V15独立权威源全文行覆盖门和选中岗位跨索引缺尾门；实际833只读803覆盖候选通过/30冲突单列|语义角色与源范围独立验证，版本化修正30项oracle|
|17|QAOPT-E01 成功证据不能被生命周期异常清空|P0|deployed_partial_verified|V19实际适配器绑定修复；V20已知指代趋势不再走失败绘图规划，确定性统计完整返回; V23全文审核：TPL-01EEE414179DB624 partial；TPL-BE97AA4EAD567003 failed; V23r2 TPL-A60B0CD794D49E48部分，成功最新值保留但重复规划近百秒、单位缺失，后身份未核实|全部工具成功证据恢复与追加账本|
|18|QAOPT-E02 有类型的证据与适用范围|P1|deployed_partial_verified|V6当前对象及A-D统计EvidenceItem绑定对象/时间/单位/来源; V23全文审核：TPL-E1C7A67C947531E9 partial|全部工具证据追加账本|
|19|QAOPT-E03 字段级事实校验与合理舍入|P0|deployed_partial_verified|V14实际压力单位/时间/来源及规范单位血缘独立通过，未知制度partial；未登记单位partial合同通过|全部工具单位/派生量血缘|
|20|QAOPT-E04 固定计算与统计定义|P1|deployed_partial_verified|V5相邻两窗/V6确定性统计及公式样本数质量限制; V23全文审核：TPL-FACD6F5FE05C74FC partial；TPL-01EEE414179DB624 partial; V23r2 TPL-A60B0CD794D49E48部分，成功最新值保留但重复规划近百秒、单位缺失，后身份未核实|统一跨工具派生计算与冲突|
|21|QAOPT-E05 输出字段边界及完整性|P0|deployed_partial_verified|V15多章、V17历史复合、V20多轮代表题答案完成独立通过；趋势模型解释拒绝单列|全部工具及模型分支完成覆盖，不凭非空升级|
|22|QAOPT-E06 多源证据冲突与分析深度|P1|deployed_partial_verified|单点不推趋势、窗口均值不冒充同步温差、V12控制与热平衡条件性因果通过; V23全文审核：TPL-FACD6F5FE05C74FC partial|跨源冲突和时效矩阵|
|23|QAOPT-O01 模型就绪与请求间竞态|P0|dependency_blocked|V21复测4题后latest digest变化阻断；只读证明自动Repair候选失败后切换:1/:0，标签与实际驻留曾不一致；就绪true仍不能证明固定版本; V23全文审核：TPL-BE97AA4EAD567003 failed; V23r2 TPL-A60B0CD794D49E48部分，成功最新值保留但重复规划近百秒、单位缺失，后身份未核实|单独授权受控模型窗口，原状态恢复验证后续跑399明确未发送题|
|24|QAOPT-O02 工具超时和故障域隔离|P1|deployed_partial_verified|执行器已有独立超时/每服务预算；V12成功证据保留和失败不扩散合同通过|MCP注册/会话/流式故障矩阵|
|25|QAOPT-O03 工具参数schema及步骤依赖|P1|deployed_contract_verified|V12实际部署StepPlan依赖绑定、声明上游和环检查；67项DAG/完整性测试通过|全部工具输入输出类型化及实际故障矩阵|
|26|QAOPT-O04 状态、耗时与可观测性|P1|deployed_partial_verified|V11受控turn投影实际803题和定向题均仅返回当前2条消息；浏览器默认全历史兼容保留|浏览器有界消息合并与历史分页，现场UI验收|
|27|QAOPT-O05 并发与角色边界|P1|deployed_partial_verified|V21已受控发布：精确控制模块、受保护PID及生产CAS通过；独占9项和关联35项本机通过；真实双角色409/取消验收待测|固定模型版本后完成真实双角色409、取消实际停止释放与owner隔离；不排队、不重放|
|28|QAOPT-T01 题目状态、分母与未知发送隔离|P0|implemented_verified|1418行分母、1259已收集和1条不确定发送已独立记录|保持不确定发送永不自动重放|
|29|QAOPT-T02 导入错误与评测污染|P0|implemented_partial_verified|原分母保留；833知识源明确30个编号/同问不同标准答案冲突，禁止当失败重发或自动改标准|版本化修正经原文独立审核|
|30|QAOPT-T03 系统Prompt绑定与故障夹具|P1|partial|TaskPlan/故障夹具已建立；系统Prompt版本绑定仍需全链路证明|记录prompt_hash并覆盖工具/模型/流式故障|
|31|QAOPT-T04 全答案审阅、持出集与重复可靠性|P1|in_progress|历史828待语义审查为旧快照；新有效803题原文覆盖已核验，30oracle阻断单列，不称833全通过; V23全文审核：TPL-E1C7A67C947531E9 partial|828真实逐题审核完成；初筛默认passed结果不作为语义准确率|
|32|QAOPT-T05 版本冻结、候选对比与受控发布|P1|implemented_verified|V3至V20受控切换/保护PID/CAS；V18/V19失败冻结，V20新五题独立通过；实际适配器和续跑claim去重门保持|后续版本保持冻结字节与独立最终答案审查|
|33|QAOPT-T06 范围缺口与长期运营|P2|ongoing|回归集已公开并可扩展，长期范围和SLO仍需运营|按新故障自动归类并每版发布覆盖/SLO报告|


## 固定处理顺序

1. **S1 线上明确失败**：R03 → R04 → R05 → O01 → R02/E01。
2. **S2 完成合同与证据类型**：E02 → O03 → E05 → E04/E06。
3. **S3 知识全文链**：K01 → K02/K04/K05 → K03/K06。
4. **S4 多轮与无工具回答**：R07 → R10 → R08/R09。
5. **S5 稳定性和全量评测**：O02/O04/O05 → T03/T04/T06。

每项只能在对应代码、聚焦回归、真实生产复测及脱敏证据四者齐全后标为 `resolved`。


### V23续跑终止补记（2026-09-17）

在只读证明未发送的范围内续跑r2，首题TPL-A60B0CD794D49E48返回真实顶压值但仍部分完成，随后身份不可核实中断。两轮累计9次单POST，2通过、4部分、3失败；398原失败题明确未发送，逐题记录为模型依赖阻断。身份稳定7题中的2通过仅是小样本观察，不代表全量准确率。下一步需受控固定模型窗口，原9题不自动重放。
