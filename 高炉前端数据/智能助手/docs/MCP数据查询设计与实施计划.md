# 冀南钢铁 GL02 数据查询 MCP 设计与实施计划

确认日期：2026-05-08

更新日期：2026-05-13

## 1. 目标

为 8092 智能助手增加一层可信数据查询能力，让本地 Ollama 大模型可以通过 MCP 工具协助用户查询 PostgreSQL 数据库、pSpace 只读实时/历史数据、炉况快照、GL02 变量字典、1 分钟均值历史数据和报表内容。

核心原则：

- Ollama 只负责理解用户意图、选择工具和组织回答。
- MCP Server 负责安全访问数据库、变量配置、报表文件和必要的只读数据源。
- 不允许大模型直接拼 SQL。
- 不允许用户通过聊天入口执行任意 SQL。
- 默认数据范围固定为 `\冀南钢铁\SIO\GL02`。
- 默认时序查询策略为 `hybrid`：先查 PostgreSQL，本地库无数据或不可用时再只读兜底查询备份数采 pSpace。
- pSpace 只读兜底只访问备份数采，不默认访问主数采 `10.22.181.244`。

## 2. 当前系统事实

Ollama：

- Base URL：`http://10.30.220.12:11434`
- 当前主模型：`chiqiong-blast-furnace:latest`
- 固定调用策略：所有 `/api/generate` 和 `/api/chat` 请求必须显式传入 `"think": false`
- 业务侧只消费最终 `response` 或 `message.content`

8092 智能助手：

- 主后端：`高炉前端数据/智能助手/backend/ollama_proxy_server.py`
- PostgreSQL 助手库：schema `bf_assistant`
- QA / 炉况快照主要表：`bf_assistant.furnace_snapshots`、`bf_assistant.qa_conversations`、`bf_assistant.qa_messages`
- RAG 知识库主要表：`bf_assistant.rag_document`、`bf_assistant.rag_chunk`、`bf_assistant.rag_query_log`
- 旧 `bf_qa.sqlite3`、`bf_unified_vectors.sqlite3` 只作为一次性迁移来源，不作为运行期依赖
- 智能助手专属代码优先放在 `高炉前端数据/智能助手/`

GL02 变量配置：

- 映射配置：`趋势分析/trend_backend/config/gl02_sio_mapping.json`
- 默认根节点：`\冀南钢铁\SIO\GL02`
- 禁止默认混用：`\冀南二期\EQ\SI0\GL02`
- 当前高置信变量包括：`PI`、`DP_total`、`DP_lower`、`DP_upper`、`P_top`、`P_top_gas_A-D`、`L`、`T_blast`、`P_blast`、`P_blast_cold`、`Q_blast`、`PCI_set`
- 中置信或替代变量必须在回答中明确说明，不得包装成精确确认点
- “炉体温度/炉身温度”是 7-16 层 A-H 变量族，不得误解析为 `T_blast` 热风温度；用户未指定层号和方位时，应先澄清或返回变量族说明
- 用户指定具体层位和方位时，例如 `7层A炉体温度`、`16层H炉身温度`，MCP 可按 `SIO_GL02_BT_T0155..SIO_GL02_BT_T0234` 自动映射为具体 BT 炉体温度点。
- `T_top` 是由 `T_top_A`、`T_top_B`、`T_top_C`、`T_top_D` 查询时派生的平均值，返回时必须标注 `DERIVED_AVERAGE`。

GL02 1 分钟均值库：

- 配置文件：`趋势分析/trend_backend/config/gl02_1min_storage.json`
- 当前运行库：PostgreSQL schema `bf_sensor`
- 旧开发 SQLite：`趋势分析/trend_backend/data/gl02_1min.sqlite3` 只作为历史配置说明，MCP 运行期已禁用该 profile
- 当前核心表：`sensor_registry`、按月分区的 `one_minute_values`、`sync_state`、`sync_runs`
- 历史口径：`HisReadProcessed`、`PS_HIS_AVERAGE`、`interval_seconds=60`

