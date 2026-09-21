# 普通问答准备阶段的现场数据授权门

状态：V48-r1本机冻结候选，原生只读合成合同及有界独立审查通过；完整回归计数以[机器证据](../../tests/qa_regression/ordinary_context_source_gate_20260917.json)为准。尚未部署，生产底座身份不符合冻结合同。
最后核对：2026-09-17。需求：REQ-QA-ORDINARY-CONTEXT-SOURCE-GATE-20260917，关联QAOPT-R01/R06/R07/R08/T05/O01。
权威：冻结V47/V48、实际prepare函数、Reliable SSH原生Python3.11.9 RAM探针、回归与gpt-5.6-luna有界只读审查。范围：8093助手准备及提示词源授权；不授权模型、恢复任务、数据库或其他服务修改。

## 缺陷与修复

此前准备阶段仅检查是否禁止现场查询，普通解释、问候及规则解释仍会提前加载最新炉况与趋势。原生修复前6个合成准备场景中，5个各触发6次传感器读取；给定数据限制场景已经为0。明确询问绑定规则时，普通来源提示词的提前返回还丢弃了服务端绑定的ABC权威上下文。这些是合成来源合同缺陷，不能计作首次数据集的生产失败。

[sensor_context_policy:L547](../../高炉前端数据/智能助手/backend/qa_task_plan.py#L547)要求TaskPlan同时明确包含`live_data`、`live_readonly_data`、`allow_prefetch=True`，才启用现场读取。显式禁止查询、禁用全部工具和纯代码请求优先拒绝；缺失或畸形授权默认拒绝。页面自带快照仍归档，但不因此进入分析证据、读取浏览器快照或生成证据snapshot_id。明确现场查询及其复合任务保留原有取数路径。

[bound_rule_context_requested:L564](../../高炉前端数据/智能助手/backend/qa_task_plan.py#L564)仅允许当前实际指令明确询问绑定规则、评分、公式或权重时，使用服务端按owner会话来源加载的上下文。引号内提及、换题、否定继承、用户给定数据、制度原文/历史/报表独占来源不会继承ABC证据。不能用聊天断言或页面数值覆盖权威批次，也不能把旧批次声称为当前现场。原`initial_context_explanation`严格JSON、动态Schema、validator、repair、缓存与owner链路不变。

“这个最近30分钟的趋势如何？”缺少明确对象，不再自动补入通用炉况。受控历史锚点仍保留；本轮未完成其生产对象绑定及最终澄清答复验收，也未将这一问题销项。已有确定性追问规划合同继续纳入回归；不能用来源门通过替代多轮答案验证。

## 冻结及验证

候选V48-r1，manifest SHA256 `ff6667172cdaac42f9335f5b28fbf382863ea2f39d9ce07a01584dc5b5abb3b8`。16文件中14个逐字节继承V47；planner只新增2个纯辅助函数，移除新增函数后全AST一致；proxy只改变prepare与来源提示词组装2个函数，归一化后剩余全AST一致。V47保留的生产3个ABC共享函数、导入和2个依赖pin全部保留。固定底座模块字节不变，无新配置、API字段或数据库迁移。

[构建器:L19](../../tools/build_qa_ordinary_context_candidate.py#L19)、[回归:L23](../../tests/test_qa_ordinary_context_source_gate.py#L23)、[证据校验器:L41](../../tools/verify_qa_full_candidate_probe.py#L41)拒绝缺少普通准备场景、sensor计数非0、归档/隔离未证明、权威标记不符和把模型未执行写成已验证。-O不能关闭候选断言守卫。

实际原生RAM加载16候选文件与60实际生产依赖，10个JSON/SSE问答合同、9个共享ABC Handler合同、6个普通prepare合同全部通过。6个普通场景修后均0传感器读取、各保留1次页面归档；只有明确绑定规则场景携带权威标记。普通组额外模拟keyword知识provider，仍执行真实来源计划和知识查询门，不访问生产知识内容。所有合同声明外部模拟边界；没有真实模型回答、真实数据库、权限会话或并发验收。

```powershell
python -B -X utf8 tools/build_qa_ordinary_context_candidate.py --revision rN
python -B -X utf8 -m pytest -q tests/test_qa_ordinary_context_source_gate.py tests/test_qa_sensor_context_source_gate.py tests/test_qa_full_candidate_probe_evidence.py
python -B -X utf8 tools/evaluate_mcp_gold_tasks.py --validate
```

rN只能选未存在编号。完整33模块复现命令、通过数及时长见机器证据；14金标schema通过。独立只读审查PASS。初轮来源测试暴露缺对象追问旧断言要求通用快照；调整为更严格的“不读取、不绑定证据、历史锚点保留”，其未完成业务行为单列，未据此宣称追问已修好。修复前原生失败及初轮记录保留私有目录。

## 生产门与原题复测

UTC2026-09-17 12:27:33的独立tags→ps→tags只读检查中，公共别名及驻留均为`9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb`，不符合冻结的`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`。生产HEAD仍cdd390…，proxy及共享依赖哈希匹配先前探测。禁止切换、fallback、同名换权重或另立基线，不执行模型POST、自动恢复或原题重放。

0生产写、真实模型调用、原题重发及销项；33项状态、首次1233有效题统计和822原fail/partial范围保持。真实8093部署还需新鲜底座/完整依赖、共享功能、EOL/recordability、密封清单及守卫验收。恢复任务/管理器和数据库源发布各自维持单独授权边界；完整规则见[固定底座策略](2026-09-17-qa-single-base-model-policy.md)。满足发布门后才单次复问统计好的原失败题，并独立审核最终答案，计算实际成功率与正确率。
