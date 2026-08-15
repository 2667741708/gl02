# MCP 智能工具系统九阶段升级总表

> - 状态：路线图，不是完成清单
> - 最后核对：2026-08-11
> - 完成证据：以 [需求追踪](../docs/requirements_traceability.md)、[测试索引](../docs/test_reference.md)
>   和 [阶段交接](../docs/handoffs/) 为准；未找到实现、测试和现网验收三方证据的阶段不得标为已完成。

总需求：`REQ-MCP-INTELLIGENT-TOOL-SYSTEM-20260726`

## 总体目标

把现有“固定口语路由 + MCP工具调用”升级为可恢复、可扩展、低延迟、可审计的
智能工具系统。模型负责理解与规划，统一目录负责业务对象解析，策略层负责安全，
MCP负责确定性只读执行。

## 阶段总表

| 阶段 | 名称 | 主要交付物 | 当前状态 |
|---|---|---|---|
| 0 | 基线与回退 | 核心文件SHA-256、快照、校验和恢复脚本 | 已完成 |
| 1 | 受控工具编排 | 模型多轮工具循环、Schema校验、调用上限 | 已完成 |
| 2 | 统一业务对象目录 | 传感器、炉次、化验、报表、计算、图表统一合同 | 已完成第一版 |
| 3 | 结构化对话状态 | 保存变量、时间窗、分析目标和追问继承 | 已完成第一版 |
| 4 | 计划—执行状态机 | 一次性计划、依赖步骤、失败修正和最终证据 | 已完成第一版 |
| 5 | 权限与风险分级 | L0-L4工具等级、角色权限、只读和范围控制 | 部分完成 |
| 6 | 低延迟执行 | 快速/标准/Agent三级路径、复合工具、缓存和预算 | 已完成第二版 |
| 7 | 运行审计与可观测 | run/call/evidence记录、耗时、错误、健康接口 | 待执行 |
| 8 | 全面测试与生产发布 | 契约、单元、E2E、性能、回退和生产验收 | 持续执行 |

## 阶段0：基线与回退

交付：

- 保存口语路由、工具策略和MCP服务文件；
- 记录SHA-256；
- 提供只读校验和显式恢复命令；
- 每次220.12部署生成远端时间戳备份。

入口：

- [基线清单](../backups/mcp_route_baseline_20260726_1552/manifest.json)
- [恢复脚本](../tools/restore_mcp_route_baseline.py)

## 阶段1：受控工具编排

交付：

- 模型自主选择MCP工具；
- 运行时工具白名单；
- JSON Schema参数校验；
- 最大轮数、最大调用数、载荷和数组限制；
- 流式问答完成多轮工具闭环。

入口：

- [工具策略](../高炉前端数据/智能助手/backend/mcp_tool_policy.py)
- [问答代理](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)

## 阶段2：统一业务对象目录

统一合同至少包含：

```json
{
  "object_id": "P_top",
  "object_type": "sensor",
  "display_name": "炉顶压力",
  "aliases": ["顶压", "炉顶煤气压力"],
  "unit": "kPa",
  "capabilities": ["latest", "history", "statistics", "plot", "correlation"],
  "status": "enabled",
  "executor": {
    "service": "blast-furnace-gl02-data-mcp",
    "tools": ["query_gl02_sensors", "plot_gl02_analysis"]
  }
}
```

目录范围：

- 传感器和18个静压力点；
- 炉次、铁水化验、炉渣化验、进料化学成分；
- 日报和历史问答；
- 统计、相关性和增强特征等计算能力；
- 趋势、矩阵、相关、分布和箱线等图表能力。

交付文件：

```text
mcp/catalog/catalog_manifest.json
mcp/catalog/business_object.schema.json
mcp/catalog/sensors.json
mcp/catalog/heat_analysis.json
mcp/catalog/calculation_tools.json
mcp/catalog/chart_capabilities.json
mcp/catalog/knowledge_assets.json
mcp/business_object_catalog.py
```

## 阶段3：结构化对话状态

状态合同：

