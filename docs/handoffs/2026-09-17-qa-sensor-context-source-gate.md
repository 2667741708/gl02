# 明确源约束前移到炉况准备执行层

状态：V46-r2本机及原生合成合同通过，未部署；生产底座和共享代理合并门仍阻断。最后核对：2026-09-17。
需求：REQ-QA-SENSOR-CONTEXT-SOURCE-GATE-20260917；关联QAOPT-R01/R07/R08/T03/T05/O01。
权威：[脱敏证据](../../tests/qa_regression/sensor_context_source_gate_20260917.json)、[33项机器账本](../../tests/qa_regression/optimization_execution_ledger_20260916.json)。

## 已证明的问题和最小修复

完整Handler执行发现：10项合成功能合同全通过，但8项明确只用给定数据、禁止实时查询或纯代码题各触发5次炉况读取（latest/trend provider与3次QA快照查询）。这是完整prepare在TaskPlan之前组装现场资料造成的执行层缺口，不能用0 MCP工具或答案非空证明零读取。没有读取生产测量值，provider/数据库均为合成边界。

[候选构建器](../../tools/build_qa_sensor_context_candidate.py)只修改冻结proxy的prepare_qa_chat：在炉况组装前形成source_task_plan，明确no_live_lookup或code_request_only时禁止PG latest/trend、snapshot_by_id、latest/recent快照兜底；生成source_plan_without_live_context及sensor_context_policy版本状态，不提供快照事实。

页面随请求携带的current_snapshot仍通过原insert_snapshot归档，保持共享访客日志合同；受限问题不再从库中读取它，不绑定本轮消息snapshot_id、Prompt、MCP或完成证据。已有ABC权威context保持独立，不由页面归档覆盖。归档失败保持明确请求失败，不能因此启用实时兜底。

r1曾直接阻止页面快照插入；合同复核发现共享访客归档要求，已冻结r2纠正，并保留r1证据。纯代码子任务仍拒绝；合法实时查询、用户数据加独立实时查询、代码加合法查询及非受限多轮/ABC路径保留。普通及非受限知识问题的旧快照路径仍需下一步审核，不能把本轮范围扩大为全部无工具问题已完善。

## 逐项验证

- 31模块760 passed（105.99秒）；24项新增源门测试、9项新增证据拒绝反例，14金标schema通过。
- 生产独立Python3.11.9进程RAM加载16冻结模块、59真实项目依赖；10完整Handler合成合同通过，sensor_context_read_count全部0。
- 8项受限prepare的页面归档模拟各1次；跨owner与占用拒绝为0次。归档隔离、消息snapshot_id空、Prompt未注入归档标记均检查；不把生产0写解释为0 QA持久化。
- gpt-5.6-luna low有界静态复审PASS；其他15模块逐字节继承V45-r2，只有prepare_qa_chat函数AST改变，固定名称及e4权重摘要保持。
- owner、消息、Prompt/缓存、原文读取、并发控制和模型解析合同不因本轮放宽；未真实测试模型答复、数据库事务或双角色并发。

完整复现命令与31模块清单见机器证据；聚焦入口：

```powershell
python -B -X utf8 tools/build_qa_sensor_context_candidate.py --revision rN
python -B -X utf8 -m pytest -q tests/test_qa_sensor_context_source_gate.py tests/test_qa_full_candidate_probe.py tests/test_qa_full_candidate_probe_evidence.py --tb=short --basetemp=.codex_runtime/qa-source-gate-new-run
```

rN须使用未存在的受控编号r1/r2/r3/r4；候选和私有输出O_EXCL拒绝覆写，不是部署或模型操作入口。原生脚本沿用完整探针生成器及Reliable SSH Python stdin，remote不落候选源码；证据校验器额外要求禁用源读取计数为整数0、页面归档次数正确并隔离。

## 新鲜生产共享变更及发布门

最新只读生产HEAD cdd390cc386ce486d8a4685ebe060b8eeda7c38a，proxy哈希d84cfe…，MCP哈希42d81a…。相比此前df9dde…，新增ABC33展示修复涉及with_public_detail_semantics、Handler.handle_furnace_rule_detail、Handler.handle_public_furnace_rule_breakdown和furnace_display_policy导入，另有abc_score_explanation及静态资源变更。它与本轮prepare修改不同，但必须合并保留并复核新依赖；V46-r2不是当前生产可直接覆盖的密封候选。此前“共享变更仅静态/后端哈希不变”已是历史快照。

tags→ps→tags仍见latest名称/驻留均为9111be…，与固定e4ad74…不一致。保持生产现状，不自动换模型、重置基线、恢复旧多模型切换或重问822原失败/partial题。本轮0真实模型调用、原题POST、生产写、服务/任务变更、销项；33项状态及历史准确率不变。

下一步先本机合并保留上述生产共享变更并扩展原生read_set，重新通过完整加载、共享合同、EOL/recordability及范围验收；固定底座、独立授权的任务/驻留/源库门也必须满足后才能部署8093。部署后逐题单次复问、独立审查最终答案，不能用本轮760合同或10合成答复计算生产准确率。
