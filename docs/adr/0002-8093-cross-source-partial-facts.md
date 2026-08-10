# ADR-0002：8093 跨源复合查询的部分事实与禁止分析

- 状态：已接受，待 8093 受控部署
- 日期：2026-08-05
- 需求：`REQ-8093-CROSS-SOURCE-MCP-20260805`
- 取代：无
- 引用：[[0001-8093-multi-mcp-host]]

## 背景

ADR-0001 §3 规定"选中的任一服务不可用时，跨数据源问题整体失败，不返回不完整结论"。
这个策略在 MES 服务完全不可达时是正确的——没有炉次信息就不能做任何炉次相关的回答。

但生产中更常见的是"GL02 传感器临时无数据"或"MES 某炉次化验试样缺失"场景：
用户问"上一炉 Si + 顶压/冷风压力/富氧率"——MES 正常返回 Si=0.45%，但 GL02 的
冷风压力传感器恰好离线。如果整题失败，用户会看到"数据库查询失败"而不是"Si 是
0.45%，但冷风压力暂时没有数据"。

ADR-0001 的全有或全无策略对跨源复合问题的可用性影响过大，需要修正。

## 决策

1. **允许部分事实**。当跨源查询中至少一个请求事实成功时，返回已有事实并标记
   `partial=true`，同时列出缺失事实和来源状态。

2. **缺失全部事实时整题失败**。如果所有数据源都没有返回有效数据（成功事实数=0），
   `ok=false`，这与 ADR-0001 的全有或全无精神一致。

3. **禁止不完整分析**。当任一 `required_for_analysis` 步骤失败时，设置
   `analysis_allowed=false`，完全跳过模型分析调用，只输出确定性事实格式。
   - 这比插入"禁止分析"Prompt 更可靠——Prompt 可能被模型忽略或绕过。
   - 确定性格式器只列出事实、来源与缺失，不生成比较、预测或操作建议。

4. **展示性失败不影响分析**。图表、热力矩阵等展示性步骤标记为
   `required_for_answer=false, required_for_analysis=false`——它们的失败使
   `complete=false` 但不禁止分析。

5. **炉次号不猜测**。口语简写（`072`）在 72 小时内查不到时返回
   `HEAT_REFERENCE_NOT_FOUND`，绝不构造"今天的 072 炉"。
   多匹配返回 `HEAT_REFERENCE_AMBIGUOUS`。

6. **P_top 语义保持**。`P_top`（炉顶压力）不替换为 `P_top_gas_A-D`
   （上升管压力），两者业务含义不同，各走各的查询路径。

## 后果

- 跨源查询可用性明显提升——一个来源临时无数据不再导致整题失败。
- 但调用方必须检查 `mcp_cross_source.partial` 和 `analysis_allowed` 标志，
  不能假设有数据就是完整答案。
- 部分事实的对话证据会保存缺失标记，后续追问"那冷风压力呢"时不会误用缓存值。
- 启用开关 `BF_QA_MCP_CROSS_SOURCE_ENABLED=0` 可完全回退到 ADR-0001 行为。

## 实现

- [backend/mcp_host/cross_source_plan.py]：合同定义
- [backend/mcp_host/cross_source_executor.py]：DAG 执行器
- [backend/ollama_proxy_server.py]：`build_cross_source_plans()` + `format_cross_source_answer()`
- [mcp/imes_relay_mcp_server.py]：`resolve_spoken_heat_reference` + 扩展 `query_hot_metal_chemistry_by_heat`
- [backend/mcp_conversation_context.py]：`context_with_cross_source_snapshot`