```json
{
  "selected_objects": ["P_top", "DP_total"],
  "time_range": {"mode": "relative", "minutes": 30},
  "analysis_goal": "correlation",
  "preferred_chart": "correlation_scatter",
  "last_evidence_ids": [],
  "pending_clarification": null
}
```

目标是支持“和刚才那个比较”“画出来”“换成两小时”“再加透气性指数”等追问。

## 阶段4：计划—执行状态机

标准状态：

```text
PLAN → VALIDATE → EXECUTE → OBSERVE → REPLAN/ANSWER
```

默认一次规划，最多一次失败修正。独立步骤可批量执行；有依赖的步骤按拓扑顺序执行。

## 阶段5：权限与风险分级

| 等级 | 能力 | 默认策略 |
|---|---|---|
| L0 | 目录检索 | 直接只读 |
| L1 | 最新值、历史值 | 只读、范围校验 |
| L2 | 统计、计算、绘图 | 数据量、超时和缓存 |
| L3 | 大范围批量分析、导出 | 角色权限、限流和审计 |
| L4 | 生产写入 | 当前禁止 |

## 阶段6：低延迟执行

三级路径：

```text
固定快速路径 → 标准复合工具路径 → 27B Agent路径
```

已完成第一版：27B低温度、小上下文、小输出，规划不注入完整炉况/RAG；相关性
问题由3次工具降为1次复合工具；提供缓存和45秒预算。

## 阶段7：运行审计与可观测

计划新增：

```text
bf_assistant.mcp_runs
bf_assistant.mcp_call_events
bf_assistant.mcp_evidence_links
GET /api/admin/mcp/tools
GET /api/admin/mcp/runs
GET /api/admin/mcp/runs/{run_id}
GET /api/admin/mcp/health
```

审计不得记录数据库密码、连接串、完整系统提示或未经净化的敏感参数。

## 阶段8：全面测试与发布

每阶段必须覆盖：

- 合同校验；
- 单元测试；
- MCP stdio工具测试；
- 8093/8094真实口语E2E；
- 图片`200 image/png`；
- 延迟对比；
- 8768/8770进程守卫；
- 基线恢复验证。

## 阶段推进规则

1. 每阶段先形成合同和验收标准；
2. 保留旧接口兼容，不一次删除固定路由；
3. 新能力通过测试后再部署8093/8094；
4. 8768实时数据服务不得因问答升级而重启；
5. 阶段完成后更新本表状态、实现链接、测试命令和现网证据。

## 阶段2实施结果（2026-07-26）

已建立：

- 统一JSON Schema合同；
- catalog manifest；
- 传感器、炉次/化验、计算、图表、知识资产目录；
- 运行时传感器映射转换器；
- `list_business_objects`、`search_business_objects`、`get_business_object`三个
  MCP目录工具；
- 模型规划优先使用统一目录，旧`find_gl02_variables`继续兼容。

本地缺少可选GL02全量映射文件时，目录仍包含P_top核心兜底和18个静压力点，
合计19个传感器；220.12运行时会把其实际`VARIABLES`全量转换为统一合同。

测试：`61 passed`。8093实测搜索铁水硅含量命中`hot_metal_chemistry`，
8094实测搜索相关散点图命中`correlation_chart`，均只调用一次
`search_business_objects`。

验收证据：
[统一业务对象目录验收](../logs/8093_8094_business_object_catalog_acceptance_20260726.json)。

## 阶段3、4、6本轮实施结果（2026-07-26）

阶段3已建立紧凑对话状态并写入问答消息的`hidden_context_json`：

- 保存`selected_objects/time_range/analysis_goal/preferred_chart`；
- 支持“画出来”“换成两小时”“再加透气性”“北尺也加上”“一张图”；
- 新问题明确给出多个对象时替换旧对象，只有“再加/也加/和……比较”等追问才合并；
- 状态不保存SQL、密码、完整炉况资料或系统提示。

阶段4第一版使用：

```text
确定性计划/27B计划 → 实时Schema校验 → MCP执行 → 结果观察 → 确定性回答/继续规划
```

