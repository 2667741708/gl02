# V18–V19 多轮来源绑定及生产适配器兼容修复

- 状态：V19 已部署，六题真实复测完成；五通过、一失败，整体33项仍执行中。
- 最后核对：2026-09-16。需求：`REQ-QA-FULL-ISSUE-INVENTORY-20260916`；问题：QAOPT-R10/E01/E05/O01/T05。
- 权威来源：密封候选、受控部署、生产版本记录、独立答案审阅、已知测试回合的 PostgreSQL 只读核查。仅适用于8093。
- V18生产提交：`32388025eeb33b74000b865b743c0ec1c13fb899`；V19：`501853215757fae629af31c74c8a4048cce301ec`。

## 修复与真实缺陷

1. 从同 owner、同会话的已持久化 user 回合加载工具上下文，拒绝来源越界；不从迟到的 assistant 回合继承状态。
2. 对象与时间窗分别记录实际来源消息ID，本轮状态在服务端 user 消息持久化后绑定；请求体不能提供身份或来源ID。换题清对象，最新追问清旧窗口，旧工具读数不复用。
3. V18唯一已发送题在真实生产适配器上失败：`CursorAdapter`没有`rowcount`。独立合同测试不能替代真实适配器测试。V19只替换上下文模块，使用 `UPDATE … RETURNING id` + `fetchall()` 核验准确目标ID，保留全部身份/会话/user角色门。
4. 新增使用真实 `PgCompatConnection/CursorAdapter` 的回归，覆盖成功绑定与越权拒绝。
5. 续跑器核对原计划哈希、claim数、问题哈希与既有claim，禁止重放任何已发送或不确定请求；仅复用成功回合的服务端会话引用。

符号行号：TODO-LINES。工具：`build_qa_routing_v18_candidate.py`、`audit_qa_context_provenance_readonly.py`、`build_qa_context_provenance_fixture.py`。所有原始答案/私有消息ID夹具保留在忽略目录。

## V18回滚与重试授权

- 初次激活因批准模型未驻留触发受控回滚；代码恢复为V17字节，守卫恢复、受保护PID不变，未记录为成功版本。
- 遵守部署skill“Never retry the same deployment automatically after rollback.”，只读检查后请求明确授权；用户回复“授权重新部署 V18 并复测”。随后执行一次重部署并成功记录。
- V18复测1 POST、1确定失败；剩余5题在前回合会话依赖门前停止，未创建claim、未发送，不计语义失败。
- [V18冻结失败报告](../../tests/qa_regression/routing_v18_production_review_20260916.json)。

## V19测试与来源验收

- 发布前107项不同针对性测试通过；应用及最终发布均经独立审查。
- 真实六题分三个续跑批次完成，6 POST、6确定结果、0自动POST重发。两次模型未驻留均在发送前暂停；恢复后仅发送未提交题。
- SEED趋势、LATEST最新值、SWITCH新对象、USER用户均值分析、HISTORY-LIVE历史+当前通过。
- WINDOW“这个最近30分钟趋势”仍 `answer_contract_failed`：只有时间范围，没有可用趋势答案，路由为生命周期失败。规划器指代词表缺少“这个”，待V20修复；不因SSE done或来源proof通过而升级。
- SEED模型解释被grounding guard拒绝，最终已核验的确定性趋势事实满足该题；不称模型趋势判断通过。
- 真实数据库只读来源核查6/6通过，逐项确认对象、窗口、源消息、同owner user来源、旧证据不复用；0数据库写、0模型、0问答POST。
- proof仅覆盖已知guest测试回合，不推断operator/admin并发通过。
- [V19独立答案报告](../../tests/qa_regression/routing_v19_production_review_20260916.json)、[脱敏来源检查](../../tests/qa_regression/routing_v19_provenance_review_20260916.json)。

复现：`python -X utf8 -m pytest tests/test_qa_context_provenance.py tests/test_qa_context_provenance_seams.py tests/test_qa_retest_persistence.py -q --basetemp .codex_runtime/pytest-provenance-new-run`。线上POST必须使用新的受控测试轮次，不能重跑既有输出。

## 8093部署验收

- V19只替换`mcp_conversation_context.py`；安装SHA256 `98fb56b92135df039e22dd0eac812fda24071a07f188e997f7e5a1094158fbd5`。
- V19 PID18076→11144；HTTP200、批准模型就绪、守卫恢复、未回滚；8094/8768/8770/5432/11434 PID全部不变。
- V19激活34717.031ms、记录3883.966ms，CAS1次；6行语义变化、26依赖哈希通过，无EOL迁移。
- 备份：`F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/backups/qa-routing-v19-20260916-r1-20260916-215315`。
- V18代理安装SHA256 `c8b2c1afebf921715d5b588540a0b727c69ce983ae0870dee2c3d5551a9711f0`保留于V19；模型配置、生产建议和其他服务边界未变。

## 未关闭事项

30分钟指代趋势答案、模型驻留波动、浏览器有界历史、多角色并发、知识语义元数据与30项oracle冲突继续按[33项执行台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md)推进。不得把本轮5/6或来源6/6称为全部问题解决。
