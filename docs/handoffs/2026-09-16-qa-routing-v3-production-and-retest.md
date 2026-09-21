# QA 路由 V3 生产更新与失败题复测

- 状态：生产已更新，目标失败题已逐题单次复测并完成审阅
- 最后核对：2026-09-16
- 需求：`REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916`
- 执行：`qa-routing-v3-20260916-r1`
- 适用边界：220.12 的 8093 智能助手；不包含 8094、8768、数据库或 Ollama 配置修改
- 权威来源：本记录、生产 Git 提交、脱敏复测审阅；原始回答与生产数据只保存在 Git 忽略的本机受控目录

## 1. 生产结果

8093 按受控部署流程完成五文件原子替换。守卫只暂停并恢复
`BFV4PreviewProxy8093`，没有触碰其他服务。

| 项目 | 结果 |
|---|---|
| 8093 PID | `12440 → 9768` |
| HTTP/模型状态 | 页面 200；代理、Ollama、目标模型均正常 |
| 回滚 | 未触发 |
| 生产 Git | `70b36c52c2ccddb1fa08429fc0fe6455cfff4ba9` |
| 任务引用 | `refs/heads/codex/8093/qa-routing-v3-20260916-r1` |
| 不可变生产引用 | `refs/prod-8093/20260916/qa-routing-v3-20260916-r1` |
| 保护端口 | 8094、8768、8770、5432、11434 的 PID 前后不变；8892 前后均无监听 |

安装哈希：

| 文件 | SHA-256 |
|---|---|
| `ollama_proxy_server.py` | `ABD7CC463C42A7E1C707E1B840B33C9040B33CB850AC7719B164732329AF6E67` |
| `mcp_tool_selection.py` | `F986EC49226593BEFE064763622821FC6BF738A66649B3A23BCA17EB6F00C4E4` |
| `qa_evidence_policy.py` | `0724E66578F521BA272867C06436DA836111669D38356DF9D939186CDB2E62E3` |
| `qa_task_plan.py` | `BC34986D7A8CB7FF5AF11D073809FCE623B4CD924865484D5BF98CD9255510E8` |
| `qa_evidence_claims.py` | `73B077850D710301473F0FF2D37F3E0521D15C96895232C4443630050EC51C5A` |

## 2. 发布前门禁

- 聚焦策略测试：`44 passed`。
- TaskPlan 合同：`15/15`。
- 合成问答目录：`32` 条有效。
- MCP 金标结构：`14/14`。
- 共享能力标记：全部保留。
- UTF-8、无 BOM、LF：五个候选文件通过。
- Git 可记录性：五个目标精确命中，语义变化 `491` 行，无换行迁移、路径冲突或读集漂移。
- 独立低成本语义审查：初审发现未知工具名和强制工具选择门禁缺口；修复后复审通过。

## 3. 失败题复测口径

复测对象为 [routing_failures_20260915.json](../../tests/qa_regression/routing_failures_20260915.json)
中的 16 道人工确认失败题。每题发送前先写不可覆盖的 claim；每题最多一次 POST，自动重试为 0。

| 结果 | 数量 |
|---|---:|
| POST | 16 |
| 完整 SSE `done` | 14 |
| 明确 SSE 错误 | 1 |
| 客户端同源合同拒绝 | 1 |
| 未核算请求 | 0 |

首题因验收客户端漏传 `Origin` 得到明确 `qa_origin_required`，没有重发。后续客户端按生产同源合同
修正，仅用于尚未发送的题。该首题列为客户端合同阻断，不计入路由通过。

逐题脱敏审阅见
[routing_retest_review_20260916.json](../../tests/qa_regression/routing_retest_review_20260916.json)：

| 判定 | 数量 | 说明 |
|---|---:|---|
| 通过 | 2 | 权威诊断；诊断与风量、风压、喷煤综合分析 |
| 部分通过 | 6 | 原缺陷有所修复，但仍有来源降级、原始 JSON、缺基线、截断或 SSE 字段投影问题 |
| 失败 | 7 | 历史检索生命周期、多对象展开、双窗口、日报二阶段、模型驻留竞态仍未解决 |
| 客户端合同阻断 | 1 | 缺少同源头，未评价回答质量 |

## 4. 已确认的主要遗留问题

1. **任务计划没有完全驱动执行参数。** 多对象计划仍落成单对象工具参数；CO/CO2/H2、南北探尺、
   A-D 炉喉温度仍缺对象展开。
2. **复合读取仍会提前结束。** 两时间窗比较只使用注入快照；日报流程只列目录，没有读取最新正文。
3. **历史问答已能选对工具，但结果投影失败。** 两题调用 `search_qa_messages` 后因 grounding guard
   返回原始工具 JSON；另一题仍出现 MCP 生命周期错误。
4. **模型驻留存在请求间竞态。** 健康检查通过后，准备阶段仍能返回“模型未驻留”。
5. **无工具分析仍可能截断。** 通用顶压原因回答以 `done_reason=length` 结束，最后一句不完整。
6. **SSE 最终对象过大。** 可见回答已拒绝隐藏上下文，但 final 仍携带完整共享访客 conversation
   对象；应改为最小字段投影。
7. **简单实时值降级不稳定。** 顶压题不再被禁代码守卫误杀，但工具生命周期失败后只能使用注入快照。

## 5. 下一轮修复顺序

1. 让 TaskPlan 的对象集合、时间窗和步骤成为确定性执行输入，禁止执行层再次缩成单对象。
2. 为“最新报表并摘要”和“双窗口比较”增加服务端复合只读工具，执行完整后才允许形成最终回答。
3. 对历史问答结果做字段投影与摘要；grounding fallback 禁止直接拼接工具 JSON。
4. 把模型就绪检查和实际调用放入同一有界租约；准备后失驻留时返回明确可恢复状态，不自动重发。
5. 对 `done_reason=length` 标记回答不完整，并为无工具知识解释设置合适的长度预算或分段收尾。
6. 将 SSE conversation 字段缩为 `id/title/access_mode` 等公开字段，消息列表由独立分页接口读取。

## 6. 可复现命令

本机策略回归：

```powershell
python -m pytest tests/test_qa_task_plan.py tests/test_qa_evidence_claims.py tests/test_qa_routing_candidate.py tests/test_qa_evidence_policy.py -q
python tools/evaluate_qa_task_plan_contracts.py
python tools/qa_regression.py
python tools/evaluate_mcp_gold_tasks.py --validate
```

生产失败题执行器：

```powershell
python -X utf8 tools/run_qa_failed_retest_once.py --help
```

该执行器要求显式 `--execute`、新输出目录和逐题 claim。已存在 claim 或结果时禁止自动重放。
