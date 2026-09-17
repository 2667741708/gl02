# 智能助手：先看证据、再决定工具的回归集

- 需求：REQ-QA-EVIDENCE-FIRST-REGRESSION-20260915。
- 状态：核心32条合成用例保留；全量问题收集已冻结，1条发送状态不确定继续隔离；生产V26已部署。固定同一底座的管理器/V27及继承该约束的V28统计修复为本机候选，尚未部署，原822失败/部分题复测尚未发送。
- 最后核对：2026-09-17。
- 最新：[全量问题统计](issue_statistics_20260916.md)、[33项执行台账](optimization_execution_ledger_20260916.md)、
  [33项整改清单](optimization_checklist_20260916.md)、
  [TaskPlan路由合同](task_plan_contracts_20260916.json)和
  [V26生产验收](routing_v26_production_20260917.json)、
  [固定同一底座合同](../../docs/handoffs/2026-09-17-qa-single-base-model-policy.md)和
  [V28统计证据修复](../../docs/handoffs/2026-09-17-qa-v28-statistics-evidence.md)。
- 机器权威：[cases.v1.json](cases.v1.json)、[fixtures.v1.json](fixtures.v1.json)。
- 适用范围：普通问答的路由、已有证据利用、最终回答及恢复；不替代生产控制、ABC33 严格首问或线上数据验收。
- 数据政策：核心 32 题使用合成数据；导入模板保留来源索引并对历史炉号、地址及凭据形态脱敏。禁止提交线上原始会话、真实炉号、身份、内部地址、Cookie、令牌、密码、连接串或生产环境文件。脱敏后的展示文本不是本次实际执行文本，使用 case_id 与受控原文证据关联。

## 先判断什么

**综合分析不等于必须调用工具。** 工具只用于取得或计算完成问题所缺的信息。

| 情况 | 工具策略 | 回答要求 |
|---|---|---|
| 科普、产品说明 | forbidden | 直接回答问题，不转移为炉况汇报 |
| 要求代码、伪代码、SQL、脚本或命令示例 | forbidden | 当前暂时关闭，说明限制并提供中文步骤；QA-004 已升为版本 2 |
| 用户给出足够数据 | forbidden 或仅允许 calculate | 可以分析，声明基于用户输入；不能冒充实时核验 |
| 同对象、同权限、时间适用的证据已足够 | forbidden | 直接利用数据综合判断，无需重复读取 |
| 只有单点却问趋势、旧快照却问当前 | required | 补充必要查询；缺信息而非“分析”这个词触发工具 |
| 简单计算或已可独立复算 | optional，仅 calculate | 不要求为了算术调用生产数据库 |
| 已有部分成功结果，预算用完或其它工具失败 | forbidden（本阶段不再发起调用） | 保留成功事实，说明不能确认的部分 |
| 歧义、证据冲突、全部失败或权限不足 | 按用例 | 澄清、解释冲突、有限降级或拒绝，不能编造 |

旧金标 [PT/智能体工具能力金标任务清单.v1.json](../../PT/智能体工具能力金标任务清单.v1.json) 继续负责具体 MCP 工具名、参数、依赖与调用合同；本集合补充整轮问答和免工具场景，使用能力类别而非某个工具名做长期约束。不要用新集合替代旧金标。

## 本地检查

从仓库根目录运行，Python 3.10+，仅标准库依赖：

```powershell
python -X utf8 tools/qa_regression.py
python -X utf8 tools/qa_regression.py --list
python -X utf8 tools/evaluate_qa_task_plan_contracts.py
python -X utf8 -m unittest discover -s tests -p test_qa_regression.py -v
```

第一条输出 corpus_valid，表示用例引用、规则及合成算术夹具合法，不是模型回答通过。`--list` 从 JSON 生成列表并带 SHA-256，避免维护第二套手工金标。
TaskPlan 验证器检查公开模板和合成反例的来源隔离、知识检索、预取及工具域合同；同样不调用模型或生产接口。

