# V4 时间窗与报表读取修复

- 状态：本机候选已验证，未部署；最后核对：2026-09-16。
- 需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`；问题：`QAOPT-R03/R04/R05`。
- 权威状态：[33项执行台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md)。
- 范围：隔离回归工作树；生产只读探测，没有生产POST、上传、停启或自动重放。

## 生产基线

Reliable SSH 确认身份为目标 Windows administrator，8093守卫服务处于Running；生产提交仍为
`70b36c52c2ccddb1fa08429fc0fe6455cfff4ba9`。r3进度为953/953 completed。
完整问答收集不等于全部语义通过，828项待审状态保留。

| 精确基线 | SHA-256 |
|---|---|
| V3代理 | `abd7cc463c42a7e1c707e1b840b33c9040b33cb850ac7719b164732329af6e67` |
| V3 TaskPlan | `bc34986d7a8cb7ff5af11d073809fce623b4cd924865484d5bf98cd9255510e8` |
| 当前生产MCP | `35e35f540077e615d5a6213b3a81dbaf875be6d7257d4428ae2b2acb6a6bee31` |

生产MCP通过Reliable SSH read_file只读取回，落入忽略提交目录；本机文件哈希与远端Get-FileHash一致。
不以旧的本机代理或MCP整文件替换生产文件。构建器在精确基线上只应用已命名差分，基线变化即失败。

## 逐项修复

### QAOPT-R04：两个窗口及历史基线

1. 修正TaskPlan入口：原题“对比最近30分钟和前30分钟的炉顶压力。”与“全炉压差最近一小时相对历史基线偏高吗？”未含旧动作词，可能在执行器之前被拒用工具。现在识别显式时间窗比较；普通“历史基线含义”仍不调用工具。
2. [build_time_window_plan](../../高炉前端数据/智能助手/backend/qa_time_window_plan.py#L40)在MCP附加前冻结一个Asia/Shanghai时区锚点。
3. 使用两个串行query_gl02_sensors统计调用。工具及适配器为秒精度、包含结束时刻；前一窗结束为最近窗起点前1秒，GL02分钟样本不会重复计入。窗口不超过24小时，未知对象不猜测。
4. 比较均值；差值=最近均值−前窗均值，相对差=差值/绝对值(前窗均值)。前窗均值为0不计算百分比；单位冲突不计算差值。
5. 历史基线选择现有query_gl02_feature_statistics，取得查询窗统计与独立30日baseline证据；复算(均值−median_ref)/iqr_ref，不信任上游z字符串。
6. 校验对象、起止时间、样本数、来源、基线变量血缘；基线结束不晚于查询起点、覆盖率至少80%、IQR有效、采样未截断才能比较。80%是证据质量门，不是炉况报警阈值。
7. 每一步结果立即保留；缺数、错误输出、工具不可用、策略拒绝或超时明确降级，不调用模型补写实时数值或重发请求。
8. 时间窗工作流优先于通用DAG与单窗快路；单窗prefetch不再提前消费这类问题。复合来源问题保留原执行链，本模块没有宣称解决所有复合任务。

### QAOPT-R05：最近日报摘要

1. [execute_report_plan](../../高炉前端数据/智能助手/backend/qa_report_workflow.py#L73)明确执行list→select→read→摘要摘录。
2. 复用list_recent_reports按文件modified_at降序的合同，限定报表类型；仅读取首项受控相对路径，不接受盘符、UNC、绝对路径、../或非法扩展名。
3. 校验实际正文返回的来源路径一致。目录查询成功不等于正文已读取；依赖失败不猜测下一份报表，不重发。
4. 摘录报表自身摘要/总结/概览/要点/结论章节；缺章节时显示明确标注的正文摘录，不伪装成全文总结。正文指令不执行，代码块按禁代码策略省略。
5. 修正read_report_excerpt的中文截断误报：先保存total_chars，截断后将返回字符数与总字符数比较，避免与文件字节数比较。增加total_chars是向后兼容字段。
6. 真正截断、摘录缩短或禁代码省略均保持非完整状态；报表历史数据不被表述为当前实时炉况。

## 本机验证

```text
python tools/build_qa_routing_v4_candidate.py --v3-candidate .codex_runtime/qa-routing-v3/candidate --mcp-baseline .codex_runtime/qa-routing-v4/production-baseline/bf_data_mcp_server.py --output .codex_runtime/qa-routing-v4/candidate
python -m pytest tests/test_qa_task_plan.py tests/test_qa_entity_resolution.py tests/test_qa_time_window_plan.py tests/test_qa_report_workflow.py tests/test_qa_report_excerpt_contract.py tests/test_qa_evidence_claims.py tests/test_qa_routing_candidate.py tests/test_qa_routing_v4_candidate.py tests/test_qa_evidence_policy.py -q -p no:cacheprovider --basetemp .codex_runtime/qa-routing-v4/pytest-20260916-r2
python tools/evaluate_qa_task_plan_contracts.py
python tools/evaluate_mcp_gold_tasks.py --validate
git diff --check
```

- 相关回归98 passed；最后public_trace接缝修改后4项候选测试再次通过。
- TaskPlan合同15/15；MCP金标准结构14/14。MCP结构校验不是实际调用成功率。
- 覆盖：独立分钟样本边界验证、差值与标准化偏离复算、时间/变量错配、部分缺失、未来及重叠基线、低覆盖、非有限数、单位冲突、串行超时、路径越界、中文全文及真实截断。
- 执行代理实际AST接缝，不需要导入无关生产依赖。中文报表测试执行本机及精确生产差分候选中的真实读取函数。
- 默认Windows临时目录权限导致2项夹具初始化失败；改用已核对的隔离工作树basetemp后通过，没有放宽业务断言。
- 本机Python3.13验证；生产Python3.11真实执行、模型驻留竞争、并发和生产答案语义仍未验证。

## 下一门禁

先继续`QAOPT-O01`模型驻留竞争与`R02/E01`历史呈现/生命周期保全，再冻结S1候选。
生产发布须扩展精确allowlist纳入两个工作流模块、实体模块、TaskPlan及MCP差分；重新执行守卫部署skill、本机候选EOL门禁和受保护PID验收。
各代表题建立新的明确执行ID，只发送一次；历史已发送/不确定的批次不得自动重放。
生产验证前台账只记录local_candidate_verified，不能标成production_verified。
