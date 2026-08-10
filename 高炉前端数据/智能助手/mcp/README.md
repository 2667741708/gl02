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

BF_QA_MCP_SERVER_REGISTRY
  覆盖 Host 侧多服务注册表；默认 `backend/mcp_host/server_registry.json`。
```

### 8093 按需多 MCP Host

问答代理不再固定只挂载一个数据 MCP，而是先根据问题选择服务：

```text
顶压/风量/炉温/趋势             → gl02-data
炉次/铁水或炉渣化验/进料成分    → imes-readonly
上一炉出铁期间的顶压走势         → gl02-data + imes-readonly
```

GL02 继续暴露原工具名以兼容旧确定性路由；IMES 通过 `imes__` 命名空间暴露，例如
`imes__get_current_heat_context`。注册表中的 `excluded_tools` 是生产模型权限边界，
当前明确屏蔽 `query_imes_readonly_sql`；不得仅因它是只读就重新暴露给模型。

“当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？”固定路由到一次
`imes__get_current_previous_heat_si_summary`。它使用 MES 正式 `meltno`，聚合上一炉
全部非空数值 Si 试样，并返回样本数、均值、范围、取样时间、数据来源与缺失状态。

只做服务发现、不查询数据库的本地验证：

```powershell
& 'C:\Users\hmw20\.conda\envs\torch_cuda128_whm\python.exe' `
  tools\test_mcp_multi_server_discovery.py `
  --question '当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？'
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

## 本机三服务 MCP 注册表（扩展 IMES Web）

本机 `backend/mcp_host/server_registry.json` 已在 8093 两服务合同的基础上增加
`imes-web-readonly`，用于把本机经跳板转发的 MES Web 只读接口纳入同一 Host。
当前启用服务和 Host 可见工具数为：

| 服务 | 数据源 | Host 可见工具 |
|---|---|---:|
| `gl02-data` | pSpace/高炉传感器 | 18 |
| `imes-readonly` | Vastbase/MES 业务表 | 14（原生15，排除任意 SQL） |
| `imes-web-readonly` | IMES Web 白名单 HTTP 接口 | 3 |

因此本机全部发现应得到 3 个服务、35 个工具；8093 生产端当前已部署的仍是前两项，
本节是本机扩展，不代表已经把 Web 服务部署到 8093。命名空间工具包括：
`imesweb__get_imes_web_status`、`imesweb__list_imes_web_datasets` 和
`imesweb__query_imes_web_dataset`。

仅做 stdio 服务发现（不查询业务数据库）：

```powershell
& 'C:\Users\hmw20\.conda\envs\torch_cuda128_whm\python.exe' `
  tools\test_mcp_multi_server_discovery.py --all `
  --question '通过 IMES Web 查看今天的炉次化验'
```

IMES Web MCP 只允许 `export_imes_web_readonly.py` 已核实的数据集和日期/分页参数，
不接受任意 URL、任意 SQL 或写入操作。Web 登录存在验证码时，服务需要由当前进程注入
`IMES_WEB_CAPTCHA`，或由运维在受控环境注入 `IMES_WEB_SESSION_COOKIE`；它不会读取浏览器
Cookie，也不会把账号、口令、验证码或会话值放进工具结果。没有验证码/会话时会明确返回
`IMES_WEB_CAPTCHA_REQUIRED`，这不是路由失败。

运行时前置：本机 Web 使用 `http://127.0.0.1:18080/imes.web/`，Vastbase MCP 使用
`127.0.0.1:15433`。两者均由 `tools/imes_22012_relay.py --profile imes` 通过
220.12 跳板建立，转发未运行时分别返回 Web 不可达或 `relay unavailable`，不会静默直连生产网。

## 当前炉次与大概时间段 Si 查询（2026-08-07）

需求编号：`REQ-MCP-IMES-HEAT-SI-SAMPLES-20260807`。

- “当前炉次/当前鸬鹚的硅含量”固定调用 `imes__query_current_heat_chemistry`。正在出铁时只汇总查询时点已经发布的非空数值试样，并明确标记为阶段性结果，不等待堵口，也不把缺失样本当作 0。
- 每条试样返回试样号、通过 `batchno -> v_qpes_mat_final.thankno` 精确关联的铁罐号、Si 和时间。时间优先级为真实取样时间、化验判定时间、结果发布时间；使用后两者时回答会明确名称，不冒充真实取样时间。
- “昨天上午4点到7点左右是哪几个炉次”调用 `imes__query_heat_chemistry_by_time_range`。工具解析日期、钟点、上午/下午、最近N小时等有界时间表达，返回所有与时间段重叠的正式炉次；没有重叠时只返回最近炉次并标记“最近炉次”供用户确认。
- “鸬鹚”作为“炉次”的语音误识别别名进入 IMES 路由，不影响正式 `meltno`。

批量验证：

```powershell
python -m pytest 高炉前端数据\智能助手\tests\test_imes_heat_summary_tools.py 高炉前端数据\智能助手\tests\test_mcp_multi_server_host.py -q
```
