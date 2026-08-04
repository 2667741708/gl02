# 智能助手 MCP 数据查询模块

本目录用于承载 8092 智能助手的数据查询 MCP 能力。

## 文件

```text
bf_data_mcp_server.py
  MCP Server。暴露 GL02 变量、1min 均值库、炉况快照和报表查询工具。

bf_ollama_mcp_bridge.py
  最小 Ollama + MCP Bridge 示例。把 MCP 工具交给 Ollama，并执行 tool call。
```

2026-05-14 起，8092 主问答链路已经把这套 bridge 流程正式接入 `backend/ollama_proxy_server.py`：

```text
/api/qa/chat -> list MCP tools -> Ollama /api/chat tools -> tool_calls -> call MCP tool -> role=tool -> final answer
```

独立 `bf_ollama_mcp_bridge.py` 仍保留为命令行测试和参考实现。

## 安全默认值

- 默认模型：`chiqiong-blast-furnace:latest`
- 默认 Ollama：`http://10.30.220.12:11434`
- 默认 GL02 根：`\冀南钢铁\SIO\GL02`
- 默认只读备份数采：`10.22.181.243:8889`
- 默认 MCP 数据源：`hybrid`，先查 PostgreSQL，本地库无数据或不可用时再只读兜底查 pSpace
- 不提供任意 SQL 工具
- 不默认访问主数采 `10.22.181.244`
- 不默认混用 `\冀南二期\EQ\SI0\GL02`

## 运行方式

安装依赖后可使用：

```powershell
uv run python .\高炉前端数据\智能助手\mcp\bf_data_mcp_server.py
```

命令行桥接测试：

```powershell
$env:OLLAMA_MODEL = "chiqiong-blast-furnace:latest"
$env:OLLAMA_BASE_URL = "http://10.30.220.12:11434"
uv run python .\高炉前端数据\智能助手\mcp\bf_ollama_mcp_bridge.py
```

## 关键环境变量

```text
BF_MCP_DB_PROFILE
  默认读取 gl02_1min_storage.json 的 active_profile。
  本项目运行默认使用 bf_sensor_postgresql；MCP 运行期已禁用 dev_sqlite。

BF_MCP_DATA_SOURCE
  MCP 时序数据源策略。默认 hybrid。
  可设为 hybrid、database 或 pspace。
  hybrid 表示先查 PostgreSQL，本地库无数据时再查 pSpace。

BF_MCP_AUTO_PSPACE_FALLBACK
  hybrid 模式下是否允许 pSpace 兜底，默认 1。

BF_TREND_DB_DSN
  PostgreSQL/Vastbase 连接串。仅 prod_postgresql 使用。

BF_GL02_MAPPING_PATH
  覆盖 GL02 映射配置路径。

BF_GL02_STORAGE_CONFIG
  覆盖 1min 均值库配置路径。

BF_ASSISTANT_PG_SCHEMA
  8092 智能助手 PostgreSQL schema，默认 bf_assistant。
  QA 历史、炉况快照、RAG 知识库均写入该 schema，不再依赖运行期 SQLite。

BF_REPORTS_DIR
  覆盖报表根目录。
```

首次启用 PostgreSQL 助手库时，若应用账号没有建 schema / 建表权限，请先由数据库 owner 执行：

```powershell
psql -d bf_trend -f .\高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql
```

执行后按现场应用账号补齐脚本末尾的 `GRANT` 权限。

## MCP 数据源选择

`get_latest_gl02_value`、`query_gl02_history`、`query_gl02_statistics` 均支持 `source_preference`：

```text
auto / hybrid   先查 PostgreSQL，本地库无数据或不可用时再查 pSpace
database        只查 PostgreSQL 本地库
pspace          只读直查 10.22.181.243 pSpace
```

工具返回的 `source` 会标明实际命中的来源；发生兜底时会带 `fallback=true`、`fallback_reason` 和 `primary_attempt`，便于大模型在回答中说明“本地库未命中，已从 pSpace 补查”。

### 通用单点/多点查询 `query_gl02_sensors`

