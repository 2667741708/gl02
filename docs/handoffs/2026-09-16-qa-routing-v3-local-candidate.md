# QA 路由 V3 本机候选交接

- 状态：`historical_predeployment_snapshot`；已由
  [生产更新与复测](./2026-09-16-qa-routing-v3-production-and-retest.md)取代
- 最后核对：2026-09-16
- 需求：`REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916`
- 适用边界：普通智能助手问答、知识检索、只读 MCP 路由、证据降级和禁代码输出。
- 权威基线：220.12 当前 V2 生产字节的本机哈希绑定副本；本轮没有修改 220.12、8093 服务、数据库或模型配置。

## 1. 已形成的候选

候选由 [build_qa_routing_candidate.py](../../tools/build_qa_routing_candidate.py) 从两个精确基线生成：

| 文件 | 基线 SHA-256 |
|---|---|
| `ollama_proxy_server.py` | `c94dc585cd0d319ae9ef2235620acd7802d880f569510dac43c2e571a0e6298c` |
| `mcp_tool_selection.py` | `50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033` |

本轮结束前通过 Reliable SSH 只读复核：R3 `progress.json` 为 `state=completed`、
`completed=953/953`、`requests=953`，原 PID `18224` 已退出。220.12 五个受控文件仍为 V2：

| 生产文件 | SHA-256 |
|---|---|
| `ollama_proxy_server.py` | `c94dc585cd0d319ae9ef2235620acd7802d880f569510dac43c2e571a0e6298c` |
| `qa_evidence_policy.py` | `442ea9df0f2ab41738b8b9613491dcc4838890800974f96c3d8ccf27a2369d4d` |
| `mcp_tool_selection.py` | `50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033` |
| `mcp_conversation_context.py` | `fbef24db2d324ac3417ad1f3a59e1cdcfc8f5bd7d79f959c1f60b3b51b33db15` |
| `bf_knowledge_rag.py` | `3f9fc5347fd0ad8927be66d6c19d1024d82b105bab755991257d4a7551286da4` |

构建器发现基线漂移、替换点数量异常、Python 语法错误、BOM 或 CRLF 时立即失败。生成目录是忽略提交的
`.codex_runtime/qa-routing-v3/candidate`；Git 只保存可审查的构建器、纯模块、合同和测试。

## 2. 本轮修复

### 统一 TaskPlan

[qa_task_plan.py](../../高炉前端数据/智能助手/backend/qa_task_plan.py) 在任何预取之前分离外层指令和
引文，确定 `document_knowledge / conversation_history / period_report / live_data /
user_supplied_data / general_knowledge / ordinary_qa`。同一计划控制：

1. 是否允许现场数据预取；
2. 是否检索知识库；
3. 是否进入 MCP；
4. MCP 目录中可见的证据域。

因此制度标题或引文中的“当前、风量、曲线、操作”等词不再触发现场工具；历史问答只能看到聊天历史域，
制度问答看不到聊天和现场工具，实时问题看不到聊天检索工具。明确的“文档 + 当前数据”复合请求仍保留
知识检索与只读实时数据两个来源。

### 回答与证据边界

- [qa_evidence_policy.py](../../高炉前端数据/智能助手/backend/qa_evidence_policy.py) 恢复统一助手目标：
  普通知识、文档、数学、用户数据和已核验只读数据均可回答；没有必要时不调用工具。继续禁止生成或执行
  代码、SQL、脚本和命令。
- JSON、text 和普通 Markdown 围栏不再因存在三个反引号而整段拒绝。可执行语言围栏和实际可执行语法
  仍被拦截；混合问题保留允许的分析，只拒绝代码子任务。
- [qa_evidence_claims.py](../../高炉前端数据/智能助手/backend/qa_evidence_claims.py) 按对象和统计字段核对
  数值，并按答案显示精度允许合理舍入。`42.500123 → 42.5` 可通过，把同一数值从顶压换成顶温会拒绝。
- 普通、规划器和强制工具路径把工具结果写入请求级 EvidenceLedger。后续请求生命周期异常时，如已有成功
  事实，则返回确定性事实和明确缺项，不再清空为“所有数据不可用”。

## 3. 回归集合

[task_plan_contracts_20260916.json](../../tests/qa_regression/task_plan_contracts_20260916.json) 新增 15 条稳定
路由合同，其中 10 条直接引用已公开的真实模板 ID，4 条为合成反例。验证器
[evaluate_qa_task_plan_contracts.py](../../tools/evaluate_qa_task_plan_contracts.py) 只读取公开模板与合成题，
不读取或输出线上原始答案、会话身份和生产数值。

本轮验证结果：

| 检查 | 结果 |
|---|---|
| 路由、证据、禁代码聚焦测试 | `43 passed` |
| TaskPlan 稳定合同 | `15/15` |
| 原 32 条合成问答目录 | `corpus_valid` |
| MCP 金标结构 | `14/14` |
| 候选 Python AST/编码 | 通过 |

## 4. 尚未完成

1. EvidenceLedger 尚未覆盖复合 DAG 在成功后又发生清理异常的路径。
2. 字段校验已覆盖对象、统计字段和值；单位、时间窗、来源和 owner 仍需 E02 类型化证据。
3. 原文章节的完整正文/表格展开、报表正文读取、多对象和多时间窗仍属于后续阶段。
4. 这只是本机候选。未在隔离端口运行真实模型，也未执行 8093 受控部署和生产复测。

## 5. 可复现命令

```powershell
python tools/build_qa_routing_candidate.py --proxy-baseline <V2代理基线> --selection-baseline <V2工具选择基线> --output .codex_runtime/qa-routing-v3/candidate
python -m pytest tests/test_qa_task_plan.py tests/test_qa_evidence_claims.py tests/test_qa_routing_candidate.py tests/test_qa_evidence_policy.py -q
python tools/evaluate_qa_task_plan_contracts.py
python tools/qa_regression.py
python tools/evaluate_mcp_gold_tasks.py --validate
```

成功信号分别为：构建报告 `syntax=passed` 且 `production_changed=false`、`43 passed`、TaskPlan
`ok=true checked=15`、`corpus_valid case_count=32`、MCP 金标 `ok=true case_count=14`。
