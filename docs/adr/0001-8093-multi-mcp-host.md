# ADR-0001：8093 使用按领域选择的多 MCP Host

- 状态：已接受并完成 220.12 受控部署
- 日期：2026-08-05
- 需求：`REQ-8093-MULTI-MCP-HOST-20260805`

## 背景

8093 原问答循环每次只启动 `BF_QA_MCP_DATA_SERVER` 指向的一个 stdio 服务，实际
只能看到 GL02 数据 MCP。MES/IMES 炉次与化验工具虽然存在于独立 MCP 服务和统一
业务目录中，却没有可执行 Client，因此“当前炉次 + 上一炉次 Si 平均值”会进入
模型多轮试探，最后以查询轮数超过上限结束。

当前只有两个正式服务、约三十个工具，延迟约束又要求常用问题尽量不经过额外模型
规划。IMES 服务还包含供运维诊断的任意只读 SQL，不能直接暴露给生产问答模型。

## 决策

1. 在 `backend/mcp_host/` 建立 Host 侧服务注册表、领域路由和 Client Manager；不使用
   `backend/mcp/`，避免遮蔽官方 Python 包 `mcp`。
2. GL02 工具保留既有裸名称以兼容确定性路由；IMES 工具统一暴露为
   `imes__<native_name>`，Host 保存暴露名到服务会话/原生名的映射。
3. 领域路由先根据问题选择 `gl02-data`、`imes-readonly` 或二者，只启动所需 stdio
   服务；选中的任一服务不可用时，跨数据源问题整体失败，不返回不完整结论。
4. 高频问题由业务复合工具一次完成。首个复合工具
   `get_current_previous_heat_si_summary` 使用 MES 正式 `meltno`，返回上一炉全部有效
   Si 试样及 count/mean/min/max、取样时间、来源与缺失状态。
5. `query_imes_readonly_sql` 保留在 IMES Server 供授权运维直连，但由 Host 注册表
   `excluded_tools` 屏蔽，8093 模型看不到也不能调用。
6. P0 每个问答请求建立并关闭所选 stdio Client；空闲 TTL、Schema 缓存、显式 DAG
   与持久化证据审计放入后续阶段。

## 结果

- 8093 可以在不提高模型轮数的情况下执行常用 MES 查询，并能为未来跨 MES/GL02
  问题同时挂载两个只读服务。
- 服务、工具和权限边界成为配置合同，统一目录中的 `executor.service` 可以与实际
  Host 服务 ID 对齐。
- 每请求启动 stdio 仍有冷启动成本；后续可在不改变工具合同的情况下增加 TTL。
- 当前/上一炉判定依赖 `public.t_ipes_cond` 的 `opentime/workdate/closetime`；部署前后
  必须用真实 MES 数据复核业务排序口径。

## 未采用方案

- 仅提高模型轮数：不能修复 IMES Client 根本未挂载的问题，还会增加 27B 延迟。
- 把所有工具永久注入模型：扩大上下文与权限面，且会暴露任意只读 SQL。
- 让模型生成 SQL 或代码：当前规模没有必要，生产安全与审计成本过高。
- 立刻引入通用工具搜索三件套：两个服务规模下会增加不必要的规划轮次。

## 验证

- 单元/回归：`test_mcp_multi_server_host.py`、`test_imes_heat_summary_tools.py` 及既有
  对话、延迟、Schema 策略回归共 `38 passed`。
- 真实 MCP SDK `tools/list`：IMES 问题选择 1 个服务并暴露 14 个生产工具；GL02
  问题选择 1 个服务并暴露 18 个工具；跨源问题选择 2 个服务并暴露 32 个工具。
- `query_imes_readonly_sql` 在 Server 原生列表中存在，但不在 Host 暴露列表中。
- 受控部署与真实 MES 验收：[交接记录](../handoffs/2026-08-05-8093-multi-mcp-deploy.md)。