统一查询任意已配置 GL02 传感器，单个和多个变量使用同一个合同：

```text
variables: 标准变量名、短名、点ID、完整长名、唯一描述或 T_body_L{层}_{方位}
query_type: latest / history / statistics
start_time/end_time: history/statistics 必填，同一批变量共用时间窗
agg: statistics 模式支持 avg/min/max/count/stddev/slope/trend/first/last/all
max_points_per_variable: history 模式每个变量的返回上限
source_preference: auto / database / pspace
```

- 最多接受 80 个查询变量；每个变量独立返回成功、无数据或解析错误，一个失败不会中断整批。
- `latest` 返回当前值和数据时间，`history` 返回 1 分钟历史点，`statistics` 返回同窗统计。
- 不暴露任意 SQL，不写数据库或生产控制。
- 问答层会从完整变量目录匹配标准变量名、短名、点ID、完整长名和唯一描述；“7层炉温”固定展开为 `T_body_L7_A` 至 `T_body_L7_H`。

## 数据绘图工具

### 时间趋势图 `plot_gl02_trends`

保留原有参数兼容，并支持自动选图和可读性增强：

```text
variables: ["T_top"] 或 ["T_top", "P_top"]
start_time/end_time: ISO8601 或 YYYY-MM-DD HH:MM:SS
scale: raw / minmax / zscore
chart_type: auto / line / area / step / scatter / dual_axis / small_multiples
moving_average_points: 0-240，0 表示不叠加移动平均
show_extrema/show_latest: 是否标注极值和最新值
reference_values: {"P_top": 250.0}，仅在 raw 模式画参考线
theme: industrial / light / dark
source_preference: auto / database / pspace
```

`chart_type=auto` 的选择规则：同单位变量使用折线图；两个不同单位变量使用双 Y 轴；三个及以上不同单位变量使用分面图。用户明确要求形态比较时再使用 `scale=minmax` 或 `zscore`。

若单位元数据为空但各序列典型数量级相差 20 倍以上，`auto` 同样会选择双轴或分面，防止大流量曲线把压力、温度等小量级曲线压平。

### 关系与分布图 `plot_gl02_analysis`

```text
analysis_type: auto / correlation_scatter / correlation_heatmap / distribution / boxplot
scale: raw / minmax / zscore
theme: industrial / light / dark
```

- 两变量“关系/相关性”使用 `correlation_scatter`，返回同分钟对齐点数、Pearson 相关系数和线性拟合参数。
- 三个及以上变量“相关矩阵”使用 `correlation_heatmap`，每个单元格同时标注相关系数和对齐点数。
- “分布/直方图”使用 `distribution`；“箱线图/离群点对比”使用 `boxplot`。
- 变量缺失、时间窗无数据或相关分析对齐点不足时返回结构化错误，不生成空白图。

输出 PNG 默认写入：

```text
高炉前端数据/data/mcp_charts/
```

8092 可直接访问：

```text
http://127.0.0.1:8092/data/mcp_charts/<文件名>.png
```

每张 PNG 同目录生成一个 JSON 旁车文件，记录实际图型、变量摘要、数据源、部分失败项、相关系数等审计信息。

### 炉体温度热力趋势矩阵 `plot_gl02_body_temperature_matrix`

面向炉身、炉腹、炉缸各层各方位温度总览。默认行范围为 7–16 层、列范围为 A–F，也支持把 `positions` 扩到 A–H。

```text
start_time/end_time: 通常传最近1小时
start_layer/end_layer: 7-16
positions: ["A","B","C","D","E","F"]，也可传 "A-H"
max_points_per_cell: 每格最多返回的历史点数，默认120
source_preference: auto / database / pspace
```

- 每格底色只编码当前温度，格内 sparkline 只编码所选时间窗趋势，并显示当前值、末次采样时间和升降方向。
- 缺测格固定使用灰色“无数据”，不插值；返回 `available_cell_count/missing_cell_count/coverage_ratio`。
- 问答返回紧凑 60 格摘要，完整统计与数据源写入 JSON 旁车，避免长结果截断图片 URL。
- 口语“7到16层、A-F炉体温度热力矩阵，每格带最近1小时曲线和当前值”由 `qa_mcp_chart_plan()` 确定性路由到该工具。