明确的`latest/history/statistics/plot/correlation`优先生成一次批量计划；复杂且无法
确定工具的问题才进入27B小上下文规划。模型规划仍受最大轮数、调用数、参数大小、
数组大小和只读工具白名单约束。

阶段6第二版新增：

- 明确传感器当前值改为一次`query_gl02_sensors`批量调用；
- 确定性查询/图表使用事实格式器直接回答，不再额外调用27B；
- “无Prompt模板”只作为MCP stdio直连测试模式，不删除生产口语路由和模板；
- 机器变量ID必须精确匹配，未知ID不得模糊落到其他传感器；
- 本地最小目录补入经核实的`DP_total → SIO_GL02_BT_T0132`。

验收：

- 本地相关回归：`76 passed`；
- 8093关键实时口语：4/4自动通过，中位总耗时约`1.12s`；
- 8093少信息多轮：2个会话、7轮，7/7通过，图像均`200 image/png`；
- 无Prompt/无27B/无RAG直连：4/4通过，总耗时约`3.73s`；
- 最终部署`2026-07-26 18:21:19`，8093/8094 PID为`16636/13924`，
  受保护8768/8770在该次部署前后保持`12672/12956`。

证据：

- [少信息多轮验收](../logs/8093_mcp_context_followups_20260726.json)
- [四个关键口语验收](../logs/8093_phase3_four_priority_prompts_20260726.json)
- [无Prompt直连验收](../logs/mcp_direct_no_prompt_20260726.json)
- [部署后服务与哈希诊断](../logs/22012_8093_phase3_postdeploy_diagnostic_20260726.json)

## 阶段4多服务 P0 实施结果（2026-08-05）

阶段4从单 MCP Session 升级为按领域选择的多 Client Host：

- `gl02-data`：传感器、图表、报表、历史问答和统一目录；
- `imes-readonly`：正式炉次、铁水/炉渣化验和进料成分；
- 单源问题只启动一个服务，跨源问题同时启动两个；
- GL02 保持旧工具名，IMES 使用 `imes__` 命名空间；
- 生产 Host 排除 `query_imes_readonly_sql`；
- “当前炉次 + 上一炉 Si 平均值”使用一次复合工具，输出正式 `meltno`、全部有效试样、样本数、均值、范围、时间、来源和缺失状态。

本地相关回归 `38 passed`；真实 MCP SDK 发现验证 IMES 14、GL02 18、跨源 32 个 Host 可见工具。2026-08-05 已完成 220.12 受控部署和真实 MES 单次 SSE，上一炉有效 Si 试样数为 0 时正确返回 `NO_SI_SAMPLES`。显式跨服务 DAG、连接 TTL、Schema 缓存和完整证据审计仍分别属于阶段4后续、阶段6/7工作，不得标成全部完成。

## 2026-08-06：8093 跨源 MCP 稳定调用与守护进程上线

- 已将 `CrossSourcePlan`、`FactRequest`、按能力路由、DAG 执行器、统一目录和事实提取逻辑同步到 220.12 的 8093 服务。
- MES 与 pSpace/GL02 请求现在可并行执行；炉身温度使用 `gl02-extended` 能力，`P_top` 只进入传感器能力，不再误路由到历史炉况工具。
- 正式 `meltno`、口语炉次解析、样本时间、单位、来源、缺失原因和 `analysis_allowed` 门控已纳入统一结果合同。
- 8093 新增 `/api/qa/mcp/health` 只读探针，守护进程只检查并恢复 `BFV4PreviewProxy8093`，不操作 8768、8094、8770 或数据库服务。
- 本地专项测试 `51 passed`，跨源及相关回归 `108 passed`，专项测试占位项 `0`；生产已完成 6 类真实口语验收。
- 2026-08-06 受控部署仅更换 8093 进程，8093 新 PID 为 `12368`；8768、8094、8770 PID 保持不变。部署备份和回滚证据见 `docs/handoffs/2026-08-06-8093-cross-source-mcp-deployment.md`。