```powershell
python -X utf8 tools/qa_regression.py --results tests/qa_regression/run.example.json
```

此命令**预期退出 1**：例子只包含一个人工构造结果，报告一项 contract_passed_pending_review、其余 not_run；不得将它当作模型评测。

## 用例格式

每条用例含稳定 case_id、version、category、provenance、prompt、as_of、fixture_ids、history、tool_fixtures、expected、rubric。

- `fixture_ids`：该场景开始时已有上下文；传给模型前排除 other_owner 证据。错误夹具只能作为错误状态，不能当作实测数值。
- `tool_fixtures`：模拟工具被实际请求后才提供的结果，不得提前塞入模型上下文。capability 是 sensor_latest、sensor_history、heat_quality 或 calculate。
- `expected`：仅供评测器，不能传给被测模型。包含工具允许/要求、终态、必需/禁止证据、调用上限和时间上限。
- `rubric`：只供独立审阅，检查是否回答问题、推断是否越界、来源是否准确，不要求逐字匹配参考答案。
- fixture 的 source_kind、scope、quality、observed_at/window 决定适用性；“trusted”指测试中约定的来源，不是对合成数据真实性的声明。
- 部分失败、预算结束、取消、EOF 用例是相应阶段的恢复输入。已有工具结果属于前序证据，tool_calls 只记录从该用例起点之后新增的调用，不能与完整请求的累计调用数混用。

## 接入真实候选程序

合成夹具仍需在与生产一致的隔离候选中接入。另提供 [线上用例](live_cases.v1.json) 和单次请求收集器 `tools/run_qa_live_case.py`、后台启动器 `tools/start_qa_live_case.py`；线上执行必须显式开启，每题独立私有会话、恰好一次 POST，禁止自动重放。收集器不把 expected 传给模型，不自行判定答案通过，原始结果只写入受控的忽略目录。

夹具接入步骤：

1. 将 prompt、history、as_of 和授权范围内的初始夹具传入实际问答入口；不提供 expected、rubric 或未请求工具的结果。
2. 把工具调用替换为确定性的夹具适配器。按实际调用能力返回对应 tool_fixture；记录工具是否真正发起、成功/失败、时间、重放次数和最终结果。
3. 由可信收集器从实际轨迹产生结果文件；不得让被测模型自行填写“是否使用工具”“是否超时”“通过与否”。数值 claims 必须对应实际最终答案中的断言，不能只照抄金标。
4. 每次保存 model、model_version、program_commit、prompt_version、tool_schema_version 及两个目录文件的 SHA-256，保证新旧候选使用同一题目与数据。
5. 输入结果格式见 [run.example.json](run.example.json)。实际模型配合夹具运行使用 execution_kind=model_with_fixtures；示例使用 synthetic_example。
6. 独立人工或独立评审器逐项核对 rubric，并对整段答案的事实、数值断言提取完整性、来源、时间、权限和推断边界签署 answer_fidelity_passed。不能用被测模型的自我评价代替。

审阅文件格式：

```json
{
  "run_id": "与结果一致",
  "items": [{
    "case_id": "QA-006",
    "answer_sha256": "实际最终答案UTF-8字节的SHA-256",
    "reviewer": "独立评审标识",
    "rubric_passed": [true, true],
    "answer_fidelity_passed": true
  }]
}
```

```powershell
python -X utf8 tools/qa_regression.py --results path/to/run.json --reviews path/to/reviews.json
```

退出码：0=目录验证成功，或指定真实模型夹具运行的全部用例通过合同及审阅；1=存在失败/未运行/待审阅，或仅为合成示例；2=输入合同无效。实际线上生产验收不由此评分器执行，production_verified 始终为 false。

## 评分边界

自动检查工具策略、实际结果夹具引用、终态、重放、时限、数值和单位、证据权限及缺项。数值容差由每条事实的 decimals 确定（半个末位单位）；新增单位换算应提供独立复算夹具，而不是放宽误差掩盖错误。

