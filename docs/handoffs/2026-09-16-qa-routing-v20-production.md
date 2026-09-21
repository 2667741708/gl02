# V20 指代趋势追问规划修复

- 状态：已部署且五题真实生产复测通过；33项整体仍执行中。
- 最后核对：2026-09-16。需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`；问题：QAOPT-R10/E01/E05。
- 权威来源：冻结候选、受控8093部署与版本记录、独立逐题答案审阅、已知guest测试回合的生产PostgreSQL只读来源核查。
- 生产提交：`4304243a1e53cee2ed35c8f541b38be2d359f55e`；父版本V19 `501853215757fae629af31c74c8a4048cce301ec`。

## 缺陷与修复

[V19真实失败](2026-09-16-qa-routing-v18-v19-production.md)中“这个最近30分钟趋势”已正确继承DP_total与窗口，但 `qa_mcp_planning_question` 的指代词表缺少“这个”，进入模型规划及绘图后生命周期失败，最终仅给时间范围。

V20以V18实际已接受代理字节为基线，只修改指代词表一行，增加“它们/这个/那个/这些/刚才/上面”。存在明确新对象时仍以当前问题为准；无指代的新题移除旧私有路由后缀。服务端owner来源绑定、窗口质量、禁代码和来源隔离合同保留。

符号行号：TODO-LINES。构建入口`tools/build_qa_routing_v20_candidate.py`，实际AST规划与sensor接缝测试`tests/test_qa_followup_planning.py`。

## 验证与范围

- 100项不同针对性测试通过：联合99项加新增sensor接缝1项；独立应用/最终发布审查PASS。12项新测试覆盖实际规划器、30分钟统计执行及明确新对象/无指代反例。
- 发布后为GitHub回归集导出无生产数据的规划器代码接缝夹具，使12项规划测试不依赖本机忽略候选目录；夹具、真实适配器及续跑门联合38项通过。该测试资产变更不是再次部署；历史发布密封字节仍按发布时冻结记录。
- 生产新轮5POST、5确定答案，5独立语义通过，0自动POST重发。两次模型发送前阻断后仅续跑未发送题。
- 最新总压差、30分钟指代趋势、指代最新值、明确切换顶压、无工具用户均值计算均通过。趋势实际执行 `query_gl02_sensors/statistics`，不是只返回时间范围。
- 趋势模型解释仍被grounding guard拒绝，最终保留已核验确定性统计与趋势；不能称模型推断通过。
- 真实数据库只读来源proof5/5通过，确认对象/窗口来源与清除旧状态；0写、0模型、0问答POST。仅覆盖已知guest回合，多角色并发另测。
- [逐题脱敏报告](../../tests/qa_regression/routing_v20_production_review_20260916.json)、[来源proof](../../tests/qa_regression/routing_v20_provenance_review_20260916.json)。V18及V19失败保留，不覆盖旧结果。

复现：`python -X utf8 -m pytest tests/test_qa_followup_planning.py tests/test_qa_context_provenance.py tests/test_qa_context_provenance_seams.py tests/test_qa_context_boundaries.py tests/test_qa_history_completion.py tests/test_qa_history_compound.py tests/test_qa_history_compound_seams.py tests/test_qa_retest_persistence.py -q --basetemp .codex_runtime/pytest-v20-new-run`。线上复测需新的受控轮次，不能重跑既有输出目录。

## 部署验收

- 唯一替换目标`ollama_proxy_server.py`；SHA256 `38c99c5fbde8e967549f0435a608b92db5648520a3e37622b686a391c004deb2`。
- 8093 PID11144→17072；HTTP200，模型健康、守卫恢复、未回滚；8094/8768/8770/5432/11434 PID不变。
- 26项依赖哈希、Python3.11语法、scoped Git clean通过；2行语义变化，无换行迁移。
- 激活35880.647ms，版本记录4720.464ms，CAS1次。
- 备份：`F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/backups/qa-routing-v20-20260916-r1-20260916-220825`。

## 仍开放

模型驻留波动、模型解释grounding稳定性、浏览器有界历史、operator/admin并发、知识语义/30项oracle冲突按[33项执行台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md)继续。5/5定向通过不代表所有综合问题通过。