## 3. 推荐架构

```text
8092 智能助手页面
  ↓ /api/qa/chat
高炉前端数据/智能助手/backend/ollama_proxy_server.py
  ↓
Ollama MCP Bridge
  ↓ tools schema
Ollama chiqiong-blast-furnace:latest
  ↓ tool_calls
MCP Server: bf_data_mcp_server.py
  ├─ GL02 变量字典
  ├─ PostgreSQL GL02 1min 均值库
  ├─ pSpace 只读实时/历史兜底
  ├─ PostgreSQL 8092 QA / 炉况快照 / RAG
  ├─ 报表 Markdown 文件
  └─ 数据源命中与兜底来源标注
```

## 4. 文件布局

```text
高炉前端数据/智能助手/mcp/
  ├─ README.md
  ├─ bf_data_mcp_server.py
  └─ bf_ollama_mcp_bridge.py
```

说明：

- `bf_data_mcp_server.py` 是 MCP Server，暴露安全工具。
- `bf_ollama_mcp_bridge.py` 是最小 Agent/Bridge 示例，把 MCP 工具 schema 交给 Ollama，并执行 tool call。
- 后续正式接入 8092 时，可把 bridge 逻辑合入 `ollama_proxy_server.py` 的 `/api/qa/chat` 流程。

## 5. MCP 工具清单

第一阶段工具：

```text
find_gl02_variables(keyword, limit)
get_gl02_variable_info(variable)
list_gl02_available_variables(include_medium_confidence, limit)
get_latest_gl02_value(variable, source_preference)
query_gl02_history(variable, start_time, end_time, limit, source_preference)
query_gl02_statistics(variable, start_time, end_time, agg, source_preference)
get_latest_furnace_snapshot()
search_qa_messages(keyword, limit)
list_recent_reports(report_type, start_date, end_date, limit)
read_report_excerpt(report_path, mode, max_chars)
```

工具选择建议：

```text
用户问“热风压力是什么点？” → get_gl02_variable_info
用户问“热风压力现在多少？” → find_gl02_variables → get_latest_gl02_value
用户问“过去一小时热风压力走势” → find_gl02_variables → query_gl02_history
用户问“过去一小时平均/最大/最小” → query_gl02_statistics
用户问“当前炉况如何？” → get_latest_furnace_snapshot + 必要变量 latest/history
用户问“之前有没有问过某问题？” → search_qa_messages
用户问“今天日报里怎么写？” → list_recent_reports → read_report_excerpt
```

## 6. 数据源优先级

实时/最新值：

```text
1. PostgreSQL bf_sensor.one_minute_values / 配置 profile 对应 1min 均值库
2. 若 source_preference=auto/hybrid 且本地库无数据，则只读查询 pSpace 243
3. furnace_snapshots 只用于炉况上下文，不再伪装为传感器最新值
```

历史曲线：

```text
1. PostgreSQL bf_sensor.one_minute_values / 配置 profile 对应 1min 均值库
2. 若 source_preference=auto/hybrid 且本地库无数据，则只读查询 pSpace HisReadProcessed
```

时间参数：

```text
对外工具参数使用 ISO8601。
PostgreSQL 查询保留 timestamptz 查询口径。
pSpace 查询前统一转换为 Asia/Shanghai 本地时间。
若旧配置仍残留 dev_sqlite profile，MCP 会直接拒绝并提示改用 `bf_sensor_postgresql` 或 pSpace。
start_time 必须小于或等于 end_time。
```

变量解释：

```text
1. 趋势分析/trend_backend/config/gl02_sio_mapping.json
2. 未来可选 gl02_sensor_registry
```

报表上下文：

```text
1. 高炉前端数据/data/reports/
2. 只允许读取该根目录下 Markdown/Text 文件片段
```

## 7. 返回字段契约