本评测器不对全文做粗糙数字正则校验：编号、公式和示例数字不能都当作生产事实。它也不能自动证明自然语言推断正确；没有独立审阅只能标记 contract_passed_pending_review。不可把“引用正确但正文错误”算作通过。

8 条线上基线的观察结论见 [基线记录](live_baseline_20260915.md)，复测及优化方案见 [第一版复测记录](live_after_v1_20260915.md)。这是小样本功能排障，不代表整体用户成功率；pass^5、并发稳定性与全部 32 条夹具的真实模型运行仍未测。所有越权、伪造实测、错误自动重放均应阻断，不能被平均分抵消。

## 如何持续扩展

全来源核对入口：[问题统计](issue_statistics_20260916.md)、[1418行逐题CSV](question_ledger_20260916.csv)、[33项逐条执行台账](optimization_execution_ledger_20260916.md)、[33项整改与验收清单](optimization_checklist_20260916.md)。本轮异常标签可重叠，未审阅答案不能计通过；实施状态与收集状态分别跟踪。

当前实施计划见[路由策略与智能助手完善计划](assistant_improvement_plan_20260916.md)。2026-09-16核对的知识来源为833行，其中818条独立ready题、15条重复来源；收集完成与答案通过分别验收，先冻结问题收集和审阅，再修改路由。

全量模板入口：[来源与问题目录](templates.v1.json)、[合同检查](template_contracts_20260915.json)、[第二版结果与范围](live_after_v2_20260915.md)。导入工具为 tools/import_qa_prompt_sources.py，执行计划生成器为 tools/prepare_qa_template_batch.py，串行执行器为 tools/run_qa_template_batch.py；系统模板不作为用户消息发送，参考答案不能进入执行载荷。

长批次使用 tools/start_qa_batch_independent.ps1 在已授权服务器上启动无窗口独立进程。恢复前先核实原进程、claim、结果及必要的会话持久化，再用 tools/prepare_qa_batch_continuation.py 排除所有已 claim 题；未知结果不能自动重发，多轮题缺少原会话时拒绝续接。progress.json 的 completed 表示收集完成，answer_contract=pending_review 表示尚未通过内容审阅。

1. 从新问题提炼失败模式，先脱敏/改写，再分配下一个 QA 编号；不要复用或重排旧编号。
2. 添加最小合成夹具，明确对象、时间、来源、质量、权限和故障阶段；计算结果必须可独立复算。
3. 优先成对补题：同一句话配“足够/不足”证据，或同一证据配“历史/当前”问题，验证路由依据而不是关键词。
4. 写清允许的答案终态、工具政策、证据要求和独立审阅标准；用失败实现检验新题是否真正能抓住问题。
5. 修改旧题语义时增加 case.version；整体破坏性格式改变才升级 schema。保留旧运行记录及其目录哈希，不能删失败题或放宽规则制造全绿。
6. 修改 cases/fixtures 后，旧 run.example.json 的哈希会失效；只更新这个明确标为 synthetic_example 的格式例子，不能重写历史真实运行记录。
7. 执行上述检查，提交独立变更；真实结果若含生产或个人信息，保留在受控位置，公开仓库只提交合成用例与经过审查的汇总。

扩展顺序：同义口语 → 连续追问与范围切换 → 多源组合 → 部分缺失与冲突 → 超时取消 → 新业务需求。与实际故障关联只保留问题类型及需求编号，不上传原始日志。

## 2026-09-16 V4新增故障回归

- [V4修复交接](../../docs/handoffs/2026-09-16-qa-routing-v4-temporal-report-local.md)：R04时间窗/独立基线，R05报表依赖链/中文截断。
- 合成测试位于tests/test_qa_time_window_plan.py、test_qa_report_workflow.py、test_qa_report_excerpt_contract.py；包含独立复算、部分失败和越界输入，不含生产数据。
- [33项执行台账](optimization_execution_ledger_20260916.md)保留本机候选与生产通过的区别；候选源文件、原始线上源码及真实工具结果不随回归集上传。