8093 问答代理会先用 `qa_mcp_chart_plan()` 把中文口语确定性转换为标准变量和图型，再调用上述工具。这样可以避免模型只检索变量却不继续作图，或自行猜测 `T_hot_wind/P_wind` 等非标准变量。模型最终只解释已返回的 MCP 图表结果。

本地直接验证示例：

```bash
python -c "import os, importlib.util, json; from pathlib import Path; from datetime import datetime,timedelta; os.environ.update({'GL02_PGHOST':'127.0.0.1','GL02_PGPORT':'15432','GL02_PGDATABASE':'bf_trend','GL02_PGUSER':'gl02_sync','GL02_PGPASSWORD':'gl02_local_sync','BF_MCP_DB_PROFILE':'bf_sensor_postgresql','BF_MCP_DATA_SOURCE':'database','BF_MCP_AUTO_PSPACE_FALLBACK':'0'}); p=Path(r'高炉前端数据/智能助手/mcp/bf_data_mcp_server.py'); spec=importlib.util.spec_from_file_location('bf_data_mcp_server_test',p); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); latest=mod.get_latest_gl02_value('T_top',source_preference='database'); end=datetime.fromisoformat(str((latest.get('latest') or {}).get('ts')).replace('T',' ')); start=end-timedelta(minutes=60); res=mod.plot_gl02_trends(['T_top','P_top'],start.strftime('%Y-%m-%d %H:%M:%S'),end.strftime('%Y-%m-%d %H:%M:%S'),scale='minmax',source_preference='database'); print(json.dumps({'ok':res.get('ok'),'image_url':res.get('image_url'),'series_count':len(res.get('series') or [])},ensure_ascii=False,indent=2))"
```

## 8092 通用 MCP 工具调用开关

`backend/ollama_proxy_server.py` 中的 8092 问答支持以下环境变量：

```text
BF_QA_MCP_TOOLS
  是否启用通用 tools/tool_calls/call_tool/result 桥接，默认 1。

BF_QA_MCP_TOOL_MODE
  auto / always / off。默认 auto，只在问题包含查询、历史、趋势、报表、画图、对比等意图时启用工具桥接。

BF_QA_MCP_MAX_TOOL_ROUNDS
  非流式回答的最大工具调用轮数，默认 4。

BF_QA_MCP_MAX_RESULT_CHARS
  单次工具结果注入模型的最大字符数，默认 20000。

BF_QA_MCP_DATA_SERVER
  覆盖 MCP 数据服务脚本路径，默认本目录 bf_data_mcp_server.py。

BF_MCP_PYTHON
  启动 MCP stdio server 使用的 Python；默认使用 8092 当前 Python。
```

8092 验证示例：

```bash
python -c "import json, urllib.request; payload={'message':'请调用MCP工具画出最近1小时炉顶温度和顶压的趋势对比图，使用归一化对比，并告诉我图片路径。','stream':False}; req=urllib.request.Request('http://127.0.0.1:8092/api/qa/chat',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'},method='POST'); data=json.loads(urllib.request.urlopen(req,timeout=300).read().decode('utf-8')); print(json.dumps({'ok':data.get('ok'),'tool_calling':data.get('mcp_tool_calling'),'tools':[t.get('tool') for t in data.get('mcp_tool_trace') or []]},ensure_ascii=False,indent=2))"
```

## 统一业务对象目录

`catalog/`使用统一合同描述传感器、炉次、铁水/炉渣化验、进料化学成分、日报、
历史问答、计算能力和图表类型。传感器对象由运行时`VARIABLES`动态转换，因此
220.12会按实际映射扩展全量传感器，本地缺少可选映射时仍保留核心变量和18个
静压力点。

统一目录工具：

- `list_business_objects`：按类型、能力和状态列出；
- `search_business_objects`：跨对象类型口语搜索；
- `get_business_object`：按标准object_id取完整合同。

旧`find_gl02_variables`继续用于已确定为GL02传感器的细点位匹配。

