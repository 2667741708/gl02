# 8093 跨 MCP 组合计算验收

> 状态：已完成  
> 最后核对：2026-08-13  
> 事项编号：`Q-8093-CROSS-MCP-COMPUTATION-20260813`

## 验收问题

向 `http://10.30.220.12:8093/api/qa/chat` 的共享访客会话提交一次真实 SSE 问答：

> 请查询上一炉铁水Si平均值和当前顶压，并分析两者的数值比值（顶压÷Si），明确列出两个来源、原始数值和计算过程。

前两次 HTTP 预检分别被 `qa_origin_required` 和 `conversation_id_required` 拒绝，均发生在模型与
MCP 调用前。适配同源 `Origin` 和 bootstrap 返回的共享 `conversation_id` 后，只提交了一次
有效模型问答；问答消息已持久化为 `id=1028/1029`。

## 实际结果

| 数据 | MCP 服务 | 工具 | 原始值 | 数据时间 | 耗时 |
|---|---|---|---:|---|---:|
| 上一炉铁水 Si 平均值 | `imes-readonly` | `imes__get_current_previous_heat_si_summary` | `0.3 %` | `2026-08-13T22:13:49` | `2109 ms` |
| 当前顶压 | `gl02-data` | `query_gl02_sensors` | `255.29724799262152` | `2026-08-13T22:12:00` | `109 ms` |

独立复算：

```text
P_top / si_avg
= 255.29724799262152 / 0.3
= 850.9908266420717
```

模型答案明确列出两个来源、两个原始值、公式和结果 `850.9908266420717`，与独立复算一致。

## 能力边界

- 这次验证的是跨服务组合：主机先构建 `CrossSourcePlan`，把没有依赖关系的 IMES 与 GL02
  步骤放在同一 DAG 层并发执行；证据完整后，再进行一次 `tools=None` 的低温模型分析。
- 因此它证明“当前智能助手系统能组合两个 MCP 服务的结果并让模型完成后续计算与解释”。
  跨服务选路和工具参数主要由确定性编排器约束，不应描述成模型完全自由地发现并调用所有服务。
- 此前的同服务测试已经证明模型可以执行“查目录 → 依据返回 ID 查询点位”的两轮工具规划。
  两项合起来覆盖了多轮工具使用和跨 MCP 组合回答，但尚不代表任意长度、任意依赖图都可靠。
- 如果任一必需来源缺失，跨源分析门禁禁止模型伪造比值；工具全部失败时则进入一次无工具降级回答，
  并必须声明实时数据未核实。

## 实现与验证

- 跨源计划入口：`高炉前端数据/智能助手/backend/ollama_proxy_server.py` 的
  `build_cross_source_plans()` 与 `cross_source_dag` 分支。
- 并发执行：`高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py` 的
  `execute_cross_source_plan()`，同层使用 `asyncio.gather`，同一 server 仍串行。
- 可复用探针：`tools/probe_8093_cross_mcp_computation.py`；`--inspect-last` 只读回查，不发送问答。
- 聚焦合同测试：

  ```powershell
  pytest -q "高炉前端数据\智能助手\tests\test_mcp_multi_server_host.py" "tests\test_qa_mcp_parallel_planning.py"
  ```

  结果：`22 passed in 1.65s`。本次没有部署、停启或修改 220.12 服务。