涉及 GL02 变量的工具，必须尽量返回：

```json
{
  "variable_name": "P_blast",
  "short_name": "SIO_GL02_BT_T0149",
  "point_id": "\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0149",
  "tag_long_name": "\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0149",
  "tag": "\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0149",
  "description": "2号炉本体_高炉本体热风压力",
  "unit": "",
  "path_group": "BT",
  "status": "available",
  "confidence": "high",
  "source_branch": "BT",
  "notes": "",
  "max_history_range": {
    "status": "未探明"
  }
}
```

最新值返回：

```json
{
  "ok": true,
  "variable": {},
  "latest": {
    "ts": "2026-05-08T10:11:00+08:00",
    "value": 123.45,
    "quality": "Good(CALCULATED)",
    "aggregate": "PS_HIS_AVERAGE",
    "interval_seconds": 60
  },
  "source": {
    "type": "gl02_1min_average",
    "read_policy": "readonly"
  }
}
```

无数据返回：

```json
{
  "ok": false,
  "error": "NO_DATA",
  "message": "没有查询到数据",
  "variable": {}
}
```

## 8. 安全边界

禁止项：

- 禁止暴露 `run_sql(sql)` 工具。
- 禁止让模型生成 SQL。
- 禁止查询未登记的 tag。
- 禁止默认访问 `10.22.181.244`。
- 禁止默认混用 `\冀南二期\EQ\SI0\GL02`。
- 禁止把 pSpace 账号、密码、服务器密码、Cookie、Token、API Key 写入 prompt、日志、Markdown 或前端配置。
- 禁止从报表工具读取允许根目录之外的文件。
- 禁止把缺失变量伪造成已有数据，例如 `GasUtil`、`L_south`、`L_north`。

允许项：

- 只读查询 PostgreSQL。
- hybrid 模式下只读查询备份 pSpace 作为本地库缺数兜底。
- 查询 `gl02_sio_mapping.json` 中登记的变量。
- 查询 `高炉前端数据/data/reports/` 下的 Markdown/Text 报表片段。
- 对中置信或替代变量做查询，但必须在回答中说明置信状态。

## 9. Ollama Prompt 约束

推荐系统提示词要点：

```text
你是冀南钢铁 GL02 高炉数据助手。
涉及实时值、历史值、变量点位、报表事实时，必须调用工具查询，不得编造。
默认高炉范围是 \冀南钢铁\SIO\GL02，不得混用 \冀南二期\EQ\SI0\GL02。
调用 chiqiong-blast-furnace:latest 时始终 think:false。
如果变量 status 是 available_substitute、derived、derived_substitute，回答中必须说明替代/派生口径。
如果 confidence 不是 high，回答中必须说明置信等级。
如果工具返回无数据或变量缺失，必须明确说明，不得补造数值。
如果 source.fallback=true，必须说明“本地 PostgreSQL 未命中，已从 pSpace 只读补查”。
```

## 10. 分阶段实施路线

第一阶段：独立最小可用

```text
1. 实现 bf_data_mcp_server.py
2. 实现变量检索、变量解释、最新值、历史、统计、快照、报表读取工具
3. 实现 bf_ollama_mcp_bridge.py
4. 用命令行验证 Ollama 能完成 find → query → answer 工具链
```

第二阶段：接入 8092

```text
1. 把 bridge 的工具调用循环接入 /api/qa/chat
2. 工具调用阶段可先使用非流式
3. 最终回答继续走现有流式输出与会话持久化
4. 只保存清洗后的最终回答，不保存 thinking 或半截增量
```

第三阶段：生产增强

```text
1. 增加审计日志：用户问题、工具名、变量、时间范围、返回行数
2. 增加用户/角色权限过滤
3. 增加 latest 短 TTL 缓存
4. 增加 PostgreSQL 连接池
5. 完善 pSpace 兜底审计与错误分级
6. HTTP 模式必须加鉴权，内网也不裸奔
```

